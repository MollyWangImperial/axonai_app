"""Build provenance-aware rehabilitation measurement forms.

The form deliberately separates observations, model estimates and clinician
measurements.  A missing measurement stays pending instead of being inferred
from a different evidence source.
"""

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


DOMAIN_LABELS = {
    "upper_limb": "上肢功能",
    "hand": "手功能",
    "lower_limb": "下肢功能",
    "balance": "平衡功能",
    "cross_domain": "跨域临床评定",
}

SOURCE_LABELS = {
    "pose": "Pose estimation 自动计算",
    "musculoskeletal_model": "肌骨建模反推",
    "clinician": "康复师评定",
    "external_tool": "外部工具测量",
    "clinician_or_tool": "康复师或外部工具",
}


def _metric(
    code: str,
    domain: str,
    label: str,
    source: str,
    *,
    unit: str = "",
    metric_keys: Sequence[str] = (),
    task_ids: Sequence[str] = (),
    aggregation: str = "max",
    method: str,
    scale: str = "任务特异性功能评定",
    confidence: str = "screening",
    requirement: str = "",
) -> Dict[str, Any]:
    return {
        "code": code,
        "domain": domain,
        "label": label,
        "source_type": source,
        "unit": unit,
        "metric_keys": list(metric_keys),
        "task_ids": list(task_ids),
        "aggregation": aggregation,
        "method": method,
        "scale": scale,
        "confidence": confidence,
        "requirement": requirement,
    }


