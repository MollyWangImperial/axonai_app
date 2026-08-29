from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.alira_care_orchestrator import (
    MAX_CHECK_IN_QUESTIONS,
    build_adaptive_care_plan,
    validate_check_in_answers,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


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
    assert plan["survey"]["due"] is True
    assert 1 <= len(plan["survey"]["questions"]) <= MAX_CHECK_IN_QUESTIONS
    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["packages"] == ["initial"]


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
    assert plan["assessment"]["packages"] == ["upper_limb", "hand", "lower_limb", "balance"]


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
    assert "reduce_next_session" in rehab_plan
    assert "blocks_exercise" in rehab_plan
    assert 'authedFetch("/api/alira/activities"' in exercise
    assert 'identifier: "adaptive_recovery_check_in"' in notifications
    assert 'identifier: "adaptive_movement_assessment"' in notifications
    assert "plan?.assessment?.due_at" in notifications
