import os

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "movement_snapshot_audit_test")

from backend import server
from backend.biomechanics_pipeline import patient_body_function_summary


def _reach_result(*, failed: bool, trunk_lean: float = 0, shoulder_hike: bool = False):
    steps = [
        server.TaskStepResult(step_id="T1-S1", completed=True),
        server.TaskStepResult(
            step_id="T1-S2",
            completed=not failed,
            metrics={"trunk_lean_deg": trunk_lean, "shoulder_hike": shoulder_hike},
        ),
    ]
    return server.TaskResult(
        task_id="T1",
        completed_steps=sum(step.completed for step in steps),
        total_steps=len(steps),
        duration_ms=4200,
        steps=steps,
        metrics={},
    )


def test_snapshot_decision_records_steps_thresholds_findings_and_marker_provenance():
    result = _reach_result(failed=True, trunk_lean=24, shoulder_hike=True)
    issues = server.derive_functional_issues([result])
    body_summary = patient_body_function_summary([result], issues, {}, ("upper_limb",))

    decision = server.build_movement_snapshot_decision(
        [result],
        issues,
        body_summary,
        "right",
        {
            "status": "queued",
            "gpu_stage": {"status": "queued", "device": "cuda:0"},
            "musculoskeletal_stage": {"status": "queued", "modeled_tasks": ["T1"]},
        },
    )

    failed_step = next(item for item in decision["step_outcomes"] if item["step_id"] == "T1-S2")
    assert failed_step == {
        "task_id": "T1",
        "step_id": "T1-S2",
        "completed": False,
        "failure_code": "REACH_INCOMPLETE",
    }
    assert {item["finding_code"] for item in decision["triggered_thresholds"]} == {
        "TRUNK_COMP",
        "SHOULDER_HIKE",
    }
    assert decision["selection_rule"]["selected_issue_code"] == "REACH_INCOMPLETE"
    assert decision["anatomy_marker"]["region"] == "right_shoulder"
    assert decision["anatomy_marker"]["source_issue_code"] == "REACH_INCOMPLETE"
    assert "upper-limb" in decision["anatomy_marker"]["reason"]
    assert decision["model_status"]["gpu_stage"]["device"] == "cuda:0"
    assert decision["body_function_domains"][0]["status"] == "review_recommended"


def test_no_issue_sentinel_never_creates_a_false_shoulder_highlight():
    result = _reach_result(failed=False)
    issues = server.derive_functional_issues([result])
    body_summary = patient_body_function_summary([result], issues, {}, ("upper_limb",))

    decision = server.build_movement_snapshot_decision(
        [result], issues, body_summary, "left", {"status": "waiting_for_inputs"}
    )

    assert [item.code for item in issues] == ["NO_ISSUES"]
    assert decision["functional_findings"] == []
    assert decision["primary_finding"] is None
    assert decision["selection_rule"]["no_issue_sentinel_excluded"] is True
    assert decision["anatomy_marker"]["visible"] is False
    assert decision["presentation"]["tone"] == "pending"
    assert decision["presentation"]["title"] == "We are checking your movement"


def test_pytest_server_actions_are_isolated_from_patient_action_logs():
    assert "rehyn-pytest-action-logs" in str(server.ALIRA_ACTION_LOGGER.base_dir)


def test_patient_snapshot_endpoints_require_sign_in(monkeypatch):
    async def no_user(_headers):
        return None

    monkeypatch.setattr(server, "_user_from_header", no_user)
    with TestClient(server.app) as client:
        assert client.get("/api/assessment/private-assessment").status_code == 401
        assert client.get("/api/assessment/private-assessment/patient-summary").status_code == 401
        assert client.get("/api/assessment/private-assessment/analysis-status").status_code == 401
        assert client.get("/api/assessment/private-assessment/muscle-diagnosis").status_code == 401
