from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
DEPS = os.path.join(ROOT, ".codex_deps")
for path in (SRC, DEPS):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.agents.pre_screen import PreScreenGate
from compliance_agent.agents.tooling import ToolExecutionContext, UnknownToolError
from compliance_agent.agents.phase1_tools import build_scope_for_alert
from compliance_agent.agents.typology_router import (
    CORE_TOOL_NAMES,
    TYPOLOGY_ORDER,
    TypologyRouter,
)


class Phase5TypologyRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.gate = PreScreenGate()
        self.router = TypologyRouter()

    def _route(self, alert_id: int):
        alert_context = self.source.get_alert_context(alert_id)
        gate_result = self.gate.run(self.source, alert_id)
        baseline = gate_result.tool_observations[
            "compute_behavioral_baseline"
        ].computed_features
        return self.router.route(
            alert_context,
            baseline_features=baseline,
            pre_screen_signals=gate_result.selected_typology_signals,
        )

    def test_no_destination_cash_alert_skips_geography_tool(self) -> None:
        route = self._route(1003)

        self.assertIn("geography", route.skipped)
        self.assertNotIn("run_geography_check", route.registry.names)
        self.assertIn("run_structuring_check", route.registry.names)
        self.assertEqual(set(route.reasons), set(TYPOLOGY_ORDER))
        for tool_name in CORE_TOOL_NAMES:
            self.assertIn(tool_name, route.registry.names)

        context = ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, 1003),
        )
        with self.assertRaises(UnknownToolError):
            route.registry.execute("run_geography_check", context, {})

    def test_destination_country_alert_activates_geography(self) -> None:
        route = self._route(1001)

        self.assertIn("geography", route.activated)
        self.assertIn("run_geography_check", route.registry.names)

    def test_structuring_band_cash_alert_activates_structuring(self) -> None:
        route = self._route(1004)

        self.assertIn("structuring", route.activated)
        self.assertIn("run_structuring_check", route.registry.names)

    def test_sanctions_and_pep_context_activates_sanctions(self) -> None:
        self.source._alert_contexts[1002]["sanctions_matches"] = [
            {
                "sanction_id": 7701,
                "customer_id": 502,
                "full_name": "Morgan Lee",
                "active": True,
            }
        ]
        self.source._alert_contexts[1002]["pep_matches"] = [
            {
                "pep_id": 8801,
                "customer_id": 502,
                "full_name": "Morgan Lee",
                "active": True,
            }
        ]
        route = self._route(1002)

        self.assertIn("sanctions", route.activated)
        self.assertIn("screen_sanctions_pep", route.registry.names)

    def test_same_day_burst_activates_velocity(self) -> None:
        current = self.source._alert_contexts[1002]["transaction"]
        burst = []
        for offset in range(1, 10):
            tx = dict(current)
            tx["transaction_id"] = current["transaction_id"] + offset
            tx["amount_usd"] = 1000 + offset
            tx["created_at"] = f"2026-06-06T1{offset}:00:00+00:00"
            burst.append(tx)
        self.source._alert_contexts[1002]["recent_transactions"] = [current, *burst]

        route = self._route(1002)

        self.assertIn("velocity", route.activated)
        self.assertIn("run_velocity_check", route.registry.names)

    def test_counterparty_or_new_counterparty_activates_graph(self) -> None:
        self.source._alert_contexts[1002]["transaction"]["counterparty_account_id"] = 4500
        route = self._route(1002)

        self.assertIn("graph", route.activated)
        self.assertIn("trace_money_flow", route.registry.names)


if __name__ == "__main__":
    unittest.main()
