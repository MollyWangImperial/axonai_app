"""Create an ElevenLabs Instant Voice Clone for Rehyn instructions.

The recording is read from the supplied local path and sent directly to
ElevenLabs. Rehyn does not copy it into the repository or its patient database.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import mimetypes
import os
from pathlib import Path

import httpx


CREATE_VOICE_URL = "https://api.elevenlabs.io/v1/voices/add"
ACCEPTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an ElevenLabs Instant Voice Clone for assessment and exercise instructions."
    )
    parser.add_argument("samples", nargs="+", type=Path, help="One or more recordings of the voice owner")
    parser.add_argument("--name", default="Rehyn instruction voice", help="Name shown in ElevenLabs")
    parser.add_argument(
        "--remove-background-noise",
        action="store_true",
        help="Ask ElevenLabs to isolate the voice; leave off for a clean recording",
    )
    parser.add_argument(
        "--confirm-consent",
        action="store_true",
        help="Confirm that the speaker owns the voice and consents to its cloning and use",
    )
    return parser.parse_args()


def validate_samples(samples: list[Path]) -> list[Path]:
    validated: list[Path] = []
    for supplied in samples:
        path = supplied.expanduser().resolve()
        if not path.is_file():
            raise SystemExit(f"Voice sample not found: {path}")
        if path.suffix.lower() not in ACCEPTED_EXTENSIONS:
            accepted = ", ".join(sorted(ACCEPTED_EXTENSIONS))
            raise SystemExit(f"Unsupported voice sample {path.name}. Use one of: {accepted}")
        if path.stat().st_size == 0:
            raise SystemExit(f"Voice sample is empty: {path}")
        validated.append(path)
    return validated


def create_voice_clone(
    samples: list[Path],
    name: str,
    remove_background_noise: bool,
    api_key: str,
) -> str:
    with ExitStack() as stack:
        files = []
        for path in samples:
            handle = stack.enter_context(path.open("rb"))
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            # ElevenLabs' OpenAPI schema names this multipart field `files`.
            # Using the curl-style `files[]` spelling makes the current API
            # reject the request as though no audio file was supplied.
            files.append(("files", (path.name, handle, mime_type)))
        response = httpx.post(
            CREATE_VOICE_URL,
            headers={"xi-api-key": api_key},
            data={
                "name": name[:100],
                "description": "Voice owner's clone for Rehyn assessment and exercise instructions",
                "remove_background_noise": str(remove_background_noise).lower(),
            },
            files=files,
            timeout=180,
        )
    if response.is_error:
        detail = response.text.strip().replace("\n", " ")[:500]
        raise SystemExit(f"ElevenLabs voice cloning failed ({response.status_code}): {detail}")
    voice_id = str(response.json().get("voice_id") or "").strip()
    if not voice_id:
        raise SystemExit("ElevenLabs created the voice but did not return a voice_id.")
    return voice_id


def main() -> None:
    args = parse_args()
    if not args.confirm_consent:
        raise SystemExit("Add --confirm-consent after confirming that the speaker owns and permits use of this voice.")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Set ELEVENLABS_API_KEY in your shell. Do not put the key in the repository.")
    samples = validate_samples(args.samples)
    voice_id = create_voice_clone(samples, args.name.strip() or "Rehyn instruction voice", args.remove_background_noise, api_key)
    print("Voice clone created. Add this value to Render as ELEVENLABS_VOICE_ID:")
    print(voice_id)


if __name__ == "__main__":
    main()
