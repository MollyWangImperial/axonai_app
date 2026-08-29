from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
CALL_SCREEN = (ROOT / "frontend" / "app" / "alira-call.tsx").read_text(encoding="utf-8")


def test_realtime_session_is_authenticated_and_server_side():
    route = SERVER.split('@api_router.post("/realtime/session")', 1)[1].split(
        '@api_router.post("/chat/message"', 1
    )[0]
    assert "_user_from_header" in route
    assert "https://api.openai.com/v1/realtime/calls" in route
    assert '"Authorization": f"Bearer {OPENAI_API_KEY}"' in route
    assert "OpenAI-Safety-Identifier" in route
    assert "hashlib.sha256" in route


def test_realtime_session_is_patient_friendly_and_interruptible():
    assert '"model": ALIRA_REALTIME_MODEL' in SERVER
    assert '"type": "semantic_vad"' in SERVER
    assert '"eagerness": "low"' in SERVER
    assert '"create_response": True' in SERVER
    assert '"interrupt_response": True' in SERVER
    assert '"model": "gpt-transcribe"' in SERVER


def test_web_call_uses_continuous_webrtc_instead_of_record_upload():
    realtime = CALL_SCREEN.split("function RealtimeWebCall()", 1)[1].split(
        "const realtimeStyles", 1
    )[0]
    assert "RTCPeerConnection" in realtime
    assert "getUserMedia" in realtime
    assert 'createDataChannel("oai-events")' in realtime
    assert 'authedFetch("/api/realtime/session"' in realtime
    assert 'type: "response.create"' in realtime
    assert "/api/stt/transcribe" not in realtime
    assert "No recording or send button" in CALL_SCREEN
