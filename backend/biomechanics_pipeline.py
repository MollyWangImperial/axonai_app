"""Validated contracts for asynchronous per-task musculoskeletal analysis.

Camera-derived movement rules and OpenSim/Moco solver outputs are deliberately
kept separate. Only a trusted worker result that passes this module's quality
checks may be stored as model-estimated muscle activation.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


DOMAIN_LABELS = {
    "upper_limb": "Upper limb",
    "hand": "Hand function",
    "lower_limb": "Walking",
    "balance": "Balance",
}

TASK_MODEL_ROUTES: Dict[str, Dict[str, str]] = {
    "T1": {"domain": "upper_limb", "model_family": "upper_extremity", "solver": "OpenSim MocoInverse/static optimization"},
    "T2": {"domain": "upper_limb", "model_family": "upper_extremity", "solver": "OpenSim MocoInverse/static optimization"},
    "T3": {"domain": "upper_limb", "model_family": "upper_extremity", "solver": "OpenSim MocoInverse/static optimization"},
    "H1": {"domain": "hand", "model_family": "hand_wrist", "solver": "Validated hand/wrist muscle-redundancy solver"},
    "H3": {"domain": "hand", "model_family": "hand_wrist", "solver": "Validated hand/wrist muscle-redundancy solver"},
    "H4": {"domain": "hand", "model_family": "hand_wrist", "solver": "Validated hand/wrist muscle-redundancy solver"},
    "L6": {"domain": "lower_limb", "model_family": "full_body_gait", "solver": "OpenSim MocoInverse"},
}


def task_model_route(task_id: str) -> Dict[str, str]:
    if task_id in TASK_MODEL_ROUTES:
        return dict(TASK_MODEL_ROUTES[task_id])
    if task_id.startswith("H"):
        return {"domain": "hand", "model_family": "hand_wrist", "solver": "Validated hand/wrist muscle-redundancy solver"}
    if task_id.startswith("L"):
        return {"domain": "lower_limb", "model_family": "full_body_lower_limb", "solver": "OpenSim MocoInverse/static optimization"}
    if task_id.startswith("B"):
        return {"domain": "balance", "model_family": "full_body_balance", "solver": "OpenSim MocoInverse/static optimization"}
    return {"domain": "upper_limb", "model_family": "upper_extremity", "solver": "OpenSim MocoInverse/static optimization"}


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)


def patient_collection_summary(
    task_results: Iterable[Any],
    expected_task_count: int,
) -> Dict[str, Any]:
    tasks = list(task_results)
    completed_steps = sum(int(_value(task, "completed_steps", 0) or 0) for task in tasks)
    total_steps = sum(int(_value(task, "total_steps", 0) or 0) for task in tasks)
    duration_ms = sum(max(0, int(_value(task, "duration_ms", 0) or 0)) for task in tasks)
    domains: List[Dict[str, str]] = []
    seen = set()
    for task in tasks:
        task_id = str(_value(task, "task_id", ""))
        domain = task_model_route(task_id)["domain"]
        if domain not in seen:
            domains.append({"domain": domain, "label": DOMAIN_LABELS.get(domain, "Movement")})
            seen.add(domain)
    return {
        "tasks_collected": len(tasks),
        "tasks_expected": max(expected_task_count, len(tasks)),
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "completion_percent": round(100 * completed_steps / total_steps) if total_steps else 0,
        "duration_ms": duration_ms,
        "domains": domains,
    }


def build_model_analysis_manifest(
    assessment_id: str,
    task_ids: Sequence[str],
    videos_by_task: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    videos = videos_by_task or {}
    tasks = []
    for task_id in task_ids:
        route = task_model_route(task_id)
        video = videos.get(task_id) or {}
        tasks.append({
            "task_id": task_id,
            **route,
            "video_id": video.get("id"),
            "status": "queued" if video.get("id") else "waiting_for_video",
            "required_quality": [
                "kinematics_valid",
                "model_scaled",
                "external_loads_valid",
                "residuals_within_threshold",
            ],
        })
    return {
        "version": "1.0",
        "assessment_id": assessment_id,
        "status": "queued" if tasks and all(task["status"] == "queued" for task in tasks) else "waiting_for_inputs",
        "tasks": tasks,
        "reporting_rule": "Camera heuristics are never accepted as model-estimated muscle activation. Each task requires a trusted, quality-validated solver output.",
    }


def _activation_value(value: Any) -> float:
    if isinstance(value, Mapping):
        candidate = value.get("mean", value.get("mean_activation"))
    else:
        candidate = value
    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        raise ValueError("Each muscle activation requires a numeric mean value")
    number = float(candidate)
    if number < 0 or number > 1:
        raise ValueError("Muscle activation values must be normalized to 0..1")
    return number


def validate_model_outputs(
    payload: Mapping[str, Any],
    expected_task_ids: Sequence[str],
    expected_videos: Mapping[str, str | None] | None = None,
) -> Dict[str, Any]:
    if payload.get("status") != "completed":
        raise ValueError("Model output status must be completed")
    rows = payload.get("per_task")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Validated model outputs require a non-empty per_task list")
    expected = set(expected_task_ids)
    received = {str(row.get("task_id")) for row in rows if isinstance(row, Mapping)}
    if received != expected:
        raise ValueError(f"Model output tasks do not match assessment tasks: expected {sorted(expected)}, received {sorted(received)}")

    validated: List[Dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        task_id = str(row.get("task_id"))
        quality = row.get("quality")
        if not isinstance(quality, Mapping) or not all(
            quality.get(key) is True
            for key in ("kinematics_valid", "model_scaled", "external_loads_valid", "residuals_within_threshold")
        ):
            raise ValueError(f"Task {task_id} did not pass every model quality gate")
        if not str(row.get("external_load_method") or "").strip():
            raise ValueError(f"Task {task_id} is missing its external-load method")
        provenance = row.get("provenance")
        if not isinstance(provenance, Mapping) or not all(
            str(provenance.get(key) or "").strip()
            for key in ("solver", "model_version", "source_video_id", "code_version")
        ):
            raise ValueError(f"Task {task_id} is missing solver provenance")
        expected_video = (expected_videos or {}).get(task_id)
        if expected_videos is not None and not expected_video:
            raise ValueError(f"Task {task_id} has no saved source video")
        if expected_video and str(provenance.get("source_video_id")) != str(expected_video):
            raise ValueError(f"Task {task_id} output does not match its saved source video")
        activations = row.get("muscle_activations")
        if not isinstance(activations, Mapping) or not activations:
            raise ValueError(f"Task {task_id} has no model-estimated muscle activations")
        for activation in activations.values():
            _activation_value(activation)
        findings = row.get("functional_findings") or []
        if not isinstance(findings, list):
            raise ValueError(f"Task {task_id} functional findings must be a list")
        validated.append(row)

    return {"status": "completed", "per_task": validated}


def aggregate_model_outputs(validated: Mapping[str, Any]) -> Dict[str, Any]:
    rows = list(validated.get("per_task") or [])
    activations: Dict[str, Any] = {}
    forces: Dict[str, Any] = {}
    moments: Dict[str, Any] = {}
    findings: List[Dict[str, Any]] = []
    for row in rows:
        task_id = str(row["task_id"])
        activations[task_id] = row.get("muscle_activations") or {}
        for name, value in (row.get("muscle_forces_n") or {}).items():
            forces[f"{task_id}:{name}"] = value
        for name, value in (row.get("joint_moments_nm") or {}).items():
            moments[f"{task_id}:{name}"] = value
        for finding in row.get("functional_findings") or []:
            item = dict(finding)
            item.setdefault("related_tasks", [task_id])
            item.setdefault("source", "validated_musculoskeletal_model")
            findings.append(item)
    return {
        "status": "completed",
        "method": "Per-task subject-scaled musculoskeletal modeling",
        "external_load_method": "task_specific",
        "confidence": "model_estimate",
        "quality": {
            "kinematics_valid": True,
            "external_loads_valid": True,
            "model_scaled": True,
            "residuals_within_threshold": True,
        },
        "per_task": rows,
        "muscle_activations": activations,
        "muscle_forces_n": forces,
        "joint_moments_nm": moments,
        "functional_findings": findings,
    }


def model_activation_report(outputs: Mapping[str, Any]) -> Dict[str, Any]:
    findings = []
    for index, raw in enumerate(outputs.get("functional_findings") or []):
        item = dict(raw)
        item.setdefault("code", f"MODEL_FINDING_{index + 1}")
        item.setdefault("label", "Movement pattern requiring review")
        item.setdefault("severity", "review")
        item.setdefault("related_tasks", [])
        item["provenance"] = "validated_musculoskeletal_model"
        findings.append(item)
    return {
        "version": "2.0",
        "status": "model_complete",
        "method": "validated_per_task_musculoskeletal_model",
        "findings": findings,
        "reporting_rule": "These are model-estimated functional findings, not direct EMG measurements or an etiologic medical diagnosis. Clinician review is required.",
    }


def pending_model_activation_report() -> Dict[str, Any]:
    return {
        "version": "2.0",
        "status": "awaiting_validated_model",
        "method": "validated_per_task_musculoskeletal_model",
        "findings": [],
        "reporting_rule": "No muscle activation finding is reported until trusted per-task solver outputs pass every quality gate.",
    }
