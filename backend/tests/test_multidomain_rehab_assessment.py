import os
import sys
import types

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_multidomain_test")

if "emergentintegrations.llm.chat" not in sys.modules:
    emergent = types.ModuleType("emergentintegrations")
    llm = types.ModuleType("emergentintegrations.llm")
    chat = types.ModuleType("emergentintegrations.llm.chat")

    class _UnavailableChatDependency:
        def __init__(self, *args, **kwargs):
            pass

    chat.LlmChat = _UnavailableChatDependency
    chat.UserMessage = _UnavailableChatDependency
    sys.modules.setdefault("emergentintegrations", emergent)
    sys.modules.setdefault("emergentintegrations.llm", llm)
    sys.modules.setdefault("emergentintegrations.llm.chat", chat)

from backend import server
from backend.rehab_assessment import build_biomechanical_estimates
from backend.clinical_measurement_form import build_clinical_measurement_form
from backend.rehab_goal_evidence import retrieve_goal_evidence
from backend.rehab_goals import build_rehab_goals


def _failed_result(package_id: str, task_id: str, step_id: str):
    task = next(task for task in server.ASSESSMENT_PACKAGES[package_id]["tasks"] if task["id"] == task_id)
    steps = [
        server.TaskStepResult(step_id=step["id"], completed=step["id"] != step_id)
        for step in task["steps"]
    ]
    return server.TaskResult(
        task_id=task_id,
        completed_steps=sum(step.completed for step in steps),
        total_steps=len(steps),
        steps=steps,
    )


def test_all_packages_expose_unique_step_level_failure_phenotypes():
    assert set(server.ASSESSMENT_PACKAGES) == {"upper_limb", "hand", "lower_limb", "balance"}
    step_ids = []
    for package in server.ASSESSMENT_PACKAGES.values():
        for task in package["tasks"]:
            for step in task["steps"]:
                step_ids.append(step["id"])
                assert step.get("failure_phenotype"), step["id"]
                assert step["failure_phenotype"].get("rehab_code")
    assert len(step_ids) == len(set(step_ids))
    assert set(server.STEP_PHENOTYPES) == set(step_ids)


def test_hand_lower_limb_and_balance_failures_are_localized():
    cases = [
        ("hand", "H3", "H3-S2", "PINCH_IMPAIRED"),
        ("lower_limb", "L3", "L3-S2", "SIT_TO_STAND_IMPAIRED"),
        ("balance", "B4", "B4-S2", "WEIGHT_BEARING_ASYMMETRY"),
    ]
    for package_id, task_id, step_id, expected_code in cases:
        issue = server.derive_functional_issues([_failed_result(package_id, task_id, step_id)])[0]
        assert issue.code == expected_code
        assert issue.related_task == task_id
        assert issue.related_step == step_id


def test_pose_only_outputs_never_claim_direct_strength_or_plantar_pressure():
    result = server.TaskResult(
        task_id="B4",
        completed_steps=2,
        total_steps=3,
        metrics={"affected_load_proxy": 0.42, "trunk_lean_deg": 17},
    )
    estimates = build_biomechanical_estimates([result])
    by_code = {item["code"]: item for item in estimates}
    assert by_code["PLANTAR_LOAD_DISTRIBUTION_PROXY"]["provenance"] == "camera_proxy"
    assert "not plantar pressure" in by_code["PLANTAR_LOAD_DISTRIBUTION_PROXY"]["interpretation"].lower()
    assert by_code["MUSCLE_FORCE_MODEL_STATUS"]["value"] is None
    assert by_code["MUSCLE_FORCE_MODEL_STATUS"]["confidence"] == "unavailable"


def test_validated_opensim_outputs_are_reported_as_model_estimates():
    estimates = build_biomechanical_estimates(
        [],
        {"height_cm": 170, "mass_kg": 70},
        {
            "status": "completed",
            "external_load_method": "modeled_contact",
            "quality": {"kinematics_valid": True, "external_loads_valid": True},
            "muscle_forces_n": {"quadriceps": 820},
            "joint_moments_nm": {"knee_extension": 44},
            "confidence": "model_estimate_with_modeled_external_loads",
        },
    )
    by_code = {item["code"]: item for item in estimates}
    assert by_code["MUSCLE_FORCE_QUADRICEPS"]["value"] == 820
    assert by_code["MUSCLE_FORCE_QUADRICEPS"]["provenance"] == "musculoskeletal_model"
    assert "not directly measured maximum muscle strength" in by_code["MUSCLE_FORCE_QUADRICEPS"]["interpretation"]
    assert by_code["JOINT_MOMENT_KNEE_EXTENSION"]["value"] == 44


