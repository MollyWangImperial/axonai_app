from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_alira_page_uses_an_accessible_dynamic_background():
    chat = (ROOT / "frontend" / "app" / "(tabs)" / "chat.tsx").read_text(encoding="utf-8")
    background = (ROOT / "frontend" / "src" / "components" / "AliraLivingBackground.tsx").read_text(encoding="utf-8")

    assert "<AliraLivingBackground" in chat
    assert "engaged={sending || conversationTurns.length > 0}" in chat
    assert 'testID="alira-living-background"' in background
    assert 'pointerEvents="none"' in background
    assert "AccessibilityInfo.isReduceMotionEnabled" in background
    assert 'AccessibilityInfo.addEventListener("reduceMotionChanged"' in background
    assert "Animated.loop" in background
    assert "breathingLoop.stop()" in background
    assert "driftingLoop.stop()" in background
