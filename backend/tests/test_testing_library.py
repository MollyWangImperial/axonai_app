import os
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_testing_library_test")

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


FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"


async def _signed_in_user(_headers):
    return {
        "id": "u_testing_library",
        "credits": 1000,
        "consent": {"health_data_consent": True},
        "profile": {"side_affected": "right"},
    }


def test_testing_library_exposes_every_unique_task_and_guided_exercise(monkeypatch):
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    with TestClient(server.app) as client:
        response = client.get("/api/testing/library")

    assert response.status_code == 200
    payload = response.json()
    tasks = [task for package in payload["assessment_packages"] for task in package["tasks"]]
    exercises = payload["exercises"]
    expected_task_ids = {
        task["id"]
        for package_id, package in server.ASSESSMENT_PACKAGES.items()
        if package_id != "initial"
        for task in package["tasks"]
    }
    expected_exercise_ids = {exercise.id for exercise in server.EXERCISE_LIBRARY.values()}

    assert payload["assessment_task_count"] == 25
    assert payload["exercise_count"] == 18
    assert payload["test_runs_are_recorded"] is False
    assert {task["id"] for task in tasks} == expected_task_ids
    assert len(tasks) == len(expected_task_ids)
    assert {exercise["id"] for exercise in exercises} == expected_exercise_ids
    assert expected_exercise_ids == set(server.REHAB_RUNNER_CONFIG)
    assert all(exercise["guided_reps"] > 0 for exercise in exercises)
    assert all(exercise["calibration_instruction"] for exercise in exercises)
    assert all(exercise["training_focus"] for exercise in exercises)
    assert all(exercise["repetition_definition"] for exercise in exercises)
    assert all(exercise["rom_metrics"] for exercise in exercises)
    assert all(exercise["scoring_method"] == server.EXERCISE_SCORING_METHOD for exercise in exercises)
    assert all(exercise["overlay_style"] == server.EXERCISE_OVERLAY_STYLE for exercise in exercises)
    assert all(
        metric["coaching_cue"]
        for exercise in exercises
        for metric in exercise["rom_metrics"]
    )
    assert all(
        metric["label"] and metric["correction"]
        for exercise in exercises
        for metric in exercise["compensation_metrics"]
    )


def test_library_task_launch_bypasses_schedule_only_for_one_explicit_task(monkeypatch):
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)

    async def schedule_must_not_run(*_args, **_kwargs):
        raise AssertionError("scheduled assessment access should not run in library test mode")

    monkeypatch.setattr(server, "_assessment_access_plan", schedule_must_not_run)
    with TestClient(server.app) as client:
        response = client.get("/api/assessment/tasks?package=hand&task_ids=H1&library_test=true")
        missing_task = client.get("/api/assessment/tasks?package=hand&library_test=true")
        multiple_tasks = client.get("/api/assessment/tasks?package=hand&task_ids=H1,H2&library_test=true")

    assert response.status_code == 200
    assert response.json()["assigned_task_ids"] == ["H1"]
    assert [task["id"] for task in response.json()["tasks"]] == ["H1"]
    assert missing_task.status_code == 422
    assert multiple_tasks.status_code == 422


def test_testing_routes_require_a_signed_in_account(monkeypatch):
    async def no_user(_headers):
        return None

    monkeypatch.setattr(server, "_user_from_header", no_user)
    with TestClient(server.app) as client:
        assert client.get("/api/testing/library").status_code == 401
        assert client.get("/api/assessment/tasks?package=hand&task_ids=H1&library_test=true").status_code == 401


def test_frontend_library_and_runners_keep_test_results_out_of_progress():
    settings = (FRONTEND_ROOT / "app" / "(tabs)" / "settings.tsx").read_text(encoding="utf-8")
    library = (FRONTEND_ROOT / "app" / "testing-library.tsx").read_text(encoding="utf-8")
    assessment = (FRONTEND_ROOT / "app" / "assessment.tsx").read_text(encoding="utf-8")
    exercise = (FRONTEND_ROOT / "app" / "exercise.tsx").read_text(encoding="utf-8")
    runner = server.POSE_RUNNER_HTML

    assert 'testID="settings-testing-library"' in settings
    assert 'router.push("/testing-library" as never)' in settings
    assert 'library_test: "1"' in library
    assert 'task_ids: task.id' in library
    assert 'plan_id: "library-test"' in library
    assert 'if (!isLibraryTest && msg.task_id && userIdRef.current)' in assessment
    assert 'msg.type === "library_test_complete"' in assessment
    assert 'if (isLibraryTest) return;' in exercise
    assert 'if (!isLibraryTest) {' in exercise
    assert 'const LIBRARY_TEST_MODE = URL_PARAMS.get("library_test") === "1";' in runner
    assert 'stepTitle.textContent = "Single task test";' in runner
    assert 'if(LIBRARY_TEST_MODE) return Promise.resolve(null);' in runner
    assert 'if(LIBRARY_TEST_MODE) return;' in runner
    assert 'if(LIBRARY_TEST_MODE) taskQuery.set("library_test", "1");' in runner
    assert 'if(!LIBRARY_TEST_MODE){' in runner
    assert 'postRN({type:"library_test_complete"' in runner


