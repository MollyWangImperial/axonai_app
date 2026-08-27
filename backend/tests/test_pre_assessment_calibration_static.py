import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_pre_assessment_calibration_test")

from backend import server


def test_runner_has_a_patient_facing_seated_calibration_gate():
    source = server.POSE_RUNNER_HTML
    for marker in (
        'id="calibrationOverlay"',
        'data-testid="assessment-calibration"',
        "Sit still with your affected hand resting on your lap",
        "Face, shoulders, and affected arm are visible",
        "Hips and affected knee are visible",
        'data-testid="calibration-auto-status"',
        "Assessment will start automatically",
        "Calibration complete. Starting assessment",
    ):
        assert marker in source


def test_calibration_requires_visible_arm_seated_anchors_and_a_stable_lap():
    source = server.POSE_RUNNER_HTML
    assert "function calibrationLandmarkStatus(lm)" in source
    assert "const faceVisible = [lm[0], lm[9], lm[10]].some" in source
    assert "[lm[11], lm[12], affected.elbow, affected.wrist]" in source
    assert "[lm[23], lm[24], affected.knee]" in source
    assert "lapTargetCalibration.ready && lapTargetCalibration.target" in source
    assert "cameraReady && armVisible && seatedAnchorsVisible && lapReady" in source
    assert "function landmarkIsInFrame(point" in source
    assert "point.x >= margin && point.x <= 1 - margin" in source
    assert "point.y >= margin && point.y <= 1 - margin" in source
    assert ".every(point => landmarkIsInFrame(point, visibility))" in source


def test_calibration_runs_before_task_one_and_is_not_recorded_as_task_motion():
    source = server.POSE_RUNNER_HTML
    start_handler = source[source.index('startBtn.addEventListener("click"') : source.index('markerConfirmBtn.addEventListener')]
    assert "calibratingAssessment = shouldRunSeatedCalibration();" in start_handler
    assert start_handler.index("requestAnimationFrame(loop);") < start_handler.index("await playVoice(CALIBRATION_INSTRUCTION);")
    assert "await startStep();" in start_handler
    assert "prefetchVoice(CALIBRATION_COMPLETE_INSTRUCTION);" in start_handler
    assert "if(!running || calibratingAssessment || motionFrames.length >= MAX_MOTION_FRAMES) return;" in source
    assert "if(calibratingAssessment){\n    requestAnimationFrame(loop);\n    return;" in source


def test_calibration_auto_starts_with_a_position_hold_instruction():
    source = server.POSE_RUNNER_HTML
    assert "function completePreAssessmentCalibration()" in source
    assert "if(calibrationInstructionFinished) void completePreAssessmentCalibration();" in source
    assert "await playVoice(CALIBRATION_COMPLETE_INSTRUCTION);" in source
    assert "Stay seated in this position and do not move the camera" in source
    assert "automatic:true" in source
    assert 'calibrationBeginBtn.addEventListener("click"' not in source
    assert 'data-testid="calibration-begin"' not in source


def test_calibrated_lap_is_drawn_live_and_preserved_for_first_task():
    source = server.POSE_RUNNER_HTML
    assert 'ctx.strokeStyle = "#7FE5A3";' in source
    assert "preservePreAssessmentLapCalibration = true;" in source
    assert "if(preservePreAssessmentLapCalibration && currentTaskLapStep()){" in source
    assert "}else if(!preservePreAssessmentLapCalibration){\n      lapTargetCalibration = newLapTargetCalibration();" in source
    assert 'type:"assessment_calibrated"' in source
    assert "lap_target:lapTargetCalibration.target" in source


def test_packages_without_an_upcoming_lap_step_can_start_normally():
    source = server.POSE_RUNNER_HTML
    assert "function upcomingLapStep()" in source
    assert "function shouldRunSeatedCalibration(){\n  return !!upcomingLapStep();" in source
    assert "if(calibratingAssessment){" in source


def test_browser_hook_can_drive_the_real_calibration_gate():
    source = server.POSE_RUNNER_HTML
    assert "applyCalibrationSequence:" in source
    assert "updatePreAssessmentCalibrationUI(landmarks);" in source
    assert "autoStarting:calibrationAutoStartInProgress" in source
    assert "statusText:calibrationAutoStatus.textContent" in source
