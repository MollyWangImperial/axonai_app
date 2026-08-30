import json
from datetime import datetime, timezone
from pathlib import Path

from backend.alira_action_log import AliraActionLogger


ROOT = Path(__file__).resolve().parents[2]
SERVER = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
TASK_INTRO = (ROOT / "frontend" / "app" / "task-intro.tsx").read_text(encoding="utf-8")
TEXT_CHAT = (ROOT / "frontend" / "app" / "(tabs)" / "chat.tsx").read_text(encoding="utf-8")
VOICE_CALL = (ROOT / "frontend" / "app" / "alira-call.tsx").read_text(encoding="utf-8")


def test_actions_append_to_a_dated_folder_and_flush_each_event(tmp_path):
    logger = AliraActionLogger(tmp_path, timezone_name="Europe/London")
    occurred_at = datetime(2026, 8, 30, 12, 5, tzinfo=timezone.utc)

    first_path = logger.record(
        "assessment_tasks_selected",
        source="assessment_recommendation",
        user_id="patient-123",
        session_id="session-abc",
        details={"task_ids": ["T1", "L6"], "destination": "initial_assessment"},
        occurred_at=occurred_at,
    )
    second_path = logger.record(
        "navigation_executed",
        source="text_chat",
        user_id="patient-123",
        session_id="session-abc",
        details={"destination": "initial_assessment"},
        occurred_at=occurred_at,
    )

    assert first_path == second_path == tmp_path / "2026-08-30" / "alira-actions.jsonl"
    rows = [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()]
    assert [row["action"] for row in rows] == ["assessment_tasks_selected", "navigation_executed"]
    assert rows[0]["details"]["task_ids"] == ["T1", "L6"]
    assert rows[0]["user_ref"].startswith("user_")
    assert rows[0]["session_ref"].startswith("session_")
    assert "patient-123" not in first_path.read_text(encoding="utf-8")


def test_sensitive_fields_are_redacted(tmp_path):
    logger = AliraActionLogger(tmp_path, timezone_name="UTC")
    log_path = logger.record(
        "check_in_recorded",
        source="realtime_voice",
        details={
            "question_ids": ["pain", "fatigue"],
            "answers": {"pain": 8},
            "patient_note": "private health note",
            "nested": {"token": "secret", "destination": "progress"},
        },
        occurred_at=datetime(2026, 8, 30, 12, 5, tzinfo=timezone.utc),
    )

    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["details"]["answers"] == "[redacted]"
    assert event["details"]["patient_note"] == "[redacted]"
    assert event["details"]["nested"]["token"] == "[redacted]"
    assert event["details"]["nested"]["destination"] == "progress"
    assert "private health note" not in log_path.read_text(encoding="utf-8")


def test_alira_actions_and_the_actual_assessment_resume_decision_are_instrumented():
    for action in (
        "assessment_tasks_selected",
        "assessment_resume_selected",
        "guided_assessment_task_completed",
        "survey_questions_selected",
        "check_in_recorded",
        "care_plan_updated",
        "exercise_activity_recorded",
        "chat_response_generated",
        "realtime_call_started",
        "proactive_check_in_selected",
    ):
        assert f'"{action}"' in SERVER
    assert 'authedFetch("/api/alira/assessment-resume-events"' in TASK_INTRO
    assert "completed_task_ids: completedTaskIds" in TASK_INTRO
    assert "next_task_id: nextTask?.id || null" in TASK_INTRO
    assert "progress_source: serverProgressResult.available" in TASK_INTRO
    assert "ignored_device_completed_task_ids" in TASK_INTRO
    assert '"progress_source": payload.progress_source' in SERVER
    assert 'authedFetch("/api/alira/navigation-events"' in TEXT_CHAT
    assert 'authedFetch("/api/alira/navigation-events"' in VOICE_CALL
