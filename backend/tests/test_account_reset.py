"""Account reset tests use only synthetic in-memory records and temp files."""
import copy
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_reset_test")

import pytest
from fastapi.testclient import TestClient
from backend import server
from backend.account_reset import ACTIVITY_COLLECTIONS


def value(doc, key):
    for part in key.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def matches(doc, query):
    return all((value(doc, key) is not None) == wanted["$exists"]
               if isinstance(wanted, dict) and "$exists" in wanted
               else value(doc, key) == wanted for key, wanted in query.items())


class Cursor:
    def __init__(self, docs): self.docs = copy.deepcopy(docs)
    async def to_list(self, *_args): return self.docs


class Collection:
    def __init__(self, docs=()):
        self.docs = copy.deepcopy(list(docs))
        self.fail_delete = False

    def find(self, query, *_args): return Cursor([d for d in self.docs if matches(d, query)])
    async def find_one(self, query, *_args):
        return next((copy.deepcopy(d) for d in self.docs if matches(d, query)), None)
    async def update_one(self, query, update, **_kwargs):
        for doc in self.docs:
            if matches(doc, query):
                doc.update(copy.deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)
    async def replace_one(self, query, replacement):
        for index, doc in enumerate(self.docs):
            if matches(doc, query):
                self.docs[index] = copy.deepcopy(replacement)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)
    async def delete_many(self, query):
        if self.fail_delete: raise RuntimeError("Synthetic database failure")
        self.docs[:] = [d for d in self.docs if not matches(d, query)]
    async def delete_one(self, query): await self.delete_many(query)


class Database:
    def __init__(self): self.collections = {}
    def __getitem__(self, key): return self.collections.setdefault(key, Collection())
    def __getattr__(self, key): return self[key]


def patient(uid):
    return dict(id=uid, name="Reset QA", email=f"{uid}@example.invalid", role="patient", credits=100,
                trial_access_granted=True, onboarding_complete=True, profile={"preferred_name": "QA"},
                consent={"terms_version": "1.0", "terms_accepted": True, "health_data_consent": True},
                initial_assessment_completed_at="2026-09-01", daily_checkins={"2026-09-07": {"status": "complete"}},
                reward_milestones_acknowledged=["100"], next_assessment_override="2026-09-07")


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    db = Database()
    db.users.docs = [patient("reset-qa"), patient("other-qa")]
    for name in ACTIVITY_COLLECTIONS:
        db[name].docs = [{"user_id": "reset-qa", "id": "old"}, {"user_id": "other-qa", "id": "keep"}]
    db.plan_signoffs.docs = [{"patient_user_id": "reset-qa"}, {"patient_user_id": "other-qa"}]
    db.task_videos.files = Collection()
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "LOCAL_USERS", {"reset-qa": patient("reset-qa"), "other-qa": patient("other-qa")})
    monkeypatch.setattr(server, "LOCAL_ASSESSMENTS", copy.deepcopy(db.assessments.docs))
    monkeypatch.setattr(server, "LOCAL_TASK_PROGRESS", {"old": {"user_id": "reset-qa"}, "keep": {"user_id": "other-qa"}})
    monkeypatch.setattr(server, "LOCAL_CARE_STATE", {"reset-qa": {"activities": [1]}, "other-qa": {"activities": [2]}})
    monkeypatch.setattr(server, "LOCAL_CHAT_SESSIONS", {"old": {"user_id": "reset-qa"}, "keep": {"user_id": "other-qa"}})
    monkeypatch.setattr(server, "LOCAL_LOGIN_HANDOFFS", {})
    for name in ("LOCAL_USERS_FILE", "LOCAL_ASSESSMENTS_FILE", "LOCAL_TASK_PROGRESS_FILE", "LOCAL_CARE_STATE_FILE"):
        monkeypatch.setattr(server, name, tmp_path / f"{name}.json")
    monkeypatch.setattr(server, "TASK_VIDEO_FALLBACK_DIR", tmp_path / "videos")
    return TestClient(server.app), db


def reset(client, **body):
    return client.post("/api/users/account/reset", headers={"X-User-Id": "reset-qa"},
                       json={"confirmation": "RESET", "request_id": "reset-request-123456", **body})


def test_reset_clears_journey_keeps_identity_and_other_account(isolated):
    client, db = isolated
    original = copy.deepcopy(db.users.docs[1])
    response = reset(client)
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["id"] == "reset-qa" and user["email"] == "reset-qa@example.invalid"
    assert user["name"] == "Reset QA" and user["trial_access_granted"] is True
    assert user["is_new_account"] and user["consent_required"]
    assert not user["onboarding_complete"] and not user["initial_assessment_completed_at"]
    assert user["profile"] is None and user["daily_checkins"] == {}
    assert "next_assessment_override" not in user and user["account_generation"] == 1
    assert db.users.docs[1] == original
    for name in ACTIVITY_COLLECTIONS:
        assert db[name].docs == [{"user_id": "other-qa", "id": "keep"}]
    assert db.plan_signoffs.docs == [{"patient_user_id": "other-qa"}]
    assert server.LOCAL_ASSESSMENTS == [{"user_id": "other-qa", "id": "keep"}]
    assert "reset-qa" not in server.LOCAL_CARE_STATE and "other-qa" in server.LOCAL_CARE_STATE


