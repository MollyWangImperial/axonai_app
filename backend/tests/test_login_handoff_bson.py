"""Exercise the sign-in bridge with actual BSON datetime encoding/decoding."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import BSON
from bson.codec_options import CodecOptions
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_handoff_bson_test")

from backend import server


class BsonHandoffs:
    def __init__(self, tz_aware):
        self.records = {}
        self.options = CodecOptions(tz_aware=tz_aware)

    async def insert_one(self, record):
        self.records[record["token_hash"]] = BSON.encode(record)

    async def find_one_and_delete(self, query, projection=None):
        raw = self.records.get(query["token_hash"])
        if raw is None:
            return None
        record = BSON(raw).decode(codec_options=self.options)
        expires_at = record["expires_at"]
        # MongoDB compares UTC instants regardless of the client's decode mode.
        comparable = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if comparable <= query["expires_at"]["$gt"]:
            return None
        self.records.pop(query["token_hash"])
        return record


@pytest.mark.parametrize("tz_aware", [False, True])
def test_public_site_handoff_survives_bson_roundtrip_and_is_single_use(monkeypatch, tz_aware):
    user = {
        "id": "u_bson_handoff",
        "email": "bson@example.com",
        "name": "BSON Test",
        "role": "patient",
        "credits": 100,
        "trial_access_granted": True,
    }
    handoffs = BsonHandoffs(tz_aware)

    async def get_user(query, projection=None):
        return dict(user) if query.get("id") == user["id"] else None

    async def get_or_create(email, name, role="patient"):
        return dict(user)

    async def grant(account):
        return account

    monkeypatch.setattr(server, "db", SimpleNamespace(
        login_handoffs=handoffs, users=SimpleNamespace(find_one=get_user)))
    monkeypatch.setattr(server, "get_or_create_user", get_or_create)
    monkeypatch.setattr(server, "_grant_trial_access", grant)
    monkeypatch.setattr(server, "TRIAL_ACCESS_CHECK_ENABLED", True)
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "bson-test-code")
    monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
    payload = {"email": user["email"], "name": user["name"], "trial_code": "bson-test-code"}

    with TestClient(server.app) as client:
        created = client.post("/api/users/login-handoff", json=payload)
        assert created.status_code == 200
        token = created.json()["handoff_token"]
        completed = client.post("/api/users/login-handoff/complete", json={"token": token})
        assert completed.status_code == 200
        assert completed.json()["id"] == user["id"]
        assert completed.json()["trial_access_granted"] is True
        assert client.post("/api/users/login-handoff/complete", json={"token": token}).status_code == 401

        created = client.post("/api/users/login-handoff", json=payload)
        expired_token = created.json()["handoff_token"]
        digest = server._login_handoff_digest(expired_token)
        expired = BSON(handoffs.records[digest]).decode()
        expired["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        handoffs.records[digest] = BSON.encode(expired)
        assert client.post("/api/users/login-handoff/complete", json={"token": expired_token}).status_code == 401
