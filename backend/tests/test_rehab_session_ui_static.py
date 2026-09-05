import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rehab_plan_skips_patient_session_questions_and_uses_recommended_difficulty():
    source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "rehab-session-popup" not in source
    assert "Switch to a different set of exercises?" not in source
    assert "Increase the difficulty for today?" not in source
    assert "session-switch-yes" not in source
    assert "session-increase-yes" not in source
    assert "session-options" in source
    assert "recommended_difficulty" in source
    assert "isSessionDifficulty(frequencyDifficulty)" in source
    assert "configureSessionPlan(adjustedAssessment, baseDifficulty, loadedSessionOptions)" in source
    assert "difficulty: sessionDifficulty" in source
    assert 'variation: "standard"' in source
    assert "requires_same_support_at_all_levels" in source


def test_rehab_plan_does_not_store_or_reopen_the_removed_patient_choice_window():
    source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "DAILY_SESSION_CHOICE_KEY" not in source
    assert "loadTodaySessionChoice" not in source
    assert "saveTodaySessionChoice" not in source
    assert "sessionConfirmed" not in source
    assert "sessionVariation" not in source
    assert "confirmSessionChoice" not in source


def test_exercise_screen_saves_session_average_and_repetition_scores():
    source = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")

    assert "saveSessionAverage" in source
    assert "last_session_scores" in source
    assert "score_history" in source
    assert "repetition_scores: arr" in source
    assert "arr.reduce((a, b) => a + b, 0) / arr.length" in source


def test_rehab_plan_reuses_one_calibration_for_consecutive_exercises_only():
    plan_source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    exercise_source = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")

    assert "const rehabSessionIdRef = React.useRef(" in plan_source
    assert "rehab_session_id: rehabSessionIdRef.current" in plan_source
    assert "rehab_session_id" in exercise_source
    assert "encodeURIComponent(rehabSessionId)" in exercise_source


def test_settings_exposes_reminder_time_and_fast_quick_access():
    settings = (ROOT / "frontend" / "app" / "(tabs)" / "settings.tsx").read_text(encoding="utf-8")
    notifications = (ROOT / "frontend" / "src" / "utils" / "notifications.ts").read_text(encoding="utf-8")

    assert "settings-reminder-time" in settings
    assert "settings-fast-shortcut" in settings
    assert "FAST quick access" in settings
    assert "setNotificationCategoryAsync" in notifications
    assert 'data: { route: "/emergency" }' in notifications


def test_installed_web_app_has_a_direct_fast_shortcut():
    manifest = json.loads((ROOT / "frontend" / "public" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["shortcuts"][0]["name"] == "Start FAST check"
    assert manifest["shortcuts"][0]["url"].startswith("/emergency")
