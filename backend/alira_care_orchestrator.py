"""Adaptive care orchestration for Alira.

The module makes repeatable scheduling and content-selection decisions from
patient-reported and assessment evidence. Alira may autonomously select from
approved clinical libraries; unsupported ideas remain non-active drafts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


CARE_POLICY_VERSION = "alira-care-v2"
MOVEMENT_READINESS_VERSION = "survey-exercise-v3"
MAX_CHECK_IN_QUESTIONS = 8
SURVEY_PREFACE = (
    "A few short questions about how you have been getting on. Your answers help Rehyn adjust your plan to suit you better.\n\n"
    "This takes about two minutes. Every question is optional and you can stop at any point. Skipping the check in does not change anything about your plan or your access to Rehyn.\n\n"
    "This is not a way to get help. If something is wrong, contact your GP or physiotherapist. In an emergency, call 999."
)
APPROVED_ASSESSMENT_PACKAGES = {"initial", "upper_limb", "hand", "lower_limb", "balance"}
INITIAL_ASSESSMENT_TASK_IDS = ("T1", "T2", "T3", "H1", "H3", "H4", "L6")
INITIAL_TASKS_BY_DOMAIN = {
    "upper_limb": ("T1", "T2", "T3"),
    "hand": ("H1", "H3", "H4"),
    "lower_limb": ("L6",),
}
ASSESSMENT_READINESS_FIELDS = (
    "sitting_ability",
    "affected_arm_movement",
    "affected_hand_movement",
    "mobility_level",
    "movement_pain",
    "instruction_support",
)
EXERCISE_SELECTION_SURVEY_FIELDS = (
    "arm_activity_difficulties",
    "hand_activity_difficulties",
    "mobility_activity_difficulties",
)
STANDING_OR_STEPPING_DIFFICULTIES = {
    "sit_to_stand",
    "standing_balance",
    "weight_affected_leg",
    "start_step",
    "step_balance",
}


# Six-level assistance scale (spec section 6.2), used consistently everywhere a
# level of help is described: intake, assessment records, plans and progress.
ASSISTANCE_LEVELS = (
    "unable",
    "maximum_assistance",
    "moderate_assistance",
    "minimum_assistance",
    "supervision_only",
    "fully_independent",
)
ASSISTANCE_LEVEL_LABELS = {
    "unable": "Unable / not safely attempted",
    "maximum_assistance": "Maximum assistance",
    "moderate_assistance": "Moderate assistance",
    "minimum_assistance": "Minimum assistance",
    "supervision_only": "Supervision only",
    "fully_independent": "Fully independent",
}

# Functional tiers (spec section 1.3), assigned per domain. Tier 1: no
# voluntary movement even with help - no camera assessment, caregiver-delivered
# plan. Tier 2: moves with caregiver assistance - goal is independence.
# Tier 3: independent but quality may be impaired - full camera assessment.
FUNCTIONAL_TIER_DOMAINS = ("upper_limb", "hand", "lower_limb")


def classify_functional_rehab_profile(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify survey answers for rehabilitation routing, not stroke diagnosis."""
    profile = dict(profile or {})
    missing = [
        key
        for key in ASSESSMENT_READINESS_FIELDS
        if profile.get(key) is None or str(profile.get(key)).strip() == ""
    ]
    if str(profile.get("movement_readiness_version") or "") == MOVEMENT_READINESS_VERSION:
        missing.extend(
            key
            for key in EXERCISE_SELECTION_SURVEY_FIELDS
            if profile.get(key) is None or str(profile.get(key)).strip() == ""
        )
    mobility_difficulties = {
        str(value).strip().lower()
        for value in (profile.get("mobility_activity_difficulties") or [])
        if str(value).strip()
    }
    if mobility_difficulties & STANDING_OR_STEPPING_DIFFICULTIES:
        if not str(profile.get("standing_exercise_clearance") or "").strip():
            missing.append("standing_exercise_clearance")
    if str(profile.get("movement_readiness_version") or "") != MOVEMENT_READINESS_VERSION:
        for key in ("affected_arm_movement", "affected_hand_movement"):
            if str(profile.get(key) or "").lower() == "no_movement" and key not in missing:
                missing.append(key)
    arm = str(profile.get("affected_arm_movement") or "").lower()
    hand = str(profile.get("affected_hand_movement") or "").lower()
    mobility = str(profile.get("mobility_level") or "").lower()
    sitting = str(profile.get("sitting_ability") or "").lower()
    pain = str(profile.get("movement_pain") or "").lower()
    instruction_support = str(profile.get("instruction_support") or "").lower()
    affected_areas = {str(item).lower() for item in (profile.get("affected_areas") or [])}

    upper_relevant = arm not in {"", "not_affected"}
    hand_relevant = hand not in {"", "not_affected"}
    lower_relevant = any(area.endswith("_lower") for area in affected_areas) or mobility not in {"", "independent"}
    reported_domains = [
        domain
        for domain, relevant in (
            ("upper_limb", upper_relevant),
            ("hand", hand_relevant),
            ("lower_limb", lower_relevant),
        )
        if relevant
    ]

    def result(
        profile_id: str,
        label: str,
        description: str,
        rationale: List[str],
        domains: Optional[List[str]] = None,
        candidate_tasks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        assessment_domains = list(reported_domains if domains is None else domains)
        selected_candidates = candidate_tasks or [
            task_id
            for domain in assessment_domains
            for task_id in INITIAL_TASKS_BY_DOMAIN.get(domain, ())
        ]
        return {
            "version": "rehyn-functional-profile-v1",
            "id": profile_id,
            "label": label,
            "description": description,
            "rationale": rationale,
            "reported_domains": list(reported_domains),
            "assessment_domains": assessment_domains,
            "candidate_task_ids": selected_candidates,
            "missing_fields": list(missing),
            "source": "movement_readiness_survey",
            "non_diagnostic": True,
        }

    if missing:
        return result(
            "needs_clarification",
            "More readiness information needed",
            "Alira needs the remaining movement-readiness answers before selecting a functional profile or camera tasks.",
            [f"Missing readiness answer: {key}." for key in missing],
            [],
        )
    if pain == "severe_or_worsening":
        return result(
            "safety_pause",
            "Safety pause",
            "Severe or worsening movement pain was reported, so camera assessment is paused for clinical advice.",
            ["Severe or worsening movement pain was reported."],
            [],
        )
    if sitting == "unable" and arm == "no_movement" and hand == "no_movement" and mobility in {"unable_walk", "not_cleared", "wheelchair"}:
        return result(
            "profound_dependency",
            "Profound movement support needs",
            "The survey indicates that the current camera tasks are not suitable and caregiver-delivered support is the safer route.",
            ["Safe unsupported sitting, active arm and hand movement, and walking were not available for camera assessment."],
            [],
        )

    helper_needed = (
        sitting == "needs_support"
        or instruction_support in {"helper_preferred", "helper_required"}
        or arm in {"help_only", "not_sure"}
        or hand in {"help_only", "not_sure"}
        or mobility == "person_assist"
    )
    communication_support = "face_speech" in affected_areas and instruction_support in {"helper_preferred", "helper_required"}
    if communication_support:
        routing_domains = list(reported_domains or FUNCTIONAL_TIER_DOMAINS)
        return result(
            "communication_supported",
            "Communication-supported movement profile",
            "Motor tasks are selected from current movement ability, with a helper present for instructions and screen use.",
            ["Face or speech effects and a preference or need for instruction support were reported."],
            routing_domains,
            None if reported_domains else ["T1", "H1", "L6"],
        )
    if helper_needed:
        routing_domains = list(reported_domains or FUNCTIONAL_TIER_DOMAINS)
        return result(
            "helper_dependent",
            "Helper-supported movement profile",
            "Suitable tasks can be attempted only with the support identified in the survey.",
            ["The survey reports support needs for sitting, movement, walking, or following the assessment."],
            routing_domains,
            None if reported_domains else ["T1", "H1", "L6"],
        )

    has_upper = upper_relevant or hand_relevant
    if has_upper and lower_relevant:
        mild_pattern = (
            arm in {"most_movements", "not_affected"}
            and hand in {"opens_and_moves", "not_affected"}
            and mobility in {"independent", "cane"}
        )
        if mild_pattern:
            return result(
                "mild_mixed_impairment",
                "Mild mixed movement difficulty",
                "Independent arm, hand and mobility tasks can establish a broad functional baseline.",
                ["More than one movement domain was reported, with independent movement across the selected domains."],
            )
        return result(
            "mixed_moderate_impairment",
            "Mixed arm, hand and mobility needs",
            "The assessment combines eligible arm, hand and walking observations because more than one domain may need support.",
            ["The survey indicates current needs across upper-limb and mobility domains."],
        )
    if lower_relevant:
        return result(
            "walking_dominant_impairment",
            "Walking and mobility dominant difficulty",
            "The assessment focuses on walking because no current arm or hand difficulty was reported.",
            ["A lower-limb or mobility effect was reported while arm and hand were marked not affected."],
        )
    if has_upper:
        if arm in {"most_movements", "not_affected"} and hand in {"some_finger_movement", "very_little_movement", "help_only", "no_movement", "not_sure"}:
            return result(
                "hand_dominant_difficulty",
                "Hand-control dominant difficulty",
                "The assessment prioritises eligible hand-control tasks while retaining arm positioning checks when relevant.",
                ["Arm movement is relatively preserved while current finger or hand control difficulty was reported."],
            )
        if hand == "no_movement" or not hand_relevant:
            return result(
                "arm_dominant_weakness",
                "Arm and reaching dominant difficulty",
                "The assessment focuses on eligible reaching and arm-raising tasks; active hand tasks are not assigned without finger movement.",
                ["Current arm difficulty was reported without testable active hand movement."],
            )
        return result(
            "mixed_moderate_impairment",
            "Mixed arm and hand needs",
            "The assessment combines eligible reaching and hand-control tasks.",
            ["Current arm and hand movement difficulties were both reported."],
        )
    return result(
        "high_functioning_monitoring",
        "High-functioning monitoring",
        "A short cross-domain screen can establish a baseline without requiring the full seven-task assessment.",
        ["No current arm, hand, or mobility difficulty was reported, so a brief baseline is sufficient."],
        ["upper_limb", "hand", "lower_limb"],
        ["T1", "H1", "L6"],
    )


def functional_tiers(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Assign a functional tier per domain from the self-reported screen."""
    profile = dict(profile or {})
    arm = str(profile.get("affected_arm_movement") or "").lower()
    hand = str(profile.get("affected_hand_movement") or "").lower()
    mobility = str(profile.get("mobility_level") or "").lower()
    sitting = str(profile.get("sitting_ability") or "").lower()

    def tier(value: int, reason: str) -> Dict[str, Any]:
        return {"tier": value, "reason": reason, "camera_assessment": value >= 2}

    if arm in {"most_movements", "not_affected"}:
        upper = tier(3, "Independent arm movement was reported; quality and efficiency are assessed.")
    elif arm in {"some_movement"}:
        upper = tier(3 if sitting == "independent" else 2, "Some unassisted arm movement was reported.")
    elif arm in {"help_only"}:
        upper = tier(2, "Arm movement was reported as possible only with help.")
    elif arm in {"no_movement"}:
        upper = tier(1, "No arm movement was reported even with help, so camera tasks are not assigned for this domain.")
    else:
        upper = tier(2, "Arm movement could not be confirmed, so assisted-level tasks are assumed until assessed.")

    if hand in {"opens_and_moves", "not_affected"}:
        hand_tier = tier(3, "Independent hand movement was reported; quality and dexterity are assessed.")
    elif hand in {"some_finger_movement", "very_little_movement"}:
        hand_tier = tier(2, "Partial finger movement was reported.")
    elif hand in {"help_only"}:
        hand_tier = tier(2, "Hand or finger movement was reported as possible only with help.")
    elif hand in {"no_movement"}:
        hand_tier = tier(1, "No hand or finger movement was reported even with help, so camera tasks are not assigned for this domain.")
    else:
        hand_tier = tier(2, "Hand movement could not be confirmed, so assisted-level tasks are assumed until assessed.")

    if mobility in {"independent", "cane", "walker"}:
        lower = tier(3, "Independent walking with the usual aid was reported.")
    elif mobility in {"person_assist", "wheelchair"}:
        lower = tier(2, "Moving with hands-on help or a wheelchair was reported.")
    elif mobility in {"unable_walk", "not_cleared"}:
        lower = tier(1, "Walking is not currently possible or not cleared, so camera walking tasks are not assigned.")
    else:
        lower = tier(2, "Mobility could not be confirmed, so assisted-level tasks are assumed until assessed.")

    tiers = {"upper_limb": upper, "hand": hand_tier, "lower_limb": lower}
    return {
        "by_domain": tiers,
        "any_tier_one": any(item["tier"] == 1 for item in tiers.values()),
        "assistance_levels": list(ASSISTANCE_LEVELS),
        "assistance_level_labels": dict(ASSISTANCE_LEVEL_LABELS),
        "reason": "Tiers are assigned per domain from the self-reported functional screen and are updated by each survey and assessment.",
    }


# Caregiver-delivered programme content for Tier 1 domains (spec section 7.1).
# Deterministic, approved content: positioning, passive range of movement and
# guided activation for the named muscle groups, with dose and safety limits.
CAREGIVER_PROGRAMME_LIBRARY: Dict[str, Dict[str, Any]] = {
    "upper_limb": {
        "id": "CG_UPPER_LIMB",
        "domain": "upper_limb",
        "goal": "Elicit any voluntary movement in the arm",
        "muscle_groups": ["shoulder flexors", "elbow flexors and extensors", "forearm rotators"],
        "instructions": [
            "Position the arm supported on a pillow, shoulder slightly away from the body, palm facing inward.",
            "Move the shoulder slowly through a comfortable range: forward lift, gentle outward movement, then rest. Never push into pain.",
            "Bend and straighten the elbow slowly, supporting the wrist. 8-10 slow repetitions.",
            "Ask the patient to try to join in with even a flicker of effort during each movement, and praise any attempt.",
        ],
        "dose": "Once or twice daily, 5-10 minutes, stopping sooner if the patient tires.",
        "safety_limits": "Stop immediately and contact the clinical team if there is new pain, swelling, or resistance that was not there before. Never force a stiff joint.",
    },
    "hand": {
        "id": "CG_HAND",
        "domain": "hand",
        "goal": "Elicit any voluntary finger movement and keep the hand supple",
        "muscle_groups": ["finger flexors and extensors", "thumb muscles", "wrist flexors and extensors"],
        "instructions": [
            "Support the forearm on a table with the wrist in a neutral position.",
            "Gently open the fingers one by one, hold a few seconds, then let them relax. 5 repetitions per finger.",
            "Move the wrist slowly up and down through a comfortable range, 8-10 repetitions.",
            "Ask the patient to try to squeeze or open with you on each repetition, and note any flicker of movement.",
        ],
        "dose": "Twice daily, about 5 minutes per session.",
        "safety_limits": "Stop if the hand becomes painful, cold, or discoloured, and tell the clinical team. Do not force fingers that are tightly stiff - report spasticity instead.",
    },
    "lower_limb": {
        "id": "CG_LOWER_LIMB",
        "domain": "lower_limb",
        "goal": "Maintain leg movement and circulation, and elicit any voluntary activity",
        "muscle_groups": ["hip flexors", "knee flexors and extensors", "ankle movers"],
        "instructions": [
            "With the patient lying safely, support under the knee and move the hip and knee through a gentle bend and straighten, 8-10 slow repetitions.",
            "Move the ankle up and down slowly, 10 repetitions per side.",
            "Ask the patient to try to press down or pull up with you on each repetition.",
            "Change the patient's resting position regularly to protect skin and comfort.",
        ],
        "dose": "Once or twice daily, 5-10 minutes.",
        "safety_limits": "Stop and seek advice for calf pain or swelling, new redness, or any breathing difficulty during the routine - call 999 for sudden breathlessness or chest pain.",
    },
}


def caregiver_delivered_plan(
    profile: Optional[Dict[str, Any]],
    tiers: Optional[Dict[str, Any]] = None,
    force_domains: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Tier 1 output (spec 7.1): instructions addressed to the caregiver.

    force_domains adds programmes for domains beyond Tier 1 - used when no
    camera assessment is possible at all, so every ruled-out domain still gets
    a qualitative caregiver-delivered routine.
    """
    tiers = tiers or functional_tiers(profile)
    tier_one_domains = [domain for domain, item in tiers["by_domain"].items() if item["tier"] == 1]
    selected_domains = list(dict.fromkeys([*tier_one_domains, *(force_domains or [])]))
    programmes = [dict(CAREGIVER_PROGRAMME_LIBRARY[domain]) for domain in selected_domains if domain in CAREGIVER_PROGRAMME_LIBRARY]
    return {
        "applicable": bool(programmes),
        "audience": "caregiver",
        "tier_one_domains": tier_one_domains,
        "programmes": programmes,
        "stop_and_call": (
            "Stop the routine and call 999 immediately for any new facial droop, arm weakness, speech change, "
            "chest pain, or severe breathlessness. For new pain, stiffness, or anything that worries you, stop "
            "and contact the clinical team at info@rehyn.com."
        ),
        "reason": "No unassisted movement was reported in these domains, so Alira issues a caregiver-delivered programme instead of camera tasks.",
    }


FUNCTIONAL_PROBLEM_SEVERITIES = {1: "needs_attention", 2: "building_strength", 3: "moving_well"}
FUNCTIONAL_PROBLEM_TITLES = {"upper_limb": "Shoulder and arm", "hand": "Hand", "lower_limb": "Leg and walking"}


def survey_functional_problems(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Anatomy pin-points derived from the survey alone (report page 2).

    Every domain gets an honest pin: needs_attention (Tier 1),
    building_strength (Tier 2), or moving_well (Tier 3), with the survey-based
    reason. A completed camera assessment later refines this map.
    """
    profile = dict(profile or {})
    tiers = functional_tiers(profile)
    side = str(profile.get("side_affected") or "").lower()
    affected_side = side if side in {"left", "right"} else "right"
    pins = [
        {
            "domain": domain,
            "title": FUNCTIONAL_PROBLEM_TITLES.get(domain, domain),
            "affected_side": affected_side,
            "tier": item["tier"],
            "severity": FUNCTIONAL_PROBLEM_SEVERITIES.get(item["tier"], "building_strength"),
            "problem": item["reason"],
        }
        for domain, item in tiers["by_domain"].items()
    ]
    return {
        "affected_side": affected_side,
        "pins": pins,
        "reason": "Pin-pointed from the movement-readiness survey answers; a completed camera assessment refines this map.",
    }


CAREGIVER_OBSERVATION_LEVELS = ("none", "flicker", "small_movement", "more_than_before")
CAREGIVER_OBSERVATION_LABELS = {
    "none": "No movement yet",
    "flicker": "A flicker of effort",
    "small_movement": "Small movements",
    "more_than_before": "Joining in more than before",
}


def caregiver_progress_summary(
    activities: Sequence[Dict[str, Any]],
    programme_ids: Sequence[str],
    now: datetime,
) -> Dict[str, Any]:
    """Qualitative progress for caregiver-delivered (non-camera) patients.

    Progress is demonstrated two ways: consistency (delivered session days,
    which also feed the check-in calendar, points, and streaks) and the
    carer's observation of how much the patient joined in - the clinically
    meaningful Tier 1 signal that voluntary movement is returning. Repeated
    higher observations suggest re-screening for camera tasks (tier change).
    """
    ids = {str(programme_id) for programme_id in programme_ids}
    relevant = [
        (completed_at, item)
        for item in activities
        if str(item.get("exercise_id")) in ids and (completed_at := _as_utc(item.get("completed_at")))
    ]
    days_this_week = {at.date() for at, _ in relevant if (now - at).days < 7}
    days_prior_week = {at.date() for at, _ in relevant if 7 <= (now - at).days < 14}
    observation_counts = {level: 0 for level in CAREGIVER_OBSERVATION_LEVELS}
    recent_higher = 0
    for at, item in relevant:
        level = str(item.get("observed_response") or "")
        if level in observation_counts:
            observation_counts[level] += 1
            if level in {"small_movement", "more_than_before"} and (now - at).days < 7:
                recent_higher += 1
    movement_emerging = recent_higher >= 1
    re_screen_suggested = recent_higher >= 2
    if re_screen_suggested:
        message = (
            "Your carer has recorded the patient joining in with small movements more than once this week. "
            "That is real progress - update the movement-readiness answers so Alira can check whether camera tasks are now suitable."
        )
    elif movement_emerging:
        message = "Your carer noticed the patient joining in - keep the daily routines going and record what you see."
    elif len(days_this_week) > len(days_prior_week):
        message = f"{len(days_this_week)} session day{'s' if len(days_this_week) != 1 else ''} this week - more than last week. Consistency is progress at this stage."
    elif days_this_week:
        message = f"{len(days_this_week)} session day{'s' if len(days_this_week) != 1 else ''} delivered this week. Every delivered session protects comfort, joints, and the chance of movement returning."
    else:
        message = "No sessions are recorded yet this week. The first delivered routine today starts the record."
    return {
        "mode": "caregiver_qualitative",
        "how_progress_is_shown": [
            "Delivered session days on the check-in calendar, with points and streaks",
            "The carer's recorded observation of how much the patient joined in",
            "A prompt to re-check readiness when small movements keep appearing",
        ],
        "session_days_this_week": len(days_this_week),
        "session_days_prior_week": len(days_prior_week),
        "total_sessions": len(relevant),
        "observation_counts": observation_counts,
        "observation_labels": dict(CAREGIVER_OBSERVATION_LABELS),
        "movement_emerging": movement_emerging,
        "re_screen_suggested": re_screen_suggested,
        "message": message,
    }


def missing_assessment_domains(assessment: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]]) -> List[str]:
    """Domains that were eligible but not captured in the given assessment.

    Spec 2.2 / user flow: after a partial initial assessment (e.g. the walking
    video was skipped because no helper was present), Alira asks to complete
    just the missing task - and if the patient cannot do it today, the rehab
    plan proceeds for the domains that WERE assessed.
    """
    if not assessment:
        return []
    profile = dict(profile or {})
    task_results = assessment.get("task_results") or []
    recorded_tasks = set()
    for task in task_results:
        task_id = task.get("task_id") if isinstance(task, dict) else getattr(task, "task_id", None)
        if task_id:
            recorded_tasks.add(str(task_id))
    if not recorded_tasks:
        return []
    missing: List[str] = []
    walking_eligible = str(profile.get("mobility_level") or "").lower() in {"independent", "cane", "walker"}
    walking_skipped = False
    for task in task_results:
        metrics = (task.get("metrics") if isinstance(task, dict) else None) or {}
        if metrics.get("walking_skipped"):
            walking_skipped = True
    if walking_eligible and (walking_skipped or "L6" not in recorded_tasks):
        missing.append("lower_limb")
    return missing


MISSING_DOMAIN_TASKS = {"lower_limb": ["L6"]}
MISSING_DOMAIN_LABELS = {"lower_limb": "the walking video"}


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
    "feeling_today": {
        "id": "feeling_today",
        "domain": "wellbeing",
        "question": "How do you feel today?",
        "type": "single",
        "options": ["good", "okay", "low", "unwell"],
        "required": False,
    },
    "caregiver_today": {
        "id": "caregiver_today",
        "domain": "support",
        "question": "Is a caregiver or helper available to you today?",
        "type": "single",
        "options": ["with_me_now", "available_later", "not_today"],
        "required": False,
    },
    "session_preference": {
        "id": "session_preference",
        "domain": "exercise",
        "question": "Would you like a normal, lighter, or rest and recovery session today?",
        "type": "single",
        "options": ["normal", "lighter", "rest_recovery"],
        "required": False,
    },
    "spasticity_change": {
        "id": "spasticity_change",
        "domain": "tolerance",
        "question": "Any new or changed muscle stiffness, tightness, or spasms since last time?",
        "type": "single",
        "options": ["no", "same_as_usual", "new_or_worse"],
        "required": False,
    },
}


# The five daily check-in topics from spec section 3.1, served at every
# session start. Answers modulate the day's dose and gate caregiver tasks;
# a rest choice is honoured without penalty.
DAILY_CHECK_IN_QUESTION_IDS = (
    "feeling_today",
    "sudden_change",
    "falls",
    "fatigue",
    "caregiver_today",
    "session_preference",
)


def daily_check_in_questions() -> List[Dict[str, Any]]:
    return [dict(QUESTION_BANK[question_id]) for question_id in DAILY_CHECK_IN_QUESTION_IDS]



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
    functional_profile = classify_functional_rehab_profile(profile)
    missing = list(functional_profile["missing_fields"])
    base = {
        "policy_version": CARE_POLICY_VERSION,
        "package_id": "initial",
        "functional_profile": functional_profile,
        "missing_answers": missing,
        "task_ids": [],
        "task_count": 0,
        "excluded": [],
        "requires_helper": False,
        "helper_assisted_task_ids": [],
        "helper_confirmation_required": False,
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

    # Task gate (spec Tier 2): a task is assigned whenever the patient can
    # attempt it independently OR with a helper's support. Only an answer that
    # rules the movement out entirely ("no movement even with help", cannot
    # sit for seated tasks, cannot walk / advised not to walk) excludes it.
    # When help is needed but no caregiver was reported, the tasks stay
    # assigned and the start is paused until a helper is confirmed present.
    assessment_domains = set(functional_profile["assessment_domains"])
    candidate_task_ids = set(functional_profile["candidate_task_ids"])
    active_arm = arm in {"most_movements", "some_movement"}
    helper_capable_arm = arm in {"help_only", "not_sure"}
    active_hand = hand in {"opens_and_moves", "some_finger_movement", "very_little_movement"}
    helper_capable_hand = hand in {"help_only", "not_sure"}
    seated_task_possible = sitting in {"independent", "needs_support"}
    seated_support_needed = sitting == "needs_support"
    helper_assisted_task_ids: List[str] = []

    # An unaffected arm can position an affected hand, but it is not itself a
    # reason to assign upper-limb assessment tasks.
    arm_positioning_possible = seated_task_possible and (active_arm or helper_capable_arm or arm == "not_affected")
    hand_positioning_possible = seated_task_possible and (active_hand or helper_capable_hand or hand == "not_affected")
    upper_profile_tasks = [task_id for task_id in INITIAL_TASKS_BY_DOMAIN["upper_limb"] if task_id in candidate_task_ids]
    skipped_upper_tasks = [task_id for task_id in INITIAL_TASKS_BY_DOMAIN["upper_limb"] if task_id not in candidate_task_ids]
    if skipped_upper_tasks and "upper_limb" in assessment_domains:
        excluded.append({
            "task_ids": skipped_upper_tasks,
            "reason": "This functional profile uses a shorter upper-limb screen rather than the detailed task set.",
        })
    if "upper_limb" not in assessment_domains or not upper_profile_tasks:
        excluded.append({
            "task_ids": ["T1", "T2", "T3"],
            "reason": "No current affected-arm difficulty was reported, so upper-limb camera tasks are not needed for this profile.",
        })
    elif arm_positioning_possible:
        task_ids.extend(upper_profile_tasks)
        if helper_capable_arm or seated_support_needed:
            helper_assisted_task_ids.extend(upper_profile_tasks)
    else:
        reason = (
            "These seated reaching tasks need the patient to sit upright safely without being held."
            if not seated_task_possible
            else "No affected-arm movement was reported, even with help, so an active reaching task cannot be measured yet."
        )
        excluded.append({"task_ids": upper_profile_tasks, "reason": reason})

    hand_profile_tasks = [task_id for task_id in INITIAL_TASKS_BY_DOMAIN["hand"] if task_id in candidate_task_ids]
    skipped_hand_tasks = [task_id for task_id in INITIAL_TASKS_BY_DOMAIN["hand"] if task_id not in candidate_task_ids]
    if skipped_hand_tasks and "hand" in assessment_domains:
        excluded.append({
            "task_ids": skipped_hand_tasks,
            "reason": "This functional profile uses a shorter hand-control screen rather than the detailed task set.",
        })
    if "hand" not in assessment_domains or not hand_profile_tasks:
        excluded.append({
            "task_ids": ["H1", "H3", "H4"],
            "reason": "No current affected-hand difficulty was reported, so hand-control camera tasks are not needed for this profile.",
        })
    elif hand_positioning_possible:
        task_ids.extend(hand_profile_tasks)
        if helper_capable_hand or seated_support_needed or arm in {"help_only", "no_movement", "not_sure"}:
            helper_assisted_task_ids.extend(hand_profile_tasks)
    else:
        reason = (
            "These hand tasks require the affected hand to be raised safely in front of the camera."
            if not seated_task_possible
            else "No affected-finger movement was reported, even with help, so an active hand task cannot be measured yet."
        )
        excluded.append({"task_ids": hand_profile_tasks, "reason": reason})

    if "lower_limb" not in assessment_domains:
        excluded.append({
            "task_ids": ["L6"],
            "reason": "No current lower-limb or mobility difficulty was reported, so the walking video is not needed for this profile.",
        })
    elif mobility in {"independent", "cane", "walker"}:
        task_ids.append("L6")
        safety_notes.append("Use the usual walking aid and have a separate helper nearby if normally needed for safety.")
    elif mobility == "person_assist":
        task_ids.append("L6")
        helper_assisted_task_ids.append("L6")
        safety_notes.append(
            "The helper must stay hands-on for the whole walking task, and a second person should film from the side. Alira records this walk as helper-supported."
        )
    else:
        walking_exclusion_reasons = {
            "not_cleared": "Walking has been advised against for this patient, so the walking video is never assigned.",
            "unable_walk": "The patient cannot walk at the moment, so the walking video is not assigned.",
            "wheelchair": "The patient uses a wheelchair, so the walking video is not assigned.",
            "unsure": "It is not clear that walking is currently safe, so the walking video is not assigned.",
        }
        excluded.append({
            "task_ids": ["L6"],
            "reason": walking_exclusion_reasons.get(
                mobility,
                "Walking video is assigned only when the patient can walk with, at most, hands-on help from another person.",
            ),
        })

    if helper_assisted_task_ids:
        requires_helper = True
        safety_notes.append(
            "A carer should stay within arm's reach to steady or guide the affected side, while the patient attempts each movement themselves so Alira can measure it."
        )

    if pain in {"moderate", "not_sure"}:
        safety_notes.append("Use a comfortable range and stop if pain increases, dizziness occurs, or movement feels unsafe.")
    if requires_helper:
        safety_notes.append("A trusted helper should stay nearby throughout the assessment.")

    selected = set(task_ids)
    task_ids = [task_id for task_id in INITIAL_ASSESSMENT_TASK_IDS if task_id in selected]
    helper_assisted_task_ids = [task_id for task_id in INITIAL_ASSESSMENT_TASK_IDS if task_id in set(helper_assisted_task_ids)]
    helper_needed_to_start = bool(helper_assisted_task_ids) or instruction_support == "helper_required"
    if helper_needed_to_start:
        requires_helper = True

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

    if helper_needed_to_start and not has_caregiver:
        return {
            **base,
            "status": "support_needed",
            "can_start": False,
            "helper_confirmation_required": True,
            "task_ids": task_ids,
            "task_count": len(task_ids),
            "excluded": excluded,
            "requires_helper": True,
            "helper_assisted_task_ids": helper_assisted_task_ids,
            "safety_notes": safety_notes,
            "message": (
                f"Alira assigned {len(task_ids)} task{'s' if len(task_ids) != 1 else ''}, but they need a helper with you. "
                "The assessment stays paused until you confirm a helper is present."
            ),
        }

    message = (
        f"Your answers fit the {functional_profile['label'].lower()} functional profile. "
        f"Alira selected {len(task_ids)} suitable task{'s' if len(task_ids) != 1 else ''} from the approved initial assessment."
    )
    if requires_helper:
        message += " Please begin the assessment with a carer or family member nearby."

    return {
        **base,
        "status": "ready",
        "can_start": True,
        "task_ids": task_ids,
        "task_count": len(task_ids),
        "excluded": excluded,
        "requires_helper": requires_helper,
        "helper_assisted_task_ids": helper_assisted_task_ids,
        "safety_notes": safety_notes,
        "message": message,
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
    # Spec 5.1: every survey re-screens spasticity and the three functional
    # domains so the reassessment task set and tiers can be updated.
    ids.append("spasticity_change")
    unique = list(dict.fromkeys(ids))
    for rescreen in ("arm_use", "hand_use", "walking_confidence"):
        if rescreen not in unique and len(unique) < MAX_CHECK_IN_QUESTIONS:
            unique.append(rescreen)
    unique = unique[:MAX_CHECK_IN_QUESTIONS]
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

    # Spec 3.2 / 7.2: today's check-in shapes today's session. A rest choice is
    # honoured without penalty; high fatigue, high pain, or a "lighter" choice
    # reduces today's dose without changing the underlying plan.
    preference = str(_answer(latest_check_in, "session_preference", "")).lower()
    fatigue = str(_answer(latest_check_in, "fatigue", "")).lower()
    try:
        pain_score = float(_answer(latest_check_in, "pain", ""))
    except (TypeError, ValueError):
        pain_score = None
    if safety["blocks_exercise"]:
        todays_mode, todays_factor = "hold", 0.0
        todays_reason = "Exercise is paused for safety until the reported change is reviewed."
    elif preference == "rest_recovery":
        todays_mode, todays_factor = "rest", 0.0
        todays_reason = "A rest and recovery day was chosen. This is honoured without any penalty to streaks or points."
    elif preference == "lighter" or fatigue in {"quite_a_bit", "a_lot"} or (pain_score is not None and pain_score >= 5):
        todays_mode, todays_factor = "lighter", 0.7
        todays_reason = "Today's session is lighter because of the check-in answers (preference, fatigue, or pain)."
    else:
        todays_mode, todays_factor = "normal", 1.0
        todays_reason = "Today's session runs at the planned dose."

    # Spec 2.2: performance far above expectation triggers early reassessment
    # rather than silently continuing.
    tolerance_answer = str(_answer(latest_check_in, "exercise_tolerance", "")).lower()
    function_answer = str(_answer(latest_check_in, "function_change", "")).lower()
    early_reassessment = bool(
        latest_assessment
        and tolerance_answer == "too_easy"
        and function_answer in {"much_easier", "a_little_easier"}
        and not safety["blocks_assessment"]
    )

    # Spec 7.2: new or worsening spasticity is always considered.
    spasticity_flag = str(_answer(latest_check_in, "spasticity_change", "")).lower() == "new_or_worse"

    return {
        "action": action,
        "dose_change_percent": dose_change,
        "reason": reason,
        "approved_exercise_ids": active_ids,
        "prescriptions": prescriptions,
        "todays_session": {
            "mode": todays_mode,
            "dose_factor": todays_factor,
            "reason": todays_reason,
            "no_penalty": todays_mode == "rest",
        },
        "early_reassessment_recommended": early_reassessment,
        "spasticity_review_needed": spasticity_flag,
        "spasticity_note": (
            "New or worsening stiffness or spasm was reported. Prefer relaxation and slow, supported range work today, "
            "avoid fast forceful repetitions of the stiff muscle group, and tell the clinical team if it persists."
            if spasticity_flag else None
        ),
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
    missed_days: int = 0,
    week_round_complete: bool = False,
    missing_domains: Sequence[str] = (),
    caregiver_mode: bool = False,
    caregiver_remaining_ids: Sequence[str] = (),
    caregiver_re_screen: bool = False,
    survey_report_viewed: bool = False,
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

    # No camera assessment is possible: the next step goes straight to the
    # caregiver-delivered programme - qualitative strengthening and relaxation
    # of the affected muscle groups from approved guidance, ticked off daily
    # by the carer. The clinical team reviews the case in parallel.
    if caregiver_mode and not has_initial_assessment:
        # Report first: the survey-only assessment report (daily-activity
        # scores, the anatomy pin-point map, and the rehab plan) is viewed
        # before the daily caregiver-delivered rehab plan takes over.
        if not survey_report_viewed:
            return {
                "action": "view_survey_report",
                "title": "Your assessment report is ready",
                "message": (
                    "Alira prepared your report from your survey answers: your daily-activity scores, "
                    "the areas that need attention on the body map, and your rehab plan."
                ),
                "cta": "View my report",
                "destination": "survey_report",
                "secondary_action": None,
            }
        remaining = list(caregiver_remaining_ids)
        re_screen_secondary = {
            "action": "update_readiness_answers",
            "title": "Movement is returning",
            "message": (
                "Your carer has recorded the patient joining in with small movements more than once this week. "
                "Update the movement-readiness answers so Alira can check whether camera tasks are now suitable."
            ),
            "cta": "Update readiness answers",
            "destination": "initial_assessment",
        } if caregiver_re_screen else None
        if remaining:
            return {
                "action": "caregiver_exercises",
                "title": "Today's caregiver-delivered exercises",
                "message": (
                    "The camera tasks are not suitable right now, so recovery continues with a "
                    "caregiver-delivered programme: gentle strengthening and relaxation of the affected "
                    "muscle groups, following approved guidance. Your carer ticks each routine off once "
                    "it is done today, and the clinical team reviews the next step."
                ),
                "cta": "Open the caregiver programme",
                "destination": "caregiver_plan",
                "remaining_programme_ids": remaining,
                "secondary_action": re_screen_secondary,
            }
        return {
            "action": "caregiver_session_complete",
            "title": "Today's caregiver session is complete",
            "message": "Every routine is ticked off for today. Rest now - the next caregiver session is tomorrow.",
            "cta": "See your progress",
            "destination": "progress",
            "secondary_action": re_screen_secondary,
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

    # Spec 5: a completed week-round routes to the survey before more exercises.
    if week_round_complete and survey_reminder_due:
        return {
            "action": "recovery_check_in",
            "title": "You completed a full exercise round",
            "message": "One week of sessions is done. A short check-in comes next, then a reassessment to measure your progress and refresh your plan.",
            "cta": "Start the check-in",
            "destination": "survey",
            "secondary_action": None,
        }

    # Partial initial assessment: ask for the one missing task, with an easy
    # no-penalty way to defer and continue with the plan already issued.
    if missing_domains:
        label = MISSING_DOMAIN_LABELS.get(missing_domains[0], "the remaining task")
        return {
            "action": "complete_missing_assessment",
            "title": f"One check is still missing: {label}",
            "message": (
                "Your plan for the assessed areas is already active. When a helper is with you, "
                f"record {label} so the plan can cover that area too. If you cannot do it today, "
                "that is completely fine - your current plan continues."
            ),
            "cta": "Record it now",
            "destination": "assessment",
            "missing_domains": list(missing_domains),
            "secondary_action": {
                "action": "defer_missing_assessment",
                "title": "I can't do this today",
                "message": "Alira will continue with your current plan and ask again another day.",
                "cta": "Continue with my current plan",
                "destination": "rehab_plan",
                "defer_domains": list(missing_domains),
            },
        }

    # Spec 2.2: warm re-entry after missed days - no guilt language.
    if missed_days >= 3 and active_ids and remaining_ids:
        return {
            "action": "gentle_re_entry",
            "title": "Welcome back",
            "message": "It is good to see you again. Today's session restarts at a gentler intensity - missed days are simply part of recovery, never a failure.",
            "cta": "Start a gentle session",
            "destination": "rehab_plan",
            "remaining_exercise_ids": remaining_ids,
            "secondary_action": None,
        }

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
    initial_assessments = [
        item for item in assessments
        if str(item.get("assessment_package") or "initial") == "initial"
    ]
    has_initial_assessment = bool(initial_assessments)
    initial_assessment_completed_at = max(
        (str(item.get("created_at") or "") for item in initial_assessments),
        default="",
    ) or None
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

    # Spec 1.2 / 5: an exercise round is one week of daily sessions. Completing
    # a round triggers the survey and reassessment sequence.
    plan_issued_at = _as_utc((latest_assessment or {}).get("created_at"))
    session_days_this_round = {
        completed_at.date()
        for item in activities
        if (completed_at := _as_utc(item.get("completed_at")))
        and (not plan_issued_at or completed_at >= plan_issued_at)
    }
    round_length_days = 7
    week_round_complete = bool(latest_assessment and len(session_days_this_round) >= round_length_days)

    # Spec 2.2: a warm, no-guilt re-entry after several missed days.
    missed_days = (now.date() - latest_activity_at.date()).days if latest_activity_at else 0

    exercise_plan = _exercise_action(latest_check_in, latest_assessment, safety, sessions_last_7_days)
    if week_round_complete or exercise_plan.get("early_reassessment_recommended"):
        survey_due = True
        if not safety["blocks_assessment"]:
            assessment_due = True
            if not pending_issue:
                selection = dict(selection)
                selection["trigger"] = "round_complete" if week_round_complete else "early_reassessment"
            assessment_due_at = now
    if missed_days >= 3 and exercise_plan.get("todays_session", {}).get("mode") == "normal":
        todays = dict(exercise_plan.get("todays_session") or {})
        todays.update({
            "mode": "lighter",
            "dose_factor": 0.7,
            "reason": "Welcome back. After a few days away, today's session restarts at a reduced intensity - missed days are context, never failure.",
        })
        exercise_plan = {**exercise_plan, "todays_session": todays}
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

    tiers = functional_tiers(profile)

    # When the readiness answers rule out every camera task, the patient is not
    # left waiting on clinical review with nothing to do: recovery starts with
    # a caregiver-delivered programme covering each ruled-out domain, delivered
    # qualitatively and ticked off daily by the carer.
    camera_assessment_impossible = bool(
        not has_initial_assessment
        and initial_readiness
        and initial_readiness.get("status") == "clinical_review"
        and not initial_readiness.get("task_ids")
    )
    if camera_assessment_impossible:
        excluded_domains: List[str] = []
        for exclusion in initial_readiness.get("excluded") or []:
            for task_id in exclusion.get("task_ids") or []:
                if str(task_id).startswith("T"):
                    excluded_domains.append("upper_limb")
                elif str(task_id).startswith("H"):
                    excluded_domains.append("hand")
                elif str(task_id).startswith("L"):
                    excluded_domains.append("lower_limb")
        caregiver_plan = caregiver_delivered_plan(profile, tiers, force_domains=list(dict.fromkeys(excluded_domains)))
    elif tiers["any_tier_one"]:
        caregiver_plan = caregiver_delivered_plan(profile, tiers)
    else:
        caregiver_plan = {"applicable": False, "programmes": []}

    caregiver_programme_ids = [str(programme.get("id")) for programme in caregiver_plan.get("programmes") or [] if programme.get("id")]
    caregiver_completed_today_ids = [
        programme_id for programme_id in caregiver_programme_ids if programme_id in completed_exercise_ids_today
    ]
    caregiver_remaining_today_ids = [
        programme_id for programme_id in caregiver_programme_ids if programme_id not in completed_exercise_ids_today
    ]
    caregiver_plan["daily_delivery"] = {
        "required_today": camera_assessment_impossible and bool(caregiver_programme_ids),
        "checkoff_instruction": "Tick each routine once you have delivered it today. The day earns its check mark when every routine is done.",
        "programme_ids": caregiver_programme_ids,
        "completed_today_ids": caregiver_completed_today_ids,
        "remaining_today_ids": caregiver_remaining_today_ids,
        "completed_today": bool(caregiver_programme_ids) and not caregiver_remaining_today_ids,
    }
    caregiver_progress = (
        caregiver_progress_summary(activities, caregiver_programme_ids, now)
        if caregiver_programme_ids
        else None
    )
    if caregiver_progress is not None:
        caregiver_plan["progress"] = caregiver_progress

    # Partial initial assessment: prompt for the missing task unless the
    # patient deferred it today (a decline is context, never a failure).
    deferrals = dict(profile.get("_assessment_deferrals") or {})
    today_iso = now.date().isoformat()
    missing_domains = [
        domain for domain in missing_assessment_domains(latest_assessment, profile)
        if str((deferrals.get(domain) or {}).get("deferred_at") or "")[:10] != today_iso
    ]
    missing_prompt = bool(missing_domains and has_initial_assessment and safety["status"] == "clear" and not assessment_due)

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
        missed_days=missed_days,
        week_round_complete=week_round_complete,
        missing_domains=missing_domains if missing_prompt else [],
        caregiver_mode=camera_assessment_impossible and bool(caregiver_programme_ids),
        caregiver_remaining_ids=caregiver_remaining_today_ids,
        caregiver_re_screen=bool(caregiver_progress and caregiver_progress.get("re_screen_suggested")),
        survey_report_viewed=bool(profile.get("_survey_report_viewed_at")),
    )

    return {
        "version": CARE_POLICY_VERSION,
        "generated_at": now.isoformat(),
        "account_state": {
            "has_completed_initial_assessment": has_initial_assessment,
            "initial_assessment_completed_at": initial_assessment_completed_at,
        },
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
            "requires_helper": bool((initial_readiness or {}).get("requires_helper")),
            "helper_confirmation_required": bool((initial_readiness or {}).get("helper_confirmation_required")),
            "missing_domains": missing_domains,
            "missing_task_ids": [task for domain in missing_domains for task in MISSING_DOMAIN_TASKS.get(domain, [])],
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
        "daily_check_in": {
            "questions": daily_check_in_questions(),
            "purpose": "Asked at the start of every session. Answers shape today's dose, gate caregiver tasks, and screen for red flags before any activity.",
            "rest_is_honoured_without_penalty": True,
        },
        "exercise_round": {
            "round_length_days": round_length_days,
            "session_days_completed": len(session_days_this_round),
            "complete": week_round_complete,
            "started_at": plan_issued_at.isoformat() if plan_issued_at else None,
            "reason": "One round is one week of daily sessions; completing it triggers the survey and reassessment.",
        },
        "functional_tiers": tiers,
        "caregiver_plan": caregiver_plan,
        "survey_report": {
            "available": camera_assessment_impossible,
            "viewed": bool(profile.get("_survey_report_viewed_at")),
            "viewed_at": profile.get("_survey_report_viewed_at"),
            "reason": "With no camera tasks assignable, the assessment report is built from the survey alone and leads to the caregiver-delivered rehab plan.",
        },
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
