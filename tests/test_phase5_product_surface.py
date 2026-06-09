from __future__ import annotations

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
for path in (ROOT, SRC):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi.testclient import TestClient

from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.domain import AgentResult, Claim, EvidenceItem, ReasoningItem, SourceRef, ValidationReport


OFFICER = {
    "officer_id": 1,
    "full_name": "Manager",
    "email": "manager@bank.test",
    "is_active": True,
    "branch_id": 1,
    "role_id": 2,
    "role_name": "manager",
    "can_view_alerts": True,
    "can_manage_cases": True,
    "can_file_sar": False,
    "can_manage_rules": False,
    "can_manage_users": False,
}

VIEW_ONLY = {**OFFICER, "officer_id": 2, "can_manage_cases": False, "can_file_sar": False}
SAR_OFFICER = {**OFFICER, "officer_id": 3, "can_file_sar": True}

HEADERS = {"X-Officer-Id": "1"}


def make_client() -> TestClient:
    from backend.main import app

    return TestClient(app, raise_server_exceptions=False)


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id="demo-bank",
        bank_source_dsn="postgresql://example.invalid/db",
        sidecar_db_path="data/test-sidecar.sqlite3",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_endpoint="https://example.invalid/v1/chat/completions",
        llm_timeout_seconds=30.0,
        llm_prompt_version="phase5_prompt_v1",
        mcp_tool_registry_version="phase5_tools_v1",
        agent_policy_version="phase5_policy_v1",
    )


def mock_rbac(mock_ro, officer=OFFICER) -> None:
    cur = MagicMock()
    cur.fetchone.return_value = officer
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    mock_ro.return_value = cur


def mock_audit(mock_rw) -> None:
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    mock_rw.return_value = conn


def run_record(*, agent_name: str = "investigation_agent", subject_type: str = "alert") -> dict:
    return {
        "run": {
            "run_id": "run-phase5",
            "agent_name": agent_name,
            "subject_type": subject_type,
            "subject_id": "1003",
            "status": "completed",
            "created_at": "2026-06-09T00:00:00+00:00",
        },
        "output": {
            "agent_name": agent_name,
            "subject_type": subject_type,
            "subject_id": "1003",
            "recommendation": "open_case",
            "confidence": 0.74,
            "score": 42,
            "reasoning": [
                {
                    "statement": "Evidence supports human review.",
                    "source_refs": [{"table": "alerts", "key": "1003", "columns": ["alert_id", "status"]}],
                }
            ],
            "claims": [
                {
                    "statement": "Alert is linked to governed evidence.",
                    "source_refs": [{"table": "alerts", "key": "1003", "columns": ["alert_id", "status"]}],
                }
            ],
            "details": {
                "required_human_action": "Review proposal and record a decision.",
                "phase4_live_mcp": {
                    "workflow": "investigation",
                    "stop_reason": "completed",
                    "tool_calls": [{"tool_name": "get_prior_alerts", "audit_id": "audit-tool"}],
                },
            },
        },
        "validation": {
            "status": "passed",
            "unsupported_count": 0,
            "report_json": "{\"findings\": [{\"statement\": \"All claims grounded.\"}]}",
        },
        "evidence": [
            {
                "evidence_id": "alerts:1003",
                "source_table": "alerts",
                "source_key": "1003",
                "fields": ["alert_id", "status"],
                "payload_json": "{\"alert_id\": 1003, \"status\": \"open\"}",
            }
        ],
    }


