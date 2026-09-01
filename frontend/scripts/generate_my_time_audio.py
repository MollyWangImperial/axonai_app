"""Generate the small public-domain melody clips used by My Time."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 22_050
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "audio" / "my-time"

NOTE_FREQUENCIES = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "F4": 349.23,
    "G4": 392.00,
    "A4": 440.00,
}

MELODIES = {
    "twinkle-twinkle.wav": [
        ("C4", 0.44), ("C4", 0.44), ("G4", 0.44), ("G4", 0.44),
        ("A4", 0.44), ("A4", 0.44), ("G4", 0.88),
        ("F4", 0.44), ("F4", 0.44), ("E4", 0.44), ("E4", 0.44),
        ("D4", 0.44), ("D4", 0.44), ("C4", 0.88),
    ],
    "ode-to-joy.wav": [
        ("E4", 0.38), ("E4", 0.38), ("F4", 0.38), ("G4", 0.38),
        ("G4", 0.38), ("F4", 0.38), ("E4", 0.38), ("D4", 0.38),
        ("C4", 0.38), ("C4", 0.38), ("D4", 0.38), ("E4", 0.38),
        ("E4", 0.56), ("D4", 0.20), ("D4", 0.76),
    ],
    "frere-jacques.wav": [
        ("C4", 0.38), ("D4", 0.38), ("E4", 0.38), ("C4", 0.38),
        ("C4", 0.38), ("D4", 0.38), ("E4", 0.38), ("C4", 0.38),
        ("E4", 0.38), ("F4", 0.38), ("G4", 0.76),
        ("E4", 0.38), ("F4", 0.38), ("G4", 0.76),
    ],
}


def tone(frequency: float, duration: float) -> bytes:
    frame_count = int(SAMPLE_RATE * duration)
    frames = bytearray()
    for frame in range(frame_count):
        t = frame / SAMPLE_RATE
        edge = min(1.0, frame / (SAMPLE_RATE * 0.025), (frame_count - frame) / (SAMPLE_RATE * 0.06))
        envelope = max(0.0, edge) * math.exp(-1.15 * t / max(duration, 0.01))
        sample = (
            math.sin(2 * math.pi * frequency * t)
            + 0.28 * math.sin(2 * math.pi * frequency * 2 * t)
            + 0.12 * math.sin(2 * math.pi * frequency * 3 * t)
        )
        frames.extend(struct.pack("<h", int(10_500 * envelope * sample / 1.4)))
    return bytes(frames)


def write_melody(path: Path, notes: list[tuple[str, float]]) -> None:
    pause = b"\x00\x00" * int(SAMPLE_RATE * 0.045)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for note, duration in notes:
            output.writeframes(tone(NOTE_FREQUENCIES[note], duration))
            output.writeframes(pause)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, notes in MELODIES.items():
        write_melody(OUTPUT / filename, notes)


if __name__ == "__main__":
    main()
