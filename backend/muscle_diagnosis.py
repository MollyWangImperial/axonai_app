"""Muscle-activation diagnosis layer (AxonAI dual-brain "left brain" rules).

For each function package (upper_limb / hand / lower_limb / balance) this module
maps the video-derived task metrics onto:
  - target muscles (which muscles the finding is attributed to),
  - the activation-inference pipeline route that produces/validates it
    (C1 upper-limb 2-link ID+SO · C2 lower-limb swing ID+SO ·
     C3 OpenSimAD contact-sphere full-cycle simulation · C4 quasi-static
     inverted-pendulum balance route · C5 hand-landmark tendon-excursion route),
  - one of FOUR anomaly classes:
        hypoactivation      激活不足
        hyperactivation     过度激活（含代偿性过度募集）
        timing_disorder     时序错乱
        co_contraction      过度共收缩,
  - a textbook citation whose page numbers come from real retrievals against
    the AxonAI textbook vector index (Winter Biomechanics 5e · Perry &
    Burnfield Gait Analysis 2e · Sahrmann Movement Impairment Syndromes ·
    Merletti Surface EMG). Pages are PDF pages of the indexed copies.

All rules are deterministic (no LLM). Every finding carries its metric
evidence so a clinician can audit the trigger. Screening only — not a
substitute for MMT, tone exam, force plates, or clinical judgement.
"""

from typing import Any, Dict, Iterable, List, Mapping, Optional

ANOMALY_LABELS = {
    "hypoactivation": "Hypoactivation",
    "hyperactivation": "Hyperactivation or compensatory over-recruitment",
    "timing_disorder": "Timing disorder",
    "co_contraction": "Excessive co-contraction",
}

ROUTES = {
    "C1": "Upper-limb two-link inverse dynamics and static optimization",
    "C2": "Lower-limb swing-phase inverse dynamics and static optimization",
    "C3": "OpenSimAD contact-sphere muscle-driven full-cycle simulation",
    "C4": "Quasi-static inverted-pendulum balance model and static optimization",
    "C5": "21-point hand-landmark and tendon-excursion model",
}


def _metric(metrics: Mapping[str, Any], key: str) -> Optional[float]:
    value = metrics.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _rule(
    code: str,
    anomaly: str,
    package: str,
    task_ids: List[str],
    muscles: str,
    route: str,
    metric_keys: List[str],
    trigger,
    label: str,
    interpretation: str,
    citation: str,
    severity: str = "moderate",
) -> Dict[str, Any]:
    return {
        "code": code,
        "anomaly": anomaly,
        "package": package,
        "task_ids": task_ids,
        "muscles": muscles,
        "route": route,
        "metric_keys": metric_keys,
        "trigger": trigger,          # callable(metrics, failed_steps) -> bool
        "label": label,
        "interpretation": interpretation,
        "citation": citation,
        "severity": severity,
    }


# ---------------------------------------------------------------------------
# Rule tables per function package.
# Thresholds operate on the metric keys actually emitted by the pose runner
# (metricSnapshot / handMetricSnapshot in server.py). Body-relative ratios are
# size-invariant (normalized by shoulder width or leg length in the runner).
# ---------------------------------------------------------------------------

