from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compliance_agent.contracts.phase1 import (  # noqa: E402
    AgentProposal,
    AgentRunRequest,
    MCPRequestEnvelope,
    MCPResponseEnvelope,
)
from compliance_agent.contracts.tool_catalog import (  # noqa: E402
    PHASE1_TOOL_CATALOG,
    TOOL_REGISTRY_VERSION,
)


SCHEMAS = {
    "agent_proposal.schema.json": AgentProposal.model_json_schema(),
    "agent_run_request.schema.json": AgentRunRequest.model_json_schema(),
    "mcp_request_envelope.schema.json": MCPRequestEnvelope.model_json_schema(),
    "mcp_response_envelope.schema.json": MCPResponseEnvelope.model_json_schema(),
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
        "tool_registry_version": TOOL_REGISTRY_VERSION,
        "tools": [item.model_dump(mode="json") for item in PHASE1_TOOL_CATALOG],
    }
    (out_dir / "phase1_tool_catalog.json").write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + os.linesep,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
