"""Phase C backend test suite — covers:
- /api/credits/balance shape (costs map + subscription_active flag)
- New user initial credits=100
- /api/progress/summary shape (empty for anon/new, populates after assessment)
- /api/billing/{subscribe,buy-credits,verify-session,webhook} wiring
- /api/auth/google/session validation + invalid-session rejection
- consume_credits subscription bypass for assessment
- Persona chat credit consumption (premium_chat_message=10) — covers the spec
  endpoint /api/chat/persona/message AND the actual /api/personas/chat route
- Existing endpoints unaffected (tts/health, assessment/tasks, pose/runner, rehab/runner, onboarding)
"""
import os
import uuid
import requests
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           open("/app/frontend/.env").read().split("EXPO_PUBLIC_BACKEND_URL=")[1].split("\n")[0].strip()

EXPECTED_COSTS = {
    "assessment": 40,
    "rehab_plan": 30,
    "guided_exercise": 30,
    "premium_chat_message": 10,
    "video_call": 50,
    "in_person_session": 80,
}


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _new_user(api):
    """Create a fresh test user via /users/signup. Returns user dict."""
    email = f"TEST_phasec_{uuid.uuid4().hex[:8]}@example.com"
    r = api.post(f"{BASE_URL}/api/users/signup",
                 json={"email": email, "name": "PhaseC Tester", "role": "patient"})
    assert r.status_code == 200, f"signup failed: {r.status_code} {r.text}"
    return r.json()


# ============ Credits balance ============
class TestCreditsBalance:
    def test_anonymous_balance_returns_costs_and_sub_flag(self, api):
        r = api.get(f"{BASE_URL}/api/credits/balance")
        assert r.status_code == 200
        data = r.json()
        assert data.get("anonymous") is True
        assert data.get("credits") == 0
        assert data.get("subscription_active") is False
        assert data.get("costs") == EXPECTED_COSTS

    def test_signed_in_balance_costs_and_initial_credits(self, api):
        u = _new_user(api)
        assert u["credits"] == 100
        r = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        assert r.status_code == 200
        data = r.json()
        assert data["credits"] == 100
        assert data["subscription_active"] is False
        assert data["costs"] == EXPECTED_COSTS
        assert data["user_id"] == u["id"]


# ============ Progress summary ============
class TestProgressSummary:
    def test_anonymous_returns_empty(self, api):
        r = api.get(f"{BASE_URL}/api/progress/summary")
        assert r.status_code == 200
        data = r.json()
        assert data.get("assessments") == []
        assert data.get("first_seen") is None

    def test_new_user_returns_empty(self, api):
        u = _new_user(api)
        r = api.get(f"{BASE_URL}/api/progress/summary", headers={"X-User-Id": u["id"]})
        assert r.status_code == 200
        data = r.json()
        assert data["assessments"] == []
        assert data["first_seen"] is None
        assert data.get("count", 0) == 0

    def test_assessment_then_progress_summary_includes_it(self, api):
        u = _new_user(api)
        # Submit a minimal assessment
        payload = {
            "task_results": [
                {"task_id": "T1", "completed_steps": 3, "total_steps": 3,
                 "duration_ms": 1000, "steps": [], "metrics": {"trunk_lean_deg": 5}}
            ],
            "affected_side": "right",
        }
        sub = api.post(f"{BASE_URL}/api/assessment/submit",
                       json=payload, headers={"X-User-Id": u["id"]})
        assert sub.status_code == 200, f"assessment/submit failed: {sub.status_code} {sub.text}"
        body = sub.json()
        assert "id" in body and "rehab_plan" in body

        prog = api.get(f"{BASE_URL}/api/progress/summary", headers={"X-User-Id": u["id"]})
        assert prog.status_code == 200
        data = prog.json()
        assert isinstance(data["assessments"], list)
        assert len(data["assessments"]) >= 1
        # The returned series item should reference our assessment id
        ids = [a.get("id") for a in data["assessments"]]
        assert body["id"] in ids
        assert data["first_seen"] is not None


