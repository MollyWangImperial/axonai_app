from pathlib import Path

import pytest

from backend.biomechanics_pipeline import (
    aggregate_model_outputs,
    build_model_analysis_manifest,
    model_activation_report,
    patient_collection_summary,
    validate_model_outputs,
)


def _valid_task_output(task_id: str, video_id: str):
    return {
        "task_id": task_id,
        "quality": {
            "kinematics_valid": True,
            "model_scaled": True,
            "external_loads_valid": True,
            "residuals_within_threshold": True,
        },
        "external_load_method": "gravity_only_seated_no_external_object",
        "muscle_activations": {
            "anterior_deltoid": {"mean": 0.31, "peak": 0.62},
        },
        "muscle_forces_n": {"anterior_deltoid": 112.0},
        "joint_moments_nm": {"shoulder_flexion": 18.5},
        "functional_findings": [
            {
                "code": "UL_REDUCED_DRIVE",
                "label": "Reduced shoulder elevation drive",
                "severity": "moderate",
                "evidence_metrics": {"peak_activation": 0.62},
            }
        ],
        "provenance": {
            "solver": "OpenSim MocoInverse",
            "model_version": "upper-extremity-1.0",
            "source_video_id": video_id,
            "code_version": "abc123",
        },
    }


def test_patient_summary_contains_collection_metrics_only():
    summary = patient_collection_summary(
        [
            {"task_id": "T1", "completed_steps": 3, "total_steps": 4, "duration_ms": 61000},
            {"task_id": "H1", "completed_steps": 2, "total_steps": 2, "duration_ms": 29000},
            {"task_id": "L6", "completed_steps": 1, "total_steps": 2, "duration_ms": 30000},
        ],
        7,
    )
    assert summary == {
        "tasks_collected": 3,
        "tasks_expected": 7,
        "completed_steps": 6,
        "total_steps": 8,
        "completion_percent": 75,
        "duration_ms": 120000,
        "domains": [
            {"domain": "upper_limb", "label": "Upper limb"},
            {"domain": "hand", "label": "Hand function"},
            {"domain": "lower_limb", "label": "Walking"},
        ],
    }


def test_manifest_links_each_task_to_its_saved_video():
    manifest = build_model_analysis_manifest(
        "assessment-1",
        ["T1", "H1", "L6"],
        {"T1": {"id": "video-t1"}, "H1": {"id": "video-h1"}, "L6": {"id": "video-l6"}},
    )
    assert manifest["status"] == "queued"
    assert {item["task_id"]: item["video_id"] for item in manifest["tasks"]} == {
        "T1": "video-t1",
        "H1": "video-h1",
        "L6": "video-l6",
    }


def test_model_outputs_require_quality_provenance_and_matching_video():
    valid = {"status": "completed", "per_task": [_valid_task_output("T1", "video-t1")]}
    checked = validate_model_outputs(valid, ["T1"], {"T1": "video-t1"})
    outputs = aggregate_model_outputs(checked)
    report = model_activation_report(outputs)
    assert outputs["muscle_activations"]["T1"]["anterior_deltoid"]["mean"] == 0.31
    assert report["status"] == "model_complete"
    assert report["findings"][0]["provenance"] == "validated_musculoskeletal_model"

    invalid = _valid_task_output("T1", "wrong-video")
    with pytest.raises(ValueError, match="saved source video"):
        validate_model_outputs({"status": "completed", "per_task": [invalid]}, ["T1"], {"T1": "video-t1"})

    with pytest.raises(ValueError, match="no saved source video"):
        validate_model_outputs(valid, ["T1"], {"T1": None})

    invalid = _valid_task_output("T1", "video-t1")
    invalid["quality"]["external_loads_valid"] = False
    with pytest.raises(ValueError, match="quality gate"):
        validate_model_outputs({"status": "completed", "per_task": [invalid]}, ["T1"])


def test_patient_results_screen_does_not_render_backend_diagnostics():
    source = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")
    assert "Task collection" in source
    assert "Guided steps completed" in source
    for internal_label in (
        "Analysis quality",
        "Movement phenotypes identified",
        "Muscle activation screening",
        "Biomechanics and measurement status",
        "Clinical measurement form",
        "Movement and survey check",
    ):
        assert internal_label not in source
