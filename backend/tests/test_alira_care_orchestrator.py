from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.alira_care_orchestrator import (
    ASSESSMENT_READINESS_FIELDS,
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
        "assessment_package": "initial",
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


def test_starting_patient_is_prompted_for_initial_assessment_before_adaptive_survey():
    plan = build_adaptive_care_plan(
        {"months_since_stroke": 1, "affected_areas": ["right_upper"]},
        [],
        [],
        now=NOW,
    )

    assert plan["stage"] == "starting"
    assert plan["survey"]["schedule_due"] is True
    assert plan["survey"]["due"] is False
    assert plan["survey"]["questions"] == []
    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["packages"] == ["initial"]
    assert plan["assessment"]["recommended_packages"] == ["initial"]
    assert plan["assessment"]["can_start"] is False
    assert set(plan["assessment"]["missing_answers"]) == set(ASSESSMENT_READINESS_FIELDS)
    assert plan["next_step"]["action"] == "initial_assessment"


def test_first_adaptive_survey_waits_for_cadence_after_initial_assessment():
    plan = build_adaptive_care_plan(
        ready_profile(months_since_stroke=8),
        [assessment(days_ago=1, plan=[{"id": "ex_reach"}])],
        [],
        now=NOW,
    )

    assert plan["survey"]["cadence_days"] == 3
    assert plan["survey"]["due"] is False
    assert plan["next_step"]["action"] == "continue_exercises"
    assert plan["next_step"]["secondary_action"] is None


def test_due_survey_is_secondary_until_today_exercises_are_complete():
    current = assessment(
        days_ago=8,
        issues=[{"code": "SHOULDER_HIKE", "phenotype_domain": "upper_limb"}],
        plan=[{"id": "ex_reach"}, {"id": "ex_hand"}],
    )
    plan = build_adaptive_care_plan(
        ready_profile(months_since_stroke=8),
        [current],
        [check_in(days_ago=8, sudden_change="no", function_change="about_the_same")],
        [{"id": "activity-1", "completed_at": NOW.isoformat(), "exercise_id": "ex_reach"}],
        now=NOW,
    )

    assert plan["survey"]["due"] is True
    assert plan["daily_monitoring"]["remaining_exercise_ids_today"] == ["ex_hand"]
    assert plan["next_step"]["action"] == "continue_exercises"
    assert plan["next_step"]["secondary_action"]["action"] == "recovery_check_in"


def test_due_survey_becomes_primary_after_today_exercises_are_complete():
    current = assessment(
        days_ago=8,
        issues=[{"code": "SHOULDER_HIKE", "phenotype_domain": "upper_limb"}],
        plan=[{"id": "ex_reach"}, {"id": "ex_hand"}],
    )
    activities = [
        {"id": "activity-1", "completed_at": NOW.isoformat(), "exercise_id": "ex_reach"},
        {"id": "activity-2", "completed_at": NOW.isoformat(), "exercise_id": "ex_hand"},
    ]
    plan = build_adaptive_care_plan(
        ready_profile(months_since_stroke=8),
        [current],
        [check_in(days_ago=8, sudden_change="no", function_change="about_the_same")],
        activities,
        now=NOW,
    )

    assert plan["daily_monitoring"]["current_round_complete"] is True
    assert plan["next_step"]["action"] == "recovery_check_in"
    assert plan["next_step"]["secondary_action"] is None


def test_initial_assessment_selects_all_tasks_only_when_prerequisites_are_met():
    recommendation = initial_assessment_recommendation(ready_profile())

    assert recommendation["status"] == "ready"
    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]


def test_initial_assessment_does_not_assign_walking_when_hands_on_help_is_needed():
    recommendation = initial_assessment_recommendation(ready_profile(mobility_level="person_assist"))

    assert recommendation["can_start"] is True
    assert recommendation["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert any("hands-on assistance" in item["reason"] for item in recommendation["excluded"])


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
    home = (root / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    next_step_card = (root / "frontend" / "src" / "components" / "DailyCheckInCard.tsx").read_text(encoding="utf-8")

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
    assert "patient_prompt_enabled" in notifications
    assert "plan={carePlan}" in home
    assert 'nextStep.action === "continue_exercises"' in next_step_card
    assert 'secondary_action?.action === "recovery_check_in"' in next_step_card
