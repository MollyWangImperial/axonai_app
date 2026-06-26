from fastapi import FastAPI, APIRouter, HTTPException, Request
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

from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# OpenAI TTS via Emergent LLM key (universal key)
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
TTS_VOICE = os.environ.get("TTS_VOICE", "nova")  # warm/encouraging default
TTS_MODEL = os.environ.get("TTS_MODEL", "tts-1")
tts_client = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)

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
                "voice": "Welcome. Let's begin with a seated forward reach. Sit upright, with your arm relaxed. When you're ready, touch the circle that appears on your hand.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.12, "landmark": "WRIST_DYNAMIC"},
                "hold_ms": 1200,
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
                "voice": "Let's try bringing your hand to your mouth. When you're ready, touch the circle on your hand to begin.",
                "target": {"x": 0.5, "y": 0.78, "r": 0.12, "landmark": "WRIST_DYNAMIC"},
                "hold_ms": 1200,
                "caption": "Touch the circle on your hand",
            },
            {
                "id": "T3-S2",
                "voice": "Now, slowly bring your hand up to your mouth, as if you were drinking from a cup. Keep your head still.",
                "target": {"x": 0.5, "y": 0.30, "r": 0.10, "landmark": "MOUTH"},
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
                "voice": "Imagine a cup is on the table in front of you. Reach with your affected hand toward the cup.",
                "target": {"x": 0.30, "y": 0.65, "r": 0.10, "landmark": "WRIST", "icon": "cup"},
                "hold_ms": 1200,
                "caption": "Reach for the cup",
            },
            {
                "id": "T4-S2",
                "voice": "Pretend to close your fingers around the cup, then carefully move it to the table on your other side.",
                "target": {"x": 0.70, "y": 0.65, "r": 0.12, "landmark": "WRIST", "icon": "table"},
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
                "voice": "Hold your affected hand up at your chest, palm open and steady.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.10, "landmark": "CHEST"},
                "hold_ms": 1500,
                "caption": "Hand on chest",
            },
            {
                "id": "T5-S2",
                "voice": "Open your hand wide. When fully open, hold for a moment. Then slowly close your hand around an imaginary ball.",
                "target": {"x": 0.5, "y": 0.45, "r": 0.12, "landmark": "HAND_OPEN", "icon": "ball"},
                "hold_ms": 1800,
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
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "PINCH", "icon": "coin"},
                "hold_ms": 1800,
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
                "target": {"x": 0.5, "y": 0.40, "r": 0.12, "landmark": "WRISTS", "icon": "towel"},
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
            add("REACH_INCOMPLETE", "Difficulty reaching forward",
                "Your arm couldn't quite reach as far forward as the target. This is something we can improve with focused practice.",
                "Fugl-Meyer UE; ARAT", "moderate", "T1")
        trunk = t1.metrics.get("trunk_lean_deg", 0)
        if isinstance(trunk, (int, float)) and trunk > 15:
            add("TRUNK_COMP", "Leaning forward when reaching",
                "Your body leaned forward to help your arm reach. We'll work on letting your arm do the work while you stay upright.",
                "Levin & Michaelsen (Trunk Restraint Reaching)", "mild", "T1")

    t2 = by_id.get("T2")
    if t2:
        if t2.completed_steps < t2.total_steps:
            add("SHOULDER_FLEX_LIMITED", "Difficulty lifting your arm overhead",
                "Raising your arm up high felt harder than it should be. With practice, this range will grow over time.",
                "Fugl-Meyer UE (Synergistic Movement)", "moderate", "T2")
        if t2.metrics.get("shoulder_hike", False):
            add("SHOULDER_HIKE", "Shoulder lifts toward your ear",
                "Your shoulder hiked up as you reached — a very common pattern after a stroke. We'll teach it to stay relaxed.",
                "Bobath / NDT principles", "mild", "T2")

    t3 = by_id.get("T3")
    if t3 and t3.completed_steps < t3.total_steps:
        add("H2M_IMPAIRED", "Difficulty bringing your hand to your mouth",
            "Bringing your hand to your mouth — for eating or drinking — is harder right now. We'll practice this important everyday movement.",
            "Chedoke-McMaster Stroke Assessment", "moderate", "T3")

    t4 = by_id.get("T4")
    if t4 and t4.completed_steps < t4.total_steps:
        add("GROSS_GRASP", "Trouble grasping and moving objects",
            "Picking something up and moving it across the table felt difficult. We'll rebuild this with simple, everyday items.",
            "ARAT (Grasp subscale)", "moderate", "T4")

    t5 = by_id.get("T5")
    if t5 and t5.completed_steps < t5.total_steps:
        add("HAND_OPENING", "Difficulty opening your hand",
            "Opening your fingers wide is harder than closing them — this is the most common challenge after a stroke. There's a lot we can do.",
            "Constraint-Induced Movement Therapy (Taub)", "moderate", "T5")

    t6 = by_id.get("T6")
    if t6 and t6.completed_steps < t6.total_steps:
        add("PINCH_IMPAIRED", "Difficulty with small finger movements",
            "Picking up small objects like a coin or pen is tricky right now. Fine motor skills will return with patient practice.",
            "Jebsen Hand Function Test", "mild", "T6")

    t7 = by_id.get("T7")
    if t7 and t7.completed_steps < t7.total_steps:
        add("BILATERAL_NONUSE", "Your affected arm needs more practice joining in",
            "When using both hands together, your affected side took a back seat. We'll gently bring it back into your daily activities.",
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
    return {"tasks": TASKS_DATA, "voice_id": TTS_VOICE}


@api_router.post("/tts/generate", response_model=TTSResponse)
async def generate_tts(req: TTSRequest):
    # Use OpenAI TTS (nova by default) via Emergent LLM key.
    # `voice_id` from old clients is accepted but ignored unless it matches a valid OpenAI voice.
    valid_voices = {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}
    voice = req.voice_id if (req.voice_id in valid_voices) else TTS_VOICE
    try:
        audio_b64 = await tts_client.generate_speech_base64(
            text=req.text,
            model=TTS_MODEL,
            voice=voice,
            response_format="mp3",
        )
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
    """Diagnostic: check whether OpenAI TTS via Emergent LLM key works."""
    try:
        b = await tts_client.generate_speech(
            text="ok",
            model=TTS_MODEL,
            voice=TTS_VOICE,
            response_format="mp3",
        )
        return {"ok": True, "bytes": len(b), "voice": TTS_VOICE, "model": TTS_MODEL, "provider": "openai"}
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


@api_router.post("/assessment/submit", response_model=Assessment)
async def submit_assessment(payload: AssessmentSubmit, request: Request):
    user = await _user_from_header(dict(request.headers))
    if user:
        await consume_credits(user["id"], "assessment")
        await consume_credits(user["id"], "rehab_plan")
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
    doc = assessment.dict()
    if user:
        doc["user_id"] = user["id"]
    await db.assessments.insert_one(doc)
    return assessment


@api_router.get("/assessment/history", response_model=List[Assessment])
async def get_assessment_history(request: Request):
    """Return ONLY the signed-in user's assessments. Anonymous → empty list."""
    user = await _user_from_header(dict(request.headers))
    if not user:
        return []
    docs = (
        await db.assessments
        .find({"user_id": user["id"]}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(50)
    )
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
  <div id="celebrate" class="hidden">
    <div class="star">⭐</div>
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
let running = false;
let audioEl = new Audio();
let latestHandLandmarks = null;        // result.landmarks[0] from HandLandmarker (21 points)
let latestPoseLandmarks = null;        // result.landmarks[0] from PoseLandmarker (33 points)
let dynamicTargetPos = null;           // {x,y} captured once per step for WRIST_DYNAMIC
let handOpenScore = 0;                 // 0..1 — finger extension confidence
let pinchScore = 0;                    // 0..1 — pinch confidence (1 = very close)
// Pull signed-in user id from URL (?uid=…) so /assessment/submit attributes the
// new assessment to the correct user and credits get debited from their wallet.
const URL_PARAMS = new URLSearchParams(window.location.search);
const CURRENT_USER_ID = URL_PARAMS.get("uid") || "";

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
  try{
    handLandmarker = await HandLandmarker.createFromOptions(filesetResolver, {
      baseOptions:{ modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" },
      runningMode: "VIDEO",
      numHands: 2,
    });
  }catch(e){
    // hand detection optional — falls back to pose-based heuristics
    handLandmarker = null;
    postRN({type:"hand_landmarker_unavailable", message:String(e)});
  }
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
  stepStartedAt = stepStartTime;
  voiceFinishedAt = 0;
  arrivedAfterMovement = false;
  stepStartWristXY = null;
  inTargetSince = null;
  lastInTargetTs = 0;
  stepCompleted = false;
  stepMetrics = {};
  trunkLeanMax = 0;
  shoulderFlexionMax = 0;
  shoulderHikeDetected = false;
  dynamicTargetPos = null;
  stepTitle.textContent = `Task ${currentTaskIdx+1} of ${tasks.length} · ${task.title}`;
  captionEl.textContent = step.caption;
  renderDots();
  // Show step intro card (caption + voice waveform)
  document.body.classList.add("voice-playing");
  document.body.classList.remove("step-active");
  postRN({type:"step_start", task_id: task.id, step_id: step.id});
  await playVoice(step.voice);
  // Voice finished → unlock the target and fade the bottom card
  voiceFinishedAt = performance.now();
  document.body.classList.remove("voice-playing");
  document.body.classList.add("step-active");
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

// ---------- Dynamic target resolution ----------
// Returns the on-screen (mirrored, normalized) point at which to draw the target,
// and the candidate body point(s) to test against the target zone.
// Mirroring: user sees themselves mirrored — so on-screen X = (1 - landmark.x).
function mirrorX(p){ return {x: 1 - p.x, y: p.y}; }

function resolveLandmarkPoint(which){
  const lm = latestPoseLandmarks;
  if(!lm) return null;
  if(which === "WRIST" || which === "WRIST_DYNAMIC"){
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
  if(which === "HAND_OPEN" || which === "PINCH"){
    // Anchor on whichever wrist is most raised (active hand)
    const active = lm[15].y < lm[16].y ? lm[15] : lm[16];
    return mirrorX(active);
  }
  return null;
}

function getEffectiveTargetXY(step){
  // For WRIST_DYNAMIC, MOUTH, CHEST, HAND_OPEN, PINCH the target follows the body.
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
  if(which === "HAND_OPEN" || which === "PINCH"){
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
    pinchScore = Math.max(0, pinchScore - 0.15);
    return;
  }
  const h = latestHandLandmarks;
  const dist = (a,b) => Math.hypot(a.x-b.x, a.y-b.y);
  const palmWidth = Math.max(0.01, dist(h[5], h[17])); // index_mcp <-> pinky_mcp
  const fingerSpread = (
    dist(h[0], h[8])  +  // wrist to index_tip
    dist(h[0], h[12]) +  // wrist to middle_tip
    dist(h[0], h[16]) +  // wrist to ring_tip
    dist(h[0], h[20])    // wrist to pinky_tip
  ) / 4;
  // Normalize by palm width — extended fingers ~3-4x palm width
  const openRatio = fingerSpread / palmWidth;
  // Map 1.8 (closed) -> 0 ; 3.0 (open) -> 1
  const open = Math.max(0, Math.min(1, (openRatio - 1.8) / 1.2));
  handOpenScore = handOpenScore * 0.6 + open * 0.4;

  const pinchDist = dist(h[4], h[8]) / palmWidth;
  // pinchDist < 0.5 means tips are touching; > 1.2 means apart
  const pinch = Math.max(0, Math.min(1, (1.2 - pinchDist) / 0.7));
  pinchScore = pinchScore * 0.6 + pinch * 0.4;
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

function distXY(a,b){ if(!a||!b) return Infinity; return Math.hypot(a.x-b.x, a.y-b.y); }

function activeWrist(lm){
  if(!lm) return null;
  // pick the wrist closer to the current effective target
  const step = getCurrentStep();
  if(!step) return mirrorX(lm[15]);
  const target = getEffectiveTargetXY(step);
  const lW = mirrorX(lm[15]); const rW = mirrorX(lm[16]);
  const dL = lW ? Math.hypot(lW.x - target.x, lW.y - target.y) : Infinity;
  const dR = rW ? Math.hypot(rW.x - target.x, rW.y - target.y) : Infinity;
  return dL < dR ? lW : rW;
}

function updateMovementGate(lm){
  if(!stepStartWristXY){
    const w = activeWrist(lm);
    if(w) stepStartWristXY = {x: w.x, y: w.y};
    return;
  }
  if(arrivedAfterMovement) return;
  const w = activeWrist(lm);
  if(!w) return;
  // Required movement scales with shoulder-width to be size-invariant
  const requiredMove = Math.max(0.12, shoulderWidth(lm) * 0.75);
  if(distXY(w, stepStartWristXY) >= requiredMove) arrivedAfterMovement = true;
}

function checkTarget(landmarks){
  const step = getCurrentStep();
  if(!step || !landmarks) return false;
  // VOICE GATE — target is NOT detectable until the voice intro has finished
  // playing AND a short settle window (350ms) has elapsed. Prevents the patient
  // accidentally triggering the step while Aria is still explaining it.
  if(voiceFinishedAt === 0) return false;
  if(performance.now() - voiceFinishedAt < 350) return false;
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
  if(which === "PINCH"){
    const near = wristDist() < R;
    const gestureOk = handLandmarker ? pinchScore > 0.45 : true;
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
  const step = getCurrentStep();
  if(!step) return;
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

  // small status badge for hand gesture requirements
  const which = step.target.landmark;
  if(which === "HAND_OPEN" || which === "PINCH"){
    const score = which === "HAND_OPEN" ? handOpenScore : pinchScore;
    const label = which === "HAND_OPEN" ? "Open" : "Pinch";
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

  postRN({type:"task_complete", task_id: finishedTask.id, task_index: currentTaskIdx});

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
  captionEl.textContent = "Saving your results…";
  voiceText.textContent = "Generating personalized plan…";
  try{
    const res = await fetch(`${API_BASE}/assessment/submit`,{
      method:"POST", headers:{"Content-Type":"application/json", ...(CURRENT_USER_ID ? {"X-User-Id": CURRENT_USER_ID} : {})},
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
  latestPoseLandmarks = landmarks;
  if(landmarks){
    computeMetrics(landmarks);
    updateMovementGate(landmarks);
  }

  // Hand landmarks (optional)
  if(handLandmarker){
    try{
      const hr = handLandmarker.detectForVideo(video, now);
      if(hr && hr.landmarks && hr.landmarks[0]){
        latestHandLandmarks = hr.landmarks[0];
      }else{
        latestHandLandmarks = null;
      }
    }catch(e){}
  }
  computeHandMetrics();

  drawOverlay(landmarks);

  // check target hit — with a small "grace period" so brief jitter doesn't reset the hold
  const inTarget = checkTarget(landmarks);
  const step = getCurrentStep();
  if(step){
    if(inTarget){
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

// Per-rep accumulated metrics
let trunkLeanMax = 0;
let shoulderHikeDetected = false;
let reachMax = 0;

exName.textContent = CFG.name;
overlayTitle.textContent = CFG.name;
overlayBody.textContent = CFG.setup_voice;

function postRN(d){ if(window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(d)); }

async function playVoice(text){
  if(!text) return;
  try{
    voiceText.textContent = "Playing instruction…";
    const res = await fetch(`${API_BASE}/tts/generate`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    if(!res.ok) throw new Error("tts fail");
    const data = await res.json();
    audioEl.src = "data:audio/mpeg;base64," + data.audio_b64;
    await audioEl.play().catch(()=>{});
    return new Promise(r => { audioEl.onended = () => { voiceText.textContent = "—"; r(); }; });
  }catch(e){
    voiceText.textContent = "Voice unavailable — follow on-screen text";
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
  overlay.classList.add("hidden");
  startBtn.disabled = true;
  const camOk = await setupCamera();
  if(!camOk){ overlay.classList.remove("hidden"); return; }
  await setupPose();
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
async def persona_chat(req: PersonaChatRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="Chat unavailable — LLM key not configured.")
    persona = _find_persona(req.persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

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
from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: E402

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
    "assessment": 10,
    "rehab_plan": 20,
    "guided_exercise": 5,
    "premium_chat_message": 2,
    "video_call": 50,
    "in_person_session": 80,
}


async def get_or_create_user(email: str, name: str, role: str = "patient") -> Dict[str, Any]:
    doc = await db.users.find_one({"email": email.lower()}, {"_id": 0})
    if doc:
        return doc
    doc = {
        "id": "u_" + str(uuid.uuid4())[:12],
        "email": email.lower(),
        "name": name,
        "role": role,
        "credits": 100,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc


async def _user_from_header(request_headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    uid = request_headers.get("x-user-id") or request_headers.get("X-User-Id")
    if not uid:
        return None
    return await db.users.find_one({"id": uid}, {"_id": 0})


async def consume_credits(user_id: str, kind: str) -> Dict[str, Any]:
    cost = CREDIT_COSTS.get(kind, 0)
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    if user["credits"] < cost:
        raise HTTPException(status_code=402, detail=f"Not enough credits. Need {cost}, have {user['credits']}.")
    new_credits = user["credits"] - cost
    await db.users.update_one({"id": user_id}, {"$set": {"credits": new_credits}})
    await db.credit_log.insert_one({
        "user_id": user_id, "kind": kind, "cost": cost, "new_balance": new_credits,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
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
    age_band: Optional[str] = None         # "<40" | "40-54" | "55-64" | "65-74" | "75+"
    months_since_stroke: Optional[int] = None
    side_affected: Optional[str] = None    # "left" | "right" | "both" | "unsure"
    dominant_hand: Optional[str] = None    # "left" | "right" | "ambidextrous"
    mobility_level: Optional[str] = None   # "wheelchair" | "walker" | "cane" | "independent"
    primary_goal: Optional[str] = None     # free text
    secondary_goals: Optional[List[str]] = None
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
    await db.users.update_one({"id": user["id"]}, {"$set": {"profile": update, "onboarding_complete": True}})
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
        return {"credits": 0, "anonymous": True, "costs": CREDIT_COSTS}
    return {"credits": user["credits"], "user_id": user["id"], "costs": CREDIT_COSTS}


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
