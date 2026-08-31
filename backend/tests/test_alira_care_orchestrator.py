from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.alira_care_orchestrator import (
    ASSESSMENT_READINESS_FIELDS,
    MAX_CHECK_IN_QUESTIONS,
    build_adaptive_care_plan,
    initial_assessment_recommendation,
    validate_check_in_answers,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def ready_profile(**overrides):
    profile = {
        "months_since_stroke": 6,
        "affected_areas": ["right_upper", "right_lower"],
        "sitting_ability": "independent",
        "affected_arm_movement": "some_movement",
        "affected_hand_movement": "some_finger_movement",
        "mobility_level": "walker",
        "movement_pain": "mild",
        "instruction_support": "independent",
        "has_caregiver": False,
    }
    profile.update(overrides)
    return profile


def iso_days_ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def assessment(days_ago: int = 1, issues=None, plan=None, assessment_id: str = "a1", gate=None):
    result = {
        "id": assessment_id,
        "created_at": iso_days_ago(days_ago),
        "functional_issues": issues or [],
        "rehab_plan": plan or [],
    }
    if gate is not None:
        result["clinical_review_gate"] = gate
    return result


def check_in(days_ago: int = 0, **answers):
    return {
        "id": "c1",
        "created_at": iso_days_ago(days_ago),
        "answers": answers,
    }


def test_starting_patient_gets_short_survey_and_initial_assessment():
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 1, "affected_areas": ["right_upper"]},
        [],
        [],
        now=NOW,
    )

    assert plan["stage"] == "starting"
    # The survey prompt is gated until the initial assessment exists (spec 2.1:
    # a just-registered patient's single next step is the initial assessment).
    assert plan["survey"]["due"] is False
    assert plan["survey"]["schedule_due"] is True
    assert plan["survey"]["questions"] == []
    assert plan["next_step"]["action"] == "initial_assessment"
    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["packages"] == ["initial"]
    assert plan["assessment"]["recommended_packages"] == ["initial"]
    assert plan["assessment"]["can_start"] is False
    assert set(plan["assessment"]["missing_answers"]) == set(ASSESSMENT_READINESS_FIELDS)


def test_initial_assessment_selects_all_tasks_only_when_prerequisites_are_met():
    recommendation = initial_assessment_recommendation(ready_profile())

    assert recommendation["status"] == "ready"
    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]


def test_walking_with_hands_on_help_is_assigned_as_a_helper_supported_task():
    recommendation = initial_assessment_recommendation(ready_profile(
        mobility_level="person_assist",
        has_caregiver="yes",
    ))

    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]
    assert recommendation["helper_assisted_task_ids"] == ["L6"]
    assert recommendation["requires_helper"] is True
    assert any("hands-on" in note for note in recommendation["safety_notes"])


@pytest.mark.parametrize("mobility", ["not_cleared", "unable_walk", "wheelchair", "unsure"])
def test_walking_video_is_never_assigned_when_unassisted_walking_is_not_reported(mobility):
    recommendation = initial_assessment_recommendation(ready_profile(mobility_level=mobility))

    assert "L6" not in recommendation["task_ids"]
    walking_exclusion = next(item for item in recommendation["excluded"] if item["task_ids"] == ["L6"])
    assert walking_exclusion["reason"]
    if mobility == "not_cleared":
        assert "advised against" in walking_exclusion["reason"]


def test_seated_tasks_stay_assigned_with_carer_support_when_arm_moves_only_with_help():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="help_only",
        has_caregiver="yes",
        mobility_level="not_cleared",
    ))

    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert recommendation["requires_helper"] is True
    assert recommendation["helper_assisted_task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert any("carer" in note.lower() for note in recommendation["safety_notes"])
    assert "carer" in recommendation["message"].lower()


def test_help_only_arm_without_a_carer_keeps_tasks_but_pauses_start_for_helper_confirmation():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="help_only",
        has_caregiver="no",
    ))

    assert recommendation["status"] == "support_needed"
    assert recommendation["can_start"] is False
    assert recommendation["helper_confirmation_required"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]
    assert recommendation["helper_assisted_task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert "helper" in recommendation["message"].lower()


def test_uncertain_arm_and_hand_answers_still_assign_tasks_when_a_carer_is_available():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="not_sure",
        affected_hand_movement="not_sure",
        has_caregiver="yes",
    ))

    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]
    assert recommendation["requires_helper"] is True
    assert recommendation["helper_assisted_task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]


def test_no_arm_movement_is_excluded_even_with_a_carer_available():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="no_movement",
        has_caregiver="yes",
    ))

    assert all(task_id not in recommendation["task_ids"] for task_id in ("T1", "T2", "T3", "H1", "H3", "H4"))
    assert any("even with help" in item["reason"] for item in recommendation["excluded"])


