"""Independent reads overlap without weakening durable save requirements."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend import server


def care_reads(monkeypatch):
    started = set()
    gate = asyncio.Event()
    records = {
        "_care_assessments_for_user": [{"id": "a1", "created_at": "2026-09-01T12:00:00Z", "rehab_plan": [{"id": "ex_reach", "sets": 3, "reps": 10}]}],
        "_care_check_ins_for_user": [],
        "_care_activities_for_user": [],
        "_care_issue_reports_for_user": [],
    }
    for name, rows in records.items():
        async def read(user_id, name=name, rows=rows):
            assert user_id == "parallel-patient"
            started.add(name)
            if len(started) == len(records):
                gate.set()
            # Sequential readers cannot pass: none finishes until all begin.
            await asyncio.wait_for(gate.wait(), timeout=1)
            return list(rows)
        monkeypatch.setattr(server, name, read)
    return started


USER = {"id": "parallel-patient", "profile": {}, "initial_assessment_completed_at": "2026-09-01T12:00:00Z", "consent": {"health_data_consent": True}}


def test_care_plan_fetches_independent_histories_together(monkeypatch):
    async def run():
        started = care_reads(monkeypatch)
        plan = await server._adaptive_care_plan_for_user(dict(USER))
        assert len(started) == 4
        assert plan["account_state"]["has_completed_initial_assessment"] is True
    asyncio.run(run())


def test_activity_save_still_waits_for_durable_activity_and_review(monkeypatch):
    async def run():
        started = care_reads(monkeypatch)
        activities = SimpleNamespace(find_one=AsyncMock(return_value=None), update_one=AsyncMock())
        reviews = SimpleNamespace(insert_one=AsyncMock())
        monkeypatch.setattr(server, "db", SimpleNamespace(alira_activities=activities, alira_care_reviews=reviews))
        monkeypatch.setattr(server, "_record_alira_action", lambda *_a, **_k: None)
        payload = server.AliraActivitySubmit(client_activity_id="testing:plan:2026-09-10:ex_reach", day="2026-09-10", exercise_id="ex_reach", plan_id="plan", completed_reps=30, repetition_scores=[90] * 30, testing_shortcut=True)
        result = await server._persist_alira_activity(dict(USER), payload)
        assert len(started) == 4
        assert result["ok"] is True
        assert result["activity"]["average_score"] == 90
        activities.update_one.assert_awaited_once()
        reviews.insert_one.assert_awaited_once()

        activities.update_one.side_effect = RuntimeError("save failed")
        monkeypatch.setattr(server, "ALLOW_EPHEMERAL_PATIENT_STATE", False)
        with pytest.raises(server.HTTPException) as error:
            await server._persist_alira_activity(dict(USER), payload)
        assert error.value.status_code == 503
        assert reviews.insert_one.await_count == 1
    asyncio.run(run())


def test_supplied_care_records_are_reused(monkeypatch):
    async def forbidden(_user_id):
        raise AssertionError("supplied records must not be fetched again")
    for name in ["_care_assessments_for_user", "_care_check_ins_for_user", "_care_activities_for_user", "_care_issue_reports_for_user"]:
        monkeypatch.setattr(server, name, forbidden)
    plan = asyncio.run(server._adaptive_care_plan_for_user(dict(USER), assessments=[], check_ins=[], activities=[], issue_reports=[]))
    assert plan["account_state"]["has_completed_initial_assessment"] is True
