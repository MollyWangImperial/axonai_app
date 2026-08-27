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
        "face the camera clearly for two seconds",
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
    assert "face the camera clearly" in setup
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


def test_walking_uses_device_specific_capture_controls_instead_of_target_circles():
    source = server.POSE_RUNNER_HTML
    assert 'data-testid="walking-capture"' in source
    assert 'data-testid="walking-desktop-actions"' in source
    assert 'data-testid="walking-mobile-actions"' in source
    assert 'data-testid="walking-choose-video"' in source
    assert 'data-testid="walking-start-recording"' in source
    assert "const IS_MOBILE_CAPTURE_DEVICE" in source
    assert 'if(isWalkingTask()){\n    lapStatus.classList.add("hidden");\n    return;' in source


def test_desktop_walking_upload_keeps_identity_blocking_but_framing_advisory():
    source = server.POSE_RUNNER_HTML
    assert "async function validateWalkingVideo(file, onProgress=()=>{})" in source
    assert "durationSeconds < 6 || durationSeconds > 90" not in source
    assert "Math.min(width, height) < 360" not in source
    assert "const qualityAdvisory" in source
    assert "fullBodyVisibleForWalking(pose)" in source
    assert "if(fullBodyRatio < 0.70)" not in source
    assert "patientMatchScore < WALKING_FACE_MATCH_THRESHOLD" in source
    assert "completeUploadedWalkingTask(file, validation)" in source
    assert 'capture_source:"uploaded_walking_video"' in source


def test_desktop_video_picker_receives_the_user_gesture_directly():
    source = server.POSE_RUNNER_HTML
    assert 'id="walkingVideoInput" type="file" accept="video/*"' in source
    assert '#walkingVideoInput{position:absolute;inset:0;width:100%;height:100%;opacity:0' in source
    assert '#walkingChooseVideoBtn{pointer-events:none}' in source
    assert 'walkingVideoInput.addEventListener("click"' in source
    assert 'walkingChooseVideoBtn.addEventListener("click"' not in source
    assert 'walkingVideoInput.click()' not in source


def test_walking_video_picker_recovers_after_validation_errors():
    source = server.POSE_RUNNER_HTML
    change_handler = source[source.index('walkingVideoInput.addEventListener("change"') : source.index('walkingRecordBtn.addEventListener')]
    assert 'walkingDesktopActions.classList.add("busy")' in change_handler
    assert 'catch(error)' in change_handler
    assert 'walkingDesktopActions.classList.remove("busy")' in change_handler
    assert 'walkingVideoInput.value = ""' in change_handler


def test_walking_upload_checks_same_patient_locally_before_accepting_video():
    source = server.POSE_RUNNER_HTML
    for marker in (
        "function normalizedFaceAppearance(source, pose)",
        "function faceSignatureSimilarity(reference, candidate)",
        "function capturePatientFaceReference(source, pose",
        "const identityTimes = Array.from(new Set(",
        "const patientMatchScore = medianValue(identityScores);",
        "patientMatchScore < WALKING_FACE_MATCH_THRESHOLD",
        "samePatientConfirmed:true",
        "walking_same_patient_confirmed",
        'URL_PARAMS.get("test_mode") === "walking_identity"',
    ):
        assert marker in source
    assert "patientFaceReferenceSamples" in source
    assert "body:patientFaceReference" not in source


def test_walking_upload_rejects_oversize_early_and_reports_real_progress():
    source = server.POSE_RUNNER_HTML
    assert "file.size || 0) > 35 * 1024 * 1024" in source
    assert "function uploadTaskVideoToCloud" in source
    assert "request.upload.onprogress" in source
    assert "Promise.all([localSavePromise, cloudSavePromise])" in source
    assert "Saving securely (${percent}%)" in source


def test_walking_validator_is_initialized_before_the_video_is_selected():
    source = server.POSE_RUNNER_HTML
    assert "let walkingVideoValidatorPromise = null;" in source
    assert "async function getWalkingVideoValidator()" in source
    assert "function preloadWalkingVideoValidator()" in source
    assert "preloadWalkingVideoValidator();" in source
    assert "validator = await getWalkingVideoValidator();" in source
    validation = source[source.index("async function validateWalkingVideo") : source.index("async function completeUploadedWalkingTask")]
    assert 'PoseLandmarker.createFromOptions' not in validation
    assert 'validator.close()' not in validation


def test_phone_walking_capture_uses_an_explicit_record_button_and_rear_camera_when_available():
    source = server.POSE_RUNNER_HTML
    assert "walkingRecordBtn.addEventListener" in source
    assert 'facingMode:{ideal:"environment"}' in source
    assert 'type:"walking_recording_started"' in source
    assert 'device_mode:"mobile"' in source


def test_camera_switch_waits_for_a_real_frame_before_pose_detection_resumes():
    source = server.POSE_RUNNER_HTML
    assert "async function waitForWalkingCameraFrame" in source
    assert "video.videoWidth > 0 && video.videoHeight > 0" in source
    assert "walkingCameraSwitching = true" in source
    assert "walkingCameraSwitching = false" in source
    assert "const cameraFrameReady = !walkingCameraSwitching" in source
    assert "if(cameraFrameReady && landmarker" in source
    assert "if(cameraFrameReady && handLandmarker" in source
