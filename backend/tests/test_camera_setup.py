import os

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "camera_setup_test")

from backend import server


def test_camera_devices_persist_with_existing_profile(monkeypatch):
    user = {"id": "camera-test", "profile": {"preferred_name": "Test", "affected_areas": ["left_upper"]}}

    async def current_user(*_args, **_kwargs):
        return user

    async def save_user(_user, fields, **_kwargs):
        user.update(fields)

    monkeypatch.setattr(server, "_user_from_header", current_user)
    monkeypatch.setattr(server, "_save_user_fields", save_user)
    client = TestClient(server.app)
    response = client.post("/api/users/onboarding", json={"camera_devices": ["iphone", "laptop", "iphone"]})
    assert response.status_code == 200
    profile = client.get("/api/users/onboarding").json()["profile"]
    assert profile["camera_devices"] == ["iphone", "laptop"]
    assert profile["affected_areas"] == ["left_upper"]
    assert profile["preferred_name"] == "Test"
    client.post("/api/users/onboarding", json={"preferred_name": "Changed"})
    assert user["profile"]["camera_devices"] == ["iphone", "laptop"]


def test_camera_devices_validation_and_no_camera(monkeypatch):
    async def current_user(*_args, **_kwargs):
        return {"id": "camera-test", "profile": {}}

    async def save_user(*_args, **_kwargs):
        pass

    monkeypatch.setattr(server, "_user_from_header", current_user)
    monkeypatch.setattr(server, "_save_user_fields", save_user)
    client = TestClient(server.app)
    assert client.post("/api/users/onboarding", json={"camera_devices": ["unknown"]}).status_code == 422
    assert client.post("/api/users/onboarding", json={"camera_devices": ["none", "iphone"]}).status_code == 422
    assert client.post("/api/users/onboarding", json={"camera_devices": ["none"]}).json()["profile"]["camera_devices"] == ["none"]


def test_camera_setup_assets_are_served_as_assets():
    client = TestClient(server.app)
    for name, marker in [("index.html", "Open camera check"), ("setup.mjs", "getUserMedia"), ("framing.mjs", "checkFraming"), ("setup.css", "object-fit: cover")]:
        response = client.get(f"/camera-setup/{name}")
        assert response.status_code == 200
        assert marker in response.text
    image = client.get("/camera-setup/iphone-setup.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"


def test_both_live_sessions_require_fresh_camera_setup():
    root = server.ROOT_DIR.parent / "frontend"
    for route in ["assessment", "exercise"]:
        source = (root / "app" / f"{route}.tsx").read_text(encoding="utf-8")
        assert f'<CameraSetup purpose="{route}"' in source
        assert "const [cameraReady, setCameraReady] = useState(false)" in source
        assert "return isFocused ?" in source
        assert "event.persisted" in source
    assert "walking_test !== \"1\"" in (root / "app/assessment.tsx").read_text(encoding="utf-8")
    layout = (root / "app/_layout.tsx").read_text(encoding="utf-8")
    assert "if (accountEpoch === null) return null" in layout
