"""Terms acceptance and the initial survey are stored on the MongoDB account.

A new account is asked to accept the Terms and complete the survey once; a
returning account signs in with both already recorded, so neither is shown
again - even after a backend restart or on a different device.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_account_state_test")

from backend import server


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class MemoryUsers:
    """Minimal in-memory stand-in for the MongoDB `users` collection."""

    def __init__(self, *documents):
        self.documents = [dict(document) for document in documents]
        self.calls = []

    def _match(self, query):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                return document
        return None

    async def find_one(self, query, projection=None):
        document = self._match(query)
        return dict(document) if document else None

    async def update_one(self, query, update, upsert=False):
        self.calls.append((query, update, upsert))
        document = self._match(query)
        if document is None:
            if not upsert:
                return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)
            document = dict(query)
            document.update(update.get("$setOnInsert", {}))
            self.documents.append(document)
        for key, value in update.get("$set", {}).items():
            document[key] = value
        for key, value in update.get("$push", {}).items():
            document.setdefault(key, []).append(value)
        return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)

    async def create_index(self, *_args, **_kwargs):
        return None


class UnavailableUsers:
    async def find_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def update_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def insert_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")


def _isolate_local_state(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOCAL_USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(server, "LOCAL_USERS", {})
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "test-trial-code")


def _login(client, email="Returning@Example.com", name="Returning Patient"):
    return client.post(
        "/api/users/login",
        json={"email": email, "name": name, "role": "patient", "trial_code": "test-trial-code"},
    )


def test_new_account_must_accept_terms_and_complete_survey_once(monkeypatch, tmp_path):
    _isolate_local_state(monkeypatch, tmp_path)
    users = MemoryUsers()
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))

    with TestClient(server.app) as client:
        first = _login(client).json()
        assert first["is_new_account"] is True
        assert first["consent_accepted"] is False
        assert first["consent_required"] is True
        assert first["onboarding_complete"] is False

        headers = {"X-User-Id": first["id"]}
        accepted = client.post(
            "/api/users/consent",
            headers=headers,
            json={"terms_version": server.CURRENT_TERMS_VERSION, "terms_accepted": True, "health_data_consent": True},
        )
        assert accepted.status_code == 200
        survey = client.post(
            "/api/users/onboarding",
            headers=headers,
            json={"preferred_name": "Ret", "side_affected": "left", "age_band": "60-69"},
        )
        assert survey.status_code == 200
        assert survey.json()["onboarding_complete"] is True

        # The account document in MongoDB now carries both records.
        stored = users._match({"id": first["id"]})
        assert stored["consent"]["terms_accepted"] is True
        assert stored["consent"]["health_data_consent"] is True
        assert stored["onboarding_complete"] is True
        assert stored["profile"]["preferred_name"] == "Ret"

        # Signing in again (new device, cleared storage, backend restart) skips both.
        again = _login(client, email="returning@example.com").json()
        assert again["id"] == first["id"]
        assert again["is_new_account"] is False
        assert again["consent_accepted"] is True
        assert again["consent_required"] is False
        assert again["onboarding_complete"] is True
        assert again["profile"]["preferred_name"] == "Ret"


def test_returning_account_survives_backend_restart_with_empty_local_state(monkeypatch, tmp_path):
    _isolate_local_state(monkeypatch, tmp_path)
    users = MemoryUsers({
        "id": "u_restart",
        "email": "restart@example.com",
        "name": "Restart",
        "role": "patient",
        "credits": 100,
        "trial_access_granted": True,
        "consent": {
            "terms_version": server.CURRENT_TERMS_VERSION,
            "terms_accepted": True,
            "health_data_consent": True,
            "accepted_at": "2026-08-01T10:00:00+00:00",
        },
        "onboarding_complete": True,
        "profile": {"preferred_name": "Res", "side_affected": "right"},
    })
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))

    with TestClient(server.app) as client:
        login = _login(client, email="restart@example.com", name="Restart").json()
        assert login["is_new_account"] is False
        assert login["consent_accepted"] is True
        assert login["onboarding_complete"] is True

        headers = {"X-User-Id": "u_restart"}
        assert client.get("/api/users/consent", headers=headers).json()["accepted"] is True
        onboarding = client.get("/api/users/onboarding", headers=headers).json()
        assert onboarding["onboarding_complete"] is True
        assert onboarding["profile"]["preferred_name"] == "Res"

        # Accepting again must not overwrite the original acceptance record.
        repeat = client.post(
            "/api/users/consent",
            headers=headers,
            json={"terms_version": server.CURRENT_TERMS_VERSION, "terms_accepted": True, "health_data_consent": True},
        ).json()
        assert repeat["already_accepted"] is True
        assert users._match({"id": "u_restart"})["consent"]["accepted_at"] == "2026-08-01T10:00:00+00:00"


def test_state_saved_during_a_mongo_outage_is_promoted_when_mongo_returns(monkeypatch, tmp_path):
    _isolate_local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "db", SimpleNamespace(users=UnavailableUsers()))

    with TestClient(server.app) as client:
        offline = _login(client, email="outage@example.com", name="Outage").json()
        headers = {"X-User-Id": offline["id"]}
        assert client.post(
            "/api/users/consent",
            headers=headers,
            json={"terms_version": server.CURRENT_TERMS_VERSION, "terms_accepted": True, "health_data_consent": True},
        ).status_code == 200
        assert client.post(
            "/api/users/onboarding", headers=headers, json={"preferred_name": "Out", "side_affected": "left"},
        ).status_code == 200

    # Mongo is reachable again but knows nothing about the account.
    users = MemoryUsers()
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))
    with TestClient(server.app) as client:
        online = _login(client, email="outage@example.com", name="Outage").json()
        assert online["id"] == offline["id"]
        assert online["consent_accepted"] is True
        assert online["onboarding_complete"] is True

    promoted = users._match({"id": offline["id"]})
    assert promoted["email"] == "outage@example.com"
    assert promoted["consent"]["terms_accepted"] is True
    assert promoted["profile"]["preferred_name"] == "Out"


def test_account_writes_create_the_mongo_document_when_it_is_missing(monkeypatch, tmp_path):
    _isolate_local_state(monkeypatch, tmp_path)
    users = MemoryUsers()
    monkeypatch.setattr(server, "db", SimpleNamespace(users=users))
    local_only = {"id": "u_local_only", "email": "local@example.com", "name": "Local", "role": "patient", "credits": 100}

    merged = asyncio.run(server._save_user_fields(local_only, {"onboarding_complete": True, "profile": {"preferred_name": "L"}}))

    assert merged["onboarding_complete"] is True
    created = users._match({"id": "u_local_only"})
    assert created["email"] == "local@example.com"
    assert created["onboarding_complete"] is True
    assert server.LOCAL_USERS["u_local_only"]["profile"] == {"preferred_name": "L"}
    assert users.calls[-1][2] is True  # upserted after the plain update matched nothing


def test_unauthenticated_onboarding_lookup_is_not_reported_as_incomplete(monkeypatch, tmp_path):
    _isolate_local_state(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "db", SimpleNamespace(users=MemoryUsers()))

    with TestClient(server.app) as client:
        assert client.get("/api/users/onboarding").status_code == 401
        assert client.get("/api/users/onboarding", headers={"X-User-Id": "u_unknown"}).status_code == 401


def test_hosted_mongo_gets_a_realistic_connection_timeout():
    assert server._mongo_timeout_ms("MONGO_SERVER_SELECTION_TIMEOUT_MS", 10000) == 10000
    assert server._MONGO_IS_LOCAL is True  # test URL points at 127.0.0.1
    assert server.MONGO_SERVER_SELECTION_TIMEOUT_MS == 1000


def test_frontend_routes_returning_accounts_straight_in():
    auth = read("frontend/src/auth.ts")
    sign_in = read("frontend/app/sign-in.tsx")
    layout = read("frontend/app/_layout.tsx")

    # Sign-in seeds the device from the account record stored in MongoDB.
    assert "await hydrateAccountStateFromServer(u);" in auth
    assert "consent_accepted?: boolean;" in auth
    assert "onboarding_complete?: boolean;" in auth
    # A server hiccup never sends an existing patient back to the Terms.
    assert "if (!response.ok) return locallyAccepted;" in auth
    # Returning accounts skip the Terms and the survey using the sign-in payload.
    assert "if (user.consent_accepted !== true) {" in sign_in
    assert "if (user.onboarding_complete === true) {" in sign_in
    # A failed onboarding lookup keeps the current screen instead of restarting the survey.
    assert "if (r.ok) {" in layout
    assert 'if (consentOk && seg0 === "consent")' in layout
