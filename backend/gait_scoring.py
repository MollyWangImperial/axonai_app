"""Quality-gated lower-limb scoring for uploaded walking videos.

This is an engineering movement score, not a validated clinical gait scale.
Camera/tracking quality determines whether a clip is scorable; it never earns
or removes patient-performance points.
"""

from __future__ import annotations

from math import isfinite
from statistics import median
from typing import Any, Iterable, Mapping


VERSION = "rehyn-gait-score-1"
SUPPORTED_CAMERA_METHODS = {
    "body_centric_2d_background_ransac",
    "body_centric_3d_background_ransac",
    "wham_dpvo_slam",
}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = float(value)
        return value if isfinite(value) else None
    return None


def _numbers(values: Iterable[Any]) -> list[float]:
    return [number for value in values if (number := _number(value)) is not None]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _ramp_up(value: float, zero_at: float, full_at: float) -> float:
    return _clamp((value - zero_at) / max(full_at - zero_at, 1e-9))


def _ramp_down(value: float, full_until: float, zero_at: float) -> float:
    return 1.0 - _ramp_up(value, full_until, zero_at)


def _symmetry(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    smaller, larger = sorted((abs(median(left)), abs(median(right))))
    return _clamp(smaller / larger) if larger > 1e-9 else None


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    centre = sum(values) / len(values)
    if centre <= 1e-9:
        return None
    variance = sum((value - centre) ** 2 for value in values) / len(values)
    return variance ** 0.5 / centre


def _weighted_score(components: Mapping[str, dict[str, Any]]) -> float | None:
    available = [item for item in components.values() if _number(item.get("score")) is not None]
    weight = sum(float(item["weight"]) for item in available)
    if not available or weight <= 0:
        return None
    return round(sum(float(item["score"]) * float(item["weight"]) for item in available) / weight, 1)


def score_gait_features(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert camera-robust gait features into a transparent 0-100 score.

    Expected step events contain ``side``, ``time_s`` and a body-normalized
    2D step-length proxy. Absolute distance and raw image travel are excluded
    because they are not reliable with a moving monocular camera.
    """

    quality = payload.get("quality") if isinstance(payload.get("quality"), Mapping) else {}
    features = payload.get("features") if isinstance(payload.get("features"), Mapping) else {}
    camera_method = str(payload.get("camera_motion_handling") or "")
    events = [
        event for event in (features.get("step_events") or [])
        if isinstance(event, Mapping)
        and str(event.get("side")) in {"left", "right"}
        and _number(event.get("time_s")) is not None
        and _number(event.get("step_length_proxy_leg_ratio")) is not None
    ]
    events.sort(key=lambda item: float(item["time_s"]))

    tracking_coverage = _number(quality.get("tracking_coverage")) or 0.0
    full_body_visibility = _number(quality.get("full_body_visibility")) or 0.0
    distal_visibility = _number(quality.get("distal_visibility")) or 0.0
    detected_frames = int(_number(quality.get("detected_frames")) or 0)
    multi_person_ratio = _number(quality.get("multi_person_ratio")) or 0.0
    left_events = [event for event in events if event["side"] == "left"]
    right_events = [event for event in events if event["side"] == "right"]

    failures = []
    if camera_method not in SUPPORTED_CAMERA_METHODS:
        failures.append("camera_motion_not_compensated")
    if detected_frames < 24:
        failures.append("too_few_tracked_frames")
    if tracking_coverage < 0.72:
        failures.append("insufficient_pose_tracking")
    if full_body_visibility < 0.50 or distal_visibility < 0.50:
        failures.append("feet_not_visible_enough")
    if multi_person_ratio > 0.20:
        failures.append("multiple_people_in_frame")
    if len(events) < 3 or not left_events or not right_events:
        failures.append("too_few_alternating_steps")

    base = {
        "version": VERSION,
        "status": "unscorable" if failures else "scored",
        "score": None,
        "quality": dict(quality),
        "camera_motion_handling": camera_method,
        "analysis_method": str(payload.get("analysis_method") or ""),
        "provenance": dict(payload.get("provenance") or {}),
        "reason_codes": failures,
    }
    if failures:
        return base

    left_lengths = _numbers(event["step_length_proxy_leg_ratio"] for event in left_events)
    right_lengths = _numbers(event["step_length_proxy_leg_ratio"] for event in right_events)
    alternating_intervals = []
    left_times = []
    right_times = []
    for previous, current in zip(events, events[1:]):
        if previous["side"] == current["side"]:
            continue
        interval = float(current["time_s"]) - float(previous["time_s"])
        if 0.18 <= interval <= 2.5:
            alternating_intervals.append(interval)
            (left_times if current["side"] == "left" else right_times).append(interval)

    median_step_length = median(left_lengths + right_lengths)
    length_symmetry = _symmetry(left_lengths, right_lengths)
    time_symmetry = _symmetry(left_times, right_times)
    rhythm_cv = _coefficient_of_variation(alternating_intervals)
    left_clearance = _number(features.get("left_foot_clearance_leg_ratio"))
    right_clearance = _number(features.get("right_foot_clearance_leg_ratio"))
    minimum_clearance = min(left_clearance, right_clearance) if left_clearance is not None and right_clearance is not None else None
    left_knee = _number(features.get("left_swing_knee_flexion_deg"))
    right_knee = _number(features.get("right_swing_knee_flexion_deg"))
    minimum_knee = min(left_knee, right_knee) if left_knee is not None and right_knee is not None else None
    trunk_excursion = _number(features.get("trunk_lateral_excursion_deg"))
    trunk_reliable = bool(features.get("trunk_measurement_reliable"))

    clearance_parts = []
    if bool(features.get("foot_clearance_reliable")) and minimum_clearance is not None:
        clearance_parts.append(_ramp_up(minimum_clearance, 0.008, 0.040))
    if minimum_knee is not None:
        clearance_parts.append(_ramp_up(minimum_knee, 15.0, 50.0))
    clearance_score = 100 * sum(clearance_parts) / len(clearance_parts) if clearance_parts else None

    components = {
        "step_length_proxy": {
            "score": round(100 * _ramp_up(median_step_length, 0.10, 0.35), 1),
            "weight": 20,
            "observed": round(median_step_length, 3),
            "unit": "2D inter-foot separation / leg length",
        },
        "step_length_proxy_symmetry": {
            "score": round(100 * _ramp_up(length_symmetry, 0.55, 0.90), 1) if length_symmetry is not None else None,
            "weight": 25,
            "observed": round(length_symmetry, 3) if length_symmetry is not None else None,
            "unit": "ratio",
        },
        "step_time_symmetry": {
            "score": round(100 * _ramp_up(time_symmetry, 0.60, 0.92), 1) if time_symmetry is not None else None,
            "weight": 20,
            "observed": round(time_symmetry, 3) if time_symmetry is not None else None,
            "unit": "ratio",
        },
        "rhythm_regularity": {
            "score": round(100 * _ramp_down(rhythm_cv, 0.08, 0.35), 1) if rhythm_cv is not None else None,
            "weight": 15,
            "observed": round(rhythm_cv, 3) if rhythm_cv is not None else None,
            "unit": "coefficient of variation",
        },
        "swing_clearance_proxy": {
            "score": round(clearance_score, 1) if clearance_score is not None else None,
            "weight": 10,
            "observed": {
                "minimum_clearance_leg_ratio": round(minimum_clearance, 3) if minimum_clearance is not None else None,
                "minimum_knee_flexion_deg": round(minimum_knee, 1) if minimum_knee is not None else None,
            },
            "unit": "combined",
        },
        "trunk_stability": {
            "score": round(100 * _ramp_down(trunk_excursion, 5.0, 20.0), 1) if trunk_reliable and trunk_excursion is not None else None,
            "weight": 10,
            "observed": round(trunk_excursion, 1) if trunk_excursion is not None else None,
            "unit": "degrees",
        },
    }
    score = _weighted_score(components)
    symmetry_values = [value for value in (length_symmetry, time_symmetry) if value is not None]
    bilateral_symmetry = round(sum(symmetry_values) / len(symmetry_values), 3) if symmetry_values else None

    return {
        **base,
        "status": "scored" if score is not None else "unscorable",
        "score": score,
        "reason_codes": [] if score is not None else ["insufficient_gait_components"],
        "components": components,
        "summary": {
            "step_count": len(events),
            "alternating_intervals": len(alternating_intervals),
            "median_step_length_proxy_leg_ratio": round(median_step_length, 3),
            "step_length_symmetry": round(length_symmetry, 3) if length_symmetry is not None else None,
            "step_time_symmetry": round(time_symmetry, 3) if time_symmetry is not None else None,
            "rhythm_cv": round(rhythm_cv, 3) if rhythm_cv is not None else None,
            "bilateral_symmetry": bilateral_symmetry,
        },
    }
