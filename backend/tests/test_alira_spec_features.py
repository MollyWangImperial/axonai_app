"""Tests for the Alira Functional Specification features:

tiers per domain, caregiver-delivered Tier-1 plans, the daily check-in set,
today's-session dose modulation, the week-round loop, early reassessment,
warm re-entry, survey re-screen with spasticity, encouragement (points,
medals, streak freezes), safe sharing, goal-linked exercises, and
activity-driven progress labels.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_alira_spec_test")

from backend import server
from backend.alira_care_orchestrator import (
    ASSISTANCE_LEVELS,
    DAILY_CHECK_IN_QUESTION_IDS,
    build_adaptive_care_plan,
    caregiver_delivered_plan,
    functional_tiers,
)
from backend.daily_activity_metrics import build_daily_activity_metrics
from backend.encouragement import compute_rewards

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def profile(**overrides):
    base = {
        "months_since_stroke": 6,
        "affected_areas": ["right_upper"],
        "sitting_ability": "independent",
        "affected_arm_movement": "most_movements",
        "affected_hand_movement": "opens_and_moves",
        "mobility_level": "independent",
        "movement_pain": "mild",
        "instruction_support": "independent",
        "has_caregiver": True,
    }
    base.update(overrides)
    return base


def assessment(created_days_ago=3, exercise_ids=("EX1", "EX2")):
    return {
        "id": "a1",
        "assessment_package": "initial",
        "created_at": (NOW - timedelta(days=created_days_ago)).isoformat(),
        "rehab_plan": [{"id": eid, "reps": 10, "sets": 2, "frequency": "Daily"} for eid in exercise_ids],
        "functional_issues": [],
    }


def check_in(days_ago=0, **answers):
    return {"id": "c1", "created_at": (NOW - timedelta(days=days_ago)).isoformat(), "answers": answers}


def activity(days_ago, exercise_id="EX1"):
    return {"exercise_id": exercise_id, "completed_at": (NOW - timedelta(days=days_ago)).isoformat()}


# ---------- Tiers and assistance scale (spec 1.3 / 6.2) ----------

def test_assistance_scale_has_six_levels_in_order():
    assert ASSISTANCE_LEVELS == (
        "unable", "maximum_assistance", "moderate_assistance",
        "minimum_assistance", "supervision_only", "fully_independent",
    )


def test_tiers_are_assigned_per_domain():
    tiers = functional_tiers(profile(
        affected_arm_movement="no_movement",
        affected_hand_movement="some_finger_movement",
        mobility_level="independent",
    ))
    assert tiers["by_domain"]["upper_limb"]["tier"] == 1
    assert tiers["by_domain"]["upper_limb"]["camera_assessment"] is False
    assert tiers["by_domain"]["hand"]["tier"] == 2
    assert tiers["by_domain"]["lower_limb"]["tier"] == 3
    assert tiers["any_tier_one"] is True


def test_tier_one_gets_caregiver_delivered_programme_with_stop_rules():
    plan = caregiver_delivered_plan(profile(affected_arm_movement="no_movement"))
    assert plan["applicable"] is True
    assert plan["audience"] == "caregiver"
    assert "upper_limb" in plan["tier_one_domains"]
    programme = plan["programmes"][0]
    assert programme["muscle_groups"]
    assert programme["dose"]
    assert "Stop" in programme["safety_limits"] or "stop" in programme["safety_limits"]
    assert "999" in plan["stop_and_call"]


def test_fully_independent_patient_has_no_caregiver_plan():
    plan_output = build_adaptive_care_plan(profile(), [assessment()], [], [], now=NOW)
    assert plan_output["functional_tiers"]["any_tier_one"] is False
    assert plan_output["caregiver_plan"]["applicable"] is False


# ---------- Daily check-in and dose modulation (spec 3) ----------

def test_care_plan_carries_the_daily_check_in_questions():
    plan = build_adaptive_care_plan(profile(), [assessment()], [], [], now=NOW)
    ids = [question["id"] for question in plan["daily_check_in"]["questions"]]
    assert ids == list(DAILY_CHECK_IN_QUESTION_IDS)
    assert plan["daily_check_in"]["rest_is_honoured_without_penalty"] is True


def test_rest_choice_is_honoured_without_penalty():
    plan = build_adaptive_care_plan(
        profile(), [assessment()], [check_in(session_preference="rest_recovery")], [], now=NOW,
    )
    todays = plan["exercise_plan"]["todays_session"]
    assert todays["mode"] == "rest"
    assert todays["dose_factor"] == 0.0
    assert todays["no_penalty"] is True


def test_severe_pain_holds_exercise_for_safety():
    plan = build_adaptive_care_plan(profile(), [assessment()], [check_in(pain=8)], [], now=NOW)
    assert plan["exercise_plan"]["todays_session"]["mode"] == "hold"


def test_high_fatigue_or_pain_makes_today_lighter():
    for answers in ({"fatigue": "a_lot"}, {"pain": 5}, {"session_preference": "lighter"}):
        plan = build_adaptive_care_plan(profile(), [assessment()], [check_in(**answers)], [], now=NOW)
        assert plan["exercise_plan"]["todays_session"]["mode"] == "lighter", answers


def test_spasticity_report_adds_relaxation_guidance():
    plan = build_adaptive_care_plan(
        profile(), [assessment()], [check_in(spasticity_change="new_or_worse")], [], now=NOW,
    )
    assert plan["exercise_plan"]["spasticity_review_needed"] is True
    assert "relaxation" in plan["exercise_plan"]["spasticity_note"]


# ---------- Week-round loop and exceptions (spec 2 / 5) ----------

def test_seven_session_days_complete_the_round_and_trigger_survey_then_reassessment():
    activities = [activity(days_ago) for days_ago in range(1, 8)]
    plan = build_adaptive_care_plan(profile(), [assessment(created_days_ago=9)], [], activities, now=NOW)
    assert plan["exercise_round"]["session_days_completed"] >= 7
    assert plan["exercise_round"]["complete"] is True
    assert plan["survey"]["due"] is True
    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["trigger"] == "round_complete"
    assert plan["next_step"]["action"] == "recovery_check_in"
    assert "full exercise round" in plan["next_step"]["title"]


def test_overperformance_triggers_early_reassessment():
    plan = build_adaptive_care_plan(
        profile(),
        [assessment()],
        [check_in(exercise_tolerance="too_easy", function_change="much_easier")],
        [activity(1)],
        now=NOW,
    )
    assert plan["exercise_plan"]["early_reassessment_recommended"] is True
    assert plan["assessment"]["due"] is True
    assert plan["assessment"]["trigger"] == "early_reassessment"


def test_missed_days_get_a_warm_reduced_intensity_re_entry():
    plan = build_adaptive_care_plan(profile(), [assessment(created_days_ago=10)], [], [activity(5)], now=NOW)
    assert plan["next_step"]["action"] == "gentle_re_entry"
    assert "Welcome back" in plan["next_step"]["title"]
    lowered = plan["next_step"]["message"].lower()
    assert "fail" not in lowered.replace("never a failure", "")
    assert plan["exercise_plan"]["todays_session"]["mode"] == "lighter"


def test_survey_rescreens_spasticity_and_functional_domains():
    plan = build_adaptive_care_plan(profile(), [assessment(created_days_ago=40)], [], [], now=NOW)
    assert plan["survey"]["due"] is True
    ids = {question["id"] for question in plan["survey"]["questions"]}
    assert "spasticity_change" in ids
    assert ids & {"arm_use", "hand_use", "walking_confidence"}


# ---------- Partial initial assessment (spec 2.2 + user flow) ----------

def partial_initial_assessment(created_days_ago=1):
    base = assessment(created_days_ago=created_days_ago)
    base["task_results"] = [
        {"task_id": "T1", "completed_steps": 3, "total_steps": 3, "metrics": {}},
        {"task_id": "H1", "completed_steps": 2, "total_steps": 2, "metrics": {}},
        {"task_id": "L6", "completed_steps": 0, "total_steps": 1, "metrics": {"walking_skipped": True}},
    ]
    return base


def test_partial_initial_assessment_prompts_for_the_missing_walking_video():
    plan = build_adaptive_care_plan(profile(), [partial_initial_assessment()], [], [], now=NOW)
    step = plan["next_step"]
    assert step["action"] == "complete_missing_assessment"
    assert "walking video" in step["title"]
    assert step["secondary_action"]["action"] == "defer_missing_assessment"
    assert step["secondary_action"]["defer_domains"] == ["lower_limb"]
    assert plan["assessment"]["missing_domains"] == ["lower_limb"]
    assert plan["assessment"]["missing_task_ids"] == ["L6"]
    # The plan for the assessed domains stays active meanwhile.
    assert plan["exercise_plan"]["approved_exercise_ids"]


def test_deferring_the_walking_video_continues_with_the_current_plan():
    deferred_profile = profile()
    deferred_profile["_assessment_deferrals"] = {"lower_limb": {"deferred_at": NOW.isoformat()}}
    plan = build_adaptive_care_plan(deferred_profile, [partial_initial_assessment()], [], [], now=NOW)
    assert plan["next_step"]["action"] != "complete_missing_assessment"


def test_wheelchair_users_are_not_asked_for_the_walking_video():
    plan = build_adaptive_care_plan(
        profile(mobility_level="wheelchair"), [partial_initial_assessment()], [], [], now=NOW,
    )
    assert plan["next_step"]["action"] != "complete_missing_assessment"


def test_assessment_deferral_endpoint_requires_sign_in():
    with TestClient(server.app) as client:
        response = client.post("/api/alira/assessment-deferral", json={"domain": "lower_limb"})
        assert response.status_code == 401


# ---------- Encouragement (spec 10) ----------

def test_points_reward_effort_and_rounds():
    activities = [activity(days_ago) for days_ago in range(1, 8)]
    rewards = compute_rewards(activities, [], {}, now=NOW)
    assert rewards["breakdown"]["session_days"] == 7
    assert rewards["breakdown"]["rounds_completed"] == 1
    assert rewards["points"] == 7 * 5 + 7 * 20 + 50
    assert rewards["effort_based"] is True
    assert rewards["reduced_intensity_counts"] is True


def test_streak_freeze_for_chosen_rest_day():
    activities = [activity(1), activity(3)]  # gap on day 2
    rest_day = check_in(days_ago=2, session_preference="rest_recovery")
    rewards = compute_rewards(activities, [rest_day], {}, now=NOW)
    assert rewards["streak"]["current_days"] == 2
    assert rewards["streak"]["frozen_days_used"] == 1
    without_freeze = compute_rewards(activities, [], {}, now=NOW)
    assert without_freeze["streak"]["current_days"] == 1


def test_medal_ladder():
    rewards = compute_rewards([], [], {}, now=NOW)
    names = [medal["name"] for medal in rewards["medals"]]
    assert names == [
        "Persistence Pro",
        "Persistence Champion",
        "Persistence Master",
    ]
    assert all(medal["earned"] is False for medal in rewards["medals"])


def test_rewards_endpoint_requires_sign_in():
    with TestClient(server.app) as client:
        assert client.get("/api/users/rewards").status_code == 401


# ---------- Safe sharing (spec 10.2) ----------

def test_story_posting_requires_sign_in_and_preview_confirmation(monkeypatch):
    async def signed_in(_headers):
        return {"id": "u_spec", "consent": {"health_data_consent": True}}

    with TestClient(server.app) as client:
        anonymous = client.post(
            "/api/community/stories",
            json={"author": "A", "title": "T", "body": "B", "confirmed_preview": True},
        )
        assert anonymous.status_code == 401

    monkeypatch.setattr(server, "_user_from_header", signed_in)
    with TestClient(server.app) as client:
        unconfirmed = client.post(
            "/api/community/stories",
            json={"author": "A", "title": "T", "body": "B"},
        )
        assert unconfirmed.status_code == 422


# ---------- Goal-linked exercises (spec 7.2 / 8) ----------

def test_exercises_carry_the_patient_goal_they_serve():
    issue = server.FunctionalIssue(
        code="REACH_INCOMPLETE", label="Incomplete reach", description="d",
        source="model", severity="mild", related_task="T1",
    )
    plan = server.build_rehab_plan([issue], {"patient_priorities": ["make tea"]})
    assert plan, "expected at least one exercise"
    assert plan[0].linked_goal == "make tea"


# ---------- Activity-driven progress (spec 6) ----------

def test_daily_activity_metrics_use_honest_status_labels():
    rows = [
        {"reach_completion": 0.5, "hand_opening": 0.4, "pinch_grip": None, "walking_skipped": True},
        {"reach_completion": 0.9, "hand_opening": 0.8, "pinch_grip": 0.7, "walking_skipped": True},
    ]
    metrics = build_daily_activity_metrics(rows, profile(mobility_level="person_assist"))
    by_name = {item["activity"]: item for item in metrics["activities"]}
    assert by_name["Eating and drinking"]["status"] == "complete"
    assert by_name["Eating and drinking"]["change_from_baseline"] == "Better than your baseline"
    walking = by_name["Moving around"]
    assert walking["status"] == "estimated"  # reported only - walking was skipped
    assert walking["reported_assistance_level"] == "moderate_assistance"
    assert metrics["principles"]["no_score_when_not_assessed"] is True


def test_never_assessed_activity_is_not_assessed_not_a_low_score():
    metrics = build_daily_activity_metrics([], {})
    for item in metrics["activities"]:
        assert item["status"] == "not_assessed"
        assert item["change_from_baseline"] is None


# ---------- Frontend wiring (static) ----------

def test_safety_strip_and_rewards_and_preview_are_wired():
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    assessment_screen = (ROOT / "frontend" / "app" / "assessment.tsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    community = (ROOT / "frontend" / "app" / "(tabs)" / "community.tsx").read_text(encoding="utf-8")
    summary = (ROOT / "frontend" / "app" / "function-summary.tsx").read_text(encoding="utf-8")
    rehab = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "<SafetyStopStrip />" in exercise
    assert "<SafetyStopStrip />" in assessment_screen
    assert "<RewardsCard />" in home
    assert 'testID="post-preview"' in community
    assert "confirmed_preview: true" in community
    assert "This one is for:" in rehab
    # Raw joint angles are no longer rendered to patients (spec 6.1).
    assert "shoulder_elevation_deg)}°" not in summary
    assert "trunk_lean_deg)}°" not in summary
