
"""Small, thread-safe reliability utilities for tool invocation."""

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
import threading
import time
from typing import Any


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: float


class SlidingWindowRateLimiter:
    """Limit the number of requests per key within a rolling time window."""

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds

        with self._lock:
            timestamps = self._requests.setdefault(key, deque())

            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                retry_after = max(
                    0.0,
                    timestamps[0] + self.window_seconds - current,
                )
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=round(retry_after, 3),
                )

            timestamps.append(current)
            return RateLimitDecision(
                allowed=True,
                remaining=self.max_requests - len(timestamps),
                retry_after_seconds=0.0,
            )


def request_fingerprint(call: dict[str, Any], principal: dict[str, Any]) -> str:
    """Create a stable fingerprint for the call and its caller."""
    canonical = {
        "call": call,
        "principal": {
            "id": principal.get("id"),
            "role": principal.get("role"),
        },
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class IdempotencyStore:
    """Thread-safe in-memory store for completed request results."""

    def __init__(self) -> None:
        self._results: dict[str, tuple[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, request_id: str, fingerprint: str) -> tuple[bool, Any]:
        with self._lock:
            entry = self._results.get(request_id)

            if entry is None:
                return False, None

            stored_fingerprint, result = entry
            if stored_fingerprint != fingerprint:
                raise ValueError(
                    "Request ID was already used with a different request"
                )

            return True, result

    def put(
        self,
        request_id: str,
        fingerprint: str,
        result: Any,
    ) -> None:
        with self._lock:
            existing = self._results.get(request_id)

            if existing is not None and existing[0] != fingerprint:
                raise ValueError(
                    "Request ID was already used with a different request"
                )

            self._results[request_id] = (fingerprint, result)

    def clear(self) -> None:
        """Clear stored results, primarily for tests and local demonstrations."""
        with self._lock:
            self._results.clear()


def retry_on_timeout(
    operation,
    *,
    max_attempts: int = 3,
    sleep_seconds: float = 0.0,
):
    """Retry an operation only when it raises TimeoutError."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if sleep_seconds < 0:
        raise ValueError("sleep_seconds cannot be negative")

    for attempt in range(max_attempts):
        try:
            return operation()
        except TimeoutError:
            if attempt == max_attempts - 1:
                raise
            if sleep_seconds:
                time.sleep(sleep_seconds)

    raise RuntimeError("Unreachable retry state")