def test_measurement_form_keeps_pose_model_and_clinician_sources_separate():
    result = server.TaskResult(
        task_id="L4",
        completed_steps=3,
        total_steps=3,
        steps=[
            server.TaskStepResult(
                step_id="L4-S2",
                completed=True,
                metrics={
                    "toe_clearance_leg_ratio": 0.08,
                    "circumduction_leg_ratio": 0.04,
                    "affected_step_length_leg_ratio": 0.31,
                },
            )
        ],
    )
    form = build_clinical_measurement_form(
        [result],
        {"clinician_measures": {"mmt_lower_limb": "2/5", "mas": "2"}},
        {
            "status": "completed",
            "external_load_method": "modeled_contact",
            "quality": {"kinematics_valid": True, "external_loads_valid": True},
            "muscle_forces_n": {"quadriceps": 650},
            "joint_moments_nm": {"knee_extension": 38},
        },
    )
    rows = {
        row["code"]: row
        for domain in form["domains"]
        for row in domain["rows"]
    }
    assert rows["LE_TOE_CLEARANCE"]["status"] == "auto_filled"
    assert rows["LE_TOE_CLEARANCE"]["value"] == 0.08
    assert rows["LE_MUSCLE_FORCE_DEMAND"]["status"] == "model_filled"
    assert rows["LE_MMT"]["status"] == "clinician_filled"
    assert rows["MAS"]["status"] == "clinician_filled"
    assert rows["PLANTAR_PRESSURE"]["status"] == "tool_required"


def test_measurement_form_never_converts_model_force_to_mmt():
    form = build_clinical_measurement_form(
        [server.TaskResult(task_id="L1", completed_steps=1, total_steps=1)],
        {},
        {
            "status": "completed",
            "external_load_method": "modeled_contact",
            "quality": {"kinematics_valid": True, "external_loads_valid": True},
            "muscle_forces_n": {"quadriceps": 900},
        },
    )
    rows = {
        row["code"]: row
        for domain in form["domains"]
        for row in domain["rows"]
    }
    assert rows["LE_MUSCLE_FORCE_DEMAND"]["status"] == "model_filled"
    assert rows["LE_MMT"]["value"] is None
    assert rows["LE_MMT"]["status"] == "clinician_required"


