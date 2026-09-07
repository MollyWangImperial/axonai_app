"""Restart a patient's app journey without deleting their sign-in identity."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field


class AccountResetRequest(BaseModel):
    confirmation: Literal["RESET"]
    request_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


ACTIVITY_COLLECTIONS = (
    "assessments", "assessment_task_progress", "exercise_repetitions",
    "journal_entries", "chat_sessions", "alira_activities", "alira_check_ins",
    "alira_care_reviews", "alira_functional_issue_reports", "login_handoffs",
)

# Do not cancel appointments/subscriptions or erase payment/audit records when
# restarting the testing journey. They do not contribute to patient progress.
IDENTITY_FIELDS = (
    "_id", "id", "name", "email", "role", "created_at", "credits", "google",
    "trial_access_granted", "trial_access_granted_at", "last_login_at",
    "subscription_active", "subscription_id", "subscription_plan", "subscription_period_end",
    "stripe_customer_id",
)


async def reset_patient_account(db, user_id, payload, *, delete_videos, clear_local):
    """A durable pending marker makes interrupted cleanup retryable, not success.

    Other account requests are blocked until all cleanup finishes. The request
    id makes a retry after a lost success response harmless, including after the
    patient has started filling out their new survey.
    """
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("trial_access_granted"):
        raise HTTPException(401, "Sign in required")
    if user.get("role") != "patient":
        raise HTTPException(403, "Account reset is only available for patient accounts.")
    if not user.get("reset_pending") and user.get("last_reset_request_id") == payload.request_id:
        return user

    now = datetime.now(timezone.utc).isoformat()
    pending = user.get("reset_pending")
    if not pending:
        pending = {"request_id": payload.request_id, "started_at": now}
        result = await db.users.update_one(
            {"id": user_id, "reset_pending": {"$exists": False}},
            {"$set": {"reset_pending": pending}},
        )
        if result.matched_count != 1:
            raise HTTPException(409, "Another reset is in progress. Please retry.")

    # Delete blobs before their ownership metadata, so an interrupted reset
    # still knows exactly which files to remove on the next attempt.
    await delete_videos(user_id)
    for collection in ACTIVITY_COLLECTIONS:
        await db[collection].delete_many({"user_id": user_id})
    await db.plan_signoffs.delete_many({"patient_user_id": user_id})
    await clear_local(user_id)

    fresh = {key: user[key] for key in IDENTITY_FIELDS if key in user}
    fresh.update(
        credits=max(100, int(user.get("credits") or 0)),
        onboarding_complete=False, profile=None, consent={}, consent_audit=[],
        data_permissions={}, initial_assessment_completed_at=None,
        daily_checkins={}, reward_milestones_acknowledged=[],
        account_generation=int(user.get("account_generation") or 0) + 1,
        account_reset_at=now, last_reset_request_id=pending["request_id"],
    )
    result = await db.users.replace_one(
        {"id": user_id, "reset_pending.request_id": pending["request_id"]}, fresh,
    )
    if result.matched_count != 1:
        raise HTTPException(409, "Account reset could not finish. Please retry.")
    return fresh
