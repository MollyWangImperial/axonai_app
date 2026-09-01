import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_my_time_is_a_primary_tab_with_playable_content():
    tabs = (ROOT / "frontend" / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
    screen = (ROOT / "frontend" / "app" / "(tabs)" / "my-time.tsx").read_text(encoding="utf-8")

    assert 'name="my-time"' in tabs
    assert 'title: "My Time"' in tabs
    assert "Relax with something you enjoy." in screen
    assert "The Garden by the Sea" in screen
    assert "Name That Song" in screen
    assert "Movement games" in screen
    assert "Garden Reach" in screen
    assert "Lantern Trail" in screen
    assert "Set the Table" in screen
    assert 'testID="rehab-games-section"' in screen
    assert "garden-by-the-sea-narration.mp3" in screen
    assert "useAudioPlayerStatus" in screen
    assert "AUDIOBOOK_POSITION_KEY" in screen


def test_my_time_visual_and_song_assets_are_real_files():
    image_dir = ROOT / "frontend" / "assets" / "images" / "my-time"
    audio_dir = ROOT / "frontend" / "assets" / "audio" / "my-time"

    for filename in ("garden-by-the-sea.png", "name-that-song.png"):
        asset = image_dir / filename
        assert asset.exists()
        assert asset.stat().st_size > 100_000

    for filename in ("twinkle-twinkle.wav", "ode-to-joy.wav", "frere-jacques.wav"):
        asset = audio_dir / filename
        assert asset.exists()
        with wave.open(str(asset), "rb") as clip:
            assert clip.getnchannels() == 1
            assert clip.getframerate() == 22_050
            assert clip.getnframes() > 22_050 * 4

    narration = audio_dir / "garden-by-the-sea-narration.mp3"
    assert narration.exists()
    assert narration.stat().st_size > 500_000
