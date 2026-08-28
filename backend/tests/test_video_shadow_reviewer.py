import json

from backend.video_shadow_reviewer import ClinicalVideoShadowReviewer, _safe_json


def test_video_shadow_reviewer_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CLINICAL_SHADOW_REVIEW_ENABLED", raising=False)
    reviewer = ClinicalVideoShadowReviewer()
    assert reviewer.status()["status"] == "disabled"
    assert reviewer.analyze({})["status"] == "disabled"


def test_video_shadow_reviewer_requires_explicit_patient_consent(monkeypatch):
    monkeypatch.setenv("CLINICAL_SHADOW_REVIEW_ENABLED", "1")
    monkeypatch.setenv("CLINICAL_SHADOW_REVIEW_ALLOW_EXTERNAL_VIDEO", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    reviewer = ClinicalVideoShadowReviewer()
    result = reviewer.analyze(
        {"patient_parameters": {}, "video_sources": [{"task_id": "T1"}]}
    )
    assert result["status"] == "consent_required"


def test_safe_json_accepts_plain_or_fenced_json():
    assert _safe_json('{"observations": []}') == {"observations": []}
    assert _safe_json('```json\n{"observations": []}\n```') == {"observations": []}


def test_enabled_reviewer_sends_sampled_frames_and_parses_structured_result(
    monkeypatch,
):
    monkeypatch.setenv("CLINICAL_SHADOW_REVIEW_ENABLED", "1")
    monkeypatch.setenv("CLINICAL_SHADOW_REVIEW_ALLOW_EXTERNAL_VIDEO", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    reviewer = ClinicalVideoShadowReviewer()
    monkeypatch.setattr(
        reviewer,
        "_collect_frames",
        lambda sources, root: [
            {
                "task_id": "T1",
                "frame_index": "1",
                "data_url": "data:image/jpeg;base64,AA==",
            }
        ],
    )
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "review-response-1",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "observations": [],
                                        "quality_concerns": [],
                                        "urgent_review_flags": [],
                                    }
                                )
                            }
                        }
                    ],
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "backend.video_shadow_reviewer.urllib.request.urlopen", fake_urlopen
    )
    result = reviewer.analyze(
        {
            "patient_parameters": {"ai_video_review_consent": True},
            "video_sources": [{"task_id": "T1", "url": "https://example.test/video"}],
        }
    )
    assert result["status"] == "completed"
    assert result["reviewer"]["response_id"] == "review-response-1"
    assert result["tasks_reviewed"] == ["T1"]
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["payload"]["response_format"] == {"type": "json_object"}
