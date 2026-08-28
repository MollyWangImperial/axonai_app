# Rehyn local development

Run `start_dev.ps1` from the repository root. The launcher starts:

- the local API on port `8001`;
- a loopback-only CUDA worker on port `8003` using the model environment at
  `E:\Rehyn_Video_Projects\stroke_mocap_to_motion_encoder\.venv`;
- Expo/Metro for the frontend.

The CUDA worker preloads the frozen WHAM motion encoder and the trained Stroke
Functional Encoder. Local assessments automatically queue their captured 2D
keypoint sequences to this worker. Check it through
`http://127.0.0.1:8001/api/analysis/local-gpu/status`.
An assessment's processing state is available at
`/api/assessment/{assessment_id}/analysis-status`; this endpoint omits raw
model predictions.

The GPU stage is an intermediate research output. OpenSim inverse kinematics
and Moco remain CPU-oriented and must pass the existing model-quality gates
before Rehyn reports muscle activation or enables a model-derived plan.

## Independent video shadow review

The local worker also supports an optional multimodal audit of evenly sampled
frames from each saved task video. It is disabled by default and never acts as
ground truth, changes findings, or rewrites production logic. A disagreement
blocks a new plan and creates a clinician-adjudication case; only a labeled
cohort plus an independent holdout can become a candidate for a versioned
architecture update.

Enable it in the environment that launches `start_dev.ps1` only after the
deployment's privacy policy and patient consent flow are ready:

```powershell
$env:CLINICAL_SHADOW_REVIEW_ENABLED = "1"
$env:CLINICAL_SHADOW_REVIEW_ALLOW_EXTERNAL_VIDEO = "1"
$env:CLINICAL_SHADOW_REVIEW_MODEL = "gpt-4o"
$env:OPENAI_API_KEY = "..."
```

The assessment must also contain `ai_video_review_consent: true`. Sampled
frames can contain a face, so the worker returns `consent_required` rather than
sending video when that explicit consent is absent. Review state is available
at `/api/assessment/{assessment_id}/clinical-review-audit` to the patient or a
therapist. Adjudication requires a therapist account that has
`clinical_review_approved: true`, or whose ID is in the deployment's
`CLINICAL_REVIEW_APPROVER_IDS` allowlist.
