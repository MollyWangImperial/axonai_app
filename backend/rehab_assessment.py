"""Domain summaries and provenance-aware biomechanics reporting for AxonAI."""

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional


DOMAIN_BY_PREFIX = {
    "T": ("upper_limb", "Upper limb function"),
    "H": ("hand", "Hand function"),
    "L": ("lower_limb", "Lower limb function"),
    "B": ("balance", "Balance function"),
}


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _metrics(record: Any) -> Dict[str, Any]:
    value = _value(record, "metrics", {})
    return value if isinstance(value, dict) else {}


def build_domain_assessments(task_results: Iterable[Any]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for task in task_results:
        task_id = str(_value(task, "task_id", ""))
        domain_id, label = DOMAIN_BY_PREFIX.get(task_id[:1], ("other", "Other function"))
        bucket = grouped.setdefault(
            domain_id,
            {
                "domain": domain_id,
                "label": label,
                "task_count": 0,
                "completed_steps": 0,
                "total_steps": 0,
                "failed_steps": [],
                "metrics": {},
                "method": "Video-based task-performance screening",
                "clinical_status": "screening_only",
            },
        )
        bucket["task_count"] += 1
        bucket["completed_steps"] += int(_value(task, "completed_steps", 0) or 0)
        bucket["total_steps"] += int(_value(task, "total_steps", 0) or 0)
        for step in _value(task, "steps", []) or []:
            if not bool(_value(step, "completed", False)):
                bucket["failed_steps"].append(
                    {
                        "task_id": task_id,
                        "step_id": _value(step, "step_id"),
                        "failure_code": _value(step, "failure_code"),
                    }
                )
        for key, value in _metrics(task).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                previous = bucket["metrics"].get(key)
                bucket["metrics"][key] = value if previous is None else max(previous, value)
            elif value is True:
                bucket["metrics"][key] = True

    for bucket in grouped.values():
        total = bucket["total_steps"]
        bucket["completion_percent"] = round(100 * bucket["completed_steps"] / total) if total else 0
        if not total:
            bucket["interpretation"] = "No valid task steps were submitted."
        elif bucket["failed_steps"]:
            bucket["interpretation"] = "One or more guided movement steps were not completed; review the localized phenotypes and safety conditions."
        else:
            bucket["interpretation"] = "All submitted task steps were completed; this does not rule out impairment outside the observed tasks."
    return list(grouped.values())


def build_clinician_measure_summary(patient_parameters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    params = patient_parameters or {}
    measures = params.get("clinician_measures") or {}
    summaries = []
    for code, value in measures.items():
        summaries.append(
            {
                "code": str(code).upper(),
                "value": value,
                "method": "Clinician-entered standardized assessment",
                "provenance": "clinician_measure",
                "clinical_status": "observed",
            }
        )
    return summaries


def _camera_metric_values(task_results: Iterable[Any]) -> Dict[str, List[float]]:
    values: Dict[str, List[float]] = defaultdict(list)
    for task in task_results:
        candidates = [_metrics(task)] + [_metrics(step) for step in (_value(task, "steps", []) or [])]
        for metrics in candidates:
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values[key].append(float(value))
    return values


def build_biomechanical_estimates(
    task_results: Iterable[Any],
    patient_parameters: Optional[Dict[str, Any]] = None,
    musculoskeletal_outputs: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return estimates with explicit provenance and availability.

    OpenSim static optimization estimates force demand needed to reproduce an
    observed motion. It is not a direct MMT score or proof of neural recovery.
    """
    task_results = list(task_results)
    metric_values = _camera_metric_values(task_results)
    estimates: List[Dict[str, Any]] = []

    trunk_values = metric_values.get("trunk_lean_deg", [])
    if trunk_values:
        estimates.append(
            {
                "code": "TRUNK_COMPENSATION_ANGLE",
                "label": "Peak trunk compensation angle",
                "value": round(max(trunk_values), 1),
                "unit": "deg",
                "method": "Pose-derived kinematic proxy",
                "provenance": "camera",
                "confidence": "screening",
                "interpretation": "Use for within-patient trend and task-specific compensation review, not diagnosis.",
            }
        )

    affected_load = metric_values.get("affected_load_proxy", []) or metric_values.get("weight_shift_affected_ratio", [])
    estimates.append(
        {
            "code": "PLANTAR_LOAD_DISTRIBUTION_PROXY",
            "label": "Affected-side plantar load distribution proxy",
            "value": round(max(affected_load), 3) if affected_load else None,
            "unit": "ratio",
            "method": "Pose-derived center-of-mass/base-of-support proxy",
            "provenance": "camera_proxy",
            "confidence": "low" if affected_load else "unavailable",
            "interpretation": "This is not plantar pressure or center of pressure. Absolute plantar pressure requires a pressure insole or force platform.",
        }
    )

    outputs = musculoskeletal_outputs or {}
    completed = outputs.get("status") == "completed"
    external_load_method = outputs.get("external_load_method")
    quality = outputs.get("quality") if isinstance(outputs.get("quality"), dict) else {}
    quality_ok = bool(completed and external_load_method and quality.get("kinematics_valid") is True and quality.get("external_loads_valid") is True)

    if quality_ok:
        for group, value in (outputs.get("muscle_forces_n") or {}).items():
            estimates.append(
                {
                    "code": f"MUSCLE_FORCE_{str(group).upper()}",
                    "label": f"Estimated {group} muscle force demand",
                    "value": value,
                    "unit": "N",
                    "method": "Subject-scaled OpenSim inverse dynamics plus static optimization",
                    "provenance": "musculoskeletal_model",
                    "confidence": outputs.get("confidence", "model_estimate"),
                    "interpretation": "Estimated force required by the modeled motion; it is not directly measured maximum muscle strength.",
                }
            )
        for joint, value in (outputs.get("joint_moments_nm") or {}).items():
            estimates.append(
                {
                    "code": f"JOINT_MOMENT_{str(joint).upper()}",
                    "label": f"Estimated {joint} net joint moment",
                    "value": value,
                    "unit": "N*m",
                    "method": "Subject-scaled OpenSim inverse dynamics",
                    "provenance": "musculoskeletal_model",
                    "confidence": outputs.get("confidence", "model_estimate"),
                    "interpretation": "Net joint demand estimated from 3D motion and modeled external loads.",
                }
            )
    else:
        estimates.append(
            {
                "code": "MUSCLE_FORCE_MODEL_STATUS",
                "label": "Muscle force estimation",
                "value": None,
                "unit": None,
                "method": "OpenSim inverse dynamics plus static optimization",
                "provenance": "musculoskeletal_model",
                "confidence": "unavailable",
                "interpretation": "Not calculated: requires a subject-scaled model, quality-controlled 3D kinematics, body mass and measured or explicitly modeled external loads.",
            }
        )

    return estimates


def modeling_specification() -> Dict[str, Any]:
    return {
        "purpose": "Estimate joint moments, muscle activations and muscle force demand from observed movement.",
        "required_inputs": [
            "patient height, body mass, affected side and segment-length calibration",
            "quality-controlled 3D joint trajectories over time",
            "task events and contact states",
            "measured or explicitly modeled external loads, including ground reaction forces for stance tasks",
            "a subject-scaled OpenSim musculoskeletal model",
        ],
        "pipeline": [
            "2D keypoint quality control and multi-view or validated monocular 3D reconstruction",
            "subject-specific model scaling and joint-range constraints",
            "inverse kinematics",
            "external-load estimation with uncertainty labels",
            "inverse dynamics",
            "static optimization or Moco inverse to estimate activation and muscle force demand",
            "residual, reserve-actuator and sensitivity checks",
        ],
        "optimization": {
            "objective": "min sum_t tracking_error + lambda_r*residual_effort + lambda_a*sum_m(activation_m^p) + lambda_theta*patient_parameter_regularization",
            "constraints": [
                "multibody equations of motion",
                "0 <= muscle activation <= 1",
                "muscle force-length-velocity and moment-arm relationships",
                "patient-specific joint range and side-specific capacity priors",
            ],
            "patient_parameter_role": "Anthropometrics scale geometry and inertial properties; clinician measures constrain broad capacity/ROM priors; they must not be converted to exact muscle force without validation.",
        },
        "reporting_rule": "Report model-estimated force demand, never direct muscle strength, unless separately calibrated against dynamometry or validated strength testing.",
        "sources": [
            "https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53089624/Getting+Started+with+Static+Optimization",
            "https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53089741/Tutorial+3+-+Scaling+Inverse+Kinematics+and+Inverse+Dynamics",
        ],
    }
