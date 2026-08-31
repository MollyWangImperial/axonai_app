import os

from fastapi.testclient import TestClient


os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_alira_care_api_test")

from backend import server


def signed_in_user(consented: bool = True):
    return {
        "id": "u_alira_care",
        "name": "Care Test",
        "profile": {"months_since_stroke": 6, "affected_areas": ["right_upper"]},
        "consent": {"health_data_consent": consented},
    }


def readiness_user(**overrides):
    user = signed_in_user()
    user["profile"] = {
        "months_since_stroke": 6,
        "affected_areas": ["right_upper", "right_lower"],
        "sitting_ability": "independent",
        "affected_arm_movement": "some_movement",
        "affected_hand_movement": "some_finger_movement",
        "mobility_level": "not_cleared",
        "movement_pain": "mild",
        "instruction_support": "independent",
        "has_caregiver": True,
        **overrides,
    }
    return user


def sample_plan():
    return {
        "version": "alira-care-v2",
        "stage": "active",
        "survey": {"due": True, "questions": [{"id": "function_change"}]},
        "assessment": {"due": False, "packages": []},
        "exercise_plan": {"action": "maintain"},
        "safety": {"status": "clear", "blocks_exercise": False},
        "daily_monitoring": {"next_day_action": "none"},
        "next_step": {
            "action": "continue_exercises",
            "title": "Continue today's exercise plan",
            "message": "Complete 1 remaining exercise in this round.",
            "secondary_action": {
                "action": "recovery_check_in",
                "title": "Short recovery check-in also due",
            },
        },
    }


