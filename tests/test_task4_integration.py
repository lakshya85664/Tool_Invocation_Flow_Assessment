
from dataclasses import replace

import pytest

from src.contracts import ToolStatus
from src.dispatcher import dispatch, reset_reliability_state
from src.registry import get_tool


SUPPORT_USER = {
    "id": "support-task4",
    "role": "customer_support",
}

VALID_CALL = {
    "name": "order.lookup",
    "arguments": {"order_id": "ORD-1001"},
    "request_id": "task4-integration-001",
}


@pytest.fixture(autouse=True)
def clean_state():
    reset_reliability_state()
    yield
    reset_reliability_state()


def test_repeated_request_returns_cached_result(monkeypatch):
    spec = get_tool("order.lookup")
    calls = {"count": 0}
    original_handler = spec.handler

    def counted_handler(validated_input):
        calls["count"] += 1
        return original_handler(validated_input)

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=counted_handler),
    )

    first = dispatch(VALID_CALL, SUPPORT_USER)
    second = dispatch(VALID_CALL, SUPPORT_USER)

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.OK
    assert first.data == second.data
    assert calls["count"] == 1


def test_same_request_id_with_different_arguments_conflicts():
    first = dispatch(VALID_CALL, SUPPORT_USER)

    changed_call = {
        **VALID_CALL,
        "arguments": {"order_id": "ORD-1002"},
    }
    second = dispatch(changed_call, SUPPORT_USER)

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.CONFLICT


def test_rate_limit_rejects_excess_requests(monkeypatch):
    # Allow only one request in this test.
    from src import dispatcher

    monkeypatch.setattr(
        dispatcher,
        "_rate_limiter",
        dispatcher.SlidingWindowRateLimiter(
            max_requests=1,
            window_seconds=60,
        ),
    )

    first_call = {
        **VALID_CALL,
        "request_id": "rate-limit-001",
    }
    second_call = {
        **VALID_CALL,
        "request_id": "rate-limit-002",
    }

    first = dispatch(first_call, SUPPORT_USER)
    second = dispatch(second_call, SUPPORT_USER)

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.RATE_LIMITED


def test_timeout_recovers_when_retry_is_enabled(monkeypatch):
    spec = get_tool("order.lookup")
    calls = {"count": 0}
    original_handler = spec.handler

    def timeout_once(validated_input):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("temporary private timeout")
        return original_handler(validated_input)

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=timeout_once),
    )

    result = dispatch(
        {
            **VALID_CALL,
            "request_id": "timeout-recovery-001",
        },
        SUPPORT_USER,
        max_attempts=2,
    )

    assert result.status == ToolStatus.OK
    assert calls["count"] == 2
    assert result.data["order_id"] == "ORD-1001"


def test_timeout_returns_controlled_status_when_retries_exhausted(
    monkeypatch,
):
    spec = get_tool("order.lookup")
    calls = {"count": 0}

    def always_timeout(_validated_input):
        calls["count"] += 1
        raise TimeoutError("private timeout details")

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=always_timeout),
    )

    result = dispatch(
        {
            **VALID_CALL,
            "request_id": "timeout-exhausted-001",
        },
        SUPPORT_USER,
        max_attempts=2,
    )

    assert result.status == ToolStatus.TIMEOUT
    assert calls["count"] == 2
    assert "private timeout details" not in str(
        result.model_dump(mode="json")
    )


def test_unexpected_exception_is_not_retried(monkeypatch):
    spec = get_tool("order.lookup")
    calls = {"count": 0}

    def unexpected_failure(_validated_input):
        calls["count"] += 1
        raise ValueError("private internal details")

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=unexpected_failure),
    )

    result = dispatch(
        {
            **VALID_CALL,
            "request_id": "unexpected-failure-001",
        },
        SUPPORT_USER,
        max_attempts=3,
    )

    assert result.status == ToolStatus.FAILED
    assert calls["count"] == 1
    assert "private internal details" not in str(
        result.model_dump(mode="json")
    )
