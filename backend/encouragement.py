"""Encouragement mechanism (spec section 10).

Rewards are separate from movement-quality grades: 10 per completed daily
plan, 20 per completed assessment and 2 per daily check-in. Repetitions,
individual routines and weekly rounds do not add bonus points.

Streaks include streak freezes: a day is never counted as broken when the
patient chose a rest or recovery day, reported heavy fatigue, or reported
feeling unwell in that day's check-in. All copy avoids framing illness,
fatigue, or missed sessions as failure.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

ENCOURAGEMENT_VERSION = "rehyn-encouragement-2.0"

POINTS_PER_REPETITION = 0
POINTS_PER_CAREGIVER_ROUTINE = 0
LEGACY_REPETITIONS_PER_EXERCISE = 5
POINTS_PER_SESSION_DAY = 10
POINTS_PER_ASSESSMENT = 20
POINTS_PER_ROUND = 0
POINTS_PER_CHECKIN_TAP = 2
ROUND_LENGTH_DAYS = 7

MEDALS = (
    {"id": "hundred_point_medal", "name": "Rehyn Consistency Champion", "threshold": 100},
    {"id": "persistence_pro", "name": "Rehyn Dedication Star", "threshold": 200},
    {"id": "persistence_champion", "name": "Rehyn Perseverance Champion", "threshold": 500},
    {"id": "persistence_master", "name": "Rehyn Perseverance Master", "threshold": 1000},
)


def _as_utc(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _answers(check_in: Mapping[str, Any]) -> Mapping[str, Any]:
    answers = check_in.get("answers")
    return answers if isinstance(answers, Mapping) else {}


def _excused_dates(check_ins: Sequence[Mapping[str, Any]]) -> set:
    """Days on which a freeze applies: chosen rest, heavy fatigue, or illness."""
    excused = set()
    for check_in in check_ins:
        created = _as_utc(check_in.get("created_at"))
        if not created:
            continue
        answers = _answers(check_in)
        if (
            str(answers.get("session_preference") or "").lower() == "rest_recovery"
            or str(answers.get("fatigue") or "").lower() == "a_lot"
            or str(answers.get("feeling_today") or "").lower() == "unwell"
        ):
            excused.add(created.date())
    return excused


def compute_rewards(
    activities: Optional[Sequence[Mapping[str, Any]]],
    check_ins: Optional[Sequence[Mapping[str, Any]]] = None,
    daily_checkins: Optional[Mapping[str, Mapping[str, Any]]] = None,
    *,
    assessments: Optional[Sequence[Mapping[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    activities = list(activities or [])
    check_ins = list(check_ins or [])
    daily_checkins = dict(daily_checkins or {})

    session_days: set = set()
    exercise_count = 0
    repetition_count = 0
    caregiver_routine_count = 0
    for activity in activities:
        completed = _as_utc(activity.get("completed_at"))
        if not completed:
            continue
        exercise_count += 1
        raw_repetitions = activity.get("completed_reps")
        if raw_repetitions is None:
            completed_repetitions = LEGACY_REPETITIONS_PER_EXERCISE
        else:
            try:
                completed_repetitions = max(0, int(raw_repetitions))
            except (TypeError, ValueError):
                completed_repetitions = 0
        repetition_count += completed_repetitions
        if str(activity.get("exercise_id") or "").startswith("CG_"):
            caregiver_routine_count += 1
        session_days.add(completed.date())

    tap_days = 0
    completed_plan_days = set()
    for day, record in daily_checkins.items():
        try:
            date.fromisoformat(str(day))
        except ValueError:
            continue
        if (record or {}).get("status") in {"in_progress", "complete"}:
            tap_days += 1
        if (record or {}).get("status") == "complete":
            completed_plan_days.add(day)

    # A stored assessment id is the award identity. Test shortcuts and unfinished
    # collections do not earn assessment points; retries cannot double the award.
    completed_assessments = set()
    for assessment in assessments or []:
        if assessment.get("testing_shortcut") or assessment.get("result_provenance") == "generated_testing_sample":
            continue
        tasks = assessment.get("task_results") or []
        summary = assessment.get("patient_summary") or {}
        complete = summary.get("collection_complete") is True or (bool(tasks) and all(
            (task.get("metrics") or {}).get("walking_skipped") or (
                int(task.get("total_steps") or 0) > 0
                and len(task.get("steps") or []) >= int(task.get("total_steps") or 0)
            ) for task in tasks
        ))
        expected = set(assessment.get("assigned_task_ids") or [])
        if expected and not expected.issubset({task.get("task_id") for task in tasks}):
            complete = False
        if complete and assessment.get("id") and assessment.get("created_at"):
            completed_assessments.add(assessment["id"])

    rounds_completed = len(session_days) // ROUND_LENGTH_DAYS
    points = (
        len(completed_plan_days) * POINTS_PER_SESSION_DAY
        + len(completed_assessments) * POINTS_PER_ASSESSMENT
        + tap_days * POINTS_PER_CHECKIN_TAP
    )

    # Streak with freezes: walk backwards from the most recent qualifying day.
    excused = _excused_dates(check_ins)
    streak = 0
    cursor = now.date()
    if cursor not in session_days and cursor not in excused:
        # Today is still open - it never breaks a streak by itself.
        cursor -= timedelta(days=1)
    frozen_days_used = 0
    while cursor in session_days or cursor in excused:
        if cursor in session_days:
            streak += 1
        else:
            frozen_days_used += 1
        cursor -= timedelta(days=1)

    medals: List[Dict[str, Any]] = []
    for medal in MEDALS:
        medals.append({
            **medal,
            "earned": points >= medal["threshold"],
            "progress": min(1.0, round(points / medal["threshold"], 3)),
        })
    next_medal = next((medal for medal in medals if not medal["earned"]), None)

    if not session_days:
        message = "Every recovery starts with a single session. Alira is ready whenever you are."
    elif streak >= 3:
        message = f"You have shown up {streak} days in a row. Steady effort like this is what recovery is built on."
    else:
        message = "Points here reward effort and safe participation - a lighter or assisted session counts just as much."

    return {
        "version": ENCOURAGEMENT_VERSION,
        "points": points,
        "breakdown": {
            "exercises_completed": exercise_count,
            "repetitions_completed": repetition_count,
            "caregiver_routines_completed": caregiver_routine_count,
            "session_days": len(session_days),
            "rounds_completed": rounds_completed,
            "check_in_days": tap_days,
            "completed_plan_days": len(completed_plan_days),
            "assessments_completed": len(completed_assessments),
            "points_per_assessment": POINTS_PER_ASSESSMENT,
            "points_per_repetition": POINTS_PER_REPETITION,
            "points_per_caregiver_routine": POINTS_PER_CAREGIVER_ROUTINE,
            "points_per_session_day": POINTS_PER_SESSION_DAY,
            "points_per_round": POINTS_PER_ROUND,
            "points_per_check_in": POINTS_PER_CHECKIN_TAP,
        },
        "effort_based": True,
        "reduced_intensity_counts": True,
        "assisted_sessions_count": True,
        "streak": {
            "current_days": streak,
            "frozen_days_used": frozen_days_used,
            "freezes_explained": "Rest days you choose, heavy fatigue, and feeling unwell never break your streak.",
        },
        "medals": medals,
        "next_medal": next_medal,
        "message": message,
    }
