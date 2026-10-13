
from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from src.contracts import (
    NextAction,
    ToolInvocationInput,
    ToolResult,
    ToolStatus,
)
from src.observability import build_log_record, emit_log
from src.registry import get_tool
from src.reliability import (
    IdempotencyStore,
    SlidingWindowRateLimiter,
    request_fingerprint,
    retry_on_timeout,
)


# Process-local reliability controls for this assessment.
_rate_limiter = SlidingWindowRateLimiter(
    max_requests=10,
    window_seconds=60.0,
)
_idempotency_store = IdempotencyStore()


def reset_reliability_state() -> None:
    """Reset reliability state for tests and repeatable demonstrations."""
    with _rate_limiter._lock:
        _rate_limiter._requests.clear()

    _idempotency_store.clear()


def dispatch(
    call: dict[str, Any],
    principal: dict[str, Any] | None,
    *,
    max_attempts: int = 1,
) -> ToolResult:
    """Run a tool call through validation, authorization, and execution."""
    events: list[dict[str, Any]] = []
    reliability_events: list[dict[str, Any]] = []
    started = time.monotonic()

    request_id = (
        call.get("request_id", "invalid-request")
        if isinstance(call, dict)
        else "invalid-request"
    )
    tool_name = (
        call.get("name", "unknown")
        if isinstance(call, dict)
        else "unknown"
    )

    def record_event(stage: str, status: str, **details: Any) -> None:
        event = {
            "stage": stage,
            "status": status,
            **details,
        }

        if stage in {
            "request",
            "selection",
            "authorization",
            "validation",
            "execution",
        }:
            events.append(event)
        else:
            reliability_events.append(event)

    def finish(
        status: ToolStatus,
        next_action: NextAction,
        data: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Create a safe result and emit a structured summary log."""
        result = ToolResult(
            status=status,
            data=data if data is not None else {},
            next_action=next_action,
            events=events,
        )

        try:
            emit_log(
                build_log_record(
                    request_id=str(request_id),
                    tool_name=str(tool_name),
                    stage="dispatch",
                    status=status.value,
                    duration_ms=(time.monotonic() - started) * 1000,
                    details={
                        "event_count": len(events),
                        "reliability_events": reliability_events,
                    },
                )
            )
        except Exception:
            # Logging failures must not break the invocation pipeline.
            pass

        return result

    # Stage 1: Validate the request envelope.
    try:
        request = ToolInvocationInput.model_validate({
            "tool_name": call.get("name"),
            "arguments": call.get("arguments"),
            "request_id": call.get("request_id"),
        })
    except (ValidationError, AttributeError, TypeError):
        record_event("request", "invalid")
        return finish(
            ToolStatus.INVALID,
            NextAction.CORRECT_ARGUMENTS,
        )

    request_id = request.request_id
    tool_name = request.tool_name

    record_event(
        "request",
        "accepted",
        request_id=request.request_id,
    )

    # Stage 2: Select the registered tool.
    spec = get_tool(request.tool_name)

    if spec is None:
        record_event("selection", "not_found")
        return finish(
            ToolStatus.NOT_FOUND,
            NextAction.CHOOSE_REGISTERED_TOOL,
        )

    record_event(
        "selection",
        "selected",
        tool=spec.name,
        version=spec.version,
    )

    # Stage 3: Authorize the principal.
    if not isinstance(principal, dict):
        record_event("authorization", "denied")
        return finish(
            ToolStatus.DENIED,
            NextAction.REQUEST_AUTHORIZATION,
        )

    role = principal.get("role")
    principal_id = principal.get("id")

    if (
        not isinstance(role, str)
        or not isinstance(principal_id, str)
        or not principal_id.strip()
        or role not in spec.allowed_roles
    ):
        record_event("authorization", "denied")
        return finish(
            ToolStatus.DENIED,
            NextAction.REQUEST_AUTHORIZATION,
        )

    record_event("authorization", "allowed", role=role)

    # Stage 4: Validate tool arguments.
    try:
        validated_input = spec.input_model.model_validate(
            request.arguments
        )
    except ValidationError as exc:
        record_event(
            "validation",
            "invalid",
            error_count=len(exc.errors()),
        )
        return finish(
            ToolStatus.INVALID,
            NextAction.CORRECT_ARGUMENTS,
        )

    record_event("validation", "valid")

    # Record the fifth stage once, before reliability checks and execution.
    record_event("execution", "started")

    # Validate retry configuration before any handler is called.
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or max_attempts < 1
    ):
        events[-1]["status"] = "invalid_retry_configuration"
        return finish(
            ToolStatus.INVALID,
            NextAction.CORRECT_ARGUMENTS,
        )

    # Reliability control 1: per-principal rate limiting.
    limit = _rate_limiter.check(principal_id)

    if not limit.allowed:
        record_event(
            "rate_limit",
            "rejected",
            retry_after_seconds=limit.retry_after_seconds,
        )
        events[-1]["status"] = "rate_limited"
        return finish(
            ToolStatus.RATE_LIMITED,
            NextAction.RETRY_OR_REVIEW,
        )

    record_event(
        "rate_limit",
        "allowed",
        remaining=limit.remaining,
    )

    # Reliability control 2: idempotency fingerprint.
    fingerprint = request_fingerprint(
        {
            "name": request.tool_name,
            "arguments": request.arguments,
            "request_id": request.request_id,
        },
        principal,
    )

    try:
        found, cached_result = _idempotency_store.get(
            request.request_id,
            fingerprint,
        )
    except ValueError:
        record_event("idempotency", "conflict")
        events[-1]["status"] = "conflict"
        return finish(
            ToolStatus.CONFLICT,
            NextAction.CORRECT_ARGUMENTS,
        )

    if found:
        record_event("idempotency", "replayed")

        # Return the cached result without invoking the handler again.
        replay = cached_result.model_copy(deep=True)
        events[-1]["status"] = "replayed"
        replay.events = [*replay.events, *events]
        return finish(
            replay.status,
            replay.next_action,
            replay.data,
        )

    record_event("idempotency", "new")

    # Reliability control 3: bounded timeout retry.
    try:
        raw_output = retry_on_timeout(
            lambda: spec.handler(validated_input),
            max_attempts=max_attempts,
        )

        output = spec.output_model.model_validate(raw_output)

        events[-1].update({
            "status": "completed",
            "duration_ms": round(
                (time.monotonic() - started) * 1000,
                2,
            ),
        })

        result = finish(
            ToolStatus.OK,
            NextAction.NONE,
            output.model_dump(mode="json"),
        )

        # Cache successful results only.
        _idempotency_store.put(
            request.request_id,
            fingerprint,
            result,
        )
        return result

    except LookupError:
        events[-1]["status"] = "not_found"
        return finish(
            ToolStatus.NOT_FOUND,
            NextAction.CONTACT_SUPPORT,
        )

    except TimeoutError:
        events[-1]["status"] = "timeout"
        return finish(
            ToolStatus.TIMEOUT,
            NextAction.RETRY_OR_REVIEW,
        )

    except ValidationError:
        events[-1]["status"] = "invalid_output"
        return finish(
            ToolStatus.FAILED,
            NextAction.CONTACT_SUPPORT,
        )

    except Exception:
        # Never expose internal provider or handler exception details.
        events[-1]["status"] = "failed"
        return finish(
            ToolStatus.FAILED,
            NextAction.RETRY_OR_REVIEW,
        )
