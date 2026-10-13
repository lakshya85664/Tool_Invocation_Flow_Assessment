
from __future__ import annotations

import json
from pathlib import Path

from src.dispatcher import dispatch


PROJECT_ROOT = Path(__file__).resolve().parent
TRACE_DIR = PROJECT_ROOT / "traces"
TRACE_DIR.mkdir(exist_ok=True)

CALL = {
    "name": "order.lookup",
    "arguments": {
        "order_id": "ORD-1001",
    },
    "request_id": "task2-demo-001",
}

PRINCIPAL = {
    "id": "support-agent-001",
    "role": "customer_support",
}


def main() -> None:
    print("=" * 60)
    print("TOPIC 3 — TASK 2: TOOL INVOCATION FLOW")
    print("=" * 60)

    result = dispatch(CALL, PRINCIPAL)
    result_data = result.model_dump(mode="json")

    print("\nFinal response:")
    print(json.dumps(result_data, indent=2))

    trace = {
        "scenario": "successful_order_lookup",
        "request_id": CALL["request_id"],
        "tool": CALL["name"],
        "principal_role": PRINCIPAL["role"],
        "result": result_data,
    }

    trace_path = TRACE_DIR / "task2_success.json"
    trace_path.write_text(
        json.dumps(trace, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved trace: {trace_path.relative_to(PROJECT_ROOT)}")
    print(f"Final status: {result.status.value}")
    print(f"Recorded stages: {len(result.events)}")


if __name__ == "__main__":
    main()