# ============ Billing wiring (Stripe sentinel key) ============
class TestBilling:
    def test_subscribe_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/billing/subscribe")
        assert r.status_code == 401

    def test_subscribe_wired_returns_500_with_stripe_error(self, api):
        u = _new_user(api)
        r = api.post(f"{BASE_URL}/api/billing/subscribe", headers={"X-User-Id": u["id"]})
        # NOT a 404 → endpoint is wired.
        assert r.status_code != 404, f"endpoint not wired: {r.status_code}"
        # Sentinel API key → Stripe rejects → 500 with Invalid API Key
        assert r.status_code == 500
        detail = (r.json() or {}).get("detail", "")
        assert "invalid api key" in detail.lower() or "api key" in detail.lower(), \
            f"unexpected detail: {detail}"

    def test_buy_credits_wired_returns_500_with_stripe_error(self, api):
        u = _new_user(api)
        r = api.post(f"{BASE_URL}/api/billing/buy-credits", headers={"X-User-Id": u["id"]})
        assert r.status_code != 404
        assert r.status_code == 500
        detail = (r.json() or {}).get("detail", "")
        assert "api key" in detail.lower()

    def test_verify_session_unknown_returns_404(self, api):
        u = _new_user(api)
        r = api.get(f"{BASE_URL}/api/billing/verify-session?session_id=fake_unknown_xyz",
                    headers={"X-User-Id": u["id"]})
        assert r.status_code == 404
        assert "unknown session" in (r.json().get("detail", "").lower())

    def test_webhook_accepts_no_signature_when_secret_unset(self, api):
        # Sample checkout.session.completed payload — unknown session_id, so no DB mutation.
        payload = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_phasec_nonexistent", "payment_status": "paid"}},
        }
        r = api.post(f"{BASE_URL}/api/billing/webhook", json=payload)
        assert r.status_code == 200, f"webhook returned {r.status_code}: {r.text}"
        assert r.json() == {"ok": True}


# ============ Google auth (Emergent-managed) ============
class TestGoogleAuth:
    def test_missing_session_id_returns_400(self, api):
        r = api.post(f"{BASE_URL}/api/auth/google/session", json={})
        assert r.status_code == 400
        assert "session_id" in r.json().get("detail", "").lower()

    def test_bogus_session_id_returns_401(self, api):
        r = api.post(f"{BASE_URL}/api/auth/google/session",
                     json={"session_id": "bogus_session_phasec_test_xyz"})
        # The Emergent auth backend rejects bogus session_ids → 401 surfaced.
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ============ Subscription bypass for assessment ============
class TestSubscriptionBypass:
    def test_assessment_does_not_decrement_credits_for_subscriber(self, api):
        u = _new_user(api)
        # Flip subscription_active=true directly in MongoDB
        mongo_url = "mongodb://localhost:27017"
        db_name = "test_database"
        # Use a sync motor-equivalent via a small async snippet.
        async def flip():
            cli = AsyncIOMotorClient(mongo_url)
            await cli[db_name].users.update_one(
                {"id": u["id"]}, {"$set": {"subscription_active": True}}
            )
            cli.close()
        asyncio.get_event_loop().run_until_complete(flip())

        # Confirm via balance
        bal = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        assert bal.status_code == 200
        assert bal.json()["subscription_active"] is True
        assert bal.json()["credits"] == 100

        # Submit an assessment — would normally cost 40 (assess) + 30 (rehab_plan) = 70
        payload = {
            "task_results": [
                {"task_id": "T1", "completed_steps": 3, "total_steps": 3,
                 "duration_ms": 1000, "steps": [], "metrics": {}}
            ],
            "affected_side": "right",
        }
        sub = api.post(f"{BASE_URL}/api/assessment/submit",
                       json=payload, headers={"X-User-Id": u["id"]})
        assert sub.status_code == 200

        bal2 = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        # Subscription bypass → no credit decrement
        assert bal2.json()["credits"] == 100, \
            f"subscription should bypass credits, got {bal2.json()['credits']}"


