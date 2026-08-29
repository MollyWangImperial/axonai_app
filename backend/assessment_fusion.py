"""Evidence provenance and survey reconciliation for functional assessment.

The camera and survey are independent evidence sources. Agreement increases
confidence; disagreement is surfaced for review instead of being overwritten.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


DOMAIN_LABELS = {
    "upper_limb": "arm and shoulder",
    "hand": "hand",
    "lower_limb": "walking and lower limb",
    "balance": "balance",
}


def _task_domain(task_id: str) -> str:
    if task_id.startswith("H"):
        return "hand"
    if task_id.startswith("L"):
        return "lower_limb"
    if task_id.startswith("B"):
        return "balance"
    return "upper_limb"


def _survey_domains(patient_parameters: Mapping[str, Any]) -> tuple[set[str], bool, List[str]]:
    areas = {str(item).strip().lower() for item in patient_parameters.get("affected_areas") or []}
    domains: set[str] = set()
    evidence: List[str] = []
    if areas & {"left_upper", "right_upper"}:
        domains.update(("upper_limb", "hand"))
        evidence.append("The onboarding survey reports an affected upper limb.")
    if areas & {"left_lower", "right_lower"}:
        domains.update(("lower_limb", "balance"))
        evidence.append("The onboarding survey reports an affected lower limb.")

    goal_text = " ".join(
        [str(patient_parameters.get("primary_goal") or "")]
        + [str(item) for item in patient_parameters.get("patient_priorities") or []]
    ).lower()
    if any(word in goal_text for word in ("hand", "finger", "pinch", "button", "write", "fork", "grasp")):
        domains.add("hand")
        evidence.append("The patient's stated goals include hand use.")
    if any(word in goal_text for word in ("arm", "shoulder", "reach", "overhead", "dress", "feed")):
        domains.add("upper_limb")
        evidence.append("The patient's stated goals include arm or shoulder use.")
    if any(word in goal_text for word in ("walk", "step", "stairs", "stand", "mobility", "balance")):
        domains.update(("lower_limb", "balance"))
        evidence.append("The patient's stated goals include walking, standing, or balance.")

    survey_is_explicit = bool(areas) and "unsure" not in areas
    return domains, survey_is_explicit, evidence


def _item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def build_clinical_review_gate(
    issues: Sequence[Any],
    patient_parameters: Mapping[str, Any] | None,
    task_results: Sequence[Any] | None,
    musculoskeletal_outputs: Mapping[str, Any] | None,
    expected_task_count: int = 0,
) -> Dict[str, Any]:
    """Gate automatic rehab when validated objective and survey evidence diverge.

    Missing model output is never interpreted as normal. The discrepancy state
    is reached only after complete task collection and quality-gated model output.
    """
    params = patient_parameters or {}
    reported_domains, survey_is_explicit, _ = _survey_domains(params)
    results = list(task_results or [])
    outputs = dict(musculoskeletal_outputs or {})
    quality = outputs.get("quality") if isinstance(outputs.get("quality"), Mapping) else {}
    model_complete = outputs.get("status") == "completed" and all(
        quality.get(key) is True
        for key in (
            "kinematics_valid",
            "model_scaled",
            "external_loads_valid",
            "residuals_within_threshold",
        )
    )
    collection_complete = bool(results) and all(
        int(_item_value(item, "total_steps", 0) or 0) > 0
        and int(_item_value(item, "completed_steps", 0) or 0)
        >= int(_item_value(item, "total_steps", 0) or 0)
        for item in results
    )
    if expected_task_count:
        collection_complete = collection_complete and len(results) >= expected_task_count

    camera_findings = [
        item for item in issues
        if str(_item_value(item, "code", "")) != "NO_ISSUES"
    ]
    model_findings = outputs.get("functional_findings") or []
    explicit_report = survey_is_explicit and bool(reported_domains)

    base = {
        "version": "1.0",
        "therapist_confirmation_required": False,
        "reported_domains": sorted(reported_domains),
        "objective_evidence": {
            "task_collection_complete": collection_complete,
            "validated_model_complete": model_complete,
            "camera_findings_count": len(camera_findings),
            "model_findings_count": len(model_findings),
        },
        "reporting_rule": (
            "A missing or incomplete model is never treated as evidence of normal function. "
            "Patient-reported symptoms are retained for clinical review even when they are not observed in the recorded tasks."
        ),
    }

    if not collection_complete or not model_complete:
        return {
            **base,
            "status": "awaiting_model_analysis",
            "rehab_access": "blocked",
            "reason_code": "objective_review_incomplete",
            "patient_title": "Your movement analysis is still in progress",
            "patient_message": "Your recordings and survey answers have been saved. We will not prepare exercises until the movement and musculoskeletal analysis is complete.",
            "next_step": "Return later to review the result. Do not begin a new rehabilitation plan from this assessment yet.",
        }

    if camera_findings or model_findings:
        return {
            **base,
            "status": "clear",
            "rehab_access": "allowed",
            "reason_code": "objective_survey_hold_not_required",
            "patient_title": "Your plan can be prepared",
            "patient_message": "Your completed, validated assessment can be used to prepare the next step in your rehabilitation plan.",
            "next_step": "Review the plan with your therapist before beginning new rehabilitation activities.",
        }

    if explicit_report:
        return {
            **base,
            "status": "therapist_confirmation_required",
            "rehab_access": "blocked",
            "reason_code": "survey_objective_mismatch_no_observable_impairment",
            "therapist_confirmation_required": True,
            "patient_title": "Please confirm these results with your therapist",
            "patient_message": (
                "Your survey reports symptoms, but the completed movement assessment and validated musculoskeletal model "
                "did not detect an observable functional impairment in these tasks. This does not mean your symptoms are not real."
            ),
            "next_step": "Please confirm the results with your therapist before starting any rehabilitation exercises.",
        }

    return {
        **base,
        "status": "no_rehab_needed",
        "rehab_access": "not_needed",
        "reason_code": "no_observable_impairment_in_assessed_tasks",
        "patient_title": "No rehabilitation plan is recommended from this assessment",
        "patient_message": (
            "The completed tasks and quality-validated movement analysis did not detect an observable functional "
            "difficulty in the areas assessed."
        ),
        "next_step": "Continue your usual activities and speak with a therapist if you notice symptoms or a change in function.",
    }


def build_survey_consistency(
    issues: Sequence[Any],
    patient_parameters: Mapping[str, Any] | None,
    task_results: Sequence[Any] | None = None,
) -> Dict[str, Any]:
    params = patient_parameters or {}
    reported_domains, survey_is_explicit, general_evidence = _survey_domains(params)
    findings: List[Dict[str, Any]] = []
    movement_domains: set[str] = set()

    for issue in issues:
        if str(getattr(issue, "code", "")) == "NO_ISSUES":
            continue
        task_id = str(getattr(issue, "related_task", "") or "")
        domain = _task_domain(task_id)
        movement_domains.add(domain)
        if domain in reported_domains:
            status = "consistent"
            interpretation = "The movement finding agrees with the area or goal reported in the survey."
            action = "Use both sources when prioritizing clinician review and the rehabilitation plan."
        elif survey_is_explicit:
            status = "discordant"
            interpretation = "The camera finding was not reported in the survey. This may be a new observation, a camera error, or a difference between perceived and observed function."
            action = "Recheck task quality and ask the patient or clinician to confirm before treating it as an established problem."
        else:
            status = "not_addressed"
            interpretation = "The survey did not provide enough information to confirm or contradict this movement finding."
            action = "Keep the finding as camera-screening evidence and confirm it during clinical review."
        findings.append(
            {
                "issue_code": str(getattr(issue, "code", "")),
                "issue_label": str(getattr(issue, "label", "")),
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "status": status,
                "interpretation": interpretation,
                "action": action,
            }
        )

    survey_only = sorted(reported_domains - movement_domains)
    for domain in survey_only:
        findings.append(
            {
                "issue_code": None,
                "issue_label": f"Patient-reported {DOMAIN_LABELS[domain]} difficulty",
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "status": "survey_only",
                "interpretation": "The patient reported this area, but the selected camera tasks did not flag a matching movement problem.",
                "action": "Do not label the area normal. Review task coverage, confidence, and patient priorities, and collect a focused follow-up if needed.",
            }
        )

    counts = {name: sum(item["status"] == name for item in findings) for name in ("consistent", "discordant", "not_addressed", "survey_only")}
    overall = "discordant_review_required" if counts["discordant"] else (
        "evidence_consistent" if counts["consistent"] else "insufficient_overlap"
    )
    return {
        "version": "1.0",
        "method": "independent_evidence_reconciliation",
        "overall_status": overall,
        "counts": counts,
        "reported_domains": sorted(reported_domains),
        "survey_evidence": general_evidence,
        "findings": findings,
        "reporting_rule": "Survey and movement evidence are compared, not forced to agree. Discordant or survey-only findings require confirmation rather than automatic rejection or diagnosis.",
    }


def _frames(motion_data: Mapping[str, Any] | None) -> List[Mapping[str, Any]]:
    raw = (motion_data or {}).get("frames") or []
    return [item for item in raw if isinstance(item, Mapping)]


def build_analysis_pipeline(
    motion_data: Mapping[str, Any] | None,
    musculoskeletal_outputs: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    frames = _frames(motion_data)
    pose_frames = sum(bool(frame.get("pose_2d")) for frame in frames)
    world_frames = sum(bool(frame.get("pose_world_3d")) for frame in frames)
    hand_frames = sum(bool(frame.get("hand_2d")) for frame in frames)
    task_ids = sorted({str(frame.get("task_id")) for frame in frames if frame.get("task_id")})
    outputs = dict(musculoskeletal_outputs or {})
    quality = outputs.get("quality") if isinstance(outputs.get("quality"), Mapping) else {}
    model_complete = outputs.get("status") == "completed" and bool(quality.get("kinematics_valid"))
    activation_available = model_complete and isinstance(outputs.get("muscle_activations"), Mapping) and bool(outputs.get("muscle_activations"))
    force_available = model_complete and isinstance(outputs.get("muscle_forces_n"), Mapping) and bool(outputs.get("muscle_forces_n"))

    stages = [
        {
            "id": "camera_2d",
            "label": "2D keypoint extraction",
            "status": "complete" if pose_frames + hand_frames >= 10 else "insufficient_data",
            "method": "MediaPipe PoseLandmarker and HandLandmarker in video mode",
            "evidence": {"pose_frames": pose_frames, "hand_frames": hand_frames, "tasks_sampled": task_ids},
        },
        {
            "id": "camera_3d",
            "label": "Estimated 3D keypoints",
            "status": "complete" if world_frames >= 10 else "insufficient_data",
            "method": "MediaPipe world landmarks from a single camera",
            "evidence": {"world_landmark_frames": world_frames},
            "limitation": "These are estimated world landmarks, not calibrated laboratory motion capture.",
        },
        {
            "id": "stroke_3d_refinement",
            "label": "Stroke-aware 3D trajectory refinement",
            "status": "complete" if outputs.get("stroke_3d_status") == "completed" else "not_run",
            "method": "WHAM plus the trained stroke functional encoder",
            "reason": None if outputs.get("stroke_3d_status") == "completed" else "The deployed app has not received output from the separate GPU biomechanics worker.",
        },
        {
            "id": "musculoskeletal_model",
            "label": "Musculoskeletal model",
            "status": "complete" if model_complete else "not_run",
            "method": str(outputs.get("method") or "OpenSim inverse kinematics and Moco/static optimization"),
            "reason": None if model_complete else "No validated OpenSim/Moco result with valid kinematics was supplied for this assessment.",
        },
        {
            "id": "muscle_activation",
            "label": "Model-estimated muscle activation",
            "status": "complete" if activation_available else "screening_only",
            "method": "Musculoskeletal model estimate" if activation_available else "Kinematic pattern screening only",
            "reason": None if activation_available else "Camera movement alone cannot directly determine which muscle was active or how much force it produced.",
        },
    ]
    overall = "advanced_model_complete" if activation_available else (
        "kinematic_screening_complete" if pose_frames + hand_frames >= 10 else "insufficient_motion_data"
    )
    return {
        "version": "1.0",
        "overall_status": overall,
        "stages": stages,
        "model_outputs": {
            "activation_available": activation_available,
            "muscle_force_available": force_available,
            "confidence": outputs.get("confidence") if model_complete else "unavailable",
        },
        "reporting_rule": "Only validated solver outputs are reported as model-estimated activation or force. Kinematic rules remain screening hypotheses and are not relabeled as measured muscle activity.",
    }
