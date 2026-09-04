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


def test_local_assessment_fallback_survives_backend_restart(tmp_path):
    assessments_file = tmp_path / "assessments.json"
    records = [{
        "id": "assessment_resume_test",
        "user_id": "u_resume_test",
        "assessment_package": "initial",
        "created_at": "2026-09-02T09:30:00+00:00",
    }]

    server._persist_local_list(assessments_file, records)

    assert server._load_local_list(assessments_file) == records


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
    assert "patient_activity_v1:${userId}" in auth
    assert "cacheDailyCheckInActivity" in auth
    assert "cacheAssessmentActivity" in auth
    assert 'authedFetch("/api/users/onboarding", {' in sign_in
    assert "JSON.stringify(cachedProfile)" in sign_in
    assert "fetchTaskProgress(packageId)" in intro
    assert "serverProgressResult.available ? serverCompleted : deviceCompleted" in intro
    assert "progress_source: serverProgressResult.available ? \"server\" : \"device_fallback\"" in intro
    assert "ignored_device_completed_task_ids: ignoredDeviceCompletedTaskIds" in intro
    assert 'testID="task-intro-start-over"' in intro
    assert 'query.set("completed_tasks", completedTasksParam)' in assessment
    assert "cacheAssessmentActivity(" in assessment


def test_home_restores_account_activity_before_deciding_the_next_step():
    home = (server.ROOT_DIR.parent / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")

    session_restore = 'await authedFetch("/api/users/consent")'
    history_load = "const [assessments, preferredName, initialTaskCache, initialCarePlanPayload"
    assert home.index(session_restore) < home.index(history_load)
    assert "getCachedPatientActivity(user.id)" in home
    assert "cachedActivity.daily_check_ins?.[requestedDate]" in home
    assert "|| initialAssessmentCompletedAt" in home
    assert 'primaryTitle = isInitialAssessment' in home
    assert 'activeExerciseIds.length\n        ? "Today\'s exercises"' in home
    assert "fetchHistory().catch(() => null)" in home
    assert "A 5xx/database outage is unknown state" in home
    assert 'testID="home-account-state-unavailable"' in home
    assert "Nothing has been reset" in home


def test_sign_in_hydrates_the_initial_assessment_marker_from_the_account():
    auth = (server.ROOT_DIR.parent / "frontend" / "src" / "auth.ts").read_text(encoding="utf-8")
    api = (server.ROOT_DIR.parent / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "initial_assessment_completed_at?: string | null;" in auth
    assert "await cacheInitialAssessmentCompletion(user.id, user.initial_assessment_completed_at);" in auth
    assert 'body?.detail || "Could not load assessment history"' in api


def test_completed_legacy_task_ledger_recovers_initial_assessment_account_state(monkeypatch):
    user = {
        "id": "u_legacy_resume",
        "name": "Legacy Resume",
        "consent": {"health_data_consent": True},
        "profile": {
            "sitting_ability": "independent",
            "affected_arm_movement": "some_movement",
            "affected_hand_movement": "some_finger_movement",
            "mobility_level": "not_cleared",
            "movement_pain": "mild",
            "instruction_support": "independent",
            "arm_activity_difficulties": ["reaching_forward"],
            "hand_activity_difficulties": ["opening_hand"],
        },
    }

    async def signed_in_user(_headers):
        return user

    async def no_assessments(_user_id):
        return []

    async def no_server_progress(_user_id):
        return [], None

    async def record_completion(record_user, completed_at, *, source="assessment_submission"):
        record_user["initial_assessment_completed_at"] = completed_at
        record_user["initial_assessment_completion_source"] = source
        return completed_at

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "_care_assessments_for_user", no_assessments)
    monkeypatch.setattr(server, "_initial_task_progress_evidence", no_server_progress)
    monkeypatch.setattr(server, "_record_initial_assessment_completion", record_completion)

    expected = server.initial_assessment_recommendation(user["profile"])["task_ids"]
    with TestClient(server.app) as client:
        recovered = client.post(
            "/api/users/activity/recover-initial-assessment",
            json={"completed_task_ids": expected},
        )
        assert recovered.status_code == 200
        payload = recovered.json()
        assert payload["care_plan"]["account_state"]["has_completed_initial_assessment"] is True
        assert payload["care_plan"]["daily_monitoring"]["active_exercise_ids"]
        assert user["initial_assessment_completion_source"] == "device_task_progress_recovery"

        current_plan = client.get("/api/rehab/current-plan")
        assert current_plan.status_code == 200
        assert current_plan.json()["id"] == "account-current-plan"
        assert current_plan.json()["rehab_plan"]
        assert current_plan.json()["task_results"] == []


def test_incomplete_legacy_task_ledger_does_not_skip_initial_assessment(monkeypatch):
    user = {
        "id": "u_incomplete_resume",
        "consent": {"health_data_consent": True},
        "profile": {
            "sitting_ability": "independent",
            "affected_arm_movement": "some_movement",
            "affected_hand_movement": "some_finger_movement",
            "mobility_level": "not_cleared",
            "movement_pain": "mild",
            "instruction_support": "independent",
        },
    }

    async def signed_in_user(_headers):
        return user

    async def no_assessments(_user_id):
        return []

    async def no_server_progress(_user_id):
        return [], None

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "_care_assessments_for_user", no_assessments)
    monkeypatch.setattr(server, "_initial_task_progress_evidence", no_server_progress)

    expected = server.initial_assessment_recommendation(user["profile"])["task_ids"]
    with TestClient(server.app) as client:
        response = client.post(
            "/api/users/activity/recover-initial-assessment",
            json={"completed_task_ids": expected[:-1]},
        )
    assert response.status_code == 409


def test_frontend_recovers_legacy_account_identity_and_completed_task_state():
    auth = (server.ROOT_DIR.parent / "frontend" / "src" / "auth.ts").read_text(encoding="utf-8")
    home = (server.ROOT_DIR.parent / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    rehab = (server.ROOT_DIR.parent / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert 'storage.getItem("active_user_obj_v1", "")' in auth
    assert "patientActivityKey(previousUserId), patientActivityKey(nextUserId)" in auth
    assert "legacy.id !== userId" in auth
    assert 'completedTaskIdsFromCache(initialTaskCache || "")' in home
    assert 'authedFetch("/api/users/activity/recover-initial-assessment"' in home
    assert 'id: CURRENT_ACCOUNT_PLAN_ID' in home
    assert 'authedFetch("/api/rehab/current-plan")' in rehab
