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


def test_interim_plan_surfaces_instead_of_the_waiting_for_review_dead_end():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    server_source = (root / "backend" / "server.py").read_text(encoding="utf-8")
    rehab_plan_screen = (root / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    movement_map = (root / "frontend" / "app" / "movement-map.tsx").read_text(encoding="utf-8")
    results = (root / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")
    home = (root / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    # While the movement analysis processes, a survey-derived starting plan is
    # issued (rehab_access "interim") and replaced automatically on completion.
    assert '"rehab_access": "interim"' in server_source
    assert '"rehab_plan_source": "survey_interim"' in server_source
    assert 'in ("allowed", "interim")' in server_source
    assert 'testID="plan-interim-banner"' in rehab_plan_screen
    assert 'reviewGate?.rehab_access === "interim"' in movement_map
    assert '"Your starting plan is ready"' in movement_map
    assert 'reviewGate?.rehab_access === "interim"' in results

    # The Home goal is derived from the survey's functional problems.
    assert "deriveFunctionalGoal" in home
    assert "eating and dressing with your arm" in home
    assert "grooming and small hand tasks" in home
    assert "moving around more safely" in home


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
    # Every points-earning moment celebrates: check-in (+2), a delivered
    # caregiver routine (+5), and a completed exercise (+5).
    assert "celebrationEvent(2" in home
    assert "celebrationEvent(5" in caregiver
    assert "celebrationEvent(5" in exercise
    for source in (home, caregiver, exercise):
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

    assert 'testID="rehab-plan-preparation"' in rehab
    assert '"Reviewing your assessment"' in rehab
    assert '"Choosing suitable exercises"' in rehab
    assert '"Creating your plan"' in rehab
    assert "This usually takes less than a minute." in rehab
    assert "const assessment = id === DEMO_ASSESSMENT_ID ? demoAssessment : await fetchAssessment(id);" in rehab
    assert "setPreparationStage(1);" in rehab
    assert 'authedFetch("/api/alira/care-plan")' in rehab
    assert "setPreparationStage(2);" in rehab
    assert "await loadProgress(adjustedAssessment);" in rehab


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
