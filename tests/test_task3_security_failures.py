
from dataclasses import replace

import pytest

from src.contracts import NextAction, ToolStatus
from src.dispatcher import dispatch
from src.registry import get_tool


SUPPORT_USER = {
    "id": "support-001",
    "role": "customer_support",
}

GUEST_USER = {
    "id": "guest-001",
    "role": "guest",
}

VALID_CALL = {
    "name": "order.lookup",
    "arguments": {"order_id": "ORD-1001"},
    "request_id": "task3-request-001",
}


def test_guest_is_denied():
    result = dispatch(VALID_CALL, GUEST_USER)

    assert result.status == ToolStatus.DENIED
    assert result.next_action == NextAction.REQUEST_AUTHORIZATION
    assert not any(
        event["stage"] == "execution"
        for event in result.events
    )


def test_missing_principal_is_denied():
    result = dispatch(VALID_CALL, None)

    assert result.status == ToolStatus.DENIED


@pytest.mark.parametrize(
    "bad_call",
    [
        None,
        {},
        {"name": "order.lookup"},
        {
            "name": "order.lookup",
            "arguments": [],
            "request_id": "bad-001",
        },
        {
            "name": "order.lookup",
            "arguments": {"order_id": "ORD-1001"},
            "request_id": "",
        },
    ],
)
def test_malformed_calls_are_rejected(bad_call):
    result = dispatch(bad_call, SUPPORT_USER)

    assert result.status == ToolStatus.INVALID


def test_unregistered_tool_is_rejected():
    call = {
        **VALID_CALL,
        "name": "system.delete",
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.NOT_FOUND
    assert result.next_action == NextAction.CHOOSE_REGISTERED_TOOL


def test_invalid_order_identifier_is_rejected():
    call = {
        **VALID_CALL,
        "arguments": {"order_id": "INVALID"},
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.INVALID
    assert not any(
        event["stage"] == "execution"
        for event in result.events
    )


def test_unexpected_exception_is_not_exposed(monkeypatch):
    spec = get_tool("order.lookup")

    def failing_handler(_validated_input):
        raise RuntimeError("PRIVATE_PROVIDER_SECRET")

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=failing_handler),
    )

    result = dispatch(VALID_CALL, SUPPORT_USER)

    assert result.status == ToolStatus.FAILED
    assert "PRIVATE_PROVIDER_SECRET" not in str(
        result.model_dump(mode="json")
    )


def test_timeout_returns_controlled_status(monkeypatch):
    spec = get_tool("order.lookup")

    def timeout_handler(_validated_input):
        raise TimeoutError("PRIVATE_TIMEOUT_DETAILS")

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=timeout_handler),
    )

    result = dispatch(VALID_CALL, SUPPORT_USER)

    assert result.status == ToolStatus.TIMEOUT
    assert result.next_action == NextAction.RETRY_OR_REVIEW
    assert "PRIVATE_TIMEOUT_DETAILS" not in str(
        result.model_dump(mode="json")
    )


def test_handler_is_not_called_for_unauthorized_user(monkeypatch):
    spec = get_tool("order.lookup")
    called = {"value": False}

    def forbidden_handler(_validated_input):
        called["value"] = True
        raise AssertionError("Handler should not run")

    monkeypatch.setattr(
        "src.dispatcher.get_tool",
        lambda _name: replace(spec, handler=forbidden_handler),
    )

    result = dispatch(VALID_CALL, GUEST_USER)

    assert result.status == ToolStatus.DENIED
    assert called["value"] is False


def test_admin_can_access_registered_tool():
    admin = {
        "id": "admin-001",
        "role": "admin",
    }

    result = dispatch(VALID_CALL, admin)

    assert result.status == ToolStatus.OK
