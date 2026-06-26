#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: "Stroke rehab Expo app. Recent issues: (1) ElevenLabs TTS quota exceeded — migrate to OpenAI TTS via Emergent LLM key, voice=nova. (2) Assessment WebView broken — the JS pose-runner only knew WRIST/WRISTS landmarks; new targets WRIST_DYNAMIC, MOUTH, CHEST, HAND_OPEN, PINCH and emoji icons (cup/table/towel/ball/coin) need full implementation."

backend:
  - task: "OpenAI TTS (nova) replaces ElevenLabs via Emergent LLM key"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: "Replaced ElevenLabs ImportError block + endpoints. /api/tts/health returns ok=true with provider=openai voice=nova; /api/tts/generate returns ~34KB mp3 audio_b64. Tasks endpoint now returns voice_id='nova'."
  - task: "Dynamic landmark targets in pose-runner WebView (WRIST_DYNAMIC, MOUTH, CHEST, HAND_OPEN, PINCH) + emoji icons"
    implemented: true
    working: "NA"
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Added HandLandmarker integration, computeHandMetrics() for open/pinch scores, resolveLandmarkPoint() that mirrors body landmarks, getEffectiveTargetXY() that dynamically anchors targets, ICON_EMOJI map (cup/table/towel/ball/coin) drawn with counter-flip on the CSS-mirrored canvas. checkTarget now requires wrist proximity AND gesture for HAND_OPEN/PINCH. WRIST_DYNAMIC locks position on first valid wrist detection per step. Needs end-to-end browser test with camera (which testing_agent may not have access to). Backend-side: GET /api/pose/runner returns HTML with 25+ matches of new symbols."

frontend:
  - task: "Assessment WebView renders new dynamic targets/icons end-to-end"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/assessment.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: "NA"
          agent: "main"
          comment: "No frontend code change needed — assessment.tsx already hosts WebView pointing to /api/pose/runner. Voice now plays via OpenAI Nova."

metadata:
  created_by: "main_agent"
  version: "10.0"
  test_sequence: 10
  run_ui: false

test_plan:
  current_focus:
    - "Aria chat tab rename (was Hope) + typing indicator"
    - "Aria floating bubble on Home with personalized caring messages"
    - "Persona chat typing indicator (community + therapist)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Iteration 11 — Assessment + Exercise quality fixes. ASSESSMENT (server.py POSE_RUNNER_HTML): (0) Replaced the always-on bottom card with CSS that fades it to 30% opacity once the voice intro ends so the patient can see the target circle clearly (hover/focus brings it back to 95%). (1) effectiveRadius tightened — was 0.85×shoulder-width capped at 0.28, now 0.55×sw (0.70 for MOUTH/CHEST) capped at 0.18. The visually drawn circle matches the hit zone exactly. (1b) Added a MOVEMENT GATE: target is not detectable until the wrist has moved ≥0.75×shoulder-width away from its position at step-start. Fixes the 'I didn't move my arm down and the lower circle still fired' bug. (2) Added a VOICE GATE: target is not detectable while voice is playing nor for 350ms after — fixes accidental early triggers. The circle is rendered dashed-and-dim while not yet armed, solid-and-bright when armed, so users see when it's safe to start moving. EXERCISE RUNNER (server.py REHAB_RUNNER_HTML): (7) Hit radius bumped 1.55×; visual circle matched. (4) Added a sets/reps progress bar in the top card that fills as reps complete. (5) Added computeRepScore() (0-100) using trunk lean, shoulder hike, reach completion, plus scoreLabel() mapping. rep_complete WebView message now includes `score`. Feedback overlay shows 'Your score: 87/100 — Great work' and reads it aloud via TTS. (6) Voice-input UX overhaul — single 'yes' is enough (also yeah/yep/okay/ok/continue/next), the dreaded 'Voice input error — tap the button' has been removed and replaced with a friendly 'Tap Continue when ready.' that never panics the user. FRONTEND rehab-plan.tsx: (4) Removed Mark-done toggle. Added per-exercise pct progress badge (e.g. '30%'), inline progress bar, and last-session score line. 'Guided practice' button renamed to 'Start exercise' (or 'Continue exercise'/'Practice again' depending on state). Progress persisted in AsyncStorage and refreshed via useFocusEffect when returning from /exercise. FRONTEND exercise.tsx: per-rep score TOAST appears mid-screen for ~2.5s after each rep ('Rep 1/5 · 87 · Great work'), session-average score shown on Exercise complete overlay, progress saved to the same AsyncStorage key on every rep so closing mid-session doesn't lose work.\n\nPlease backend-test: 1) /api/pose/runner HTML payload contains the strings 'voiceFinishedAt', 'arrivedAfterMovement', 'updateMovementGate', 'effectiveRadius', 'step-active', 'stepStartWristXY'. 2) /api/rehab/runner?exercise_id=ex_maintenance HTML contains 'computeRepScore', 'lastRepScore', 'repBarFill', 't.r * 1.55', 'Heard you', and DOES NOT contain 'Voice input error'. 3) /api/assessment/tasks returns 7 tasks voice_id=nova. 4) /api/tts/health still ok. 5) /api/assessment/history (with X-User-Id) still filters by user. 6) /api/users/onboarding round-trip still works. CAMERA-DEPENDENT BEHAVIOR (movement gate, voice gate, accuracy on T3 mouth, exercise circle size feel, rep score values) cannot be exercised here without a live camera feed — those will be verified by the user on their device after this iteration. Skip frontend e2e for camera screens."

    - agent: "main"
      message: "Phase B complete. (1+2) Replaced spinning ActivityIndicator on send button in both /chat tab and /persona-chat with a static arrow icon that just dims via `sendBtnDisabled` opacity; added animated three-dot TypingIndicator bubble as ListFooterComponent during `sending=true`. New shared component /app/frontend/src/components/TypingIndicator.tsx. (7) Renamed Hope→Aria across the codebase: tab label, chat header, placeholder, backend CHAT_SYSTEM_PROMPT_BASE persona name, and proactive opener templates. Backend now reads preferred_name from `users.profile` and injects it into both /chat/message system prompt and /chat/proactive templates. Added new GET /api/chat/proactive/messages?n=N endpoint that returns N personalized caring messages with the user's preferred name baked in. Built /app/frontend/src/components/AriaFloatingChat.tsx: a heart-shaped FAB in lower-right with a fade+scale-in speech bubble that pops up 2s after Home loads, plays the greeting via OpenAI Nova TTS (mobile only — web autoplay is blocked), cycles random caring messages every 25s, tappable bubble or FAB jumps to /chat. Verified e2e: typing indicator visible in screenshot during send delay; Aria FAB+bubble shows 'Anything on your mind, Sam? I'm here.' with the user's preferred name."
