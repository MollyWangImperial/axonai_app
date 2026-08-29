import os
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_step_failure_test")

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


EXPECTED_STEP_COUNTS = {
    "T1": 4,
    "T2": 4,
    "T3": 4,
    "T4": 6,
    "T5": 6,
    "T6": 4,
    "T7": 4,
}


def _task_result_with_failures(task_id: str, failed_step_ids: set[str]):
    task = next(task for task in server.TASKS_DATA if task["id"] == task_id)
    steps = [
        server.TaskStepResult(
            step_id=step["id"],
            completed=step["id"] not in failed_step_ids,
        )
        for step in task["steps"]
    ]
    return server.TaskResult(
        task_id=task_id,
        completed_steps=sum(step.completed for step in steps),
        total_steps=len(steps),
        steps=steps,
        metrics={},
    )


def test_every_upper_limb_step_declares_one_failure_phenotype():
    step_ids = []
    phenotype_codes = []
    for task in server.TASKS_DATA:
        assert len(task["steps"]) == EXPECTED_STEP_COUNTS[task["id"]]
        for step in task["steps"]:
            step_ids.append(step["id"])
            phenotype = step.get("failure_phenotype")
            assert phenotype is not None, step["id"]
            assert {
                "code",
                "domain",
                "label",
                "description",
                "severity",
                "source",
                "rehab_code",
            } <= set(phenotype)
            phenotype_codes.append(phenotype["code"])

    assert len(step_ids) == len(set(step_ids))
    assert len(server.UPPER_LIMB_STEP_PHENOTYPES) == len(step_ids)
    assert set(server.UPPER_LIMB_STEP_PHENOTYPES) == set(step_ids)
    assert all(code for code in phenotype_codes)


def test_each_failed_step_maps_to_its_declared_movement_phenotype():
    for task in server.TASKS_DATA:
        for step in task["steps"]:
            result = _task_result_with_failures(task["id"], {step["id"]})
            issues = server.derive_functional_issues([result])
            localized = [issue for issue in issues if issue.related_step == step["id"]]
            assert len(localized) == 1
            issue = localized[0]
            expected = step["failure_phenotype"]
            assert issue.code == expected["code"]
            assert issue.phenotype_domain == expected["domain"]
            assert issue.related_task == task["id"]


def test_multiple_failed_steps_remain_separate_within_one_task():
    result = _task_result_with_failures("T4", {"T4-S2", "T4-S6"})
    issues = server.derive_functional_issues([result])
    localized = {(issue.related_step, issue.code) for issue in issues if issue.related_step}
    assert localized == {
        ("T4-S2", "GROSS_GRASP"),
        ("T4-S6", "OBJECT_RELEASE_IMPAIRED"),
    }


def test_completed_steps_can_create_compensation_findings_without_range_failures():
    results = [_task_result_with_failures(task["id"], set()) for task in server.TASKS_DATA]
    results[0].metrics = {"trunk_lean_deg": 30}
    results[1].metrics = {"shoulder_hike": True}
    issues = server.derive_functional_issues(results)
    assert {issue.code for issue in issues} == {"TRUNK_COMP", "SHOULDER_HIKE"}
    assert all(issue.related_step is None for issue in issues)


def test_runner_persists_failure_code_from_step_metadata():
    source = server.POSE_RUNNER_HTML
    server_source = Path(server.__file__).read_text(encoding="utf-8")
    assert "failure_code: skipped && step.failure_phenotype ? step.failure_phenotype.code : null" in source
    assert 'step.movement_required === false' in source
    for landmark in [
        'landmark": "HAND_CLOSED"',
        'landmark": "OBJECT_COUPLED"',
        'landmark": "OBJECT_AT_TARGET"',
        'landmark": "OBJECT_RELEASED"',
        'landmark": "PINCH_RELEASED"',
        'landmark": "WRISTS_APART"',
        'landmark": "WRISTS_LOW"',
    ]:
        assert landmark in server_source


def test_live_tasks_and_runner_routes_expose_step_failure_contract():
    with TestClient(server.app) as client:
        tasks_response = client.get("/api/assessment/tasks?package=upper_limb")
        assert tasks_response.status_code == 200
        assert tasks_response.headers["content-type"].startswith("application/json")
        payload = tasks_response.json()
        assert payload["package_id"] == "upper_limb"
        assert len(payload["tasks"]) == 7
        assert all(
            step.get("failure_phenotype")
            for task in payload["tasks"]
            for step in task["steps"]
        )

        runner_response = client.get("/api/pose/runner")
        assert runner_response.status_code == 200
        assert runner_response.headers["content-type"].startswith("text/html")
        assert "failure_code: skipped && step.failure_phenotype" in runner_response.text

        task_result = _task_result_with_failures("T4", {"T4-S6"})
        submit_response = client.post(
            "/api/assessment/submit",
            json={
                "affected_side": "right",
                "task_results": [task_result.model_dump()],
            },
        )
        assert submit_response.status_code == 200
        assert submit_response.headers["content-type"].startswith("application/json")
        assessment = submit_response.json()
        assert assessment["functional_issues"] == [
            {
                "code": "OBJECT_RELEASE_IMPAIRED",
                "label": "Difficulty releasing an object",
                "description": "The cup reached the target but the affected hand did not open and separate from it.",
                "source": "ARAT grasp subscale",
                "severity": "moderate",
                "related_task": "T4",
                "related_step": "T4-S6",
                "phenotype_domain": "object_release",
            }
        ]
        assert assessment["rehab_plan"] == []
        assert assessment["clinical_review_gate"]["status"] == "awaiting_model_analysis"
