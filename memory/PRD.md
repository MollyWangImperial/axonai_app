# Rehyn — Product Requirements & Progress (PRD)

## Original problem statement
Improve the existing Rehyn app (external repo `axonai_app`, live PWA on Render) to make it immediately go-to-market. User priorities: **Polish & UX, Onboarding & Activation, Trust & Compliance**. Audience: **patients (D2C) + therapists (B2B)**. Platforms: **Web PWA + iOS/Android app stores**.

## What Rehyn is
Camera-based stroke rehabilitation platform. MediaPipe pose capture (WebView) → rule-based clinical reasoning (Fugl-Meyer, ARAT, Chedoke-McMaster, CIMT, Bobath/NDT) → personalized rehab plan + guided exercises. AI coach "Alira". Patient + therapist roles, email-only auth + Emergent Google auth, credits monetization. Optional local GPU/OpenSim/Moco muscle-model tier (not in cloud).

## Architecture (as imported into this environment)
- **Frontend**: Expo Router (`/app/frontend`). Screens: sign-in, consent (new), onboarding, session-check, camera-check (new), task-intro, assessment, results, function-summary, movement-map, rehab-plan, exercise, progress, history, credits, account-center, therapist, persona-chat, alira-call, (tabs) home/journey/chat/community/therapists/profile/settings.
- **Backend**: FastAPI monolith `/app/backend/server.py` (+ rehab modules). MongoDB. `/api` prefix. TTS via emergentintegrations (OpenAI). ElevenLabs available.
- **Env**: EMERGENT_LLM_KEY set; MONGO_URL local; DB_NAME=rehyn.

## Personas
- **Patient / stroke survivor** — often older, may have hemiparesis, low vision, cognitive fatigue. Wants to recover everyday function; motivation-sensitive.
- **Caregiver / family** — frequently the payer and session helper.
- **Therapist / clinic** — supervises home practice, confirms plans; B2B buyer.

## Implemented (this round — 2026-08-29)
### Phase 1 — Compliance & Safety (DONE, tested)
- **Medical consent gate** (`/app/frontend/app/consent.tsx`): new patients must accept a non-diagnostic + safety disclaimer before onboarding. Wired in `_layout.tsx` AuthGate (`hasAcceptedConsent`).
- **Pre-session safety checklist** on `session-check.tsx`: Continue disabled until actor + safety acknowledgement.
- **Native-Alert removed**: `task-intro.tsx` "Start over" now uses an in-app Modal.
- **Non-diagnostic disclaimer banner** (`src/components/MedicalDisclaimer.tsx`) on results, rehab-plan, function-summary.
- **Account deletion** (store requirement): frontend confirm modal in account-center + backend `DELETE /api/users/account` (soft delete, sets `deleted_at`, flips `onboarding_complete`).

### Phase 2 — Activation (STARTED)
- **Camera setup coach** (`/app/frontend/app/camera-check.tsx`): framing/lighting/clothing/stability guidance shown before every assessment (task-intro → camera-check → assessment).

## Backlog
### P0 (before store submission)
- Public **privacy policy** page/URL (in-app privacy section exists; needs standalone policy + link).
- Deeper **non-diagnostic copy** pass across all clinical-sounding strings (results/plan/summary/insights).

### P1 (activation & retention)
- **Cold-start polish**: branded splash + skeleton loaders on production (Render cold start).
- **Progress visualization**: range-of-motion / tasks-unlocked trends on progress + movement-map (shareable asset).
- **Proactive Alira coach**: daily encouragement nudges, small-win celebrations.
- Activation funnel instrumentation (signup → first assessment → plan → first exercise).

### P2 (scale / revenue)
- **Therapist dashboard** (B2B2C wedge): view patients' assessments + adherence, confirm/edit plans.
- Cloud GPU inference → premium "Clinical" muscle-model tier.
- RTM reimbursement positioning; multi-language (Chinese clinical docs exist); clinical validation study.

## Notes / limitations
- Local GPU/OpenSim worker not reachable in cloud — 2D MediaPipe assessment + rule-based plan is the shippable path.
- App-store lane: launch as "wellness / movement coaching" (not "diagnosis") to ease Apple/Google health review.
- `eas.json` is Emergent-managed; app.json owner/eas.projectId are the user's (revisit at publish time).

## Next tasks
1. Standalone privacy policy + non-diagnostic copy sweep (finish P0).
2. Progress visualization + proactive Alira (P1).
3. Therapist dashboard (P2, primary revenue wedge).
