from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "backend" / "server.py"
TASK_INTRO = ROOT / "frontend" / "app" / "task-intro.tsx"


def test_advanced_marker_gate_runner_contract():
    html_source = SERVER.read_text(encoding="utf-8")
    required_tokens = [
        "advancedMarkerGate",
        "AXONAI_MARKER_STORE_URL",
        "detectAxonAIMarker",
        "object_center",
        "object_visibility",
        "object_stability",
        "objectHandCoupling",
        "releaseDelayMs",
        "objectHandSeparation",
        "placementEndpointError",
        "handDetectionRate",
        "markerDetectionRate",
        "markerCenterJitter",
        "MIN_RUNTIME_FPS",
        "Next: advanced grasp-release task",
        "Order AxonAI marker",
        "I have an AxonAI marker and placed it on the object",
        "Do basic hand tasks first",
        "I cannot see the marker clearly yet",
        "Turn the marker toward the camera",
        "Not enough data. Please adjust the marker and lighting, then try again.",
    ]
    missing = [token for token in required_tokens if token not in html_source]
    assert not missing


def test_advanced_marker_tasks_keep_seven_task_contract():
    html_source = SERVER.read_text(encoding="utf-8")
    assert '"id": "T4"' in html_source
    assert '"id": "T5"' in html_source
    assert '"id": "H5"' in html_source
    assert '"id": "H6"' in html_source
    assert "HAND_TASKS_DATA" in html_source
    assert "ASSESSMENT_PACKAGES" in html_source
    assert 'package: str = "upper_limb"' in html_source
    assert 'ASSESSMENT_PACKAGE = URL_PARAMS.get("package") || "upper_limb"' in html_source
    assert 'START_TASK_ID = URL_PARAMS.get("start_task") || ""' in html_source
    assert "tasks.findIndex((task) => task.id === START_TASK_ID)" in html_source
    assert "HAND_METRIC_NAMES" in html_source
    assert "measures.some((name) => HAND_METRIC_NAMES.has(name))" in html_source
    assert "const POSE_SCAN_INTERVAL_MS = 0" in html_source
    assert "const HAND_SCAN_INTERVAL_MS = 0" in html_source
    assert "async function setupTrackingModels()" in html_source
    assert 'if(ASSESSMENT_PACKAGE === "hand"){' in html_source
    assert 'await setupPose();' in html_source
    assert 'await setupHand();' in html_source
    assert '"id": "H1-S1"' in html_source
    assert '"landmark": "WRIST"' in html_source
    assert "Please do not open your hand yet" in html_source
    assert "Now slowly open your fingers" in html_source
    assert '"id": "H1-S2"' in html_source
    assert '"hold_ms": 1300' in html_source
    assert '"hold_ms": 4500' in html_source
    assert "Slowly close your fingers into a fist. Take your time" in html_source
    assert "fistClosureScore" in html_source
    assert "fistCloseReadyObserved" in html_source
    assert "fistClosureMinScore" in html_source
    assert "fistClosingStarted" in html_source
    assert 'step.id === "H2-S2"' in html_source
    assert "fistClosureScore < 0.86" in html_source
    assert "closureDelta > 0.035" in html_source
    assert "closure_completeness" in html_source
    assert "measures.includes(\"closure_completeness\")" in html_source
    assert "fistClosureScore > 0.45" in html_source
    assert "fist_closure_score" in html_source
    assert "palmFacingScore" in html_source
    assert "latestHandedness" in html_source
    assert "function anatomicalHandedness(rawCategory)" in html_source
    assert 'rawCategory === "Right"' in html_source
    assert "function selectAffectedHandDetection" in html_source
    assert "sideLandmarks(latestPoseLandmarks, AFFECTED_SIDE).wrist" in html_source
    assert "function palmProjectionEvidence(h)" in html_source
    assert "Math.abs(signedPlaneFacing)" in html_source
    assert "projectedAreaRatio" in html_source
    assert "const angleDeg = (a,b,c)" in html_source
    assert "const handScale = Math.max(0.01, palmWidth, palmHeight * 0.9)" in html_source
    assert "fingerStraightnessScore" in html_source
    assert "fingertipDistanceScore" in html_source
    assert "thumbIndexSpreadScore" in html_source
    assert 'step.id === "H1-S1"' in html_source
    assert "PALM_FACING_THRESHOLD" in html_source
    assert "palmFacingScore > PALM_FACING_THRESHOLD" in html_source
    assert "handOpenScore < 0.72" in html_source
    assert 'step.id !== "H1-S2" || palmFacingScore > PALM_FACING_THRESHOLD' in html_source
    assert "const openThreshold = 0.45" in html_source
    assert "Palm + open" in html_source
    assert "voiceAudioCache" in html_source
    assert "voiceAudioInflight" in html_source
    assert "function prefetchUpcomingVoice()" in html_source
    assert "prefetchUpcomingVoice();" in html_source
    assert 'package_id: ASSESSMENT_PACKAGE' in html_source
    assert "taskResults.filter(Boolean)" in html_source
    assert '"id": "H1-S3"' in html_source
    assert '"r": 0.20' in html_source
    assert "palm_facing_score" in html_source
    assert "responsiveVideoSettings(640, 480)" in html_source
    assert "#cameraFrame video,#cameraFrame canvas{position:absolute;inset:0;width:100%;height:100%" in html_source
    assert "object-fit:cover" not in html_source
    assert "minTrackingConfidence: 0.7" in html_source
    assert "radius:1.4" in html_source
    assert "function activeHandPoint()" in html_source
    assert "drawingUtils.drawConnectors(latestHandLandmarks, HAND_CONNECTIONS" in html_source
    assert html_source.count('"advanced_marker_required": True') == 4
    assert '"recommended_objects": ["empty plastic cup", "soft ball", "foam cylinder", "small paper box"]' in html_source


def test_initial_intro_stays_guided_without_package_choice():
    intro_source = TASK_INTRO.read_text(encoding="utf-8")
    assert 'const packageId: AssessmentPackageId = "initial"' in intro_source
    assert "launch your next guided task automatically" in intro_source
    assert "PACKAGE_OPTIONS" not in intro_source
    assert "task-package-card-${option.id}" not in intro_source
