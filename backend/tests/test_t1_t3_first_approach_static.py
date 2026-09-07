import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_t1_t3_first_approach_test")

from backend import server


def test_t1_uses_only_the_affected_hand_and_accepts_hand_contact_points():
    source = server.POSE_RUNNER_HTML
    assert "function affectedReachContactPoints(lm)" in source
    assert "function closestAffectedReachPointToTarget(lm, target)" in source
    assert 'if(task && task.id === "T1")' in source
    assert "distXY(closestAffectedReachPointToTarget(landmarks, targetXY), targetXY)" in source
    active_wrist = source[source.index("function activeWrist") : source.index("function activeControlPoint")]
    assert "sideLandmarks(lm, AFFECTED_SIDE).wrist" in active_wrist
    assert "dL < dR" not in active_wrist
    assert 'window.__rehynUpperLimbEndpointTest' in source
    assert "evaluateReachHit:(landmarks, target, radius=0.10)" in source


def test_t1_and_t3_first_approaches_do_not_require_a_second_movement():
    source = server.POSE_RUNNER_HTML
    assert "function movementGateRequired(step)" in source
    assert '["T1-S1", "T1-S2", "T3-S1", "T3-S2"].includes(step.id)' in source
    assert "arrivedAfterMovement = !movementGateRequired(step);" in source
    assert "if(movementGateRequired(step) && !arrivedAfterMovement) return false;" in source


def test_other_upper_limb_movement_gates_use_a_patient_scaled_threshold():
    source = server.POSE_RUNNER_HTML
    movement_gate = source[source.index("function updateMovementGate") : source.index("function movementGateRequired")]
    assert "Math.max(0.035, shoulderWidth(lm) * 0.30)" in movement_gate
    assert "Math.max(0.12, shoulderWidth(lm) * 0.75)" not in movement_gate


def test_t3_mouth_is_locked_before_the_hand_covers_the_face():
    source = server.POSE_RUNNER_HTML
    assert 'activeTask && activeTask.id === "T3" && !mouthTargetCalibration.locked' in source
    assert 'currentStepIdx === 0 || isMouthTarget(getCurrentStep())' in source
    assert "updateMouthTargetCalibration(landmarks, lastPoseScanTs);" in source
    assert "if(mouthTargetCalibration.locked && mouthTargetCalibration.target)" in source


def test_arm_start_targets_are_fixed_to_the_horizontal_screen_center():
    source = server.POSE_RUNNER_HTML
    resolver = source[source.index("function getEffectiveTargetXY") : source.index("// ---------- Hand metrics")]
    expected = {
        "T1-S1", "T2-S1", "T3-S1", "T5-S1", "T6-S1", "T7-S1",
        "H1-S1", "H2-S1", "H3-S1", "H4-S1",
    }

    assert "const CENTERED_ARM_START_STEP_IDS = new Set" in source
    assert "return {x:0.5, y:step.target.y};" in resolver
    assert resolver.index("if(isCenteredArmStartStep(step))") < resolver.index('if(which === "CHEST")')
    assert "centeredStartTarget:(step, landmarks=null)" in source
    for step_id in expected:
        assert f'"{step_id}"' in source[source.index("const CENTERED_ARM_START_STEP_IDS") : source.index("function poseMouthTarget")]
