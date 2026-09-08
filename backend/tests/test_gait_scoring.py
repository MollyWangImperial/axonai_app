import asyncio
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from starlette.requests import Request

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_gait_scoring_test")

from backend import server
from backend.assessment_quality import score_assessment
from backend.gait_scoring import score_gait_features
from backend.gait_video_analysis import LANDMARK, _body_normalized_landmarks_2d


def _payload(*, left_lengths=None, right_lengths=None, times=None, quality=None, camera_method="body_centric_2d_background_ransac"):
    left_lengths = left_lengths or [0.46, 0.45]
    right_lengths = right_lengths or [0.45, 0.44]
    times = times or [0.0, 0.5, 1.0, 1.5]
    lengths = [left_lengths[0], right_lengths[0], left_lengths[-1], right_lengths[-1]]
    events = [
        {"side": "left" if index % 2 == 0 else "right", "time_s": time, "step_length_proxy_leg_ratio": lengths[index]}
        for index, time in enumerate(times)
    ]
    return {
        "status": "completed",
        "analysis_method": "test_body_centric",
        "camera_motion_handling": camera_method,
        "quality": quality or {
            "detected_frames": 90,
            "tracking_coverage": 0.98,
            "full_body_visibility": 0.92,
            "distal_visibility": 0.90,
            "multi_person_ratio": 0.0,
        },
        "features": {
            "step_events": events,
            "left_swing_knee_flexion_deg": 48.0,
            "right_swing_knee_flexion_deg": 46.0,
            "foot_clearance_reliable": False,
            "trunk_lateral_excursion_deg": 6.0,
            "trunk_measurement_reliable": True,
        },
        "provenance": {"source_video_id": "video-l6"},
    }


def test_balanced_gait_scores_high_and_exposes_weighted_components():
    result = score_gait_features(_payload())

    assert result["status"] == "scored"
    assert result["score"] >= 90
    assert result["summary"]["step_count"] == 4
    assert result["components"]["step_length_proxy_symmetry"]["weight"] == 25
    assert result["components"]["step_time_symmetry"]["weight"] == 20


def test_asymmetric_steps_score_lower_than_balanced_steps():
    balanced = score_gait_features(_payload())
    asymmetric = score_gait_features(_payload(
        left_lengths=[0.46, 0.45],
        right_lengths=[0.22, 0.20],
        times=[0.0, 0.42, 1.16, 1.58],
    ))

    assert asymmetric["status"] == "scored"
    assert asymmetric["score"] < balanced["score"]
    assert asymmetric["components"]["step_length_proxy_symmetry"]["score"] < 25


def test_camera_or_tracking_failures_abstain_instead_of_assigning_points():
    unsupported = score_gait_features(_payload(camera_method="raw_screen_displacement"))
    low_quality = score_gait_features(_payload(quality={
        "detected_frames": 18,
        "tracking_coverage": 0.40,
        "full_body_visibility": 0.20,
        "distal_visibility": 0.20,
        "multi_person_ratio": 0.0,
    }))

    assert unsupported["status"] == "unscorable"
    assert unsupported["score"] is None
    assert "camera_motion_not_compensated" in unsupported["reason_codes"]
    assert low_quality["status"] == "unscorable"
    assert low_quality["score"] is None
    assert "feet_not_visible_enough" in low_quality["reason_codes"]


def test_browser_body_normalized_2d_evidence_uses_the_same_score_weights():
    result = score_gait_features(_payload(camera_method="body_centric_2d_browser"))

    assert result["status"] == "scored"
    assert result["score"] >= 90


def test_browser_2d_evidence_must_match_the_saved_video_and_exclude_3d():
    candidate = _payload(camera_method="body_centric_2d_browser")
    candidate.update({
        "analysis_method": "mediapipe_browser_body_centric_2d_v1",
        "coordinate_frame": "pelvis_centered_leg_normalized_2d",
    })
    candidate["quality"]["sampled_frames"] = 40
    candidate["quality"]["detected_frames"] = 40
    candidate["provenance"].update({
        "processing_location": "patient_browser",
        "uses_3d_reconstruction": False,
    })

    accepted = server._validated_browser_gait_evidence(candidate, "video-l6", 3000)
    assert accepted is not None
    assert server._validated_browser_gait_evidence(candidate, "another-video", 3000) is None

    candidate["provenance"]["uses_3d_reconstruction"] = True
    assert server._validated_browser_gait_evidence(candidate, "video-l6", 3000) is None


def test_settings_walking_video_endpoint_scores_without_saving_an_assessment(monkeypatch):
    candidate = _payload(camera_method="body_centric_2d_browser")
    candidate.update({
        "analysis_method": "mediapipe_browser_body_centric_2d_v1",
        "coordinate_frame": "pelvis_centered_leg_normalized_2d",
    })
    candidate["quality"].update({"sampled_frames": 40, "detected_frames": 40})
    candidate["provenance"].update({
        "source_video_id": "settings-walking-video-test",
        "processing_location": "patient_browser",
        "uses_3d_reconstruction": False,
    })

    async def signed_in(*_args):
        return {"id": "walking-test-patient"}

    monkeypatch.setattr(server, "_user_from_header", signed_in)
    request = Request({"type": "http", "method": "POST", "path": "/api/analysis/gait-2d/test-score", "headers": []})
    payload = server.Gait2DTestScoreRequest(duration_ms=3000, evidence=server.GaitStageResultSubmit(**candidate))

    result = asyncio.run(server.score_gait_2d_for_testing(payload, request))

    assert result["testing_only"] is True
    assert result["saved_to_assessment"] is False
    assert result["gait_analysis"]["status"] == "scored"
    assert result["gait_analysis"]["score"] >= 90


