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
  version: "8.0"
  test_sequence: 8
  run_ui: false

test_plan:
  current_focus:
    - "OpenAI TTS (nova) replaces ElevenLabs via Emergent LLM key"
    - "Dynamic landmark targets in pose-runner WebView (WRIST_DYNAMIC, MOUTH, CHEST, HAND_OPEN, PINCH) + emoji icons"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: "Iteration 8 fixes: (a) Swapped ElevenLabs → OpenAI TTS (nova) using emergentintegrations.llm.openai.text_to_speech.OpenAITextToSpeech with EMERGENT_LLM_KEY. Confirmed /api/tts/health ok=true and /api/tts/generate returns valid mp3 base64. (b) Rewrote the pose-runner JS to handle the new dynamic landmark target IDs and added MediaPipe HandLandmarker for HAND_OPEN/PINCH. Added emoji icons (☕🪵🧺🏐🪙) drawn with counter-flip on the mirrored canvas. Please backend-test: POST /api/tts/generate with sample text returns valid base64 mp3; GET /api/tts/health returns provider=openai voice=nova; GET /api/assessment/tasks returns 7 tasks with voice_id=nova and at least 5 icon-bearing steps; GET /api/pose/runner returns HTML containing HandLandmarker, WRIST_DYNAMIC, MOUTH, CHEST, HAND_OPEN, PINCH, ICON_EMOJI. The actual MediaPipe loop requires a camera-enabled browser and is hard to e2e via testing_agent — verify only that the HTML payload is well-formed."
