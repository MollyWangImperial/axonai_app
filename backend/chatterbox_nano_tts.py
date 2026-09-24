"""Local, opt-in Chatterbox Nano synthesis for app-authored speech."""

from __future__ import annotations

import io
import shutil
import subprocess
import threading
from functools import lru_cache
from pathlib import Path


_inference_lock = threading.Lock()


@lru_cache(maxsize=1)
def _model():
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    return ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)


def synthesize_mp3(text: str, reference: Path, ffmpeg_path: str = "") -> bytes:
    if not reference.is_file():
        raise FileNotFoundError("Chatterbox reference recording is unavailable")
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for Chatterbox MP3 output")

    import torchaudio

    with _inference_lock:
        model = _model()
        # The current Nano loudness normalizer promotes the reference to float64,
        # while its speech tokenizer expects float32 on CPU.
        waveform = model.generate(text, audio_prompt_path=str(reference), norm_loudness=False)
    wav = io.BytesIO()
    torchaudio.save(wav, waveform.cpu(), model.sr, format="wav")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-af", "loudnorm=I=-18:TP=-2:LRA=11", "-codec:a", "libmp3lame", "-b:a", "128k", "-f", "mp3", "pipe:1"],
        input=wav.getvalue(),
        capture_output=True,
        check=True,
    )
    if len(result.stdout) < 1000:
        raise RuntimeError("Chatterbox produced no usable MP3 audio")
    return result.stdout
