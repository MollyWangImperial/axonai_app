from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import base64
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone

from elevenlabs.client import ElevenLabs

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ElevenLabs
ELEVEN_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVEN_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaC")
eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)

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


class FunctionalIssue(BaseModel):
    code: str
    label: str
    description: str
    source: str
    severity: str  # mild | moderate | severe
    related_task: str


class RehabExercise(BaseModel):
    id: str
    name: str
    description: str
    sets: int
    reps: int
    frequency: str  # e.g. "Daily"
    targets_issue: str
    source: str


class Assessment(BaseModel):
    id: str
    created_at: str
    affected_side: str
    task_results: List[TaskResult]
    functional_issues: List[FunctionalIssue]
    rehab_plan: List[RehabExercise]


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
                "voice": "Welcome. Let's begin with a seated forward reach. Please sit upright with your back away from the chair, and place your hand on your lap. Take a deep breath when you're ready.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Start position: hand on lap",
            },
            {
                "id": "T1-S2",
                "voice": "Now, slowly reach your affected arm forward, as far as you comfortably can, toward the bright circle in front of you. Keep your back straight and stay relaxed.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Reach forward to the target",
                "measure": ["reach_distance", "trunk_lean", "elbow_extension"],
            },
            {
                "id": "T1-S3",
                "voice": "Wonderful effort. Slowly bring your hand back to your lap. You are doing great.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Return to lap",
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
                "voice": "Next, we will raise your arm. Stand or sit tall, with your arms relaxed by your side. I'm here to guide you.",
                "target": {"x": 0.5, "y": 0.85, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Arm relaxed at your side",
            },
            {
                "id": "T2-S2",
                "voice": "Slowly raise your affected arm forward and upward, reaching toward the target above. Keep your shoulder relaxed and avoid hiking it up.",
                "target": {"x": 0.5, "y": 0.18, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Raise arm upward",
                "measure": ["shoulder_flexion_rom", "shoulder_hike", "trunk_lean"],
            },
            {
                "id": "T2-S3",
                "voice": "Beautiful. Now, gently lower your arm back to your side.",
                "target": {"x": 0.5, "y": 0.85, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Lower arm",
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
                "voice": "Let's try bringing your hand to your mouth. Place your hand on your lap to start. You're doing wonderfully.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Start with hand on lap",
            },
            {
                "id": "T3-S2",
                "voice": "Now, slowly bring your hand up to your mouth, as if you were drinking from a cup. Keep your head still and stay upright.",
                "target": {"x": 0.5, "y": 0.30, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Hand to mouth",
                "measure": ["elbow_flexion", "trunk_lean", "coordination"],
            },
            {
                "id": "T3-S3",
                "voice": "Great job. Lower your hand back to your lap.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Return to lap",
            },
        ],
    },
    {
        "id": "T4",
        "title": "Grasp Cup and Move to Target",
        "view": "Front view",
        "focus": "Grasp, release, movement quality, endpoint control, trunk compensation",
        "steps": [
            {
                "id": "T4-S1",
                "voice": "Imagine a cup is on the table in front of you. Reach with your affected hand toward the cup at this lower position.",
                "target": {"x": 0.35, "y": 0.70, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Reach for the cup",
            },
            {
                "id": "T4-S2",
                "voice": "Pretend to close your fingers around the cup, then carefully move it sideways to the target on your other side.",
                "target": {"x": 0.70, "y": 0.50, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Move cup across to target",
                "measure": ["endpoint_accuracy", "trunk_lean", "movement_smoothness"],
            },
            {
                "id": "T4-S3",
                "voice": "Excellent control. Now gently release the cup and bring your hand back.",
                "target": {"x": 0.35, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Release and return",
            },
        ],
    },
    {
        "id": "T5",
        "title": "Open Hand, Grasp Ball, Release",
        "view": "Front view",
        "focus": "Hand opening, wrist control, grasp, release",
        "steps": [
            {
                "id": "T5-S1",
                "voice": "Hold your affected hand up in front of you, around chest height. Keep your wrist steady.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Raise hand to chest",
            },
            {
                "id": "T5-S2",
                "voice": "Open your hand as wide as you can, then slowly close it as if you are grasping a soft ball. Repeat this opening and closing slowly.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 3500,
                "caption": "Open and close hand around a ball",
                "measure": ["hand_opening", "grasp_release"],
            },
            {
                "id": "T5-S3",
                "voice": "Beautiful work. Lower your hand to rest.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Lower hand to rest",
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
            },
            {
                "id": "T6-S2",
                "voice": "Now, slowly touch the tip of your thumb to the tip of your index finger, as if you were pinching a small coin. Hold for a moment.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 3000,
                "caption": "Pinch thumb and index finger",
                "measure": ["pinch_grip"],
            },
            {
                "id": "T6-S3",
                "voice": "Lovely. Relax and lower your hand.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.10, "landmark": "WRIST"},
                "hold_ms": 1500,
                "caption": "Lower hand to rest",
            },
        ],
    },
    {
        "id": "T7",
        "title": "Fold Towel / Open Bottle (Two-Handed)",
        "view": "Front view",
        "focus": "Affected-side participation, bilateral coordination",
        "steps": [
            {
                "id": "T7-S1",
                "voice": "Our last task uses both hands together. Bring both hands up in front of you, around chest height.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS"},
                "hold_ms": 1500,
                "caption": "Both hands up at chest",
            },
            {
                "id": "T7-S2",
                "voice": "Pretend to fold a towel. Move both hands together, bringing them inward to meet in front of you, then outward. Make sure both hands move equally.",
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS"},
                "hold_ms": 3500,
                "caption": "Fold towel with both hands",
                "measure": ["bilateral_symmetry", "affected_participation"],
            },
            {
                "id": "T7-S3",
                "voice": "Magnificent work! You've finished the assessment. Lower your hands and relax.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.12, "landmark": "WRISTS"},
                "hold_ms": 1500,
                "caption": "Lower hands - assessment complete",
            },
        ],
    },
]


# ============ Functional Issue Rules ============
# Sources: Fugl-Meyer Upper Extremity Assessment (Fugl-Meyer, 1975);
# Action Research Arm Test (Lyle, 1981); Stroke Rehabilitation: A Function-Based Approach (Gillen);
# Bobath / NDT principles; Task-Specific Training (Carr & Shepherd).
def derive_functional_issues(task_results: List[TaskResult]) -> List[FunctionalIssue]:
    issues: List[FunctionalIssue] = []
    by_id = {t.task_id: t for t in task_results}

    def add(code, label, description, source, severity, related):
        issues.append(FunctionalIssue(
            code=code, label=label, description=description,
            source=source, severity=severity, related_task=related,
        ))

    t1 = by_id.get("T1")
    if t1:
        if t1.completed_steps < t1.total_steps:
            add("REACH_INCOMPLETE", "Reduced forward reach",
                "The patient was unable to complete the full forward reach within the allotted time, indicating impaired shoulder flexion and/or elbow extension.",
                "Fugl-Meyer UE; ARAT", "moderate", "T1")
        trunk = t1.metrics.get("trunk_lean_deg", 0)
        if isinstance(trunk, (int, float)) and trunk > 15:
            add("TRUNK_COMP", "Excessive trunk compensation",
                "Trunk lean exceeded normal limits during forward reach, suggesting compensation for limited shoulder/elbow ROM.",
                "Levin & Michaelsen (Trunk Restraint Reaching)", "mild", "T1")

    t2 = by_id.get("T2")
    if t2:
        if t2.completed_steps < t2.total_steps:
            add("SHOULDER_FLEX_LIMITED", "Limited shoulder flexion",
                "Patient could not reach the overhead target, indicating restricted shoulder flexion/abduction range of motion.",
                "Fugl-Meyer UE (Synergistic Movement)", "moderate", "T2")
        if t2.metrics.get("shoulder_hike", False):
            add("SHOULDER_HIKE", "Scapular elevation compensation (shoulder hike)",
                "Shoulder girdle elevation observed during reach — common compensatory pattern after stroke.",
                "Bobath / NDT principles", "mild", "T2")

    t3 = by_id.get("T3")
    if t3 and t3.completed_steps < t3.total_steps:
        add("H2M_IMPAIRED", "Impaired hand-to-mouth function",
            "Patient could not complete a hand-to-mouth movement, an essential ADL for feeding and grooming.",
            "Chedoke-McMaster Stroke Assessment", "moderate", "T3")

    t4 = by_id.get("T4")
    if t4 and t4.completed_steps < t4.total_steps:
        add("GROSS_GRASP", "Impaired gross grasp & transport",
            "Difficulty grasping and transporting an object across the workspace, indicating reduced upper-limb selective control.",
            "ARAT (Grasp subscale)", "moderate", "T4")

    t5 = by_id.get("T5")
    if t5 and t5.completed_steps < t5.total_steps:
        add("HAND_OPENING", "Impaired active hand opening",
            "Finger extension weakness — a hallmark deficit after stroke, frequently addressed with CIMT and EMG-triggered stimulation.",
            "Constraint-Induced Movement Therapy (Taub)", "moderate", "T5")

    t6 = by_id.get("T6")
    if t6 and t6.completed_steps < t6.total_steps:
        add("PINCH_IMPAIRED", "Impaired fine pinch",
            "Difficulty isolating thumb-index opposition; affects buttoning, writing, and other fine motor tasks.",
            "Jebsen Hand Function Test", "mild", "T6")

    t7 = by_id.get("T7")
    if t7 and t7.completed_steps < t7.total_steps:
        add("BILATERAL_NONUSE", "Reduced affected-side participation",
            "During the bilateral task, the affected limb participated minimally — characteristic learned non-use.",
            "CIMT / Bilateral Arm Training (BATRAC)", "moderate", "T7")

    if not issues:
        issues.append(FunctionalIssue(
            code="NO_ISSUES",
            label="No major functional limitations detected",
            description="The patient completed all tasks. Continue maintenance exercises and progressive challenges.",
            source="Clinical observation",
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
        id="ex_wallslide", name="Wall Slides + Active Shoulder Flexion",
        description="Stand facing a wall. Slide forearms up the wall as high as possible, keeping shoulders relaxed.",
        sets=3, reps=10, frequency="Twice daily",
        targets_issue="SHOULDER_FLEX_LIMITED", source="Fugl-Meyer UE; Bobath",
    ),
    "SHOULDER_HIKE": RehabExercise(
        id="ex_scapdepress", name="Scapular Depression Practice",
        description="Sit tall. Gently depress shoulders downward and away from ears, then reach without elevating shoulder.",
        sets=3, reps=10, frequency="Daily",
        targets_issue="SHOULDER_HIKE", source="Bobath / NDT principles",
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
        id="ex_handopen", name="Finger Extension with Rubber Band",
        description="Place a rubber band around fingers. Open hand against light resistance. Slow, controlled extension.",
        sets=3, reps=15, frequency="Twice daily",
        targets_issue="HAND_OPENING", source="CIMT protocol (Taub et al.)",
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
    "NO_ISSUES": RehabExercise(
        id="ex_maintenance", name="Maintenance Conditioning",
        description="Continue full-ROM stretches, light resistance work, and functional ADL practice.",
        sets=2, reps=15, frequency="Daily",
        targets_issue="NO_ISSUES", source="General stroke rehab guidelines",
    ),
}


def build_rehab_plan(issues: List[FunctionalIssue]) -> List[RehabExercise]:
    seen = set()
    plan: List[RehabExercise] = []
    for issue in issues:
        ex = EXERCISE_LIBRARY.get(issue.code)
        if ex and ex.id not in seen:
            plan.append(ex)
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
async def get_tasks():
    return {"tasks": TASKS_DATA, "voice_id": ELEVEN_VOICE_ID}


@api_router.post("/tts/generate", response_model=TTSResponse)
async def generate_tts(req: TTSRequest):
    voice_id = req.voice_id or ELEVEN_VOICE_ID
    try:
        audio_iter = eleven_client.text_to_speech.convert(
            text=req.text,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        audio_bytes = b"".join(audio_iter)
        return TTSResponse(audio_b64=base64.b64encode(audio_bytes).decode(), text=req.text)
    except Exception as e:
        msg = str(e)
        logger.error(f"TTS error: {msg}")
        if "missing_permissions" in msg or "401" in msg:
            raise HTTPException(
                status_code=503,
                detail="Voice service unavailable: ElevenLabs API key lacks text_to_speech permission. Enable it at https://elevenlabs.io/app/settings/api-keys.",
            )
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {msg[:200]}")


@api_router.get("/tts/health")
async def tts_health():
    """Diagnostic: check whether the configured ElevenLabs key can synthesize speech."""
    try:
        audio_iter = eleven_client.text_to_speech.convert(
            text="ok",
            voice_id=ELEVEN_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        b = b"".join(audio_iter)
        return {"ok": True, "bytes": len(b)}
    except Exception as e:
        msg = str(e)
        scope_missing = "missing_permissions" in msg or "401" in msg
        return {
            "ok": False,
            "scope_missing": scope_missing,
            "hint": (
                "Open https://elevenlabs.io/app/settings/api-keys, edit the key, "
                "enable 'Text to Speech' permission, then save."
                if scope_missing else "Check key validity / network."
            ),
            "error": msg[:300],
        }


@api_router.post("/assessment/submit", response_model=Assessment)
async def submit_assessment(payload: AssessmentSubmit):
    issues = derive_functional_issues(payload.task_results)
    plan = build_rehab_plan(issues)
    assessment = Assessment(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        affected_side=payload.affected_side,
        task_results=payload.task_results,
        functional_issues=issues,
        rehab_plan=plan,
    )
    await db.assessments.insert_one(assessment.dict())
    return assessment


@api_router.get("/assessment/history", response_model=List[Assessment])
async def get_assessment_history():
    docs = await db.assessments.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return [Assessment(**d) for d in docs]


@api_router.get("/assessment/{assessment_id}", response_model=Assessment)
async def get_assessment(assessment_id: str):
    doc = await db.assessments.find_one({"id": assessment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return Assessment(**doc)


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
  canvas{position:absolute;inset:0;width:100%;height:100%;transform:scaleX(-1)}
  #ui{position:absolute;inset:0;pointer-events:none;display:flex;flex-direction:column;justify-content:space-between;padding:env(safe-area-inset-top,24px) 16px env(safe-area-inset-bottom,24px) 16px}
  #top{display:flex;align-items:center;gap:8px;background:rgba(28,32,29,0.65);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:12px 16px;pointer-events:auto}
  #top .dots{display:flex;gap:6px;flex:1;justify-content:center}
  #top .dot{width:10px;height:10px;border-radius:50%;background:rgba(255,255,255,0.25)}
  #top .dot.active{background:#E18E6D;transform:scale(1.3)}
  #top .dot.done{background:#4A7856}
  #top .label{font-size:14px;font-weight:600;opacity:0.95}
  #exitBtn{background:rgba(255,255,255,0.18);border:none;color:#fff;padding:8px 12px;border-radius:16px;font-weight:600;font-size:13px;pointer-events:auto;cursor:pointer}
  #bottom{background:rgba(28,32,29,0.85);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-radius:24px;padding:16px 18px;pointer-events:auto}
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
  .hidden{display:none !important}
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
</div>

<script type="module">
import { PoseLandmarker, FilesetResolver, DrawingUtils } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

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

let landmarker = null;
let drawingUtils = null;
let tasks = [];
let voiceId = "EXAVITQu4vr4xnSDxMaC";
let currentTaskIdx = 0;
let currentStepIdx = 0;
let taskResults = []; // accumulating
let stepStartTime = 0;
let inTargetSince = null;
let stepCompleted = false;
let stepMetrics = {};
let trunkLeanMax = 0;
let shoulderFlexionMax = 0;
let shoulderHikeDetected = false;
let running = false;
let audioEl = new Audio();

function postRN(data){
  if(window.ReactNativeWebView){
    window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }
}

async function loadTasks(){
  const res = await fetch(`${API_BASE}/assessment/tasks`);
  const json = await res.json();
  tasks = json.tasks;
  voiceId = json.voice_id;
  renderDots();
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
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"user", width:{ideal:1280}, height:{ideal:720}}, audio:false});
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

async function setupPose(){
  const filesetResolver = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
  );
  landmarker = await PoseLandmarker.createFromOptions(filesetResolver, {
    baseOptions:{ modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task" },
    runningMode: "VIDEO",
    numPoses: 1,
  });
  drawingUtils = new DrawingUtils(ctx);
}

async function playVoice(text){
  try{
    voiceText.textContent = "Playing instruction…";
    const res = await fetch(`${API_BASE}/tts/generate`,{
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({text, voice_id: voiceId})
    });
    if(!res.ok) throw new Error("tts failed");
    const data = await res.json();
    audioEl.src = "data:audio/mpeg;base64," + data.audio_b64;
    audioEl.play().catch(()=>{});
    audioEl.onended = () => { voiceText.textContent = "Instruction ready · follow the target"; };
  }catch(e){
    voiceText.textContent = "Voice unavailable — follow on-screen text";
    postRN({type:"voice_error", message:String(e)});
  }
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
  stepStartTime = performance.now();
  inTargetSince = null;
  stepCompleted = false;
  stepMetrics = {};
  trunkLeanMax = 0;
  shoulderFlexionMax = 0;
  shoulderHikeDetected = false;
  stepTitle.textContent = `Task ${currentTaskIdx+1} of ${tasks.length} · ${task.title}`;
  captionEl.textContent = step.caption;
  renderDots();
  postRN({type:"step_start", task_id: task.id, step_id: step.id});
  await playVoice(step.voice);
}

function distance(a,b){ return Math.hypot(a.x-b.x, a.y-b.y); }

function rad2deg(r){ return r*180/Math.PI; }

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

  // shoulder hike: shoulder higher than baseline relative to hip
  const shoulderHipDist = midHip.y - midSh.y;
  if(shoulderHipDist > 0.35) shoulderHikeDetected = true;
}

function checkTarget(landmarks){
  const step = getCurrentStep();
  if(!step || !landmarks) return false;
  const target = step.target;
  // landmark already mirrored (we flipped canvas), but landmarks come from video.
  // Since video is mirrored via CSS only, landmarks are still in original video coords.
  // We mirror by computing 1-x for landmarks because user sees themselves mirrored.
  const which = target.landmark;
  let pts = [];
  if(which === "WRIST") pts = [landmarks[15], landmarks[16]];
  else if(which === "WRISTS") pts = [landmarks[15], landmarks[16]];
  else pts = [landmarks[15], landmarks[16]];

  if(which === "WRISTS"){
    // both wrists must be near target
    const ok = pts.every(p => p && Math.hypot((1-p.x)-target.x, p.y - target.y) < target.r);
    return ok;
  }else{
    // any wrist near target
    return pts.some(p => p && Math.hypot((1-p.x)-target.x, p.y - target.y) < target.r);
  }
}

function drawOverlay(landmarks){
  ctx.clearRect(0,0,canvas.width,canvas.height);
  // draw skeleton
  if(landmarks){
    drawingUtils.drawLandmarks(landmarks, {color:"#D9E5DC", radius:3});
    drawingUtils.drawConnectors(landmarks, PoseLandmarker.POSE_CONNECTIONS, {color:"#4A7856", lineWidth:4});
  }
  // draw target — coords are in user-facing (mirrored) space, so flip x for the un-mirrored canvas (we apply scaleX(-1) via CSS, so drawing at target.x normal works visually)
  const step = getCurrentStep();
  if(step){
    const tx = step.target.x * canvas.width;
    const ty = step.target.y * canvas.height;
    const tr = step.target.r * Math.min(canvas.width, canvas.height);
    const pulse = 1 + 0.08*Math.sin(performance.now()/250);
    ctx.beginPath();
    ctx.arc(tx, ty, tr*pulse, 0, Math.PI*2);
    ctx.lineWidth = 6;
    ctx.strokeStyle = "#E18E6D";
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(tx, ty, tr*0.5, 0, Math.PI*2);
    ctx.fillStyle = "rgba(225,142,109,0.4)";
    ctx.fill();
    // hold ring
    if(inTargetSince){
      const elapsed = performance.now() - inTargetSince;
      const progress = Math.min(1, elapsed / step.hold_ms);
      ctx.beginPath();
      ctx.arc(tx, ty, tr*1.25, -Math.PI/2, -Math.PI/2 + progress*Math.PI*2);
      ctx.strokeStyle = "#3C8255";
      ctx.lineWidth = 8;
      ctx.stroke();
    }
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
  taskResults[currentTaskIdx].steps.push({
    step_id: step.id, completed: !skipped, duration_ms: Math.round(performance.now() - stepStartTime),
    metrics: {trunk_lean_deg: Math.round(trunkLeanMax), shoulder_flexion_ratio: +shoulderFlexionMax.toFixed(2), shoulder_hike: shoulderHikeDetected}
  });
  if(!skipped) taskResults[currentTaskIdx].completed_steps += 1;
  taskResults[currentTaskIdx].duration_ms += Math.round(performance.now() - stepStartTime);

  // aggregate metrics
  if(trunkLeanMax > (taskResults[currentTaskIdx].metrics.trunk_lean_deg||0))
    taskResults[currentTaskIdx].metrics.trunk_lean_deg = Math.round(trunkLeanMax);
  if(shoulderHikeDetected) taskResults[currentTaskIdx].metrics.shoulder_hike = true;

  currentStepIdx += 1;
  if(currentStepIdx >= task.steps.length){
    currentStepIdx = 0;
    currentTaskIdx += 1;
    if(currentTaskIdx >= tasks.length){
      finishAssessment();
      return;
    }
  }
  startStep();
}

async function finishAssessment(){
  running = false;
  audioEl.pause();
  captionEl.textContent = "Saving your results…";
  voiceText.textContent = "Generating personalized plan…";
  try{
    const res = await fetch(`${API_BASE}/assessment/submit`,{
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({task_results: taskResults, affected_side: "right"})
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
  let result = null;
  try{
    result = landmarker.detectForVideo(video, now);
  }catch(e){}
  let landmarks = null;
  if(result && result.landmarks && result.landmarks[0]) landmarks = result.landmarks[0];
  if(landmarks) computeMetrics(landmarks);
  drawOverlay(landmarks);

  // check target hit
  const inTarget = checkTarget(landmarks);
  const step = getCurrentStep();
  if(step){
    if(inTarget){
      if(inTargetSince == null) inTargetSince = now;
      if(!stepCompleted && (now - inTargetSince) >= step.hold_ms){
        stepCompleted = true;
        if(navigator.vibrate) navigator.vibrate(80);
        setTimeout(()=>nextStep(false), 350);
      }
    }else{
      inTargetSince = null;
    }
  }
  requestAnimationFrame(loop);
}

startBtn.addEventListener("click", async () => {
  overlay.classList.add("hidden");
  startBtn.disabled = true;
  await loadTasks();
  const camOk = await setupCamera();
  if(!camOk){ overlay.classList.remove("hidden"); return; }
  await setupPose();
  running = true;
  await startStep();
  requestAnimationFrame(loop);
});

skipBtn.addEventListener("click", () => {
  if(!running) return;
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


# Mount routes
app.include_router(api_router)

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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
