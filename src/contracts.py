
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class ToolStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    CONFLICT = "conflict"


class NextAction(str, Enum):
    NONE = "none"
    CORRECT_ARGUMENTS = "correct_arguments"
    CHOOSE_REGISTERED_TOOL = "choose_registered_tool"
    REQUEST_AUTHORIZATION = "request_authorization"
    RETRY_OR_REVIEW = "retry_or_review"
    CONTACT_SUPPORT = "contact_support"


class ToolInvocationInput(BaseModel):
    """Validated request envelope for the invocation flow."""

    model_config = ConfigDict(extra="forbid", strict=True)

    tool_name: StrictStr = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    arguments: dict[str, Any]
    request_id: StrictStr = Field(min_length=1, max_length=100)


class OrderLookupInput(BaseModel):
    """Arguments accepted by the order.lookup tool."""

    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: StrictStr = Field(
        min_length=8,
        max_length=16,
        pattern=r"^ORD-[0-9]{4,12}$",
    )


class OrderLookupOutput(BaseModel):
    """Public output for a successful order lookup."""

    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: StrictStr
    status: StrictStr
    estimated_delivery: StrictStr | None = None


class ToolResult(BaseModel):
    """Stable result envelope used across the invocation pipeline."""

    model_config = ConfigDict(extra="forbid")

    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    next_action: NextAction = NextAction.NONE
    events: list[dict[str, Any]] = Field(default_factory=list)