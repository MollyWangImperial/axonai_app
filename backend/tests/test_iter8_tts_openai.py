"""
Iteration 8 backend regression tests.

Covers:
- TTS migration to OpenAI Nova via Emergent LLM key (/api/tts/health, /api/tts/generate)
- Assessment tasks payload (7 tasks, voice_id=nova, icon fields present)
- Pose runner HTML contains required tokens for new dynamic landmark logic
- Existing endpoints still work (/api/credits/balance, /api/assessment/history, /api/status)
- /api/assessment/submit returns Assessment with rehab_plan
"""

import base64
import os
import re
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
)
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --------------------------- TTS (OpenAI Nova) ---------------------------
class TestTTS:
    def test_tts_health_openai_nova(self, api):
        r = api.get(f"{BASE_URL}/api/tts/health", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True, f"Expected ok=true, got {data}"
        assert data.get("provider") == "openai", data
        assert data.get("voice") == "nova", data
        assert data.get("model") == "tts-1", data
        assert isinstance(data.get("bytes"), int) and data["bytes"] > 0

    def test_tts_generate_returns_valid_mp3_base64(self, api):
        r = api.post(
            f"{BASE_URL}/api/tts/generate",
            json={"text": "Hello, this is a test"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "audio_b64" in data and isinstance(data["audio_b64"], str)
        assert len(data["audio_b64"]) > 500, "audio_b64 unexpectedly short"
        raw = base64.b64decode(data["audio_b64"], validate=True)
        assert len(raw) > 200, "decoded mp3 too small"
        # MP3 header: ID3 tag or 0xFF 0xFB / 0xFF 0xF3 / 0xFF 0xF2 frame sync
        head = raw[:4]
        valid = head.startswith(b"ID3") or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
        assert valid, f"Unexpected mp3 header: {head!r}"
        assert data.get("text") == "Hello, this is a test"

    def test_tts_generate_empty_text_not_503(self, api):
        r = api.post(
            f"{BASE_URL}/api/tts/generate", json={"text": ""}, timeout=60
        )
        # Should be sensible 4xx/500, NOT a 503 (which is reserved for quota_exceeded)
        assert r.status_code != 503, f"Empty text returned 503 quota error: {r.text}"
        assert r.status_code >= 400, f"Empty text should be an error, got {r.status_code}"


# --------------------------- Assessment tasks ---------------------------
class TestAssessmentTasks:
    def test_tasks_count_voice_and_icons(self, api):
        r = api.get(f"{BASE_URL}/api/assessment/tasks", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("voice_id") == "nova", data.get("voice_id")
        tasks = data.get("tasks", [])
        assert len(tasks) == 7, f"Expected 7 tasks, got {len(tasks)}"

        # Count steps with icon across all tasks; ensure key icons exist
        icon_steps = []
        for t in tasks:
            for s in t.get("steps", []):
                tgt = s.get("target", {}) or {}
                if "icon" in tgt:
                    icon_steps.append(tgt["icon"])
        assert len(icon_steps) >= 5, f"Expected >=5 steps with icon, got {len(icon_steps)} ({icon_steps})"
        for required_icon in ("cup", "table", "ball", "coin", "towel"):
            assert required_icon in icon_steps, f"Missing icon '{required_icon}' in {icon_steps}"


# --------------------------- Pose runner HTML ---------------------------
class TestPoseRunner:
    REQUIRED_TOKENS = [
        "HandLandmarker",
        "WRIST_DYNAMIC",
        "MOUTH",
        "CHEST",
        "HAND_OPEN",
        "PINCH",
        "ICON_EMOJI",
        "computeHandMetrics",
        "getEffectiveTargetXY",
    ]

    def test_pose_runner_contains_required_tokens(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner", timeout=30)
        assert r.status_code == 200, r.text
        html = r.text
        missing = [tok for tok in self.REQUIRED_TOKENS if tok not in html]
        assert not missing, f"Pose runner HTML missing tokens: {missing}"

    def test_pose_runner_has_single_module_script(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner", timeout=30)
        assert r.status_code == 200
        html = r.text
        # Count <script type="module"> open tags
        matches = re.findall(r'<script\s+type="module"\s*>', html)
        assert len(matches) == 1, f"Expected exactly 1 <script type=\"module\"> block, got {len(matches)}"
        # Ensure balanced script tags
        open_scripts = len(re.findall(r"<script\b", html))
        close_scripts = len(re.findall(r"</script>", html))
        assert open_scripts == close_scripts, (
            f"Unbalanced <script> tags: {open_scripts} open vs {close_scripts} close"
        )
        # Quick template-literal sanity: extract the module script body and ensure
        # backticks are balanced (even count).
        m = re.search(
            r'<script\s+type="module"\s*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        assert m, "Could not extract module script body"
        body = m.group(1)
        backticks = body.count("`")
        assert backticks % 2 == 0, f"Unbalanced template-literal backticks: {backticks}"


# --------------------------- Existing endpoints ---------------------------
class TestExistingEndpoints:
    def test_credits_balance_no_auth(self, api):
        # Use a fresh session WITHOUT auth header
        r = requests.get(f"{BASE_URL}/api/credits/balance", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("anonymous") is True
        assert "credits" in data
        assert "costs" in data and isinstance(data["costs"], dict)

    def test_assessment_history(self, api):
        r = api.get(f"{BASE_URL}/api/assessment/history", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)

    def test_status_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/status", timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# --------------------------- Assessment submit ---------------------------
class TestAssessmentSubmit:
    def test_submit_returns_assessment_with_rehab_plan(self, api):
        payload = {
            "affected_side": "right",
            "task_results": [
                {
                    "task_id": "T1",
                    "completed_steps": 1,
                    "total_steps": 3,
                    "duration_ms": 4200,
                    "steps": [
                        {
                            "step_id": "T1-S2",
                            "completed": False,
                            "duration_ms": 1500,
                            "metrics": {"trunk_lean_deg": 22, "shoulder_hike": False},
                        }
                    ],
                    "metrics": {"trunk_lean_deg": 22},
                },
                {
                    "task_id": "T5",
                    "completed_steps": 1,
                    "total_steps": 3,
                    "duration_ms": 3300,
                    "steps": [],
                    "metrics": {},
                },
            ],
        }
        r = api.post(
            f"{BASE_URL}/api/assessment/submit", json=payload, timeout=60
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data and data["id"]
        assert data.get("affected_side") == "right"
        assert isinstance(data.get("functional_issues"), list)
        assert len(data["functional_issues"]) >= 1
        assert isinstance(data.get("rehab_plan"), list)
        assert len(data["rehab_plan"]) >= 1, "rehab_plan should be non-empty"
        # Each rehab item should have id + name + targets_issue
        for ex in data["rehab_plan"]:
            assert ex.get("id") and ex.get("name") and ex.get("targets_issue")

        # Verify persistence by checking history contains this id
        h = api.get(f"{BASE_URL}/api/assessment/history", timeout=30)
        assert h.status_code == 200
        ids = {a["id"] for a in h.json()}
        assert data["id"] in ids, "Submitted assessment not found in history"
