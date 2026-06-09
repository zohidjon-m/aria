from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from .contracts.phase1 import RuntimeBounds


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    bank_source_dsn: str | None
    sidecar_db_path: str
    tenant_id: str = "demo-bank"
    planner_type: str = "heuristic"
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_endpoint: str = "https://api.openai.com/v1/chat/completions"
    llm_timeout_seconds: float = 30.0
    llm_prompt_version: str = "phase1_live_mcp_agent_v1"
    mcp_tool_registry_version: str = "phase1_reference_mcp_v1"
    agent_policy_version: str = "phase1_reference_mcp_policy_v1"
    runtime_max_steps: int = 6
    runtime_max_tool_calls: int = 6
    runtime_max_rows: int = 100
    runtime_max_graph_hops: int = 4
    runtime_timeout_seconds: float = 60.0
    runtime_max_cost_usd: float = 1.0

    def default_runtime_bounds(self) -> RuntimeBounds:
        return RuntimeBounds(
            max_steps=self.runtime_max_steps,
            max_tool_calls=self.runtime_max_tool_calls,
            max_rows=self.runtime_max_rows,
            max_graph_hops=self.runtime_max_graph_hops,
            timeout_seconds=self.runtime_timeout_seconds,
            max_cost_usd=self.runtime_max_cost_usd,
        )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        demo = os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            demo_mode=demo,
            tenant_id=os.getenv("TENANT_ID", "demo-bank"),
            bank_source_dsn=os.getenv("BANK_SOURCE_DSN"),
            sidecar_db_path=os.getenv("SIDECAR_DB_PATH", "data/sidecar.sqlite3"),
            planner_type=os.getenv("PLANNER_TYPE", "heuristic").strip().lower(),
            llm_model=os.getenv("LLM_MODEL") or None,
            llm_api_key=os.getenv("LLM_API_KEY") or None,
            llm_endpoint=os.getenv(
                "LLM_ENDPOINT",
                "https://api.openai.com/v1/chat/completions",
            ),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            llm_prompt_version=os.getenv("LLM_PROMPT_VERSION", "phase1_live_mcp_agent_v1"),
            mcp_tool_registry_version=os.getenv("MCP_TOOL_REGISTRY_VERSION", "phase1_reference_mcp_v1"),
            agent_policy_version=os.getenv("AGENT_POLICY_VERSION", "phase1_reference_mcp_policy_v1"),
            runtime_max_steps=int(os.getenv("RUNTIME_MAX_STEPS", "6")),
            runtime_max_tool_calls=int(os.getenv("RUNTIME_MAX_TOOL_CALLS", "6")),
            runtime_max_rows=int(os.getenv("RUNTIME_MAX_ROWS", "100")),
            runtime_max_graph_hops=int(os.getenv("RUNTIME_MAX_GRAPH_HOPS", "4")),
            runtime_timeout_seconds=float(os.getenv("RUNTIME_TIMEOUT_SECONDS", "60")),
            runtime_max_cost_usd=float(os.getenv("RUNTIME_MAX_COST_USD", "1")),
        )
