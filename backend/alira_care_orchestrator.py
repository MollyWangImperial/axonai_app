"""Bounded adaptive care orchestration for Alira.

The module makes repeatable scheduling and content-selection decisions from
patient-reported and assessment evidence. It deliberately cannot activate
novel clinical content; unsupported ideas are emitted as reviewable drafts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


CARE_POLICY_VERSION = "alira-care-v1"
MAX_CHECK_IN_QUESTIONS = 4
APPROVED_ASSESSMENT_PACKAGES = {"initial", "upper_limb", "hand", "lower_limb", "balance"}


QUESTION_BANK: Dict[str, Dict[str, Any]] = {
    "sudden_change": {
        "id": "sudden_change",
        "domain": "safety",
        "question": "Since your last check-in, have you had any sudden new weakness, facial droop, speech change, severe headache, collapse, chest pain, or trouble breathing?",
        "type": "single",
        "options": ["no", "yes"],
        "required": True,
    },
    "falls": {
        "id": "falls",
        "domain": "safety",
        "question": "Have you fallen or nearly fallen since your last check-in?",
        "type": "single",
        "options": ["no", "near_fall", "fall_no_injury", "fall_with_injury"],
        "required": True,
    },
    "pain": {
        "id": "pain",
        "domain": "tolerance",
        "question": "How much pain is affecting movement today, from 0 to 10?",
        "type": "number",
        "min": 0,
        "max": 10,
        "required": True,
    },
    "fatigue": {
        "id": "fatigue",
        "domain": "tolerance",
        "question": "How much is fatigue limiting what you can do today?",
        "type": "single",
        "options": ["not_at_all", "a_little", "quite_a_bit", "a_lot"],
        "required": False,
    },
    "function_change": {
        "id": "function_change",
        "domain": "function",
        "question": "Compared with your last check-in, do your everyday movements feel easier, about the same, or harder?",
        "type": "single",
        "options": ["much_easier", "a_little_easier", "about_the_same", "a_little_harder", "much_harder"],
        "required": True,
    },
    "exercise_tolerance": {
        "id": "exercise_tolerance",
        "domain": "exercise",
        "question": "How did your current exercises feel the last time you tried them?",
        "type": "single",
        "options": ["not_tried", "too_easy", "about_right", "too_hard", "stopped_for_symptoms"],
        "required": False,
    },
    "goal_activity": {
        "id": "goal_activity",
        "domain": "goal",
        "question": "How did the everyday activity you most want to improve feel this week?",
        "type": "single",
        "options": ["not_tried", "easier", "about_the_same", "harder", "needed_more_help"],
        "required": False,
    },
    "walking_confidence": {
        "id": "walking_confidence",
        "domain": "walking",
        "question": "How confident did you feel while walking or transferring today?",
        "type": "single",
        "options": ["not_applicable", "confident", "a_little_unsure", "very_unsure", "needed_more_help"],
        "required": False,
    },
    "hand_use": {
        "id": "hand_use",
        "domain": "hand",
        "question": "How much did you use your affected hand in everyday activities today?",
        "type": "single",
        "options": ["not_at_all", "a_little", "often", "most_activities"],
        "required": False,
    },
}


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest(items: Sequence[Dict[str, Any]], key: str = "created_at") -> Optional[Dict[str, Any]]:
    dated = [(date, item) for item in items if (date := _as_utc(item.get(key)))]
    return max(dated, key=lambda pair: pair[0])[1] if dated else None


def _days_since(item: Optional[Dict[str, Any]], now: datetime, key: str = "created_at") -> Optional[int]:
    when = _as_utc((item or {}).get(key))
    return max(0, (now - when).days) if when else None


def _answer(check_in: Optional[Dict[str, Any]], question_id: str, default: Any = None) -> Any:
    answers = (check_in or {}).get("answers") or {}
    return answers.get(question_id, default) if isinstance(answers, dict) else default


def _issue_domains(assessment: Optional[Dict[str, Any]], profile: Dict[str, Any]) -> List[str]:
    domains = set()
    for area in profile.get("affected_areas") or []:
        value = str(area).lower()
        if "upper" in value:
            domains.add("upper_limb")
        if "lower" in value:
            domains.add("lower_limb")
    for issue in (assessment or {}).get("functional_issues") or []:
        code = str(issue.get("code") or "").upper()
        domain = str(issue.get("phenotype_domain") or "").lower()
        if "hand" in domain or any(token in code for token in ("HAND", "PINCH", "GRASP", "BILATERAL")):
            domains.add("hand")
        if any(token in domain for token in ("gait", "balance", "lower")) or any(token in code for token in ("GAIT", "BALANCE", "LOWER", "WALK")):
            domains.add("lower_limb")
        if not domains or any(token in code for token in ("REACH", "SHOULDER", "TRUNK", "H2M")):
            domains.add("upper_limb")
    return [domain for domain in ("upper_limb", "hand", "lower_limb") if domain in domains]


def _safety_status(check_in: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    sudden_change = str(_answer(check_in, "sudden_change", "no")).lower() == "yes"
    fall = str(_answer(check_in, "falls", "no")).lower()
    try:
        pain = float(_answer(check_in, "pain", 0) or 0)
    except (TypeError, ValueError):
        pain = 0
    function_change = str(_answer(check_in, "function_change", "")).lower()
    tolerance = str(_answer(check_in, "exercise_tolerance", "")).lower()

    if sudden_change:
        return {
            "status": "emergency",
            "message": "Possible new stroke or medical emergency symptoms were reported. Stop the app activity and call emergency services now; in the UK call 999.",
            "blocks_assessment": True,
            "blocks_exercise": True,
            "requires_clinician_review": True,
        }
    if fall == "fall_with_injury":
        return {
            "status": "urgent_review",
            "message": "A fall with possible injury was reported. Do not continue unsupervised exercise until urgent clinical advice has been obtained.",
            "blocks_assessment": True,
            "blocks_exercise": True,
            "requires_clinician_review": True,
        }
    if pain >= 7 or tolerance == "stopped_for_symptoms" or function_change == "much_harder" or fall == "fall_no_injury":
        return {
            "status": "clinical_review",
            "message": "A meaningful change was reported. Pause progression and contact the stroke rehabilitation team before changing the plan.",
            "blocks_assessment": False,
            "blocks_exercise": tolerance == "stopped_for_symptoms" or pain >= 7,
            "requires_clinician_review": True,
        }
    return {
        "status": "clear",
        "message": "No immediate safety trigger was reported in the latest check-in.",
        "blocks_assessment": False,
        "blocks_exercise": False,
        "requires_clinician_review": False,
    }


def _supports_stable_classification(assessment: Optional[Dict[str, Any]]) -> bool:
    """Only quality-complete assessments may support a stable classification."""
    gate = (assessment or {}).get("clinical_review_gate") or {}
    return str(gate.get("status") or "") in {"clear", "no_rehab_needed"}


def _stage(profile: Dict[str, Any], assessments: Sequence[Dict[str, Any]], check_ins: Sequence[Dict[str, Any]], safety: Dict[str, Any]) -> str:
    if safety["status"] != "clear":
        return "needs_review"
    if not assessments:
        return "starting"
    try:
        months = int(profile.get("months_since_stroke"))
    except (TypeError, ValueError):
        months = 99
    latest_check_in = _latest(check_ins)
    if str(_answer(latest_check_in, "function_change", "")).lower() in {"a_little_harder", "much_harder"}:
        return "needs_review"
    if months <= 3 or len(assessments) < 2:
        return "early"
    latest_assessment = _latest(assessments)
    issues = [issue for issue in (latest_assessment or {}).get("functional_issues") or [] if issue.get("code") != "NO_ISSUES"]
    if issues:
        return "active"
    return "stable" if _supports_stable_classification(latest_assessment) else "active"


def _cadence(stage: str) -> Dict[str, int]:
    return {
        "starting": {"survey_days": 0, "assessment_days": 0},
        "needs_review": {"survey_days": 1, "assessment_days": 7},
        "early": {"survey_days": 3, "assessment_days": 14},
        "active": {"survey_days": 7, "assessment_days": 28},
        "stable": {"survey_days": 14, "assessment_days": 56},
    }[stage]


def _due_at(last: Optional[Dict[str, Any]], days: int, now: datetime) -> datetime:
    last_at = _as_utc((last or {}).get("created_at"))
    return (last_at + timedelta(days=days)) if last_at else now


def _assessment_packages(domains: Sequence[str], has_assessment: bool) -> List[str]:
    if not has_assessment:
        return ["initial"]
    packages: List[str] = []
    if "upper_limb" in domains:
        packages.append("upper_limb")
    if "hand" in domains:
        packages.append("hand")
    if "lower_limb" in domains:
        packages.extend(["lower_limb", "balance"])
    return packages or ["initial"]


def _select_questions(domains: Sequence[str], has_plan: bool, stage: str) -> List[Dict[str, Any]]:
    ids = ["sudden_change", "function_change"]
    if has_plan:
        ids.append("exercise_tolerance")
    elif "lower_limb" in domains:
        ids.append("walking_confidence")
    else:
        ids.append("pain")
    if "hand" in domains:
        ids.append("hand_use")
    elif "lower_limb" in domains:
        ids.append("falls")
    elif stage in {"early", "needs_review"}:
        ids.append("fatigue")
    else:
        ids.append("goal_activity")
    unique = list(dict.fromkeys(ids))[:MAX_CHECK_IN_QUESTIONS]
    return [dict(QUESTION_BANK[question_id]) for question_id in unique]


def _exercise_action(latest_check_in: Optional[Dict[str, Any]], latest_assessment: Optional[Dict[str, Any]], safety: Dict[str, Any]) -> Dict[str, Any]:
    active_ids = [str(item.get("id")) for item in (latest_assessment or {}).get("rehab_plan") or [] if item.get("id")]
    if safety["blocks_exercise"]:
        return {"action": "hold", "dose_change_percent": 0, "reason": safety["message"], "approved_exercise_ids": active_ids}
    tolerance = str(_answer(latest_check_in, "exercise_tolerance", "")).lower()
    function_change = str(_answer(latest_check_in, "function_change", "")).lower()
    if tolerance == "too_hard" or function_change == "a_little_harder":
        return {
            "action": "reduce_next_session",
            "dose_change_percent": -20,
            "reason": "The patient reported that movement or the current dose felt harder. Keep the same approved exercises and reduce the next session dose.",
            "approved_exercise_ids": active_ids,
        }
    if tolerance == "too_easy" and function_change in {"much_easier", "a_little_easier"} and latest_assessment:
        return {
            "action": "small_progression_after_confirmation",
            "dose_change_percent": 10,
            "reason": "The current plan felt easy and function was reported as easier. A small progression may be offered only within the approved exercise definition.",
            "approved_exercise_ids": active_ids,
        }
    return {
        "action": "maintain",
        "dose_change_percent": 0,
        "reason": "Keep the current approved plan until new patient-reported or objective evidence supports a change.",
        "approved_exercise_ids": active_ids,
    }


def _content_gaps(profile: Dict[str, Any], domains: Sequence[str]) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    affected = {str(item).lower() for item in profile.get("affected_areas") or []}
    if "face_speech" in affected:
        gaps.append({
            "type": "assessment_task",
            "status": "draft_clinical_review",
            "title": "Communication goal screening gap",
            "reason": "The current camera movement library does not validate speech or language function.",
            "activation_rule": "Must be designed and approved by an appropriately qualified stroke clinician before patient use.",
        })
    goal = str(profile.get("primary_goal") or "").strip()
    if goal and not domains:
        gaps.append({
            "type": "goal_specific_question",
            "status": "draft_clinical_review",
            "title": "Goal-specific follow-up question",
            "reason": f"The saved patient goal is not yet mapped to an approved camera task: {goal[:120]}",
            "activation_rule": "A clinician must confirm relevance, wording, scoring, and escalation rules before activation.",
        })
    return gaps


def build_adaptive_care_plan(
    profile: Optional[Dict[str, Any]],
    assessments: Optional[Sequence[Dict[str, Any]]],
    check_ins: Optional[Sequence[Dict[str, Any]]],
    activities: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return Alira's next bounded action from current evidence."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    profile = dict(profile or {})
    assessments = list(assessments or [])
    check_ins = list(check_ins or [])
    activities = list(activities or [])
    latest_assessment = _latest(assessments)
    latest_check_in = _latest(check_ins)
    safety = _safety_status(latest_check_in)
    stage = _stage(profile, assessments, check_ins, safety)
    cadence = _cadence(stage)
    domains = _issue_domains(latest_assessment, profile)
    survey_due_at = _due_at(latest_check_in, cadence["survey_days"], now)
    assessment_due_at = _due_at(latest_assessment, cadence["assessment_days"], now)
    survey_due = now >= survey_due_at
    assessment_due = now >= assessment_due_at and not safety["blocks_assessment"]
    has_plan = bool((latest_assessment or {}).get("rehab_plan"))
    packages = _assessment_packages(domains, bool(latest_assessment))
    latest_activity = _latest(activities, key="completed_at")
    latest_activity_at = _as_utc((latest_activity or {}).get("completed_at"))
    sessions_last_7_days = sum(
        1
        for item in activities
        if (completed_at := _as_utc(item.get("completed_at"))) and now - completed_at <= timedelta(days=7)
    )
    completed_today = bool(latest_activity_at and latest_activity_at.date() == now.date())
    reminder_needed = bool(has_plan and not completed_today and (not latest_activity_at or now - latest_activity_at >= timedelta(days=2)))
    if safety["status"] != "clear":
        next_day_action = "safety_follow_up"
    elif completed_today:
        next_day_action = "recognize_completed_session"
    elif reminder_needed:
        next_day_action = "send_plan_reminder"
    else:
        next_day_action = "none"

    return {
        "version": CARE_POLICY_VERSION,
        "generated_at": now.isoformat(),
        "stage": stage,
        "safety": safety,
        "survey": {
            "due": survey_due,
            "due_at": survey_due_at.isoformat(),
            "cadence_days": cadence["survey_days"],
            "max_questions": MAX_CHECK_IN_QUESTIONS,
            "questions": _select_questions(domains, has_plan, stage) if survey_due else [],
            "reason": "The interval adapts to recovery stage and recent changes; safety and function are checked before plan changes.",
        },
        "assessment": {
            "due": assessment_due,
            "due_at": assessment_due_at.isoformat(),
            "cadence_days": cadence["assessment_days"],
            "packages": packages if assessment_due else [],
            "blocked_by_safety": safety["blocks_assessment"],
            "reason": "Only approved camera packages matching the affected functional domains are selected.",
        },
        "exercise_plan": _exercise_action(latest_check_in, latest_assessment, safety),
        "daily_monitoring": {
            "enabled": True,
            "uses_model": False,
            "next_review_at": (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat(),
            "notify_only_when_actionable": True,
            "sessions_last_7_days": sessions_last_7_days,
            "last_session_at": latest_activity_at.isoformat() if latest_activity_at else None,
            "reminder_needed": reminder_needed,
            "next_day_action": next_day_action,
            "reason": "Daily activity can be checked with deterministic rules; an AI-model call is reserved for a changed or scheduled clinical state.",
        },
        "content_proposals": _content_gaps(profile, domains),
        "autonomy": {
            "may_select_approved_questions": True,
            "may_select_approved_assessments": True,
            "may_adjust_approved_exercise_dose": True,
            "maximum_automatic_dose_change_percent": 20,
            "may_change_app_features": False,
            "may_activate_novel_clinical_content": False,
            "novel_content_status": "draft_clinical_review",
        },
        "evidence": {
            "assessment_count": len(assessments),
            "check_in_count": len(check_ins),
            "activity_count": len(activities),
            "functional_domains": domains,
            "latest_assessment_id": (latest_assessment or {}).get("id"),
            "latest_check_in_id": (latest_check_in or {}).get("id"),
        },
    }


def validate_check_in_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize answers accepted from app or realtime tools."""
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    unknown = sorted(set(answers) - set(QUESTION_BANK))
    if unknown:
        raise ValueError(f"unsupported question ids: {', '.join(unknown)}")
    normalized: Dict[str, Any] = {}
    for question_id, value in answers.items():
        spec = QUESTION_BANK[question_id]
        if spec["type"] == "number":
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{question_id} must be a number") from exc
            if number < spec["min"] or number > spec["max"]:
                raise ValueError(f"{question_id} must be between {spec['min']} and {spec['max']}")
            normalized[question_id] = int(number) if number.is_integer() else number
            continue
        text = str(value).strip().lower()
        if text not in spec.get("options", []):
            raise ValueError(f"unsupported answer for {question_id}")
        normalized[question_id] = text
    return normalized


def approved_question_ids() -> List[str]:
    return list(QUESTION_BANK)
