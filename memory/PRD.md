# NeuroMotion — Stroke Rehabilitation App

## Overview
A guided upper-limb stroke rehabilitation app for Expo. 7 movement tasks are performed
in front of the camera using **MediaPipe Pose** running inside a WebView. A warm
**ElevenLabs** voice guides each step, an on-screen target shows the patient where to
reach, and the app advances only when the patient's wrist enters the target zone and
holds for the required duration.

After all tasks, the backend derives **functional issues** (rule-based, sourced from
Fugl-Meyer UE, ARAT, Chedoke-McMaster, Bobath/NDT, and CIMT principles) and generates a
**personalized rehab plan** with evidence-based exercises.

## Architecture
- **Frontend**: Expo Router screens (`index`, `task-intro`, `assessment`, `results`, `rehab-plan`, `history`).
  The Assessment screen renders a `WebView` that loads `/api/pose/runner`, which contains
  MediaPipe PoseLandmarker, camera capture, target overlay, voice playback, and progress logic.
- **Backend**: FastAPI on port 8001 with `/api` prefix.
  - `GET /api/assessment/tasks` — 7 tasks + step-by-step voice prompts + target zones
  - `POST /api/tts/generate` — ElevenLabs TTS (mp3 base64)
  - `POST /api/assessment/submit` — derives functional issues + rehab plan
  - `GET /api/assessment/history` & `GET /api/assessment/{id}`
  - `GET /api/pose/runner` — HTML page with MediaPipe pose runner
- **DB**: MongoDB (`assessments` collection).

## Integrations
- **ElevenLabs** TTS — voice ID `EXAVITQu4vr4xnSDxMaC` (Bella), warm/encouraging tone.
- **MediaPipe Tasks Vision (web)** — pose landmark detection inside WebView.

## Clinical sources (used in functional-issue & rehab rules)
- Fugl-Meyer Upper Extremity Assessment (1975)
- Action Research Arm Test (Lyle, 1981)
- Chedoke-McMaster Stroke Assessment
- Constraint-Induced Movement Therapy (Taub et al.)
- BATRAC (Whitall et al.)
- Task-Specific Training (Carr & Shepherd)
- Bobath / NDT principles
- Levin & Michaelsen — Trunk-Restraint Reaching (2008)

## Notes
- Camera/pose run inside the WebView using device camera via `getUserMedia` (HTTPS preview URL).
- Voice playback uses MP3 base64 returned from the ElevenLabs backend route.
- No auth in this MVP — single-user / local-history.
