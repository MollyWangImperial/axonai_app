from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from types import SimpleNamespace

import torch
import torchaudio

from backend import chatterbox_nano_tts


def test_nano_generation_is_serialized_and_encoded_as_mp3(tmp_path, monkeypatch):
    reference = tmp_path / "molly.wav"
    reference.write_bytes(b"private-audio")
    state = {"active": 0, "maximum": 0}
    state_lock = Lock()
    commands = []

    class FakeModel:
        sr = 24000

        def generate(self, text, audio_prompt_path, norm_loudness):
            assert audio_prompt_path == str(reference)
            assert norm_loudness is False
            with state_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
            sleep(0.02)
            with state_lock:
                state["active"] -= 1
            return torch.zeros((1, 2400))

    monkeypatch.setattr(chatterbox_nano_tts, "_model", lambda: FakeModel())
    monkeypatch.setattr(torchaudio, "save", lambda destination, waveform, sample_rate, format: destination.write(b"RIFF-test-wav"))

    def fake_run(command, **kwargs):
        commands.append(command)
        assert kwargs["input"].startswith(b"RIFF")
        return SimpleNamespace(stdout=b"ID3" + b"a" * 1000)

    monkeypatch.setattr(chatterbox_nano_tts.subprocess, "run", fake_run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda text: chatterbox_nano_tts.synthesize_mp3(text, reference, "ffmpeg-test"), ("one", "two")))
    assert all(output.startswith(b"ID3") for output in outputs)
    assert state["maximum"] == 1
    assert all("loudnorm=I=-18:TP=-2:LRA=11" in command for command in commands)
