"""Iter 5 tests: AI patient personas, AI therapists, persona chat, reminders."""
import os
import pytest
import requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# AI patient personas
class TestAIPatients:
    def test_list_ai_patients(self, s):
        r = s.get(f"{API}/community/ai_patients", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        patients = data.get("patients") or data.get("ai_patients") or data
        if isinstance(data, dict) and "patients" not in data and "ai_patients" not in data:
            # might directly be a list
            patients = data
        assert isinstance(patients, list), f"unexpected shape: {data}"
        assert len(patients) == 6, f"expected 6 patients, got {len(patients)}"
        for p in patients:
            assert "id" in p and "name" in p and "photo" in p
            assert "age" in p and "months_since_stroke" in p
            assert "stage" in p and "bio" in p
            assert p.get("ai") is True
            assert "persona_prompt" not in p, "persona_prompt should not leak"

    def test_pt_001_opener(self, s):
        r = s.get(f"{API}/personas/pt_001/opener", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        text = body.get("text") or body.get("opener") or body.get("message") or ""
        assert "Marisol" in text, f"opener should mention Marisol: {text}"

    def test_invalid_persona_opener_404(self, s):
        r = s.get(f"{API}/personas/nope_xyz/opener", timeout=20)
        assert r.status_code == 404


# AI Therapists
class TestAITherapists:
    def test_therapists_all_ai(self, s):
        r = s.get(f"{API}/therapists", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        therapists = data.get("therapists") if isinstance(data, dict) else data
        assert isinstance(therapists, list)
        assert len(therapists) == 6
        for t in therapists:
            assert t.get("ai") is True, f"therapist not marked ai: {t}"
            name = t.get("name", "")
            assert name.startswith("AI ") or "(AI Therapist)" in name or "AI" in name, f"unexpected name: {name}"
            assert "persona_prompt" not in t

    def test_th_001_opener(self, s):
        r = s.get(f"{API}/personas/th_001/opener", timeout=30)
        assert r.status_code == 200, r.text
        text = r.json().get("text", "") or r.json().get("opener", "") or r.json().get("message", "")
        assert len(text) > 5


# Persona chat
class TestPersonaChat:
    def test_chat_patient(self, s):
        r = s.post(f"{API}/personas/chat",
                   json={"persona_id": "pt_001", "session_id": "TEST_p", "text": "Hi Marisol"},
                   timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        reply = body.get("reply") or body.get("text") or body.get("message") or ""
        assert len(reply) > 5, f"empty reply: {body}"

    def test_chat_therapist(self, s):
        r = s.post(f"{API}/personas/chat",
                   json={"persona_id": "th_001", "session_id": "TEST_t", "text": "I keep hiking my shoulder"},
                   timeout=60)
        assert r.status_code == 200, r.text
        reply = r.json().get("reply") or r.json().get("text") or r.json().get("message") or ""
        assert len(reply) > 5

    def test_chat_history(self, s):
        r = s.get(f"{API}/personas/chat/history",
                  params={"persona_id": "pt_001", "session_id": "TEST_p"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        turns = data.get("turns") or data.get("history") or data.get("messages") or []
        assert isinstance(turns, list)
        assert len(turns) >= 1, f"expected saved turns: {data}"

    def test_chat_invalid_persona_404(self, s):
        r = s.post(f"{API}/personas/chat",
                   json={"persona_id": "bogus_999", "session_id": "TEST_x", "text": "hi"},
                   timeout=20)
        assert r.status_code == 404


# Reminders
class TestReminders:
    def test_reminders_status(self, s):
        r = s.get(f"{API}/reminders/status", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("days_since_assessment", "exercise_overdue", "assessment_overdue",
                  "daily_reminder_text", "weekly_reminder_text"):
            assert k in d, f"missing key {k} in {d}"
        assert isinstance(d["exercise_overdue"], bool)
        assert isinstance(d["assessment_overdue"], bool)


# Stories (regression)
class TestStories:
    def test_list_stories(self, s):
        r = s.get(f"{API}/community/stories", timeout=20)
        assert r.status_code == 200
        data = r.json()
        stories = data.get("stories") if isinstance(data, dict) else data
        assert isinstance(stories, list) and len(stories) > 0

    def test_post_story(self, s):
        payload = {"author": "TEST_user", "title": "TEST_title", "body": "TEST hopeful body text"}
        r = s.post(f"{API}/community/stories", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text


# Regression: previous endpoints
class TestRegression:
    def test_root(self, s):
        r = s.get(f"{API}/", timeout=20)
        assert r.status_code == 200

    def test_tasks(self, s):
        r = s.get(f"{API}/assessment/tasks", timeout=20)
        assert r.status_code == 200
        assert len(r.json().get("tasks", [])) == 7
