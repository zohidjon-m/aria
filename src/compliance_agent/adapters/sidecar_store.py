from __future__ import annotations

from contextlib import contextmanager
import json
import os
import sqlite3
from collections.abc import Iterator
from typing import Any

from ..domain import AgentResult, ValidationReport
from ..utils import json_dumps, stable_hash, utc_now


SIDECAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id),
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS validation_reports (
    validation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    unsupported_count INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    alert_id INTEGER NOT NULL,
    customer_id INTEGER,
    disposition TEXT NOT NULL,
    confidence REAL NOT NULL,
    score REAL NOT NULL,
    reasoning_json TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    risk_score_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    score REAL NOT NULL,
    level TEXT NOT NULL,
    rationale_json TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS sar_drafts (
    sar_draft_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_id INTEGER NOT NULL,
    narrative TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft_for_human_review',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS human_decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    officer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);
"""


class SidecarStore:
    """Separate persistence for all generated agent artifacts."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(SIDECAR_SCHEMA)

    def save_result(
        self,
        run_id: str,
        input_payload: dict[str, Any],
        result: AgentResult,
        validation: ValidationReport,
    ) -> None:
        status = "completed" if validation.status == "passed" else "validation_failed"
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs (
                    run_id, agent_name, subject_type, subject_id, status,
                    input_hash, output_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.agent_name,
                    result.subject_type,
                    str(result.subject_id),
                    status,
                    stable_hash(input_payload),
                    json_dumps(result),
                    utc_now(),
                ),
            )
            for evidence in result.evidence:
                conn.execute(
                    """
                    INSERT INTO evidence_items (
                        evidence_id, run_id, source_table, source_key,
                        payload_json, retrieved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence.evidence_id,
                        run_id,
                        evidence.source_ref.table,
                        evidence.source_ref.key,
                        json_dumps(evidence.payload),
                        evidence.retrieved_at,
                    ),
                )
            conn.execute(
                """
                INSERT INTO validation_reports (
                    validation_id, run_id, status, unsupported_count,
                    report_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    validation.validation_id,
                    run_id,
                    validation.status,
                    validation.unsupported_count,
                    json_dumps(validation),
                    validation.checked_at,
                ),
            )
            if result.agent_name == "triage_agent":
                self._save_recommendation(conn, run_id, result, validation)
            elif result.agent_name == "risk_scoring_agent":
                self._save_risk_score(conn, run_id, result, validation)
            elif result.agent_name == "sar_drafting_agent":
                self._save_sar_draft(conn, run_id, result, validation)

    def _save_recommendation(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        result: AgentResult,
        validation: ValidationReport,
    ) -> None:
        conn.execute(
            """
            INSERT INTO recommendations (
                recommendation_id, run_id, alert_id, customer_id, disposition,
                confidence, score, reasoning_json, validation_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.details["recommendation_id"],
                run_id,
                int(result.subject_id),
                result.details.get("customer_id"),
                result.recommendation,
                result.confidence,
                result.score,
                json_dumps(result.reasoning),
                validation.status,
                utc_now(),
            ),
        )

    def _save_risk_score(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        result: AgentResult,
        validation: ValidationReport,
    ) -> None:
        conn.execute(
            """
            INSERT INTO risk_scores (
                risk_score_id, run_id, customer_id, score, level,
                rationale_json, validation_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.details["risk_score_id"],
                run_id,
                int(result.subject_id),
                result.score,
                result.details["level"],
                json_dumps(result.reasoning),
                validation.status,
                utc_now(),
            ),
        )

    def _save_sar_draft(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        result: AgentResult,
        validation: ValidationReport,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sar_drafts (
                sar_draft_id, run_id, case_id, narrative,
                validation_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.details["sar_draft_id"],
                run_id,
                int(result.subject_id),
                result.details["narrative"],
                validation.status,
                utc_now(),
            ),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not row:
                return None
            validation = conn.execute(
                "SELECT * FROM validation_reports WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            evidence_rows = conn.execute(
                "SELECT * FROM evidence_items WHERE run_id = ? ORDER BY evidence_id",
                (run_id,),
            ).fetchall()

        return {
            "run": dict(row),
            "output": json.loads(row["output_json"]),
            "validation": dict(validation) if validation else None,
            "evidence": [dict(item) for item in evidence_rows],
        }