UPPER_LIMB_RULES: List[Dict[str, Any]] = [
    _rule(
        "UL_DELTOID_HYPO", "hypoactivation", "upper_limb", ["T1", "T2"],
        "Anterior and middle deltoid; supraspinatus", "C1",
        ["shoulder_elevation_deg", "affected_wrist_displacement_body_ratio"],
        lambda m, f: (
            (_metric(m, "shoulder_elevation_deg") is not None and _metric(m, "shoulder_elevation_deg") < 95)
            or (_metric(m, "affected_wrist_displacement_body_ratio") is not None
                and _metric(m, "affected_wrist_displacement_body_ratio") < 0.45)
        ),
        "Reduced shoulder elevation drive",
        "Active shoulder elevation or affected-wrist displacement was below the task threshold. This pattern may be consistent with reduced deltoid recruitment and should be confirmed clinically.",
        "Sahrmann, Movement System Impairment Syndromes, shoulder flexion examination, PDF p.244; Merletti, normalized sEMG amplitude interpretation, PDF p.355",
    ),
    _rule(
        "UL_TRAPEZIUS_HYPER", "hyperactivation", "upper_limb", ["T1", "T2"],
        "Upper trapezius and trunk muscles", "C1",
        ["shoulder_hike", "trunk_lean_deg"],
        lambda m, f: bool(m.get("shoulder_hike")) or (
            _metric(m, "trunk_lean_deg") is not None and _metric(m, "trunk_lean_deg") > 18
        ),
        "Shoulder-hike or trunk compensation pattern",
        "Affected shoulder elevation or trunk lean above 18 degrees suggests compensatory recruitment while raising the arm. Camera data cannot directly measure muscle activation.",
        "Sahrmann, scapular compensation and recruitment patterns, PDF pp.106 and 212",
    ),
    _rule(
        "UL_REACH_SEGMENTED", "timing_disorder", "upper_limb", ["T1", "T3"],
        "Anterior deltoid-triceps coordination chain", "C1",
        ["shoulder_elevation_deg"],
        lambda m, f: (
            _metric(m, "shoulder_elevation_deg") is not None
            and _metric(m, "shoulder_elevation_deg") >= 95
            and any(str(step.get("task_id", "")) in ("T1", "T3") for step in f)
        ),
        "Available range with incomplete task performance",
        "Shoulder elevation reached the range threshold, but the target step was not completed. This may reflect segmented movement or impaired coordination timing rather than range alone.",
        "Merletti, muscle synergy timing, PDF p.189; Winter 5e, movement-velocity analysis, PDF p.188",
    ),
    _rule(
        "UL_ELBOW_COCON", "co_contraction", "upper_limb", ["T1", "T3"],
        "Biceps-triceps antagonist pair", "C1",
        ["elbow_flexion_deg", "hand_to_mouth_distance_ratio"],
        lambda m, f: (
            _metric(m, "elbow_flexion_deg") is not None
            and _metric(m, "elbow_flexion_deg") > 55
            and _metric(m, "hand_to_mouth_distance_ratio") is not None
            and _metric(m, "hand_to_mouth_distance_ratio") > 0.8
        ),
        "Persistent elbow flexion without reaching the target",
        "The elbow remained flexed while the hand stayed far from the mouth target. This kinematic pattern may be consistent with excessive antagonist co-contraction and requires clinical or EMG confirmation.",
        "Winter 5e, muscle mechanics and joint stiffness, PDF p.203; Merletti, EMG-driven stiffness estimation, PDF p.573",
    ),
]

HAND_RULES: List[Dict[str, Any]] = [
    _rule(
        "HAND_EXTENSOR_HYPO", "hypoactivation", "hand", ["H1", "H4"],
        "Extensor digitorum and wrist extensors (ECRL/ECRB)", "C5",
        ["finger_total_flexion_deg"],
        lambda m, f: any(step.get("step_id") in ("H1-S2", "H4-S1") for step in f),
        "Reduced finger extension and hand opening",
        "The hand-opening step did not reach its threshold. This pattern may be consistent with reduced finger-extensor recruitment, but camera landmarks do not directly measure muscle activity.",
        "Merletti, forearm-muscle EMG spatial distribution, PDF p.157; Sahrmann, wrist-finger coupling, PDF p.51",
    ),
    _rule(
        "HAND_FLEXOR_COCON", "co_contraction", "hand", ["H2", "H4"],
        "Finger flexors (FDS/FDP) and extensor digitorum", "C5",
        ["finger_total_flexion_deg", "finger_abduction_ratio"],
        lambda m, f: any(step.get("step_id") in ("H2-S3", "H4-S2") for step in f),
        "Difficulty reopening after grasp",
        "Failure to reopen after forming a fist may reflect delayed flexor release, reduced extensor recruitment, or excessive flexor-extensor co-contraction. Clinical examination is needed to distinguish these causes.",
        "Merletti, neurophysiological sEMG applications, PDF p.355; Winter 5e, stiffness mechanisms, PDF p.203",
    ),
    _rule(
        "HAND_PINCH_HYPO", "hypoactivation", "hand", ["H3"],
        "Flexor pollicis longus, abductor pollicis brevis, and first dorsal interosseous", "C5",
        ["thumb_index_distance_ratio"],
        lambda m, f: (
            _metric(m, "thumb_index_distance_ratio") is not None
            and _metric(m, "thumb_index_distance_ratio") > 0.35
        ),
        "Reduced thumb-index pinch approximation",
        "The minimum thumb-index distance remained above the pinch threshold. This may indicate reduced opposition control or positioning accuracy rather than a direct measure of muscle strength.",
        "Merletti, forearm-muscle spatial distribution, PDF p.157; Sahrmann, hand movement examination, PDF p.51",
    ),
    _rule(
        "HAND_RELEASE_TIMING", "timing_disorder", "hand", ["H5", "H6"],
        "Finger-extensor recruitment timing during release", "C5",
        [],
        lambda m, f: any(step.get("step_id") in ("H6-S2", "H6-S3", "H5-S3") for step in f),
        "Delayed object release",
        "Grasp was achieved, but the release or hand-separation phase was not completed. This may indicate delayed release timing and should be distinguished from limited range or strength.",
        "Merletti, muscle-synergy timing structure, PDF p.189",
    ),
]

