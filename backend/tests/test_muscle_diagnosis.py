import json
import re

from backend.muscle_diagnosis import build_muscle_activation_diagnosis


def _task(task_id, metrics=None, failed_steps=()):
    return {
        "task_id": task_id,
        "metrics": metrics or {},
        "steps": [
            {"step_id": step_id, "completed": False}
            for step_id in failed_steps
        ],
    }


def test_diagnosis_covers_all_four_function_packages():
    result = build_muscle_activation_diagnosis([
        _task("T2", {"shoulder_elevation_deg": 80}),
        _task("H3", {"thumb_index_distance_ratio": 0.5}),
        _task("L1", {"knee_extension_deg": 140}),
        _task("B3", {"trunk_sway_ratio": 0.4}),
    ])

    codes = {finding["code"] for finding in result["findings"]}
    assert result["packages_evaluated"] == ["balance", "hand", "lower_limb", "upper_limb"]
    assert {
        "UL_DELTOID_HYPO",
        "HAND_PINCH_HYPO",
        "LL_QUAD_HYPO",
        "BAL_PF_HYPO",
    } <= codes


def test_failed_release_step_can_trigger_timing_screen():
    result = build_muscle_activation_diagnosis([
        _task("H6", failed_steps=("H6-S2",)),
    ])

    assert "HAND_RELEASE_TIMING" in {finding["code"] for finding in result["findings"]}


def test_patient_facing_diagnosis_payload_is_english_only():
    result = build_muscle_activation_diagnosis([
        _task("L1", {"knee_extension_deg": 140}),
    ])

    assert not re.search(r"[\u4e00-\u9fff]", json.dumps(result, ensure_ascii=False))
    assert "screening-level" in result["reporting_rule"]


def test_no_threshold_crossing_returns_an_empty_screening_result():
    result = build_muscle_activation_diagnosis([
        _task("L1", {"knee_extension_deg": 165, "knee_stability_deg": 8}),
    ])

    assert result["packages_evaluated"] == ["lower_limb"]
    assert result["findings"] == []
