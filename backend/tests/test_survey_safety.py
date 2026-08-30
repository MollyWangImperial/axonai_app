from datetime import datetime, timedelta, timezone

from backend.alira_care_orchestrator import (
    QUESTION_BANK,
    SURVEY_PREFACE,
    build_adaptive_care_plan,
    evaluate_survey_safety,
    validate_check_in_answers,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def test_every_due_survey_has_the_required_preface_and_optional_questions():
    plan = build_adaptive_care_plan(
        {},
        [{
            "id": "initial-1",
            "assessment_package": "initial",
            "created_at": (NOW - timedelta(days=4)).isoformat(),
            "functional_issues": [],
            "rehab_plan": [],
        }],
        [],
        now=NOW,
    )

    assert plan["survey"]["due"] is True
    assert plan["survey"]["preface"] == SURVEY_PREFACE
    assert "This takes about two minutes." in SURVEY_PREFACE
    assert "Every question is optional" in SURVEY_PREFACE
    assert "In an emergency, call 999." in SURVEY_PREFACE
    assert plan["survey"]["all_questions_optional"] is True
    assert plan["survey"]["may_stop_at_any_point"] is True
    assert all(question["required"] is False for question in QUESTION_BANK.values())
    assert {"sudden_change", "falls", "emotional_safety"}.issubset(
        {question["id"] for question in plan["survey"]["questions"]}
    )


def test_partial_optional_answers_are_valid():
    assert validate_check_in_answers({"falls": "near_fall"}) == {"falls": "near_fall"}
    assert validate_check_in_answers({"emotional_safety": "prefer_not_to_say"}) == {
        "emotional_safety": "prefer_not_to_say"
    }


def test_new_stroke_symptoms_always_return_an_immediate_999_response():
    safety = evaluate_survey_safety({"answers": {"sudden_change": "yes"}})

    assert safety["status"] == "emergency"
    assert safety["code"] == "possible_stroke_or_medical_emergency"
    assert safety["call_999"] is True
    assert safety["offer_call_999"] is True
    assert "call 999 now" in safety["message"].lower()
    assert "even if the symptoms improve" in safety["message"].lower()


def test_fall_response_separates_999_criteria_from_nhs_111():
    safety = evaluate_survey_safety({"answers": {"falls": "fall_with_injury"}})

    assert safety["status"] == "urgent_review"
    assert safety["code"] == "fall_with_possible_injury"
    assert "head, back, neck or hip" in safety["message"]
    assert "cannot get up" in safety["message"]
    assert "NHS 111" in safety["message"]
    assert safety["blocks_exercise"] is True
    assert safety["offer_call_999"] is True


def test_free_text_fall_disclosure_gets_the_same_immediate_routing_criteria():
    safety = evaluate_survey_safety({"answers": {}, "patient_note": "I had a fall this morning."})

    assert safety["code"] == "fall_details_needed"
    assert "Call 999 now" in safety["message"]
    assert "NHS 111" in safety["message"]


def test_self_harm_responses_distinguish_immediate_danger_from_urgent_support():
    emergency = evaluate_survey_safety({"answers": {"emotional_safety": "cannot_keep_safe"}})
    urgent = evaluate_survey_safety({"answers": {"emotional_safety": "thoughts_but_safe"}})

    assert emergency["status"] == "emergency"
    assert emergency["call_999"] is True
    assert "call 999 or go to a&e now" in emergency["message"].lower()
    assert urgent["status"] == "urgent_review"
    assert urgent["offer_call_999"] is True
    assert "NHS 111" in urgent["message"]
    assert "116 123" in urgent["message"]


def test_major_non_sudden_regression_pauses_activity_and_explains_when_999_is_needed():
    safety = evaluate_survey_safety({"answers": {"function_change": "much_harder", "sudden_change": "no"}})

    assert safety["code"] == "major_functional_decline"
    assert safety["status"] == "urgent_review"
    assert safety["blocks_assessment"] is True
    assert safety["blocks_exercise"] is True
    assert safety["offer_call_999"] is True
    assert "If this change happened suddenly" in safety["message"]


def test_explicit_denials_in_a_patient_note_do_not_create_a_false_emergency():
    safety = evaluate_survey_safety({
        "answers": {},
        "patient_note": "I have no suicidal thoughts, no face droop and no arm weakness.",
    })

    assert safety["status"] == "clear"


def test_denial_of_one_sign_does_not_hide_a_different_emergency_sign():
    safety = evaluate_survey_safety({
        "answers": {},
        "patient_note": "I have no face droop, but I have chest pain.",
    })

    assert safety["status"] == "emergency"
    assert safety["code"] == "possible_stroke_or_medical_emergency"