def test_upper_limb_form_exposes_camera_model_and_clinical_metrics_without_cross_domain_leakage():
    results = [
        server.TaskResult(
            task_id="T1",
            completed_steps=3,
            total_steps=4,
            duration_ms=4200,
            metrics={
                "affected_wrist_displacement_body_ratio": 1.25,
                "trunk_lean_deg": 22,
                "shoulder_elevation_deg": 88,
                "elbow_flexion_deg": 64,
                "shoulder_hike": True,
            },
        ),
        server.TaskResult(
            task_id="T4",
            completed_steps=6,
            total_steps=6,
            duration_ms=6500,
            metrics={"objectHandCoupling": 0.84, "placementEndpointError": 0.07, "releaseDelayMs": 310},
        ),
        server.TaskResult(
            task_id="T3",
            completed_steps=4,
            total_steps=4,
            duration_ms=3600,
            metrics={"hand_to_mouth_distance_ratio": 0.18},
        ),
        server.TaskResult(
            task_id="T5",
            completed_steps=5,
            total_steps=6,
            duration_ms=5100,
            metrics={
                "hand_open_score": 0.68,
                "fist_closure_score": 0.61,
                "finger_total_flexion_deg": 124,
                "finger_abduction_ratio": 1.42,
            },
        ),
        server.TaskResult(
            task_id="T6",
            completed_steps=4,
            total_steps=4,
            duration_ms=3900,
            metrics={"pinch_score": 0.73, "thumb_index_distance_ratio": 0.21},
        ),
        server.TaskResult(
            task_id="T7",
            completed_steps=4,
            total_steps=4,
            duration_ms=4300,
            metrics={"bilateral_wrist_displacement_symmetry": 0.81},
        ),
    ]
    form = build_clinical_measurement_form(
        results,
        {"clinician_measures": {"mmt_upper_limb": "2/5", "mas": "2", "brunnstrom": "III"}},
        {
            "status": "completed",
            "external_load_method": "modeled_contact",
            "quality": {"kinematics_valid": True, "external_loads_valid": True},
            "muscle_forces_n": {"anterior_deltoid": 210},
            "joint_moments_nm": {"shoulder_flexion": 18},
        },
    )
    rows = {row["code"]: row for domain in form["domains"] for row in domain["rows"]}

    expected_auto = {
        "UL_TASK_COMPLETION", "UL_TASK_DURATION", "UL_WRIST_DISPLACEMENT",
        "UL_TRUNK_COMPENSATION", "UL_SHOULDER_ELEVATION", "UL_ELBOW_FLEXION",
        "UL_HAND_TO_MOUTH_DISTANCE", "UL_SHOULDER_HIKE", "UL_BILATERAL_SYMMETRY",
        "UL_HAND_OPEN", "UL_GRASP_CLOSURE", "UL_PINCH",
        "UL_FINGER_FLEXION", "UL_FINGER_ABDUCTION", "UL_THUMB_OPPOSITION",
        "UL_OBJECT_COUPLING", "UL_OBJECT_PLACEMENT_ERROR", "UL_OBJECT_RELEASE_DELAY",
    }
    assert all(rows[code]["status"] == "auto_filled" for code in expected_auto)
    assert rows["UL_MUSCLE_FORCE_DEMAND"]["status"] == "model_filled"
    assert rows["UL_JOINT_MOMENT"]["status"] == "model_filled"
    assert rows["UL_MMT"]["value"] == "2/5"
    assert rows["MAS"]["value"] == "2"
    assert rows["BRUNNSTROM"]["value"] == "III"
    assert rows["LE_MUSCLE_FORCE_DEMAND"]["status"] == "model_required"
    assert rows["LE_MUSCLE_FORCE_DEMAND"]["applicable_to_submitted_tasks"] is False
    assert rows["BERG_TOTAL"]["applicable_to_submitted_tasks"] is False
    assert all(
        row["domain"] in {"upper_limb", "cross_domain"}
        for domain in form["domains"]
        for row in domain["rows"]
        if row["applicable_to_submitted_tasks"]
    )


def test_completed_upper_limb_task_still_reports_compensation_and_adapts_plan_to_mmt_mas():
    result = server.TaskResult(
        task_id="T1",
        completed_steps=4,
        total_steps=4,
        metrics={"trunk_lean_deg": 27, "shoulder_hike": True},
    )
    issues = server.derive_functional_issues([result])
    assert {issue.code for issue in issues} == {"TRUNK_COMP", "SHOULDER_HIKE"}

    plan = server.build_rehab_plan(
        issues,
        {
            "patient_priorities": ["Eat independently with the affected hand"],
            "clinician_measures": {"mmt_upper_limb": "2/5", "mas": "2"},
        },
    )
    assert {exercise.id for exercise in plan} == {"ex_trunk", "ex_scapdepress"}
    assert all(exercise.sets <= 2 and exercise.reps <= 8 for exercise in plan)
    assert all("MMT 0-2/5" in exercise.safety_note for exercise in plan)
    assert all("MAS 2" in exercise.safety_note for exercise in plan)
    assert all("Eat independently" in exercise.selection_reason for exercise in plan)


def test_profile_goal_is_merged_into_assessment_parameters():
    merged = server._assessment_patient_parameters(
        {},
        {
            "profile": {
                "primary_goal": "Drink from a cup using my affected hand",
                "secondary_goals": ["dress"],
                "dominant_hand": "right",
            }
        },
    )
    assert merged["patient_priorities"] == ["Drink from a cup using my affected hand", "dress"]
    assert merged["dominant_hand"] == "right"