LOWER_LIMB_RULES: List[Dict[str, Any]] = [
    _rule(
        "LL_QUAD_HYPO", "hypoactivation", "lower_limb", ["L1"],
        "Quadriceps, including rectus femoris and the vasti", "C3",
        ["knee_extension_deg"],
        lambda m, f: (
            _metric(m, "knee_extension_deg") is not None and _metric(m, "knee_extension_deg") < 150
        ),
        "Reduced antigravity knee extension",
        "Peak seated knee extension below 150 degrees may be consistent with reduced quadriceps drive. Pain, range restriction, posture, and camera view can also affect this result.",
        "Sahrmann, quadriceps examination, PDF p.147; Winter 5e, knee-angle interpretation, PDF p.312",
    ),
    _rule(
        "LL_TA_HYPO", "hypoactivation", "lower_limb", ["L2", "L4", "L5", "L6"],
        "Tibialis anterior", "C2",
        ["ankle_dorsiflexion_proxy", "toe_clearance_leg_ratio"],
        lambda m, f: (
            (_metric(m, "ankle_dorsiflexion_proxy") is not None
             and _metric(m, "ankle_dorsiflexion_proxy") < 0.012)
            or (_metric(m, "toe_clearance_leg_ratio") is not None
                and _metric(m, "toe_clearance_leg_ratio") < 0.03)
        ),
        "Reduced ankle dorsiflexion or toe clearance",
        "Dorsiflexion or toe-clearance metrics were below threshold. This may indicate reduced swing-phase dorsiflexor control and an increased foot-clearance risk.",
        "Perry and Burnfield, swing-phase ankle control, PDF p.126; abnormal ankle-muscle activity, PDF p.304",
    ),
    _rule(
        "LL_HIPFLEX_HYPO", "hypoactivation", "lower_limb", ["L5", "L6"],
        "Iliopsoas and rectus femoris during swing initiation", "C2",
        ["hip_flexion_deg", "knee_flexion_deg"],
        lambda m, f: (
            _metric(m, "hip_flexion_deg") is not None
            and _metric(m, "hip_flexion_deg") < 30
            and _metric(m, "knee_flexion_deg") is not None
            and _metric(m, "knee_flexion_deg") < 45
        ),
        "Reduced hip and knee flexion during leg lift",
        "Hip flexion below 30 degrees together with knee flexion below 45 degrees suggests reduced swing initiation and may contribute to a stiff-legged clearance strategy.",
        "Perry and Burnfield, reduced swing-phase knee flexion and hip-flexor weakness, PDF pp.325-326",
    ),
    _rule(
        "LL_CIRCUMDUCTION_HYPER", "hyperactivation", "lower_limb", ["L4", "L5", "L6"],
        "Ipsilateral quadratus lumborum and hip abductors", "C3",
        ["circumduction_leg_ratio", "lateral_trunk_shift"],
        lambda m, f: (
            (_metric(m, "circumduction_leg_ratio") is not None
             and _metric(m, "circumduction_leg_ratio") > 0.18)
            or (_metric(m, "lateral_trunk_shift") is not None
                and _metric(m, "lateral_trunk_shift") > 0.09)
        ),
        "Circumduction or hip-hiking compensation",
        "Marked lateral foot travel or trunk shift during stepping suggests a compensatory clearance strategy that may substitute for hip and knee flexion.",
        "Perry and Burnfield, circumduction compensation, PDF p.325; Sahrmann, pelvic control, PDF p.377",
    ),
    _rule(
        "LL_STS_TIMING", "timing_disorder", "lower_limb", ["L3"],
        "Gluteus maximus-quadriceps sit-to-stand coordination", "C3",
        ["sit_to_stand_time_ms", "trunk_lean_deg"],
        lambda m, f: (
            (_metric(m, "sit_to_stand_time_ms") is not None
             and _metric(m, "sit_to_stand_time_ms") > 4000)
            or (_metric(m, "trunk_lean_deg") is not None and _metric(m, "trunk_lean_deg") > 35)
        ),
        "Slow sit-to-stand or excessive trunk-momentum strategy",
        "A rise time above 4 seconds or trunk lean above 35 degrees suggests reliance on trunk momentum and may reflect impaired extensor timing or force production.",
        "Winter 5e, linked-segment and movement-phase methods, PDF pp.115 and 176",
    ),
    _rule(
        "LL_KNEE_COCON", "co_contraction", "lower_limb", ["L1", "L3"],
        "Quadriceps-hamstrings antagonist pair", "C3",
        ["knee_stability_deg"],
        lambda m, f: (
            _metric(m, "knee_stability_deg") is not None
            and _metric(m, "knee_stability_deg") < 4
            and any(step.get("task_id") in ("L1", "L3") for step in f)
        ),
        "Stiff-knee holding pattern",
        "An unusually small knee-angle range during an unsuccessful task may be consistent with a stiffening strategy or excessive flexor-extensor co-contraction. Model or EMG confirmation is required.",
        "Winter 5e, co-contraction and joint stiffness, PDF p.203",
        severity="mild",
    ),
]

