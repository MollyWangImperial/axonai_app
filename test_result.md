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
  version: "12.0"
  test_sequence: 12
  run_ui: false

test_plan:
  current_focus:
    - "Phase C — Progress dashboard, Google Auth, Stripe subscription, paywall"
    - "Persona chat credit-charge fix"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Phase C complete. (1) Credit costs updated: assessment=40, rehab_plan=30, guided_exercise=30, premium_chat_message=10 → 100 starting credits exactly cover 1 assessment + 1 plan + 1 exercise. (2) subscription_active flag added to users; consume_credits BYPASSES charging for assessment/rehab_plan/guided_exercise when active, but premium_chat_message (AI therapist) always charges. (3) New endpoints: POST /api/billing/subscribe (creates $9.99/mo Stripe Checkout via inline price_data), POST /api/billing/buy-credits ($4.99 → 200 credits), GET /api/billing/verify-session (poll-based fallback to webhook), POST /api/billing/webhook (idempotent grant logic), POST /api/auth/google/session (exchanges Emergent session_id for app user via demobackend.emergentagent.com/auth/v1/env/oauth/session-data), GET /api/progress/summary (time-series of functional metrics + issues + counts; empty arrays for anonymous/new users). (4) Persona chat bug fix: /api/personas/chat now requires X-User-Id, charges 10 credits BEFORE LLM call, returns 402 'Not enough credits to chat' with insufficient balance. Added alias /api/chat/persona/message. (5) Frontend: PaywallModal component (full-screen $9.99/mo + $4.99 credit pack option, opens Stripe Checkout in WebBrowser/new tab, polls verify-session every 2s for up to 90s). Wired into rehab-plan.tsx (pre-flight credit check before Start exercise) and persona-chat.tsx (402 → open paywall). Progress dashboard at /progress with SVG line charts for shoulder_flexion_deg / reach_completion / bilateral_symmetry / trunk_lean_deg, empty state when no assessments. Home tile 'Progress' opens it. Sign-in adds 'Continue with Google' button (opens auth.emergentagent.com, parses session_id from URL hash, exchanges via /api/auth/google/session). New /billing-return route polls verify-session and shows success/fail. Tests: 23/23 PASS via testing_agent including all 5 persona-chat credit tests."

    - agent: "main"
      message: "Iteration 11 — Assessment + Exercise quality fixes. ASSESSMENT (server.py POSE_RUNNER_HTML): (0) Bottom card auto-fades to 30% opacity once voice ends. (1) effectiveRadius tightened: 0.55×shoulder-width (0.70 for MOUTH/CHEST) capped at 0.18. (1b) MOVEMENT GATE — wrist must move ≥0.75×sw from step-start position. (2) VOICE GATE — locked until 350ms after voice ends, circle dashed-and-dim until armed. EXERCISE RUNNER: (7) Hit radius × 1.55; visual matches. (4) Sets/reps progress bar. (5) computeRepScore() 0-100. (6) Removed 'Voice input error' phrase; single 'yes' is enough. FRONTEND rehab-plan.tsx: per-exercise pct badge + progress bar + last score; 'Guided practice' → 'Start exercise'. exercise.tsx: per-rep score TOAST + session-avg on completion."

    - agent: "main"
      message: "Phase B complete. (1+2) Replaced spinning ActivityIndicator on send button in both /chat tab and /persona-chat with a static arrow icon that just dims via `sendBtnDisabled` opacity; added animated three-dot TypingIndicator bubble as ListFooterComponent during `sending=true`. New shared component /app/frontend/src/components/TypingIndicator.tsx. (7) Renamed Hope→Aria across the codebase: tab label, chat header, placeholder, backend CHAT_SYSTEM_PROMPT_BASE persona name, and proactive opener templates. Backend now reads preferred_name from `users.profile` and injects it into both /chat/message system prompt and /chat/proactive templates. Added new GET /api/chat/proactive/messages?n=N endpoint that returns N personalized caring messages with the user's preferred name baked in. Built /app/frontend/src/components/AriaFloatingChat.tsx: a heart-shaped FAB in lower-right with a fade+scale-in speech bubble that pops up 2s after Home loads, plays the greeting via OpenAI Nova TTS (mobile only — web autoplay is blocked), cycles random caring messages every 25s, tappable bubble or FAB jumps to /chat. Verified e2e: typing indicator visible in screenshot during send delay; Aria FAB+bubble shows 'Anything on your mind, Sam? I'm here.' with the user's preferred name."
