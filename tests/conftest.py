
import pytest

from src.dispatcher import reset_reliability_state


@pytest.fixture(autouse=True)
def isolate_dispatch_reliability_state():
    """Keep rate-limit and idempotency state isolated between tests."""
    reset_reliability_state()
    yield
    reset_reliability_state()