BALANCE_RULES: List[Dict[str, Any]] = [
    _rule(
        "BAL_PF_HYPO", "hypoactivation", "balance", ["B3", "B5"],
        "Soleus and gastrocnemius ankle-strategy muscles", "C4",
        ["trunk_sway_ratio", "pelvis_sway_ratio"],
        lambda m, f: (
            _metric(m, "trunk_sway_ratio") is not None and _metric(m, "trunk_sway_ratio") > 0.35
        ),
        "Excessive sway during supported standing",
        "A trunk-sway ratio above 0.35 suggests reduced control of the ankle strategy. Camera sway cannot identify the responsible muscle without additional modelling or clinical assessment.",
        "Winter 5e, standing-balance mechanics and center-of-pressure methods, PDF pp.131 and 134",
    ),
    _rule(
        "BAL_GMED_HYPO", "hypoactivation", "balance", ["B4", "B2"],
        "Gluteus medius and minimus during frontal-plane weight transfer", "C4",
        ["affected_load_proxy", "weight_shift_symmetry", "pelvis_shift_affected"],
        lambda m, f: (
            (_metric(m, "affected_load_proxy") is not None
             and _metric(m, "affected_load_proxy") < 0.35)
            or (_metric(m, "pelvis_shift_affected") is not None
                and _metric(m, "pelvis_shift_affected") < 0.015)
        ),
        "Reduced affected-side weight acceptance",
        "Low pelvic shift or estimated loading toward the affected side suggests reduced frontal-plane weight acceptance. This is a geometric proxy, not a force-plate measurement.",
        "Winter 5e, frontal-plane balance control, PDF p.134; Sahrmann, hip-abductor examination, PDF p.147",
        severity="severe",
    ),
    _rule(
        "BAL_TRUNK_HYPER", "hyperactivation", "balance", ["B4"],
        "Lateral trunk muscles in a Duchenne-type compensation", "C4",
        ["lateral_trunk_shift", "pelvis_shift_affected"],
        lambda m, f: (
            _metric(m, "lateral_trunk_shift") is not None
            and _metric(m, "lateral_trunk_shift") > 0.08
            and _metric(m, "pelvis_shift_affected") is not None
            and _metric(m, "pelvis_shift_affected") < 0.03
        ),
        "Compensatory trunk shift with limited pelvic transfer",
        "Marked shoulder-girdle shift with little pelvic movement suggests a trunk-lean compensation for limited affected-side weight transfer.",
        "Sahrmann, hip-abductor compensation patterns, PDF pp.147 and 377",
    ),
    _rule(
        "BAL_STIFFNESS_COCON", "co_contraction", "balance", ["B1", "B3"],
        "Tibialis anterior and triceps surae", "C4",
        ["trunk_sway_ratio", "midline_alignment_deg"],
        lambda m, f: (
            _metric(m, "trunk_sway_ratio") is not None
            and _metric(m, "trunk_sway_ratio") < 0.06
            and any(step.get("task_id") in ("B1", "B3") for step in f)
        ),
        "Possible stiffening strategy despite low sway",
        "Very low sway during an unsuccessful or interrupted hold may reflect a rigid ankle strategy rather than adaptable balance control. Clinical review is required.",
        "Winter 5e, stiffness strategies in balance, PDF p.134; Merletti, sustained-contraction assessment, PDF p.135",
        severity="mild",
    ),
    _rule(
        "BAL_RESPONSE_TIMING", "timing_disorder", "balance", ["B2", "B5"],
        "Anticipatory postural-adjustment chain across trunk and lower limbs", "C4",
        ["trunk_sway_ratio", "pelvis_sway_ratio"],
        lambda m, f: any(step.get("step_id") in ("B2-S3", "B5-S2") for step in f),
        "Delayed weight-shift recovery or postural response",
        "Failure to return to midline after reaching or to stabilize in step stance may reflect impaired anticipatory or corrective response timing.",
        "Winter 5e, postural-control timing, PDF p.134; Merletti, synergy timing, PDF p.189",
    ),
]

