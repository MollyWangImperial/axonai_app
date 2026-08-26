"""Generate auditable short- and long-term stroke rehabilitation goals."""

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    from backend.rehab_goal_evidence import retrieve_goal_evidence
except ImportError:
    from rehab_goal_evidence import retrieve_goal_evidence


DOMAIN_BY_PREFIX = {
    "T": "upper_limb",
    "H": "hand",
    "L": "lower_limb",
    "B": "balance",
}

DOMAIN_LABELS = {
    "upper_limb": "上肢功能",
    "hand": "手功能",
    "lower_limb": "下肢功能",
    "balance": "平衡功能",
    "adl": "日常生活活动",
}

SHORT_TARGETS = {
    "upper_limb": "在相同坐位和安全条件下完成至少1个当前未完成的上肢步骤，并保持已完成步骤；全过程记录关节角和躯干/肩胛带代偿。",
    "hand": "在清晰手部视野下完成至少1个当前未完成的张手、捏合、抓持或释放步骤，并在连续3次尝试中至少2次达到步骤完成条件。",
    "lower_limb": "在治疗师或具备能力的照护者保护及既定支撑条件下完成至少1个当前未完成的下肢步骤，并保持已完成步骤。",
    "balance": "在原安全条件下完成至少1个当前未完成的坐位或扶持站立平衡步骤，且不增加人工帮助等级。",
}

LONG_TARGETS = {
    "upper_limb": "在一项由患者确认的重要日常任务中主动使用患侧上肢完成到达、定位或持物环节，所需帮助不高于治疗师设定等级。",
    "hand": "在一项由患者选择的进食、修饰、穿衣或物品操作任务中，将患手作为操作手或稳定手完成连续功能链。",
    "lower_limb": "在治疗师确认安全并选择适当辅具后，完成床椅转移并向室内功能性移动目标进阶，帮助等级较基线至少改善1级或达到共同约定等级。",
    "balance": "在与个人生活环境相关的转移或站立活动中维持安全平衡，并在完整标准化平衡量表复评后达到治疗师共同设定的变化目标。",
}

OUTCOME_MEASURES = {
    "upper_limb": "重复相同上肢任务包；记录完成步骤、肩/肘角度及代偿表型",
    "hand": "重复相同手功能任务包；必要时结合ARAT/FMA-UE或医院手功能表",
    "lower_limb": "重复相同下肢任务包；结合MMT、ROM、转移帮助等级和步行观察",
    "balance": "重复相同平衡任务包；由治疗师完成Berg/PASS及帮助等级记录",
    "adl": "改良Barthel指数及选定ADL项目的实际帮助等级",
}