def test_initial_assessment_does_not_assign_active_arm_or_hand_tasks_without_active_arm_movement():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="no_movement",
        affected_hand_movement="some_finger_movement",
        mobility_level="wheelchair",
    ))

    assert recommendation["can_start"] is False
    assert recommendation["requires_clinician_review"] is True
    assert recommendation["task_ids"] == []


def test_initial_assessment_keeps_tasks_for_an_unaffected_arm_and_hand():
    recommendation = initial_assessment_recommendation(ready_profile(
        affected_arm_movement="not_affected",
        affected_hand_movement="not_affected",
    ))

    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]


def test_helper_required_treats_saved_no_answer_as_no_available_caregiver():
    recommendation = initial_assessment_recommendation(ready_profile(
        instruction_support="helper_required",
        has_caregiver="no",
    ))

    assert recommendation["can_start"] is False
    assert recommendation["status"] == "support_needed"
    # The tasks stay assigned; only the start is paused until a helper is confirmed.
    assert recommendation["helper_confirmation_required"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]


def test_initial_assessment_pauses_for_severe_or_worsening_pain():
    recommendation = initial_assessment_recommendation(ready_profile(movement_pain="severe_or_worsening"))

    assert recommendation["status"] == "clinical_review"
    assert recommendation["can_start"] is False
    assert recommendation["requires_clinician_review"] is True


def test_early_stage_uses_three_day_survey_and_fourteen_day_assessment_cadence():
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 2, "affected_areas": ["right_upper"]},
        [assessment(days_ago=4)],
        [check_in(days_ago=2, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )

    assert plan["stage"] == "early"
    assert plan["survey"]["cadence_days"] == 3
    assert plan["survey"]["due"] is False
    assert plan["assessment"]["cadence_days"] == 14
    assert plan["assessment"]["due"] is False


def test_stable_stage_reduces_prompt_frequency():
    assessments = [
        assessment(days_ago=10, issues=[], assessment_id="a2", gate={"status": "no_rehab_needed"}),
        assessment(days_ago=70, issues=[], assessment_id="a1", gate={"status": "no_rehab_needed"}),
    ]
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 18, "affected_areas": ["right_upper"]},
        assessments,
        [check_in(days_ago=5, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )

    assert plan["stage"] == "stable"
    assert plan["survey"]["cadence_days"] == 14
    assert plan["assessment"]["cadence_days"] == 56
    assert plan["survey"]["due"] is False
    assert plan["assessment"]["due"] is False


def test_pending_or_unvalidated_analysis_never_becomes_stable():
    assessments = [
        assessment(days_ago=10, issues=[], assessment_id="a2", gate={"status": "awaiting_model_analysis"}),
        assessment(days_ago=70, issues=[], assessment_id="a1", gate={"status": "clear"}),
    ]
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 18},
        assessments,
        [check_in(days_ago=5, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )

    assert plan["stage"] == "active"


def test_sudden_new_symptoms_block_camera_assessment_and_exercise():
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 7, "affected_areas": ["right_upper"]},
        [assessment(days_ago=30, plan=[{"id": "ex_reach"}])],
        [check_in(days_ago=0, sudden_change="yes", function_change="much_harder")],
        now=NOW,
    )

    assert plan["stage"] == "needs_review"
    assert plan["safety"]["status"] == "emergency"
    assert plan["safety"]["blocks_assessment"] is True
    assert plan["assessment"]["due"] is False
    assert plan["exercise_plan"]["action"] == "hold"
    assert "999" in plan["safety"]["message"]


