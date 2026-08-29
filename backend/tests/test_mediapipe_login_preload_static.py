from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_patient_auth_gate_preloads_assessment_models_on_hosted_web():
    layout = (ROOT / "frontend" / "app" / "_layout.tsx").read_text(encoding="utf-8")
    preload = (ROOT / "frontend" / "src" / "assessmentPreload.ts").read_text(encoding="utf-8")

    assert 'import { preloadAssessmentMediaPipe }' in layout
    assert 'if (u.role !== "therapist")' in layout
    assert "void preloadAssessmentMediaPipe();" in layout
    assert 'Platform.OS !== "web"' in preload
    assert 'cache: "force-cache"' in preload
    assert "vision_bundle.mjs" in preload
    assert "vision_wasm_internal.wasm" in preload
    assert "pose_landmarker_lite.task" in preload
    assert "hand_landmarker.task" in preload


def test_mediapipe_assets_are_bundled_and_cached_with_the_pwa():
    package = (ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    downloader = (ROOT / "frontend" / "scripts" / "download-mediapipe-assets.js").read_text(encoding="utf-8")
    service_worker = (ROOT / "frontend" / "public" / "sw.js").read_text(encoding="utf-8")

    assert "download-mediapipe-assets.js" in package
    assert "pose_landmarker_lite.task" in downloader
    assert "hand_landmarker.task" in downloader
    assert "vision_wasm_nosimd_internal.wasm" in downloader
    assert 'const CACHE_NAME = "rehyn-shell-v3"' in service_worker
    assert "MODEL_FILES" in service_worker
    assert "Promise.allSettled(MODEL_FILES.map" in service_worker
    assert 'cache: "no-store"' in service_worker
    assert "staleShellExists" in service_worker


def test_hosted_web_forces_fresh_app_shell_and_service_worker():
    deploy_server = (ROOT / "backend" / "deploy_server.py").read_text(encoding="utf-8")
    pwa_injector = (ROOT / "frontend" / "scripts" / "inject-pwa.js").read_text(encoding="utf-8")

    assert '"Cache-Control": "no-store, max-age=0, must-revalidate"' in deploy_server
    assert '"Cache-Control": "no-cache, no-store, max-age=0, must-revalidate"' in deploy_server
    assert 'full_path == "sw.js"' in deploy_server
    assert 'full_path.startswith("_expo/static/")' in deploy_server
    assert 'updateViaCache: "none"' in pwa_injector
    assert "registration.update();" in pwa_injector
