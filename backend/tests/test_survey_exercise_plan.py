import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_survey_exercise_plan_test")

from backend import server
from backend.alira_care_orchestrator import classify_functional_rehab_profile


ROOT = Path(__file__).resolve().parents[2]


def survey_profile(**overrides):
    profile = {
        "movement_readiness_version": "survey-exercise-v3",
        "affected_areas": ["right_upper", "right_lower"],
        "sitting_ability": "independent",
        "affected_arm_movement": "some_movement",
        "arm_activity_difficulties": ["none"],
        "affected_hand_movement": "some_finger_movement",
        "hand_activity_difficulties": ["none"],
        "mobility_level": "independent",
        "mobility_activity_difficulties": ["none"],
        "standing_exercise_clearance": "independent",
        "movement_pain": "mild",
        "instruction_support": "independent",
        "has_caregiver": True,
    }
    profile.update(overrides)
    return profile


@pytest.mark.parametrize(
    ("field", "option", "exercise_id"),
    [
        ("arm_activity_difficulties", "reach_forward", "ex_reach"),
        ("arm_activity_difficulties", "raise_arm", "ex_wallslide"),
        ("arm_activity_difficulties", "hand_to_mouth", "ex_h2m"),
        ("arm_activity_difficulties", "trunk_lean", "ex_trunk"),
        ("arm_activity_difficulties", "shoulder_hike", "ex_scapdepress"),
        ("arm_activity_difficulties", "use_both_arms", "ex_bilateral"),
        ("hand_activity_difficulties", "open_release", "ex_handopen"),
        ("hand_activity_difficulties", "grasp_hold", "ex_grasp"),
        ("hand_activity_difficulties", "pinch_small_objects", "ex_pinch"),
        ("mobility_activity_difficulties", "sitting_balance", "ex_sitting_balance"),
        ("mobility_activity_difficulties", "knee_control", "ex_lower_selective"),
        ("mobility_activity_difficulties", "foot_clearance", "ex_ankle_dorsiflexion"),
        ("mobility_activity_difficulties", "sit_to_stand", "ex_sit_to_stand"),
        ("mobility_activity_difficulties", "standing_balance", "ex_supported_stand"),
        ("mobility_activity_difficulties", "weight_affected_leg", "ex_weight_shift"),
        ("mobility_activity_difficulties", "start_step", "ex_supported_step"),
        ("mobility_activity_difficulties", "step_balance", "ex_step_stance"),
    ],
)
def test_each_reported_problem_has_one_direct_exercise_match(field, option, exercise_id):
    plan = server.survey_rehab_plan(survey_profile(**{field: [option]}))

    assert exercise_id in {exercise.id for exercise in plan}
    assert all("survey answers" in (exercise.selection_reason or "") for exercise in plan)


@pytest.mark.parametrize(
    "answers",
    [
        {"arm_activity_difficulties": ["reach_forward"]},
        {"hand_activity_difficulties": ["open_release"]},
        {"mobility_activity_difficulties": ["knee_control"]},
        {
            "arm_activity_difficulties": ["reach_forward", "raise_arm", "hand_to_mouth"],
            "hand_activity_difficulties": ["open_release", "grasp_hold", "pinch_small_objects"],
            "mobility_activity_difficulties": ["knee_control", "foot_clearance", "sit_to_stand"],
        },
    ],
)
def test_safe_reported_difficulties_produce_a_deduplicated_four_or_five_exercise_plan(answers):
    plan = server.survey_rehab_plan(survey_profile(**answers))
    ids = [exercise.id for exercise in plan]

    assert 4 <= len(ids) <= 5
    assert len(ids) == len(set(ids))


def test_compensation_exercises_are_not_used_as_unreported_fillers():
    plan = server.survey_rehab_plan(survey_profile(arm_activity_difficulties=["reach_forward"]))
    ids = {exercise.id for exercise in plan}

    assert "ex_reach" in ids
    assert "ex_trunk" not in ids
    assert "ex_scapdepress" not in ids


def test_survey_sentinels_and_severe_pain_are_not_positive_prescribing_evidence():
    assert server.survey_rehab_plan(survey_profile(
        arm_activity_difficulties=["not_sure"],
        hand_activity_difficulties=["none"],
        mobility_activity_difficulties=["none"],
    )) == []
    assert server.survey_rehab_plan(survey_profile(
        arm_activity_difficulties=["reach_forward"],
        movement_pain="severe_or_worsening",
    )) == []


def test_safety_filter_returns_fewer_than_four_instead_of_padding_with_unsafe_standing_work():
    plan = server.survey_rehab_plan(survey_profile(
        affected_arm_movement="not_affected",
        arm_activity_difficulties=["none"],
        affected_hand_movement="not_affected",
        hand_activity_difficulties=["none"],
        mobility_level="not_cleared",
        mobility_activity_difficulties=["sit_to_stand"],
        standing_exercise_clearance="not_cleared",
        has_caregiver=False,
    ))

    assert len(plan) < 4
    assert not ({exercise.id for exercise in plan} & {
        "ex_sit_to_stand", "ex_supported_stand", "ex_weight_shift", "ex_supported_step", "ex_step_stance",
    })


def test_supervised_mobility_exercises_keep_confirmation_requirement():
    plan = server.survey_rehab_plan(survey_profile(
        mobility_activity_difficulties=["sit_to_stand", "standing_balance"],
    ))
    supervised = [exercise for exercise in plan if exercise.id in {"ex_sit_to_stand", "ex_supported_stand"}]

    assert len(supervised) == 2
    assert all(exercise.requires_clinician_confirmation for exercise in supervised)


