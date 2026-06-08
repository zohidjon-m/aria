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

CREATE TABLE IF NOT EXISTS runtime_versions (
    run_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    planner_type TEXT NOT NULL,
    model_id TEXT,
    prompt_version TEXT NOT NULL,
    tool_registry_version TEXT NOT NULL,
    runtime_bounds_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS typology_routes (
    route_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    activated_json TEXT NOT NULL,
    skipped_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    allowed_tools_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    thought TEXT,
    hypothesis TEXT,
    tool_name TEXT,
    stop_reason TEXT,
    error TEXT,
    step_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stop_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    tool_name TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    computed_features_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    data_completeness_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    hypothesis TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS baseline_snapshots (
    baseline_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    baseline_assessment TEXT,
    features_json TEXT NOT NULL,
    data_completeness_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS money_flow_paths (
    money_flow_path_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    path_index INTEGER NOT NULL,
    hop_count INTEGER,
    account_path_json TEXT NOT NULL,
    path_json TEXT NOT NULL,
    graph_signals_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runtime_versions_idempotency_key
    ON runtime_versions(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_runtime_versions_subject
    ON runtime_versions(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_typology_routes_run_id
    ON typology_routes(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run_step
    ON agent_steps(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run_phase_tool
    ON tool_calls(run_id, phase, tool_name);
CREATE INDEX IF NOT EXISTS idx_observations_run_phase_tool
    ON observations(run_id, phase, tool_name);
CREATE INDEX IF NOT EXISTS idx_hypotheses_run_step
    ON hypotheses(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_baseline_snapshots_run_phase
    ON baseline_snapshots(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_money_flow_paths_run_phase
    ON money_flow_paths(run_id, phase);
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
        input_hash = stable_hash(input_payload)
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
                    input_hash,
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
                self._save_triage_trace(conn, run_id, input_hash, result)
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

    def _save_triage_trace(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        input_hash: str,
        result: AgentResult,
    ) -> None:
        runtime_version = self._runtime_version_details(result)
        planner_type = str(runtime_version.get("planner_type") or "unknown")
        prompt_version = str(runtime_version.get("prompt_version") or "")
        tool_registry_version = str(
            runtime_version.get("tool_registry_version") or "unknown"
        )
        runtime_bounds = runtime_version.get("runtime_bounds") or {}
        idempotency_key = stable_hash(
            {
                "subject_id": str(result.subject_id),
                "input_hash": input_hash,
                "planner_type": planner_type,
                "prompt_version": prompt_version,
                "tool_registry_version": tool_registry_version,
            }
        )
        conn.execute(
            """
            INSERT INTO runtime_versions (
                run_id, subject_type, subject_id, planner_type, model_id,
                prompt_version, tool_registry_version, runtime_bounds_json,
                input_hash, idempotency_key, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result.subject_type,
                str(result.subject_id),
                planner_type,
                runtime_version.get("model_id"),
                prompt_version,
                tool_registry_version,
                json_dumps(runtime_bounds),
                input_hash,
                idempotency_key,
                json_dumps(
                    {
                        "triage_path": result.details.get("triage_path"),
                        "runtime_version": runtime_version,
                    }
                ),
                utc_now(),
            ),
        )

        pre_screen = result.details.get("pre_screen_gate")
        if isinstance(pre_screen, dict):
            self._save_pre_screen_trace(conn, run_id, pre_screen)

        react_runtime = result.details.get("react_runtime")
        if isinstance(react_runtime, dict):
            route = result.details.get("typology_route")
            if isinstance(route, dict):
                self._save_typology_route(conn, run_id, route)
            self._save_react_trace(conn, run_id, react_runtime)

    def _runtime_version_details(self, result: AgentResult) -> dict[str, Any]:
        runtime_version = result.details.get("runtime_version")
        if isinstance(runtime_version, dict):
            return dict(runtime_version)

        react_runtime = result.details.get("react_runtime")
        if isinstance(react_runtime, dict):
            planner_metadata = react_runtime.get("planner_metadata") or {}
            return {
                "planner_type": react_runtime.get("planner") or "unknown",
                "model_id": planner_metadata.get("model_id"),
                "prompt_version": planner_metadata.get("prompt_version") or "",
                "tool_registry_version": "unknown",
                "runtime_bounds": {
                    "max_steps": react_runtime.get("max_steps"),
                    "max_tool_calls": react_runtime.get("max_tool_calls"),
                },
            }
        if result.details.get("pre_screen_gate"):
            return {
                "planner_type": "pre_screen_gate",
                "model_id": None,
                "prompt_version": "",
                "tool_registry_version": "unknown",
                "runtime_bounds": {},
            }
        return {
            "planner_type": result.agent_name,
            "model_id": None,
            "prompt_version": "",
            "tool_registry_version": "unknown",
            "runtime_bounds": {},
        }

    def _save_pre_screen_trace(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        pre_screen: dict[str, Any],
    ) -> None:
        observations = pre_screen.get("tool_observations") or {}
        if not isinstance(observations, dict):
            return
        for index, (tool_name, observation) in enumerate(observations.items(), start=1):
            if not isinstance(observation, dict):
                continue
            self._save_tool_call(
                conn,
                run_id,
                phase="pre_screen",
                step_number=None,
                tool_name=tool_name,
                tool_args={},
                status="observed",
                stop_reason=None,
                row_suffix=str(index),
            )
            self._save_observation(
                conn,
                run_id,
                phase="pre_screen",
                step_number=None,
                tool_name=tool_name,
                observation=observation,
                row_suffix=str(index),
            )

    def _save_typology_route(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        route: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO typology_routes (
                route_id, run_id, activated_json, skipped_json, reasons_json,
                allowed_tools_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:typology_route",
                run_id,
                json_dumps(route.get("activated") or []),
                json_dumps(route.get("skipped") or []),
                json_dumps(route.get("reasons") or {}),
                json_dumps(route.get("allowed_tools") or []),
                utc_now(),
            ),
        )

    def _save_react_trace(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        react_runtime: dict[str, Any],
    ) -> None:
        tool_observations = react_runtime.get("tool_observations") or {}
        if not isinstance(tool_observations, dict):
            tool_observations = {}
        steps = react_runtime.get("steps") or []
        if not isinstance(steps, list):
            return
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            step_number = int(step.get("step_number") or index)
            self._save_agent_step(conn, run_id, step_number, step)
            hypothesis = step.get("hypothesis")
            if hypothesis:
                self._save_hypothesis(conn, run_id, step_number, str(hypothesis))

            tool_name = step.get("tool_name")
            if not tool_name:
                continue
            tool_name = str(tool_name)
            observation = tool_observations.get(tool_name)
            if not isinstance(observation, dict):
                observation = step.get("observation") or {}
            if not isinstance(observation, dict):
                observation = {}
            self._save_tool_call(
                conn,
                run_id,
                phase="react_runtime",
                step_number=step_number,
                tool_name=tool_name,
                tool_args=step.get("tool_args") or {},
                status=str(step.get("status") or "observed"),
                stop_reason=step.get("stop_reason"),
                row_suffix=str(step_number),
            )
            self._save_observation(
                conn,
                run_id,
                phase="react_runtime",
                step_number=step_number,
                tool_name=tool_name,
                observation=observation,
                row_suffix=str(step_number),
            )

    def _save_agent_step(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        step_number: int,
        step: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO agent_steps (
                step_id, run_id, step_number, status, thought, hypothesis,
                tool_name, stop_reason, error, step_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:step:{step_number}",
                run_id,
                step_number,
                str(step.get("status") or "unknown"),
                step.get("thought"),
                step.get("hypothesis"),
                step.get("tool_name"),
                step.get("stop_reason"),
                step.get("error"),
                json_dumps(step),
                utc_now(),
            ),
        )

    def _save_hypothesis(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        step_number: int,
        hypothesis: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO hypotheses (
                hypothesis_id, run_id, step_number, hypothesis, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:hypothesis:{step_number}",
                run_id,
                step_number,
                hypothesis,
                utc_now(),
            ),
        )

    def _save_tool_call(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        phase: str,
        step_number: int | None,
        tool_name: str,
        tool_args: dict[str, Any],
        status: str,
        stop_reason: Any,
        row_suffix: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO tool_calls (
                tool_call_id, run_id, phase, step_number, tool_name,
                tool_args_json, status, stop_reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:{phase}:tool_call:{row_suffix}:{tool_name}",
                run_id,
                phase,
                step_number,
                tool_name,
                json_dumps(tool_args),
                status,
                str(stop_reason) if stop_reason is not None else None,
                utc_now(),
            ),
        )

    def _save_observation(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        phase: str,
        step_number: int | None,
        tool_name: str,
        observation: dict[str, Any],
        row_suffix: str,
    ) -> None:
        facts = observation.get("facts") or {}
        computed_features = observation.get("computed_features") or {}
        source_refs = observation.get("source_refs") or []
        data_completeness = observation.get("data_completeness") or {}
        limitations = observation.get("limitations") or []
        conn.execute(
            """
            INSERT INTO observations (
                observation_id, run_id, phase, step_number, tool_name,
                facts_json, computed_features_json, source_refs_json,
                data_completeness_json, limitations_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:{phase}:observation:{row_suffix}:{tool_name}",
                run_id,
                phase,
                step_number,
                tool_name,
                json_dumps(facts),
                json_dumps(computed_features),
                json_dumps(source_refs),
                json_dumps(data_completeness),
                json_dumps(limitations),
                utc_now(),
            ),
        )
        if tool_name == "compute_behavioral_baseline":
            self._save_baseline_snapshot(
                conn,
                run_id,
                phase=phase,
                step_number=step_number,
                row_suffix=row_suffix,
                features=computed_features,
                data_completeness=data_completeness,
                limitations=limitations,
            )
        if tool_name == "trace_money_flow":
            self._save_money_flow_paths(
                conn,
                run_id,
                phase=phase,
                step_number=step_number,
                row_suffix=row_suffix,
                facts=facts,
                computed_features=computed_features,
            )

    def _save_baseline_snapshot(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        phase: str,
        step_number: int | None,
        row_suffix: str,
        features: dict[str, Any],
        data_completeness: dict[str, Any],
        limitations: list[dict[str, Any]],
    ) -> None:
        conn.execute(
            """
            INSERT INTO baseline_snapshots (
                baseline_snapshot_id, run_id, phase, step_number,
                baseline_assessment, features_json, data_completeness_json,
                limitations_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:{phase}:baseline:{row_suffix}",
                run_id,
                phase,
                step_number,
                features.get("baseline_assessment"),
                json_dumps(features),
                json_dumps(data_completeness),
                json_dumps(limitations),
                utc_now(),
            ),
        )

    def _save_money_flow_paths(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        phase: str,
        step_number: int | None,
        row_suffix: str,
        facts: dict[str, Any],
        computed_features: dict[str, Any],
    ) -> None:
        paths = facts.get("paths") or []
        if not isinstance(paths, list):
            return
        signals = computed_features.get("signals") or {}
        for index, path in enumerate(paths, start=1):
            if not isinstance(path, dict):
                continue
            conn.execute(
                """
                INSERT INTO money_flow_paths (
                    money_flow_path_id, run_id, phase, step_number, path_index,
                    hop_count, account_path_json, path_json, graph_signals_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{run_id}:{phase}:money_flow:{row_suffix}:{index}",
                    run_id,
                    phase,
                    step_number,
                    index,
                    path.get("hop_count"),
                    json_dumps(path.get("account_path") or []),
                    json_dumps(path),
                    json_dumps(signals),
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

    def get_trace(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            run = conn.execute(
                "SELECT run_id FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if not run:
                return None
            runtime_version = conn.execute(
                "SELECT * FROM runtime_versions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            typology_routes = conn.execute(
                "SELECT * FROM typology_routes WHERE run_id = ? ORDER BY route_id",
                (run_id,),
            ).fetchall()
            agent_steps = conn.execute(
                "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY step_number",
                (run_id,),
            ).fetchall()
            tool_calls = conn.execute(
                """
                SELECT * FROM tool_calls
                WHERE run_id = ?
                ORDER BY phase, COALESCE(step_number, 0), tool_name
                """,
                (run_id,),
            ).fetchall()
            observations = conn.execute(
                """
                SELECT * FROM observations
                WHERE run_id = ?
                ORDER BY phase, COALESCE(step_number, 0), tool_name
                """,
                (run_id,),
            ).fetchall()
            hypotheses = conn.execute(
                "SELECT * FROM hypotheses WHERE run_id = ? ORDER BY step_number",
                (run_id,),
            ).fetchall()
            baseline_snapshots = conn.execute(
                """
                SELECT * FROM baseline_snapshots
                WHERE run_id = ?
                ORDER BY phase, COALESCE(step_number, 0)
                """,
                (run_id,),
            ).fetchall()
            money_flow_paths = conn.execute(
                """
                SELECT * FROM money_flow_paths
                WHERE run_id = ?
                ORDER BY phase, COALESCE(step_number, 0), path_index
                """,
                (run_id,),
            ).fetchall()

        return {
            "run_id": run_id,
            "runtime_version": (
                self._runtime_version_row(runtime_version)
                if runtime_version
                else None
            ),
            "typology_routes": [
                self._typology_route_row(row) for row in typology_routes
            ],
            "agent_steps": [
                self._agent_step_row(row) for row in agent_steps
            ],
            "tool_calls": [
                self._tool_call_row(row) for row in tool_calls
            ],
            "observations": [
                self._observation_row(row) for row in observations
            ],
            "hypotheses": [dict(row) for row in hypotheses],
            "baseline_snapshots": [
                self._baseline_snapshot_row(row) for row in baseline_snapshots
            ],
            "money_flow_paths": [
                self._money_flow_path_row(row) for row in money_flow_paths
            ],
        }

    def find_runs_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    agent_runs.run_id,
                    agent_runs.agent_name,
                    agent_runs.subject_type,
                    agent_runs.subject_id,
                    agent_runs.status,
                    agent_runs.input_hash,
                    agent_runs.created_at,
                    runtime_versions.idempotency_key,
                    runtime_versions.planner_type,
                    runtime_versions.prompt_version,
                    runtime_versions.tool_registry_version
                FROM runtime_versions
                JOIN agent_runs ON agent_runs.run_id = runtime_versions.run_id
                WHERE runtime_versions.idempotency_key = ?
                ORDER BY agent_runs.created_at, agent_runs.run_id
                """,
                (idempotency_key,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _runtime_version_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["runtime_bounds"] = self._loads(item.pop("runtime_bounds_json"))
        item["metadata"] = self._loads(item.pop("metadata_json"))
        return item

    def _typology_route_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["activated"] = self._loads(item.pop("activated_json"))
        item["skipped"] = self._loads(item.pop("skipped_json"))
        item["reasons"] = self._loads(item.pop("reasons_json"))
        item["allowed_tools"] = self._loads(item.pop("allowed_tools_json"))
        return item

    def _agent_step_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["step"] = self._loads(item.pop("step_json"))
        return item

    def _tool_call_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tool_args"] = self._loads(item.pop("tool_args_json"))
        return item

    def _observation_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["facts"] = self._loads(item.pop("facts_json"))
        item["computed_features"] = self._loads(item.pop("computed_features_json"))
        item["source_refs"] = self._loads(item.pop("source_refs_json"))
        item["data_completeness"] = self._loads(item.pop("data_completeness_json"))
        item["limitations"] = self._loads(item.pop("limitations_json"))
        return item

    def _baseline_snapshot_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["features"] = self._loads(item.pop("features_json"))
        item["data_completeness"] = self._loads(item.pop("data_completeness_json"))
        item["limitations"] = self._loads(item.pop("limitations_json"))
        return item

    def _money_flow_path_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["account_path"] = self._loads(item.pop("account_path_json"))
        item["path"] = self._loads(item.pop("path_json"))
        item["graph_signals"] = self._loads(item.pop("graph_signals_json"))
        return item

    def _loads(self, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        return json.loads(value)
