"""
Iteration 11 backend regression tests.

Covers the 7 user-reported issues with the assessment+exercise flow as backend contracts:
- Pose runner HTML contains new gates: voiceFinishedAt, arrivedAfterMovement,
  updateMovementGate, effectiveRadius, step-active class, stepStartWristXY,
  sw*0.55 / sw*0.70 radius math, dynamicTargetPos
- Rehab runner HTML contains new scoring helpers: computeRepScore, lastRepScore,
  repBarFill, t.r * 1.55 (slightly larger exercise circle), "Heard you" softer voice
  fallback; AND the literal 'Voice input error' string was removed
- Assessment tasks unchanged (7 tasks, voice=nova, icon coverage)
- TTS health + generation still works (OpenAI Nova)
- Assessment history per-user filtering via X-User-Id header
- Onboarding round-trip POST -> GET
- /api/chat/proactive uses preferred_name from profile
- /api/chat/proactive/messages?n=3 returns 3 personalized messages
- /api/assessment/submit returns Assessment with non-empty rehab_plan
- /api/community/stories returns >=8 stories with full author names (Marisol Reyes,
  Daniel Okafor, Asha Narayan, ...)
- Backend logs free of 5xx during this run (best-effort check via responses)
"""

import base64
import os
import re
import uuid
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


