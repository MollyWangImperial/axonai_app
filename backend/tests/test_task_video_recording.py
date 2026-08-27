import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_task_video_test")

from backend import server


ROOT = Path(__file__).resolve().parents[2]


def test_pose_runner_records_and_saves_each_completed_task():
    source = server.POSE_RUNNER_HTML
    assert "new MediaRecorder(recordingStream" in source
    assert 'const TASK_VIDEO_DB_NAME = "rehyn-task-videos-v1"' in source
    assert "if(currentStepIdx === 0) beginTaskRecording(task.id);" in source
    assert "stopAndSaveTaskRecording(finishedTask.id);" in source
    assert "/assessment/task-videos?${query.toString()}" in source
    assert "await Promise.allSettled(Array.from(pendingTaskVideoSaves));" in source
    assert 'getUserMedia({video:videoSettings, audio:false})' in source
    assert "window.__rehynStartRequested = true" in source
    assert "if(window.__rehynStartRequested) void beginAssessmentSetup()" in source
    assert "Camera access requires a secure HTTPS connection" in source
    assert "Camera permission request timed out" in source


def test_frontend_tracks_saved_video_events_without_showing_a_task_picker():
    assessment = (ROOT / "frontend/app/assessment.tsx").read_text(encoding="utf-8")
    intro = (ROOT / "frontend/app/task-intro.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert 'msg.type === "task_video_saved"' in assessment
    assert "markTaskVideoSaved" in assessment
    assert "fetchTaskVideos(packageId)" in intro
    assert 'testID="saved-task-video-count"' in intro
    assert "tasks.map(" not in intro
    assert 'authedFetch(`/api/assessment/task-videos?package=' in api
    assert "const serverCompleted = Object.fromEntries(" in intro
    assert "const completed = { ...deviceCompleted, ...serverCompleted }" in intro


def test_task_video_falls_back_to_persistent_local_storage(monkeypatch, tmp_path):
    async def signed_in_user(*_args, **_kwargs):
        return {"id": "u_video_test", "name": "Video Test"}

    class UnavailableBucket:
        async def upload_from_stream(self, *_args, **_kwargs):
            raise RuntimeError("Mongo unavailable")

    monkeypatch.setattr(server, "_task_video_user", signed_in_user)
    monkeypatch.setattr(server, "task_video_bucket", UnavailableBucket())
    monkeypatch.setattr(server, "TASK_VIDEO_FALLBACK_DIR", tmp_path)

    client = TestClient(server.app)
    response = client.post(
        "/api/assessment/task-videos?package_id=initial&task_id=T1&duration_ms=1250",
        content=b"test-video-bytes",
        headers={"Content-Type": "video/webm", "X-User-Id": "u_video_test"},
    )

    assert response.status_code == 200
    record = response.json()
    assert record["storage"] == "local"
    assert record["task_id"] == "T1"
    assert record["duration_ms"] == 1250
    assert (tmp_path / f"{record['id']}.bin").read_bytes() == b"test-video-bytes"

    playback = client.get(
        f"/api/assessment/task-videos/file/{record['id']}?uid=u_video_test"
    )
    assert playback.status_code == 200
    assert playback.headers["content-type"].startswith("video/webm")
    assert playback.content == b"test-video-bytes"


def test_task_video_rejects_non_video_payload(monkeypatch):
    async def signed_in_user(*_args, **_kwargs):
        return {"id": "u_video_test", "name": "Video Test"}

    monkeypatch.setattr(server, "_task_video_user", signed_in_user)
    client = TestClient(server.app)
    response = client.post(
        "/api/assessment/task-videos?package_id=initial&task_id=T1",
        content=b"not-a-video",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 415
