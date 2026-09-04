"""When MongoDB is unreachable the server fails fast instead of waiting for the
server-selection timeout on every call, so sign-in and the app stay responsive
on the local fallback."""

import asyncio
import os
import time

import pytest
from fastapi import HTTPException
from pymongo.errors import ServerSelectionTimeoutError

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_circuit_breaker_test")

from backend import server


class _DeadCollection:
    """Behaves like a Motor collection whose server never answers."""

    def __init__(self):
        self.calls = 0

    async def find_one(self, *args, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.01)
        raise ServerSelectionTimeoutError("cluster0.example.mongodb.net: timed out")

    async def update_one(self, *args, **kwargs):
        self.calls += 1
        raise ServerSelectionTimeoutError("cluster0.example.mongodb.net: timed out")

    def find(self, *args, **kwargs):
        return _DeadCursor(self)


class _DeadCursor:
    def __init__(self, collection):
        self.collection = collection

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, *args, **kwargs):
        self.collection.calls += 1
        raise ServerSelectionTimeoutError("timed out")


class _LiveCollection:
    def __init__(self):
        self.calls = 0

    async def find_one(self, *args, **kwargs):
        self.calls += 1
        return {"id": "u_1"}


def test_first_timeout_trips_the_breaker_and_later_calls_fail_at_once():
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    dead = _DeadCollection()
    guarded = server._GuardedCollection(dead, breaker)

    async def run():
        started = time.monotonic()
        try:
            await guarded.find_one({"id": "x"})
        except ServerSelectionTimeoutError:
            pass
        assert breaker.is_open()
        # Every further call while the breaker is open raises immediately and
        # never touches the driver.
        for _ in range(5):
            try:
                await guarded.update_one({"id": "x"}, {"$set": {"a": 1}})
                raise AssertionError("expected MongoUnavailableError")
            except server.MongoUnavailableError:
                pass
        try:
            await guarded.find({}).sort("a", 1).to_list(10)
            raise AssertionError("expected MongoUnavailableError")
        except server.MongoUnavailableError:
            pass
        return time.monotonic() - started

    elapsed = asyncio.run(run())
    assert dead.calls == 1
    assert elapsed < 1.0
    assert breaker.status()["state"] == "cooldown" and breaker.status()["retry_in_s"] > 0


def test_breaker_lets_one_call_through_after_the_cooldown_and_clears_on_success():
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    breaker.trip(ServerSelectionTimeoutError("timed out"))
    breaker.down_until = time.monotonic() - 1  # cooldown elapsed
    live = _LiveCollection()
    guarded = server._GuardedCollection(live, breaker)
    result = asyncio.run(guarded.find_one({"id": "u_1"}))
    assert result == {"id": "u_1"} and live.calls == 1
    assert not breaker.is_open() and breaker.status()["state"] == "closed"


def test_cursor_results_trip_the_breaker_too():
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    dead = _DeadCollection()
    guarded = server._GuardedCollection(dead, breaker)

    async def run():
        try:
            await guarded.find({"user_id": "u"}).to_list(100)
        except ServerSelectionTimeoutError:
            pass

    asyncio.run(run())
    assert breaker.is_open() and dead.calls == 1


def test_sign_in_falls_back_locally_within_seconds_when_the_database_is_down(monkeypatch, tmp_path):
    breaker = server._MongoCircuitBreaker(cooldown_s=30)

    class _DeadDatabase:
        users = server._GuardedCollection(_DeadCollection(), breaker)

    monkeypatch.setattr(server, "db", _DeadDatabase())
    monkeypatch.setattr(server, "_persist_local_dict", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "LOCAL_USERS", {})
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "trial-code-for-test")

    started = time.monotonic()
    result = asyncio.run(server._sign_in(server.UserSignup(email="molly@example.com", name="Molly", role="patient", trial_code="trial-code-for-test")))
    assert time.monotonic() - started < 2.0
    assert result["trial_access_granted"] is True
    assert result["email"] == "molly@example.com"
    assert breaker.is_open()


def test_database_is_guarded_and_hosted_timeout_is_five_seconds():
    assert isinstance(server.db, server._GuardedDatabase)
    assert isinstance(server.db.users, server._GuardedCollection)
    assert isinstance(server.db["users"], server._GuardedCollection)
    source = (os.path.dirname(server.__file__) + "/server.py")
    text = open(source, encoding="utf-8").read()
    assert '"MONGO_SERVER_SELECTION_TIMEOUT_MS", 1000 if _MONGO_IS_LOCAL else 5000' in text
    assert 'task_video_bucket = AsyncIOMotorGridFSBucket(_mongo_database, bucket_name="task_videos")' in text
    assert '@api_router.get("/health/db")' in text


def test_hosted_sign_in_never_creates_an_ephemeral_patient_account(monkeypatch):
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    dead = _DeadCollection()
    monkeypatch.setattr(server, "db", type("DeadDatabase", (), {
        "users": server._GuardedCollection(dead, breaker),
    })())
    monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
    monkeypatch.setattr(server, "LOCAL_USERS", {})

    with pytest.raises(HTTPException) as raised:
        asyncio.run(server.get_or_create_user("molly@example.com", "Molly"))

    assert raised.value.status_code == 503
    assert "Nothing has been reset or marked incomplete" in raised.value.detail
    assert server.LOCAL_USERS == {}


def test_hosted_account_write_is_not_acknowledged_when_mongo_is_down(monkeypatch):
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    dead = _DeadCollection()
    monkeypatch.setattr(server, "db", type("DeadDatabase", (), {
        "users": server._GuardedCollection(dead, breaker),
    })())
    monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
    monkeypatch.setattr(server, "LOCAL_USERS", {})

    with pytest.raises(HTTPException) as raised:
        asyncio.run(server._save_user_fields(
            {"id": "u_patient", "email": "molly@example.com"},
            {"initial_assessment_completed_at": "2026-09-04T12:00:00+00:00"},
            context="initial-assessment account marker",
        ))

    assert raised.value.status_code == 503
    assert server.LOCAL_USERS == {}


def test_database_health_is_unhealthy_while_durable_store_is_in_cooldown(monkeypatch):
    breaker = server._MongoCircuitBreaker(cooldown_s=30)
    breaker.trip(ServerSelectionTimeoutError("Atlas unavailable"))
    monkeypatch.setattr(server, "MONGO_CIRCUIT", breaker)

    response = asyncio.run(server.database_health())

    assert response.status_code == 503
    assert b'"ok":false' in response.body


def test_hosted_atlas_client_uses_certifi_and_render_checks_database_health():
    source = open(os.path.dirname(server.__file__) + "/server.py", encoding="utf-8").read()
    render = open(os.path.dirname(server.__file__) + "/../render.yaml", encoding="utf-8").read()

    assert '_mongo_client_options["tlsCAFile"] = certifi.where()' in source
    assert "ALLOW_EPHEMERAL_PATIENT_STATE = _MONGO_IS_LOCAL" in source
    assert "healthCheckPath: /api/health/db" in render


def test_assessment_reads_and_first_plan_access_require_the_durable_store():
    source = open(os.path.dirname(server.__file__) + "/server.py", encoding="utf-8").read()

    assert '_require_durable_patient_store(purpose, e)' in source
    assert '_require_durable_patient_store("rehab plan access", exc)' in source
