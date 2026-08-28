from backend.clinical_shadow_review import (
    apply_shadow_review_hold,
    build_improvement_candidate,
    compare_architecture_to_shadow_review,
    evaluate_promotion_gate,
    normalize_shadow_review,
)


def _review(domain="upper_limb", confidence=0.9):
    return normalize_shadow_review(
        {
            "status": "completed",
            "reviewer": {"provider": "test", "model": "vision-reviewer"},
            "tasks_reviewed": ["T1"],
            "observations": [
                {
                    "finding_code": "UPPER_LIMB_LIMITATION",
                    "label": "Reach looked limited",
                    "domain": domain,
                    "severity": "moderate",
                    "confidence": confidence,
                    "task_ids": ["T1"],
                    "evidence": "The wrist did not progress beyond the first target.",
                }
            ],
        }
    )


def _outputs(findings=None):
    return {
        "status": "completed",
        "quality": {
            "kinematics_valid": True,
            "model_scaled": True,
            "external_loads_valid": True,
            "residuals_within_threshold": True,
        },
        "functional_findings": findings or [],
    }


def test_shadow_reviewer_agreement_keeps_architecture_unchanged():
    issues = [{"code": "REACH_INCOMPLETE", "related_task": "T1"}]
    comparison = compare_architecture_to_shadow_review(
        issues, _outputs(), _review(), architecture_complete=True
    )
    assert comparison["status"] == "agreement"
    assert comparison["automatic_change_applied"] is False
    assert comparison["ground_truth_source"] == "clinician_adjudication_only"
    assert (
        build_improvement_candidate("assessment-1", comparison)["status"]
        == "not_created"
    )


def test_shadow_reviewer_disagreement_creates_a_review_case_and_blocks_rehab():
    comparison = compare_architecture_to_shadow_review(
        [], _outputs(), _review(), architecture_complete=True
    )
    assert comparison["status"] == "disagreement"
    assert comparison["mismatches"][0]["type"] == "reviewer_only"
    candidate = build_improvement_candidate("assessment-2", comparison)
    assert candidate["status"] == "pending_clinical_adjudication"
    assert candidate["automatic_change_applied"] is False
    held = apply_shadow_review_hold(
        {"status": "clear", "rehab_access": "allowed"}, comparison
    )
    assert held["status"] == "independent_review_required"
    assert held["rehab_access"] == "blocked"
    assert held["therapist_confirmation_required"] is True


def test_same_domain_but_different_functional_problem_is_not_counted_as_agreement():
    issues = [{"code": "SHOULDER_HIKE", "related_task": "T1"}]
    comparison = compare_architecture_to_shadow_review(
        issues, _outputs(), _review(), architecture_complete=True
    )
    assert comparison["status"] == "disagreement"
    categories = {item["category"] for item in comparison["mismatches"]}
    assert categories == {"shoulder_compensation", "reach_control"}


def test_shadow_review_never_treats_missing_reviewer_or_model_as_normal():
    missing = compare_architecture_to_shadow_review(
        [], {}, {"status": "failed"}, architecture_complete=False
    )
    assert missing["status"] == "reviewer_unavailable"
    awaiting = compare_architecture_to_shadow_review(
        [], {}, _review(), architecture_complete=False
    )
    assert awaiting["status"] == "awaiting_trusted_architecture"
    assert awaiting["agreement"] is None


def test_low_confidence_video_observation_does_not_create_a_mismatch():
    comparison = compare_architecture_to_shadow_review(
        [], _outputs(), _review(confidence=0.4), architecture_complete=True
    )
    assert comparison["status"] == "agreement"
    assert comparison["reviewer_domains"] == []


def test_promotion_gate_requires_cohort_holdout_approvals_and_rollback():
    incomplete = evaluate_promotion_gate({"clinician_adjudicated_cases": 29})
    assert incomplete["eligible_for_controlled_release"] is False
    complete = evaluate_promotion_gate(
        {
            "clinician_adjudicated_cases": 30,
            "independent_holdout_cases": 20,
            "clinician_approvals": 2,
            "subgroup_checks_passed": True,
            "safety_regression_detected": False,
            "rollback_plan_present": True,
        }
    )
    assert complete["eligible_for_controlled_release"] is True
    assert complete["automatic_release"] is False
