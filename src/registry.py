
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts import OrderLookupInput, OrderLookupOutput


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_model: type
    output_model: type
    access: str
    allowed_roles: tuple[str, ...]
    handler: Callable[[Any], Any]


from src.order_repository import lookup_order


def order_lookup_handler(validated_input):
    """Handle a validated order lookup request."""
    return lookup_order(validated_input)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "order.lookup": ToolSpec(
        name="order.lookup",
        version="1.0.0",
        description="Look up a sample order using its order ID.",
        input_model=OrderLookupInput,
        output_model=OrderLookupOutput,
        access="read",
        allowed_roles=("customer_support", "admin"),
        handler=order_lookup_handler,
    )
}


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)


def registry_summary() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "version": spec.version,
            "description": spec.description,
            "access": spec.access,
            "allowed_roles": list(spec.allowed_roles),
        }
        for spec in TOOL_REGISTRY.values()
    ]


if __name__ == "__main__":
    import json

    print(json.dumps(registry_summary(), indent=2))