def test_high_pain_holds_plan_and_too_hard_reduces_only_the_next_dose():
    current = assessment(days_ago=2, plan=[{"id": "ex_reach"}, {"id": "ex_hand"}])
    high_pain = build_adaptive_care_plan(
        {"months_since_stroke": 8},
        [current],
        [check_in(pain=8, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )
    assert high_pain["exercise_plan"]["action"] == "hold"

    too_hard = build_adaptive_care_plan(
        {"months_since_stroke": 8},
        [current],
        [check_in(pain=2, sudden_change="no", function_change="about_the_same", exercise_tolerance="too_hard")],
        now=NOW,
    )
    assert too_hard["exercise_plan"]["action"] == "reduce_next_session"
    assert too_hard["exercise_plan"]["dose_change_percent"] == -20
    assert too_hard["exercise_plan"]["approved_exercise_ids"] == ["ex_reach", "ex_hand"]


def test_targeted_packages_follow_saved_and_observed_domains():
    issues = [
        {"code": "HAND_OPENING", "phenotype_domain": "hand", "related_task": "H1"},
        {"code": "GAIT_ASYMMETRY", "phenotype_domain": "gait", "related_task": "W1"},
    ]
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 10, "affected_areas": ["right_upper", "right_lower"]},
        [assessment(days_ago=60, issues=issues)],
        [check_in(days_ago=8, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )

    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["packages"] == ["upper_limb"]
    assert plan["assessment"]["task_ids"] == ["T1", "T2", "T3"]
    assert plan["assessment"]["recommended_packages"] == ["upper_limb"]


def test_recommended_packages_remain_available_for_patient_requested_assessment():
    issues = [{"code": "HAND_OPENING", "phenotype_domain": "hand", "related_task": "H1"}]
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 10, "affected_areas": ["right_upper"]},
        [assessment(days_ago=2, issues=issues)],
        [check_in(days_ago=1, sudden_change="no", function_change="about_the_same")],
        now=NOW,
    )

    assert plan["assessment"]["due"] is False
    assert plan["assessment"]["packages"] == []
    assert plan["assessment"]["recommended_packages"] == ["upper_limb"]


def test_new_functional_issue_opens_one_targeted_assessment_before_routine_due_date():
    issue_report = {
        "id": "afi-new-hand",
        "category": "hand_opening",
        "status": "pending",
        "created_at": iso_days_ago(0),
    }
    plan = build_adaptive_care_plan(
        ready_profile(months_since_stroke=10),
        [assessment(days_ago=2)],
        [check_in(days_ago=1, sudden_change="no", function_change="about_the_same")],
        [],
        [issue_report],
        now=NOW,
    )

    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["trigger"] == "new_functional_issue"
    assert plan["assessment"]["exception_for_new_issue"] is True
    assert plan["assessment"]["packages"] == ["hand"]
    assert plan["assessment"]["task_ids"] == ["H1", "H3"]
    assert plan["assessment"]["issue_report_id"] == "afi-new-hand"


def test_alira_autonomously_applies_only_incremental_approved_dose_changes():
    current = assessment(days_ago=2, plan=[{
        "id": "ex_reach",
        "sets": 3,
        "reps": 10,
        "frequency": "3 days per week",
    }])
    plan = build_adaptive_care_plan(
        ready_profile(months_since_stroke=8),
        [current],
        [check_in(
            pain=0,
            sudden_change="no",
            function_change="a_little_easier",
            exercise_tolerance="too_easy",
        )],
        [
            {"id": f"activity-{index}", "completed_at": iso_days_ago(index), "exercise_id": "ex_reach"}
            for index in range(3)
        ],
        now=NOW,
    )

    decision = plan["exercise_plan"]
    assert decision["action"] == "small_progression"
    assert decision["dose_change_percent"] == 10
    assert decision["requires_approval"] is False
    assert decision["prescriptions"] == [{
        "exercise_id": "ex_reach",
        "sets": 3,
        "reps": 11,
        "weekly_frequency": 4,
        "frequency": "4 days per week",
    }]
    assert plan["autonomy"]["requires_per_decision_approval"] is False


def test_novel_content_is_only_a_reviewable_draft():
    plan = build_adaptive_care_plan(
        {
            "months_since_stroke": 6,
            "affected_areas": ["face_speech"],
            "primary_goal": "Speak clearly during family meals",
        },
        [],
        [],
        now=NOW,
    )

    assert plan["content_proposals"]
    assert all(item["status"] == "draft_clinical_review" for item in plan["content_proposals"])
    assert plan["autonomy"]["may_activate_novel_clinical_content"] is False
    assert plan["autonomy"]["may_change_app_features"] is False
    assert plan["autonomy"]["may_draft_novel_assessment_tasks"] is True
    assert all(item.get("not_for_patient_use") is True for item in plan["content_proposals"])
    assert all(item.get("proposed_steps") for item in plan["content_proposals"] if item["type"] == "assessment_task")


