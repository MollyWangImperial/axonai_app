"""Append-only, privacy-conscious action logging for Alira.

Each local calendar date gets its own folder and JSONL file. The logger records
what Alira did and why without storing raw conversations or direct identifiers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_LOG_DIR = Path(__file__).resolve().parent / ".local_state" / "alira_action_logs"
SENSITIVE_KEYS = {
    "answers",
    "api_key",
    "authorization",
    "email",
    "message",
    "name",
    "patient_note",
    "prompt",
    "raw_text",
    "sdp",
    "text",
    "token",
    "transcript",
}
MAX_DETAIL_ITEMS = 50
MAX_STRING_LENGTH = 500


def _reference(prefix: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digest = hashlib.sha256(f"rehyn-alira-log:{prefix}:{value}".encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _clean_label(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower()).strip("_")
    return (cleaned or fallback)[:80]


def _sanitized(value: Any, key: Optional[str] = None, depth: int = 0) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[redacted]"
    if depth >= 5:
        return "[max-depth]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    if isinstance(value, Mapping):
        output: Dict[str, Any] = {}
        for item_key, item_value in list(value.items())[:MAX_DETAIL_ITEMS]:
            safe_key = _clean_label(str(item_key), "field")
            output[safe_key] = _sanitized(item_value, str(item_key), depth + 1)
        return output
    if isinstance(value, (list, tuple, set)):
        return [_sanitized(item, depth=depth + 1) for item in list(value)[:MAX_DETAIL_ITEMS]]
    return str(value)[:MAX_STRING_LENGTH]


class AliraActionLogger:
    """Write one flushed JSON object per consequential Alira action."""

    def __init__(self, base_dir: Optional[Path | str] = None, timezone_name: Optional[str] = None):
        configured_dir = base_dir or os.environ.get("ALIRA_ACTION_LOG_DIR") or DEFAULT_LOG_DIR
        self.base_dir = Path(configured_dir).expanduser().resolve()
        configured_timezone = timezone_name or os.environ.get("ALIRA_ACTION_LOG_TIMEZONE", "Europe/London")
        try:
            self.timezone = ZoneInfo(configured_timezone)
        except ZoneInfoNotFoundError:
            self.timezone = datetime.now().astimezone().tzinfo or timezone.utc
        self._lock = threading.Lock()

    def record(
        self,
        action: str,
        *,
        source: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: str = "completed",
        details: Optional[Mapping[str, Any]] = None,
        occurred_at: Optional[datetime] = None,
    ) -> Path:
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        local_timestamp = timestamp.astimezone(self.timezone)
        date_folder = self.base_dir / local_timestamp.date().isoformat()
        log_path = date_folder / "alira-actions.jsonl"
        event = {
            "event_id": "ala_" + uuid.uuid4().hex[:20],
            "timestamp": local_timestamp.isoformat(),
            "action": _clean_label(action, "unknown_action"),
            "source": _clean_label(source, "unknown_source"),
            "status": _clean_label(status, "unknown_status"),
            "user_ref": _reference("user", user_id),
            "session_ref": _reference("session", session_id),
            "details": _sanitized(details or {}),
        }
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self._lock:
            date_folder.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", buffering=1) as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        return log_path
