from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = ROOT / "frontend"


def test_text_and_voice_alira_expose_a_user_confirmed_999_action():
    chat = (FRONTEND_ROOT / "app" / "(tabs)" / "chat.tsx").read_text(encoding="utf-8")
    voice = (FRONTEND_ROOT / "app" / "alira-call.tsx").read_text(encoding="utf-8")
    server = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")

    assert "emergency_call_available" in chat
    assert "<EmergencyCallButton compact />" in chat
    assert voice.count("<EmergencyCallButton compact />") >= 2
    assert "emergency_call_available: bool = False" in server
    assert 'direct_safety.get("offer_call_999")' in server