def test_daily_activity_monitoring_uses_sessions_for_reminders_without_model_calls():
    current = assessment(days_ago=2, plan=[{"id": "ex_reach"}])
    no_activity = build_adaptive_care_plan(
        {"months_since_stroke": 8},
        [current],
        [check_in(sudden_change="no", function_change="about_the_same")],
        [],
        now=NOW,
    )
    assert no_activity["daily_monitoring"]["reminder_needed"] is True
    assert no_activity["daily_monitoring"]["next_day_action"] == "send_plan_reminder"
    assert no_activity["daily_monitoring"]["uses_model"] is False

    completed_today = build_adaptive_care_plan(
        {"months_since_stroke": 8},
        [current],
        [check_in(sudden_change="no", function_change="about_the_same")],
        [{"id": "activity-1", "completed_at": NOW.isoformat(), "exercise_id": "ex_reach"}],
        now=NOW,
    )
    assert completed_today["daily_monitoring"]["sessions_last_7_days"] == 1
    assert completed_today["daily_monitoring"]["next_day_action"] == "recognize_completed_session"


def test_check_in_validation_rejects_unknown_or_out_of_range_answers():
    assert validate_check_in_answers({"pain": 4, "sudden_change": "no"}) == {"pain": 4, "sudden_change": "no"}
    with pytest.raises(ValueError, match="unsupported question ids"):
        validate_check_in_answers({"diagnosis": "fine"})
    with pytest.raises(ValueError, match="between 0 and 10"):
        validate_check_in_answers({"pain": 11})


def test_frontend_connects_voice_check_in_targeted_assessment_and_plan_guardrails():
    root = Path(__file__).resolve().parents[2]
    call = (root / "frontend" / "app" / "alira-call.tsx").read_text(encoding="utf-8")
    navigation = (root / "frontend" / "src" / "aliraNavigation.ts").read_text(encoding="utf-8")
    session_check = (root / "frontend" / "app" / "session-check.tsx").read_text(encoding="utf-8")
    task_intro = (root / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")
    rehab_plan = (root / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    exercise = (root / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    notifications = (root / "frontend" / "src" / "utils" / "notifications.ts").read_text(encoding="utf-8")

    assert 'event.name !== "record_rehab_check_in"' in call
    assert 'authedFetch("/api/alira/check-ins"' in call
    assert 'authedFetch("/api/alira/care-plan"' in navigation
    assert "package: params.package || \"initial\"" in session_check
    assert "allowedPackages.includes(params.package as AssessmentPackageId)" in task_intro
    assert "prescriptions" in rehab_plan
    assert "blocks_exercise" in rehab_plan
    assert 'authedFetch("/api/alira/activities"' in exercise
    assert 'identifier: "adaptive_recovery_check_in"' in notifications
    assert 'identifier: "adaptive_movement_assessment"' in notifications
    assert "plan?.assessment?.due_at" in notifications


def test_preparation_tips_follow_the_assigned_tasks():
    root = Path(__file__).resolve().parents[2]
    task_intro = (root / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")

    # Walking guidance only shows when a walking task is actually assigned,
    # and the carer tip only when Alira marked the assessment helper-assisted.
    assert "BASE_PREPARATION_TIPS" in task_intro
    assert "WALKING_PREPARATION_TIPS" in task_intro
    assert "HELPER_PREPARATION_TIP" in task_intro
    assert 'effectiveTaskIds.some((taskId) => taskId.startsWith("L"))' in task_intro
    assert "includesWalkingTask ? WALKING_PREPARATION_TIPS : []" in task_intro
    assert "recommendation?.requires_helper ? [HELPER_PREPARATION_TIP] : []" in task_intro
    assert "const PREPARATION_TIPS" not in task_intro


def test_task_intro_pauses_start_until_the_helper_is_confirmed_present():
    root = Path(__file__).resolve().parents[2]
    task_intro = (root / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")

    # A helper-confirmation pause loads the assigned tasks but locks the Start
    # button behind an explicit "a helper is with me" confirmation.
    assert "helper_confirmation_required?: boolean" in task_intro
    assert 'testID="task-intro-helper-confirm"' in task_intro
    assert "recommendationResponse?.helper_confirmation_required && recommendationResponse?.task_ids?.length" in task_intro
    assert "disabled={loading || (helperConfirmationNeeded && !helperConfirmed)}" in task_intro
    assert "if (helperConfirmationNeeded && !helperConfirmed) return;" in task_intro
    assert "A helper is with me now and will stay for the whole assessment." in task_intro
    assert "Confirm your helper is here first" in task_intro
