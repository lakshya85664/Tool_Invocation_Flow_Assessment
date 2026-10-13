
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.contracts import OrderLookupInput, OrderLookupOutput
from src.registry import TOOL_REGISTRY, get_tool, registry_summary


ROOT = Path(__file__).resolve().parents[1]


def test_valid_order_lookup_input():
    item = OrderLookupInput(order_id="ORD-1001")
    assert item.order_id == "ORD-1001"


@pytest.mark.parametrize(
    "order_id",
    [
        "",
        "ORD-123",
        "ORD-1234567890123",
        "BAD-1001",
        "ORD-ABCD",
    ],
)
def test_invalid_order_ids_are_rejected(order_id):
    with pytest.raises(ValidationError):
        OrderLookupInput(order_id=order_id)


def test_extra_input_fields_are_rejected():
    with pytest.raises(ValidationError):
        OrderLookupInput(
            order_id="ORD-1001",
            internal_note="not allowed",
        )


def test_missing_order_id_is_rejected():
    with pytest.raises(ValidationError):
        OrderLookupInput()


def test_output_contract_accepts_valid_result():
    output = OrderLookupOutput(
        order_id="ORD-1001",
        status="shipped",
        estimated_delivery="2026-10-15",
    )
    assert output.status == "shipped"


def test_output_contract_rejects_extra_fields():
    with pytest.raises(ValidationError):
        OrderLookupOutput(
            order_id="ORD-1001",
            status="shipped",
            secret="unexpected",
        )


def test_registry_contains_versioned_read_tool():
    spec = get_tool("order.lookup")

    assert spec is not None
    assert spec.version == "1.0.0"
    assert spec.access == "read"
    assert "customer_support" in spec.allowed_roles
    assert "admin" in spec.allowed_roles


def test_unknown_tool_is_not_registered():
    assert get_tool("admin.delete_everything") is None


def test_registry_summary_is_json_serializable():
    summary = registry_summary()
    assert summary[0]["name"] == "order.lookup"
    json.dumps(summary)


def test_input_schema_file_exists_and_matches_contract():
    path = ROOT / "schemas" / "order_lookup_input.json"
    schema = json.loads(path.read_text(encoding="utf-8"))

    assert schema["properties"]["order_id"]["pattern"] == (
        "^ORD-[0-9]{4,12}$"
    )
    assert schema["additionalProperties"] is False


def test_output_schema_file_exists():
    path = ROOT / "schemas" / "order_lookup_output.json"
    schema = json.loads(path.read_text(encoding="utf-8"))

    assert schema["title"] == "OrderLookupOutput"
    assert schema["additionalProperties"] is False