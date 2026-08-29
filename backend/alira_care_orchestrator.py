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
INITIAL_ASSESSMENT_TASK_IDS = ("T1", "T2", "T3", "H1", "H3", "H4", "L6")
ASSESSMENT_READINESS_FIELDS = (
    "sitting_ability",
    "affected_arm_movement",
    "affected_hand_movement",
    "mobility_level",
    "movement_pain",
    "instruction_support",
)


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


def initial_assessment_recommendation(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Select only approved initial tasks that match the saved self-reported prerequisites."""
    profile = dict(profile or {})
    missing = [
        key
        for key in ASSESSMENT_READINESS_FIELDS
        if profile.get(key) is None or str(profile.get(key)).strip() == ""
    ]
    base = {
        "policy_version": CARE_POLICY_VERSION,
        "package_id": "initial",
        "missing_answers": missing,
        "task_ids": [],
        "task_count": 0,
        "excluded": [],
        "requires_helper": False,
        "requires_clinician_review": False,
        "safety_notes": [],
    }
    if missing:
        return {
            **base,
            "status": "needs_answers",
            "can_start": False,
            "message": "Answer the short movement-readiness questions before Alira selects camera tasks.",
        }

    sitting = str(profile.get("sitting_ability") or "").lower()
    arm = str(profile.get("affected_arm_movement") or "").lower()
    hand = str(profile.get("affected_hand_movement") or "").lower()
    mobility = str(profile.get("mobility_level") or "").lower()
    pain = str(profile.get("movement_pain") or "").lower()
    instruction_support = str(profile.get("instruction_support") or "").lower()
    caregiver_answer = profile.get("has_caregiver")
    has_caregiver = caregiver_answer is True or str(caregiver_answer or "").lower() in {"yes", "true", "1"}

    excluded: List[Dict[str, Any]] = []
    task_ids: List[str] = []
    safety_notes: List[str] = []
    requires_helper = sitting == "needs_support" or instruction_support in {"helper_preferred", "helper_required"}

    if pain == "severe_or_worsening":
        return {
            **base,
            "status": "clinical_review",
            "can_start": False,
            "requires_clinician_review": True,
            "excluded": [{"task_ids": list(INITIAL_ASSESSMENT_TASK_IDS), "reason": "Severe or worsening movement pain was reported."}],
            "message": "The camera assessment is paused because severe or worsening pain needs clinical advice first.",
        }

    if instruction_support == "helper_required" and not has_caregiver:
        return {
            **base,
            "status": "support_needed",
            "can_start": False,
            "requires_helper": True,
            "excluded": [{"task_ids": list(INITIAL_ASSESSMENT_TASK_IDS), "reason": "The patient reported needing help to follow instructions or use the screen."}],
            "message": "Please have a trusted helper present before starting the camera assessment.",
        }

    active_arm = arm in {"most_movements", "some_movement", "not_affected"}
    active_hand = hand in {"opens_and_moves", "some_finger_movement", "very_little_movement", "not_affected"}
    independent_sitting = sitting == "independent"

    if independent_sitting and active_arm:
        task_ids.extend(["T1", "T2", "T3"])
    else:
        reason = (
            "These seated reaching tasks need independent sitting and some unassisted affected-arm movement."
            if sitting != "independent"
            else "The patient did not report enough unassisted affected-arm movement for active reaching tasks."
        )
        excluded.append({"task_ids": ["T1", "T2", "T3"], "reason": reason})

    if independent_sitting and active_arm and active_hand:
        task_ids.extend(["H1", "H3", "H4"])
    else:
        reason = (
            "These hand tasks require the affected hand to be raised safely in front of the camera."
            if not independent_sitting or not active_arm
            else "The patient did not report active affected-finger movement for these hand tasks."
        )
        excluded.append({"task_ids": ["H1", "H3", "H4"], "reason": reason})

    if mobility in {"independent", "cane", "walker"}:
        task_ids.append("L6")
        safety_notes.append("Use the usual walking aid and have a separate helper nearby if normally needed for safety.")
    else:
        excluded.append({
            "task_ids": ["L6"],
            "reason": "Walking video is assigned only when the patient reports walking safely without hands-on assistance.",
        })

    if pain in {"moderate", "not_sure"}:
        safety_notes.append("Use a comfortable range and stop if pain increases, dizziness occurs, or movement feels unsafe.")
    if requires_helper:
        safety_notes.append("A trusted helper should stay nearby throughout the assessment.")

    selected = set(task_ids)
    task_ids = [task_id for task_id in INITIAL_ASSESSMENT_TASK_IDS if task_id in selected]
    if not task_ids:
        return {
            **base,
            "status": "clinical_review",
            "can_start": False,
            "excluded": excluded,
            "requires_helper": requires_helper,
            "requires_clinician_review": True,
            "safety_notes": safety_notes,
            "message": "None of the current camera tasks match the reported abilities safely. A clinician should choose an appropriate assessment.",
        }

    return {
        **base,
        "status": "ready",
        "can_start": True,
        "task_ids": task_ids,
        "task_count": len(task_ids),
        "excluded": excluded,
        "requires_helper": requires_helper,
        "safety_notes": safety_notes,
        "message": f"Alira selected {len(task_ids)} suitable task{'s' if len(task_ids) != 1 else ''} from the approved initial assessment.",
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
            "proposed_steps": [
                {"sequence": 1, "instruction": "Confirm the communication goal and preferred communication method."},
                {"sequence": 2, "instruction": "Use a validated communication screen selected by a speech and language therapist."},
                {"sequence": 3, "instruction": "Record support needs without inferring a diagnosis from camera movement."},
            ],
            "not_for_patient_use": True,
            "activation_rule": "Must be designed and approved by an appropriately qualified stroke clinician before patient use.",
        })
    goal = str(profile.get("primary_goal") or "").strip()
    if goal and not domains:
        gaps.append({
            "type": "survey_question",
            "status": "draft_clinical_review",
            "title": "Goal-specific follow-up question",
            "reason": f"The saved patient goal is not yet mapped to an approved camera task: {goal[:120]}",
            "draft": {
                "question": "How much help did you need with your chosen activity this week?",
                "options": ["not_tried", "no_help", "a_little_help", "a_lot_of_help", "unable"],
                "escalation_required_for": ["unable"],
            },
            "not_for_patient_use": True,
            "activation_rule": "A clinician must confirm relevance, wording, scoring, and escalation rules before activation.",
        })
        gaps.append({
            "type": "assessment_task",
            "status": "draft_clinical_review",
            "title": "Goal-specific camera task draft",
            "reason": f"No approved camera task currently measures this saved goal: {goal[:120]}",
            "proposed_steps": [
                {"sequence": 1, "instruction": "Confirm a safe starting position and the equipment normally used."},
                {"sequence": 2, "instruction": "Demonstrate one comfortable attempt with a clear stop option."},
                {"sequence": 3, "instruction": "Observe completion and compensation without forcing range or speed."},
                {"sequence": 4, "instruction": "Return to the safe starting position and ask about pain or fatigue."},
            ],
            "not_for_patient_use": True,
            "activation_rule": "A stroke clinician must approve eligibility, exclusions, scoring, voice wording, and stop rules before activation.",
        })
        gaps.append({
            "type": "exercise",
            "status": "draft_clinical_review",
            "title": "Goal-specific guided exercise draft",
            "reason": f"The approved exercise library does not yet contain a progression for this saved goal: {goal[:120]}",
            "proposed_steps": [
                {"sequence": 1, "instruction": "Set up in the clinician-approved supported position."},
                {"sequence": 2, "instruction": "Practise a small, comfortable part of the goal activity."},
                {"sequence": 3, "instruction": "Pause, check symptoms, and rest before another repetition."},
                {"sequence": 4, "instruction": "Finish in a stable position and record effort, pain, and assistance."},
            ],
            "not_for_patient_use": True,
            "activation_rule": "A stroke clinician must approve the movement, dose, progression, contraindications, and step-by-step guidance before activation.",
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
    initial_readiness = initial_assessment_recommendation(profile) if not latest_assessment else None
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
            "task_ids": (initial_readiness or {}).get("task_ids", []) if assessment_due else [],
            "readiness": (initial_readiness or {}).get("status", "ready"),
            "can_start": bool((initial_readiness or {}).get("can_start", True)) and not safety["blocks_assessment"],
            "missing_answers": (initial_readiness or {}).get("missing_answers", []),
            "selection_message": (initial_readiness or {}).get("message"),
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
            "may_draft_novel_survey_questions": True,
            "may_draft_novel_assessment_tasks": True,
            "may_draft_novel_exercises": True,
            "novel_drafts_require_step_by_step_guidance": True,
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