# ============ Persona chat still burns 10 credits (premium_chat_message) ============
class TestPersonaChatCredits:
    """Spec says POST /api/chat/persona/message should burn 10 credits even for subscribers.
    Both /api/personas/chat (canonical) and /api/chat/persona/message (alias) must work."""

    def test_personas_chat_route_credit_behavior(self, api):
        """The canonical /api/personas/chat endpoint — must burn 10 credits.
        Valid persona ids are th_001..th_006."""
        u = _new_user(api)
        r = api.post(f"{BASE_URL}/api/personas/chat",
                     json={"persona_id": "th_001", "session_id": f"sess_{uuid.uuid4().hex[:6]}",
                           "text": "Hello"},
                     headers={"X-User-Id": u["id"]},
                     timeout=90)
        assert r.status_code in (200, 502), f"persona chat returned {r.status_code}: {r.text[:300]}"
        bal = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        credits_after = bal.json()["credits"]
        # On 502 (LLM error) credits should still have been consumed because charge happens BEFORE LLM call.
        assert credits_after == 90, \
            f"premium_chat_message should burn 10 credits; balance={credits_after} (expected 90)"

    def test_chat_persona_message_alias_also_charges_10(self, api):
        """Alias /api/chat/persona/message must also charge 10 credits and return 200."""
        u = _new_user(api)
        r = api.post(f"{BASE_URL}/api/chat/persona/message",
                     json={"persona_id": "th_002", "session_id": f"sess_{uuid.uuid4().hex[:6]}",
                           "text": "Hi there"},
                     headers={"X-User-Id": u["id"]},
                     timeout=90)
        # Endpoint must NOT 404 (it's the spec-stated alias)
        assert r.status_code != 404, f"alias endpoint not wired: {r.status_code} {r.text[:200]}"
        assert r.status_code in (200, 502), f"alias returned {r.status_code}: {r.text[:300]}"
        bal = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        credits_after = bal.json()["credits"]
        assert credits_after == 90, \
            f"alias should burn 10 credits; balance={credits_after} (expected 90)"

    def test_personas_chat_without_user_id_returns_401(self, api):
        """No X-User-Id header → 401 'Sign in required'."""
        r = api.post(f"{BASE_URL}/api/personas/chat",
                     json={"persona_id": "th_001", "session_id": "anon_sess",
                           "text": "Hi"},
                     timeout=15)
        assert r.status_code == 401, f"expected 401 without X-User-Id, got {r.status_code}: {r.text[:200]}"
        detail = (r.json() or {}).get("detail", "").lower()
        assert "sign in" in detail or "required" in detail, f"unexpected detail: {detail}"

    def test_personas_chat_insufficient_credits_returns_402(self, api):
        """User with <10 credits → 402 'Not enough credits to chat'."""
        u = _new_user(api)
        # Set credits to 5 directly in mongo
        async def set_low():
            cli = AsyncIOMotorClient("mongodb://localhost:27017")
            await cli["test_database"].users.update_one(
                {"id": u["id"]}, {"$set": {"credits": 5}}
            )
            cli.close()
        asyncio.get_event_loop().run_until_complete(set_low())

        r = api.post(f"{BASE_URL}/api/personas/chat",
                     json={"persona_id": "th_001", "session_id": "lowc",
                           "text": "Hi"},
                     headers={"X-User-Id": u["id"]},
                     timeout=15)
        assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text[:300]}"
        detail = (r.json() or {}).get("detail", "").lower()
        assert "not enough credits" in detail, f"unexpected 402 detail: {detail}"

        # And credits must NOT have been decremented further (still 5)
        bal = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        assert bal.json()["credits"] == 5, f"402 path should not decrement; got {bal.json()['credits']}"

    def test_subscribed_user_still_pays_for_persona_chat(self, api):
        """Subscription bypass should NOT cover AI therapist chat — subscribers still pay 10 credits."""
        u = _new_user(api)
        async def flip_sub():
            cli = AsyncIOMotorClient("mongodb://localhost:27017")
            await cli["test_database"].users.update_one(
                {"id": u["id"]}, {"$set": {"subscription_active": True}}
            )
            cli.close()
        asyncio.get_event_loop().run_until_complete(flip_sub())

        # Confirm subscription active and credits=100
        bal0 = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        assert bal0.json()["subscription_active"] is True
        assert bal0.json()["credits"] == 100

        r = api.post(f"{BASE_URL}/api/personas/chat",
                     json={"persona_id": "th_001", "session_id": f"sub_{uuid.uuid4().hex[:6]}",
                           "text": "Hello as subscriber"},
                     headers={"X-User-Id": u["id"]},
                     timeout=90)
        assert r.status_code in (200, 502), f"persona chat returned {r.status_code}: {r.text[:300]}"

        bal1 = api.get(f"{BASE_URL}/api/credits/balance", headers={"X-User-Id": u["id"]})
        assert bal1.json()["credits"] == 90, \
            f"subscribers MUST still pay for AI chat; got {bal1.json()['credits']} (expected 90)"


# ============ Existing endpoints unaffected ============
class TestExistingEndpoints:
    def test_tts_health(self, api):
        r = api.get(f"{BASE_URL}/api/tts/health")
        assert r.status_code == 200
        data = r.json()
        # Either ok=true OR quota_exceeded — either way endpoint responds.
        assert "ok" in data

    def test_assessment_tasks(self, api):
        r = api.get(f"{BASE_URL}/api/assessment/tasks")
        assert r.status_code == 200
        data = r.json()
        assert len(data["tasks"]) == 7
        assert data["voice_id"] == "nova"

    def test_pose_runner_html(self, api):
        r = api.get(f"{BASE_URL}/api/pose/runner")
        assert r.status_code == 200
        assert "<html" in r.text.lower()

    def test_rehab_runner_ex_maintenance(self, api):
        r = api.get(f"{BASE_URL}/api/rehab/runner?exercise_id=ex_maintenance")
        assert r.status_code == 200
        assert "<html" in r.text.lower()

    def test_onboarding_roundtrip(self, api):
        u = _new_user(api)
        # POST onboarding
        post = api.post(
            f"{BASE_URL}/api/users/onboarding",
            json={"preferred_name": "Phase", "age_band": "55-64",
                  "months_since_stroke": 6, "side_affected": "right",
                  "primary_goal": "open jar"},
            headers={"X-User-Id": u["id"]},
        )
        assert post.status_code == 200
        assert post.json()["ok"] is True

        get = api.get(f"{BASE_URL}/api/users/onboarding",
                      headers={"X-User-Id": u["id"]})
        assert get.status_code == 200
        body = get.json()
        assert body["onboarding_complete"] is True
        assert body["profile"]["preferred_name"] == "Phase"
        assert body["profile"]["primary_goal"] == "open jar"
