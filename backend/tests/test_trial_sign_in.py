import os

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
