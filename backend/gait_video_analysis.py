"""Extract rough, camera-robust 2D gait features from a frontal video.

The video is sampled at a modest frame rate and each image-space pose is
expressed relative to the patient's pelvis, trunk axis, and visible leg length.
That removes camera pan, zoom, and roll from the step signals. Background
optical flow independently estimates camera roll for the trunk-stability term.
No 3D reconstruction, SLAM, WHAM, or mesh fitting is used in this path.
"""

from __future__ import annotations

import argparse
import json
from math import atan2, ceil, degrees
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from scipy.signal import find_peaks, savgol_filter


LANDMARK = {
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_heel": 29,
    "right_heel": 30,
    "left_toe": 31,
    "right_toe": 32,
}
LOWER_INDICES = tuple(LANDMARK[name] for name in (
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_toe", "right_toe",
))


def _unit(vector: np.ndarray) -> np.ndarray | None:
    norm = float(np.linalg.norm(vector))
    return vector / norm if np.isfinite(norm) and norm > 1e-6 else None


def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    first = a - b
    second = c - b
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-9:
        return float("nan")
    cosine = float(np.dot(first, second) / denominator)
    return degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _body_normalized_landmarks_2d(image_xy: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Remove 2D camera translation, roll, and visible subject scale.

    The local axes are rebuilt from the patient's hips and trunk on every
    sampled frame. A moving recorder therefore cannot create step length merely
    by panning or changing distance from the patient.
    """

    pelvis = (image_xy[LANDMARK["left_hip"]] + image_xy[LANDMARK["right_hip"]]) / 2
    shoulders = (image_xy[LANDMARK["left_shoulder"]] + image_xy[LANDMARK["right_shoulder"]]) / 2
    up = _unit(shoulders - pelvis)
    if up is None:
        return None
    lateral_raw = image_xy[LANDMARK["right_hip"]] - image_xy[LANDMARK["left_hip"]]
    lateral = _unit(lateral_raw - up * np.dot(lateral_raw, up))
    if lateral is None:
        return None
    leg_lengths = []
    for side in ("left", "right"):
        hip = image_xy[LANDMARK[f"{side}_hip"]]
        knee = image_xy[LANDMARK[f"{side}_knee"]]
        ankle = image_xy[LANDMARK[f"{side}_ankle"]]
        leg_lengths.append(np.linalg.norm(hip - knee) + np.linalg.norm(knee - ankle))
    leg_length = float(np.mean(leg_lengths))
    if not np.isfinite(leg_length) or leg_length <= 0.04:
        return None
    basis = np.stack((lateral, up), axis=1)
    return (image_xy - pelvis) @ basis / leg_length, leg_length


def _smooth(values: np.ndarray, fps: float) -> np.ndarray:
    if len(values) < 5:
        return values
    window = min(len(values) if len(values) % 2 else len(values) - 1, max(5, int(round(fps * 0.35)) | 1))
    return savgol_filter(values, window, min(3, window - 2))


def _background_motion(previous: np.ndarray, current: np.ndarray, bbox: tuple[int, int, int, int] | None) -> tuple[float, float] | None:
    mask = np.full(previous.shape, 255, dtype=np.uint8)
    if bbox:
        x1, y1, x2, y2 = bbox
        margin_x = int((x2 - x1) * 0.25)
        margin_y = int((y2 - y1) * 0.15)
        cv2.rectangle(
            mask,
            (max(0, x1 - margin_x), max(0, y1 - margin_y)),
            (min(previous.shape[1] - 1, x2 + margin_x), min(previous.shape[0] - 1, y2 + margin_y)),
            0,
            -1,
        )
    points = cv2.goodFeaturesToTrack(previous, 180, 0.01, 8, mask=mask)
    if points is None or len(points) < 12:
        return None
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(previous, current, points, None)
    if tracked is None or status is None:
        return None
    valid = status.reshape(-1).astype(bool)
    if int(valid.sum()) < 10:
        return None
    matrix, inliers = cv2.estimateAffinePartial2D(
        points.reshape(-1, 2)[valid],
        tracked.reshape(-1, 2)[valid],
        method=cv2.RANSAC,
        ransacReprojThreshold=2.5,
    )
    if matrix is None or inliers is None or int(inliers.sum()) < 8:
        return None
    rotation = degrees(atan2(float(matrix[1, 0]), float(matrix[0, 0])))
    translation = float(np.linalg.norm(matrix[:, 2])) / max(np.hypot(*previous.shape), 1.0)
    return rotation, translation


def _select_pose(result: Any, width: int, height: int) -> tuple[Any, tuple[int, int, int, int] | None, int]:
    candidates = []
    for index, image_landmarks in enumerate(result.pose_landmarks or []):
        xs = np.asarray([item.x for item in image_landmarks], dtype=float)
        ys = np.asarray([item.y for item in image_landmarks], dtype=float)
        bbox = (
            int(np.clip(xs.min(), 0, 1) * width),
            int(np.clip(ys.min(), 0, 1) * height),
            int(np.clip(xs.max(), 0, 1) * width),
            int(np.clip(ys.max(), 0, 1) * height),
        )
        area = max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])
        visibility = float(np.mean([image_landmarks[item].visibility for item in LOWER_INDICES]))
        candidates.append((area * max(visibility, 0.05), index, bbox))
    if not candidates:
        return None, None, 0
    _, index, bbox = max(candidates)
    return result.pose_landmarks[index], bbox, len(candidates)


def analyze_video(video: Path, model: Path, source_video_id: str = "") -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("Walking video could not be decoded")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_stride = max(1, int(ceil(fps / 12.0)))
    sampled_fps = fps / sample_stride
    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=2,
        min_pose_detection_confidence=0.45,
        min_pose_presence_confidence=0.45,
        min_tracking_confidence=0.45,
    )

    records = []
    previous_gray = None
    previous_bbox = None
    cumulative_roll = 0.0
    camera_rotations = []
    camera_translations = []
    camera_motion_frames = 0
    multi_person_frames = 0
    frame_index = 0
    sampled_frames = 0
    with vision.PoseLandmarker.create_from_options(options) as detector:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            current_index = frame_index
            frame_index += 1
            if current_index % sample_stride != 0:
                continue
            sampled_frames += 1
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous_gray is not None:
                motion = _background_motion(previous_gray, gray, previous_bbox)
                if motion:
                    rotation, translation = motion
                    cumulative_roll += rotation
                    camera_rotations.append(rotation)
                    camera_translations.append(translation)
                    camera_motion_frames += 1
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            result = detector.detect_for_video(image, int(round(current_index * 1000 / fps)))
            image_points, bbox, count = _select_pose(result, width, height)
            multi_person_frames += int(count > 1)
            previous_gray = gray
            previous_bbox = bbox
            if image_points is None:
                continue

            image_xy = np.asarray([[item.x, item.y] for item in image_points], dtype=float)
            visibility = np.asarray([item.visibility for item in image_points], dtype=float)
            normalized = _body_normalized_landmarks_2d(image_xy)
            if normalized is None:
                continue
            body, _leg_length = normalized
            feet = {}
            knee_flexion = {}
            for side in ("left", "right"):
                feet[side] = np.mean([
                    body[LANDMARK[f"{side}_ankle"]],
                    body[LANDMARK[f"{side}_heel"]],
                    body[LANDMARK[f"{side}_toe"]],
                ], axis=0)
                knee_flexion[side] = 180.0 - _angle(
                    image_xy[LANDMARK[f"{side}_hip"]],
                    image_xy[LANDMARK[f"{side}_knee"]],
                    image_xy[LANDMARK[f"{side}_ankle"]],
                )
            image_pelvis = (image_xy[LANDMARK["left_hip"]] + image_xy[LANDMARK["right_hip"]]) / 2
            image_shoulders = (image_xy[LANDMARK["left_shoulder"]] + image_xy[LANDMARK["right_shoulder"]]) / 2
            trunk_angle = degrees(atan2(
                float(image_shoulders[0] - image_pelvis[0]),
                float(image_pelvis[1] - image_shoulders[1]),
            )) - cumulative_roll
            records.append({
                "time": current_index / fps,
                "visibility": visibility,
                "left_foot": feet["left"],
                "right_foot": feet["right"],
                "left_knee": knee_flexion["left"],
                "right_knee": knee_flexion["right"],
                "trunk": trunk_angle,
            })
    capture.release()

    if not records:
        raise RuntimeError("No complete body pose was found in the walking video")
    times = np.asarray([item["time"] for item in records])
    left_foot = np.asarray([item["left_foot"] for item in records])
    right_foot = np.asarray([item["right_foot"] for item in records])
    forward_difference = _smooth(left_foot[:, 1] - right_foot[:, 1], sampled_fps)
    foot_separation = _smooth(np.linalg.norm(left_foot - right_foot, axis=1), sampled_fps)
    prominence = max(0.035, float(np.ptp(forward_difference)) * 0.15)
    distance = max(3, int(round(sampled_fps * 0.28)))
    left_peaks, _ = find_peaks(forward_difference, prominence=prominence, distance=distance)
    right_peaks, _ = find_peaks(-forward_difference, prominence=prominence, distance=distance)
    events = sorted(
        [
            {"index": int(index), "side": side, "time_s": float(times[index]), "step_length_proxy_leg_ratio": float(foot_separation[index])}
            for side, indices in (("left", left_peaks), ("right", right_peaks))
            for index in indices
            if times[index] >= times[0] + 0.12 and times[index] <= times[-1] - 0.12
        ],
        key=lambda item: item["time_s"],
    )
    alternating = []
    for event in events:
        if alternating and alternating[-1]["side"] == event["side"]:
            if event["step_length_proxy_leg_ratio"] > alternating[-1]["step_length_proxy_leg_ratio"]:
                alternating[-1] = event
        else:
            alternating.append(event)
    for event in alternating:
        event.pop("index", None)

    visibility = np.asarray([item["visibility"] for item in records])
    full_body = np.all(visibility[:, LOWER_INDICES] >= 0.45, axis=1)
    distal_indices = tuple(LANDMARK[name] for name in (
        "left_knee", "right_knee", "left_ankle", "right_ankle",
        "left_heel", "right_heel", "left_toe", "right_toe",
    ))
    left_height = _smooth(left_foot[:, 1], sampled_fps)
    right_height = _smooth(right_foot[:, 1], sampled_fps)
    trunk = _smooth(np.asarray([item["trunk"] for item in records]), sampled_fps)
    background_ratio = camera_motion_frames / max(1, sampled_frames - 1)
    quality = {
        "total_frames": frame_index or total_frames,
        "sampled_frames": sampled_frames,
        "detected_frames": len(records),
        "tracking_coverage": round(len(records) / max(1, sampled_frames), 3),
        "full_body_visibility": round(float(np.mean(full_body)), 3),
        "distal_visibility": round(float(np.mean(visibility[:, distal_indices])), 3),
        "multi_person_ratio": round(multi_person_frames / max(1, sampled_frames), 3),
        "background_motion_reliable_ratio": round(background_ratio, 3),
    }
    features = {
        "step_events": alternating,
        "left_foot_clearance_leg_ratio": round(float(np.percentile(left_height, 95) - np.percentile(left_height, 5)), 4),
        "right_foot_clearance_leg_ratio": round(float(np.percentile(right_height, 95) - np.percentile(right_height, 5)), 4),
        # A frontal 2D video cannot estimate true vertical toe clearance.
        "foot_clearance_reliable": False,
        "left_swing_knee_flexion_deg": round(float(np.percentile([item["left_knee"] for item in records], 90)), 1),
        "right_swing_knee_flexion_deg": round(float(np.percentile([item["right_knee"] for item in records], 90)), 1),
        "trunk_lateral_excursion_deg": round(float(np.percentile(trunk, 95) - np.percentile(trunk, 5)), 1),
        "trunk_measurement_reliable": background_ratio >= 0.50,
        "camera_rotation_rms_deg_per_frame": round(float(np.sqrt(np.mean(np.square(camera_rotations)))), 3) if camera_rotations else None,
        "camera_translation_median_frame_ratio": round(float(np.median(camera_translations)), 5) if camera_translations else None,
    }
    return {
        "status": "completed",
        "analysis_method": "mediapipe_sampled_body_centric_2d_v1",
        "camera_motion_handling": "body_centric_2d_background_ransac",
        "coordinate_frame": "pelvis_centered_leg_normalized_2d",
        "quality": quality,
        "features": features,
        "provenance": {
            "source_video_id": source_video_id,
            "pose_model": model.name,
            "video_fps": round(fps, 3),
            "analysis_fps": round(sampled_fps, 3),
            "uses_3d_reconstruction": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-video-id", default="")
    args = parser.parse_args()
    result = analyze_video(args.video, args.model, args.source_video_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
