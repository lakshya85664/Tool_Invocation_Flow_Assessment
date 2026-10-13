
from __future__ import annotations

from src.contracts import OrderLookupInput, OrderLookupOutput


ORDERS: dict[str, dict[str, str | None]] = {
    "ORD-1001": {
        "status": "shipped",
        "estimated_delivery": "2026-10-15",
    },
    "ORD-1002": {
        "status": "processing",
        "estimated_delivery": "2026-10-18",
    },
    "ORD-1003": {
        "status": "delivered",
        "estimated_delivery": "2026-10-10",
    },
}


def lookup_order(
    validated_input: OrderLookupInput,
) -> OrderLookupOutput:
    """Look up an order from the local sample repository."""
    order_id = validated_input.order_id
    record = ORDERS.get(order_id)

    if record is None:
        raise LookupError("Order was not found.")

    return OrderLookupOutput(
        order_id=order_id,
        status=record["status"],
        estimated_delivery=record["estimated_delivery"],
    )