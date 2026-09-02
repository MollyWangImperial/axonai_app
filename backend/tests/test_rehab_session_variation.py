import os
import sys
import types
import asyncio

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_rehab_session_test")

if "emergentintegrations.llm.chat" not in sys.modules:
    emergent = types.ModuleType("emergentintegrations")
    llm = types.ModuleType("emergentintegrations.llm")
    chat = types.ModuleType("emergentintegrations.llm.chat")

    class _UnavailableChatDependency:
        def __init__(self, *args, **kwargs):
            pass

    chat.LlmChat = _UnavailableChatDependency
    chat.UserMessage = _UnavailableChatDependency
    sys.modules.setdefault("emergentintegrations", emergent)
    sys.modules.setdefault("emergentintegrations.llm", llm)
    sys.modules.setdefault("emergentintegrations.llm.chat", chat)

from backend import server


def _first_work_target(config):
    return next(
        step["target"]
        for step in config["cycle"]
        if isinstance(step.get("target"), dict) and float(step["target"].get("y", 0.5)) < 0.70
    )


def test_repetition_average_uses_every_scored_repetition():
    scores = server._normalise_repetition_scores([72, 84, 90])

    assert scores == [72.0, 84.0, 90.0]
    assert server._average_repetition_scores(scores) == 82.0


def test_every_guided_exercise_defines_three_levels_and_an_alternate_variation():
    assert set(server.REHAB_RUNNER_CONFIG).issubset(server.EXERCISE_SESSION_RULES)
    assert set(server.REHAB_RUNNER_CONFIG) == set(server.EXERCISE_MOVEMENT_STANDARDS)
    assert set(server.REHAB_RUNNER_CONFIG) == set(server.EXERCISE_COACHING_PROFILES)
    for exercise_id in server.REHAB_RUNNER_CONFIG:
        exercise = server._exercise_by_id(exercise_id)
        assert exercise is not None
        levels = server._exercise_difficulty_levels(exercise)
        assert set(levels) == {"easy", "medium", "difficult"}
        assert server.EXERCISE_SESSION_RULES[exercise_id]["variation"]
        standard = server.EXERCISE_MOVEMENT_STANDARDS[exercise_id]
        profile = server.EXERCISE_COACHING_PROFILES[exercise_id]
        assert standard["tracking_mode"] in {"pose", "hand"}
        assert standard["rom_steps"]
        assert standard["calibration_instruction"]
        assert profile["training_focus"]
        assert profile["repetition_definition"]
        assert profile["measurement_limit"]
        for step in standard["rom_steps"]:
            assert set(step["targets"]) == {"easy", "medium", "difficult"}
            assert all(float(value) > 0 for value in step["targets"].values())
            assert profile["rom_cues"][step["id"]].startswith("On the next repetition") or "next repetition" in profile["rom_cues"][step["id"]].lower()
        for compensation in standard["compensations"]:
            assert profile["compensation_labels"][compensation["id"]]
            assert compensation["correction"]


def test_reach_difficulty_changes_the_drawn_and_hit_test_target_geometry():
    easy = _first_work_target(server._configure_rehab_runner("ex_reach", "easy", "standard"))
    difficult = _first_work_target(server._configure_rehab_runner("ex_reach", "difficult", "standard"))

    assert easy["y"] > difficult["y"]  # Larger screen y is a lower, easier target.
    assert easy["r"] > difficult["r"]


def test_supported_reach_return_uses_the_assessment_lap_calibration_contract():
    for level in ("easy", "medium", "difficult"):
        configured = server._configure_rehab_runner("ex_reach", level, "standard")
        lap_step = next(step for step in configured["cycle"] if step["caption"] == "Return to lap")
        assert lap_step["target"]["landmark"] == "LAP_DYNAMIC"
        assert lap_step["target"]["r"] == 0.10

    html = server._rehab_runner_html("ex_reach", prescribed_reps=3)
    for marker in (
        "function exerciseLapTargetCandidateStatus(lm)",
        "CALIBRATION_CONTRACT.lap_minimum_samples",
        "CALIBRATION_CONTRACT.lap_minimum_duration_ms",
        "LAP_CALIBRATION_STABLE_RATIO",
        "now-exerciseLapTargetCalibration.lastCandidateAt <= 900",
        "affected.wrist.x",
        "affected.wrist.y",
        "return exerciseLapTarget || exerciseLapTargetCalibration.target || sub.target;",
        "Math.hypot(affectedWrist.x-t.x,affectedWrist.y-t.y) < R",
        "lap_target:exerciseLapTarget",
        "lap_target_radius:exerciseLapTargetRadius",
        "window.__rehynExerciseLapCalibrationTest",
    ):
        assert marker in html
    assert "exerciseLandmarkIsInFrame(affected.knee" not in html
    calibration = html[html.index("function updateCalibration(lm,handLm)") : html.index("async function completeCalibration()")]
    assert calibration.index("updateExerciseLapTargetCalibration(lm,performance.now());") < calibration.index("const quality=trackingQuality")


def test_every_completed_repetition_shows_and_speaks_a_one_point_celebration():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=3)

    assert 'id="fbReward"' in html
    assert 'role="status" aria-live="polite"' in html
    assert "&#11088;" in html
    assert "+1 point" in html
    assert "Great repetition!" in html
    assert "Great repetition. You earned one point." in html
    assert 'URL_PARAMS.get("test_mode") === "rep_feedback"' in html


def test_alternate_variation_changes_the_actual_target_path():
    standard = _first_work_target(server._configure_rehab_runner("ex_grasp", "medium", "standard"))
    alternate = _first_work_target(server._configure_rehab_runner("ex_grasp", "medium", "alternate"))

    assert alternate["x"] == round(1 - standard["x"], 3)