def test_routes_expose_packages_modeling_contract_and_multidomain_results():
    with TestClient(server.app) as client:
        for package_id in ("hand", "lower_limb", "balance"):
            response = client.get(f"/api/assessment/tasks?package={package_id}")
            assert response.status_code == 200
            payload = response.json()
            assert payload["package_id"] == package_id
            assert payload["tasks"]
            assert all(step.get("failure_phenotype") for task in payload["tasks"] for step in task["steps"])

        spec = client.get("/api/assessment/modeling-spec")
        assert spec.status_code == 200
        assert "external loads" in " ".join(spec.json()["required_inputs"]).lower()

        result = _failed_result("lower_limb", "L3", "L3-S2")
        submitted = client.post(
            "/api/assessment/submit",
            json={
                "affected_side": "right",
                "patient_parameters": {
                    "height_cm": 170,
                    "mass_kg": 70,
                    "clinician_measures": {"mmt_lower_limb": "2/5"},
                },
                "task_results": [result.model_dump()],
            },
        )
        assert submitted.status_code == 200
        assessment = submitted.json()
        assert assessment["domain_assessments"][0]["domain"] == "lower_limb"
        assert assessment["clinician_measures"][0]["provenance"] == "clinician_measure"
        assert any(item["code"] == "MUSCLE_FORCE_MODEL_STATUS" for item in assessment["biomechanical_estimates"])
        assert assessment["measurement_form"]["version"] == "1.0"
        measurement_rows = {
            row["code"]: row
            for domain in assessment["measurement_form"]["domains"]
            for row in domain["rows"]
        }
        assert measurement_rows["LE_MMT"]["value"] == "2/5"
        assert assessment["rehab_plan"][0]["targets_issue"] == "SIT_TO_STAND_IMPAIRED"
        assert assessment["rehabilitation_goals"]["method"] == "retrieval_augmented_rule_engine"


def test_goal_generator_uses_patient_baseline_and_traceable_rules():
    result = _failed_result("lower_limb", "L3", "L3-S2")
    issues = server.derive_functional_issues([result])
    patient_parameters = {
        "patient_priorities": ["在家中安全完成床椅转移并逐步恢复室内行走"],
        "clinician_measures": {
            "mmt_lower_limb": "2/5",
            "mas": "2",
            "mbi": 23,
        },
    }
    form = build_clinical_measurement_form([result], patient_parameters, None)

    goals = build_rehab_goals([result], issues, form, patient_parameters)

    assert goals["status"] == "draft_for_shared_decision"
    assert goals["short_term"]
    assert goals["long_term"]
    assert all(goal["evidence"] for goal in goals["short_term"] + goals["long_term"])
    assert all(
        item["url"].startswith("https://")
        for goal in goals["short_term"] + goals["long_term"]
        for item in goal["evidence"]
    )
    assert all(goal["patient_agreement_required"] is False for goal in goals["short_term"] + goals["long_term"])
    assert any(goal["baseline"] == "治疗师MMT基线 2/5" for goal in goals["short_term"])
    assert any("3/5" in goal["target"] for goal in goals["short_term"])
    assert any("MAS" in goal["baseline"] and "唯一成功标准" in goal["target"] for goal in goals["short_term"])
    assert all(patient_parameters["patient_priorities"][0] in goal["statement"] for goal in goals["long_term"][:1])


def test_goal_generator_requires_shared_decision_when_patient_priority_is_missing():
    result = _failed_result("balance", "B4", "B4-S2")
    issues = server.derive_functional_issues([result])
    form = build_clinical_measurement_form([result], {}, None)

    goals = build_rehab_goals([result], issues, form, {})

    assert any("患者最重视" in item for item in goals["missing_information"])
    assert all(goal["patient_agreement_required"] is True for goal in goals["short_term"] + goals["long_term"])


def test_evidence_retrieval_is_deterministic_and_relevant():
    first = retrieve_goal_evidence(("smart", "shared_decision", "task_specific"), top_k=3)
    second = retrieve_goal_evidence(("smart", "shared_decision", "task_specific"), top_k=3)

    assert first == second
    assert len(first) == 3
    assert all(item["retrieval_score"] > 0 for item in first)
    assert any("NICE" in item["source"] for item in first)


def test_runner_contains_lower_limb_balance_and_affected_side_logic():
    source = server.POSE_RUNNER_HTML
    assert 'const AFFECTED_SIDE = URL_PARAMS.get("affected_side")' in source
    assert 'ASSESSMENT_PACKAGE === "lower_limb"' in source
    assert 'ASSESSMENT_PACKAGE === "balance"' in source
    assert 'which === "KNEE_EXTENDED"' in source
    assert 'which === "WEIGHT_SHIFT_AFFECTED"' in source
    assert "toe_clearance_leg_ratio" in source
    assert "finger_total_flexion_deg" in source
    assert "affected_side: AFFECTED_SIDE" in source
