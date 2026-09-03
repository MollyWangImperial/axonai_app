import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_trial_sign_in_test")

from backend import server


def test_login_rejects_missing_or_incorrect_trial_code(monkeypatch):
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "test-trial-code")

    with TestClient(server.app) as client:
        missing = client.post("/api/users/login", json={
            "email": "trial@example.com",
            "name": "Trial Patient",
            "role": "patient",
        })
        incorrect = client.post("/api/users/login", json={
            "email": "trial@example.com",
            "name": "Trial Patient",
            "role": "patient",
            "trial_code": "incorrect",
        })

    assert missing.status_code == 403
    assert incorrect.status_code == 403
    assert missing.json()["detail"] == "The trial code is not valid."


def test_login_and_signup_grant_access_only_after_valid_code(monkeypatch):
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "test-trial-code")

    async def fake_get_or_create_user(email, name, role="patient"):
        return {
            "id": "u_trial_test",
            "email": email.strip().lower(),
            "name": name,
            "role": role,
            "credits": 100,
        }

    async def fake_grant_trial_access(user):
        return {**user, "trial_access_granted": True, "trial_access_granted_at": "2026-09-02T12:00:00+00:00"}

    monkeypatch.setattr(server, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(server, "_grant_trial_access", fake_grant_trial_access)
    payload = {
        "email": "Trial@Example.com",
        "name": "Trial Patient",
        "role": "patient",
        "trial_code": "test-trial-code",
    }

    with TestClient(server.app) as client:
        login = client.post("/api/users/login", json=payload)
        signup = client.post("/api/users/signup", json=payload)

    assert login.status_code == 200
    assert signup.status_code == 200
    assert login.json()["trial_access_granted"] is True
    assert signup.json()["trial_access_granted"] is True


def test_trial_code_is_not_bundled_into_the_frontend():
    frontend_root = server.ROOT_DIR.parent / "frontend"
    auth = (frontend_root / "src" / "auth.ts").read_text(encoding="utf-8")
    sign_in = (frontend_root / "app" / "sign-in.tsx").read_text(encoding="utf-8")

    assert "REHYN_TRIAL_ACCESS_CODE" not in auth
    assert "REHYN_TRIAL_ACCESS_CODE" not in sign_in
    assert "trial_code: accessCode" in auth
    assert 'testID="signin-trial-code"' in sign_in


def test_sign_in_page_matches_the_selected_welcome_flow():
    source = (server.ROOT_DIR.parent / "frontend" / "app" / "sign-in.tsx").read_text(encoding="utf-8")

    assert "Recovery at home that" in source
    assert "feels clearer." in source
    assert "From uncertainty to" in source
    assert 'testID="signin-start-free"' in source
    assert 'testID="signin-start-assessment"' not in source
    assert "Good morning, Molly" not in source
    assert "PULSE NETWORK" not in source
    assert 'testID="signin-progress-preview"' in source
    assert "Continue with Google" not in source


def test_external_sign_in_link_can_open_the_trial_form_directly():
    source = (server.ROOT_DIR.parent / "frontend" / "app" / "sign-in.tsx").read_text(encoding="utf-8")

    assert "useLocalSearchParams" in source
    assert 'requestedAuth === "signin" || requestedAuth === "start" ? "auth" : null' in source
    assert 'requestedAuth === "signin" ? "signin" : "start"' in source


def test_landing_page_handoff_is_short_lived_and_single_use(monkeypatch):
    monkeypatch.setattr(server, "REHYN_TRIAL_ACCESS_CODE", "test-trial-code")

    user = {
        "id": "u_handoff_test",
        "email": "handoff@example.com",
        "name": "Handoff Patient",
        "role": "patient",
        "credits": 100,
        "trial_access_granted": True,
    }

    async def fake_get_or_create_user(email, name, role="patient"):
        return {**user, "email": email.strip().lower(), "name": name, "role": role}

    async def fake_grant_trial_access(account):
        return {**account, "trial_access_granted": True}

    class FakeHandoffs:
        def __init__(self):
            self.records = {}

        async def insert_one(self, record):
            self.records[record["token_hash"]] = dict(record)
            return SimpleNamespace(inserted_id=record["token_hash"])

        async def find_one_and_delete(self, query, projection=None):
            record = self.records.get(query["token_hash"])
            if not record or record["expires_at"] <= query["expires_at"]["$gt"]:
                return None
            return self.records.pop(query["token_hash"])

    class FakeUsers:
        async def find_one(self, query, projection=None):
            return dict(user) if query.get("id") == user["id"] else None

    handoffs = FakeHandoffs()
    monkeypatch.setattr(server, "db", SimpleNamespace(login_handoffs=handoffs, users=FakeUsers()))
    monkeypatch.setattr(server, "get_or_create_user", fake_get_or_create_user)
    monkeypatch.setattr(server, "_grant_trial_access", fake_grant_trial_access)

    payload = {
        "email": user["email"],
        "name": user["name"],
        "role": "patient",
        "trial_code": "test-trial-code",
    }
    with TestClient(server.app) as client:
        created = client.post("/api/users/login-handoff", json=payload)
        token = created.json()["handoff_token"]
        completed = client.post("/api/users/login-handoff/complete", json={"token": token})
        replayed = client.post("/api/users/login-handoff/complete", json={"token": token})

    assert created.status_code == 200
    assert created.json()["expires_in"] == server.LOGIN_HANDOFF_TTL_SECONDS
    assert token not in handoffs.records
    assert "test-trial-code" not in created.text
    assert completed.status_code == 200
    assert completed.json()["id"] == user["id"]
    assert completed.json()["trial_access_granted"] is True
    assert replayed.status_code == 401


def test_external_handoff_opens_the_app_without_the_old_landing_page():
    auth = (server.ROOT_DIR.parent / "frontend" / "src" / "auth.ts").read_text(encoding="utf-8")
    sign_in = (server.ROOT_DIR.parent / "frontend" / "app" / "sign-in.tsx").read_text(encoding="utf-8")

    assert "completeSignInHandoff" in auth
    assert "requestedHandoff" in sign_in
    assert "Opening Rehyn" in sign_in