def test_patient_testing_list_matches_initial_tasks_without_walking(monkeypatch):
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    with TestClient(server.app) as client:
        result = client.get("/api/testing/library?patient_tasks_only=true").json()
    tasks = [task for package in result["assessment_packages"] for task in package["tasks"]]
    assert [task["id"] for task in tasks] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert result["assessment_task_count"] == 6
    assert tasks[0]["title"] == "Seated Forward Reach"


def _measured_reach():
    from backend.assessment_quality import VERSION
    steps = []
    for rule in server.ASSESSMENT_RUBRICS["T1"]["steps"]:
        steps.append({"step_id": rule["id"], "completed": True, "duration_ms": 2000,
                      "metrics": {"quality": {"version": VERSION,
                          "measurements": {c["metric"]: {"value": c["target"], "samples": 10} for c in rule["criteria"]},
                          "compensations": {cid: {"eligible_ms": 900, "max_value": 0, "max_streak_ms": 0} for cid in rule["compensations"]},
                          "observations": {"arm_elevation": {"samples": 10, "median": 50, "endpoint": 60, "min": 10, "max": 70}}
                      }}})
    return {"task_id": "T1", "completed_steps": 4, "total_steps": 4, "duration_ms": 8000, "steps": steps}


def test_testing_report_explains_score_without_persisting_or_charging(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    # Any storage use fails: this route must be a pure calculation.
    monkeypatch.setattr(server, "db", SimpleNamespace())
    async def forbidden(*args, **kwargs):
        raise AssertionError("Test run must not affect the patient account")
    monkeypatch.setattr(server, "consume_credits", forbidden)
    monkeypatch.setattr(server, "_record_initial_assessment_completion", forbidden)
    result = _measured_reach()
    reach = result["steps"][1]["metrics"]["quality"]
    reach["measurements"]["elbow_extension"]["value"] = 90
    reach["compensations"]["trunk_lean"].update(max_value=20, max_streak_ms=700)
    with TestClient(server.app) as client:
        response = client.post("/api/testing/assessment-score", json=result)
    assert response.status_code == 200
    report = response.json()
    assert report["recorded"] is False and report["clinical_measure"] is False
    assert report["task"]["score"] == 91.8
    assert report["completed_steps"] == 4 and report["duration_ms"] == 8000
    step = report["task"]["steps"][1]
    assert step["score"] == 67.2
    assert step["calculation"] == {"completion_points": 20, "range_points": 64,
                                   "detected_compensations": 1, "form_factor": .8}
    shoulder = next(row for row in step["measurements"] if row["metric"] == "arm_elevation")
    assert shoulder["endpoint"] == 60 and shoulder["max"] == 70
    assert next(row for row in step["measurements"] if row["metric"] == "wrist_bend")["median"] is None


def test_testing_report_preserves_missing_evidence_and_rejects_wrong_steps(monkeypatch):
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    result = _measured_reach()
    result["steps"][1]["metrics"] = {}
    with TestClient(server.app) as client:
        report = client.post("/api/testing/assessment-score", json=result).json()
        assert report["task"]["score"] is None
        assert report["task"]["earned_score"] == 75
        assert report["task"]["steps"][1]["score"] is None
        assert all(row["median"] is None for row in report["task"]["steps"][1]["measurements"])
        result["steps"][0]["step_id"] = "H1-S1"
        assert client.post("/api/testing/assessment-score", json=result).status_code == 422
        result = _measured_reach()
        result["steps"].append(result["steps"][0])
        assert client.post("/api/testing/assessment-score", json=result).status_code == 422
        result["task_id"] = "L6"
        assert client.post("/api/testing/assessment-score", json=result).status_code == 422


def test_testing_report_requires_sign_in(monkeypatch):
    async def no_user(_headers):
        return None
    monkeypatch.setattr(server, "_user_from_header", no_user)
    with TestClient(server.app) as client:
        assert client.post("/api/testing/assessment-score", json=_measured_reach()).status_code == 401
