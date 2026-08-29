"""Patient-facing charts and observations derived from traceable evidence."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


DOMAIN_LABELS = {
    "upper_limb": "Upper limb",
    "hand": "Hand function",
    "lower_limb": "Lower limb",
}


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, Mapping):
        value = value.get("mean", value.get("mean_activation", default))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _humanize(value: str) -> str:
    text = re.sub(r"[_:/-]+", " ", value).strip()
    return " ".join(word.capitalize() for word in text.split())


def _activation_rows(outputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in outputs.get("per_task") or []:
        if not isinstance(task, Mapping):
            continue
        task_id = str(task.get("task_id") or "")
        domain = str(task.get("domain") or "lower_limb")
        for muscle, raw in (task.get("muscle_activations") or {}).items():
            if isinstance(raw, Mapping):
                mean = _number(raw.get("mean", raw.get("mean_activation")))
                peak = _number(raw.get("peak", raw.get("peak_activation", mean)))
                template_mean = raw.get("template_mean")
                delta = raw.get("delta_mean")
            else:
                mean = peak = _number(raw)
                template_mean = None
                delta = None
            rows.append({
                "task_id": task_id,
                "domain": domain,
                "muscle": str(muscle),
                "label": _humanize(str(muscle)),
                "mean": round(max(0.0, min(1.0, mean)), 4),
                "peak": round(max(0.0, min(1.0, peak)), 4),
                "template_mean": round(_number(template_mean), 4) if template_mean is not None else None,
                "delta_mean": round(_number(delta), 4) if delta is not None else None,
            })
    return rows


def _domain_rows(body_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "domain": str(item.get("domain") or ""),
            "label": str(item.get("label") or DOMAIN_LABELS.get(str(item.get("domain")), "Movement")),
            "completion_percent": int(item.get("step_completion_percent") or 0),
            "findings_count": int(item.get("findings_count") or 0),
            "status": str(item.get("status") or "analysis_pending"),
        }
        for item in body_summary.get("domains") or []
        if isinstance(item, Mapping)
    ]


def _notable_observations(
    activations: list[dict[str, Any]],
    stage: Mapping[str, Any],
) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    if activations:
        highest = max(activations, key=lambda item: item["peak"])
        observations.append({
            "title": f"Highest modeled demand: {highest['label']}",
            "detail": (
                f"The model's peak activation estimate was {round(highest['peak'] * 100)}% during "
                f"task {highest['task_id']}. This is a model estimate, not an EMG measurement."
            ),
        })
        comparable = [item for item in activations if item.get("delta_mean") is not None]
        if comparable:
            changed = max(comparable, key=lambda item: abs(float(item["delta_mean"])))
            direction = "higher" if changed["delta_mean"] >= 0 else "lower"
            observations.append({
                "title": f"Largest template difference: {changed['label']}",
                "detail": (
                    f"Mean modeled activation was {abs(round(changed['delta_mean'] * 100))} percentage points "
                    f"{direction} than the matched movement template."
                ),
            })
    kinematics = stage.get("kinematics") if isinstance(stage.get("kinematics"), Mapping) else {}
    patient_excursion = kinematics.get("patient_knee_excursion_deg")
    template_excursion = kinematics.get("template_knee_excursion_deg")
    if isinstance(patient_excursion, (int, float)) and isinstance(template_excursion, (int, float)):
        observations.append({
            "title": "Knee movement through the observed walking cycle",
            "detail": (
                f"The video-informed model used {patient_excursion:.1f} degrees of knee excursion; "
                f"the matched template used {template_excursion:.1f} degrees."
            ),
        })
    return observations[:4]


def build_patient_insights(
    body_summary: Mapping[str, Any],
    trusted_outputs: Mapping[str, Any] | None = None,
    research_stage: Mapping[str, Any] | None = None,
    model_analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trusted = dict(trusted_outputs or {})
    research = dict(research_stage or {})
    analysis = dict(model_analysis or {})
    source = trusted if trusted.get("status") == "completed" else research
    activations = _activation_rows(source)
    if trusted.get("status") == "completed":
        status = "validated"
        badge = "Validated model result"
    elif research.get("status") == "completed":
        status = "research_ready"
        badge = "Moco model estimate"
    elif (analysis.get("musculoskeletal_stage") or {}).get("status") in {"failed", "failed_to_queue"}:
        status = "needs_review"
        badge = "Analysis needs review"
    else:
        status = "processing"
        badge = "Musculoskeletal analysis in progress"

    coverage = sorted({str(item.get("domain") or "") for item in source.get("per_task") or [] if item.get("domain")})
    top_activations = sorted(activations, key=lambda item: item["peak"], reverse=True)[:6]
    return {
        "version": "1.0",
        "status": status,
        "badge": badge,
        "headline": (
            "Your movement model is ready to explore"
            if activations else
            "Your recordings are being prepared for movement modelling"
        ),
        "summary": (
            "Explore how the model distributed effort across the observed walking movement."
            if activations else
            "Domain metrics are available now. Muscle-activation charts will appear after the local worker finishes."
        ),
        "domain_metrics": _domain_rows(body_summary),
        "activation_profile": top_activations,
        "modeled_domains": coverage,
        "observations": _notable_observations(activations, research),
        "analysis_order": ["task_collection", "musculoskeletal_analysis", "patient_insights", "rehab_plan"],
        "reporting_rule": (
            "Moco values are optimization-based model estimates, not measured EMG, absolute strength, or a medical diagnosis. "
            "Only a fully quality-validated result may unlock automatic rehabilitation planning."
        ),
    }
