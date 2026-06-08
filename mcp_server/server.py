from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEPS = ROOT / ".codex_deps"
for path in (ROOT, SRC, DEPS):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from compliance_agent.contracts.tool_catalog import PHASE1_TOOL_NAMES

from mcp_server.repository import PostgresReferenceRepository, ReferenceRepository
from mcp_server.service import ReferenceMCPTools


def create_reference_mcp_server(repository: ReferenceRepository | None = None):
    """Create the phase 1 reference MCP server.

    The MCP SDK is imported lazily so contract tests can run before project
    dependencies are installed.
    """

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install the 'mcp' package to run the reference MCP server.") from exc

    tools = ReferenceMCPTools(repository or PostgresReferenceRepository())
    mcp = FastMCP("AML_Phase1_Reference_MCP", json_response=True)

    @mcp.tool()
    def get_customer_profile(request: dict) -> dict:
        """Return scoped customer, account, and profile facts."""
        return tools.get_customer_profile(request)

    @mcp.tool()
    def get_transaction_history(request: dict) -> dict:
        """Return bounded transaction history for the scoped customer."""
        return tools.get_transaction_history(request)

    @mcp.tool()
    def get_behavioral_baseline(request: dict) -> dict:
        """Return customer-relative behavioral baseline facts."""
        return tools.get_behavioral_baseline(request)

    @mcp.tool()
    def get_prior_alerts(request: dict) -> dict:
        """Return prior alerts for the scoped customer."""
        return tools.get_prior_alerts(request)

    @mcp.tool()
    def get_case_history(request: dict) -> dict:
        """Return case history for the scoped customer."""
        return tools.get_case_history(request)

    @mcp.tool()
    def trace_counterparty_graph(request: dict) -> dict:
        """Trace bounded counterparty graph paths from the alert transaction."""
        return tools.trace_counterparty_graph(request)

    @mcp.tool()
    def screen_sanctions_pep(request: dict) -> dict:
        """Return sanctions and PEP screening facts for the scoped customer."""
        return tools.screen_sanctions_pep(request)

    @mcp.tool()
    def get_similar_alerts(request: dict) -> dict:
        """Return similar prior alerts for the scoped customer and alert rule."""
        return tools.get_similar_alerts(request)

    @mcp.tool()
    def get_compliance_rule(request: dict) -> dict:
        """Return the compliance rule that generated the scoped alert."""
        return tools.get_compliance_rule(request)

    mcp.phase1_tool_names = PHASE1_TOOL_NAMES  # type: ignore[attr-defined]
    return mcp


def main() -> None:
    load_dotenv()
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    server = create_reference_mcp_server()
    server.run(transport=transport)


if __name__ == "__main__":
    main()
