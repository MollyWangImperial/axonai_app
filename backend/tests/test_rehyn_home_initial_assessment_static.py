from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_patient_tabs_are_home_journey_and_alira_only():
    layout = read("frontend/app/(tabs)/_layout.tsx")
    assert 'title: "Home"' in layout
    assert 'title: "Journey"' in layout
    assert 'title: "Alira"' in layout
    assert 'name="community"' in layout and "href: null" in layout
    assert 'name="therapists"' in layout and "href: null" in layout
    assert 'const isWeb = Platform.OS === "web"' in layout
    assert "height: isWeb ? 80" in layout
    assert "paddingBottom: isWeb ? 14" in layout
    assert "lineHeight: 16" in layout


def test_home_launches_standardized_initial_assessment():
    home = read("frontend/app/(tabs)/index.tsx")
    assert '"Start Initial Assessment"' in home
    assert 'carePlanAssessment?.task_ids' in home
    assert 'carePlanAssessment?.task_ids?.includes("L6")' in home
    assert '"Selected if safe"' in home
    assert '"Not assigned"' in home
    assert 'authedFetch("/api/alira/care-plan")' in home
    assert '"Alira selected suitable tasks from your readiness answers."' in home
    assert 'pathname: "/session-check"' in home


def test_home_becomes_next_assessment_after_initial_completion():
    home = read("frontend/app/(tabs)/index.tsx")
    journey = read("frontend/app/(tabs)/journey.tsx")
    assert 'history.some((item) => item.assessment_package === "initial")' in home
    assert "carePlan?.account_state?.has_completed_initial_assessment" in home
    assert 'activeExerciseIds.length\n        ? "Today\'s exercises"' in home
    assert "followUpDue" in home
    assert 'testID: "home-assessment-action"' in home
    assert 'testID="home-see-full-progress"' in home
    assert "startNextSession" in home
    assert 'testID="assessment-history"' in journey
    assert 'item.id === initialAssessmentId ? "Initial Assessment" : "Movement check-in"' in journey
    assert 'return "No rehab plan recommended"' in journey
    assert 'return "Movement analysis in progress"' in journey


def test_home_day_titles_are_dark_in_light_mode_and_lighter_only_in_dark_mode():
    home = read("frontend/app/(tabs)/index.tsx")

    assert "const titleColor = preferences.darkMode ? palette.brand : palette.text" in home
    assert "styles.dayStepTitle, { color: titleColor }" in home


def test_readiness_survey_separates_assisted_movement_from_complete_inability():
    survey = read("frontend/src/patientSurvey.ts")
    onboarding = read("frontend/app/onboarding.tsx")
    server = read("backend/server.py")

    assert 'value: "help_only", label: "I can move it only with help"' in survey
    assert 'value: "help_only", label: "I can move my hand or fingers only with help"' in survey
    assert survey.count("even with help") >= 2
    assert 'MOVEMENT_READINESS_VERSION = "survey-exercise-v3"' in survey
    assert "usesLegacyMovementMeaning" in onboarding
    assert 'update["movement_readiness_version"] = MOVEMENT_READINESS_VERSION' in server
    assert "exercise_selection_fields" in server


def test_initial_assessment_is_automatically_selected_without_a_manual_task_choice():
    intro = read("frontend/app/task-intro.tsx")
    assert 'authedFetch("/api/assessment/recommendation?package=initial")' in intro
    assert 'fetchTasks(packageId, assignedTaskIds)' in intro
    assert 'task_ids: taskIds.join(",")' in intro
    assert "launch your next guided task automatically" in intro
    assert "tasks.map(" not in intro
    assert "task-row-" not in intro
    assert "Choose assessment package" not in intro
    assert "setSelectedTaskId" not in intro


def test_initial_assessment_shows_the_survey_based_functional_profile_and_tasks():
    intro = read("frontend/app/task-intro.tsx")
    assert 'testID="task-intro-functional-profile"' in intro
    assert "YOUR FUNCTIONAL ASSESSMENT PROFILE" in intro
    assert "recommendation.task_ids.map" in intro
    assert "This profile guides task selection. It is not a medical diagnosis." in intro


def test_followup_starts_fresh_without_removing_assessment_history():
    intro = read("frontend/app/task-intro.tsx")
    assert "if (!isInitial && assessmentComplete && userId)" in intro
    assert "await resetTaskProgress(packageId)" in intro
    assert "Your previous results will remain in Assessment history" in intro
    assert '"Start Next Assessment"' in intro
    assert "delete assessment" not in intro.lower()


