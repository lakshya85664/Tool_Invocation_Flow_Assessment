
"""Structured, JSON-friendly observability for tool invocations."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("tool_invocation")


def build_log_record(
    *,
    request_id: str,
    tool_name: str,
    stage: str,
    status: str,
    duration_ms: float = 0.0,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a consistent log record without exposing sensitive arguments."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "tool_name": tool_name,
        "stage": stage,
        "status": status,
        "duration_ms": round(max(0.0, duration_ms), 2),
        "details": details or {},
    }


def emit_log(record: dict[str, Any]) -> str:
    """Serialize and emit a structured JSON log record."""
    serialized = json.dumps(record, sort_keys=True, default=str)
    logger.info("%s", serialized)
    return serialized
