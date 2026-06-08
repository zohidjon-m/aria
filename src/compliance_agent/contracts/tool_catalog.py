from __future__ import annotations

from typing import Any

from .phase1 import MCPResponseEnvelope, ToolCatalogItem


TOOL_REGISTRY_VERSION = "phase1_reference_mcp_v1"

_REQUEST_ARG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request": {
            "type": "object",
            "description": "MCPRequestEnvelope. Runtime-supplied scope, audit, and bounded tool arguments.",
        }
    },
    "required": ["request"],
    "additionalProperties": False,
}


def _tool(name: str, description: str) -> ToolCatalogItem:
    return ToolCatalogItem(
        name=name,
        description=description,
        purpose="triage",
        read_only=True,
        args_schema=_REQUEST_ARG_SCHEMA,
        response_schema=MCPResponseEnvelope.model_json_schema(),
    )


PHASE1_TOOL_CATALOG: list[ToolCatalogItem] = [
    _tool("get_customer_profile", "Return scoped customer, account, and latest profile facts."),
    _tool("get_transaction_history", "Return bounded transaction history for the scoped customer."),
    _tool("get_behavioral_baseline", "Return customer-relative behavioral baseline features."),
    _tool("get_prior_alerts", "Return prior alerts for the scoped customer."),
    _tool("get_case_history", "Return case history and linked alert context for the scoped customer."),
    _tool("trace_counterparty_graph", "Trace bounded counterparty graph paths from the alert transaction."),
    _tool("screen_sanctions_pep", "Return sanctions and PEP screening facts for the scoped customer."),
    _tool("get_similar_alerts", "Return similar prior alerts for the scoped customer and alert rule."),
    _tool("get_compliance_rule", "Return the compliance rule that generated the scoped alert."),
]

PHASE1_TOOL_NAMES = tuple(item.name for item in PHASE1_TOOL_CATALOG)
