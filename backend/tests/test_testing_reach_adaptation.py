from backend.assessment_quality import VERSION, build_rubrics, testing_task_report as report

TASK = {"id": "T1", "title": "Seated Forward Reach", "steps": [
    {"id": f"T1-S{i}", "caption": f"Step {i}", "target": {"landmark": "LAP_DYNAMIC" if i == 4 else "WRIST"}}
    for i in range(1, 5)]}
RULES = build_rubrics([TASK])


def attempt(level=0, assisted=False):
    return {"task_id": "T1", "steps": [{"step_id": rule["id"], "completed": True, "duration_ms": 1000, "metrics": {
        "quality": {"version": VERSION, "measurements": {r["metric"]: {"value": r["target"], "samples": 10} for r in rule["criteria"]},
                    "compensations": {c: {"eligible_ms": 1000, "max_value": 0, "max_streak_ms": 0} for c in rule["compensations"]}},
        "testing_reach": {"version": "testing-reach-adaptation-1", "final_level": level, "assisted": assisted, "reductions": []}}}
        for rule in RULES["T1"]["steps"]]}


def test_fixed_references_and_reduced_movement_points_with_per_step_assistance():
    full = report(attempt(), RULES)["task"]
    easier = report(attempt(2), RULES)["task"]
    assisted = report(attempt(2, True), RULES)["task"]
    assert full["score"] == 100
    assert [s["score"] for s in easier["steps"]] == [76, 76, 76, 100]
    assert easier["score"] == 82
    assert assisted["score"] == 53.5  # return-to-lap remains completion-only
    assert assisted["steps"][3]["score"] == 100
    assert assisted["steps"][3]["calculation"]["assistance_factor"] == 1
    assert easier["steps"][1]["criteria"][0]["target"] == 110
    assert easier["steps"][1]["calculation"]["raw_range_points"] == 80
    assert easier["steps"][1]["calculation"]["range_points"] == 56


def test_missing_tracking_is_not_zero_function_or_perfect_form():
    data = attempt()
    data["steps"][1]["metrics"]["quality"] = {}
    result = report(data, RULES)["task"]
    assert result["score"] is None
    assert result["steps"][1]["score"] is None
    assert result["measured_steps"] == 3


def test_invalid_adaptation_does_not_award_full_credit_and_legacy_scoring_is_preserved():
    data = attempt()
    data["steps"][0]["metrics"]["testing_reach"]["final_level"] = -1
    assert report(data, RULES)["task"]["score"] is None
    data = attempt()
    for s in data["steps"]:
        del s["metrics"]["testing_reach"]
    assert report(data, RULES)["task"]["score"] == 100


def test_face_only_comparison_lean_reduces_testing_reach_score():
    data = attempt()
    face_only = data["steps"][1]["metrics"]["quality"]["compensations"]["trunk_lean"]
    face_only.update(method="pelvis_normalized_shoulder_or_face_v1", max_value=8.1,
                     max_streak_ms=600, face_peak=8.1, shoulder_peak=0)
    step = report(data, RULES)["task"]["steps"][1]
    check = next(item for item in step["compensations"] if item["id"] == "trunk_lean")
    assert check["status"] == "detected"
    assert check["face_threshold"] == 7
    assert check["face_peak"] == 8.1
    assert step["score"] == 80
    assert report(data, RULES)["task"]["score"] == 95

    face_only.pop("method")
    assert report(data, RULES)["task"]["steps"][1]["score"] == 100
