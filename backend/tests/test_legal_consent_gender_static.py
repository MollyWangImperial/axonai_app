from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_full_terms_and_privacy_content_are_present():
    legal = read("frontend/src/legalContent.ts")

    assert "14. Contact, complaints and governing law" in legal
    assert "13. Changes to this notice" in legal
    assert "IMPORTANT SAFETY INFORMATION" not in legal  # headings use patient-friendly sentence case
    assert "Build note" not in legal
    assert "Accepting these Terms is not that consent" in legal


def test_terms_gate_requires_two_separate_acknowledgements():
    consent = read("frontend/app/consent.tsx")

    assert 'testID="consent-terms-checkbox"' in consent
    assert 'testID="consent-health-checkbox"' in consent
    assert "const ready = termsChecked && healthChecked" in consent
    assert 'pathname: "/data-permissions"' in consent
    assert "setPendingConsentAccepted" in consent


def test_fresh_app_launch_routes_to_terms_before_sign_in():
    layout = read("frontend/app/_layout.tsx")
    sign_in = read("frontend/app/sign-in.tsx")

    assert 'router.replace("/consent")' in layout
    assert '"sign-in", "consent", "privacy-policy"' in layout
    assert "hasPendingConsent" in layout
    assert "await setConsentAccepted(user.id)" in sign_in
    assert "await clearPendingConsent()" in sign_in


def test_settings_open_full_legal_screens_and_removed_care_circle_sharing():
    settings = read("frontend/app/(tabs)/settings.tsx")
    account_center = read("frontend/app/account-center.tsx")

    assert 'router.push("/privacy-policy"' in settings
    assert 'router.push("/data-permissions"' in settings
    assert "Share with care circle" not in account_center


def test_gender_question_and_server_profile_fields_are_comprehensive():
    survey = read("frontend/src/patientSurvey.ts")
    server = read("backend/server.py")

    for label in (
        "Female",
        "Male",
        "Transgender woman",
        "Transgender man",
        "Non-binary",
        "Another gender identity",
        "Prefer not to say",
    ):
        assert label in survey
    assert "gender: Optional[str]" in server
    assert "gender_self_description: Optional[str]" in server


def test_consent_and_optional_improvement_choice_are_account_backed():
    server = read("backend/server.py")
    auth = read("frontend/src/auth.ts")
    data_permissions = read("frontend/app/data-permissions.tsx")

    assert '@api_router.get("/users/consent")' in server
    assert '@api_router.post("/users/consent")' in server
    assert '@api_router.get("/users/data-permissions")' in server
    assert '@api_router.post("/users/data-permissions")' in server
    assert 'authedFetch("/api/users/consent"' in auth
    assert "Off by default" in data_permissions
    assert "Raw movement videos are not used for model training" in data_permissions


def test_care_facility_has_clear_profile_privacy_note():
    profile = read("frontend/app/(tabs)/profile.tsx")

    assert 'testID="profile-facility-privacy-note"' in profile
    assert "Rehyn will not contact this facility or share your profile with it." in profile
