"""The daily flow: the app date (as_of) the care plan follows, Alira's once-a-day
exercise reminder posted into the chat, the daily medal on the calendar, and
the testing-phase shortcut that finishes today's exercises with a score."""

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_daily_flow_test")

from backend import server

ROOT = Path(__file__).resolve().parents[2]
USER_ID = "u_daily_flow"


def _user(**overrides):
    user = {
        "id": USER_ID,
        "name": "Molly Wang",
        "profile": {"months_since_stroke": 6, "affected_areas": ["right_upper"], "preferred_name": "Molly"},
        "consent": {"health_data_consent": True},
        "initial_assessment_completed_at": "2026-09-01T09:00:00+00:00",
    }
    user.update(overrides)
    return user


def _stub_care_data(monkeypatch, store, *, activities=None):
    async def user_from_header(_headers):
        return store["user"]

    async def assessments(_user_id):
        return [{
            "id": "a1",
            "created_at": "2026-09-01T09:00:00+00:00",
            "assessment_package": "initial",
            "rehab_plan": [
                {"id": "ex_trunk", "reps": 10, "sets": 3},
                {"id": "ex_reach", "reps": 10, "sets": 3},
            ],
        }]

    async def empty(_user_id):
        return []

    async def activity_rows(_user_id):
        return list(store.get("activities") or [])

    store.setdefault("activities", list(activities or []))
    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", assessments)
    monkeypatch.setattr(server, "_care_check_ins_for_user", empty)
    monkeypatch.setattr(server, "_care_activities_for_user", activity_rows)
    monkeypatch.setattr(server, "_care_issue_reports_for_user", empty)
    monkeypatch.setattr(server, "_persist_local_dict", lambda *_a, **_k: None)
    monkeypatch.setitem(server.LOCAL_CARE_STATE, USER_ID, {})
    monkeypatch.setitem(server.LOCAL_USERS, USER_ID, store["user"])


def _activity(exercise_id, completed_at):
    return {"id": f"aca_{exercise_id}_{completed_at[:10]}", "user_id": USER_ID, "exercise_id": exercise_id, "completed_at": completed_at, "completed_reps": 30}


def test_care_plan_and_rewards_follow_the_app_date(monkeypatch):
    store = {"user": _user()}
    _stub_care_data(monkeypatch, store, activities=[
        _activity("ex_trunk", "2026-09-10T10:00:00+00:00"),
        _activity("ex_reach", "2026-09-10T10:20:00+00:00"),
    ])
    with TestClient(server.app) as client:
        on_the_day = client.get("/api/alira/care-plan?as_of=2026-09-10").json()
        next_day = client.get("/api/alira/care-plan?as_of=2026-09-11").json()
        bad = client.get("/api/alira/care-plan?as_of=2026-13-40")
        rewards_then = client.get("/api/users/rewards?as_of=2026-09-10").json()
    monitoring_then = on_the_day["daily_monitoring"]
    assert sorted(monitoring_then["completed_exercise_ids_today"]) == ["ex_reach", "ex_trunk"]
    assert monitoring_then["remaining_exercise_ids_today"] == []
    assert monitoring_then["current_round_complete"] is True
    monitoring_next = next_day["daily_monitoring"]
    assert monitoring_next["completed_exercise_ids_today"] == []
    assert set(monitoring_next["remaining_exercise_ids_today"]) >= {"ex_reach", "ex_trunk"}
    assert bad.status_code == 422
    assert rewards_then["streak"]["current_days"] == 1
    # The scheduled next assessment date is exposed for the calendar.
    assert on_the_day["assessment"]["due_at"]


def test_alira_sends_the_daily_reminder_once_into_the_chat(monkeypatch):
    store = {"user": _user()}
    _stub_care_data(monkeypatch, store)

    async def no_db(*_args, **_kwargs):
        raise RuntimeError("no db in test")

    monkeypatch.setattr(server.db.chat_sessions, "find_one", no_db, raising=False)
    monkeypatch.setattr(server.db.chat_sessions, "update_one", no_db, raising=False)
    session_key = f"{USER_ID}:s_daily"
    server.LOCAL_CHAT_SESSIONS.pop(session_key, None)
    try:
        with TestClient(server.app) as client:
            first = client.post("/api/chat/daily-reminder", json={"session_id": "s_daily", "date": "2026-09-12"}).json()
            second = client.post("/api/chat/daily-reminder", json={"session_id": "s_daily", "date": "2026-09-12"}).json()
            history = client.get("/api/chat/history?session_id=s_daily").json()
        assert first["sent"] is True
        text = first["text"]
        assert "Molly" in text
        assert "before the end of today" in text
        assert "today's scores are not saved" in text and "lose track of the progress" in text
        assert "You have got this" in text
        assert set(first["remaining_exercise_ids"]) >= {"ex_reach", "ex_trunk"}
        # Sent once per day; the chat carries it as a message from Alira.
        assert second["sent"] is False and second["reason"] == "already_sent_today"
        turns = history["turns"]
        assert len(turns) == 1 and turns[0]["role"] == "assistant" and turns[0]["text"] == text
        assert turns[0]["daily_reminder_date"] == "2026-09-12"
    finally:
        server.LOCAL_CHAT_SESSIONS.pop(session_key, None)


