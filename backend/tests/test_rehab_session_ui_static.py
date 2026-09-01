import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rehab_plan_requires_a_session_choice_and_passes_it_to_the_runner():
    source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")

    assert "Choose how today should feel" in source
    assert "session-options" in source
    assert "Object.keys(DIFFICULTY_COPY)" in source
    assert "session-difficulty-${level}" in source
    assert 'easy: { label: "Easy"' in source
    assert 'difficult: { label: "Difficult"' in source
    assert "difficulty: sessionDifficulty" in source
    assert "variation: sessionVariation" in source
    assert "requires_same_support_at_all_levels" in source


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
