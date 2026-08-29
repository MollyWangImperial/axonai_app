"""
Backend tests for iteration 2 - Rehyn go-to-market features:
- GET /api/therapist/patients: role-gated (400 for patient, {patients:[]} for therapist)
- POST /api/therapist/patient/{id}/signoff: role-gated (400 for patient)
- GET /api/progress/summary: returns empty arrays for new user
- POST /api/users/login: email-only, role-aware
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def patient(s):
    email = f"TEST_patient_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/users/login", json={
        "email": email, "name": "TEST Patient", "role": "patient"})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u.get("role") == "patient"
    assert "id" in u
    return u


@pytest.fixture(scope="module")
def therapist(s):
    email = f"TEST_therapist_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/users/login", json={
        "email": email, "name": "TEST Therapist", "role": "therapist"})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u.get("role") == "therapist"
    assert "id" in u
    return u


# ---- Login sanity ----
def test_login_returns_id_and_role(patient, therapist):
    assert patient["id"] and therapist["id"]
    assert patient["id"] != therapist["id"]


# ---- GET /api/therapist/patients ----
def test_therapist_patients_requires_auth(s):
    r = s.get(f"{BASE_URL}/api/therapist/patients")
    # No X-User-Id → 400 (therapist required) or 401
    assert r.status_code in (400, 401), r.text


def test_therapist_patients_rejects_patient_role(s, patient):
    r = s.get(f"{BASE_URL}/api/therapist/patients",
              headers={"X-User-Id": patient["id"]})
    assert r.status_code == 400, r.text
    assert "therapist" in r.text.lower()


def test_therapist_patients_accepts_therapist_returns_list(s, therapist):
    r = s.get(f"{BASE_URL}/api/therapist/patients",
              headers={"X-User-Id": therapist["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "patients" in data
    assert isinstance(data["patients"], list)
    # New therapist with no bookings should get []
    assert data["patients"] == []


# ---- POST /api/therapist/patient/{id}/signoff ----
def test_signoff_rejects_patient_role(s, patient):
    r = s.post(
        f"{BASE_URL}/api/therapist/patient/{patient['id']}/signoff",
        headers={"X-User-Id": patient["id"]},
        json={"assessment_id": "rehyn-demo-assessment", "note": "test"},
    )
    assert r.status_code == 400, r.text


def test_signoff_accepts_therapist(s, therapist, patient):
    r = s.post(
        f"{BASE_URL}/api/therapist/patient/{patient['id']}/signoff",
        headers={"X-User-Id": therapist["id"]},
        json={"assessment_id": "rehyn-demo-assessment", "note": "TEST signoff"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert "signed_at" in data


# ---- GET /api/progress/summary ----
def test_progress_summary_empty_for_new_user(s, patient):
    r = s.get(f"{BASE_URL}/api/progress/summary",
              headers={"X-User-Id": patient["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "assessments" in data
    assert isinstance(data["assessments"], list)
    # New user → empty. ProgressStoryCard hides itself when < 2 assessments.
    assert len(data["assessments"]) == 0


def test_progress_summary_no_auth_returns_empty(s):
    r = s.get(f"{BASE_URL}/api/progress/summary")
    assert r.status_code == 200
    data = r.json()
    assert data.get("assessments") == []
