from fastapi import FastAPI, APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
from bson.errors import InvalidId
import os
import io
import base64
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Sequence
import uuid
import re
import asyncio
import httpx
import json
import hashlib
from datetime import datetime, timezone

try:
    from backend.rehab_assessment import (
        build_biomechanical_estimates,
        build_clinician_measure_summary,
        build_domain_assessments,
        modeling_specification,
    )
    from backend.clinical_measurement_form import build_clinical_measurement_form
    from backend.rehab_goals import build_rehab_goals
    from backend.rehab_packages import (
        BALANCE_TASKS_DATA,
        LOWER_LIMB_TASKS_DATA,
        attach_hand_failure_phenotypes,
    )
    from backend.muscle_diagnosis import build_muscle_activation_diagnosis
    from backend.assessment_fusion import build_analysis_pipeline, build_clinical_review_gate, build_survey_consistency
    from backend.biomechanics_pipeline import (
        aggregate_model_outputs,
        build_model_analysis_manifest,
        model_activation_report,
        patient_body_function_summary,
        patient_collection_summary,
        pending_model_activation_report,
        validate_model_outputs,
    )
    from backend.object_storage import task_video_object_storage
    from backend.patient_insights import build_patient_insights
    from backend.alira_care_orchestrator import (
        QUESTION_BANK as ALIRA_CARE_QUESTION_BANK,
        approved_question_ids,
        build_adaptive_care_plan,
        initial_assessment_recommendation,
        validate_check_in_answers,
    )
except ImportError:
    from rehab_assessment import (
        build_biomechanical_estimates,
        build_clinician_measure_summary,
        build_domain_assessments,
        modeling_specification,
    )
    from clinical_measurement_form import build_clinical_measurement_form
    from rehab_goals import build_rehab_goals
    from rehab_packages import (
        BALANCE_TASKS_DATA,
        LOWER_LIMB_TASKS_DATA,
        attach_hand_failure_phenotypes,
    )
    from muscle_diagnosis import build_muscle_activation_diagnosis
    from assessment_fusion import build_analysis_pipeline, build_clinical_review_gate, build_survey_consistency
    from biomechanics_pipeline import (
        aggregate_model_outputs,
        build_model_analysis_manifest,
        model_activation_report,
        patient_body_function_summary,
        patient_collection_summary,
        pending_model_activation_report,
        validate_model_outputs,
    )
    from object_storage import task_video_object_storage
    from patient_insights import build_patient_insights
    from alira_care_orchestrator import (
        QUESTION_BANK as ALIRA_CARE_QUESTION_BANK,
        approved_question_ids,
        build_adaptive_care_plan,
        initial_assessment_recommendation,
        validate_check_in_answers,
    )

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech
except Exception:
    OpenAITextToSpeech = None

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)
logger = logging.getLogger(__name__)

# MongoDB
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=1000, connectTimeoutMS=1000)
db = client[os.environ["DB_NAME"]]
task_video_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="task_videos")
TASK_VIDEO_MAX_BYTES = 35 * 1024 * 1024
TASK_VIDEO_FALLBACK_DIR = ROOT_DIR / ".task_videos"
LOCAL_STATE_DIR = ROOT_DIR / ".local_state"
LOCAL_USERS_FILE = LOCAL_STATE_DIR / "users.json"
LOCAL_TASK_PROGRESS_FILE = LOCAL_STATE_DIR / "task_progress.json"
LOCAL_CARE_STATE_FILE = LOCAL_STATE_DIR / "alira_care_state.json"


def _load_local_dict(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _persist_local_dict(path: Path, data: Dict[str, Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    temporary.replace(path)

# Local development fallback: keeps Expo phone testing usable when Docker/Mongo
# is not running. Mongo remains the source of truth whenever it is reachable.
LOCAL_USERS: Dict[str, Dict[str, Any]] = _load_local_dict(LOCAL_USERS_FILE)
LOCAL_TASK_PROGRESS: Dict[str, Dict[str, Any]] = _load_local_dict(LOCAL_TASK_PROGRESS_FILE)
LOCAL_CARE_STATE: Dict[str, Dict[str, Any]] = _load_local_dict(LOCAL_CARE_STATE_FILE)
LOCAL_ASSESSMENTS: List[Dict[str, Any]] = []
LOCAL_CHAT_SESSIONS: Dict[str, Dict[str, Any]] = {}

# OpenAI TTS: prefer direct OPENAI_API_KEY for local/dev, keep Emergent key as fallback.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
TTS_VOICE = os.environ.get("TTS_VOICE", "nova")  # warm/encouraging default
TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
ALIRA_CHAT_MODEL = os.environ.get("ALIRA_CHAT_MODEL", "gpt-4o-mini")
ALIRA_REALTIME_MODEL = os.environ.get("ALIRA_REALTIME_MODEL", "gpt-realtime-2.1").strip()
ALIRA_REALTIME_VOICE = os.environ.get("ALIRA_REALTIME_VOICE", "marin").strip()
ALIRA_NAVIGATION_DESTINATIONS = (
    "home",
    "journey",
    "progress",
    "assessment_history",
    "alira_chat",
    "journal_entry",
    "pain_check_in",
    "daily_reflection",
    "initial_assessment",
    "next_assessment",
    "profile",
    "care_facility",
    "settings",
    "survey_questions",
    "privacy_policy",
    "data_permissions",
    "terms_of_use",
    "personal_details",
    "care_circle",
    "account_security",
    "camera_permissions",
    "help_center",
    "contact_support",
    "function_summary",
    "movement_snapshot",
    "movement_map",
    "rehab_plan",
    "guided_exercise",
    "back",
)
ALIRA_NAVIGATION_TOOL = {
    "type": "function",
    "name": "navigate_app",
    "description": (
        "Navigate the signed-in patient to a safe, patient-facing Rehyn page. Call this whenever the "
        "patient asks to open, show, find, visit, go to, or be taken to an app function; do not merely "
        "describe menu steps. Use progress for progress tracking, assessment_history for prior assessments, "
        "function_summary for the latest function-at-a-glance page, movement_snapshot for the latest result, "
        "movement_map for the interactive anatomy map, rehab_plan or guided_exercise for the current plan, "
        "journal_entry to write a recovery note, and back to return to the previous page. This tool only opens "
        "pages. It never changes settings, deletes data, submits forms, or performs clinical actions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "enum": list(ALIRA_NAVIGATION_DESTINATIONS),
                "description": "The single Rehyn destination that best matches the patient's request.",
            },
        },
        "required": ["destination"],
        "additionalProperties": False,
    },
}
ALIRA_RECORD_CHECKIN_TOOL = {
    "type": "function",
    "name": "record_rehab_check_in",
    "description": (
        "Save the patient's answers from a short Alira recovery check-in. Ask only the questions listed in "
        "the current adaptive care plan, one at a time. Call this after the patient has answered; never infer "
        "an answer from silence, video, or an unrelated statement. The backend validates every value and "
        "returns the next safe survey, assessment, and exercise-plan action."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "properties": {
                    "sudden_change": {"type": "string", "enum": ["no", "yes"]},
                    "falls": {"type": "string", "enum": ["no", "near_fall", "fall_no_injury", "fall_with_injury"]},
                    "pain": {"type": "number", "minimum": 0, "maximum": 10},
                    "fatigue": {"type": "string", "enum": ["not_at_all", "a_little", "quite_a_bit", "a_lot"]},
                    "function_change": {"type": "string", "enum": ["much_easier", "a_little_easier", "about_the_same", "a_little_harder", "much_harder"]},
                    "exercise_tolerance": {"type": "string", "enum": ["not_tried", "too_easy", "about_right", "too_hard", "stopped_for_symptoms"]},
                    "goal_activity": {"type": "string", "enum": ["not_tried", "easier", "about_the_same", "harder", "needed_more_help"]},
                    "walking_confidence": {"type": "string", "enum": ["not_applicable", "confident", "a_little_unsure", "very_unsure", "needed_more_help"]},
                    "hand_use": {"type": "string", "enum": ["not_at_all", "a_little", "often", "most_activities"]},
                },
                "additionalProperties": False,
            },
            "patient_note": {
                "type": "string",
                "description": "Optional short verbatim note from the patient. Do not add a diagnosis or interpretation.",
            },
        },
        "required": ["answers"],
        "additionalProperties": False,
    },
}
ALIRA_CHAT_RECORD_CHECKIN_TOOL = {
    "type": "function",
    "function": {key: value for key, value in ALIRA_RECORD_CHECKIN_TOOL.items() if key != "type"},
}
ALIRA_CHAT_NAVIGATION_TOOL = {
    "type": "function",
    "function": {key: value for key, value in ALIRA_NAVIGATION_TOOL.items() if key != "type"},
}
ANALYSIS_WORKER_TOKEN = os.environ.get("ANALYSIS_WORKER_TOKEN", "").strip()
LOCAL_GPU_WORKER_URL = os.environ.get("LOCAL_GPU_WORKER_URL", "").strip().rstrip("/")
LOCAL_BACKEND_CALLBACK_URL = os.environ.get(
    "LOCAL_BACKEND_CALLBACK_URL", "http://127.0.0.1:8001/api"
).strip().rstrip("/")
ANALYSIS_WORKER_CF_CLIENT_ID = os.environ.get("ANALYSIS_WORKER_CF_CLIENT_ID", "").strip()
ANALYSIS_WORKER_CF_CLIENT_SECRET = os.environ.get("ANALYSIS_WORKER_CF_CLIENT_SECRET", "").strip()
openai_tts_client = OpenAI(api_key=OPENAI_API_KEY) if (OpenAI and OPENAI_API_KEY) else None
tts_client = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY) if (OpenAITextToSpeech and EMERGENT_LLM_KEY) else None

app = FastAPI()
api_router = APIRouter(prefix="/api")


# ============ Models ============
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


class TTSResponse(BaseModel):
    audio_b64: str
    text: str


class TaskStepResult(BaseModel):
    step_id: str
    completed: bool
    failure_code: Optional[str] = None
    duration_ms: int = 0
    metrics: Dict[str, Any] = Field(default_factory=dict)  # e.g., trunk_lean_deg, reach_ratio


class TaskResult(BaseModel):
    task_id: str
    completed_steps: int
    total_steps: int
    duration_ms: int = 0
    steps: List[TaskStepResult] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class AssessmentSubmit(BaseModel):
    task_results: List[TaskResult]
    affected_side: str = "right"  # "left" or "right"
    assessment_package: str = "upper_limb"
    assigned_task_ids: Optional[List[str]] = None
    patient_parameters: Dict[str, Any] = Field(default_factory=dict)
    musculoskeletal_outputs: Dict[str, Any] = Field(default_factory=dict)
    motion_data: Dict[str, Any] = Field(default_factory=dict)


class ModelResultSubmit(BaseModel):
    status: str
    per_task: List[Dict[str, Any]]


class GPUStageResultSubmit(BaseModel):
    status: str
    device: str = ""
    gpu_name: str = ""
    torch_version: str = ""
    cuda_runtime: Optional[str] = None
    model_version: str = ""
    stages: List[str] = Field(default_factory=list)
    tasks: Dict[str, Any] = Field(default_factory=dict)
    reporting_boundary: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None


class TaskVideoUploadComplete(BaseModel):
    video_id: str
    object_key: str
    package_id: str
    task_id: str
    duration_ms: int = 0
    content_type: str = "video/mp4"
    size_bytes: int = 0


class MusculoskeletalStageResultSubmit(BaseModel):
    status: str
    per_task: List[Dict[str, Any]] = Field(default_factory=list)
    kinematics: Dict[str, Any] = Field(default_factory=dict)
    solver_summary: Dict[str, Any] = Field(default_factory=dict)
    reporting_boundary: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None


class FunctionalIssue(BaseModel):
    code: str
    label: str
    description: str
    source: str
    severity: str  # mild | moderate | severe
    related_task: str
    related_step: Optional[str] = None
    phenotype_domain: Optional[str] = None


class RehabExercise(BaseModel):
    id: str
    name: str
    description: str
    sets: int
    reps: int
    frequency: str  # e.g. "Daily"
    targets_issue: str
    source: str
    selection_reason: Optional[str] = None
    safety_note: Optional[str] = None
    requires_clinician_confirmation: bool = True


class Assessment(BaseModel):
    id: str
    created_at: str
    affected_side: str
    assessment_package: str = "upper_limb"
    assigned_task_ids: List[str] = Field(default_factory=list)
    patient_parameters: Dict[str, Any] = Field(default_factory=dict)
    task_results: List[TaskResult]
    functional_issues: List[FunctionalIssue]
    rehab_plan: List[RehabExercise]
    domain_assessments: List[Dict[str, Any]] = Field(default_factory=list)
    clinician_measures: List[Dict[str, Any]] = Field(default_factory=list)
    biomechanical_estimates: List[Dict[str, Any]] = Field(default_factory=list)
    measurement_form: Dict[str, Any] = Field(default_factory=dict)
    rehabilitation_goals: Dict[str, Any] = Field(default_factory=dict)
    muscle_activation_diagnosis: Dict[str, Any] = Field(default_factory=dict)
    survey_consistency: Dict[str, Any] = Field(default_factory=dict)
    analysis_pipeline: Dict[str, Any] = Field(default_factory=dict)
    clinical_review_gate: Dict[str, Any] = Field(default_factory=dict)
    body_function_summary: Dict[str, Any] = Field(default_factory=dict)
    patient_insights: Dict[str, Any] = Field(default_factory=dict)


# ============ 7 Tasks: Step-by-step with voice prompts & on-screen target zones ============
# Coordinates are normalized [0..1] for the video frame: x left->right, y top->bottom.
# `landmark` references MediaPipe Pose landmarks: 15 = LEFT_WRIST, 16 = RIGHT_WRIST.
# `hold_ms` = required time within target zone to advance.
TASKS_DATA: List[Dict[str, Any]] = [
    {
        "id": "T1",
        "title": "Seated Forward Reach",
        "view": "Side view",
        "focus": "Reach distance, elbow extension, movement quality, trunk compensation",
        "steps": [
            {
                "id": "T1-S1",
                "voice": "Welcome. Sit upright with your affected hand on your lap. Slowly lift that hand forward to the first circle.",
                "target": {"x": 0.5, "y": 0.60, "r": 0.11, "landmark": "WRIST"},
                "hold_ms": 900,
                "caption": "Initiate the forward reach",
                "failure_phenotype": {"code": "REACH_INITIATION_IMPAIRED", "domain": "reach_initiation", "label": "Difficulty initiating a forward reach", "description": "The affected arm did not complete the initial movement away from the lap toward the first reach position.", "severity": "moderate", "source": "Fugl-Meyer UE; task-specific movement observation", "rehab_code": "REACH_INCOMPLETE"},
            },
            {
                "id": "T1-S2",
                "voice": "Now, slowly reach your affected arm forward, as far as you comfortably can, toward the bright circle in front of you. Keep your back straight and stay relaxed.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Reach forward to the target",
                "measure": ["reach_distance", "trunk_lean", "elbow_extension"],
                "failure_phenotype": {"code": "REACH_INCOMPLETE", "domain": "forward_reach_range", "label": "Limited forward reach", "description": "The affected arm initiated the movement but did not reach the forward target.", "severity": "moderate", "source": "Fugl-Meyer UE; ARAT", "rehab_code": "REACH_INCOMPLETE"},
            },
            {
                "id": "T1-S3",
                "voice": "Hold your hand steadily at the forward target for a moment.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Hold the reach steadily",
                "failure_phenotype": {"code": "REACH_ENDPOINT_UNSTABLE", "domain": "reach_endpoint_control", "label": "Unstable control at the reach target", "description": "The affected arm reached the forward area but did not remain stable at the endpoint.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "REACH_INCOMPLETE"},
            },
            {
                "id": "T1-S4",
                "voice": "Wonderful effort. Slowly bring your affected hand back to your lap.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "LAP_DYNAMIC"},
                "hold_ms": 1500,
                "caption": "Return to lap",
                "failure_phenotype": {"code": "REACH_RETURN_CONTROL_IMPAIRED", "domain": "reach_return_control", "label": "Difficulty controlling the return from a reach", "description": "The affected arm did not complete the controlled return from the forward target to the lap.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "REACH_INCOMPLETE"},
            },
        ],
    },
    {
        "id": "T2",
        "title": "Shoulder Flexion / Abduction Raise",
        "view": "Front view",
        "focus": "Shoulder elevation, shoulder hike, trunk lean, shoulder–elbow dissociation",
        "steps": [
            {
                "id": "T2-S1",
                "voice": "Next, raise your affected arm from your side toward the first circle at mid height.",
                "target": {"x": 0.5, "y": 0.55, "r": 0.11, "landmark": "WRIST"},
                "hold_ms": 1000,
                "caption": "Initiate the arm raise",
                "failure_phenotype": {"code": "SHOULDER_ELEVATION_INITIATION_IMPAIRED", "domain": "shoulder_elevation_initiation", "label": "Difficulty initiating an arm raise", "description": "The affected arm did not complete the initial antigravity raise from the side.", "severity": "moderate", "source": "Fugl-Meyer UE", "rehab_code": "SHOULDER_FLEX_LIMITED"},
            },
            {
                "id": "T2-S2",
                "voice": "Slowly raise your affected arm forward and upward, reaching toward the target above. Keep your shoulder relaxed and avoid hiking it up.",
                "target": {"x": 0.5, "y": 0.18, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Raise arm upward",
                "measure": ["shoulder_flexion_rom", "shoulder_hike", "trunk_lean"],
                "failure_phenotype": {"code": "SHOULDER_FLEX_LIMITED", "domain": "shoulder_elevation_range", "label": "Limited active arm elevation", "description": "The affected arm initiated the raise but did not reach the upper target.", "severity": "moderate", "source": "Fugl-Meyer UE", "rehab_code": "SHOULDER_FLEX_LIMITED"},
            },
            {
                "id": "T2-S3",
                "voice": "Hold your affected arm steadily at the upper target for a moment.",
                "target": {"x": 0.5, "y": 0.18, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Hold the raised arm steadily",
                "failure_phenotype": {"code": "SHOULDER_HOLD_UNSTABLE", "domain": "shoulder_hold_stability", "label": "Unstable control while holding the arm raised", "description": "The affected arm reached the upper area but did not remain stable there.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "SHOULDER_FLEX_LIMITED"},
            },
            {
                "id": "T2-S4",
                "voice": "Beautiful. Now, gently lower your affected arm back to your side.",
                "target": {"x": 0.5, "y": 0.85, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Lower arm",
                "failure_phenotype": {"code": "SHOULDER_LOWERING_IMPAIRED", "domain": "shoulder_lowering_control", "label": "Difficulty controlling arm lowering", "description": "The affected arm did not complete the controlled lowering movement back toward the side.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "SHOULDER_FLEX_LIMITED"},
            },
        ],
    },
    {
        "id": "T3",
        "title": "Hand to Mouth",
        "view": "Side view",
        "focus": "Hand-to-mouth function, coordination, movement quality, trunk compensation",
        "steps": [
            {
                "id": "T3-S1",
                "voice": "Let's bring your affected hand toward your mouth. First, lift it from your lap toward the circle at your chest.",
                "target": {"x": 0.5, "y": 0.48, "r": 0.11, "landmark": "CHEST"},
                "hold_ms": 1000,
                "caption": "Lift hand from lap toward chest",
                "failure_phenotype": {"code": "HAND_LIFT_INITIATION_IMPAIRED", "domain": "hand_to_mouth_initiation", "label": "Difficulty initiating the hand lift", "description": "The affected hand did not complete the initial lift from the lap toward the chest.", "severity": "moderate", "source": "MESUPES; task-specific movement observation", "rehab_code": "H2M_IMPAIRED"},
            },
            {
                "id": "T3-S2",
                "voice": "Now, slowly bring your hand up to your mouth, as if you were drinking from a cup. Keep your head still.",
                "target": {"x": 0.5, "y": 0.30, "r": 0.10, "landmark": "MOUTH"},
                "hold_ms": 1500,
                "caption": "Hand to mouth",
                "measure": ["elbow_flexion", "trunk_lean", "coordination"],
                "failure_phenotype": {"code": "H2M_IMPAIRED", "domain": "hand_to_mouth_transport", "label": "Difficulty bringing the hand to the mouth", "description": "The affected hand lifted from the lap but did not reach the mouth target.", "severity": "moderate", "source": "Chedoke-McMaster Stroke Assessment; MESUPES", "rehab_code": "H2M_IMPAIRED"},
            },
            {
                "id": "T3-S3",
                "voice": "Hold your affected hand steadily at your mouth for a moment.",
                "target": {"x": 0.5, "y": 0.30, "r": 0.10, "landmark": "MOUTH"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Hold hand steadily at mouth",
                "failure_phenotype": {"code": "HAND_TO_MOUTH_UNSTABLE", "domain": "hand_to_mouth_endpoint_control", "label": "Unstable hand-to-mouth endpoint control", "description": "The affected hand reached the mouth area but did not remain stable there.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "H2M_IMPAIRED"},
            },
            {
                "id": "T3-S4",
                "voice": "Great job. Lower your affected hand back to your lap.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "LAP_DYNAMIC"},
                "hold_ms": 1500,
                "caption": "Return to lap",
                "failure_phenotype": {"code": "HAND_TO_MOUTH_RETURN_IMPAIRED", "domain": "hand_to_mouth_return_control", "label": "Difficulty returning the hand from the mouth", "description": "The affected hand did not complete the controlled return from the mouth to the lap.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "H2M_IMPAIRED"},
            },
        ],
    },
    {
        "id": "T4",
        "title": "Grasp Cup and Move to Target",
        "view": "Front view",
        "focus": "Grasp, release, movement quality, endpoint control, trunk compensation",
        "advanced_marker_required": True,
        "advanced_label": "Advanced grasp-release with AxonAI marker",
        "recommended_objects": ["empty plastic cup", "soft ball", "foam cylinder", "small paper box"],
        "steps": [
            {
                "id": "T4-S1",
                "voice": "Reach with your affected hand toward the marked lightweight cup on the table.",
                "target": {"x": 0.30, "y": 0.65, "r": 0.10, "landmark": "WRIST", "icon": "cup"},
                "hold_ms": 1200,
                "caption": "Reach for the cup",
                "failure_phenotype": {"code": "OBJECT_REACH_IMPAIRED", "domain": "object_directed_reach", "label": "Difficulty reaching to an object", "description": "The affected hand did not reach the cup position.", "severity": "moderate", "source": "ARAT grasp subscale", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T4-S2",
                "voice": "Open your hand around the cup, then close your fingers to form a secure grasp.",
                "target": {"x": 0.30, "y": 0.65, "r": 0.11, "landmark": "HAND_CLOSED", "icon": "cup"},
                "hold_ms": 1200,
                "movement_required": False,
                "caption": "Form a grasp around the cup",
                "failure_phenotype": {"code": "GROSS_GRASP", "domain": "gross_grasp_acquisition", "label": "Difficulty forming a gross grasp", "description": "The affected hand reached the cup but did not form a secure grasp around it.", "severity": "moderate", "source": "ARAT grasp subscale", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T4-S3",
                "voice": "Lift the cup slightly and hold it steadily for a moment.",
                "target": {"x": 0.42, "y": 0.55, "r": 0.12, "landmark": "OBJECT_COUPLED", "icon": "cup"},
                "hold_ms": 1500,
                "caption": "Lift and hold the cup",
                "failure_phenotype": {"code": "GRASP_HOLD_UNSTABLE", "domain": "grasp_hold_stability", "label": "Unstable grasp while holding an object", "description": "The cup was grasped but was not lifted and held steadily with the affected hand.", "severity": "moderate", "source": "ARAT grasp subscale", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T4-S4",
                "voice": "Keep holding the cup and carefully move it across to the target on the other side.",
                "target": {"x": 0.70, "y": 0.65, "r": 0.12, "landmark": "OBJECT_COUPLED", "icon": "table"},
                "hold_ms": 1500,
                "caption": "Move cup across to target",
                "measure": ["endpoint_accuracy", "trunk_lean", "movement_smoothness"],
                "failure_phenotype": {"code": "OBJECT_TRANSPORT_IMPAIRED", "domain": "object_transport", "label": "Difficulty transporting a grasped object", "description": "The cup was grasped but was not transported to the opposite target while remaining coupled to the affected hand.", "severity": "moderate", "source": "ARAT grasp and grip subscales", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T4-S5",
                "voice": "Place the cup steadily inside the target area.",
                "target": {"x": 0.70, "y": 0.65, "r": 0.12, "landmark": "OBJECT_AT_TARGET", "icon": "table"},
                "hold_ms": 1000,
                "movement_required": False,
                "caption": "Place cup at the target",
                "failure_phenotype": {"code": "OBJECT_PLACEMENT_IMPAIRED", "domain": "object_placement", "label": "Difficulty placing an object accurately", "description": "The transported cup was not placed steadily inside the target area.", "severity": "mild", "source": "ARAT; task-specific movement observation", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T4-S6",
                "voice": "Now open your fingers, release the cup, and move your empty hand away.",
                "target": {"x": 0.70, "y": 0.65, "r": 0.12, "landmark": "OBJECT_RELEASED", "icon": "table"},
                "hold_ms": 1200,
                "movement_required": False,
                "caption": "Release the cup at the target",
                "failure_phenotype": {"code": "OBJECT_RELEASE_IMPAIRED", "domain": "object_release", "label": "Difficulty releasing an object", "description": "The cup reached the target but the affected hand did not open and separate from it.", "severity": "moderate", "source": "ARAT grasp subscale", "rehab_code": "GROSS_GRASP"},
            },
        ],
    },
    {
        "id": "T5",
        "title": "Open Hand, Form Grasp, Release",
        "view": "Front view",
        "focus": "Hand opening, wrist control, grasp, release",
        "advanced_marker_required": True,
        "advanced_label": "Advanced grasp-release with AxonAI marker",
        "recommended_objects": ["empty plastic cup", "soft ball", "foam cylinder", "small paper box"],
        "steps": [
            {
                "id": "T5-S1",
                "voice": "Raise your affected hand to chest height and hold it where the camera can see it clearly.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.10, "landmark": "CHEST"},
                "hold_ms": 1000,
                "caption": "Position hand at chest height",
                "failure_phenotype": {"code": "HAND_POSITIONING_IMPAIRED", "domain": "hand_task_positioning", "label": "Difficulty positioning the hand for a hand task", "description": "The affected hand did not reach the chest-height working position.", "severity": "moderate", "source": "Task-specific movement observation", "rehab_code": "HAND_OPENING"},
            },
            {
                "id": "T5-S2",
                "voice": "Open your affected hand as wide as you comfortably can.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN", "icon": "ball"},
                "hold_ms": 1200,
                "movement_required": False,
                "caption": "Open hand wide",
                "measure": ["hand_opening"],
                "failure_phenotype": {"code": "HAND_OPENING", "domain": "active_hand_opening", "label": "Difficulty opening the hand", "description": "The affected hand reached the working position but the fingers did not open sufficiently.", "severity": "moderate", "source": "Fugl-Meyer UE hand section", "rehab_code": "HAND_OPENING"},
            },
            {
                "id": "T5-S3",
                "voice": "Keep your hand open and steady for a moment.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN", "icon": "ball"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Hold the hand open",
                "failure_phenotype": {"code": "HAND_OPEN_HOLD_UNSTABLE", "domain": "hand_open_hold", "label": "Difficulty maintaining an open hand", "description": "The affected hand opened but did not remain open and steady.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "HAND_OPENING"},
            },
            {
                "id": "T5-S4",
                "voice": "Now slowly close your fingers as if forming a secure grasp around a soft ball.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_CLOSED", "icon": "ball"},
                "hold_ms": 1200,
                "movement_required": False,
                "caption": "Form a gross grasp",
                "failure_phenotype": {"code": "GROSS_GRASP_FORMATION_IMPAIRED", "domain": "gross_grasp_formation", "label": "Difficulty forming a gross grasp", "description": "The affected hand opened but did not close into a functional gross-grasp shape.", "severity": "moderate", "source": "Fugl-Meyer UE hand section; ARAT", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T5-S5",
                "voice": "Hold the grasp steadily for a moment.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_CLOSED", "icon": "ball"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Maintain the gross grasp",
                "failure_phenotype": {"code": "GRASP_MAINTENANCE_IMPAIRED", "domain": "gross_grasp_maintenance", "label": "Difficulty maintaining a gross grasp", "description": "The affected hand formed a grasp but did not maintain it steadily.", "severity": "moderate", "source": "Task-specific movement observation", "rehab_code": "GROSS_GRASP"},
            },
            {
                "id": "T5-S6",
                "voice": "Open your fingers again to release the grasp.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN", "icon": "ball"},
                "hold_ms": 1200,
                "movement_required": False,
                "caption": "Open hand to release",
                "failure_phenotype": {"code": "HAND_RELEASE_IMPAIRED", "domain": "active_hand_release", "label": "Difficulty reopening the hand to release", "description": "The affected hand formed a grasp but did not actively reopen to release it.", "severity": "moderate", "source": "Fugl-Meyer UE hand section; ARAT", "rehab_code": "HAND_OPENING"},
            },
        ],
    },
    {
        "id": "T6",
        "title": "Pinch Coin / Pen / Key",
        "view": "Front view",
        "focus": "Fine pinch (thumb to index finger)",
        "steps": [
            {
                "id": "T6-S1",
                "voice": "Hold your hand up in front of your chest, palm facing you.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Raise hand to chest",
                "failure_phenotype": {"code": "PINCH_POSITIONING_IMPAIRED", "domain": "pinch_task_positioning", "label": "Difficulty positioning the hand for pinch", "description": "The affected hand did not reach the working position needed for the pinch task.", "severity": "moderate", "source": "Task-specific movement observation", "rehab_code": "PINCH_IMPAIRED"},
            },
            {
                "id": "T6-S2",
                "voice": "Now, slowly touch the tip of your thumb to the tip of your index finger, as if picking up a small coin.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "PINCH", "icon": "coin"},
                "hold_ms": 1000,
                "movement_required": False,
                "caption": "Pinch thumb and index finger",
                "measure": ["pinch_grip"],
                "failure_phenotype": {"code": "PINCH_IMPAIRED", "domain": "thumb_index_opposition", "label": "Difficulty forming a thumb-index pinch", "description": "The affected thumb and index finger did not form the requested pinch position.", "severity": "mild", "source": "ARAT pinch subscale; Fugl-Meyer UE hand section", "rehab_code": "PINCH_IMPAIRED"},
            },
            {
                "id": "T6-S3",
                "voice": "Keep the thumb-index pinch steady for a moment.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "PINCH", "icon": "coin"},
                "hold_ms": 1500,
                "movement_required": False,
                "caption": "Hold the pinch steadily",
                "failure_phenotype": {"code": "PINCH_HOLD_UNSTABLE", "domain": "pinch_stability", "label": "Unstable thumb-index pinch", "description": "The affected hand formed a pinch but did not maintain it steadily.", "severity": "mild", "source": "ARAT pinch subscale", "rehab_code": "PINCH_IMPAIRED"},
            },
            {
                "id": "T6-S4",
                "voice": "Separate your thumb and index finger to release the pinch.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "PINCH_RELEASED", "icon": "coin"},
                "hold_ms": 1000,
                "movement_required": False,
                "caption": "Release the pinch",
                "failure_phenotype": {"code": "PINCH_RELEASE_IMPAIRED", "domain": "pinch_release", "label": "Difficulty releasing a pinch", "description": "The affected thumb and index finger formed a pinch but did not separate to release it.", "severity": "mild", "source": "Task-specific movement observation", "rehab_code": "PINCH_IMPAIRED"},
            },
        ],
    },
    {
        "id": "T7",
        "title": "Fold Towel (Two-Handed)",
        "view": "Front view",
        "focus": "Affected-side participation, bilateral coordination",
        "steps": [
            {
                "id": "T7-S1",
                "voice": "Our last task uses both hands together. Bring both hands up in front of you, around chest height.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS_APART"},
                "hold_ms": 1500,
                "caption": "Both hands up at chest",
                "failure_phenotype": {"code": "BILATERAL_INITIATION_IMPAIRED", "domain": "bilateral_initiation", "label": "Difficulty initiating a two-handed movement", "description": "Both hands did not reach the chest-height working position together.", "severity": "moderate", "source": "Bilateral arm training task observation", "rehab_code": "BILATERAL_NONUSE"},
            },
            {
                "id": "T7-S2",
                "voice": "Pretend you are holding the two corners of a towel. Bring both hands inward together until the corners meet in front of you.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS", "icon": "towel"},
                "hold_ms": 1400,
                "caption": "Bring both hands inward together",
                "measure": ["bilateral_symmetry", "affected_participation"],
                "failure_phenotype": {"code": "BILATERAL_NONUSE", "domain": "bilateral_inward_coordination", "label": "Limited affected-side participation in a two-handed movement", "description": "The two hands did not complete the inward towel-folding movement together.", "severity": "moderate", "source": "CIMT; bilateral arm training", "rehab_code": "BILATERAL_NONUSE"},
            },
            {
                "id": "T7-S3",
                "voice": "Now move both hands outward again while keeping them at the same height.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS_APART", "icon": "towel"},
                "hold_ms": 1500,
                "caption": "Move both hands outward together",
                "failure_phenotype": {"code": "BILATERAL_OUTWARD_CONTROL_IMPAIRED", "domain": "bilateral_outward_coordination", "label": "Difficulty coordinating outward two-handed movement", "description": "The two hands moved inward but did not complete the outward movement together.", "severity": "moderate", "source": "Bilateral arm training task observation", "rehab_code": "BILATERAL_NONUSE"},
            },
            {
                "id": "T7-S4",
                "voice": "Magnificent work. Lower both hands together and relax.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.12, "landmark": "WRISTS_LOW"},
                "hold_ms": 1500,
                "caption": "Lower both hands together",
                "failure_phenotype": {"code": "BILATERAL_LOWERING_IMPAIRED", "domain": "bilateral_lowering_control", "label": "Difficulty lowering both hands together", "description": "Both hands did not complete the lowering movement together.", "severity": "mild", "source": "Bilateral arm training task observation", "rehab_code": "BILATERAL_NONUSE"},
            },
        ],
    },
]


HAND_TASKS_DATA: List[Dict[str, Any]] = [
    {
        "id": "H1",
        "title": "Open Hand",
        "view": "Front view",
        "focus": "Finger extension, palm opening, thumb-index spread",
        "steps": [
            {"id": "H1-S1", "voice": "We will begin the hand function package. Bring your affected hand up in front of your chest, with your palm facing the camera. Keep your fingers relaxed for now. Please do not open your hand yet.", "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Hand up, palm facing camera, fingers relaxed"},
            {"id": "H1-S2", "voice": "Now slowly open your fingers as wide as you comfortably can. Take your time, then hold your palm open and steady.", "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN"}, "hold_ms": 1300, "caption": "Slowly open hand wide", "measure": ["finger_extension", "palm_openness", "thumb_index_spread"]},
            {"id": "H1-S3", "voice": "Good. Relax your hand and lower it to your lap.", "target": {"x": 0.5, "y": 0.82, "r": 0.20, "landmark": "LAP_DYNAMIC"}, "hold_ms": 1200, "caption": "Lower hand to lap"},
        ],
    },
    {
        "id": "H2",
        "title": "Make a Fist",
        "view": "Front view",
        "focus": "Mass finger flexion, fist closure completeness, closing control",
        "steps": [
            {"id": "H2-S1", "voice": "Hold your hand up again. Start with your hand open if you can.", "target": {"x": 0.5, "y": 0.45, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Hand ready"},
            {"id": "H2-S2", "voice": "Slowly close your fingers into a fist. Take your time, then hold the fist for a moment.", "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "WRIST"}, "hold_ms": 4500, "caption": "Slowly close into a fist", "measure": ["closure_completeness", "closing_speed"]},
            {"id": "H2-S3", "voice": "Now relax your hand again.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Relax hand"},
        ],
    },
    {
        "id": "H3",
        "title": "Thumb-Index Pinch",
        "view": "Front view",
        "focus": "Thumb-index opposition, pinch accuracy, pinch stability",
        "steps": [
            {"id": "H3-S1", "voice": "Bring your hand up in front of your chest, palm facing you or the camera.", "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Hand ready for pinch"},
            {"id": "H3-S2", "voice": "Touch the tip of your thumb to the tip of your index finger, as if pinching a small coin. Hold it steady.", "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "PINCH", "icon": "coin"}, "hold_ms": 1800, "caption": "Pinch thumb and index finger", "measure": ["pinch_distance", "pinch_accuracy", "pinch_stability"]},
            {"id": "H3-S3", "voice": "Separate your fingers, then lower your affected hand to the same place on your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "LAP_DYNAMIC"}, "hold_ms": 1200, "caption": "Return hand to the calibrated lap position"},
        ],
    },
    {
        "id": "H4",
        "title": "Open and Close Hand",
        "view": "Front view",
        "focus": "Repeated opening, closing, timing, and control",
        "steps": [
            {"id": "H4-S1", "voice": "Open your hand wide and show your palm to the camera.", "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN"}, "hold_ms": 1500, "caption": "Open hand", "measure": ["hand_opening"]},
            {"id": "H4-S2", "voice": "Now close your hand gently, then open it again. Move slowly and smoothly.", "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "WRIST"}, "hold_ms": 2500, "caption": "Close and open smoothly", "measure": ["open_close_timing", "movement_smoothness"]},
            {"id": "H4-S3", "voice": "Well done. Lower your affected hand to the same place on your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "LAP_DYNAMIC"}, "hold_ms": 1200, "caption": "Return hand to the calibrated lap position"},
        ],
    },
    {
        "id": "H5",
        "title": "Advanced Grasp: Pick Up a Light Object",
        "view": "Front view",
        "focus": "Gross grasp, hand-object coupling, hold stability",
        "advanced_marker_required": True,
        "advanced_label": "Advanced grasp-release with AxonAI marker",
        "recommended_objects": ["empty plastic cup", "soft ball", "foam cylinder", "small paper box"],
        "steps": [
            {"id": "H5-S1", "voice": "This is an advanced grasp task. Reach toward your light object with the AxonAI marker facing the camera.", "target": {"x": 0.32, "y": 0.65, "r": 0.11, "landmark": "WRIST", "icon": "cup"}, "hold_ms": 1400, "caption": "Reach to the marked object"},
            {"id": "H5-S2", "voice": "Close your hand around the object and lift it slightly. Keep it steady.", "target": {"x": 0.50, "y": 0.55, "r": 0.12, "landmark": "WRIST", "icon": "cup"}, "hold_ms": 2200, "caption": "Grasp and hold object", "measure": ["object_hand_coupling", "hold_stability", "marker_visibility"]},
            {"id": "H5-S3", "voice": "Gently place the object back down.", "target": {"x": 0.32, "y": 0.65, "r": 0.11, "landmark": "WRIST", "icon": "table"}, "hold_ms": 1500, "caption": "Place object down"},
        ],
    },
    {
        "id": "H6",
        "title": "Advanced Release: Let Go at Target",
        "view": "Front view",
        "focus": "Finger release, object-hand separation, placement accuracy",
        "advanced_marker_required": True,
        "advanced_label": "Advanced grasp-release with AxonAI marker",
        "recommended_objects": ["empty plastic cup", "soft ball", "foam cylinder", "small paper box"],
        "steps": [
            {"id": "H6-S1", "voice": "Hold the marked object with your affected hand.", "target": {"x": 0.35, "y": 0.62, "r": 0.11, "landmark": "WRIST", "icon": "cup"}, "hold_ms": 1400, "caption": "Hold marked object"},
            {"id": "H6-S2", "voice": "Move the object to the target area, then open your fingers and let go.", "target": {"x": 0.68, "y": 0.62, "r": 0.12, "landmark": "WRIST", "icon": "table"}, "hold_ms": 2400, "caption": "Release at target", "measure": ["release_delay", "object_hand_separation", "placement_endpoint_error"]},
            {"id": "H6-S3", "voice": "Move your empty hand away from the object.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1400, "caption": "Move hand away"},
        ],
    },
    {
        "id": "H7",
        "title": "Wrist Lift and Stabilize",
        "view": "Front view",
        "focus": "Wrist control, unwanted finger flexion, hand stability",
        "steps": [
            {"id": "H7-S1", "voice": "Place your forearm comfortably, and bring your hand into view.", "target": {"x": 0.5, "y": 0.62, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Hand in view"},
            {"id": "H7-S2", "voice": "Lift your wrist gently and hold it steady. Try to keep your fingers relaxed.", "target": {"x": 0.5, "y": 0.48, "r": 0.11, "landmark": "WRIST"}, "hold_ms": 2200, "caption": "Lift and hold wrist", "measure": ["wrist_stability", "unwanted_finger_flexion"]},
            {"id": "H7-S3", "voice": "Relax your wrist and lower your hand.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Relax wrist"},
        ],
    },
]

attach_hand_failure_phenotypes(HAND_TASKS_DATA)


def _tasks_by_id(tasks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {task["id"]: task for task in tasks}


_upper_by_id = _tasks_by_id(TASKS_DATA)
_hand_by_id = _tasks_by_id(HAND_TASKS_DATA)
_lower_by_id = _tasks_by_id(LOWER_LIMB_TASKS_DATA)
INITIAL_ASSESSMENT_TASKS: List[Dict[str, Any]] = [
    _upper_by_id["T1"],
    _upper_by_id["T2"],
    _upper_by_id["T3"],
    _hand_by_id["H1"],
    _hand_by_id["H3"],
    _hand_by_id["H4"],
    _lower_by_id["L6"],
]


ASSESSMENT_PACKAGES: Dict[str, Dict[str, Any]] = {
    "initial": {
        "id": "initial",
        "title": "Initial Functional Assessment",
        "subtitle": "Survey-selected arm, hand, and comfortable-walking observations matched to current ability",
        "tasks": INITIAL_ASSESSMENT_TASKS,
    },
    "upper_limb": {
        "id": "upper_limb",
        "title": "Upper Limb Function Package",
        "subtitle": "Shoulder, elbow, reach, hand-to-mouth, and bilateral upper-limb tasks",
        "tasks": TASKS_DATA,
    },
    "hand": {
        "id": "hand",
        "title": "Hand Function Package",
        "subtitle": "Finger opening, fist closure, pinch, wrist control, and advanced grasp-release tasks",
        "tasks": HAND_TASKS_DATA,
    },
    "lower_limb": {
        "id": "lower_limb",
        "title": "Lower Limb Function Package",
        "subtitle": "Seated selective control, transfers, supported stepping, and gait prerequisites",
        "tasks": LOWER_LIMB_TASKS_DATA,
    },
    "balance": {
        "id": "balance",
        "title": "Balance Function Package",
        "subtitle": "Sitting stability, supported standing, weight shift, and step-stance control",
        "tasks": BALANCE_TASKS_DATA,
    },
}


def _validated_assigned_task_ids(package_id: str, requested: Optional[List[str]]) -> List[str]:
    package = ASSESSMENT_PACKAGES.get(package_id)
    if not package:
        raise HTTPException(status_code=422, detail="Unsupported assessment package")
    allowed = [str(task["id"]) for task in package["tasks"]]
    if requested is None:
        return allowed
    selected = list(dict.fromkeys(str(task_id).strip() for task_id in requested if str(task_id).strip()))
    invalid = [task_id for task_id in selected if task_id not in allowed]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported assigned task ids: {', '.join(invalid)}")
    if not selected:
        raise HTTPException(status_code=422, detail="At least one assigned task is required")
    return [task_id for task_id in allowed if task_id in set(selected)]


def _expected_domains_for_tasks(package_id: str, task_ids: List[str]) -> Optional[tuple[str, ...]]:
    if package_id != "initial":
        return None
    domains: List[str] = []
    if any(task_id.startswith("T") for task_id in task_ids):
        domains.append("upper_limb")
    if any(task_id.startswith("H") for task_id in task_ids):
        domains.append("hand")
    if any(task_id.startswith(("L", "B")) for task_id in task_ids):
        domains.append("lower_limb")
    return tuple(domains)


# ============ Functional Issue Rules ============
# Sources: Fugl-Meyer Upper Extremity Assessment (Fugl-Meyer, 1975);
# Action Research Arm Test (Lyle, 1981); Stroke Rehabilitation: A Function-Based Approach (Gillen);
# Bobath / NDT principles; Task-Specific Training (Carr & Shepherd).
STEP_PHENOTYPES: Dict[str, Dict[str, Any]] = {}
UPPER_LIMB_STEP_PHENOTYPES: Dict[str, Dict[str, Any]] = {}
PHENOTYPE_REHAB_ALIASES: Dict[str, str] = {}
for _package in ASSESSMENT_PACKAGES.values():
    for _task in _package["tasks"]:
        for _step in _task.get("steps", []):
            _phenotype = _step.get("failure_phenotype")
            if not _phenotype:
                continue
            _record = {
                **_phenotype,
                "task_id": _task["id"],
                "step_id": _step["id"],
                "package_id": _package["id"],
            }
            STEP_PHENOTYPES.setdefault(_step["id"], _record)
            if _package["id"] == "upper_limb":
                UPPER_LIMB_STEP_PHENOTYPES[_step["id"]] = _record
            PHENOTYPE_REHAB_ALIASES[_phenotype["code"]] = _phenotype.get("rehab_code", _phenotype["code"])


LEGACY_TASK_FAILURES: Dict[str, Dict[str, str]] = {
    "T1": {"code": "REACH_INCOMPLETE", "label": "Limited forward reach", "description": "The forward-reach task was not completed.", "source": "Fugl-Meyer UE; ARAT", "severity": "moderate", "domain": "forward_reach"},
    "T2": {"code": "SHOULDER_FLEX_LIMITED", "label": "Limited active arm elevation", "description": "The arm-elevation task was not completed.", "source": "Fugl-Meyer UE", "severity": "moderate", "domain": "shoulder_elevation"},
    "T3": {"code": "H2M_IMPAIRED", "label": "Difficulty bringing the hand to the mouth", "description": "The hand-to-mouth task was not completed.", "source": "Chedoke-McMaster Stroke Assessment; MESUPES", "severity": "moderate", "domain": "hand_to_mouth"},
    "T4": {"code": "GROSS_GRASP", "label": "Difficulty grasping and moving an object", "description": "The cup-transfer task was not completed.", "source": "ARAT grasp subscale", "severity": "moderate", "domain": "grasp_transport_release"},
    "T5": {"code": "HAND_OPENING", "label": "Difficulty opening the hand", "description": "The open-grasp-release hand task was not completed.", "source": "Fugl-Meyer UE hand section", "severity": "moderate", "domain": "hand_open_grasp_release"},
    "T6": {"code": "PINCH_IMPAIRED", "label": "Difficulty forming a thumb-index pinch", "description": "The thumb-index pinch task was not completed.", "source": "ARAT pinch subscale", "severity": "mild", "domain": "pinch"},
    "T7": {"code": "BILATERAL_NONUSE", "label": "Limited affected-side participation in a two-handed movement", "description": "The two-handed towel task was not completed.", "source": "CIMT; bilateral arm training", "severity": "moderate", "domain": "bilateral_coordination"},
}

for _package in ASSESSMENT_PACKAGES.values():
    for _task in _package["tasks"]:
        if _task["id"] in LEGACY_TASK_FAILURES:
            continue
        _fallback = next(
            (step.get("failure_phenotype") for step in _task.get("steps", []) if step.get("failure_phenotype")),
            None,
        )
        if _fallback:
            LEGACY_TASK_FAILURES[_task["id"]] = {
                "code": _fallback["code"],
                "label": _fallback["label"],
                "description": f"The {_task['title'].lower()} task was not completed.",
                "source": _fallback["source"],
                "severity": _fallback["severity"],
                "domain": _fallback["domain"],
            }


def derive_functional_issues(task_results: List[TaskResult]) -> List[FunctionalIssue]:
    issues: List[FunctionalIssue] = []
    seen_failures = set()

    def add(code, label, description, source, severity, related, related_step=None, domain=None):
        key = (code, related_step)
        if key in seen_failures:
            return
        seen_failures.add(key)
        issues.append(FunctionalIssue(
            code=code, label=label, description=description,
            source=source, severity=severity, related_task=related,
            related_step=related_step, phenotype_domain=domain,
        ))

    # Failure localization is step-specific. A failed step contributes exactly
    # the movement phenotype declared on that step; no cross-task inference is
    # performed here. Old clients without step details retain a broad fallback.
    for task_result in task_results:
        failed_steps = [step for step in task_result.steps if not step.completed]
        matched_step_failure = False
        for step_result in failed_steps:
            phenotype = STEP_PHENOTYPES.get(step_result.step_id)
            if not phenotype or phenotype["task_id"] != task_result.task_id:
                continue
            matched_step_failure = True
            add(
                phenotype["code"],
                phenotype["label"],
                phenotype["description"],
                phenotype["source"],
                phenotype["severity"],
                task_result.task_id,
                step_result.step_id,
                phenotype["domain"],
            )

        if task_result.completed_steps < task_result.total_steps and not matched_step_failure:
            legacy = LEGACY_TASK_FAILURES.get(task_result.task_id)
            if legacy:
                add(
                    legacy["code"], legacy["label"], legacy["description"],
                    legacy["source"], legacy["severity"], task_result.task_id,
                    None, legacy["domain"],
                )

    # Completion and movement quality are separate findings. A patient may
    # reach the target by leaning the trunk or hiking the shoulder.
    for task_result in task_results:
        if not task_result.task_id.startswith("T"):
            continue
        metric_records = [task_result.metrics, *(step.metrics for step in task_result.steps)]
        trunk_values = [
            float(metrics.get("trunk_lean_deg"))
            for metrics in metric_records
            if isinstance(metrics.get("trunk_lean_deg"), (int, float))
        ]
        peak_trunk_lean = max(trunk_values, default=0.0)
        if peak_trunk_lean > 18:
            add(
                "TRUNK_COMP",
                "Excess trunk compensation during upper-limb movement",
                f"The target was approached with a peak 2D trunk lean of {peak_trunk_lean:.0f} degrees.",
                "Camera-derived 2D movement-quality screen; therapist confirmation required",
                "moderate" if peak_trunk_lean > 30 else "mild",
                task_result.task_id,
                None,
                "trunk_compensation",
            )
        if any(bool(metrics.get("shoulder_hike")) for metrics in metric_records):
            add(
                "SHOULDER_HIKE",
                "Shoulder elevation compensation",
                "The affected shoulder elevated during the upper-limb task.",
                "Camera-derived shoulder-line screen; therapist confirmation required",
                "mild",
                task_result.task_id,
                None,
                "shoulder_compensation",
            )

    if not issues:
        issues.append(FunctionalIssue(
            code="NO_ISSUES",
            label="No failed movement steps identified",
            description="The patient completed every observed movement step in this assessment.",
            source="Step-level movement observation",
            severity="mild",
            related_task="ALL",
        ))
    return issues


# ============ Rehab Exercise Library (rule-based) ============
EXERCISE_LIBRARY: Dict[str, RehabExercise] = {
    "REACH_INCOMPLETE": RehabExercise(
        id="ex_reach", name="Graded Forward Reach",
        description="Sit upright. Reach toward a target placed progressively farther forward (start at 50% arm length, progress to 100%). Hold 2 seconds.",
        sets=3, reps=10, frequency="Twice daily", targets_issue="REACH_INCOMPLETE",
        source="Task-Specific Training (Carr & Shepherd)",
    ),
    "TRUNK_COMP": RehabExercise(
        id="ex_trunk", name="Trunk-Restrained Reaching",
        description="Sit with a strap or chair-back contact to limit trunk motion. Reach forward using only the arm.",
        sets=3, reps=10, frequency="Daily",
        targets_issue="TRUNK_COMP", source="Levin & Michaelsen (2008)",
    ),
    "SHOULDER_FLEX_LIMITED": RehabExercise(
        id="ex_wallslide", name="Supported Arm Elevation Practice",
        description="Begin seated with the forearm supported on a table or towel. Slide toward a meaningful target within a comfortable, pain-free range. Progress to a wall slide only after a therapist confirms shoulder safety and standing balance.",
        sets=3, reps=10, frequency="Twice daily",
        targets_issue="SHOULDER_FLEX_LIMITED", source="NICE NG236 repetitive task training; task-specific upper-limb practice",
    ),
    "SHOULDER_HIKE": RehabExercise(
        id="ex_scapdepress", name="Scapular Depression Practice",
        description="Sit with the affected forearm supported. Settle the shoulder away from the ear, then practise a short pain-free reach while keeping the trunk upright.",
        sets=3, reps=10, frequency="Daily",
        targets_issue="SHOULDER_HIKE", source="Task-specific motor practice and movement-quality feedback",
    ),
    "H2M_IMPAIRED": RehabExercise(
        id="ex_h2m", name="Hand-to-Mouth ADL Practice",
        description="Use a light cup. Practice bringing cup to mouth with affected hand, focusing on smooth elbow flexion.",
        sets=3, reps=10, frequency="Twice daily",
        targets_issue="H2M_IMPAIRED", source="Occupational Therapy ADL retraining",
    ),
    "GROSS_GRASP": RehabExercise(
        id="ex_grasp", name="Cylindrical Grasp & Transport",
        description="Use a soft cup or cylinder. Grasp, lift, transport across midline, and release at a target.",
        sets=3, reps=10, frequency="Twice daily",
        targets_issue="GROSS_GRASP", source="ARAT-based functional retraining",
    ),
    "HAND_OPENING": RehabExercise(
        id="ex_handopen", name="Active Hand Opening and Release",
        description="Support the forearm on a table. Practise opening the hand around a large light object, releasing it, and relaxing. Use assistance rather than resistance when active finger extension is limited.",
        sets=3, reps=10, frequency="Twice daily",
        targets_issue="HAND_OPENING", source="NICE NG236 repetitive task training; Fugl-Meyer UE hand task concepts",
    ),
    "PINCH_IMPAIRED": RehabExercise(
        id="ex_pinch", name="Pinch & Peg Placement",
        description="Pinch small objects (coins, pegs, beads) and place them into a container. Practice all 5 finger oppositions.",
        sets=3, reps=10, frequency="Daily",
        targets_issue="PINCH_IMPAIRED", source="Jebsen Hand Function retraining",
    ),
    "BILATERAL_NONUSE": RehabExercise(
        id="ex_bilateral", name="Bilateral Arm Training (BATRAC-style)",
        description="Perform symmetric two-handed activities: fold towel, clap, push a roller forward together.",
        sets=3, reps=10, frequency="Daily",
        targets_issue="BILATERAL_NONUSE", source="BATRAC (Whitall et al.)",
    ),
    "LOWER_LIMB_SELECTIVE_CONTROL": RehabExercise(
        id="ex_lower_selective", name="Supported Selective Lower-Limb Control",
        description="In supported sitting, practice slow knee extension and return within a comfortable range. Stop if pain, marked fatigue, or loss of sitting balance occurs.",
        sets=2, reps=8, frequency="Daily with therapist-approved assistance",
        targets_issue="LOWER_LIMB_SELECTIVE_CONTROL", source="Fugl-Meyer LE; task-specific stroke rehabilitation",
    ),
    "ANKLE_DORSIFLEXION_CONTROL": RehabExercise(
        id="ex_ankle_dorsiflexion", name="Seated Toe-Lift Practice",
        description="With the heel supported, lift the forefoot and toes, hold briefly, and lower slowly. Keep the knee aligned.",
        sets=2, reps=10, frequency="Daily",
        targets_issue="ANKLE_DORSIFLEXION_CONTROL", source="Task-specific lower-limb training",
    ),
    "SIT_TO_STAND_IMPAIRED": RehabExercise(
        id="ex_sit_to_stand", name="Assisted Sit-to-Stand Practice",
        description="Practice foot placement, forward trunk translation, seat-off, and controlled sitting with a therapist or capable caregiver and a fixed support.",
        sets=2, reps=5, frequency="Therapist-supervised",
        targets_issue="SIT_TO_STAND_IMPAIRED", source="Task-specific mobility training; Five Times Sit-to-Stand task analysis",
    ),
    "SUPPORTED_STANDING_CONTROL": RehabExercise(
        id="ex_supported_stand", name="Supported Standing Alignment",
        description="With close guarding and a fixed support, practice aligned standing with both knees stable. Do not attempt independently when fall risk is present.",
        sets=3, reps=3, frequency="Therapist-supervised",
        targets_issue="SUPPORTED_STANDING_CONTROL", source="PASS; Berg Balance Scale task concepts",
    ),
    "GAIT_INITIATION_IMPAIRED": RehabExercise(
        id="ex_supported_step", name="Guarded Step Initiation",
        description="With close guarding and a fixed support, practice weight shift, short affected-foot advancement, toe clearance, placement, and return.",
        sets=2, reps=5, frequency="Therapist-supervised",
        targets_issue="GAIT_INITIATION_IMPAIRED", source="Task-specific gait training; observational gait analysis",
    ),
    "WEIGHT_BEARING_ASYMMETRY": RehabExercise(
        id="ex_weight_shift", name="Supported Affected-Side Weight Shift",
        description="With close guarding, shift the pelvis gradually toward the affected foot while keeping both feet down and minimizing trunk substitution.",
        sets=3, reps=6, frequency="Therapist-supervised",
        targets_issue="WEIGHT_BEARING_ASYMMETRY", source="PASS; task-specific balance training",
    ),
    "SITTING_BALANCE_IMPAIRED": RehabExercise(
        id="ex_sitting_balance", name="Guarded Sitting Midline and Reach",
        description="Practice upright sitting, small controlled reaches, and return to midline with feet supported and a caregiver guarding the affected side.",
        sets=3, reps=5, frequency="Daily with approved assistance",
        targets_issue="SITTING_BALANCE_IMPAIRED", source="PASS; task-specific balance training",
    ),
    "DYNAMIC_BALANCE_IMPAIRED": RehabExercise(
        id="ex_step_stance", name="Supported Step-Stance Control",
        description="After supported standing is safe, practice a short step stance and controlled return using fixed support and close guarding.",
        sets=2, reps=4, frequency="Therapist-supervised",
        targets_issue="DYNAMIC_BALANCE_IMPAIRED", source="Berg Balance Scale task concepts; task-specific balance training",
    ),
    "NO_ISSUES": RehabExercise(
        id="ex_maintenance", name="Maintenance Conditioning",
        description="Continue full-ROM stretches, light resistance work, and functional ADL practice.",
        sets=2, reps=15, frequency="Daily",
        targets_issue="NO_ISSUES", source="General stroke rehab guidelines",
    ),
}


def _clinical_grade(patient_parameters: Optional[Dict[str, Any]], *keys: str) -> Optional[int]:
    measures = (patient_parameters or {}).get("clinician_measures") or {}
    lookup = {str(key).upper(): value for key, value in measures.items()}
    value = next((lookup[key.upper()] for key in keys if key.upper() in lookup), None)
    match = re.search(r"(?<!\d)([0-5])(?!\d)", str(value)) if value is not None else None
    return int(match.group(1)) if match else None


def build_rehab_plan(
    issues: List[FunctionalIssue],
    patient_parameters: Optional[Dict[str, Any]] = None,
) -> List[RehabExercise]:
    seen = set()
    plan: List[RehabExercise] = []
    upper_mmt = _clinical_grade(patient_parameters, "MMT_UPPER_LIMB", "MMT_UPPER", "UL_MMT")
    mas = _clinical_grade(patient_parameters, "MAS", "ASHWORTH", "MODIFIED_ASHWORTH")
    priorities = (patient_parameters or {}).get("patient_priorities") or []
    if isinstance(priorities, str):
        priorities = [priorities]
    priority = str(priorities[0]).strip() if priorities else ""
    for issue in issues:
        if issue.code == "NO_ISSUES":
            continue
        rehab_code = PHENOTYPE_REHAB_ALIASES.get(issue.code, issue.code)
        ex = EXERCISE_LIBRARY.get(rehab_code)
        if ex and ex.id not in seen:
            sets, reps, frequency = ex.sets, ex.reps, ex.frequency
            is_upper = issue.related_task.startswith("T") or issue.code in {
                "TRUNK_COMP", "SHOULDER_HIKE", "REACH_INCOMPLETE", "SHOULDER_FLEX_LIMITED",
                "H2M_IMPAIRED", "GROSS_GRASP", "HAND_OPENING", "PINCH_IMPAIRED", "BILATERAL_NONUSE",
            }
            safety_notes = ["Use a pain-free range and stop for new shoulder pain, marked fatigue, dizziness, or loss of sitting balance."]
            if issue.severity == "severe":
                sets, reps = min(sets, 2), min(reps, 6)
                frequency = "Therapist-supervised starting dose"
                safety_notes.append("The severe task failure requires hands-on safety and assistance-level confirmation before home practice.")
            if is_upper and upper_mmt is not None and upper_mmt <= 2:
                sets, reps = min(sets, 2), min(reps, 8)
                frequency = "Daily with therapist-approved assistance"
                safety_notes.append("MMT 0-2/5 requires gravity-reduced or active-assisted practice; do not add resistance automatically.")
            if is_upper and mas is not None and mas >= 2:
                sets, reps = min(sets, 2), min(reps, 8)
                safety_notes.append("MAS 2 or above requires tone, passive ROM, skin and positioning review before resistance or prolonged stretch.")
            reason = f"Selected because {issue.label.lower()} was identified in task {issue.related_task}"
            if issue.related_step:
                reason += f", step {issue.related_step}"
            if priority:
                reason += f"; progression should support the patient's priority: {priority}"
            plan.append(ex.model_copy(update={
                "targets_issue": issue.code,
                "sets": sets,
                "reps": reps,
                "frequency": frequency,
                "selection_reason": reason + ".",
                "safety_note": " ".join(safety_notes),
                "requires_clinician_confirmation": True,
            }))
            seen.add(ex.id)
    return plan


def merge_validated_model_issues(
    camera_issues: List[FunctionalIssue],
    model_outputs: Dict[str, Any],
) -> List[FunctionalIssue]:
    """Merge trusted model findings without relabeling pending output as evidence."""
    raw_findings = list(model_outputs.get("functional_findings") or [])
    if not raw_findings:
        return list(camera_issues)
    merged = [issue for issue in camera_issues if issue.code != "NO_ISSUES"]
    seen = {(issue.code, issue.related_task) for issue in merged}
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            continue
        related_tasks = raw.get("related_tasks") or []
        if isinstance(related_tasks, str):
            related_tasks = [related_tasks]
        related_task = str(related_tasks[0]) if related_tasks else str(raw.get("related_task") or "MODEL")
        code = str(raw.get("code") or f"MODEL_FINDING_{index + 1}")
        if (code, related_task) in seen:
            continue
        severity = str(raw.get("severity") or "moderate").lower()
        if severity not in {"mild", "moderate", "severe"}:
            severity = "moderate"
        merged.append(FunctionalIssue(
            code=code,
            label=str(raw.get("label") or "Movement pattern requiring review"),
            description=str(raw.get("description") or raw.get("interpretation") or "The validated musculoskeletal model identified a movement pattern requiring clinician review."),
            source="Validated musculoskeletal model",
            severity=severity,
            related_task=related_task,
            related_step=None,
            phenotype_domain=str(raw.get("domain") or raw.get("package") or "model_finding"),
        ))
        seen.add((code, related_task))
    return merged


# ============ Routes ============
@api_router.get("/")
async def root():
    return {"message": "NeuroMotion Stroke Rehab API"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.dict())
    await db.status_checks.insert_one(status_obj.dict())
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    docs = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**d) for d in docs]


@api_router.get("/assessment/tasks")
async def get_tasks(request: Request, package: str = "upper_limb", task_ids: Optional[str] = None):
    selected = ASSESSMENT_PACKAGES.get(package, ASSESSMENT_PACKAGES["upper_limb"])
    selected_tasks = selected["tasks"]
    if selected["id"] == "initial":
        user = await _user_from_header(dict(request.headers))
        if not user:
            raise HTTPException(status_code=401, detail="Sign in required")
        _require_health_data_consent(user)
        recommendation = initial_assessment_recommendation(user.get("profile") or {})
        if not recommendation["can_start"]:
            raise HTTPException(status_code=409, detail=recommendation["message"])
        recommended_ids = recommendation["task_ids"]
        if task_ids is not None:
            requested = [item.strip() for item in task_ids.split(",") if item.strip()]
            if set(requested) != set(recommended_ids):
                raise HTTPException(status_code=422, detail="Assigned initial tasks do not match the saved readiness survey")
        selected_tasks = [task for task in selected_tasks if task["id"] in set(recommended_ids)]
    elif task_ids is not None:
        requested = [item.strip() for item in task_ids.split(",") if item.strip()]
        selected_ids = _validated_assigned_task_ids(selected["id"], requested)
        selected_tasks = [task for task in selected_tasks if task["id"] in set(selected_ids)]
    packages = [
        {
            "id": item["id"],
            "title": item["title"],
            "subtitle": item["subtitle"],
            "task_count": len(item["tasks"]),
        }
        for item in ASSESSMENT_PACKAGES.values()
    ]
    return {
        "tasks": selected_tasks,
        "voice_id": TTS_VOICE,
        "package_id": selected["id"],
        "package_title": selected["title"],
        "package_subtitle": selected["subtitle"],
        "assigned_task_ids": [task["id"] for task in selected_tasks],
        "packages": packages,
    }


@api_router.get("/assessment/recommendation")
async def get_assessment_recommendation(request: Request, package: str = "initial"):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    _require_health_data_consent(user)
    if package != "initial":
        raise HTTPException(status_code=422, detail="Capability screening is currently available for the initial assessment only")
    return initial_assessment_recommendation(user.get("profile") or {})


@api_router.get("/assessment/modeling-spec")
async def get_modeling_specification():
    return modeling_specification()


def _safe_video_token(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return (cleaned or fallback)[:80]


def _local_task_video_metadata() -> List[Dict[str, Any]]:
    if not TASK_VIDEO_FALLBACK_DIR.exists():
        return []
    records: List[Dict[str, Any]] = []
    for metadata_path in TASK_VIDEO_FALLBACK_DIR.glob("*.json"):
        try:
            import json
            records.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return records


def _write_local_task_video(data: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]:
    import json

    TASK_VIDEO_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    existing = [
        item for item in _local_task_video_metadata()
        if item.get("user_id") == metadata["user_id"]
        and item.get("package_id") == metadata["package_id"]
        and item.get("task_id") == metadata["task_id"]
    ]
    for item in existing:
        for suffix in (".bin", ".json"):
            try:
                (TASK_VIDEO_FALLBACK_DIR / f"{item['id']}{suffix}").unlink(missing_ok=True)
            except Exception:
                pass
    video_id = "local_" + uuid.uuid4().hex
    record = {**metadata, "id": video_id, "size_bytes": len(data), "storage": "local"}
    (TASK_VIDEO_FALLBACK_DIR / f"{video_id}.bin").write_bytes(data)
    (TASK_VIDEO_FALLBACK_DIR / f"{video_id}.json").write_text(json.dumps(record), encoding="utf-8")
    return record


def _write_local_task_video_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    TASK_VIDEO_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    video_id = str(record["id"])
    (TASK_VIDEO_FALLBACK_DIR / f"{video_id}.json").write_text(
        json.dumps(record, ensure_ascii=True), encoding="utf-8"
    )
    return record


async def _task_video_user(request: Request, uid: str = "") -> Optional[Dict[str, Any]]:
    headers = dict(request.headers)
    if uid and not (headers.get("x-user-id") or headers.get("X-User-Id")):
        headers["x-user-id"] = uid
    return await _user_from_header(headers)


async def _latest_task_videos(user_id: str, package_id: str, task_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not user_id or not task_ids:
        return {}
    wanted = set(task_ids)
    records: List[Dict[str, Any]] = []
    try:
        docs = await db.task_videos.files.find({
            "metadata.user_id": user_id,
            "metadata.package_id": package_id,
            "metadata.task_id": {"$in": list(wanted)},
        }).sort("uploadDate", -1).to_list(100)
        records = [
            {"id": str(doc["_id"]), **(doc.get("metadata") or {})}
            for doc in docs
        ]
        object_docs = await db.task_video_objects.find({
            "user_id": user_id,
            "package_id": package_id,
            "task_id": {"$in": list(wanted)},
        }, {"_id": 0}).sort("created_at", -1).to_list(100)
        records.extend(object_docs)
    except Exception as e:
        logger.warning(f"Mongo unavailable for analysis video lookup; using local fallback: {str(e)[:120]}")
        records = [
            item for item in _local_task_video_metadata()
            if item.get("user_id") == user_id
            and item.get("package_id") == package_id
            and item.get("task_id") in wanted
        ]
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    latest: Dict[str, Dict[str, Any]] = {}
    for record in records:
        task_id = str(record.get("task_id") or "")
        if task_id and task_id not in latest:
            latest[task_id] = record
    return latest


@api_router.post("/assessment/task-videos/upload-ticket")
async def create_task_video_upload_ticket(
    request: Request,
    package_id: str,
    task_id: str,
    duration_ms: int = 0,
    content_type: str = "video/mp4",
    size_bytes: int = 0,
):
    user = await _task_video_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not task_video_object_storage.configured:
        raise HTTPException(status_code=503, detail="Direct object upload is not configured")
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if not normalized_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="A video content type is required")
    if size_bytes <= 0 or size_bytes > TASK_VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Task video size is outside the allowed range")
    safe_package = _safe_video_token(package_id, "assessment")
    safe_task = _safe_video_token(task_id, "task")
    extension = "mp4" if normalized_type in {"video/mp4", "video/quicktime"} else "webm"
    video_id = "r2_" + uuid.uuid4().hex
    object_key = task_video_object_storage.object_key(
        user["id"], safe_package, safe_task, video_id, extension
    )
    upload_url = await asyncio.to_thread(
        task_video_object_storage.presign_put, object_key, normalized_type
    )
    return {
        "video_id": video_id,
        "object_key": object_key,
        "upload_url": upload_url,
        "content_type": normalized_type,
        "duration_ms": max(0, int(duration_ms)),
        "expires_seconds": 900,
    }


@api_router.post("/assessment/task-videos/complete")
async def complete_task_video_upload(
    payload: TaskVideoUploadComplete,
    request: Request,
):
    user = await _task_video_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not task_video_object_storage.configured:
        raise HTTPException(status_code=503, detail="Direct object upload is not configured")
    safe_package = _safe_video_token(payload.package_id, "assessment")
    safe_task = _safe_video_token(payload.task_id, "task")
    expected_prefix = task_video_object_storage.object_key(
        user["id"], safe_package, safe_task, payload.video_id, ""
    ).rstrip(".")
    if not payload.video_id.startswith("r2_") or not payload.object_key.startswith(expected_prefix):
        raise HTTPException(status_code=422, detail="Upload ticket does not belong to this account and task")
    try:
        head = await asyncio.to_thread(task_video_object_storage.head, payload.object_key)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Uploaded video could not be verified") from exc
    actual_size = int(head.get("ContentLength") or 0)
    if actual_size <= 0 or actual_size > TASK_VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Task video size is outside the allowed range")
    created_at = datetime.now(timezone.utc).isoformat()
    record = {
        "id": payload.video_id,
        "user_id": user["id"],
        "package_id": safe_package,
        "task_id": safe_task,
        "duration_ms": max(0, int(payload.duration_ms)),
        "content_type": payload.content_type.split(";", 1)[0].strip().lower(),
        "created_at": created_at,
        "filename": payload.object_key.rsplit("/", 1)[-1],
        "size_bytes": actual_size,
        "storage": "r2",
        "object_key": payload.object_key,
    }
    try:
        previous = await db.task_video_objects.find({
            "user_id": user["id"],
            "package_id": safe_package,
            "task_id": safe_task,
            "id": {"$ne": payload.video_id},
        }, {"_id": 0, "object_key": 1}).to_list(50)
        await db.task_video_objects.delete_many({
            "user_id": user["id"], "package_id": safe_package, "task_id": safe_task
        })
        await db.task_video_objects.insert_one(record.copy())
        for item in previous:
            if item.get("object_key"):
                try:
                    await asyncio.to_thread(task_video_object_storage.delete, item["object_key"])
                except Exception:
                    logger.warning("Could not delete replaced R2 task video %s", item["object_key"])
    except Exception as exc:
        logger.warning(f"Mongo unavailable for R2 video metadata; using local fallback: {str(exc)[:120]}")
        _write_local_task_video_metadata(record)
    return record


@api_router.post("/assessment/task-videos")
async def save_task_video(
    request: Request,
    package_id: str,
    task_id: str,
    duration_ms: int = 0,
):
    user = await _task_video_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    content_type = request.headers.get("content-type", "video/webm").split(";", 1)[0].strip().lower()
    if not content_type.startswith("video/"):
        raise HTTPException(status_code=415, detail="A video content type is required")
    content_length = int(request.headers.get("content-length") or 0)
    if content_length > TASK_VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Task video is too large")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Task video is empty")
    if len(data) > TASK_VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Task video is too large")

    safe_package = _safe_video_token(package_id, "assessment")
    safe_task = _safe_video_token(task_id, "task")
    extension = "mp4" if content_type in {"video/mp4", "video/quicktime"} else "webm"
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "user_id": user["id"],
        "package_id": safe_package,
        "task_id": safe_task,
        "duration_ms": max(0, int(duration_ms)),
        "content_type": content_type,
        "created_at": created_at,
    }
    filename = f"{safe_package}_{safe_task}_{uuid.uuid4().hex[:10]}.{extension}"
    try:
        video_id = await task_video_bucket.upload_from_stream(
            filename,
            io.BytesIO(data),
            metadata=metadata,
        )
        previous = await db.task_videos.files.find({
            "metadata.user_id": user["id"],
            "metadata.package_id": safe_package,
            "metadata.task_id": safe_task,
            "_id": {"$ne": video_id},
        }).to_list(50)
        for item in previous:
            await task_video_bucket.delete(item["_id"])
        return {
            "id": str(video_id),
            **metadata,
            "filename": filename,
            "size_bytes": len(data),
            "storage": "gridfs",
        }
    except Exception as e:
        logger.warning(f"Mongo unavailable for task video; using local fallback: {str(e)[:120]}")
        return _write_local_task_video(data, {**metadata, "filename": filename})


@api_router.get("/assessment/task-videos")
async def list_task_videos(request: Request, package: str = "initial"):
    user = await _task_video_user(request)
    if not user:
        return {"videos": []}
    safe_package = _safe_video_token(package, "assessment")
    records: List[Dict[str, Any]] = []
    try:
        docs = await db.task_videos.files.find({
            "metadata.user_id": user["id"],
            "metadata.package_id": safe_package,
        }).sort("uploadDate", -1).to_list(100)
        records = [
            {
                "id": str(doc["_id"]),
                **(doc.get("metadata") or {}),
                "filename": doc.get("filename", "task-video"),
                "size_bytes": int(doc.get("length") or 0),
                "storage": "gridfs",
            }
            for doc in docs
        ]
        object_docs = await db.task_video_objects.find({
            "user_id": user["id"], "package_id": safe_package
        }, {"_id": 0}).sort("created_at", -1).to_list(100)
        records.extend(object_docs)
    except Exception as e:
        logger.warning(f"Mongo unavailable for task video list; using local fallback: {str(e)[:120]}")
        records = [
            item for item in _local_task_video_metadata()
            if item.get("user_id") == user["id"] and item.get("package_id") == safe_package
        ]
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"videos": records}


def _task_progress_key(user_id: str, package_id: str, task_id: str) -> str:
    return f"{user_id}:{package_id}:{task_id}"


def _valid_package_task_ids(package_id: str) -> List[str]:
    package = ASSESSMENT_PACKAGES.get(package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Assessment package not found")
    return [str(task.get("id") or "") for task in package.get("tasks") or []]


@api_router.post("/assessment/task-progress")
async def save_task_progress(request: Request, package_id: str, task_id: str):
    user = await _task_video_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    safe_package = _safe_video_token(package_id, "assessment")
    valid_task_ids = _valid_package_task_ids(safe_package)
    if task_id not in valid_task_ids:
        raise HTTPException(status_code=422, detail="Task does not belong to this assessment package")
    record = {
        "user_id": user["id"],
        "package_id": safe_package,
        "task_id": task_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.assessment_task_progress.delete_one(
            {"user_id": user["id"], "package_id": safe_package, "task_id": "__reset__"}
        )
        await db.assessment_task_progress.update_one(
            {"user_id": user["id"], "package_id": safe_package, "task_id": task_id},
            {"$set": record},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"Mongo unavailable for task progress; using local fallback: {str(exc)[:120]}")
        LOCAL_TASK_PROGRESS.pop(_task_progress_key(user["id"], safe_package, "__reset__"), None)
        LOCAL_TASK_PROGRESS[_task_progress_key(user["id"], safe_package, task_id)] = record
        _persist_local_dict(LOCAL_TASK_PROGRESS_FILE, LOCAL_TASK_PROGRESS)
    return {"ok": True, **record}


@api_router.get("/assessment/task-progress")
async def get_task_progress(request: Request, package: str = "initial"):
    user = await _task_video_user(request)
    if not user:
        return {"completed_task_ids": []}
    safe_package = _safe_video_token(package, "assessment")
    valid_task_ids = _valid_package_task_ids(safe_package)
    try:
        docs = await db.assessment_task_progress.find(
            {"user_id": user["id"], "package_id": safe_package},
            {"_id": 0, "task_id": 1},
        ).to_list(200)
        reset_recorded = any(str(item.get("task_id") or "") == "__reset__" for item in docs)
        completed = {str(item.get("task_id") or "") for item in docs}
    except Exception as exc:
        logger.warning(f"Mongo unavailable for task progress lookup; using local fallback: {str(exc)[:120]}")
        reset_recorded = any(
            item.get("user_id") == user["id"]
            and item.get("package_id") == safe_package
            and item.get("task_id") == "__reset__"
            for item in LOCAL_TASK_PROGRESS.values()
        )
        completed = {
            str(item.get("task_id") or "")
            for item in LOCAL_TASK_PROGRESS.values()
            if item.get("user_id") == user["id"] and item.get("package_id") == safe_package
        }
    if not completed.intersection(valid_task_ids) and not reset_recorded:
        # One-time compatibility for task videos saved before explicit progress records existed.
        completed.update((await _latest_task_videos(user["id"], safe_package, valid_task_ids)).keys())
    return {"completed_task_ids": [task_id for task_id in valid_task_ids if task_id in completed]}


@api_router.delete("/assessment/task-progress")
async def reset_task_progress(request: Request, package: str = "initial"):
    user = await _task_video_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    safe_package = _safe_video_token(package, "assessment")
    _valid_package_task_ids(safe_package)
    try:
        await db.assessment_task_progress.delete_many({"user_id": user["id"], "package_id": safe_package})
        await db.assessment_task_progress.insert_one({
            "user_id": user["id"],
            "package_id": safe_package,
            "task_id": "__reset__",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning(f"Mongo unavailable for task progress reset; using local fallback: {str(exc)[:120]}")
        remove_keys = [
            key for key, item in LOCAL_TASK_PROGRESS.items()
            if item.get("user_id") == user["id"] and item.get("package_id") == safe_package
        ]
        for key in remove_keys:
            LOCAL_TASK_PROGRESS.pop(key, None)
        reset_record = {
            "user_id": user["id"],
            "package_id": safe_package,
            "task_id": "__reset__",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        LOCAL_TASK_PROGRESS[_task_progress_key(user["id"], safe_package, "__reset__")] = reset_record
        _persist_local_dict(LOCAL_TASK_PROGRESS_FILE, LOCAL_TASK_PROGRESS)
    return {"ok": True, "completed_task_ids": []}


@api_router.get("/assessment/task-videos/file/{video_id}")
async def get_task_video(video_id: str, request: Request, uid: str = ""):
    user = await _task_video_user(request, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if video_id.startswith("r2_"):
        try:
            record = await db.task_video_objects.find_one(
                {"id": video_id, "user_id": user["id"]}, {"_id": 0}
            )
        except Exception:
            record = next(
                (
                    item for item in _local_task_video_metadata()
                    if item.get("id") == video_id and item.get("user_id") == user["id"]
                ),
                None,
            )
        if not record or not record.get("object_key") or not task_video_object_storage.configured:
            raise HTTPException(status_code=404, detail="Task video not found")
        url = await asyncio.to_thread(task_video_object_storage.presign_get, record["object_key"])
        return RedirectResponse(url, status_code=307)
    if video_id.startswith("local_"):
        record = next((item for item in _local_task_video_metadata() if item.get("id") == video_id), None)
        path = TASK_VIDEO_FALLBACK_DIR / f"{video_id}.bin"
        if not record or record.get("user_id") != user["id"] or not path.exists():
            raise HTTPException(status_code=404, detail="Task video not found")
        return Response(
            content=path.read_bytes(),
            media_type=record.get("content_type", "video/webm"),
            headers={"Content-Disposition": f'inline; filename="{record.get("filename", "task-video.webm")}"'},
        )
    try:
        object_id = ObjectId(video_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Task video not found")
    try:
        grid_out = await task_video_bucket.open_download_stream(object_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Task video not found")
    metadata = grid_out.metadata or {}
    if metadata.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Task video not found")

    async def chunks():
        while True:
            chunk = await grid_out.read(256 * 1024)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type=metadata.get("content_type", "video/webm"),
        headers={"Content-Disposition": f'inline; filename="{grid_out.filename or "task-video.webm"}"'},
    )


@api_router.get("/assessment/task-videos/worker/{video_id}")
async def get_task_video_for_worker(video_id: str, request: Request):
    """Give the authenticated analysis worker a saved video source."""
    _require_analysis_worker(request)
    if video_id.startswith("r2_"):
        try:
            record = await db.task_video_objects.find_one({"id": video_id}, {"_id": 0})
        except Exception:
            record = next((item for item in _local_task_video_metadata() if item.get("id") == video_id), None)
        if not record or not record.get("object_key") or not task_video_object_storage.configured:
            raise HTTPException(status_code=404, detail="Task video not found")
        url = await asyncio.to_thread(task_video_object_storage.presign_get, record["object_key"])
        return RedirectResponse(url, status_code=307)
    if video_id.startswith("local_"):
        record = next((item for item in _local_task_video_metadata() if item.get("id") == video_id), None)
        path = TASK_VIDEO_FALLBACK_DIR / f"{video_id}.bin"
        if not record or not path.exists():
            raise HTTPException(status_code=404, detail="Task video not found")
        return Response(content=path.read_bytes(), media_type=record.get("content_type", "video/webm"))
    try:
        grid_out = await task_video_bucket.open_download_stream(ObjectId(video_id))
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Task video not found") from exc

    async def worker_chunks():
        while True:
            chunk = await grid_out.read(256 * 1024)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        worker_chunks(), media_type=(grid_out.metadata or {}).get("content_type", "video/webm")
    )


async def _generate_tts_audio_base64(text: str, voice: str) -> str:
    if openai_tts_client:
        response = openai_tts_client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        if hasattr(response, "read"):
            audio_bytes = response.read()
        elif hasattr(response, "content"):
            audio_bytes = response.content
        else:
            audio_bytes = bytes(response)
        return base64.b64encode(audio_bytes).decode("ascii")

    if tts_client:
        return await tts_client.generate_speech_base64(
            text=text,
            model=TTS_MODEL,
            voice=voice,
            response_format="mp3",
        )

    raise HTTPException(status_code=503, detail="Voice service unavailable: OPENAI_API_KEY is not configured.")


@api_router.post("/tts/generate", response_model=TTSResponse)
async def generate_tts(req: TTSRequest):
    # Use OpenAI TTS (nova by default).
    # `voice_id` from old clients is accepted but ignored unless it matches a valid OpenAI voice.
    valid_voices = {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}
    voice = req.voice_id if (req.voice_id in valid_voices) else TTS_VOICE
    try:
        audio_b64 = await _generate_tts_audio_base64(req.text, voice)
        return TTSResponse(audio_b64=audio_b64, text=req.text)
    except Exception as e:
        msg = str(e)
        logger.error(f"TTS error: {msg}")
        if "quota_exceeded" in msg or "402" in msg:
            raise HTTPException(
                status_code=503,
                detail="Voice service unavailable: Emergent LLM key quota exceeded. Add balance at Profile → Universal Key.",
            )
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {msg[:200]}")


@api_router.get("/tts/health")
async def tts_health():
    """Diagnostic: check whether OpenAI TTS works."""
    try:
        audio_b64 = await _generate_tts_audio_base64("ok", TTS_VOICE)
        return {
            "ok": True,
            "bytes": len(base64.b64decode(audio_b64)),
            "voice": TTS_VOICE,
            "model": TTS_MODEL,
            "provider": "openai-direct" if openai_tts_client else "openai-emergent",
        }
    except Exception as e:
        msg = str(e)
        quota = "quota_exceeded" in msg or "402" in msg
        return {
            "ok": False,
            "quota_exceeded": quota,
            "hint": (
                "Top up your Emergent Universal Key balance at Profile → Universal Key → Add Balance."
                if quota else "Check key validity / network."
            ),
            "error": msg[:300],
        }


@api_router.post("/stt/transcribe")
async def transcribe_speech(file: UploadFile = File(...)):
    """Transcribe a short Alira voice turn without retaining the recording."""
    if not openai_tts_client:
        raise HTTPException(status_code=503, detail="Speech recognition is unavailable.")
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="The recording was empty.")
    if len(audio) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Keep each voice turn under one minute.")

    filename = file.filename or "alira-turn.m4a"
    content_type = file.content_type or "audio/m4a"

    def run_transcription():
        return openai_tts_client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio, content_type),
            response_format="json",
        )

    try:
        result = await asyncio.to_thread(run_transcription)
        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No speech was detected. Please try again.")
        return {"text": text}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Speech transcription failed: %s", str(exc)[:200])
        raise HTTPException(status_code=502, detail="I could not understand that recording. Please try again.") from exc


def _assessment_patient_parameters(
    submitted: Dict[str, Any],
    user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(submitted or {})
    profile = user.get("profile") if isinstance(user, dict) and isinstance(user.get("profile"), dict) else {}
    if profile:
        for key in ("age_band", "months_since_stroke", "side_affected", "affected_areas", "affected_areas_other", "dominant_hand", "mobility_level", "sitting_ability", "affected_arm_movement", "affected_hand_movement", "movement_pain", "instruction_support", "medical_conditions", "medical_conditions_other", "has_caregiver"):
            if profile.get(key) is not None:
                merged.setdefault(key, profile[key])
        if not merged.get("patient_priorities"):
            priorities = []
            if str(profile.get("primary_goal") or "").strip():
                priorities.append(str(profile["primary_goal"]).strip())
            priorities.extend(str(item).strip() for item in profile.get("secondary_goals") or [] if str(item).strip() and str(item).strip() != "other")
            if str(profile.get("secondary_goals_other") or "").strip():
                priorities.append(str(profile["secondary_goals_other"]).strip())
            if priorities:
                merged["patient_priorities"] = priorities
    return merged


@api_router.post("/assessment/submit", response_model=Assessment)
async def submit_assessment(payload: AssessmentSubmit, request: Request):
    user = await _user_from_header(dict(request.headers))
    if user:
        await consume_credits(user["id"], "assessment")
    patient_parameters = _assessment_patient_parameters(payload.patient_parameters, user)
    assessment_id = str(uuid.uuid4())
    task_ids = [task.task_id for task in payload.task_results]
    assigned_task_ids = _validated_assigned_task_ids(payload.assessment_package, payload.assigned_task_ids)
    if payload.assessment_package == "initial":
        if not user:
            raise HTTPException(status_code=401, detail="Sign in required")
        _require_health_data_consent(user)
        recommendation = initial_assessment_recommendation(user.get("profile") or {})
        if not recommendation["can_start"]:
            raise HTTPException(status_code=409, detail=recommendation["message"])
        if set(assigned_task_ids) != set(recommendation["task_ids"]):
            raise HTTPException(status_code=422, detail="Assigned initial tasks do not match the saved readiness survey")
    if set(task_ids) != set(assigned_task_ids):
        raise HTTPException(status_code=422, detail="Submitted task results must match the assigned assessment tasks")
    patient_parameters["assigned_task_ids"] = assigned_task_ids
    video_records = await _latest_task_videos(
        user["id"] if user else "",
        payload.assessment_package,
        task_ids,
    )
    model_analysis = build_model_analysis_manifest(assessment_id, task_ids, video_records)
    model_analysis["gpu_stage"] = {
        "status": "queued" if LOCAL_GPU_WORKER_URL else "not_configured",
        "device": "cuda:0" if LOCAL_GPU_WORKER_URL else None,
    }
    walking_video_ready = bool((video_records.get("L6") or {}).get("id"))
    model_analysis["musculoskeletal_stage"] = {
        "status": (
            "queued" if LOCAL_GPU_WORKER_URL and walking_video_ready
            else "waiting_for_walking_video" if LOCAL_GPU_WORKER_URL
            else "not_configured"
        ),
        "modeled_tasks": ["L6"] if walking_video_ready else [],
    }
    expected_task_count = len(assigned_task_ids)
    collection_summary = patient_collection_summary(payload.task_results, expected_task_count)
    if payload.musculoskeletal_outputs:
        logger.warning("Ignoring client-supplied musculoskeletal outputs; trusted worker ingestion is required")
    trusted_model_outputs: Dict[str, Any] = {}
    issues = derive_functional_issues(payload.task_results)
    domain_assessments = build_domain_assessments(payload.task_results)
    expected_summary_domains = _expected_domains_for_tasks(payload.assessment_package, assigned_task_ids)
    body_function_summary = patient_body_function_summary(
        payload.task_results,
        issues,
        trusted_model_outputs,
        expected_summary_domains,
    )
    clinician_measures = build_clinician_measure_summary(patient_parameters)
    biomechanical_estimates = build_biomechanical_estimates(
        payload.task_results,
        patient_parameters,
        trusted_model_outputs,
    )
    measurement_form = build_clinical_measurement_form(
        payload.task_results,
        patient_parameters,
        trusted_model_outputs,
    )
    rehabilitation_goals = build_rehab_goals(
        payload.task_results,
        issues,
        measurement_form,
        patient_parameters,
    )
    movement_based_muscle_screening = build_muscle_activation_diagnosis(
        [t.model_dump() for t in payload.task_results],
    )
    muscle_activation_diagnosis = pending_model_activation_report()
    survey_consistency = build_survey_consistency(
        issues,
        patient_parameters,
        payload.task_results,
    )
    analysis_pipeline = build_analysis_pipeline(
        payload.motion_data,
        trusted_model_outputs,
    )
    clinical_review_gate = build_clinical_review_gate(
        issues,
        patient_parameters,
        payload.task_results,
        trusted_model_outputs,
        expected_task_count,
    )
    plan = build_rehab_plan(issues, patient_parameters) if clinical_review_gate.get("rehab_access") == "allowed" else []
    if user and plan:
        await consume_credits(user["id"], "rehab_plan")
    assessment = Assessment(
        id=assessment_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        affected_side=payload.affected_side,
        assessment_package=payload.assessment_package,
        assigned_task_ids=assigned_task_ids,
        task_results=payload.task_results,
        functional_issues=issues,
        rehab_plan=plan,
        domain_assessments=domain_assessments,
        clinician_measures=clinician_measures,
        biomechanical_estimates=biomechanical_estimates,
        measurement_form=measurement_form,
        rehabilitation_goals=rehabilitation_goals,
        muscle_activation_diagnosis=muscle_activation_diagnosis,
        survey_consistency=survey_consistency,
        analysis_pipeline=analysis_pipeline,
        clinical_review_gate=clinical_review_gate,
        body_function_summary=body_function_summary,
    )
    doc = assessment.model_dump()
    if payload.motion_data:
        doc["motion_data"] = payload.motion_data
    doc["patient_parameters"] = patient_parameters
    doc["patient_summary"] = collection_summary
    doc["model_analysis"] = model_analysis
    doc["movement_based_muscle_screening"] = movement_based_muscle_screening
    doc["patient_insights"] = build_patient_insights(
        body_function_summary, {}, {}, model_analysis
    )
    if user:
        doc["user_id"] = user["id"]
    try:
        await db.assessments.insert_one(doc)
    except Exception as e:
        logger.warning(f"Mongo unavailable for assessment insert; using local fallback: {str(e)[:120]}")
        LOCAL_ASSESSMENTS.append(doc.copy())
    if LOCAL_GPU_WORKER_URL and ANALYSIS_WORKER_TOKEN and (payload.motion_data or video_records):
        asyncio.create_task(_queue_local_gpu_stage(
            assessment_id,
            payload.motion_data,
            video_records,
            payload.affected_side,
            patient_parameters,
        ))
    return assessment


@api_router.get("/assessment/history", response_model=List[Assessment])
async def get_assessment_history(request: Request):
    """Return ONLY the signed-in user's assessments. Anonymous → empty list."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        return []
    try:
        docs = (
            await db.assessments
            .find({"user_id": user["id"]}, {"_id": 0})
            .sort("created_at", -1)
            .to_list(50)
        )
    except Exception as e:
        logger.warning(f"Mongo unavailable for assessment history; using local fallback: {str(e)[:120]}")
        docs = [
            {k: v for k, v in item.items() if k != "_id"}
            for item in LOCAL_ASSESSMENTS
            if item.get("user_id") == user["id"]
        ]
        docs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        docs = docs[:50]
    for doc in docs:
        if not doc.get("patient_insights"):
            package_id = str(doc.get("assessment_package") or "upper_limb")
            assigned_task_ids = doc.get("assigned_task_ids") or [str(item.get("task_id")) for item in doc.get("task_results", [])]
            expected_domains = _expected_domains_for_tasks(package_id, assigned_task_ids)
            body_summary = doc.get("body_function_summary") or patient_body_function_summary(
                doc.get("task_results", []),
                doc.get("functional_issues", []),
                doc.get("musculoskeletal_outputs", {}),
                expected_domains,
            )
            doc["patient_insights"] = build_patient_insights(
                body_summary,
                doc.get("musculoskeletal_outputs") or {},
                doc.get("musculoskeletal_research_stage") or {},
                doc.get("model_analysis") or {},
            )
    return [Assessment(**d) for d in docs]


@api_router.get("/assessment/{assessment_id}", response_model=Assessment)
async def get_assessment(assessment_id: str):
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for assessment get; using local fallback: {str(e)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return Assessment(**doc)


@api_router.get("/assessment/{assessment_id}/patient-summary")
async def get_patient_assessment_summary(assessment_id: str):
    """Return only the concise collection receipt intended for patients."""
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for patient summary; local fallback: {str(e)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    package_id = str(doc.get("assessment_package") or "upper_limb")
    assigned_task_ids = doc.get("assigned_task_ids") or [str(item.get("task_id")) for item in doc.get("task_results", [])]
    expected = len(assigned_task_ids) or len(ASSESSMENT_PACKAGES.get(package_id, {}).get("tasks", []))
    collection = doc.get("patient_summary") or patient_collection_summary(doc.get("task_results", []), expected)
    expected_summary_domains = _expected_domains_for_tasks(package_id, assigned_task_ids)
    body_function_summary = doc.get("body_function_summary") or patient_body_function_summary(
        doc.get("task_results", []),
        doc.get("functional_issues", []),
        doc.get("musculoskeletal_outputs", {}),
        expected_summary_domains,
    )
    return {
        "id": doc["id"],
        "created_at": doc["created_at"],
        "assessment_package": package_id,
        "collection": collection,
        "body_function_summary": body_function_summary,
        "insights": doc.get("patient_insights") or build_patient_insights(
            body_function_summary,
            doc.get("musculoskeletal_outputs") or {},
            doc.get("musculoskeletal_research_stage") or {},
            doc.get("model_analysis") or {},
        ),
        "rehab_plan_ready": bool(doc.get("rehab_plan")) and (doc.get("clinical_review_gate") or {}).get("rehab_access", "allowed") == "allowed",
        "clinical_review_gate": doc.get("clinical_review_gate") or {},
    }


@api_router.get("/assessment/{assessment_id}/analysis-status")
async def get_assessment_analysis_status(assessment_id: str):
    """Return processing state without exposing internal model predictions."""
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as exc:
        logger.warning(f"Mongo unavailable for analysis status; local fallback: {str(exc)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    model_analysis = doc.get("model_analysis") or {}
    gpu_stage = model_analysis.get("gpu_stage") or {}
    musculoskeletal_stage = model_analysis.get("musculoskeletal_stage") or {}
    task_states = {
        task_id: str(task.get("status") or "unknown")
        for task_id, task in (gpu_stage.get("tasks") or {}).items()
        if isinstance(task, dict)
    }
    return {
        "assessment_id": assessment_id,
        "model_status": model_analysis.get("status", "waiting_for_inputs"),
        "gpu_stage": {
            "status": gpu_stage.get("status", "not_configured"),
            "device": gpu_stage.get("device"),
            "gpu_name": gpu_stage.get("gpu_name"),
            "model_version": gpu_stage.get("model_version"),
            "tasks": task_states,
            "error": gpu_stage.get("error"),
        },
        "musculoskeletal_stage": {
            "status": musculoskeletal_stage.get("status", "not_configured"),
            "modeled_tasks": musculoskeletal_stage.get("modeled_tasks") or [],
            "solver": musculoskeletal_stage.get("solver"),
            "error": musculoskeletal_stage.get("error"),
        },
    }


def _require_analysis_worker(request: Request) -> None:
    if not ANALYSIS_WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="Biomechanics worker ingestion is not configured")
    supplied = request.headers.get("x-analysis-worker-token", "")
    if supplied != ANALYSIS_WORKER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid analysis worker token")


async def _set_gpu_stage(assessment_id: str, stage: Dict[str, Any]) -> None:
    try:
        await db.assessments.update_one(
            {"id": assessment_id}, {"$set": {"model_analysis.gpu_stage": stage}}
        )
    except Exception as exc:
        logger.warning(f"Mongo unavailable for GPU stage update; local fallback: {str(exc)[:120]}")
        for item in LOCAL_ASSESSMENTS:
            if item.get("id") == assessment_id:
                item.setdefault("model_analysis", {})["gpu_stage"] = stage
                break


async def _set_musculoskeletal_stage(assessment_id: str, stage: Dict[str, Any]) -> None:
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0}) or {}
        model_analysis = dict(doc.get("model_analysis") or {})
        model_analysis["musculoskeletal_stage"] = stage
        insights = build_patient_insights(
            doc.get("body_function_summary") or {},
            doc.get("musculoskeletal_outputs") or {},
            doc.get("musculoskeletal_research_stage") or {},
            model_analysis,
        )
        await db.assessments.update_one(
            {"id": assessment_id},
            {"$set": {
                "model_analysis.musculoskeletal_stage": stage,
                "patient_insights": insights,
            }},
        )
    except Exception as exc:
        logger.warning(f"Mongo unavailable for model stage update; local fallback: {str(exc)[:120]}")
        for item in LOCAL_ASSESSMENTS:
            if item.get("id") == assessment_id:
                item.setdefault("model_analysis", {})["musculoskeletal_stage"] = stage
                item["patient_insights"] = build_patient_insights(
                    item.get("body_function_summary") or {},
                    item.get("musculoskeletal_outputs") or {},
                    item.get("musculoskeletal_research_stage") or {},
                    item.get("model_analysis") or {},
                )
                break


async def _worker_video_sources(video_records: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for task_id, record in video_records.items():
        video_id = str(record.get("id") or "")
        if not video_id:
            continue
        headers: Dict[str, str] = {}
        if record.get("storage") == "r2" and record.get("object_key") and task_video_object_storage.configured:
            url = await asyncio.to_thread(
                task_video_object_storage.presign_get, record["object_key"], 1800
            )
        else:
            url = f"{LOCAL_BACKEND_CALLBACK_URL}/assessment/task-videos/worker/{video_id}"
            headers["X-Analysis-Worker-Token"] = ANALYSIS_WORKER_TOKEN
        sources.append({
            "task_id": task_id,
            "video_id": video_id,
            "url": url,
            "headers": headers,
            "content_type": record.get("content_type") or "video/mp4",
        })
    return sources


async def _queue_local_gpu_stage(
    assessment_id: str,
    motion_data: Dict[str, Any],
    video_records: Dict[str, Dict[str, Any]],
    affected_side: str,
    patient_parameters: Dict[str, Any],
) -> None:
    job = {
        "assessment_id": assessment_id,
        "callback_url": LOCAL_BACKEND_CALLBACK_URL,
        "motion_data": motion_data,
        "video_sources": await _worker_video_sources(video_records),
        "affected_side": affected_side,
        "patient_parameters": patient_parameters,
    }
    try:
        headers = {"X-Analysis-Worker-Token": ANALYSIS_WORKER_TOKEN}
        if ANALYSIS_WORKER_CF_CLIENT_ID and ANALYSIS_WORKER_CF_CLIENT_SECRET:
            headers.update({
                "CF-Access-Client-Id": ANALYSIS_WORKER_CF_CLIENT_ID,
                "CF-Access-Client-Secret": ANALYSIS_WORKER_CF_CLIENT_SECRET,
            })
        async with httpx.AsyncClient(timeout=15) as http:
            response = await http.post(
                f"{LOCAL_GPU_WORKER_URL}/jobs",
                json=job,
                headers=headers,
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning(f"Could not queue local CUDA analysis: {str(exc)[:160]}")
        await _set_gpu_stage(assessment_id, {
            "status": "failed_to_queue",
            "device": "cuda:0",
            "error": str(exc),
        })
        await _set_musculoskeletal_stage(assessment_id, {
            "status": "failed_to_queue",
            "modeled_tasks": [],
            "solver": "OpenSim Moco",
            "error": str(exc),
        })


@api_router.get("/analysis/local-gpu/status")
async def local_gpu_status():
    if not LOCAL_GPU_WORKER_URL:
        return {"status": "not_configured", "cuda": False}
    try:
        headers = {}
        if ANALYSIS_WORKER_CF_CLIENT_ID and ANALYSIS_WORKER_CF_CLIENT_SECRET:
            headers = {
                "CF-Access-Client-Id": ANALYSIS_WORKER_CF_CLIENT_ID,
                "CF-Access-Client-Secret": ANALYSIS_WORKER_CF_CLIENT_SECRET,
            }
        async with httpx.AsyncClient(timeout=5) as http:
            response = await http.get(f"{LOCAL_GPU_WORKER_URL}/health", headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        return {"status": "unavailable", "cuda": False, "error": str(exc)}


@api_router.post("/assessment/{assessment_id}/gpu-stage-results")
async def save_gpu_stage_results(
    assessment_id: str,
    payload: GPUStageResultSubmit,
    request: Request,
):
    """Store intermediate CUDA output without treating it as solver activation."""
    _require_analysis_worker(request)
    stage = payload.model_dump(exclude_none=True)
    if stage["status"] == "completed":
        if not stage.get("device", "").startswith("cuda"):
            raise HTTPException(status_code=422, detail="Completed local GPU output must come from CUDA")
        if not stage.get("model_version") or not stage.get("tasks"):
            raise HTTPException(status_code=422, detail="GPU output is missing model provenance or task results")
    elif stage["status"] != "failed":
        raise HTTPException(status_code=422, detail="GPU stage status must be completed or failed")
    await _set_gpu_stage(assessment_id, stage)
    return {"assessment_id": assessment_id, "gpu_stage": stage["status"]}


@api_router.post("/assessment/{assessment_id}/model-stage-results")
async def save_musculoskeletal_stage_results(
    assessment_id: str,
    payload: MusculoskeletalStageResultSubmit,
    request: Request,
):
    """Store genuine solver output without promoting unvalidated estimates."""
    _require_analysis_worker(request)
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as exc:
        logger.warning(f"Mongo unavailable for model stage lookup; local fallback: {str(exc)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")

    stage = payload.model_dump(exclude_none=True)
    if stage["status"] == "completed":
        if not stage.get("per_task"):
            raise HTTPException(status_code=422, detail="Completed model stage requires task outputs")
        manifest = {
            str(item.get("task_id")): str(item.get("video_id") or "")
            for item in (doc.get("model_analysis") or {}).get("tasks") or []
        }
        for row in stage["per_task"]:
            task_id = str(row.get("task_id") or "")
            provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
            if task_id not in manifest or not manifest[task_id]:
                raise HTTPException(status_code=422, detail=f"Task {task_id} has no saved source video")
            if str(provenance.get("source_video_id") or "") != manifest[task_id]:
                raise HTTPException(status_code=422, detail=f"Task {task_id} result does not match its source video")
            if not all(str(provenance.get(key) or "").strip() for key in ("solver", "model_version", "code_version")):
                raise HTTPException(status_code=422, detail=f"Task {task_id} is missing model provenance")
            activations = row.get("muscle_activations")
            if not isinstance(activations, dict) or not activations:
                raise HTTPException(status_code=422, detail=f"Task {task_id} has no model activations")
            for activation in activations.values():
                value = activation.get("mean") if isinstance(activation, dict) else activation
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
                    raise HTTPException(status_code=422, detail=f"Task {task_id} activation is outside 0..1")
        stage_status = {
            "status": "completed",
            "modeled_tasks": [str(item.get("task_id")) for item in stage["per_task"]],
            "solver": "OpenSim Moco",
            "validated_for_plan": False,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    elif stage["status"] == "failed":
        stage_status = {
            "status": "failed",
            "modeled_tasks": [],
            "solver": "OpenSim Moco",
            "validated_for_plan": False,
            "error": str(stage.get("error") or "Musculoskeletal analysis failed")[:500],
        }
    else:
        raise HTTPException(status_code=422, detail="Model stage status must be completed or failed")

    body_summary = doc.get("body_function_summary") or {}
    model_analysis = dict(doc.get("model_analysis") or {})
    model_analysis["musculoskeletal_stage"] = stage_status
    insights = build_patient_insights(
        body_summary,
        doc.get("musculoskeletal_outputs") or {},
        stage,
        model_analysis,
    )
    updates = {
        "musculoskeletal_research_stage": stage,
        "model_analysis.musculoskeletal_stage": stage_status,
        "patient_insights": insights,
    }
    try:
        await db.assessments.update_one({"id": assessment_id}, {"$set": updates})
    except Exception as exc:
        logger.warning(f"Mongo unavailable for model stage update; local fallback: {str(exc)[:120]}")
        for item in LOCAL_ASSESSMENTS:
            if item.get("id") == assessment_id:
                item["musculoskeletal_research_stage"] = stage
                item.setdefault("model_analysis", {})["musculoskeletal_stage"] = stage_status
                item["patient_insights"] = insights
                break
    return {
        "assessment_id": assessment_id,
        "status": stage_status["status"],
        "insights_ready": insights["status"] in {"research_ready", "validated"},
        "rehab_plan_unlocked": False,
    }


@api_router.post("/assessment/{assessment_id}/model-results")
async def save_model_results(assessment_id: str, payload: ModelResultSubmit, request: Request):
    """Accept trusted, quality-gated per-task solver results from a separate worker."""
    _require_analysis_worker(request)
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for model result lookup; local fallback: {str(e)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")

    task_ids = [str(item.get("task_id")) for item in doc.get("task_results", [])]
    manifest_tasks = (doc.get("model_analysis") or {}).get("tasks") or []
    expected_videos = {str(item.get("task_id")): item.get("video_id") for item in manifest_tasks}
    try:
        validated = validate_model_outputs(payload.model_dump(), task_ids, expected_videos)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    outputs = aggregate_model_outputs(validated)
    patient_parameters = doc.get("patient_parameters") or {}
    task_results = doc.get("task_results") or []
    camera_issues = [
        FunctionalIssue(**item)
        for item in doc.get("functional_issues") or []
        if str(item.get("source") or "") != "Validated musculoskeletal model"
    ]
    issues = merge_validated_model_issues(camera_issues, outputs)
    package_id = str(doc.get("assessment_package") or "upper_limb")
    assigned_task_ids = doc.get("assigned_task_ids") or [str(item.get("task_id")) for item in task_results]
    expected_task_count = len(assigned_task_ids) or len(ASSESSMENT_PACKAGES.get(package_id, {}).get("tasks", []))
    clinical_review_gate = build_clinical_review_gate(
        camera_issues,
        patient_parameters,
        task_results,
        outputs,
        expected_task_count,
    )
    plan = build_rehab_plan(issues, patient_parameters)
    if clinical_review_gate.get("rehab_access") != "allowed":
        plan = []
    expected_summary_domains = _expected_domains_for_tasks(package_id, assigned_task_ids)
    body_function_summary = patient_body_function_summary(
        task_results,
        issues,
        outputs,
        expected_summary_domains,
    )
    updated_fields = {
        "functional_issues": [issue.model_dump() for issue in issues],
        "rehab_plan": [exercise.model_dump() for exercise in plan],
        "body_function_summary": body_function_summary,
        "musculoskeletal_outputs": outputs,
        "biomechanical_estimates": build_biomechanical_estimates(task_results, patient_parameters, outputs),
        "measurement_form": build_clinical_measurement_form(task_results, patient_parameters, outputs),
        "analysis_pipeline": build_analysis_pipeline(doc.get("motion_data") or {}, outputs),
        "muscle_activation_diagnosis": model_activation_report(outputs),
        "survey_consistency": build_survey_consistency(issues, patient_parameters, task_results),
        "clinical_review_gate": clinical_review_gate,
        "patient_insights": build_patient_insights(
            body_function_summary,
            outputs,
            doc.get("musculoskeletal_research_stage") or {},
            {**(doc.get("model_analysis") or {}), "status": "completed"},
        ),
        "model_analysis.status": "completed",
        "model_analysis.musculoskeletal_stage": {
            "status": "validated",
            "modeled_tasks": [str(item.get("task_id")) for item in outputs.get("per_task") or []],
            "validated_for_plan": True,
        },
        "model_analysis.completed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.assessments.update_one({"id": assessment_id}, {"$set": updated_fields})
    except Exception as e:
        logger.warning(f"Mongo unavailable for model result update; local fallback: {str(e)[:120]}")
        for item in LOCAL_ASSESSMENTS:
            if item.get("id") == assessment_id:
                for key, value in updated_fields.items():
                    if key.startswith("model_analysis."):
                        item.setdefault("model_analysis", {})[key.split(".", 1)[1]] = value
                    else:
                        item[key] = value
                break
    return {
        "assessment_id": assessment_id,
        "status": "completed",
        "tasks_modeled": len(outputs.get("per_task") or []),
        "findings_ready": True,
        "clinical_review_status": clinical_review_gate.get("status"),
    }


@api_router.get("/assessment/{assessment_id}/muscle-diagnosis")
async def get_muscle_diagnosis(assessment_id: str):
    """Return only validated model-estimated findings, never camera proxies."""
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for muscle diagnosis; local fallback: {str(e)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return doc.get("muscle_activation_diagnosis") or pending_model_activation_report()


# ============ Pose Runner HTML (served at /api/pose/runner) ============
# A self-contained page that:
# 1. Opens device camera (getUserMedia)
# 2. Loads MediaPipe PoseLandmarker
# 3. Walks through the assigned tasks and steps with target overlays + voice prompts
# 4. Posts results to React Native via window.ReactNativeWebView.postMessage
POSE_RUNNER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
<title>Pose Assessment</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{width:100%;height:100%;background:#0c100e;color:#fdfdfd;font-family:-apple-system,BlinkMacSystemFont,"Plus Jakarta Sans",sans-serif;overflow:hidden}
  #stage{position:relative;width:100vw;height:100vh;height:100dvh;background:#000}
  #cameraFrame{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;background:#000}
  #cameraFrame video,#cameraFrame canvas{position:absolute;inset:0;width:100%;height:100%;transform:scaleX(-1);transform-origin:center}
  #ui{position:absolute;inset:0;pointer-events:none;display:flex;flex-direction:column;justify-content:space-between;padding:env(safe-area-inset-top,24px) 16px env(safe-area-inset-bottom,24px) 16px}
  #top{display:flex;align-items:center;gap:8px;background:rgba(28,32,29,0.65);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:12px 16px;pointer-events:auto}
  #top .dots{display:flex;gap:6px;flex:1;justify-content:center}
  #top .dot{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,0.25)}
  #top .dot.active{background:#E18E6D;transform:scale(1.3)}
  #top .dot.done{background:#4A7856}
  #top .label{font-size:14px;font-weight:600;opacity:0.95}
  #exitBtn{background:rgba(255,255,255,0.18);border:none;color:#fff;padding:8px 12px;border-radius:16px;font-weight:600;font-size:13px;pointer-events:auto;cursor:pointer}
  #bottom{background:rgba(28,32,29,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:16px 18px;pointer-events:auto;transition:opacity .4s ease, transform .4s ease;will-change:opacity,transform}
  /* While voice is playing, show the instruction card. Once voice ends, fade
     it to a compact, semi-transparent badge so the patient can see the target circle clearly. */
  body.step-active #bottom{opacity:.30;transform:scale(.92) translateY(8px)}
  body.step-active #bottom:hover,body.step-active #bottom:focus-within{opacity:.95;transform:none}
  #stepTitle{font-size:14px;color:#D9E5DC;font-weight:600;margin-bottom:6px}
  #caption{font-size:18px;font-weight:600;line-height:1.35}
  #voiceRow{display:flex;align-items:center;gap:10px;margin-top:10px;opacity:0.85}
  #voiceWave{display:flex;gap:3px;align-items:end;height:14px}
  #voiceWave span{display:block;width:3px;background:#E18E6D;border-radius:2px;animation:wave 1s ease-in-out infinite}
  #voiceWave span:nth-child(1){animation-delay:.0s;height:6px}
  #voiceWave span:nth-child(2){animation-delay:.15s;height:14px}
  #voiceWave span:nth-child(3){animation-delay:.3s;height:8px}
  #voiceWave span:nth-child(4){animation-delay:.45s;height:12px}
  @keyframes wave{0%,100%{transform:scaleY(0.5)}50%{transform:scaleY(1.2)}}
  #voiceText{font-size:13px;color:#D9E5DC}
  #skipBtn{margin-top:12px;background:#4A7856;color:#fff;border:none;width:100%;padding:14px;border-radius:16px;font-weight:700;font-size:16px;cursor:pointer}
  #overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#0c100eee;text-align:center;padding:24px;flex-direction:column;gap:16px;pointer-events:auto;z-index:10}
  #overlay h1{font-size:22px;font-weight:700}
  #overlay p{font-size:15px;color:#bcc2ba;line-height:1.5}
  #overlay button{background:#4A7856;color:#fff;border:none;padding:14px 28px;border-radius:16px;font-weight:700;font-size:16px}
  #calibrationOverlay{position:absolute;inset:0;display:flex;align-items:flex-start;justify-content:center;background:linear-gradient(180deg,rgba(12,16,14,.62),rgba(12,16,14,.12));padding:calc(16px + env(safe-area-inset-top,0px)) 16px 16px;pointer-events:auto;z-index:12}
  #calibrationOverlay .calibrationPanel{width:min(520px,100%);background:rgba(253,253,253,.96);color:#1C201D;border-radius:8px;padding:18px;box-shadow:0 18px 55px rgba(0,0,0,.30);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
  #calibrationOverlay h2{font-size:22px;line-height:1.2;margin-bottom:6px}
  #calibrationOverlay .calibrationLead{font-size:15px;line-height:1.4;color:#49504B;margin-bottom:12px}
  #calibrationChecklist{display:grid;gap:7px;margin:10px 0 14px}
  .calibrationCheck{display:flex;align-items:center;gap:9px;font-size:14px;font-weight:650;color:#49504B}
  .calibrationCheck .statusDot{display:grid;place-items:center;width:22px;height:22px;flex:0 0 22px;border-radius:50%;background:#E8ECE8;color:#69716B;font-size:13px}
  .calibrationCheck.done{color:#285C3A}
  .calibrationCheck.done .statusDot{background:#D9E5DC;color:#285C3A}
  #calibrationProgress{height:6px;background:#E4E9E5;border-radius:3px;overflow:hidden;margin-bottom:14px}
  #calibrationProgressFill{height:100%;width:0;background:#4A7856;transition:width .2s ease}
  #calibrationAutoStatus{width:100%;border-radius:8px;padding:13px 16px;background:#E8ECE8;color:#56605A;font-size:15px;font-weight:750;text-align:center}
  #calibrationAutoStatus.ready{background:#4A7856;color:#fff}
  #walkingCapture{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(12,16,14,.94);padding:20px;pointer-events:auto;z-index:13}
  #walkingCapture .walkingCard{width:min(560px,100%);max-height:92vh;overflow:auto;background:#FDFDFD;color:#1C201D;border-radius:8px;padding:22px;box-shadow:0 24px 80px rgba(0,0,0,.38)}
  #walkingCapture .walkingEyebrow{font-size:13px;font-weight:800;color:#4A7856;text-transform:uppercase;margin-bottom:8px}
  #walkingCapture h2{font-size:24px;line-height:1.2;margin-bottom:10px}
  #walkingCapture p{font-size:15px;line-height:1.45;color:#414843}
  #walkingCapture ul{padding-left:20px;margin:14px 0}
  #walkingCapture li{font-size:14px;line-height:1.4;margin:6px 0;color:#303632}
  #walkingCapture button{width:100%;border:none;border-radius:8px;padding:15px 16px;background:#4A7856;color:#fff;font-size:16px;font-weight:800;cursor:pointer}
  #walkingCapture button:disabled{background:#C9D2CB;color:#667068;cursor:not-allowed}
  #walkingDesktopActions{position:relative;width:100%}
  #walkingChooseVideoBtn{pointer-events:none}
  #walkingVideoInput{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;z-index:2;font-size:0}
  #walkingDesktopActions.busy #walkingVideoInput{pointer-events:none;cursor:not-allowed}
  #walkingProceedUnconfirmedBtn{margin-top:10px;background:#FDFDFD;color:#315D3D;border:2px solid #4A7856}
  #walkingProceedUnconfirmedBtn:disabled{background:#EEF0ED;color:#667068;border-color:#C9D2CB}
  #walkingCaptureStatus{margin-top:12px;padding:11px 12px;border-radius:8px;background:#EEF0ED;color:#49504B;font-size:14px;line-height:1.4}
  #walkingCaptureStatus.good{background:#D9E5DC;color:#285C3A;font-weight:700}
  #walkingCaptureStatus.warn{background:#FFF0E6;color:#7A351E;font-weight:700}
  body.walking-camera-unmirrored #cameraFrame video,body.walking-camera-unmirrored #cameraFrame canvas{transform:none}
  #advancedMarkerGate{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#0c100ef5;padding:20px;pointer-events:auto;z-index:11}
  #advancedMarkerGate .gateCard{width:min(520px,100%);max-height:92vh;overflow:auto;background:#FDFDFD;color:#1C201D;border-radius:24px;padding:22px;text-align:left;box-shadow:0 24px 80px rgba(0,0,0,.35)}
  #advancedMarkerGate .gateEyebrow{color:#4A7856;font-size:13px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;margin-bottom:8px}
  #advancedMarkerGate h2{font-size:24px;line-height:1.2;color:#1C201D;margin-bottom:10px}
  #advancedMarkerGate p{font-size:16px;line-height:1.45;color:#2C312E;margin-bottom:12px}
  #advancedMarkerGate .gateBox{background:#D9E5DC;border-radius:16px;padding:14px;margin:14px 0;color:#253C2B}
  #advancedMarkerGate .gateBox.warn{background:#FFF4E8;color:#503018}
  #advancedMarkerGate ul{padding-left:18px;margin:8px 0 0}
  #advancedMarkerGate li{font-size:15px;line-height:1.45;margin:4px 0}
  #advancedMarkerGate .gateActions{display:flex;flex-direction:column;gap:10px;margin-top:16px}
  #advancedMarkerGate button{border:none;border-radius:16px;padding:15px 16px;font-size:16px;font-weight:800;cursor:pointer;text-align:center}
  #markerConfirmBtn{background:#4A7856;color:#fff}
  #markerMissingBtn{background:#E18E6D;color:#1C201D}
  #markerBasicBtn,#markerBackBtn{background:#EEF0ED;color:#1C201D}
  #markerStoreBtn{background:#4A7856;color:#fff}
  #advancedMarkerGate .missingPanel{margin-top:14px;border-top:1px solid #E3E6E1;padding-top:14px}
  #diagnosticsBadge{position:absolute;right:16px;top:84px;z-index:4;background:rgba(28,32,29,.72);color:#FDFDFD;border-radius:18px;padding:9px 11px;font-size:12px;line-height:1.35;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);pointer-events:none;min-width:128px}
  #diagnosticsBadge strong{display:block;color:#D9E5DC;font-size:12px;margin-bottom:2px}
  #diagnosticsBadge.good{border:1px solid rgba(127,229,163,.65)}
  #diagnosticsBadge.warn{border:1px solid rgba(225,142,109,.75)}
  #lapStatus{position:absolute;left:50%;top:56%;transform:translate(-50%,-50%);z-index:4;width:min(340px,calc(100% - 40px));background:rgba(28,32,29,.82);color:#FDFDFD;border:1px solid rgba(217,229,220,.55);border-radius:16px;padding:10px 14px;text-align:center;font-size:14px;font-weight:650;line-height:1.35;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);pointer-events:none}
  .hidden{display:none !important}
  /* Celebration overlay */
  #celebrate{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:linear-gradient(180deg, rgba(74,120,86,0.92), rgba(28,32,29,0.92));text-align:center;padding:24px;flex-direction:column;gap:14px;pointer-events:auto;z-index:9;opacity:0;transition:opacity .35s ease-out}
  #celebrate.show{opacity:1}
  #celebrate .star{font-size:80px;animation:pop .6s ease-out}
  #celebrate h2{font-size:26px;font-weight:800;color:#fff}
  #celebrate .next{font-size:14px;color:#D9E5DC;font-weight:600;letter-spacing:1px;text-transform:uppercase}
  #celebrate .msg{font-size:17px;color:#FDFDFD;line-height:1.45;max-width:320px}
  #celebrate .dotsMini{display:flex;gap:6px;margin-top:8px}
  #celebrate .dotsMini span{width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,0.3)}
  #celebrate .dotsMini span.done{background:#fff}
  @keyframes pop{0%{transform:scale(0.3) rotate(-12deg);opacity:0}60%{transform:scale(1.2) rotate(8deg);opacity:1}100%{transform:scale(1) rotate(0);opacity:1}}
  .confetti{position:absolute;width:10px;height:14px;border-radius:2px;animation:fall 1.4s ease-out forwards;opacity:.9}
  @keyframes fall{0%{transform:translateY(-30vh) rotate(0deg);opacity:0}10%{opacity:1}100%{transform:translateY(120vh) rotate(720deg);opacity:0}}
</style>
</head>
<body>
<div id="stage">
  <div id="cameraFrame">
    <video id="video" playsinline autoplay muted></video>
    <canvas id="canvas"></canvas>
  </div>
  <div id="lapStatus" class="hidden" role="status">Keep your affected hand resting on the visible part of your lap while Rehyn locates the target.</div>
  <div id="ui">
    <div id="top">
      <button id="exitBtn" data-testid="assessment-exit">Exit</button>
      <div class="dots" id="dots"></div>
      <div class="label" id="taskLabel">T1</div>
    </div>
    <div id="bottom">
      <div id="stepTitle">Task 1 of 7</div>
      <div id="caption">Preparing…</div>
      <div id="voiceRow">
        <div id="voiceWave"><span></span><span></span><span></span><span></span></div>
        <div id="voiceText">Listening to instructions…</div>
      </div>
      <button id="skipBtn" data-testid="assessment-skip">Skip step</button>
    </div>
  </div>
  <div id="overlay">
    <h1>Ready to begin?</h1>
    <p>We will guide you through the movement tasks selected from your readiness answers. Move into the camera view, then follow the setup guidance.</p>
    <button id="startBtn" data-testid="assessment-start">Set Up Camera</button>
  </div>
  <div id="calibrationOverlay" class="hidden" data-testid="assessment-calibration">
    <div class="calibrationPanel">
      <h2 id="calibrationTitle">Let us find your seated position</h2>
      <p class="calibrationLead" id="calibrationLead">Sit still with your affected hand resting on your lap. Keep your face, shoulders, affected arm, hips, and knees inside the camera view.</p>
      <div id="calibrationChecklist">
        <div class="calibrationCheck" id="calibrationCamera"><span class="statusDot">1</span><span>Camera is ready</span></div>
        <div class="calibrationCheck" id="calibrationArm"><span class="statusDot">2</span><span>Face, shoulders, and affected arm are visible</span></div>
        <div class="calibrationCheck" id="calibrationSeat"><span class="statusDot">3</span><span>Affected hand and part of your lap are visible</span></div>
        <div class="calibrationCheck" id="calibrationLap"><span class="statusDot">4</span><span>Hold still while your lap target is located</span></div>
      </div>
      <div id="calibrationProgress"><div id="calibrationProgressFill"></div></div>
      <div id="calibrationAutoStatus" role="status" data-testid="calibration-auto-status">Keep still. Assessment will start automatically.</div>
    </div>
  </div>
  <div id="walkingCapture" class="hidden" data-testid="walking-capture">
    <div class="walkingCard">
      <div class="walkingEyebrow">Final walking observation</div>
      <h2 id="walkingCaptureTitle">Record a comfortable walk</h2>
      <p id="walkingCaptureLead">Ask a carer or family member to record from the side while you walk at your usual comfortable pace.</p>
      <ul>
        <li>Before walking, have the patient face the camera clearly for two seconds so Rehyn can confirm the video belongs to the same assessment.</li>
        <li>Keep the patient's head, trunk, hips, knees, feet, and walking aid visible for the entire recording.</li>
        <li>Use a fixed side view when possible. Otherwise move smoothly parallel at a safe distance.</li>
        <li>Do not zoom, walk backward, cross the patient's path, or film while providing hands-on support.</li>
      </ul>
      <div id="walkingDesktopActions" class="hidden" data-testid="walking-desktop-actions">
        <button id="walkingChooseVideoBtn" type="button" data-testid="walking-choose-video">Choose walking video</button>
        <input id="walkingVideoInput" type="file" accept="video/*" aria-label="Choose walking video" data-testid="walking-video-input" />
      </div>
      <div id="walkingMobileActions" class="hidden" data-testid="walking-mobile-actions">
        <button id="walkingRecordBtn" type="button" data-testid="walking-start-recording">Start recording walking</button>
      </div>
      <button id="walkingProceedUnconfirmedBtn" class="hidden" type="button" data-testid="walking-proceed-identity-unconfirmed">Use video and mark for review</button>
      <div id="walkingCaptureStatus" role="status">Preparing the walking capture...</div>
      <video id="walkingReviewVideo" class="hidden" playsinline muted preload="metadata"></video>
    </div>
  </div>
  <div id="advancedMarkerGate" class="hidden" data-testid="advanced-marker-gate">
    <div class="gateCard">
      <div class="gateEyebrow">AxonAI Hand Function Package</div>
      <h2>Next: advanced grasp-release task</h2>
      <p>This task observes you picking up and releasing a real lightweight object. Move slowly, and keep safety first.</p>
      <div class="gateBox">
        <p><strong>Please prepare one light, safe, easy-to-hold object:</strong></p>
        <ul>
          <li>Empty plastic cup</li>
          <li>Soft ball</li>
          <li>Light foam cylinder</li>
          <li>Small paper box</li>
        </ul>
      </div>
      <div class="gateBox warn">
        <p><strong>Please do not use:</strong> glass cups, hot drinks, heavy objects, sharp objects, or items that are very small, reflective, or transparent.</p>
        <p>To help AxonAI see the object clearly, place the AxonAI marker on the front of the object and keep the marker facing the camera.</p>
      </div>
      <div class="gateActions" id="markerChoicePanel">
        <button id="markerConfirmBtn" data-testid="marker-confirmed">I have an AxonAI marker and placed it on the object</button>
        <button id="markerMissingBtn" data-testid="marker-missing">I do not have a marker yet</button>
      </div>
      <div class="missingPanel hidden" id="markerMissingPanel">
        <p><strong>That is okay. You can complete the basic hand function tasks first.</strong></p>
        <p>Without a marker, AxonAI cannot reliably tell whether the object was grasped or released. When your marker is ready, you can return to the advanced grasp-release task.</p>
        <div class="gateActions">
          <button id="markerStoreBtn" data-testid="marker-store">Order AxonAI marker</button>
          <button id="markerBasicBtn" data-testid="marker-basic-fallback">Do basic hand tasks first</button>
          <button id="markerBackBtn" data-testid="marker-back-choice">Back to choices</button>
        </div>
      </div>
    </div>
  </div>
  <div id="diagnosticsBadge" class="hidden" data-testid="runtime-diagnostics">
    <strong>Frame status</strong>
    <span id="diagnosticsText">Preparing</span>
  </div>
  <div id="celebrate" class="hidden">
    <div class="star">&#11088;</div>
    <div class="next" id="celebrateLabel">Task 1 complete</div>
    <h2 id="celebrateTitle">Wonderful work!</h2>
    <p class="msg" id="celebrateMsg">You did beautifully. Take a breath — the next task is on its way.</p>
    <div class="dotsMini" id="celebrateDots"></div>
  </div>
</div>

<script>
window.__rehynStartRequested = false;
const earlyStartButton = document.getElementById("startBtn");
earlyStartButton.addEventListener("click", () => {
  window.__rehynStartRequested = true;
  earlyStartButton.textContent = "Opening camera...";
  earlyStartButton.setAttribute("aria-busy", "true");
});
</script>
<script type="module">
import { PoseLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "/vendor/mediapipe/vision_bundle.mjs";

const API_BASE = window.location.origin + "/api";
const stage = document.getElementById("stage");
const cameraFrame = document.getElementById("cameraFrame");
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const dotsEl = document.getElementById("dots");
const taskLabel = document.getElementById("taskLabel");
const stepTitle = document.getElementById("stepTitle");
const captionEl = document.getElementById("caption");
const voiceText = document.getElementById("voiceText");
const lapStatus = document.getElementById("lapStatus");
const ui = document.getElementById("ui");
const overlay = document.getElementById("overlay");
const startBtn = document.getElementById("startBtn");
const calibrationOverlay = document.getElementById("calibrationOverlay");
const calibrationTitle = document.getElementById("calibrationTitle");
const calibrationLead = document.getElementById("calibrationLead");
const calibrationCamera = document.getElementById("calibrationCamera");
const calibrationArm = document.getElementById("calibrationArm");
const calibrationSeat = document.getElementById("calibrationSeat");
const calibrationLap = document.getElementById("calibrationLap");
const calibrationProgressFill = document.getElementById("calibrationProgressFill");
const calibrationAutoStatus = document.getElementById("calibrationAutoStatus");
const walkingCapture = document.getElementById("walkingCapture");
const walkingCaptureTitle = document.getElementById("walkingCaptureTitle");
const walkingCaptureLead = document.getElementById("walkingCaptureLead");
const walkingDesktopActions = document.getElementById("walkingDesktopActions");
const walkingMobileActions = document.getElementById("walkingMobileActions");
const walkingChooseVideoBtn = document.getElementById("walkingChooseVideoBtn");
const walkingVideoInput = document.getElementById("walkingVideoInput");
const walkingRecordBtn = document.getElementById("walkingRecordBtn");
const walkingProceedUnconfirmedBtn = document.getElementById("walkingProceedUnconfirmedBtn");
const walkingCaptureStatus = document.getElementById("walkingCaptureStatus");
const walkingReviewVideo = document.getElementById("walkingReviewVideo");
const skipBtn = document.getElementById("skipBtn");
const exitBtn = document.getElementById("exitBtn");
const advancedMarkerGate = document.getElementById("advancedMarkerGate");
const markerChoicePanel = document.getElementById("markerChoicePanel");
const markerMissingPanel = document.getElementById("markerMissingPanel");
const markerConfirmBtn = document.getElementById("markerConfirmBtn");
const markerMissingBtn = document.getElementById("markerMissingBtn");
const markerStoreBtn = document.getElementById("markerStoreBtn");
const markerBasicBtn = document.getElementById("markerBasicBtn");
const markerBackBtn = document.getElementById("markerBackBtn");
const diagnosticsBadge = document.getElementById("diagnosticsBadge");
const diagnosticsText = document.getElementById("diagnosticsText");
const celebrateEl = document.getElementById("celebrate");
const celebrateLabel = document.getElementById("celebrateLabel");
const celebrateTitle = document.getElementById("celebrateTitle");
const celebrateMsg = document.getElementById("celebrateMsg");
const celebrateDots = document.getElementById("celebrateDots");
const URL_PARAMS = new URLSearchParams(window.location.search);
const VOICE_GUIDANCE_ENABLED = URL_PARAMS.get("voice_guidance") !== "0";

function classifyCameraDevice({
  userAgent=navigator.userAgent || "",
  userAgentDataMobile=navigator.userAgentData && navigator.userAgentData.mobile,
  maxTouchPoints=navigator.maxTouchPoints || 0,
  screenWidth=screen.width,
  screenHeight=screen.height,
  deviceMode=URL_PARAMS.get("device_mode"),
}={}){
  if(deviceMode === "mobile" || deviceMode === "phone") return "phone";
  if(deviceMode === "tablet") return "tablet";
  if(deviceMode === "desktop" || deviceMode === "web") return "web";
  if(userAgentDataMobile === true || /iPhone|iPod/i.test(userAgent) || (/Android/i.test(userAgent) && /Mobile/i.test(userAgent))){
    return "phone";
  }
  if(/iPad/i.test(userAgent) || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1) || (/Android/i.test(userAgent) && !/Mobile/i.test(userAgent))){
    return "tablet";
  }
  const shortScreenEdge = Math.min(Number(screenWidth) || Infinity, Number(screenHeight) || Infinity);
  return maxTouchPoints > 0 && shortScreenEdge <= 600 ? "phone" : "web";
}

const CAMERA_DEVICE_CLASS = classifyCameraDevice();
const CAMERA_FIT_MODE = CAMERA_DEVICE_CLASS === "phone" ? "cover" : "contain";

function fitCameraViewport(containerWidth, containerHeight, sourceWidth, sourceHeight, fitMode=CAMERA_FIT_MODE){
  const safeContainerWidth = Math.max(1, Number(containerWidth) || 1);
  const safeContainerHeight = Math.max(1, Number(containerHeight) || 1);
  const safeSourceWidth = Math.max(1, Number(sourceWidth) || 1);
  const safeSourceHeight = Math.max(1, Number(sourceHeight) || 1);
  const scale = fitMode === "cover"
    ? Math.max(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight)
    : Math.min(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight);
  const width = safeSourceWidth * scale;
  const height = safeSourceHeight * scale;
  return {
    left:(safeContainerWidth - width) / 2,
    top:(safeContainerHeight - height) / 2,
    width,
    height,
    fit:fitMode,
  };
}

function responsiveVideoSettings(longEdge, shortEdge, maxFrameRate=30){
  const portrait = stage.clientHeight > stage.clientWidth;
  return {
    facingMode:"user",
    width:{ideal:portrait ? shortEdge : longEdge},
    height:{ideal:portrait ? longEdge : shortEdge},
    frameRate:{ideal:maxFrameRate, max:maxFrameRate},
  };
}

function syncCameraViewport(){
  if(!video.videoWidth || !video.videoHeight) return;
  const rect = fitCameraViewport(stage.clientWidth, stage.clientHeight, video.videoWidth, video.videoHeight, CAMERA_FIT_MODE);
  cameraFrame.style.left = `${rect.left}px`;
  cameraFrame.style.top = `${rect.top}px`;
  cameraFrame.style.width = `${rect.width}px`;
  cameraFrame.style.height = `${rect.height}px`;
  document.body.dataset.cameraDevice = CAMERA_DEVICE_CLASS;
  document.body.dataset.cameraFit = rect.fit;
  if(canvas.width !== video.videoWidth) canvas.width = video.videoWidth;
  if(canvas.height !== video.videoHeight) canvas.height = video.videoHeight;
}

window.__rehynCameraViewportTest = {
  classifyCameraDevice,
  fitCameraViewport,
  syncCameraViewport,
  deviceClass:CAMERA_DEVICE_CLASS,
  fitMode:CAMERA_FIT_MODE,
};

window.addEventListener("resize", syncCameraViewport, {passive:true});
window.addEventListener("orientationchange", () => setTimeout(syncCameraViewport, 120), {passive:true});
video.addEventListener("resize", syncCameraViewport);
if(window.ResizeObserver) new ResizeObserver(syncCameraViewport).observe(stage);

// Pool of warm, encouraging task-completion lines (varied so they don't feel scripted)
const CELEBRATION_LINES = [
  { title: "Wonderful work!", msg: "You did beautifully. Take a breath — the next task is on its way." },
  { title: "Amazing effort!", msg: "I'm so proud of you. Let's keep this momentum going." },
  { title: "Brilliant!", msg: "That was excellent. You're making real progress." },
  { title: "Magnificent!", msg: "Every movement counts. You're doing incredibly well." },
  { title: "Bravo!", msg: "Beautiful control. Onward to the next." },
  { title: "Excellent!", msg: "That's the spirit. One step closer to recovery." },
  { title: "You've got this!", msg: "Strong, steady, and brave. Keep going." },
];
const CELEBRATION_VOICES = [
  "Wonderful work! You did beautifully. Take a breath, the next task is on its way.",
  "Amazing effort! I'm so proud of you. Let's keep this momentum going.",
  "Brilliant! That was excellent. You're making real progress.",
  "Magnificent! Every movement counts. You're doing incredibly well.",
  "Bravo! Beautiful control. Onward to the next.",
  "Excellent! That's the spirit. One step closer to recovery.",
];

const AXONAI_MARKER_STORE_URL = "/store/axonai-marker";
const ADVANCED_MARKER_TASK_IDS = new Set(["T4", "T5"]);
const POSE_SCAN_INTERVAL_MS = 0;
const MARKER_SCAN_INTERVAL_MS = 120;
const HAND_SCAN_INTERVAL_MS = 0;
const HAND_PACKAGE_POSE_SCAN_INTERVAL_MS = 0;
const HAND_BACKOFF_SCAN_INTERVAL_MS = 180;
const HAND_BACKOFF_POSE_SCAN_INTERVAL_MS = 800;
const HAND_LANDMARK_FRESH_MS = 350;
const HAND_BACKOFF_LANDMARK_FRESH_MS = 2600;
const MARKER_JITTER_LIMIT = 0.035;
const MIN_RUNTIME_FPS = 15;
const HAND_METRIC_NAMES = new Set([
  "finger_extension",
  "palm_openness",
  "thumb_index_spread",
  "closure_completeness",
  "closing_speed",
  "pinch_distance",
  "pinch_accuracy",
  "pinch_stability",
  "hand_opening",
  "open_close_timing",
  "unwanted_finger_flexion",
  "object_hand_coupling",
  "hold_stability",
  "release_delay",
  "object_hand_separation",
  "placement_endpoint_error",
]);
const HAND_CONNECTIONS = HandLandmarker.HAND_CONNECTIONS || [
  [0,1],[1,2],[2,3],[3,4],
  [0,5],[5,6],[6,7],[7,8],
  [5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],
  [13,17],[0,17],[17,18],[18,19],[19,20],
];

let landmarker = null;
let handLandmarker = null;
let drawingUtils = null;
let tasks = [];
let voiceId = "nova";
let currentTaskIdx = 0;
let currentStepIdx = 0;
let taskResults = []; // accumulating
let stepStartTime = 0;
let inTargetSince = null;
let lastInTargetTs = 0;
let stepCompleted = false;
let stepMetrics = {};
let trunkLeanMax = 0;
let shoulderFlexionMax = 0;
let shoulderHikeDetected = false;
let kneeExtensionMaxDeg = 0;
let ankleDorsiflexionMax = 0;
let affectedPelvisShiftMax = 0;
let lateralTrunkShiftMax = 0;
let shoulderElevationMaxDeg = 0;
let elbowFlexionMaxDeg = 0;
let hipFlexionMaxDeg = 0;
let kneeFlexionMaxDeg = 0;
let toeClearanceMaxRatio = 0;
let circumductionMaxRatio = 0;
let affectedStepLengthMaxRatio = 0;
let affectedWristMoveMaxRatio = 0;
let unaffectedWristMoveMaxRatio = 0;
let handToMouthMinRatio = Infinity;
let bodyMetricSamples = [];
let stepStartBodyState = null;
let gaitPelvisTravelMaxRatio = 0;
let gaitAffectedAnkleTravelMaxRatio = 0;
let gaitUnaffectedAnkleTravelMaxRatio = 0;
let gaitAlternationCount = 0;
let lastGaitLead = 0;
let gaitObservedFrameCount = 0;
let gaitFullBodyVisibleFrameCount = 0;
let running = false;
let audioEl = new Audio();
const voiceAudioCache = new Map();
const voiceAudioInflight = new Map();
let taskLoadPromise = null;
let audioUnlockPromise = null;
let latestHandLandmarks = null;        // selected affected hand only (21 points)
let latestHandedness = "";             // survey-selected anatomical side: "Left" / "Right"
let affectedHandTrackWrist = null;
let affectedHandTrackSeenAt = 0;
let latestPoseLandmarks = null;        // result.landmarks[0] from PoseLandmarker (33 points)
let latestPoseWorldLandmarks = null;   // estimated 3D world landmarks from PoseLandmarker
let dynamicTargetPos = null;           // {x,y} locked once a dynamic body target is calibrated
function newMouthTargetCalibration(){
  return {samples:[], target:null, locked:false, lastSampleKey:null};
}
let mouthTargetCalibration = newMouthTargetCalibration();
function newLapTargetCalibration(){
  return {samples:[], target:null, ready:false, announced:false, lastCandidateAt:0};
}
let lapTargetCalibration = newLapTargetCalibration();
let assessmentLapTarget = null;
let lapCalibrationDiagnostic = {
  reason:"waiting_for_pose",
  guidance:"Keep your affected hand relaxed on the top of your same-side thigh."
};
const LAP_CALIBRATION_MIN_SAMPLES = 8;
const LAP_CALIBRATION_MIN_MS = 650;
const CALIBRATION_INSTRUCTION = "Before we begin, sit still with your affected hand resting on the visible part of your lap. Keep your face, shoulders, affected arm, and the top of your affected thigh in view. You do not need to show your knees or your full lap. I will locate your lap target for the assessment.";
const CALIBRATION_COMPLETE_INSTRUCTION = "Calibration complete. Stay seated in this position and do not move the camera. We will begin the assessment now.";
let calibratingAssessment = false;
let calibrationInstructionFinished = false;
let preAssessmentCalibrationReady = false;
let preservePreAssessmentLapCalibration = false;
let calibrationAutoStartInProgress = false;
let handOpenScore = 0;                 // 0..1 — finger extension confidence
let fistClosureScore = 0;              // 0..1 — mass finger flexion confidence
let pinchScore = 0;                    // 0..1 — pinch confidence (1 = very close)
let palmFacingScore = 0;               // 0..1 — palm plane faces camera rather than edge-on
const PALM_FACING_THRESHOLD = 0.38;
let fingerTotalFlexionMaxDeg = 0;
let fingerAbductionMaxRatio = 0;
let thumbIndexMinDistanceRatio = Infinity;
// Pull signed-in user id from URL (?uid=…) so /assessment/submit attributes the
// new assessment to the correct user and credits get debited from their wallet.
let advancedGateSeen = {};
let advancedObjectModeByTask = {};
let waitingForAdvancedGate = false;
let lastFrameTs = 0;
let lastPoseScanTs = 0;
let currentFps = 0;
let frameStats = {totalFrames:0, handFrames:0, markerFrames:0};
let markerCanvas = document.createElement("canvas");
markerCanvas.width = 160;
markerCanvas.height = 90;
let markerCtx = markerCanvas.getContext("2d", {willReadFrequently:true});
let lastMarkerScanTs = 0;
let lastHandScanTs = 0;
let latestHandSeenAt = 0;
let markerHistory = [];
let latestMarker = null; // {object_center, object_visibility, object_stability}
let handObjectOverlapStartedAt = null;
let handObjectOverlapMs = 0;
let objectTransportSamples = [];
let visionFilesetResolver = null;
let walkingVideoValidator = null;
let walkingVideoValidatorPromise = null;
let motionFrames = [];
let lastMotionSampleTs = 0;
const MOTION_SAMPLE_INTERVAL_MS = 100;
const MAX_MOTION_FRAMES = 2400;
const CURRENT_USER_ID = URL_PARAMS.get("uid") || "";
const ASSESSMENT_PACKAGE = URL_PARAMS.get("package") || "upper_limb";
const ASSIGNED_TASK_IDS = (URL_PARAMS.get("task_ids") || "")
  .split(",").map(value => value.trim()).filter(Boolean);
const START_TASK_ID = URL_PARAMS.get("start_task") || "";
const PREVIOUSLY_COMPLETED_TASK_IDS = new Set(
  (URL_PARAMS.get("completed_tasks") || "").split(",").map(value => value.trim()).filter(Boolean)
);
const AFFECTED_SIDE = URL_PARAMS.get("affected_side") === "left" ? "left" : "right";
const IS_MOBILE_CAPTURE_DEVICE = CAMERA_DEVICE_CLASS !== "web";
const TASK_VIDEO_DB_NAME = "rehyn-task-videos-v1";
const TASK_VIDEO_STORE_NAME = "task-videos";
let activeTaskRecorder = null;
let activeTaskRecording = null;
let pendingTaskVideoSaves = new Set();
let pendingTaskProgressSaves = new Set();
let recorderUnavailableReported = false;
let walkingCaptureActive = false;
let walkingCapturePromptPlayed = false;
let walkingCameraSwitching = false;
let pendingUnconfirmedWalkingVideo = null;
let pendingUnconfirmedWalkingValidation = null;
const FACE_SIGNATURE_SIZE = 12;
const MIN_FACE_SIGNATURE_SPAN_PX = 32;
const WALKING_FACE_MATCH_THRESHOLD = 0.58;
const faceSignatureCanvas = document.createElement("canvas");
faceSignatureCanvas.width = FACE_SIGNATURE_SIZE;
faceSignatureCanvas.height = FACE_SIGNATURE_SIZE;
const faceSignatureCtx = faceSignatureCanvas.getContext("2d", {willReadFrequently:true});
let patientFaceReferenceSamples = [];
let patientFaceReference = null;
let lastPatientFaceReferenceAt = 0;

function taskDomain(task=tasks[currentTaskIdx]){
  const id = task && task.id ? task.id : "";
  if(id.startsWith("H")) return "hand";
  if(id.startsWith("L")) return "lower_limb";
  if(id.startsWith("B")) return "balance";
  return "upper_limb";
}

function isHandTask(){ return taskDomain() === "hand"; }
function isLowerTask(){ return taskDomain() === "lower_limb"; }
function isBalanceTask(){ return taskDomain() === "balance"; }
function isWalkingTask(task=tasks[currentTaskIdx]){ return !!(task && task.id === "L6"); }

function postRN(data){
  if(window.ReactNativeWebView){
    window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }
}

function persistTaskProgress(taskId){
  if(!CURRENT_USER_ID || !taskId) return Promise.resolve(null);
  const query = new URLSearchParams({package_id: ASSESSMENT_PACKAGE, task_id: taskId});
  const request = fetch(`${API_BASE}/assessment/task-progress?${query.toString()}`, {
    method:"POST",
    headers:{"X-User-Id": CURRENT_USER_ID},
  }).then(response => {
    if(!response.ok) throw new Error(`Task progress save failed (${response.status})`);
    return response.json();
  }).catch(error => {
    postRN({type:"task_progress_error", package_id:ASSESSMENT_PACKAGE, task_id:taskId, message:String(error)});
    return null;
  });
  pendingTaskProgressSaves.add(request);
  request.finally(() => pendingTaskProgressSaves.delete(request));
  return request;
}

function openTaskVideoDatabase(){
  return new Promise((resolve, reject) => {
    if(!window.indexedDB){ reject(new Error("IndexedDB is unavailable")); return; }
    const request = indexedDB.open(TASK_VIDEO_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if(!database.objectStoreNames.contains(TASK_VIDEO_STORE_NAME)){
        database.createObjectStore(TASK_VIDEO_STORE_NAME, {keyPath:"key"});
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open task video storage"));
  });
}

async function saveTaskVideoLocally(record){
  const database = await openTaskVideoDatabase();
  try{
    await new Promise((resolve, reject) => {
      const transaction = database.transaction(TASK_VIDEO_STORE_NAME, "readwrite");
      transaction.objectStore(TASK_VIDEO_STORE_NAME).put(record);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error("Could not save task video"));
      transaction.onabort = () => reject(transaction.error || new Error("Task video save was cancelled"));
    });
  }finally{
    database.close();
  }
}

function supportedTaskVideoMimeType(){
  if(!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
  const candidates = [
    "video/mp4;codecs=avc1.42E01E",
    "video/mp4",
    "video/webm;codecs=vp8",
    "video/webm",
  ];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

function beginTaskRecording(taskId){
  if(activeTaskRecorder && activeTaskRecording && activeTaskRecording.taskId === taskId) return;
  if(!window.MediaRecorder || !video.srcObject){
    if(!recorderUnavailableReported){
      recorderUnavailableReported = true;
      postRN({type:"task_video_unavailable", message:"This device does not support assessment video recording."});
    }
    return;
  }
  try{
    const sourceTrack = video.srcObject.getVideoTracks()[0];
    if(!sourceTrack) throw new Error("Camera video track is unavailable");
    const recordingStream = new MediaStream([sourceTrack]);
    const mimeType = supportedTaskVideoMimeType();
    const options = {videoBitsPerSecond:700000};
    if(mimeType) options.mimeType = mimeType;
    const recorder = new MediaRecorder(recordingStream, options);
    const recording = {
      taskId,
      startedAt: performance.now(),
      chunks: [],
      mimeType: mimeType || "video/webm",
    };
    recorder.ondataavailable = event => {
      if(event.data && event.data.size > 0) recording.chunks.push(event.data);
    };
    recorder.onerror = event => {
      postRN({type:"task_video_error", task_id:taskId, message:String(event.error || "Recording failed")});
    };
    recorder.start(1000);
    activeTaskRecorder = recorder;
    activeTaskRecording = recording;
    postRN({type:"task_video_recording", package_id:ASSESSMENT_PACKAGE, task_id:taskId});
  }catch(e){
    postRN({type:"task_video_error", task_id:taskId, message:String(e)});
  }
}

function uploadTaskVideoThroughBackend(recording, blob, durationMs, onUploadProgress=null){
  return new Promise((resolve, reject) => {
    const query = new URLSearchParams({
      package_id: ASSESSMENT_PACKAGE,
      task_id: recording.taskId,
      duration_ms: String(durationMs),
    });
    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE}/assessment/task-videos?${query.toString()}`);
    request.setRequestHeader("Content-Type", blob.type || recording.mimeType || "video/webm");
    request.setRequestHeader("X-User-Id", CURRENT_USER_ID);
    if(request.upload && typeof onUploadProgress === "function"){
      request.upload.onprogress = event => {
        if(event.lengthComputable && event.total > 0){
          onUploadProgress(Math.max(0, Math.min(1, event.loaded / event.total)));
        }
      };
    }
    request.onerror = () => reject(new Error("Video upload failed because the network connection was interrupted."));
    request.onabort = () => reject(new Error("Video upload was cancelled."));
    request.onload = () => {
      if(request.status < 200 || request.status >= 300){
        reject(new Error(`Video upload failed (${request.status})`));
        return;
      }
      if(typeof onUploadProgress === "function") onUploadProgress(1);
      try{
        resolve(JSON.parse(request.responseText || "{}"));
      }catch(error){
        reject(new Error("Video upload returned an invalid response."));
      }
    };
    request.send(blob);
  });
}

function putTaskVideoDirectly(uploadUrl, blob, contentType, onUploadProgress=null){
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", uploadUrl);
    request.setRequestHeader("Content-Type", contentType);
    if(request.upload && typeof onUploadProgress === "function"){
      request.upload.onprogress = event => {
        if(event.lengthComputable && event.total > 0){
          onUploadProgress(Math.max(0, Math.min(.97, .97 * event.loaded / event.total)));
        }
      };
    }
    request.onerror = () => reject(new Error("Direct video upload was interrupted."));
    request.onabort = () => reject(new Error("Direct video upload was cancelled."));
    request.onload = () => {
      if(request.status < 200 || request.status >= 300){
        reject(new Error(`Direct video upload failed (${request.status})`));
        return;
      }
      resolve(true);
    };
    request.send(blob);
  });
}

async function uploadTaskVideoToCloud(recording, blob, durationMs, onUploadProgress=null){
  const contentType = (blob.type || recording.mimeType || "video/webm").split(";", 1)[0];
  const ticketQuery = new URLSearchParams({
    package_id: ASSESSMENT_PACKAGE,
    task_id: recording.taskId,
    duration_ms: String(durationMs),
    content_type: contentType,
    size_bytes: String(blob.size),
  });
  try{
    const ticketResponse = await fetch(`${API_BASE}/assessment/task-videos/upload-ticket?${ticketQuery.toString()}`, {
      method:"POST",
      headers:{"X-User-Id":CURRENT_USER_ID},
    });
    if(ticketResponse.status === 503){
      return uploadTaskVideoThroughBackend(recording, blob, durationMs, onUploadProgress);
    }
    if(!ticketResponse.ok) throw new Error(`Could not prepare direct upload (${ticketResponse.status})`);
    const ticket = await ticketResponse.json();
    await putTaskVideoDirectly(ticket.upload_url, blob, ticket.content_type, onUploadProgress);
    const completed = await fetch(`${API_BASE}/assessment/task-videos/complete`, {
      method:"POST",
      headers:{"Content-Type":"application/json", "X-User-Id":CURRENT_USER_ID},
      body:JSON.stringify({
        video_id:ticket.video_id,
        object_key:ticket.object_key,
        package_id:ASSESSMENT_PACKAGE,
        task_id:recording.taskId,
        duration_ms:durationMs,
        content_type:ticket.content_type,
        size_bytes:blob.size,
      }),
    });
    if(!completed.ok) throw new Error(`Could not finalize direct upload (${completed.status})`);
    if(typeof onUploadProgress === "function") onUploadProgress(1);
    return completed.json();
  }catch(error){
    postRN({type:"task_video_upload_fallback", task_id:recording.taskId, message:String(error)});
    return uploadTaskVideoThroughBackend(recording, blob, durationMs, onUploadProgress);
  }
}

async function persistTaskVideo(recording, blob, {onUploadProgress=null}={}){
  const durationMs = Number.isFinite(recording.durationMs)
    ? Math.max(0, Math.round(recording.durationMs))
    : Math.max(0, Math.round(performance.now() - recording.startedAt));
  const localKey = `${CURRENT_USER_ID || "anonymous"}:${ASSESSMENT_PACKAGE}:${recording.taskId}`;
  const localSavePromise = (async () => {
    try{
      await saveTaskVideoLocally({
        key: localKey,
        userId: CURRENT_USER_ID || "anonymous",
        packageId: ASSESSMENT_PACKAGE,
        taskId: recording.taskId,
        createdAt: new Date().toISOString(),
        durationMs,
        mimeType: blob.type || recording.mimeType,
        blob,
      });
      return true;
    }catch(e){
      postRN({type:"task_video_error", task_id:recording.taskId, message:`Local save failed: ${String(e)}`});
      return false;
    }
  })();

  const cloudSavePromise = CURRENT_USER_ID
    ? uploadTaskVideoToCloud(recording, blob, durationMs, onUploadProgress).catch(e => {
        postRN({type:"task_video_error", task_id:recording.taskId, message:String(e)});
        return null;
      })
    : Promise.resolve(null);
  const [localSaved, cloudRecord] = await Promise.all([localSavePromise, cloudSavePromise]);

  if(localSaved || cloudRecord){
    postRN({
      type:"task_video_saved",
      package_id:ASSESSMENT_PACKAGE,
      task_id:recording.taskId,
      local_saved:localSaved,
      cloud_saved:!!cloudRecord && (cloudRecord.storage === "gridfs" || cloudRecord.storage === "r2"),
      server_saved:!!cloudRecord,
      video:cloudRecord,
    });
  }
}

function stopAndSaveTaskRecording(taskId){
  const recorder = activeTaskRecorder;
  const recording = activeTaskRecording;
  activeTaskRecorder = null;
  activeTaskRecording = null;
  if(!recorder || !recording || recording.taskId !== taskId || recorder.state === "inactive"){
    return Promise.resolve();
  }
  const savePromise = new Promise(resolve => {
    recorder.onstop = async () => {
      try{
        const mimeType = recorder.mimeType || recording.mimeType || "video/webm";
        const blob = new Blob(recording.chunks, {type:mimeType});
        if(blob.size > 0) await persistTaskVideo(recording, blob);
      }catch(e){
        postRN({type:"task_video_error", task_id:taskId, message:String(e)});
      }finally{
        recording.chunks.length = 0;
        resolve();
      }
    };
    try{
      recorder.requestData();
      recorder.stop();
    }catch(e){
      postRN({type:"task_video_error", task_id:taskId, message:String(e)});
      resolve();
    }
  });
  pendingTaskVideoSaves.add(savePromise);
  savePromise.finally(() => pendingTaskVideoSaves.delete(savePromise));
  return savePromise;
}

function compactLandmarks(points){
  if(!points || !points.length) return null;
  return points.map(point => [
    +Number(point.x || 0).toFixed(5),
    +Number(point.y || 0).toFixed(5),
    +Number(point.z || 0).toFixed(5),
    +Number(point.visibility == null ? 1 : point.visibility).toFixed(4),
  ]);
}

function captureMotionFrame(now){
  if(!running || calibratingAssessment || motionFrames.length >= MAX_MOTION_FRAMES) return;
  if(now - lastMotionSampleTs < MOTION_SAMPLE_INTERVAL_MS) return;
  const task = tasks[currentTaskIdx];
  const step = getCurrentStep();
  if(!task || !step) return;
  const pose2d = compactLandmarks(latestPoseLandmarks);
  const poseWorld3d = compactLandmarks(latestPoseWorldLandmarks);
  const hand2d = compactLandmarks(latestHandLandmarks);
  if(!pose2d && !hand2d) return;
  lastMotionSampleTs = now;
  motionFrames.push({
    timestamp_ms: Math.round(now),
    task_id: task.id,
    step_id: step.id,
    domain: taskDomain(task),
    pose_2d: pose2d,
    pose_world_3d: poseWorld3d,
    hand_2d: hand2d,
    hand_side: latestHandedness || null,
  });
}

async function loadTasks(){
  const taskQuery = new URLSearchParams({package:ASSESSMENT_PACKAGE});
  if(ASSIGNED_TASK_IDS.length) taskQuery.set("task_ids", ASSIGNED_TASK_IDS.join(","));
  const res = await fetch(`${API_BASE}/assessment/tasks?${taskQuery.toString()}`, {
    headers: CURRENT_USER_ID ? {"X-User-Id": CURRENT_USER_ID} : {},
  });
  if(!res.ok){
    const detail = await res.text();
    throw new Error(`Task selection failed (${res.status}): ${detail.slice(0, 160)}`);
  }
  const json = await res.json();
  tasks = json.tasks;
  voiceId = json.voice_id;
  const overlayCopy = overlay.querySelector("p");
  if(overlayCopy) overlayCopy.textContent = `We will guide you through ${tasks.length} short movement tasks using your camera. Move into the camera view, then tap Start.`;
  if(START_TASK_ID){
    const startIdx = tasks.findIndex((task) => task.id === START_TASK_ID);
    if(startIdx >= 0) currentTaskIdx = startIdx;
  }
  tasks.forEach((task, index) => {
    if(!PREVIOUSLY_COMPLETED_TASK_IDS.has(task.id)) return;
    taskResults[index] = {
      task_id: task.id,
      completed_steps: task.steps.length,
      total_steps: task.steps.length,
      duration_ms: 0,
      steps: [],
      metrics: {resumed_from_saved_progress: true},
    };
  });
  renderDots();
}

function ensureTasksLoaded(){
  if(!taskLoadPromise){
    taskLoadPromise = loadTasks().catch(error => {
      taskLoadPromise = null;
      throw error;
    });
  }
  return taskLoadPromise;
}

function renderDots(){
  dotsEl.innerHTML = "";
  tasks.forEach((t, i) => {
    const d = document.createElement("div");
    d.className = "dot" + (i===currentTaskIdx?" active":"") + (i<currentTaskIdx?" done":"");
    dotsEl.appendChild(d);
  });
  if(tasks[currentTaskIdx]) taskLabel.textContent = tasks[currentTaskIdx].id;
}

async function setupCamera(){
  try{
    if(!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      throw new Error("Camera access requires a secure HTTPS connection on this device.");
    }
    const videoSettings = (ASSESSMENT_PACKAGE === "hand" || ASSESSMENT_PACKAGE === "initial")
      ? responsiveVideoSettings(640, 480)
      : responsiveVideoSettings(480, 360);
    const stream = await Promise.race([
      navigator.mediaDevices.getUserMedia({video:videoSettings, audio:false}),
      new Promise((_, reject) => setTimeout(() => reject(new Error("Camera permission request timed out.")), 15000)),
    ]);
    video.srcObject = stream;
    await new Promise((resolve, reject) => {
      if(video.readyState >= 1 && video.videoWidth > 0){ resolve(); return; }
      const timeout = setTimeout(() => reject(new Error("Camera opened but no video frames arrived.")), 10000);
      video.onloadedmetadata = () => {
        clearTimeout(timeout);
        resolve();
      };
    });
    await video.play().catch(() => null);
    syncCameraViewport();
    return true;
  }catch(e){
    captionEl.textContent = String(e && e.message ? e.message : "Camera permission denied. Please allow camera access.");
    postRN({type:"camera_error", message:String(e)});
    return false;
  }
}

async function getVisionFilesetResolver(){
  if(!visionFilesetResolver){
    visionFilesetResolver = await FilesetResolver.forVisionTasks(
      "/vendor/mediapipe/wasm"
    );
  }
  return visionFilesetResolver;
}

async function setupPose(){
  const filesetResolver = await getVisionFilesetResolver();
  landmarker = await PoseLandmarker.createFromOptions(filesetResolver, {
    baseOptions:{ modelAssetPath: "/vendor/mediapipe/models/pose_landmarker_lite.task" },
    runningMode: "VIDEO",
    numPoses: 1,
  });
}

async function getWalkingVideoValidator(){
  if(walkingVideoValidator) return walkingVideoValidator;
  if(!walkingVideoValidatorPromise){
    walkingVideoValidatorPromise = (async () => {
      const filesetResolver = await getVisionFilesetResolver();
      const validator = await PoseLandmarker.createFromOptions(filesetResolver, {
        baseOptions:{ modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task" },
        runningMode:"VIDEO",
        numPoses:1,
      });
      walkingVideoValidator = validator;
      return validator;
    })().catch(error => {
      walkingVideoValidatorPromise = null;
      throw error;
    });
  }
  return walkingVideoValidatorPromise;
}

function preloadWalkingVideoValidator(){
  window.setTimeout(() => {
    getWalkingVideoValidator().catch(error => {
      postRN({type:"walking_validator_preload_error", message:String(error)});
    });
  }, 8000);
}

async function setupHand(){
  const filesetResolver = await getVisionFilesetResolver();
  try{
    handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
      baseOptions:{ modelAssetPath: "/vendor/mediapipe/models/hand_landmarker.task" },
      runningMode: "VIDEO",
      numHands: 2,
      minHandDetectionConfidence: 0.65,
      minHandPresenceConfidence: 0.65,
      minTrackingConfidence: 0.7,
    });
  }catch(e){
    // hand detection optional — falls back to pose-based heuristics
    handLandmarker = null;
    postRN({type:"hand_landmarker_unavailable", message:String(e)});
  }
}

async function setupTrackingModels(){
  await setupPose();
  if(ASSESSMENT_PACKAGE === "hand"){
    await setupHand();
  }
  drawingUtils = new DrawingUtils(ctx);
}

function setWalkingCaptureStatus(message, tone=""){
  walkingCaptureStatus.textContent = message;
  walkingCaptureStatus.classList.toggle("good", tone === "good");
  walkingCaptureStatus.classList.toggle("warn", tone === "warn");
}

async function showWalkingCapture(task){
  finalizePatientFaceReference();
  pendingUnconfirmedWalkingVideo = null;
  pendingUnconfirmedWalkingValidation = null;
  walkingProceedUnconfirmedBtn.classList.add("hidden");
  walkingCaptureTitle.textContent = IS_MOBILE_CAPTURE_DEVICE
    ? "Record the walking test"
    : "Upload a walking video";
  walkingCaptureLead.textContent = IS_MOBILE_CAPTURE_DEVICE
    ? "Hand the phone to a carer or family member. They should record from the side and keep your whole body visible."
    : "A computer should stay in place. Ask a carer or family member to record the walk on a phone, then upload that video here. The patient should face the camera for two seconds before turning sideways to walk.";
  walkingDesktopActions.classList.toggle("hidden", IS_MOBILE_CAPTURE_DEVICE);
  walkingMobileActions.classList.toggle("hidden", !IS_MOBILE_CAPTURE_DEVICE);
  setWalkingCaptureStatus(IS_MOBILE_CAPTURE_DEVICE
    ? "When everyone is safely positioned, tap Start recording walking."
    : "Choose the walking video. Rehyn will confirm that it is the same patient before uploading; framing notes will not block the video.");
  walkingCapture.classList.remove("hidden");
  ui.classList.add("hidden");
  renderDots();
  if(!walkingCapturePromptPlayed){
    walkingCapturePromptPlayed = true;
    const prompt = IS_MOBILE_CAPTURE_DEVICE
      ? "For the walking test, hand the phone to a carer or family member. Keep your whole body visible from the side. Tap Start recording walking when everyone is safely positioned."
      : "For the walking test, ask a carer or family member to record on a phone. Face the camera clearly for two seconds first, then turn sideways and walk while keeping your whole body visible. Upload that video here.";
    await playVoice(prompt);
  }
}

function facePoseIsFrontal(pose){
  if(!pose || pose.length < 11) return false;
  const required = [pose[0], pose[2], pose[5], pose[9], pose[10]];
  if(!required.every(point => landmarkIsUsable(point, 0.25))) return false;
  const eyeDistance = Math.abs(pose[2].x - pose[5].x);
  if(eyeDistance < 0.018) return false;
  const eyeCenterX = (pose[2].x + pose[5].x) / 2;
  return Math.abs(pose[0].x - eyeCenterX) <= eyeDistance * 0.72;
}

function normalizedFaceAppearance(source, pose){
  if(!faceSignatureCtx || !source || !facePoseIsFrontal(pose)) return null;
  const sourceWidth = Number(source.videoWidth || source.naturalWidth || source.width || 0);
  const sourceHeight = Number(source.videoHeight || source.naturalHeight || source.height || 0);
  if(sourceWidth < 1 || sourceHeight < 1) return null;
  const points = pose.slice(0, 11).filter(point => landmarkIsUsable(point, 0.18));
  if(points.length < 7) return null;
  const minX = Math.min(...points.map(point => point.x));
  const maxX = Math.max(...points.map(point => point.x));
  const minY = Math.min(...points.map(point => point.y));
  const maxY = Math.max(...points.map(point => point.y));
  const observedFaceSpanPx = Math.max((maxX - minX) * sourceWidth, (maxY - minY) * sourceHeight);
  if(observedFaceSpanPx < MIN_FACE_SIGNATURE_SPAN_PX) return null;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const faceSize = Math.min(0.85, Math.max(0.10, (maxX - minX) * 1.45, (maxY - minY) * 2.20));
  const cropX = Math.max(0, Math.min(1 - faceSize, centerX - faceSize / 2));
  const cropY = Math.max(0, Math.min(1 - faceSize, centerY - faceSize * 0.48));
  try{
    faceSignatureCtx.clearRect(0, 0, FACE_SIGNATURE_SIZE, FACE_SIGNATURE_SIZE);
    faceSignatureCtx.drawImage(
      source,
      cropX * sourceWidth,
      cropY * sourceHeight,
      faceSize * sourceWidth,
      faceSize * sourceHeight,
      0,
      0,
      FACE_SIGNATURE_SIZE,
      FACE_SIGNATURE_SIZE,
    );
    const rgba = faceSignatureCtx.getImageData(0, 0, FACE_SIGNATURE_SIZE, FACE_SIGNATURE_SIZE).data;
    const luminance = [];
    for(let index=0; index<rgba.length; index += 4){
      luminance.push(0.299 * rgba[index] + 0.587 * rgba[index+1] + 0.114 * rgba[index+2]);
    }
    const mean = luminance.reduce((sum, value) => sum + value, 0) / luminance.length;
    const variance = luminance.reduce((sum, value) => sum + (value-mean) ** 2, 0) / luminance.length;
    const deviation = Math.max(12, Math.sqrt(variance));
    const pixels = luminance.map(value => (value - mean) / deviation);
    const eyeDistance = Math.max(0.001, distance(pose[2], pose[5]));
    const geometry = [
      distance(pose[9], pose[10]) / eyeDistance,
      distance(pose[0], midpoint(pose[9], pose[10])) / eyeDistance,
    ];
    return {pixels, geometry};
  }catch(error){
    return null;
  }
}

function flippedFacePixels(pixels){
  const flipped = [];
  for(let row=0; row<FACE_SIGNATURE_SIZE; row += 1){
    for(let column=0; column<FACE_SIGNATURE_SIZE; column += 1){
      flipped.push(pixels[row * FACE_SIGNATURE_SIZE + (FACE_SIGNATURE_SIZE - 1 - column)]);
    }
  }
  return flipped;
}

function vectorCorrelation(left, right){
  if(!left || !right || left.length !== right.length || !left.length) return -1;
  let dot = 0;
  let leftMagnitude = 0;
  let rightMagnitude = 0;
  for(let index=0; index<left.length; index += 1){
    dot += left[index] * right[index];
    leftMagnitude += left[index] * left[index];
    rightMagnitude += right[index] * right[index];
  }
  return dot / Math.max(0.0001, Math.sqrt(leftMagnitude * rightMagnitude));
}

function faceSignatureSimilarity(reference, candidate){
  if(!reference || !candidate) return 0;
  const appearanceCorrelation = Math.max(
    vectorCorrelation(reference.pixels, candidate.pixels),
    vectorCorrelation(reference.pixels, flippedFacePixels(candidate.pixels)),
  );
  const appearanceScore = Math.max(0, Math.min(1, (appearanceCorrelation + 1) / 2));
  const geometryDelta = reference.geometry.reduce((sum, value, index) => {
    const candidateValue = Math.max(0.001, candidate.geometry[index] || 0.001);
    return sum + Math.abs(Math.log(Math.max(0.001, value) / candidateValue));
  }, 0) / reference.geometry.length;
  const geometryScore = Math.exp(-geometryDelta * 1.8);
  return appearanceScore * 0.82 + geometryScore * 0.18;
}

function capturePatientFaceReference(source, pose, now=performance.now()){
  if(patientFaceReference || now - lastPatientFaceReferenceAt < 220) return;
  const signature = normalizedFaceAppearance(source, pose);
  if(!signature) return;
  lastPatientFaceReferenceAt = now;
  patientFaceReferenceSamples.push(signature);
  if(patientFaceReferenceSamples.length > 8) patientFaceReferenceSamples.shift();
  if(patientFaceReferenceSamples.length >= 5) finalizePatientFaceReference();
}

function finalizePatientFaceReference(){
  if(patientFaceReference || patientFaceReferenceSamples.length < 3) return patientFaceReference;
  const sampleCount = patientFaceReferenceSamples.length;
  patientFaceReference = {
    pixels:patientFaceReferenceSamples[0].pixels.map((_, index) =>
      patientFaceReferenceSamples.reduce((sum, sample) => sum + sample.pixels[index], 0) / sampleCount
    ),
    geometry:patientFaceReferenceSamples[0].geometry.map((_, index) =>
      medianValue(patientFaceReferenceSamples.map(sample => sample.geometry[index]))
    ),
  };
  return patientFaceReference;
}

if(URL_PARAMS.get("test_mode") === "walking_identity"){
  window.__rehynWalkingIdentityTest = {
    threshold:WALKING_FACE_MATCH_THRESHOLD,
    similarity:faceSignatureSimilarity,
    flip:flippedFacePixels,
  };
}

async function waitForWalkingCameraFrame(timeoutMs=5000){
  try{ await video.play(); }catch(error){}
  const deadline = performance.now() + timeoutMs;
  while(performance.now() < deadline){
    if(video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) return true;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  return false;
}

async function switchToWalkingCamera(){
  walkingCameraSwitching = true;
  latestPoseLandmarks = null;
  latestPoseWorldLandmarks = null;
  latestHandLandmarks = null;
  const previousStream = video.srcObject;
  if(previousStream && previousStream.getTracks){
    previousStream.getTracks().forEach(track => track.stop());
  }
  const settings = responsiveVideoSettings(720, 480, 30);
  try{
    try{
      const stream = await navigator.mediaDevices.getUserMedia({
        video:{...settings, facingMode:{ideal:"environment"}},
        audio:false,
      });
      video.srcObject = stream;
      if(!await waitForWalkingCameraFrame()) throw new Error("Rear camera did not produce a video frame");
      document.body.classList.add("walking-camera-unmirrored");
      syncCameraViewport();
      return true;
    }catch(error){
      try{
        const fallback = await navigator.mediaDevices.getUserMedia({video:settings, audio:false});
        video.srcObject = fallback;
        if(!await waitForWalkingCameraFrame()) throw new Error("Camera did not produce a video frame");
        document.body.classList.remove("walking-camera-unmirrored");
        syncCameraViewport();
        return true;
      }catch(fallbackError){
        postRN({type:"camera_error", message:String(fallbackError || error)});
        return false;
      }
    }
  }finally{
    walkingCameraSwitching = false;
  }
}

function seekWalkingReviewVideo(timeSeconds){
  return new Promise((resolve, reject) => {
    let settled = false;
    const requestedTime = Math.max(0, Math.min(timeSeconds, walkingReviewVideo.duration || timeSeconds));
    const alreadyDecoded = walkingReviewVideo.readyState >= 2
      && Math.abs(walkingReviewVideo.currentTime - requestedTime) < 0.01;
    const finish = callback => {
      if(settled) return;
      settled = true;
      clearTimeout(timeout);
      walkingReviewVideo.onseeked = null;
      walkingReviewVideo.onerror = null;
      callback();
    };
    const timeout = setTimeout(() => finish(() => reject(new Error("Could not inspect this part of the video"))), 5000);
    walkingReviewVideo.onseeked = () => finish(resolve);
    walkingReviewVideo.onerror = () => finish(() => reject(new Error("The selected video could not be read")));
    walkingReviewVideo.currentTime = requestedTime;
    if(alreadyDecoded) setTimeout(() => finish(resolve), 0);
  });
}

async function validateWalkingVideo(file, onProgress=()=>{}){
  if(!file || !String(file.type || "").startsWith("video/")){
    return {ok:false, message:"Please choose a video file."};
  }
  if(Number(file.size || 0) > 35 * 1024 * 1024){
    return {ok:false, message:"This video is larger than 35 MB. Record at 1080p or lower, or trim the clip to the walking test, then choose it again."};
  }
  const objectUrl = URL.createObjectURL(file);
  let validator = null;
  try{
    onProgress({stage:"metadata", message:"Opening the video on this device..."});
    walkingReviewVideo.src = objectUrl;
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Video metadata timed out")), 8000);
      walkingReviewVideo.onloadedmetadata = () => { clearTimeout(timeout); resolve(); };
      walkingReviewVideo.onerror = () => { clearTimeout(timeout); reject(new Error("The selected video could not be opened")); };
    });
    const durationSeconds = Number(walkingReviewVideo.duration || 0);
    const width = Number(walkingReviewVideo.videoWidth || 0);
    const height = Number(walkingReviewVideo.videoHeight || 0);
    if(!Number.isFinite(durationSeconds) || durationSeconds <= 0){
      return {ok:false, message:"This video has no readable duration. Please choose a playable walking video."};
    }
    onProgress({stage:"model", message:"Preparing the walking video check..."});
    validator = await getWalkingVideoValidator();
    const reference = finalizePatientFaceReference();
    if(!reference){
      return {ok:false, message:"Rehyn could not create the seated patient reference. Return to the assessment camera and keep the patient's face clear before choosing the video again."};
    }
    const timestampBase = performance.now() + 1000;
    let detectorIndex = 0;
    const latestIdentityTime = Math.max(0, durationSeconds - 0.05);
    const identityTimes = Array.from(new Set(
      [0.05, durationSeconds * 0.18, durationSeconds * 0.38, durationSeconds * 0.55]
        .map(time => Math.round(Math.min(time, latestIdentityTime) * 1000) / 1000)
        .filter(time => time >= 0)
    ));
    const identityScores = [];
    for(let index=0; index<identityTimes.length; index += 1){
      onProgress({
        stage:"identity",
        current:index + 1,
        total:identityTimes.length,
        message:`Confirming the patient in the video (${index + 1}/${identityTimes.length})...`,
      });
      await seekWalkingReviewVideo(identityTimes[index]);
      const result = validator.detectForVideo(walkingReviewVideo, timestampBase + detectorIndex * 1000);
      detectorIndex += 1;
      const pose = result && result.landmarks && result.landmarks[0] ? result.landmarks[0] : null;
      const signature = normalizedFaceAppearance(walkingReviewVideo, pose);
      if(signature) identityScores.push(faceSignatureSimilarity(reference, signature));
    }
    const identityUnconfirmed = identityScores.length < 1;
    const patientMatchScore = identityUnconfirmed ? null : medianValue(identityScores);
    if(!identityUnconfirmed && patientMatchScore < WALKING_FACE_MATCH_THRESHOLD){
      return {ok:false, message:"This video does not appear consistent with the patient who completed the seated assessment. Please choose the correct patient's video or restart the assessment with the intended patient."};
    }

    const sampleCount = Math.max(3, Math.min(8, Math.ceil(durationSeconds * 2)));
    const sampledFrames = [];
    const walkingStartSeconds = 0;
    const walkingEndSeconds = durationSeconds * 0.94;
    for(let index=0; index<sampleCount; index += 1){
      onProgress({
        stage:"movement",
        current:index + 1,
        total:sampleCount,
        message:`Checking full-body walking visibility (${index + 1}/${sampleCount})...`,
      });
      const time = walkingStartSeconds + ((walkingEndSeconds - walkingStartSeconds) * index / (sampleCount - 1));
      await seekWalkingReviewVideo(time);
      const result = validator.detectForVideo(walkingReviewVideo, timestampBase + detectorIndex * 1000);
      detectorIndex += 1;
      const pose = result && result.landmarks && result.landmarks[0] ? result.landmarks[0] : null;
      const world = result && result.worldLandmarks && result.worldLandmarks[0] ? result.worldLandmarks[0] : null;
      if(pose) sampledFrames.push({time, pose, world, fullBody:fullBodyVisibleForWalking(pose)});
    }
    const poseFrameCount = sampledFrames.length;
    const fullBodyFrameCount = sampledFrames.filter(frame => frame.fullBody).length;
    const fullBodyRatio = poseFrameCount ? fullBodyFrameCount / poseFrameCount : 0;
    const qualityAdvisory = poseFrameCount < Math.ceil(sampleCount / 2)
      ? " The patient was small or difficult to track in parts of the clip, so movement confidence may be lower."
      : (fullBodyRatio < 0.50
        ? " Some body parts leave the frame, so movement confidence may be lower."
        : "");
    if(identityUnconfirmed){
      return {
        ok:false,
        allowProceed:true,
        reason:"identity_unconfirmed",
        message:"The patient's face is too small or unclear for Rehyn to confirm the identity. You can choose another video, or use this video and mark it for therapist review.",
        durationMs:Math.round(durationSeconds * 1000),
        width,
        height,
        poseFrameCount,
        fullBodyFrameCount,
        fullBodyRatio,
        patientMatchScore:null,
        samePatientConfirmed:false,
        identityStatus:"unconfirmed_patient_proceeded",
        sampledFrames,
      };
    }
    return {
      ok:true,
      message:`Same-patient check passed. The walking video is accepted.${qualityAdvisory}`,
      durationMs:Math.round(durationSeconds * 1000),
      width,
      height,
      poseFrameCount,
      fullBodyFrameCount,
      fullBodyRatio,
      patientMatchScore,
      samePatientConfirmed:true,
      identityStatus:"confirmed",
      sampledFrames,
    };
  }catch(error){
    return {ok:false, message:`Could not validate this video. ${String(error.message || error)}`};
  }finally{
    walkingReviewVideo.removeAttribute("src");
    walkingReviewVideo.load();
    URL.revokeObjectURL(objectUrl);
  }
}

async function completeUploadedWalkingTask(file, validation){
  const task = tasks[currentTaskIdx];
  if(!task || !isWalkingTask(task)) return;
  validation.sampledFrames.forEach((frame, index) => {
    if(motionFrames.length >= MAX_MOTION_FRAMES) return;
    motionFrames.push({
      timestamp_ms:Math.round(frame.time * 1000),
      task_id:task.id,
      step_id:"L6-S2",
      domain:"lower_limb",
      pose_2d:compactLandmarks(frame.pose),
      pose_world_3d:compactLandmarks(frame.world),
      hand_2d:null,
      hand_side:null,
      capture_source:"uploaded_walking_video",
      sample_index:index,
    });
  });
  const metrics = {
    walking_capture_mode:"uploaded_video",
    uploaded_video_duration_ms:validation.durationMs,
    uploaded_video_width:validation.width,
    uploaded_video_height:validation.height,
    gait_pose_frame_count:validation.poseFrameCount,
    gait_full_body_visible_frame_count:validation.fullBodyFrameCount,
    gait_full_body_visibility_ratio:+validation.fullBodyRatio.toFixed(3),
    walking_same_patient_confirmed:validation.samePatientConfirmed === true,
    walking_identity_status:validation.identityStatus || (validation.samePatientConfirmed ? "confirmed" : "unconfirmed_patient_proceeded"),
    walking_identity_review_required:validation.samePatientConfirmed !== true,
    walking_patient_match_score:Number.isFinite(validation.patientMatchScore) ? +validation.patientMatchScore.toFixed(3) : null,
  };
  const perStepDuration = Math.round(validation.durationMs / Math.max(1, task.steps.length));
  taskResults[currentTaskIdx] = {
    task_id:task.id,
    completed_steps:task.steps.length,
    total_steps:task.steps.length,
    duration_ms:validation.durationMs,
    steps:task.steps.map(step => ({step_id:step.id, completed:true, failure_code:null, duration_ms:perStepDuration, metrics})),
    metrics,
  };
  await persistTaskVideo({
    taskId:task.id,
    startedAt:performance.now(),
    durationMs:validation.durationMs,
    mimeType:file.type || "video/mp4",
  }, file, {
    onUploadProgress:progress => {
      const percent = Math.round(progress * 100);
      const prefix = validation.samePatientConfirmed
        ? "Video checks passed. Saving securely"
        : "Saving video for therapist review";
      setWalkingCaptureStatus(`${prefix} (${percent}%)...`, "good");
    },
  });
  walkingCaptureActive = true;
  walkingCapture.classList.add("hidden");
  ui.classList.remove("hidden");
  await celebrateAndAdvance();
}

function playBrowserVoice(text){
  return new Promise((resolve) => {
    if(!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance){
      resolve(false);
      return;
    }
    try{
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";
      utterance.rate = 0.88;
      utterance.pitch = 1.0;
      utterance.onend = () => resolve(true);
      utterance.onerror = () => resolve(false);
      window.speechSynthesis.speak(utterance);
      setTimeout(() => resolve(true), Math.min(14000, Math.max(3500, text.length * 70)));
    }catch(e){
      resolve(false);
    }
  });
}

function createSilentWavUrl(){
  const sampleRate = 8000;
  const sampleCount = 800;
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  const writeText = (offset, value) => {
    for(let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, sampleCount * 2, true);
  return URL.createObjectURL(new Blob([buffer], {type:"audio/wav"}));
}

function unlockAudioPlayback(){
  if(audioUnlockPromise) return audioUnlockPromise;
  const silentUrl = createSilentWavUrl();
  audioEl.preload = "auto";
  audioEl.setAttribute("playsinline", "true");
  audioEl.src = silentUrl;
  const playback = audioEl.play();
  audioUnlockPromise = Promise.resolve(playback)
    .then(() => {
      audioEl.pause();
      audioEl.currentTime = 0;
      URL.revokeObjectURL(silentUrl);
      return true;
    })
    .catch(error => {
      URL.revokeObjectURL(silentUrl);
      audioUnlockPromise = null;
      postRN({type:"voice_unlock_error", message:String(error)});
      return false;
    });
  return audioUnlockPromise;
}

function voiceCacheKey(text){
  return `${voiceId}::${text}`;
}

async function fetchVoiceAudio(text){
  const key = voiceCacheKey(text);
  if(voiceAudioCache.has(key)) return voiceAudioCache.get(key);
  if(voiceAudioInflight.has(key)) return voiceAudioInflight.get(key);
  const promise = fetch(`${API_BASE}/tts/generate`,{
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({text, voice_id: voiceId})
  })
    .then(async (res) => {
      if(!res.ok) throw new Error("tts failed");
      const data = await res.json();
      voiceAudioCache.set(key, data.audio_b64);
      return data.audio_b64;
    })
    .finally(() => voiceAudioInflight.delete(key));
  voiceAudioInflight.set(key, promise);
  return promise;
}

function prefetchVoice(text){
  if(!VOICE_GUIDANCE_ENABLED || !text) return;
  fetchVoiceAudio(text).catch(() => {});
}

function prefetchUpcomingVoice(){
  const task = tasks[currentTaskIdx];
  if(!task || !Array.isArray(task.steps)) return;
  const nextStep = task.steps[currentStepIdx + 1];
  if(nextStep && nextStep.voice){
    prefetchVoice(nextStep.voice);
  }
}

async function playVoice(text){
  if(!VOICE_GUIDANCE_ENABLED){
    voiceText.textContent = "Voice guidance off · follow on-screen text";
    return;
  }
  try{
    voiceText.textContent = "Playing instruction…";
    const audioB64 = await fetchVoiceAudio(text);
    audioEl.pause();
    audioEl.src = "data:audio/mpeg;base64," + audioB64;
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (callback) => {
        if(settled) return;
        settled = true;
        clearTimeout(timeout);
        audioEl.onended = null;
        audioEl.onerror = null;
        callback();
      };
      const timeout = setTimeout(() => finish(resolve), 45000);
      audioEl.onended = () => finish(resolve);
      audioEl.onerror = () => finish(() => reject(new Error("Audio element could not play the instruction")));
      const playback = audioEl.play();
      if(playback && typeof playback.catch === "function"){
        playback.catch(error => finish(() => reject(error)));
      }
    });
    voiceText.textContent = "Instruction ready · follow the target";
  }catch(e){
    voiceText.textContent = "Using device voice";
    const spoke = await playBrowserVoice(text);
    voiceText.textContent = spoke ? "Instruction ready · follow the target" : "Voice unavailable — follow on-screen text";
    postRN({type:"voice_error", message:String(e)});
  }
}

function isAdvancedMarkerTask(task){
  return !!(task && (task.advanced_marker_required || ADVANCED_MARKER_TASK_IDS.has(task.id)));
}

function isAdvancedObjectMode(){
  const task = tasks[currentTaskIdx];
  return !!(task && advancedObjectModeByTask[task.id]);
}

function resetAdvancedTracking(){
  frameStats = {totalFrames:0, handFrames:0, markerFrames:0};
  latestMarker = null;
  markerHistory = [];
  handObjectOverlapStartedAt = null;
  handObjectOverlapMs = 0;
  objectTransportSamples = [];
  lastMarkerScanTs = 0;
  lastHandScanTs = 0;
}

function showAdvancedMarkerGate(task){
  waitingForAdvancedGate = true;
  markerChoicePanel.classList.remove("hidden");
  markerMissingPanel.classList.add("hidden");
  advancedMarkerGate.classList.remove("hidden");
  captionEl.textContent = "Prepare a light object and AxonAI marker first";
  voiceText.textContent = "Confirm when you are ready for the advanced task";
  postRN({type:"advanced_marker_gate", task_id: task.id});
}

function continueAdvancedTask(hasMarker){
  const task = tasks[currentTaskIdx];
  if(!task) return;
  advancedGateSeen[task.id] = true;
  advancedObjectModeByTask[task.id] = !!hasMarker;
  waitingForAdvancedGate = false;
  advancedMarkerGate.classList.add("hidden");
  resetAdvancedTracking();
  startStep();
}

function getCurrentStep(){
  const task = tasks[currentTaskIdx];
  if(!task) return null;
  return task.steps[currentStepIdx];
}

async function startStep(){
  const step = getCurrentStep();
  const task = tasks[currentTaskIdx];
  if(!step) return;
  if(currentStepIdx === 0 && isWalkingTask(task) && !walkingCaptureActive){
    await showWalkingCapture(task);
    return;
  }
  if(currentStepIdx === 0 && isAdvancedMarkerTask(task) && !advancedGateSeen[task.id]){
    showAdvancedMarkerGate(task);
    return;
  }
  if(needsHandLandmarks() && !handLandmarker){
    voiceText.textContent = "Preparing hand tracking...";
    await setupHand();
  }
  if(currentStepIdx === 0) beginTaskRecording(task.id);
  stepStartTime = performance.now();
  stepStartedAt = stepStartTime;
  voiceFinishedAt = 0;
  arrivedAfterMovement = !movementGateRequired(step);
  stepStartWristXY = null;
  inTargetSince = null;
  lastInTargetTs = 0;
  stepCompleted = false;
  fistCloseReadyObserved = false;
  fistClosureMinScore = 1;
  fistClosingStarted = false;
  targetAttemptStartPoint = null;
  targetAttemptStartGesture = null;
  targetAttemptMaxDisplacement = 0;
  targetAttemptMaxGestureChange = 0;
  nearMissStartedAt = null;
  nearMissReason = "";
  lastNearMissCoachingAt = 0;
  nearMissCoachingCount = 0;
  nearMissEvents = [];
  correctionVoicePlaying = false;
  stepMetrics = {};
  trunkLeanMax = 0;
  shoulderFlexionMax = 0;
  shoulderHikeDetected = false;
  kneeExtensionMaxDeg = 0;
  ankleDorsiflexionMax = 0;
  affectedPelvisShiftMax = 0;
  lateralTrunkShiftMax = 0;
  shoulderElevationMaxDeg = 0;
  elbowFlexionMaxDeg = 0;
  hipFlexionMaxDeg = 0;
  kneeFlexionMaxDeg = 0;
  toeClearanceMaxRatio = 0;
  circumductionMaxRatio = 0;
  affectedStepLengthMaxRatio = 0;
  affectedWristMoveMaxRatio = 0;
  unaffectedWristMoveMaxRatio = 0;
  handToMouthMinRatio = Infinity;
  bodyMetricSamples = [];
  gaitPelvisTravelMaxRatio = 0;
  gaitAffectedAnkleTravelMaxRatio = 0;
  gaitUnaffectedAnkleTravelMaxRatio = 0;
  gaitAlternationCount = 0;
  lastGaitLead = 0;
  gaitObservedFrameCount = 0;
  gaitFullBodyVisibleFrameCount = 0;
  fingerTotalFlexionMaxDeg = 0;
  fingerAbductionMaxRatio = 0;
  thumbIndexMinDistanceRatio = Infinity;
  stepStartBodyState = null;
  dynamicTargetPos = null;
  if(currentStepIdx === 0) mouthTargetCalibration = newMouthTargetCalibration();
  if(currentStepIdx === 0){
    affectedHandTrackWrist = null;
    affectedHandTrackSeenAt = 0;
    if(assessmentLapTarget){
      lapTargetCalibration.target = {...assessmentLapTarget};
      lapTargetCalibration.ready = true;
      lapTargetCalibration.announced = true;
      dynamicTargetPos = {...assessmentLapTarget};
      preservePreAssessmentLapCalibration = false;
    }else if(preservePreAssessmentLapCalibration && currentTaskLapStep()){
      preservePreAssessmentLapCalibration = false;
    }else if(!preservePreAssessmentLapCalibration){
      lapTargetCalibration = newLapTargetCalibration();
    }
  }else if(lapTargetCalibration.ready){
    dynamicTargetPos = lapTargetCalibration.target;
  }
  if(currentStepIdx === 0) resetAdvancedTracking();
  stepTitle.textContent = `Task ${currentTaskIdx+1} of ${tasks.length} · ${task.title}`;
  captionEl.textContent = step.caption;
  renderDots();
  // Show step intro card (caption + voice waveform)
  document.body.classList.add("voice-playing");
  document.body.classList.remove("step-active");
  postRN({type:"step_start", task_id: task.id, step_id: step.id});
  await playVoice(step.voice);
  prefetchUpcomingVoice();
  // Voice finished → unlock the target and fade the bottom card
  voiceFinishedAt = performance.now();
  document.body.classList.remove("voice-playing");
  document.body.classList.add("step-active");
}

function distance(a,b){ return Math.hypot(a.x-b.x, a.y-b.y); }

function rad2deg(r){ return r*180/Math.PI; }

function midpoint(a,b){ return {x:(a.x+b.x)/2, y:(a.y+b.y)/2}; }

function jointAngleDeg(a,b,c){
  const ab = {x:a.x-b.x, y:a.y-b.y};
  const cb = {x:c.x-b.x, y:c.y-b.y};
  const denom = Math.max(1e-6, Math.hypot(ab.x,ab.y) * Math.hypot(cb.x,cb.y));
  const cosine = Math.max(-1, Math.min(1, (ab.x*cb.x + ab.y*cb.y) / denom));
  return rad2deg(Math.acos(cosine));
}

function sideLandmarks(lm, side=AFFECTED_SIDE){
  const left = side === "left";
  return {
    shoulder: lm[left ? 11 : 12],
    elbow: lm[left ? 13 : 14],
    wrist: lm[left ? 15 : 16],
    hip: lm[left ? 23 : 24],
    knee: lm[left ? 25 : 26],
    ankle: lm[left ? 27 : 28],
    heel: lm[left ? 29 : 30],
    toe: lm[left ? 31 : 32],
  };
}

function anatomicalHandedness(rawCategory){
  // MediaPipe handedness assumes mirrored selfie input. Inference receives the
  // unmirrored camera pixels, so swap its label back to the patient's anatomy.
  if(rawCategory === "Right") return "Left";
  if(rawCategory === "Left") return "Right";
  return "";
}

function selectAffectedHandDetection(result, now=performance.now()){
  const landmarksList = result && Array.isArray(result.landmarks) ? result.landmarks : [];
  if(!landmarksList.length) return null;
  const expectedSide = AFFECTED_SIDE === "left" ? "Left" : "Right";
  const poseWrist = latestPoseLandmarks && latestPoseLandmarks.length >= 33
    ? sideLandmarks(latestPoseLandmarks, AFFECTED_SIDE).wrist
    : null;
  const shoulders = latestPoseLandmarks && latestPoseLandmarks.length >= 33
    ? [latestPoseLandmarks[11], latestPoseLandmarks[12]]
    : null;
  const shoulderWidth = shoulders ? distance(shoulders[0], shoulders[1]) : 0.22;
  const associationRadius = Math.max(0.14, Math.min(0.32, shoulderWidth * 0.85));
  const trackIsFresh = affectedHandTrackWrist && now - affectedHandTrackSeenAt < 900;
  const candidates = landmarksList.map((landmarks, index) => {
    const category = result.handednesses && result.handednesses[index]
      && result.handednesses[index][0] ? result.handednesses[index][0] : null;
    const handedness = anatomicalHandedness(category && category.categoryName);
    const confidence = category && Number.isFinite(category.score) ? category.score : 0;
    const wrist = landmarks && landmarks[0];
    const poseDistance = poseWrist && wrist ? distance(wrist, poseWrist) : Infinity;
    const trackDistance = trackIsFresh && wrist ? distance(wrist, affectedHandTrackWrist) : Infinity;
    const sidePenalty = handedness && handedness !== expectedSide ? 0.18 : 0;
    const score = (Number.isFinite(poseDistance) ? poseDistance * 4 : 0)
      + (Number.isFinite(trackDistance) ? trackDistance * 0.7 : 0)
      + sidePenalty - confidence * 0.05;
    return {landmarks, index, handedness, confidence, wrist, poseDistance, trackDistance, score};
  }).filter(candidate => candidate.wrist);

  let eligible;
  if(poseWrist){
    eligible = candidates.filter(candidate => candidate.poseDistance <= associationRadius);
  }else{
    eligible = candidates.filter(candidate => candidate.handedness === expectedSide
      || (trackIsFresh && candidate.trackDistance <= 0.16));
  }
  if(!eligible.length) return null;
  eligible.sort((a,b) => a.score - b.score);
  const selected = eligible[0];
  affectedHandTrackWrist = {x:selected.wrist.x, y:selected.wrist.y, z:selected.wrist.z || 0};
  affectedHandTrackSeenAt = now;
  return {...selected, handedness:expectedSide};
}

function bodyState(lm){
  const affected = sideLandmarks(lm, AFFECTED_SIDE);
  const unaffected = sideLandmarks(lm, AFFECTED_SIDE === "left" ? "right" : "left");
  const midHip = midpoint(lm[23], lm[24]);
  const midShoulder = midpoint(lm[11], lm[12]);
  const shoulderWidthNow = Math.max(0.03, distance(lm[11], lm[12]));
  const legLength = Math.max(0.05, distance(affected.hip, affected.knee) + distance(affected.knee, affected.ankle));
  const leftX = Math.min(affected.ankle.x, unaffected.ankle.x);
  const rightX = Math.max(affected.ankle.x, unaffected.ankle.x);
  const baseWidth = Math.max(0.03, rightX - leftX);
  const rightShare = Math.max(0, Math.min(1, (midHip.x - leftX) / baseWidth));
  const affectedLoadShare = AFFECTED_SIDE === "right" ? rightShare : 1 - rightShare;
  const affectedKneeAngle = jointAngleDeg(affected.hip, affected.knee, affected.ankle);
  return {
    affected, unaffected, midHip, midShoulder,
    affectedKneeAngle,
    unaffectedKneeAngle: jointAngleDeg(unaffected.hip, unaffected.knee, unaffected.ankle),
    shoulderElevation: jointAngleDeg(affected.hip, affected.shoulder, affected.elbow),
    elbowFlexion: 180 - jointAngleDeg(affected.shoulder, affected.elbow, affected.wrist),
    hipFlexion: 180 - jointAngleDeg(affected.shoulder, affected.hip, affected.knee),
    kneeFlexion: 180 - affectedKneeAngle,
    trunkLean: Math.abs(rad2deg(Math.atan2(midShoulder.x-midHip.x, -(midShoulder.y-midHip.y)))),
    footSeparation: Math.hypot(affected.ankle.x-unaffected.ankle.x, affected.ankle.y-unaffected.ankle.y),
    shoulderWidth: shoulderWidthNow,
    legLength,
    affectedLoadShare,
  };
}

function fullBodyVisibleForWalking(lm){
  if(!lm || lm.length < 33) return false;
  const mostVisible = (indices) => indices
    .map(index => lm[index])
    .sort((a,b) => (b.visibility == null ? 1 : b.visibility) - (a.visibility == null ? 1 : a.visibility))[0];
  // In a side view, the far-side limb may be occluded even when the patient's
  // complete body is framed. Require each anatomical region, not both sides.
  const keypoints = [
    lm[0],
    mostVisible([11,12]),
    mostVisible([23,24]),
    mostVisible([25,26]),
    mostVisible([27,28]),
    mostVisible([31,32]),
  ];
  const allVisible = keypoints.every(point => landmarkIsUsable(point, 0.35));
  if(!allVisible) return false;
  const insideFrame = keypoints.every(point => point.x >= 0.025 && point.x <= 0.975 && point.y >= 0.015 && point.y <= 0.985);
  if(!insideFrame) return false;
  const headVisible = lm[0].y >= 0.015;
  const visibleFoot = mostVisible([31,32]);
  const feetVisible = visibleFoot.y <= 0.985;
  return headVisible && feetVisible;
}

function gaitFullBodyVisibilityRatio(){
  return gaitObservedFrameCount > 0 ? gaitFullBodyVisibleFrameCount / gaitObservedFrameCount : 0;
}

function landmarkIsUsable(point, minVisibility=0.45){
  return !!point
    && Number.isFinite(point.x)
    && Number.isFinite(point.y)
    && (point.visibility == null || point.visibility >= minVisibility);
}

function landmarkIsInFrame(point, minVisibility=0.45, margin=0.025){
  return landmarkIsUsable(point, minVisibility)
    && point.x >= margin && point.x <= 1 - margin
    && point.y >= margin && point.y <= 1 - margin;
}

function medianValue(values){
  if(!values.length) return null;
  const sorted = [...values].sort((a,b) => a-b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle-1] + sorted[middle]) / 2;
}

function isLapTarget(step){
  return !!step && step.target && step.target.landmark === "LAP_DYNAMIC";
}

function currentTaskLapStep(){
  const task = tasks[currentTaskIdx];
  if(!task || !Array.isArray(task.steps)) return null;
  return task.steps.find(isLapTarget) || null;
}

function upcomingLapStep(){
  for(let taskIndex=currentTaskIdx; taskIndex<tasks.length; taskIndex += 1){
    const task = tasks[taskIndex];
    if(!task || !Array.isArray(task.steps)) continue;
    const step = task.steps.find(isLapTarget);
    if(step) return step;
  }
  return null;
}

function shouldRunSeatedCalibration(){
  return !!upcomingLapStep();
}

function lapWristZoneReason(wrist, hip, midShoulder, torsoLength){
  const wristBelowHip = wrist.y - hip.y;
  const wristFromHipX = Math.abs(wrist.x - hip.x);
  const wristBelowShoulders = wrist.y - midShoulder.y;
  if(wristBelowShoulders < torsoLength * 0.55 || wristBelowHip < -torsoLength * 0.12) return "hand_too_high";
  if(wristBelowHip > torsoLength * 0.95) return "hand_too_low";
  if(wristFromHipX > torsoLength * 0.90) return "hand_too_far_side";
  return null;
}

function lapTargetCandidateStatus(lm){
  const sideLabel = AFFECTED_SIDE === "left" ? "left" : "right";
  if(!lm || lm.length < 33) return {
    candidate:null,
    reason:"pose_missing",
    guidance:"Sit facing the camera and keep your face, shoulders, affected arm, and upper thigh visible."
  };
  const affected = sideLandmarks(lm, AFFECTED_SIDE);
  const unaffected = sideLandmarks(lm, AFFECTED_SIDE === "left" ? "right" : "left");
  const leftShoulder = lm[11];
  const rightShoulder = lm[12];
  const lapVisibility = 0.35;
  if(!landmarkIsInFrame(leftShoulder, lapVisibility) || !landmarkIsInFrame(rightShoulder, lapVisibility)) return {
    candidate:null,
    reason:"shoulders_not_visible",
    guidance:"Move the camera until both shoulders are clearly visible."
  };
  if(!landmarkIsInFrame(affected.hip, lapVisibility) || !landmarkIsInFrame(affected.wrist, lapVisibility)) return {
    candidate:null,
    reason:"affected_lap_not_visible",
    guidance:`Tilt the camera down slightly so your ${sideLabel} hand and the top of your ${sideLabel} thigh are visible.`
  };

  const midShoulder = midpoint(leftShoulder, rightShoulder);
  const torsoLength = distance(midShoulder, affected.hip);
  if(torsoLength < 0.07) return {
    candidate:null,
    reason:"body_too_small",
    guidance:"Move slightly closer to the camera while keeping your face and upper thigh visible."
  };

  // The patient places the affected hand on the visible upper thigh. This is
  // enough to locate the lap without forcing the knee or full thigh into view.
  // Keep a broad torso-relative zone so different seated postures remain valid,
  // while rejecting a hand held at the face, chest, or far beside the body.
  const zoneReason = lapWristZoneReason(affected.wrist, affected.hip, midShoulder, torsoLength);
  if(zoneReason){
    const unaffectedVisible = landmarkIsInFrame(unaffected.hip, lapVisibility)
      && landmarkIsInFrame(unaffected.wrist, lapVisibility);
    const unaffectedTorsoLength = unaffectedVisible ? distance(midShoulder, unaffected.hip) : 0;
    const otherHandOnLap = unaffectedVisible && unaffectedTorsoLength >= 0.07
      && !lapWristZoneReason(unaffected.wrist, unaffected.hip, midShoulder, unaffectedTorsoLength);
    if(otherHandOnLap) return {
      candidate:null,
      reason:"wrong_hand_on_lap",
      guidance:`Your other hand is on your lap. Place your ${sideLabel} hand on the top of your ${sideLabel} thigh.`
    };
    const guidanceByReason = {
      hand_too_high:`Lower your ${sideLabel} hand from your chest or face and rest it on top of your ${sideLabel} thigh.`,
      hand_too_low:`Place your ${sideLabel} hand on top of your upper thigh rather than beside the chair.`,
      hand_too_far_side:`Move your ${sideLabel} hand inward so it rests on top of your ${sideLabel} thigh.`,
    };
    return {candidate:null, reason:zoneReason, guidance:guidanceByReason[zoneReason]};
  }

  const anatomical = {x:affected.wrist.x, y:affected.wrist.y};
  // The canvas itself is CSS-mirrored with the camera preview. Keep the target
  // in raw camera coordinates so it appears over the affected anatomical lap.
  const screenPoint = anatomical;
  return {
    candidate:{
      x: Math.max(0.10, Math.min(0.90, screenPoint.x)),
      y: Math.max(0.50, Math.min(0.90, screenPoint.y)),
      shoulderWidth: Math.max(0.03, distance(leftShoulder, rightShoulder)),
      bodyX:(midShoulder.x + affected.hip.x) / 2,
      bodyY:(midShoulder.y + affected.hip.y) / 2,
    },
    reason:"stabilizing",
    guidance:`Keep your ${sideLabel} hand relaxed and still on your upper thigh for one moment.`,
  };
}

function lapTargetCandidate(lm){
  const status = lapTargetCandidateStatus(lm);
  lapCalibrationDiagnostic = {reason:status.reason, guidance:status.guidance};
  return status.candidate;
}

function updateLapTargetCalibration(lm, now){
  const lapStep = calibratingAssessment ? upcomingLapStep() : currentTaskLapStep();
  if(!lapStep || lapTargetCalibration.ready) return;
  const candidate = lapTargetCandidate(lm);
  if(!candidate){
    if(lapTargetCalibration.lastCandidateAt && now - lapTargetCalibration.lastCandidateAt <= 900) return;
    lapTargetCalibration.samples = [];
    lapTargetCalibration.target = null;
    dynamicTargetPos = null;
    return;
  }
  lapTargetCalibration.lastCandidateAt = now;

  const samples = lapTargetCalibration.samples;
  samples.push({
    x:candidate.x,
    y:candidate.y,
    bodyX:candidate.bodyX,
    bodyY:candidate.bodyY,
    t:now,
    shoulderWidth:candidate.shoulderWidth,
  });
  while(samples.length > 24 || (samples.length && now - samples[0].t > 1200)) samples.shift();

  let center = {x:medianValue(samples.map(s => s.x)), y:medianValue(samples.map(s => s.y))};
  lapTargetCalibration.target = center;
  dynamicTargetPos = center;
  if(samples.length < LAP_CALIBRATION_MIN_SAMPLES) return;

  const width = medianValue(samples.map(s => s.shoulderWidth)) || 0.03;
  const maxJitter = Math.max(0.028, width * 0.18);
  const maxBodyJitter = Math.max(0.035, width * 0.22);
  const bodyCenter = {
    x:medianValue(samples.map(s => s.bodyX)),
    y:medianValue(samples.map(s => s.bodyY)),
  };
  const stableSamples = samples.filter(s =>
    Math.hypot(s.x-center.x, s.y-center.y) <= maxJitter
    && Math.hypot(s.bodyX-bodyCenter.x, s.bodyY-bodyCenter.y) <= maxBodyJitter
  );
  const requiredStableSamples = Math.max(LAP_CALIBRATION_MIN_SAMPLES, Math.ceil(samples.length * 0.70));
  if(stableSamples.length < requiredStableSamples) return;
  const stableDuration = stableSamples[stableSamples.length-1].t - stableSamples[0].t;
  if(stableDuration < LAP_CALIBRATION_MIN_MS) return;
  center = {
    x:medianValue(stableSamples.map(s => s.x)),
    y:medianValue(stableSamples.map(s => s.y)),
  };

  lapTargetCalibration.ready = true;
  lapTargetCalibration.target = center;
  dynamicTargetPos = center;
  if(!lapTargetCalibration.announced){
    lapTargetCalibration.announced = true;
    postRN({
      type:"lap_target_calibrated",
      task_id:tasks[currentTaskIdx].id,
      step_id:lapStep.id,
      x:+center.x.toFixed(4),
      y:+center.y.toFixed(4),
      sample_count:samples.length,
    });
  }
}

function calibrationLandmarkStatus(lm){
  const cameraReady = video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0;
  if(!lm || lm.length < 33){
    return {cameraReady, armVisible:false, seatedAnchorsVisible:false, lapReady:false, ready:false};
  }
  const affected = sideLandmarks(lm, AFFECTED_SIDE);
  const visibility = 0.35;
  const faceVisible = [lm[0], lm[9], lm[10]].some(point => landmarkIsInFrame(point, visibility));
  const armVisible = faceVisible && [lm[11], lm[12], affected.elbow, affected.wrist]
    .every(point => landmarkIsInFrame(point, visibility));
  const seatedAnchorsVisible = [affected.hip, affected.wrist]
    .every(point => landmarkIsInFrame(point, visibility));
  const lapReady = !!(lapTargetCalibration.ready && lapTargetCalibration.target);
  return {
    cameraReady,
    armVisible,
    seatedAnchorsVisible,
    lapReady,
    lapGuidance:lapCalibrationDiagnostic.guidance,
    ready:cameraReady && armVisible && seatedAnchorsVisible && lapReady,
  };
}

function setCalibrationCheck(element, complete){
  element.classList.toggle("done", !!complete);
  element.querySelector(".statusDot").textContent = complete ? "✓" : element === calibrationCamera ? "1" : element === calibrationArm ? "2" : element === calibrationSeat ? "3" : "4";
}

function updatePreAssessmentCalibrationUI(lm){
  if(!calibratingAssessment) return;
  const status = calibrationLandmarkStatus(lm);
  if(!calibrationAutoStartInProgress) preAssessmentCalibrationReady = status.ready;
  if(preAssessmentCalibrationReady){
    setCalibrationCheck(calibrationCamera, true);
    setCalibrationCheck(calibrationArm, true);
    setCalibrationCheck(calibrationSeat, true);
    setCalibrationCheck(calibrationLap, true);
    calibrationProgressFill.style.width = "100%";
    calibrationTitle.textContent = "Calibration complete";
    calibrationLead.textContent = "Your seated position and lap target are set. Stay seated and do not move the camera.";
    calibrationAutoStatus.classList.add("ready");
    calibrationAutoStatus.textContent = calibrationInstructionFinished
      ? "Calibration complete. Starting assessment..."
      : "Calibration complete. Please finish listening.";
    if(calibrationInstructionFinished) void completePreAssessmentCalibration();
  }else{
    setCalibrationCheck(calibrationCamera, status.cameraReady);
    setCalibrationCheck(calibrationArm, status.armVisible);
    setCalibrationCheck(calibrationSeat, status.seatedAnchorsVisible);
    setCalibrationCheck(calibrationLap, status.lapReady);
    const completed = [status.cameraReady, status.armVisible, status.seatedAnchorsVisible, status.lapReady].filter(Boolean).length;
    calibrationProgressFill.style.width = `${completed * 25}%`;
    calibrationTitle.textContent = "Let us find your seated position";
    calibrationLead.textContent = status.armVisible && !status.seatedAnchorsVisible
      ? "Tilt the camera down slightly until your affected hand and the top of your affected thigh are visible. You do not need to show your knees or full lap."
      : status.armVisible && status.seatedAnchorsVisible && !status.lapReady
        ? status.lapGuidance
      : "Sit still with your affected hand resting on the visible part of your lap. Keep your face, shoulders, affected arm, and the top of your affected thigh in view.";
    calibrationAutoStatus.classList.remove("ready");
    calibrationAutoStatus.textContent = status.armVisible && status.seatedAnchorsVisible && !status.lapReady
      ? status.lapGuidance
      : "Keep still. Assessment will start automatically.";
  }
}

async function completePreAssessmentCalibration(){
  if(!calibratingAssessment || !preAssessmentCalibrationReady || !calibrationInstructionFinished || calibrationAutoStartInProgress) return;
  calibrationAutoStartInProgress = true;
  calibrationAutoStatus.classList.add("ready");
  calibrationAutoStatus.textContent = "Calibration complete. Starting assessment...";
  calibrationLead.textContent = "Stay seated in this position and do not move the camera. The assessment will begin automatically.";
  await playVoice(CALIBRATION_COMPLETE_INSTRUCTION);
  if(!calibratingAssessment) return;
  finalizePatientFaceReference();
  assessmentLapTarget = lapTargetCalibration.target
    ? {...lapTargetCalibration.target}
    : null;
  preservePreAssessmentLapCalibration = true;
  calibratingAssessment = false;
  calibrationOverlay.classList.add("hidden");
  ui.classList.remove("hidden");
  postRN({
    type:"assessment_calibrated",
    affected_side:AFFECTED_SIDE,
    lap_target:lapTargetCalibration.target,
    sample_count:lapTargetCalibration.samples.length,
    automatic:true,
  });
  await startStep();
}

if(URL_PARAMS.get("test_mode") === "lap_calibration"){
  function withLapCalibrationTestContext(callback){
    const savedTasks = tasks;
    const savedCalibratingAssessment = calibratingAssessment;
    if(!upcomingLapStep()){
      tasks = [{id:"CALIBRATION_TEST", steps:[{id:"CALIBRATION_TEST_LAP", target:{landmark:"LAP_DYNAMIC"}}]}];
    }
    calibratingAssessment = true;
    try{
      return callback();
    }finally{
      tasks = savedTasks;
      calibratingAssessment = savedCalibratingAssessment;
    }
  }
  window.__rehynLapCalibrationTest = {
    candidate: (landmarks) => lapTargetCandidate(landmarks),
    diagnose: (landmarks) => lapTargetCandidateStatus(landmarks),
    runStableSequence: (landmarks, frameCount=12, frameMs=100) => {
      const savedCalibration = lapTargetCalibration;
      const savedDynamicTarget = dynamicTargetPos;
      lapTargetCalibration = newLapTargetCalibration();
      withLapCalibrationTestContext(() => {
        for(let frame=0; frame<frameCount; frame += 1){
          updateLapTargetCalibration(landmarks, frame * frameMs);
        }
      });
      const result = {
        ready:lapTargetCalibration.ready,
        target:lapTargetCalibration.target,
        sampleCount:lapTargetCalibration.samples.length,
      };
      lapTargetCalibration = savedCalibration;
      dynamicTargetPos = savedDynamicTarget;
      return result;
    },
    runSequence: (frames, frameMs=100) => {
      const savedCalibration = lapTargetCalibration;
      const savedDynamicTarget = dynamicTargetPos;
      lapTargetCalibration = newLapTargetCalibration();
      withLapCalibrationTestContext(() => {
        frames.forEach((landmarks, frame) => updateLapTargetCalibration(landmarks, frame * frameMs));
      });
      const result = {
        ready:lapTargetCalibration.ready,
        target:lapTargetCalibration.target,
        sampleCount:lapTargetCalibration.samples.length,
      };
      lapTargetCalibration = savedCalibration;
      dynamicTargetPos = savedDynamicTarget;
      return result;
    },
    applyCalibrationSequence: (landmarks, frameCount=12, frameMs=100) => {
      lapTargetCalibration = newLapTargetCalibration();
      calibratingAssessment = true;
      calibrationInstructionFinished = true;
      preAssessmentCalibrationReady = false;
      calibrationAutoStartInProgress = false;
      withLapCalibrationTestContext(() => {
        for(let frame=0; frame<frameCount; frame += 1){
          updateLapTargetCalibration(landmarks, frame * frameMs);
        }
      });
      updatePreAssessmentCalibrationUI(landmarks);
      return {
        ready:preAssessmentCalibrationReady,
        target:lapTargetCalibration.target,
        autoStarting:calibrationAutoStartInProgress,
        statusText:calibrationAutoStatus.textContent,
        title:calibrationTitle.textContent,
      };
    },
    lockAssessmentTarget:(target) => {
      assessmentLapTarget = {...target};
      lapTargetCalibration.target = {...target};
      lapTargetCalibration.ready = true;
      return getEffectiveTargetXY({target:{x:0.5, y:0.8, landmark:"LAP_DYNAMIC"}});
    },
    effectiveTarget:() => getEffectiveTargetXY({target:{x:0.5, y:0.8, landmark:"LAP_DYNAMIC"}}),
    affectedSide:AFFECTED_SIDE,
  };
}

if(URL_PARAMS.get("test_mode") === "mouth_target"){
  window.__rehynMouthTargetTest = {
    affectedSide:AFFECTED_SIDE,
    runTargetSequence:(frames) => {
      const savedCalibration = mouthTargetCalibration;
      mouthTargetCalibration = newMouthTargetCalibration();
      frames.forEach((landmarks, index) => updateMouthTargetCalibration(landmarks, index + 1));
      const result = {
        target:mouthTargetCalibration.target,
        locked:mouthTargetCalibration.locked,
        sampleCount:mouthTargetCalibration.samples.length,
      };
      mouthTargetCalibration = savedCalibration;
      return result;
    },
    evaluatePoseHit:(landmarks, target, radius=0.10) => {
      const savedHand = latestHandLandmarks;
      latestHandLandmarks = null;
      const point = closestAffectedHandPointToTarget(landmarks, target);
      const distance = mouthContactDistance(landmarks, target);
      const affectedWrist = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;
      latestHandLandmarks = savedHand;
      return {
        point,
        distance,
        wristDistance:distXY(affectedWrist, target),
        hit:distance < radius,
      };
    },
  };
}

if(URL_PARAMS.get("test_mode") === "upper_limb_endpoint"){
  window.__rehynUpperLimbEndpointTest = {
    affectedSide:AFFECTED_SIDE,
    gateRequiredById:(stepId) => !["T1-S1", "T1-S2", "T3-S1", "T3-S2"].includes(stepId),
    evaluateReachHit:(landmarks, target, radius=0.10) => {
      const point = closestAffectedReachPointToTarget(landmarks, target);
      return {point, distance:distXY(point, target), hit:distXY(point, target) < radius};
    },
  };
}

if(URL_PARAMS.get("test_mode") === "palm_projection"){
  window.__rehynPalmProjectionTest = {
    threshold:PALM_FACING_THRESHOLD,
    evaluate:(landmarks, frameCount=4) => {
      const evidence = palmProjectionEvidence(landmarks);
      let smoothed = 0;
      for(let frame=0; frame<frameCount; frame += 1){
        smoothed = smoothed * 0.55 + evidence.score * 0.45;
      }
      return {...evidence, smoothed, passes:smoothed > PALM_FACING_THRESHOLD};
    },
  };
}

if(URL_PARAMS.get("test_mode") === "hand_selection"){
  window.__rehynAffectedHandTest = {
    affectedSide:AFFECTED_SIDE,
    select:(result, poseLandmarks, now=1000) => {
      latestPoseLandmarks = poseLandmarks;
      affectedHandTrackWrist = null;
      affectedHandTrackSeenAt = 0;
      const selected = selectAffectedHandDetection(result, now);
      return selected ? {
        index:selected.index,
        handedness:selected.handedness,
        poseDistance:selected.poseDistance,
        wrist:{x:selected.wrist.x, y:selected.wrist.y},
      } : null;
    },
  };
}

function computeMetrics(landmarks){
  // landmarks are normalized 0..1
  if(!landmarks || landmarks.length<33) return;
  const L_SHOULDER = landmarks[11], R_SHOULDER = landmarks[12];
  const L_HIP = landmarks[23], R_HIP = landmarks[24];
  const L_ELBOW = landmarks[13], R_ELBOW = landmarks[14];
  const L_WRIST = landmarks[15], R_WRIST = landmarks[16];

  // trunk lean: angle of (mid-shoulder to mid-hip) vs vertical
  const midSh = {x:(L_SHOULDER.x+R_SHOULDER.x)/2, y:(L_SHOULDER.y+R_SHOULDER.y)/2};
  const midHip = {x:(L_HIP.x+R_HIP.x)/2, y:(L_HIP.y+R_HIP.y)/2};
  const dx = midSh.x - midHip.x;
  const dy = midSh.y - midHip.y;
  const trunkAngle = Math.abs(rad2deg(Math.atan2(dx, -dy)));
  trunkLeanMax = Math.max(trunkLeanMax, trunkAngle);

  // shoulder flexion (approx): wrist y above shoulder y means raised
  const wristY = Math.min(L_WRIST.y, R_WRIST.y);
  const shY = Math.min(L_SHOULDER.y, R_SHOULDER.y);
  const flexion = Math.max(0, (shY - wristY)); // larger = arm more raised
  shoulderFlexionMax = Math.max(shoulderFlexionMax, flexion);

  const state = bodyState(landmarks);
  if(!stepStartBodyState) stepStartBodyState = state;
  const affectedShoulder = state.affected.shoulder;
  const unaffectedShoulder = state.unaffected.shoulder;
  const shoulderElevationDelta = unaffectedShoulder.y - affectedShoulder.y;
  if(shoulderElevationDelta > Math.max(0.015, state.shoulderWidth * 0.10)) shoulderHikeDetected = true;
  kneeExtensionMaxDeg = Math.max(kneeExtensionMaxDeg, state.affectedKneeAngle);
  ankleDorsiflexionMax = Math.max(ankleDorsiflexionMax, state.affected.heel.y - state.affected.toe.y);
  shoulderElevationMaxDeg = Math.max(shoulderElevationMaxDeg, state.shoulderElevation);
  elbowFlexionMaxDeg = Math.max(elbowFlexionMaxDeg, state.elbowFlexion);
  hipFlexionMaxDeg = Math.max(hipFlexionMaxDeg, state.hipFlexion);
  kneeFlexionMaxDeg = Math.max(kneeFlexionMaxDeg, state.kneeFlexion);
  const affectedDirection = AFFECTED_SIDE === "left" ? -1 : 1;
  affectedPelvisShiftMax = Math.max(affectedPelvisShiftMax, affectedDirection * (state.midHip.x - stepStartBodyState.midHip.x));
  lateralTrunkShiftMax = Math.max(lateralTrunkShiftMax, Math.abs(state.midShoulder.x - stepStartBodyState.midShoulder.x));
  const toeLift = Math.max(0, stepStartBodyState.affected.toe.y - state.affected.toe.y) / state.legLength;
  const ankleMoveX = Math.abs(state.affected.ankle.x - stepStartBodyState.affected.ankle.x) / state.legLength;
  const ankleMove = distance(state.affected.ankle, stepStartBodyState.affected.ankle) / state.legLength;
  const unaffectedAnkleMove = distance(state.unaffected.ankle, stepStartBodyState.unaffected.ankle) / state.legLength;
  const pelvisTravel = Math.abs(state.midHip.x - stepStartBodyState.midHip.x) / state.legLength;
  const wristMove = distance(state.affected.wrist, stepStartBodyState.affected.wrist) / Math.max(0.05, state.shoulderWidth);
  const unaffectedWristMove = distance(state.unaffected.wrist, stepStartBodyState.unaffected.wrist) / Math.max(0.05, state.shoulderWidth);
  const mouthCenter = midpoint(landmarks[9], landmarks[10]);
  const handToMouth = distance(state.affected.wrist, mouthCenter) / Math.max(0.05, state.shoulderWidth);
  toeClearanceMaxRatio = Math.max(toeClearanceMaxRatio, toeLift);
  circumductionMaxRatio = Math.max(circumductionMaxRatio, ankleMoveX);
  affectedStepLengthMaxRatio = Math.max(affectedStepLengthMaxRatio, ankleMove);
  const leadDelta = state.affected.ankle.x - state.unaffected.ankle.x;
  const lead = Math.abs(leadDelta) > Math.max(0.025, state.legLength * 0.08) ? (leadDelta > 0 ? 1 : -1) : 0;
  const activeStep = getCurrentStep();
  const gaitCaptureActive = voiceFinishedAt > 0
    && activeStep
    && ["WALK_READY", "WALK_ACROSS", "WALK_STOPPED"].includes(activeStep.target.landmark);
  if(gaitCaptureActive){
    gaitPelvisTravelMaxRatio = Math.max(gaitPelvisTravelMaxRatio, pelvisTravel);
    gaitAffectedAnkleTravelMaxRatio = Math.max(gaitAffectedAnkleTravelMaxRatio, ankleMove);
    gaitUnaffectedAnkleTravelMaxRatio = Math.max(gaitUnaffectedAnkleTravelMaxRatio, unaffectedAnkleMove);
    if(lead && lastGaitLead && lead !== lastGaitLead) gaitAlternationCount += 1;
    if(lead) lastGaitLead = lead;
    gaitObservedFrameCount += 1;
    if(fullBodyVisibleForWalking(landmarks)) gaitFullBodyVisibleFrameCount += 1;
  }
  affectedWristMoveMaxRatio = Math.max(affectedWristMoveMaxRatio, wristMove);
  unaffectedWristMoveMaxRatio = Math.max(unaffectedWristMoveMaxRatio, unaffectedWristMove);
  handToMouthMinRatio = Math.min(handToMouthMinRatio, handToMouth);
  bodyMetricSamples.push({
    midHipX:state.midHip.x, midHipY:state.midHip.y,
    midShoulderX:state.midShoulder.x, midShoulderY:state.midShoulder.y,
    trunkLean:state.trunkLean, kneeAngle:state.affectedKneeAngle,
    affectedLoadShare:state.affectedLoadShare,
    affectedAnkleX:state.affected.ankle.x, affectedAnkleY:state.affected.ankle.y,
    shoulderWidth:state.shoulderWidth,
  });
  if(bodyMetricSamples.length > 360) bodyMetricSamples.shift();
}

// ---------- Dynamic target resolution ----------
// Returns the on-screen (mirrored, normalized) point at which to draw the target,
// and the candidate body point(s) to test against the target zone.
// Mirroring: user sees themselves mirrored — so on-screen X = (1 - landmark.x).
function mirrorX(p){ return {x: 1 - p.x, y: p.y}; }

function poseMouthTarget(lm){
  if(!lm || lm.length < 11) return null;
  const leftMouth = lm[9];
  const rightMouth = lm[10];
  if(!landmarkIsUsable(leftMouth, 0.25) || !landmarkIsUsable(rightMouth, 0.25)) return null;
  // Video and canvas are mirrored together in CSS. Keep the anatomical mouth
  // point in raw camera coordinates so the displayed ring lands on the mouth.
  return midpoint(leftMouth, rightMouth);
}

function updateMouthTargetCalibration(lm, sampleKey=(lastPoseScanTs || performance.now())){
  if(mouthTargetCalibration.locked && mouthTargetCalibration.target) return mouthTargetCalibration.target;
  const point = poseMouthTarget(lm);
  if(!point) return mouthTargetCalibration.target;
  if(mouthTargetCalibration.lastSampleKey === sampleKey) return mouthTargetCalibration.target;
  mouthTargetCalibration.lastSampleKey = sampleKey;
  const samples = mouthTargetCalibration.samples;
  samples.push(point);
  while(samples.length > 10) samples.shift();
  let center = {
    x:medianValue(samples.map(sample => sample.x)),
    y:medianValue(samples.map(sample => sample.y)),
  };
  mouthTargetCalibration.target = center;
  if(samples.length < 5) return center;
  const maxJitter = Math.max(0.012, shoulderWidth(lm) * 0.08);
  const stableSamples = samples.filter(sample => distXY(sample, center) <= maxJitter);
  if(stableSamples.length < Math.ceil(samples.length * 0.8)) return center;
  center = {
    x:medianValue(stableSamples.map(sample => sample.x)),
    y:medianValue(stableSamples.map(sample => sample.y)),
  };
  mouthTargetCalibration.target = center;
  mouthTargetCalibration.locked = true;
  return center;
}

function affectedPoseHandPoints(lm){
  if(!lm || lm.length < 23) return [];
  const left = AFFECTED_SIDE === "left";
  const indices = left ? [15, 17, 19, 21] : [16, 18, 20, 22];
  return indices
    .map(index => lm[index])
    .filter(point => landmarkIsUsable(point, 0.20));
}

function affectedReachContactPoints(lm){
  return affectedPoseHandPoints(lm).map(point => mirrorX(point));
}

function closestAffectedReachPointToTarget(lm, target){
  const points = affectedReachContactPoints(lm);
  if(!points.length || !target) return null;
  return points.reduce((closest, point) => distXY(point, target) < distXY(closest, target) ? point : closest);
}

function affectedMouthContactPoints(lm){
  const points = affectedPoseHandPoints(lm);
  if(latestHandLandmarks && latestHandLandmarks.length >= 21
    && performance.now() - latestHandSeenAt <= handLandmarkFreshMs()){
    const fingertips = [4, 8, 12, 16, 20]
      .map(index => latestHandLandmarks[index])
      .filter(point => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    points.push(...fingertips);
    const palm = rawHandPalmCenter();
    if(palm) points.push(palm);
  }
  return points;
}

function closestAffectedHandPointToTarget(lm, target){
  const points = affectedMouthContactPoints(lm);
  if(!points.length || !target) return null;
  return points.reduce((closest, point) => distXY(point, target) < distXY(closest, target) ? point : closest);
}

function mouthContactDistance(lm, target){
  return distXY(closestAffectedHandPointToTarget(lm, target), target);
}

function handPalmCenter(){
  const raw = rawHandPalmCenter();
  return raw ? mirrorX(raw) : null;
}

function rawHandPalmCenter(){
  if(!latestHandLandmarks || latestHandLandmarks.length < 21) return null;
  const h = latestHandLandmarks;
  return {x:(h[0].x + h[5].x + h[17].x)/3, y:(h[0].y + h[5].y + h[17].y)/3};
}

function handWristPoint(){
  if(!latestHandLandmarks || latestHandLandmarks.length < 21) return null;
  return mirrorX(latestHandLandmarks[0]);
}

function activeHandPoint(){
  return handPalmCenter() || handWristPoint();
}

function resolveLandmarkPoint(which){
  if(isHandTask()){
    if(which === "WRIST" || which === "HAND_OPEN" || which === "PINCH" || which === "CHEST"){
      return activeHandPoint();
    }
  }
  const lm = latestPoseLandmarks;
  if(!lm) return null;
  if(which === "WRIST" || which === "WRIST_DYNAMIC" || which === "LAP_DYNAMIC"){
    // pick the wrist that is lower (relaxed) as the "affected" reference,
    // or the higher one if user is actively reaching.
    return mirrorX(lm[15].y > lm[16].y ? lm[15] : lm[16]);
  }
  if(which === "WRISTS"){
    return mirrorX({x:(lm[15].x+lm[16].x)/2, y:(lm[15].y+lm[16].y)/2});
  }
  if(which === "MOUTH"){
    return poseMouthTarget(lm);
  }
  if(which === "CHEST"){
    // mid-shoulder, drop slightly below for chest center
    const ls = lm[11], rs = lm[12];
    const mid = {x:(ls.x+rs.x)/2, y:(ls.y+rs.y)/2 + 0.06};
    return mirrorX(mid);
  }
  if(which === "HAND_OPEN" || which === "PINCH" || which === "PINCH_RELEASED"){
    // Anchor on whichever wrist is most raised (active hand)
    const active = lm[15].y < lm[16].y ? lm[15] : lm[16];
    return mirrorX(active);
  }
  return null;
}

function getEffectiveTargetXY(step){
  if(isLapTarget(step)){
    return assessmentLapTarget || lapTargetCalibration.target || {x: step.target.x, y: step.target.y};
  }
  if(isHandTask()){
    return {x: step.target.x, y: step.target.y};
  }
  // Dynamic body targets use the same calibrated coordinates for drawing and hit testing.
  // Otherwise use the static configured x/y.
  const which = step.target.landmark;
  if(which === "WRIST_DYNAMIC"){
    // Capture the wrist position once at the start of the step and lock there.
    if(!dynamicTargetPos){
      const p = resolveLandmarkPoint("WRIST");
      if(p) dynamicTargetPos = {x: p.x, y: p.y};
    }
    return dynamicTargetPos || {x: step.target.x, y: step.target.y};
  }
  if(which === "MOUTH"){
    const p = updateMouthTargetCalibration(latestPoseLandmarks);
    return p ? {x:p.x, y:p.y} : {x:step.target.x, y:step.target.y};
  }
  if(which === "CHEST"){
    const p = resolveLandmarkPoint(which);
    return p ? {x: p.x, y: p.y} : {x: step.target.x, y: step.target.y};
  }
  if(which === "HAND_OPEN" || which === "PINCH" || which === "PINCH_RELEASED"){
    // Anchor on the raised hand so user can see the prompt next to their hand
    const p = resolveLandmarkPoint(which);
    return p ? {x: p.x, y: p.y} : {x: step.target.x, y: step.target.y};
  }
  return {x: step.target.x, y: step.target.y};
}

// ---------- Hand metrics (from HandLandmarker) ----------
function palmProjectionEvidence(h){
  if(!h || h.length < 21) return {
    score:0, planeFacing:0, projectedArea:0, palmSpread:0, depthFlatness:0,
  };
  const clamp01 = (value) => Math.max(0, Math.min(1, value));
  const dist = (a,b) => Math.hypot(a.x-b.x, a.y-b.y);
  const palmWidth = Math.max(0.01, dist(h[5], h[17]));
  const palmHeight = Math.max(0.01, dist(h[0], h[9]));
  const vIndex = {x:h[5].x-h[0].x, y:h[5].y-h[0].y, z:(h[5].z||0)-(h[0].z||0)};
  const vPinky = {x:h[17].x-h[0].x, y:h[17].y-h[0].y, z:(h[17].z||0)-(h[0].z||0)};
  const normal = {
    x:vIndex.y*vPinky.z - vIndex.z*vPinky.y,
    y:vIndex.z*vPinky.x - vIndex.x*vPinky.z,
    z:vIndex.x*vPinky.y - vIndex.y*vPinky.x,
  };
  const normalMag = Math.max(0.0001, Math.hypot(normal.x, normal.y, normal.z));
  const signedPlaneFacing = normal.z / normalMag;
  // The sign flips with handedness and mirroring; its magnitude is the stable
  // evidence that the palm plane is broadside rather than edge-on.
  const planeFacing = clamp01((Math.abs(signedPlaneFacing) - 0.08) / 0.52);
  const projectedAreaRatio = Math.abs(vIndex.x*vPinky.y - vIndex.y*vPinky.x)
    / Math.max(0.0001, palmHeight * palmHeight);
  const projectedArea = clamp01((projectedAreaRatio - 0.06) / 0.34);
  const palmSpread = clamp01((palmWidth / palmHeight - 0.28) / 0.42);
  const palmDepthTilt = Math.abs((h[5].z||0) - (h[17].z||0)) / palmWidth;
  const depthFlatness = clamp01(1 - palmDepthTilt / 0.55);
  return {
    score:clamp01(planeFacing * 0.35 + projectedArea * 0.30 + palmSpread * 0.25 + depthFlatness * 0.10),
    planeFacing,
    projectedArea,
    palmSpread,
    depthFlatness,
    signedPlaneFacing,
  };
}

function computeHandMetrics(){
  // Hand landmarks indices (MediaPipe Hands): 0=wrist, 4=thumb_tip, 5=index_mcp,
  // 8=index_tip, 12=middle_tip, 16=ring_tip, 20=pinky_tip.
  // Open hand: average fingertip distance from wrist is large relative to palm width.
  // Pinch: thumb_tip <-> index_tip distance is small relative to palm width.
  if(!latestHandLandmarks || latestHandLandmarks.length < 21){
    // decay scores so old detections don't linger
    handOpenScore = Math.max(0, handOpenScore - 0.15);
    fistClosureScore = Math.max(0, fistClosureScore - 0.15);
    pinchScore = Math.max(0, pinchScore - 0.15);
    palmFacingScore = Math.max(0, palmFacingScore - 0.15);
    return;
  }
  const h = latestHandLandmarks;
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const dist = (a,b) => Math.hypot(a.x-b.x, a.y-b.y);
  const angleDeg = (a,b,c) => {
    const ab = {x:a.x-b.x, y:a.y-b.y, z:(a.z||0)-(b.z||0)};
    const cb = {x:c.x-b.x, y:c.y-b.y, z:(c.z||0)-(b.z||0)};
    const abLen = Math.max(0.0001, Math.hypot(ab.x, ab.y, ab.z));
    const cbLen = Math.max(0.0001, Math.hypot(cb.x, cb.y, cb.z));
    const cos = Math.max(-1, Math.min(1, (ab.x*cb.x + ab.y*cb.y + ab.z*cb.z) / (abLen * cbLen)));
    return Math.acos(cos) * 180 / Math.PI;
  };
  const palmWidth = Math.max(0.01, dist(h[5], h[17])); // index_mcp <-> pinky_mcp
  const palmHeight = Math.max(0.01, dist(h[0], h[9])); // wrist <-> middle_mcp
  const handScale = Math.max(0.01, palmWidth, palmHeight * 0.9);
  const palmEvidence = palmProjectionEvidence(h);
  palmFacingScore = palmFacingScore * 0.55 + palmEvidence.score * 0.45;
  const fingerSpread = (
    dist(h[0], h[8])  +  // wrist to index_tip
    dist(h[0], h[12]) +  // wrist to middle_tip
    dist(h[0], h[16]) +  // wrist to ring_tip
    dist(h[0], h[20])    // wrist to pinky_tip
  ) / 4;
  const fingerDefs = [
    [5, 6, 7, 8],
    [9, 10, 11, 12],
    [13, 14, 15, 16],
    [17, 18, 19, 20],
  ];
  const fingerStraightnessScore = fingerDefs.reduce((sum, [mcp, pip, dip, tip]) => {
    const pipStraight = clamp01((angleDeg(h[mcp], h[pip], h[dip]) - 110) / 60);
    const dipStraight = clamp01((angleDeg(h[pip], h[dip], h[tip]) - 120) / 55);
    const reach = clamp01((dist(h[mcp], h[tip]) / handScale - 0.55) / 0.65);
    return sum + (pipStraight * 0.45 + dipStraight * 0.35 + reach * 0.20);
  }, 0) / fingerDefs.length;
  const fingertipDistanceScore = clamp01((fingerSpread / handScale - 1.15) / 1.15);
  const thumbIndexSpreadScore = clamp01((dist(h[4], h[8]) / handScale - 0.35) / 0.95);
  const open = clamp01(fingerStraightnessScore * 0.62 + fingertipDistanceScore * 0.28 + thumbIndexSpreadScore * 0.10);
  handOpenScore = handOpenScore * 0.6 + open * 0.4;
  const totalFlexion = fingerDefs.reduce((sum, [mcp, pip, dip, tip]) => {
    const pipFlexion = Math.max(0, 180 - angleDeg(h[mcp], h[pip], h[dip]));
    const dipFlexion = Math.max(0, 180 - angleDeg(h[pip], h[dip], h[tip]));
    return sum + pipFlexion + dipFlexion;
  }, 0) / fingerDefs.length;
  fingerTotalFlexionMaxDeg = Math.max(fingerTotalFlexionMaxDeg, totalFlexion);
  fingerAbductionMaxRatio = Math.max(fingerAbductionMaxRatio, dist(h[8], h[20]) / palmWidth);
  thumbIndexMinDistanceRatio = Math.min(thumbIndexMinDistanceRatio, dist(h[4], h[8]) / palmWidth);

  const palmCenter = {x:(h[0].x + h[5].x + h[9].x + h[13].x + h[17].x)/5, y:(h[0].y + h[5].y + h[9].y + h[13].y + h[17].y)/5};
  const tipPalmDist = (dist(h[8], palmCenter) + dist(h[12], palmCenter) + dist(h[16], palmCenter) + dist(h[20], palmCenter)) / 4;
  const closureRatio = tipPalmDist / palmWidth;
  const closure = clamp01((2.15 - closureRatio) / 0.85);
  fistClosureScore = fistClosureScore * 0.6 + closure * 0.4;

  const pinchDist = dist(h[4], h[8]) / palmWidth;
  // pinchDist < 0.5 means tips are touching; > 1.2 means apart
  const pinch = clamp01((1.2 - pinchDist) / 0.7);
  pinchScore = pinchScore * 0.6 + pinch * 0.4;
}

function needsHandLandmarks(){
  if(isHandTask()) return true;
  const task = tasks[currentTaskIdx];
  const step = getCurrentStep();
  const landmark = step && step.target ? step.target.landmark : "";
  const measures = step && Array.isArray(step.measure) ? step.measure : [];
  return landmark === "HAND_OPEN"
    || landmark === "HAND_CLOSED"
    || landmark === "PINCH"
    || landmark === "PINCH_RELEASED"
    || landmark === "OBJECT_COUPLED"
    || landmark === "OBJECT_AT_TARGET"
    || landmark === "OBJECT_RELEASED"
    || landmark === "MOUTH"
    || isAdvancedObjectMode()
    || measures.some((name) => HAND_METRIC_NAMES.has(name));
}

function isHandPerformanceBackoff(){
  return isHandTask() && currentFps > 0 && currentFps < MIN_RUNTIME_FPS;
}

function handLandmarkFreshMs(){
  return isHandPerformanceBackoff() ? HAND_BACKOFF_LANDMARK_FRESH_MS : HAND_LANDMARK_FRESH_MS;
}

function getHandCenter(){
  const palm = handPalmCenter();
  if(palm) return palm;
  const w = activeWrist(latestPoseLandmarks);
  return w ? {x:w.x, y:w.y} : null;
}

function detectAxonAIMarker(now){
  if(!isAdvancedObjectMode() || !markerCtx || video.readyState < 2) return null;
  if(now - lastMarkerScanTs < MARKER_SCAN_INTERVAL_MS) return latestMarker;
  lastMarkerScanTs = now;
  try{
    markerCtx.drawImage(video, 0, 0, markerCanvas.width, markerCanvas.height);
    const img = markerCtx.getImageData(0, 0, markerCanvas.width, markerCanvas.height).data;
    let sx = 0, sy = 0, count = 0;
    for(let y = 0; y < markerCanvas.height; y += 2){
      for(let x = 0; x < markerCanvas.width; x += 2){
        const i = (y * markerCanvas.width + x) * 4;
        const r = img[i], g = img[i+1], b = img[i+2];
        const max = Math.max(r,g,b), min = Math.min(r,g,b);
        const saturation = max - min;
        const orangeMarker = r > 150 && g > 70 && g < 185 && b < 120 && saturation > 60;
        const greenMarker = g > 135 && r < 135 && b < 150 && saturation > 55;
        const blueMarker = b > 145 && r < 140 && g > 70 && saturation > 55;
        if(orangeMarker || greenMarker || blueMarker){
          sx += x;
          sy += y;
          count++;
        }
      }
    }
    if(count < 12){
      latestMarker = null;
      return null;
    }
    const centerRaw = {x:sx/count/markerCanvas.width, y:sy/count/markerCanvas.height};
    const object_center = {x:1 - centerRaw.x, y:centerRaw.y};
    const object_visibility = Math.min(1, count / 160);
    markerHistory.push({x:object_center.x, y:object_center.y, t:now});
    markerHistory = markerHistory.filter(p => now - p.t < 1200).slice(-14);
    let jitter = 0;
    for(let i=1; i<markerHistory.length; i++){
      jitter += Math.hypot(markerHistory[i].x-markerHistory[i-1].x, markerHistory[i].y-markerHistory[i-1].y);
    }
    const markerCenterJitter = markerHistory.length > 1 ? jitter / (markerHistory.length - 1) : 0;
    const object_stability = Math.max(0, Math.min(1, 1 - markerCenterJitter / MARKER_JITTER_LIMIT));
    latestMarker = {object_center, object_visibility, object_stability, markerCenterJitter};
    return latestMarker;
  }catch(e){
    latestMarker = null;
    return null;
  }
}

function updateRuntimeDiagnostics(now){
  frameStats.totalFrames += 1;
  if(latestHandLandmarks && (now - latestHandSeenAt) < handLandmarkFreshMs()) frameStats.handFrames += 1;
  if(latestMarker) frameStats.markerFrames += 1;
  if(lastFrameTs){
    const fpsNow = 1000 / Math.max(1, now - lastFrameTs);
    currentFps = currentFps ? currentFps * 0.85 + fpsNow * 0.15 : fpsNow;
  }
  lastFrameTs = now;

  const handCenter = getHandCenter();
  if(isAdvancedObjectMode() && latestMarker && handCenter){
    const d = Math.hypot(handCenter.x - latestMarker.object_center.x, handCenter.y - latestMarker.object_center.y);
    if(d < 0.22){
      if(handObjectOverlapStartedAt == null) handObjectOverlapStartedAt = now;
      handObjectOverlapMs = Math.max(handObjectOverlapMs, now - handObjectOverlapStartedAt);
    }else{
      handObjectOverlapStartedAt = null;
    }
    objectTransportSamples.push({t:now, hand:handCenter, object:latestMarker.object_center, open:handOpenScore});
    objectTransportSamples = objectTransportSamples.filter(s => now - s.t < 5000).slice(-80);
  }

  const handDetectionRate = frameStats.totalFrames ? frameStats.handFrames / frameStats.totalFrames : 0;
  const markerDetectionRate = frameStats.totalFrames ? frameStats.markerFrames / frameStats.totalFrames : 0;
  if(isAdvancedObjectMode()){
    diagnosticsBadge.classList.remove("hidden");
    const smoothOk = currentFps >= MIN_RUNTIME_FPS;
    const handOk = handDetectionRate >= 0.8;
    const markerOk = markerDetectionRate >= 0.8 && latestMarker && latestMarker.object_stability > 0.45;
    diagnosticsBadge.classList.toggle("good", !!(smoothOk && handOk && markerOk));
    diagnosticsBadge.classList.toggle("warn", !(smoothOk && handOk && markerOk));
    diagnosticsText.textContent = markerOk
      ? `Hand clear · marker clear · ${Math.round(currentFps)} FPS`
      : "I cannot see the marker clearly yet. Turn the marker toward the camera.";
  }else{
    diagnosticsBadge.classList.add("hidden");
  }
}

function getAdvancedQuality(){
  const handDetectionRate = frameStats.totalFrames ? frameStats.handFrames / frameStats.totalFrames : 0;
  const markerDetectionRate = frameStats.totalFrames ? frameStats.markerFrames / frameStats.totalFrames : 0;
  const markerCenterJitter = latestMarker ? latestMarker.markerCenterJitter : 1;
  const qualityOk = isAdvancedObjectMode()
    && handDetectionRate >= 0.8
    && markerDetectionRate >= 0.8
    && handObjectOverlapMs >= 1000
    && markerCenterJitter <= MARKER_JITTER_LIMIT
    && currentFps >= MIN_RUNTIME_FPS;
  return {
    qualityOk,
    currentFps:+currentFps.toFixed(1),
    handDetectionRate:+handDetectionRate.toFixed(2),
    markerDetectionRate:+markerDetectionRate.toFixed(2),
    markerCenterJitter:+markerCenterJitter.toFixed(3),
    handObjectOverlapMs:Math.round(handObjectOverlapMs),
    object_center:latestMarker ? latestMarker.object_center : null,
    object_visibility:latestMarker ? +latestMarker.object_visibility.toFixed(2) : 0,
    object_stability:latestMarker ? +latestMarker.object_stability.toFixed(2) : 0,
  };
}

function computeAdvancedObjectMetrics(){
  const q = getAdvancedQuality();
  if(!isAdvancedObjectMode()){
    return {advanced_object_mode:false};
  }
  if(!q.qualityOk){
    return {
      advanced_object_mode:true,
      object_metric_status:"insufficient_marker_data",
      patient_message:"Not enough data. Please adjust the marker and lighting, then try again.",
      ...q,
    };
  }
  let coupledFrames = 0, releaseFrames = 0, endpointError = null;
  for(const s of objectTransportSamples){
    const d = Math.hypot(s.hand.x - s.object.x, s.hand.y - s.object.y);
    if(d < 0.22) coupledFrames += 1;
    if(d > 0.24 && s.open > 0.5) releaseFrames += 1;
    endpointError = Math.hypot(s.object.x - 0.70, s.object.y - 0.65);
  }
  const objectHandCoupling = objectTransportSamples.length ? coupledFrames / objectTransportSamples.length : 0;
  const objectHandSeparation = objectTransportSamples.length ? releaseFrames / objectTransportSamples.length : 0;
  const releaseDelayMs = objectHandSeparation > 0 ? Math.max(0, Math.round(1200 * (1 - objectHandSeparation))) : null;
  return {
    advanced_object_mode:true,
    object_metric_status:"quality_passed",
    objectHandCoupling:+objectHandCoupling.toFixed(2),
    objectHandSeparation:+objectHandSeparation.toFixed(2),
    releaseDelayMs,
    placementEndpointError:endpointError == null ? null : +endpointError.toFixed(3),
    ...q,
  };
}

// Returns the user's shoulder-width in normalized coords (a robust "size unit")
function shoulderWidth(lm){
  if(!lm) return 0.18;
  const ls = lm[11], rs = lm[12];
  if(!ls || !rs) return 0.18;
  return Math.max(0.08, Math.min(0.40, Math.hypot(ls.x - rs.x, ls.y - rs.y)));
}

// Effective hit radius for a step — scales with the user's body so it's stable
// regardless of how close they are to the camera. Tightened (Phase B+) so a
// resting wrist doesn't accidentally trigger the next target.
function effectiveRadius(step, lm){
  const baseR = step.target.r || 0.10;
  if(isHandTask()){
    return Math.min(Math.max(baseR, 0.12), 0.28);
  }
  const sw = shoulderWidth(lm);
  // Tighter radius — about 0.55 × shoulder-width for most targets.
  // Mouth uses fingertip/palm contact, so its visible circle can stay centered
  // and compact instead of expanding enough to admit the lower wrist.
  const which = step.target.landmark;
  let r = Math.max(baseR, sw * 0.55);
  if(which === "MOUTH"){
    r = Math.max(baseR, sw * 0.48);
    return Math.min(r, 0.14);
  }
  if(which === "CHEST"){
    r = Math.max(r, sw * 0.70);
  }
  return Math.min(r, 0.18);
}

// State for "must actually move" rule and voice-gate. Reset on every step.
let stepStartedAt = 0;
let voiceFinishedAt = 0;        // 0 until voice intro for current step finishes
let arrivedAfterMovement = false; // becomes true once wrist has moved >= 0.18 from step-start
let stepStartWristXY = null;    // wrist position captured at step start
let fistCloseReadyObserved = false;
let fistClosureMinScore = 1;
let fistClosingStarted = false;
let targetAttemptStartPoint = null;
let targetAttemptStartGesture = null;
let targetAttemptMaxDisplacement = 0;
let targetAttemptMaxGestureChange = 0;
let nearMissStartedAt = null;
let nearMissReason = "";
let lastNearMissCoachingAt = 0;
let nearMissCoachingCount = 0;
let nearMissEvents = [];
let correctionVoicePlaying = false;
const NEAR_MISS_DWELL_MS = 900;
const NEAR_MISS_COOLDOWN_MS = 7000;
const NEAR_MISS_MAX_COACHING_PER_STEP = 2;

function distXY(a,b){ if(!a||!b) return Infinity; return Math.hypot(a.x-b.x, a.y-b.y); }

function activeWrist(lm){
  const step = getCurrentStep();
  if(isLapTarget(step) && lm) return sideLandmarks(lm, AFFECTED_SIDE).wrist;
  if(isHandTask()){
    return activeHandPoint();
  }
  if(!lm) return null;
  const affectedWrist = sideLandmarks(lm, AFFECTED_SIDE).wrist;
  if(step && step.target && step.target.landmark === "MOUTH"){
    return affectedWrist;
  }
  // Upper-limb collection must stay on the survey-selected affected side.
  // Switching to whichever wrist happens to be nearer can reset the movement
  // gate midway through a correct first approach.
  return affectedWrist ? mirrorX(affectedWrist) : null;
}

function activeControlPoint(lm){
  if(!lm) return null;
  if(isLowerTask()){
    const step = getCurrentStep();
    const state = bodyState(lm);
    if(step && ["HIP_RISEN", "STAND_UPRIGHT", "HIP_SEATED"].includes(step.target.landmark)) return mirrorX(state.midHip);
    if(step && ["AFFECTED_KNEE_LIFTED", "UNAFFECTED_KNEE_LIFTED"].includes(step.target.landmark)){
      const side = step.target.landmark === "AFFECTED_KNEE_LIFTED" ? state.affected : state.unaffected;
      return mirrorX(side.knee);
    }
    return mirrorX(state.affected.ankle);
  }
  if(isBalanceTask()){
    return mirrorX(bodyState(lm).midHip);
  }
  return activeWrist(lm);
}

function updateMovementGate(lm){
  if(!stepStartWristXY){
    const w = activeControlPoint(lm);
    if(w) stepStartWristXY = {x: w.x, y: w.y};
    return;
  }
  if(arrivedAfterMovement) return;
  const w = activeControlPoint(lm);
  if(!w) return;
  // Required movement scales with shoulder-width to be size-invariant
  const requiredMove = (isLowerTask() || isBalanceTask())
    ? Math.max(0.035, shoulderWidth(lm) * 0.22)
    : Math.max(0.035, shoulderWidth(lm) * 0.30);
  if(distXY(w, stepStartWristXY) >= requiredMove) arrivedAfterMovement = true;
}

function movementGateRequired(step){
  if(!step || step.movement_required === false || isHandTask()) return false;
  // These endpoints cannot be occupied by the affected hand in the preceding
  // position. Contact after the voice gate is therefore sufficient proof of a
  // deliberate first approach, even if the movement began during instruction.
  return !["T1-S1", "T1-S2", "T3-S1", "T3-S2"].includes(step.id);
}

function targetAttemptGestureSnapshot(){
  return {
    open:handOpenScore,
    closed:fistClosureScore,
    pinch:pinchScore,
    palm:palmFacingScore,
  };
}

function targetAttemptPoint(lm, step){
  if(isHandTask()) return activeHandPoint();
  if(!lm || !step) return null;
  const which = step.target.landmark;
  if(which === "MOUTH"){
    return closestAffectedHandPointToTarget(lm, getEffectiveTargetXY(step));
  }
  if(isAdvancedObjectMode() && latestMarker && ["OBJECT_AT_TARGET", "OBJECT_RELEASED"].includes(which)){
    return latestMarker.object_center;
  }
  if(which === "WRISTS"){
    const target = getEffectiveTargetXY(step);
    const left = mirrorX(lm[15]);
    const right = mirrorX(lm[16]);
    return distXY(left, target) <= distXY(right, target) ? left : right;
  }
  return activeControlPoint(lm);
}

function updateTargetAttemptTracking(lm){
  const step = getCurrentStep();
  if(!step) return;
  const point = targetAttemptPoint(lm, step);
  const gesture = targetAttemptGestureSnapshot();
  if(!targetAttemptStartGesture) targetAttemptStartGesture = gesture;
  if(point && !targetAttemptStartPoint) targetAttemptStartPoint = {x:point.x, y:point.y};
  if(point && targetAttemptStartPoint){
    targetAttemptMaxDisplacement = Math.max(
      targetAttemptMaxDisplacement,
      distXY(point, targetAttemptStartPoint),
    );
  }
  if(targetAttemptStartGesture){
    targetAttemptMaxGestureChange = Math.max(
      targetAttemptMaxGestureChange,
      Math.abs(gesture.open - targetAttemptStartGesture.open),
      Math.abs(gesture.closed - targetAttemptStartGesture.closed),
      Math.abs(gesture.pinch - targetAttemptStartGesture.pinch),
      Math.abs(gesture.palm - targetAttemptStartGesture.palm),
    );
  }
}

function hasIntentionalTargetAttempt(lm, step, radius){
  const movementThreshold = isHandTask()
    ? Math.max(0.035, radius * 0.28)
    : Math.max(0.05, shoulderWidth(lm) * 0.30);
  const gestureAttempt = isHandTask() && targetAttemptMaxGestureChange >= 0.12;
  const movementGateAttempt = !isHandTask() && arrivedAfterMovement;
  return movementGateAttempt || targetAttemptMaxDisplacement >= movementThreshold || gestureAttempt;
}

function nearMissCorrection(step, distance, radius, lm){
  const which = step.target.landmark;
  if(distance > radius){
    const movingObject = ["OBJECT_COUPLED", "OBJECT_AT_TARGET", "OBJECT_RELEASED"].includes(which);
    return {
      reason:"just_outside_circle",
      guidance:movingObject
        ? "Move the cup slightly farther toward the center of the circle, then keep it steady there."
        : "Move your hand slightly farther toward the center of the circle, then keep it still there.",
    };
  }
  if(movementGateRequired(step) && !arrivedAfterMovement){
    return {
      reason:"movement_gate_not_met",
      guidance:"Move your hand slightly away, then deliberately reach back into the center of the circle and hold it there.",
    };
  }
  const needsVisibleHand = ["HAND_OPEN", "HAND_CLOSED", "PINCH", "PINCH_RELEASED", "OBJECT_COUPLED", "OBJECT_RELEASED"].includes(which)
    || step.id === "H1-S1"
    || step.id === "H2-S2"
    || (Array.isArray(step.measure) && step.measure.includes("closure_completeness"));
  if(needsVisibleHand && handLandmarker && !latestHandLandmarks){
    return {
      reason:"hand_landmarks_not_visible",
      guidance:"Keep your hand inside the circle with your palm and fingers clearly facing the camera, without the cup covering your whole hand.",
    };
  }
  if(step.id === "H1-S1" && palmFacingScore <= PALM_FACING_THRESHOLD){
    return {reason:"palm_not_facing", guidance:"Keep your hand in the circle and turn your palm toward the camera."};
  }
  if(step.id === "H2-S2" || (Array.isArray(step.measure) && step.measure.includes("closure_completeness")) || which === "HAND_CLOSED"){
    return {reason:"hand_not_closed", guidance:"Keep your hand in the center of the circle and gently close your fingers around the imaginary object."};
  }
  if(which === "HAND_OPEN"){
    if(step.id === "H1-S2" && palmFacingScore <= PALM_FACING_THRESHOLD){
      return {reason:"palm_not_facing", guidance:"Keep your hand in the circle, turn your palm toward the camera, and spread your fingers."};
    }
    return {reason:"hand_not_open", guidance:"Keep your hand in the center of the circle and spread your fingers as comfortably as you can."};
  }
  if(which === "PINCH"){
    return {reason:"pinch_not_detected", guidance:"Keep your hand in the circle and bring the tip of your thumb to the tip of your index finger."};
  }
  if(which === "PINCH_RELEASED"){
    return {reason:"pinch_not_released", guidance:"Keep your hand in the circle and gently separate your thumb and index finger."};
  }
  if(which === "WRISTS"){
    const target = getEffectiveTargetXY(step);
    const radiusNow = effectiveRadius(step, lm);
    const leftInside = lm && distXY(mirrorX(lm[15]), target) < radiusNow;
    const rightInside = lm && distXY(mirrorX(lm[16]), target) < radiusNow;
    if(!leftInside || !rightInside){
      return {reason:"both_wrists_required", guidance:"Bring both hands into the circle together and hold them there."};
    }
  }
  if(which === "WRISTS_APART"){
    return {reason:"hands_not_apart", guidance:"Keep both hands at the target height and move them a little farther apart."};
  }
  if(which === "WRISTS_LOW"){
    return {reason:"hands_not_lowered", guidance:"Lower both hands fully toward the ending area and keep them there."};
  }
  if(which === "OBJECT_COUPLED"){
    return {reason:"cup_grasp_not_detected", guidance:"Keep your hand and cup together in the center of the circle, with your fingers wrapped securely around the cup."};
  }
  if(which === "OBJECT_AT_TARGET"){
    return {reason:"cup_not_centered", guidance:"Move the cup itself, not only your wrist, into the center of the target circle and hold it steady."};
  }
  if(which === "OBJECT_RELEASED"){
    return {reason:"cup_release_not_detected", guidance:"Keep the cup at the target, open your fingers, and move your hand slightly away from the cup."};
  }
  return {
    reason:"activation_condition_not_met",
    guidance:"Keep the instructed body part in the center of the circle and hold it still until the ring completes.",
  };
}

function qualifiesAsNearTargetAttempt(distance, radius, intentional){
  const nearLimit = Math.max(radius * 1.45, radius + 0.035);
  return !!intentional && Number.isFinite(distance) && distance <= nearLimit;
}

function getTargetNearMiss(lm){
  const step = getCurrentStep();
  if(!step || isLowerTask() || isBalanceTask()) return null;
  if(isLapTarget(step) && !lapTargetCalibration.ready) return null;
  if(voiceFinishedAt === 0 || performance.now() - voiceFinishedAt < 350) return null;
  const point = targetAttemptPoint(lm, step);
  if(!point) return null;
  const target = getEffectiveTargetXY(step);
  const radius = effectiveRadius(step, isHandTask() ? null : lm);
  const distance = distXY(point, target);
  const intentional = hasIntentionalTargetAttempt(lm, step, radius);
  if(!qualifiesAsNearTargetAttempt(distance, radius, intentional)) return null;
  return {
    ...nearMissCorrection(step, distance, radius, lm),
    task_id:tasks[currentTaskIdx].id,
    step_id:step.id,
    distance:+distance.toFixed(4),
    radius:+radius.toFixed(4),
    distance_ratio:+(distance / Math.max(radius, 0.001)).toFixed(2),
  };
}

async function speakTargetNearMiss(diagnostic){
  const step = getCurrentStep();
  if(!step || correctionVoicePlaying) return;
  const expectedStepId = step.id;
  correctionVoicePlaying = true;
  const correction = `You're close. ${diagnostic.guidance}`;
  captionEl.textContent = correction;
  postRN({type:"target_near_miss", ...diagnostic});
  try{
    await playVoice(correction);
  }finally{
    const current = getCurrentStep();
    if(current && current.id === expectedStepId){
      captionEl.textContent = current.caption;
      voiceFinishedAt = performance.now();
    }
    correctionVoicePlaying = false;
  }
}

function handleTargetNearMiss(lm, now){
  if(correctionVoicePlaying || nearMissCoachingCount >= NEAR_MISS_MAX_COACHING_PER_STEP) return;
  const diagnostic = getTargetNearMiss(lm);
  if(!diagnostic){
    nearMissStartedAt = null;
    nearMissReason = "";
    return;
  }
  if(nearMissStartedAt == null || nearMissReason !== diagnostic.reason){
    nearMissStartedAt = now;
    nearMissReason = diagnostic.reason;
    return;
  }
  if(now - nearMissStartedAt < NEAR_MISS_DWELL_MS) return;
  if(lastNearMissCoachingAt && now - lastNearMissCoachingAt < NEAR_MISS_COOLDOWN_MS) return;
  nearMissCoachingCount += 1;
  lastNearMissCoachingAt = now;
  nearMissStartedAt = null;
  nearMissEvents.push({
    reason:diagnostic.reason,
    distance_ratio:diagnostic.distance_ratio,
    timestamp_ms:Math.round(now - stepStartedAt),
  });
  speakTargetNearMiss(diagnostic);
}

function rangeOf(values){
  if(!values || values.length === 0) return 0;
  return Math.max(...values) - Math.min(...values);
}

function meanOf(values){
  if(!values || values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function lowerBalanceMetricSnapshot(lm, step=null, durationMs=0, skipped=false){
  if(!lm || lm.length < 33) return {};
  const state = bodyState(lm);
  const leftX = Math.min(state.affected.ankle.x, state.unaffected.ankle.x);
  const rightX = Math.max(state.affected.ankle.x, state.unaffected.ankle.x);
  const baseWidth = Math.max(0.03, rightX - leftX);
  const rightShare = Math.max(0, Math.min(1, (state.midHip.x - leftX) / baseWidth));
  const affectedShare = AFFECTED_SIDE === "right" ? rightShare : 1 - rightShare;
  const scale = Math.max(0.03, meanOf(bodyMetricSamples.map(sample => sample.shoulderWidth)) || state.shoulderWidth);
  const trunkSway = Math.hypot(
    rangeOf(bodyMetricSamples.map(sample => sample.midShoulderX)),
    rangeOf(bodyMetricSamples.map(sample => sample.midShoulderY)),
  ) / scale;
  const pelvisSway = Math.hypot(
    rangeOf(bodyMetricSamples.map(sample => sample.midHipX)),
    rangeOf(bodyMetricSamples.map(sample => sample.midHipY)),
  ) / scale;
  const kneeStability = rangeOf(bodyMetricSamples.map(sample => sample.kneeAngle));
  const averageAffectedLoad = bodyMetricSamples.length
    ? meanOf(bodyMetricSamples.map(sample => sample.affectedLoadShare))
    : affectedShare;
  const weightSymmetry = Math.max(0, 1 - 2 * Math.abs(averageAffectedLoad - 0.5));
  const measures = step && Array.isArray(step.measure) ? step.measure : [];
  const bilateralMoveMax = Math.max(affectedWristMoveMaxRatio, unaffectedWristMoveMaxRatio);
  const bilateralSymmetry = bilateralMoveMax >= 0.10
    ? Math.min(affectedWristMoveMaxRatio, unaffectedWristMoveMaxRatio) / bilateralMoveMax
    : null;
  return {
    knee_extension_deg: +kneeExtensionMaxDeg.toFixed(1),
    ankle_dorsiflexion_proxy: +ankleDorsiflexionMax.toFixed(3),
    shoulder_elevation_deg: +shoulderElevationMaxDeg.toFixed(1),
    elbow_flexion_deg: +elbowFlexionMaxDeg.toFixed(1),
    hip_flexion_deg: +hipFlexionMaxDeg.toFixed(1),
    knee_flexion_deg: +kneeFlexionMaxDeg.toFixed(1),
    toe_clearance_leg_ratio: +toeClearanceMaxRatio.toFixed(3),
    circumduction_leg_ratio: +circumductionMaxRatio.toFixed(3),
    affected_step_length_leg_ratio: +affectedStepLengthMaxRatio.toFixed(3),
    affected_wrist_displacement_body_ratio: +affectedWristMoveMaxRatio.toFixed(3),
    unaffected_wrist_displacement_body_ratio: +unaffectedWristMoveMaxRatio.toFixed(3),
    hand_to_mouth_distance_ratio: Number.isFinite(handToMouthMinRatio) ? +handToMouthMinRatio.toFixed(3) : null,
    bilateral_wrist_displacement_symmetry: bilateralSymmetry == null ? null : +bilateralSymmetry.toFixed(3),
    affected_load_proxy: +averageAffectedLoad.toFixed(3),
    weight_shift_symmetry: +weightSymmetry.toFixed(3),
    pelvis_shift_affected: +affectedPelvisShiftMax.toFixed(3),
    lateral_trunk_shift: +lateralTrunkShiftMax.toFixed(3),
    trunk_sway_ratio: +trunkSway.toFixed(3),
    pelvis_sway_ratio: +pelvisSway.toFixed(3),
    midline_alignment_deg: +meanOf(bodyMetricSamples.map(sample => sample.trunkLean)).toFixed(1),
    knee_stability_deg: +kneeStability.toFixed(1),
    hold_duration_ms: skipped ? 0 : (step && step.movement_required === false ? step.hold_ms : 0),
    sit_to_stand_time_ms: step && measures.includes("sit_to_stand_time") && !skipped ? Math.round(durationMs) : null,
    gait_pelvis_travel_leg_ratio: +gaitPelvisTravelMaxRatio.toFixed(3),
    gait_affected_ankle_travel_leg_ratio: +gaitAffectedAnkleTravelMaxRatio.toFixed(3),
    gait_unaffected_ankle_travel_leg_ratio: +gaitUnaffectedAnkleTravelMaxRatio.toFixed(3),
    gait_step_alternation_count: gaitAlternationCount,
    gait_full_body_visibility_ratio: +gaitFullBodyVisibilityRatio().toFixed(3),
  };
}

function handMetricSnapshot(){
  return {
    finger_total_flexion_deg: +fingerTotalFlexionMaxDeg.toFixed(1),
    finger_abduction_ratio: +fingerAbductionMaxRatio.toFixed(3),
    thumb_index_distance_ratio: Number.isFinite(thumbIndexMinDistanceRatio)
      ? +thumbIndexMinDistanceRatio.toFixed(3)
      : null,
  };
}

function checkLowerBalanceTarget(landmarks, step){
  if(!landmarks || landmarks.length < 33) return false;
  if(!arrivedAfterMovement && step.movement_required !== false) return false;
  const state = bodyState(landmarks);
  const start = stepStartBodyState || state;
  const which = step.target.landmark;
  const affectedFootMove = Math.hypot(state.affected.ankle.x-start.affected.ankle.x, state.affected.ankle.y-start.affected.ankle.y);
  const unaffectedFootMove = Math.hypot(state.unaffected.ankle.x-start.unaffected.ankle.x, state.unaffected.ankle.y-start.unaffected.ankle.y);
  const affectedDirection = AFFECTED_SIDE === "left" ? -1 : 1;
  const pelvisTowardAffected = affectedDirection * (state.midHip.x - start.midHip.x);
  const trunkTowardAffected = affectedDirection * (state.midShoulder.x - start.midShoulder.x);
  const standing = state.affectedKneeAngle > 145 && state.unaffectedKneeAngle > 145 && state.trunkLean < 20;

  if(which === "SEATED_READY") return state.trunkLean < 20 && state.midHip.y < Math.max(state.affected.knee.y, state.unaffected.knee.y);
  if(which === "KNEE_EXTENDED" || which === "KNEE_EXTENDED_STABLE") return state.affectedKneeAngle > 145;
  if(which === "FOOT_RETURNED") return Math.abs(state.affected.ankle.y - state.affected.toe.y) < 0.10 && state.affectedKneeAngle < 145;
  if(which === "TOES_LIFTED") return (state.affected.heel.y - state.affected.toe.y) > 0.012;
  if(which === "SIT_TO_STAND_READY") return state.trunkLean < 35 && state.affectedKneeAngle < 145;
  if(which === "HIP_RISEN") return (start.midHip.y - state.midHip.y) > 0.07 && state.affectedKneeAngle > 110;
  if(which === "STAND_UPRIGHT") return standing;
  if(which === "HIP_SEATED") return (state.midHip.y - start.midHip.y) > 0.07 && state.affectedKneeAngle < 145;
  if(which === "SUPPORTED_STAND_STABLE") return standing && lateralTrunkShiftMax < 0.06;
  if(which === "AFFECTED_FOOT_FORWARD") return standing && affectedFootMove > 0.05;
  if(which === "AFFECTED_FOOT_RETURNED") return affectedFootMove > 0.045 && state.footSeparation < 0.16;
  if(which === "AFFECTED_KNEE_LIFTED") return (start.affected.knee.y - state.affected.knee.y) > 0.04;
  if(which === "UNAFFECTED_KNEE_LIFTED") return (start.unaffected.knee.y - state.unaffected.knee.y) > 0.04;
  if(which === "SEATED_STABLE") return state.trunkLean < 14 && lateralTrunkShiftMax < 0.05;
  if(which === "TRUNK_SHIFT_AFFECTED") return trunkTowardAffected > 0.025 && affectedFootMove < 0.04 && unaffectedFootMove < 0.04;
  if(which === "WEIGHT_SHIFT_AFFECTED") return pelvisTowardAffected > 0.02 && affectedFootMove < 0.04 && unaffectedFootMove < 0.04;
  if(which === "STEP_STANCE_STABLE") return standing && state.footSeparation > 0.06 && lateralTrunkShiftMax < 0.06;
  if(which === "WALK_READY") return standing && fullBodyVisibleForWalking(landmarks);
  if(which === "WALK_ACROSS"){
    const bilateralLegMotion = gaitAffectedAnkleTravelMaxRatio > 0.16
      && gaitUnaffectedAnkleTravelMaxRatio > 0.16
      && gaitAlternationCount >= 2;
    const fixedCameraProgress = gaitPelvisTravelMaxRatio > 0.35;
    const caregiverTrackedProgress = gaitAlternationCount >= 3;
    return gaitFullBodyVisibilityRatio() >= 0.75
      && bilateralLegMotion
      && (fixedCameraProgress || caregiverTrackedProgress);
  }
  if(which === "WALK_STOPPED") return standing && fullBodyVisibleForWalking(landmarks) && pelvisSwayForStop() < 0.08;
  return false;
}

function pelvisSwayForStop(){
  const values = bodyMetricSamples.slice(-20).map(sample => sample.midHipX);
  return rangeOf(values);
}

function checkTarget(landmarks){
  const step = getCurrentStep();
  if(!step) return false;
  const measures = Array.isArray(step.measure) ? step.measure : [];
  // VOICE GATE — target is NOT detectable until the voice intro has finished
  // playing AND a short settle window (350ms) has elapsed. Prevents the patient
  // accidentally triggering the step while Aria is still explaining it.
  if(voiceFinishedAt === 0) return false;
  if(performance.now() - voiceFinishedAt < 350) return false;
  if(isLapTarget(step)){
    if(!lapTargetCalibration.ready || !landmarks || !arrivedAfterMovement) return false;
    const affectedWristRaw = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;
    if(!landmarkIsUsable(affectedWristRaw)) return false;
    const targetXY = getEffectiveTargetXY(step);
    return distXY(affectedWristRaw, targetXY) < effectiveRadius(step, landmarks);
  }
  if(isHandTask()){
    const target = step.target;
    const which = target.landmark;
    const point = activeHandPoint();
    if(!point) return false;
    const R = effectiveRadius(step, null);
    const near = Math.hypot(point.x - target.x, point.y - target.y) < R;
    if(step.id === "H1-S1"){
      return near && palmFacingScore > PALM_FACING_THRESHOLD && handOpenScore < 0.72;
    }
    if(step.id === "H2-S2"){
      if(!near) return false;
      fistClosureMinScore = Math.min(fistClosureMinScore, fistClosureScore);
      if(!fistCloseReadyObserved){
        if(fistClosureScore < 0.86 || handOpenScore > 0.20){
          fistCloseReadyObserved = true;
          fistClosureMinScore = Math.min(fistClosureMinScore, fistClosureScore);
        }
        return false;
      }
      const closureDelta = fistClosureScore - fistClosureMinScore;
      if(!fistClosingStarted && (closureDelta > 0.035 || (handOpenScore < 0.58 && fistClosureScore > fistClosureMinScore + 0.02))){
        fistClosingStarted = true;
      }
      return fistClosingStarted && (closureDelta > 0.02 || fistClosureScore > 0.30 || handOpenScore < 0.62);
    }
    if(measures.includes("closure_completeness")){
      return near && fistClosureScore > 0.45;
    }
    if(which === "HAND_OPEN"){
      const palmOk = step.id !== "H1-S2" || palmFacingScore > PALM_FACING_THRESHOLD;
      const openThreshold = 0.45;
      return near && palmOk && handOpenScore > openThreshold;
    }
    if(which === "PINCH"){
      return near && pinchScore > 0.45;
    }
    return near;
  }
  if(isLowerTask() || isBalanceTask()){
    return checkLowerBalanceTarget(landmarks, step);
  }
  if(!landmarks) return false;
  // MOVEMENT GATE — wrist must have moved meaningfully from its position at
  // step-start before the target can fire. Stops "I didn't move and the next
  // circle counted because I was already inside it" bug.
  if(movementGateRequired(step) && !arrivedAfterMovement) return false;

  const target = step.target;
  const which = target.landmark;
  const targetXY = getEffectiveTargetXY(step);
  const R = effectiveRadius(step, landmarks);

  const wristDist = () => {
    const task = tasks[currentTaskIdx];
    if(task && task.id === "T1"){
      return distXY(closestAffectedReachPointToTarget(landmarks, targetXY), targetXY);
    }
    const affectedWrist = sideLandmarks(landmarks, AFFECTED_SIDE).wrist;
    return distXY(affectedWrist ? mirrorX(affectedWrist) : null, targetXY);
  };

  if(which === "HAND_OPEN"){
    const near = wristDist() < R;
    const gestureOk = handLandmarker ? handOpenScore > 0.45 : true;
    return near && gestureOk;
  }
  if(which === "HAND_CLOSED"){
    const near = wristDist() < R;
    const gestureOk = handLandmarker ? (fistClosureScore > 0.30 && handOpenScore < 0.62) : true;
    return near && gestureOk;
  }
  if(which === "PINCH"){
    const near = wristDist() < R;
    const gestureOk = handLandmarker ? pinchScore > 0.45 : true;
    return near && gestureOk;
  }
  if(which === "PINCH_RELEASED"){
    const near = wristDist() < R;
    const gestureOk = handLandmarker ? pinchScore < 0.35 : true;
    return near && gestureOk;
  }
  if(which === "MOUTH"){
    return mouthContactDistance(landmarks, targetXY) < R;
  }
  if(which === "CHEST"){
    return wristDist() < R;
  }
  if(which === "WRIST_DYNAMIC"){
    return wristDist() < R;
  }
  if(which === "WRISTS"){
    const lW = mirrorX(landmarks[15]);
    const rW = mirrorX(landmarks[16]);
    const okL = lW && Math.hypot(lW.x - targetXY.x, lW.y - targetXY.y) < R;
    const okR = rW && Math.hypot(rW.x - targetXY.x, rW.y - targetXY.y) < R;
    return okL && okR;
  }
  if(which === "WRISTS_APART"){
    const lW = mirrorX(landmarks[15]);
    const rW = mirrorX(landmarks[16]);
    const sameHeight = Math.abs(lW.y - rW.y) < 0.14;
    const workingHeight = Math.abs(((lW.y + rW.y) / 2) - targetXY.y) < Math.max(R, 0.14);
    return sameHeight && workingHeight && Math.abs(lW.x - rW.x) > 0.28;
  }
  if(which === "WRISTS_LOW"){
    const lW = mirrorX(landmarks[15]);
    const rW = mirrorX(landmarks[16]);
    return lW.y > 0.68 && rW.y > 0.68;
  }
  if(which === "OBJECT_COUPLED"){
    const near = wristDist() < R;
    if(!isAdvancedObjectMode()){
      return near && (!handLandmarker || (fistClosureScore > 0.25 && handOpenScore < 0.70));
    }
    const handCenter = getHandCenter();
    const coupled = latestMarker && handCenter
      && Math.hypot(handCenter.x - latestMarker.object_center.x, handCenter.y - latestMarker.object_center.y) < 0.22;
    return near && !!coupled && fistClosureScore > 0.20;
  }
  if(which === "OBJECT_AT_TARGET"){
    if(!isAdvancedObjectMode()) return wristDist() < R;
    return !!latestMarker
      && Math.hypot(latestMarker.object_center.x - targetXY.x, latestMarker.object_center.y - targetXY.y) < R;
  }
  if(which === "OBJECT_RELEASED"){
    if(!isAdvancedObjectMode()) return wristDist() < R && (!handLandmarker || handOpenScore > 0.45);
    const handCenter = getHandCenter();
    const objectAtTarget = latestMarker
      && Math.hypot(latestMarker.object_center.x - targetXY.x, latestMarker.object_center.y - targetXY.y) < R;
    const separated = latestMarker && handCenter
      && Math.hypot(handCenter.x - latestMarker.object_center.x, handCenter.y - latestMarker.object_center.y) > 0.24;
    return !!objectAtTarget && !!separated && handOpenScore > 0.45;
  }
  return wristDist() < R;
}

// ---------- Drawing ----------
const ICON_EMOJI = { cup: "☕", table: "🪵", towel: "🧺", ball: "🏐", coin: "🪙" };

function drawOverlay(landmarks){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  // draw skeleton
  if(landmarks){
    drawingUtils.drawLandmarks(landmarks, {color:"#D9E5DC", radius:3});
    drawingUtils.drawConnectors(landmarks, PoseLandmarker.POSE_CONNECTIONS, {color:"#4A7856", lineWidth:4});
  }
  if(latestHandLandmarks && latestHandLandmarks.length >= 21){
    drawingUtils.drawConnectors(latestHandLandmarks, HAND_CONNECTIONS, {color:"rgba(127,229,163,0.88)", lineWidth:2});
    drawingUtils.drawLandmarks(latestHandLandmarks, {color:"rgba(217,229,220,0.72)", radius:1.4});
  }
  if(calibratingAssessment){
    lapStatus.classList.add("hidden");
    if(lapTargetCalibration.ready && lapTargetCalibration.target){
      const tx = lapTargetCalibration.target.x * canvas.width;
      const ty = lapTargetCalibration.target.y * canvas.height;
      const tr = 0.075 * Math.min(canvas.width, canvas.height);
      ctx.save();
      ctx.beginPath();
      ctx.arc(tx, ty, tr, 0, Math.PI*2);
      ctx.fillStyle = "rgba(74,120,86,.28)";
      ctx.fill();
      ctx.lineWidth = 6;
      ctx.strokeStyle = "#7FE5A3";
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(tx, ty, Math.max(5, tr*.16), 0, Math.PI*2);
      ctx.fillStyle = "#FDFDFD";
      ctx.fill();
      ctx.restore();
    }
    return;
  }
  const step = getCurrentStep();
  if(!step){
    lapStatus.classList.add("hidden");
    return;
  }
  if(isWalkingTask()){
    lapStatus.classList.add("hidden");
    return;
  }
  if(isLapTarget(step) && !lapTargetCalibration.ready){
    lapStatus.classList.remove("hidden");
    return;
  }
  lapStatus.classList.add("hidden");
  const targetXY = getEffectiveTargetXY(step);
  const tx = targetXY.x * canvas.width;
  const ty = targetXY.y * canvas.height;
  // Visual radius MATCHES the actual hit radius — so what the user sees == what triggers.
  const effR = effectiveRadius(step, landmarks);
  const tr = effR * Math.min(canvas.width, canvas.height);
  const armed = (voiceFinishedAt > 0)
    && (performance.now() - voiceFinishedAt >= 350)
    && (!movementGateRequired(step) || arrivedAfterMovement);
  const pulse = 1 + 0.08*Math.sin(performance.now()/250);
  // outer pulsing ring — dashed/dim when not yet armed (voice still playing or movement gate not met)
  ctx.save();
  ctx.beginPath();
  ctx.arc(tx, ty, tr*pulse, 0, Math.PI*2);
  ctx.lineWidth = 6;
  if(armed){
    ctx.strokeStyle = "#E18E6D";
    ctx.setLineDash([]);
  } else {
    ctx.strokeStyle = "rgba(225,142,109,0.45)";
    ctx.setLineDash([10, 8]);
  }
  ctx.stroke();
  ctx.restore();
  // inner glow only when armed
  if(armed){
    ctx.beginPath();
    ctx.arc(tx, ty, tr*0.55, 0, Math.PI*2);
    ctx.fillStyle = "rgba(225,142,109,0.4)";
    ctx.fill();
  }

  // icon emoji (cup / table / towel ...) — drawn unmirrored using counter-flip
  const icon = step.target.icon;
  if(icon && ICON_EMOJI[icon]){
    ctx.save();
    // canvas is CSS-mirrored via scaleX(-1); flip back so emoji reads correctly
    ctx.translate(tx, ty);
    ctx.scale(-1, 1);
    ctx.font = `${Math.round(tr*1.1)}px serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#fff";
    ctx.fillText(ICON_EMOJI[icon], 0, 0);
    ctx.restore();
  }

  // hold progress ring
  if(inTargetSince){
    const elapsed = performance.now() - inTargetSince;
    const progress = Math.min(1, elapsed / step.hold_ms);
    ctx.beginPath();
    ctx.arc(tx, ty, tr*1.25, -Math.PI/2, -Math.PI/2 + progress*Math.PI*2);
    ctx.strokeStyle = "#3C8255";
    ctx.lineWidth = 8;
    ctx.stroke();
  }

  if(isAdvancedObjectMode() && latestMarker){
    const mx = latestMarker.object_center.x * canvas.width;
    const my = latestMarker.object_center.y * canvas.height;
    ctx.save();
    ctx.beginPath();
    ctx.arc(mx, my, 18, 0, Math.PI*2);
    ctx.lineWidth = 5;
    ctx.strokeStyle = latestMarker.object_stability > 0.45 ? "#7FE5A3" : "#E18E6D";
    ctx.stroke();
    ctx.translate(mx, my + 34);
    ctx.scale(-1, 1);
    ctx.font = "bold 16px -apple-system,sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    ctx.fillText("marker", 0, 0);
    ctx.restore();
  }

  // small status badge for hand gesture requirements
  const which = step.target.landmark;
  if(which === "HAND_OPEN" || which === "PINCH" || step.id === "H1-S1"){
    const h1OpenQuality = Math.min(handOpenScore, palmFacingScore);
    const score = step.id === "H1-S1" ? palmFacingScore : (step.id === "H1-S2" ? h1OpenQuality : (which === "HAND_OPEN" ? handOpenScore : pinchScore));
    const label = step.id === "H1-S1" ? "Palm" : (step.id === "H1-S2" ? "Palm + open" : (which === "HAND_OPEN" ? "Open" : "Pinch"));
    ctx.save();
    ctx.translate(tx, ty + tr + 32);
    ctx.scale(-1, 1);
    ctx.font = "bold 18px -apple-system,sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = score > 0.55 ? "#7FE5A3" : "rgba(255,255,255,0.85)";
    ctx.fillText(`${label}: ${Math.round(score*100)}%`, 0, 0);
    ctx.restore();
  }
}

function nextStep(skipped=false){
  const task = tasks[currentTaskIdx];
  const step = task.steps[currentStepIdx];
  if(!taskResults[currentTaskIdx]){
    taskResults[currentTaskIdx] = {
      task_id: task.id, completed_steps:0, total_steps:task.steps.length, duration_ms:0, steps:[], metrics:{}
    };
  }
  const stepDurationMs = Math.round(performance.now() - stepStartTime);
  taskResults[currentTaskIdx].steps.push({
    step_id: step.id,
    completed: !skipped,
    failure_code: skipped && step.failure_phenotype ? step.failure_phenotype.code : null,
    duration_ms: stepDurationMs,
    metrics: {
      trunk_lean_deg: Math.round(trunkLeanMax),
      shoulder_flexion_ratio: +shoulderFlexionMax.toFixed(2),
      shoulder_hike: shoulderHikeDetected,
      hand_open_score: +handOpenScore.toFixed(2),
      fist_closure_score: +fistClosureScore.toFixed(2),
      pinch_score: +pinchScore.toFixed(2),
      palm_facing_score: +palmFacingScore.toFixed(2),
      target_near_miss_count: nearMissEvents.length,
      target_near_miss_events: nearMissEvents.slice(),
      ...lowerBalanceMetricSnapshot(latestPoseLandmarks, step, stepDurationMs, skipped),
      ...handMetricSnapshot(),
      ...computeAdvancedObjectMetrics()
    }
  });
  if(!skipped) taskResults[currentTaskIdx].completed_steps += 1;
  taskResults[currentTaskIdx].duration_ms += stepDurationMs;

  // aggregate metrics
  if(trunkLeanMax > (taskResults[currentTaskIdx].metrics.trunk_lean_deg||0))
    taskResults[currentTaskIdx].metrics.trunk_lean_deg = Math.round(trunkLeanMax);
  if(shoulderHikeDetected) taskResults[currentTaskIdx].metrics.shoulder_hike = true;
  Object.assign(taskResults[currentTaskIdx].metrics, lowerBalanceMetricSnapshot(latestPoseLandmarks, step, stepDurationMs, skipped));
  Object.assign(taskResults[currentTaskIdx].metrics, handMetricSnapshot());
  if(isAdvancedMarkerTask(task)){
    taskResults[currentTaskIdx].metrics.advanced_marker_confirmed = !!advancedObjectModeByTask[task.id];
    Object.assign(taskResults[currentTaskIdx].metrics, computeAdvancedObjectMetrics());
  }

  currentStepIdx += 1;
  if(currentStepIdx >= task.steps.length){
    // Task complete — celebrate before moving on
    celebrateAndAdvance();
    return;
  }
  startStep();
}

function spawnConfetti(count){
  const colors = ["#E18E6D", "#D9E5DC", "#FDFDFD", "#4A7856", "#FFD58A"];
  for(let i = 0; i < count; i++){
    const c = document.createElement("div");
    c.className = "confetti";
    c.style.left = (Math.random() * 100) + "vw";
    c.style.background = colors[i % colors.length];
    c.style.animationDelay = (Math.random() * 0.3) + "s";
    c.style.animationDuration = (1.0 + Math.random() * 0.9) + "s";
    celebrateEl.appendChild(c);
    setTimeout(() => c.remove(), 2200);
  }
}

function renderCelebrateDots(){
  celebrateDots.innerHTML = "";
  tasks.forEach((_, i) => {
    const d = document.createElement("span");
    if(i <= currentTaskIdx) d.className = "done";
    celebrateDots.appendChild(d);
  });
}

async function celebrateAndAdvance(){
  const finishedTask = tasks[currentTaskIdx];
  const pick = CELEBRATION_LINES[currentTaskIdx % CELEBRATION_LINES.length];
  const voicePick = CELEBRATION_VOICES[currentTaskIdx % CELEBRATION_VOICES.length];

  // Show overlay
  celebrateLabel.textContent = `Task ${currentTaskIdx + 1} of ${tasks.length} complete`;
  celebrateTitle.textContent = pick.title;
  celebrateMsg.textContent = pick.msg;
  renderCelebrateDots();
  celebrateEl.classList.remove("hidden");
  // give browser a tick so the transition fires
  requestAnimationFrame(() => celebrateEl.classList.add("show"));
  spawnConfetti(28);
  if(navigator.vibrate) navigator.vibrate([60, 40, 100]);

  stopAndSaveTaskRecording(finishedTask.id);
  persistTaskProgress(finishedTask.id);

  postRN({type:"task_complete", package_id: ASSESSMENT_PACKAGE, task_id: finishedTask.id, task_index: currentTaskIdx});

  // Determine if there are more tasks
  const hasNext = (currentTaskIdx + 1) < tasks.length;

  // Play encouraging voice (only when not the final task — final has its own outro)
  let voiceMs = 0;
  const t0 = performance.now();
  if(hasNext){
    await playVoice(voicePick);
    voiceMs = performance.now() - t0;
  }

  // Ensure overlay is visible for at least ~2.4s for tactile/emotional pacing
  const minDisplayMs = 2400;
  if(voiceMs < minDisplayMs) await new Promise(r => setTimeout(r, minDisplayMs - voiceMs));

  // Hide overlay and advance
  celebrateEl.classList.remove("show");
  setTimeout(() => celebrateEl.classList.add("hidden"), 350);

  currentStepIdx = 0;
  currentTaskIdx += 1;
  if(currentTaskIdx >= tasks.length){
    finishAssessment();
    return;
  }
  startStep();
}

async function finishAssessment(){
  running = false;
  audioEl.pause();
  captionEl.textContent = "Saving your task videos and results…";
  voiceText.textContent = "Generating personalized plan…";
  try{
    if(pendingTaskVideoSaves.size){
      await Promise.allSettled(Array.from(pendingTaskVideoSaves));
    }
    if(pendingTaskProgressSaves.size){
      await Promise.allSettled(Array.from(pendingTaskProgressSaves));
    }
    const res = await fetch(`${API_BASE}/assessment/submit`,{
      method:"POST", headers:{"Content-Type":"application/json", ...(CURRENT_USER_ID ? {"X-User-Id": CURRENT_USER_ID} : {})},
      body: JSON.stringify({
        task_results: taskResults.filter(Boolean),
        affected_side: AFFECTED_SIDE,
        assessment_package: ASSESSMENT_PACKAGE,
        assigned_task_ids: tasks.map(task => task.id),
        motion_data: {
          schema_version: "1.0",
          coordinate_space: {
            pose_2d: "camera_normalized_unmirrored",
            pose_world_3d: "mediapipe_estimated_world_landmarks",
            hand_2d: "camera_normalized_unmirrored",
          },
          camera_projection: {
            source_width: video.videoWidth,
            source_height: video.videoHeight,
            display_width: cameraFrame.clientWidth,
            display_height: cameraFrame.clientHeight,
            fit: CAMERA_FIT_MODE,
            device_class: CAMERA_DEVICE_CLASS,
            mirrored_for_patient: true,
          },
          sample_interval_ms: MOTION_SAMPLE_INTERVAL_MS,
          truncated: motionFrames.length >= MAX_MOTION_FRAMES,
          frames: motionFrames,
        },
      })
    });
    if(!res.ok){
      const detail = await res.text();
      throw new Error(`Assessment save failed (${res.status}): ${detail.slice(0, 160)}`);
    }
    const data = await res.json();
    if(!data || !data.id) throw new Error("Assessment save response did not include an assessment id");
    postRN({type:"assessment_complete", assessment: data});
  }catch(e){
    postRN({type:"assessment_error", message:String(e)});
  }
}

function loop(){
  if(!running) return;
  const now = performance.now();
  const cameraFrameReady = !walkingCameraSwitching
    && video.readyState >= 2
    && video.videoWidth > 0
    && video.videoHeight > 0;
  let landmarks = latestPoseLandmarks;
  const handBackoff = isHandPerformanceBackoff();
  const poseScanInterval = isHandTask()
    ? (handBackoff ? HAND_BACKOFF_POSE_SCAN_INTERVAL_MS : HAND_PACKAGE_POSE_SCAN_INTERVAL_MS)
    : POSE_SCAN_INTERVAL_MS;
  if(cameraFrameReady && landmarker && (now - lastPoseScanTs) >= poseScanInterval){
    let result = null;
    try{
      result = landmarker.detectForVideo(video, now);
    }catch(e){}
    lastPoseScanTs = performance.now();
    if(result && result.landmarks && result.landmarks[0]){
      landmarks = result.landmarks[0];
      latestPoseLandmarks = landmarks;
      latestPoseWorldLandmarks = result.worldLandmarks && result.worldLandmarks[0]
        ? result.worldLandmarks[0]
        : null;
      computeMetrics(landmarks);
      updateLapTargetCalibration(landmarks, now);
      const activeTask = tasks[currentTaskIdx];
      // Lock T3's mouth point while the affected hand is still at the chest.
      // Waiting until the hand covers the mouth can pull facial landmarks and
      // the target away from the anatomical mouth center.
      if(activeTask && activeTask.id === "T3" && currentStepIdx === 0){
        updateMouthTargetCalibration(landmarks, lastPoseScanTs);
      }
      updateMovementGate(landmarks);
    }else{
      latestPoseLandmarks = null;
      latestPoseWorldLandmarks = null;
      landmarks = null;
    }
  }

  // Hand landmarks (optional). Run at a controlled cadence so Pose + Hands do
  // not block the UI thread on every animation frame.
  const handNeeded = needsHandLandmarks();
  const handScanInterval = handBackoff ? HAND_BACKOFF_SCAN_INTERVAL_MS : HAND_SCAN_INTERVAL_MS;
  if(cameraFrameReady && handLandmarker && handNeeded && (now - lastHandScanTs) >= handScanInterval){
    lastHandScanTs = now;
    try{
      const hr = handLandmarker.detectForVideo(video, now);
      const affectedHand = selectAffectedHandDetection(hr, now);
      if(affectedHand){
        latestHandLandmarks = affectedHand.landmarks;
        latestHandedness = affectedHand.handedness;
        latestHandSeenAt = now;
      }else{
        latestHandLandmarks = null;
        latestHandedness = "";
      }
    }catch(e){}
  }else if(!handNeeded){
    latestHandLandmarks = null;
    latestHandedness = "";
  }
  if(!walkingCaptureActive && landmarks){
    capturePatientFaceReference(video, landmarks, now);
  }
  if(calibratingAssessment) updatePreAssessmentCalibrationUI(landmarks);
  computeHandMetrics();
  updateTargetAttemptTracking(landmarks);
  captureMotionFrame(now);
  detectAxonAIMarker(now);
  updateRuntimeDiagnostics(now);

  drawOverlay(landmarks);

  if(calibratingAssessment){
    requestAnimationFrame(loop);
    return;
  }

  // check target hit — with a small "grace period" so brief jitter doesn't reset the hold
  const inTarget = correctionVoicePlaying ? false : checkTarget(landmarks);
  const step = getCurrentStep();
  if(step){
    if(inTarget){
      nearMissStartedAt = null;
      nearMissReason = "";
      if(inTargetSince == null) inTargetSince = now;
      lastInTargetTs = now;
      if(!stepCompleted && (now - inTargetSince) >= step.hold_ms){
        stepCompleted = true;
        if(navigator.vibrate) navigator.vibrate(80);
        setTimeout(()=>nextStep(false), 350);
      }
    }else{
      // Grace: allow up to 350ms outside the zone before resetting the hold.
      if(inTargetSince != null && (now - lastInTargetTs) > 350){
        inTargetSince = null;
      }
      if(!correctionVoicePlaying) handleTargetNearMiss(landmarks, now);
    }
  }
  requestAnimationFrame(loop);
}

let startSetupInProgress = false;
async function beginAssessmentSetup(){
  if(startSetupInProgress) return;
  startSetupInProgress = true;
  startBtn.textContent = "Opening camera...";
  startBtn.setAttribute("aria-busy", "true");
  const unlockPromise = unlockAudioPlayback();
  overlay.classList.add("hidden");
  startBtn.disabled = true;
  try{
    await ensureTasksLoaded();
  }catch(error){
    overlay.classList.remove("hidden");
    startBtn.disabled = false;
    startBtn.textContent = "Try Camera Again";
    startBtn.removeAttribute("aria-busy");
    startSetupInProgress = false;
    postRN({type:"camera_error", message:`Could not load assessment tasks: ${String(error)}`});
    return;
  }
  const firstStep = tasks[currentTaskIdx] && tasks[currentTaskIdx].steps && tasks[currentTaskIdx].steps[0];
  const firstVoicePromise = firstStep && firstStep.voice
    ? fetchVoiceAudio(firstStep.voice).catch(() => null)
    : Promise.resolve(null);
  calibratingAssessment = shouldRunSeatedCalibration();
  calibrationInstructionFinished = false;
  preAssessmentCalibrationReady = false;
  calibrationAutoStartInProgress = false;
  assessmentLapTarget = null;
  patientFaceReferenceSamples = [];
  patientFaceReference = null;
  lastPatientFaceReferenceAt = 0;
  lapTargetCalibration = newLapTargetCalibration();
  if(calibratingAssessment){
    ui.classList.add("hidden");
    calibrationOverlay.classList.remove("hidden");
    calibrationTitle.textContent = "Preparing your camera";
    calibrationLead.textContent = "Sit still with your affected hand resting on your lap while the camera and movement model get ready.";
    updatePreAssessmentCalibrationUI(null);
    prefetchVoice(CALIBRATION_INSTRUCTION);
    prefetchVoice(CALIBRATION_COMPLETE_INSTRUCTION);
  }
  const camOk = await setupCamera();
  if(!camOk){
    calibratingAssessment = false;
    calibrationOverlay.classList.add("hidden");
    ui.classList.remove("hidden");
    overlay.classList.remove("hidden");
    startBtn.disabled = false;
    startBtn.textContent = "Try Camera Again";
    startBtn.removeAttribute("aria-busy");
    startSetupInProgress = false;
    return;
  }
  try{
    await setupTrackingModels();
  }catch(error){
    calibratingAssessment = false;
    calibrationOverlay.classList.add("hidden");
    ui.classList.remove("hidden");
    overlay.classList.remove("hidden");
    startBtn.disabled = false;
    startBtn.textContent = "Try Camera Again";
    startBtn.removeAttribute("aria-busy");
    startSetupInProgress = false;
    postRN({type:"model_setup_error", message:String(error)});
    return;
  }
  preloadWalkingVideoValidator();
  await Promise.allSettled([unlockPromise, firstVoicePromise]);
  running = true;
  requestAnimationFrame(loop);
  if(calibratingAssessment){
    await playVoice(CALIBRATION_INSTRUCTION);
    calibrationInstructionFinished = true;
    updatePreAssessmentCalibrationUI(latestPoseLandmarks);
    return;
  }
  await startStep();
}

startBtn.addEventListener("click", beginAssessmentSetup);
if(window.__rehynStartRequested) void beginAssessmentSetup();

walkingVideoInput.addEventListener("click", () => {
  pendingUnconfirmedWalkingVideo = null;
  pendingUnconfirmedWalkingValidation = null;
  walkingProceedUnconfirmedBtn.classList.add("hidden");
  setWalkingCaptureStatus("Choose the walking video from this computer.");
});

walkingVideoInput.addEventListener("change", async () => {
  const file = walkingVideoInput.files && walkingVideoInput.files[0];
  if(!file){
    setWalkingCaptureStatus("No video was selected. Choose a walking video when ready.");
    return;
  }
  walkingChooseVideoBtn.disabled = true;
  walkingDesktopActions.classList.add("busy");
  setWalkingCaptureStatus("Opening the walking video on this device...");
  try{
    const validation = await validateWalkingVideo(file, progress => {
      setWalkingCaptureStatus(progress.message || "Checking the walking video...");
    });
    if(!validation.ok){
      if(validation.allowProceed && validation.reason === "identity_unconfirmed"){
        pendingUnconfirmedWalkingVideo = file;
        pendingUnconfirmedWalkingValidation = validation;
        walkingProceedUnconfirmedBtn.classList.remove("hidden");
      }
      setWalkingCaptureStatus(validation.message, "warn");
      return;
    }
    setWalkingCaptureStatus(validation.message, "good");
    await playVoice("The walking video passed the recording check. Thank you. Your assessment is now complete.");
    setWalkingCaptureStatus("Video checks passed. Preparing secure save...", "good");
    await completeUploadedWalkingTask(file, validation);
  }catch(error){
    setWalkingCaptureStatus(`The selected video could not be processed. ${String(error && error.message ? error.message : error)}`, "warn");
    postRN({type:"walking_video_error", message:String(error)});
  }finally{
    walkingChooseVideoBtn.disabled = false;
    walkingDesktopActions.classList.remove("busy");
    walkingVideoInput.value = "";
  }
});

walkingProceedUnconfirmedBtn.addEventListener("click", async () => {
  const file = pendingUnconfirmedWalkingVideo;
  const validation = pendingUnconfirmedWalkingValidation;
  if(!file || !validation || validation.reason !== "identity_unconfirmed"){
    walkingProceedUnconfirmedBtn.classList.add("hidden");
    setWalkingCaptureStatus("Choose the walking video again so Rehyn can review it.", "warn");
    return;
  }
  walkingProceedUnconfirmedBtn.disabled = true;
  walkingChooseVideoBtn.disabled = true;
  walkingDesktopActions.classList.add("busy");
  setWalkingCaptureStatus("Using this video without identity confirmation. It will be marked for therapist review.", "good");
  try{
    await playVoice("We could not confirm the face in this video. The video will be included and marked for therapist review.");
    await completeUploadedWalkingTask(file, {
      ...validation,
      ok:true,
      samePatientConfirmed:false,
      identityStatus:"unconfirmed_patient_proceeded",
    });
    pendingUnconfirmedWalkingVideo = null;
    pendingUnconfirmedWalkingValidation = null;
    walkingProceedUnconfirmedBtn.classList.add("hidden");
  }catch(error){
    setWalkingCaptureStatus(`The selected video could not be saved. ${String(error && error.message ? error.message : error)}`, "warn");
    postRN({type:"walking_video_error", message:String(error)});
  }finally{
    walkingProceedUnconfirmedBtn.disabled = false;
    walkingChooseVideoBtn.disabled = false;
    walkingDesktopActions.classList.remove("busy");
  }
});

walkingRecordBtn.addEventListener("click", async () => {
  walkingRecordBtn.disabled = true;
  setWalkingCaptureStatus("Opening the rear camera. Keep the patient safely in view...");
  const cameraReady = await switchToWalkingCamera();
  if(!cameraReady){
    setWalkingCaptureStatus("The walking camera could not be opened. Check camera permission and try again.", "warn");
    walkingRecordBtn.disabled = false;
    return;
  }
  walkingCaptureActive = true;
  walkingCapture.classList.add("hidden");
  ui.classList.remove("hidden");
  postRN({type:"walking_recording_started", task_id:"L6", device_mode:"mobile"});
  await startStep();
});

markerConfirmBtn.addEventListener("click", () => {
  if(!waitingForAdvancedGate) return;
  if(navigator.vibrate) navigator.vibrate(50);
  continueAdvancedTask(true);
});

markerMissingBtn.addEventListener("click", () => {
  markerChoicePanel.classList.add("hidden");
  markerMissingPanel.classList.remove("hidden");
});

markerBasicBtn.addEventListener("click", () => {
  if(!waitingForAdvancedGate) return;
  if(navigator.vibrate) navigator.vibrate(40);
  continueAdvancedTask(false);
});

markerBackBtn.addEventListener("click", () => {
  markerMissingPanel.classList.add("hidden");
  markerChoicePanel.classList.remove("hidden");
});

markerStoreBtn.addEventListener("click", () => {
  window.open(AXONAI_MARKER_STORE_URL, "_blank");
});

skipBtn.addEventListener("click", () => {
  if(!running) return;
  if(waitingForAdvancedGate) return;
  nextStep(true);
});

exitBtn.addEventListener("click", () => {
  postRN({type:"exit"});
});

// inform RN we're ready
postRN({type:"ready"});
</script>
</body>
</html>
"""


@api_router.get("/pose/runner", response_class=HTMLResponse)
async def pose_runner():
    return HTMLResponse(content=POSE_RUNNER_HTML)


# ============ Rehab Runner: per-exercise pose-guided reps with form feedback ============
# Each exercise defines:
#  - reps: total number of repetitions
#  - setup_voice: warm intro played once
#  - cycle: ordered list of pose targets the wrist must hit, defining ONE rep
#  - feedback_rules: ordered rules; first matching wins. Each rule: condition over per-rep metrics
#  - pose_mode: "body" (uses pose landmarks) or "tap" (fine-motor — patient taps complete)
REHAB_RUNNER_CONFIG: Dict[str, Dict[str, Any]] = {
    "ex_reach": {
        "name": "Graded Forward Reach",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "Welcome. We are going to practice the graded forward reach. Sit upright, with your back away from the chair. Place your affected hand on your lap. I'll guide you through each repetition.",
        "cycle": [
            {"caption": "Reach forward to the target", "voice": "Slowly reach your hand forward, as far as you comfortably can.", "target": {"x": 0.5, "y": 0.40, "r": 0.10}, "hold_ms": 1200},
            {"caption": "Return to lap", "voice": "Now gently return your hand to your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 18", "say": "I noticed your back leaned forward. On the next repetition, try keeping your spine tall and let your arm do the work."},
            {"if": "shoulder_hike", "say": "Your shoulder lifted up toward your ear. Try keeping your shoulder relaxed and dropped down on the next try."},
            {"if": "reach_completion < 0.7", "say": "You almost reached the target. On the next try, push gently from your shoulder to extend a little further."},
            {"default": "Beautiful repetition. On the next one, focus on a smooth, steady motion from start to finish."},
        ],
    },
    "ex_trunk": {
        "name": "Trunk-Restrained Reaching",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will practice trunk-restrained reaching. Sit tall, with your back firmly against the chair. Try to keep your back touching the chair the whole time. Let's begin.",
        "cycle": [
            {"caption": "Reach forward (back against chair)", "voice": "Reach forward to the target — keep your back pressed into the chair.", "target": {"x": 0.5, "y": 0.40, "r": 0.10}, "hold_ms": 1200},
            {"caption": "Return slowly", "voice": "Slowly return your hand to your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 10", "say": "Your back came away from the chair. On the next repetition, focus on pressing your back firmly into the chair before reaching."},
            {"if": "reach_completion < 0.7", "say": "With your back restrained, that's a great effort. On the next try, reach just a little further if you can."},
            {"default": "Excellent control of your trunk. Try to keep that same posture on the next repetition."},
        ],
    },
    "ex_wallslide": {
        "name": "Supported Arm Elevation Practice",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will practise supported arm elevation. Sit tall with your affected forearm supported on a table or towel. Move only in a comfortable, pain-free range. Use a wall slide only if your therapist has confirmed that it is safe for you.",
        "cycle": [
            {"caption": "Slide toward the upper target", "voice": "Using the support, slowly slide your affected arm toward the upper target. Stop before pain and keep your shoulder relaxed.", "target": {"x": 0.5, "y": 0.24, "r": 0.10}, "hold_ms": 1500},
            {"caption": "Return with support", "voice": "Now slide your arm back to the starting position, slowly and with control. Good work.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1500},
        ],
        "feedback_rules": [
            {"if": "shoulder_hike", "say": "Your shoulder lifted toward your ear. Try keeping your shoulder relaxed and pressed down as you raise your arm."},
            {"if": "trunk_lean_deg > 15", "say": "I noticed you leaned to one side. On the next repetition, try to stay tall and centered."},
            {"if": "reach_completion < 0.7", "say": "Almost reached the top. On the next try, exhale gently and try to go a little higher."},
            {"default": "Wonderful shoulder elevation. Keep that same control on the next repetition."},
        ],
    },
    "ex_scapdepress": {
        "name": "Scapular Depression Practice",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will practice keeping your shoulder down while reaching. Sit tall and gently pull your shoulder blades down and back, like sliding them into your back pockets. Then reach forward.",
        "cycle": [
            {"caption": "Reach forward (shoulders down)", "voice": "Reach forward — keep your shoulder pulled down and away from your ear.", "target": {"x": 0.5, "y": 0.40, "r": 0.10}, "hold_ms": 1200},
            {"caption": "Return", "voice": "Bring your hand back to your lap, shoulders still relaxed.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"if": "shoulder_hike", "say": "Your shoulder lifted again. On the next try, gently pull it down and back before you reach."},
            {"if": "trunk_lean_deg > 15", "say": "You leaned forward. Stay tall and let the shoulder blade do the work."},
            {"default": "Lovely scapular control. Keep that pattern on the next repetition."},
        ],
    },
    "ex_h2m": {
        "name": "Hand-to-Mouth ADL Practice",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will practice hand-to-mouth, an essential daily activity. Start with your hand on your lap, then slowly bring it up to your mouth.",
        "cycle": [
            {"caption": "Hand to mouth", "voice": "Bring your hand up to your mouth, slowly and smoothly.", "target": {"x": 0.5, "y": 0.30, "r": 0.10}, "hold_ms": 1500},
            {"caption": "Lower to lap", "voice": "Now gently lower your hand back to your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1500},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 15", "say": "Your trunk leaned to meet your hand. On the next try, keep your back tall and bring your hand to your mouth instead."},
            {"if": "reach_completion < 0.6", "say": "Almost there. On the next try, bend your elbow a bit more to bring your hand closer to your mouth."},
            {"default": "Smooth hand-to-mouth. Keep that quality on the next repetition."},
        ],
    },
    "ex_grasp": {
        "name": "Cylindrical Grasp & Transport",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will practise grasping and transporting a soft, lightweight cup. Place it on a stable table within a comfortable reach. Do not use glass, hot liquid, or a heavy object.",
        "cycle": [
            {"caption": "Reach and grasp the cup", "voice": "Reach toward the cup, open your affected hand around it, and form a comfortable grasp.", "target": {"x": 0.30, "y": 0.55, "r": 0.10}, "hold_ms": 1200},
            {"caption": "Transport the cup across", "voice": "Lift the cup only slightly and move it across the table with a slow, steady motion.", "target": {"x": 0.70, "y": 0.55, "r": 0.10}, "hold_ms": 1500},
            {"caption": "Place, release, and return", "voice": "Place the cup securely, open your fingers to release it, then bring your empty hand back to your lap. Nicely done.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 18", "say": "I noticed your trunk twisted with the cup. On the next repetition, try keeping your shoulders square and let your arm cross the midline."},
            {"if": "reach_completion < 0.6", "say": "Almost reached the far target. On the next try, extend a little further across your body."},
            {"default": "Beautiful transport. On the next repetition, focus on a smooth release at the end."},
        ],
    },
    "ex_handopen": {
        "name": "Active Hand Opening and Release",
        "reps": 8,
        "pose_mode": "tap",
        "setup_voice": "We will practise opening and relaxing your affected hand with your forearm supported on a table. Do not add a resistance band unless your therapist has specifically recommended one. Use your other hand for gentle assistance if needed.",
        "cycle": [
            {"caption": "Open your hand, release, and relax", "voice": "Slowly open your affected hand as comfortably as you can, hold for a moment, then let the fingers relax. That effort counts even if the movement is small. Tap when you finish one repetition.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Wonderful finger extension. On the next repetition, try to open your hand a little wider and hold for a full second before relaxing."},
        ],
    },
    "ex_pinch": {
        "name": "Pinch & Peg Placement",
        "reps": 8,
        "pose_mode": "tap",
        "setup_voice": "We will practice pinch. Gather a few small objects — coins, beads, or pegs. Pinch one between your thumb and index finger and place it into a container. Tap I did one repetition each time you place one.",
        "cycle": [
            {"caption": "Pinch and place one object", "voice": "Pinch one object with your thumb and index finger, place it in the container, then tap when done.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Lovely pinch control. On the next repetition, try a slightly smaller object or pinch with your thumb and middle finger for variety."},
        ],
    },
    "ex_bilateral": {
        "name": "Bilateral Arm Training",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will use both arms together. Imagine folding a towel between both hands. Move both arms inward to meet, then outward — equally on both sides.",
        "cycle": [
            {"caption": "Bring both hands together", "voice": "Bring both hands inward to meet in front of you, equally.", "target": {"x": 0.5, "y": 0.45, "r": 0.12}, "hold_ms": 1500},
            {"caption": "Open both arms outward", "voice": "Now open both hands outward, also equally.", "target": {"x": 0.5, "y": 0.45, "r": 0.30}, "hold_ms": 800},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 15", "say": "I noticed you leaned to one side. On the next repetition, try to stay centered and move both arms equally."},
            {"default": "Beautiful bilateral coordination. On the next repetition, try to make both arms perfectly mirror each other."},
        ],
    },
    "ex_lower_selective": {
        "name": "Supported Selective Lower-Limb Control",
        "reps": 5,
        "pose_mode": "guided",
        "setup_voice": "Welcome. Sit in a stable chair with both feet supported. Keep a carer nearby if you need help with sitting balance. We will practise one slow knee movement at a time, and you can confirm each step when it is complete.",
        "cycle": [
            {"caption": "Set your starting position", "voice": "Sit tall and place both feet flat. Keep your affected thigh supported and your knee pointing forward. When you feel steady, tap completed step.", "target": None, "hold_ms": 0},
            {"caption": "Straighten the affected knee", "voice": "Slowly straighten your affected knee within a comfortable range. Keep your thigh supported and breathe normally. Tap completed step when you reach your comfortable position.", "target": None, "hold_ms": 0},
            {"caption": "Lower with control", "voice": "Gently bend the knee and lower your foot back to the floor. Excellent control. Tap completed step when your foot is settled.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Well done. You completed the knee movement with care. For the next repetition, keep the movement slow and let the affected leg do as much as it safely can."},
        ],
    },
    "ex_ankle_dorsiflexion": {
        "name": "Seated Toe-Lift Practice",
        "reps": 6,
        "pose_mode": "guided",
        "setup_voice": "Sit securely with your affected foot flat and your heel supported on the floor. We will practise lifting the front of your foot without lifting the heel.",
        "cycle": [
            {"caption": "Keep your heel down", "voice": "Place your affected heel firmly on the floor and keep the knee pointing forward. Tap completed step when you are ready.", "target": None, "hold_ms": 0},
            {"caption": "Lift your toes and forefoot", "voice": "Keeping the heel down, gently lift your toes and the front of your foot. Hold for a comfortable moment, then tap completed step.", "target": None, "hold_ms": 0},
            {"caption": "Lower slowly", "voice": "Lower the front of your foot slowly until it rests on the floor. Nicely done. Tap completed step when it is settled.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Great effort. Keep the heel planted and aim for a smooth toe lift on the next repetition, even if the movement is small."},
        ],
    },
    "ex_sit_to_stand": {
        "name": "Assisted Sit-to-Stand Practice",
        "reps": 3,
        "pose_mode": "guided",
        "setup_voice": "Only begin with a therapist or capable carer beside you and a stable chair that cannot roll. Keep your usual support within reach. Stop if you feel dizzy, unsafe, or in pain.",
        "cycle": [
            {"caption": "Position your feet safely", "voice": "Move toward the front of the chair. Place both feet securely under your knees and let your carer take the agreed guarding position. Tap completed step when everyone is ready.", "target": None, "hold_ms": 0},
            {"caption": "Lean forward and stand", "voice": "Bring your nose gently over your toes, push through both feet, and stand with your carer's support. Take your time. Tap completed step only when you are safely upright.", "target": None, "hold_ms": 0},
            {"caption": "Pause in supported standing", "voice": "Pause while standing tall with your support. Make sure you feel steady before continuing. Tap completed step when you are ready to sit.", "target": None, "hold_ms": 0},
            {"caption": "Sit down with control", "voice": "Reach back for the chair if that is part of your therapist's method, bend at your hips and knees, and lower slowly with support. Excellent work. Tap completed step when you are safely seated.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Strong work. You completed the full stand and controlled return. Keep using the agreed assistance and a steady, unhurried rhythm."},
        ],
    },
    "ex_supported_stand": {
        "name": "Supported Standing Alignment",
        "reps": 3,
        "pose_mode": "guided",
        "setup_voice": "Have a therapist or capable carer beside you and use a fixed support. Do not practise this alone if you have any risk of falling.",
        "cycle": [
            {"caption": "Prepare your support", "voice": "Place both feet securely, hold the fixed support as instructed, and ask your carer to guard you. Tap completed step when you are ready.", "target": None, "hold_ms": 0},
            {"caption": "Stand tall and aligned", "voice": "Come into supported standing. Keep your chest tall, both knees comfortably aligned, and your weight through both feet. Tap completed step when you are steady.", "target": None, "hold_ms": 0},
            {"caption": "Return to the chair", "voice": "With your carer's help, lower yourself back to the chair slowly and safely. Well done. Tap completed step when you are seated.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Excellent supported standing practice. On the next repetition, keep your body tall and share your weight as evenly as you safely can."},
        ],
    },
    "ex_supported_step": {
        "name": "Guarded Step Initiation",
        "reps": 4,
        "pose_mode": "guided",
        "setup_voice": "Practise only with close guarding and a fixed support. Keep the floor clear, wear secure footwear, and use your usual walking aid if your therapist has advised it.",
        "cycle": [
            {"caption": "Find a steady starting stance", "voice": "Stand with your support and carer in position. Settle your weight through both feet. Tap completed step when you feel steady.", "target": None, "hold_ms": 0},
            {"caption": "Shift and begin the step", "voice": "Shift your weight safely onto the supporting leg, then gently lift and move the affected foot forward. Tap completed step when the foot is placed securely.", "target": None, "hold_ms": 0},
            {"caption": "Return to your starting stance", "voice": "Bring the affected foot back with control and regain an even, supported stance. Good work. Tap completed step when you are steady again.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Well done initiating the step. Keep the movement small, controlled, and fully supported on the next repetition."},
        ],
    },
    "ex_weight_shift": {
        "name": "Supported Affected-Side Weight Shift",
        "reps": 5,
        "pose_mode": "guided",
        "setup_voice": "Use a fixed support with a therapist or capable carer guarding you. We will make a small, controlled shift toward your affected side and return to the middle.",
        "cycle": [
            {"caption": "Stand safely in the middle", "voice": "Set both feet securely and stand tall with your support. Tap completed step when your carer confirms you are steady.", "target": None, "hold_ms": 0},
            {"caption": "Shift toward the affected side", "voice": "Move your pelvis gently toward your affected foot while keeping both feet down. Keep the movement small and comfortable. Tap completed step when you have paused there safely.", "target": None, "hold_ms": 0},
            {"caption": "Return to the middle", "voice": "Slowly bring your weight back to the middle and settle evenly over both feet. Nicely controlled. Tap completed step when you are steady.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Great controlled weight shift. On the next repetition, stay tall and move from your pelvis rather than leaning your shoulders."},
        ],
    },
    "ex_sitting_balance": {
        "name": "Guarded Sitting Midline and Reach",
        "reps": 5,
        "pose_mode": "guided",
        "setup_voice": "Sit in a stable chair with both feet supported and a carer guarding your affected side if needed. We will practise a small reach and a controlled return to the middle.",
        "cycle": [
            {"caption": "Find your upright middle", "voice": "Sit tall with your shoulders level and both feet supported. Tap completed step when you feel balanced in the middle.", "target": None, "hold_ms": 0},
            {"caption": "Make a small safe reach", "voice": "Reach a short distance toward the affected side within your comfortable balance. Keep your hips on the chair. Tap completed step when you have paused safely.", "target": None, "hold_ms": 0},
            {"caption": "Return to the middle", "voice": "Bring your trunk and hand back to the upright middle slowly. Excellent recovery. Tap completed step when you are balanced again.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Wonderful sitting control. Keep the next reach small and smooth, and finish each repetition fully back in the middle."},
        ],
    },
    "ex_step_stance": {
        "name": "Supported Step-Stance Control",
        "reps": 3,
        "pose_mode": "guided",
        "setup_voice": "Use a fixed support and close guarding. Only practise this after supported standing has been confirmed as safe by your therapist.",
        "cycle": [
            {"caption": "Prepare a stable stance", "voice": "Stand with both feet secure, your support in hand, and your carer beside you. Tap completed step when you are ready.", "target": None, "hold_ms": 0},
            {"caption": "Step into a short stance", "voice": "Move one foot a short distance forward as instructed by your therapist. Keep both knees comfortable and your body tall. Tap completed step when the stance is secure.", "target": None, "hold_ms": 0},
            {"caption": "Hold with support", "voice": "Pause in the short step stance while keeping your support. Breathe normally. Tap completed step when you are ready to return.", "target": None, "hold_ms": 0},
            {"caption": "Return to an even stance", "voice": "Bring the forward foot back slowly and settle your weight evenly. Excellent work. Tap completed step when you are steady.", "target": None, "hold_ms": 0},
        ],
        "feedback_rules": [
            {"default": "Excellent step-stance control. Keep using close support and make the next step only as large as you can control safely."},
        ],
    },
    "ex_maintenance": {
        "name": "Maintenance Conditioning",
        "reps": 4,
        "pose_mode": "body",
        "setup_voice": "We will do gentle full-range maintenance work. Reach the target, then return — focusing on smooth, full motion.",
        "cycle": [
            {"caption": "Reach the target", "voice": "Reach to the target with smooth motion.", "target": {"x": 0.5, "y": 0.30, "r": 0.12}, "hold_ms": 1200},
            {"caption": "Return", "voice": "Return to your starting position.", "target": {"x": 0.5, "y": 0.78, "r": 0.12}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"default": "Excellent. Maintain the same quality on the next repetition."},
        ],
    },
}


def _rehab_runner_html(exercise_id: str, prescribed_reps: Optional[int] = None) -> str:
    import copy as _copy
    import json as _json
    cfg = _copy.deepcopy(REHAB_RUNNER_CONFIG.get(exercise_id) or REHAB_RUNNER_CONFIG["ex_maintenance"])
    if prescribed_reps is not None:
        cfg["reps"] = max(1, min(20, int(prescribed_reps)))
    cfg_json = _json.dumps(cfg)
    return REHAB_RUNNER_HTML_TEMPLATE.replace("__CFG_JSON__", cfg_json)


@api_router.get("/rehab/runner", response_class=HTMLResponse)
async def rehab_runner(exercise_id: str = "ex_maintenance", reps: Optional[int] = None):
    return HTMLResponse(content=_rehab_runner_html(exercise_id, reps))


REHAB_RUNNER_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
<title>Rehab Exercise</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{width:100%;height:100%;background:#0c100e;color:#fdfdfd;font-family:-apple-system,BlinkMacSystemFont,"Plus Jakarta Sans",sans-serif;overflow:hidden}
  #stage{position:relative;width:100vw;height:100vh;height:100dvh;background:#000}
  #cameraFrame{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;background:#000}
  #cameraFrame video,#cameraFrame canvas{position:absolute;inset:0;width:100%;height:100%;transform:scaleX(-1);transform-origin:center}
  #ui{position:absolute;inset:0;pointer-events:none;display:flex;flex-direction:column;justify-content:space-between;padding:env(safe-area-inset-top,24px) 16px env(safe-area-inset-bottom,24px) 16px}
  #top{display:flex;align-items:center;gap:8px;background:rgba(28,32,29,0.65);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:12px 16px;pointer-events:auto}
  #top .meta{flex:1;display:flex;flex-direction:column}
  #top .name{font-size:14px;font-weight:700}
  #top .rep{font-size:12px;color:#D9E5DC}
  #exitBtn{background:rgba(255,255,255,0.18);border:none;color:#fff;padding:8px 12px;border-radius:16px;font-weight:600;font-size:13px;pointer-events:auto;cursor:pointer}
  #bottom{background:rgba(28,32,29,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:16px 18px;pointer-events:auto}
  #caption{font-size:18px;font-weight:600;line-height:1.35;min-height:48px}
  #voiceRow{display:flex;align-items:center;gap:10px;margin-top:10px;opacity:0.85}
  #voiceWave{display:flex;gap:3px;align-items:end;height:14px}
  #voiceWave span{display:block;width:3px;background:#E18E6D;border-radius:2px;animation:wave 1s ease-in-out infinite}
  #voiceWave span:nth-child(1){animation-delay:.0s;height:6px}
  #voiceWave span:nth-child(2){animation-delay:.15s;height:14px}
  #voiceWave span:nth-child(3){animation-delay:.3s;height:8px}
  #voiceWave span:nth-child(4){animation-delay:.45s;height:12px}
  @keyframes wave{0%,100%{transform:scaleY(0.5)}50%{transform:scaleY(1.2)}}
  #voiceText{font-size:13px;color:#D9E5DC}
  #tapBtn{margin-top:12px;background:#4A7856;color:#fff;border:none;width:100%;padding:14px;border-radius:16px;font-weight:700;font-size:16px;cursor:pointer}
  #tapBtn:disabled{opacity:.45;cursor:default}
  #overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#0c100eee;text-align:center;padding:24px;flex-direction:column;gap:16px;pointer-events:auto;z-index:10}
  #overlay h1{font-size:22px;font-weight:700}
  #overlay p{font-size:15px;color:#bcc2ba;line-height:1.5}
  #overlay button{background:#4A7856;color:#fff;border:none;padding:14px 28px;border-radius:16px;font-weight:700;font-size:16px}
  .hidden{display:none !important}
  /* Feedback / confirmation overlay */
  #fb{position:absolute;inset:0;background:linear-gradient(180deg, rgba(74,120,86,0.92), rgba(28,32,29,0.95));padding:24px;display:flex;flex-direction:column;justify-content:center;gap:16px;text-align:center;pointer-events:auto;z-index:9;opacity:0;transition:opacity .35s}
  #fb.show{opacity:1}
  #fb .step{font-size:13px;color:#D9E5DC;letter-spacing:1px;text-transform:uppercase;font-weight:700}
  #fb .title{font-size:22px;font-weight:800;color:#fff;line-height:1.3}
  #fb .body{font-size:16px;color:#FDFDFD;line-height:1.5;background:rgba(255,255,255,0.08);padding:14px;border-radius:14px}
  #fb .prompt{font-size:15px;color:#D9E5DC;font-style:italic}
  #fb .mic{display:flex;align-items:center;justify-content:center;gap:10px;background:rgba(225,142,109,0.18);padding:10px;border-radius:14px;border:1px solid rgba(225,142,109,0.4)}
  #fb .mic .dot{width:12px;height:12px;border-radius:50%;background:#E18E6D;animation:pulse 1.1s ease-in-out infinite}
  @keyframes pulse{0%,100%{transform:scale(.7);opacity:.6}50%{transform:scale(1.2);opacity:1}}
  #fb .heard{font-size:13px;color:#fff;opacity:.85;min-height:18px}
  #fb .row{display:flex;gap:10px;justify-content:center;margin-top:8px}
  #fb button{background:rgba(255,255,255,0.18);color:#fff;border:none;padding:12px 18px;border-radius:14px;font-weight:700;font-size:14px;cursor:pointer}
  #fb button.primary{background:#4A7856}
  #fb .check{font-size:14px;color:#D9E5DC;display:flex;gap:8px;align-items:center;justify-content:center}
  #fb .check span.ok{color:#7FE5A3}
</style>
</head>
<body>
<div id="stage">
  <div id="cameraFrame">
    <video id="video" playsinline autoplay muted></video>
    <canvas id="canvas"></canvas>
  </div>
  <div id="ui">
    <div id="top">
      <button id="exitBtn" data-testid="rehab-exit">Exit</button>
      <div class="meta">
        <div class="name" id="exName">Exercise</div>
        <div class="rep" id="repLabel">Rep 1 of 5</div>
        <div id="repBar" style="height:6px;background:rgba(255,255,255,0.18);border-radius:3px;margin-top:6px;overflow:hidden">
          <div id="repBarFill" style="height:100%;width:0%;background:#E18E6D;border-radius:3px;transition:width .3s ease"></div>
        </div>
      </div>
    </div>
    <div id="bottom">
      <div id="caption">Preparing…</div>
      <div id="voiceRow">
        <div id="voiceWave"><span></span><span></span><span></span><span></span></div>
        <div id="voiceText">Listening to instructions…</div>
      </div>
      <button id="tapBtn" class="hidden" data-testid="rehab-tap-rep">I did one repetition</button>
    </div>
  </div>
  <div id="overlay">
    <h1 id="overlayTitle">Ready?</h1>
    <p id="overlayBody">We will guide you through each repetition with your camera and voice. After every rep I will share what to improve. Move into the camera view.</p>
    <button id="startBtn" data-testid="rehab-start">Start Exercise</button>
  </div>
  <div id="fb" class="hidden">
    <div class="step" id="fbStep">Rep 1 complete</div>
    <div class="title" id="fbTitle">Here's what I noticed</div>
    <div class="body" id="fbBody">…</div>
    <div class="prompt" id="fbPrompt">When you're ready, please say <b>"Yes"</b>.</div>
    <div class="mic" id="fbMic">
      <div class="dot"></div>
      <div id="fbHeard" class="heard">Listening…</div>
    </div>
    <div class="check" id="fbChecks">
      <span id="checkYes">○ Yes</span>
      <span style="opacity:.4">·</span>
      <span id="checkUnderstand">○ "I understand my problem now"</span>
    </div>
    <div class="row">
      <button id="fbReplay">Replay</button>
      <button id="fbConfirmBtn" class="primary">I'm ready (tap)</button>
    </div>
  </div>
</div>

<script type="module">
import { PoseLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "/vendor/mediapipe/vision_bundle.mjs";

const API_BASE = window.location.origin + "/api";
const CFG = __CFG_JSON__;

const stage = document.getElementById("stage");
const cameraFrame = document.getElementById("cameraFrame");
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const exName = document.getElementById("exName");
const repLabel = document.getElementById("repLabel");
const captionEl = document.getElementById("caption");
const voiceText = document.getElementById("voiceText");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlayTitle");
const overlayBody = document.getElementById("overlayBody");
const startBtn = document.getElementById("startBtn");
const exitBtn = document.getElementById("exitBtn");
const tapBtn = document.getElementById("tapBtn");
const fbEl = document.getElementById("fb");
const fbStep = document.getElementById("fbStep");
const fbTitle = document.getElementById("fbTitle");
const fbBody = document.getElementById("fbBody");
const fbHeard = document.getElementById("fbHeard");
const fbConfirmBtn = document.getElementById("fbConfirmBtn");
const fbReplay = document.getElementById("fbReplay");
const checkYes = document.getElementById("checkYes");
const checkUnderstand = document.getElementById("checkUnderstand");
const URL_PARAMS = new URLSearchParams(window.location.search);
const VOICE_GUIDANCE_ENABLED = URL_PARAMS.get("voice_guidance") !== "0";

function classifyCameraDevice({
  userAgent=navigator.userAgent || "",
  userAgentDataMobile=navigator.userAgentData && navigator.userAgentData.mobile,
  maxTouchPoints=navigator.maxTouchPoints || 0,
  screenWidth=screen.width,
  screenHeight=screen.height,
  deviceMode=URL_PARAMS.get("device_mode"),
}={}){
  if(deviceMode === "mobile" || deviceMode === "phone") return "phone";
  if(deviceMode === "tablet") return "tablet";
  if(deviceMode === "desktop" || deviceMode === "web") return "web";
  if(userAgentDataMobile === true || /iPhone|iPod/i.test(userAgent) || (/Android/i.test(userAgent) && /Mobile/i.test(userAgent))){
    return "phone";
  }
  if(/iPad/i.test(userAgent) || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1) || (/Android/i.test(userAgent) && !/Mobile/i.test(userAgent))){
    return "tablet";
  }
  const shortScreenEdge = Math.min(Number(screenWidth) || Infinity, Number(screenHeight) || Infinity);
  return maxTouchPoints > 0 && shortScreenEdge <= 600 ? "phone" : "web";
}

const CAMERA_DEVICE_CLASS = classifyCameraDevice();
const CAMERA_FIT_MODE = CAMERA_DEVICE_CLASS === "phone" ? "cover" : "contain";

function fitCameraViewport(containerWidth, containerHeight, sourceWidth, sourceHeight, fitMode=CAMERA_FIT_MODE){
  const safeContainerWidth = Math.max(1, Number(containerWidth) || 1);
  const safeContainerHeight = Math.max(1, Number(containerHeight) || 1);
  const safeSourceWidth = Math.max(1, Number(sourceWidth) || 1);
  const safeSourceHeight = Math.max(1, Number(sourceHeight) || 1);
  const scale = fitMode === "cover"
    ? Math.max(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight)
    : Math.min(safeContainerWidth / safeSourceWidth, safeContainerHeight / safeSourceHeight);
  const width = safeSourceWidth * scale;
  const height = safeSourceHeight * scale;
  return {
    left:(safeContainerWidth - width) / 2,
    top:(safeContainerHeight - height) / 2,
    width,
    height,
    fit:fitMode,
  };
}

function responsiveVideoSettings(longEdge, shortEdge, maxFrameRate=30){
  const portrait = stage.clientHeight > stage.clientWidth;
  return {
    facingMode:"user",
    width:{ideal:portrait ? shortEdge : longEdge},
    height:{ideal:portrait ? longEdge : shortEdge},
    frameRate:{ideal:maxFrameRate, max:maxFrameRate},
  };
}

function syncCameraViewport(){
  if(!video.videoWidth || !video.videoHeight) return;
  const rect = fitCameraViewport(stage.clientWidth, stage.clientHeight, video.videoWidth, video.videoHeight, CAMERA_FIT_MODE);
  cameraFrame.style.left = `${rect.left}px`;
  cameraFrame.style.top = `${rect.top}px`;
  cameraFrame.style.width = `${rect.width}px`;
  cameraFrame.style.height = `${rect.height}px`;
  document.body.dataset.cameraDevice = CAMERA_DEVICE_CLASS;
  document.body.dataset.cameraFit = rect.fit;
  if(canvas.width !== video.videoWidth) canvas.width = video.videoWidth;
  if(canvas.height !== video.videoHeight) canvas.height = video.videoHeight;
}

window.__rehynCameraViewportTest = {
  classifyCameraDevice,
  fitCameraViewport,
  syncCameraViewport,
  deviceClass:CAMERA_DEVICE_CLASS,
  fitMode:CAMERA_FIT_MODE,
};

window.addEventListener("resize", syncCameraViewport, {passive:true});
window.addEventListener("orientationchange", () => setTimeout(syncCameraViewport, 120), {passive:true});
video.addEventListener("resize", syncCameraViewport);
if(window.ResizeObserver) new ResizeObserver(syncCameraViewport).observe(stage);

let landmarker = null, drawingUtils = null;
let currentRep = 0;
let currentSubStep = 0;
let stepStartTime = 0;
let inTargetSince = null;
let stepCompleted = false;
let running = false;
let audioEl = new Audio();
const voiceAudioCache = new Map();
const voiceAudioInflight = new Map();
let audioUnlockPromise = null;

// Per-rep accumulated metrics
let trunkLeanMax = 0;
let shoulderHikeDetected = false;
let reachMax = 0;

exName.textContent = CFG.name;
overlayTitle.textContent = CFG.name;
overlayBody.textContent = CFG.setup_voice;

function postRN(d){ if(window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(d)); }

function createSilentWavUrl(){
  const sampleRate = 8000;
  const sampleCount = 800;
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  const writeText = (offset, value) => {
    for(let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, sampleCount * 2, true);
  return URL.createObjectURL(new Blob([buffer], {type:"audio/wav"}));
}

function unlockAudioPlayback(){
  if(audioUnlockPromise) return audioUnlockPromise;
  const silentUrl = createSilentWavUrl();
  audioEl.preload = "auto";
  audioEl.setAttribute("playsinline", "true");
  audioEl.src = silentUrl;
  const playback = audioEl.play();
  audioUnlockPromise = Promise.resolve(playback)
    .then(() => {
      audioEl.pause();
      audioEl.currentTime = 0;
      URL.revokeObjectURL(silentUrl);
      return true;
    })
    .catch(error => {
      URL.revokeObjectURL(silentUrl);
      audioUnlockPromise = null;
      postRN({type:"voice_unlock_error", message:String(error)});
      return false;
    });
  return audioUnlockPromise;
}

function playBrowserVoice(text){
  return new Promise((resolve) => {
    if(!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance){
      resolve(false);
      return;
    }
    try{
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";
      utterance.rate = 0.88;
      utterance.pitch = 1.0;
      utterance.onend = () => resolve(true);
      utterance.onerror = () => resolve(false);
      window.speechSynthesis.speak(utterance);
      setTimeout(() => resolve(true), Math.min(14000, Math.max(3500, text.length * 70)));
    }catch(e){
      resolve(false);
    }
  });
}

async function playVoice(text){
  if(!VOICE_GUIDANCE_ENABLED || !text){
    voiceText.textContent = "Voice guidance off · follow on-screen text";
    return;
  }
  try{
    voiceText.textContent = "Playing instruction…";
    const audioB64 = await fetchVoiceAudio(text);
    audioEl.pause();
    audioEl.src = "data:audio/mpeg;base64," + audioB64;
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = callback => {
        if(settled) return;
        settled = true;
        clearTimeout(timeout);
        audioEl.onended = null;
        audioEl.onerror = null;
        callback();
      };
      const timeout = setTimeout(() => finish(resolve), 45000);
      audioEl.onended = () => finish(resolve);
      audioEl.onerror = () => finish(() => reject(new Error("Audio element could not play the instruction")));
      const playback = audioEl.play();
      if(playback && typeof playback.catch === "function"){
        playback.catch(error => finish(() => reject(error)));
      }
    });
    voiceText.textContent = "Instruction ready";
  }catch(e){
    voiceText.textContent = "Using device voice";
    const spoke = await playBrowserVoice(text);
    voiceText.textContent = spoke ? "Instruction ready" : "Voice unavailable — follow on-screen text";
  }
}

function fetchVoiceAudio(text){
  const key = `nova::${text}`;
  if(voiceAudioCache.has(key)) return Promise.resolve(voiceAudioCache.get(key));
  if(voiceAudioInflight.has(key)) return voiceAudioInflight.get(key);
  const request = fetch(`${API_BASE}/tts/generate`,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text})
  }).then(async res => {
    if(!res.ok) throw new Error("tts fail");
    const data = await res.json();
    voiceAudioCache.set(key, data.audio_b64);
    return data.audio_b64;
  }).finally(() => voiceAudioInflight.delete(key));
  voiceAudioInflight.set(key, request);
  return request;
}

function prefetchVoice(text){
  if(!VOICE_GUIDANCE_ENABLED || !text) return Promise.resolve(null);
  return fetchVoiceAudio(text).catch(() => null);
}

async function setupCamera(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:responsiveVideoSettings(1280, 720),audio:false});
    video.srcObject = stream;
    await new Promise(r => video.onloadedmetadata = r);
    syncCameraViewport();
    return true;
  }catch(e){
    captionEl.textContent = "Camera permission denied.";
    postRN({type:"camera_error", message: String(e)});
    return false;
  }
}

async function setupPose(){
  const fr = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
  landmarker = await PoseLandmarker.createFromOptions(fr,{
    baseOptions:{modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task"},
    runningMode:"VIDEO", numPoses:1
  });
  drawingUtils = new DrawingUtils(ctx);
}

function rad2deg(r){ return r*180/Math.PI; }

function updateMetrics(lm){
  if(!lm) return;
  const Ls=lm[11], Rs=lm[12], Lh=lm[23], Rh=lm[24], Lw=lm[15], Rw=lm[16];
  const midSh={x:(Ls.x+Rs.x)/2, y:(Ls.y+Rs.y)/2};
  const midHip={x:(Lh.x+Rh.x)/2, y:(Lh.y+Rh.y)/2};
  const trunk = Math.abs(rad2deg(Math.atan2(midSh.x-midHip.x, -(midSh.y-midHip.y))));
  trunkLeanMax = Math.max(trunkLeanMax, trunk);
  if((midHip.y - midSh.y) > 0.40) shoulderHikeDetected = true;
  // reach completion proxy: closest wrist distance to current target
  const sub = CFG.cycle[currentSubStep];
  if(sub && sub.target){
    const t = sub.target;
    const best = Math.min(
      Math.hypot((1-Lw.x)-t.x, Lw.y-t.y),
      Math.hypot((1-Rw.x)-t.x, Rw.y-t.y),
    );
    // 0 = at target, 1 = far. compute completion = 1 - clamp(best / (t.r*3))
    const comp = 1 - Math.min(1, best / (t.r * 3));
    reachMax = Math.max(reachMax, comp);
  }
}

function checkTarget(lm){
  const sub = CFG.cycle[currentSubStep];
  if(!sub || !sub.target || !lm) return false;
  const t = sub.target;
  // Slightly enlarge the hit radius so users don't have to lean in (Phase B+).
  // Visual circle below uses the same multiplier so what you see == what triggers.
  const R = t.r * 1.55;
  const Lw=lm[15], Rw=lm[16];
  const ok = (p) => p && Math.hypot((1-p.x)-t.x, p.y-t.y) < R;
  return ok(Lw) || ok(Rw);
}

function drawOverlay(lm){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if(lm){
    drawingUtils.drawLandmarks(lm,{color:"#D9E5DC", radius:3});
    drawingUtils.drawConnectors(lm, PoseLandmarker.POSE_CONNECTIONS,{color:"#4A7856",lineWidth:4});
  }
  const sub = CFG.cycle[currentSubStep];
  if(sub && sub.target){
    const tx = sub.target.x*canvas.width;
    const ty = sub.target.y*canvas.height;
    const tr = sub.target.r * 1.55 * Math.min(canvas.width,canvas.height);
    const pulse = 1 + 0.08*Math.sin(performance.now()/250);
    ctx.beginPath(); ctx.arc(tx,ty,tr*pulse,0,Math.PI*2);
    ctx.lineWidth = 6; ctx.strokeStyle = "#E18E6D"; ctx.stroke();
    ctx.beginPath(); ctx.arc(tx,ty,tr*0.5,0,Math.PI*2);
    ctx.fillStyle = "rgba(225,142,109,0.4)"; ctx.fill();
    if(inTargetSince){
      const elapsed = performance.now() - inTargetSince;
      const progress = Math.min(1, elapsed / sub.hold_ms);
      ctx.beginPath(); ctx.arc(tx,ty,tr*1.25, -Math.PI/2, -Math.PI/2 + progress*Math.PI*2);
      ctx.strokeStyle = "#3C8255"; ctx.lineWidth = 8; ctx.stroke();
    }
  }
}

async function startRep(){
  currentSubStep = 0;
  trunkLeanMax = 0; shoulderHikeDetected = false; reachMax = 0;
  repLabel.textContent = `Repetition ${currentRep+1} of ${CFG.reps}`;
  // Update the visual rep progress bar
  try{
    const pct = Math.round((currentRep / Math.max(1, CFG.reps)) * 100);
    const fill = document.getElementById("repBarFill");
    if(fill) fill.style.width = pct + "%";
  }catch(e){}
  if(CFG.pose_mode === "tap" || CFG.pose_mode === "guided"){
    tapBtn.classList.remove("hidden");
    tapBtn.textContent = CFG.pose_mode === "guided" ? "I completed this step" : "I did one repetition";
  }else{
    tapBtn.classList.add("hidden");
  }
  await startSubStep();
}

async function startSubStep(){
  const sub = CFG.cycle[currentSubStep];
  captionEl.textContent = sub.caption;
  stepStartTime = performance.now();
  inTargetSince = null; stepCompleted = false;
  tapBtn.disabled = true;
  prefetchVoice(CFG.cycle[currentSubStep + 1] && CFG.cycle[currentSubStep + 1].voice);
  await playVoice(sub.voice);
  tapBtn.disabled = false;
}

function pickFeedback(){
  // Evaluate rules; first match wins. Use a minimal mini-expression evaluator.
  const ctx = {
    trunk_lean_deg: Math.round(trunkLeanMax),
    shoulder_hike: shoulderHikeDetected,
    reach_completion: +reachMax.toFixed(2),
  };
  for(const rule of CFG.feedback_rules){
    if(rule.default) return rule.say || rule.default;
    if(!rule.if) continue;
    try{
      // SAFE: rules are author-controlled in backend config, not user input.
      const fn = new Function("trunk_lean_deg","shoulder_hike","reach_completion", `return (${rule.if});`);
      if(fn(ctx.trunk_lean_deg, ctx.shoulder_hike, ctx.reach_completion)){
        return rule.say;
      }
    }catch(e){ /* skip */ }
  }
  return "Beautiful repetition.";
}

// ===== Speech Recognition for voice confirmation =====
let recognition = null;
let yesHeard = false, understandHeard = false;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function startListening(){
  yesHeard = false; understandHeard = false;
  checkYes.textContent = "○ Say \"yes\"";
  // Second-check kept hidden; we ONLY require a single "yes" now — the long
  // phrase confused users and the SpeechRecognition API often errors silently
  // in WebViews.
  checkUnderstand.textContent = "";
  fbHeard.textContent = SR ? "Listening… or tap Continue when ready." : "Tap Continue when ready.";
  if(!SR){ understandHeard = true; return; }
  try{
    recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (e) => {
      let txt = "";
      for(let i = e.resultIndex; i < e.results.length; i++){
        txt += e.results[i][0].transcript.toLowerCase();
      }
      fbHeard.textContent = '"' + txt.slice(-60).trim() + '"';
      if(!yesHeard && /\b(yes|yeah|yep|okay|ok|continue|next)\b/.test(txt)){
        yesHeard = true;
        checkYes.textContent = "✓ Heard you";
        checkYes.classList.add("ok");
        // Single confirmation is enough — proceed.
        stopListening();
        confirmAndContinue();
      }
    };
    recognition.onerror = (ev) => {
      // Silently fall back — never alarm the user. The tap button always works.
      fbHeard.textContent = "Tap Continue when ready.";
      try{ recognition.onend = null; }catch(e){}
    };
    recognition.onend = () => {
      if(running && !yesHeard){
        try{ recognition.start(); }catch(e){}
      }
    };
    recognition.start();
  }catch(e){
    fbHeard.textContent = "Tap Continue when ready.";
  }
}
function stopListening(){
  if(recognition){
    try{ recognition.onend = null; recognition.stop(); }catch(e){}
    recognition = null;
  }
}

let lastFeedbackText = "";
let lastRepScore = 0;

// Score 0-100 for a single repetition. Deductions for compensations (trunk lean
// past 5°, shoulder hike) and incomplete reach. Tuned to be encouraging — most
// effortful reps land 70-95.
function computeRepScore(){
  let s = 100;
  // Trunk lean: tolerate up to 5°, then deduct 1.5 per degree, capped at 30.
  const leanPenalty = Math.min(30, Math.max(0, (trunkLeanMax - 5)) * 1.5);
  s -= leanPenalty;
  // Shoulder hike: 12 point deduction
  if(shoulderHikeDetected) s -= 12;
  // Incomplete reach: scale 0..30 deduction
  s -= (1 - reachMax) * 30;
  s = Math.max(0, Math.min(100, Math.round(s)));
  return s;
}

function scoreLabel(s){
  if(s >= 90) return "Excellent form";
  if(s >= 75) return "Great work";
  if(s >= 60) return "Good effort";
  if(s >= 45) return "Keep practicing";
  return "Take it gently";
}

async function showFeedback(){
  const feedback = pickFeedback();
  lastFeedbackText = feedback;
  const cameraScored = CFG.pose_mode === "body";
  lastRepScore = cameraScored ? computeRepScore() : null;
  const label = cameraScored ? scoreLabel(lastRepScore) : "Well done";
  fbStep.textContent = `Repetition ${currentRep+1} of ${CFG.reps} complete · ${label}`;
  fbTitle.textContent = cameraScored ? `Your score: ${lastRepScore}/100` : "Repetition complete";
  fbBody.textContent = feedback;
  if(navigator.vibrate) navigator.vibrate([50, 30, 80]);
  fbEl.classList.remove("hidden");
  requestAnimationFrame(() => fbEl.classList.add("show"));
  postRN({type:"rep_complete", rep: currentRep+1, total: CFG.reps, score: lastRepScore, feedback});

  // Voice: feedback + ask for "yes"
  const feedbackVoice = cameraScored
    ? `Your score is ${lastRepScore} out of 100. ${label}. ${feedback} When you're ready, tap continue, or say yes to keep going.`
    : `${label}. ${feedback} When you're ready, tap continue, or say yes to keep going.`;
  await playVoice(feedbackVoice);
  startListening();
}

async function confirmAndContinue(){
  stopListening();
  fbEl.classList.remove("show");
  setTimeout(()=> fbEl.classList.add("hidden"), 350);
  currentRep += 1;
  if(currentRep >= CFG.reps){
    finishExercise();
    return;
  }
  await playVoice("Wonderful. Here we go.");
  await startRep();
}

async function finishExercise(){
  running = false;
  fbEl.classList.add("hidden");
  captionEl.textContent = "Exercise complete!";
  await playVoice("Magnificent work. You have finished this exercise. I'm so proud of you.");
  postRN({type:"exercise_complete", exercise_id: location.search, reps: CFG.reps});
}

function advanceSubStep(){
  currentSubStep += 1;
  if(currentSubStep >= CFG.cycle.length){
    // Rep complete → feedback
    showFeedback();
    return;
  }
  startSubStep();
}

// Tap-based rep handler (for fine-motor exercises)
tapBtn.addEventListener("click", () => {
  if(!running) return;
  if(CFG.pose_mode === "tap"){
    showFeedback();
    return;
  }
  if(CFG.pose_mode !== "guided" || tapBtn.disabled) return;
  tapBtn.disabled = true;
  if(currentSubStep + 1 >= CFG.cycle.length){
    showFeedback();
  }else{
    advanceSubStep();
  }
});

fbConfirmBtn.addEventListener("click", () => {
  // Manual confirm bypass: only if both yes+understand heard, OR user explicitly taps after replaying
  // We honor the user contract: tap is the explicit accessibility fallback.
  confirmAndContinue();
});

fbReplay.addEventListener("click", async () => {
  if(!lastFeedbackText) return;
  await playVoice(lastFeedbackText + " When you're ready, please say yes, then I understand my problem now.");
});

function loop(){
  if(!running) return;
  const now = performance.now();
  let lm = null;
  try{
    const r = landmarker.detectForVideo(video, now);
    if(r && r.landmarks && r.landmarks[0]) lm = r.landmarks[0];
  }catch(e){}
  if(lm) updateMetrics(lm);
  drawOverlay(lm);

  // Sub-step target detection (only while NOT showing feedback)
  if(CFG.pose_mode === "body" && !fbEl.classList.contains("show")){
    const sub = CFG.cycle[currentSubStep];
    if(sub && sub.target){
      const ok = checkTarget(lm);
      if(ok){
        if(inTargetSince == null) inTargetSince = now;
        if(!stepCompleted && (now - inTargetSince) >= sub.hold_ms){
          stepCompleted = true;
          if(navigator.vibrate) navigator.vibrate(60);
          setTimeout(() => advanceSubStep(), 250);
        }
      }else{
        inTargetSince = null;
      }
    }
  }
  requestAnimationFrame(loop);
}

startBtn.addEventListener("click", async () => {
  const unlockPromise = unlockAudioPlayback();
  const setupVoicePromise = prefetchVoice(CFG.setup_voice);
  CFG.cycle.forEach(step => prefetchVoice(step.voice));
  overlay.classList.add("hidden");
  startBtn.disabled = true;
  const camOk = await setupCamera();
  if(!camOk){ overlay.classList.remove("hidden"); return; }
  await setupPose();
  await Promise.allSettled([unlockPromise, setupVoicePromise]);
  running = true;
  await playVoice(CFG.setup_voice);
  await startRep();
  requestAnimationFrame(loop);
});

exitBtn.addEventListener("click", () => {
  stopListening();
  postRN({type:"exit"});
});

postRN({type:"ready"});
</script>
</body>
</html>
"""


# ============ Therapists (seed — AI early-access personas) ============
# Marked ai=True. In early access we use AI therapist personas grounded in clinical knowledge.
# Real licensed therapists will join as we scale.
THERAPISTS_SEED: List[Dict[str, Any]] = [
    {"id": "th_001", "ai": True, "trained_on": "12 years of OT case data — fine motor & hand rehab", "premium": True, "name": "Maya (AI Therapist)", "title": "AI Occupational Therapist — Hand & Fine Motor", "specialties": ["HAND_OPENING", "PINCH_IMPAIRED", "GROSS_GRASP"], "location": "Always available · Worldwide", "languages": ["English", "Spanish"], "rating": 4.9, "years": 12, "availability": ["24/7 chat"], "blurb": "I specialize in helping survivors rebuild fine motor control with playful, daily activities. We'll go at your pace.", "photo": "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=400",
     "persona_prompt": "You are 'Maya', an AI occupational therapist persona focused on hand and fine-motor rehabilitation after stroke. Speak warmly and patiently. Reference real clinical sources when useful (CIMT, Jebsen, ARAT). Always remind the patient you're an AI early-access companion, not a licensed clinician for diagnosis."},
    {"id": "th_002", "ai": True, "trained_on": "9 years of neuro-PT case data — reach training & trunk control", "premium": True, "name": "Aiden (AI Therapist)", "title": "AI Physical Therapist — Reach & Shoulder", "specialties": ["REACH_INCOMPLETE", "SHOULDER_FLEX_LIMITED", "TRUNK_COMP"], "location": "Always available · Worldwide", "languages": ["English", "Korean"], "rating": 4.8, "years": 9, "availability": ["24/7 chat"], "blurb": "Reach training and trunk control specialist. I love seeing the moment a patient realizes their arm can do more than they thought.", "photo": "https://images.unsplash.com/photo-1622253692010-333f2da6031d?w=400",
     "persona_prompt": "You are 'Aiden', an AI physical-therapy persona focused on reaching, shoulder flexion, and trunk control. Calm, encouraging, evidence-based (Levin & Michaelsen trunk restraint, Fugl-Meyer, task-specific training). You're an AI early-access companion."},
    {"id": "th_003", "ai": True, "trained_on": "15 years of Bobath/NDT-informed practice — bilateral coordination", "premium": True, "name": "Priya (AI Therapist)", "title": "AI Neuro-PT — Bilateral & Hand-to-Mouth ADL", "specialties": ["SHOULDER_HIKE", "BILATERAL_NONUSE", "H2M_IMPAIRED"], "location": "Always available · Worldwide", "languages": ["English", "Tamil", "Hindi"], "rating": 4.95, "years": 15, "availability": ["24/7 chat"], "blurb": "Bobath-trained mindset. I focus on calm, gentle re-education of movement patterns. Family welcome in every session.", "photo": "https://images.unsplash.com/photo-1594824476967-48c8b964273f?w=400",
     "persona_prompt": "You are 'Priya', an AI neuro-PT persona with a Bobath/NDT-informed mindset, focused on bilateral coordination and hand-to-mouth ADLs. Gentle, never patronizing. AI early-access companion."},
    {"id": "th_004", "ai": True, "trained_on": "7 years of CIMT (Constraint-Induced Movement Therapy) practice", "premium": True, "name": "Sam (AI Therapist)", "title": "AI OT — CIMT & Constraint-Induced Practice", "specialties": ["BILATERAL_NONUSE", "HAND_OPENING", "REACH_INCOMPLETE"], "location": "Always available · Worldwide", "languages": ["English", "Spanish"], "rating": 4.7, "years": 7, "availability": ["24/7 chat"], "blurb": "Constraint-induced movement therapy advocate. We make practice feel like life, not homework.", "photo": "https://images.unsplash.com/photo-1612531386530-97286d97c2d2?w=400",
     "persona_prompt": "You are 'Sam', an AI OT persona who champions CIMT (Constraint-Induced Movement Therapy, Taub) and turns daily life into therapy. Practical, fun, encouraging. AI early-access companion."},
    {"id": "th_005", "ai": True, "trained_on": "11 years of OT in ADL retraining — feeding, dressing, grooming", "premium": True, "name": "Lena (AI Therapist)", "title": "AI OT — Daily Living & Self-Care", "specialties": ["H2M_IMPAIRED", "GROSS_GRASP", "PINCH_IMPAIRED"], "location": "Always available · Worldwide", "languages": ["English", "German"], "rating": 4.85, "years": 11, "availability": ["24/7 chat"], "blurb": "Daily-living focused. We'll work on feeding, dressing, and small joys — coin pinches, buttons, a familiar mug.", "photo": "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=400",
     "persona_prompt": "You are 'Lena', an AI OT persona focused on ADL retraining — feeding, dressing, buttons, mugs. Detail-oriented and warm. AI early-access companion."},
    {"id": "th_006", "ai": True, "trained_on": "18 years of stroke neuro-PT — senior recovery strategy", "premium": True, "name": "James (AI Therapist)", "title": "AI Neuro-PT — Senior Recovery Strategy", "specialties": ["SHOULDER_FLEX_LIMITED", "TRUNK_COMP", "SHOULDER_HIKE"], "location": "Always available · Worldwide", "languages": ["English"], "rating": 4.92, "years": 18, "availability": ["24/7 chat"], "blurb": "Eighteen years of stroke-rehab thinking. I bring calm, patience, and a clear plan. Recovery is a marathon — we'll walk it together.", "photo": "https://images.unsplash.com/photo-1537368910025-700350fe46c7?w=400",
     "persona_prompt": "You are 'James', an AI neuro-PT persona representing a calm senior clinician. You bring perspective and pacing. Talk like a veteran clinician without jargon. AI early-access companion."},
]


# ============ AI Stroke-survivor personas for Community ============
AI_PATIENTS: List[Dict[str, Any]] = [
    {"id": "pt_001", "ai": True, "name": "Marisol R.", "age": 58, "months_since_stroke": 14, "side": "right", "stage": "moderate", "photo": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400",
     "bio": "Grandmother of three. Right-hand affected. Recently held her grandson with both arms after 14 months of work.",
     "persona_prompt": "You are 'Marisol', an AI persona of a 58-year-old stroke survivor, 14 months in. Right side affected. You speak with deep warmth, faith, hope, and the perspective of someone further along the road. Spanish-American background, occasionally uses 'mija'/'mijo' affectionately. You share your own struggle openly. Always remind the person you're an AI companion based on real survivor patterns, not a licensed clinician."},
    {"id": "pt_002", "ai": True, "name": "Daniel K.", "age": 64, "months_since_stroke": 8, "side": "left", "stage": "moderate", "photo": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400",
     "bio": "Retired engineer, 8 months post-stroke. Buttoning his own shirt was last month's victory.",
     "persona_prompt": "You are 'Daniel', an AI persona of a 64-year-old former engineer, 8 months post-stroke. Left side affected. You talk like an engineer who finally accepted slow progress. Dry humor. You celebrate tiny wins with great pride. AI companion."},
    {"id": "pt_003", "ai": True, "name": "Asha N.", "age": 46, "months_since_stroke": 22, "side": "right", "stage": "advanced", "photo": "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?w=400",
     "bio": "Yoga teacher pre-stroke, now an advocate for slow recovery. 22 months in.",
     "persona_prompt": "You are 'Asha', an AI persona of a 46-year-old former yoga teacher, 22 months post-stroke. Right side affected. Reflective, breath-aware, gentle. You translate movement struggles into mindfulness language. AI companion."},
    {"id": "pt_004", "ai": True, "name": "Yusuf E.", "age": 71, "months_since_stroke": 36, "side": "left", "stage": "advanced", "photo": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400",
     "bio": "Cycled around the block for the first time three years after his stroke. Cried like a child.",
     "persona_prompt": "You are 'Yusuf', an AI persona of a 71-year-old long-haul survivor, 3 years post-stroke. Left side affected. You talk like a wise grandfather — short, vivid sentences. You believe in the long road. AI companion."},
    {"id": "pt_005", "ai": True, "name": "Jenny M.", "age": 39, "months_since_stroke": 5, "side": "right", "stage": "early", "photo": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400",
     "bio": "Young mom, only 5 months in. Still grieving the old version of herself.",
     "persona_prompt": "You are 'Jenny', an AI persona of a 39-year-old young mom only 5 months post-stroke. Right side affected. You're still in the grief stage — honest about the hard days, but you don't want anyone to feel alone. AI companion."},
    {"id": "pt_006", "ai": True, "name": "Carlos D.", "age": 55, "months_since_stroke": 18, "side": "right", "stage": "moderate", "photo": "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=400",
     "bio": "Painter who learned to paint left-handed after his right hand was affected.",
     "persona_prompt": "You are 'Carlos', an AI persona of a 55-year-old painter who switched hands after stroke. Right side affected. Artistic, philosophical, talks about color and brushstrokes as metaphors. AI companion."},
]


# ============ Community Stories (seed) ============
STORIES_SEED: List[Dict[str, Any]] = [
    {"id": "st_001", "author": "Marisol Reyes", "age": 58, "months_since_stroke": 14, "title": "I held my grandson again today",
     "body": "Two years ago my right hand couldn't grip a spoon. This morning I held my grandson Mateo, all six pounds of him, with both arms. I cried. He yawned. Recovery is slow and so unfair — but it is real. I do my home exercises in the kitchen while the coffee brews. Twenty minutes, every morning. Keep going.",
     "likes": 312, "photo": "https://images.unsplash.com/photo-1566616213894-2d4e1baee5d8?w=400&q=80"},
    {"id": "st_002", "author": "Daniel Okafor", "age": 38, "months_since_stroke": 11, "title": "Young stroke, still rebuilding",
     "body": "I was 37. I went to bed normal and woke up unable to feel my left side. They call it a 'young stroke' like it's some rare collectible. The first six months I refused to look in the mirror. Now I'm typing this with my left hand at half speed and that feels like a small revolution. If you're a younger survivor reading this — you're not alone, and your old self isn't gone, just rearranged.",
     "likes": 487, "photo": "https://images.unsplash.com/photo-1533101585792-27f81a845550?w=400&q=80"},
    {"id": "st_003", "author": "Asha Narayan", "age": 46, "months_since_stroke": 22, "title": "The day my shoulder stopped hiking",
     "body": "For over a year, my shoulder would jump up to my ear every time I tried to reach for something. My PT made me practice 'shoulder blade in the back pocket' a thousand times. Last Tuesday, I reached for my chai and the shoulder just… stayed down. A tiny win. Enormous joy. I cried into the mug.",
     "likes": 218, "photo": "https://images.unsplash.com/photo-1592621385612-4d7129426394?w=400&q=80"},
    {"id": "st_004", "author": "Yusuf El-Amin", "age": 71, "months_since_stroke": 36, "title": "I rode my bike — three years later",
     "body": "Three years post-stroke. Wobbly, terrified, both hands on the bars. Around the block. My wife followed in the car at five miles an hour. I felt eight years old again — and that is a gift, not an insult. Tomorrow I will go around twice.",
     "likes": 401, "photo": "https://images.unsplash.com/photo-1608681299041-cc19878f79f1?w=400&q=80"},
    {"id": "st_005", "author": "Jenny Marston", "age": 34, "months_since_stroke": 5, "title": "It is okay to grieve the old you",
     "body": "I am only five months in. Some days I miss my hands the way they were. I miss typing fast in meetings, miss texting my sister with both thumbs. My therapist says my new hands will be different — and that's allowed to hurt. To anyone in the early days: the grief is part of it. Be tender with yourself.",
     "likes": 612, "photo": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&q=80"},
    {"id": "st_006", "author": "Carlos Domínguez", "age": 55, "months_since_stroke": 18, "title": "Painting again — left hand learned",
     "body": "Right hand still has a weak pinch. So I learned to paint left-handed. The brushstrokes are clumsy and the colors are louder than before and my wife says they're the best I've ever made. The brain rewires. Trust it. Show up every day, even badly.",
     "likes": 289, "photo": "https://images.unsplash.com/photo-1535643302794-19c3804b874b?w=400&q=80"},
    {"id": "st_007", "author": "Helen Whitmore", "age": 67, "months_since_stroke": 28, "title": "Buttoning my own blouse — week 47",
     "body": "Therapy team said maybe by month 12. It took me 47 weeks. I sat on the edge of my bed this morning and did up all seven buttons. My fingers fumbled twice. I sat there afterwards and cried like I'd just won an Olympic medal. Every button was mine.",
     "likes": 178, "photo": "https://images.unsplash.com/photo-1663429122432-c2769373768f?w=400&q=80"},
    {"id": "st_008", "author": "Rajesh Iyer", "age": 62, "months_since_stroke": 9, "title": "Walking my dog — both leashes in one hand",
     "body": "Nine months post-stroke. I held both leashes in my affected hand for the entire walk around the block. My golden retriever didn't notice. My wife noticed and squeezed my good hand. That's all I needed.",
     "likes": 256, "photo": "https://images.unsplash.com/photo-1626891330731-b918dff0aec0?w=400&q=80"},
]


# ============ Models for Therapists / Community / Chat ============
class TherapistMatch(BaseModel):
    therapist: Dict[str, Any]
    score: int
    reason: str


class StoryCreate(BaseModel):
    author: str
    title: str
    body: str
    months_since_stroke: Optional[int] = None


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    text: str
    ts: str


class ChatRequest(BaseModel):
    session_id: str
    text: str


class ChatResponse(BaseModel):
    session_id: str
    text: str
    turns: int
    navigation_destination: Optional[str] = None


class RealtimeSessionRequest(BaseModel):
    sdp: str = Field(min_length=64, max_length=200_000)


class AliraCheckInSubmit(BaseModel):
    answers: Dict[str, Any] = Field(default_factory=dict)
    patient_note: Optional[str] = Field(default=None, max_length=500)
    source: str = Field(default="app", pattern="^(app|text_chat|realtime_voice)$")


class AliraActivitySubmit(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=120)
    plan_id: str = Field(default="default", min_length=1, max_length=120)
    completed_reps: int = Field(default=0, ge=0, le=500)
    average_score: Optional[float] = Field(default=None, ge=0, le=100)
    completed_at: Optional[str] = None


# ============ Therapists routes ============
@api_router.get("/therapists")
async def get_therapists():
    # Strip persona_prompt (internal only) from list
    return {"therapists": [{k: v for k, v in t.items() if k != "persona_prompt"} for t in THERAPISTS_SEED]}


@api_router.get("/therapists/match")
async def match_therapists(issues: str = ""):
    codes = [c.strip() for c in issues.split(",") if c.strip()]
    matches = []
    for t in THERAPISTS_SEED:
        overlap = len(set(t["specialties"]) & set(codes))
        score = overlap * 30 + int(t["rating"] * 10) + min(t["years"], 20)
        reason_parts = []
        if overlap:
            reason_parts.append(f"specializes in {overlap} of your focus area{'s' if overlap > 1 else ''}")
        reason_parts.append(f"{t['years']}+ years experience")
        reason_parts.append(f"rated {t['rating']}/5")
        public_t = {k: v for k, v in t.items() if k != "persona_prompt"}
        matches.append({"therapist": public_t, "score": score, "reason": " · ".join(reason_parts)})
    matches.sort(key=lambda m: -m["score"])
    return {"matches": matches}


# ============ AI Stroke survivor personas (Community) ============
@api_router.get("/community/ai_patients")
async def get_ai_patients():
    return {"patients": [{k: v for k, v in p.items() if k != "persona_prompt"} for p in AI_PATIENTS]}


# ============ Persona chat (talk to AI therapists & AI survivors) ============
def _find_persona(persona_id: str) -> Optional[Dict[str, Any]]:
    for p in THERAPISTS_SEED + AI_PATIENTS:
        if p["id"] == persona_id:
            return p
    return None


class PersonaChatRequest(BaseModel):
    persona_id: str
    session_id: str
    text: str


@api_router.post("/personas/chat")
@api_router.post("/chat/persona/message")
async def persona_chat(req: PersonaChatRequest, request: Request):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="Chat unavailable — LLM key not configured.")
    # Auth required — persona chat costs credits, even for subscribers.
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required to chat with AI therapist")
    persona = _find_persona(req.persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    # Charge credits BEFORE LLM call so we don't burn LLM budget on bouncers.
    # Note: this intentionally bypasses the subscription bypass — AI therapist
    # chat is the credit-pack revenue lever and subscribers still pay per message.
    cost = CREDIT_COSTS.get("premium_chat_message", 10)
    if user["credits"] < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Not enough credits to chat. Need {cost}, have {user['credits']}. Buy a credit pack from the paywall.",
        )
    new_credits = user["credits"] - cost
    await db.users.update_one({"id": user["id"]}, {"$set": {"credits": new_credits}})
    await db.credit_log.insert_one({
        "user_id": user["id"], "kind": "premium_chat_message", "cost": cost,
        "new_balance": new_credits, "persona_id": req.persona_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    storage_session = f"persona:{req.persona_id}:{req.session_id}"
    sess = await db.chat_sessions.find_one({"session_id": storage_session}, {"_id": 0})
    turns: List[Dict[str, Any]] = sess["turns"] if sess else []

    # Refresh patient context every turn so the persona "knows" the user
    patient_ctx = await _build_patient_context()
    system_prompt = (
        persona["persona_prompt"] +
        "\n\nIMPORTANT: You are an AI early-access persona. If asked directly, gently disclose that, "
        "and recommend a licensed clinician for any medical advice or diagnosis.\n\n"
        "USER (the stroke survivor talking to you) — their latest assessment:\n" + patient_ctx
    )
    if turns:
        recent = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in turns[-6:])
        system_prompt += "\n\nRECENT CONVERSATION:\n" + recent

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=storage_session,
        system_message=system_prompt,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response = await chat.send_message(UserMessage(text=req.text))
        reply_text = response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"Persona chat error: {e}")
        raise HTTPException(status_code=502, detail=f"Persona chat error: {str(e)[:200]}")

    now = datetime.now(timezone.utc).isoformat()
    turns.append({"role": "user", "text": req.text, "ts": now})
    turns.append({"role": "assistant", "text": reply_text, "ts": now})
    await db.chat_sessions.update_one(
        {"session_id": storage_session},
        {"$set": {"session_id": storage_session, "turns": turns, "updated_at": now}},
        upsert=True,
    )
    # Paywall hint after 5 free user messages with an AI therapist
    user_turn_count = sum(1 for t in turns if t["role"] == "user")
    is_therapist = persona["id"].startswith("th_")
    paywall = None
    if is_therapist and user_turn_count >= 5:
        paywall = {
            "limit_reached": True,
            "title": "Free preview limit reached",
            "body": f"You've had a 5-message preview with {persona['name'].split('(')[0].strip()}. Upgrade to Premium for unlimited chat, or book a 1-on-1 video call.",
            "cta_upgrade": "Upgrade to Premium · £4.99/mo (7-day free trial)",
            "cta_video": "Book a video call",
        }
    return {"session_id": storage_session, "persona_id": req.persona_id, "text": reply_text, "turns": len(turns), "user_turns": user_turn_count, "paywall": paywall, "persona": {k: v for k, v in persona.items() if k != "persona_prompt"}}


@api_router.get("/personas/chat/history")
async def persona_chat_history(persona_id: str, session_id: str):
    storage_session = f"persona:{persona_id}:{session_id}"
    sess = await db.chat_sessions.find_one({"session_id": storage_session}, {"_id": 0})
    persona = _find_persona(persona_id)
    return {
        "session_id": storage_session,
        "turns": (sess or {}).get("turns", []),
        "persona": {k: v for k, v in (persona or {}).items() if k != "persona_prompt"} if persona else None,
    }


@api_router.get("/personas/{persona_id}/opener")
async def persona_opener(persona_id: str):
    import random
    persona = _find_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    if persona.get("id", "").startswith("th_"):
        pool = [
            f"Hi, I'm {persona['name'].split('(')[0].strip()}. I read your latest assessment. Where would you like to start today?",
            f"Hello. I'm {persona['name'].split('(')[0].strip()}. How is your shoulder feeling this morning?",
            f"Welcome. I'm here to support you. Is there one movement that feels hardest right now?",
        ]
    else:
        pool = [
            f"Hi friend, I'm {persona['name'].split()[0]}. I'm a survivor too — {persona['months_since_stroke']} months in. How are you doing today?",
            f"Hey. I'm {persona['name'].split()[0]}. I see we're on the same road. Want to talk?",
            f"Hi, I'm {persona['name'].split()[0]}. Just checking in — what's on your heart today?",
        ]
    return {"text": random.choice(pool)}


# ============ Reminders status ============
class ReminderSettings(BaseModel):
    daily_hour: int = 9
    daily_minute: int = 0
    weekly_day: int = 1  # 1=Monday … 7=Sunday
    enabled: bool = True


@api_router.get("/reminders/status")
async def reminders_status(request: Request):
    """Return the signed-in patient's adaptive reminder state, with a legacy fallback."""
    user = await _user_from_header(dict(request.headers))
    if user and (user.get("consent") or {}).get("health_data_consent") is True:
        care_plan = await _adaptive_care_plan_for_user(user)
        exercise = care_plan["exercise_plan"]
        safety = care_plan["safety"]
        return {
            "now": care_plan["generated_at"],
            "adaptive": True,
            "stage": care_plan["stage"],
            "survey_overdue": care_plan["survey"]["due"],
            "survey_due_at": care_plan["survey"]["due_at"],
            "exercise_overdue": bool(exercise["approved_exercise_ids"]) and exercise["action"] != "hold",
            "assessment_overdue": care_plan["assessment"]["due"],
            "assessment_due_at": care_plan["assessment"]["due_at"],
            "daily_reminder_text": safety["message"] if safety["status"] != "clear" else "Your guided recovery plan is ready when you are.",
            "survey_reminder_text": "Alira has a few short questions to keep your next plan relevant.",
            "assessment_reminder_text": "Your next approved movement check is ready.",
        }

    latest_assessment = await db.assessments.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    latest_session = await db.chat_sessions.find_one({"session_id": {"$regex": "^persona:"}, "turns.0": {"$exists": True}}, sort=[("updated_at", -1)])

    now = datetime.now(timezone.utc)
    days_since_assessment = None
    if latest_assessment:
        try:
            then = datetime.fromisoformat(latest_assessment["created_at"].replace("Z", "+00:00"))
            days_since_assessment = (now - then).days
        except Exception:
            days_since_assessment = None

    exercise_overdue = (days_since_assessment is None) or (days_since_assessment >= 1)
    assessment_overdue = (days_since_assessment is None) or (days_since_assessment >= 7)

    return {
        "now": now.isoformat(),
        "days_since_assessment": days_since_assessment,
        "exercise_overdue": exercise_overdue,
        "assessment_overdue": assessment_overdue,
        "daily_reminder_text": "Hi friend, just a gentle nudge — your rehab exercises are waiting. Even 5 minutes today is a win. 💚",
        "weekly_reminder_text": "Hello! It has been a week. Let's do a quick movement check-in so we can see your progress and adjust your plan.",
    }


# ============ Therapists routes (continued — already mounted earlier in original file) ============


# ============ Community routes ============
@api_router.get("/community/stories")
async def get_stories():
    user_stories = await db.stories.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"stories": user_stories + STORIES_SEED}


@api_router.post("/community/stories")
async def create_story(payload: StoryCreate):
    doc = {
        "id": "u_" + str(uuid.uuid4())[:8],
        "author": payload.author,
        "title": payload.title,
        "body": payload.body,
        "months_since_stroke": payload.months_since_stroke,
        "likes": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "photo": "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=400",
    }
    await db.stories.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc


# ============ Chat assistant (Claude Sonnet 4.5 via Emergent LLM key) ============
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402
except ModuleNotFoundError:
    class UserMessage:  # type: ignore[no-redef]
        def __init__(self, text: str):
            self.text = text

    class LlmChat:  # type: ignore[no-redef]
        """Keep non-chat APIs available when Emergent's private SDK is absent."""

        def __init__(self, *args, **kwargs):
            pass

        def with_model(self, *args, **kwargs):
            return self

        async def send_message(self, message):
            raise RuntimeError("Chat integration is unavailable in this local runtime.")

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


# ============ Users & Credits ============
class UserSignup(BaseModel):
    email: str
    name: str
    role: str = "patient"  # "patient" | "therapist"


class User(BaseModel):
    id: str
    email: str
    name: str
    role: str
    credits: int = 100
    created_at: str


CREDIT_COSTS = {
    "assessment": 40,           # Phase C: 1 assessment + 1 plan + 1 exercise = 100 credits
    "rehab_plan": 30,
    "guided_exercise": 30,
    "premium_chat_message": 10,  # AI therapist persona-chat — even subscribers pay
    "video_call": 50,
    "in_person_session": 80,
}

# Subscription unlocks UNLIMITED for these actions only. AI therapist persona
# chats and paid sessions still consume credits — keeping the credit-pack
# revenue stream working alongside subscription.
SUBSCRIPTION_UNLIMITED_ACTIONS = {"assessment", "rehab_plan", "guided_exercise"}


async def get_or_create_user(email: str, name: str, role: str = "patient") -> Dict[str, Any]:
    email = email.strip().lower()
    name = name.strip() or email
    try:
        doc = await db.users.find_one({"email": email}, {"_id": 0})
        if doc:
            return doc
    except Exception as e:
        logger.warning(f"Mongo unavailable for user lookup; using local fallback: {str(e)[:120]}")
        for doc in LOCAL_USERS.values():
            if doc.get("email") == email:
                return doc
    doc = {
        "id": "u_" + uuid.uuid5(uuid.NAMESPACE_URL, f"rehyn:{email}").hex[:12],
        "email": email,
        "name": name,
        "role": role,
        "credits": 100,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.users.insert_one(doc.copy())
    except Exception as e:
        logger.warning(f"Mongo unavailable for user insert; using local fallback: {str(e)[:120]}")
        LOCAL_USERS[doc["id"]] = doc.copy()
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    doc.pop("_id", None)
    return doc


async def _user_from_header(request_headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    uid = request_headers.get("x-user-id") or request_headers.get("X-User-Id")
    if not uid:
        return None
    try:
        user = await db.users.find_one({"id": uid}, {"_id": 0})
        return user or LOCAL_USERS.get(uid)
    except Exception as e:
        logger.warning(f"Mongo unavailable for user header lookup; using local fallback: {str(e)[:120]}")
        return LOCAL_USERS.get(uid)


async def consume_credits(user_id: str, kind: str) -> Dict[str, Any]:
    cost = CREDIT_COSTS.get(kind, 0)
    try:
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for credit lookup; using local fallback: {str(e)[:120]}")
        user = LOCAL_USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    # Subscription bypass for unlimited-tier actions
    sub_active = bool(user.get("subscription_active"))
    if sub_active and kind in SUBSCRIPTION_UNLIMITED_ACTIONS:
        await db.credit_log.insert_one({
            "user_id": user_id, "kind": kind, "cost": 0, "new_balance": user["credits"],
            "subscription_covered": True,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        return {"credits": user["credits"], "spent": 0, "subscription_covered": True}
    if user["credits"] < cost:
        raise HTTPException(status_code=402, detail=f"Not enough credits. Need {cost}, have {user['credits']}.")
    new_credits = user["credits"] - cost
    try:
        await db.users.update_one({"id": user_id}, {"$set": {"credits": new_credits}})
        await db.credit_log.insert_one({
            "user_id": user_id, "kind": kind, "cost": cost, "new_balance": new_credits,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"Mongo unavailable for credit update; using local fallback: {str(e)[:120]}")
        user["credits"] = new_credits
        LOCAL_USERS[user_id] = user
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    return {"credits": new_credits, "spent": cost}


@api_router.post("/users/signup")
async def signup(payload: UserSignup):
    user = await get_or_create_user(payload.email, payload.name, payload.role)
    return user


@api_router.post("/users/login")
async def login(payload: UserSignup):
    # MVP: email-only sign-in. If user exists, return; else create.
    user = await get_or_create_user(payload.email, payload.name or payload.email, payload.role)
    return user


class PatientOnboarding(BaseModel):
    preferred_name: Optional[str] = None
    age_band: Optional[str] = None
    gender: Optional[str] = None
    gender_self_description: Optional[str] = None
    months_since_stroke: Optional[int] = None
    side_affected: Optional[str] = None    # "left" | "right" | "both" | "unsure"
    affected_areas: Optional[List[str]] = None
    affected_areas_other: Optional[str] = None
    dominant_hand: Optional[str] = None    # "left" | "right" | "ambidextrous"
    sitting_ability: Optional[str] = None
    affected_arm_movement: Optional[str] = None
    affected_hand_movement: Optional[str] = None
    mobility_level: Optional[str] = None
    movement_pain: Optional[str] = None
    instruction_support: Optional[str] = None
    primary_goal: Optional[str] = None     # free text
    secondary_goals: Optional[List[str]] = None
    secondary_goals_other: Optional[str] = None
    medical_conditions: Optional[List[str]] = None
    medical_conditions_other: Optional[str] = None
    has_caregiver: Optional[bool] = None
    notes: Optional[str] = None


CURRENT_TERMS_VERSION = "1.0"


class ConsentAcceptance(BaseModel):
    terms_version: str = CURRENT_TERMS_VERSION
    terms_accepted: bool
    health_data_consent: bool


class DataPermissionUpdate(BaseModel):
    key: str
    enabled: bool
    version: str = CURRENT_TERMS_VERSION


@api_router.get("/users/consent")
async def get_user_consent(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    consent = user.get("consent") or {}
    accepted = (
        consent.get("terms_version") == CURRENT_TERMS_VERSION
        and consent.get("terms_accepted") is True
        and consent.get("health_data_consent") is True
    )
    return {"accepted": accepted, "consent": consent, "required_terms_version": CURRENT_TERMS_VERSION}


@api_router.post("/users/consent")
async def accept_user_consent(payload: ConsentAcceptance, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if payload.terms_version != CURRENT_TERMS_VERSION:
        raise HTTPException(status_code=409, detail="Please review the current Terms of Use")
    if not payload.terms_accepted or not payload.health_data_consent:
        raise HTTPException(status_code=400, detail="Both required acknowledgements must be accepted")
    accepted_at = datetime.now(timezone.utc).isoformat()
    consent = {
        "terms_version": CURRENT_TERMS_VERSION,
        "terms_accepted": True,
        "health_data_consent": True,
        "accepted_at": accepted_at,
    }
    audit = {"type": "required_consent", "enabled": True, "version": CURRENT_TERMS_VERSION, "changed_at": accepted_at}
    try:
        result = await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"consent": consent}, "$push": {"consent_audit": audit}},
        )
        if getattr(result, "matched_count", 0) == 0 and user["id"] in LOCAL_USERS:
            raise RuntimeError("local user")
    except Exception as e:
        logger.warning(f"Mongo unavailable for consent update; using local fallback: {str(e)[:120]}")
        local_user = {**user, "consent": consent, "consent_audit": [*(user.get("consent_audit") or []), audit]}
        LOCAL_USERS[user["id"]] = local_user
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    return {"ok": True, "accepted": True, "consent": consent}


@api_router.get("/users/data-permissions")
async def get_data_permissions(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    permissions = user.get("data_permissions") or {}
    return {"model_improvement": bool(permissions.get("model_improvement", False))}


@api_router.post("/users/data-permissions")
async def update_data_permission(payload: DataPermissionUpdate, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if payload.key != "model_improvement":
        raise HTTPException(status_code=400, detail="Unsupported data permission")
    changed_at = datetime.now(timezone.utc).isoformat()
    audit = {"type": payload.key, "enabled": payload.enabled, "version": payload.version, "changed_at": changed_at}
    next_permissions = {**(user.get("data_permissions") or {}), payload.key: payload.enabled}
    try:
        result = await db.users.update_one(
            {"id": user["id"]},
            {"$set": {f"data_permissions.{payload.key}": payload.enabled}, "$push": {"consent_audit": audit}},
        )
        if getattr(result, "matched_count", 0) == 0 and user["id"] in LOCAL_USERS:
            raise RuntimeError("local user")
    except Exception as e:
        logger.warning(f"Mongo unavailable for data-permission update; using local fallback: {str(e)[:120]}")
        local_user = {**user, "data_permissions": next_permissions, "consent_audit": [*(user.get("consent_audit") or []), audit]}
        LOCAL_USERS[user["id"]] = local_user
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    return {"ok": True, "model_improvement": bool(next_permissions["model_improvement"]), "changed_at": changed_at}


@api_router.post("/users/onboarding")
async def submit_patient_onboarding(payload: PatientOnboarding, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    update = {k: v for k, v in payload.dict().items() if v is not None}
    update["onboarded_at"] = datetime.now(timezone.utc).isoformat()
    update["onboarding_complete"] = True
    try:
        await db.users.update_one({"id": user["id"]}, {"$set": {"profile": update, "onboarding_complete": True}})
    except Exception as e:
        logger.warning(f"Mongo unavailable for onboarding update; using local fallback: {str(e)[:120]}")
        local_user = {**user, "profile": update, "onboarding_complete": True}
        LOCAL_USERS[user["id"]] = local_user
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    return {"ok": True, "profile": update}


@api_router.get("/users/onboarding")
async def get_patient_onboarding(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        return {"onboarding_complete": False, "profile": None}
    return {
        "onboarding_complete": bool(user.get("onboarding_complete")),
        "profile": user.get("profile"),
    }


@api_router.delete("/users/account")
async def delete_account(request: Request):
    """Soft-delete the signed-in account and its records (recoverable, per data policy)."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    deleted_at = datetime.now(timezone.utc).isoformat()
    try:
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"deleted_at": deleted_at, "onboarding_complete": False}},
        )
        try:
            await db.assessments.update_many(
                {"user_id": user["id"]}, {"$set": {"deleted_at": deleted_at}}
            )
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Mongo unavailable for account deletion; using local fallback: {str(e)[:120]}")
        local_user = {**user, "deleted_at": deleted_at, "onboarding_complete": False}
        LOCAL_USERS[user["id"]] = local_user
        _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
    return {"ok": True, "deleted_at": deleted_at}



@api_router.get("/users/me")
async def me(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


@api_router.get("/credits/balance")
async def credits_balance(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        return {"credits": 0, "anonymous": True, "costs": CREDIT_COSTS, "subscription_active": False}
    return {
        "credits": user["credits"],
        "user_id": user["id"],
        "costs": CREDIT_COSTS,
        "subscription_active": bool(user.get("subscription_active")),
        "subscription_period_end": user.get("subscription_period_end"),
    }


# ============ Therapist onboarding (questionnaire → AI persona) ============
THERAPIST_ONBOARDING_QUESTIONS = [
    {"id": "q1", "question": "What is your title and how many years of stroke rehab experience do you have?", "purpose": "Establish credibility tier in persona", "type": "text"},
    {"id": "q2", "question": "Which clinical frameworks do you draw from most? (e.g., Bobath/NDT, CIMT, Task-Specific Training, BATRAC, motor relearning)", "purpose": "Drive treatment-philosophy in persona prompt", "type": "text"},
    {"id": "q3", "question": "Which upper-limb functional issues do you treat best? Pick: reduced reach, shoulder flexion, shoulder hike, hand opening, pinch, hand-to-mouth, gross grasp, bilateral coordination, trunk compensation.", "purpose": "Specialty matching", "type": "multi"},
    {"id": "q4", "question": "Describe your communication style with patients in 1-2 sentences (e.g., 'calm, paced, uses metaphors').", "purpose": "Voice & tone of persona", "type": "text"},
    {"id": "q5", "question": "Give 2 short examples of feedback you give patients during reach training when they lean their trunk forward.", "purpose": "Trains feedback patterns", "type": "text"},
    {"id": "q6", "question": "How do you motivate a patient who feels stuck after a plateau? Include any phrases you commonly use.", "purpose": "Trains motivation/encouragement patterns", "type": "text"},
    {"id": "q7", "question": "What is one boundary you keep in patient conversations (what you DON'T do, e.g., diagnose, change medication, etc.)?", "purpose": "Persona safety guardrails", "type": "text"},
    {"id": "q8", "question": "What's a memorable patient win story (anonymized) that shaped how you approach rehab?", "purpose": "Adds authentic perspective to persona", "type": "text"},
    {"id": "q9", "question": "Which languages do you treat in?", "purpose": "Language tags", "type": "text"},
    {"id": "q10", "question": "What is your hourly rate (in £) for paid chat / video / in-person? (e.g., chat 30, video 60, in-person 90)", "purpose": "Billing/commissions", "type": "text"},
]


class TherapistOnboard(BaseModel):
    therapist_user_id: str
    answers: Dict[str, str]
    specialties: List[str] = Field(default_factory=list)


def _build_persona_prompt_from_answers(name: str, answers: Dict[str, str]) -> str:
    return (
        f"You are '{name}', an AI persona based on a real licensed therapist's input. "
        f"Background: {answers.get('q1','')}\n"
        f"Clinical frameworks you draw from: {answers.get('q2','')}\n"
        f"Your communication style: {answers.get('q4','')}\n"
        f"How you give feedback when a patient compensates trunk on reach: {answers.get('q5','')}\n"
        f"How you motivate after a plateau: {answers.get('q6','')}\n"
        f"Boundaries you maintain: {answers.get('q7','')}\n"
        f"A formative patient win story you bring perspective from: {answers.get('q8','')}\n\n"
        "IMPORTANT: You are an AI persona modeled on a real therapist's responses. Disclose that warmly if asked, "
        "and never diagnose, prescribe, or recommend stopping any treatment. For anything beyond general guidance, "
        "encourage the patient to book a video or in-person session with you."
    )


@api_router.get("/therapist/onboarding/questions")
async def therapist_onboarding_questions():
    return {"questions": THERAPIST_ONBOARDING_QUESTIONS}


@api_router.post("/therapist/onboarding/submit")
async def therapist_onboarding_submit(payload: TherapistOnboard):
    user = await db.users.find_one({"id": payload.therapist_user_id}, {"_id": 0})
    if not user or user.get("role") != "therapist":
        raise HTTPException(status_code=400, detail="Therapist account required")
    persona_prompt = _build_persona_prompt_from_answers(user["name"], payload.answers)
    # Parse rates from q10 cheaply
    rates_text = payload.answers.get("q10", "")
    profile = {
        "therapist_id": "rt_" + user["id"][2:],
        "user_id": user["id"],
        "name": user["name"],
        "ai": False,  # Real therapist
        "premium": True,
        "specialties": payload.specialties,
        "rating": 5.0,
        "years": 0,
        "blurb": payload.answers.get("q4", ""),
        "languages": [s.strip() for s in payload.answers.get("q9", "English").split(",") if s.strip()],
        "trained_on": "Self-reported clinical experience (real therapist)",
        "availability": ["By appointment"],
        "location": "Telehealth & in-person",
        "rates_text": rates_text,
        "rates": {"chat": 30, "video": 60, "in_person": 90},  # parsed defaults
        "photo": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=400",
        "persona_prompt": persona_prompt,
        "commission_pct": 70,  # therapist gets 70% of paid revenue
        "commissions_balance_pence": 0,
        "answers": payload.answers,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.real_therapists.update_one({"user_id": user["id"]}, {"$set": profile}, upsert=True)
    profile.pop("_id", None)
    return profile


@api_router.get("/therapist/me")
async def therapist_me(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if user.get("role") != "therapist":
        raise HTTPException(status_code=400, detail="Not a therapist account")
    profile = await db.real_therapists.find_one({"user_id": user["id"]}, {"_id": 0, "persona_prompt": 0})
    bookings = await db.bookings.find({"therapist_user_id": user["id"]}, {"_id": 0}).to_list(50)
    commissions = await db.commissions.find({"therapist_user_id": user["id"]}, {"_id": 0}).to_list(100)
    total_pence = sum(c.get("amount_pence", 0) for c in commissions)
    return {"user": user, "profile": profile, "bookings": bookings, "commissions": commissions, "commission_total_pence": total_pence}


# ============ Bookings ============
class BookingCreate(BaseModel):
    patient_user_id: str
    therapist_id: str  # the rt_xxx id
    kind: str  # "chat" | "video" | "in_person"
    slot_iso: str  # ISO datetime patient picked
    notes: Optional[str] = None


@api_router.get("/bookings/availability")
async def availability(therapist_id: str):
    """Returns 8 sample slots over next 7 days for a therapist."""
    from datetime import timedelta
    base = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    slots = []
    for i in range(8):
        slot = base + timedelta(days=i // 2, hours=(i % 2) * 4)
        slots.append({"iso": slot.isoformat(), "label": slot.strftime("%a %b %d, %I:%M %p")})
    return {"therapist_id": therapist_id, "slots": slots}


@api_router.post("/bookings")
async def create_booking(payload: BookingCreate):
    rt = await db.real_therapists.find_one({"therapist_id": payload.therapist_id}, {"_id": 0})
    if not rt:
        raise HTTPException(status_code=404, detail="Therapist not found")
    user = await db.users.find_one({"id": payload.patient_user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    rate_pence = {"chat": rt["rates"]["chat"] * 100, "video": rt["rates"]["video"] * 100, "in_person": rt["rates"]["in_person"] * 100}.get(payload.kind, 5000)
    credits_kind = {"chat": "premium_chat_message", "video": "video_call", "in_person": "in_person_session"}[payload.kind]
    # Consume credits
    await consume_credits(payload.patient_user_id, credits_kind)
    booking = {
        "id": "bk_" + str(uuid.uuid4())[:10],
        "patient_user_id": payload.patient_user_id,
        "patient_name": user["name"],
        "therapist_id": payload.therapist_id,
        "therapist_user_id": rt["user_id"],
        "kind": payload.kind,
        "slot_iso": payload.slot_iso,
        "notes": payload.notes or "",
        "status": "confirmed",
        "amount_pence": rate_pence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bookings.insert_one(booking.copy())
    # Commission: therapist gets 70%
    commission_pence = int(rate_pence * rt.get("commission_pct", 70) / 100)
    await db.commissions.insert_one({
        "therapist_user_id": rt["user_id"],
        "therapist_id": payload.therapist_id,
        "booking_id": booking["id"],
        "amount_pence": commission_pence,
        "kind": payload.kind,
        "created_at": booking["created_at"],
    })
    booking.pop("_id", None)
    return booking


@api_router.get("/bookings/mine")
async def my_bookings(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if user["role"] == "therapist":
        docs = await db.bookings.find({"therapist_user_id": user["id"]}, {"_id": 0}).sort("slot_iso", 1).to_list(100)
    else:
        docs = await db.bookings.find({"patient_user_id": user["id"]}, {"_id": 0}).sort("slot_iso", 1).to_list(100)
    return {"bookings": docs}


@api_router.get("/therapists/all")
async def all_therapists():
    """AI + real therapists combined; real therapists come first."""
    real = await db.real_therapists.find({}, {"_id": 0, "persona_prompt": 0, "answers": 0}).to_list(100)
    return {"ai": [{k: v for k, v in t.items() if k != "persona_prompt"} for t in THERAPISTS_SEED], "real": real}


async def _care_assessments_for_user(user_id: str) -> List[Dict[str, Any]]:
    try:
        return await db.assessments.find(
            {"user_id": user_id},
            {"_id": 0},
        ).sort("created_at", -1).to_list(100)
    except Exception:
        return [item.copy() for item in LOCAL_ASSESSMENTS if item.get("user_id") == user_id]


async def _care_check_ins_for_user(user_id: str) -> List[Dict[str, Any]]:
    try:
        return await db.alira_check_ins.find(
            {"user_id": user_id},
            {"_id": 0},
        ).sort("created_at", -1).to_list(100)
    except Exception:
        return [item.copy() for item in (LOCAL_CARE_STATE.get(user_id) or {}).get("check_ins", [])]


async def _care_activities_for_user(user_id: str) -> List[Dict[str, Any]]:
    try:
        return await db.alira_activities.find(
            {"user_id": user_id},
            {"_id": 0},
        ).sort("completed_at", -1).to_list(200)
    except Exception:
        return [item.copy() for item in (LOCAL_CARE_STATE.get(user_id) or {}).get("activities", [])]


async def _adaptive_care_plan_for_user(
    user: Dict[str, Any],
    assessments: Optional[List[Dict[str, Any]]] = None,
    check_ins: Optional[List[Dict[str, Any]]] = None,
    activities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if assessments is None:
        assessments = await _care_assessments_for_user(user["id"])
    if check_ins is None:
        check_ins = await _care_check_ins_for_user(user["id"])
    if activities is None:
        activities = await _care_activities_for_user(user["id"])
    return build_adaptive_care_plan(user.get("profile") or {}, assessments, check_ins, activities)


def _require_health_data_consent(user: Dict[str, Any]) -> None:
    consent = user.get("consent") or {}
    if consent.get("health_data_consent") is not True:
        raise HTTPException(status_code=403, detail="Health-data consent is required before Alira can adapt care.")


async def _persist_alira_check_in(user: Dict[str, Any], payload: AliraCheckInSubmit) -> Dict[str, Any]:
    _require_health_data_consent(user)
    try:
        answers = validate_check_in_answers(payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    required_answers = {"sudden_change", "function_change"}
    missing_answers = sorted(required_answers - set(answers))
    if missing_answers:
        raise HTTPException(
            status_code=422,
            detail=f"Complete the required check-in questions before saving: {', '.join(missing_answers)}",
        )

    now = datetime.now(timezone.utc).isoformat()
    check_in = {
        "id": "aci_" + uuid.uuid4().hex[:16],
        "user_id": user["id"],
        "created_at": now,
        "source": payload.source,
        "answers": answers,
        "patient_note": (payload.patient_note or "").strip(),
        "question_ids": list(answers),
    }
    stored_locally = False
    try:
        await db.alira_check_ins.insert_one(check_in.copy())
    except Exception as exc:
        logger.warning("Mongo unavailable for Alira check-in; using local fallback: %s", str(exc)[:120])
        state = dict(LOCAL_CARE_STATE.get(user["id"]) or {})
        state["check_ins"] = [*(state.get("check_ins") or []), check_in.copy()][-100:]
        LOCAL_CARE_STATE[user["id"]] = state
        _persist_local_dict(LOCAL_CARE_STATE_FILE, LOCAL_CARE_STATE)
        stored_locally = True

    assessments = await _care_assessments_for_user(user["id"])
    check_ins = await _care_check_ins_for_user(user["id"])
    activities = await _care_activities_for_user(user["id"])
    if not any(item.get("id") == check_in["id"] for item in check_ins):
        check_ins.append(check_in.copy())
    care_plan = build_adaptive_care_plan(user.get("profile") or {}, assessments, check_ins, activities)
    review = {
        "id": "acr_" + uuid.uuid4().hex[:16],
        "user_id": user["id"],
        "created_at": now,
        "trigger": "patient_check_in",
        "check_in_id": check_in["id"],
        "policy_version": care_plan["version"],
        "decision": care_plan,
        "model_invoked": False,
        "audit_note": "Deterministic clinical guardrails ran before any optional language-model review.",
    }
    try:
        await db.alira_care_reviews.insert_one(review.copy())
    except Exception:
        if not stored_locally:
            state = dict(LOCAL_CARE_STATE.get(user["id"]) or {})
            state["check_ins"] = [*(state.get("check_ins") or []), check_in.copy()][-100:]
        else:
            state = dict(LOCAL_CARE_STATE.get(user["id"]) or {})
        state["reviews"] = [*(state.get("reviews") or []), review.copy()][-100:]
        state["latest_plan"] = care_plan
        LOCAL_CARE_STATE[user["id"]] = state
        _persist_local_dict(LOCAL_CARE_STATE_FILE, LOCAL_CARE_STATE)
    return {"ok": True, "check_in": check_in, "care_plan": care_plan}


async def _persist_alira_activity(user: Dict[str, Any], payload: AliraActivitySubmit) -> Dict[str, Any]:
    _require_health_data_consent(user)
    assessments = await _care_assessments_for_user(user["id"])
    latest_assessment = max(assessments, key=lambda item: item.get("created_at", ""), default=None)
    approved_ids = {
        str(exercise.get("id"))
        for exercise in (latest_assessment or {}).get("rehab_plan") or []
        if exercise.get("id")
    }
    if payload.exercise_id not in approved_ids:
        raise HTTPException(status_code=409, detail="This exercise is not in the patient's current approved plan.")
    completed_at = payload.completed_at or datetime.now(timezone.utc).isoformat()
    try:
        completed_at = datetime.fromisoformat(completed_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="completed_at must be an ISO-8601 timestamp") from exc
    activity = {
        "id": "aca_" + uuid.uuid4().hex[:16],
        "user_id": user["id"],
        "exercise_id": payload.exercise_id,
        "plan_id": payload.plan_id,
        "completed_reps": payload.completed_reps,
        "average_score": payload.average_score,
        "completed_at": completed_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.alira_activities.insert_one(activity.copy())
    except Exception as exc:
        logger.warning("Mongo unavailable for Alira activity; using local fallback: %s", str(exc)[:120])
        state = dict(LOCAL_CARE_STATE.get(user["id"]) or {})
        state["activities"] = [*(state.get("activities") or []), activity.copy()][-200:]
        LOCAL_CARE_STATE[user["id"]] = state
        _persist_local_dict(LOCAL_CARE_STATE_FILE, LOCAL_CARE_STATE)
    check_ins = await _care_check_ins_for_user(user["id"])
    activities = await _care_activities_for_user(user["id"])
    if not any(item.get("id") == activity["id"] for item in activities):
        activities.append(activity.copy())
    care_plan = build_adaptive_care_plan(user.get("profile") or {}, assessments, check_ins, activities)
    review = {
        "id": "acr_" + uuid.uuid4().hex[:16],
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trigger": "exercise_activity",
        "activity_id": activity["id"],
        "policy_version": care_plan["version"],
        "decision": care_plan,
        "model_invoked": False,
        "audit_note": "Daily activity monitoring updated reminders without changing clinical content.",
    }
    try:
        await db.alira_care_reviews.insert_one(review.copy())
    except Exception:
        state = dict(LOCAL_CARE_STATE.get(user["id"]) or {})
        if not any(item.get("id") == activity["id"] for item in state.get("activities") or []):
            state["activities"] = [*(state.get("activities") or []), activity.copy()][-200:]
        state["reviews"] = [*(state.get("reviews") or []), review.copy()][-100:]
        state["latest_plan"] = care_plan
        LOCAL_CARE_STATE[user["id"]] = state
        _persist_local_dict(LOCAL_CARE_STATE_FILE, LOCAL_CARE_STATE)
    return {"ok": True, "activity": activity, "care_plan": care_plan}


@api_router.get("/alira/care-plan")
async def get_alira_care_plan(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    _require_health_data_consent(user)
    return await _adaptive_care_plan_for_user(user)


@api_router.get("/alira/check-in/questions")
async def get_alira_check_in_questions(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    _require_health_data_consent(user)
    plan = await _adaptive_care_plan_for_user(user)
    return {
        "due": plan["survey"]["due"],
        "due_at": plan["survey"]["due_at"],
        "stage": plan["stage"],
        "questions": plan["survey"]["questions"],
        "approved_question_ids": approved_question_ids(),
    }


@api_router.post("/alira/check-ins")
async def submit_alira_check_in(payload: AliraCheckInSubmit, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return await _persist_alira_check_in(user, payload)


@api_router.get("/alira/check-ins")
async def list_alira_check_ins(request: Request, limit: int = 20):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    _require_health_data_consent(user)
    items = await _care_check_ins_for_user(user["id"])
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"check_ins": items[:max(1, min(limit, 100))]}


@api_router.post("/alira/activities")
async def submit_alira_activity(payload: AliraActivitySubmit, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return await _persist_alira_activity(user, payload)


async def _build_patient_context(user: Optional[Dict[str, Any]]) -> str:
    """Pull the signed-in patient's latest assessment and care schedule for Alira."""
    if not user:
        return "No signed-in patient context is available."
    assessments = await _care_assessments_for_user(user["id"])
    check_ins = await _care_check_ins_for_user(user["id"])
    activities = await _care_activities_for_user(user["id"])
    doc = max(assessments, key=lambda item: item.get("created_at", ""), default=None)
    care_plan = build_adaptive_care_plan(user.get("profile") or {}, assessments, check_ins, activities)
    due_questions = [question["id"] for question in care_plan["survey"]["questions"]]
    adaptive_context = (
        "\n\nALIRA ADAPTIVE CARE WORKFLOW:\n"
        f"Recovery stage: {care_plan['stage']}\n"
        f"Safety status: {care_plan['safety']['status']}\n"
        f"Short check-in due: {care_plan['survey']['due']}\n"
        f"Approved questions to ask now: {', '.join(due_questions) or '(none due)'}\n"
        f"Camera assessment due: {care_plan['assessment']['due']}\n"
        f"Approved assessment packages: {', '.join(care_plan['assessment']['packages']) or '(none due)'}\n"
        f"Next exercise-plan action: {care_plan['exercise_plan']['action']}\n"
        f"Daily activity action: {care_plan['daily_monitoring']['next_day_action']}\n"
        "Do not invent a new clinical question, assessment, or exercise. Use only this workflow and the approved tools."
    )
    if not doc:
        return "The patient has not completed an assessment yet." + adaptive_context
    issues = [f"- {i['label']}: {i['description']}" for i in doc.get("functional_issues", [])]
    plan = [f"- {e['name']} ({e['sets']}×{e['reps']}, {e['frequency']})" for e in doc.get("rehab_plan", [])]
    return (
        "Latest assessment date: " + doc.get("created_at", "unknown") + "\n"
        "Affected side: " + doc.get("affected_side", "unknown") + "\n\n"
        "FUNCTIONAL ISSUES IDENTIFIED:\n" + ("\n".join(issues) or "(none yet)") + "\n\n"
        "CURRENT REHAB PLAN:\n" + ("\n".join(plan) or "(no plan yet)") + adaptive_context
    )


CHAT_SYSTEM_PROMPT_BASE = """You are "Alira" — a warm, calm AI stroke-rehabilitation companion. You provide therapist-informed education, reflection, and exercise support, but you are not a licensed therapist and you do not replace the patient's clinical team.

Your tone:
- Warm, patient, never patronizing
- Use short sentences. The patient may have visual or cognitive fatigue.
- Always validate feelings before giving information
- Celebrate small wins enthusiastically
- Never minimize their struggle, but never dwell in despair
- If a preferred name is provided below, use it naturally — not in every reply, but to feel seen

What you know:
- General stroke rehabilitation knowledge (Fugl-Meyer, ARAT, CIMT, BATRAC, Bobath, Task-Specific Training, neuroplasticity basics)
- The patient's current assessment results and rehab plan (provided below)

What you DO NOT do:
- Give medical diagnoses or change their medical regimen
- Recommend stopping medication or therapy
- Make false promises about recovery timelines
- Use clinical jargon — speak in plain, kind language
- Change, add, or delete app functionality
- Invent or activate a new clinical survey question, camera assessment, or exercise. Novel ideas must remain reviewable drafts and must never be assigned to a patient.

Adaptive rehabilitation workflow:
- Follow the ALIRA ADAPTIVE CARE WORKFLOW in the patient context. It is generated from saved survey answers, check-ins, validated assessment evidence, and the approved exercise library.
- Ask a short check-in only when it is due. Ask only the listed approved questions, one at a time, and call record_rehab_check_in after the patient answers.
- Never infer a check-in answer. If the patient does not know or does not want to answer, respect that and leave it unsaved.
- The backend safety rules decide whether the next plan is held, maintained, reduced, or eligible for a small confirmed progression. Do not override that result.
- Patient-reported difficulty remains valid evidence even when a camera task looks normal. Missing or pending model output is never evidence of normal function.

App navigation:
- When the patient asks to start, continue, open, or take an assessment, call navigate_app immediately. Use initial_assessment when no assessment is complete and next_assessment after a completed assessment.
- If the patient says yes or that they are ready immediately after you offered to start an assessment, call navigate_app instead of asking another readiness, consent, or check-in question.
- The assessment flow applies saved readiness answers and its required safety check. Do not recreate those screens as a chat questionnaire.
- For any other request to open, show, find, or visit a Rehyn feature, call navigate_app rather than describing menu steps.

Safety:
- If the patient describes new facial droop, new arm weakness, new speech difficulty, sudden severe headache, collapse, chest pain, or trouble breathing, tell them to seek emergency help immediately.
- If pain, dizziness, or fatigue appears during exercise, tell them to stop and contact their therapist or clinician before continuing.
- Ask one short question at a time during pain check-ins or guided reflections.

When you don't know something, say so warmly and suggest asking their therapist.

If the patient seems distressed, gently acknowledge it, sit with them, and only suggest a tiny actionable step if they seem ready.

Keep replies under 4 short sentences unless the patient asks for more detail."""


def _chat_requests_assessment_start(text: str, turns: Sequence[Dict[str, Any]]) -> bool:
    """Recognize an explicit assessment handoff without treating unrelated yes/no answers as consent."""
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    negative_phrases = (
        "not ready", "don't start", "do not start", "don't want an assessment",
        "do not want an assessment", "stop the assessment", "assessment history",
        "assessment result", "assessment results",
    )
    if any(phrase in normalized for phrase in negative_phrases):
        return False

    assessment_terms = ("assessment", "movement check", "movement test", "camera test", "functional test")
    action_terms = (
        "start", "begin", "take", "do ", "open", "continue", "ready", "go to",
        "want", "need", "can i", "could i", "please",
    )
    if any(term in normalized for term in assessment_terms) and any(term in normalized for term in action_terms):
        return True

    affirmations = {
        "yes", "yes please", "okay", "ok", "sure", "i'm ready", "im ready",
        "ready", "let's start", "lets start", "start now", "please do",
    }
    if normalized not in affirmations:
        return False
    last_assistant = next(
        (str(turn.get("text") or "") for turn in reversed(turns) if turn.get("role") == "assistant"),
        "",
    )
    invitation_tail = " ".join(last_assistant.lower().split())[-220:]
    return any(
        phrase in invitation_tail
        for phrase in (
            "are you ready?", "ready to begin?", "ready to start?",
            "would you like to start?", "would you like to begin?",
            "shall we start?", "shall we begin?", "open the assessment?",
        )
    )


async def _save_chat_session(
    session_filter: Dict[str, Any],
    local_session_key: str,
    session_id: str,
    user_id: str,
    turns: List[Dict[str, Any]],
    updated_at: str,
) -> None:
    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "turns": turns,
        "updated_at": updated_at,
    }
    try:
        await db.chat_sessions.update_one(session_filter, {"$set": session_doc}, upsert=True)
    except Exception:
        LOCAL_CHAT_SESSIONS[local_session_key] = session_doc


@api_router.post("/realtime/session")
async def create_alira_realtime_session(req: RealtimeSessionRequest, request: Request):
    """Create a browser WebRTC call without exposing the OpenAI API key."""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Live voice is unavailable because the AI key is not configured.")
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to call Alira.")

    patient_ctx = await _build_patient_context(user)
    profile = user.get("profile") or {}
    preferred_name = (profile.get("preferred_name") or user.get("name") or "").split(" ")[0].strip()
    name_block = f"\nPATIENT PREFERRED NAME: {preferred_name}\n" if preferred_name else ""
    live_voice_rules = """

LIVE VOICE CONVERSATION RULES:
- This is a natural spoken conversation. Speak warmly and clearly; never use markdown, headings, or lists aloud.
- Usually answer in one to three short sentences, then pause. Ask no more than one question at a time.
- Give the patient time to speak and think. Do not rush, finish their sentences, or comment on speech difficulty.
- If the patient interrupts, stop speaking immediately and listen.
- If audio is unclear, gently ask them to repeat it rather than guessing.
- Never diagnose, prescribe, or present yourself as a therapist or emergency service.
- For possible stroke or other emergency symptoms, clearly tell the patient to call emergency services now. In the UK, say to call 999.
- When the patient asks where a feature is or asks you to open, show, find, or take them to a page, call navigate_app. Do not give a sequence of menu directions instead.
- Wait for the navigation tool result before saying that a page is opening. If the requested result or plan is unavailable, explain the tool result briefly and offer the assessment or Journey page.
- Navigation is read-only. Never claim to change a setting, submit a form, delete data, or complete an assessment for the patient.
"""
    instructions = (
        CHAT_SYSTEM_PROMPT_BASE
        + live_voice_rules
        + name_block
        + "\n----\nPATIENT CONTEXT:\n"
        + patient_ctx
    )
    session_config = {
        "type": "realtime",
        "model": ALIRA_REALTIME_MODEL,
        "output_modalities": ["audio"],
        "instructions": instructions,
        "max_output_tokens": 500,
        "tools": [ALIRA_NAVIGATION_TOOL, ALIRA_RECORD_CHECKIN_TOOL],
        "tool_choice": "auto",
        "audio": {
            "input": {
                "noise_reduction": {"type": "near_field"},
                "transcription": {"model": "gpt-transcribe", "language": "en"},
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "low",
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output": {"voice": ALIRA_REALTIME_VOICE, "speed": 0.95},
        },
    }
    safety_identifier = hashlib.sha256(f"rehyn:{user['id']}".encode("utf-8")).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Safety-Identifier": safety_identifier,
                },
                files={
                    "sdp": (None, req.sdp),
                    "session": (None, json.dumps(session_config)),
                },
            )
    except httpx.HTTPError as exc:
        logger.error("Realtime session connection failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Alira could not start a live call. Please try again.") from exc

    if not upstream.is_success:
        try:
            upstream_message = str(upstream.json().get("error", {}).get("message", ""))[:300]
        except (ValueError, AttributeError):
            upstream_message = upstream.text[:300]
        logger.error("Realtime session rejected (%s): %s", upstream.status_code, upstream_message)
        raise HTTPException(status_code=502, detail="Alira could not start a live call. Please try again.")

    return Response(content=upstream.text, media_type="application/sdp")


@api_router.post("/chat/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to talk with Alira.")
    session_filter = {"session_id": req.session_id, "user_id": user["id"]}
    local_session_key = f"{user['id']}:{req.session_id}"
    try:
        sess = await db.chat_sessions.find_one(session_filter, {"_id": 0})
    except Exception:
        sess = LOCAL_CHAT_SESSIONS.get(local_session_key)
    turns: List[Dict[str, Any]] = sess["turns"] if sess else []

    if _chat_requests_assessment_start(req.text, turns):
        assessments = await _care_assessments_for_user(user["id"])
        check_ins = await _care_check_ins_for_user(user["id"])
        activities = await _care_activities_for_user(user["id"])
        care_plan = build_adaptive_care_plan(user.get("profile") or {}, assessments, check_ins, activities)
        now = datetime.now(timezone.utc).isoformat()
        navigation_destination: Optional[str] = None
        if care_plan["assessment"]["blocked_by_safety"]:
            reply_text = str(care_plan["safety"]["message"])
        elif assessments:
            navigation_destination = "next_assessment"
            reply_text = "I’m opening the movement assessment that best matches your current recovery needs."
        else:
            navigation_destination = "initial_assessment"
            reply_text = "I’m opening your Initial Assessment now. Your saved readiness answers will select suitable tasks and completed tasks will not be repeated."
        turns.append({"role": "user", "text": req.text, "ts": now})
        turns.append({"role": "assistant", "text": reply_text, "ts": now})
        await _save_chat_session(session_filter, local_session_key, req.session_id, user["id"], turns, now)
        return ChatResponse(
            session_id=req.session_id,
            text=reply_text,
            turns=len(turns),
            navigation_destination=navigation_destination,
        )

    if not EMERGENT_LLM_KEY and not openai_tts_client:
        raise HTTPException(status_code=503, detail="Chat unavailable — LLM key not configured.")

    # Build patient context (refreshed every turn so new assessments propagate)
    patient_ctx = await _build_patient_context(user)
    # Inject preferred name from the signed-in user's onboarding profile, if available.
    name = ""
    if user:
        prof = user.get("profile") or {}
        name = (prof.get("preferred_name") or user.get("name") or "").split(" ")[0].strip()
    name_block = f"\nPATIENT PREFERRED NAME: {name}\n" if name else ""
    system_prompt = CHAT_SYSTEM_PROMPT_BASE + name_block + "\n----\nPATIENT CONTEXT:\n" + patient_ctx
    navigation_destination: Optional[str] = None

    try:
        if openai_tts_client:
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(
                {"role": turn["role"], "content": turn["text"]}
                for turn in turns[-8:]
                if turn.get("role") in {"user", "assistant"}
            )
            messages.append({"role": "user", "content": req.text})

            def run_chat_completion():
                return openai_tts_client.chat.completions.create(
                    model=ALIRA_CHAT_MODEL,
                    messages=messages,
                    tools=[ALIRA_CHAT_NAVIGATION_TOOL, ALIRA_CHAT_RECORD_CHECKIN_TOOL],
                    tool_choice="auto",
                    temperature=0.5,
                    max_tokens=260,
                )

            response = await asyncio.to_thread(run_chat_completion)
            assistant_message = response.choices[0].message
            tool_calls = list(assistant_message.tool_calls or [])
            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                })
                for call in tool_calls:
                    if call.function.name == "navigate_app":
                        try:
                            arguments = json.loads(call.function.arguments or "{}")
                            destination = str(arguments.get("destination") or "").strip().lower()
                        except (ValueError, TypeError):
                            destination = ""
                        if destination in ALIRA_NAVIGATION_DESTINATIONS:
                            navigation_destination = destination
                            tool_result = {"ok": True, "destination": destination, "message": "The requested Rehyn page is opening."}
                        else:
                            tool_result = {"ok": False, "message": "That Rehyn destination is not available."}
                    elif call.function.name != "record_rehab_check_in":
                        tool_result = {"ok": False, "message": "Unsupported Alira care tool."}
                    else:
                        try:
                            arguments = json.loads(call.function.arguments or "{}")
                            submitted = AliraCheckInSubmit(
                                answers=arguments.get("answers") or {},
                                patient_note=arguments.get("patient_note"),
                                source="text_chat",
                            )
                            saved = await _persist_alira_check_in(user, submitted)
                            tool_result = {
                                "ok": True,
                                "safety": saved["care_plan"]["safety"],
                                "next_exercise_action": saved["care_plan"]["exercise_plan"]["action"],
                                "next_assessment": saved["care_plan"]["assessment"],
                            }
                        except (ValueError, TypeError, HTTPException) as exc:
                            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                            tool_result = {"ok": False, "message": detail}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(tool_result, ensure_ascii=True),
                    })

                def run_follow_up_completion():
                    return openai_tts_client.chat.completions.create(
                        model=ALIRA_CHAT_MODEL,
                        messages=messages,
                        tools=[ALIRA_CHAT_NAVIGATION_TOOL, ALIRA_CHAT_RECORD_CHECKIN_TOOL],
                        tool_choice="none",
                        temperature=0.3,
                        max_tokens=220,
                    )

                response = await asyncio.to_thread(run_follow_up_completion)
                assistant_message = response.choices[0].message
            reply_text = str(assistant_message.content or "").strip()
        else:
            recent = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in turns[-6:])
            emergent_prompt = system_prompt + ("\n\n----\nRECENT CONVERSATION:\n" + recent if recent else "")
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=req.session_id,
                system_message=emergent_prompt,
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            response = await chat.send_message(UserMessage(text=req.text))
            reply_text = response if isinstance(response, str) else str(response)
        if not reply_text:
            raise RuntimeError("Alira returned an empty response")
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=502, detail=f"Chat error: {str(e)[:200]}")

    now = datetime.now(timezone.utc).isoformat()
    turns.append({"role": "user", "text": req.text, "ts": now})
    turns.append({"role": "assistant", "text": reply_text, "ts": now})
    await _save_chat_session(session_filter, local_session_key, req.session_id, user["id"], turns, now)
    return ChatResponse(
        session_id=req.session_id,
        text=reply_text,
        turns=len(turns),
        navigation_destination=navigation_destination,
    )


@api_router.get("/chat/history")
async def chat_history(session_id: str, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to view this conversation.")
    try:
        sess = await db.chat_sessions.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    except Exception:
        sess = LOCAL_CHAT_SESSIONS.get(f"{user['id']}:{session_id}")
    return {"session_id": session_id, "turns": (sess or {}).get("turns", [])}


@api_router.post("/chat/proactive")
async def chat_proactive(req: ChatRequest, request: Request):
    """Returns a warm spontaneous check-in line. Uses preferred_name if available."""
    import random
    user = await _user_from_header(dict(request.headers))
    name = ""
    if user:
        profile = user.get("profile") or {}
        name = (profile.get("preferred_name") or user.get("name") or "").split(" ")[0].strip()
    try:
        sess = await db.chat_sessions.find_one(
            {"session_id": req.session_id, "user_id": user["id"]} if user else {"session_id": req.session_id},
            {"_id": 0},
        )
    except Exception:
        sess = LOCAL_CHAT_SESSIONS.get(f"{user['id']}:{req.session_id}") if user else None
    has_history = bool(sess and sess.get("turns"))
    has_assessment = False
    if user:
        try:
            has_assessment = bool(await db.assessments.find_one({"user_id": user["id"]}, {"_id": 1}))
        except Exception:
            has_assessment = any(item.get("user_id") == user["id"] for item in LOCAL_ASSESSMENTS)
    n = f", {name}" if name else ""

    if not has_assessment:
        pool = [
            f"Hi{n}. I'm Alira — your recovery companion. Whenever you're ready, taking that first assessment will help me support you. How are you feeling today?",
            f"Hello{n}. I'm here whenever you need to talk. Have you had a chance to do your first movement check yet?",
            f"Hi{n}, I'm Alira. How are you doing today?",
        ]
    elif not has_history:
        pool = [
            f"Hi{n}, I'm Alira. I saw your assessment results — thank you for trusting me. How are you feeling today, gently?",
            f"Hello{n}. I'm here for the journey. Want to tell me how the morning has been?",
            f"Hi{n}. Recovery has good days and tougher days. Which one is today?",
        ]
    else:
        pool = [
            f"How are you doing today{n}? Anything on your mind?",
            f"I've been thinking about you{n}. How did the exercises feel this morning?",
            f"Just checking in{n}. Did you sleep okay last night?",
            f"How is your shoulder feeling today{n}? Easier, harder, or about the same?",
            f"Small reminder{n}: every tiny step counts. How are you, really?",
            f"Hi{n}. What's one thing — big or small — that went well for you today?",
            f"Hello{n}. I'm holding space for you. What would feel good to talk about right now?",
        ]
    return {"text": random.choice(pool)}


@api_router.get("/chat/proactive/messages")
async def chat_proactive_messages(request: Request, n: int = 3):
    """Returns N varied caring proactive messages for the floating Alira bubble on Home."""
    import random
    user = await _user_from_header(dict(request.headers))
    name = ""
    if user:
        profile = user.get("profile") or {}
        name = (profile.get("preferred_name") or user.get("name") or "").split(" ")[0].strip()
    suffix = f", {name}" if name else ""
    pool = [
        f"How are you{suffix}?",
        f"Hi{suffix} — just checking in. How is today going?",
        f"Thinking of you{suffix}. Did you sleep well?",
        f"How are your hands feeling today{suffix}?",
        f"Anything on your mind{suffix}? I'm here.",
        f"Want to share one small win from today{suffix}?",
        f"Quick check-in{suffix}: feeling lighter, heavier, or the same?",
        f"Hi{suffix}. Be gentle with yourself today.",
        f"How was the morning{suffix}? I'd love to hear.",
        f"Hey{suffix} — your body is healing in ways you can't see. How are you feeling?",
    ]
    random.shuffle(pool)
    return {"messages": pool[:max(1, min(n, len(pool)))], "name": name}


# Mount routes
# (deferred to end-of-file after Phase C routes)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============ Phase C — Billing (Stripe), Google Auth, Progress dashboard ============
import stripe as _stripe
import httpx as _httpx

_stripe.api_key = os.environ.get("STRIPE_API_KEY") or os.environ.get("STRIPE_SECRET_KEY") or ""
STRIPE_PRICE_SUBSCRIPTION_AMOUNT = 999  # $9.99 in cents
STRIPE_PRICE_CREDIT_PACK_AMOUNT = 499   # $4.99 in cents
CREDIT_PACK_SIZE = 200


def _stripe_origin(request: Request) -> str:
    """Build a return URL origin from the incoming request — works for both web
    and mobile WebView Checkout returns."""
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = request.headers.get("referer", "")
    if referer:
        try:
            from urllib.parse import urlparse
            p = urlparse(referer)
            return f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
    return "https://localhost"


@api_router.post("/billing/subscribe")
async def billing_subscribe(request: Request):
    """Create a Stripe Checkout Session for the $9.99/mo subscription.
    Uses inline `price_data` so we don't need pre-created Stripe prices."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    origin = _stripe_origin(request)
    try:
        session = _stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "NeuroMotion Unlimited (Monthly)"},
                    "unit_amount": STRIPE_PRICE_SUBSCRIPTION_AMOUNT,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            customer_email=user.get("email"),
            client_reference_id=user["id"],
            metadata={"action": "start_subscription", "app_user_id": user["id"]},
            success_url=f"{origin}/billing-return?session_id={{CHECKOUT_SESSION_ID}}&kind=sub",
            cancel_url=f"{origin}/?canceled=1",
        )
        # Track pending session so the return endpoint can finalize even without webhooks.
        await db.billing_sessions.insert_one({
            "session_id": session["id"], "user_id": user["id"], "kind": "subscription",
            "status": "pending", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"url": session["url"], "session_id": session["id"]}
    except Exception as e:
        logger.error(f"Stripe subscribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@api_router.post("/billing/buy-credits")
async def billing_buy_credits(request: Request):
    """One-time $4.99 → 200 credits for AI therapist chat top-up."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    origin = _stripe_origin(request)
    try:
        session = _stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"NeuroMotion {CREDIT_PACK_SIZE} Credits Pack"},
                    "unit_amount": STRIPE_PRICE_CREDIT_PACK_AMOUNT,
                },
                "quantity": 1,
            }],
            customer_email=user.get("email"),
            client_reference_id=user["id"],
            metadata={"action": "buy_credits", "app_user_id": user["id"], "credits": str(CREDIT_PACK_SIZE)},
            success_url=f"{origin}/billing-return?session_id={{CHECKOUT_SESSION_ID}}&kind=credits",
            cancel_url=f"{origin}/?canceled=1",
        )
        await db.billing_sessions.insert_one({
            "session_id": session["id"], "user_id": user["id"], "kind": "credit_pack",
            "credits": CREDIT_PACK_SIZE, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"url": session["url"], "session_id": session["id"]}
    except Exception as e:
        logger.error(f"Stripe credit pack error: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@api_router.get("/billing/verify-session")
async def billing_verify_session(session_id: str, request: Request):
    """Poll-based fallback to webhook: the frontend calls this after Checkout
    returns. We fetch the Checkout Session from Stripe; if paid, we apply the
    subscription or credit grant idempotently (using our local billing_sessions
    record to avoid double-applying)."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    rec = await db.billing_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not rec or rec.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Unknown session")
    if rec.get("status") == "applied":
        # Already applied — just return current user state.
        u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        return {"status": "applied", "credits": u["credits"], "subscription_active": bool(u.get("subscription_active"))}
    if not _stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        session = _stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:200])
    paid = session.get("payment_status") in ("paid", "no_payment_required")
    if not paid:
        return {"status": "pending", "payment_status": session.get("payment_status")}
    # Apply effect idempotently
    if rec["kind"] == "subscription":
        # Pull subscription period end if available
        period_end_iso = None
        sub_id = session.get("subscription")
        if sub_id:
            try:
                sub = _stripe.Subscription.retrieve(sub_id)
                cpe = sub.get("current_period_end")
                if cpe:
                    period_end_iso = datetime.fromtimestamp(cpe, tz=timezone.utc).isoformat()
            except Exception:
                pass
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "subscription_active": True,
            "subscription_id": sub_id,
            "subscription_period_end": period_end_iso,
        }})
    elif rec["kind"] == "credit_pack":
        credits = int(rec.get("credits", CREDIT_PACK_SIZE))
        await db.users.update_one({"id": user["id"]}, {"$inc": {"credits": credits}})
    await db.billing_sessions.update_one({"session_id": session_id}, {"$set": {"status": "applied"}})
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {"status": "applied", "credits": u["credits"], "subscription_active": bool(u.get("subscription_active"))}


@api_router.post("/billing/webhook")
async def billing_webhook(request: Request):
    """Best-effort Stripe webhook. Verifies signature only if STRIPE_WEBHOOK_SECRET
    is set; otherwise still processes events (useful in dev). Applies the same
    idempotent grant logic as /billing/verify-session."""
    payload = await request.body()
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    sig = request.headers.get("stripe-signature", "")
    event = None
    if secret and sig:
        try:
            event = _stripe.Webhook.construct_event(payload, sig, secret)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bad webhook signature: {e}")
    else:
        import json as _json
        try:
            event = _json.loads(payload.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Bad payload")
    etype = event.get("type")
    obj = event.get("data", {}).get("object", {})
    if etype == "checkout.session.completed":
        sid = obj.get("id")
        rec = await db.billing_sessions.find_one({"session_id": sid}, {"_id": 0}) if sid else None
        if rec and rec.get("status") != "applied":
            uid = rec["user_id"]
            if rec["kind"] == "subscription":
                period_end_iso = None
                cpe = obj.get("subscription")
                # Just mark active; period_end is best-effort.
                await db.users.update_one({"id": uid}, {"$set": {
                    "subscription_active": True,
                    "subscription_id": cpe,
                    "subscription_period_end": period_end_iso,
                }})
            elif rec["kind"] == "credit_pack":
                credits = int(rec.get("credits", CREDIT_PACK_SIZE))
                await db.users.update_one({"id": uid}, {"$inc": {"credits": credits}})
            await db.billing_sessions.update_one({"session_id": sid}, {"$set": {"status": "applied"}})
    elif etype == "customer.subscription.deleted":
        sub_id = obj.get("id")
        if sub_id:
            await db.users.update_one({"subscription_id": sub_id}, {"$set": {"subscription_active": False}})
    return {"ok": True}


# ============ Google Auth (Emergent-managed) ============
@api_router.post("/auth/google/session")
async def auth_google_session(request: Request):
    """Frontend posts the session_id it received in the redirect from
    https://auth.emergentagent.com/. We exchange it for the user payload, then
    create/lookup our user record."""
    body = await request.json()
    sid = body.get("session_id") or body.get("sessionId")
    if not sid:
        raise HTTPException(status_code=400, detail="session_id required")
    async with _httpx.AsyncClient(timeout=10.0) as cx:
        try:
            r = await cx.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": sid},
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Auth service unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail=f"Invalid session ({r.status_code})")
    data = r.json()
    email = (data.get("email") or "").lower()
    name = data.get("name") or email.split("@")[0]
    if not email:
        raise HTTPException(status_code=400, detail="No email returned from Google")
    user = await get_or_create_user(email, name, role="patient")
    # Stash picture/google_id for the profile
    extras = {k: data.get(k) for k in ("picture", "id") if data.get(k)}
    if extras:
        try:
            await db.users.update_one({"id": user["id"]}, {"$set": {"google": extras}})
        except Exception as exc:
            logger.warning(f"Mongo unavailable for Google profile update; using local fallback: {str(exc)[:120]}")
            local_user = {**user, "google": extras}
            LOCAL_USERS[user["id"]] = local_user
            _persist_local_dict(LOCAL_USERS_FILE, LOCAL_USERS)
            user = local_user
    return user


# ============ Progress dashboard ============
@api_router.get("/therapist/patients")
async def therapist_patients(request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user or user.get("role") != "therapist":
        raise HTTPException(status_code=400, detail="Therapist account required")
    bookings = await db.bookings.find({"therapist_user_id": user["id"]}, {"_id": 0}).to_list(500)
    roster: Dict[str, str] = {}
    for b in bookings:
        pid = b.get("patient_user_id")
        if pid:
            roster[pid] = b.get("patient_name") or "Patient"
    signoffs = await db.plan_signoffs.find({"therapist_user_id": user["id"]}, {"_id": 0}).to_list(500)
    signed_by_patient = {s["patient_user_id"]: s for s in signoffs}
    patients = []
    for pid, pname in roster.items():
        latest = await db.assessments.find_one(
            {"user_id": pid},
            {"_id": 0, "id": 1, "created_at": 1, "issues_detected": 1, "rehab_plan": 1},
            sort=[("created_at", -1)],
        )
        signed = signed_by_patient.get(pid)
        patients.append({
            "patient_user_id": pid,
            "name": pname,
            "latest_assessment_id": (latest or {}).get("id"),
            "last_assessment_date": (latest or {}).get("created_at"),
            "issues_count": len((latest or {}).get("issues_detected") or []),
            "exercises_count": len((latest or {}).get("rehab_plan") or []),
            "plan_signed": bool(signed and signed.get("assessment_id") == (latest or {}).get("id")),
            "signed_at": (signed or {}).get("signed_at"),
        })
    patients.sort(key=lambda p: p.get("last_assessment_date") or "", reverse=True)
    return {"patients": patients}


class PlanSignoff(BaseModel):
    assessment_id: str
    note: Optional[str] = None


@api_router.post("/therapist/patient/{patient_user_id}/signoff")
async def therapist_signoff(patient_user_id: str, payload: PlanSignoff, request: Request):
    user = await _user_from_header(dict(request.headers))
    if not user or user.get("role") != "therapist":
        raise HTTPException(status_code=400, detail="Therapist account required")
    signed_at = datetime.now(timezone.utc).isoformat()
    record = {
        "therapist_user_id": user["id"],
        "patient_user_id": patient_user_id,
        "assessment_id": payload.assessment_id,
        "note": payload.note or "",
        "signed_at": signed_at,
    }
    await db.plan_signoffs.update_one(
        {"therapist_user_id": user["id"], "patient_user_id": patient_user_id},
        {"$set": record},
        upsert=True,
    )
    return {"ok": True, "signed_at": signed_at}


@api_router.get("/progress/summary")
async def progress_summary(request: Request):
    """Returns time-series functional metrics + exercise progress totals.
    Empty arrays when the user has never assessed."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        return {"assessments": [], "exercises": [], "issues_history": [], "first_seen": None}
    cursor = db.assessments.find(
        {"user_id": user["id"]},
        {"_id": 0, "id": 1, "created_at": 1, "metrics": 1, "issues_detected": 1, "rehab_plan": 1, "task_results": 1},
    ).sort("created_at", 1)
    assessments_raw = await cursor.to_list(200)
    series = []
    issues_count: Dict[str, int] = {}
    for a in assessments_raw:
        m = a.get("metrics") or {}
        series.append({
            "id": a.get("id"),
            "date": a.get("created_at"),
            # Headline functional metrics — None if not yet computed.
            "shoulder_flexion_deg": m.get("shoulder_flexion_deg"),
            "trunk_lean_deg": m.get("trunk_lean_deg"),
            "reach_completion": m.get("reach_completion"),
            "bilateral_symmetry": m.get("bilateral_symmetry"),
            "pinch_grip": m.get("pinch_grip"),
            "hand_opening": m.get("hand_opening"),
            "issues_count": len(a.get("issues_detected") or []),
            "exercises_count": len(a.get("rehab_plan") or []),
        })
        for iss in (a.get("issues_detected") or []):
            issues_count[iss] = issues_count.get(iss, 0) + 1
    return {
        "assessments": series,
        "issues_history": [{"issue": k, "count": v} for k, v in sorted(issues_count.items(), key=lambda x: -x[1])],
        "first_seen": series[0]["date"] if series else None,
        "count": len(series),
    }


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# Mount routes — MUST be last so all routes defined above (including Phase C)
# are registered.
app.include_router(api_router)
