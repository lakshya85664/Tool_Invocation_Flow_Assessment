
"""Generate Task 5 scenario traces and an operator report."""

import json
from dataclasses import replace
from pathlib import Path

from src import dispatcher
from src.contracts import ToolStatus
from src.dispatcher import dispatch, reset_reliability_state
from src.registry import get_tool


ROOT = Path(__file__).resolve().parent
TRACES_DIR = ROOT / "traces"
EVIDENCE_DIR = ROOT / "evidence"

SUPPORT_USER = {
    "id": "support-task5",
    "role": "customer_support",
}

GUEST_USER = {
    "id": "guest-task5",
    "role": "guest",
}

BASE_CALL = {
    "name": "order.lookup",
    "arguments": {"order_id": "ORD-1001"},
}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_scenario(name, call, principal, *, max_attempts=1):
    """Run one isolated scenario and persist its observable result."""
    reset_reliability_state()
    result = dispatch(
        call,
        principal,
        max_attempts=max_attempts,
    )

    payload = {
        "scenario": name,
        "request": call,
        "principal": {
            "id": principal.get("id") if isinstance(principal, dict) else None,
            "role": principal.get("role") if isinstance(principal, dict) else None,
        },
        "result": result.model_dump(mode="json"),
    }

    write_json(TRACES_DIR / f"task5_{name}.json", payload)
    return result


def main():
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    original_get_tool = dispatcher.get_tool
    outcomes = {}

    try:
        # Scenario 1: Successful order lookup.
        success_call = {
            **BASE_CALL,
            "request_id": "task5-success-001",
        }
        success = run_scenario(
            "success",
            success_call,
            SUPPORT_USER,
        )
        outcomes["success"] = success.status.value

        # Scenario 2: Authorization denied.
        denied_call = {
            **BASE_CALL,
            "request_id": "task5-denied-001",
        }
        denied = run_scenario(
            "denied",
            denied_call,
            GUEST_USER,
        )
        outcomes["denied"] = denied.status.value

        # Scenario 3: A provider/handler failure is safely contained.
        failure_spec = get_tool("order.lookup")

        def failing_handler(_validated_input):
            raise RuntimeError("PRIVATE_PROVIDER_FAILURE")

        dispatcher.get_tool = lambda _name: replace(
            failure_spec,
            handler=failing_handler,
        )

        failure_call = {
            **BASE_CALL,
            "request_id": "task5-provider-failure-001",
        }
        failure = run_scenario(
            "provider_failure",
            failure_call,
            SUPPORT_USER,
        )
        outcomes["provider_failure"] = failure.status.value

        # Scenario 4: A temporary timeout recovers on the second attempt.
        recovery_spec = failure_spec
        attempts = {"count": 0}
        original_handler = recovery_spec.handler

        def timeout_once(validated_input):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("temporary timeout")
            return original_handler(validated_input)

        dispatcher.get_tool = lambda _name: replace(
            recovery_spec,
            handler=timeout_once,
        )

        recovery_call = {
            **BASE_CALL,
            "request_id": "task5-recovery-001",
        }
        recovery = run_scenario(
            "timeout_recovery",
            recovery_call,
            SUPPORT_USER,
            max_attempts=2,
        )
        outcomes["timeout_recovery"] = recovery.status.value

    finally:
        dispatcher.get_tool = original_get_tool
        reset_reliability_state()

    expected = {
        "success": ToolStatus.OK.value,
        "denied": ToolStatus.DENIED.value,
        "provider_failure": ToolStatus.FAILED.value,
        "timeout_recovery": ToolStatus.OK.value,
    }

    report = {
        "report_title": "Tool Invocation Flow — Operator Report",
        "scenario_count": len(outcomes),
        "expected_statuses": expected,
        "actual_statuses": outcomes,
        "scenarios_match_expected": outcomes == expected,
        "timeout_recovery_attempts": attempts["count"],
        "observations": [
            "Successful requests return validated tool output.",
            "Unauthorized requests are denied before handler execution.",
            "Unexpected handler exceptions are mapped to a controlled failure.",
            "A timeout can recover when bounded retries are explicitly enabled.",
        ],
        "limitations": [
            "Rate limiting and idempotency are in-memory and process-local.",
            "Concurrent requests with the same request ID are not atomically reserved.",
            "The sample repository is local demonstration data, not a live order service.",
        ],
    }

    write_json(EVIDENCE_DIR / "operator_report.json", report)

    print("Task 5 evidence generation complete")
    print("=" * 48)

    for scenario, status in outcomes.items():
        print(f"{scenario:20} {status}")

    print(f"\nScenario results match expected: {outcomes == expected}")
    print(f"Timeout recovery attempts: {attempts['count']}")
    print(f"Operator report: {EVIDENCE_DIR / 'operator_report.json'}")
    print(f"Scenario traces: {TRACES_DIR}")


if __name__ == "__main__":
    main()
