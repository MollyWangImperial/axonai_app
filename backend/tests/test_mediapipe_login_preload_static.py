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
    assert 'const CACHE_NAME = "rehyn-shell-__BUILD_ID__"' in service_worker
    assert "MODEL_FILES" in service_worker
    assert "Promise.allSettled(MODEL_FILES.map" in service_worker
    assert 'cache: "no-store"' in service_worker
    assert "client.navigate" not in service_worker


def test_hosted_web_forces_fresh_app_shell_and_service_worker():
    deploy_server = (ROOT / "backend" / "deploy_server.py").read_text(encoding="utf-8")
    pwa_injector = (ROOT / "frontend" / "scripts" / "inject-pwa.js").read_text(encoding="utf-8")

    assert '"Cache-Control": "no-store, max-age=0, must-revalidate"' in deploy_server
    assert '"Cache-Control": "no-cache, no-store, max-age=0, must-revalidate"' in deploy_server
    assert 'full_path == "sw.js"' in deploy_server
    assert 'full_path.startswith("_expo/static/")' in deploy_server
    assert 'updateViaCache: "none"' in pwa_injector
    assert "await registration.update();" in pwa_injector
    assert 'html.match(/entry-([a-f0-9]+)\\.js/)' in pwa_injector
    assert 'serviceWorker.replace("rehyn-shell-__BUILD_ID__"' in pwa_injector
    assert 'navigator.serviceWorker.addEventListener("controllerchange"' in pwa_injector
    assert "window.location.reload();" in pwa_injector


def test_ios_pwa_reserves_the_status_bar_safe_area():
    html = (ROOT / "frontend" / "app" / "+html.tsx").read_text(encoding="utf-8")
    pwa_injector = (ROOT / "frontend" / "scripts" / "inject-pwa.js").read_text(encoding="utf-8")

    expected = 'name="apple-mobile-web-app-status-bar-style" content="default"'
    assert expected in html
    assert expected in pwa_injector


def test_patient_exit_actions_restore_existing_screens_without_replacing_them():
    results = (ROOT / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")
    movement_map = (ROOT / "frontend" / "app" / "movement-map.tsx").read_text(encoding="utf-8")
    progress = (ROOT / "frontend" / "app" / "progress.tsx").read_text(encoding="utf-8")
    rehab_plan = (ROOT / "frontend" / "app" / "rehab-plan.tsx").read_text(encoding="utf-8")
    function_summary = (ROOT / "frontend" / "app" / "function-summary.tsx").read_text(encoding="utf-8")

    assert 'router.dismissTo("/")' in results
    assert 'router.dismissTo("/")' in movement_map
    assert 'router.dismissTo("/")' in progress
    assert 'router.dismissTo("/")' in rehab_plan
    assert 'router.dismissTo("/(tabs)/journey")' in function_summary
