"""Spoken instruction lines are generated once, off the event loop, and reused."""

import asyncio
import os
import threading
from types import SimpleNamespace

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_tts_cache_test")

from backend import server


class _FakeSpeech:
    def __init__(self):
        self.calls = 0
        self.threads = []

    def create(self, **kwargs):
        self.calls += 1
        self.threads.append(threading.current_thread())
        return SimpleNamespace(read=lambda: f"mp3:{kwargs['voice']}:{kwargs['input']}".encode("utf-8"))


def _fake_client():
    speech = _FakeSpeech()
    return SimpleNamespace(audio=SimpleNamespace(speech=speech)), speech


def test_repeated_and_concurrent_requests_for_a_line_generate_it_once(tmp_path, monkeypatch):
    client, speech = _fake_client()
    monkeypatch.setattr(server, "openai_tts_client", client)
    monkeypatch.setattr(server, "TTS_CACHE_DIR", tmp_path / "tts")
    server._tts_memory_cache.clear()
    server._tts_inflight.clear()

    async def run():
        first = await server._generate_tts_audio_base64("Reach forward to the target.", "nova")
        again = await server._generate_tts_audio_base64("Reach forward to the target.", "nova")
        burst = await asyncio.gather(*[server._generate_tts_audio_base64("Wonderful. Here we go.", "nova") for _ in range(4)])
        return first, again, burst

    first, again, burst = asyncio.run(run())
    assert first == again and len(set(burst)) == 1
    assert speech.calls == 2  # one per distinct line, however many callers asked
    # The blocking OpenAI call never runs on the event-loop thread.
    assert all(thread is not threading.main_thread() for thread in speech.threads)
    # The line survives a restart: it is on disk and found without a new call.
    server._tts_memory_cache.clear()
    assert asyncio.run(server._generate_tts_audio_base64("Reach forward to the target.", "nova")) == first
    assert speech.calls == 2
    assert list((tmp_path / "tts").glob("*.b64"))


def test_different_voices_and_texts_are_cached_separately(tmp_path, monkeypatch):
    client, speech = _fake_client()
    monkeypatch.setattr(server, "openai_tts_client", client)
    monkeypatch.setattr(server, "TTS_CACHE_DIR", tmp_path / "tts")
    server._tts_memory_cache.clear()
    server._tts_inflight.clear()

    async def run():
        return await asyncio.gather(
            server._generate_tts_audio_base64("Hold still.", "nova"),
            server._generate_tts_audio_base64("Hold still.", "alloy"),
            server._generate_tts_audio_base64("Hold still, please.", "nova"),
        )

    results = asyncio.run(run())
    assert len(set(results)) == 3
    assert speech.calls == 3
    assert server._tts_cache_key("Hold still.", "nova") != server._tts_cache_key("Hold still.", "alloy")
