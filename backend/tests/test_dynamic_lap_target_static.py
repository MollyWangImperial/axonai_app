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
        (server.HAND_TASKS_DATA, "H3", "H3-S3"),
        (server.HAND_TASKS_DATA, "H4", "H4-S3"),
    )
    for tasks, task_id, step_id in expected:
        step = _step(tasks, task_id, step_id)
        assert step["target"]["landmark"] == "LAP_DYNAMIC"
        assert "lap" in (step["voice"] + " " + step["caption"]).lower()


def test_lap_calibration_uses_a_stable_affected_hand_resting_on_the_visible_lap():
    source = server.POSE_RUNNER_HTML
    for marker in (
        "function lapTargetCandidate(lm)",
        "landmarkIsInFrame(affected.hip, lapVisibility)",
        "landmarkIsInFrame(affected.wrist, lapVisibility)",
        "const wristBelowHip = wrist.y - hip.y;",
        "const wristFromHipX = Math.abs(wrist.x - hip.x);",
        "const anatomical = {x:affected.wrist.x, y:affected.wrist.y};",
        "const LAP_CALIBRATION_MIN_SAMPLES = 8;",
        "const LAP_CALIBRATION_MIN_MS = 650;",
        "let center = {x:medianValue(samples.map(s => s.x)), y:medianValue(samples.map(s => s.y))};",
        "const stableSamples = samples.filter",
        "Math.hypot(s.bodyX-bodyCenter.x, s.bodyY-bodyCenter.y) <= maxBodyJitter",
        "Math.ceil(samples.length * 0.70)",
        "stableDuration < LAP_CALIBRATION_MIN_MS",
        "const screenPoint = anatomical;",
    ):
        assert marker in source
    assert "landmarkIsInFrame(affected.knee, lapVisibility)" not in source


def test_lap_calibration_starts_before_the_return_step_and_survives_brief_tracking_loss():
    source = server.POSE_RUNNER_HTML
    assert "function currentTaskLapStep()" in source
    assert "const lapStep = calibratingAssessment ? upcomingLapStep() : currentTaskLapStep();" in source
    assert "if(!lapStep || lapTargetCalibration.ready) return;" in source
    assert "now - lapTargetCalibration.lastCandidateAt <= 900" in source
    assert "if(preservePreAssessmentLapCalibration && currentTaskLapStep()){" in source


def test_one_preassessment_lap_target_is_locked_across_all_tasks():
    source = server.POSE_RUNNER_HTML
    assert "let assessmentLapTarget = null;" in source
    assert "assessmentLapTarget = lapTargetCalibration.target" in source
    assert "if(assessmentLapTarget){" in source
    assert "lapTargetCalibration.target = {...assessmentLapTarget};" in source
    assert "dynamicTargetPos = {...assessmentLapTarget};" in source
    assert "return assessmentLapTarget || lapTargetCalibration.target" in source


def test_hand_assessment_loads_pose_for_its_dynamic_lap_target():
    source = server.POSE_RUNNER_HTML
    setup = source[source.index("async function setupTrackingModels()") : source.index("function playBrowserVoice")]
    assert setup.index("await setupPose();") < setup.index('if(ASSESSMENT_PACKAGE === "hand"){')
    assert "await setupHand();" in setup


def test_lap_calibration_has_a_browser_simulation_hook():
    source = server.POSE_RUNNER_HTML
    assert 'URL_PARAMS.get("test_mode") === "lap_calibration"' in source
    assert "window.__rehynLapCalibrationTest" in source
    assert "updateLapTargetCalibration(landmarks, frame * frameMs);" in source
    assert "applyCalibrationSequence:" in source
    assert "runSequence: (frames, frameMs=100)" in source
    assert "diagnose: (landmarks) => lapTargetCandidateStatus(landmarks)" in source
    assert "function withLapCalibrationTestContext(callback)" in source
    assert "lockAssessmentTarget:(target)" in source
    assert "effectiveTarget:() => getEffectiveTargetXY" in source


def test_lap_circle_is_hidden_and_noninteractive_until_calibration_is_ready():
    source = server.POSE_RUNNER_HTML
    assert "if(isLapTarget(step) && !lapTargetCalibration.ready){" in source
    assert 'lapStatus.classList.remove("hidden");' in source
    assert "if(!lapTargetCalibration.ready || !landmarks || !arrivedAfterMovement) return false;" in source
    assert "if(isLapTarget(step) && !lapTargetCalibration.ready) return null;" in source
    assert 'type:"lap_target_calibrated"' in source


def test_lap_drawing_and_hit_testing_share_calibrated_coordinates():
    source = server.POSE_RUNNER_HTML
    assert "return assessmentLapTarget || lapTargetCalibration.target || {x: step.target.x, y: step.target.y};" in source
    assert "const targetXY = getEffectiveTargetXY(step);" in source
    assert "const affectedWristRaw = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;" in source
    assert "return distXY(affectedWristRaw, targetXY) < effectiveRadius(step, landmarks);" in source
    assert "if(isLapTarget(step) && lm) return sideLandmarks(lm, AFFECTED_SIDE).wrist;" in source
    assert "updateLapTargetCalibration(landmarks, now);" in source


def test_lap_target_uses_the_survey_selected_anatomical_side_without_double_mirroring():
    source = server.POSE_RUNNER_HTML
    assert 'const AFFECTED_SIDE = URL_PARAMS.get("affected_side") === "left" ? "left" : "right";' in source
    assert "const affected = sideLandmarks(lm, AFFECTED_SIDE);" in source
    assert "const screenPoint = anatomical;" in source
    assert "const screenPoint = mirrorX(anatomical);" not in source
    assert "affectedSide:AFFECTED_SIDE" in source


def test_hand_package_lap_step_is_not_forced_back_to_static_coordinates():
    source = server.POSE_RUNNER_HTML
    dynamic_index = source.index("if(isLapTarget(step)){\n    return assessmentLapTarget || lapTargetCalibration.target")
    hand_index = source.index("if(isHandTask()){\n    return {x: step.target.x, y: step.target.y};", dynamic_index)
    assert dynamic_index < hand_index