def _value(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _clinician_lookup(patient_parameters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    measures = (patient_parameters or {}).get("clinician_measures") or {}
    return {str(key).upper(): value for key, value in measures.items()}


def _parse_grade(value: Any) -> Optional[int]:
    if value is None:
        return None
    match = re.search(r"(?<!\d)([0-5])(?!\d)", str(value))
    return int(match.group(1)) if match else None


def _domain_task_summary(task_results: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    summaries: Dict[str, Dict[str, Any]] = {}
    for task in task_results:
        task_id = str(_value(task, "task_id", ""))
        domain = DOMAIN_BY_PREFIX.get(task_id[:1])
        if not domain:
            continue
        bucket = summaries.setdefault(domain, {"task_ids": [], "completed": 0, "total": 0, "failed_steps": []})
        bucket["task_ids"].append(task_id)
        bucket["completed"] += int(_value(task, "completed_steps", 0) or 0)
        bucket["total"] += int(_value(task, "total_steps", 0) or 0)
        for step in _value(task, "steps", []) or []:
            if not bool(_value(step, "completed", False)):
                bucket["failed_steps"].append(str(_value(step, "step_id", "")))
    return summaries


def _domain_issue_codes(functional_issues: Iterable[Any], domain: str) -> List[str]:
    prefixes = {"upper_limb": "T", "hand": "H", "lower_limb": "L", "balance": "B"}
    prefix = prefixes[domain]
    return [
        str(_value(issue, "code", ""))
        for issue in functional_issues
        if str(_value(issue, "related_task", "")).startswith(prefix)
    ]


def _patient_priorities(patient_parameters: Optional[Dict[str, Any]]) -> List[str]:
    raw = (patient_parameters or {}).get("patient_priorities") or []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    return [str(item) for item in raw if str(item).strip()]


def _goal(
    goal_id: str,
    horizon: str,
    domain: str,
    statement: str,
    timeframe: str,
    baseline: str,
    target: str,
    task_ids: Sequence[str],
    issue_codes: Sequence[str],
    patient_priority: Optional[str],
    extra_tags: Sequence[str] = (),
    clinician_confirmation_required: bool = True,
) -> Dict[str, Any]:
    tags = ["stroke", "goal_setting", domain, "smart", "review", *extra_tags]
    if patient_priority:
        tags.append("patient_priority")
    return {
        "id": goal_id,
        "horizon": horizon,
        "domain": domain,
        "domain_label": DOMAIN_LABELS[domain],
        "statement": statement,
        "timeframe": timeframe,
        "baseline": baseline,
        "target": target,
        "outcome_measure": OUTCOME_MEASURES[domain],
        "review_schedule": "每周由康复团队复核进展；在时间窗结束时使用相同方法正式复评。",
        "linked_task_ids": list(task_ids),
        "linked_issue_codes": list(issue_codes),
        "patient_priority": patient_priority,
        "patient_agreement_required": patient_priority is None,
        "clinician_confirmation_required": clinician_confirmation_required,
        "status": "draft_for_shared_decision",
        "evidence": retrieve_goal_evidence(tags, top_k=3),
    }


def build_rehab_goals(
    task_results: Iterable[Any],
    functional_issues: Iterable[Any],
    measurement_form: Dict[str, Any],
    patient_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build short/long-term drafts from measured baseline and retrieved rules."""
    task_results = list(task_results)
    functional_issues = list(functional_issues)
    summaries = _domain_task_summary(task_results)
    priorities = _patient_priorities(patient_parameters)
    patient_priority = priorities[0] if priorities else None
    short_term: List[Dict[str, Any]] = []
    long_term: List[Dict[str, Any]] = []

    for domain, summary in summaries.items():
        completed = summary["completed"]
        total = summary["total"]
        failed_steps = summary["failed_steps"]
        issue_codes = _domain_issue_codes(functional_issues, domain)
        baseline = f"本次{DOMAIN_LABELS[domain]}任务完成 {completed}/{total} 个步骤"
        if failed_steps:
            baseline += f"；未完成步骤：{', '.join(failed_steps)}"
            short_target = SHORT_TARGETS[domain]
        else:
            baseline += "；本次提交步骤均完成，但仍需复核动作质量和未采集能力"
            short_target = "在相同协议下再次完成全部步骤，并保持安全、无新增失败表型；由治疗师选择一项动作质量指标作为进阶条件。"

        short_term.append(
            _goal(
                f"ST_{domain.upper()}_TASK",
                "short_term",
                domain,
                f"近期（2-4周）{short_target}",
                "2-4周",
                baseline,
                short_target,
                summary["task_ids"],
                issue_codes,
                patient_priority,
                ("task_specific",),
            )
        )
        long_target = LONG_TARGETS[domain]
        if patient_priority:
            long_target = f"围绕患者确认的优先事项“{patient_priority}”，{long_target}"
        long_term.append(
            _goal(
                f"LT_{domain.upper()}_PARTICIPATION",
                "long_term",
                domain,
                f"远期（8-12周或出院前）{long_target}",
                "8-12周或出院前",
                baseline,
                long_target,
                summary["task_ids"],
                issue_codes,
                patient_priority,
                ("adl", "task_specific") if domain in {"upper_limb", "hand"} else ("walking", "adl"),
            )
        )

    measures = _clinician_lookup(patient_parameters)
    mmt_upper = _parse_grade(measures.get("MMT_UPPER_LIMB", measures.get("MMT_UPPER")))
    mmt_lower = _parse_grade(measures.get("MMT_LOWER_LIMB", measures.get("MMT_LOWER")))
    for domain, grade in (("upper_limb", mmt_upper), ("lower_limb", mmt_lower)):
        if grade is None or grade >= 5:
            continue
        next_grade = grade + 1
        short_term.append(
            _goal(
                f"ST_{domain.upper()}_MMT",
                "short_term",
                domain,
                f"近期（2-4周）在治疗师标准化MMT复评中，使目标肌群从当前{grade}/5向{next_grade}/5的下一运动能力等级进阶，同时改善对应功能任务。",
                "2-4周",
                f"治疗师MMT基线 {grade}/5",
                f"目标肌群达到相邻等级{next_grade}/5，或虽未跨级但功能任务帮助等级改善；最终目标由治疗师结合具体肌群确认。",
                summaries.get(domain, {}).get("task_ids", []),
                _domain_issue_codes(functional_issues, domain),
                patient_priority,
                ("measurement",),
            )
        )

    mas = measures.get("MAS", measures.get("ASHWORTH", measures.get("MODIFIED_ASHWORTH")))
    if mas is not None:
        affected_domain = "upper_limb" if "upper_limb" in summaries else "lower_limb"
        short_term.append(
            _goal(
                "ST_TONE_FUNCTION",
                "short_term",
                affected_domain,
                "近期（2-4周）维持治疗师测得的被动关节活动范围，并减少异常肌张力对摆位、清洁、穿衣或主动任务的干扰；MAS作为复评指标之一，不作为唯一成功标准。",
                "2-4周",
                f"治疗师记录MAS {mas}",
                "被动ROM不下降，且至少1项受肌张力影响的护理或功能任务帮助程度改善；MAS由治疗师按相同协议复评，但不作为唯一成功标准。",
                summaries.get(affected_domain, {}).get("task_ids", []),
                _domain_issue_codes(functional_issues, affected_domain),
                patient_priority,
                ("measurement", "adl"),
            )
        )

    mbi = measures.get("MBI", measures.get("MODIFIED_BARTHEL_INDEX"))
    if mbi is not None:
        long_term.append(
            _goal(
                "LT_ADL_INDEPENDENCE",
                "long_term",
                "adl",
                "远期（8-12周或出院前）在患者选择的一项基本日常生活活动中，将实际帮助等级较基线改善至少1级，并用同一MBI条目及现场表现复评。",
                "8-12周或出院前",
                f"MBI总分基线 {mbi}；仍需记录患者最重视的具体ADL条目",
                "选定ADL条目帮助等级改善至少1级；总分变化仅作辅助，不替代具体活动表现。",
                [],
                [],
                patient_priority,
                ("adl", "patient_priority"),
            )
        )

    # Keep the draft usable while preventing an unreviewed list from becoming
    # an overlong treatment plan.
    short_term = short_term[:8]
    long_term = long_term[:5]
    missing = []
    if not patient_priority:
        missing.append("患者最重视并希望恢复的具体活动或参与目标")
    if not measures:
        missing.append("治疗师量表基线（至少MMT、MAS、ROM、平衡/ADL相关量表）")
    if any(domain in summaries for domain in ("lower_limb", "balance")):
        missing.append("站立、转移和步行的当前帮助等级及辅具")

    return {
        "version": "1.0",
        "method": "retrieval_augmented_rule_engine",
        "status": "draft_for_shared_decision",
        "short_term": short_term,
        "long_term": long_term,
        "missing_information": missing,
        "safety_rule": "目标生成不构成独立治疗处方；站立、转移、步行、被动牵伸和抗阻目标必须由卒中康复专业人员确认安全条件。",
        "generation_rule": "目标必须绑定本次基线、可观察目标、时间窗、复评方法和来源；缺少个人优先事项或临床基线时保留待确认状态。",
        "measurement_form_version": measurement_form.get("version"),
    }
