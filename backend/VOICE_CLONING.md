# Rehyn instruction voice cloning

Rehyn can use a private voice reference for assessment and exercise instructions. Alira chat, emergency speech, and dynamic movement feedback keep the existing OpenAI voice. The cloned instruction endpoint only accepts app-authored rehabilitation guidance, so it cannot be used to make the clone say arbitrary text.

## Local Chatterbox Nano (Molly)

The local seated forward-reach test and other instruction requests can use Chatterbox Nano. Keep Molly's recording and the derived 10-second WAV in `backend/voice_samples/`, which is ignored by Git. The source recording is never served as a static asset. Obtain the speaker's permission before using her voice.

The Nano API is currently in the official Chatterbox repository, not in the latest PyPI wheel. Use an isolated Python environment with CPU PyTorch, torchaudio and FFmpeg, then install the pinned source revision:

```powershell
python -m venv --system-site-packages backend/voice_samples/venv
backend/voice_samples/venv/Scripts/python.exe -m pip install chatterbox-tts==0.1.7
backend/voice_samples/venv/Scripts/python.exe -m pip install --force-reinstall --no-deps "git+https://github.com/resemble-ai/chatterbox.git@5de7a54aa4e5e2baadb0182dde554908b48b85c2"
```

Set `INSTRUCTION_TTS_PROVIDER=chatterbox-nano`, `CHATTERBOX_REFERENCE_AUDIO` to the private WAV path, and `HF_HOME` to a disk with several GB free. `CHATTERBOX_FFMPEG_PATH` is optional if FFmpeg is on `PATH`. Start the backend with that environment's Python. The first voice request downloads the model; subsequent lines are cached in `backend/.local_state/tts_cache`. `/api/tts/health?purpose=instruction` should report `provider: chatterbox-nano` and `voice: Molly`.

This local setup does not change Render's voice. Its free web service does not include the private sample or the model dependencies; deployment needs a separately provisioned voice worker or private storage and enough memory. Do not commit Molly's recording or generated voice clips to public assets.

## Seated Forward Reach Testing on Render

The Testing version of Seated Forward Reach has a finite set of authored cues. Its private `/api/testing/reach/voice` endpoint serves those cues to signed-in users using either an existing configured clone provider or a prepared private bundle. It never accepts arbitrary speech text and never falls back to the preset Nova voice. If cloned audio is unavailable, the exercise continues with captions.

For a Render Free service without a voice worker, generate the clips locally with `python -m backend.build_testing_reach_voice_bundle --reference <private-molly-wav>`. Use the Chatterbox Nano environment described above, set `HF_HOME` to the disk containing the cached model, and keep the generated `backend/voice_samples/reach-molly-bundle.json` out of Git. Render limits each secret file to 500 KiB, so run `python -m backend.split_testing_reach_voice_bundle backend/voice_samples/reach-molly-bundle.json` and upload both resulting files as private secret files named `reach-molly-bundle-1.json` and `reach-molly-bundle-2.json`. Remove any oversized unsplit secret file before deploying. A restart loads both files; `/api/testing/reach/voice/health` then reports `ready: true`, `voice: Molly`, and the cue count. The original recording is never uploaded to Render for this approach.

If an ElevenLabs Molly clone is already configured on Render, the same Testing endpoint can synthesize the authored cues on demand. Verify an actual cue after configuration; a configured provider alone does not prove the voice is working.

## ElevenLabs alternative

## Create the clone

The ElevenLabs account must be on a plan that includes Instant Voice Cloning.

Use 1–2 minutes of clean, single-speaker audio with a consistent, calm instruction style. MP3 at 192 kbps or higher is preferred. Avoid music, room echo, other speakers, long silences, and aggressive noise removal.

Keep recordings in `backend/voice_samples/` or another private local folder. That repository folder is ignored by Git.

In PowerShell:

```powershell
$env:ELEVENLABS_API_KEY = "your-key"
python backend/clone_instruction_voice.py --name "Rehyn instruction voice" --confirm-consent backend/voice_samples/my-voice.mp3
```

The command prints an ElevenLabs voice ID. Do not commit the API key or the original voice recording.

Cloned instruction audio is generated on demand and cached privately by the backend. The prepared-audio build script refuses to write cloned speech into public web assets unless a developer makes an explicit distribution decision.

## Configure Render

Set these secret environment variables on the `rehyn` service:

- `ELEVENLABS_API_KEY`: the ElevenLabs API key
- `ELEVENLABS_VOICE_ID`: the ID printed by the cloning command

The deployment already sets `INSTRUCTION_TTS_PROVIDER=elevenlabs`, `ELEVENLABS_TTS_MODEL=eleven_multilingual_v2`, and `ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128`. Render falls back to the current OpenAI instruction voice until both secrets are present.

After Render redeploys, open `/api/tts/health?purpose=instruction`. A working clone reports `provider: elevenlabs`, `voice: custom-cloned-voice`, and `instruction_clone_ready: true` without exposing the real voice ID.
