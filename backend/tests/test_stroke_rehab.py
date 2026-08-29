"""Backend tests for NeuroMotion Stroke Rehab API."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://arm-rehab-ai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---- TTS health diagnostic (new in iter 2) ----
def test_tts_health_reports_scope_missing():
    r = requests.get(f"{API}/tts/health", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "ok" in j
    # If key lacks scope, must explicitly say so with actionable hint
    if not j["ok"]:
        assert j.get("scope_missing") is True, f"expected scope_missing=True, got {j}"
        assert "Text to Speech" in j.get("hint", ""), f"hint missing actionable text: {j}"
        assert "elevenlabs.io" in j.get("hint", "")


# ---- TTS generate now returns 503 (not 500) when scope missing ----
def test_tts_generate_returns_503_when_scope_missing():
    r = requests.post(f"{API}/tts/generate", json={"text": "hello"}, timeout=30)
    # Acceptable: 200 if key works, 503 if scope missing
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}: {r.text[:300]}"
    if r.status_code == 503:
        detail = r.json().get("detail", "")
        assert "Voice service unavailable" in detail, f"detail must mention Voice service unavailable: {detail}"
        assert "text_to_speech" in detail or "ElevenLabs" in detail


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# ---- Tasks ----
def test_get_tasks_returns_7(s):
    r = s.get(f"{API}/assessment/tasks", timeout=20)
    assert r.status_code == 200
    j = r.json()
    assert "tasks" in j and "voice_id" in j
    assert len(j["tasks"]) == 7
    ids = [t["id"] for t in j["tasks"]]
    assert ids == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    for t in j["tasks"]:
        assert t.get("steps") and len(t["steps"]) >= 3
        for st in t["steps"]:
            assert "voice" in st and "target" in st and "hold_ms" in st
            assert {"x", "y", "r", "landmark"} <= set(st["target"].keys())


# ---- Pose runner HTML ----
def test_pose_runner_html(s):
    r = s.get(f"{API}/pose/runner", timeout=20)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    html = r.text
    assert "mediapipe" in html.lower()
    assert "assessment-start" in html  # Start button testID
    assert "getUserMedia" in html


# ---- TTS endpoint (iter 2: 503 with actionable message when scope missing) ----
def test_tts_generate_status(s):
    r = s.post(f"{API}/tts/generate", json={"text": "hello"}, timeout=30)
    assert r.status_code in (200, 503), f"unexpected {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        assert "audio_b64" in r.json()
    else:
        assert "Voice service unavailable" in r.json().get("detail", "")


# ---- Submit assessment ----
def _sample_payload(complete=False):
    """Build sample task_results triggering some issues if complete=False."""
    results = []
    task_specs = [("T1", 3), ("T2", 3), ("T3", 3), ("T4", 3), ("T5", 3), ("T6", 3), ("T7", 3)]
    for tid, n in task_specs:
        results.append({
            "task_id": tid,
            "completed_steps": n if complete else 1,
            "total_steps": n,
            "duration_ms": 4500,
            "steps": [{"step_id": f"{tid}-S{i+1}", "completed": complete or i == 0, "duration_ms": 1500, "metrics": {}} for i in range(n)],
            "metrics": {"trunk_lean_deg": 20} if (tid == "T1" and not complete) else {},
        })
    return {"task_results": results, "affected_side": "right"}


@pytest.fixture(scope="module")
def created_assessment(s):
    r = s.post(f"{API}/assessment/submit", json=_sample_payload(complete=False), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data and "_id" not in data
    assert "functional_issues" in data and len(data["functional_issues"]) > 0
    assert "rehab_plan" in data and len(data["rehab_plan"]) > 0
    # Should detect TRUNK_COMP because trunk_lean_deg=20 > 15
    codes = [i["code"] for i in data["functional_issues"]]
    assert "TRUNK_COMP" in codes
    assert "REACH_INCOMPLETE" in codes  # T1 not fully complete
    return data


def test_submit_returns_issues_and_plan(created_assessment):
    a = created_assessment
    assert a["affected_side"] == "right"
    for ex in a["rehab_plan"]:
        assert {"id", "name", "description", "sets", "reps", "source"} <= set(ex.keys())
    for iss in a["functional_issues"]:
        assert {"code", "label", "source", "severity"} <= set(iss.keys())


def test_get_assessment_by_id(s, created_assessment):
    aid = created_assessment["id"]
    r = s.get(f"{API}/assessment/{aid}", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == aid
    assert "_id" not in data


def test_get_assessment_404(s):
    r = s.get(f"{API}/assessment/nonexistent-id-xyz", timeout=20)
    assert r.status_code == 404


def test_history_returns_list_no_id_leak(s, created_assessment):
    r = s.get(f"{API}/assessment/history", timeout=20)
    assert r.status_code == 200
    arr = r.json()
    assert isinstance(arr, list) and len(arr) >= 1
    for item in arr:
        assert "_id" not in item
        assert "id" in item
    assert any(a["id"] == created_assessment["id"] for a in arr)


# ---- Rehab Runner (iter 3) ----
def test_rehab_runner_body_mode_ex_reach(s):
    r = s.get(f"{API}/rehab/runner", params={"exercise_id": "ex_reach"}, timeout=20)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    html = r.text
    # CFG should be injected with name, reps, cycle, feedback_rules
    assert "Graded Forward Reach" in html
    assert '"reps": 5' in html or '"reps":5' in html
    assert "feedback_rules" in html
    assert '"pose_mode": "body"' in html or '"pose_mode":"body"' in html
    assert "cycle" in html
    # Speech recognition logic + key phrase
    assert "SpeechRecognition" in html or "webkitSpeechRecognition" in html
    assert "I understand my problem now" in html
    # testIDs present
    assert "rehab-start" in html
    assert "rehab-exit" in html


def test_rehab_runner_tap_mode_ex_handopen(s):
    r = s.get(f"{API}/rehab/runner", params={"exercise_id": "ex_handopen"}, timeout=20)
    assert r.status_code == 200
    html = r.text
    assert "Finger Extension with Rubber Band" in html
    assert '"pose_mode": "tap"' in html or '"pose_mode":"tap"' in html
    assert "rehab-tap-rep" in html
    assert "I understand my problem now" in html


def test_rehab_runner_unknown_falls_back_to_maintenance(s):
    r = s.get(f"{API}/rehab/runner", params={"exercise_id": "bogus_nope_xyz"}, timeout=20)
    assert r.status_code == 200, f"must not 500, got {r.status_code}: {r.text[:200]}"
    html = r.text
    # Falls back to ex_maintenance config
    assert "Maintenance Conditioning" in html
    assert "feedback_rules" in html


def test_rehab_runner_default_is_maintenance(s):
    r = s.get(f"{API}/rehab/runner", timeout=20)
    assert r.status_code == 200
    assert "Maintenance Conditioning" in r.text


def test_rehab_runner_pinch_tap_mode(s):
    r = s.get(f"{API}/rehab/runner", params={"exercise_id": "ex_pinch"}, timeout=20)
    assert r.status_code == 200
    html = r.text
    assert "Pinch" in html
    assert '"pose_mode": "tap"' in html or '"pose_mode":"tap"' in html


def test_submit_all_complete_no_issues(s):
    r = s.post(f"{API}/assessment/submit", json=_sample_payload(complete=True), timeout=20)
    assert r.status_code == 200
    data = r.json()
    codes = [i["code"] for i in data["functional_issues"]]
    # When all tasks complete and no trunk metrics -> NO_ISSUES
    assert "NO_ISSUES" in codes
