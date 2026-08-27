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
