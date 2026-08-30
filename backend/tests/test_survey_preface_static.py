from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_visual_check_in_entry_points_show_the_preface_before_questions():
    modal = read("frontend/src/components/SurveyPrefaceModal.tsx")
    daily_card = read("frontend/src/components/DailyCheckInCard.tsx")
    chat = read("frontend/app/(tabs)/chat.tsx")

    assert "A few short questions about how you have been getting on." in modal
    assert "Every question is optional and you can stop at any point." in modal
    assert "Skipping the check in does not change anything about your plan or your access to Rehyn." in modal
    assert "In an emergency, call 999." in modal
    assert "<SurveyPrefaceModal" in daily_card
    assert 'case "survey":' in daily_card
    assert "setShowPreface(true)" in daily_card
    assert "<SurveyPrefaceModal" in chat


def test_chat_and_realtime_paths_cannot_soften_a_saved_safety_response():
    server = read("backend/server.py")
    realtime = read("frontend/app/alira-call.tsx")

    assert "survey_preface_presented" in server
    assert "reply_text = forced_safety_reply" in server
    assert "safety_response_presented" in server
    assert "Say this safety message exactly before anything else" in realtime
    assert "Every question is optional" in server
