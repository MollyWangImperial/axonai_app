import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_dynamic_lap_target_test")

from backend import server


def _step(tasks, task_id, step_id):
    task = next(item for item in tasks if item["id"] == task_id)
    return next(item for item in task["steps"] if item["id"] == step_id)


def test_true_lap_return_steps_use_patient_specific_dynamic_targets():
    expected = (
        (server.TASKS_DATA, "T1", "T1-S4"),
        (server.TASKS_DATA, "T3", "T3-S4"),
        (server.HAND_TASKS_DATA, "H1", "H1-S3"),
    )
    for tasks, task_id, step_id in expected:
        step = _step(tasks, task_id, step_id)
        assert step["target"]["landmark"] == "LAP_DYNAMIC"
        assert "lap" in (step["voice"] + " " + step["caption"]).lower()


def test_lap_calibration_uses_stable_seated_anatomy_not_a_wrist_snapshot():
    source = server.POSE_RUNNER_HTML
    for marker in (
        "function lapTargetCandidate(lm)",
        "affected.hip.x * 0.58 + affected.knee.x * 0.42",
        "affected.hip.y * 0.58 + affected.knee.y * 0.42",
        "const LAP_CALIBRATION_MIN_SAMPLES = 8;",
        "const LAP_CALIBRATION_MIN_MS = 650;",
        "const center = {x:medianValue(samples.map(s => s.x)), y:medianValue(samples.map(s => s.y))};",
        "const stable = samples.every",
        "Math.hypot(s.bodyX-bodyCenter.x, s.bodyY-bodyCenter.y) <= maxJitter",
        "if(kneeAngle > 158) return null;",
    ):
        assert marker in source


def test_lap_circle_is_hidden_and_noninteractive_until_calibration_is_ready():
    source = server.POSE_RUNNER_HTML
    assert "if(isLapTarget(step) && !lapTargetCalibration.ready) return;" in source
    assert "if(!lapTargetCalibration.ready || !landmarks || !arrivedAfterMovement) return false;" in source
    assert "if(isLapTarget(step) && !lapTargetCalibration.ready) return null;" in source
    assert 'type:"lap_target_calibrated"' in source


def test_lap_drawing_and_hit_testing_share_calibrated_coordinates():
    source = server.POSE_RUNNER_HTML
    assert "return lapTargetCalibration.target || {x: step.target.x, y: step.target.y};" in source
    assert "const targetXY = getEffectiveTargetXY(step);" in source
    assert "const affectedWristRaw = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;" in source
    assert "return distXY(affectedWrist, targetXY) < effectiveRadius(step, landmarks);" in source
    assert "updateLapTargetCalibration(landmarks, now);" in source


def test_hand_package_lap_step_is_not_forced_back_to_static_coordinates():
    source = server.POSE_RUNNER_HTML
    dynamic_index = source.index("if(isLapTarget(step)){\n    return lapTargetCalibration.target")
    hand_index = source.index("if(isHandTask()){\n    return {x: step.target.x, y: step.target.y};", dynamic_index)
    assert dynamic_index < hand_index
