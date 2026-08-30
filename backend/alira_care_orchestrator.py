"""Adaptive care orchestration for Alira.

The module makes repeatable scheduling and content-selection decisions from
patient-reported and assessment evidence. Alira may autonomously select from
approved clinical libraries; unsupported ideas remain non-active drafts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


CARE_POLICY_VERSION = "alira-care-v2"
MAX_CHECK_IN_QUESTIONS = 5
SURVEY_PREFACE = (
    "A few short questions about how you have been getting on. Your answers help Rehyn adjust your plan to suit you better.\n\n"
    "This takes about two minutes. Every question is optional and you can stop at any point. Skipping the check in does not change anything about your plan or your access to Rehyn.\n\n"
    "This is not a way to get help. If something is wrong, contact your GP or physiotherapist. In an emergency, call 999."
)
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
        "required": False,
    },
    "falls": {
        "id": "falls",
        "domain": "safety",
        "question": "Have you fallen or nearly fallen since your last check-in?",
        "type": "single",
        "options": ["no", "near_fall", "fall_no_injury", "fall_with_injury"],
        "required": False,
    },
    "pain": {
        "id": "pain",
        "domain": "tolerance",
        "question": "How much pain is affecting movement today, from 0 to 10?",
        "type": "number",
        "min": 0,
        "max": 10,
        "required": False,
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
        "required": False,
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
    "arm_use": {
        "id": "arm_use",
        "domain": "upper_limb",
        "question": "How comfortable was reaching, lifting, or bringing your affected arm toward your face today?",
        "type": "single",
        "options": ["not_tried", "comfortable", "needed_more_effort", "needed_help", "unable"],
        "required": False,
    },
    "balance_confidence": {
        "id": "balance_confidence",
        "domain": "balance",
        "question": "How steady did you feel during sitting, standing, or transfers today?",
        "type": "single",
        "options": ["not_applicable", "steady", "a_little_unsteady", "very_unsteady", "needed_help"],
        "required": False,
    },
    "emotional_safety": {
        "id": "emotional_safety",
        "domain": "safety",
        "question": "Have you had thoughts of harming yourself, or felt unable to keep yourself safe?",
        "type": "single",
        "options": ["no", "thoughts_but_safe", "cannot_keep_safe", "prefer_not_to_say"],
        "required": False,
    },
}


FUNCTIONAL_ISSUE_CATALOG: Dict[str, Dict[str, Any]] = {
    "reaching": {"domain": "upper_limb", "package": "upper_limb", "task_ids": ["T1", "T2", "T3"]},
    "arm_lifting": {"domain": "upper_limb", "package": "upper_limb", "task_ids": ["T2"]},
    "hand_to_mouth": {"domain": "upper_limb", "package": "upper_limb", "task_ids": ["T3"]},
    "hand_opening": {"domain": "hand", "package": "hand", "task_ids": ["H1", "H3"]},
    "grasping": {"domain": "hand", "package": "hand", "task_ids": ["H2", "H4"]},
    "pinching": {"domain": "hand", "package": "hand", "task_ids": ["H3", "H5"]},
    "walking": {"domain": "lower_limb", "package": "lower_limb", "task_ids": ["L6"]},
    "transfers": {"domain": "lower_limb", "package": "lower_limb", "task_ids": ["L2", "L3"]},
    "balance": {"domain": "lower_limb", "package": "balance", "task_ids": ["B1", "B2", "B3"]},
}

DEFAULT_FOLLOW_UP_TASKS: Dict[str, List[str]] = {
    "upper_limb": ["T1", "T2", "T3"],
    "hand": ["H1", "H3", "H4"],
    "lower_limb": ["L1", "L2", "L6"],
    "balance": ["B1", "B2", "B3"],
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


def _contains_any(text: str, phrases: Sequence[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _safety_outcome(
    status: str,
    code: str,
    headline: str,
    message: str,
    *,
    blocks_assessment: bool,
    blocks_exercise: bool,
    requires_clinician_review: bool,
    call_999: bool = False,
    offer_call_999: bool = False,
) -> Dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "headline": headline,
        "message": message,
        "call_999": call_999,
        "offer_call_999": call_999 or offer_call_999,
        "blocks_assessment": blocks_assessment,
        "blocks_exercise": blocks_exercise,
        "requires_clinician_review": requires_clinician_review,
    }


def evaluate_survey_safety(check_in: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return deterministic crisis routing from optional survey answers and patient wording."""
    sudden_change = str(_answer(check_in, "sudden_change", "no")).lower() == "yes"
    fall = str(_answer(check_in, "falls", "no")).lower()
    emotional_safety = str(_answer(check_in, "emotional_safety", "no")).lower()
    note = " ".join(str((check_in or {}).get("patient_note") or "").lower().split())
    try:
        pain = float(_answer(check_in, "pain", 0) or 0)
    except (TypeError, ValueError):
        pain = 0
    function_change = str(_answer(check_in, "function_change", "")).lower()
    tolerance = str(_answer(check_in, "exercise_tolerance", "")).lower()

    self_harm_denials = (
        "no suicidal thoughts", "not suicidal", "no thoughts of harming myself",
        "do not want to die", "don't want to die",
    )
    immediate_self_harm_phrases = (
        "cannot keep myself safe", "can't keep myself safe", "i have a suicide plan",
        "i have a plan to kill myself", "about to kill myself", "going to kill myself",
        "i might kill myself", "i am going to hurt myself", "i have taken an overdose", "i overdosed",
    )
    self_harm_phrases = (
        "i have suicidal thoughts", "i've had suicidal thoughts", "i am suicidal", "i'm suicidal",
        "thinking about suicide", "thoughts of harming myself", "thoughts of killing myself",
        "thinking of harming myself", "thinking of hurting myself", "i want to die", "end my life",
        "i don't want to live", "i do not want to live", "i would be better off dead",
    )
    immediate_self_harm = emotional_safety == "cannot_keep_safe" or _contains_any(note, immediate_self_harm_phrases)
    self_harm_thoughts = emotional_safety == "thoughts_but_safe" or (
        not _contains_any(note, self_harm_denials) and _contains_any(note, self_harm_phrases)
    )

    emergency_sign_groups = (
        (("my face is drooping", "my face has drooped", "new facial droop", "new face droop"), ("no facial droop", "no face droop")),
        (("my arm is suddenly weak", "new arm weakness"), ("no arm weakness",)),
        (("my speech is slurred", "new slurred speech", "i suddenly cannot speak"), ("no slurred speech", "no speech change")),
        (("sudden severe headache",), ("no severe headache", "no sudden headache")),
        (("i collapsed",), ("did not collapse", "haven't collapsed", "have not collapsed")),
        (("i have chest pain",), ("no chest pain",)),
        (("i can't breathe", "i cannot breathe", "trouble breathing"), ("no trouble breathing", "not having trouble breathing")),
    )
    note_reports_emergency = any(
        _contains_any(note, signs) and not _contains_any(note, denials)
        for signs, denials in emergency_sign_groups
    )
    note_reports_fall = (
        _contains_any(note, ("i fell today", "i have fallen", "i've fallen", "i had a fall", "i fell over"))
        and not _contains_any(note, ("i have not fallen", "i haven't fallen", "no falls"))
    )

    if sudden_change or note_reports_emergency:
        return _safety_outcome(
            "emergency",
            "possible_stroke_or_medical_emergency",
            "Call 999 now",
            "New stroke or other emergency symptoms may be present. Stop using Rehyn and call 999 now. Say that you suspect a stroke, note when the symptoms started if you can, and do not wait even if the symptoms improve.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            call_999=True,
        )
    if immediate_self_harm:
        return _safety_outcome(
            "emergency",
            "cannot_keep_self_safe",
            "Get emergency help now",
            "Your safety matters. Call 999 or go to A&E now because you may not be able to keep yourself safe. If someone is with you, tell them now and ask them to stay with you while help is arranged.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            call_999=True,
        )
    if self_harm_thoughts:
        return _safety_outcome(
            "urgent_review",
            "thoughts_of_self_harm",
            "Please get urgent support today",
            "You deserve support with this today. Call NHS 111 and select the mental health option, or ask for an urgent GP appointment. You can also call Samaritans on 116 123. If you may act on these thoughts or cannot keep yourself safe, call 999 or go to A&E now.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            offer_call_999=True,
        )
    if fall == "fall_with_injury":
        return _safety_outcome(
            "urgent_review",
            "fall_with_possible_injury",
            "A fall can be serious",
            "Stop the check-in and do not continue exercises. Call 999 now if you may have injured your head, back, neck or hip, or if you cannot get up. Otherwise, if you may be in pain, injured or unwell, contact NHS 111 now and tell your GP or physiotherapist about the fall.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            offer_call_999=True,
        )
    if fall == "no" and note_reports_fall:
        return _safety_outcome(
            "urgent_review",
            "fall_details_needed",
            "A fall can be serious",
            "Stop the check-in and do not continue exercises. Call 999 now if you cannot get up or may have injured your head, back, neck or hip. If you may be in pain, injured or unwell, contact NHS 111 now. Otherwise, rest and tell your GP or physiotherapist about the fall.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            offer_call_999=True,
        )
    if function_change == "much_harder" or _contains_any(note, ("massive regression", "major regression", "much worse than before")):
        return _safety_outcome(
            "urgent_review",
            "major_functional_decline",
            "A major change needs urgent review",
            "Stop exercises and contact your stroke team, physiotherapist or GP today. If this change happened suddenly, or includes new face droop, arm weakness, speech difficulty, severe headache or collapse, call 999 now even if the symptoms improve. If you cannot reach your care team, contact NHS 111.",
            blocks_assessment=True,
            blocks_exercise=True,
            requires_clinician_review=True,
            offer_call_999=True,
        )
    if fall == "fall_no_injury":
        return _safety_outcome(
            "clinical_review",
            "fall_without_reported_injury",
            "Please pause and check how you feel",
            "A fall is important even when no injury is obvious. Do not continue exercises today if you have pain, dizziness or feel unwell, and tell your GP or physiotherapist. Call 999 if you cannot get up or may have injured your head, back, neck or hip; contact NHS 111 if you are in pain, injured, unwell or unsure.",
            blocks_assessment=False,
            blocks_exercise=True,
            requires_clinician_review=True,
            offer_call_999=True,
        )
    if fall == "near_fall":
        return _safety_outcome(
            "caution",
            "near_fall",
            "A near fall is worth following up",
            "Pause and make sure you feel steady before continuing. Tell your physiotherapist or GP about the near fall, especially if this is new or happening more often. If you develop sudden stroke symptoms or are in immediate danger, call 999.",
            blocks_assessment=False,
            blocks_exercise=False,
            requires_clinician_review=True,
        )
    if pain >= 7 or tolerance == "stopped_for_symptoms":
        return _safety_outcome(
            "clinical_review",
            "exercise_symptoms_or_severe_pain",
            "Pause your plan",
            "Stop exercises and contact your physiotherapist, stroke team or GP before continuing. If symptoms are sudden or severe, or you have new face, arm or speech changes, call 999.",
            blocks_assessment=False,
            blocks_exercise=True,
            requires_clinician_review=True,
        )
    return _safety_outcome(
        "clear",
        "no_immediate_trigger_reported",
        "No immediate safety trigger reported",
        "No immediate safety trigger was reported in the latest check-in.",
        blocks_assessment=False,
        blocks_exercise=False,
        requires_clinician_review=False,
    )