def test_assessment_and_model_result_routes_both_use_the_survey_selector():
    source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
    assessment_route = source.split('async def submit_assessment', 1)[1].split('@api_router.get("/assessment/history")', 1)[0]
    model_route = source.split('async def save_model_results', 1)[1].split('@api_router.get("/assessment/{assessment_id}/muscle-diagnosis")', 1)[0]

    assert "plan = survey_rehab_plan(survey_profile)" in assessment_route
    assert "plan = build_rehab_plan(issues, patient_parameters)" not in assessment_route
    assert "plan = survey_rehab_plan(patient_parameters)" in model_route
    assert "plan = build_rehab_plan(issues, patient_parameters)" not in model_route


def test_validated_model_finding_does_not_change_survey_selected_exercise_ids(monkeypatch):
    assessment_id = "survey-plan-model-callback"
    user_id = "u_survey_plan_model_callback"
    patient_parameters = survey_profile(
        arm_activity_difficulties=["none"],
        hand_activity_difficulties=["open_release"],
        mobility_activity_difficulties=["none"],
    )
    expected_ids = [exercise.id for exercise in server.survey_rehab_plan(patient_parameters)]
    server.LOCAL_ASSESSMENTS.append({
        "id": assessment_id,
        "user_id": user_id,
        "created_at": "2026-09-02T00:00:00+00:00",
        "affected_side": "right",
        "assessment_package": "upper_limb",
        "assigned_task_ids": ["T1"],
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
        "patient_parameters": patient_parameters,
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
            "functional_findings": [{
                "code": "SHOULDER_HIKE",
                "label": "Model-estimated shoulder hike",
                "severity": "moderate",
                "related_task": "T1",
            }],
            "provenance": {
                "solver": "OpenSim MocoInverse",
                "model_version": "upper-extremity-1.0",
                "source_video_id": "video-t1",
                "code_version": "abc123",
            },
        }],
    }
    try:
        response = TestClient(server.app).post(
            f"/api/assessment/{assessment_id}/model-results",
            json=payload,
            headers={"X-Analysis-Worker-Token": "test-worker-token"},
        )

        assert response.status_code == 200
        assert response.json()["clinical_review_status"] == "clear"
        stored = next(item for item in server.LOCAL_ASSESSMENTS if item.get("id") == assessment_id)
        actual_ids = [exercise["id"] for exercise in stored["rehab_plan"]]
        assert actual_ids == expected_ids
        assert "ex_scapdepress" not in actual_ids
        assert stored["clinical_review_gate"]["rehab_plan_source"] == "survey_reported_problems"
    finally:
        server.LOCAL_ASSESSMENTS[:] = [
            item for item in server.LOCAL_ASSESSMENTS if item.get("id") != assessment_id
        ]


def test_new_survey_answers_are_declared_and_partial_profile_updates_preserve_them(monkeypatch):
    saved = {}

    class UsersCollection:
        async def update_one(self, query, update):
            saved["query"] = query
            saved["update"] = update

    async def user_from_header(_headers):
        return {
            "id": "u_survey_profile",
            "profile": survey_profile(preferred_name="Before"),
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "db", SimpleNamespace(users=UsersCollection()))
    response = TestClient(server.app).post(
        "/api/users/onboarding",
        headers={"X-User-Id": "u_survey_profile"},
        json={"preferred_name": "After"},
    )

    assert response.status_code == 200
    returned = response.json()["profile"]
    assert returned["preferred_name"] == "After"
    assert returned["movement_readiness_version"] == "survey-exercise-v3"
    assert returned["arm_activity_difficulties"] == ["none"]
    assert returned["hand_activity_difficulties"] == ["none"]
    assert returned["mobility_activity_difficulties"] == ["none"]
    assert saved["update"]["$set"]["profile"] == returned


def test_frontend_asks_only_three_problem_questions_plus_conditional_standing_clearance():
    survey = (ROOT / "frontend" / "src" / "patientSurvey.ts").read_text(encoding="utf-8")
    onboarding = (ROOT / "frontend" / "app" / "onboarding.tsx").read_text(encoding="utf-8")

    for key in (
        "arm_activity_difficulties",
        "hand_activity_difficulties",
        "mobility_activity_difficulties",
        "standing_exercise_clearance",
    ):
        assert f'key: "{key}"' in survey
    assert 'key !== "standing_exercise_clearance"' in onboarding
    assert "STANDING_OR_STEPPING_DIFFICULTIES.has" in onboarding
    assert '["none", "not_sure", "unsure"]' in onboarding


def test_current_survey_requires_problem_answers_and_conditionally_requires_standing_clearance():
    missing_problem_answers = survey_profile()
    missing_problem_answers.pop("arm_activity_difficulties")
    missing_problem_answers.pop("hand_activity_difficulties")
    missing_problem_answers.pop("mobility_activity_difficulties")
    result = classify_functional_rehab_profile(missing_problem_answers)

    assert {
        "arm_activity_difficulties",
        "hand_activity_difficulties",
        "mobility_activity_difficulties",
    } <= set(result["missing_fields"])

    missing_clearance = survey_profile(
        mobility_activity_difficulties=["sit_to_stand"],
        standing_exercise_clearance=None,
    )
    result = classify_functional_rehab_profile(missing_clearance)

    assert "standing_exercise_clearance" in result["missing_fields"]
