from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    bank_source_dsn: str | None
    sidecar_db_path: str
    planner_type: str = "heuristic"
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_endpoint: str = "https://api.openai.com/v1/chat/completions"
    llm_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        demo = os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            demo_mode=demo,
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
        )
