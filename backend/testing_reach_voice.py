"""Serve the finite, privately stored Molly voice cues to signed-in testers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend import server
from backend.testing_reach_voice_lines import LINES

router = APIRouter(prefix="/api/testing/reach/voice")
_ALLOWED = frozenset(LINES)
_REQUIRED_HASHES = frozenset(hashlib.sha256(text.encode("utf-8")).hexdigest() for text in LINES)


def _bundle_path() -> Path:
    configured = os.environ.get("TESTING_REACH_VOICE_BUNDLE", "").strip()
    if configured:
        return Path(configured)
    local = Path(__file__).resolve().parent / "voice_samples" / "reach-molly-bundle.json"
    return local if local.is_file() else Path("/etc/secrets/reach-molly-bundle.json")


@lru_cache(maxsize=1)
def _bundle() -> dict[str, str]:
    path = _bundle_path()
    if not path.is_file() or path.stat().st_size > 1_000_000:
        return {}
    try:
        content = json.loads(path.read_text(encoding="ascii"))
        if content.get("version") != 1 or content.get("voice") != "Molly":
            return {}
        entries = content.get("entries")
        if not isinstance(entries, dict) or not _REQUIRED_HASHES.issubset(entries):
            return {}
        for key, encoded in entries.items():
            if key not in _REQUIRED_HASHES or not isinstance(encoded, str):
                return {}
            audio = base64.b64decode(encoded, validate=True)
            if not (1000 <= len(audio) <= 200_000) or not (audio.startswith(b"ID3") or audio[:1] == b"\xff"):
                return {}
        return entries
    except (OSError, ValueError, TypeError, UnicodeError):
        return {}


class CueRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.get("/health")
async def voice_health():
    entries = _bundle()
    live_clone = server._instruction_clone_ready() and server.INSTRUCTION_TTS_PROVIDER in {"elevenlabs", "chatterbox-nano"}
    return {"ready": bool(entries) or live_clone, "voice": "Molly" if entries or live_clone else None,
            "provider": "prepared-private-clone" if entries else server.INSTRUCTION_TTS_PROVIDER if live_clone else "unavailable",
            "required_cues": len(_REQUIRED_HASHES), "available_cues": len(entries)}


@router.post("")
async def voice_cue(request: Request, cue: CueRequest):
    if not await server._task_video_user(request):
        raise HTTPException(401, "Sign in required")
    if cue.text not in _ALLOWED:
        raise HTTPException(403, "Only authored Testing instructions can use this voice")
    encoded = _bundle().get(hashlib.sha256(cue.text.encode("utf-8")).hexdigest())
    if not encoded and server._instruction_clone_ready() and server.INSTRUCTION_TTS_PROVIDER in {"elevenlabs", "chatterbox-nano"}:
        encoded = await server._generate_tts_audio_base64(cue.text, server.TTS_VOICE, purpose="instruction")
    if not encoded:
        raise HTTPException(503, "Molly voice is unavailable")
    return {"audio_b64": encoded, "text": cue.text}
