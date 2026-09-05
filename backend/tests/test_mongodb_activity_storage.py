"""Account-scoped durable activity routes, retries, and connection recovery."""
import asyncio
import copy
import os
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_activity_test")
from backend import server


class Collection:
    def __init__(self):
        self.docs = {}
        self.fail = False

    def check(self):
        if self.fail:
            raise ServerSelectionTimeoutError("test database unavailable")

    async def update_one(self, query, update, upsert=False):
        self.check()
        key = query["_id"]
        if key not in self.docs and upsert:
            self.docs[key] = {**query, **copy.deepcopy(update.get("$setOnInsert", {}))}
        return SimpleNamespace(acknowledged=True)

    async def find_one(self, query, projection=None):
        self.check()
        return next((copy.deepcopy(doc) for doc in self.docs.values() if all(doc.get(k) == v for k, v in query.items())), None)

    def find(self, query, projection=None):
        self.check()
        def matches(doc, filters):
            for key, value in filters.items():
                if key == "$or":
                    if not any(matches(doc, option) for option in value):
                        return False
                elif isinstance(value, dict) and "$regex" in value:
                    if not re.search(value["$regex"], str(doc.get(key, ""))):
                        return False
                elif doc.get(key) != value:
                    return False
            return True
        docs = [copy.deepcopy(doc) for doc in self.docs.values() if matches(doc, query)]
        class Cursor:
            def sort(self, field, direction):
                docs.sort(key=lambda x: x.get(field, ""), reverse=direction == -1)
                return self

            async def to_list(self, limit):
                return [{k: v for k, v in doc.items() if k != "_id"} for doc in docs]
        return Cursor()


@pytest.fixture
def activity_api(monkeypatch):
    db = SimpleNamespace(exercise_repetitions=Collection(), journal_entries=Collection(), alira_activities=Collection())
    async def user(headers):
        uid = headers.get("x-user-id")
        return {"id": uid} if uid else None
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_user_from_header", user)
    monkeypatch.setattr(server, "_require_health_data_consent", lambda _: None)
    monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
    return TestClient(server.app), db


REP = {"exercise_id": "ex_grasp", "plan_id": "plan", "session_id": "session-1", "day": "2026-09-05", "rep": 1, "total_reps": 5, "score": 82}


def test_repetition_retries_do_not_duplicate_and_accounts_are_isolated(activity_api, monkeypatch):
    api, db = activity_api
    for _ in range(3):
        response = api.post("/api/users/exercise-repetitions", headers={"X-User-Id": "patient-a"}, json=REP)
        assert response.status_code == 200 and response.json()["store"] == "mongodb"
    assert len(db.exercise_repetitions.docs) == 1
    monkeypatch.setattr(server, "LOCAL_USERS", {})
    monkeypatch.setattr(server, "LOCAL_CARE_STATE", {})
    # A fresh client (no browser or local-server state) sees the stored record.
    reopened = TestClient(server.app)
    url = "/api/users/exercise-progress?plan_id=plan&date=2026-09-05"
    response = reopened.get(url, headers={"X-User-Id": "patient-a"})
    assert response.json()["progress"]["ex_grasp"]["completed_reps"] == 1
    assert reopened.get(url, headers={"X-User-Id": "patient-b"}).json()["progress"] == {}
    assert reopened.get(url.replace("09-05", "09-06"), headers={"X-User-Id": "patient-a"}).json()["progress"] == {}
    api.post("/api/users/exercise-repetitions", headers={"X-User-Id": "patient-b"}, json=REP)
    assert len(db.exercise_repetitions.docs) == 2


def test_failed_rep_save_or_read_is_not_reported_as_success_or_zero(activity_api):
    api, db = activity_api
    db.exercise_repetitions.fail = True
    headers = {"X-User-Id": "patient-a"}
    response = api.post("/api/users/exercise-repetitions", headers=headers, json=REP)
    assert response.status_code == 503 and response.headers["retry-after"] == "5"
    response = api.get("/api/users/exercise-progress?plan_id=plan&date=2026-09-05", headers=headers)
    assert response.status_code == 503 and "progress" not in response.json()


def test_existing_exercise_activity_is_recovered_even_without_new_day_field(activity_api):
    api, db = activity_api
    db.alira_activities.docs["old"] = {
        "id": "old", "user_id": "patient-a", "plan_id": "plan", "exercise_id": "ex_grasp",
        "completed_at": "2026-09-05T09:00:00Z", "completed_reps": 5, "average_score": 82,
    }
    response = api.get("/api/users/exercise-progress?plan_id=plan&date=2026-09-05", headers={"X-User-Id": "patient-a"})
    assert response.json()["progress"]["ex_grasp"]["completed_reps"] == 5
    assert response.json()["progress"]["ex_grasp"]["last_score"] == 82


def test_retried_completed_activity_returns_the_original_without_duplicate_rewards(activity_api):
    api, db = activity_api
    key = server._patient_record_id("patient-a", "activity", "finished-session")
    db.alira_activities.docs[key] = {
        "_id": key, "id": key, "user_id": "patient-a", "exercise_id": "ex_grasp", "quality_reps": 5,
    }
    response = api.post("/api/alira/activities", headers={"X-User-Id": "patient-a"}, json={
        "client_activity_id": "finished-session", "exercise_id": "ex_grasp", "completed_reps": 5,
    })
    assert response.status_code == 200 and response.json()["already_saved"] is True
    assert len(db.alira_activities.docs) == 1


