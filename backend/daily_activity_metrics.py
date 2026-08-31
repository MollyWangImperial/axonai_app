"""Daily activity-driven progress metrics (spec section 6).

Patients are shown their ability to perform everyday activities and the level
of assistance needed - never raw biomechanics. Every result carries an honest
status: "complete" (observed in an assessment), "estimated" (partly observed,
or reported by the patient or caregiver rather than measured), or
"not_assessed" (never fabricated into a low score).

Change is always reported against the patient's own baseline, not other
people. Raw ROM stays internal for plan generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

STATUS_COMPLETE = "complete"
STATUS_ESTIMATED = "estimated"
STATUS_NOT_ASSESSED = "not_assessed"
STATUS_LABELS = (STATUS_COMPLETE, STATUS_ESTIMATED, STATUS_NOT_ASSESSED)

# Reported assistance mapping from the intake/survey screen answers onto the
# shared six-level scale (spec 6.2). These are patient/caregiver reports, so
# any activity relying on them alone is labelled "estimated".
_MOBILITY_TO_ASSISTANCE = {
    "independent": "fully_independent",
    "cane": "fully_independent",
    "walker": "fully_independent",
    "person_assist": "moderate_assistance",
    "wheelchair": "maximum_assistance",
    "unable_walk": "unable",
    "not_cleared": "unable",
}
_ARM_TO_ASSISTANCE = {
    "not_affected": "fully_independent",
    "most_movements": "supervision_only",
    "some_movement": "minimum_assistance",
    "help_only": "moderate_assistance",
    "no_movement": "maximum_assistance",
}
_HAND_TO_ASSISTANCE = {
    "not_affected": "fully_independent",
    "opens_and_moves": "supervision_only",
    "some_finger_movement": "minimum_assistance",
    "very_little_movement": "moderate_assistance",
    "no_movement": "maximum_assistance",
}


def _observed_upper(row: Mapping[str, Any]) -> Optional[str]:
    reach = row.get("reach_completion")
    if reach is None:
        return None
    if reach >= 0.85:
        return "Reached and completed the arm tasks steadily"
    if reach >= 0.5:
        return "Completed part of the arm tasks"
    return "Arm tasks were difficult to complete"


def _observed_hand(row: Mapping[str, Any]) -> Optional[str]:
    opening = row.get("hand_opening")
    pinch = row.get("pinch_grip")
    if opening is None and pinch is None:
        return None
    strongest = max(value for value in (opening, pinch) if value is not None)
    if strongest >= 0.75:
        return "Opened and used the hand well in the tasks"
    if strongest >= 0.4:
        return "Used the hand with some difficulty"
    return "Hand tasks were difficult to complete"


def _observed_walking(row: Mapping[str, Any]) -> Optional[str]:
    # Only rows from a real assessment carry the walking_skipped key; with no
    # assessment at all, nothing was observed.
    if "walking_skipped" not in row or row.get("walking_skipped"):
        return None
    return "Completed the walking task safely"


def _change_text(latest: Optional[float], baseline: Optional[float], better_when_higher: bool = True) -> Optional[str]:
    if latest is None or baseline is None:
        return None
    delta = latest - baseline
    if abs(delta) < 0.05:
        return "About the same as your baseline"
    improved = delta > 0 if better_when_higher else delta < 0
    return "Better than your baseline" if improved else "Not yet back to your baseline"


def build_daily_activity_metrics(
    assessment_rows: Sequence[Mapping[str, Any]],
    profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Derive activity-level progress from assessment metric rows.

    `assessment_rows` are the per-assessment rows already produced for the
    progress series (oldest first). Nothing is fabricated: an activity whose
    supporting tasks were not observed is `not_assessed` (with any
    patient-reported level shown as `estimated`), never a low score.
    """
    profile = dict(profile or {})
    rows = list(assessment_rows or [])
    latest = rows[-1] if rows else {}
    baseline = rows[0] if rows else {}

    mobility_reported = _MOBILITY_TO_ASSISTANCE.get(str(profile.get("mobility_level") or "").lower())
    arm_reported = _ARM_TO_ASSISTANCE.get(str(profile.get("affected_arm_movement") or "").lower())
    hand_reported = _HAND_TO_ASSISTANCE.get(str(profile.get("affected_hand_movement") or "").lower())

    def activity(
        name: str,
        domain: str,
        observed: Optional[str],
        reported_level: Optional[str],
        change: Optional[str],
    ) -> Dict[str, Any]:
        if observed:
            status = STATUS_COMPLETE
        elif reported_level:
            status = STATUS_ESTIMATED
        else:
            status = STATUS_NOT_ASSESSED
        return {
            "activity": name,
            "domain": domain,
            "status": status,
            "observed": observed,
            "reported_assistance_level": reported_level,
            "change_from_baseline": change if status == STATUS_COMPLETE else None,
            "source": (
                "camera_assessment" if observed
                else "patient_or_caregiver_report" if reported_level
                else "none"
            ),
        }

    upper_observed = _observed_upper(latest)
    hand_observed = _observed_hand(latest)
    walking_observed = _observed_walking(latest)

    activities = [
        activity(
            "Eating and drinking", "upper_limb",
            upper_observed, arm_reported,
            _change_text(latest.get("reach_completion"), baseline.get("reach_completion")),
        ),
        activity(
            "Dressing", "upper_limb",
            upper_observed if upper_observed and hand_observed else None,
            arm_reported or hand_reported,
            _change_text(latest.get("reach_completion"), baseline.get("reach_completion")),
        ),
        activity(
            "Grooming and self-care", "hand",
            hand_observed, hand_reported,
            _change_text(latest.get("hand_opening"), baseline.get("hand_opening")),
        ),
        activity(
            "Moving around", "lower_limb",
            walking_observed, mobility_reported,
            None if latest.get("walking_skipped") else "Walking was completed at both points" if rows and not baseline.get("walking_skipped") and walking_observed else None,
        ),
    ]

    return {
        "activities": activities,
        "status_labels": list(STATUS_LABELS),
        "principles": {
            "no_score_when_not_assessed": True,
            "no_pass_fail_thresholds": True,
            "change_is_against_own_baseline": True,
            "raw_biomechanics_internal_only": True,
        },
        "reason": (
            "Progress is expressed as everyday activities and the help needed, from what was actually observed "
            "or reported. A result that was not assessed is shown as not assessed, never as a low score."
        ),
    }