def _safety_status(check_in: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return evaluate_survey_safety(check_in)


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
    return packages or ["upper_limb"]


def _pending_issue_report(issue_reports: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pending = [
        item for item in issue_reports
        if str(item.get("status") or "pending") == "pending"
        and str(item.get("category") or "") in FUNCTIONAL_ISSUE_CATALOG
    ]
    return _latest(pending)


def _selected_assessment(
    domains: Sequence[str],
    has_assessment: bool,
    pending_issue: Optional[Dict[str, Any]],
    initial_readiness: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if not has_assessment:
        return {
            "packages": ["initial"],
            "task_ids": list((initial_readiness or {}).get("task_ids") or []),
            "trigger": "initial",
            "issue_report_id": None,
            "issue_category": None,
        }
    if pending_issue:
        category = str(pending_issue.get("category") or "")
        selection = FUNCTIONAL_ISSUE_CATALOG[category]
        return {
            "packages": [selection["package"]],
            "task_ids": list(selection["task_ids"]),
            "trigger": "new_functional_issue",
            "issue_report_id": pending_issue.get("id"),
            "issue_category": category,
        }
    packages = _assessment_packages(domains, True)
    package = packages[0]
    return {
        "packages": [package],
        "task_ids": list(DEFAULT_FOLLOW_UP_TASKS.get(package, [])),
        "trigger": "scheduled",
        "issue_report_id": None,
        "issue_category": None,
    }


def _select_questions(
    domains: Sequence[str],
    has_plan: bool,
    stage: str,
    pending_issue: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    ids = ["sudden_change", "falls", "emotional_safety", "function_change"]
    if has_plan:
        ids.append("exercise_tolerance")
    elif "lower_limb" in domains:
        ids.append("walking_confidence")
    else:
        ids.append("pain")
    pending_category = str((pending_issue or {}).get("category") or "")
    if pending_category in {"reaching", "arm_lifting", "hand_to_mouth"}:
        ids.append("arm_use")
    elif pending_category == "balance":
        ids.append("balance_confidence")
    elif "hand" in domains:
        ids.append("hand_use")
    elif "lower_limb" in domains:
        ids.append("walking_confidence")
    elif stage in {"early", "needs_review"}:
        ids.append("fatigue")
    else:
        ids.append("goal_activity")
    unique = list(dict.fromkeys(ids))[:MAX_CHECK_IN_QUESTIONS]
    return [dict(QUESTION_BANK[question_id]) for question_id in unique]


def _weekly_frequency(frequency: Any) -> int:
    text = str(frequency or "").lower()
    if "twice daily" in text or "daily" in text:
        return 7
    match = next((int(value) for value in text.split() if value.isdigit()), None)
    return max(1, min(7, match)) if match else 3


def _exercise_action(
    latest_check_in: Optional[Dict[str, Any]],
    latest_assessment: Optional[Dict[str, Any]],
    safety: Dict[str, Any],
    sessions_last_7_days: int = 0,
) -> Dict[str, Any]:
    active_plan = [dict(item) for item in (latest_assessment or {}).get("rehab_plan") or [] if item.get("id")]
    active_ids = [str(item["id"]) for item in active_plan]
    if safety["blocks_exercise"]:
        action = "hold"
        dose_change = 0
        reason = safety["message"]
    else:
        tolerance = str(_answer(latest_check_in, "exercise_tolerance", "")).lower()
        function_change = str(_answer(latest_check_in, "function_change", "")).lower()
        if tolerance == "too_hard" or function_change == "a_little_harder":
            action = "reduce_next_session"
            dose_change = -20
            reason = "The patient reported that movement or the current dose felt harder, so Alira selected a small reduction within the approved plan."
        elif tolerance == "too_easy" and function_change in {"much_easier", "a_little_easier"} and latest_assessment:
            action = "small_progression"
            dose_change = 10
            reason = "The current plan felt easy and function was reported as easier, so Alira selected a small progression within the approved plan."
        else:
            action = "maintain"
            dose_change = 0
            reason = "Alira kept the current approved plan because the latest survey, assessment, and activity evidence did not support a dose change."

    prescriptions: List[Dict[str, Any]] = []
    factor = 1 + dose_change / 100
    for exercise in active_plan:
        base_reps = max(1, int(exercise.get("reps") or 1))
        base_sets = max(1, int(exercise.get("sets") or 1))
        base_frequency = _weekly_frequency(exercise.get("frequency"))
        weekly_frequency = base_frequency
        if action == "reduce_next_session" and base_frequency > 1:
            weekly_frequency = base_frequency - 1
        elif action == "small_progression" and sessions_last_7_days >= base_frequency and base_frequency < 7:
            weekly_frequency = base_frequency + 1
        prescriptions.append({
            "exercise_id": str(exercise["id"]),
            "sets": base_sets,
            "reps": max(1, round(base_reps * factor)),
            "weekly_frequency": weekly_frequency,
            "frequency": f"{weekly_frequency} days per week",
        })

    return {
        "action": action,
        "dose_change_percent": dose_change,
        "reason": reason,
        "approved_exercise_ids": active_ids,
        "prescriptions": prescriptions,
        "decision_mode": "autonomous_approved_library",
        "requires_approval": False,
    }


def _next_step_decision(
    *,
    has_initial_assessment: bool,
    initial_can_start: bool,
    safety: Dict[str, Any],
    survey_reminder_due: bool,
    assessment_due: bool,
    assessment_trigger: str,
    active_exercise_ids: Sequence[str],
    remaining_exercise_ids: Sequence[str],
    completed_today: bool,
) -> Dict[str, Any]:
    """Choose the single primary action Alira should show to the patient."""
    if safety["status"] != "clear":
        return {
            "action": "safety_follow_up",
            "title": safety["headline"],
            "message": safety["message"],
            "cta": "Get the next safe step",
            "destination": "emergency" if safety["status"] == "emergency" else "alira",
            "secondary_action": None,
        }

    if not has_initial_assessment:
        return {
            "action": "initial_assessment",
            "title": "Complete your initial assessment",
            "message": (
                "Your first movement assessment is the next step. Alira has selected tasks from your readiness answers."
                if initial_can_start
                else "Finish the short readiness questions so Alira can select a safe first movement assessment."
            ),
            "cta": "Start initial assessment" if initial_can_start else "Finish assessment setup",
            "destination": "initial_assessment" if initial_can_start else "alira",
            "secondary_action": None,
        }

    active_ids = list(active_exercise_ids)
    remaining_ids = list(remaining_exercise_ids)
    if active_ids and remaining_ids:
        remaining_count = len(remaining_ids)
        secondary = None
        if survey_reminder_due:
            secondary = {
                "action": "recovery_check_in",
                "title": "Short recovery check-in also due",
                "message": "It can be completed before or after today's exercises and will not replace them.",
                "cta": "Start short check-in",
                "destination": "survey",
            }
        return {
            "action": "continue_exercises",
            "title": "Continue today's exercise plan",
            "message": f"Complete {remaining_count} remaining exercise{'s' if remaining_count != 1 else ''} in this round.",
            "cta": "Continue today's plan",
            "destination": "rehab_plan",
            "remaining_exercise_ids": remaining_ids,
            "secondary_action": secondary,
        }

    if survey_reminder_due:
        return {
            "action": "recovery_check_in",
            "title": "Your short recovery check-in is due",
            "message": "Alira will ask only the questions needed to keep your next plan relevant.",
            "cta": "Start short check-in",
            "destination": "survey",
            "secondary_action": None,
        }

    if assessment_due:
        return {
            "action": "movement_assessment",
            "title": "Your next movement assessment is ready",
            "message": (
                "Alira selected a focused check for the new functional problem you reported."
                if assessment_trigger == "new_functional_issue"
                else "This scheduled check will measure change over a meaningful interval."
            ),
            "cta": "Start movement assessment",
            "destination": "assessment",
            "secondary_action": None,
        }

    if active_ids and completed_today:
        return {
            "action": "round_complete",
            "title": "Today's exercise round is complete",
            "message": "Your next step is to rest and return for the next planned session.",
            "cta": "See your progress",
            "destination": "progress",
            "secondary_action": None,
        }

    return {
        "action": "review_progress",
        "title": "Your recovery record is up to date",
        "message": "No check-in or assessment is due now. You can review your latest results and progress.",
        "cta": "See your progress",
        "destination": "progress",
        "secondary_action": None,
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
    issue_reports: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return Alira's next bounded action from current evidence."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    profile = dict(profile or {})
    assessments = list(assessments or [])
    check_ins = list(check_ins or [])
    activities = list(activities or [])
    issue_reports = list(issue_reports or [])
    latest_assessment = _latest(assessments)
    latest_check_in = _latest(check_ins)
    pending_issue = _pending_issue_report(issue_reports) if latest_assessment else None
    safety = _safety_status(latest_check_in)
    stage = _stage(profile, assessments, check_ins, safety)
    cadence = _cadence(stage)
    domains = _issue_domains(latest_assessment, profile)
    pending_category = str((pending_issue or {}).get("category") or "")
    pending_domain = str(FUNCTIONAL_ISSUE_CATALOG.get(pending_category, {}).get("domain") or "")
    if pending_domain and pending_domain not in domains:
        domains.append(pending_domain)
    survey_due_at = _due_at(latest_check_in or latest_assessment, cadence["survey_days"], now)
    assessment_due_at = _due_at(latest_assessment, cadence["assessment_days"], now)
    survey_due = now >= survey_due_at
    scheduled_assessment_due = now >= assessment_due_at
    assessment_due = (scheduled_assessment_due or bool(pending_issue)) and not safety["blocks_assessment"]
    has_plan = bool((latest_assessment or {}).get("rehab_plan"))
    has_initial_assessment = any(
        str(item.get("assessment_package") or "initial") == "initial"
        for item in assessments
    )
    initial_readiness = initial_assessment_recommendation(profile) if not latest_assessment else None
    selection = _selected_assessment(domains, bool(latest_assessment), pending_issue, initial_readiness)
    if pending_issue:
        assessment_due_at = now
    latest_activity = _latest(activities, key="completed_at")
    latest_activity_at = _as_utc((latest_activity or {}).get("completed_at"))
    sessions_last_7_days = sum(
        1
        for item in activities
        if (completed_at := _as_utc(item.get("completed_at"))) and now - completed_at <= timedelta(days=7)
    )
    completed_today = bool(latest_activity_at and latest_activity_at.date() == now.date())
    exercise_plan = _exercise_action(latest_check_in, latest_assessment, safety, sessions_last_7_days)
    active_exercise_ids = list(exercise_plan["approved_exercise_ids"])
    completed_exercise_ids_today = list(dict.fromkeys(
        str(item.get("exercise_id"))
        for item in activities
        if item.get("exercise_id")
        and (completed_at := _as_utc(item.get("completed_at")))
        and completed_at.date() == now.date()
    ))
    remaining_exercise_ids_today = [
        exercise_id for exercise_id in active_exercise_ids
        if exercise_id not in completed_exercise_ids_today
    ]
    survey_reminder_due = bool(survey_due and has_initial_assessment)
    reminder_needed = bool(has_plan and not completed_today and (not latest_activity_at or now - latest_activity_at >= timedelta(days=2)))
    if safety["status"] != "clear":
        next_day_action = "safety_follow_up"
    elif completed_today:
        next_day_action = "recognize_completed_session"
    elif reminder_needed:
        next_day_action = "send_plan_reminder"
    else:
        next_day_action = "none"

    next_step = _next_step_decision(
        has_initial_assessment=has_initial_assessment,
        initial_can_start=bool((initial_readiness or {}).get("can_start", True)),
        safety=safety,
        survey_reminder_due=survey_reminder_due,
        assessment_due=assessment_due,
        assessment_trigger=selection["trigger"] if assessment_due else "not_due",
        active_exercise_ids=active_exercise_ids,
        remaining_exercise_ids=remaining_exercise_ids_today,
        completed_today=completed_today,
    )

    return {
        "version": CARE_POLICY_VERSION,
        "generated_at": now.isoformat(),
        "stage": stage,
        "safety": safety,
        "survey": {
            "due": survey_reminder_due,
            "schedule_due": survey_due,
            "reminder_due": survey_reminder_due,
            "patient_prompt_enabled": has_initial_assessment,
            "due_at": survey_due_at.isoformat(),
            "cadence_days": cadence["survey_days"],
            "max_questions": MAX_CHECK_IN_QUESTIONS,
            "preface": SURVEY_PREFACE,
            "all_questions_optional": True,
            "may_stop_at_any_point": True,
            "questions": _select_questions(domains, has_plan, stage, pending_issue) if survey_reminder_due else [],
            "reason": "The interval adapts to recovery stage and recent changes; safety and function are checked before plan changes.",
        },
        "assessment": {
            "due": assessment_due,
            "due_at": assessment_due_at.isoformat(),
            "cadence_days": cadence["assessment_days"],
            "packages": selection["packages"] if assessment_due else [],
            "recommended_packages": selection["packages"],
            "task_ids": selection["task_ids"] if assessment_due else [],
            "trigger": selection["trigger"] if assessment_due else "not_due",
            "exception_for_new_issue": bool(pending_issue) and assessment_due,
            "issue_report_id": selection["issue_report_id"] if assessment_due else None,
            "issue_category": selection["issue_category"] if assessment_due else None,
            "readiness": (initial_readiness or {}).get("status", "ready"),
            "can_start": bool((initial_readiness or {}).get("can_start", True)) and not safety["blocks_assessment"],
            "missing_answers": (initial_readiness or {}).get("missing_answers", []),
            "selection_message": (initial_readiness or {}).get("message"),
            "blocked_by_safety": safety["blocks_assessment"],
            "reason": (
                "A new functional problem opened one targeted assessment outside the routine schedule."
                if pending_issue and assessment_due
                else "Only the approved camera package and tasks selected for the current recovery stage may be started."
            ),
        },
        "exercise_plan": exercise_plan,
        "daily_monitoring": {
            "enabled": True,
            "uses_model": False,
            "next_review_at": (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat(),
            "notify_only_when_actionable": True,
            "sessions_last_7_days": sessions_last_7_days,
            "last_session_at": latest_activity_at.isoformat() if latest_activity_at else None,
            "active_exercise_ids": active_exercise_ids,
            "completed_exercise_ids_today": completed_exercise_ids_today,
            "remaining_exercise_ids_today": remaining_exercise_ids_today,
            "current_round_complete": bool(active_exercise_ids and not remaining_exercise_ids_today),
            "reminder_needed": reminder_needed,
            "next_day_action": next_day_action,
            "reason": "Daily activity can be checked with deterministic rules; an AI-model call is reserved for a changed or scheduled clinical state.",
        },
        "next_step": next_step,
        "content_proposals": _content_gaps(profile, domains),
        "autonomy": {
            "may_select_approved_questions": True,
            "may_select_approved_assessments": True,
            "may_adjust_approved_exercise_dose": True,
            "may_choose_approved_sets_repetitions_and_frequency": True,
            "requires_per_decision_approval": False,
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
            "functional_issue_report_count": len(issue_reports),
            "pending_functional_issue_report_id": (pending_issue or {}).get("id"),
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


def approved_functional_issue_categories() -> List[str]:
    return list(FUNCTIONAL_ISSUE_CATALOG)