# This registry is shared conceptually with the workbook delivered to the user.
# Pose rows are only auto-filled from matching tasks. Model and clinical rows
# require explicit values from their own source.
MEASUREMENT_DEFINITIONS: List[Dict[str, Any]] = [
    _metric("UL_TASK_COMPLETION", "upper_limb", "上肢功能任务步骤完成率", "pose", unit="0-1", metric_keys=("task_completion_ratio",), task_ids=("T1", "T2", "T3", "T4", "T5", "T6", "T7"), aggregation="mean", method="各上肢任务已完成步骤数除以总步骤数后取平均", scale="任务特异性功能评定"),
    _metric("UL_TASK_DURATION", "upper_limb", "上肢功能任务平均用时", "pose", unit="ms", metric_keys=("task_duration_ms",), task_ids=("T1", "T2", "T3", "T4", "T5", "T6", "T7"), aggregation="mean", method="各上肢任务从首步骤开始至末步骤结束的平均时长", scale="任务特异性功能评定"),
    _metric("UL_WRIST_DISPLACEMENT", "upper_limb", "患腕最大位移代理", "pose", unit="shoulder-width ratio", metric_keys=("affected_wrist_displacement_body_ratio",), task_ids=("T1", "T2", "T3", "T4", "T5", "T6", "T7"), method="患腕相对步骤起点的最大二维位移除以肩宽", scale="上肢任务运动学"),
    _metric("UL_TRUNK_COMPENSATION", "upper_limb", "上肢任务峰值躯干代偿角", "pose", unit="deg", metric_keys=("trunk_lean_deg",), task_ids=("T1", "T2", "T3", "T4", "T5", "T6", "T7"), method="肩-髋中点连线相对垂直方向的二维角度"),
    _metric("UL_SHOULDER_ELEVATION", "upper_limb", "患侧肩关节抬举角代理", "pose", unit="deg", metric_keys=("shoulder_elevation_deg",), task_ids=("T1", "T2", "T6", "T7"), method="患侧髋-肩-肘夹角；单目二维、任务平面内解释", scale="ROM/任务特异性运动学"),
    _metric("UL_ELBOW_FLEXION", "upper_limb", "患侧肘屈曲角代理", "pose", unit="deg", metric_keys=("elbow_flexion_deg",), task_ids=("T1", "T3", "T4", "T5"), method="180度减去肩-肘-腕夹角", scale="ROM/任务特异性运动学"),
    _metric("UL_HAND_TO_MOUTH_DISTANCE", "upper_limb", "患腕到口部最小距离代理", "pose", unit="shoulder-width ratio", metric_keys=("hand_to_mouth_distance_ratio",), task_ids=("T3",), aggregation="min", method="患腕到双侧口角中点的最小二维距离除以肩宽；不是三维口部接触距离", scale="上肢进食相关任务"),
    _metric("UL_SHOULDER_HIKE", "upper_limb", "肩胛带抬高代偿", "pose", metric_keys=("shoulder_hike",), task_ids=("T1", "T2", "T3", "T4", "T5", "T6", "T7"), aggregation="any", method="患侧肩相对双侧肩线和躯干基线的抬高事件"),
    _metric("UL_BILATERAL_SYMMETRY", "upper_limb", "双腕位移对称性代理", "pose", unit="0-1", metric_keys=("bilateral_wrist_displacement_symmetry",), task_ids=("T7",), method="双腕相对步骤起点最大位移的较小值除以较大值；仅表示二维位移幅度对称性", scale="双侧上肢参与筛查"),
    _metric("UL_HAND_OPEN", "upper_limb", "患手张开评分", "pose", unit="0-1", metric_keys=("hand_open_score",), task_ids=("T5",), method="手指伸直度、指尖展开和拇食指间距的归一化组合", scale="上肢远端功能筛查"),
    _metric("UL_GRASP_CLOSURE", "upper_limb", "患手握合评分", "pose", unit="0-1", metric_keys=("fist_closure_score",), task_ids=("T4", "T5"), method="指尖至掌心距离相对掌宽的归一化评分", scale="上肢远端功能筛查"),
    _metric("UL_PINCH", "upper_limb", "拇食指捏合评分", "pose", unit="0-1", metric_keys=("pinch_score",), task_ids=("T6",), method="拇指尖与食指尖距离相对掌宽的归一化接近评分", scale="上肢远端功能筛查"),
    _metric("UL_FINGER_FLEXION", "upper_limb", "四指平均总屈曲角代理", "pose", unit="deg", metric_keys=("finger_total_flexion_deg",), task_ids=("T4", "T5", "T6"), method="四指PIP与DIP屈曲角之和的平均值", scale="上肢远端功能/TAM筛查"),
    _metric("UL_FINGER_ABDUCTION", "upper_limb", "手指外展宽度代理", "pose", unit="palm-width ratio", metric_keys=("finger_abduction_ratio",), task_ids=("T5",), method="食指尖至小指尖距离除以掌宽", scale="上肢远端功能筛查"),
    _metric("UL_THUMB_OPPOSITION", "upper_limb", "拇指对指距离代理", "pose", unit="palm-width ratio", metric_keys=("thumb_index_distance_ratio",), task_ids=("T6",), aggregation="min", method="拇指尖至食指尖距离除以掌宽；越小表示越接近", scale="上肢远端功能筛查"),
    _metric("UL_OBJECT_COUPLING", "upper_limb", "杯子抓持-移动耦合稳定性", "pose", unit="0-1", metric_keys=("objectHandCoupling",), task_ids=("T4",), method="标记物体与患手同步移动帧占比；仅在高级标记模式质量门通过后填值", scale="上肢功能性抓持"),
    _metric("UL_OBJECT_PLACEMENT_ERROR", "upper_limb", "杯子放置终点误差", "pose", unit="normalized image", metric_keys=("placementEndpointError",), task_ids=("T4",), aggregation="min", method="标记物体中心与目标中心的归一化二维距离；仅在高级标记模式质量门通过后填值", scale="上肢功能性抓持"),
    _metric("UL_OBJECT_RELEASE_DELAY", "upper_limb", "杯子释放延迟", "pose", unit="ms", metric_keys=("releaseDelayMs",), task_ids=("T4",), aggregation="min", method="物体到达目标后患手张开并与物体分离的估计延迟；仅在高级标记模式质量门通过后填值", scale="上肢功能性抓持"),
    _metric("UL_JOINT_MOMENT", "upper_limb", "上肢净关节力矩", "musculoskeletal_model", unit="N*m", method="个体化模型逆运动学、逆动力学", requirement="标定3D运动、体重/节段参数和外载荷"),
    _metric("UL_MUSCLE_FORCE_DEMAND", "upper_limb", "上肢肌肉力需求", "musculoskeletal_model", unit="N", method="OpenSim静态优化或Moco inverse", requirement="个体化模型、有效3D运动和外载荷；不是MMT肌力"),
    _metric("UL_MMT", "upper_limb", "上肢MMT肌力等级", "clinician_or_tool", unit="0-5级", method="标准体位、抗重力活动、治疗师施阻与触诊", scale="MMT", confidence="clinical", requirement="康复师；需要定量时使用手持测力计"),
    _metric("UL_PASSIVE_ROM", "upper_limb", "上肢被动ROM及终末感", "clinician_or_tool", unit="deg", method="被动活动配合量角器及终末感判断", scale="ROM", confidence="clinical", requirement="康复师和量角器"),

    _metric("HAND_OPEN_SCORE", "hand", "手掌张开评分", "pose", unit="0-1", metric_keys=("hand_open_score",), task_ids=("H1", "H4"), method="手指伸直度、指尖展开和拇食指间距的归一化组合"),
    _metric("HAND_FIST_CLOSURE", "hand", "握拳闭合评分", "pose", unit="0-1", metric_keys=("fist_closure_score",), task_ids=("H2", "H4", "H5"), method="指尖到掌心距离相对掌宽的归一化评分"),
    _metric("HAND_PINCH", "hand", "拇食指捏合评分", "pose", unit="0-1", metric_keys=("pinch_score",), task_ids=("H3",), method="拇指尖与食指尖距离相对掌宽"),
    _metric("HAND_FINGER_FLEXION", "hand", "四指平均总屈曲角代理", "pose", unit="deg", metric_keys=("finger_total_flexion_deg",), task_ids=("H2", "H4", "H5"), method="四指PIP与DIP屈曲角之和的平均值", scale="手功能/TAM筛查"),
    _metric("HAND_FINGER_ABDUCTION", "hand", "手指外展宽度代理", "pose", unit="palm-width ratio", metric_keys=("finger_abduction_ratio",), task_ids=("H1", "H4"), method="食指尖至小指尖距离除以掌宽", scale="手功能"),
    _metric("HAND_THUMB_OPPOSITION", "hand", "拇指对指距离代理", "pose", unit="palm-width ratio", metric_keys=("thumb_index_distance_ratio",), task_ids=("H3",), aggregation="min", method="拇指尖至食指尖距离除以掌宽；越小表示接近", scale="手功能"),
    _metric("HAND_OBJECT_COUPLING", "hand", "抓持物体耦合稳定性", "pose", unit="0-1", metric_keys=("objectHandCoupling",), task_ids=("H5", "H6"), method="手部与带视觉标记物体的同步运动比例", scale="手功能日常活动"),
    _metric("HAND_RELEASE_DELAY", "hand", "物体释放延迟", "pose", unit="ms", metric_keys=("releaseDelayMs",), task_ids=("H6",), method="物体到达目标后手-物分离及张手事件的延迟", scale="手功能日常活动"),
    _metric("HAND_MUSCLE_FORCE_DEMAND", "hand", "手内在肌/肌腱力需求", "musculoskeletal_model", unit="N", method="经验证的手部肌骨模型优化", requirement="手部专用模型、可靠手指3D运动和外部物体载荷"),
    _metric("HAND_SENSATION", "hand", "手感觉恢复S0-S4", "clinician_or_tool", unit="等级", method="痛触觉、深压觉及静态两点辨别", scale="手功能", confidence="clinical", requirement="康复师、两点辨别器/单丝等感觉工具"),
    _metric("HAND_APPEARANCE", "hand", "萎缩/瘢痕/变色/畸形", "clinician", unit="等级", method="视诊、触诊和病史核对", scale="手功能", confidence="clinical", requirement="康复师确认；摄像头只可辅助记录外观"),

    _metric("LE_KNEE_EXTENSION_ROM", "lower_limb", "坐位主动膝伸角代理", "pose", unit="deg", metric_keys=("knee_extension_deg",), task_ids=("L1",), method="患侧髋-膝-踝夹角峰值", scale="ROM/下肢功能"),
    _metric("LE_ANKLE_DORSIFLEXION", "lower_limb", "踝背屈/前足抬起代理", "pose", unit="normalized", metric_keys=("ankle_dorsiflexion_proxy",), task_ids=("L2", "L4"), method="足跟与足尖的垂直相对位移；非量角器角度", scale="ROM/下肢功能"),
    _metric("LE_HIP_FLEXION", "lower_limb", "髋屈曲角代理", "pose", unit="deg", metric_keys=("hip_flexion_deg",), task_ids=("L3", "L5"), method="180度减去肩-髋-膝夹角", scale="ROM/下肢功能"),
    _metric("LE_KNEE_FLEXION", "lower_limb", "膝屈曲角代理", "pose", unit="deg", metric_keys=("knee_flexion_deg",), task_ids=("L3", "L5"), method="180度减去髋-膝-踝夹角", scale="ROM/下肢功能"),
    _metric("LE_TOE_CLEARANCE", "lower_limb", "患足离地高度代理", "pose", unit="leg-length ratio", metric_keys=("toe_clearance_leg_ratio",), task_ids=("L4", "L5"), method="足尖相对步骤起点的最大垂直位移/患侧腿长"),
    _metric("LE_CIRCUMDUCTION", "lower_limb", "患足画圈代偿代理", "pose", unit="leg-length ratio", metric_keys=("circumduction_leg_ratio",), task_ids=("L4", "L5"), method="摆动期踝点最大侧向偏移/患侧腿长；需合适拍摄视角"),
    _metric("LE_STEP_LENGTH", "lower_limb", "患侧迈步长度代理", "pose", unit="leg-length ratio", metric_keys=("affected_step_length_leg_ratio",), task_ids=("L4",), method="患侧踝相对步骤起点的位移/患侧腿长"),
    _metric("LE_STS_TIME", "lower_limb", "坐站转换用时", "pose", unit="ms", metric_keys=("sit_to_stand_time_ms",), task_ids=("L3",), method="从坐站步骤开放到髋部升起目标稳定的时长"),
    _metric("LE_JOINT_MOMENT", "lower_limb", "下肢净关节力矩", "musculoskeletal_model", unit="N*m", method="个体化OpenSim逆动力学", requirement="3D运动、体重/节段参数、足地接触和有效外载荷"),
    _metric("LE_MUSCLE_FORCE_DEMAND", "lower_limb", "下肢肌肉力需求", "musculoskeletal_model", unit="N", method="OpenSim静态优化或Moco inverse", requirement="有效逆动力学结果；不是最大肌力或MMT"),
    _metric("LE_MMT", "lower_limb", "下肢MMT肌力等级", "clinician_or_tool", unit="0-5级", method="标准体位下抗重力、去重力、施阻和触诊", scale="MMT", confidence="clinical", requirement="康复师；可选手持测力计"),

    _metric("BAL_TRUNK_SWAY", "balance", "躯干摆动范围代理", "pose", unit="body-width ratio", metric_keys=("trunk_sway_ratio",), task_ids=("B1", "B3", "B5"), method="保持阶段肩中点二维轨迹范围/肩宽"),
    _metric("BAL_PELVIS_SWAY", "balance", "骨盆摆动范围代理", "pose", unit="body-width ratio", metric_keys=("pelvis_sway_ratio",), task_ids=("B1", "B3", "B5"), method="保持阶段髋中点二维轨迹范围/肩宽"),
    _metric("BAL_MIDLINE", "balance", "中线对齐偏差", "pose", unit="deg", metric_keys=("midline_alignment_deg",), task_ids=("B1", "B3"), method="躯干相对垂直方向的平均绝对角度"),
    _metric("BAL_AFFECTED_LOAD", "balance", "患侧负重分布代理", "pose", unit="ratio", metric_keys=("affected_load_proxy",), task_ids=("B3", "B4", "B5", "L3", "L5"), method="髋中点在双踝支撑基底内的相对位置", scale="平衡/负重筛查", confidence="low"),
    _metric("BAL_WEIGHT_SYMMETRY", "balance", "左右负重对称性代理", "pose", unit="0-1", metric_keys=("weight_shift_symmetry",), task_ids=("B3", "B4", "L3"), method="由患侧负重位置代理计算；1为几何对称", confidence="low"),
    _metric("BAL_KNEE_STABILITY", "balance", "站立期膝角稳定性", "pose", unit="deg range", metric_keys=("knee_stability_deg",), task_ids=("B3", "B4", "B5", "L5"), aggregation="min", method="保持阶段患膝角最大值减最小值"),
    _metric("BAL_SUPPORT_TIME", "balance", "姿势保持时间", "pose", unit="ms", metric_keys=("hold_duration_ms",), task_ids=("B1", "B3", "B5"), method="目标姿势实际维持时长", scale="Berg相关任务筛查"),
    _metric("PLANTAR_LOAD_PROXY", "balance", "足底负荷分布代理", "pose", unit="ratio", metric_keys=("affected_load_proxy",), task_ids=("B3", "B4", "B5", "L3", "L5"), method="身体重心投影与双足支撑几何关系；不是足底压力或CoP", confidence="low"),
    _metric("PLANTAR_PRESSURE", "balance", "真实足底压力/CoP", "external_tool", unit="kPa / mm", method="压力鞋垫或测力台直接测量", confidence="instrumented", requirement="压力鞋垫或测力台"),
    _metric("GRF_MODEL_ESTIMATE", "balance", "地面反作用力估计", "musculoskeletal_model", unit="N", method="接触模型或优化估计外力", confidence="model_estimate", requirement="足地接触状态、体重、3D运动和经验证接触模型；无测力台时必须标低置信度"),

    _metric("MAS", "cross_domain", "改良Ashworth肌张力", "clinician", unit="0,1,1+,2,3,4", method="治疗师按规定速度完成被动活动并感受阻力/卡住", scale="MAS", confidence="clinical", requirement="不能从主动动作或静态优化替代"),
    _metric("BRUNNSTROM", "cross_domain", "Brunnstrom恢复阶段", "clinician", unit="I-VI", method="综合协同模式、脱离协同运动、联合反应及肌张力", scale="Brunnstrom", confidence="clinical", requirement="Pose可提供动作证据，但正式分期需康复师确认"),
    _metric("BERG_TOTAL", "cross_domain", "Berg平衡量表总分", "clinician", unit="0-56", method="完整14项标准任务逐项0-4分", scale="Berg", confidence="clinical", requirement="需完整14项、帮助/监护/提示记录和安全保护；当前视频包不足以给正式总分"),
]


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _metrics(record: Any) -> Dict[str, Any]:
    value = _value(record, "metrics", {})
    return value if isinstance(value, dict) else {}


