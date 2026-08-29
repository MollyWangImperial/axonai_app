from pathlib import Path


SERVER = Path(__file__).resolve().parents[1] / "server.py"


def test_palm_facing_is_projection_stable_instead_of_handedness_sign_gated():
    source = SERVER.read_text(encoding="utf-8")
    for marker in (
        "function palmProjectionEvidence(h)",
        "Math.abs(signedPlaneFacing)",
        "projectedAreaRatio",
        "palmSpread",
        "depthFlatness",
        "PALM_FACING_THRESHOLD = 0.38",
    ):
        assert marker in source
    assert "expectedPalmSign" not in source
    assert "signedPalmTowardCamera" not in source


def test_h1_palm_gate_and_coaching_use_the_same_threshold():
    source = SERVER.read_text(encoding="utf-8")
    assert 'palmFacingScore > PALM_FACING_THRESHOLD && handOpenScore < 0.72' in source
    assert 'step.id !== "H1-S2" || palmFacingScore > PALM_FACING_THRESHOLD' in source
    assert source.count("palmFacingScore <= PALM_FACING_THRESHOLD") == 2


def test_palm_projection_has_a_browser_simulation_hook():
    source = SERVER.read_text(encoding="utf-8")
    assert 'URL_PARAMS.get("test_mode") === "palm_projection"' in source
    assert "window.__rehynPalmProjectionTest" in source
    assert "evaluate:(landmarks, frameCount=4)" in source
