import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = (ROOT / "backend" / "server.py").read_text(encoding="utf-8")
CALL_SCREEN = (ROOT / "frontend" / "app" / "alira-call.tsx").read_text(encoding="utf-8")
NAVIGATION = (ROOT / "frontend" / "src" / "aliraNavigation.ts").read_text(encoding="utf-8")
JOURNEY = (ROOT / "frontend" / "app" / "(tabs)" / "journey.tsx").read_text(encoding="utf-8")


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


def test_realtime_registers_the_same_allowlisted_destinations_as_the_client():
    server_block = SERVER.split("ALIRA_NAVIGATION_DESTINATIONS = (", 1)[1].split(
        ")\nALIRA_NAVIGATION_TOOL", 1
    )[0]
    client_block = NAVIGATION.split("ALIRA_NAVIGATION_DESTINATIONS = {", 1)[1].split(
        "} as const", 1
    )[0]
    server_destinations = set(re.findall(r'^\s{4}"([a-z_]+)",$', server_block, re.MULTILINE))
    client_destinations = set(re.findall(r"^\s{2}([a-z_]+): \{", client_block, re.MULTILINE))

    assert server_destinations == client_destinations
    assert {"progress", "movement_snapshot", "movement_map", "rehab_plan", "guided_exercise"} <= server_destinations
    assert '"tools": [ALIRA_NAVIGATION_TOOL, ALIRA_RECORD_CHECKIN_TOOL]' in SERVER
    assert '"tool_choice": "auto"' in SERVER
    assert '"additionalProperties": False' in SERVER


def test_web_call_executes_navigation_tool_and_returns_function_output():
    realtime = CALL_SCREEN.split("function RealtimeWebCall()", 1)[1].split(
        "const realtimeStyles", 1
    )[0]
    assert 'event.type === "response.function_call_arguments.done"' in realtime
    assert 'event.name !== "navigate_app"' in realtime
    assert 'type: "function_call_output"' in realtime
    assert "resolveAliraNavigation(destination)" in realtime
    assert 'tool_choice: "none"' in realtime
    assert "completeNavigation(pending)" in realtime
    assert "deleteAccount" not in NAVIGATION


def test_web_call_can_save_an_adaptive_recovery_check_in():
    realtime = CALL_SCREEN.split("function RealtimeWebCall()", 1)[1].split(
        "const realtimeStyles", 1
    )[0]
    assert 'event.name !== "record_rehab_check_in"' in realtime
    assert 'authedFetch("/api/alira/check-ins"' in realtime
    assert 'source: "realtime_voice"' in realtime
    assert "next_exercise_action" in realtime


def test_result_navigation_uses_latest_assessment_and_journal_opens_composer():
    assert "fetchHistory()" in NAVIGATION
    assert "newestFirst(history)" in NAVIGATION
    assert "clinical_review_gate?.rehab_access" in NAVIGATION
    assert 'path: "/(tabs)/journey?action=new-journal"' in NAVIGATION
    assert 'action === "new-journal"' in JOURNEY