def _metric_samples(task_results: Iterable[Any]) -> Dict[str, List[Dict[str, Any]]]:
    samples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for task in task_results:
        task_id = str(_value(task, "task_id", ""))
        total_steps = int(_value(task, "total_steps", 0) or 0)
        completed_steps = int(_value(task, "completed_steps", 0) or 0)
        if total_steps > 0:
            samples["task_completion_ratio"].append({"value": completed_steps / total_steps, "task_id": task_id, "step_id": None})
        task_duration = int(_value(task, "duration_ms", 0) or 0)
        if task_duration > 0:
            samples["task_duration_ms"].append({"value": task_duration, "task_id": task_id, "step_id": None})
        for key, value in _metrics(task).items():
            if isinstance(value, (int, float, bool)):
                samples[key].append({"value": value, "task_id": task_id, "step_id": None})
        for step in _value(task, "steps", []) or []:
            step_id = str(_value(step, "step_id", ""))
            for key, value in _metrics(step).items():
                if isinstance(value, (int, float, bool)):
                    samples[key].append({"value": value, "task_id": task_id, "step_id": step_id})
    return samples


def _aggregate(values: List[Any], aggregation: str) -> Any:
    if not values:
        return None
    if aggregation == "any":
        return any(bool(value) for value in values)
    numeric = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if not numeric:
        return values[-1]
    if aggregation == "min":
        return round(min(numeric), 3)
    if aggregation == "mean":
        return round(sum(numeric) / len(numeric), 3)
    if aggregation == "latest":
        return round(numeric[-1], 3)
    return round(max(numeric), 3)


