import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER_SOURCE = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
PREPARED_DIR = ROOT / "frontend" / "public" / "audio" / "prepared"
PRELOAD_SOURCE = (ROOT / "frontend" / "src" / "assessmentPreload.ts").read_text(encoding="utf-8")
SERVICE_WORKER_SOURCE = (ROOT / "frontend" / "public" / "sw.js").read_text(encoding="utf-8")


def test_cylindrical_grasp_fixed_prompts_are_prepared_audio_assets():
    manifest = json.loads((PREPARED_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["exercise_id"] == "ex_grasp"
    assert manifest["model"] == "tts-1"
    assert manifest["voice"] == "nova"
    assert len(manifest["assets"]) >= 18
    assert all((PREPARED_DIR / f'{asset["key"]}.mp3').stat().st_size > 1000 for asset in manifest["assets"])
    assert all(asset["url"].startswith("/audio/prepared/") for asset in manifest["assets"])


def test_runner_prefers_prepared_audio_and_initializes_pose_and_hand_together():
    assert 'FRONTEND_PUBLIC_DIR if FRONTEND_PUBLIC_DIR.is_dir() else FRONTEND_ROOT_DIR / "dist"' in SERVER_SOURCE
    assert 'cfg["prepared_voice_assets"]' in SERVER_SOURCE
    assert 'const preparedUrl = CFG.prepared_voice_assets && CFG.prepared_voice_assets[text];' in SERVER_SOURCE
    assert 'fetch(preparedUrl,{cache:"force-cache"})' in SERVER_SOURCE
    assert '[landmarker,handLandmarker]=await Promise.all([posePromise,handPromise]);' in SERVER_SOURCE
    assert 'response.headers["Cache-Control"] = "public, max-age=31536000, immutable"' in SERVER_SOURCE


def test_app_install_and_signed_in_preload_include_models_and_prepared_voice():
    assert 'const PREPARED_VOICE_MANIFEST = "/audio/prepared/manifest.json";' in SERVICE_WORKER_SOURCE
    assert "await cachePreparedVoice(cache);" in SERVICE_WORKER_SOURCE
    assert 'import { API_BASE } from "@/src/config";' in PRELOAD_SOURCE
    assert 'assetUrl("/audio/prepared/manifest.json")' in PRELOAD_SOURCE
    assert "await response.arrayBuffer();" in PRELOAD_SOURCE
