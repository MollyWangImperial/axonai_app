import asyncio
import os
import sys
import types
import wave
from pathlib import Path

from starlette.requests import Request


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_hundred_point_test")

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
from backend.encouragement import compute_rewards


ROOT = Path(__file__).resolve().parents[2]


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/users/rewards", "headers": []})


def _hundred_point_activities():
    return [
        {
            "exercise_id": f"exercise-{index}",
            "completed_at": f"2026-09-0{index + 1}T12:00:00+00:00",
            "completed_reps": 5,
            "quality_reps": 5,
        }
        for index in range(4)
    ]


def test_reward_ladder_earns_the_first_medal_at_100_points():
    rewards = compute_rewards(_hundred_point_activities(), [], {})

    assert rewards["points"] == 100
    assert rewards["medals"][0] == {
        "id": "first_100_points",
        "name": "100-Point Medal",
        "threshold": 100,
        "earned": True,
        "progress": 1.0,
    }


def test_acknowledging_earned_milestone_persists_to_the_account(monkeypatch):
    saved = {}

    async def signed_in_user(_headers):
        return {"id": "patient-100", "reward_milestones_acknowledged": []}

    async def activities(_user_id):
        return _hundred_point_activities()

    async def no_check_ins(_user_id):
        return []

    async def save_fields(user, fields, **_kwargs):
        saved.update(fields)
        return {**user, **fields}

    monkeypatch.setattr(server, "_user_from_header", signed_in_user)
    monkeypatch.setattr(server, "_care_activities_for_user", activities)
    monkeypatch.setattr(server, "_care_check_ins_for_user", no_check_ins)
    monkeypatch.setattr(server, "_save_user_fields", save_fields)

    response = asyncio.run(server.acknowledge_reward_milestone("first_100_points", _request()))

    assert response == {"ok": True, "milestone_id": "first_100_points", "celebrated": True}
    assert saved["reward_milestones_acknowledged"] == ["first_100_points"]


def test_home_celebration_is_animated_audible_and_has_no_music_panel():
    component = (ROOT / "frontend" / "src" / "components" / "HundredPointCelebration.tsx").read_text(encoding="utf-8")
    home = (ROOT / "frontend" / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    server_source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")

    assert 'testID="hundred-point-celebration"' in component
    assert "useAudioPlayer" in component and "celebrationFanfare" in component
    assert "Animated.spring(medalScale" in component
    assert "Music playing" not in component
    assert "claimHundredPointCelebration" in home
    assert "reward_milestone_seen_v1" in home
    assert "/api/users/rewards/milestones/${milestone.id}/acknowledge" in home
    assert 'visible={Boolean(hundredPointAward)}' in home
    assert 'visible={!hundredPointAward && showMedal}' in home
    assert 'event={hundredPointAward ? null : celebration}' in home
    assert '"reward_milestones_acknowledged"' in server_source


def test_celebration_assets_are_bundled_and_audio_is_brief():
    medal = ROOT / "frontend" / "assets" / "images" / "rewards" / "100-point-medal.png"
    fanfare = ROOT / "frontend" / "assets" / "audio" / "rewards" / "100-point-fanfare.wav"

    assert medal.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with wave.open(str(fanfare), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    assert 2.5 <= duration <= 4.0
