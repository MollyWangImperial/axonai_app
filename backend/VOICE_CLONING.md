# Rehyn instruction voice cloning

Rehyn can use one ElevenLabs voice clone for fixed assessment and exercise instructions. Alira chat, emergency speech, and dynamic movement feedback keep the existing OpenAI voice. The cloned voice endpoint only accepts app-authored rehabilitation guidance, so it cannot be used to make the clone say arbitrary text.

## Create the clone

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
