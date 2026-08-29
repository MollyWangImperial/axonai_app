"""
Iteration 6 partial — Therapists `trained_on` + AI therapist 5-msg paywall.

Tests:
  - GET /api/therapists: all 6 entries are ai=True, premium=True, have trained_on
  - GET /api/therapists/match: trained_on bubbles up inside match.therapist
  - POST /api/personas/chat: th_001 -> no paywall on msgs 1..4, paywall on msg >= 5
  - POST /api/personas/chat: pt_001 (patient persona) -> NEVER paywall
  - Hope tab GET /api/personas/th_001/opener still healthy
  - General health: existing assessment endpoints still respond
"""

import os
import uuid
import pytest
import requests

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
).rstrip("/")

TIMEOUT = 60  # LLM chat can be slow


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Therapists list ----------
class TestTherapistsList:
    def test_returns_six_therapists_with_trained_on(self, api):
        r = api.get(f"{BASE_URL}/api/therapists", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        ts = data.get("therapists", [])
        assert len(ts) == 6, f"expected 6 therapists, got {len(ts)}"
        for t in ts:
            assert t.get("ai") is True, f"{t.get('id')} ai != True"
            assert t.get("premium") is True, f"{t.get('id')} premium != True"
            assert isinstance(t.get("trained_on"), str) and len(t["trained_on"]) > 5, (
                f"{t.get('id')} missing/short trained_on: {t.get('trained_on')!r}"
            )
            # Should never leak prompt
            assert "persona_prompt" not in t


# ---------- Therapist match ----------
class TestTherapistMatch:
    def test_match_includes_trained_on(self, api):
        r = api.get(
            f"{BASE_URL}/api/therapists/match",
            params={"issues": "HAND_OPENING,REACH_INCOMPLETE"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        matches = r.json().get("matches", [])
        assert len(matches) == 6
        for m in matches:
            th = m.get("therapist", {})
            assert isinstance(th.get("trained_on"), str) and th["trained_on"], (
                f"match for {th.get('id')} missing trained_on"
            )
            assert "persona_prompt" not in th


# ---------- Paywall logic on AI therapist ----------
class TestTherapistPaywall:
    """th_001 — first 4 user messages must have paywall=None, 5th must be set."""

    def test_paywall_after_fifth_user_message(self, api):
        session_id = f"TEST_paywall_{uuid.uuid4().hex[:10]}"
        last = None
        for i in range(1, 6):
            r = api.post(
                f"{BASE_URL}/api/personas/chat",
                json={"persona_id": "th_001", "session_id": session_id, "text": f"hi msg {i}"},
                timeout=TIMEOUT,
            )
            if r.status_code == 503:
                pytest.skip("LLM key not configured in this environment")
            assert r.status_code == 200, f"msg{i}: {r.status_code} {r.text[:200]}"
            data = r.json()
            assert data["user_turns"] == i
            if i < 5:
                assert data.get("paywall") in (None, {}), (
                    f"msg{i} should have NO paywall, got {data.get('paywall')}"
                )
            else:
                pw = data.get("paywall")
                assert pw is not None, "paywall missing on msg 5"
                assert pw.get("limit_reached") is True
                for k in ("title", "body", "cta_upgrade", "cta_video"):
                    assert pw.get(k), f"paywall missing key {k}"
            last = data
        assert last is not None


# ---------- Patient personas never paywall ----------
class TestPatientNoPaywall:
    def test_patient_persona_never_paywalls(self, api):
        session_id = f"TEST_patient_nopay_{uuid.uuid4().hex[:10]}"
        # Send 6 messages — should never paywall
        for i in range(1, 7):
            r = api.post(
                f"{BASE_URL}/api/personas/chat",
                json={"persona_id": "pt_001", "session_id": session_id, "text": f"hi {i}"},
                timeout=TIMEOUT,
            )
            if r.status_code == 503:
                pytest.skip("LLM key not configured")
            if r.status_code == 404:
                pytest.skip("pt_001 patient persona not seeded in this environment")
            assert r.status_code == 200, f"msg{i}: {r.status_code} {r.text[:200]}"
            data = r.json()
            assert data["user_turns"] == i
            assert data.get("paywall") in (None, {}), (
                f"patient persona returned paywall at msg{i}: {data.get('paywall')}"
            )


# ---------- Hope opener (used by chat.tsx auto-voice bubble) ----------
class TestHopeOpener:
    def test_th_001_opener(self, api):
        r = api.get(f"{BASE_URL}/api/personas/th_001/opener", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("text") or j.get("opener") or j.get("message"), str) or j, (
            f"unexpected opener shape: {j}"
        )


# ---------- Prior endpoints still healthy ----------
class TestPriorEndpoints:
    def test_root(self, api):
        r = api.get(f"{BASE_URL}/api/", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_assessment_tasks(self, api):
        r = api.get(f"{BASE_URL}/api/assessment/tasks", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert len(d.get("tasks", [])) == 7

    def test_community_patients(self, api):
        r = api.get(f"{BASE_URL}/api/community/ai_patients", timeout=TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json().get("patients", []), list)