def test_web_assessment_shim_has_a_defined_full_size_container():
    shim = read("frontend/src/shims/webview-web.tsx")
    assert "const styles = StyleSheet.create" in shim
    assert 'width: "100%"' in shim
    assert 'height: "100%"' in shim


def test_onboarding_collects_pdf_feedback_fields():
    onboarding = read("frontend/app/onboarding.tsx")
    survey = read("frontend/src/patientSurvey.ts")
    server = read("backend/server.py")
    assert "ASSESSMENT_READINESS_KEYS, PATIENT_SURVEY_STEPS" in onboarding
    assert 'value: "under_20"' in survey
    assert 'key: "affected_areas"' in survey
    assert 'label: "Left upper limb (shoulder, arm or hand)"' in survey
    assert 'label: "Left lower limb (hip, leg or foot)"' in survey
    assert 'label: "Right upper limb (shoulder, arm or hand)"' in survey
    assert 'label: "Right lower limb (hip, leg or foot)"' in survey
    assert 'testID="onb-other-area-input"' in onboarding
    assert 'testID="onb-other-area-save"' in onboarding
    assert 'label: "Other"' in survey
    assert 'testID="onb-other-goal-input"' in onboarding
    assert 'testID="onb-other-goal-save"' in onboarding
    assert 'key: "medical_conditions"' in survey
    assert 'testID="onb-other-condition-input"' in onboarding
    assert 'testID="onb-other-condition-save"' in onboarding
    assert "affected_areas: Optional[List[str]]" in server
    assert "affected_areas_other: Optional[str]" in server
    assert "secondary_goals_other: Optional[str]" in server
    assert "medical_conditions: Optional[List[str]]" in server
    assert "medical_conditions_other: Optional[str]" in server


def test_settings_can_open_all_canonical_survey_questions():
    settings = read("frontend/app/(tabs)/settings.tsx")
    survey_page = read("frontend/app/survey-questions.tsx")

    assert 'testID="settings-survey-questions"' in settings
    assert 'router.push("/survey-questions"' in settings
    assert "PATIENT_SURVEY_STEPS.map" in survey_page
    assert 'testID="survey-questions-list"' in survey_page
    assert "does not change your saved answers" in survey_page


def test_onboarding_finish_recovers_stale_session_and_reports_failures():
    onboarding = read("frontend/app/onboarding.tsx")
    auth = read("frontend/src/auth.ts")
    assert "if (response.status === 401)" in onboarding
    assert "const refreshedUser = await signIn" in onboarding
    assert 'headers: userId ? { "X-User-Id": userId } : undefined' in onboarding
    assert 'testID="onb-save-error"' in onboarding
    assert 'router.replace(isReadinessUpdate ? "/task-intro?mode=initial" : "/")' in onboarding
    assert 'uid && !headers.has("X-User-Id")' in auth


def test_journey_prioritizes_patient_story_and_map_uses_captured_view_only():
    journey = read("frontend/app/(tabs)/journey.tsx")
    movement_map = read("frontend/app/movement-map.tsx")
    assert journey.index("Journal & milestones") < journey.index("Learn about stroke recovery")
    assert journey.index("Assessment history") < journey.index("Learn about stroke recovery")
    assert 'testID="movement-map-back-view"' not in movement_map
    assert "Front-view map available" not in movement_map


def test_display_preferences_are_shared_and_brightness_is_adjustable():
    root_layout = read("frontend/app/_layout.tsx")
    display = read("frontend/src/displayPreferences.tsx")
    settings = read("frontend/app/(tabs)/settings.tsx")
    preferences = read("frontend/src/userPreferences.ts")
    assert "DisplayPreferencesProvider" in root_layout
    assert "subscribeUserPreferences" in display
    assert 'testID="display-brightness-overlay"' in display
    assert 'testID="settings-brightness-slider"' in settings
    assert 'title="Dark mode"' in settings
    assert "brightness: 94" in preferences


def test_each_home_session_confirms_patient_or_carer():
    session_check = read("frontend/app/session-check.tsx")
    assert "Who is starting this session?" in session_check
    assert 'type SessionActor = "patient" | "carer"' in session_check
    assert 'storage.setItem("current_session_actor_v1", actor)' in session_check
