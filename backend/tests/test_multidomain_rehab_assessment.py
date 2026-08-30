import os
import sys
import types
import uuid
import asyncio

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
from backend.assessment_fusion import build_analysis_pipeline, build_clinical_review_gate, build_survey_consistency


def test_text_chat_assessment_start_intent_advances_only_when_requested():
    ready_offer = [{"role": "assistant", "text": "I can open your initial assessment now. Are you ready?"}]
    safety_question = [{"role": "assistant", "text": "Before the assessment, have you had any sudden changes recently?"}]

    assert server._chat_requests_assessment_start("Please start my assessment", []) is True
    assert server._chat_requests_assessment_start("yes", ready_offer) is True
    assert server._chat_requests_assessment_start("yes", safety_question) is False
    assert server._chat_requests_assessment_start("show my assessment history", []) is False
    assert server._chat_requests_assessment_start("I am not ready for the assessment", []) is False


def test_text_chat_identifies_only_consent_setup_loops():
    assert server._chat_mentions_consent_setup("Please check your health-data consent settings") is True
    assert server._chat_mentions_consent_setup("Would you like to provide consent?") is True
    assert server._chat_mentions_consent_setup("Explain how Rehyn protects my privacy") is False


def test_text_chat_returns_initial_assessment_navigation_without_calling_the_llm(monkeypatch):
    class _ChatSessions:
        async def find_one(self, *_args, **_kwargs):
            return None

        async def update_one(self, *_args, **_kwargs):
            return None

    async def _signed_in_user(_headers):
        return {"id": "patient-1", "name": "Patient", "profile": {}}

    async def _empty_records(_user_id):
        return []

    monkeypatch.setattr(server, "EMERGENT_LLM_KEY", "")
    monkeypatch.setattr(server, "openai_tts_client", None)
    monkeypatch.setattr(server, "db", types.SimpleNamespace(chat_sessions=_ChatSessions()))
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    monkeypatch.setattr(server, "_care_assessments_for_user", _empty_records)
    monkeypatch.setattr(server, "_care_check_ins_for_user", _empty_records)
    monkeypatch.setattr(server, "_care_activities_for_user", _empty_records)

    response = asyncio.run(server.chat_message(
        server.ChatRequest(session_id="assessment-handoff", text="Please start my assessment"),
        types.SimpleNamespace(headers={}),
    ))

    assert response.navigation_destination == "initial_assessment"
    assert "opening your Initial Assessment" in response.text


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
    assert set(server.ASSESSMENT_PACKAGES) == {"initial", "upper_limb", "hand", "lower_limb", "balance"}
    step_ids = []
    for package_id, package in server.ASSESSMENT_PACKAGES.items():
        if package_id == "initial":
            continue
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


def test_no_observed_issue_does_not_create_a_maintenance_rehab_plan():
    issues = [server.FunctionalIssue(
        code="NO_ISSUES",
        label="No failed movement steps identified",
        description="All observed steps were completed.",
        source="camera",
        severity="mild",
        related_task="ALL",
    )]
    assert server.build_rehab_plan(issues) == []


def test_every_plan_exercise_has_dedicated_stepwise_encouraging_voice_guidance():
    library_ids = {exercise.id for exercise in server.EXERCISE_LIBRARY.values()}
    assert set(server.REHAB_RUNNER_CONFIG) == library_ids
    for exercise_id, config in server.REHAB_RUNNER_CONFIG.items():
        assert config.get("setup_voice"), exercise_id
        assert config.get("cycle"), exercise_id
        assert config.get("feedback_rules"), exercise_id
        assert any(rule.get("default") for rule in config["feedback_rules"]), exercise_id
        for step in config["cycle"]:
            assert step.get("caption"), (exercise_id, step)
            assert step.get("voice"), (exercise_id, step)
    guided_ids = {
        "ex_lower_selective", "ex_ankle_dorsiflexion", "ex_sit_to_stand", "ex_supported_stand",
        "ex_supported_step", "ex_weight_shift", "ex_sitting_balance", "ex_step_stance",
    }
    assert all(server.REHAB_RUNNER_CONFIG[item]["pose_mode"] == "guided" for item in guided_ids)
    assert all(len(server.REHAB_RUNNER_CONFIG[item]["cycle"]) >= 3 for item in guided_ids)


