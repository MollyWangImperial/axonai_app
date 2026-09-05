import asyncio
import os
import sys
import types
from pathlib import Path

from starlette.requests import Request


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_testing_shortcut_test")

if "emergentintegrations.llm.chat" not in sys.modules:
    emergent = types.ModuleType("emergentintegrations")
    llm = types.ModuleType("emergentintegrations.llm")
    chat = types.ModuleType("emergentintegrations.llm.chat")

    class _UnavailableChatDependency:
        def __init__(self, *args, **kwargs):
            pass

    chat.LlmChat = _UnavailableChatDependency
    chat.UserMessage = _UnavailableChatDependency
    sys.modules.setdefault("emergentintegrations", emergent)
    sys.modules.setdefault("emergentintegrations.llm", llm)
    sys.modules.setdefault("emergentintegrations.llm.chat", chat)

from backend import server


class _AssessmentCollection:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, doc):
        self.inserted.append(doc)
        return types.SimpleNamespace(inserted_id="sample-assessment")


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/assessment/complete-for-testing", "headers": []})


def test_generated_testing_results_cover_the_complete_initial_package():
    task_ids = [task["id"] for task in server.ASSESSMENT_PACKAGES["initial"]["tasks"]]
    results, variant = server._generated_testing_sample_task_results(task_ids)

    assert variant in {"steady", "building_hand_control", "building_walking_control", "building_reach_control"}
    assert [result.task_id for result in results] == task_ids
    assert all(result.completed_steps == result.total_steps > 0 for result in results)
    assert all(result.metrics["generated_testing_sample"] is True for result in results)
    assert next(result for result in results if result.task_id == "H1").metrics["hand_open_score"] > 0
    assert next(result for result in results if result.task_id == "L6").metrics["gait_bilateral_motion_symmetry"] > 0


def test_testing_shortcut_persists_sample_and_does_not_charge_credits(monkeypatch):
    collection = _AssessmentCollection()
    completed = []

    async def signed_in_user(_headers):
        return {
            "id": "testing-patient",
            "email": "testing@example.com",
            "consent": {"health_data_consent": True},
            "profile": {
                "side_affected": "left",
                "movement_pain": "mild",
                "patient_priorities": ["Eating and dressing"],
            },
        }

    async def no_assessments(_user_id):
        return []

    async def record_completion(user, created_at, **_kwargs):
        completed.append((user["id"], created_at))
        return created_at

    async def mark_issue(*_args, **_kwargs):
        return None

    async def unexpected_credit_charge(*_args, **_kwargs):
        raise AssertionError("The testing shortcut must not consume patient credits")

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "_care_assessments_for_user", no_assessments)
    monkeypatch.setattr(server, "_record_initial_assessment_completion", record_completion)
    monkeypatch.setattr(server, "_mark_functional_issue_assessed", mark_issue)
    monkeypatch.setattr(server, "consume_credits", unexpected_credit_charge)
    monkeypatch.setattr(server, "_record_alira_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "db", types.SimpleNamespace(assessments=collection))

    assessment = asyncio.run(server.complete_initial_assessment_for_testing(_request()))

    assert assessment.testing_shortcut is True
    assert assessment.result_provenance == "generated_testing_sample"
    assert assessment.affected_side == "left"
    assert assessment.assessment_package == "initial"
    assert [exercise.id for exercise in assessment.rehab_plan] == [
        "ex_trunk", "ex_reach", "ex_grasp", "ex_h2m",
    ]
    assert assessment.clinical_review_gate["rehab_access"] == "allowed"
    assert completed and completed[0][0] == "testing-patient"
    assert len(collection.inserted) == 1
    assert collection.inserted[0]["result_provenance"] == "generated_testing_sample"
    assert collection.inserted[0]["patient_insights"]["badge"] == "Generated sample"


def test_testing_shortcut_reopens_existing_result_and_repairs_account_marker(monkeypatch):
    existing = server.Assessment(
        id="saved-assessment",
        created_at="2026-08-30T09:00:00+00:00",
        affected_side="right",
        assessment_package="initial",
        assigned_task_ids=["T1"],
        task_results=[server.TaskResult(task_id="T1", completed_steps=1, total_steps=1)],
        functional_issues=[],
        rehab_plan=server.fixed_core_rehab_plan({}),
    )
    recorded = []

    async def signed_in_user(_headers):
        return {
            "id": "returning-patient",
            "consent": {"health_data_consent": True},
            "profile": {},
        }

    async def saved_assessments(_user_id):
        return [existing.model_dump()]

    async def record_completion(user, created_at, **kwargs):
        recorded.append((user["id"], created_at, kwargs.get("source")))
        return created_at

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "_care_assessments_for_user", saved_assessments)
    monkeypatch.setattr(server, "_record_initial_assessment_completion", record_completion)
    monkeypatch.setattr(server, "_record_alira_action", lambda *_args, **_kwargs: None)

    assessment = asyncio.run(server.complete_initial_assessment_for_testing(_request()))

    assert assessment.id == "saved-assessment"
    assert assessment.testing_shortcut is False
    assert recorded == [(
        "returning-patient",
        "2026-08-30T09:00:00+00:00",
        "testing_shortcut_existing_history",
    )]


def test_frontend_exposes_shortcut_and_labels_generated_results():
    root = Path(__file__).resolve().parents[2]
    session_check = (root / "frontend" / "app" / "session-check.tsx").read_text(encoding="utf-8")
    results = (root / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")

    assert 'testID="session-finish-sample-assessment"' in session_check
    assert "completeInitialAssessmentForTesting" in session_check
    assert "Skip assessment and open rehab plan" in session_check
    assert "ScrollView" in session_check
    assert session_check.index('testID="session-finish-sample-assessment"') < session_check.index('testID="session-actor-patient"')
    assert "No camera movements were measured" in results
    assert 'pathname: "/rehab-plan"' in session_check
    assert 'entry: "assessment_complete"' in session_check
