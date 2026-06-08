from __future__ import annotations

import argparse
import json
import os
import site
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
if os.path.isdir(DEPS):
    site.addsitedir(DEPS)
for path in (SRC, ROOT, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)
for path in (SRC, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv

from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.agents.live_mcp_demo import (
    LiveMCPAgent,
    LiveMCPAgentConfig,
    StdioMCPToolClient,
    build_live_provider_from_env,
)
from compliance_agent.contracts.phase1 import (
    AgentRunRequest,
    RuntimeBounds,
    SubjectRef,
    ToolExecutionScope,
)
from mcp_server.fixtures import load_phase1_fixtures

load_dotenv(os.path.join(ROOT, ".env"))


SCENARIOS = {
    "clean_false_positive": {
        "alert_id": 1003,
        "customer_id": 503,
        "account_id": 3003,
        "transaction_id": 7030,
    },
    "hard_red_flag": {
        "alert_id": 1001,
        "customer_id": 501,
        "account_id": 3001,
        "transaction_id": 7004,
    },
    "graph_ambiguous": {
        "alert_id": 1006,
        "customer_id": 506,
        "account_id": 3006,
        "transaction_id": 7060,
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the phase 1 live LLM + reference MCP demo.")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="clean_false_positive",
    )
    parser.add_argument("--tenant-id", default="demo-bank")
    parser.add_argument("--officer-id", default="officer-123")
    parser.add_argument(
        "--sidecar-db-path",
        default=os.getenv("SIDECAR_DB_PATH", os.path.join(ROOT, "data", "phase1_live_sidecar.sqlite3")),
    )
    parser.add_argument("--max-steps", default=6, type=int)
    parser.add_argument("--max-tool-calls", default=6, type=int)
    parser.add_argument(
        "--skip-fixtures",
        action="store_true",
        help="Do not load deterministic phase 1 fixtures before running.",
    )
    args = parser.parse_args()

    if not args.skip_fixtures:
        load_phase1_fixtures()

    scenario = SCENARIOS[args.scenario]
    request = AgentRunRequest(
        tenant_id=args.tenant_id,
        officer_id=args.officer_id,
        purpose="triage",
        scenario=args.scenario,
        subject=SubjectRef(
            alert_id=scenario["alert_id"],
            customer_id=scenario["customer_id"],
        ),
        scope=ToolExecutionScope(
            allowed_customer_ids=[scenario["customer_id"]],
            allowed_account_ids=[scenario["account_id"]],
            allowed_transaction_ids=[scenario["transaction_id"]],
            allowed_case_ids=[],
        ),
        runtime_bounds=RuntimeBounds(
            max_steps=args.max_steps,
            max_tool_calls=args.max_tool_calls,
            max_rows=100,
            max_graph_hops=4,
        ),
    )
    model_id = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.5"
    if not model_id:
        raise ValueError("LLM_MODEL is required for the live MCP demo.")

    agent = LiveMCPAgent(
        provider=build_live_provider_from_env(),
        tool_client=StdioMCPToolClient(),
        config=LiveMCPAgentConfig(
            model_id=model_id,
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        ),
    )
    response = agent.run_and_persist(request, SidecarStore(args.sidecar_db_path))
    proposal = response["proposal"]
    print(
        json.dumps(
            {
                "run_id": response["run_id"],
                "scenario": args.scenario,
                "recommendation": proposal["recommendation"],
                "confidence": proposal["confidence"],
                "validation_status": proposal["validation_status"]["status"],
                "selected_tools": [call["tool_name"] for call in proposal["tool_calls"]],
                "hypotheses": [
                    step.get("hypothesis_after")
                    for step in proposal["trace"]
                    if step.get("hypothesis_after")
                ],
                "required_human_action": proposal["required_human_action"],
                "sidecar_db_path": args.sidecar_db_path,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
