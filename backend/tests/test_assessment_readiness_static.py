from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_setup_survey_collects_initial_task_prerequisites():
    survey = (ROOT / "frontend" / "src" / "patientSurvey.ts").read_text(encoding="utf-8")

    for key in (
        "sitting_ability",
        "affected_arm_movement",
        "affected_hand_movement",
        "mobility_level",
        "movement_pain",
        "instruction_support",
    ):
        assert f'key: "{key}"' in survey
    assert "hands-on help from another person" in survey
    assert "Severe or worsening pain" in survey


def test_existing_accounts_get_readiness_only_update_flow():
    onboarding = (ROOT / "frontend" / "app" / "onboarding.tsx").read_text(encoding="utf-8")
    task_intro = (ROOT / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")

    assert 'params.mode === "assessment-readiness"' in onboarding
    assert "ASSESSMENT_READINESS_KEYS.includes" in onboarding
    assert 'router.replace(isReadinessUpdate ? "/task-intro?mode=initial" : "/")' in onboarding
    assert 'router.push("/onboarding?mode=assessment-readiness"' in task_intro


def test_assigned_tasks_are_carried_through_the_real_camera_path():
    task_intro = (ROOT / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")
    camera_check = (ROOT / "frontend" / "app" / "camera-check.tsx").read_text(encoding="utf-8")
    assessment = (ROOT / "frontend" / "app" / "assessment.tsx").read_text(encoding="utf-8")
    server = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")

    assert 'task_ids: taskIds.join(",")' in task_intro
    assert 'task_ids: params.task_ids || ""' in camera_check
    assert 'query.set("task_ids", assignedTaskIdsParam)' in assessment
    assert 'headers: CURRENT_USER_ID ? {"X-User-Id": CURRENT_USER_ID}' in server
    assert 'assigned_task_ids: tasks.map(task => task.id)' in server
    assert "Assigned initial tasks do not match the saved readiness survey" in server