# --------------------------- Pose runner HTML (iter 11 gates) ---------------------------
class TestPoseRunnerIter11:
    REQUIRED_TOKENS = [
        "voiceFinishedAt",
        "arrivedAfterMovement",
        "updateMovementGate",
        "effectiveRadius",
        "step-active",
        "stepStartWristXY",
        "sw * 0.55",
        "sw * 0.70",
        "dynamicTargetPos",
    ]

    def test_pose_runner_contains_all_iter11_tokens(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner", timeout=30)
        assert r.status_code == 200, r.text
        html = r.text
        missing = [tok for tok in self.REQUIRED_TOKENS if tok not in html]
        assert not missing, f"Pose runner HTML missing iter11 tokens: {missing}"

    def test_pose_runner_keeps_iter8_backbone(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner", timeout=30)
        assert r.status_code == 200, r.text
        html = r.text
        for tok in [
            "HandLandmarker",
            "WRIST_DYNAMIC",
            "MOUTH",
            "CHEST",
            "HAND_OPEN",
            "PINCH",
            "ICON_EMOJI",
            "computeHandMetrics",
            "getEffectiveTargetXY",
        ]:
            assert tok in html, f"Pose runner regressed - missing iter8 token {tok!r}"

    def test_pose_runner_html_well_formed(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner", timeout=30)
        assert r.status_code == 200
        html = r.text
        module_scripts = re.findall(r'<script\s+type="module"\s*>', html)
        assert len(module_scripts) == 1, f"expected 1 module script, got {len(module_scripts)}"
        open_scripts = len(re.findall(r"<script\b", html))
        close_scripts = len(re.findall(r"</script>", html))
        assert open_scripts == close_scripts, f"unbalanced script tags {open_scripts}/{close_scripts}"


# --------------------------- Rehab runner HTML (iter 11 scoring + softened voice) ---------------------------
class TestRehabRunnerIter11:
    REQUIRED_TOKENS = [
        "computeRepScore",
        "lastRepScore",
        "repBarFill",
        "t.r * 1.55",
        "Heard you",
    ]

    def test_rehab_runner_contains_all_iter11_tokens(self, api):
        r = api.get(
            f"{BASE_URL}/api/rehab/runner",
            params={"exercise_id": "ex_maintenance"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        html = r.text
        missing = [tok for tok in self.REQUIRED_TOKENS if tok not in html]
        assert not missing, f"Rehab runner HTML missing iter11 tokens: {missing}"

    def test_rehab_runner_does_not_contain_voice_input_error(self, api):
        r = api.get(
            f"{BASE_URL}/api/rehab/runner",
            params={"exercise_id": "ex_maintenance"},
            timeout=30,
        )
        assert r.status_code == 200
        assert "Voice input error" not in r.text, (
            "Rehab runner still contains 'Voice input error' literal — it should be softened/removed"
        )

    def test_rehab_runner_html_well_formed(self, api):
        r = api.get(
            f"{BASE_URL}/api/rehab/runner",
            params={"exercise_id": "ex_maintenance"},
            timeout=30,
        )
        assert r.status_code == 200
        html = r.text
        open_scripts = len(re.findall(r"<script\b", html))
        close_scripts = len(re.findall(r"</script>", html))
        assert open_scripts == close_scripts, f"unbalanced script tags {open_scripts}/{close_scripts}"


# --------------------------- Assessment tasks (unchanged contract) ---------------------------
class TestAssessmentTasksIter11:
    def test_seven_tasks_with_nova_voice_and_icons(self, api):
        r = api.get(f"{BASE_URL}/api/assessment/tasks", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("voice_id") == "nova", data.get("voice_id")
        tasks = data.get("tasks", [])
        assert len(tasks) == 7, f"Expected 7 tasks, got {len(tasks)}"

        icons = []
        for t in tasks:
            for s in t.get("steps", []):
                tgt = s.get("target") or {}
                if "icon" in tgt:
                    icons.append(tgt["icon"])
        for required_icon in ("cup", "table", "ball", "coin", "towel"):
            assert required_icon in icons, f"Missing icon '{required_icon}' in {icons}"


# --------------------------- TTS ---------------------------
class TestTTSIter11:
    def test_tts_health(self, api):
        r = api.get(f"{BASE_URL}/api/tts/health", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("provider") == "openai"
        assert data.get("voice") == "nova"

    def test_tts_generate_returns_valid_base64_mp3(self, api):
        r = api.post(
            f"{BASE_URL}/api/tts/generate",
            json={"text": "Iteration eleven test"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "audio_b64" in data and len(data["audio_b64"]) > 500
        raw = base64.b64decode(data["audio_b64"], validate=True)
        assert len(raw) > 200
        head = raw[:4]
        valid = head.startswith(b"ID3") or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)
        assert valid, f"Unexpected mp3 header: {head!r}"


# --------------------------- Assessment history per-user ---------------------------
class TestAssessmentHistoryPerUser:
    def test_history_empty_without_header(self, api):
        # Use clean session — no X-User-Id
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/assessment/history", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # Anonymous → must be empty per iter 11 contract
        assert data == [], f"Anonymous /assessment/history must be []; got {len(data)} items"

    def test_history_returns_only_for_user(self, api):
        # Create two users
        suffix_a = uuid.uuid4().hex[:8]
        suffix_b = uuid.uuid4().hex[:8]
        ua = requests.post(
            f"{BASE_URL}/api/users/signup",
            json={"email": f"TEST_iter11_a_{suffix_a}@example.com", "name": "Iter11 A", "role": "patient"},
            timeout=30,
        ).json()
        ub = requests.post(
            f"{BASE_URL}/api/users/signup",
            json={"email": f"TEST_iter11_b_{suffix_b}@example.com", "name": "Iter11 B", "role": "patient"},
            timeout=30,
        ).json()
        assert ua.get("id") and ub.get("id"), (ua, ub)

        payload = {
            "affected_side": "right",
            "task_results": [
                {
                    "task_id": "T1",
                    "completed_steps": 1,
                    "total_steps": 3,
                    "duration_ms": 4000,
                    "steps": [],
                    "metrics": {"trunk_lean_deg": 18},
                }
            ],
        }
        # Submit one assessment as user A only
        r = requests.post(
            f"{BASE_URL}/api/assessment/submit",
            json=payload,
            headers={"Content-Type": "application/json", "X-User-Id": ua["id"]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        a_assessment_id = r.json().get("id")
        assert a_assessment_id

        # History for A should include it
        ra = requests.get(
            f"{BASE_URL}/api/assessment/history",
            headers={"X-User-Id": ua["id"]},
            timeout=30,
        )
        assert ra.status_code == 200
        ids_a = {x["id"] for x in ra.json()}
        assert a_assessment_id in ids_a

        # History for B should NOT include A's assessment
        rb = requests.get(
            f"{BASE_URL}/api/assessment/history",
            headers={"X-User-Id": ub["id"]},
            timeout=30,
        )
        assert rb.status_code == 200
        ids_b = {x["id"] for x in rb.json()}
        assert a_assessment_id not in ids_b, "User B leaked user A's assessment"


# --------------------------- Onboarding round-trip ---------------------------
class TestOnboardingRoundTrip:
    def test_post_then_get_onboarding(self):
        suffix = uuid.uuid4().hex[:8]
        signup = requests.post(
            f"{BASE_URL}/api/users/signup",
            json={"email": f"TEST_iter11_onb_{suffix}@example.com", "name": "Iter11 Onb", "role": "patient"},
            timeout=30,
        ).json()
        uid = signup.get("id")
        assert uid

        # Before onboarding -> false
        r0 = requests.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=30,
        )
        assert r0.status_code == 200
        assert r0.json().get("onboarding_complete") is False

        # POST onboarding
        payload = {
            "preferred_name": "Sam",
            "age_band": "55-64",
            "months_since_stroke": 9,
            "side_affected": "right",
            "dominant_hand": "right",
            "mobility_level": "cane",
            "primary_goal": "Hold my grandson again",
            "has_caregiver": True,
        }
        r1 = requests.post(
            f"{BASE_URL}/api/users/onboarding",
            json=payload,
            headers={"Content-Type": "application/json", "X-User-Id": uid},
            timeout=30,
        )
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        assert data1.get("ok") is True
        assert data1.get("profile", {}).get("preferred_name") == "Sam"

        # GET onboarding -> complete=true and profile present
        r2 = requests.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=30,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2.get("onboarding_complete") is True
        prof = data2.get("profile") or {}
        assert prof.get("preferred_name") == "Sam"
        assert prof.get("primary_goal") == "Hold my grandson again"
        return uid  # not used by pytest; doc only


# --------------------------- Proactive chat uses preferred_name ---------------------------
class TestProactiveChat:
    def _onboarded_user(self, preferred_name: str = "Riya"):
        suffix = uuid.uuid4().hex[:8]
        signup = requests.post(
            f"{BASE_URL}/api/users/signup",
            json={"email": f"TEST_iter11_pro_{suffix}@example.com", "name": "Iter11 Pro", "role": "patient"},
            timeout=30,
        ).json()
        uid = signup["id"]
        requests.post(
            f"{BASE_URL}/api/users/onboarding",
            json={"preferred_name": preferred_name},
            headers={"Content-Type": "application/json", "X-User-Id": uid},
            timeout=30,
        )
        return uid

    def test_chat_proactive_uses_preferred_name(self):
        uid = self._onboarded_user("Riya")
        r = requests.post(
            f"{BASE_URL}/api/chat/proactive",
            json={"session_id": f"sess_{uuid.uuid4().hex[:8]}", "text": ""},
            headers={"Content-Type": "application/json", "X-User-Id": uid},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        text = r.json().get("text", "")
        assert "Riya" in text, f"preferred_name not used in proactive text: {text!r}"

    def test_chat_proactive_messages_n3_personalized(self):
        uid = self._onboarded_user("Kavi")
        r = requests.get(
            f"{BASE_URL}/api/chat/proactive/messages",
            params={"n": 3},
            headers={"X-User-Id": uid},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        msgs = data.get("messages") or []
        assert len(msgs) == 3, f"Expected 3 messages, got {len(msgs)}: {msgs}"
        assert data.get("name") == "Kavi"
        # Each message must mention the name (personalized)
        personalized = [m for m in msgs if "Kavi" in m]
        assert len(personalized) >= 2, (
            f"Expected most messages personalized with 'Kavi'; got {msgs}"
        )


# --------------------------- Assessment submit still returns rehab_plan ---------------------------
class TestAssessmentSubmitIter11:
    def test_submit_returns_rehab_plan(self, api):
        payload = {
            "affected_side": "left",
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
        r = api.post(f"{BASE_URL}/api/assessment/submit", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("id")
        assert isinstance(data.get("rehab_plan"), list) and len(data["rehab_plan"]) >= 1
        for ex in data["rehab_plan"]:
            assert ex.get("id") and ex.get("name") and ex.get("targets_issue")


# --------------------------- Community stories full names ---------------------------
class TestCommunityStories:
    def test_eight_seed_stories_with_full_names(self, api):
        r = api.get(f"{BASE_URL}/api/community/stories", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        stories = data.get("stories") or []
        # Seed contains 8 -- but test DB may also have user-submitted stories from
        # other tests; only require >=8 and check seed authors are present.
        assert len(stories) >= 8, f"Expected at least 8 stories, got {len(stories)}"
        authors = {s.get("author") for s in stories}
        for required in ("Marisol Reyes", "Daniel Okafor", "Asha Narayan"):
            assert required in authors, f"Missing seed author {required!r} in {authors}"
