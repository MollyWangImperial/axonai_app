import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rehab_plan_uses_targeted_yes_no_session_questions_and_passes_the_result():
    source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "rehab-session-popup" in source
    assert "Switch to a different set of exercises?" in source
    assert "Increase the difficulty for today?" in source
    assert "session-switch-yes" in source
    assert "session-increase-yes" in source
    assert "nextDifficulty(sessionDifficulty)" in source
    assert "session-options" in source
    assert "difficulty: sessionDifficulty" in source
    assert "variation: sessionVariation" in source
    assert "requires_same_support_at_all_levels" in source


def test_exercise_screen_saves_session_average_and_repetition_scores():
    source = (ROOT / "frontend" / "app" / "exercise.tsx").read_text(encoding="utf-8")

    assert "saveSessionAverage" in source
    assert "last_session_scores" in source
    assert "score_history" in source
    assert "repetition_scores: arr" in source
    assert "arr.reduce((a, b) => a + b, 0) / arr.length" in source


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
