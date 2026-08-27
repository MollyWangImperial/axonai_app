from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
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
from typing import List, Dict, Any, Optional
import uuid
import re
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
    from backend.assessment_fusion import build_analysis_pipeline, build_survey_consistency
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
    from assessment_fusion import build_analysis_pipeline, build_survey_consistency

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

# Local development fallback: keeps Expo phone testing usable when Docker/Mongo
# is not running. Mongo remains the source of truth whenever it is reachable.
LOCAL_USERS: Dict[str, Dict[str, Any]] = {}
LOCAL_ASSESSMENTS: List[Dict[str, Any]] = []

# OpenAI TTS: prefer direct OPENAI_API_KEY for local/dev, keep Emergent key as fallback.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()
TTS_VOICE = os.environ.get("TTS_VOICE", "nova")  # warm/encouraging default
TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
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
    patient_parameters: Dict[str, Any] = Field(default_factory=dict)
    musculoskeletal_outputs: Dict[str, Any] = Field(default_factory=dict)
    motion_data: Dict[str, Any] = Field(default_factory=dict)


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
            {"id": "H3-S3", "voice": "Separate your fingers and relax.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Relax hand"},
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
            {"id": "H4-S3", "voice": "Well done. Lower your hand to rest.", "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"}, "hold_ms": 1200, "caption": "Lower hand"},
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
        "subtitle": "Seven guided arm, hand, and comfortable-walking observations for every new patient",
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
async def get_tasks(package: str = "upper_limb"):
    selected = ASSESSMENT_PACKAGES.get(package, ASSESSMENT_PACKAGES["upper_limb"])
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
        "tasks": selected["tasks"],
        "voice_id": TTS_VOICE,
        "package_id": selected["id"],
        "package_title": selected["title"],
        "package_subtitle": selected["subtitle"],
        "packages": packages,
    }


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


async def _task_video_user(request: Request, uid: str = "") -> Optional[Dict[str, Any]]:
    headers = dict(request.headers)
    if uid and not (headers.get("x-user-id") or headers.get("X-User-Id")):
        headers["x-user-id"] = uid
    return await _user_from_header(headers)


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
    except Exception as e:
        logger.warning(f"Mongo unavailable for task video list; using local fallback: {str(e)[:120]}")
        records = [
            item for item in _local_task_video_metadata()
            if item.get("user_id") == user["id"] and item.get("package_id") == safe_package
        ]
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"videos": records}


