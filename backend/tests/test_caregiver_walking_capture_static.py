import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_caregiver_walking_test")

from backend import server


def _walking_task():
    return next(task for task in server.LOWER_LIMB_TASKS_DATA if task["id"] == "L6")


def test_initial_walking_task_has_explicit_caregiver_filming_guidance():
    task = _walking_task()
    assert task["caregiver_recorded"] is True
    guidance = " ".join(task["filming_guidance"]).lower()
    for phrase in (
        "head, trunk, hips, knees, feet",
        "walking aid",
        "fixed camera",
        "walk smoothly parallel",
        "must not walk backward",
        "separate person for guarding",
        "avoid zooming",
    ):
        assert phrase in guidance


def test_walking_voice_guides_carer_before_during_and_after_walk():
    steps = {step["id"]: step for step in _walking_task()["steps"]}
    setup = steps["L6-S1"]["voice"].lower()
    walking = steps["L6-S2"]["voice"].lower()
    stopping = steps["L6-S3"]["voice"].lower()
    assert "carer or family member" in setup
    assert "whole body" in setup
    assert "walk smoothly parallel" in setup
    assert "must not walk backward" in setup
    assert "keep the phone steady" in walking
    assert "do not zoom or walk backward" in walking
    assert "head and feet visible" in stopping


def test_walking_detection_requires_full_body_visibility():
    source = server.POSE_RUNNER_HTML
    assert "function fullBodyVisibleForWalking(lm)" in source
    assert "mostVisible([11,12])" in source
    assert "mostVisible([31,32])" in source
    assert "gaitFullBodyVisibilityRatio() >= 0.75" in source
    assert 'return standing && fullBodyVisibleForWalking(landmarks);' in source
    assert "gait_full_body_visibility_ratio" in source


def test_walking_detection_supports_fixed_or_parallel_tracking_camera():
    source = server.POSE_RUNNER_HTML
    assert "const fixedCameraProgress = gaitPelvisTravelMaxRatio > 0.35;" in source
    assert "const caregiverTrackedProgress = gaitAlternationCount >= 3;" in source
    assert "(fixedCameraProgress || caregiverTrackedProgress)" in source
    assert "const bilateralLegMotion = gaitAffectedAnkleTravelMaxRatio > 0.16" in source


def test_walking_evidence_does_not_accumulate_during_voice_instructions():
    source = server.POSE_RUNNER_HTML
    assert "const gaitCaptureActive = voiceFinishedAt > 0" in source
    assert "if(gaitCaptureActive){" in source
