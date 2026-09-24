"""The Testing clone is finite, private and tied to a signed-in account."""

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_testing_reach_voice_test")

from backend import testing_reach_voice as voice
from backend.testing_reach_voice_lines import LINES


def test_every_t1_instruction_is_in_the_private_bundle_allowlist():
    from backend import server

    runtime = (Path(__file__).resolve().parents[1] / "testing_reach_flow.js").read_text(encoding="utf-8")
    assert all(step["voice"] in LINES for step in server.TASKS_DATA[0]["steps"])
    assert server.TASKS_DATA[0]["id"] == "T1"
    assert all(line in server.POSE_RUNNER_HTML for line in LINES[:2])
    assert all(line in runtime for line in LINES[6:12])


def _request() -> Request:
    return Request({"type": "http", "headers": [(b"x-user-id", b"u_test")]})


def test_private_bundle_requires_every_authored_cue(tmp_path, monkeypatch):
    audio = b"ID3" + b"a" * 1100
    entries = {hashlib.sha256(line.encode()).hexdigest(): base64.b64encode(audio).decode() for line in LINES}
    path = tmp_path / "molly.json"
    path.write_text(json.dumps({"version": 1, "voice": "Molly", "entries": entries}), encoding="ascii")
    monkeypatch.setenv("TESTING_REACH_VOICE_BUNDLE", str(path))
    voice._bundle.cache_clear()
    try:
        assert asyncio.run(voice.voice_health())["available_cues"] == len(LINES)
        del entries[next(iter(entries))]
        path.write_text(json.dumps({"version": 1, "voice": "Molly", "entries": entries}), encoding="ascii")
        voice._bundle.cache_clear()
        assert asyncio.run(voice.voice_health())["ready"] is False
    finally:
        voice._bundle.cache_clear()


def test_cues_require_sign_in_and_exact_authored_text(monkeypatch):
    audio = base64.b64encode(b"ID3" + b"a" * 1100).decode()
    monkeypatch.setattr(voice, "_bundle", lambda: {hashlib.sha256(LINES[0].encode()).hexdigest(): audio})

    async def no_user(_request):
        return None

    monkeypatch.setattr(voice.server, "_task_video_user", no_user)
    with pytest.raises(HTTPException) as unauthenticated:
        asyncio.run(voice.voice_cue(_request(), voice.CueRequest(text=LINES[0])))
    assert unauthenticated.value.status_code == 401

    async def signed_in(_request):
        return {"id": "u_test"}

    monkeypatch.setattr(voice.server, "_task_video_user", signed_in)
    with pytest.raises(HTTPException) as arbitrary:
        asyncio.run(voice.voice_cue(_request(), voice.CueRequest(text="Unapproved speech")))
    assert arbitrary.value.status_code == 403
    result = asyncio.run(voice.voice_cue(_request(), voice.CueRequest(text=LINES[0])))
    assert result == {"audio_b64": audio, "text": LINES[0]}


def test_existing_private_clone_provider_can_serve_an_authored_cue(monkeypatch):
    async def signed_in(_request):
        return {"id": "u_test"}

    async def clone_speech(text, _voice, purpose):
        assert (text, purpose) == (LINES[2], "instruction")
        return "SUQzYXVkaW8="

    monkeypatch.setattr(voice.server, "_task_video_user", signed_in)
    monkeypatch.setattr(voice, "_bundle", lambda: {})
    monkeypatch.setattr(voice.server, "_instruction_clone_ready", lambda: True)
    monkeypatch.setattr(voice.server, "INSTRUCTION_TTS_PROVIDER", "elevenlabs")
    monkeypatch.setattr(voice.server, "_generate_tts_audio_base64", clone_speech)
    assert asyncio.run(voice.voice_cue(_request(), voice.CueRequest(text=LINES[2])))["audio_b64"] == "SUQzYXVkaW8="
    assert asyncio.run(voice.voice_health())["provider"] == "elevenlabs"