class Phase5UnifiedWorkflowEndpointTest(unittest.TestCase):
    @patch("backend.routes.agent_runs.rw_conn")
    @patch("backend.routes.agent_runs.LiveMCPWorkflowAgent")
    @patch("backend.routes.agent_runs.PostgresReferenceRepository")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_unified_live_mcp_routes_all_workflows_with_scoped_requests(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_repo_cls,
        mock_agent_cls,
        mock_rw,
    ) -> None:
        mock_rbac(mock_rbac_ro)
        mock_audit(mock_rw)
        mock_settings.return_value = settings()
        repo = MagicMock()
        repo.get_alert_scope.return_value = {
            "alert_id": 1003,
            "customer_id": 503,
            "account_id": 3003,
            "transaction_id": 7030,
        }
        repo.get_customer_scope.return_value = {
            "customer_id": 503,
            "account_ids": [3003],
            "transaction_ids": [7030, 7031],
            "case_ids": [9001],
        }
        repo.get_case_scope.return_value = {
            "case_id": 9001,
            "customer_id": 503,
            "primary_alert_id": 1003,
            "account_ids": [3003],
            "transaction_ids": [7030],
            "case_ids": [9001],
        }
        mock_repo_cls.return_value = repo
        captured = []
        agent = MagicMock()

        def run_and_persist(workflow, request, sidecar, officer_context=""):
            captured.append((workflow, request, officer_context))
            return {"run_id": f"run-{workflow}", "workflow": workflow}

        agent.run_and_persist.side_effect = run_and_persist
        mock_agent_cls.return_value = agent

        client = make_client()
        bodies = [
            {"workflow": "triage", "alert_id": 1003},
            {"workflow": "investigation", "alert_id": 1003},
            {"workflow": "risk_scoring", "customer_id": 503},
            {"workflow": "sar_drafting", "case_id": 9001, "officer_context": "Narrative context"},
        ]
        for body in bodies:
            resp = client.post("/api/agent-runs/live-mcp", json=body, headers=HEADERS)
            self.assertEqual(resp.status_code, 200, resp.text)

        self.assertEqual([item[0] for item in captured], ["triage", "investigation", "risk_scoring", "sar_drafting"])
        self.assertEqual(captured[0][1].scope.allowed_transaction_ids, [7030])
        self.assertEqual(captured[2][1].subject.customer_id, 503)
        self.assertEqual(captured[2][1].scope.allowed_case_ids, [9001])
        self.assertEqual(captured[3][1].subject.case_id, 9001)
        self.assertEqual(captured[3][1].subject.alert_id, 1003)
        self.assertEqual(captured[3][2], "Narrative context")

    @patch("backend.routes.agent_runs.rw_conn")
    @patch("backend.routes.agent_runs.LiveMCPWorkflowAgent")
    @patch("backend.routes.agent_runs.PostgresReferenceRepository")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_live_mcp_triage_compatibility_wrapper_dispatches_triage(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_repo_cls,
        mock_agent_cls,
        mock_rw,
    ) -> None:
        mock_rbac(mock_rbac_ro)
        mock_audit(mock_rw)
        mock_settings.return_value = settings()
        repo = MagicMock()
        repo.get_alert_scope.return_value = {
            "alert_id": 1003,
            "customer_id": 503,
            "account_id": 3003,
            "transaction_id": 7030,
        }
        mock_repo_cls.return_value = repo
        agent = MagicMock()
        agent.run_and_persist.return_value = {"run_id": "run-triage"}
        mock_agent_cls.return_value = agent

        resp = make_client().post("/api/agent-runs/live-mcp-triage", json={"alert_id": 1003}, headers=HEADERS)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(agent.run_and_persist.call_args.args[0], "triage")