def test_assessment_submit_scores_video_bound_browser_2d_evidence(monkeypatch):
    stored = []
    user = {"id": "walking-patient", "email": "walk@example.com", "profile": {}}
    candidate = _payload(camera_method="body_centric_2d_browser")
    candidate.update({
        "analysis_method": "mediapipe_browser_body_centric_2d_v1",
        "coordinate_frame": "pelvis_centered_leg_normalized_2d",
    })
    candidate["quality"].update({"sampled_frames": 40, "detected_frames": 40})
    candidate["provenance"].update({
        "processing_location": "patient_browser",
        "uses_3d_reconstruction": False,
    })

    async def signed_in(*_args):
        return user

    async def access(*_args):
        return {"trigger": "initial", "task_ids": ["L6"], "issue_report_id": None}

    async def noop(*_args, **_kwargs):
        return None

    async def videos(*_args):
        return {"L6": {"id": "video-l6", "storage": "r2", "task_id": "L6"}}

    async def insert(doc):
        stored.append(deepcopy(doc))

    monkeypatch.setattr(server, "_user_from_header", signed_in)
    monkeypatch.setattr(server, "_assessment_access_plan", access)
    monkeypatch.setattr(server, "consume_credits", noop)
    monkeypatch.setattr(server, "_latest_task_videos", videos)
    monkeypatch.setattr(server, "_record_initial_assessment_completion", noop)
    monkeypatch.setattr(server, "_mark_functional_issue_assessed", noop)
    monkeypatch.setattr(server, "_record_alira_action", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "db", SimpleNamespace(assessments=SimpleNamespace(insert_one=insert)))
    monkeypatch.setattr(server, "LOCAL_GPU_WORKER_URL", "")
    request = Request({"type": "http", "method": "POST", "path": "/api/assessment/submit", "headers": []})
    result = server.TaskResult(
        task_id="L6",
        completed_steps=3,
        total_steps=3,
        duration_ms=3000,
        steps=[
            server.TaskStepResult(step_id=f"L6-S{index}", completed=True, duration_ms=1000)
            for index in range(1, 4)
        ],
        metrics={"walking_video_role": "gait_scoring_input", "gait_2d_evidence": candidate},
    )
    payload = server.AssessmentSubmit(
        task_results=[result],
        assessment_package="initial",
        assigned_task_ids=["L6"],
    )

    saved = asyncio.run(server.submit_assessment(payload, request))

    gait = stored[0]["model_analysis"]["gait_stage"]
    assert gait["status"] == "scored"
    assert gait["score"] == saved.metrics["task_quality"]["modules"]["lower_limb"]["score"]
    assert stored[0]["task_results"][0]["metrics"]["gait_analysis"]["score"] == gait["score"]
    assert "gait_2d_evidence" not in stored[0]["task_results"][0]["metrics"]


def test_status_reports_2d_gait_ready_without_the_optional_gpu_worker(monkeypatch):
    monkeypatch.setattr(server, "LOCAL_GPU_WORKER_URL", "")

    status = asyncio.run(server.local_gpu_status())

    assert status["status"] == "not_configured"
    assert status["gait_2d"] == {
        "status": "ready",
        "analysis_method": "mediapipe_browser_body_centric_2d_v1",
        "camera_motion_handling": "body_centric_2d_browser",
        "uses_3d_reconstruction": False,
    }


def test_backend_gait_score_becomes_the_lower_limb_module_score():
    gait = score_gait_features(_payload())
    result = score_assessment(
        [{"task_id": "L6", "duration_ms": 3000, "metrics": {"gait_analysis": gait}}],
        server.ASSESSMENT_RUBRICS,
        ["L6"],
    )

    assert result["modules"]["lower_limb"]["score"] == gait["score"]
    assert result["tasks"][0]["score"] == gait["score"]


def test_worker_callback_persists_gait_results_to_the_canonical_metrics_field():
    source = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    route = source[
        source.index('async def save_gait_stage_results('):
        source.index('@api_router.post("/assessment/{assessment_id}/model-stage-results")')
    ]

    assert '"task_results": updated_task_results' in route
    assert '"metrics": functional_metrics' in route
    assert 'item["metrics"] = updates["metrics"]' in route


def test_body_coordinates_are_invariant_to_2d_camera_pan_roll_and_zoom():
    pose = np.zeros((33, 2), dtype=float)
    pose[LANDMARK["left_shoulder"]] = [-0.25, 1.0]
    pose[LANDMARK["right_shoulder"]] = [0.25, 1.0]
    pose[LANDMARK["left_hip"]] = [-0.18, 0.0]
    pose[LANDMARK["right_hip"]] = [0.18, 0.0]
    pose[LANDMARK["left_knee"]] = [-0.18, -0.45]
    pose[LANDMARK["right_knee"]] = [0.18, -0.45]
    pose[LANDMARK["left_ankle"]] = [-0.18, -0.90]
    pose[LANDMARK["right_ankle"]] = [0.18, -0.82]
    angle = np.deg2rad(27)
    rotation = np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)],
    ])
    camera_moved = pose @ rotation.T * 1.7 + np.array([2.0, -0.7])

    original, _ = _body_normalized_landmarks_2d(pose)
    transformed, _ = _body_normalized_landmarks_2d(camera_moved)

    np.testing.assert_allclose(transformed, original, atol=1e-8)
