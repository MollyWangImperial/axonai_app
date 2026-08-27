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
