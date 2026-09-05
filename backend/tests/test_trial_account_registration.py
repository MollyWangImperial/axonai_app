"""Trial sign-in must persist a real account before returning success."""

import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_registration_test")

from backend import server
from backend.tests.test_account_state_persistence import MemoryUsers


class Handoffs:
    def __init__(self):
        self.records = {}

    async def insert_one(self, record):
        self.records[record["token_hash"]] = dict(record)

    async def find_one_and_delete(self, query, projection=None):
        record = self.records.get(query["token_hash"])
        if record and record["expires_at"] > query["expires_at"]["$gt"]:
            return self.records.pop(query["token_hash"])
        return None


@pytest.fixture
def registration(monkeypatch, tmp_path):
    users, handoffs = MemoryUsers(), Handoffs()
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users, login_handoffs=handoffs))
    monkeypatch.setattr(server, "LOCAL_USERS", {})
    monkeypatch.setattr(server, "LOCAL_USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
    monkeypatch.setattr(server, "TRIAL_ACCESS_CHECK_ENABLED", True)
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "registration-test-code")
    with TestClient(server.app) as client:
        yield client, users, handoffs


def payload(email="new@example.com", name="New Patient", code="registration-test-code"):
    return {"email": email, "name": name, "role": "patient", "trial_code": code}


@pytest.mark.parametrize("route", ["login", "signup", "login-handoff"])
def test_each_sign_in_entry_point_persists_new_accounts(registration, route):
    client, users, handoffs = registration
    response = client.post(f"/api/users/{route}", json=payload("New@Example.com", "  New Patient  "))
    assert response.status_code == 200
    assert len(users.documents) == 1
    saved = users.documents[0]
    assert saved["email"] == "new@example.com"
    assert saved["name"] == "New Patient"
    assert saved["id"] == saved["_id"] == server._stable_user_id("new@example.com")
    assert saved["trial_access_granted"] is True
    assert saved["created_at"] and saved["last_login_at"]
    assert "trial_code" not in saved
    assert "registration-test-code" not in response.text

    if route == "login-handoff":
        token = response.json()["handoff_token"]
        assert token not in handoffs.records
        completed = client.post("/api/users/login-handoff/complete", json={"token": token})
        assert completed.status_code == 200
        assert completed.json()["id"] == saved["id"]
        assert client.post("/api/users/login-handoff/complete", json={"token": token}).status_code == 401


def test_distinct_emails_get_separate_accounts_and_returning_account_retains_progress(registration, monkeypatch):
    client, users, _ = registration
    first = client.post("/api/users/login", json=payload()).json()
    stored = users._match({"id": first["id"]})
    stored.update({
        "initial_assessment_completed_at": "2026-09-01T12:00:00+00:00",
        "daily_checkins": {"2026-09-05": {"status": "complete"}},
        "onboarding_complete": True,
    })
    second = client.post("/api/users/login", json=payload("other@example.com", "Other Patient")).json()
    assert second["id"] != first["id"]
    monkeypatch.setattr(server, "LOCAL_USERS", {})
    returning = client.post("/api/users/login", json=payload("NEW@example.com")).json()
    assert len(users.documents) == 2
    assert returning["id"] == first["id"]
    assert returning["initial_assessment_completed_at"] == stored["initial_assessment_completed_at"]
    assert returning["daily_checkins"] == stored["daily_checkins"]
    assert returning["onboarding_complete"] is True


@pytest.mark.parametrize("code", ["", "wrong", "\u9519\u8bef"])
@pytest.mark.parametrize("route", ["login", "signup", "login-handoff"])
def test_invalid_code_never_creates_an_account(registration, code, route):
    client, users, handoffs = registration
    response = client.post(f"/api/users/{route}", json=payload(code=code))
    assert response.status_code == 403
    assert users.documents == []
    assert handoffs.records == {}


@pytest.mark.parametrize("email,name", [("not-an-email", "Patient"), ("new@example.com", "   ")])
def test_invalid_identity_is_not_saved(registration, email, name):
    client, users, _ = registration
    assert client.post("/api/users/login", json=payload(email, name)).status_code == 422
    assert users.documents == []


@pytest.mark.parametrize("failure", ["lookup", "write", "readback", "grant", "handoff"])
def test_mongo_failure_never_reports_success_or_creates_a_device_only_account(registration, monkeypatch, failure):
    client, users, handoffs = registration
    original_find = users.find_one
    original_update = users.update_one

    async def find(query, projection=None):
        if failure == "lookup" or (failure == "readback" and "_id" in query):
            raise RuntimeError("Database connection unavailable")
        return await original_find(query, projection)

    async def update(query, values, upsert=False):
        if failure == "write" or (failure == "grant" and "$set" in values):
            raise RuntimeError("Database write unavailable")
        return await original_update(query, values, upsert)

    async def insert(record):
        raise RuntimeError("Database handoff unavailable")

    monkeypatch.setattr(users, "find_one", find)
    monkeypatch.setattr(users, "update_one", update)
    if failure == "handoff":
        monkeypatch.setattr(handoffs, "insert_one", insert)
    response = client.post("/api/users/login-handoff", json=payload())
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "handoff_token" not in response.json()
    if failure in {"lookup", "write", "readback"}:
        assert server.LOCAL_USERS == {}


def test_concurrent_first_sign_ins_reuse_mongodb_identity_and_saved_state(registration, monkeypatch):
    _, users, _ = registration
    original_update = users.update_one

    async def competing_create(query, update, upsert=False):
        if upsert and "$setOnInsert" in update and not users.documents:
            await original_update(query, update, upsert=True)
            users.documents[0]["initial_assessment_completed_at"] = "2026-09-01T12:00:00+00:00"
        return await original_update(query, update, upsert)

    monkeypatch.setattr(users, "update_one", competing_create)
    user, _ = asyncio.run(server._find_or_create_user_account("new@example.com", "New Patient"))
    assert len(users.documents) == 1
    assert user["initial_assessment_completed_at"] == "2026-09-01T12:00:00+00:00"
    assert users.calls[0][0] == {"_id": user["id"]}


def test_rehyn_com_cors_preflight_allows_sign_in(registration):
    client, _, _ = registration
    response = client.options("/api/users/login-handoff", headers={
        "Origin": "https://rehyn.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] in {"*", "https://rehyn.com"}
