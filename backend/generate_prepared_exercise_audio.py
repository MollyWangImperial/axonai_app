"""Generate reusable instruction-voice files for fixed Cylindrical Grasp prompts.

Run this only when the wording, TTS model, or voice changes. The generated MP3
files are public app assets; the API key is read from the environment and is
never written to the manifest.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os

import httpx


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_audio_build")

from backend import server  # noqa: E402


EXERCISE_ID = "ex_grasp"
MANIFEST_PATH = server.PREPARED_TTS_DIR / "manifest.json"
TTS_SOURCE_URL = os.environ.get("REHYN_TTS_SOURCE_URL", "").strip().rstrip("/")


def fixed_prompts() -> list[str]:
    prompts = {
        server.EXERCISE_POSTURE_CHANGED_VOICE,
        server.EXERCISE_TRANSITION_VOICE,
        server.EXERCISE_ASSISTANCE_QUESTION_VOICE,
        server.EXERCISE_ASSISTED_COMPLETE_VOICE,
        server.EXERCISE_INDEPENDENT_COMPLETE_VOICE,
    }
    for difficulty in ("easy", "medium", "difficult"):
        for variation in ("standard", "alternate"):
            config = server._configure_rehab_runner(EXERCISE_ID, difficulty, variation)
            prompts.add(str(config["setup_voice"]))
            prompts.add(str(config["movement_standard"]["calibration_instruction"]))
            prompts.update(str(step["voice"]) for step in config["cycle"] if step.get("voice"))
    return sorted(prompts)


async def generate_one(text: str, semaphore: asyncio.Semaphore) -> dict[str, str | int]:
    key = server._tts_cache_key(text, server.TTS_VOICE, purpose="instruction")
    destination = server.PREPARED_TTS_DIR / f"{key}.mp3"
    if not destination.is_file() or destination.stat().st_size < 1000:
        async with semaphore:
            if TTS_SOURCE_URL:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(f"{TTS_SOURCE_URL}/api/tts/generate", json={"text": text})
                    response.raise_for_status()
                    audio = base64.b64decode(response.json()["audio_b64"])
            else:
                audio = await asyncio.to_thread(
                    server._synthesize_tts_audio_bytes,
                    text,
                    server.TTS_VOICE,
                    "instruction",
                )
        if len(audio) < 1000:
            raise RuntimeError(f"Prepared audio was unexpectedly small for {key}")
        temporary = destination.with_suffix(".mp3.part")
        temporary.write_bytes(audio)
        temporary.replace(destination)
    return {
        "key": key,
        "url": f"/audio/prepared/{key}.mp3",
        "bytes": destination.stat().st_size,
        "text": text,
    }


async def main() -> None:
    config = server._tts_request_config("instruction", server.TTS_VOICE)
    if not TTS_SOURCE_URL and config["provider"] == "unavailable":
        raise RuntimeError("Configure an instruction text-to-speech provider before generating audio")
    if config["provider"] == "elevenlabs" and os.environ.get("ALLOW_PUBLIC_CLONED_VOICE_ASSETS") != "1":
        raise RuntimeError(
            "Cloned voice files are generated at runtime and must not be added to public assets. "
            "Set ALLOW_PUBLIC_CLONED_VOICE_ASSETS=1 only after an explicit distribution decision."
        )
    server.PREPARED_TTS_DIR.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(3)
    assets = await asyncio.gather(*(generate_one(text, semaphore) for text in fixed_prompts()))
    manifest = {
        "version": 1,
        "exercise_id": EXERCISE_ID,
        "provider": config["provider"],
        "model": config["model"],
        "voice": config["public_voice"],
        "assets": assets,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Prepared {len(assets)} voice files in {server.PREPARED_TTS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
