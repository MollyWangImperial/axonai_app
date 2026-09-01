import struct
from pathlib import Path

from backend.rehab_games import REHAB_GAME_LIBRARY, game_catalog, rehab_game_html


ROOT = Path(__file__).resolve().parents[2]


def test_game_library_has_three_complete_step_by_step_games():
    assert set(REHAB_GAME_LIBRARY) == {"garden_reach", "lantern_trail", "set_the_table"}
    assert len(REHAB_GAME_LIBRARY["garden_reach"]["targets"]) == 5
    assert len(REHAB_GAME_LIBRARY["lantern_trail"]["targets"]) == 4
    assert len(REHAB_GAME_LIBRARY["set_the_table"]["targets"]) == 4

    for game in REHAB_GAME_LIBRARY.values():
        assert game["setup_voice"]
        assert game["complete_voice"]
        assert game["coaching"]
        assert all(target["voice"] for target in game["targets"])

    assert all(target["place_voice"] for target in REHAB_GAME_LIBRARY["set_the_table"]["targets"])


def test_catalog_exposes_optional_games_without_internal_prompt_data():
    catalog = game_catalog()

    assert [item["id"] for item in catalog] == ["garden_reach", "lantern_trail", "set_the_table"]
    assert all(item["optional"] is True for item in catalog)
    assert all("setup_voice" not in item for item in catalog)


def test_runner_contains_camera_tracking_voice_steps_and_pause_controls():
    html = rehab_game_html("lantern_trail", "difficult")

    assert '"id": "lantern_trail"' in html
    assert '"difficulty": "difficult"' in html
    assert "PoseLandmarker" in html
    assert "/tts/generate" in html
    assert 'voice_id:"nova"' in html
    assert 'id="pauseBtn"' in html
    assert 'id="exitBtn"' in html
    assert 'type:"game_checkpoint"' in html
    assert 'type:"game_complete"' in html
    assert "await announceCurrent()" in html


def test_unknown_runner_inputs_fall_back_to_safe_defaults():
    html = rehab_game_html("unknown", "extreme")

    assert '"id": "garden_reach"' in html
    assert '"difficulty": "medium"' in html


def test_generated_game_scenes_are_full_resolution_png_assets():
    assets = ROOT / "frontend" / "public" / "game-assets"
    for filename in ("garden-reach.png", "lantern-trail.png", "set-the-table.png"):
        path = assets / filename
        data = path.read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (1536, 1024)
        assert len(data) > 250_000


def test_my_time_hosts_games_and_gates_them_by_movement_focus():
    plan_source = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    my_time_source = (ROOT / "frontend" / "app" / "(tabs)" / "my-time.tsx").read_text(encoding="utf-8")
    game_route = (ROOT / "frontend" / "app" / "rehab-game.tsx").read_text(encoding="utf-8")
    server_source = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")

    assert 'testID="rehab-games-section"' not in plan_source
    assert my_time_source.index('testID="my-time-song-card"') < my_time_source.index('testID="rehab-games-section"')
    assert 'game.requires === "hand" ? gameContext.hand : gameContext.upperLimb' in my_time_source
    assert "Not in current plan" in my_time_source
    assert 'pathname: "/rehab-game"' in my_time_source
    assert "Returning to My Time" in game_route
    assert 'rehab_game_progress_v1:' in game_route
    assert 'activity_type: "rehab_game"' in game_route
    assert '@api_router.get("/rehab/games")' in server_source
    assert '@api_router.get("/rehab/game-runner", response_class=HTMLResponse)' in server_source
