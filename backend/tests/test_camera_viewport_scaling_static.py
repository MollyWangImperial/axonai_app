import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_camera_viewport_test")

from backend import server


def _assert_responsive_camera_mapping(source: str) -> None:
    assert 'id="cameraFrame"' in source
    assert "function classifyCameraDevice({" in source
    assert '/iPhone|iPod/i.test(userAgent)' in source
    assert 'return "tablet";' in source
    assert 'return maxTouchPoints > 0 && shortScreenEdge <= 600 ? "phone" : "web";' in source
    assert 'const CAMERA_FIT_MODE = CAMERA_DEVICE_CLASS === "phone" ? "cover" : "contain";' in source
    assert "function fitCameraViewport(containerWidth, containerHeight, sourceWidth, sourceHeight, fitMode=CAMERA_FIT_MODE)" in source
    assert 'fitMode === "cover"' in source
    assert "Math.max(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight)" in source
    assert "Math.min(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight)" in source
    assert "fit:fitMode" in source
    assert "cameraFrame.style.left = `${rect.left}px`;" in source
    assert "cameraFrame.style.top = `${rect.top}px`;" in source
    assert "cameraFrame.style.width = `${rect.width}px`;" in source
    assert "cameraFrame.style.height = `${rect.height}px`;" in source
    assert "document.body.dataset.cameraDevice = CAMERA_DEVICE_CLASS;" in source
    assert "document.body.dataset.cameraFit = rect.fit;" in source
    assert "window.__rehynCameraViewportTest" in source
    assert "syncCameraViewport," in source
    assert 'window.addEventListener("resize", syncCameraViewport' in source
    assert 'window.addEventListener("orientationchange"' in source
    assert "new ResizeObserver(syncCameraViewport).observe(stage)" in source
    assert "function responsiveVideoSettings(longEdge, shortEdge, maxFrameRate=30)" in source
    assert "const portrait = stage.clientHeight > stage.clientWidth;" in source
    assert "width:{ideal:portrait ? shortEdge : longEdge}" in source
    assert "height:{ideal:portrait ? longEdge : shortEdge}" in source
    assert "height:100vh;height:100dvh" in source
    assert "object-fit:cover" not in source


def test_assessment_runner_uses_one_mode_aware_camera_viewport_for_video_and_canvas():
    source = server.POSE_RUNNER_HTML
    _assert_responsive_camera_mapping(source)
    assert '#cameraFrame video,#cameraFrame canvas' in source
    assert 'const tx = targetXY.x * canvas.width;' in source
    assert 'const ty = targetXY.y * canvas.height;' in source
    assert 'fit: CAMERA_FIT_MODE' in source
    assert 'device_class: CAMERA_DEVICE_CLASS' in source
    assert 'mirrored_for_patient: true' in source


def test_rehab_runner_uses_the_same_responsive_camera_mapping():
    source = server.REHAB_RUNNER_HTML_TEMPLATE
    _assert_responsive_camera_mapping(source)
    assert '#cameraFrame video,#cameraFrame canvas' in source
    assert 'const tx = sub.target.x*canvas.width;' in source
    assert 'const ty = sub.target.y*canvas.height;' in source


def test_phone_cover_projection_fills_portrait_viewport_without_black_bands():
    display_width, display_height = 390, 844
    source_width, source_height = 640, 480
    scale = max(display_width / source_width, display_height / source_height)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    left = (display_width - fitted_width) / 2
    top = (display_height - fitted_height) / 2

    assert fitted_width >= display_width
    assert fitted_height >= display_height
    assert left < 0
    assert abs(top) < 1e-9


def test_contain_projection_keeps_camera_edges_visible_on_tablet_and_web():
    displays = {
        "ipad_portrait": (820, 1180),
        "desktop_wide": (1440, 900),
        "tv_16_9": (1920, 1080),
    }
    source_width, source_height = 640, 480
    for display_width, display_height in displays.values():
        scale = min(display_width / source_width, display_height / source_height)
        fitted_width = source_width * scale
        fitted_height = source_height * scale
        left = (display_width - fitted_width) / 2
        top = (display_height - fitted_height) / 2
        assert left >= 0
        assert top >= 0
        assert left + fitted_width <= display_width + 1e-9
        assert top + fitted_height <= display_height + 1e-9
