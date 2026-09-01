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


def test_every_guided_exercise_defines_three_levels_and_an_alternate_variation():
    assert set(server.REHAB_RUNNER_CONFIG).issubset(server.EXERCISE_SESSION_RULES)
    for exercise_id in server.REHAB_RUNNER_CONFIG:
        exercise = server._exercise_by_id(exercise_id)
        assert exercise is not None
        levels = server._exercise_difficulty_levels(exercise)
        assert set(levels) == {"easy", "medium", "difficult"}
        assert server.EXERCISE_SESSION_RULES[exercise_id]["variation"]


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


def test_demo_exercises_use_the_same_real_runners_and_level_definitions():
    options = asyncio.run(server.rehab_session_options("demo_supported_reach,demo_hand_opening"))
    by_id = {item["exercise_id"]: item for item in options["exercises"]}

    assert set(by_id) == {"demo_supported_reach", "demo_hand_opening"}
    assert by_id["demo_supported_reach"]["levels"]["difficult"]["adjustment"] == server.EXERCISE_SESSION_RULES["ex_reach"]["difficult"]
    assert by_id["demo_hand_opening"]["alternate_variation"] == server.EXERCISE_SESSION_RULES["ex_handopen"]["variation"]
    assert server._configure_rehab_runner("demo_supported_reach", "medium", "standard")["pose_mode"] == server.REHAB_RUNNER_CONFIG["ex_reach"]["pose_mode"]