class Phase5SidecarPersistenceTest(unittest.TestCase):
    def test_phase4_trace_decision_and_export_are_replayable_and_separate(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.unlink(path)
        try:
            store = SidecarStore(path)
            source = SourceRef("alerts", "1003", ("alert_id",))
            result = AgentResult(
                agent_name="investigation_agent",
                subject_type="alert",
                subject_id=1003,
                recommendation="open_case",
                confidence=0.74,
                score=42,
                reasoning=[ReasoningItem("Investigate linked activity.", [source])],
                claims=[Claim("Alert has linked evidence.", [source])],
                evidence=[EvidenceItem("alerts:1003", source, {"alert_id": 1003})],
                details={
                    "phase4_live_mcp": {
                        "workflow": "investigation",
                        "planner_type": "live_mcp_llm",
                        "model_id": "mock-model",
                        "prompt_version": "phase5_prompt_v1",
                        "tool_registry_version": "phase5_tools_v1",
                        "policy_version": "phase5_policy_v1",
                        "terminal_state": "proposed",
                        "stop_reason": "completed",
                        "runtime_events": [
                            {
                                "event_id": "evt-1",
                                "sequence_number": 1,
                                "state": "created",
                                "event_type": "runtime_created",
                                "created_at": "2026-06-09T00:00:00+00:00",
                            }
                        ],
                        "trace": [
                            {
                                "step_number": 1,
                                "status": "tool_executed",
                                "thought": "Check baseline.",
                                "hypothesis_after": "Baseline is relevant.",
                                "tool_name": "get_behavioral_baseline",
                                "tool_args": {"lookback_days": 180},
                            }
                        ],
                        "tool_calls": [
                            {
                                "step_number": 1,
                                "tool_name": "get_behavioral_baseline",
                                "tool_args": {"lookback_days": 180},
                                "status": "ok",
                                "audit_id": "audit-baseline",
                            }
                        ],
                        "observations": [
                            {
                                "step_number": 1,
                                "tool_name": "get_behavioral_baseline",
                                "facts": {
                                    "computed_features": {"baseline_assessment": "strong_deviation"}
                                },
                                "source_refs": [{"entity_type": "alert", "entity_id": "1003"}],
                                "data_completeness": {"complete": True},
                                "limitations": [],
                            }
                        ],
                    }
                },
            )
            store.save_result("run-phase5", {"workflow": "investigation"}, result, ValidationReport("val-1", "passed", []))
            trace = store.get_trace("run-phase5")
            assert trace is not None
            decision = store.record_human_decision(
                "run-phase5",
                officer_id="1",
                decision="approve",
                rationale="Evidence supports case opening.",
            )
            export = store.record_bank_export(
                "run-phase5",
                decision_id=decision["decision_id"],
                officer_id="1",
                export_type="human_decision",
                destination="bank_system_of_record",
                payload={"run_id": "run-phase5", "decision_id": decision["decision_id"]},
            )
            stored = store.get_run("run-phase5")
        finally:
            if os.path.exists(path):
                os.remove(path)

        self.assertEqual(trace["phase4_workflow"]["workflow"], "investigation")
        self.assertEqual(trace["runtime_events"][0]["event_type"], "runtime_created")
        self.assertEqual(trace["tool_calls"][0]["tool_name"], "get_behavioral_baseline")
        self.assertEqual(trace["baseline_snapshots"][0]["baseline_assessment"], "strong_deviation")
        self.assertEqual(decision["decision"], "approve")
        self.assertEqual(export["status"], "export_recorded")
        assert stored is not None
        self.assertEqual(stored["output"]["recommendation"], "open_case")


class Phase5ReviewDecisionExportEndpointTest(unittest.TestCase):
    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_review_endpoint_returns_officer_facing_fields(self, mock_rbac_ro, mock_settings, mock_store_cls) -> None:
        mock_rbac(mock_rbac_ro)
        mock_settings.return_value = settings()
        store = MagicMock()
        store.get_run.return_value = run_record()
        store.get_trace.return_value = {
            "phase4_workflow": {"workflow": "investigation"},
            "stop_reason": "completed",
            "runtime_events": [
                {
                    "sequence_number": 1,
                    "state": "created",
                    "event_type": "runtime_created",
                    "audit_id": "audit-runtime",
                }
            ],
            "agent_steps": [
                {
                    "step_number": 1,
                    "status": "planning",
                    "thought": "Load prior alert evidence before proposing.",
                }
            ],
            "tool_calls": [
                {
                    "step_number": 1,
                    "tool_name": "get_prior_alerts",
                    "status": "ok",
                    "audit_id": "audit-tool",
                    "policy_decisions": [{"decision": "allow"}],
                }
            ],
            "observations": [
                {
                    "step_number": 1,
                    "tool_name": "get_prior_alerts",
                    "data_completeness": {"complete": True, "rows_returned": 2},
                }
            ],
        }
        store.list_human_decisions.return_value = [
            {"decision_id": "decision-1", "decision": "approve", "created_at": "2026-06-09T00:05:00+00:00"}
        ]
        store.list_bank_exports.return_value = [
            {"export_id": "export-1", "status": "export_recorded", "created_at": "2026-06-09T00:06:00+00:00"}
        ]
        mock_store_cls.return_value = store

        resp = make_client().get("/api/agent-runs/run-phase5/review", headers=HEADERS)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["recommendation"], "open_case")
        self.assertEqual(body["workflow"], "investigation")
        self.assertEqual(body["agent_name"], "investigation_agent")
        self.assertEqual(body["subject"], {"type": "alert", "id": "1003"})
        self.assertEqual(body["created_at"], "2026-06-09T00:00:00+00:00")
        self.assertEqual(body["status"], "completed")
        self.assertIn("evidence", body)
        self.assertIn("alert_id: 1003", body["evidence"][0]["payload_preview"])
        self.assertIn("reasoning", body)
        self.assertIn("limitations", body)
        self.assertIn("missing_data", body)
        self.assertEqual(body["stop_reason"], "completed")
        self.assertIn("audit-tool", body["audit_ids"])
        self.assertEqual(body["latest_human_decision"]["decision_id"], "decision-1")
        self.assertEqual(body["latest_export"]["export_id"], "export-1")
        self.assertEqual(body["validation_findings"][0]["statement"], "All claims grounded.")
        tool_item = next(item for item in body["workflow_timeline"] if item.get("tool_name") == "get_prior_alerts" and item["phase"] == "tool")
        self.assertEqual(tool_item["audit_id"], "audit-tool")
        self.assertEqual(tool_item["policy_decisions"][0]["decision"], "allow")
        observation_item = next(item for item in body["workflow_timeline"] if item["phase"] == "observation")
        self.assertEqual(observation_item["data_completeness"]["rows_returned"], 2)

    @patch("backend.routes.agent_runs.rw_conn")
    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_human_decision_and_export_are_explicit_and_audited(
        self,
        mock_rbac_ro,
        mock_settings,
        mock_store_cls,
        mock_rw,
    ) -> None:
        mock_rbac(mock_rbac_ro)
        mock_audit(mock_rw)
        mock_settings.return_value = settings()
        store = MagicMock()
        store.get_run.return_value = run_record()
        store.get_trace.return_value = {"stop_reason": "completed", "runtime_events": [], "tool_calls": [], "observations": []}
        store.record_human_decision.return_value = {
            "decision_id": "decision-1",
            "run_id": "run-phase5",
            "decision": "approve",
        }
        store.list_human_decisions.return_value = [{"decision_id": "decision-1", "decision": "approve"}]
        store.list_bank_exports.return_value = []
        store.record_bank_export.return_value = {
            "export_id": "export-1",
            "run_id": "run-phase5",
            "decision_id": "decision-1",
            "status": "export_recorded",
        }
        mock_store_cls.return_value = store
        client = make_client()

        decision_resp = client.post(
            "/api/agent-runs/run-phase5/human-decisions",
            json={"decision": "approve", "rationale": "Reviewed"},
            headers=HEADERS,
        )
        export_resp = client.post("/api/agent-runs/run-phase5/exports", json={}, headers=HEADERS)

        self.assertEqual(decision_resp.status_code, 201)
        self.assertEqual(export_resp.status_code, 201)
        store.record_human_decision.assert_called_once()
        store.record_bank_export.assert_called_once()
        audit_sql = " ".join(str(call.args[0]) for call in mock_rw.return_value.cursor.return_value.execute.call_args_list)
        self.assertIn("audit_log", audit_sql)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_export_requires_prior_human_decision(self, mock_rbac_ro, mock_settings, mock_store_cls) -> None:
        mock_rbac(mock_rbac_ro)
        mock_settings.return_value = settings()
        store = MagicMock()
        store.get_run.return_value = run_record()
        store.list_human_decisions.return_value = []
        mock_store_cls.return_value = store

        resp = make_client().post("/api/agent-runs/run-phase5/exports", json={}, headers=HEADERS)

        self.assertEqual(resp.status_code, 409)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_rbac_denies_unprivileged_human_actions(self, mock_rbac_ro, mock_settings, mock_store_cls) -> None:
        mock_rbac(mock_rbac_ro, VIEW_ONLY)
        mock_settings.return_value = settings()
        store = MagicMock()
        store.get_run.return_value = run_record()
        mock_store_cls.return_value = store

        resp = make_client().post(
            "/api/agent-runs/run-phase5/human-decisions",
            json={"decision": "approve"},
            headers={"X-Officer-Id": "2"},
        )

        self.assertEqual(resp.status_code, 403)

    @patch("backend.routes.agent_runs.SidecarStore")
    @patch("backend.routes.agent_runs.Settings.from_env")
    @patch("backend.rbac.ro_cursor")
    def test_sar_decision_requires_file_sar_permission(self, mock_rbac_ro, mock_settings, mock_store_cls) -> None:
        mock_rbac(mock_rbac_ro, OFFICER)
        mock_settings.return_value = settings()
        store = MagicMock()
        store.get_run.return_value = run_record(agent_name="sar_drafting_agent", subject_type="case")
        mock_store_cls.return_value = store

        resp = make_client().post(
            "/api/agent-runs/run-sar/human-decisions",
            json={"decision": "approve"},
            headers=HEADERS,
        )

        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
