import asyncio
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_account_resume_test")

from backend import server


class UnavailableUsers:
    async def find_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def insert_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")


class UnavailableProgressQuery:
    async def to_list(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")


class UnavailableProgress:
    async def delete_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def update_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def delete_many(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    async def insert_one(self, *_args, **_kwargs):
        raise RuntimeError("Mongo unavailable")

    def find(self, *_args, **_kwargs):
        return UnavailableProgressQuery()


def test_local_account_survives_backend_restart_and_keeps_onboarding(monkeypatch, tmp_path):
    users_file = tmp_path / "users.json"
    monkeypatch.setattr(server, "db", SimpleNamespace(users=UnavailableUsers()))
    monkeypatch.setattr(server, "LOCAL_USERS_FILE", users_file)
    monkeypatch.setattr(server, "LOCAL_USERS", {})

    first = asyncio.run(server.get_or_create_user(" Patient@Example.com ", "Patient"))
    first["onboarding_complete"] = True
    first["profile"] = {"preferred_name": "Pat", "side_affected": "left"}
    server.LOCAL_USERS[first["id"]] = first
    server._persist_local_dict(users_file, server.LOCAL_USERS)

    monkeypatch.setattr(server, "LOCAL_USERS", server._load_local_dict(users_file))
    second = asyncio.run(server.get_or_create_user("patient@example.com", "Patient"))

    assert second["id"] == first["id"]
    assert second["onboarding_complete"] is True
    assert second["profile"]["side_affected"] == "left"


def test_task_progress_is_account_scoped_and_can_be_reset(monkeypatch, tmp_path):
    async def signed_in_user(*_args, **_kwargs):
        return {"id": "u_resume_test", "name": "Resume Test"}

    progress_file = tmp_path / "task_progress.json"
    monkeypatch.setattr(server, "_task_video_user", signed_in_user)
    monkeypatch.setattr(server, "db", SimpleNamespace(assessment_task_progress=UnavailableProgress()))
    monkeypatch.setattr(server, "LOCAL_TASK_PROGRESS_FILE", progress_file)
    monkeypatch.setattr(server, "LOCAL_TASK_PROGRESS", {})

    client = TestClient(server.app)
    saved = client.post("/api/assessment/task-progress?package_id=initial&task_id=T1")
    assert saved.status_code == 200

    progress = client.get("/api/assessment/task-progress?package=initial").json()
    assert progress["completed_task_ids"] == ["T1"]

    reset = client.delete("/api/assessment/task-progress?package=initial")
    assert reset.status_code == 200
    progress_after_reset = client.get("/api/assessment/task-progress?package=initial").json()
    assert progress_after_reset["completed_task_ids"] == []


def test_frontend_resume_state_is_scoped_to_the_signed_in_account():
    auth = (server.ROOT_DIR.parent / "frontend" / "src" / "auth.ts").read_text(encoding="utf-8")
    sign_in = (server.ROOT_DIR.parent / "frontend" / "app" / "sign-in.tsx").read_text(encoding="utf-8")
    intro = (server.ROOT_DIR.parent / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")
    assessment = (server.ROOT_DIR.parent / "frontend" / "app" / "assessment.tsx").read_text(encoding="utf-8")

    assert "onboarding_complete_v2:${userId}" in auth
    assert "patient_profile_v2:${userId}" in auth
    assert "assessment_completed_tasks_v2:${userId}:${packageId}" in auth
    assert 'authedFetch("/api/users/onboarding", {' in sign_in
    assert "JSON.stringify(cachedProfile)" in sign_in
    assert "fetchTaskProgress(packageId)" in intro
    assert "serverProgressResult.available ? serverCompleted : deviceCompleted" in intro
    assert "progress_source: serverProgressResult.available ? \"server\" : \"device_fallback\"" in intro
    assert "ignored_device_completed_task_ids: ignoredDeviceCompletedTaskIds" in intro
    assert 'testID="task-intro-start-over"' in intro
    assert 'query.set("completed_tasks", completedTasksParam)' in assessment
