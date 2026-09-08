"""Testing controls exercise real reward routes without changing activity evidence."""
import copy
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_testing_points_test")

from backend import server


@pytest.fixture
def account(monkeypatch):
    user = {"id": "points-tester", "daily_checkins": {"2026-09-08": {"status": "complete"}},
            "reward_milestones_acknowledged": ["hundred_point_medal"]}

    async def signed_in(_headers):
        return copy.deepcopy(user)

    async def empty(_user_id):
        return []

    async def save(_user, fields, **_kwargs):
        user.update(copy.deepcopy(fields))
        return copy.deepcopy(user)

    monkeypatch.setattr(server, "_user_from_header", signed_in)
    monkeypatch.setattr(server, "_care_activities_for_user", empty)
    monkeypatch.setattr(server, "_care_check_ins_for_user", empty)
    monkeypatch.setattr(server, "_reward_assessments_for_user", empty)
    monkeypatch.setattr(server, "_save_user_fields", save)
    return user


def test_set_100_persists_earns_medal_replays_and_restores(account):
    evidence = copy.deepcopy(account["daily_checkins"])
    with TestClient(server.app) as client:
        assert client.get("/api/users/rewards").json()["points"] == 12
        below = client.post("/api/users/testing/points", json={"points": 99}).json()
        assert below["points"] == 99 and not below["medals"][0]["earned"]
        assert client.post("/api/users/rewards/milestones/hundred_point_medal/acknowledge").status_code == 409
        response = client.post("/api/users/testing/points", json={"points": 100})
        assert response.status_code == 200
        rewards = response.json()
        assert rewards["points"] == 100 and rewards["earned_points"] == 12
        assert rewards["medals"][0]["earned"] and not rewards["medals"][0]["celebrated"]
        assert rewards["next_medal"]["threshold"] == 200
        assert client.get("/api/users/rewards").json()["points"] == 100
        assert client.post("/api/users/rewards/milestones/hundred_point_medal/acknowledge").status_code == 200
        assert client.get("/api/users/rewards").json()["medals"][0]["celebrated"]
        replay = client.post("/api/users/testing/points", json={"points": 100}).json()
        assert replay["testing_revision"] != rewards["testing_revision"]
        assert not replay["medals"][0]["celebrated"]
        reset = client.post("/api/users/testing/points", json={"points": None}).json()
        assert reset["points"] == reset["earned_points"] == 12
        assert reset["testing_revision"] is None
        assert not reset["medals"][0]["earned"]
    assert account["daily_checkins"] == evidence
    assert account["reward_milestones_acknowledged"] == ["hundred_point_medal"]


def test_actual_activity_keeps_earning_after_setting_points(account):
    with TestClient(server.app) as client:
        client.post("/api/users/testing/points", json={"points": 99})
        account["daily_checkins"]["2026-09-09"] = {"status": "in_progress"}
        rewards = client.get("/api/users/rewards").json()
        assert rewards["points"] == 101 and rewards["earned_points"] == 14
        assert rewards["medals"][0]["earned"]
        zero = client.post("/api/users/testing/points", json={"points": 0}).json()
        assert zero["points"] == 0 and not zero["medals"][0]["earned"]


@pytest.mark.parametrize("value", [-1, 1.5, "100", True, 1000001, {}, []])
def test_points_reject_invalid_values(account, value):
    before = copy.deepcopy(account)
    with TestClient(server.app) as client:
        assert client.post("/api/users/testing/points", json={"points": value}).status_code == 422
    assert account == before


def test_testing_points_require_sign_in(monkeypatch):
    async def signed_out(_headers):
        return None
    monkeypatch.setattr(server, "_user_from_header", signed_out)
    with TestClient(server.app) as client:
        assert client.post("/api/users/testing/points", json={"points": 100}).status_code == 401


def test_daily_medal_stays_pending_until_a_later_local_day(account, monkeypatch):
    async def save_days(_user, checkins):
        account["daily_checkins"] = copy.deepcopy(checkins)
    monkeypatch.setattr(server, "_save_daily_checkins", save_days)
    with TestClient(server.app) as client:
        same_day = client.get("/api/users/daily-checkin?date=2026-09-08").json()
        assert same_day["available_medal_date"] is None
        for current_date in ["2026-09-07", "2026-09-08"]:
            assert client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-08", "current_date": current_date}).status_code == 409
        assert client.get("/api/users/daily-checkin?date=2026-09-09").json()["available_medal_date"] == "2026-09-08"
        # A missed login does not erase the earned medal.
        assert client.get("/api/users/daily-checkin?date=2026-09-11").json()["available_medal_date"] == "2026-09-08"
        collected = client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-08", "current_date": "2026-09-09"}).json()
        assert collected["date"] == "2026-09-09" and collected["status"] == "not_checked_in"
        assert not collected["medal_collected"] and collected["available_medal_date"] is None
        assert collected["days"] == [{"date": "2026-09-08", "status": "complete", "medal": True}]
        stamp = account["daily_checkins"]["2026-09-08"]["medal_collected_at"]
        assert client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-08", "current_date": "2026-09-09"}).status_code == 200
        assert account["daily_checkins"]["2026-09-08"]["medal_collected_at"] == stamp
        assert client.get("/api/users/daily-checkin?date=2026-09-09").json()["available_medal_date"] is None


def test_medals_do_not_include_incomplete_or_future_days(account):
    account["daily_checkins"] = {"2026-09-07": {"status": "in_progress"}, "2026-09-10": {"status": "complete"}}
    with TestClient(server.app) as client:
        assert client.get("/api/users/daily-checkin?date=2026-09-09").json()["available_medal_date"] is None
        assert client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-07", "current_date": "2026-09-09"}).status_code == 409
        assert client.post("/api/users/daily-checkin/medal", json={"date": "2026-09-10", "current_date": "bad-date"}).status_code == 422
