"""Encouragement mechanism (spec section 10).

Points reward effort, safe participation, and personal progress - never only
perfect completion. A session at reduced intensity, or one completed with a
caregiver's help, earns exactly the same points as any other session, because
the recorded activity does not and should not distinguish "how well" it went.

Streaks include streak freezes: a day is never counted as broken when the
patient chose a rest or recovery day, reported heavy fatigue, or reported
feeling unwell in that day's check-in. All copy avoids framing illness,
fatigue, or missed sessions as failure.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

ENCOURAGEMENT_VERSION = "rehyn-encouragement-1.0"

POINTS_PER_EXERCISE = 5
POINTS_PER_SESSION_DAY = 20
POINTS_PER_ROUND = 50
POINTS_PER_CHECKIN_TAP = 2
ROUND_LENGTH_DAYS = 7

MEDALS = (
    {"id": "persistence_pro", "name": "Persistence Pro", "threshold": 200},
    {"id": "persistence_champion", "name": "Persistence Champion", "threshold": 500},
    {"id": "persistence_master", "name": "Persistence Master", "threshold": 1000},
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
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    activities = list(activities or [])
    check_ins = list(check_ins or [])
    daily_checkins = dict(daily_checkins or {})

    session_days: set = set()
    exercise_count = 0
    for activity in activities:
        completed = _as_utc(activity.get("completed_at"))
        if not completed:
            continue
        exercise_count += 1
        session_days.add(completed.date())

    tap_days = 0
    for day, record in daily_checkins.items():
        try:
            date.fromisoformat(str(day))
        except ValueError:
            continue
        if (record or {}).get("status") in {"in_progress", "complete"}:
            tap_days += 1

    rounds_completed = len(session_days) // ROUND_LENGTH_DAYS
    points = (
        exercise_count * POINTS_PER_EXERCISE
        + len(session_days) * POINTS_PER_SESSION_DAY
        + rounds_completed * POINTS_PER_ROUND
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
            "session_days": len(session_days),
            "rounds_completed": rounds_completed,
            "check_in_days": tap_days,
            "points_per_exercise": POINTS_PER_EXERCISE,
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
