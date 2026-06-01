"""Append-only JSONL audit log for all user interactions."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compcoach.config import AUDIT_LOG_DIR, OPENAI_MODEL

_SENSITIVE_KEYS = frozenset({"password", "password_hash", "initial_password", "api_key"})


class AuditLogger:
    """Thread-safe audit logger (one JSON object per line)."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or AUDIT_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.session_id: str | None = None

    def start_session(self, username: str) -> str:
        self.session_id = str(uuid.uuid4())
        self.log("session_started", username=username)
        return self.session_id

    def _log_path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"audit-{day}.jsonl"

    def log(
        self,
        event: str,
        *,
        username: str | None = None,
        session_id: str | None = None,
        **details: Any,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "username": username,
            "session_id": session_id or self.session_id,
            "details": _sanitize(details),
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with self._log_path().open("a", encoding="utf-8") as f:
                f.write(line)

    def log_input(
        self,
        event: str,
        *,
        username: str | None,
        prompt: str,
        value: str,
        **extra: Any,
    ) -> None:
        """Log a user-provided value (never use for passwords)."""
        self.log(
            event,
            username=username,
            prompt=prompt,
            value=value,
            **extra,
        )

    def log_assistant_message(
        self,
        *,
        username: str,
        chat_id: int,
        turn_number: int,
        content: str,
        llm_latency_ms: int,
        is_opening: bool = False,
    ) -> None:
        self.log(
            "assistant_message",
            username=username,
            chat_id=chat_id,
            turn_number=turn_number,
            is_opening=is_opening,
            content_length=len(content),
            word_count=len(content.split()),
            llm_latency_ms=llm_latency_ms,
            model=OPENAI_MODEL,
        )

    def log_search_courses(
        self,
        *,
        username: str,
        chat_id: int | None,
        turn_number: int | None,
        query: str,
        domain: str | None,
        area: str | None,
        dimension: str | None,
        results_count: int,
        course_slugs: list[str],
        tool_latency_ms: int,
    ) -> None:
        self.log(
            "search_courses",
            username=username,
            chat_id=chat_id,
            turn_number=turn_number,
            query=query,
            domain=domain,
            area=area,
            dimension=dimension,
            results_count=results_count,
            course_slugs=course_slugs,
            tool_latency_ms=tool_latency_ms,
        )


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if key in _SENSITIVE_KEYS:
            out[key] = "[REDACTED]"
        elif isinstance(val, dict):
            out[key] = _sanitize(val)
        else:
            out[key] = val
    return out