def test_rehab_runner_prefetches_voice_and_uses_prescribed_repetitions():
    source = server.REHAB_RUNNER_HTML_TEMPLATE
    assert "function prefetchVoice(text)" in source
    assert "CFG.cycle.forEach(step => prefetchVoice(step.voice))" in source
    assert 'CFG.pose_mode === "tap" || CFG.pose_mode === "guided"' in source
    assert 'tapBtn.textContent = CFG.pose_mode === "guided" ? "I completed this step"' in source
    assert 'const cameraScored = CFG.pose_mode === "body"' in source
    html = server._rehab_runner_html("ex_sit_to_stand", 7)
    assert '"name": "Assisted Sit-to-Stand Practice"' in html
    assert '"reps": 7' in html


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


def test_routes_expose_packages_modeling_contract_and_multidomain_results(monkeypatch):
    selected = {"package": "hand", "task_ids": []}

    async def user_from_header(_headers):
        return {
            "id": "u_multidomain_routes",
            "credits": 10000,
            "profile": {"months_since_stroke": 8},
            "consent": {"health_data_consent": True},
        }

    async def prior_assessments(_user_id):
        return [{"id": "prior", "created_at": "2026-01-01T00:00:00+00:00"}]

    async def care_plan(_user, **_kwargs):
        return {
            "assessment": {
                "due": True,
                "can_start": True,
                "trigger": "scheduled",
                "issue_report_id": None,
                "packages": [selected["package"]],
                "task_ids": selected["task_ids"],
            }
        }

    async def no_credit_charge(*_args, **_kwargs):
        return None

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", prior_assessments)
    monkeypatch.setattr(server, "_adaptive_care_plan_for_user", care_plan)
    monkeypatch.setattr(server, "consume_credits", no_credit_charge)
    with TestClient(server.app) as client:
        for package_id in ("hand", "lower_limb", "balance"):
            selected["package"] = package_id
            selected["task_ids"] = [task["id"] for task in server.ASSESSMENT_PACKAGES[package_id]["tasks"]]
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
        selected["package"] = "lower_limb"
        selected["task_ids"] = ["L3"]
        submitted = client.post(
            "/api/assessment/submit",
            json={
                "assessment_package": "lower_limb",
                "assigned_task_ids": ["L3"],
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
        assert assessment["rehab_plan"] == []
        assert assessment["clinical_review_gate"]["status"] == "awaiting_model_analysis"
        assert assessment["rehabilitation_goals"]["method"] == "retrieval_augmented_rule_engine"

        patient_summary = client.get(f"/api/assessment/{assessment['id']}/patient-summary")
        assert patient_summary.status_code == 200
        summary_payload = patient_summary.json()
        assert set(summary_payload) == {
            "id", "created_at", "assessment_package", "collection", "body_function_summary",
            "rehab_plan_ready", "clinical_review_gate", "insights",
        }
        assert summary_payload["insights"]["status"] == "processing"
        assert summary_payload["collection"]["tasks_collected"] == 1
        assert "analysis_pipeline" not in summary_payload
        assert "muscle_activation_diagnosis" not in summary_payload
        assert "measurement_form" not in summary_payload


def test_initial_package_keeps_an_approved_catalog_and_serves_the_survey_selection(monkeypatch):
    expected = ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]
    assert [task["id"] for task in server.ASSESSMENT_PACKAGES["initial"]["tasks"]] == expected

    async def user_from_header(_headers):
        return {
            "id": "u_ready",
            "consent": {"health_data_consent": True},
            "profile": {
                "sitting_ability": "independent",
                "affected_arm_movement": "some_movement",
                "affected_hand_movement": "some_finger_movement",
                "mobility_level": "walker",
                "movement_pain": "mild",
                "instruction_support": "independent",
            },
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    with TestClient(server.app) as client:
        response = client.get("/api/assessment/tasks?package=initial", headers={"X-User-Id": "u_ready"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["package_id"] == "initial"
        assert [task["id"] for task in payload["tasks"]] == expected
        assert all(step.get("voice") and step.get("target") for task in payload["tasks"] for step in task["steps"])


def test_completed_initial_assessment_is_saved_in_account_history():
    with TestClient(server.app) as client:
        login = client.post(
            "/api/users/login",
            json={
                "email": f"history-{uuid.uuid4().hex}@example.com",
                "name": "History Patient",
                "role": "patient",
            },
        )
        assert login.status_code == 200
        headers = {"X-User-Id": login.json()["id"]}
        consent = client.post(
            "/api/users/consent",
            headers=headers,
            json={"terms_version": server.CURRENT_TERMS_VERSION, "terms_accepted": True, "health_data_consent": True},
        )
        assert consent.status_code == 200
        onboarding = client.post(
            "/api/users/onboarding",
            headers=headers,
            json={
                "sitting_ability": "independent",
                "affected_arm_movement": "some_movement",
                "affected_hand_movement": "some_finger_movement",
                "mobility_level": "walker",
                "movement_pain": "mild",
                "instruction_support": "independent",
            },
        )
        assert onboarding.status_code == 200
        task_results = []
        for task in server.ASSESSMENT_PACKAGES["initial"]["tasks"]:
            total_steps = len(task["steps"])
            task_results.append({
                "task_id": task["id"],
                "completed_steps": total_steps,
                "total_steps": total_steps,
                "duration_ms": 10000,
                "steps": [],
                "metrics": {},
            })
        submitted = client.post(
            "/api/assessment/submit",
            headers=headers,
            json={
                "assessment_package": "initial",
                "assigned_task_ids": [task["id"] for task in server.ASSESSMENT_PACKAGES["initial"]["tasks"]],
                "affected_side": "right",
                "task_results": task_results,
            },
        )
        assert submitted.status_code == 200
        assessment_id = submitted.json()["id"]

        history = client.get("/api/assessment/history", headers=headers)
        assert history.status_code == 200
        records = history.json()
        assert records[0]["id"] == assessment_id
        assert records[0]["assessment_package"] == "initial"


def test_completed_initial_collection_returns_domain_metrics_without_a_normal_rehab_plan(monkeypatch):
    task_ids = ["T1", "T2", "T3", "H1", "H3", "H4", "L6"]

    async def user_from_header(_headers):
        return {
            "id": "u_initial_collection",
            "consent": {"health_data_consent": True},
            "credits": 1000,
            "profile": {
                "sitting_ability": "independent",
                "affected_arm_movement": "some_movement",
                "affected_hand_movement": "some_finger_movement",
                "mobility_level": "walker",
                "movement_pain": "mild",
                "instruction_support": "independent",
            },
        }

    async def consume(_user_id, _kind):
        return 1000

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "consume_credits", consume)
    with TestClient(server.app) as client:
        submitted = client.post(
            "/api/assessment/submit",
            headers={"X-User-Id": "u_initial_collection"},
            json={
                "assessment_package": "initial",
                "assigned_task_ids": task_ids,
                "affected_side": "right",
                "task_results": [
                    {
                        "task_id": task_id,
                        "completed_steps": 1,
                        "total_steps": 1,
                        "duration_ms": 10000,
                        "steps": [],
                        "metrics": {},
                    }
                    for task_id in task_ids
                ],
            },
        )
        assert submitted.status_code == 200
        assessment = submitted.json()
        assert assessment["rehab_plan"] == []
        assert assessment["clinical_review_gate"]["status"] == "awaiting_model_analysis"
        assert assessment["body_function_summary"]["overall_status"] == "analysis_pending"

        summary = client.get(f"/api/assessment/{assessment['id']}/patient-summary").json()
        assert [item["domain"] for item in summary["body_function_summary"]["domains"]] == [
            "upper_limb", "hand", "lower_limb"
        ]
        assert all(item["step_completion_percent"] == 100 for item in summary["body_function_summary"]["domains"])
        assert summary["rehab_plan_ready"] is False


def test_screened_initial_collection_does_not_report_unassigned_walking(monkeypatch):
    task_ids = ["T1", "T2", "T3", "H1", "H3", "H4"]

    async def user_from_header(_headers):
        return {
            "id": "u_screened_initial",
            "consent": {"health_data_consent": True},
            "credits": 1000,
            "profile": {
                "sitting_ability": "independent",
                "affected_arm_movement": "some_movement",
                "affected_hand_movement": "some_finger_movement",
                "mobility_level": "person_assist",
                "movement_pain": "mild",
                "instruction_support": "independent",
                "has_caregiver": True,
            },
        }

    async def consume(_user_id, _kind):
        return 1000

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "consume_credits", consume)
    with TestClient(server.app) as client:
        submitted = client.post(
            "/api/assessment/submit",
            headers={"X-User-Id": "u_screened_initial"},
            json={
                "assessment_package": "initial",
                "assigned_task_ids": task_ids,
                "affected_side": "right",
                "task_results": [
                    {
                        "task_id": task_id,
                        "completed_steps": 1,
                        "total_steps": 1,
                        "duration_ms": 10000,
                        "steps": [],
                        "metrics": {},
                    }
                    for task_id in task_ids
                ],
            },
        )

        assert submitted.status_code == 200
        assessment = submitted.json()
        assert assessment["assigned_task_ids"] == task_ids
        assert [item["domain"] for item in assessment["body_function_summary"]["domains"]] == ["upper_limb", "hand"]
        summary = client.get(f"/api/assessment/{assessment['id']}/patient-summary").json()
        assert summary["collection"]["tasks_expected"] == 6
        assert all(item["domain"] != "lower_limb" for item in summary["body_function_summary"]["domains"])


def test_initial_runner_switches_models_by_task_and_captures_2d_and_3d_trajectories():
    source = server.POSE_RUNNER_HTML
    assert 'function taskDomain(task=tasks[currentTaskIdx])' in source
    assert 'function isHandTask()' in source
    assert 'if(needsHandLandmarks() && !handLandmarker)' in source
    assert 'latestPoseWorldLandmarks = result.worldLandmarks' in source
    assert 'pose_world_3d: poseWorld3d' in source
    assert 'assessment_package: ASSESSMENT_PACKAGE' in source
    assert 'coordinate_space' in source
    assert 'if(which === "WALK_ACROSS")' in source


def test_trusted_model_result_endpoint_rejects_proxies_and_stores_validated_outputs(monkeypatch):
    assessment_id = "model-contract-test"
    server.LOCAL_ASSESSMENTS.append({
        "id": assessment_id,
        "created_at": "2026-08-27T00:00:00+00:00",
        "affected_side": "right",
        "assessment_package": "initial",
        "task_results": [{
            "task_id": "T1", "completed_steps": 1, "total_steps": 1,
            "duration_ms": 1000, "steps": [], "metrics": {},
        }],
        "functional_issues": [],
        "rehab_plan": [],
        "patient_parameters": {"height_cm": 170, "mass_kg": 70},
        "model_analysis": {"status": "queued", "tasks": [{"task_id": "T1", "video_id": "video-t1"}]},
        "motion_data": {"frames": []},
    })
    monkeypatch.setattr(server, "ANALYSIS_WORKER_TOKEN", "test-worker-token")
    payload = {
        "status": "completed",
        "per_task": [{
            "task_id": "T1",
            "quality": {
                "kinematics_valid": True,
                "model_scaled": True,
                "external_loads_valid": True,
                "residuals_within_threshold": True,
            },
            "external_load_method": "gravity_only_seated_no_external_object",
            "muscle_activations": {"anterior_deltoid": {"mean": 0.3, "peak": 0.6}},
            "muscle_forces_n": {"anterior_deltoid": 110.0},
            "joint_moments_nm": {"shoulder_flexion": 18.0},
            "functional_findings": [{"code": "UL_REVIEW", "label": "Shoulder pattern for review"}],
            "provenance": {
                "solver": "OpenSim MocoInverse",
                "model_version": "upper-extremity-1.0",
                "source_video_id": "video-t1",
                "code_version": "abc123",
            },
        }],
    }
    try:
        with TestClient(server.app) as client:
            unauthorized = client.post(f"/api/assessment/{assessment_id}/model-results", json=payload)
            assert unauthorized.status_code == 401
            accepted = client.post(
                f"/api/assessment/{assessment_id}/model-results",
                json=payload,
                headers={"X-Analysis-Worker-Token": "test-worker-token"},
            )
            assert accepted.status_code == 200
            assert accepted.json()["tasks_modeled"] == 1
        stored = next(item for item in server.LOCAL_ASSESSMENTS if item.get("id") == assessment_id)
        assert stored["muscle_activation_diagnosis"]["status"] == "model_complete"
        assert stored["muscle_activation_diagnosis"]["findings"][0]["provenance"] == "validated_musculoskeletal_model"
    finally:
        server.LOCAL_ASSESSMENTS[:] = [
            item for item in server.LOCAL_ASSESSMENTS if item.get("id") != assessment_id
        ]


def test_research_moco_result_builds_insights_without_unlocking_plan(monkeypatch):
    assessment_id = "research-moco-insights-test"
    server.LOCAL_ASSESSMENTS.append({
        "id": assessment_id,
        "created_at": "2026-08-27T00:00:00+00:00",
        "affected_side": "right",
        "assessment_package": "initial",
        "task_results": [{
            "task_id": "L6", "completed_steps": 1, "total_steps": 1,
            "duration_ms": 6000, "steps": [], "metrics": {},
        }],
        "functional_issues": [],
        "rehab_plan": [],
        "body_function_summary": {
            "domains": [{
                "domain": "lower_limb", "label": "Lower limb", "step_completion_percent": 100,
                "findings_count": 0, "status": "analysis_pending",
            }],
        },
        "clinical_review_gate": {"status": "awaiting_model_analysis", "rehab_access": "blocked"},
        "model_analysis": {"status": "queued", "tasks": [{"task_id": "L6", "video_id": "video-l6"}]},
    })
    monkeypatch.setattr(server, "ANALYSIS_WORKER_TOKEN", "test-worker-token")
    payload = {
        "status": "completed",
        "per_task": [{
            "task_id": "L6",
            "domain": "lower_limb",
            "quality": {
                "kinematics_valid": True, "model_scaled": False,
                "external_loads_valid": False, "residuals_within_threshold": False,
            },
            "muscle_activations": {
                "hamstrings": {"mean": 0.18, "peak": 0.41, "template_mean": 0.22, "delta_mean": -0.04},
            },
            "provenance": {
                "solver": "OpenSim Moco patient-informed gait comparison",
                "model_version": "opensim-moco-2d-gait-video-informed",
                "source_video_id": "video-l6",
                "code_version": "worker-test",
            },
        }],
        "kinematics": {"patient_knee_excursion_deg": 18.0, "template_knee_excursion_deg": 31.0},
        "reporting_boundary": "Research estimate only.",
    }
    try:
        with TestClient(server.app) as client:
            response = client.post(
                f"/api/assessment/{assessment_id}/model-stage-results",
                json=payload,
                headers={"X-Analysis-Worker-Token": "test-worker-token"},
            )
            assert response.status_code == 200
            assert response.json()["insights_ready"] is True
            assert response.json()["rehab_plan_unlocked"] is False
            summary = client.get(f"/api/assessment/{assessment_id}/patient-summary").json()
            assert summary["insights"]["status"] == "research_ready"
            assert summary["insights"]["activation_profile"][0]["label"] == "Hamstrings"
            assert summary["rehab_plan_ready"] is False
    finally:
        server.LOCAL_ASSESSMENTS[:] = [
            item for item in server.LOCAL_ASSESSMENTS if item.get("id") != assessment_id
        ]


def test_survey_and_camera_findings_are_reconciled_without_forcing_agreement():
    issues = [
        server.FunctionalIssue(
            code="PINCH_IMPAIRED",
            label="Difficulty forming a thumb-index pinch",
            description="Pinch target was not completed.",
            source="camera",
            severity="moderate",
            related_task="H3",
        ),
        server.FunctionalIssue(
            code="GAIT_PROGRESSION_IMPAIRED",
            label="Difficulty progressing during walking",
            description="Walking sequence was not completed.",
            source="camera",
            severity="severe",
            related_task="L6",
        ),
    ]
    fused = build_survey_consistency(issues, {"affected_areas": ["right_upper"]})
    by_code = {item["issue_code"]: item for item in fused["findings"] if item["issue_code"]}
    assert by_code["PINCH_IMPAIRED"]["status"] == "consistent"
    assert by_code["GAIT_PROGRESSION_IMPAIRED"]["status"] == "discordant"
    assert fused["overall_status"] == "discordant_review_required"
    assert "not forced to agree" in fused["reporting_rule"]


def test_clinical_review_gate_waits_for_model_then_requires_therapist_confirmation():
    completed = [{"task_id": "T1", "completed_steps": 2, "total_steps": 2}]
    no_camera_issues = [server.FunctionalIssue(
        code="NO_ISSUES",
        label="No failed movement steps identified",
        description="All observed steps were completed.",
        source="camera",
        severity="mild",
        related_task="ALL",
    )]
    survey = {"affected_areas": ["right_upper"]}

    pending = build_clinical_review_gate(no_camera_issues, survey, completed, {}, 1)
    assert pending["status"] == "awaiting_model_analysis"
    assert pending["rehab_access"] == "blocked"
    assert pending["objective_evidence"]["validated_model_complete"] is False

    camera_finding = [server.FunctionalIssue(
        code="UL_REACH_LIMITED",
        label="Forward reach needs review",
        description="The camera task identified a limited reach.",
        source="camera",
        severity="moderate",
        related_task="T1",
    )]
    camera_only = build_clinical_review_gate(camera_finding, survey, completed, {}, 1)
    assert camera_only["status"] == "awaiting_model_analysis"
    assert camera_only["rehab_access"] == "blocked"

    validated_normal = {
        "status": "completed",
        "quality": {
            "kinematics_valid": True,
            "model_scaled": True,
            "external_loads_valid": True,
            "residuals_within_threshold": True,
        },
        "functional_findings": [],
    }
    mismatch = build_clinical_review_gate(no_camera_issues, survey, completed, validated_normal, 1)
    assert mismatch["status"] == "therapist_confirmation_required"
    assert mismatch["therapist_confirmation_required"] is True
    assert mismatch["rehab_access"] == "blocked"
    assert "does not mean your symptoms are not real" in mismatch["patient_message"]

    validated_with_finding = {**validated_normal, "functional_findings": [{"code": "UL_REVIEW"}]}
    aligned = build_clinical_review_gate(no_camera_issues, survey, completed, validated_with_finding, 1)
    assert aligned["status"] == "clear"
    assert aligned["rehab_access"] == "allowed"


def test_validated_normal_result_without_reported_symptoms_needs_no_rehab_plan():
    completed = [{"task_id": "T1", "completed_steps": 2, "total_steps": 2}]
    no_camera_issues = [server.FunctionalIssue(
        code="NO_ISSUES",
        label="No failed movement steps identified",
        description="All observed steps were completed.",
        source="camera",
        severity="mild",
        related_task="ALL",
    )]
    validated_normal = {
        "status": "completed",
        "quality": {
            "kinematics_valid": True,
            "model_scaled": True,
            "external_loads_valid": True,
            "residuals_within_threshold": True,
        },
        "functional_findings": [],
    }
    gate = build_clinical_review_gate(no_camera_issues, {}, completed, validated_normal, 1)
    assert gate["status"] == "no_rehab_needed"
    assert gate["rehab_access"] == "not_needed"
    assert "No rehabilitation plan" in gate["patient_title"]


def test_trusted_normal_model_result_removes_automatic_plan_when_survey_reports_symptoms(monkeypatch):
    assessment_id = "survey-objective-hold-test"
    server.LOCAL_ASSESSMENTS.append({
        "id": assessment_id,
        "created_at": "2026-08-27T00:00:00+00:00",
        "affected_side": "right",
        "assessment_package": "test_package",
        "task_results": [{
            "task_id": "T1", "completed_steps": 1, "total_steps": 1,
            "duration_ms": 1000, "steps": [], "metrics": {},
        }],
        "functional_issues": [{
            "code": "NO_ISSUES", "label": "No failed movement steps identified",
            "description": "All observed steps were completed.", "source": "camera",
            "severity": "mild", "related_task": "ALL",
        }],
        "rehab_plan": [{"id": "ex_maintenance"}],
        "patient_parameters": {"affected_areas": ["right_upper"]},
        "model_analysis": {"status": "queued", "tasks": [{"task_id": "T1", "video_id": "video-t1"}]},
        "motion_data": {"frames": []},
    })
    monkeypatch.setattr(server, "ANALYSIS_WORKER_TOKEN", "test-worker-token")
    payload = {
        "status": "completed",
        "per_task": [{
            "task_id": "T1",
            "quality": {
                "kinematics_valid": True, "model_scaled": True,
                "external_loads_valid": True, "residuals_within_threshold": True,
            },
            "external_load_method": "gravity_only_seated_no_external_object",
            "muscle_activations": {"anterior_deltoid": {"mean": 0.3, "peak": 0.6}},
            "functional_findings": [],
            "provenance": {
                "solver": "OpenSim MocoInverse", "model_version": "upper-extremity-1.0",
                "source_video_id": "video-t1", "code_version": "abc123",
            },
        }],
    }
    try:
        with TestClient(server.app) as client:
            accepted = client.post(
                f"/api/assessment/{assessment_id}/model-results",
                json=payload,
                headers={"X-Analysis-Worker-Token": "test-worker-token"},
            )
            assert accepted.status_code == 200
            assert accepted.json()["clinical_review_status"] == "therapist_confirmation_required"
            summary = client.get(f"/api/assessment/{assessment_id}/patient-summary").json()
            assert summary["rehab_plan_ready"] is False
            assert summary["clinical_review_gate"]["rehab_access"] == "blocked"
        stored = next(item for item in server.LOCAL_ASSESSMENTS if item.get("id") == assessment_id)
        assert stored["rehab_plan"] == []
    finally:
        server.LOCAL_ASSESSMENTS[:] = [
            item for item in server.LOCAL_ASSESSMENTS if item.get("id") != assessment_id
        ]


def test_trusted_normal_model_result_marks_rehab_not_needed_without_reported_symptoms(monkeypatch):
    assessment_id = "normal-no-rehab-test"
    server.LOCAL_ASSESSMENTS.append({
        "id": assessment_id,
        "created_at": "2026-08-27T00:00:00+00:00",
        "affected_side": "right",
        "assessment_package": "test_package",
        "task_results": [{
            "task_id": "T1", "completed_steps": 1, "total_steps": 1,
            "duration_ms": 1000, "steps": [], "metrics": {},
        }],
        "functional_issues": [{
            "code": "NO_ISSUES", "label": "No failed movement steps identified",
            "description": "All observed steps were completed.", "source": "camera",
            "severity": "mild", "related_task": "ALL",
        }],
        "rehab_plan": [],
        "patient_parameters": {},
        "model_analysis": {"status": "queued", "tasks": [{"task_id": "T1", "video_id": "video-t1"}]},
        "motion_data": {"frames": []},
    })
    monkeypatch.setattr(server, "ANALYSIS_WORKER_TOKEN", "test-worker-token")
    payload = {
        "status": "completed",
        "per_task": [{
            "task_id": "T1",
            "quality": {
                "kinematics_valid": True, "model_scaled": True,
                "external_loads_valid": True, "residuals_within_threshold": True,
            },
            "external_load_method": "gravity_only_seated_no_external_object",
            "muscle_activations": {"anterior_deltoid": {"mean": 0.3, "peak": 0.6}},
            "functional_findings": [],
            "provenance": {
                "solver": "OpenSim MocoInverse", "model_version": "upper-extremity-1.0",
                "source_video_id": "video-t1", "code_version": "abc123",
            },
        }],
    }
    try:
        with TestClient(server.app) as client:
            accepted = client.post(
                f"/api/assessment/{assessment_id}/model-results",
                json=payload,
                headers={"X-Analysis-Worker-Token": "test-worker-token"},
            )
            assert accepted.status_code == 200
            assert accepted.json()["clinical_review_status"] == "no_rehab_needed"
            summary = client.get(f"/api/assessment/{assessment_id}/patient-summary").json()
            assert summary["rehab_plan_ready"] is False
            assert summary["clinical_review_gate"]["rehab_access"] == "not_needed"
            assert summary["body_function_summary"]["overall_status"] == "no_observable_difficulty"
        stored = next(item for item in server.LOCAL_ASSESSMENTS if item.get("id") == assessment_id)
        assert stored["rehab_plan"] == []
    finally:
        server.LOCAL_ASSESSMENTS[:] = [
            item for item in server.LOCAL_ASSESSMENTS if item.get("id") != assessment_id
        ]


def test_analysis_pipeline_does_not_claim_muscle_activation_without_solver_output():
    motion = {
        "frames": [
            {"task_id": "T1", "pose_2d": [[0.1, 0.2, 0.0, 0.9]], "pose_world_3d": [[0.1, 0.2, -0.1, 0.9]]}
            for _ in range(12)
        ]
    }
    report = build_analysis_pipeline(motion, {})
    stages = {item["id"]: item for item in report["stages"]}
    assert stages["camera_2d"]["status"] == "complete"
    assert stages["camera_3d"]["status"] == "complete"
    assert stages["musculoskeletal_model"]["status"] == "not_run"
    assert stages["muscle_activation"]["status"] == "screening_only"
    assert report["model_outputs"]["activation_available"] is False


def test_analysis_pipeline_accepts_only_quality_validated_solver_activation():
    report = build_analysis_pipeline(
        {},
        {
            "status": "completed",
            "method": "OpenSim Moco",
            "quality": {"kinematics_valid": True},
            "muscle_activations": {"soleus": 0.42},
            "muscle_forces_n": {"soleus": 620},
            "confidence": "model_estimate",
        },
    )
    stages = {item["id"]: item for item in report["stages"]}
    assert stages["musculoskeletal_model"]["status"] == "complete"
    assert stages["muscle_activation"]["status"] == "complete"
    assert report["model_outputs"]["muscle_force_available"] is True


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
    assert "function isLowerTask()" in source
    assert "function isBalanceTask()" in source
    assert 'which === "KNEE_EXTENDED"' in source
    assert 'which === "WEIGHT_SHIFT_AFFECTED"' in source
    assert "toe_clearance_leg_ratio" in source
    assert "finger_total_flexion_deg" in source
    assert "affected_side: AFFECTED_SIDE" in source
