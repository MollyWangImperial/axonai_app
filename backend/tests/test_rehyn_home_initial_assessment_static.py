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
    assert '"Initial Assessment"' in home
    assert 'target: "assessment", mode: "initial"' in home
    assert "same seven guided upper-limb tasks" in home
    assert 'pathname: "/session-check"' in home


def test_initial_assessment_has_no_package_or_task_choice():
    intro = read("frontend/app/task-intro.tsx")
    assert 'const packageId: AssessmentPackageId = "upper_limb"' in intro
    assert "launch your next guided task automatically" in intro
    assert "tasks.map(" not in intro
    assert "task-row-" not in intro
    assert "Choose assessment package" not in intro
    assert "setSelectedTaskId" not in intro


def test_onboarding_collects_pdf_feedback_fields():
    onboarding = read("frontend/app/onboarding.tsx")
    server = read("backend/server.py")
    assert 'value: "under_20"' in onboarding
    assert 'key: "affected_areas"' in onboarding
    assert 'label: "Left upper limb (shoulder, arm or hand)"' in onboarding
    assert 'label: "Left lower limb (hip, leg or foot)"' in onboarding
    assert 'label: "Right upper limb (shoulder, arm or hand)"' in onboarding
    assert 'label: "Right lower limb (hip, leg or foot)"' in onboarding
    assert 'testID="onb-other-area-input"' in onboarding
    assert 'testID="onb-other-area-save"' in onboarding
    assert 'key: "medical_conditions"' in onboarding
    assert 'testID="onb-other-condition-input"' in onboarding
    assert 'testID="onb-other-condition-save"' in onboarding
    assert "affected_areas: Optional[List[str]]" in server
    assert "affected_areas_other: Optional[str]" in server
    assert "medical_conditions: Optional[List[str]]" in server
    assert "medical_conditions_other: Optional[str]" in server


def test_onboarding_finish_recovers_stale_session_and_reports_failures():
    onboarding = read("frontend/app/onboarding.tsx")
    auth = read("frontend/src/auth.ts")
    assert "if (response.status === 401)" in onboarding
    assert "const refreshedUser = await signIn" in onboarding
    assert 'headers: userId ? { "X-User-Id": userId } : undefined' in onboarding
    assert 'testID="onb-save-error"' in onboarding
    assert "router.replace(\"/\")" in onboarding
    assert 'uid && !headers.has("X-User-Id")' in auth


def test_each_home_session_confirms_patient_or_carer():
    session_check = read("frontend/app/session-check.tsx")
    assert "Who is starting this session?" in session_check
    assert 'type SessionActor = "patient" | "carer"' in session_check
    assert 'storage.setItem("current_session_actor_v1", actor)' in session_check
