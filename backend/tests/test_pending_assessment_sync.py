import asyncio
import os
from types import SimpleNamespace

from pymongo.errors import ConnectionFailure

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "rehyn_pending_assessment_test")

from backend import server


def _pending_doc():
    return {
        "id": "assessment-pending-1",
        "user_id": "patient-1",
        "created_at": "2026-09-08T17:02:40+00:00",
        "assessment_trigger": "initial",
        "functional_issue_report_id": None,
        "task_results": [{"task_id": "L6"}],
        "persistence_status": server.PENDING_ASSESSMENT_SYNC_STATUS,
        "pending_mongodb_sync": {
            "queued_at": "2026-09-08T17:02:46+00:00",
            "attempts": 0,
            "account_generation": 4,
        },
    }


def test_failed_assessment_is_queued_locally_without_duplicate_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "LOCAL_ASSESSMENTS", [])
    monkeypatch.setattr(server, "LOCAL_ASSESSMENTS_FILE", tmp_path / "assessments.json")
    user = {"id": "patient-1", "account_generation": 4}
    doc = {"id": "assessment-pending-1", "user_id": "patient-1", "task_results": []}

    server._queue_assessment_for_mongodb_sync(doc, user, ConnectionFailure("Atlas timed out"))
    server._queue_assessment_for_mongodb_sync(doc, user, ConnectionFailure("Atlas timed out again"))

    assert len(server.LOCAL_ASSESSMENTS) == 1
    queued = server.LOCAL_ASSESSMENTS[0]
    assert queued["persistence_status"] == server.PENDING_ASSESSMENT_SYNC_STATUS
    assert queued["pending_mongodb_sync"]["account_generation"] == 4
    assert (tmp_path / "assessments.json").exists()


def test_pending_assessment_syncs_to_mongodb_and_restores_initial_marker(monkeypatch):
    assessment_writes = []
    user_updates = []

    class Users:
        async def find_one(self, *_args, **_kwargs):
            return {"id": "patient-1", "account_generation": 4}

        async def update_one(self, query, update):
            user_updates.append((query, update))

    class Assessments:
        async def replace_one(self, query, document, *, upsert):
            assessment_writes.append((query, document, upsert))

    class Reports:
        async def update_one(self, *_args, **_kwargs):
            raise AssertionError("No issue report should be updated")

    monkeypatch.setattr(server, "LOCAL_ASSESSMENTS", [_pending_doc()])
    monkeypatch.setattr(server, "db", SimpleNamespace(
        users=Users(),
        assessments=Assessments(),
        alira_functional_issue_reports=Reports(),
    ))
    monkeypatch.setattr(server, "_persist_local_list", lambda *_args: None)

    synced = asyncio.run(server._sync_pending_assessments_to_mongodb())

    assert synced == 1
    assert len(assessment_writes) == 1
    assert assessment_writes[0][0] == {"id": "assessment-pending-1", "user_id": "patient-1"}
    assert assessment_writes[0][2] is True
    assert "pending_mongodb_sync" not in assessment_writes[0][1]
    assert user_updates[0][1]["$min"]["initial_assessment_completed_at"] == "2026-09-08T17:02:40+00:00"
    assert server.LOCAL_ASSESSMENTS[0]["persistence_status"] == "mongodb"


def test_signed_in_user_uses_local_mirror_during_atlas_timeout(monkeypatch):
    class Users:
        async def find_one(self, *_args, **_kwargs):
            raise ConnectionFailure("Atlas timed out")

    local_user = {"id": "patient-1", "email": "patient@example.com", "account_generation": 4}
    monkeypatch.setattr(server, "LOCAL_USERS", {"patient-1": local_user})
    monkeypatch.setattr(server, "db", SimpleNamespace(users=Users()))

    result = asyncio.run(server._user_from_header({"x-user-id": "patient-1"}))

    assert result == local_user
    assert result is not local_user