def test_supervised_difficulty_never_removes_support_or_guarding():
    exercise = server._exercise_by_id("ex_supported_stand")
    assert exercise is not None
    difficult_dose = server._difficulty_dose(exercise, "difficult")
    difficult_runner = server._configure_rehab_runner("ex_supported_stand", "difficult", "alternate")

    assert difficult_dose["sets"] == exercise.sets
    assert difficult_dose["reps"] == exercise.reps + 1
    assert "same fixed support" in difficult_runner["setup_voice"]
    assert "guarding" in difficult_runner["setup_voice"]


def test_runner_html_carries_the_selected_level_and_variation():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=7, difficulty="difficult", variation="alternate")

    assert '"difficulty": "difficult"' in html
    assert '"variation": "alternate"' in html
    assert '"reps": 7' in html
    assert '"movement_standard"' in html
    assert '"target_deg": 75.0' in html


def test_runner_calibrates_scores_rom_and_uses_conservative_compensation_rules():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=3, difficulty="medium", variation="standard")

    assert 'data-testid="exercise-calibration"' in html
    assert "#calibration{position:absolute" in html
    assert "updateCalibration" in html
    assert "repRomDetails" in html
    assert "achieved_deg" in html
    assert "confirmedCompensations" in html
    assert "hits/eligible" in html
    assert "trackingFrames < SCORING_MIN_FRAMES" in html
    assert 'AFFECTED_SIDE = URL_PARAMS.get("affected_side")' in html
    assert "return ok(lm[ACTIVE.wrist])" in html
    assert "NEEDS_LOWER_BODY_VIEW" in html
    assert 'getUserMedia({video:responsiveVideoSettings(640, 480),audio:false})' in html


def test_runner_pose_and_target_overlay_match_assessment_visual_geometry():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=3)

    assert 'modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task"' in html
    assert server.EXERCISE_OVERLAY_STYLE["keypoint_color"] in html
    assert 'landmarkRadius:Number(OVERLAY_STYLE.keypoint_radius_px)||3' in html
    assert 'connectorWidth:Number(OVERLAY_STYLE.connector_width_px)||4' in html
    assert 'targetEdgeWidth:Number(OVERLAY_STYLE.target_edge_width_px)||6' in html
    assert 'targetInnerScale:Number(OVERLAY_STYLE.target_inner_scale)||.55' in html
    assert 'holdRingScale:Number(OVERLAY_STYLE.hold_ring_scale)||1.25' in html
    assert 'holdRingWidth:Number(OVERLAY_STYLE.hold_ring_width_px)||8' in html
    assert 'drawLandmarks(handLm,{color:ASSESSMENT_OVERLAY_STYLE.landmarkColor,radius:ASSESSMENT_OVERLAY_STYLE.landmarkRadius})' in html
    assert 'effectiveExerciseTargetRadius(sub,lm)' in html
    assert 'const R = effectiveExerciseTargetRadius(sub,lm);' in html
    assert 'const tr = effectiveExerciseTargetRadius(sub,lm)*Math.min(canvas.width,canvas.height);' in html
    assert 'sub.target.r * 1.55' not in html


def test_rehab_calibration_is_saved_once_and_reused_by_session_id():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=3)

    assert 'URL_PARAMS.get("rehab_session_id")' in html
    assert "function rehabCalibrationStorageKey()" in html
    assert "function loadSessionCalibration()" in html
    assert "function saveSessionCalibration()" in html
    assert "saveSessionCalibration();" in html
    assert 'type:"exercise_calibration_reused"' in html
    assert "if(sessionCalibration){" in html
    assert "baselineMetrics={...sessionCalibration.baseline_metrics};" in html


def test_every_configured_runner_exposes_the_shared_calibration_scoring_and_style_contracts():
    for exercise_id in server.REHAB_RUNNER_CONFIG:
        configured = server._configure_rehab_runner(exercise_id, "medium", "standard")
        standard = configured["movement_standard"]
        assert configured["calibration_contract"] == server.EXERCISE_CALIBRATION_CONTRACT
        assert configured["overlay_style"] == server.EXERCISE_OVERLAY_STYLE
        assert configured["scoring_method"] == server.EXERCISE_SCORING_METHOD
        assert standard["training_focus"]
        assert standard["repetition_definition"]
        assert standard["measurement_limit"]
        assert all(step["coaching_cue"] for step in standard["rom_steps"])
        assert all(rule["label"] for rule in standard["compensations"])


def test_voice_confirmation_has_openai_transcription_fallback():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=2)

    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in html
    assert "MediaRecorder" in html
    assert 'API_BASE+"/stt/transcribe"' in html
    assert "isAdvancePhrase" in html
    assert "don t|do not|stop|wait" in html
    assert "void confirmAndContinue()" in html


def test_demo_exercises_use_the_same_real_runners_and_level_definitions():
    options = asyncio.run(server.rehab_session_options("demo_supported_reach,demo_hand_opening"))
    by_id = {item["exercise_id"]: item for item in options["exercises"]}

    assert set(by_id) == {"demo_supported_reach", "demo_hand_opening"}
    assert by_id["demo_supported_reach"]["levels"]["difficult"]["adjustment"] == server.EXERCISE_SESSION_RULES["ex_reach"]["difficult"]
    assert by_id["demo_hand_opening"]["alternate_variation"] == server.EXERCISE_SESSION_RULES["ex_handopen"]["variation"]
    assert server._configure_rehab_runner("demo_supported_reach", "medium", "standard")["pose_mode"] == server.REHAB_RUNNER_CONFIG["ex_reach"]["pose_mode"]
