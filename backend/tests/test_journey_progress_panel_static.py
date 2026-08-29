from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOURNEY = (ROOT / "frontend" / "app" / "(tabs)" / "journey.tsx").read_text(encoding="utf-8")
PANEL = (ROOT / "frontend" / "src" / "components" / "JourneyProgressPanel.tsx").read_text(encoding="utf-8")


def test_journey_uses_three_domain_progress_panel():
    assert "<JourneyProgressPanel demoMode={demoMode} />" in JOURNEY
    assert "progressTrack" not in JOURNEY
    assert "progressWidth" not in JOURNEY
    assert "/api/progress/summary" in PANEL
    assert '"Reaching"' in PANEL
    assert '"Hand control"' in PANEL
    assert '"Walking"' in PANEL


def test_progress_panel_has_honest_states_and_shining_endpoints():
    assert "Sample progress" in PANEL
    assert "Complete an assessment to start this trend." in PANEL
    assert "ready for a closer review." in PANEL
    assert "r={17}" in PANEL
    assert "r={12}" in PANEL
    assert 'testID="journey-see-full-progress"' in PANEL
    assert 'router.push("/progress")' in PANEL


def test_progress_panel_is_responsive():
    assert "viewportWidth >= 760" in PANEL
    assert "horizontal" in PANEL
    assert "snapToInterval" in PANEL
    assert "trendPanelWide" in PANEL