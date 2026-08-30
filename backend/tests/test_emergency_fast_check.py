import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_emergency_fast_test")

from backend import server
from backend.fast_screening import evaluate_fast_screen


FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"


async def _signed_in_user(_headers):
    return {"id": "u_fast_check", "consent": {"health_data_consent": True}}


def test_any_observed_or_uncertain_fast_sign_triggers_demo_911_handoff():
    face = evaluate_fast_screen({"face": "yes", "arms": "no", "speech": "no"})
    uncertain = evaluate_fast_screen({"face": "no", "arms": "no", "speech": "unsure"})
    automated = evaluate_fast_screen(
        {"face": "no", "arms": "no", "speech": "no"},
        {"arms": {"positive": True}},
    )

    assert face["call_999"] is True
    assert face["algorithm_version"] == "rehyn-fast-1.5-openai-stt"
    assert face["demo_call_911"] is True
    assert face["emergency_call_mode"] == "simulation"
    assert face["observed_signs"] == ["face"]
    assert uncertain["call_999"] is True
    assert uncertain["uncertain_signs"] == ["speech"]
    assert automated["call_999"] is True
    assert automated["observed_signs"] == ["arms"]

    automatic_decision = evaluate_fast_screen(
        {},
        {
            "face": {"decision": "no"},
            "arms": {"decision": "no"},
            "speech": {"decision": "unsure"},
        },
    )
    assert automatic_decision["call_999"] is True
    assert automatic_decision["uncertain_signs"] == ["speech"]


def test_three_clear_negatives_never_claim_the_patient_is_fine():
    result = evaluate_fast_screen({"face": "no", "arms": "no", "speech": "no"})

    assert result["call_999"] is False
    assert result["demo_call_911"] is False
    assert result["status"] == "no_fast_signs_identified"
    assert "cannot rule out" in result["message"]
    assert "patient is fine" not in result["message"].lower()


