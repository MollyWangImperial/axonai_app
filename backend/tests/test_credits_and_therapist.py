"""Backend tests for iteration 7: users login, credits, therapist portal, bookings.

Covers: /api/users/login, /api/credits/balance, /api/assessment/submit (with/without user header),
/api/therapist/onboarding/{questions,submit}, /api/therapist/me,
/api/bookings/availability, /api/bookings, /api/therapists/all
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or os.environ["EXPO_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _email(prefix: str) -> str:
    return f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@test.com"


# ============ User login + credits ============
class TestUserLoginAndCredits:
    def test_login_creates_patient_with_100_credits(self, session):
        email = _email("patient")
        r = session.post(f"{API}/users/login", json={"email": email, "name": "TEST Patient", "role": "patient"})
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == email.lower()
        assert u["role"] == "patient"
        assert u["credits"] == 100
        assert u["id"].startswith("u_")

    def test_login_idempotent_same_user_preserves_credits(self, session):
        email = _email("idem")
        r1 = session.post(f"{API}/users/login", json={"email": email, "name": "TEST A", "role": "patient"})
        u1 = r1.json()
        # Deduct credits via assessment to verify they're preserved
        session.post(
            f"{API}/assessment/submit",
            json={"task_results": [], "affected_side": "right"},
            headers={"X-User-Id": u1["id"]},
        )
        r2 = session.post(f"{API}/users/login", json={"email": email, "name": "TEST A", "role": "patient"})
        u2 = r2.json()
        assert u2["id"] == u1["id"], "Same email must return same user_id"
        assert u2["credits"] == 70, f"After 10+20 deduction, expected 70, got {u2['credits']}"

    def test_credits_balance_with_header(self, session):
        email = _email("bal")
        u = session.post(f"{API}/users/login", json={"email": email, "name": "TEST", "role": "patient"}).json()
        r = session.get(f"{API}/credits/balance", headers={"X-User-Id": u["id"]})
        assert r.status_code == 200
        data = r.json()
        assert data["credits"] == 100
        assert "costs" in data
        assert data["costs"]["assessment"] == 10
        assert data["costs"]["rehab_plan"] == 20
        assert data["costs"]["guided_exercise"] == 5
        assert data["costs"]["premium_chat_message"] == 2
        assert data["costs"]["video_call"] == 50
        assert data["costs"]["in_person_session"] == 80

    def test_credits_balance_anonymous(self, session):
        r = session.get(f"{API}/credits/balance")
        assert r.status_code == 200
        data = r.json()
        assert data.get("anonymous") is True
        assert "costs" in data


# ============ Assessment credit deduction ============
class TestAssessmentCredits:
    def test_assessment_with_user_deducts_30_credits(self, session):
        email = _email("assess")
        u = session.post(f"{API}/users/login", json={"email": email, "name": "TEST", "role": "patient"}).json()
        r = session.post(
            f"{API}/assessment/submit",
            json={"task_results": [], "affected_side": "right"},
            headers={"X-User-Id": u["id"]},
        )
        assert r.status_code == 200, r.text
        bal = session.get(f"{API}/credits/balance", headers={"X-User-Id": u["id"]}).json()
        assert bal["credits"] == 70, f"Expected 100-10-20=70, got {bal['credits']}"

    def test_assessment_anonymous_still_works(self, session):
        r = session.post(f"{API}/assessment/submit", json={"task_results": [], "affected_side": "right"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body
        assert "functional_issues" in body

    def test_assessment_insufficient_credits_returns_402(self, session):
        email = _email("broke")
        u = session.post(f"{API}/users/login", json={"email": email, "name": "TEST", "role": "patient"}).json()
        # 100 credits; each assess takes 30. Do 3 successful (90), 4th should fail (need 30, have 10)
        for _ in range(3):
            r = session.post(
                f"{API}/assessment/submit",
                json={"task_results": [], "affected_side": "right"},
                headers={"X-User-Id": u["id"]},
            )
            assert r.status_code == 200
        r = session.post(
            f"{API}/assessment/submit",
            json={"task_results": [], "affected_side": "right"},
            headers={"X-User-Id": u["id"]},
        )
        assert r.status_code == 402, f"Expected 402, got {r.status_code}: {r.text}"


# ============ Therapist onboarding ============
class TestTherapistOnboarding:
    def test_questions_returns_10(self, session):
        r = session.get(f"{API}/therapist/onboarding/questions")
        assert r.status_code == 200
        qs = r.json()["questions"]
        assert len(qs) == 10
        for q in qs:
            assert "id" in q and "question" in q and "purpose" in q

    def test_submit_creates_real_therapist_profile(self, session):
        email = _email("therap")
        u = session.post(f"{API}/users/login", json={"email": email, "name": "TEST Dr Smith", "role": "therapist"}).json()
        answers = {f"q{i}": f"answer {i}" for i in range(1, 11)}
        answers["q4"] = "Calm and reassuring"
        answers["q9"] = "English, Spanish"
        answers["q10"] = "chat 30, video 60, in-person 90"
        r = session.post(
            f"{API}/therapist/onboarding/submit",
            json={"therapist_user_id": u["id"], "answers": answers, "specialties": ["hand_opening", "pinch"]},
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["ai"] is False
        assert p["commission_pct"] == 70
        assert "persona_prompt" in p and "TEST Dr Smith" in p["persona_prompt"]
        assert p["rates"] == {"chat": 30, "video": 60, "in_person": 90}
        assert "hand_opening" in p["specialties"]

    def test_therapist_me_returns_profile_and_bookings(self, session):
        email = _email("therap_me")
        u = session.post(f"{API}/users/login", json={"email": email, "name": "TEST Dr Me", "role": "therapist"}).json()
        answers = {f"q{i}": f"a{i}" for i in range(1, 11)}
        session.post(
            f"{API}/therapist/onboarding/submit",
            json={"therapist_user_id": u["id"], "answers": answers, "specialties": []},
        )
        r = session.get(f"{API}/therapist/me", headers={"X-User-Id": u["id"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["id"] == u["id"]
        assert data["profile"] is not None
        assert isinstance(data["bookings"], list)
        assert isinstance(data["commissions"], list)
        assert "commission_total_pence" in data


# ============ Bookings ============
class TestBookings:
    def test_availability_returns_8_slots(self, session):
        r = session.get(f"{API}/bookings/availability", params={"therapist_id": "th_001"})
        assert r.status_code == 200
        data = r.json()
        assert len(data["slots"]) == 8
        for s in data["slots"]:
            assert "iso" in s and "label" in s

    def test_booking_video_deducts_50_credits_and_creates_commission(self, session):
        # Create therapist
        t_email = _email("bk_t")
        t = session.post(f"{API}/users/login", json={"email": t_email, "name": "TEST Booking T", "role": "therapist"}).json()
        answers = {f"q{i}": f"a{i}" for i in range(1, 11)}
        prof = session.post(
            f"{API}/therapist/onboarding/submit",
            json={"therapist_user_id": t["id"], "answers": answers, "specialties": []},
        ).json()
        # Create patient
        p_email = _email("bk_p")
        p = session.post(f"{API}/users/login", json={"email": p_email, "name": "TEST P", "role": "patient"}).json()
        # Book video
        r = session.post(
            f"{API}/bookings",
            json={"patient_user_id": p["id"], "therapist_id": prof["therapist_id"], "kind": "video", "slot_iso": "2026-02-01T10:00:00Z"},
        )
        assert r.status_code == 200, r.text
        bk = r.json()
        assert bk["status"] == "confirmed"
        # Credits decremented by 50
        bal = session.get(f"{API}/credits/balance", headers={"X-User-Id": p["id"]}).json()
        assert bal["credits"] == 50
        # Therapist sees commission
        me = session.get(f"{API}/therapist/me", headers={"X-User-Id": t["id"]}).json()
        assert me["commission_total_pence"] > 0
        assert len(me["commissions"]) >= 1

    def test_booking_chat_deducts_2_credits(self, session):
        t_email = _email("bk_t2")
        t = session.post(f"{API}/users/login", json={"email": t_email, "name": "TEST T2", "role": "therapist"}).json()
        answers = {f"q{i}": f"a{i}" for i in range(1, 11)}
        prof = session.post(
            f"{API}/therapist/onboarding/submit",
            json={"therapist_user_id": t["id"], "answers": answers, "specialties": []},
        ).json()
        p_email = _email("bk_p2")
        p = session.post(f"{API}/users/login", json={"email": p_email, "name": "TEST P2", "role": "patient"}).json()
        r = session.post(
            f"{API}/bookings",
            json={"patient_user_id": p["id"], "therapist_id": prof["therapist_id"], "kind": "chat", "slot_iso": "2026-02-01T10:00:00Z"},
        )
        assert r.status_code == 200, r.text
        bal = session.get(f"{API}/credits/balance", headers={"X-User-Id": p["id"]}).json()
        assert bal["credits"] == 98


# ============ Therapists listing ============
class TestTherapistsAll:
    def test_all_returns_ai_and_real(self, session):
        r = session.get(f"{API}/therapists/all")
        assert r.status_code == 200
        data = r.json()
        assert "ai" in data and "real" in data
        assert len(data["ai"]) == 6, f"Expected 6 AI therapists, got {len(data['ai'])}"
        assert isinstance(data["real"], list)
