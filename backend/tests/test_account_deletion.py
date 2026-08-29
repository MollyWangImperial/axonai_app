"""Backend regression tests for Phase 1 (compliance) — account deletion + onboarding.

Focus: DELETE /api/users/account soft-delete behaviour and follow-on
GET /api/users/onboarding response.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or os.environ.get(
    "EXPO_BACKEND_URL", ""
).rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, email: str, name: str = "QA Tester", role: str = "patient"):
    r = api.post(
        f"{BASE_URL}/api/users/login",
        json={"email": email, "name": name, "role": role},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "id" in data
    return data


# --------------- health ---------------
def test_health(api):
    r = api.get(f"{BASE_URL}/api/", timeout=10)
    assert r.status_code in (200, 404), f"unexpected status {r.status_code}"


# --------------- account deletion ---------------
class TestAccountDeletion:
    def test_delete_without_header_returns_401(self, api):
        r = api.delete(f"{BASE_URL}/api/users/account", timeout=15)
        assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"

    def test_delete_with_valid_user_id_soft_deletes(self, api):
        email = f"TEST_delete_{uuid.uuid4().hex[:8]}@example.com"
        user = _login(api, email)
        uid = user["id"]

        # Complete onboarding minimally so we can verify it flips back to false.
        r_on = api.post(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            json={"preferred_name": "QA Tester", "side_affected": "right"},
            timeout=15,
        )
        assert r_on.status_code == 200, f"onboarding save failed: {r_on.text}"

        # Verify onboarding is complete before deletion.
        r_pre = api.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=15,
        )
        assert r_pre.status_code == 200
        pre = r_pre.json()
        assert pre.get("onboarding_complete") is True, f"pre-delete: {pre}"

        # Delete account.
        r_del = api.delete(
            f"{BASE_URL}/api/users/account",
            headers={"X-User-Id": uid},
            timeout=15,
        )
        assert r_del.status_code == 200, f"delete failed: {r_del.status_code} {r_del.text}"
        body = r_del.json()
        assert body.get("ok") is True, f"missing ok: {body}"
        assert body.get("deleted_at"), f"missing deleted_at: {body}"

        # After soft delete, GET /users/onboarding must report false.
        time.sleep(0.5)
        r_post = api.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=15,
        )
        assert r_post.status_code == 200
        post = r_post.json()
        assert post.get("onboarding_complete") is False, f"post-delete: {post}"


# --------------- consent-flow regression: login + onboarding round-trip ---------------
class TestConsentRegression:
    def test_new_patient_login_then_onboarding_save_and_read(self, api):
        email = f"TEST_new_{uuid.uuid4().hex[:8]}@example.com"
        user = _login(api, email)
        uid = user["id"]

        # New patient => onboarding_complete should be false initially.
        r0 = api.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=15,
        )
        assert r0.status_code == 200
        assert r0.json().get("onboarding_complete") is False

        # Save onboarding.
        r1 = api.post(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            json={
                "preferred_name": "QA Tester",
                "side_affected": "right",
                "age_band": "50-59",
                "mobility_level": "walks_with_aid",
            },
            timeout=15,
        )
        assert r1.status_code == 200, r1.text

        # Verify persistence.
        r2 = api.get(
            f"{BASE_URL}/api/users/onboarding",
            headers={"X-User-Id": uid},
            timeout=15,
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body.get("onboarding_complete") is True
        prof = body.get("profile") or {}
        assert prof.get("preferred_name") == "QA Tester"
        assert prof.get("side_affected") == "right"
