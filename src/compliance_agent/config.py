from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    bank_source_dsn: str | None
    sidecar_db_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        demo = os.getenv("DEMO_MODE", "").strip().lower() in {"1", "true", "yes"}
        return cls(
            demo_mode=demo,
            bank_source_dsn=os.getenv("BANK_SOURCE_DSN"),
            sidecar_db_path=os.getenv("SIDECAR_DB_PATH", "data/sidecar.sqlite3"),
        )