def test_care_plan_endpoint_is_authenticated_and_returns_json_contract(monkeypatch):
    async def user_from_header(_headers):
        return signed_in_user()

    async def plan_for_user(_user):
        return sample_plan()

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_adaptive_care_plan_for_user", plan_for_user)
    response = TestClient(server.app).get("/api/alira/care-plan", headers={"X-User-Id": "u_alira_care"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["survey"]["questions"][0]["id"] == "function_change"


def test_care_plan_requires_health_data_consent(monkeypatch):
    async def user_from_header(_headers):
        return signed_in_user(consented=False)

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    response = TestClient(server.app).get("/api/alira/care-plan", headers={"X-User-Id": "u_alira_care"})

    assert response.status_code == 403
    assert "consent" in response.json()["detail"].lower()


def test_proactive_alira_message_uses_next_step_instead_of_generic_daily_check_in(monkeypatch):
    async def user_from_header(_headers):
        return signed_in_user()

    async def plan_for_user(_user):
        return sample_plan()

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_adaptive_care_plan_for_user", plan_for_user)
    response = TestClient(server.app).post(
        "/api/chat/proactive",
        headers={"X-User-Id": "u_alira_care"},
        json={"session_id": "next-step-test", "text": ""},
    )

    assert response.status_code == 200
    assert "Continue today's exercise plan" in response.json()["text"]
    assert "does not replace today's exercises" in response.json()["text"]
    assert "How are you feeling today" not in response.json()["text"]


def test_initial_recommendation_uses_saved_capabilities(monkeypatch):
    async def user_from_header(_headers):
        return readiness_user()

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    response = TestClient(server.app).get(
        "/api/assessment/recommendation?package=initial",
        headers={"X-User-Id": "u_alira_care"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert "L6" not in response.json()["task_ids"]


def test_initial_task_endpoint_rejects_client_override(monkeypatch):
    async def user_from_header(_headers):
        return readiness_user()

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    client = TestClient(server.app)
    approved = client.get(
        "/api/assessment/tasks?package=initial&task_ids=T1,T2,T3,H1,H3,H4",
        headers={"X-User-Id": "u_alira_care"},
    )
    override = client.get(
        "/api/assessment/tasks?package=initial&task_ids=T1,T2,T3,H1,H3,H4,L6",
        headers={"X-User-Id": "u_alira_care"},
    )

    assert approved.status_code == 200
    assert approved.json()["assigned_task_ids"] == ["T1", "T2", "T3", "H1", "H3", "H4"]
    assert override.status_code == 422
    assert "saved readiness survey" in override.json()["detail"]


def test_check_in_endpoint_preserves_patient_answer_source(monkeypatch):
    captured = {}

    async def user_from_header(_headers):
        return signed_in_user()

    async def persist(_user, payload):
        captured.update(payload.model_dump())
        return {"ok": True, "check_in": {"answers": payload.answers}, "care_plan": sample_plan()}

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_persist_alira_check_in", persist)
    response = TestClient(server.app).post(
        "/api/alira/check-ins",
        headers={"X-User-Id": "u_alira_care"},
        json={
            "answers": {"sudden_change": "no", "function_change": "a_little_easier"},
            "patient_note": "Reaching felt easier today.",
            "source": "realtime_voice",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["source"] == "realtime_voice"
    assert captured["answers"]["function_change"] == "a_little_easier"


def _camera_impossible_user():
    user = signed_in_user()
    user["profile"] = {
        "months_since_stroke": 6,
        "affected_areas": ["right_upper"],
        "side_affected": "right",
        "sitting_ability": "unable",
        "affected_arm_movement": "no_movement",
        "affected_hand_movement": "no_movement",
        "mobility_level": "not_cleared",
        "movement_pain": "mild",
        "instruction_support": "independent",
        "has_caregiver": "yes",
    }
    return user


def test_survey_report_is_built_from_the_survey_alone_when_no_tasks_exist(monkeypatch):
    async def user_from_header(_headers):
        return _camera_impossible_user()

    async def empty(_user_id):
        return []

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", empty)
    monkeypatch.setattr(server, "_care_check_ins_for_user", empty)
    monkeypatch.setattr(server, "_care_activities_for_user", empty)
    monkeypatch.setattr(server, "_care_issue_reports_for_user", empty)
    response = TestClient(server.app).get(
        "/api/assessment/survey-report",
        headers={"X-User-Id": "u_alira_care"},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["source"] == "survey_only"
    assert report["pages"] == ["daily_activities", "functional_problems", "rehab_plan"]
    # Page 1: survey-only scores are estimates or honestly not assessed.
    statuses = {item["status"] for item in report["daily_activities"]["activities"]}
    assert statuses <= {"estimated", "not_assessed"}
    # Page 2: every domain is pinned on the anatomy map.
    assert {pin["domain"] for pin in report["functional_problems"]["pins"]} == {"upper_limb", "hand", "lower_limb"}
    # Page 3: the rehab plan is the caregiver-delivered programme.
    assert report["rehab_plan"]["type"] == "caregiver_delivered"
    assert report["rehab_plan"]["caregiver_plan"]["programmes"]
    assert report["next_step_after_viewing"] == "rehab_plan"


def test_viewing_the_survey_report_moves_the_next_step_on_to_the_rehab_plan(monkeypatch):
    stored = {}
    user = _camera_impossible_user()

    async def user_from_header(_headers):
        merged = dict(user)
        merged.update(stored)
        return merged

    async def empty(_user_id):
        return []

    class FailingUsers:
        async def update_one(self, *_args, **_kwargs):
            raise RuntimeError("mongo down")

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", empty)
    monkeypatch.setattr(server, "_care_check_ins_for_user", empty)
    monkeypatch.setattr(server, "_care_activities_for_user", empty)
    monkeypatch.setattr(server, "_care_issue_reports_for_user", empty)
    monkeypatch.setattr(server.db, "users", FailingUsers())
    client = TestClient(server.app)

    before = client.get("/api/alira/care-plan", headers={"X-User-Id": "u_alira_care"}).json()
    assert before["next_step"]["action"] == "view_survey_report"

    viewed = client.post("/api/alira/survey-report-viewed", headers={"X-User-Id": "u_alira_care"})
    assert viewed.status_code == 200
    stored["survey_report_viewed_at"] = viewed.json()["viewed_at"]

    after = client.get("/api/alira/care-plan", headers={"X-User-Id": "u_alira_care"}).json()
    assert after["next_step"]["action"] == "caregiver_exercises"
    assert after["next_step"]["destination"] == "caregiver_plan"


def test_caregiver_routine_activity_is_accepted_without_an_assessment(monkeypatch):
    async def user_from_header(_headers):
        user = signed_in_user()
        user["profile"] = {
            "months_since_stroke": 6,
            "affected_areas": ["right_upper"],
            "sitting_ability": "unable",
            "affected_arm_movement": "no_movement",
            "affected_hand_movement": "no_movement",
            "mobility_level": "not_cleared",
            "movement_pain": "mild",
            "instruction_support": "independent",
            "has_caregiver": "yes",
        }
        return user

    async def empty(_user_id):
        return []

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", empty)
    monkeypatch.setattr(server, "_care_check_ins_for_user", empty)
    monkeypatch.setattr(server, "_care_activities_for_user", empty)
    monkeypatch.setattr(server, "_care_issue_reports_for_user", empty)
    client = TestClient(server.app)
    accepted = client.post(
        "/api/alira/activities",
        headers={"X-User-Id": "u_alira_care"},
        json={"exercise_id": "CG_UPPER_LIMB", "plan_id": "caregiver", "completed_reps": 1, "observed_response": "flicker"},
    )
    rejected = client.post(
        "/api/alira/activities",
        headers={"X-User-Id": "u_alira_care"},
        json={"exercise_id": "EX_NOT_APPROVED", "plan_id": "caregiver", "completed_reps": 1},
    )

    assert accepted.status_code == 200
    assert accepted.json()["activity"]["observed_response"] == "flicker"
    assert rejected.status_code == 409


def test_completed_exercise_activity_is_an_authenticated_care_event(monkeypatch):
    captured = {}

    async def user_from_header(_headers):
        return signed_in_user()

    async def persist(_user, payload):
        captured.update(payload.model_dump())
        return {
            "ok": True,
            "activity": {"id": "aca_test", **payload.model_dump()},
            "care_plan": sample_plan(),
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_persist_alira_activity", persist)
    response = TestClient(server.app).post(
        "/api/alira/activities",
        headers={"X-User-Id": "u_alira_care"},
        json={
            "exercise_id": "ex_reach",
            "plan_id": "assessment-1",
            "completed_reps": 6,
            "average_score": 82,
            "completed_at": "2026-08-29T12:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["activity"]["id"] == "aca_test"
    assert captured["completed_reps"] == 6


def test_follow_up_assessment_is_locked_until_current_care_plan_is_due(monkeypatch):
    async def user_from_header(_headers):
        return readiness_user()

    async def assessments(_user_id):
        return [{"id": "a1", "created_at": "2026-08-29T12:00:00+00:00"}]

    async def plan_for_user(_user, **_kwargs):
        return {
            "assessment": {
                "due": False,
                "due_at": "2026-09-26T12:00:00+00:00",
                "can_start": True,
                "packages": [],
                "task_ids": [],
            }
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", assessments)
    monkeypatch.setattr(server, "_adaptive_care_plan_for_user", plan_for_user)
    response = TestClient(server.app).get(
        "/api/assessment/tasks?package=upper_limb&task_ids=T1,T2,T3",
        headers={"X-User-Id": "u_alira_care"},
    )

    assert response.status_code == 409
    assert "not due yet" in response.json()["detail"]
    assert "2026-09-26" in response.json()["detail"]


def test_new_issue_grant_serves_only_alira_selected_package_and_tasks(monkeypatch):
    async def user_from_header(_headers):
        return readiness_user()

    async def assessments(_user_id):
        return [{"id": "a1", "created_at": "2026-08-29T12:00:00+00:00"}]

    async def plan_for_user(_user, **_kwargs):
        return {
            "assessment": {
                "due": True,
                "due_at": "2026-08-30T12:00:00+00:00",
                "can_start": True,
                "trigger": "new_functional_issue",
                "issue_report_id": "afi-hand",
                "packages": ["hand"],
                "task_ids": ["H1", "H3"],
            }
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_care_assessments_for_user", assessments)
    monkeypatch.setattr(server, "_adaptive_care_plan_for_user", plan_for_user)
    client = TestClient(server.app)
    selected = client.get(
        "/api/assessment/tasks?package=hand&task_ids=H1,H3",
        headers={"X-User-Id": "u_alira_care"},
    )
    wrong_package = client.get(
        "/api/assessment/tasks?package=upper_limb&task_ids=T1,T2,T3",
        headers={"X-User-Id": "u_alira_care"},
    )

    assert selected.status_code == 200
    assert selected.json()["assigned_task_ids"] == ["H1", "H3"]
    assert wrong_package.status_code == 422
    assert "selected the hand assessment" in wrong_package.json()["detail"]


def test_functional_issue_endpoint_preserves_patient_report_and_source(monkeypatch):
    captured = {}

    async def user_from_header(_headers):
        return signed_in_user()

    async def persist(_user, payload):
        captured.update(payload.model_dump())
        return {
            "ok": True,
            "is_new": True,
            "message": "Targeted assessment added.",
            "report": {"id": "afi-1", "category": payload.category},
            "care_plan": {"assessment": {"due": True, "packages": ["hand"], "task_ids": ["H1", "H3"]}},
        }

    monkeypatch.setattr(server, "_user_from_header", user_from_header)
    monkeypatch.setattr(server, "_persist_functional_issue_report", persist)
    response = TestClient(server.app).post(
        "/api/alira/functional-issues",
        headers={"X-User-Id": "u_alira_care"},
        json={
            "category": "hand_opening",
            "description": "Opening my hand became difficult this week.",
            "source": "realtime_voice",
        },
    )

    assert response.status_code == 200
    assert response.json()["is_new"] is True
    assert captured["category"] == "hand_opening"
    assert captured["source"] == "realtime_voice"