@api_router.get("/assessment/task-videos/file/{video_id}")
async def get_task_video(video_id: str, request: Request, uid: str = ""):
    user = await _task_video_user(request, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
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


def _assessment_patient_parameters(
    submitted: Dict[str, Any],
    user: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(submitted or {})
    profile = user.get("profile") if isinstance(user, dict) and isinstance(user.get("profile"), dict) else {}
    if profile:
        for key in ("age_band", "months_since_stroke", "side_affected", "affected_areas", "affected_areas_other", "dominant_hand", "mobility_level", "medical_conditions", "medical_conditions_other", "has_caregiver"):
            if profile.get(key) is not None:
                merged.setdefault(key, profile[key])
        if not merged.get("patient_priorities"):
            priorities = []
            if str(profile.get("primary_goal") or "").strip():
                priorities.append(str(profile["primary_goal"]).strip())
            priorities.extend(str(item).strip() for item in profile.get("secondary_goals") or [] if str(item).strip())
            if priorities:
                merged["patient_priorities"] = priorities
    return merged


@api_router.post("/assessment/submit", response_model=Assessment)
async def submit_assessment(payload: AssessmentSubmit, request: Request):
    user = await _user_from_header(dict(request.headers))
    if user:
        await consume_credits(user["id"], "assessment")
        await consume_credits(user["id"], "rehab_plan")
    patient_parameters = _assessment_patient_parameters(payload.patient_parameters, user)
    issues = derive_functional_issues(payload.task_results)
    plan = build_rehab_plan(issues, patient_parameters)
    domain_assessments = build_domain_assessments(payload.task_results)
    clinician_measures = build_clinician_measure_summary(patient_parameters)
    biomechanical_estimates = build_biomechanical_estimates(
        payload.task_results,
        patient_parameters,
        payload.musculoskeletal_outputs,
    )
    measurement_form = build_clinical_measurement_form(
        payload.task_results,
        patient_parameters,
        payload.musculoskeletal_outputs,
    )
    rehabilitation_goals = build_rehab_goals(
        payload.task_results,
        issues,
        measurement_form,
        patient_parameters,
    )
    muscle_activation_diagnosis = build_muscle_activation_diagnosis(
        [t.dict() for t in payload.task_results],
    )
    survey_consistency = build_survey_consistency(
        issues,
        patient_parameters,
        payload.task_results,
    )
    analysis_pipeline = build_analysis_pipeline(
        payload.motion_data,
        payload.musculoskeletal_outputs,
    )
    assessment = Assessment(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        affected_side=payload.affected_side,
        assessment_package=payload.assessment_package,
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
    )
    doc = assessment.dict()
    if payload.motion_data:
        doc["motion_data"] = payload.motion_data
    if user:
        doc["user_id"] = user["id"]
    try:
        await db.assessments.insert_one(doc)
    except Exception as e:
        logger.warning(f"Mongo unavailable for assessment insert; using local fallback: {str(e)[:120]}")
        LOCAL_ASSESSMENTS.append(doc.copy())
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


@api_router.get("/assessment/{assessment_id}/muscle-diagnosis")
async def get_muscle_diagnosis(assessment_id: str):
    """Recompute the four-anomaly muscle-activation diagnosis for a stored
    assessment (also works for assessments saved before this feature)."""
    try:
        doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"Mongo unavailable for muscle diagnosis; local fallback: {str(e)[:120]}")
        doc = next((item for item in LOCAL_ASSESSMENTS if item.get("id") == assessment_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return build_muscle_activation_diagnosis(doc.get("task_results", []))


# ============ Pose Runner HTML (served at /api/pose/runner) ============
# A self-contained page that:
# 1. Opens device camera (getUserMedia)
# 2. Loads MediaPipe PoseLandmarker
# 3. Walks through 7 tasks × steps with target overlays + voice prompts
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
  #stage{position:relative;width:100vw;height:100vh;background:#000}
  video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
  canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
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
  <video id="video" playsinline autoplay muted></video>
  <canvas id="canvas"></canvas>
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
    <p>We will guide you through 7 short movement tasks using your camera. Move into the camera view, then tap Start.</p>
    <button id="startBtn" data-testid="assessment-start">Start Assessment</button>
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

<script type="module">
import { PoseLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

const API_BASE = window.location.origin + "/api";
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const dotsEl = document.getElementById("dots");
const taskLabel = document.getElementById("taskLabel");
const stepTitle = document.getElementById("stepTitle");
const captionEl = document.getElementById("caption");
const voiceText = document.getElementById("voiceText");
const overlay = document.getElementById("overlay");
const startBtn = document.getElementById("startBtn");
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
let running = false;
let audioEl = new Audio();
const voiceAudioCache = new Map();
const voiceAudioInflight = new Map();
let taskLoadPromise = null;
let audioUnlockPromise = null;
let latestHandLandmarks = null;        // result.landmarks[0] from HandLandmarker (21 points)
let latestHandedness = "";             // "Left" / "Right" from MediaPipe, used for palm/back orientation
let latestPoseLandmarks = null;        // result.landmarks[0] from PoseLandmarker (33 points)
let latestPoseWorldLandmarks = null;   // estimated 3D world landmarks from PoseLandmarker
let dynamicTargetPos = null;           // {x,y} locked once a dynamic body target is calibrated
let lapTargetCalibration = {samples:[], target:null, ready:false, announced:false};
const LAP_CALIBRATION_MIN_SAMPLES = 8;
const LAP_CALIBRATION_MIN_MS = 650;
let handOpenScore = 0;                 // 0..1 — finger extension confidence
let fistClosureScore = 0;              // 0..1 — mass finger flexion confidence
let pinchScore = 0;                    // 0..1 — pinch confidence (1 = very close)
let palmFacingScore = 0;               // 0..1 — palm plane faces camera rather than edge-on
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
let motionFrames = [];
let lastMotionSampleTs = 0;
const MOTION_SAMPLE_INTERVAL_MS = 100;
const MAX_MOTION_FRAMES = 2400;
const URL_PARAMS = new URLSearchParams(window.location.search);
const CURRENT_USER_ID = URL_PARAMS.get("uid") || "";
const ASSESSMENT_PACKAGE = URL_PARAMS.get("package") || "upper_limb";
const START_TASK_ID = URL_PARAMS.get("start_task") || "";
const AFFECTED_SIDE = URL_PARAMS.get("affected_side") === "left" ? "left" : "right";
const TASK_VIDEO_DB_NAME = "rehyn-task-videos-v1";
const TASK_VIDEO_STORE_NAME = "task-videos";
let activeTaskRecorder = null;
let activeTaskRecording = null;
let pendingTaskVideoSaves = new Set();
let recorderUnavailableReported = false;

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

function postRN(data){
  if(window.ReactNativeWebView){
    window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }
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

async function persistTaskVideo(recording, blob){
  const durationMs = Math.max(0, Math.round(performance.now() - recording.startedAt));
  const localKey = `${CURRENT_USER_ID || "anonymous"}:${ASSESSMENT_PACKAGE}:${recording.taskId}`;
  let localSaved = false;
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
    localSaved = true;
  }catch(e){
    postRN({type:"task_video_error", task_id:recording.taskId, message:`Local save failed: ${String(e)}`});
  }

  let cloudRecord = null;
  if(CURRENT_USER_ID){
    try{
      const query = new URLSearchParams({
        package_id: ASSESSMENT_PACKAGE,
        task_id: recording.taskId,
        duration_ms: String(durationMs),
      });
      const response = await fetch(`${API_BASE}/assessment/task-videos?${query.toString()}`, {
        method:"POST",
        headers:{
          "Content-Type": blob.type || recording.mimeType || "video/webm",
          "X-User-Id": CURRENT_USER_ID,
        },
        body:blob,
      });
      if(!response.ok) throw new Error(`Video upload failed (${response.status})`);
      cloudRecord = await response.json();
    }catch(e){
      postRN({type:"task_video_error", task_id:recording.taskId, local_saved:localSaved, message:String(e)});
    }
  }

  if(localSaved || cloudRecord){
    postRN({
      type:"task_video_saved",
      package_id:ASSESSMENT_PACKAGE,
      task_id:recording.taskId,
      local_saved:localSaved,
      cloud_saved:!!cloudRecord && cloudRecord.storage === "gridfs",
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
  if(!running || motionFrames.length >= MAX_MOTION_FRAMES) return;
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
  const res = await fetch(`${API_BASE}/assessment/tasks?package=${encodeURIComponent(ASSESSMENT_PACKAGE)}`);
  const json = await res.json();
  tasks = json.tasks;
  voiceId = json.voice_id;
  const overlayCopy = overlay.querySelector("p");
  if(overlayCopy) overlayCopy.textContent = `We will guide you through ${tasks.length} short movement tasks using your camera. Move into the camera view, then tap Start.`;
  if(START_TASK_ID){
    const startIdx = tasks.findIndex((task) => task.id === START_TASK_ID);
    if(startIdx >= 0) currentTaskIdx = startIdx;
  }
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
    const videoSettings = (ASSESSMENT_PACKAGE === "hand" || ASSESSMENT_PACKAGE === "initial")
      ? {facingMode:"user", width:{ideal:640}, height:{ideal:480}, frameRate:{ideal:30, max:30}}
      : {facingMode:"user", width:{ideal:480}, height:{ideal:360}, frameRate:{ideal:30, max:30}};
    const stream = await navigator.mediaDevices.getUserMedia({video:videoSettings, audio:false});
    video.srcObject = stream;
    await new Promise(r => video.onloadedmetadata = r);
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    return true;
  }catch(e){
    captionEl.textContent = "Camera permission denied. Please allow camera access.";
    postRN({type:"camera_error", message:String(e)});
    return false;
  }
}

async function getVisionFilesetResolver(){
  if(!visionFilesetResolver){
    visionFilesetResolver = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
    );
  }
  return visionFilesetResolver;
}

async function setupPose(){
  const filesetResolver = await getVisionFilesetResolver();
  landmarker = await PoseLandmarker.createFromOptions(filesetResolver, {
    baseOptions:{ modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task" },
    runningMode: "VIDEO",
    numPoses: 1,
  });
}

async function setupHand(){
  const filesetResolver = await getVisionFilesetResolver();
  try{
    handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
      baseOptions:{ modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" },
      runningMode: "VIDEO",
      numHands: 1,
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
  if(ASSESSMENT_PACKAGE === "hand"){
    await setupHand();
  }else{
    await setupPose();
  }
  drawingUtils = new DrawingUtils(ctx);
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
  if(!text) return;
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
  arrivedAfterMovement = isHandTask() || step.movement_required === false;
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
  fingerTotalFlexionMaxDeg = 0;
  fingerAbductionMaxRatio = 0;
  thumbIndexMinDistanceRatio = Infinity;
  stepStartBodyState = null;
  dynamicTargetPos = null;
  lapTargetCalibration = {samples:[], target:null, ready:false, announced:false};
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

function landmarkIsUsable(point, minVisibility=0.45){
  return !!point
    && Number.isFinite(point.x)
    && Number.isFinite(point.y)
    && (point.visibility == null || point.visibility >= minVisibility);
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

function lapTargetCandidate(lm){
  if(!lm || lm.length < 33) return null;
  const affected = sideLandmarks(lm, AFFECTED_SIDE);
  const leftShoulder = lm[11];
  const rightShoulder = lm[12];
  const leftHip = lm[23];
  const rightHip = lm[24];
  if(!landmarkIsUsable(affected.hip)
    || !landmarkIsUsable(affected.knee)
    || !landmarkIsUsable(leftShoulder)
    || !landmarkIsUsable(rightShoulder)
    || !landmarkIsUsable(leftHip)
    || !landmarkIsUsable(rightHip)) return null;

  const midShoulder = midpoint(leftShoulder, rightShoulder);
  const midHip = midpoint(leftHip, rightHip);
  const torsoLength = distance(midShoulder, midHip);
  const thighLength = distance(affected.hip, affected.knee);
  if(torsoLength < 0.07 || thighLength < 0.045) return null;

  // If the ankle is visible, reject a near-standing leg. Otherwise rely on
  // stable torso/hip tracking so partial phone framing can still calibrate.
  if(landmarkIsUsable(affected.ankle, 0.35)){
    const kneeAngle = jointAngleDeg(affected.hip, affected.knee, affected.ankle);
    if(kneeAngle > 158) return null;
  }

  // The upper surface of the affected thigh is a patient-specific lap anchor.
  // Bias slightly toward the hip so the target remains comfortably reachable.
  const anatomical = {
    x: affected.hip.x * 0.58 + affected.knee.x * 0.42,
    y: affected.hip.y * 0.58 + affected.knee.y * 0.42 + Math.min(0.018, torsoLength * 0.06),
  };
  const screenPoint = mirrorX(anatomical);
  return {
    x: Math.max(0.10, Math.min(0.90, screenPoint.x)),
    y: Math.max(0.50, Math.min(0.90, screenPoint.y)),
    shoulderWidth: Math.max(0.03, distance(leftShoulder, rightShoulder)),
    bodyX:(midShoulder.x + midHip.x) / 2,
    bodyY:(midShoulder.y + midHip.y) / 2,
  };
}

function updateLapTargetCalibration(lm, now){
  const step = getCurrentStep();
  if(!isLapTarget(step) || lapTargetCalibration.ready) return;
  const candidate = lapTargetCandidate(lm);
  if(!candidate){
    lapTargetCalibration.samples = [];
    lapTargetCalibration.target = null;
    dynamicTargetPos = null;
    return;
  }

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

  const center = {x:medianValue(samples.map(s => s.x)), y:medianValue(samples.map(s => s.y))};
  lapTargetCalibration.target = center;
  dynamicTargetPos = center;
  if(samples.length < LAP_CALIBRATION_MIN_SAMPLES) return;

  const duration = samples[samples.length-1].t - samples[0].t;
  const width = medianValue(samples.map(s => s.shoulderWidth)) || 0.03;
  const maxJitter = Math.max(0.018, width * 0.12);
  const bodyCenter = {
    x:medianValue(samples.map(s => s.bodyX)),
    y:medianValue(samples.map(s => s.bodyY)),
  };
  const stable = samples.every(s =>
    Math.hypot(s.x-center.x, s.y-center.y) <= maxJitter
    && Math.hypot(s.bodyX-bodyCenter.x, s.bodyY-bodyCenter.y) <= maxJitter
  );
  if(!stable || duration < LAP_CALIBRATION_MIN_MS) return;

  lapTargetCalibration.ready = true;
  dynamicTargetPos = center;
  if(!lapTargetCalibration.announced){
    lapTargetCalibration.announced = true;
    postRN({
      type:"lap_target_calibrated",
      task_id:tasks[currentTaskIdx].id,
      step_id:step.id,
      x:+center.x.toFixed(4),
      y:+center.y.toFixed(4),
      sample_count:samples.length,
    });
  }
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
  gaitPelvisTravelMaxRatio = Math.max(gaitPelvisTravelMaxRatio, pelvisTravel);
  gaitAffectedAnkleTravelMaxRatio = Math.max(gaitAffectedAnkleTravelMaxRatio, ankleMove);
  gaitUnaffectedAnkleTravelMaxRatio = Math.max(gaitUnaffectedAnkleTravelMaxRatio, unaffectedAnkleMove);
  const leadDelta = state.affected.ankle.x - state.unaffected.ankle.x;
  const lead = Math.abs(leadDelta) > Math.max(0.025, state.legLength * 0.08) ? (leadDelta > 0 ? 1 : -1) : 0;
  if(lead && lastGaitLead && lead !== lastGaitLead) gaitAlternationCount += 1;
  if(lead) lastGaitLead = lead;
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

function handPalmCenter(){
  if(!latestHandLandmarks || latestHandLandmarks.length < 21) return null;
  const h = latestHandLandmarks;
  return mirrorX({x:(h[0].x + h[5].x + h[17].x)/3, y:(h[0].y + h[5].y + h[17].y)/3});
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
    // MediaPipe Pose: 9 = mouth_left, 10 = mouth_right
    const m = {x:(lm[9].x+lm[10].x)/2, y:(lm[9].y+lm[10].y)/2};
    return mirrorX(m);
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
    return lapTargetCalibration.target || {x: step.target.x, y: step.target.y};
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
  if(which === "MOUTH" || which === "CHEST"){
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
  const vIndex = {x:h[5].x-h[0].x, y:h[5].y-h[0].y, z:(h[5].z||0)-(h[0].z||0)};
  const vPinky = {x:h[17].x-h[0].x, y:h[17].y-h[0].y, z:(h[17].z||0)-(h[0].z||0)};
  const normal = {
    x: vIndex.y*vPinky.z - vIndex.z*vPinky.y,
    y: vIndex.z*vPinky.x - vIndex.x*vPinky.z,
    z: vIndex.x*vPinky.y - vIndex.y*vPinky.x,
  };
  const normalMag = Math.max(0.0001, Math.hypot(normal.x, normal.y, normal.z));
  const signedPlaneFacing = normal.z / normalMag;
  const expectedPalmSign = latestHandedness === "Right" ? 1 : (latestHandedness === "Left" ? -1 : 0);
  const signedPalmTowardCamera = expectedPalmSign ? signedPlaneFacing * expectedPalmSign : signedPlaneFacing;
  const planeFacesCamera = clamp01((signedPalmTowardCamera - 0.08) / 0.52);
  const palmSpreadRatio = clamp01((palmWidth / palmHeight - 0.35) / 0.45);
  const palmDepthTilt = Math.abs((h[5].z||0) - (h[17].z||0)) / palmWidth;
  const depthFlatness = clamp01(1 - palmDepthTilt / 0.35);
  const palmFacing = clamp01(planeFacesCamera * 0.65 + palmSpreadRatio * 0.25 + depthFlatness * 0.10);
  palmFacingScore = palmFacingScore * 0.6 + palmFacing * 0.4;
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
  // Tighter radius — about 0.55 × shoulder-width for most targets,
  // 0.70 × for body-anchored targets (MOUTH/CHEST) since they're depth-tricky.
  const which = step.target.landmark;
  let r = Math.max(baseR, sw * 0.55);
  if(which === "MOUTH" || which === "CHEST"){
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
  if(isLapTarget(step) && lm) return mirrorX(sideLandmarks(lm, AFFECTED_SIDE).wrist);
  if(isHandTask()){
    return activeHandPoint();
  }
  if(!lm) return null;
  // pick the wrist closer to the current effective target
  if(!step) return mirrorX(lm[15]);
  const target = getEffectiveTargetXY(step);
  const lW = mirrorX(lm[15]); const rW = mirrorX(lm[16]);
  const dL = lW ? Math.hypot(lW.x - target.x, lW.y - target.y) : Infinity;
  const dR = rW ? Math.hypot(rW.x - target.x, rW.y - target.y) : Infinity;
  return dL < dR ? lW : rW;
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
    : Math.max(0.12, shoulderWidth(lm) * 0.75);
  if(distXY(w, stepStartWristXY) >= requiredMove) arrivedAfterMovement = true;
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
  if(!isHandTask() && !arrivedAfterMovement && step.movement_required !== false){
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
  if(step.id === "H1-S1" && palmFacingScore <= 0.45){
    return {reason:"palm_not_facing", guidance:"Keep your hand in the circle and turn your palm toward the camera."};
  }
  if(step.id === "H2-S2" || (Array.isArray(step.measure) && step.measure.includes("closure_completeness")) || which === "HAND_CLOSED"){
    return {reason:"hand_not_closed", guidance:"Keep your hand in the center of the circle and gently close your fingers around the imaginary object."};
  }
  if(which === "HAND_OPEN"){
    if(step.id === "H1-S2" && palmFacingScore <= 0.45){
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
  if(which === "WALK_READY") return standing;
  if(which === "WALK_ACROSS"){
    return gaitPelvisTravelMaxRatio > 0.35
      && gaitAffectedAnkleTravelMaxRatio > 0.16
      && gaitUnaffectedAnkleTravelMaxRatio > 0.16
      && gaitAlternationCount >= 2;
  }
  if(which === "WALK_STOPPED") return standing && pelvisSwayForStop() < 0.08;
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
    const affectedWrist = mirrorX(affectedWristRaw);
    return distXY(affectedWrist, targetXY) < effectiveRadius(step, landmarks);
  }
  if(isHandTask()){
    const target = step.target;
    const which = target.landmark;
    const point = activeHandPoint();
    if(!point) return false;
    const R = effectiveRadius(step, null);
    const near = Math.hypot(point.x - target.x, point.y - target.y) < R;
    if(step.id === "H1-S1"){
      return near && palmFacingScore > 0.45 && handOpenScore < 0.72;
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
      const palmOk = step.id !== "H1-S2" || palmFacingScore > 0.45;
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
  if(!arrivedAfterMovement) return false;

  const target = step.target;
  const which = target.landmark;
  const targetXY = getEffectiveTargetXY(step);
  const R = effectiveRadius(step, landmarks);

  const wristDist = () => {
    const lW = mirrorX(landmarks[15]);
    const rW = mirrorX(landmarks[16]);
    const dL = lW ? Math.hypot(lW.x - targetXY.x, lW.y - targetXY.y) : Infinity;
    const dR = rW ? Math.hypot(rW.x - targetXY.x, rW.y - targetXY.y) : Infinity;
    return Math.min(dL, dR);
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
  if(which === "MOUTH" || which === "CHEST"){
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
  const step = getCurrentStep();
  if(!step) return;
  if(isLapTarget(step) && !lapTargetCalibration.ready) return;
  const targetXY = getEffectiveTargetXY(step);
  const tx = targetXY.x * canvas.width;
  const ty = targetXY.y * canvas.height;
  // Visual radius MATCHES the actual hit radius — so what the user sees == what triggers.
  const effR = effectiveRadius(step, landmarks);
  const tr = effR * Math.min(canvas.width, canvas.height);
  const armed = (voiceFinishedAt > 0) && (performance.now() - voiceFinishedAt >= 350) && arrivedAfterMovement;
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
    const res = await fetch(`${API_BASE}/assessment/submit`,{
      method:"POST", headers:{"Content-Type":"application/json", ...(CURRENT_USER_ID ? {"X-User-Id": CURRENT_USER_ID} : {})},
      body: JSON.stringify({
        task_results: taskResults.filter(Boolean),
        affected_side: AFFECTED_SIDE,
        assessment_package: ASSESSMENT_PACKAGE,
        motion_data: {
          schema_version: "1.0",
          coordinate_space: {
            pose_2d: "camera_normalized_unmirrored",
            pose_world_3d: "mediapipe_estimated_world_landmarks",
            hand_2d: "camera_normalized_unmirrored",
          },
          sample_interval_ms: MOTION_SAMPLE_INTERVAL_MS,
          truncated: motionFrames.length >= MAX_MOTION_FRAMES,
          frames: motionFrames,
        },
      })
    });
    const data = await res.json();
    postRN({type:"assessment_complete", assessment: data});
  }catch(e){
    postRN({type:"assessment_error", message:String(e)});
  }
}

function loop(){
  if(!running) return;
  const now = performance.now();
  let landmarks = latestPoseLandmarks;
  const handBackoff = isHandPerformanceBackoff();
  const poseScanInterval = isHandTask()
    ? (handBackoff ? HAND_BACKOFF_POSE_SCAN_INTERVAL_MS : HAND_PACKAGE_POSE_SCAN_INTERVAL_MS)
    : POSE_SCAN_INTERVAL_MS;
  if(landmarker && (now - lastPoseScanTs) >= poseScanInterval){
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
  if(handLandmarker && handNeeded && (now - lastHandScanTs) >= handScanInterval){
    lastHandScanTs = now;
    try{
      const hr = handLandmarker.detectForVideo(video, now);
      if(hr && hr.landmarks && hr.landmarks[0]){
        latestHandLandmarks = hr.landmarks[0];
        const rawHandedness = (hr.handednesses && hr.handednesses[0] && hr.handednesses[0][0] && hr.handednesses[0][0].categoryName) || "";
        latestHandedness = rawHandedness === "Right" ? "Left" : (rawHandedness === "Left" ? "Right" : latestHandedness || "");
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
  computeHandMetrics();
  updateTargetAttemptTracking(landmarks);
  captureMotionFrame(now);
  detectAxonAIMarker(now);
  updateRuntimeDiagnostics(now);

  drawOverlay(landmarks);

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

startBtn.addEventListener("click", async () => {
  const unlockPromise = unlockAudioPlayback();
  overlay.classList.add("hidden");
  startBtn.disabled = true;
  await ensureTasksLoaded();
  const firstStep = tasks[currentTaskIdx] && tasks[currentTaskIdx].steps && tasks[currentTaskIdx].steps[0];
  const firstVoicePromise = firstStep && firstStep.voice
    ? fetchVoiceAudio(firstStep.voice).catch(() => null)
    : Promise.resolve(null);
  const camOk = await setupCamera();
  if(!camOk){ overlay.classList.remove("hidden"); return; }
  await setupTrackingModels();
  await Promise.allSettled([unlockPromise, firstVoicePromise]);
  running = true;
  requestAnimationFrame(loop);
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
        "name": "Wall Slides + Active Shoulder Flexion",
        "reps": 5,
        "pose_mode": "body",
        "setup_voice": "We will work on shoulder elevation. Stand or sit tall with your arms at your sides. Slowly raise your affected arm forward and up toward the target above. Let's begin.",
        "cycle": [
            {"caption": "Raise arm overhead", "voice": "Slowly raise your arm upward toward the target.", "target": {"x": 0.5, "y": 0.18, "r": 0.10}, "hold_ms": 1500},
            {"caption": "Lower arm slowly", "voice": "Now lower your arm to your side, slowly and controlled.", "target": {"x": 0.5, "y": 0.85, "r": 0.10}, "hold_ms": 1500},
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
        "setup_voice": "We will practice grasping and transporting a cup. Imagine a cup on the table to your side. Reach, grasp it, move it across your body, and release.",
        "cycle": [
            {"caption": "Reach and grasp", "voice": "Reach to the cup on your side and pretend to grasp it.", "target": {"x": 0.30, "y": 0.55, "r": 0.10}, "hold_ms": 1200},
            {"caption": "Transport across", "voice": "Now move the cup across to the other side, controlled and steady.", "target": {"x": 0.70, "y": 0.55, "r": 0.10}, "hold_ms": 1500},
            {"caption": "Release and return", "voice": "Release the cup and bring your hand back to your lap.", "target": {"x": 0.5, "y": 0.78, "r": 0.10}, "hold_ms": 1200},
        ],
        "feedback_rules": [
            {"if": "trunk_lean_deg > 18", "say": "I noticed your trunk twisted with the cup. On the next repetition, try keeping your shoulders square and let your arm cross the midline."},
            {"if": "reach_completion < 0.6", "say": "Almost reached the far target. On the next try, extend a little further across your body."},
            {"default": "Beautiful transport. On the next repetition, focus on a smooth release at the end."},
        ],
    },
    "ex_handopen": {
        "name": "Finger Extension with Rubber Band",
        "reps": 8,
        "pose_mode": "tap",
        "setup_voice": "We will work on opening your hand. Place a soft rubber band around your fingers and thumb. Slowly open your hand against the resistance, then relax. Tap I did one repetition each time you complete one.",
        "cycle": [
            {"caption": "Open hand wide, then relax", "voice": "Slowly open your hand against the band, hold, then relax. Tap the button when you finish one repetition.", "target": None, "hold_ms": 0},
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


def _rehab_runner_html(exercise_id: str) -> str:
    import json as _json
    cfg = REHAB_RUNNER_CONFIG.get(exercise_id) or REHAB_RUNNER_CONFIG["ex_maintenance"]
    cfg_json = _json.dumps(cfg)
    return REHAB_RUNNER_HTML_TEMPLATE.replace("__CFG_JSON__", cfg_json)


@api_router.get("/rehab/runner", response_class=HTMLResponse)
async def rehab_runner(exercise_id: str = "ex_maintenance"):
    return HTMLResponse(content=_rehab_runner_html(exercise_id))


REHAB_RUNNER_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no" />
<title>Rehab Exercise</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{width:100%;height:100%;background:#0c100e;color:#fdfdfd;font-family:-apple-system,BlinkMacSystemFont,"Plus Jakarta Sans",sans-serif;overflow:hidden}
  #stage{position:relative;width:100vw;height:100vh;background:#000}
  video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
  canvas{position:absolute;inset:0;width:100%;height:100%;transform:scaleX(-1)}
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
  <video id="video" playsinline autoplay muted></video>
  <canvas id="canvas"></canvas>
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
import { PoseLandmarker, HandLandmarker, FilesetResolver, DrawingUtils } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

const API_BASE = window.location.origin + "/api";
const CFG = __CFG_JSON__;

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
  if(!text) return;
  try{
    voiceText.textContent = "Playing instruction…";
    const key = `nova::${text}`;
    let request = voiceAudioCache.get(key) ? Promise.resolve(voiceAudioCache.get(key)) : voiceAudioInflight.get(key);
    if(!request){
      request = fetch(`${API_BASE}/tts/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})})
        .then(async res => {
          if(!res.ok) throw new Error("tts fail");
          const data = await res.json();
          voiceAudioCache.set(key, data.audio_b64);
          return data.audio_b64;
        })
        .finally(() => voiceAudioInflight.delete(key));
      voiceAudioInflight.set(key, request);
    }
    const audioB64 = await request;
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
    voiceText.textContent = "—";
  }catch(e){
    voiceText.textContent = "Using device voice";
    const spoke = await playBrowserVoice(text);
    voiceText.textContent = spoke ? "—" : "Voice unavailable — follow on-screen text";
  }
}

async function setupCamera(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:1280},height:{ideal:720}},audio:false});
    video.srcObject = stream;
    await new Promise(r => video.onloadedmetadata = r);
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    return true;
  }catch(e){
    captionEl.textContent = "Camera permission denied.";
    postRN({type:"camera_error", message: String(e)});
    return false;
  }
}

async function setupPose(){
  const fr = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  landmarker = await PoseLandmarker.createFromOptions(fr,{
    baseOptions:{modelAssetPath:"https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"},
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
  if(CFG.pose_mode === "tap"){
    tapBtn.classList.remove("hidden");
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
  await playVoice(sub.voice);
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
  lastRepScore = computeRepScore();
  const label = scoreLabel(lastRepScore);
  fbStep.textContent = `Repetition ${currentRep+1} of ${CFG.reps} complete · ${label}`;
  fbTitle.textContent = `Your score: ${lastRepScore}/100`;
  fbBody.textContent = feedback;
  if(navigator.vibrate) navigator.vibrate([50, 30, 80]);
  fbEl.classList.remove("hidden");
  requestAnimationFrame(() => fbEl.classList.add("show"));
  postRN({type:"rep_complete", rep: currentRep+1, total: CFG.reps, score: lastRepScore, feedback});

  // Voice: feedback + ask for "yes"
  await playVoice(`Your score is ${lastRepScore} out of 100. ${label}. ${feedback} When you're ready, tap continue, or say yes to keep going.`);
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
  postRN({type:"exercise_complete", exercise_id: location.search});
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
  if(CFG.pose_mode !== "tap") return;
  showFeedback();
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
  const setupVoicePromise = fetch(`${API_BASE}/tts/generate`,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({text:CFG.setup_voice})
  }).then(async res => {
    if(!res.ok) throw new Error("tts prefetch failed");
    const data = await res.json();
    voiceAudioCache.set(`nova::${CFG.setup_voice}`, data.audio_b64);
  }).catch(() => null);
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
async def reminders_status():
    """Computes whether the patient is overdue on daily exercise or weekly assessment."""
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
    email = email.lower()
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
        "id": "u_" + str(uuid.uuid4())[:12],
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
    months_since_stroke: Optional[int] = None
    side_affected: Optional[str] = None    # "left" | "right" | "both" | "unsure"
    affected_areas: Optional[List[str]] = None
    affected_areas_other: Optional[str] = None
    dominant_hand: Optional[str] = None    # "left" | "right" | "ambidextrous"
    mobility_level: Optional[str] = None   # "wheelchair" | "walker" | "cane" | "independent"
    primary_goal: Optional[str] = None     # free text
    secondary_goals: Optional[List[str]] = None
    medical_conditions: Optional[List[str]] = None
    medical_conditions_other: Optional[str] = None
    has_caregiver: Optional[bool] = None
    notes: Optional[str] = None


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


async def _build_patient_context() -> str:
    """Pulls the latest assessment so the assistant knows the patient's situation."""
    doc = await db.assessments.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not doc:
        return "The patient has not completed an assessment yet."
    issues = [f"- {i['label']}: {i['description']}" for i in doc.get("functional_issues", [])]
    plan = [f"- {e['name']} ({e['sets']}×{e['reps']}, {e['frequency']})" for e in doc.get("rehab_plan", [])]
    return (
        "Latest assessment date: " + doc.get("created_at", "unknown") + "\n"
        "Affected side: " + doc.get("affected_side", "unknown") + "\n\n"
        "FUNCTIONAL ISSUES IDENTIFIED:\n" + ("\n".join(issues) or "(none yet)") + "\n\n"
        "CURRENT REHAB PLAN:\n" + ("\n".join(plan) or "(no plan yet)")
    )


CHAT_SYSTEM_PROMPT_BASE = """You are "Aria" — a warm, calm, deeply empathetic AI recovery companion for a stroke survivor. You are NOT a doctor; you are a supportive friend who happens to know about stroke rehabilitation.

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

When you don't know something, say so warmly and suggest asking their therapist.

If the patient seems distressed, gently acknowledge it, sit with them, and only suggest a tiny actionable step if they seem ready.

Keep replies under 4 short sentences unless the patient asks for more detail."""


@api_router.post("/chat/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest, request: Request):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="Chat unavailable — LLM key not configured.")
    # Load previous turns from MongoDB
    sess = await db.chat_sessions.find_one({"session_id": req.session_id}, {"_id": 0})
    turns: List[Dict[str, Any]] = sess["turns"] if sess else []

    # Build patient context (refreshed every turn so new assessments propagate)
    patient_ctx = await _build_patient_context()
    # Inject preferred name from the signed-in user's onboarding profile, if available.
    user = await _user_from_header(dict(request.headers))
    name = ""
    if user:
        prof = user.get("profile") or {}
        name = (prof.get("preferred_name") or user.get("name") or "").split(" ")[0].strip()
    name_block = f"\nPATIENT PREFERRED NAME: {name}\n" if name else ""
    system_prompt = CHAT_SYSTEM_PROMPT_BASE + name_block + "\n----\nPATIENT CONTEXT:\n" + patient_ctx

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=req.session_id,
        system_message=system_prompt,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    # Replay history (LlmChat is stateless per-instance, so we replay)
    # The library accumulates history within the instance. We rebuild for stateless requests by
    # constructing a single "history-aware" message stub. For simplicity here, we rely on backend
    # session storage and pass only the new user message; the library will only see this turn.
    # That's acceptable because we inject relevant patient context every turn — recent dialogue is
    # included via the last few turns in the system prompt extension below.
    if turns:
        recent = "\n".join(f"{t['role'].upper()}: {t['text']}" for t in turns[-6:])
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=req.session_id,
            system_message=system_prompt + "\n\n----\nRECENT CONVERSATION:\n" + recent,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    try:
        response = await chat.send_message(UserMessage(text=req.text))
        reply_text = response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=502, detail=f"Chat error: {str(e)[:200]}")

    now = datetime.now(timezone.utc).isoformat()
    turns.append({"role": "user", "text": req.text, "ts": now})
    turns.append({"role": "assistant", "text": reply_text, "ts": now})
    await db.chat_sessions.update_one(
        {"session_id": req.session_id},
        {"$set": {"session_id": req.session_id, "turns": turns, "updated_at": now}},
        upsert=True,
    )
    return ChatResponse(session_id=req.session_id, text=reply_text, turns=len(turns))


@api_router.get("/chat/history")
async def chat_history(session_id: str):
    sess = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
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
    sess = await db.chat_sessions.find_one({"session_id": req.session_id}, {"_id": 0})
    has_history = bool(sess and sess.get("turns"))
    has_assessment = False
    if user:
        has_assessment = bool(await db.assessments.find_one({"user_id": user["id"]}, {"_id": 1}))
    n = f", {name}" if name else ""

    if not has_assessment:
        pool = [
            f"Hi{n}. I'm Aria — your recovery companion. Whenever you're ready, taking that first assessment will help me support you. How are you feeling today?",
            f"Hello{n}. I'm here whenever you need to talk. Have you had a chance to do your first movement check yet?",
            f"Hi{n}, I'm Aria. How are you doing today?",
        ]
    elif not has_history:
        pool = [
            f"Hi{n}, I'm Aria. I saw your assessment results — thank you for trusting me. How are you feeling today, gently?",
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
    """Returns N varied caring proactive messages — for the floating Aria bubble on Home."""
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
        await db.users.update_one({"id": user["id"]}, {"$set": {"google": extras}})
    return user


# ============ Progress dashboard ============
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
