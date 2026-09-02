import os
from pathlib import Path

from fastapi.testclient import TestClient


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_journey_score_test")

from backend import server


ROOT = Path(__file__).resolve().parents[2]
JOURNEY = (ROOT / "frontend" / "app" / "(tabs)" / "journey.tsx").read_text(encoding="utf-8")
PANEL = (ROOT / "frontend" / "src" / "components" / "JourneyExerciseScoresPanel.tsx").read_text(encoding="utf-8")
REHAB_PLAN = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
REHAB_TIMING = (ROOT / "frontend" / "src" / "rehabTiming.ts").read_text(encoding="utf-8")


def test_exercise_scores_follow_completion_summary_and_precede_movement_progress():
    assert "<JourneyExerciseScoresPanel demoMode={demoMode} />" in JOURNEY
    assert JOURNEY.index('testID="journey-completion-summary"') < JOURNEY.index('testID="journey-todays-rehab"')
    assert JOURNEY.index('testID="journey-todays-rehab"') < JOURNEY.index("<JourneyExerciseScoresPanel")
    assert JOURNEY.index("<JourneyExerciseScoresPanel") < JOURNEY.index("<JourneyProgressPanel")


def test_today_rehab_strip_uses_the_active_plan_and_opens_the_real_plan_route():
    assert 'authedFetch("/api/alira/care-plan")' in JOURNEY
    assert "remaining_exercise_ids_today" in JOURNEY
    assert "active_exercise_ids" in JOURNEY
    assert "approved_exercise_ids" in JOURNEY
    assert "estimateRehabMinutes(todayExercises)" in JOURNEY
    assert 'testID="journey-start-rehab"' in JOURNEY
    assert 'pathname: "/rehab-plan" as never' in JOURNEY
    assert "params: { id: todayPlanId }" in JOURNEY
    assert "demoMode ? DEMO_ASSESSMENT_ID" in JOURNEY


def test_journey_and_plan_share_the_same_dose_based_time_estimate():
    assert 'import { estimateRehabMinutes } from "@/src/rehabTiming";' in JOURNEY
    assert 'import { estimateRehabMinutes } from "@/src/rehabTiming";' in REHAB_PLAN
    assert "estimateRehabMinutes(todayExercises)" in JOURNEY
    assert "estimateRehabMinutes(data?.rehab_plan ?? [])" in REHAB_PLAN
    assert "exercise.sets * exercise.reps * 15" in REHAB_TIMING


def test_exercise_score_panel_uses_persisted_session_averages_and_goal_line():
    assert 'authedFetch("/api/alira/activities?limit=100")' in PANEL
    assert "activity.average_score" in PANEL
    assert "activities.reduce((sum, activity) => sum + activity.average_score, 0) / activities.length" in PANEL
    assert "const DEFAULT_TARGET = 80" in PANEL
    assert 'strokeDasharray="7 7"' in PANEL
    assert "Personal goal {target}" in PANEL


def test_exercise_score_panel_has_real_empty_loading_and_detail_states():
    assert 'testID="journey-exercise-scores"' in PANEL
    assert 'testID="journey-exercise-score-chart"' in PANEL
    assert 'testID="journey-exercise-score-details-toggle"' in PANEL
    assert 'testID="journey-exercise-score-details"' in PANEL
    assert "Each point will show the average of all scored repetitions" in PANEL
    assert "activity.repetition_scores?.length" in PANEL


def test_demo_scores_are_explicitly_labelled_as_sample_data():
    assert "DEMO_SCORE_VALUES" in PANEL
    assert ">SAMPLE</Text>" in PANEL


def test_exercise_score_activity_endpoint_returns_the_weekly_chart_contract(monkeypatch):
    async def user_from_header(_headers):
        return {"id": "journey-score-user", "consent": {"health_data_consent": True}}

    async def activities(_user_id):
        return [
            {
                "id": "activity-1",
                "exercise_id": "ex_reach",
                "completed_reps": 3,
                "average_score": 82,
                "repetition_scores": [78, 82, 86],
                "completed_at": "2026-09-02T10:00:00+00:00",
            }
        ]

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_activities_for_user", activities)

    response = TestClient(server.app).get(
        "/api/alira/activities?limit=100",
        headers={"X-User-Id": "journey-score-user"},
    )

    assert response.status_code == 200
    assert response.json()["target_score"] == 80
    assert response.json()["activities"][0]["average_score"] == 82
    assert response.json()["activities"][0]["repetition_scores"] == [78, 82, 86]