def _model_values(outputs: Dict[str, Any], active_domains: Sequence[str]) -> Dict[str, Any]:
    if outputs.get("status") != "completed":
        return {}
    if not outputs.get("external_load_method"):
        return {}
    quality = outputs.get("quality") if isinstance(outputs.get("quality"), dict) else {}
    if quality.get("kinematics_valid") is not True or quality.get("external_loads_valid") is not True:
        return {}
    values: Dict[str, Any] = {}
    domains = set(active_domains)
    if outputs.get("joint_moments_nm") and "upper_limb" in domains:
        values["UL_JOINT_MOMENT"] = outputs["joint_moments_nm"]
    if outputs.get("joint_moments_nm") and "lower_limb" in domains:
        values["LE_JOINT_MOMENT"] = outputs["joint_moments_nm"]
    if outputs.get("muscle_forces_n") and "upper_limb" in domains:
        values["UL_MUSCLE_FORCE_DEMAND"] = outputs["muscle_forces_n"]
    if outputs.get("muscle_forces_n") and "lower_limb" in domains:
        values["LE_MUSCLE_FORCE_DEMAND"] = outputs["muscle_forces_n"]
    if outputs.get("muscle_forces_n") and "hand" in domains:
        values["HAND_MUSCLE_FORCE_DEMAND"] = outputs["muscle_forces_n"]
    if outputs.get("ground_reaction_forces_n") and domains & {"lower_limb", "balance"}:
        values["GRF_MODEL_ESTIMATE"] = outputs["ground_reaction_forces_n"]
    return values


