"""Iteration 4 backend tests:
- Friendly functional issue labels
- Therapists list & match
- Community stories list & create
- Hope chat (message, history, proactive)
- Regression: assessment, tts, runners
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 60


# ---------- Friendly labels in /assessment/submit ----------
def _all_partial_payload():
    """All 7 tasks done with completed_steps < total_steps (partial) so EVERY rule triggers."""
    task_results = []
    for tid in ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]:
        task_results.append({
            "task_id": tid,
            "completed_steps": 1,
            "total_steps": 3,
            "duration_ms": 1000,
            "steps": [],
            "metrics": {"trunk_lean_deg": 20, "shoulder_hike": True},
        })
    return {"task_results": task_results, "affected_side": "right"}


def test_submit_returns_friendly_labels():
    r = requests.post(f"{API}/assessment/submit", json=_all_partial_payload(), timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    body = r.json()
    labels = [i["label"] for i in body["functional_issues"]]
    # Must use friendly language, not clinical
    assert "Difficulty reaching forward" in labels, labels
    assert "Difficulty lifting your arm overhead" in labels, labels
    # Must NOT contain clinical phrasing
    joined = " | ".join(labels)
    assert "Reduced forward reach" not in joined
    assert "Limited shoulder flexion" not in joined
    # Verify persistence
    aid = body["id"]
    r2 = requests.get(f"{API}/assessment/{aid}", timeout=TIMEOUT)
    assert r2.status_code == 200
    assert r2.json()["id"] == aid


# ---------- Therapists ----------
def test_therapists_list_has_six_with_required_fields():
    r = requests.get(f"{API}/therapists", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    ts = r.json()["therapists"]
    assert len(ts) == 6, f"expected 6, got {len(ts)}"
    for t in ts:
        for k in ("id", "name", "specialties", "rating", "photo"):
            assert k in t, f"missing {k} in {t}"


def test_therapists_match_top_is_maya_okafor():
    r = requests.get(f"{API}/therapists/match", params={"issues": "HAND_OPENING,PINCH_IMPAIRED"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    matches = r.json()["matches"]
    assert len(matches) > 0
    top = matches[0]
    assert "Maya Okafor" in top["therapist"]["name"], top
    # Sorted desc by score
    scores = [m["score"] for m in matches]
    assert scores == sorted(scores, reverse=True)


# ---------- Community stories ----------
def test_stories_list_has_at_least_six_seeds():
    r = requests.get(f"{API}/community/stories", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    stories = r.json()["stories"]
    assert len(stories) >= 6
    for s in stories[:6]:
        for k in ("id", "author", "title", "body", "likes"):
            assert k in s, f"missing {k}"
        assert "_id" not in s


def test_create_story_returns_no_mongo_id():
    payload = {"author": "TEST_Pytest", "title": "TEST_iter4 story", "body": "this is a test story body."}
    r = requests.post(f"{API}/community/stories", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "_id" not in doc, f"mongodb _id leaked: {doc}"
    for k in ("id", "author", "title", "body", "likes"):
        assert k in doc
    assert doc["author"] == "TEST_Pytest"
    # GET to verify persistence
    r2 = requests.get(f"{API}/community/stories", timeout=TIMEOUT)
    assert any(s["id"] == doc["id"] for s in r2.json()["stories"])


# ---------- Hope chat ----------
@pytest.fixture(scope="module")
def chat_session():
    return "TEST_sess_" + uuid.uuid4().hex[:8]


def test_chat_message_returns_warm_reply(chat_session):
    r = requests.post(
        f"{API}/chat/message",
        json={"session_id": chat_session, "text": "Hi Hope, my name is Sam. I'm scared about my recovery."},
        timeout=90,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    assert j["session_id"] == chat_session
    assert isinstance(j["text"], str) and len(j["text"]) > 5
    assert j["turns"] >= 2


def test_chat_message_keeps_context(chat_session):
    # Send a second message that references the first
    r = requests.post(
        f"{API}/chat/message",
        json={"session_id": chat_session, "text": "Do you remember my name?"},
        timeout=90,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # Should be a coherent reply (we can't strictly assert it knows the name but should have grown turns)
    assert j["turns"] >= 4
    assert len(j["text"]) > 3


def test_chat_history_returns_turns(chat_session):
    r = requests.get(f"{API}/chat/history", params={"session_id": chat_session}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["session_id"] == chat_session
    assert isinstance(j["turns"], list)
    assert len(j["turns"]) >= 4
    roles = [t["role"] for t in j["turns"]]
    assert "user" in roles and "assistant" in roles


def test_chat_proactive_returns_text():
    r = requests.post(
        f"{API}/chat/proactive",
        json={"session_id": "TEST_proactive_" + uuid.uuid4().hex[:6], "text": ""},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "text" in j and isinstance(j["text"], str) and len(j["text"]) > 5


# ---------- Regression: previous endpoints ----------
def test_get_tasks_still_works():
    r = requests.get(f"{API}/assessment/tasks", timeout=TIMEOUT)
    assert r.status_code == 200
    assert len(r.json()["tasks"]) == 7


def test_history_endpoint_still_works():
    r = requests.get(f"{API}/assessment/history", timeout=TIMEOUT)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_tts_health_still_works():
    r = requests.get(f"{API}/tts/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert "ok" in r.json()


def test_pose_runner_html_served():
    r = requests.get(f"{API}/pose/runner", timeout=TIMEOUT)
    assert r.status_code == 200
    assert "<html" in r.text.lower()


def test_rehab_runner_html_served():
    r = requests.get(f"{API}/rehab/runner", params={"exercise_id": "ex_reach"}, timeout=TIMEOUT)
    assert r.status_code == 200
    assert "<html" in r.text.lower()