ALL_RULES: List[Dict[str, Any]] = (
    UPPER_LIMB_RULES + HAND_RULES + LOWER_LIMB_RULES + BALANCE_RULES
)

PACKAGE_BY_PREFIX = {"T": "upper_limb", "H": "hand", "L": "lower_limb", "B": "balance"}


def _collect(task_results: Iterable[Any]):
    """Merge metrics (max per key) and failed steps, grouped by package."""
    metrics_by_pkg: Dict[str, Dict[str, Any]] = {}
    failed_by_pkg: Dict[str, List[Dict[str, Any]]] = {}
    tasks_by_pkg: Dict[str, List[str]] = {}
    for task in task_results:
        task_id = str(task.get("task_id") if isinstance(task, Mapping) else getattr(task, "task_id", ""))
        pkg = PACKAGE_BY_PREFIX.get(task_id[:1])
        if not pkg:
            continue
        tasks_by_pkg.setdefault(pkg, []).append(task_id)
        merged = metrics_by_pkg.setdefault(pkg, {})
        raw = task.get("metrics") if isinstance(task, Mapping) else getattr(task, "metrics", {})
        for key, value in (raw or {}).items():
            if isinstance(value, bool):
                merged[key] = merged.get(key) or value
            elif isinstance(value, (int, float)):
                prev = merged.get(key)
                merged[key] = value if not isinstance(prev, (int, float)) else max(prev, value)
        steps = task.get("steps") if isinstance(task, Mapping) else getattr(task, "steps", [])
        for step in steps or []:
            completed = step.get("completed") if isinstance(step, Mapping) else getattr(step, "completed", True)
            if not completed:
                sid = step.get("step_id") if isinstance(step, Mapping) else getattr(step, "step_id", "")
                failed_by_pkg.setdefault(pkg, []).append({"task_id": task_id, "step_id": sid})
    return metrics_by_pkg, failed_by_pkg, tasks_by_pkg


def build_muscle_activation_diagnosis(task_results: Iterable[Any]) -> Dict[str, Any]:
    """Deterministic four-anomaly diagnosis across all submitted packages."""
    metrics_by_pkg, failed_by_pkg, tasks_by_pkg = _collect(list(task_results))
    findings: List[Dict[str, Any]] = []
    for rule in ALL_RULES:
        pkg = rule["package"]
        if pkg not in tasks_by_pkg:
            continue
        if not any(t in tasks_by_pkg[pkg] for t in rule["task_ids"]):
            continue
        metrics = metrics_by_pkg.get(pkg, {})
        failed = failed_by_pkg.get(pkg, [])
        try:
            triggered = bool(rule["trigger"](metrics, failed))
        except Exception:
            triggered = False
        if not triggered:
            continue
        findings.append({
            "code": rule["code"],
            "package": pkg,
            "anomaly_type": rule["anomaly"],
            "anomaly_label": ANOMALY_LABELS[rule["anomaly"]],
            "label": rule["label"],
            "muscles": rule["muscles"],
            "pipeline_route": rule["route"],
            "pipeline_route_label": ROUTES[rule["route"]],
            "severity": rule["severity"],
            "interpretation": rule["interpretation"],
            "evidence_metrics": {
                k: metrics.get(k) for k in rule["metric_keys"] if k in metrics
            },
            "related_tasks": [t for t in rule["task_ids"] if t in tasks_by_pkg[pkg]],
            "citation": rule["citation"],
        })
    return {
        "version": "1.0",
        "method": "Deterministic rule engine over video-derived task metrics "
                  "(dual-brain left-brain layer; four-anomaly taxonomy)",
        "reporting_rule": "Findings are screening-level and cite the pipeline "
                          "route that can confirm them with model-based "
                          "activation inference; clinician review required.",
        "anomaly_taxonomy": ANOMALY_LABELS,
        "packages_evaluated": sorted(tasks_by_pkg.keys()),
        "findings": findings,
    }
