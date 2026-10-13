
from src.contracts import NextAction, ToolStatus
from src.dispatcher import dispatch


SUPPORT_USER = {
    "id": "support-001",
    "role": "customer_support",
}

VALID_CALL = {
    "name": "order.lookup",
    "arguments": {"order_id": "ORD-1001"},
    "request_id": "task2-request-001",
}


def test_valid_call_returns_order_data():
    result = dispatch(VALID_CALL, SUPPORT_USER)

    assert result.status == ToolStatus.OK
    assert result.data["order_id"] == "ORD-1001"
    assert result.data["status"] == "shipped"


def test_result_contains_invocation_stages():
    result = dispatch(VALID_CALL, SUPPORT_USER)

    stages = [event["stage"] for event in result.events]

    assert stages == [
        "request",
        "selection",
        "authorization",
        "validation",
        "execution",
    ]


def test_unknown_tool_returns_not_found():
    call = {
        **VALID_CALL,
        "name": "order.unknown",
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.NOT_FOUND
    assert result.next_action == NextAction.CHOOSE_REGISTERED_TOOL


def test_invalid_arguments_do_not_execute_tool():
    call = {
        **VALID_CALL,
        "arguments": {"order_id": "NOT-VALID"},
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.INVALID
    assert result.next_action == NextAction.CORRECT_ARGUMENTS
    assert result.events[-1]["stage"] == "validation"


def test_missing_request_id_is_rejected():
    call = {
        "name": "order.lookup",
        "arguments": {"order_id": "ORD-1001"},
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.INVALID


def test_missing_or_unauthorized_principal_is_denied():
    guest = {
        "id": "guest-001",
        "role": "guest",
    }

    result = dispatch(VALID_CALL, guest)

    assert result.status == ToolStatus.DENIED
    assert result.next_action == NextAction.REQUEST_AUTHORIZATION


def test_unknown_order_returns_not_found():
    call = {
        **VALID_CALL,
        "arguments": {"order_id": "ORD-9999"},
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.NOT_FOUND


def test_invalid_call_does_not_reach_handler():
    call = {
        "name": "order.lookup",
        "arguments": {"order_id": "ORD-1001"},
        "request_id": "",
    }

    result = dispatch(call, SUPPORT_USER)

    assert result.status == ToolStatus.INVALID
    assert all(
        event["stage"] != "execution"
        for event in result.events
    )