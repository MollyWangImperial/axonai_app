"""Independent video-review audit for the rehabilitation assessment pipeline.

The shadow reviewer is deliberately non-authoritative. It may surface a
disagreement, but only clinician-adjudicated labels can become reference data
for a future, separately validated architecture change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence


VALID_DOMAINS = {"upper_limb", "hand", "lower_limb", "balance"}
VALID_SEVERITIES = {"mild", "moderate", "severe", "uncertain"}


def _value(item: Any, key: str, default: Any = None) -> Any:
    return (
        item.get(key, default)
        if isinstance(item, Mapping)
        else getattr(item, key, default)
    )


def task_domain(task_id: str) -> str:
    task_id = str(task_id or "").upper()
    if task_id.startswith("H"):
        return "hand"
    if task_id.startswith("L"):
        return "lower_limb"
    if task_id.startswith("B"):
        return "balance"
    return "upper_limb"


def finding_domain(item: Any) -> str | None:
    explicit = (
        str(
            _value(item, "domain", "")
            or _value(item, "phenotype_domain", "")
            or _value(item, "package", "")
        )
        .strip()
        .lower()
        .replace(" ", "_")
    )
    aliases = {
        "upper_limb": "upper_limb",
        "arm": "upper_limb",
        "shoulder": "upper_limb",
        "hand": "hand",
        "hand_function": "hand",
        "lower_limb": "lower_limb",
        "walking": "lower_limb",
        "gait": "lower_limb",
        "balance": "balance",
    }
    if explicit in aliases:
        return aliases[explicit]
    related = _value(item, "related_tasks", []) or []
    if isinstance(related, str):
        related = [related]
    task_id = (
        str(related[0]) if related else str(_value(item, "related_task", "") or "")
    )
    if task_id and task_id != "ALL":
        return task_domain(task_id)
    code = str(_value(item, "code", "") or _value(item, "finding_code", "")).upper()
    if code.startswith(("HAND_", "PINCH_", "GRASP_")):
        return "hand"
    if code.startswith(("GAIT_", "WALK_", "LOWER_", "ANKLE_", "LE_")):
        return "lower_limb"
    if code.startswith(("BALANCE_", "POSTURAL_")):
        return "balance"
    if code.startswith(("UPPER_", "UL_", "REACH_", "SHOULDER_", "H2M_", "TRUNK_")):
        return "upper_limb"
    return None


def finding_category(item: Any, domain: str | None = None) -> str:
    domain = domain or finding_domain(item) or "movement"
    text = " ".join(
        str(_value(item, key, "") or "")
        for key in ("code", "finding_code", "label", "description", "phenotype_domain")
    ).lower().replace("_", " ").replace("-", " ")
    if any(
        token in text for token in ("fall", "unsafe", "assistance", "support person")
    ):
        return "safety_support"
    if "trunk" in text:
        return "trunk_compensation"
    if any(
        token in text
        for token in ("shoulder hike", "shoulder elevation", "shoulder compensation")
    ):
        return "shoulder_compensation"
    if domain == "hand" or any(
        token in text for token in ("hand", "finger", "pinch", "grasp", "grip")
    ):
        return "hand_control"
    if domain == "balance" or any(token in text for token in ("balance", "postural")):
        return "balance_control"
    if domain == "lower_limb" or any(
        token in text for token in ("gait", "walk", "step", "ankle", "lower limb")
    ):
        return "gait_control"
    if any(
        token in text
        for token in ("reach", "hand to mouth", "h2m", "arm", "upper limb")
    ):
        return "reach_control"
    return f"{domain}_other"


def normalize_shadow_review(payload: Mapping[str, Any]) -> Dict[str, Any]:
    status = str(payload.get("status") or "failed").strip().lower()
    if status != "completed":
        return {
            "version": "1.0",
            "status": (
                status
                if status
                in {
                    "queued",
                    "waiting_for_video",
                    "disabled",
                    "not_configured",
                    "consent_required",
                    "insufficient_video",
                    "failed",
                }
                else "failed"
            ),
            "reviewer": dict(payload.get("reviewer") or {}),
            "tasks_reviewed": [],
            "observations": [],
            "quality_concerns": list(payload.get("quality_concerns") or []),
            "urgent_review_flags": list(payload.get("urgent_review_flags") or []),
            "error": str(payload.get("error") or "")[:500] or None,
            "reporting_boundary": (
                "The independent reviewer did not complete. Its absence is not evidence of normal function."
            ),
        }

    observations: List[Dict[str, Any]] = []
    for raw in payload.get("observations") or []:
        if not isinstance(raw, Mapping):
            continue
        domain = str(raw.get("domain") or "").strip().lower().replace(" ", "_")
        if domain not in VALID_DOMAINS:
            continue
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        severity = str(raw.get("severity") or "uncertain").strip().lower()
        if severity not in VALID_SEVERITIES:
            severity = "uncertain"
        task_ids = raw.get("task_ids") or []
        if isinstance(task_ids, str):
            task_ids = [task_ids]
        observations.append(
            {
                "finding_code": str(
                    raw.get("finding_code") or f"VIDEO_{domain.upper()}_REVIEW"
                )[:80],
                "label": str(raw.get("label") or "Movement pattern for review")[:160],
                "domain": domain,
                "severity": severity,
                "confidence": round(confidence, 3),
                "task_ids": [str(item)[:20] for item in task_ids if str(item).strip()][
                    :8
                ],
                "evidence": str(raw.get("evidence") or "")[:500],
            }
        )

    return {
        "version": "1.0",
        "status": "completed",
        "mode": "independent_video_frame_review",
        "reviewer": dict(payload.get("reviewer") or {}),
        "tasks_reviewed": [
            str(item)[:20] for item in payload.get("tasks_reviewed") or []
        ],
        "observations": observations,
        "quality_concerns": [
            dict(item)
            for item in payload.get("quality_concerns") or []
            if isinstance(item, Mapping)
        ][:20],
        "urgent_review_flags": [
            dict(item)
            for item in payload.get("urgent_review_flags") or []
            if isinstance(item, Mapping)
        ][:10],
        "created_at": str(
            payload.get("created_at") or datetime.now(timezone.utc).isoformat()
        ),
        "reporting_boundary": (
            "This is an independent AI review of sampled video frames, not a diagnosis, ground truth, "
            "or permission to start rehabilitation. It can only trigger review and validation."
        ),
    }


def _architecture_findings(
    issues: Iterable[Any],
    model_outputs: Mapping[str, Any] | None,
) -> set[tuple[str, str]]:
    findings: set[tuple[str, str]] = set()
    for item in issues:
        if str(_value(item, "code", "")) == "NO_ISSUES":
            continue
        domain = finding_domain(item)
        if domain:
            findings.add((domain, finding_category(item, domain)))
    for item in (model_outputs or {}).get("functional_findings") or []:
        domain = finding_domain(item)
        if domain:
            findings.add((domain, finding_category(item, domain)))
    return findings


def _review_findings(
    review: Mapping[str, Any], minimum_confidence: float
) -> set[tuple[str, str]]:
    return {
        (str(item.get("domain")), finding_category(item, str(item.get("domain"))))
        for item in review.get("observations") or []
        if isinstance(item, Mapping)
        and str(item.get("domain")) in VALID_DOMAINS
        and float(item.get("confidence") or 0.0) >= minimum_confidence
    }


def _likely_stage(
    domain: str, mismatch_type: str, quality_concerns: Sequence[Mapping[str, Any]]
) -> str:
    if quality_concerns:
        return "video_collection_or_visibility"
    if mismatch_type == "architecture_only":
        return "reviewer_visibility_or_architecture_threshold_mapping"
    if domain == "hand":
        return "hand_landmarks_or_hand_wrist_solver"
    if domain == "lower_limb":
        return "trajectory_refinement_or_gait_solver"
    if domain == "balance":
        return "postural_tracking_or_balance_domain_mapping"
    return "target_detection_or_upper_extremity_solver"


def compare_architecture_to_shadow_review(
    issues: Iterable[Any],
    model_outputs: Mapping[str, Any] | None,
    review: Mapping[str, Any] | None,
    *,
    architecture_complete: bool,
    minimum_confidence: float = 0.65,
) -> Dict[str, Any]:
    normalized = normalize_shadow_review(review or {})
    base = {
        "version": "1.0",
        "reviewer_status": normalized["status"],
        "architecture_complete": bool(architecture_complete),
        "automatic_change_applied": False,
        "ground_truth_source": "clinician_adjudication_only",
        "reporting_boundary": (
            "Reviewer disagreement is an audit signal. It cannot overwrite the assessment, become a "
            "clinical label, or change production logic without adjudication and independent validation."
        ),
    }
    if normalized["status"] != "completed":
        return {
            **base,
            "status": "reviewer_unavailable",
            "agreement": None,
            "mismatches": [],
        }
    if not architecture_complete:
        return {
            **base,
            "status": "awaiting_trusted_architecture",
            "agreement": None,
            "mismatches": [],
        }

    architecture_findings = _architecture_findings(issues, model_outputs)
    reviewer_findings = _review_findings(normalized, minimum_confidence)
    matched = sorted(architecture_findings & reviewer_findings)
    reviewer_only = sorted(reviewer_findings - architecture_findings)
    architecture_only = sorted(architecture_findings - reviewer_findings)
    concerns = [
        item
        for item in normalized.get("quality_concerns") or []
        if isinstance(item, Mapping)
    ]
    mismatches: List[Dict[str, Any]] = []
    for domain, category in reviewer_only:
        mismatches.append(
            {
                "type": "reviewer_only",
                "domain": domain,
                "category": category,
                "summary": "The independent video review observed a limitation that the current architecture did not report.",
                "likely_pipeline_stage": _likely_stage(
                    domain, "reviewer_only", concerns
                ),
                "next_action": "Have a clinician inspect the source recording and both evidence trails before creating a labeled improvement case.",
            }
        )
    for domain, category in architecture_only:
        mismatches.append(
            {
                "type": "architecture_only",
                "domain": domain,
                "category": category,
                "summary": "The current architecture reported a limitation that the independent video review did not confirm.",
                "likely_pipeline_stage": _likely_stage(
                    domain, "architecture_only", concerns
                ),
                "next_action": "Check reviewer visibility, source-video coverage, solver evidence, and threshold mapping with a clinician.",
            }
        )

    urgent = bool(normalized.get("urgent_review_flags"))
    if urgent:
        status = "urgent_review_required"
    elif not mismatches:
        status = "agreement"
    elif matched:
        status = "partial_disagreement"
    else:
        status = "disagreement"
    return {
        **base,
        "status": status,
        "agreement": not mismatches and not urgent,
        "architecture_domains": sorted({domain for domain, _ in architecture_findings}),
        "reviewer_domains": sorted({domain for domain, _ in reviewer_findings}),
        "architecture_findings": [
            {"domain": domain, "category": category}
            for domain, category in sorted(architecture_findings)
        ],
        "reviewer_findings": [
            {"domain": domain, "category": category}
            for domain, category in sorted(reviewer_findings)
        ],
        "matched_findings": [
            {"domain": domain, "category": category} for domain, category in matched
        ],
        "matched_domains": sorted({domain for domain, _ in matched}),
        "mismatches": mismatches,
        "urgent_review_flags": normalized.get("urgent_review_flags") or [],
    }


def build_improvement_candidate(
    assessment_id: str,
    comparison: Mapping[str, Any],
) -> Dict[str, Any]:
    status = str(comparison.get("status") or "")
    if status not in {"partial_disagreement", "disagreement", "urgent_review_required"}:
        return {
            "version": "1.0",
            "status": "not_created",
            "automatic_change_applied": False,
            "reason": "No adjudicable architecture disagreement is available.",
        }
    return {
        "version": "1.0",
        "candidate_id": f"candidate:{assessment_id}",
        "assessment_id": assessment_id,
        "status": "pending_clinical_adjudication",
        "mismatches": list(comparison.get("mismatches") or []),
        "automatic_change_applied": False,
        "required_before_promotion": {
            "clinician_adjudicated_cases": 30,
            "independent_holdout_cases": 20,
            "clinician_approvals": 2,
            "subgroup_checks_passed": True,
            "safety_regression_detected": False,
            "rollback_plan_present": True,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reporting_boundary": (
            "This candidate records a possible failure mode. It is not a code change and cannot be "
            "promoted from one patient's result."
        ),
    }


def evaluate_promotion_gate(evidence: Mapping[str, Any]) -> Dict[str, Any]:
    checks = {
        "enough_adjudicated_cases": int(
            evidence.get("clinician_adjudicated_cases") or 0
        )
        >= 30,
        "enough_holdout_cases": int(evidence.get("independent_holdout_cases") or 0)
        >= 20,
        "enough_clinician_approvals": int(evidence.get("clinician_approvals") or 0)
        >= 2,
        "subgroup_checks_passed": evidence.get("subgroup_checks_passed") is True,
        "no_safety_regression": evidence.get("safety_regression_detected") is False,
        "rollback_plan_present": evidence.get("rollback_plan_present") is True,
    }
    return {
        "eligible_for_controlled_release": all(checks.values()),
        "checks": checks,
        "automatic_release": False,
        "reporting_boundary": "A passing gate still requires a reviewed, versioned deployment. Runtime self-modification is prohibited.",
    }


def apply_shadow_review_hold(
    clinical_gate: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> Dict[str, Any]:
    status = str(comparison.get("status") or "")
    if status not in {"partial_disagreement", "disagreement", "urgent_review_required"}:
        return dict(clinical_gate)
    return {
        **dict(clinical_gate),
        "status": "independent_review_required",
        "rehab_access": "blocked",
        "reason_code": "architecture_shadow_review_disagreement",
        "therapist_confirmation_required": True,
        "patient_title": "A therapist needs to review this result",
        "patient_message": (
            "Two independent movement analyses did not fully agree. Your recordings are saved, "
            "and no new rehabilitation plan will be recommended until a therapist reviews the evidence."
        ),
        "next_step": "Ask your therapist to confirm the movement findings before starting new exercises.",
    }
