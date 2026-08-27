from backend.patient_insights import build_patient_insights


def test_research_model_creates_ranked_activation_and_observations():
    body_summary = {
        "domains": [
            {
                "domain": "upper_limb",
                "label": "Upper limb",
                "step_completion_percent": 75,
                "findings_count": 1,
                "status": "review_recommended",
            },
            {
                "domain": "lower_limb",
                "label": "Lower limb",
                "step_completion_percent": 100,
                "findings_count": 0,
                "status": "analysis_pending",
            },
        ],
    }
    research = {
        "status": "completed",
        "per_task": [{
            "task_id": "L6",
            "domain": "lower_limb",
            "muscle_activations": {
                "hamstrings": {"mean": 0.2, "peak": 0.45, "template_mean": 0.25, "delta_mean": -0.05},
                "vasti": {"mean": 0.3, "peak": 0.7, "template_mean": 0.2, "delta_mean": 0.1},
            },
        }],
        "kinematics": {"patient_knee_excursion_deg": 18.2, "template_knee_excursion_deg": 31.4},
    }

    insights = build_patient_insights(body_summary, research_stage=research)

    assert insights["status"] == "research_ready"
    assert insights["activation_profile"][0]["label"] == "Vasti"
    assert insights["modeled_domains"] == ["lower_limb"]
    assert len(insights["observations"]) == 3
    assert "not measured EMG" in insights["reporting_rule"]


def test_missing_model_output_is_processing_not_normal():
    insights = build_patient_insights({"domains": []}, model_analysis={"musculoskeletal_stage": {"status": "queued"}})

    assert insights["status"] == "processing"
    assert insights["activation_profile"] == []
    assert "being prepared" in insights["headline"]


def test_failed_model_stage_needs_review():
    insights = build_patient_insights(
        {"domains": []},
        model_analysis={"musculoskeletal_stage": {"status": "failed"}},
    )

    assert insights["status"] == "needs_review"
    assert insights["badge"] == "Analysis needs review"

    queue_failure = build_patient_insights(
        {"domains": []},
        model_analysis={"musculoskeletal_stage": {"status": "failed_to_queue"}},
    )
    assert queue_failure["status"] == "needs_review"
