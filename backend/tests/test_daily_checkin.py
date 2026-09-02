import os

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_daily_checkin_test")

from backend import server


def _user_provider(store):
    async def _signed_in_user(_headers):
        return store["user"]
    return _signed_in_user


def _client_with_user(monkeypatch):
    store = {"user": {"id": "u_daily_checkin", "consent": {"health_data_consent": True}}}
    monkeypatch.setattr(server, "_user_from_header", _user_provider(store))

    original = server.LOCAL_USERS.get("u_daily_checkin")

    def sync_user():
        # The endpoints fall back to LOCAL_USERS when Mongo is unavailable;
        # mirror the persisted state back into the provider between calls.
        saved = server.LOCAL_USERS.get("u_daily_checkin")
        if saved:
            store["user"] = saved

    return store, sync_user, original


def test_check_in_marks_day_in_progress_and_completion_earns_check_mark(monkeypatch):
    store, sync_user, original = _client_with_user(monkeypatch)
    try:
        with TestClient(server.app) as client:
            fresh = client.get("/api/users/daily-checkin")
            assert fresh.status_code == 200
            assert fresh.json()["status"] == "not_checked_in"
            assert fresh.json()["days"] == []

            started = client.post("/api/users/daily-checkin", json={"date": "2026-08-30"})
            assert started.status_code == 200
            assert started.json()["status"] == "in_progress"
            assert started.json()["days"] == [{"date": "2026-08-30", "status": "in_progress"}]
            sync_user()

            # Idempotent: a second tap does not reset the day.
            again = client.post("/api/users/daily-checkin", json={"date": "2026-08-30"})
            assert again.json()["status"] == "in_progress"
            sync_user()

            # A fresh login on the same local day reads the account record and
            # does not ask the patient to check in a second time.
            same_day = client.get("/api/users/daily-checkin?date=2026-08-30")
            assert same_day.status_code == 200
            assert same_day.json()["date"] == "2026-08-30"
            assert same_day.json()["status"] == "in_progress"

            next_day = client.get("/api/users/daily-checkin?date=2026-08-31")
            assert next_day.json()["status"] == "not_checked_in"

            done = client.post("/api/users/daily-checkin/complete", json={"date": "2026-08-30"})
            assert done.status_code == 200
            assert done.json()["status"] == "complete"
            assert done.json()["days"] == [{"date": "2026-08-30", "status": "complete"}]
            sync_user()

            # Completing again stays complete; checking in later never downgrades.
            recheck = client.post("/api/users/daily-checkin", json={"date": "2026-08-30"})
            assert recheck.json()["status"] == "complete"
    finally:
        if original is None:
            server.LOCAL_USERS.pop("u_daily_checkin", None)
        else:
            server.LOCAL_USERS["u_daily_checkin"] = original


def test_completing_exercises_without_a_prior_tap_still_earns_the_mark(monkeypatch):
    store, sync_user, original = _client_with_user(monkeypatch)
    try:
        with TestClient(server.app) as client:
            done = client.post("/api/users/daily-checkin/complete", json={"date": "2026-08-29"})
            assert done.status_code == 200
            assert done.json()["status"] == "complete"
    finally:
        if original is None:
            server.LOCAL_USERS.pop("u_daily_checkin", None)
        else:
            server.LOCAL_USERS["u_daily_checkin"] = original


def test_invalid_dates_are_rejected(monkeypatch):
    store, sync_user, original = _client_with_user(monkeypatch)
    try:
        with TestClient(server.app) as client:
            for bad in ("2026-13-01", "2026-00-10", "20260830", "2026-08-32", "not-a-date"):
                response = client.post("/api/users/daily-checkin", json={"date": bad})
                assert response.status_code == 422, bad
                response = client.get(f"/api/users/daily-checkin?date={bad}")
                assert response.status_code == 422, bad
    finally:
        if original is None:
            server.LOCAL_USERS.pop("u_daily_checkin", None)
        else:
            server.LOCAL_USERS["u_daily_checkin"] = original


def test_home_screen_wires_the_calendar_and_exercise_completion_earns_the_mark():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    home = (root / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    exercise = (root / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")
    assert 'authedFetch(`/api/users/daily-checkin?date=${encodeURIComponent(requestedDate)}`)' in home
    assert 'checkIn.date === todayIso' in home
    assert 'testID: "daily-checkin-button"' in home
    assert 'testID="home-week-toggle"' in home
    assert 'authedFetch("/api/users/daily-checkin/complete"' in exercise
