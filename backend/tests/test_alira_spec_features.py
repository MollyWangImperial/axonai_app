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


def activity(days_ago, exercise_id="EX1", completed_reps=5):
    return {
        "exercise_id": exercise_id,
        "completed_reps": completed_reps,
        "completed_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


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
    assert rewards["breakdown"]["repetitions_completed"] == 35
    assert rewards["breakdown"]["points_per_repetition"] == 1
    assert rewards["breakdown"]["session_days"] == 7
    assert rewards["breakdown"]["rounds_completed"] == 1
    assert rewards["points"] == 7 * 5 + 7 * 20 + 50
    assert rewards["effort_based"] is True
    assert rewards["reduced_intensity_counts"] is True


def test_each_completed_repetition_earns_one_point():
    activities = [activity(1, completed_reps=3), activity(2, completed_reps=8)]
    rewards = compute_rewards(activities, [], {}, now=NOW)
    assert rewards["breakdown"]["exercises_completed"] == 2
    assert rewards["breakdown"]["repetitions_completed"] == 11
    assert rewards["points"] == 11 + 2 * 20


def test_caregiver_routine_keeps_its_flat_five_point_reward():
    rewards = compute_rewards([activity(1, exercise_id="CG_UPPER_LIMB", completed_reps=1)], [], {}, now=NOW)
    assert rewards["breakdown"]["caregiver_routines_completed"] == 1
    assert rewards["breakdown"]["points_per_caregiver_routine"] == 5
    assert rewards["points"] == 5 + 20


def test_only_correct_repetitions_earn_points():
    activities = [
        {"exercise_id": "ex_reach", "completed_reps": 5, "quality_reps": 2, "completed_at": (NOW - timedelta(days=1)).isoformat()},
        # Legacy client without a quality count keeps the old behaviour.
        {"exercise_id": "ex_reach", "completed_reps": 3, "completed_at": (NOW - timedelta(days=2)).isoformat()},
    ]
    rewards = compute_rewards(activities, {}, now=NOW)
    # Reporting all 5 reps as correct would earn exactly 3 more repetition points.
    all_correct = [dict(activities[0], quality_reps=5), activities[1]]
    assert compute_rewards(all_correct, {}, now=NOW)["points"] - rewards["points"] == 3
    # A compensated session (no correct reps) earns no repetition points at all.
    none_correct = [dict(activities[0], quality_reps=0), activities[1]]
    assert rewards["points"] - compute_rewards(none_correct, {}, now=NOW)["points"] == 2


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
        assert item["qualitative_score"] is None


def test_survey_only_metrics_carry_a_qualitative_weak_medium_normal_score():
    # With no completed camera tasks there is nothing quantitative to score:
    # each activity gets a plain weak / medium / normal band from the survey.
    metrics = build_daily_activity_metrics([], profile(
        affected_arm_movement="no_movement",
        affected_hand_movement="some_finger_movement",
        mobility_level="independent",
    ))
    by_name = {item["activity"]: item for item in metrics["activities"]}
    assert by_name["Eating and drinking"]["qualitative_score"] == "weak"
    assert by_name["Eating and drinking"]["qualitative_score_label"] == "Weak"
    assert by_name["Grooming and self-care"]["qualitative_score"] == "medium"
    assert by_name["Moving around"]["qualitative_score"] == "normal"
    assert metrics["qualitative_scores"] == ["weak", "medium", "normal"]
    # A quantitative 0-100 score is always present too, calculated from the
    # survey when no camera task has been completed.
    assert by_name["Eating and drinking"]["score"] == 25
    assert by_name["Eating and drinking"]["score_source"] == "survey"
    assert by_name["Grooming and self-care"]["score"] == 65
    assert by_name["Moving around"]["score"] == 95
    assert all(item["score_scale"] == "0_to_100" for item in metrics["activities"])


def test_survey_interim_rehab_plan_always_gives_a_starting_plan():
    plan = server.survey_interim_rehab_plan({
        "sitting_ability": "independent",
        "affected_arm_movement": "help_only",
        "affected_hand_movement": "very_little_movement",
        "mobility_level": "cane",
    })

    assert plan, "a survey-derived starting plan is expected"
    ids = {exercise.id for exercise in plan}
    assert len(ids) >= 2
    assert all("Starting plan from your survey answers" in (exercise.selection_reason or "") for exercise in plan)


def test_survey_plan_surfaces_instead_of_the_waiting_for_review_dead_end():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    server_source = (root / "backend" / "server.py").read_text(encoding="utf-8")
    rehab_plan_screen = (root / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    movement_map = (root / "frontend" / "app" / "movement-map.tsx").read_text(encoding="utf-8")
    results = (root / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")
    home = (root / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # While movement analysis processes, the survey-derived plan is viewable;
    # camera/model results do not select or replace exercise IDs.
    assert '"rehab_access": "interim"' in server_source
    assert '"rehab_plan_source": "survey_reported_problems"' in server_source
    assert 'in ("allowed", "interim")' in server_source
    assert 'testID="plan-survey-source-banner"' in rehab_plan_screen
    assert 'reviewGate?.rehab_access === "interim"' in movement_map
    assert '"Your survey-based plan is ready"' in movement_map
    assert "Camera and model findings do not replace them" in rehab_plan_screen
    assert 'reviewGate?.rehab_access === "interim"' in results

    # The Home goal is derived from the survey's functional problems and stays
    # short: a keyword list behind a compact lead-in, never a long sentence.
    assert "deriveFunctionalGoal" in home
    assert "Eating & dressing" in home
    assert "Grooming & hand tasks" in home
    assert "Safer mobility" in home
    assert "Your goal: " in home
    assert "Working towards your goal" not in home


def test_movement_map_is_anatomy_first_with_shiny_navigable_findings():
    movement_map = (ROOT / "frontend" / "app" / "movement-map.tsx").read_text(encoding="utf-8")

    assert 'testID="movement-map-panel"' in movement_map
    assert "areas highlighted. Select one to see its details." in movement_map
    assert "ShinyMapMarker" in movement_map
    assert 'testID={`${testID}-shine`}' in movement_map
    assert "markerGlint" in movement_map
    assert 'testID="movement-map-view-details"' in movement_map
    assert 'testID="movement-map-expanded-details"' in movement_map
    assert 'testID="movement-map-previous-area"' in movement_map
    assert 'testID="movement-map-next-area"' in movement_map
    assert "Select another area" not in movement_map
    assert "styles.legend" not in movement_map


def test_rehab_plan_uses_compact_daily_session_structure():
    rehab = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert 'testID="plan-progress-summary"' in rehab
    assert 'testID="plan-safety-banner"' in rehab
    assert "Move safely" in rehab
    assert "Why this exercise?" in rehab
    assert "exercise-rationale-" in rehab
    assert ">Demo</Text>" in rehab
    assert '"Begin exercise"' in rehab
    assert "Complete session" in rehab
    assert "ProgressRing" not in rehab
    assert "styles.completionBar" not in rehab
    assert "styles.calloutRow" not in rehab


def test_snapshot_and_report_screens_show_qualitative_scores_and_survey_highlights():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    panel = (root / "frontend" / "src" / "components" / "DailyActivitiesPanel.tsx").read_text(encoding="utf-8")
    scores = (root / "frontend" / "src" / "components" / "MovementScoresPanel.tsx").read_text(encoding="utf-8")
    report = (root / "frontend" / "app" / "survey-report.tsx").read_text(encoding="utf-8")
    results = (root / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")

    # "Daily life at a glance": one plain-language row per activity, with the
    # source, summary, status, and honest not-assessed handling kept visible.
    assert "Daily life at a glance" in panel
    assert "How much help you may need with everyday activities." in panel
    for label in ("Full help", "A lot of help", "A little help", "Independent"):
        assert f'label: "{label}"' in panel
    assert 'testID="daily-activities-summary"' in panel
    assert 'testID="daily-activities-list"' in panel
    assert "daily-activity-card-" in panel
    assert "daily-activity-status-" in panel
    assert 'testID="daily-activities-source-badge"' in panel
    assert 'testID="daily-activities-methodology"' in panel
    assert 'testID="daily-activities-methodology-modal"' in panel
    assert "Not assessed activities appear separately." in panel
    assert "QUALITATIVE_TO_BAND" in panel  # weak/medium/normal folds into the bands
    assert "daily-activity-meter-" not in panel
    assert '"/ 100"' not in panel
    assert "What this means for daily life" not in panel

    # The assessment report's first page reuses the same board.
    assert "DailyActivitiesBoard" in report
    assert "DailyActivitiesBoard activities={report.daily_activities.activities}" in report

    # The snapshot uses the requested three-part hierarchy. Guided-task scores
    # lead, daily-life meaning follows, and the interactive anatomy map is last.
    assert 'authedFetch("/api/assessment/survey-report")' in results
    assert "Your movement scores" in scores
    assert "Guided-task scores - not a clinical measure." in scores
    assert 'testID="movement-scores-panel"' in scores
    assert "movement-score-" in scores
    assert 'title="What this means for daily life"' in results
    assert 'testID="results-movement-map"' in results
    assert "Your movement map" in results
    assert "Choose a number to learn about that area." in results
    assert 'testID="results-map-areas"' in results
    assert ">Areas</Text>" in results
    assert "results-map-marker-" in results
    assert 'testID="results-map-detail"' in results
    assert "MAP_DOMAIN_ICONS" in results
    assert "mapAreaTitleWide" in results
    assert results.count('testID="results-movement-map"') == 1  # shared by demo and real assessment data
    assert results.index("<MovementScoresPanel") < results.index('title="What this means for daily life"')
    assert results.index('title="What this means for daily life"') < results.index('testID="results-movement-map"')
    assert "goPlan" in results and "goMap" not in results
    assert "Explore your movement map" not in results
    assert 'testID="results-summary"' not in results  # the old anatomy panel is gone


def test_returning_home_after_earning_points_celebrates_the_delta():
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # Every Home focus refreshes the day board and, when points rose while the
    # patient was away (e.g. the assessment was completed), pops the toast for
    # exactly the newly earned points - without double-celebrating check-in.
    assert 'getScreenCache<number>("celebrated-points")' in home
    assert "nextPoints > lastCelebratedPoints" in home
    assert "nextPoints - lastCelebratedPoints" in home
    assert '"Assessment complete - amazing work!"' in home
    assert home.count('setScreenCache<number>("celebrated-points"') >= 3


def test_your_day_reveals_steps_progressively_with_grey_locked_connectors():
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # Before check-in everything downstream is locked and both connector
    # segments are grey; the third step unlocks only once the initial
    # assessment exists.
    assert "const stepTwoRevealed = checkedInToday;" in home
    assert "const stepThreeRevealed = checkedInToday && (assessmentCompletedToday || !isInitialAssessment);" in home
    assert "!checkedInToday && styles.dayConnectorInactive" in home
    assert "!stepThreeRevealed && styles.dayConnectorInactive" in home
    assert "Check in first to see today's next step." in home
    assert "Complete the initial assessment to see what comes next." in home
    assert home.count('label="Locked"') == 2


def test_secondary_goals_options_show_pictures_instead_of_symbols():
    onboarding = (ROOT / "frontend" / "app" / "onboarding.tsx").read_text(encoding="utf-8")

    assert "GOAL_PICTURES" in onboarding
    for value in ("reach_overhead", "self_feed", "dress", "write", "drive", "cook", "play_music", "exercise", "other"):
        assert f"{value}:" in onboarding
    assert "goal-picture-" in onboarding
    assert 'step.key === "secondary_goals"' in onboarding
    assert "styles.goalPicture" in onboarding
    # The goals picker renders picture cards, never the emoji symbol.
    assert "goalCard" in onboarding


def test_trend_charts_get_shiny_points_and_a_value_axis_after_assessment():
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # Once today's assessment is complete, the Reaching / Hand control /
    # Walking points shimmer (a looping animated halo) so progress feels
    # alive, and every chart carries a y-axis plus per-point value labels so
    # patients can read the exact score of each point.
    assert "const AnimatedCircle = Animated.createAnimatedComponent(Circle);" in home
    assert "shiny?: boolean" in home
    assert "<MiniTrendChart values={trend.values} shiny={assessmentCompletedToday} />" in home
    assert "Animated.loop(" in home
    assert "pulse.interpolate" in home
    # Y-axis line, tick labels, and exact value labels on each point.
    assert 'testID="home-trend-axis-label"' in home
    assert 'testID="home-trend-point-value"' in home
    assert "axisTicks" in home
    assert "Math.round(point.value)" in home
    # The shimmer only runs when there is something to celebrate.
    assert "if (!shiny || values.length === 0) return;" in home


def test_dark_mode_is_neutral_grey_with_a_darkness_slider():
    display = (ROOT / "frontend" / "src" / "displayPreferences.tsx").read_text(encoding="utf-8")
    prefs = (ROOT / "frontend" / "src" / "userPreferences.ts").read_text(encoding="utf-8")
    auth = (ROOT / "frontend" / "src" / "auth.ts").read_text(encoding="utf-8")
    settings = (ROOT / "frontend" / "app" / "(tabs)" / "settings.tsx").read_text(encoding="utf-8")

    # Dark mode uses a neutral dark grey ground (not the old dark green) so
    # photos and the green branding stand out; green survives only as accent.
    assert "darkPaletteFor" in display
    assert '"#0F1D18"' not in display  # old green page colour removed
    assert '"#182A23"' not in display  # old green surface removed
    assert "DARK_SOFT_ANCHOR" in display and "DARK_DEEP_ANCHOR" in display
    assert 'page: "#454A4F"' in display  # 0-5% is visibly grey, not charcoal-black
    assert 'surface: "#4D5257"' in display
    assert 'muted: "#C2C7C4"' in display  # readable secondary text on the softer grey surface
    assert '"#96D7A8"' in display  # bright enough for text on the soft-grey surface
    assert "preferences.darkness" in display

    # Light mode is the account default. Dark mode persists only after that
    # signed-in patient explicitly enables it, so accounts sharing one device
    # cannot inherit each other's display choice.
    assert "darkMode: false" in prefs
    assert "darkModeKey(userId)" in prefs
    assert "const userId = await getUserId();" in prefs
    assert "subscribeAuthState(reloadPreferences)" in display
    assert "notifyAuthStateChanged();" in auth

    # Patients pick their own darkness with a slider (0-100, persisted).
    assert "DARKNESS_KEY" in prefs
    assert "darkness: 55" in prefs  # default depth
    assert 'testID="settings-darkness-slider"' in settings
    assert "Dark mode depth" in settings
    # The slider only appears while dark mode is on.
    assert "preferences.darkMode ? (" in settings


def test_home_uses_display_palette_for_green_and_supporting_text():
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # Home must not reuse light-theme dark greens on dark backgrounds. The
    # shared display palette keeps goal, step, chart and link text readable at
    # every dark-mode depth while secondary copy uses the accessible muted tone.
    assert "function DayStep" in home and "const { palette } = useDisplayPreferences();" in home
    assert "styles.goalStrong, { color: palette.brand }" in home
    assert "const titleColor = preferences.darkMode ? palette.brand : palette.text" in home
    assert "styles.dayStepTitle, { color: titleColor }" in home
    assert "styles.dayStepDescription, { color: palette.muted }" in home
    assert "styles.stepProgressLabel, { color: palette.brand }" in home
    assert "styles.progressLinkText, { color: palette.brand }" in home
    assert 'fill={palette.brand}' in home
    assert 'fill="#155D3C"' not in home


def test_object_exercises_draw_virtual_objects_on_screen():
    """Exercises that used real props now draw the object on the canvas instead."""
    cfg = server.REHAB_RUNNER_CONFIG
    # The cup attaches once the fingers close around it (step 2) and is set down
    # once the hand opens at the far side (step 4).
    assert cfg["ex_grasp"]["virtual_object"] == {"type": "cup", "mode": "carry", "grab_step": 2, "place_step": 4}
    assert cfg["ex_h2m"]["virtual_object"] == {"type": "cup", "mode": "held"}
    assert cfg["ex_handopen"]["virtual_object"] == {"type": "ball", "mode": "hand_anchor"}
    assert cfg["ex_pinch"]["virtual_object"]["mode"] == "pick_place"
    assert set(cfg["ex_pinch"]["virtual_object"]["source"]) == {"x", "y"}
    assert set(cfg["ex_pinch"]["virtual_object"]["container"]) == {"x", "y"}
    assert cfg["ex_bilateral"]["virtual_object"] == {"type": "bar", "mode": "between_hands"}

    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    # The runner renders the objects and moves the carried cup with the wrist.
    for marker in (
        "function drawVirtualObject(",
        "function drawVirtualCup(",
        "function drawVirtualBall(",
        "function drawVirtualPeg(",
        "function drawVirtualContainer(",
        "function drawVirtualBar(",
        "vobjOnStepCompleted(currentSubStep)",
        "drawVirtualObject(lm, handLm);",
        'vobjState = "carried"',
    ):
        assert marker in source, marker
    # Patients are no longer told to fetch real objects for these exercises.
    assert "Gather a few small objects" not in source
    assert "Place it on a stable table" not in source
    assert "Use a light cup." not in source
    assert "Place the light object within a comfortable reach" not in source
    # Each spoken setup makes clear the object is on the screen.
    for ex in ("ex_grasp", "ex_h2m", "ex_handopen", "ex_pinch", "ex_bilateral"):
        voice = cfg[ex]["setup_voice"].lower()
        assert "screen" in voice, ex


def test_completion_asks_about_carer_help_and_halves_assisted_scores():
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")

    # Both runners can now see more than two hands (patient + helper).
    assert "numHands: 4" in source and "numHands:4" in source
    assert "numHands: 2" not in source and "numHands:1" not in source

    # Finishing an exercise pops the carer/family question before closing.
    assert 'data-testid="exercise-assist-question"' in source
    assert "Did a carer or family member help you move during this exercise?" in source
    assert "async function askAssistance()" in source
    assert "const assisted = await askAssistance();" in source
    assert "reps: CFG.reps, assisted, quality_reps: qualityReps});" in source

    # The app sends RAW scores plus the flag; the server halves exactly once.
    assert 'msg.assisted === true' in exercise
    assert "assisted," in exercise
    assert server.ASSISTED_SCORE_FACTOR == 0.5
    assert "unassisted_average_score" in source

    # Every exercise maps to the functional domain its score affects.
    assert server.EXERCISE_FUNCTIONAL_DOMAINS["ex_reach"] == "upper_limb"
    assert server.EXERCISE_FUNCTIONAL_DOMAINS["ex_handopen"] == "hand"
    assert server.EXERCISE_FUNCTIONAL_DOMAINS["ex_sit_to_stand"] == "lower_limb"
    assert set(server.EXERCISE_FUNCTIONAL_DOMAINS) == set(server.REHAB_RUNNER_CONFIG)
    assert '"domain_scores": _domain_exercise_scores(items)' in source


def test_forward_reach_grading_is_phase_gated_and_catches_forward_lean_and_shrugs():
    """A bent elbow, a forward lean, or a two-shoulder shrug can no longer score 100."""
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    cfg = server.REHAB_RUNNER_CONFIG

    # Return-to-rest steps are tagged so they never earn ROM credit or dilute
    # compensation confirmation; the reach itself is the movement phase.
    assert [step["phase"] for step in cfg["ex_reach"]["cycle"]] == ["movement", "return"]
    assert [step["phase"] for step in cfg["ex_grasp"]["cycle"]] == ["movement"] * 5 + ["return"]
    assert [step["phase"] for step in cfg["ex_h2m"]["cycle"]] == ["movement", "return"]
    assert [step["phase"] for step in cfg["ex_bilateral"]["cycle"]] == ["movement", "movement"]
    assert "function activeMovementPhase()" in source
    assert "if(!activeMovementPhase()) return;" in source
    assert "activeFrames < SCORING_MIN_FRAMES" in source

    # Elbow extension is judged at peak reach with the arm actually raised,
    # not as the maximum angle anywhere in the repetition.
    assert "peakReachElbow=raw.elbow_extension;" in source
    assert 'if(step.metric === "elbow_extension")' in source
    assert ">= 15;" in source  # arm-raised guard against a resting straight arm

    # Forward lean toward a front-facing camera: perspective growth of the
    # shoulder and ear widths against the calibrated baseline (z as fallback).
    assert "function forwardLeanDegrees(raw)" in source
    assert "Math.asin(clamp(2*(1-w0/w),0,1))" in source
    assert "Math.asin(clamp(1.5*(1-e0/e),0,1))" in source
    assert "raw.ear_width=" in source and "raw.neck_gap=" in source
    # Shoulder hiking as clavicle elevation (lever = half the shoulder width, so
    # a ~3 cm one-sided rise reads 8 degrees), plus a two-shoulder shrug that
    # must both lift the shoulders in the frame and shorten both neck gaps.
    assert "function shoulderHikeDegrees(raw)" in source
    assert "const halfWidth=Math.max(.03,(Number(raw.shoulder_width)||.18)/2);" in source
    assert "rad2deg(Math.atan2(Math.max(0,raw.shoulder_line_delta-line0),halfWidth))" in source
    assert "const bilateral=rad2deg(Math.atan2(Math.min(frameRise,gapShrink),halfWidth));" in source
    assert "raw.shoulder_line_delta=lm[OTHER.shoulder].y-lm[ACTIVE.shoulder].y;" in source
    assert "raw.other_neck_gap=" in source
    # Stale calibrations from older builds are never reused.
    assert "const REHAB_CALIBRATION_VERSION = 3;" in source
    assert '"other_neck_gap","shoulder_line_delta","shoulders_y"' in source
    assert "REHAB_BASELINE_REQUIRED_KEYS.some(" in source

    # A confirmed compensation scores a fixed 70 and earns no point; only a
    # correct repetition (no compensation, score >= 90) earns its point. The
    # feedback names the problem with its degrees before giving the correction.
    assert server.EXERCISE_SCORING_METHOD["compensation_score"] == 70
    assert server.EXERCISE_SCORING_METHOD["point_threshold"] == 90
    assert "if(confirmed.length) score=Number(SCORING_METHOD.compensation_score)||70;" in source
    assert "function repEarnsPoint(score)" in source
    assert "if(pointEarned) qualityReps += 1;" in source
    assert "<strong>No point this time</strong>" in source
    assert '"That repetition did not earn a point yet."' in source
    assert "quality_reps: qualityReps" in source
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    assert "quality_reps: typeof msg.quality_reps" in exercise
    assert "your trunk leaned forward (${degrees} degrees)" in source
    assert "your shoulder lifted toward your ear (${degrees} degrees)" in source
    assert "your elbow stayed bent at ${achieved} of ${target} degrees" in source
    assert "Next time, keep your trunk and shoulder still and simply extend your elbow to reach the target." in source
    # Live on-screen degrees: elbow angle vs target, shoulder lift, trunk lean.
    assert "function drawLiveDegrees(lm)" in source
    assert 'elbow_extension:{joint:"elbow",text:"Elbow"}' in source
    assert "`Shoulder lift ${Math.round(hike)}°`" in source
    assert "`Trunk lean ${Math.round(lean)}°`" in source


def test_trunk_restrained_reaching_is_graded_like_forward_reach_and_recalibrates_on_posture_change():
    """Leaning off the chair or hiking the shoulder during trunk-restrained reaching is
    flagged, corrected, scored 70 and earns no point; a bent elbow never reaches 90."""
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    trunk = server.REHAB_RUNNER_CONFIG["ex_trunk"]
    standard = server.EXERCISE_MOVEMENT_STANDARDS["ex_trunk"]

    # Same shared engine: a reach phase that is scored and a return phase that is not,
    # with the workbook's stricter 8-degree trunk-lean threshold for this exercise.
    assert [step["phase"] for step in trunk["cycle"]] == ["movement", "return"]
    assert {rule["id"]: rule["threshold_deg"] for rule in standard["compensations"]} == {"trunk_lean": 8, "shoulder_hike": 8}
    assert [step["metric"] for step in standard["rom_steps"]] == ["shoulder_flexion", "elbow_extension"]

    # The alarm names what went wrong in this exercise's own terms, then the correction.
    assert trunk["compensation_problems"]["trunk_lean"] == "your back came away from the chair and your trunk leaned forward"
    assert trunk["compensation_problems"]["shoulder_hike"] == "your shoulder lifted toward your ear"
    assert "back against the chair" in trunk["correct_form_cue"] and "extend your elbow" in trunk["correct_form_cue"]
    assert "const specific=CFG.compensation_problems && CFG.compensation_problems[rule.id];" in source
    assert "const correction=CFG.correct_form_cue" in source
    configured = server._configure_rehab_runner("ex_trunk", "medium", "standard")
    assert configured["compensation_problems"] == trunk["compensation_problems"]
    assert configured["correct_form_cue"] == trunk["correct_form_cue"]

    # A repetition with a step short of its target (e.g. the elbow stayed bent) is
    # named in degrees and capped below the point threshold; only a complete,
    # uncompensated repetition earns the point.
    assert server.EXERCISE_SCORING_METHOD["complete_rom_ratio"] == 0.9
    assert "function incompleteRomSteps()" in source
    assert "else if(incompleteRomSteps().length) score=Math.min(score,POINT_THRESHOLD-1);" in source
    assert "if(incompleteRomSteps().length) return false;" in source
    assert "problems.push(...incompleteRomSteps().map(romProblemText));" in source
    assert "return `I noticed ${joinProblems(incomplete.map(romProblemText))}. ${correction}`;" in source
    assert "your arm reached ${achieved} of ${target} degrees" in source

    # A session calibration captured for another exercise (forward reach, back away
    # from the chair) is reused only when the patient is still sitting the same way;
    # otherwise the runner says so and learns the new starting position.
    assert "function ensureLoop()" in source
    assert "async function postureMatchesSessionBaseline()" in source
    assert 'for(const key of ["shoulder_width","torso_length","active_shoulder_y"])' in source
    assert "const postureMatches=await postureMatchesSessionBaseline();" in source
    assert 'reason:"posture_changed"' in source
    assert 'const POSTURE_CHANGED_VOICE="You are sitting a little differently for this exercise, so I will learn your starting position again. Please hold still for a moment.";' in source
    assert "await playVoice(POSTURE_CHANGED_VOICE);" in source
    # The setup voice (how to sit for this exercise) plays before the check, once.
    assert source.index("await playVoice(CFG.setup_voice);\n    setupVoicePlayed=true;") < source.index("const postureMatches=await postureMatchesSessionBaseline();")
    assert "if(!setupVoicePlayed){" in source
    runner_script = source.split("REHAB_RUNNER_HTML_TEMPLATE = r", 1)[1]
    assert runner_script.count("requestAnimationFrame(loop);") == 3  # ensureLoop + the loop's own two re-schedules
    assert "  ensureLoop();\n  await playVoice(STANDARD.calibration_instruction);" in source

    # The elbow is judged at the top of the reach (frames within 10% of the
    # repetition's peak shoulder flexion), never on the way up where a hanging
    # arm is naturally straight; the on-screen target verifies the reach itself,
    # so only the joints it cannot verify can make a repetition incomplete.
    assert "function reachKeyMetric()" in source
    assert "function elbowAtPeakReach()" in source
    assert "const NEAR_PEAK_REACH_RATIO=0.9, MAX_REACH_FRAMES=8;" in source
    assert "reachFrames.push({key:reachValue,elbow:raw.elbow_extension});" in source
    assert "return repRomDetails().filter(item=>item.measured && FORM_CRITICAL_METRICS.has(item.metric) && item.target_deg>0 && item.achieved_deg < item.target_deg*ROM_COMPLETE_RATIO);" in source
    # Within 5% of today's target is full attainment for a step (camera angles
    # read low for a reach toward the lens), so a correct repetition clears 90.
    assert server.EXERCISE_SCORING_METHOD["full_credit_ratio"] == 0.95
    assert "clamp(achieved/(target*ROM_FULL_CREDIT_RATIO),0,1)" in source

    # Tapping Continue while the feedback is still being read must not freeze
    # the next repetition: an interrupted instruction settles immediately and
    # never clears the listeners of the instruction that replaced it, listening
    # only starts while the feedback panel is still up, and one bad frame can
    # never stop the camera loop.
    assert "let stopActiveVoice = null;" in source
    assert "if(stopActiveVoice) stopActiveVoice();" in source
    assert 'audioEl.removeEventListener("ended", onEnded);' in source
    assert "if(sequence !== voiceSequence) return;   // superseded while the audio was being fetched" in source
    assert 'if(fbEl.classList.contains("show")) startListening();' in source
    assert 'postRN({type:"exercise_frame_error", message:String(e && e.message || e)});' in source


def test_cylindrical_grasp_reach_open_close_carry_release_flow_and_compensations():
    """Reach -> open hand -> close around the cup -> carry -> open to set down -> return,
    confirmed from the fingers, graded like the forward reach, with the circle the
    patient sees being the circle that is hit-tested."""
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    grasp = server.REHAB_RUNNER_CONFIG["ex_grasp"]
    standard = server.EXERCISE_MOVEMENT_STANDARDS["ex_grasp"]
    profile = server.EXERCISE_COACHING_PROFILES["ex_grasp"]

    captions = [step["caption"] for step in grasp["cycle"]]
    assert captions == [
        "Reach to the cup",
        "Open your hand wide around the cup",
        "Close your fingers around the cup",
        "Carry the cup across",
        "Open your hand to set the cup down",
        "Return your empty hand to your lap",
    ]
    landmarks = [(step["target"] or {}).get("landmark") for step in grasp["cycle"]]
    assert landmarks == [None, "HAND_OPEN", "HAND_CLOSED", None, "HAND_OPEN", None]
    # The hand steps sit exactly where the cup is drawn, and never trap the patient.
    assert grasp["cycle"][1]["target"]["x"] == grasp["cycle"][0]["target"]["x"] == grasp["cycle"][2]["target"]["x"]
    assert grasp["cycle"][4]["target"]["x"] == grasp["cycle"][3]["target"]["x"]
    assert all(step.get("max_wait_ms") == 6000 for step in grasp["cycle"] if (step["target"] or {}).get("landmark"))
    assert grasp["hand_tracking"] is True and grasp["mirror_for_left"] is True
    for word in ("open your hand wide", "close your fingers around the cup", "carry it across", "set it down"):
        assert word in grasp["setup_voice"].lower(), word

    # Scored metrics: reach (shoulder flexion), transport (shoulder abduction), hand opening.
    assert [(step["metric"], step["weight"]) for step in standard["rom_steps"]] == [
        ("shoulder_flexion", 0.45), ("shoulder_abduction", 0.35), ("finger_extension", 0.20)]
    assert standard["rom_steps"][2]["targets"] == {"easy": 115, "medium": 130, "difficult": 145}
    # Compensatory patterns: forward lean to the cup, side lean to carry it,
    # shoulder hiking, and a dropped wrist while gripping.
    assert [rule["id"] for rule in standard["compensations"]] == ["trunk_lean", "trunk_side_lean", "shoulder_hike", "wrist_flexion"]
    assert {rule["id"]: rule["metric"] for rule in standard["compensations"]} == {
        "trunk_lean": "trunk_lean_delta", "trunk_side_lean": "trunk_side_lean_delta",
        "shoulder_hike": "shoulder_hike_delta", "wrist_flexion": "wrist_flexion_delta"}
    assert set(profile["compensation_labels"]) == {"trunk_lean", "trunk_side_lean", "shoulder_hike", "wrist_flexion"}
    assert "hand_opening" in profile["rom_cues"]
    assert grasp["compensation_problems"] == {
        "trunk_lean": "your chest leaned toward the cup",
        "trunk_side_lean": "your body leaned to the side to carry the cup",
        "shoulder_hike": "your shoulder lifted toward your ear",
        "wrist_flexion": "your wrist bent downward instead of staying in line with your forearm while you gripped the cup",
    }
    assert "straight wrist" in grasp["correct_form_cue"]
    assert next(rule for rule in standard["compensations"] if rule["id"] == "wrist_flexion")["threshold_deg"] == 25

    # Runner: the hit test uses the same image coordinates the circle is drawn
    # in (the old mirrored comparison put the live circle on the wrong side for
    # any off-centre target), targets mirror for a left-affected patient, the
    # hand landmarker runs for hand-gated steps, and the affected hand is the
    # one nearest the affected wrist.
    assert "const ok = (p) => p && Math.hypot(p.x-t.x, p.y-t.y) < R;" in source
    assert "Math.hypot((1-p.x)-t.x, p.y-t.y) < R" not in source.split("REHAB_RUNNER_HTML_TEMPLATE = r", 1)[1]
    assert 'if(AFFECTED_SIDE === "left" && CFG.mirror_for_left){' in source
    assert 'const HAND_GATE_LANDMARKS = new Set(["HAND_OPEN","HAND_CLOSED"]);' in source
    assert "if(NEEDS_HAND_TRACKING){" in source
    assert "function selectRehabAffectedHand(result, lm, now)" in source
    assert "handLm=selectRehabAffectedHand(h, lm, now);" in source
    assert "function handOpeningDegrees(handLm)" in source
    # Same hand model settings, gesture scores (smoothed) and thresholds as the
    # initial assessment, a brief detection gap keeps the previous hand, and a
    # 350 ms grace keeps the hold ring from restarting on one jittery frame.
    assert "minHandDetectionConfidence:0.65," in source and "minTrackingConfidence:0.7," in source
    assert "function updateRehabHandScores(h)" in source
    assert "handOpenScore=handOpenScore*0.6+open*0.4;" in source
    assert "fistClosureScore=fistClosureScore*0.6+closure*0.4;" in source
    assert "const HAND_OPEN_SCORE=0.45, HAND_CLOSED_SCORE=0.30;" in source
    assert 'return which === "HAND_OPEN" ? handOpenScore > HAND_OPEN_SCORE || waitedLongEnough' in source
    assert "const HAND_LANDMARK_FRESH_MS=350;" in source
    assert "const TARGET_HOLD_GRACE_MS=350;" in source
    assert "}else if(inTargetSince != null && (now - lastInTargetTs) > TARGET_HOLD_GRACE_MS){" in source
    assert "const HAND_BACKOFF_SCAN_INTERVAL_MS=180, HAND_BACKOFF_FRESH_MS=2600, MIN_SMOOTH_FPS=15;" in source
    # The carried cup rides the palm of the tracked hand with smoothing.
    assert "let vobjAnchor = null;" in source
    assert "vobjAnchor = {x: vobjAnchor.x * 0.55 + target.x * 0.45, y: vobjAnchor.y * 0.55 + target.y * 0.45};" in source
    # Models are created as soon as the runner page opens, not on Start.
    assert "function warmUpModels(){" in source
    assert "warmUpModels().catch(() => {});" in source
    assert 'captionEl.textContent = "Loading the movement model…";' in source
    # Side lean and wrist drop are measured in ways that do not fire just because
    # the arm swings across: lateral trunk angle, and wrist bend against the forearm.
    assert 'if(metric === "trunk_side_lean_delta") return Math.abs(raw.trunk_angle-(base.trunk_angle||0));' in source
    assert "raw.wrist_bend=(fl >= sw*0.45 && hl >= sw*0.12)" in source  # image-plane only, foreshortening-guarded
    assert 'if(STANDARD.tracking_mode !== "hand" && Number.isFinite(raw.wrist_bend)){' in source
    # Live numbers the patient sees: Reach / Arm across / Hand open against target,
    # plus Shoulder lift, Trunk lean, Side lean and Wrist bend as they appear.
    assert 'shoulder_abduction:{joint:"shoulder",text:"Arm across"}' in source
    assert 'finger_extension:{joint:"hand",text:"Hand open"}' in source
    assert "`Side lean ${Math.round(side)}°`" in source
    assert "`Wrist bend ${Math.round(wristDrop)}°`" in source
    assert 'const hint = sub.target.landmark === "HAND_OPEN" ? "Open hand" : "Close hand";' in source
    # Grading: the fingers are form-critical (a weak opening never reaches 90),
    # an unseen hand neither scores nor fails, but earns no point either.
    assert 'const FORM_CRITICAL_METRICS=new Set(["elbow_extension","finger_extension"]);' in source
    assert "function measuredRomDetails()" in source
    assert "if(unmeasuredRomSteps().some(item=>FORM_CRITICAL_METRICS.has(item.metric))) return false;" in source
    assert "Keep your hand in view to earn it." in source
    assert "I could not see your affected hand clearly enough to check your grip." in source
    configured = server._configure_rehab_runner("ex_grasp", "medium", "standard")
    assert configured["hand_tracking"] is True
    assert [step["target"].get("landmark") for step in configured["cycle"]] == landmarks


def test_earning_points_pops_a_fading_congratulations_toast():
    component = (ROOT / "frontend" / "src" / "components" / "PointsCelebration.tsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    caregiver = (ROOT / "frontend" / "app" / "caregiver-plan.tsx").read_text(encoding="utf-8")
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")

    # The toast pops in, holds briefly, and fades out on its own.
    assert 'testID="points-celebration"' in component
    assert "Animated.delay(1400)" in component
    assert "toValue: 0, duration: 450" in component
    assert 'pointerEvents="none"' in component
    # App-level point moments celebrate on Home and in caregiver delivery.
    # Exercise repetitions use the runner's feedback window so the score,
    # correction, and one-point reward remain in one place.
    assert "celebrationEvent(2" in home
    assert "celebrationEvent(5" in caregiver
    assert "celebrationEvent(5" not in exercise
    assert 'msg.type === "rep_complete"' in exercise
    for source in (home, caregiver):
        assert "<PointsCelebration event={celebration} onDone={() => setCelebration(null)} />" in source


def test_safety_strip_and_rewards_and_preview_are_wired():
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    assessment_screen = (ROOT / "frontend" / "app" / "assessment.tsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    community = (ROOT / "frontend" / "app" / "(tabs)" / "community.tsx").read_text(encoding="utf-8")
    summary = (ROOT / "frontend" / "app" / "function-summary.tsx").read_text(encoding="utf-8")
    rehab = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "<SafetyStopStrip />" in exercise
    assert "<SafetyStopStrip />" in assessment_screen
    assert 'authedFetch("/api/users/rewards")' in home
    assert 'testID="home-points-badge"' in home
    assert 'testID="post-preview"' in community
    assert "confirmed_preview: true" in community
    assert "This one is for:" not in rehab  # per-exercise goal chip removed
    # Raw joint angles are no longer rendered to patients (spec 6.1).
    assert "shoulder_elevation_deg)}°" not in summary
    assert "trunk_lean_deg)}°" not in summary


def test_rehab_plan_loading_tracks_real_plan_preparation_stages():
    rehab = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    results = (ROOT / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")
    movement_map = (ROOT / "frontend" / "app" / "movement-map.tsx").read_text(encoding="utf-8")
    journey = (ROOT / "frontend" / "app" / "(tabs)" / "journey.tsx").read_text(encoding="utf-8")
    assessment = (ROOT / "frontend" / "app" / "assessment.tsx").read_text(encoding="utf-8")

    assert 'testID="rehab-plan-preparation"' in rehab
    assert '"Reviewing your assessment"' in rehab
    assert '"Choosing suitable exercises"' in rehab
    assert '"Creating your plan"' in rehab
    assert "This usually takes less than a minute." in rehab
    assert "const assessment = id === DEMO_ASSESSMENT_ID ? demoAssessment : await fetchAssessment(id);" in rehab
    assert "setPreparationStage(1);" in rehab
    assert 'authedFetch("/api/alira/care-plan")' in rehab
    assert "setPreparationStage(2);" in rehab
    assert "await loadProgress(sessionPlan);" in rehab
    assert 'entry === "assessment_complete"' in rehab
    assert "enteredFromFreshAssessment && firstAccess" in rehab
    assert "loading && showPreparation" in rehab
    assert 'entry: "assessment_complete"' in assessment
    assert 'entry === "assessment_complete"' in results
    assert 'entry: "assessment_complete"' in results
    assert 'entry: "assessment_complete"' not in movement_map
    journey_start = journey.split('testID="journey-start-rehab"', 1)[1].split("</Pressable>", 1)[0]
    assert 'entry: "assessment_complete"' not in journey_start


def test_journey_demo_opens_the_completed_movement_snapshot():
    journey = (ROOT / "frontend" / "app" / "(tabs)" / "journey.tsx").read_text(encoding="utf-8")
    results = (ROOT / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")

    demo_row = journey.split('testID="assessment-history-demo"', 1)[1].split("</Pressable>", 1)[0]
    assert 'pathname: "/results"' in demo_row
    assert 'pathname: "/function-summary"' not in demo_row
    assert "Demo movement snapshot" in demo_row
    assert "Movement scores, daily-life activities and an interactive anatomy map" in demo_row
    assert "<MovementScoresPanel" in results
    assert 'title="What this means for daily life"' in results
    assert 'testID="results-movement-map"' in results
