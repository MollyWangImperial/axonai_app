"""Generate the bundled, original 100-point celebration fanfare."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
DURATION_SECONDS = 3.2
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "audio" / "rewards" / "100-point-fanfare.wav"


def note_frequency(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


NOTES = (
    (0.00, 0.58, (72, 76, 79), 0.28),
    (0.48, 0.62, (76, 79, 84), 0.30),
    (0.98, 0.78, (79, 84, 88), 0.32),
    (1.62, 1.48, (84, 88, 91), 0.34),
)


def envelope(local_time: float, duration: float) -> float:
    attack = min(1.0, local_time / 0.025)
    release = min(1.0, max(0.0, duration - local_time) / 0.32)
    return attack * release * math.exp(-1.25 * local_time)


def sample_at(time_seconds: float) -> float:
    value = 0.0
    for start, duration, chord, gain in NOTES:
        local_time = time_seconds - start
        if local_time < 0 or local_time > duration:
            continue
        shaped = envelope(local_time, duration)
        for midi_note in chord:
            frequency = note_frequency(midi_note)
            fundamental = math.sin(2 * math.pi * frequency * local_time)
            bell = 0.34 * math.sin(2 * math.pi * frequency * 2.01 * local_time)
            shimmer = 0.12 * math.sin(2 * math.pi * frequency * 3.99 * local_time)
            value += gain * shaped * (fundamental + bell + shimmer) / len(chord)
    return max(-1.0, min(1.0, value * 0.82))


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(SAMPLE_RATE * DURATION_SECONDS)
    with wave.open(str(OUTPUT), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for frame in range(frame_count):
            frames.extend(struct.pack("<h", int(sample_at(frame / SAMPLE_RATE) * 32767)))
        audio.writeframes(frames)
    print(OUTPUT)


if __name__ == "__main__":
    main()
