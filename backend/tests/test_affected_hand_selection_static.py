import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_affected_hand_selection_test")

from backend import server


def test_hand_landmarker_can_observe_both_hands_but_keeps_only_the_affected_hand():
    source = server.POSE_RUNNER_HTML
    # Up to 4 hands are observed (patient's two plus a helping carer hand or
    # two); metric selection still keeps only the affected hand.
    assert "numHands: 4" in source
    assert "function selectAffectedHandDetection(result" in source
    assert "sideLandmarks(latestPoseLandmarks, AFFECTED_SIDE).wrist" in source
    assert "candidate.poseDistance <= associationRadius" in source
    assert "const affectedHand = selectAffectedHandDetection(hr, now);" in source
    assert "latestHandLandmarks = affectedHand.landmarks;" in source
    assert "latestHandedness = affectedHand.handedness;" in source
    assert "latestHandLandmarks = hr.landmarks[0];" not in source


def test_hand_selection_uses_the_survey_side_and_has_a_browser_simulation_hook():
    source = server.POSE_RUNNER_HTML
    assert 'const expectedSide = AFFECTED_SIDE === "left" ? "Left" : "Right";' in source
    assert 'URL_PARAMS.get("test_mode") === "hand_selection"' in source
    assert "window.__rehynAffectedHandTest" in source
    assert "affectedSide:AFFECTED_SIDE" in source


def test_only_selected_affected_hand_is_drawn_and_used_for_metrics():
    source = server.POSE_RUNNER_HTML
    assert "drawingUtils.drawConnectors(latestHandLandmarks, HAND_CONNECTIONS" in source
    assert "const h = latestHandLandmarks;" in source
    assert "hand_2d: hand2d" in source
    assert "hand_side: latestHandedness || null" in source
