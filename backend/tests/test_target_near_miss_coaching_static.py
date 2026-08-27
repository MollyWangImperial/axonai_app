import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_target_near_miss_test")

from backend import server


def test_near_miss_requires_intentional_close_sustained_attempt():
    source = server.POSE_RUNNER_HTML
    assert "const NEAR_MISS_DWELL_MS = 900;" in source
    assert "const NEAR_MISS_COOLDOWN_MS = 7000;" in source
    assert "distance <= nearLimit" in source
    assert "!!intentional" in source
    assert "targetAttemptMaxDisplacement >= movementThreshold" in source
    assert "const movementGateAttempt = !isHandTask() && arrivedAfterMovement;" in source
    assert "if(now - nearMissStartedAt < NEAR_MISS_DWELL_MS) return;" in source


def test_random_movement_and_walking_do_not_trigger_circle_coaching():
    source = server.POSE_RUNNER_HTML
    assert "if(!qualifiesAsNearTargetAttempt(distance, radius, intentional)) return null;" in source
    assert "if(!point) return null;" in source
    assert "if(!step || isLowerTask() || isBalanceTask()) return null;" in source
    assert "if(!correctionVoicePlaying) handleTargetNearMiss(landmarks, now);" in source


def test_near_miss_coaching_reports_reason_and_specific_correction():
    source = server.POSE_RUNNER_HTML
    for reason in (
        "just_outside_circle",
        "movement_gate_not_met",
        "hand_landmarks_not_visible",
        "hand_not_open",
        "hand_not_closed",
        "pinch_not_detected",
        "both_wrists_required",
        "cup_grasp_not_detected",
        "cup_not_centered",
        "cup_release_not_detected",
    ):
        assert reason in source
    assert 'postRN({type:"target_near_miss", ...diagnostic});' in source
    assert "await playVoice(correction);" in source
    assert "target_near_miss_count: nearMissEvents.length" in source
    assert "target_near_miss_events: nearMissEvents.slice()" in source


def test_coaching_is_limited_and_does_not_compete_with_target_detection():
    source = server.POSE_RUNNER_HTML
    assert "const NEAR_MISS_MAX_COACHING_PER_STEP = 2;" in source
    assert "if(correctionVoicePlaying || nearMissCoachingCount >= NEAR_MISS_MAX_COACHING_PER_STEP) return;" in source
    assert "const inTarget = correctionVoicePlaying ? false : checkTarget(landmarks);" in source
    assert "voiceFinishedAt = performance.now();" in source
