from pathlib import Path

import pytest

from backend.biomechanics_pipeline import (
    aggregate_model_outputs,
    build_model_analysis_manifest,
    model_activation_report,
    patient_body_function_summary,
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


def test_body_function_summary_separates_domains_and_waits_before_calling_results_normal():
    tasks = [
        {"task_id": "T1", "completed_steps": 2, "total_steps": 2, "duration_ms": 20000},
        {"task_id": "H1", "completed_steps": 3, "total_steps": 3, "duration_ms": 12000},
        {"task_id": "L6", "completed_steps": 3, "total_steps": 3, "duration_ms": 28000},
    ]
    pending = patient_body_function_summary(tasks, [], {}, ("upper_limb", "hand", "lower_limb"))
    assert pending["overall_status"] == "analysis_pending"
    assert [item["domain"] for item in pending["domains"]] == ["upper_limb", "hand", "lower_limb"]
    assert all(item["status"] == "analysis_pending" for item in pending["domains"])
    assert pending["domains"][0]["average_task_duration_ms"] == 20000

    validated_normal = {
        "status": "completed",
        "quality": {
            "kinematics_valid": True,
            "model_scaled": True,
            "external_loads_valid": True,
            "residuals_within_threshold": True,
        },
        "functional_findings": [],
    }
    completed = patient_body_function_summary(tasks, [], validated_normal, ("upper_limb", "hand", "lower_limb"))
    assert completed["overall_status"] == "no_observable_difficulty"
    assert all(item["status"] == "no_observable_difficulty" for item in completed["domains"])
    assert all(item["step_completion_percent"] == 100 for item in completed["domains"])


def test_body_function_summary_counts_domain_findings():
    summary = patient_body_function_summary(
        [{"task_id": "H3", "completed_steps": 1, "total_steps": 2, "duration_ms": 10000}],
        [{"code": "PINCH_IMPAIRED", "related_task": "H3"}],
        {},
        ("hand",),
    )
    hand = summary["domains"][0]
    assert hand["status"] == "review_recommended"
    assert hand["findings_count"] == 1
    assert hand["step_completion_percent"] == 50


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
    assert "Body function summary" in source
    assert 'testID={`body-function-${domain.domain}`}' in source
    assert "Tasks completed" in source
    assert "Guided steps" in source
    assert "Average task" in source
    assert "Findings to review" in source
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


def test_patient_results_and_direct_plan_route_enforce_clinical_review_hold():
    root = Path(__file__).resolve().parents[2] / "frontend" / "app"
    results = (root / "results.tsx").read_text(encoding="utf-8")
    plan = (root / "rehab-plan.tsx").read_text(encoding="utf-8")
    assert '"clinical-review-hold"' in results
    assert 'reviewGate?.rehab_access === "blocked"' in results
    assert '"plan-clinical-review-hold"' in plan
    assert 'data.clinical_review_gate?.rehab_access !== "allowed"' in plan
    assert 'data.rehab_plan.length === 0' in plan
    assert '"plan-no-rehab-needed"' in plan
    assert 'testID={canViewPlan ? "results-view-plan" : "results-return-home"}' in results
    assert "Please confirm the results with your therapist" in (
        Path(__file__).resolve().parents[1] / "assessment_fusion.py"
    ).read_text(encoding="utf-8")
