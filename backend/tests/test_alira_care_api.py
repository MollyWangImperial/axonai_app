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
