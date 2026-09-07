import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_t3_mouth_target_test")

from backend import server


def test_t3_mouth_steps_use_an_anatomical_mouth_target():
    task = next(task for task in server.TASKS_DATA if task["id"] == "T3")
    assert task["steps"][1]["target"]["landmark"] == "MOUTH"
    assert task["steps"][2]["target"]["landmark"] == "MOUTH"


def test_t3_mouth_target_is_stabilized_and_uses_affected_hand_contact_points():
    source = server.POSE_RUNNER_HTML
    for marker in (
        "function newMouthTargetCalibration()",
        "function poseMouthTarget(lm)",
        "return midpoint(leftMouth, rightMouth);",
        "function updateMouthTargetCalibration(lm, sampleKey=(lastPoseScanTs || performance.now()))",
        "function affectedPoseHandPoints(lm)",
        "const indices = left ? [15, 17, 19, 21] : [16, 18, 20, 22];",
        "function closestAffectedHandPointToTarget(lm, target)",
        "function mouthContactDistance(lm, target)",
        'if(which === "MOUTH")',
        "return mouthTargetCalibration.locked && mouthContactDistance(landmarks, targetXY) < R;",
        "const palm = rawHandPalmCenter();",
    ):
        assert marker in source
    mouth_function = source[source.index("function poseMouthTarget") : source.index("function updateMouthTargetCalibration")]
    assert "mirrorX" not in mouth_function


def test_t3_mouth_circle_never_falls_back_to_a_non_anatomical_screen_position():
    source = server.POSE_RUNNER_HTML
    resolver = source[source.index("function getEffectiveTargetXY") : source.index("// ---------- Hand metrics")]
    target_check = source[source.index("function checkTarget") : source.index("// ---------- Drawing")]

    assert "return p ? {x:p.x, y:p.y} : null;" in resolver
    assert "return p ? {x:p.x, y:p.y} : {x:step.target.x, y:step.target.y};" not in resolver
    assert "return mouthTargetCalibration.locked && mouthContactDistance(landmarks, targetXY) < R;" in target_check
    assert "Keep your face and mouth visible while Rehyn locates the mouth target." in source
    assert 'currentStepIdx === 0 || isMouthTarget(getCurrentStep())' in source


def test_t3_enables_hand_landmarks_and_has_a_browser_simulation_hook():
    source = server.POSE_RUNNER_HTML
    assert '|| landmark === "MOUTH"' in source
    assert 'window.__rehynMouthTargetTest' in source
    assert 'runTargetSequence:(frames)' in source
    assert 'evaluatePoseHit:(landmarks, target, radius=0.10)' in source
    assert "const affectedWrist = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;" in source
    assert 'step.target.landmark === "MOUTH"' in source
    assert "return sideLandmarks(lm, AFFECTED_SIDE).wrist;" in source