def build_clinical_measurement_form(
    task_results: Iterable[Any],
    patient_parameters: Optional[Dict[str, Any]] = None,
    musculoskeletal_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a structured form and only fill values supported by provenance."""
    task_results = list(task_results)
    samples = _metric_samples(task_results)
    clinician_values = (patient_parameters or {}).get("clinician_measures") or {}
    clinician_lookup = {str(key).upper(): value for key, value in clinician_values.items()}
    present_task_ids = {str(_value(task, "task_id", "")) for task in task_results}
    prefix_domains = {"T": "upper_limb", "H": "hand", "L": "lower_limb", "B": "balance"}
    active_domains = {prefix_domains[task_id[:1]] for task_id in present_task_ids if task_id[:1] in prefix_domains}
    model_values = _model_values(musculoskeletal_outputs or {}, active_domains)

    rows: List[Dict[str, Any]] = []
    for definition in MEASUREMENT_DEFINITIONS:
        value = None
        evidence: List[Dict[str, Any]] = []
        status = "pending"
        source = definition["source_type"]

        if source == "pose":
            matching: List[Dict[str, Any]] = []
            allowed_tasks = set(definition["task_ids"])
            for key in definition["metric_keys"]:
                matching.extend(
                    sample for sample in samples.get(key, [])
                    if not allowed_tasks or sample["task_id"] in allowed_tasks
                )
            value = _aggregate([sample["value"] for sample in matching], definition["aggregation"])
            evidence = [{"task_id": item["task_id"], "step_id": item["step_id"]} for item in matching]
            status = "auto_filled" if value is not None else "not_collected"
        elif source == "musculoskeletal_model":
            value = model_values.get(definition["code"])
            status = "model_filled" if value is not None else "model_required"
        else:
            aliases = {
                "UL_MMT": ("UL_MMT", "MMT_UPPER_LIMB", "MMT_UPPER"),
                "LE_MMT": ("LE_MMT", "MMT_LOWER_LIMB", "MMT_LOWER"),
                "MAS": ("MAS", "ASHWORTH", "MODIFIED_ASHWORTH"),
                "BRUNNSTROM": ("BRUNNSTROM", "BRUNNSTROM_STAGE"),
                "BERG_TOTAL": ("BERG_TOTAL", "BERG", "BBS"),
                "HAND_SENSATION": ("HAND_SENSATION", "SENSATION"),
                "HAND_APPEARANCE": ("HAND_APPEARANCE",),
                "UL_PASSIVE_ROM": ("UL_PASSIVE_ROM", "PROM_UPPER_LIMB"),
            }.get(definition["code"], (definition["code"],))
            for alias in aliases:
                if alias in clinician_lookup:
                    value = clinician_lookup[alias]
                    break
            if source == "external_tool":
                status = "tool_filled" if value is not None else "tool_required"
            else:
                status = "clinician_filled" if value is not None else "clinician_required"

        if definition["task_ids"]:
            applicable = bool(set(definition["task_ids"]) & present_task_ids)
        elif definition["domain"] == "cross_domain":
            cross_domain_applicability = {
                "MAS": {"upper_limb", "hand", "lower_limb"},
                "BRUNNSTROM": {"upper_limb", "hand", "lower_limb"},
                "BERG_TOTAL": {"lower_limb", "balance"},
            }
            applicable = bool(active_domains & cross_domain_applicability.get(definition["code"], set()))
        else:
            applicable = definition["domain"] in active_domains
        rows.append(
            {
                "code": definition["code"],
                "domain": definition["domain"],
                "domain_label": DOMAIN_LABELS[definition["domain"]],
                "label": definition["label"],
                "scale": definition["scale"],
                "source_type": source,
                "source_label": SOURCE_LABELS[source],
                "status": status,
                "value": value,
                "unit": definition["unit"],
                "method": definition["method"],
                "confidence": definition["confidence"],
                "requirement": definition["requirement"],
                "applicable_to_submitted_tasks": applicable,
                "evidence": evidence,
            }
        )

    domains = []
    for domain, label in DOMAIN_LABELS.items():
        domain_rows = [row for row in rows if row["domain"] == domain]
        applicable_rows = [row for row in domain_rows if row["applicable_to_submitted_tasks"]]
        domains.append(
            {
                "domain": domain,
                "label": label,
                "rows": domain_rows,
                "auto_filled": sum(row["status"] == "auto_filled" for row in applicable_rows),
                "model_filled": sum(row["status"] == "model_filled" for row in applicable_rows),
                "clinician_filled": sum(row["status"] == "clinician_filled" for row in applicable_rows),
                "tool_filled": sum(row["status"] == "tool_filled" for row in applicable_rows),
                "pending": sum(row["status"] not in {"auto_filled", "model_filled", "clinician_filled", "tool_filled"} for row in applicable_rows),
            }
        )

    scale_readiness = [
        {
            "scale": "Berg",
            "status": "clinician_required",
            "formal_score": clinician_lookup.get("BERG_TOTAL", clinician_lookup.get("BERG")),
            "reason": "正式总分要求完整14项及帮助、监护和提示等级；当前平衡视频包仅提供相关运动证据。",
        },
        {
            "scale": "MMT",
            "status": "clinician_required",
            "formal_score": None,
            "reason": "Pose可判断动作和抗重力表现，OpenSim可估计力需求，但0/1级触诊和4/5级施阻必须保留。",
        },
        {
            "scale": "MAS",
            "status": "clinician_required",
            "formal_score": clinician_lookup.get("MAS"),
            "reason": "需要规定速度的被动活动和阻力/卡住触感。",
        },
        {
            "scale": "Brunnstrom",
            "status": "clinician_required",
            "formal_score": clinician_lookup.get("BRUNNSTROM", clinician_lookup.get("BRUNNSTROM_STAGE")),
            "reason": "视频动作证据可辅助分期，但肌张力、联合反应和极轻微运动需临床确认。",
        },
    ]

    return {
        "version": "1.0",
        "reporting_rule": "仅按真实来源填值；模型肌力需求不转换为MMT，足底负荷代理不转换为真实足底压力或CoP。",
        "summary": {
            "auto_filled": sum(row["status"] == "auto_filled" and row["applicable_to_submitted_tasks"] for row in rows),
            "model_filled": sum(row["status"] == "model_filled" and row["applicable_to_submitted_tasks"] for row in rows),
            "clinician_filled": sum(row["status"] == "clinician_filled" and row["applicable_to_submitted_tasks"] for row in rows),
            "tool_filled": sum(row["status"] == "tool_filled" and row["applicable_to_submitted_tasks"] for row in rows),
            "pending": sum(row["status"] not in {"auto_filled", "model_filled", "clinician_filled", "tool_filled"} and row["applicable_to_submitted_tasks"] for row in rows),
        },
        "domains": domains,
        "scale_readiness": scale_readiness,
    }
