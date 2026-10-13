
import json

import pytest

from src.observability import build_log_record, emit_log
from src.reliability import (
    IdempotencyStore,
    SlidingWindowRateLimiter,
    request_fingerprint,
    retry_on_timeout,
)


def test_rate_limiter_allows_requests_within_limit():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)

    assert limiter.check("user-1", now=100).allowed
    assert limiter.check("user-1", now=101).allowed

    decision = limiter.check("user-1", now=102)
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 8


def test_rate_limiter_expires_old_requests():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=10)

    assert limiter.check("user-1", now=100).allowed
    assert limiter.check("user-1", now=111).allowed


def test_rate_limits_are_separate_per_key():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=10)

    assert limiter.check("user-1", now=100).allowed
    assert limiter.check("user-2", now=100).allowed


def test_idempotency_store_returns_saved_result():
    store = IdempotencyStore()
    result = {"status": "ok", "order_id": "ORD-1001"}

    store.put("req-1", "fingerprint-1", result)
    found, cached = store.get("req-1", "fingerprint-1")

    assert found is True
    assert cached == result


def test_reusing_request_id_with_different_fingerprint_is_rejected():
    store = IdempotencyStore()
    store.put("req-1", "fingerprint-1", {"status": "ok"})

    with pytest.raises(ValueError, match="different request"):
        store.get("req-1", "fingerprint-2")


def test_request_fingerprint_is_stable_and_sensitive_to_call():
    principal = {"id": "support-001", "role": "customer_support"}
    call = {
        "name": "order.lookup",
        "arguments": {"order_id": "ORD-1001"},
        "request_id": "req-1",
    }

    first = request_fingerprint(call, principal)
    second = request_fingerprint(dict(call), dict(principal))
    changed = request_fingerprint(
        {**call, "arguments": {"order_id": "ORD-1002"}},
        principal,
    )

    assert first == second
    assert first != changed


def test_retry_succeeds_after_timeout():
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary timeout")
        return "success"

    assert retry_on_timeout(operation, max_attempts=3) == "success"
    assert attempts["count"] == 2


def test_retry_stops_after_max_attempts():
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        raise TimeoutError("temporary timeout")

    with pytest.raises(TimeoutError):
        retry_on_timeout(operation, max_attempts=3)

    assert attempts["count"] == 3


def test_retry_does_not_retry_other_errors():
    attempts = {"count": 0}

    def operation():
        attempts["count"] += 1
        raise ValueError("invalid input")

    with pytest.raises(ValueError, match="invalid input"):
        retry_on_timeout(operation, max_attempts=3)

    assert attempts["count"] == 1


def test_structured_log_is_json_serializable():
    record = build_log_record(
        request_id="req-1",
        tool_name="order.lookup",
        stage="execution",
        status="ok",
        duration_ms=12.345,
    )

    serialized = emit_log(record)
    decoded = json.loads(serialized)

    assert decoded["request_id"] == "req-1"
    assert decoded["tool_name"] == "order.lookup"
    assert decoded["stage"] == "execution"
    assert decoded["status"] == "ok"
    assert decoded["duration_ms"] == 12.35