def test_reset_retry_does_not_clear_new_survey(isolated):
    client, db = isolated
    assert reset(client).status_code == 200
    db.users.docs[0]["profile"] = {"preferred_name": "New survey"}
    assert reset(client).status_code == 200
    assert db.users.docs[0]["profile"] == {"preferred_name": "New survey"}
    assert db.users.docs[0]["account_generation"] == 1


def test_failure_keeps_pending_marker_and_retry_finishes(isolated):
    client, db = isolated
    db.exercise_repetitions.fail_delete = True
    assert reset(client).status_code == 503
    assert db.users.docs[0]["reset_pending"]
    blocked = client.post("/api/users/consent", headers={"X-User-Id": "reset-qa"}, json={})
    assert blocked.status_code == 503
    db.exercise_repetitions.fail_delete = False
    assert reset(client).status_code == 200
    assert "reset_pending" not in db.users.docs[0]


def test_no_auth_or_confirmation_cannot_delete(isolated):
    client, db = isolated
    before = copy.deepcopy(db.users.docs)
    assert client.post("/api/users/account/reset", json={"confirmation": "RESET", "request_id": "reset-request-123456"}).status_code == 401
    assert reset(client, confirmation="no").status_code == 422
    assert db.users.docs == before


def test_previous_generation_cannot_restore_activity(isolated):
    client, db = isolated
    assert reset(client).status_code == 200
    response = client.post("/api/users/onboarding", headers={"X-User-Id": "reset-qa"}, json={"preferred_name": "Old survey"})
    assert response.status_code == 409 and response.json()["code"] == "ACCOUNT_RESET"
    assert db.users.docs[0]["profile"] is None
    consent = client.post("/api/users/consent", headers={"X-User-Id": "reset-qa", "X-Account-Generation": "1"},
                          json={"terms_version": "1.0", "terms_accepted": True, "health_data_consent": True})
    assert consent.status_code == 200, consent.text


def test_reset_prevents_old_local_user_recovery(isolated):
    client, db = isolated
    assert reset(client).status_code == 200
    server.LOCAL_USERS["reset-qa"] = patient("reset-qa")
    assert server._local_only_account_fields(db.users.docs[0], server.LOCAL_USERS["reset-qa"]) == {}
    response = client.get("/api/users/me", headers={"X-User-Id": "reset-qa"})
    assert response.status_code == 200 and not response.json()["onboarding_complete"]


def test_therapist_cannot_reset(isolated):
    client, db = isolated
    db.users.docs[0]["role"] = "therapist"
    assert reset(client).status_code == 403
    assert len(db.assessments.docs) == 2


def test_preserves_paid_entitlements(isolated):
    client, db = isolated
    db.users.docs[0].update(credits=400, subscription_active=True, subscription_id="paid", subscription_period_end="2027-01-01")
    assert reset(client).status_code == 200
    assert db.users.docs[0]["credits"] == 400 and db.users.docs[0]["subscription_id"] == "paid"
    assert db.users.docs[0]["subscription_period_end"] == "2027-01-01"


def test_fresh_trial_can_run_assessment_even_after_spending_old_credits(isolated):
    client, db = isolated
    db.users.docs[0]["credits"] = 0
    assert reset(client).status_code == 200
    assert db.users.docs[0]["credits"] == 100


def test_video_cleanup_is_scoped_to_owned_blobs(isolated, monkeypatch):
    client, db = isolated
    db.task_video_objects.docs = [
        {"id": "mine", "user_id": "reset-qa", "object_key": "qa/mine"},
        {"id": "other", "user_id": "other-qa", "object_key": "qa/other"},
    ]
    deleted = []
    monkeypatch.setattr(server.task_video_object_storage, "delete", deleted.append)
    assert reset(client).status_code == 200
    assert deleted == ["qa/mine"]
    assert db.task_video_objects.docs == [{"id": "other", "user_id": "other-qa", "object_key": "qa/other"}]


def test_sign_in_after_reset_keeps_same_identity_and_requires_setup(isolated, monkeypatch):
    client, db = isolated
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "test-reset-code")
    db.users.docs[0]["email"] = "reset-qa@example.com"
    assert reset(client).status_code == 200
    response = client.post("/api/users/login", json={"email": "reset-qa@example.com", "name": "Reset QA", "trial_code": "test-reset-code"})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == "reset-qa"
    assert response.json()["consent_required"] and not response.json()["onboarding_complete"]


def test_pre_reset_background_account_update_cannot_restore_marker(isolated):
    client, db = isolated
    old = copy.deepcopy(db.users.docs[0])
    assert reset(client).status_code == 200
    with pytest.raises(server.HTTPException) as error:
        asyncio.run(server._save_user_fields(old, {"initial_assessment_completed_at": "old"}))
    assert error.value.status_code == 409
    assert db.users.docs[0]["initial_assessment_completed_at"] is None


def test_assessment_fetch_and_video_fallback_carry_reset_generation():
    from pathlib import Path
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert 'const ACCOUNT_GENERATION = URL_PARAMS.get("account_generation") || "0";' in source
    assert 'request.setRequestHeader("X-Account-Generation", ACCOUNT_GENERATION);' in source
    assert 'headers:{"Content-Type":"application/json", ...ACCOUNT_HEADERS}' in source