def test_journal_round_trip_retry_and_account_isolation(activity_api):
    api, db = activity_api
    entry = {"id": "note-1", "body": "Managed a practice session", "createdAt": "2026-09-05T10:00:00Z"}
    for _ in range(2):
        response = api.post("/api/users/journal", headers={"X-User-Id": "patient-a"}, json=entry)
        assert response.status_code == 200
    assert len(db.journal_entries.docs) == 1
    assert api.get("/api/users/journal", headers={"X-User-Id": "patient-a"}).json()["entries"][0]["body"] == entry["body"]
    assert api.get("/api/users/journal", headers={"X-User-Id": "patient-b"}).json()["entries"] == []
    db.journal_entries.fail = True
    assert api.post("/api/users/journal", headers={"X-User-Id": "patient-a"}, json=entry).status_code == 503


def test_activity_routes_require_sign_in_and_valid_dates(activity_api):
    api, _ = activity_api
    assert api.post("/api/users/exercise-repetitions", json=REP).status_code == 401
    assert api.get("/api/users/journal").status_code == 401
    for changes in ({"day": "2026-02-31"}, {"rep": 0}, {"score": 101}):
        assert api.post("/api/users/exercise-repetitions", headers={"X-User-Id": "a"}, json={**REP, **changes}).status_code == 422


def test_final_session_does_not_double_count_reps_and_uses_assisted_score():
    reps = [{**REP, "score": 90}, {**REP, "rep": 2, "score": 80}]
    activities = [{"id": "saved", "client_activity_id": "session-1", "exercise_id": "ex_grasp", "completed_reps": 2, "repetition_scores": [45, 40], "assisted": True}]
    progress = server._exercise_progress_summary(reps, activities, REP["day"])["ex_grasp"]
    assert progress["completed_reps"] == 2
    assert progress["last_score"] == 42.5
    assert progress["sessions"] == 1


def test_health_probe_recovers_while_request_circuit_is_open(monkeypatch):
    breaker = server._MongoCircuitBreaker(30)
    breaker.trip(ServerSelectionTimeoutError("disconnected"))
    calls = []
    async def ping(_):
        calls.append("ping")
        await asyncio.sleep(0.01)
    async def read(*_):
        calls.append("read")
    monkeypatch.setattr(server, "MONGO_CIRCUIT", breaker)
    monkeypatch.setattr(server, "_MONGO_PROBE_TASK", None)
    monkeypatch.setattr(server, "client", SimpleNamespace(admin=SimpleNamespace(command=ping)))
    monkeypatch.setattr(server, "_mongo_database", SimpleNamespace(users=SimpleNamespace(find_one=read)))
    async def run():
        return await asyncio.gather(server._probe_patient_database(), server._probe_patient_database())
    results = asyncio.run(run())
    assert all(result["ok"] for result in results)
    assert calls == ["ping", "read"]
    assert not breaker.is_open()


def test_health_ping_alone_does_not_hide_account_permission_failure(monkeypatch):
    async def ping(_):
        return {"ok": 1}
    async def read(*_):
        raise OperationFailure("not authorized on secret-database", code=13)
    monkeypatch.setattr(server, "MONGO_CIRCUIT", server._MongoCircuitBreaker(30))
    monkeypatch.setattr(server, "client", SimpleNamespace(admin=SimpleNamespace(command=ping)))
    monkeypatch.setattr(server, "_mongo_database", SimpleNamespace(users=SimpleNamespace(find_one=read)))
    result = asyncio.run(server._run_patient_database_probe())
    assert result["ok"] is False and result["error_code"] == "database_permission_denied"
    assert "secret-database" not in str(result)


def test_completion_marker_is_not_mutated_on_a_failed_save(monkeypatch):
    async def fail(*args, **kwargs):
        raise server.HTTPException(503, "unavailable")
    monkeypatch.setattr(server, "_save_user_fields", fail)
    user = {"id": "patient-a"}
    with pytest.raises(server.HTTPException):
        asyncio.run(server._record_initial_assessment_completion(user, "2026-09-05T10:00:00Z"))
    assert "initial_assessment_completed_at" not in user


def test_stale_checkin_cannot_erase_another_day_or_downgrade_completion(monkeypatch):
    document = {"id": "patient-a", "daily_checkins": {}}
    class AtomicUsers:
        async def find_one_and_update(self, query, update, **kwargs):
            assert query == {"id": "patient-a"}
            assert "$set" not in update
            for path, value in update["$min"].items():
                _, day, field = path.split(".")
                entry = document["daily_checkins"].setdefault(day, {})
                entry[field] = min(entry[field], value) if field in entry else value
            return copy.deepcopy(document)
    monkeypatch.setattr(server, "db", SimpleNamespace(users=AtomicUsers()))
    monkeypatch.setattr(server, "_remember_local_user", lambda _: None)
    stale_user = {"id": "patient-a"}
    asyncio.run(server._save_daily_checkins(stale_user, {"2026-09-05": {"status": "complete", "checked_in_at": "first"}}))
    asyncio.run(server._save_daily_checkins(stale_user, {"2026-09-06": {"status": "in_progress"}}))
    calendar = {"2026-09-05": {"status": "in_progress", "checked_in_at": "second"}}
    asyncio.run(server._save_daily_checkins(stale_user, calendar))
    assert calendar["2026-09-05"] == {"status": "complete", "checked_in_at": "first"}
    assert calendar["2026-09-06"]["status"] == "in_progress"
