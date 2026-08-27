"""Local CUDA feature worker for Rehyn development assessments.

This worker is intentionally bound to loopback. It runs the learned WHAM
motion-context and stroke functional-encoder stages, then reports their output
back to the app backend. OpenSim/Moco remains a separate, quality-gated stage.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np


HOST = os.environ.get("REHYN_GPU_WORKER_HOST", "127.0.0.1")
PORT = int(os.environ.get("REHYN_GPU_WORKER_PORT", "8003"))
WORKER_TOKEN = os.environ.get("ANALYSIS_WORKER_TOKEN", "").strip()
MODEL_ROOT = Path(os.environ.get(
    "REHYN_MODEL_ROOT",
    r"E:\Rehyn_Video_Projects\stroke_mocap_to_motion_encoder",
))
WHAM_ROOT = Path(os.environ.get("REHYN_WHAM_ROOT", str(MODEL_ROOT / "third_party" / "WHAM")))
WHAM_CHECKPOINT = Path(os.environ.get(
    "REHYN_WHAM_CHECKPOINT",
    str(WHAM_ROOT / "checkpoints" / "wham_vit_w_3dpw.pth.tar"),
))
FUNCTIONAL_CHECKPOINT = Path(os.environ.get(
    "REHYN_FUNCTIONAL_CHECKPOINT",
    str(MODEL_ROOT / "training" / "functional_encoder_wham_v1" / "best_model.pt"),
))
FEATURE_ROOT = Path(os.environ.get(
    "REHYN_FEATURE_ROOT",
    str(MODEL_ROOT / "processed" / "wham_motion_features_v1"),
))


def build_task_pose_payloads(motion_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    projection = motion_data.get("camera_projection") or {}
    width = max(1, int(projection.get("source_width") or 960))
    height = max(1, int(projection.get("source_height") or 540))
    interval_ms = max(1, int(motion_data.get("sample_interval_ms") or 100))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, frame in enumerate(motion_data.get("frames") or []):
        task_id = str(frame.get("task_id") or "").strip()
        landmarks = frame.get("pose_2d")
        if not task_id or not isinstance(landmarks, list) or len(landmarks) < 33:
            continue
        points = []
        for point in landmarks[:33]:
            if not isinstance(point, list) or len(point) < 2:
                points = []
                break
            visibility = float(point[3]) if len(point) > 3 else 1.0
            points.append([float(point[0]) * width, float(point[1]) * height, visibility])
        if points:
            grouped.setdefault(task_id, []).append({"frame": f"motion_{index:04d}", "lm2d": points})
    fps = 1000.0 / interval_ms
    return {
        task_id: {"w": width, "h": height, "fps": fps, "frames": frames}
        for task_id, frames in grouped.items()
    }


class CudaRuntime:
    def __init__(self) -> None:
        scripts = MODEL_ROOT / "scripts"
        comparison = Path(os.environ.get(
            "REHYN_STROKE_APPLICATION_ROOT",
            r"E:\Rehyn_Video_Projects\stroke_patient_architecture_comparison",
        ))
        for path in (scripts, WHAM_ROOT, comparison):
            sys.path.insert(0, str(path))

        import torch
        from apply_stroke_architecture import (
            crop_normalize,
            mediapipe_to_union28,
            pad,
            window_starts,
        )
        from cache_frozen_wham_features import (
            COCO17_FROM_UNION,
            bbox_location,
            load_encoder,
            preprocess,
        )
        from train_stroke_functional_encoder import TrainConfig
        from train_stroke_functional_encoder_wham import WhamStrokeFunctionalEncoder

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable in the configured model Python environment")
        for required in (WHAM_CHECKPOINT, FUNCTIONAL_CHECKPOINT, FEATURE_ROOT / "canonical_init_coco17_train_only.npy"):
            if not required.exists():
                raise FileNotFoundError(required)

        self.torch = torch
        self.device = torch.device("cuda:0")
        self.crop_normalize = crop_normalize
        self.mediapipe_to_union28 = mediapipe_to_union28
        self.pad = pad
        self.window_starts = window_starts
        self.coco_indices = COCO17_FROM_UNION
        self.bbox_location = bbox_location
        self.preprocess = preprocess
        self.encoder, self.mask_embedding, _, _ = load_encoder(
            WHAM_ROOT, WHAM_CHECKPOINT, self.device,
        )
        self.encoder.eval()
        self.canonical = np.load(
            FEATURE_ROOT / "canonical_init_coco17_train_only.npy"
        ).astype(np.float32)[0]

        checkpoint = torch.load(FUNCTIONAL_CHECKPOINT, map_location=self.device, weights_only=False)
        cfg = TrainConfig(**checkpoint["config"])
        self.functional_model = WhamStrokeFunctionalEncoder(
            len(checkpoint["task_to_index"]), len(checkpoint["target_names"]), cfg
        ).to(self.device)
        self.functional_model.load_state_dict(checkpoint["model_state"])
        self.functional_model.eval()
        self.functional_checkpoint = checkpoint
        self.functional_config = cfg
        self.target_mean = np.asarray(checkpoint["target_mean"], np.float32)
        self.target_std = np.asarray(checkpoint["target_std"], np.float32)
        self.lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        torch = self.torch
        return {
            "status": "ready",
            "cuda": True,
            "device": str(self.device),
            "gpu_name": torch.cuda.get_device_name(0),
            "torch_version": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "allocated_mb": round(torch.cuda.memory_allocated(0) / 1048576, 1),
            "stages": ["frozen_wham_motion_context", "stroke_functional_encoder"],
        }

    def _context(self, union_crop: np.ndarray, union_image: np.ndarray, image_size: tuple[int, int]) -> np.ndarray:
        torch = self.torch
        coco_crop = union_crop[:, self.coco_indices]
        coco_image = union_image[:, self.coco_indices]
        location = self.bbox_location(coco_image[None], np.asarray(image_size, np.float32))[0]
        x_np = np.concatenate(
            (coco_crop[..., :2].reshape(len(coco_crop), -1), location), axis=-1
        ).astype(np.float32)
        mask_np = coco_crop[..., 2] < 0.3
        x = torch.from_numpy(x_np).unsqueeze(0).to(self.device)
        mask = torch.from_numpy(mask_np).unsqueeze(0).to(self.device)
        processed = self.preprocess(x, mask, self.mask_embedding)
        init_3d = torch.from_numpy(self.canonical).to(self.device).reshape(1, 1, -1)
        init = torch.cat((init_3d, x[:, :1]), dim=-1)
        with torch.inference_mode():
            _, context = self.encoder(processed, init)
        return context[0].detach().cpu().numpy().astype(np.float32)

    def _constraints(self, union_crop: np.ndarray, context: np.ndarray) -> list[dict[str, Any]]:
        torch = self.torch
        cfg = self.functional_config
        predictions = []
        for start in self.window_starts(len(union_crop), cfg.window):
            keypoints, frame_mask = self.pad(union_crop, start, cfg.window)
            wham, _ = self.pad(context, start, cfg.window)
            with torch.inference_mode():
                output = self.functional_model(
                    torch.from_numpy(keypoints).unsqueeze(0).to(self.device),
                    torch.from_numpy(wham).unsqueeze(0).to(self.device),
                    torch.from_numpy(frame_mask).unsqueeze(0).to(self.device),
                )
            mean = output["constraint_mean"][0].cpu().numpy() * self.target_std + self.target_mean
            sd = np.exp(0.5 * output["constraint_logvar"][0].cpu().numpy()) * self.target_std
            predictions.append({
                "start_frame": int(start),
                "constraints": {
                    name: {"mean": float(mean[index]), "one_sd": float(sd[index])}
                    for index, name in enumerate(self.functional_checkpoint["target_names"])
                },
            })
        return predictions

    def analyze(self, motion_data: dict[str, Any]) -> dict[str, Any]:
        payloads = build_task_pose_payloads(motion_data)
        tasks: dict[str, Any] = {}
        with self.lock:
            for task_id, payload in payloads.items():
                if len(payload["frames"]) < 4:
                    tasks[task_id] = {"status": "insufficient_frames", "frames": len(payload["frames"])}
                    continue
                temp = Path(os.environ.get("TEMP", ".")) / f"rehyn_gpu_pose_{os.getpid()}_{task_id}.json"
                try:
                    temp.write_text(json.dumps(payload), encoding="utf-8")
                    union_image, width, height, fps = self.mediapipe_to_union28(temp)
                    union_crop = self.crop_normalize(union_image)
                    context = self._context(union_crop, union_image, (width, height))
                    tasks[task_id] = {
                        "status": "completed",
                        "frames": len(union_image),
                        "fps": fps,
                        "predictions": self._constraints(union_crop, context),
                    }
                finally:
                    temp.unlink(missing_ok=True)
        return {
            **self.status(),
            "status": "completed",
            "model_version": "wham-vit-3dpw+stroke-functional-encoder-v1",
            "tasks": tasks,
            "reporting_boundary": (
                "GPU functional constraints are an intermediate research output. "
                "They are not OpenSim/Moco muscle activations or a diagnosis."
            ),
        }


RUNTIME: CudaRuntime | None = None
JOBS: queue.Queue[dict[str, Any]] = queue.Queue()


def get_runtime() -> CudaRuntime:
    global RUNTIME
    if RUNTIME is None:
        RUNTIME = CudaRuntime()
    return RUNTIME


def callback(job: dict[str, Any], result: dict[str, Any]) -> None:
    url = f"{job['callback_url'].rstrip('/')}/assessment/{job['assessment_id']}/gpu-stage-results"
    request = urllib.request.Request(
        url,
        data=json.dumps(result).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Analysis-Worker-Token": WORKER_TOKEN,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def run_jobs() -> None:
    while True:
        job = JOBS.get()
        try:
            result = get_runtime().analyze(job.get("motion_data") or {})
            callback(job, result)
        except Exception as exc:
            failure = {
                "status": "failed",
                "device": "cuda:0",
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
            }
            try:
                callback(job, failure)
            except Exception:
                pass
        finally:
            JOBS.task_done()


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, get_runtime().status())
        else:
            self._json(404, {"detail": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/jobs":
            self._json(404, {"detail": "Not found"})
            return
        if not WORKER_TOKEN or self.headers.get("X-Analysis-Worker-Token", "") != WORKER_TOKEN:
            self._json(401, {"detail": "Invalid worker token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            job = json.loads(self.rfile.read(length))
            if not all(job.get(key) for key in ("assessment_id", "callback_url")):
                raise ValueError("assessment_id and callback_url are required")
            JOBS.put(job)
            self._json(202, {"status": "queued", "assessment_id": job["assessment_id"]})
        except Exception as exc:
            self._json(400, {"detail": str(exc)})

    def log_message(self, message: str, *args: Any) -> None:
        print(f"[gpu-worker] {message % args}", flush=True)


if __name__ == "__main__":
    runtime = get_runtime()
    threading.Thread(target=run_jobs, daemon=True).start()
    print(json.dumps(runtime.status()), flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
