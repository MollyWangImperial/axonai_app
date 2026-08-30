import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_functional_progress_test")

from backend import server
from backend.biomechanics_pipeline import patient_body_function_summary, patient_collection_summary
from fastapi.testclient import TestClient


def _step(step_id, **metrics):
    return server.TaskStepResult(step_id=step_id, completed=True, metrics=metrics)


def test_progress_metrics_are_derived_from_current_task_result_contract():
    tasks = [
        server.TaskResult(
            task_id="T1",
            completed_steps=4,
            total_steps=4,
            steps=[_step("T1-S2", shoulder_elevation_deg=72, trunk_lean_deg=9)],
        ),
        server.TaskResult(
            task_id="H1",
            completed_steps=3,
            total_steps=3,
            steps=[_step("H1-S2", hand_open_score=0.82, pinch_score=0.51)],
        ),
        server.TaskResult(
            task_id="L6",
            completed_steps=3,
            total_steps=3,
            metrics={
                "gait_bilateral_motion_symmetry": 0.88,
                "gait_full_body_visibility_ratio": 0.91,
                "uploaded_video_duration_ms": 5400,
            },
        ),
    ]

    metrics = server.build_functional_metrics(tasks)

    assert metrics["reach_completion"] == 1.0
    assert metrics["shoulder_flexion_deg"] == 72
    assert metrics["trunk_lean_deg"] == 9
    assert metrics["hand_opening"] == 0.82
    assert metrics["pinch_grip"] == 0.51
    assert metrics["bilateral_symmetry"] == 0.88
    assert metrics["domains"]["lower_limb"]["video_duration_seconds"] == 5.4


def test_skipped_walking_is_not_counted_as_failed_or_observed():
    walking = server.TaskResult(
        task_id="L6",
        completed_steps=0,
        total_steps=0,
        steps=[],
        metrics={"walking_skipped": True, "skip_reason": "patient_unable_or_restricted"},
    )

    metrics = server.build_functional_metrics([walking])
    collection = patient_collection_summary([walking], 1)
    summary = patient_body_function_summary([walking], [], {}, ("lower_limb",))

    assert metrics["walking_skipped"] is True
    assert metrics["bilateral_symmetry"] is None
    assert metrics["domains"]["lower_limb"]["observed"] is False
    assert collection["tasks_collected"] == 0
    assert summary["domains"][0]["status"] == "not_observed"
    assert "not counted as a failed task" in summary["domains"][0]["summary"]


def test_patient_function_summary_exposes_explanations_and_real_metrics():
    source = open("frontend/app/function-summary.tsx", encoding="utf-8").read()
    api = open("frontend/src/api.ts", encoding="utf-8").read()
    progress = open("frontend/app/progress.tsx", encoding="utf-8").read()

    assert "Open ${domain.title} details" in source
    assert "WHY THIS RESULT" in source
    assert "movement_snapshot_decision?.functional_findings" in source
    assert "data.functional_metrics?.domains" in source
    assert 'status: "Captured"' in source
    assert "functional_metrics?: FunctionalMetrics" in api
    assert 'status: "Not observed", value: "Skipped"' in progress


def test_progress_summary_backfills_metrics_for_existing_assessments(monkeypatch):
    async def user_from_header(_headers):
        return {"id": "u_progress", "consent": {"health_data_consent": True}}

    async def assessments_for_user(_user_id):
        return [{
            "id": "a_progress",
            "created_at": "2026-08-30T10:00:00+00:00",
            "task_results": [{
                "task_id": "T1",
                "completed_steps": 3,
                "total_steps": 4,
                "steps": [{"step_id": "T1-S2", "completed": True, "metrics": {"trunk_lean_deg": 11}}],
                "metrics": {},
            }],
            "functional_issues": [{"code": "REACH_INCOMPLETE"}],
            "rehab_plan": [],
        }]

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", assessments_for_user)
    with TestClient(server.app) as client:
        response = client.get("/api/progress/summary", headers={"X-User-Id": "u_progress"})

    assert response.status_code == 200
    point = response.json()["assessments"][0]
    assert point["reach_completion"] == 0.75
    assert point["trunk_lean_deg"] == 11
    assert point["issues_count"] == 1