def test_no_reminder_before_the_initial_assessment_or_once_the_day_is_done(monkeypatch):
    store = {"user": _user(initial_assessment_completed_at=None)}
    _stub_care_data(monkeypatch, store)

    async def no_assessments(_user_id):
        return []

    monkeypatch.setattr(server, "_care_assessments_for_user", no_assessments)
    with TestClient(server.app) as client:
        pending = client.post("/api/chat/daily-reminder", json={"session_id": "s_daily2", "date": "2026-09-12"}).json()
    assert pending["sent"] is False and pending["reason"] == "initial_assessment_pending"

    store = {"user": _user()}
    _stub_care_data(monkeypatch, store, activities=[
        _activity("ex_trunk", "2026-09-12T10:00:00+00:00"),
        _activity("ex_reach", "2026-09-12T10:20:00+00:00"),
    ])
    with TestClient(server.app) as client:
        done = client.post("/api/chat/daily-reminder", json={"session_id": "s_daily3", "date": "2026-09-12"}).json()
    assert done["sent"] is False and done["reason"] == "no_exercises_remaining"


def test_daily_medal_needs_a_complete_day_and_then_shows_on_the_calendar(monkeypatch):
    store = {"user": _user()}
    _stub_care_data(monkeypatch, store)

    def sync_user():
        saved = server.LOCAL_USERS.get(USER_ID)
        if saved:
            store["user"] = saved

    with TestClient(server.app) as client:
        too_early = client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-12"})
        assert too_early.status_code == 409
        client.post("/api/users/daily-checkin/complete", json={"date": "2026-09-12"})
        sync_user()
        collected = client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-12"})
        assert collected.status_code == 200
        body = collected.json()
        assert body["medal_collected"] is True
        assert body["days"] == [{"date": "2026-09-12", "status": "complete", "medal": True}]
        sync_user()
        again = client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-12"}).json()
        assert again["medal_collected"] is True
        listed = client.get("/api/users/daily-checkin?date=2026-09-13").json()
        assert listed["medal_collected"] is False
        assert listed["days"][0]["medal"] is True


def test_testing_shortcut_activity_is_recorded_for_plan_exercises(monkeypatch):
    store = {"user": _user()}
    _stub_care_data(monkeypatch, store)
    with TestClient(server.app) as client:
        response = client.post("/api/alira/activities", json={
            "exercise_id": "ex_reach",
            "plan_id": "a1",
            "completed_reps": 30,
            "quality_reps": 30,
            "average_score": 92,
            "repetition_scores": [92] * 30,
            "completed_at": "2026-09-12T14:00:00+00:00",
            "testing_shortcut": True,
        })
    assert response.status_code == 200
    activity = response.json()["activity"]
    assert activity["testing_shortcut"] is True
    assert activity["completed_at"].startswith("2026-09-12T14:00:00")
    assert activity["average_score"] == 92


def test_app_wires_the_date_stepper_reminder_medal_calendar_and_finish_button():
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    plan = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    exercise = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    modals = (ROOT / "frontend" / "src" / "components" / "DailyFlowModals.tsx").read_text(encoding="utf-8")
    app_date = (ROOT / "frontend" / "src" / "appDate.ts").read_text(encoding="utf-8")
    calendar = (ROOT / "frontend" / "src" / "components" / "DailyCheckInCalendar.tsx").read_text(encoding="utf-8")

    # One app date everywhere: the shared helper follows the override, and the
    # server is told which day the app is showing.
    assert "export function appDateString(): string" in app_date and "export function appNow(): Date" in app_date
    assert "return date ? formatLocalDate(date) : appDateString();" in calendar
    assert "authedFetch(`/api/alira/care-plan${appDateQuery()}`)" in home
    assert "authedFetch(`/api/users/rewards${appDateQuery()}`)" in home
    assert "completed_at: appNow().toISOString()," in exercise
    # Date stepper in the upper middle of Home (wide) or under the header (compact).
    assert 'testID="home-app-date-stepper"' in modals and 'testID="home-app-date-next"' in modals
    assert "<AppDateStepper" in home and "onShift={(days) => { void changeAppDate(shiftedAppDate(days)); }}" in home
    # Alira's reminder: once per day, posted into the chat, shown on Home.
    assert 'authedFetch("/api/chat/daily-reminder"' in home
    assert 'dailyPromptKey("alira-reminder", userId, todayIso)' in home
    assert 'testID="alira-daily-reminder"' in modals
    # Re-assessment day prompt that starts the assessment.
    assert 'dailyPromptKey("reassessment", userId, todayIso)' in home and "if (hasInitialAssessment && followUpDue)" in home
    assert 'testID="reassessment-day-start"' in modals
    # Medal after the day's exercises, collected onto the calendar with the next assessment date.
    assert 'authedFetch("/api/users/daily-checkin/medal"' in home
    assert "const medalAvailable = todaysExercisesComplete && checkIn.date === todayIso && checkIn.status === \"complete\" && !checkIn.medalCollected;" in home
    assert 'testID="daily-medal-collect"' in modals and 'testID="medal-calendar"' in modals
    assert "assessmentDate={assessmentDueDate || undefined}" in home
    assert 'testID="home-open-calendar"' in home
    # Rehab plan: FINISHED banner, testing finish button with a score, award prompt.
    assert 'testID="plan-finished-banner"' in plan and ">FINISHED<" in plan
    assert 'testID="plan-testing-finish"' in plan and 'testID="plan-testing-score"' in plan
    assert "testing_shortcut: true," in plan
    assert 'testID="plan-award-go-home"' in plan and 'router.dismissTo("/")' in plan
    # Today's plan starts from zero each day.
    assert "const completedToday = saved.day === appDateString() ? Math.min(saved.completed_reps || 0, adjustedTotal) : 0;" in plan
    assert "const completedToday = prev.day === today ? prev.completed_reps : 0;" in exercise
