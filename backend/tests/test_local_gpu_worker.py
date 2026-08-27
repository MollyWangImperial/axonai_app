from pathlib import Path

from backend.local_gpu_worker import build_task_pose_payloads


def _pose(x: float = 0.25, y: float = 0.5):
    return [[x, y, 0.0, 0.9] for _ in range(33)]


def test_motion_frames_are_grouped_and_converted_to_pixel_coordinates():
    payloads = build_task_pose_payloads({
        "camera_projection": {"source_width": 1280, "source_height": 720},
        "sample_interval_ms": 50,
        "frames": [
            {"task_id": "T1", "pose_2d": _pose()},
            {"task_id": "T2", "pose_2d": _pose(0.5, 0.25)},
            {"task_id": "T1", "pose_2d": _pose(0.75, 0.5)},
        ],
    })

    assert set(payloads) == {"T1", "T2"}
    assert payloads["T1"]["fps"] == 20.0
    assert payloads["T1"]["frames"][0]["lm2d"][0] == [320.0, 360.0, 0.9]
    assert payloads["T1"]["frames"][1]["lm2d"][0] == [960.0, 360.0, 0.9]


def test_local_launcher_requires_cuda_and_starts_the_worker():
    source = (Path(__file__).resolve().parents[2] / "start_dev.ps1").read_text(encoding="utf-8")
    assert "torch.cuda.is_available()" in source
    assert "local_gpu_worker.py" in source
    assert "LOCAL_GPU_WORKER_URL='http://127.0.0.1:8003'" in source
    assert "ANALYSIS_WORKER_TOKEN" in source
    assert "D:\\anaconda3\\Anaconda3\\python.exe" in source
    assert "import fastapi, motor, uvicorn, opensim" in source
    assert "The local CUDA worker did not become ready within 45 seconds" in source


def test_gpu_stage_does_not_bypass_validated_model_result_route():
    source = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert '"/assessment/{assessment_id}/gpu-stage-results"' in source
    assert source.count('@api_router.post("/assessment/{assessment_id}/gpu-stage-results")') == 1
    assert "Store intermediate CUDA output without treating it as solver activation" in source
    assert '"model_analysis.gpu_stage"' in source


def test_local_worker_runs_cuda_and_moco_as_independent_callbacks():
    source = (Path(__file__).resolve().parents[1] / "local_gpu_worker.py").read_text(encoding="utf-8")
    assert 'callback(job, gpu_result, "gpu-stage-results")' in source
    assert 'callback(job, model_result, "model-stage-results")' in source
    assert "MOCO_RUNTIME.analyze(job)" in source
    assert "OpenSim Moco patient-informed gait comparison" in source
    assert '"model_scaled": False' in source
    assert "not subject-scaled" in source
