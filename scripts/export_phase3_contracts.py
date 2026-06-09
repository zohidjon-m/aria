from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compliance_agent.contracts.phase3 import (  # noqa: E402
    Phase3AuditEvent,
    Phase3MCPRequestEnvelope,
    Phase3MCPResponseEnvelope,
    Phase3PolicyDecision,
    Phase3ScopeExpansionPolicy,
    Phase3ToolMetadata,
)
from compliance_agent.contracts.tool_catalog_phase3 import (  # noqa: E402
    PHASE3_TOOL_CATALOG,
    PHASE3_TOOL_REGISTRY_VERSION,
)


SCHEMAS = {
    "phase3_mcp_request_envelope.schema.json": Phase3MCPRequestEnvelope.model_json_schema(),
    "phase3_mcp_response_envelope.schema.json": Phase3MCPResponseEnvelope.model_json_schema(),
    "phase3_audit_event.schema.json": Phase3AuditEvent.model_json_schema(),
    "phase3_policy_decision.schema.json": Phase3PolicyDecision.model_json_schema(),
    "phase3_scope_expansion_policy.schema.json": Phase3ScopeExpansionPolicy.model_json_schema(),
    "phase3_tool_metadata.schema.json": Phase3ToolMetadata.model_json_schema(),
}


def main() -> None:
    out_dir = ROOT / "contracts"
    out_dir.mkdir(exist_ok=True)
    for name, schema in SCHEMAS.items():
        (out_dir / name).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + os.linesep,
            encoding="utf-8",
        )
    catalog = {
        "tool_registry_version": PHASE3_TOOL_REGISTRY_VERSION,
        "tools": [item.model_dump(mode="json") for item in PHASE3_TOOL_CATALOG],
    }
    (out_dir / "phase3_tool_catalog.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + os.linesep,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