def test_fast_runner_and_audit_endpoint_apply_the_same_rule(monkeypatch):
    events = []
    monkeypatch.setattr(server, "_user_from_header", _signed_in_user)
    monkeypatch.setattr(server, "_record_alira_action", lambda *args, **kwargs: events.append((args, kwargs)))

    with TestClient(server.app) as client:
        runner = client.get("/api/emergency/fast-runner")
        vision_bundle = client.get("/vendor/mediapipe/vision_bundle.mjs")
        face_model = client.get("/vendor/mediapipe/models/face_landmarker.task")
        result = client.post(
            "/api/emergency/fast-check",
            json={
                "answers": {"face": "no", "arms": "yes", "speech": "no"},
                "automated": {
                    "arms": {"available": True, "positive": True, "metric": 0.7},
                    "speech": {"available": True, "positive": False, "transcript": "private words"},
                },
                "source": "guided_fast",
            },
        )

    assert runner.status_code == 200
    assert runner.headers["content-type"].startswith("text/html")
    assert vision_bundle.status_code == 200
    assert "javascript" in vision_bundle.headers["content-type"]
    assert len(vision_bundle.content) > 100_000
    assert face_model.status_code == 200
    assert len(face_model.content) > 3_000_000
    assert "Emergency FAST check" in runner.text
    assert "Alira automatic check" in runner.text
    assert "Please smile and hold" in runner.text
    assert "Raise both arms and hold" in runner.text
    assert "Repeat the phrase aloud" in runner.text
    assert "Begin automatic FAST check" in runner.text
    assert "Speech · OpenAI transcription" in runner.text
    assert "OpenAI speech-to-text is processing the phrase" in runner.text
    assert "answerButtons" not in runner.text
    assert "chooseAnswer" not in runner.text
    assert 'data-answer="yes"' not in runner.text
    assert 'data-answer="no"' not in runner.text
    assert "finalizeFace" in runner.text
    assert "finalizeArms" in runner.text
    assert "startSpeechCheck" in runner.text
    assert "MediaRecorder" in runner.text
    assert 'fetch("/api/stt/transcribe"' in runner.text
    assert "SPEECH_WINDOW_MS=15000" in runner.text
    assert "SPEECH_SILENCE_MS=1300" in runner.text
    assert "SPEECH_MIN_TALK_MS=900" in runner.text
    assert "startSpeechVoiceMonitor" in runner.text
    assert "stopSpeechVoiceMonitor" in runner.text
    assert "getFloatTimeDomainData" in runner.text
    assert "Rehyn records for up to 15 seconds" not in runner.text
    assert "Alira stops listening automatically" in runner.text
    assert "audio/webm;codecs=opus" in runner.text
    assert "audio/ogg;codecs=opus" in runner.text
    assert "audio/mp4" in runner.text
    assert "finalizeSpeechWindow" not in runner.text
    assert "window.SpeechRecognition" not in runner.text
    assert "window.webkitSpeechRecognition" not in runner.text
    assert "isCompleteSpeechCandidate" in runner.text
    assert 'words.includes("today")' in runner.text
    assert "pauseForIncompleteSpeech" in runner.text
    assert 'data-testid="fast-speech-retry"' in runner.text
    assert 'data-testid="fast-speech-unable"' in runner.text
    assert "No emergency result has been decided" in runner.text
    assert "A technical failure will pause the check without deciding a medical result" in runner.text
    assert "Rehyn does not retain the audio" in runner.text
    transcription_function = runner.text.split("async function transcribeSpeechRecording", 1)[1].split(
        "async function startSpeechCheck", 1
    )[0]
    transcription_failure_handler = transcription_function.split("}catch(error){", 1)[1].split("}", 1)[0]
    assert "pauseForIncompleteSpeech" in transcription_failure_handler
    assert "finishSpeech(" not in transcription_failure_handler
    assert "Call 911 now" in runner.text
    assert "Simulating a 911 call" in runner.text
    assert "No emergency call has been placed" in runner.text
    assert 'window.location.href="tel:' not in runner.text
    assert "No FAST signs identified" in runner.text
    assert result.status_code == 200
    assert result.json()["call_999"] is True
    assert result.json()["demo_call_911"] is True
    assert result.json()["emergency_call_mode"] == "simulation"
    assert events[0][1]["details"]["raw_video_saved"] is False
    assert events[0][1]["details"]["raw_audio_saved"] is False
    assert events[0][1]["details"]["automated"]["speech"].get("transcript") is None
    assert events[0][1]["details"]["automated"]["speech"]["provider"] == "unknown"
    assert events[0][1]["details"]["automated"]["speech"]["recording_retained"] is False


def test_stt_endpoint_uses_openai_transcribe_without_writing_audio(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="The sky is blue today")

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=FakeTranscriptions()),
    )
    monkeypatch.setattr(server, "openai_tts_client", fake_client)
    monkeypatch.setattr(server, "STT_MODEL", "gpt-transcribe")

    with TestClient(server.app) as client:
        response = client.post(
            "/api/stt/transcribe",
            files={"file": ("fast-speech.webm", b"short in-memory audio", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "The sky is blue today",
        "provider": "openai",
        "model": "gpt-transcribe",
        "recording_retained": False,
    }
    assert captured["model"] == "gpt-transcribe"
    assert captured["language"] == "en"
    assert captured["response_format"] == "json"
    assert captured["file"] == (
        "fast-speech.webm",
        b"short in-memory audio",
        "audio/webm",
    )


def test_emergency_entry_is_prominent_and_alira_can_open_it():
    tabs = (FRONTEND_ROOT / "app" / "(tabs)" / "_layout.tsx").read_text(encoding="utf-8")
    home = (FRONTEND_ROOT / "app" / "(tabs)" / "index.tsx").read_text(encoding="utf-8")
    navigation = (FRONTEND_ROOT / "src" / "aliraNavigation.ts").read_text(encoding="utf-8")
    emergency = (FRONTEND_ROOT / "app" / "(tabs)" / "emergency.tsx").read_text(encoding="utf-8")

    assert 'tabBarButtonTestID: "tab-emergency-fast"' in tabs
    assert 'testID="home-emergency-fast"' in home
    assert 'emergency_fast_check: { label: "Emergency FAST check"' in navigation
    assert 'testID="emergency-fast-webview"' in emergency
    assert 'message.type === "demo_911_started"' in emergency
    assert "openEmergencyDialer" not in emergency
