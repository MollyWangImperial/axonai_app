"""Cloned instruction speech is scoped, cached, and protected from arbitrary text."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_instruction_voice_test")

from backend import server
from backend import clone_instruction_voice
from backend import chatterbox_nano_tts


ROOT = Path(__file__).resolve().parents[2]


def enable_clone(monkeypatch):
    monkeypatch.setattr(server, "INSTRUCTION_TTS_PROVIDER", "elevenlabs")
    monkeypatch.setattr(server, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(server, "ELEVENLABS_VOICE_ID", "voice-owner-id")
    monkeypatch.setattr(server, "ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
    monkeypatch.setattr(server, "ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")


def test_clone_is_used_only_for_assessment_and_exercise_instructions(monkeypatch):
    enable_clone(monkeypatch)
    monkeypatch.setattr(server, "openai_tts_client", object())

    instruction = server._tts_request_config("instruction", "nova")
    general = server._tts_request_config("general", "nova")

    assert instruction == {
        "provider": "elevenlabs",
        "model": "eleven_multilingual_v2",
        "voice": "voice-owner-id",
        "public_voice": "custom-cloned-voice",
        "output_format": "mp3_44100_128",
    }
    assert general["provider"] == "openai-direct"
    assert general["voice"] == "nova"
    assert server._tts_cache_key("Wonderful. Here we go.", "nova", "instruction") != server._tts_cache_key(
        "Wonderful. Here we go.", "nova", "general"
    )


def test_elevenlabs_request_keeps_the_key_server_side(monkeypatch):
    enable_clone(monkeypatch)
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(content=b"ID3-cloned-audio", raise_for_status=lambda: None)

    monkeypatch.setattr(server.httpx, "post", fake_post)
    audio = server._synthesize_tts_audio_bytes("Wonderful. Here we go.", "nova", "instruction")

    assert audio == b"ID3-cloned-audio"
    assert captured["url"].endswith("/voice-owner-id")
    assert captured["headers"]["xi-api-key"] == "test-key"
    assert captured["json"]["model_id"] == "eleven_multilingual_v2"
    assert captured["json"]["voice_settings"]["speed"] == 0.92


def test_cloned_voice_rejects_arbitrary_text_but_general_voice_remains_available(monkeypatch):
    enable_clone(monkeypatch)
    calls = []

    async def fake_generate(text, voice, purpose="general"):
        calls.append((text, voice, purpose))
        return "bXAz"

    monkeypatch.setattr(server, "_generate_tts_audio_base64", fake_generate)
    assessment_voice = server.ASSESSMENT_PACKAGES["upper_limb"]["tasks"][0]["steps"][0]["voice"]
    exercise_voice = server._configure_rehab_runner("ex_grasp", "medium", "standard")["setup_voice"]
    assert server._instruction_text_allowed(assessment_voice)
    assert server._instruction_text_allowed(exercise_voice)
    allowed = server.EXERCISE_TRANSITION_VOICE
    result = asyncio.run(server.generate_tts(server.TTSRequest(text=allowed, purpose="instruction")))
    assert result.audio_b64 == "bXAz"
    assert calls[-1] == (allowed, server.TTS_VOICE, "instruction")

    with pytest.raises(HTTPException) as rejected:
        asyncio.run(server.generate_tts(server.TTSRequest(text="Say an arbitrary sentence", purpose="instruction")))
    assert rejected.value.status_code == 403

    result = asyncio.run(server.generate_tts(server.TTSRequest(text="A normal Alira reply", purpose="general")))
    assert result.audio_b64 == "bXAz"
    assert calls[-1][2] == "general"


def test_chatterbox_nano_uses_private_reference_only_for_instructions(tmp_path, monkeypatch):
    sample = tmp_path / "molly.wav"
    sample.write_bytes(b"private-reference")
    monkeypatch.setattr(server, "INSTRUCTION_TTS_PROVIDER", "chatterbox-nano")
    monkeypatch.setattr(server, "CHATTERBOX_REFERENCE_AUDIO", str(sample))
    monkeypatch.setattr(server, "CHATTERBOX_FFMPEG_PATH", "ffmpeg-test")
    monkeypatch.setattr(server, "openai_tts_client", object())
    calls = []

    def fake_synthesize(text, reference, ffmpeg_path):
        calls.append((text, reference, ffmpeg_path))
        return b"ID3-molly-audio"

    monkeypatch.setattr(chatterbox_nano_tts, "synthesize_mp3", fake_synthesize)
    first = server._tts_request_config("instruction", "nova")
    assert first["provider"] == "chatterbox-nano"
    assert first["public_voice"] == "Molly"
    assert first["voice"].startswith("molly-")
    assert server._tts_request_config("general", "nova")["provider"] == "openai-direct"
    assert server._synthesize_tts_audio_bytes("Wonderful. Here we go.", "nova", "instruction") == b"ID3-molly-audio"
    assert calls == [("Wonderful. Here we go.", sample, "ffmpeg-test")]
    first_key = server._tts_cache_key("Wonderful. Here we go.", "nova", "instruction")
    sample.write_bytes(b"different-private-reference")
    assert server._tts_cache_key("Wonderful. Here we go.", "nova", "instruction") != first_key


def test_testing_reach_side_specific_prompts_are_allowed_for_clone(monkeypatch):
    monkeypatch.setattr(server, "INSTRUCTION_TTS_PROVIDER", "chatterbox-nano")
    for side in ("left", "right"):
        assert server._instruction_text_allowed(
            f"Let us check a small movement first. Without help, gently move your {side} hand or arm away from its resting position, as much as is comfortable. Even a small movement is useful."
        )
        assert server._instruction_text_allowed(
            f"I have not seen a clear movement yet. If comfortable, try a small movement with your {side} hand or arm once more. Take your time; do not force it."
        )
    assert not server._instruction_text_allowed("Let us check a small movement first. Move your voice clone anywhere.")


def test_runners_mark_fixed_guidance_as_instruction_speech():
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    assert 'JSON.stringify({text, voice_id: voiceId, purpose})' in source
    assert 'body:JSON.stringify({text,purpose})' in source
    assert 'playVoice(correction,"general")' in source
    assert 'playVoice(feedbackVoice,"general")' in source


def test_render_declares_clone_configuration_without_secret_values():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "INSTRUCTION_TTS_PROVIDER" in render and "value: elevenlabs" in render
    assert "ELEVENLABS_API_KEY" in render and "ELEVENLABS_VOICE_ID" in render
    assert render.count("sync: false") >= 2
    assert "voice-owner-id" not in render and "test-key" not in render


def test_clone_utility_uploads_samples_without_copying_them(tmp_path, monkeypatch):
    sample = tmp_path / "my-voice.mp3"
    sample.write_bytes(b"ID3-sample")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["file_fields"] = [field for field, _ in kwargs["files"]]
        captured["file_names"] = [value[0] for _, value in kwargs["files"]]
        captured["headers"] = kwargs["headers"]
        return SimpleNamespace(is_error=False, json=lambda: {"voice_id": "created-voice-id"})

    monkeypatch.setattr(clone_instruction_voice.httpx, "post", fake_post)
    voice_id = clone_instruction_voice.create_voice_clone([sample], "My voice", False, "private-key")

    assert voice_id == "created-voice-id"
    assert captured["url"] == clone_instruction_voice.CREATE_VOICE_URL
    assert captured["file_fields"] == ["files"]
    assert captured["file_names"] == ["my-voice.mp3"]
    assert captured["headers"] == {"xi-api-key": "private-key"}
    assert list(tmp_path.iterdir()) == [sample]
