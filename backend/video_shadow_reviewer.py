"""Privacy-gated multimodal shadow review of saved assessment videos."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


TASK_LABELS = {
    "T1": "seated forward reach",
    "T2": "supported arm elevation",
    "T3": "hand to mouth",
    "H1": "open hand",
    "H3": "thumb-index pinch",
    "H4": "hand opening and closing",
    "L6": "walking observation",
}


SYSTEM_PROMPT = """You are an independent movement-video quality reviewer for a stroke rehabilitation assessment.
Review only observable function in the supplied sampled frames. Do not diagnose stroke, a disease, pain, weakness,
muscle activation, or an anatomical lesion. Do not infer anything that is not visible. Treat every task independently.
Return JSON only with this shape:
{
  "observations": [{
    "finding_code": "UPPER_LIMB_LIMITATION|HAND_CONTROL_LIMITATION|GAIT_LIMITATION|BALANCE_LIMITATION|TRUNK_COMPENSATION|ASSISTANCE_OR_FALL_RISK",
    "label": "short patient-safe label",
    "domain": "upper_limb|hand|lower_limb|balance",
    "severity": "mild|moderate|severe|uncertain",
    "confidence": 0.0,
    "task_ids": ["T1"],
    "evidence": "specific visible observation"
  }],
  "quality_concerns": [{"task_id": "T1", "code": "visibility|framing|occlusion|insufficient_sequence", "description": "short reason"}],
  "urgent_review_flags": [{"task_id": "L6", "code": "possible_fall_or_unsafe_support", "description": "short reason"}]
}
An observation requires a visible functional limitation, not simply an unusual posture. Use confidence below 0.65
when evidence is incomplete. Empty arrays are valid. Never recommend treatment or claim ground truth."""


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_json(text: str) -> Dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.lower().startswith("json"):
            value = value[4:].lstrip()
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Reviewer response must be a JSON object")
    return parsed


def _sample_video_frames(path: Path, frame_count: int) -> list[str]:
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return []
    try:
        total = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
        if total <= 0:
            positions = list(range(frame_count))
        elif frame_count == 1:
            positions = [total // 2]
        else:
            positions = [
                round(index * (total - 1) / (frame_count - 1))
                for index in range(frame_count)
            ]
        encoded: list[str] = []
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            if max(height, width) > 768:
                scale = 768.0 / max(height, width)
                frame = cv2.resize(
                    frame, (max(1, round(width * scale)), max(1, round(height * scale)))
                )
            ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
            if ok:
                encoded.append(
                    "data:image/jpeg;base64,"
                    + base64.b64encode(jpeg.tobytes()).decode("ascii")
                )
        return encoded
    finally:
        capture.release()


class ClinicalVideoShadowReviewer:
    def __init__(self) -> None:
        self.enabled = _enabled(os.environ.get("CLINICAL_SHADOW_REVIEW_ENABLED", "0"))
        self.external_video_allowed = _enabled(
            os.environ.get("CLINICAL_SHADOW_REVIEW_ALLOW_EXTERNAL_VIDEO", "0")
        )
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.model = os.environ.get("CLINICAL_SHADOW_REVIEW_MODEL", "gpt-4o").strip()
        self.frames_per_task = max(
            2,
            min(6, int(os.environ.get("CLINICAL_SHADOW_REVIEW_FRAMES_PER_TASK", "4"))),
        )

    def status(self) -> Dict[str, Any]:
        if not self.enabled:
            status = "disabled"
        elif not self.external_video_allowed or not self.api_key:
            status = "not_configured"
        else:
            status = "ready"
        return {
            "status": status,
            "model": self.model if status == "ready" else None,
            "external_video_transfer": self.external_video_allowed,
            "consent_required": True,
        }

    @staticmethod
    def _download(source: Mapping[str, Any], destination: Path) -> None:
        request = urllib.request.Request(
            str(source["url"]),
            headers={
                str(key): str(value)
                for key, value in (source.get("headers") or {}).items()
            },
        )
        with urllib.request.urlopen(request, timeout=180) as response, destination.open(
            "wb"
        ) as output:
            shutil.copyfileobj(response, output)

    def _collect_frames(
        self, sources: Iterable[Mapping[str, Any]], root: Path
    ) -> list[Dict[str, str]]:
        frames: list[Dict[str, str]] = []
        for source in sources:
            task_id = str(source.get("task_id") or "").strip()
            if not task_id:
                continue
            extension = (
                ".webm" if "webm" in str(source.get("content_type") or "") else ".mp4"
            )
            path = root / f"{task_id}{extension}"
            self._download(source, path)
            for index, data_url in enumerate(
                _sample_video_frames(path, self.frames_per_task), start=1
            ):
                frames.append(
                    {
                        "task_id": task_id,
                        "frame_index": str(index),
                        "data_url": data_url,
                    }
                )
        return frames

    def analyze(self, job: Mapping[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "reviewer": {"model": self.model}}
        if not self.external_video_allowed or not self.api_key:
            return {
                "status": "not_configured",
                "reviewer": {"model": self.model},
                "error": "External video review requires an API key and an explicit deployment privacy switch.",
            }
        if (job.get("patient_parameters") or {}).get(
            "ai_video_review_consent"
        ) is not True:
            return {
                "status": "consent_required",
                "reviewer": {"model": self.model},
                "error": "The patient has not explicitly consented to external AI video review.",
            }
        sources = [
            item for item in job.get("video_sources") or [] if isinstance(item, Mapping)
        ]
        if not sources:
            return {"status": "insufficient_video", "reviewer": {"model": self.model}}

        with tempfile.TemporaryDirectory(prefix="rehyn-shadow-review-") as temporary:
            frames = self._collect_frames(sources, Path(temporary))
            if not frames:
                return {
                    "status": "insufficient_video",
                    "reviewer": {"model": self.model},
                }
            content: list[Dict[str, Any]] = [
                {
                    "type": "text",
                    "text": (
                        "Review these chronologically sampled assessment frames. Names, email addresses, and account "
                        "identifiers were not included, but the patient's face may be visible. Each frame is preceded "
                        "by its task label. Compare movement only within the supplied task."
                    ),
                }
            ]
            for frame in frames:
                task_id = frame["task_id"]
                content.append(
                    {
                        "type": "text",
                        "text": f"Task {task_id} ({TASK_LABELS.get(task_id, 'guided movement')}), sampled frame {frame['frame_index']}.",
                    }
                )
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": frame["data_url"], "detail": "low"},
                    }
                )
            request = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(
                    {
                        "model": self.model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": content},
                        ],
                    }
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                response_payload = json.loads(response.read())
            response_text = response_payload["choices"][0]["message"]["content"]
            parsed = _safe_json(response_text or "{}")
            return {
                "status": "completed",
                "reviewer": {
                    "provider": "openai",
                    "model": self.model,
                    "response_id": str(response_payload.get("id") or ""),
                    "frame_sampling": "evenly_spaced_low_detail",
                    "frames_reviewed": len(frames),
                },
                "tasks_reviewed": sorted({item["task_id"] for item in frames}),
                "observations": parsed.get("observations") or [],
                "quality_concerns": parsed.get("quality_concerns") or [],
                "urgent_review_flags": parsed.get("urgent_review_flags") or [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }


SHADOW_REVIEWER = ClinicalVideoShadowReviewer()
