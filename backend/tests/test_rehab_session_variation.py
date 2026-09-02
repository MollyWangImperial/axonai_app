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
    for exercise_id in server.REHAB_RUNNER_CONFIG:
        exercise = server._exercise_by_id(exercise_id)
        assert exercise is not None
        levels = server._exercise_difficulty_levels(exercise)
        assert set(levels) == {"easy", "medium", "difficult"}
        assert server.EXERCISE_SESSION_RULES[exercise_id]["variation"]
        standard = server.EXERCISE_MOVEMENT_STANDARDS[exercise_id]
        assert standard["tracking_mode"] in {"pose", "hand"}
        assert standard["rom_steps"]
        assert standard["calibration_instruction"]
        for step in standard["rom_steps"]:
            assert set(step["targets"]) == {"easy", "medium", "difficult"}
            assert all(float(value) > 0 for value in step["targets"].values())


def test_reach_difficulty_changes_the_drawn_and_hit_test_target_geometry():
    easy = _first_work_target(server._configure_rehab_runner("ex_reach", "easy", "standard"))
    difficult = _first_work_target(server._configure_rehab_runner("ex_reach", "difficult", "standard"))

    assert easy["y"] > difficult["y"]  # Larger screen y is a lower, easier target.
    assert easy["r"] > difficult["r"]


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
    assert "trackingFrames < 8" in html
    assert 'AFFECTED_SIDE = URL_PARAMS.get("affected_side")' in html
    assert "return ok(lm[ACTIVE.wrist])" in html
    assert "NEEDS_LOWER_BODY_VIEW" in html
    assert 'getUserMedia({video:responsiveVideoSettings(640, 480),audio:false})' in html


def test_runner_pose_and_target_overlay_match_assessment_visual_geometry():
    html = server._rehab_runner_html("ex_reach", prescribed_reps=3)

    assert 'modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task"' in html
    assert 'landmarkRadius:3' in html
    assert 'connectorWidth:4' in html
    assert 'targetEdgeWidth:6' in html
    assert 'targetInnerScale:.55' in html
    assert 'holdRingScale:1.25' in html
    assert 'holdRingWidth:8' in html
    assert 'effectiveExerciseTargetRadius(sub,lm)' in html
    assert 'const R = effectiveExerciseTargetRadius(sub,lm);' in html
    assert 'const tr = effectiveExerciseTargetRadius(sub,lm)*Math.min(canvas.width,canvas.height);' in html
    assert 'sub.target.r * 1.55' not in html


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
