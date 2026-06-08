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
from compliance_agent.agents.phase1_tools import build_phase1_tool_registry, build_scope_for_alert
from compliance_agent.agents.tooling import ScopeViolationError, ToolArgumentError, ToolExecutionContext


class Phase3BehavioralBaselineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()
        self.registry = build_phase1_tool_registry()

    def _context_for_alert(self, alert_id: int) -> ToolExecutionContext:
        return ToolExecutionContext(
            source=self.source,
            scope=build_scope_for_alert(self.source, alert_id),
        )

    def test_baseline_tool_rejects_unbounded_args_and_planner_ids(self) -> None:
        context = self._context_for_alert(1003)
        with self.assertRaises(ToolArgumentError):
            self.registry.execute(
                "compute_behavioral_baseline",
                context,
                {"lookback_days": 366},
            )
        with self.assertRaises(ToolArgumentError):
            self.registry.execute(
                "compute_behavioral_baseline",
                context,
                {"max_rows": 101},
            )
        with self.assertRaises(ScopeViolationError):
            self.registry.execute(
                "compute_behavioral_baseline",
                context,
                {"customer_id": 999999},
            )

    def test_high_cash_9500_alert_is_consistent_with_baseline(self) -> None:
        observation = self.registry.execute(
            "compute_behavioral_baseline",
            self._context_for_alert(1003),
            {"lookback_days": 180, "max_rows": 100},
        )
        features = observation.computed_features

        self.assertEqual(features["baseline_assessment"], "consistent")
        self.assertEqual(features["deviation_points"], 0)
        self.assertEqual(features["amount_percentile"], 60.0)
        self.assertEqual(features["observed_cash_pct"], 100.0)
        self.assertEqual(features["median_transaction_amount"], 9450.0)
        self.assertEqual(features["max_transaction_amount"], 9900.0)
        self.assertEqual(features["similar_dismissed_count"], 2)
        self.assertEqual(features["similar_escalated_count"], 0)

    def test_low_cash_9500_alert_is_not_consistent_with_baseline(self) -> None:
        observation = self.registry.execute(
            "compute_behavioral_baseline",
            self._context_for_alert(1004),
            {"lookback_days": 180, "max_rows": 100},
        )
        features = observation.computed_features

        self.assertEqual(features["baseline_assessment"], "strong_deviation")
        self.assertGreaterEqual(features["deviation_points"], 3)
        self.assertEqual(features["amount_percentile"], 100.0)
        self.assertEqual(features["observed_cash_pct"], 0.0)
        self.assertIn("transaction_type_unseen", features["assessment_factors"])
        self.assertIn("amount_percentile_extreme", features["assessment_factors"])
        self.assertEqual(features["similar_escalated_count"], 1)

    def test_new_country_and_counterparty_flags_are_computed(self) -> None:
        self.source._alert_contexts[1004]["transaction"]["destination_country"] = "AE"
        self.source._alert_contexts[1004]["transaction"]["counterparty_account_id"] = 9999
        context = self._context_for_alert(1004)

        observation = self.registry.execute("compute_behavioral_baseline", context, {})
        features = observation.computed_features

        self.assertTrue(features["new_destination_country"])
        self.assertTrue(features["new_counterparty"])
        self.assertIn("new_destination_country", features["assessment_factors"])
        self.assertIn("new_counterparty", features["assessment_factors"])

    def test_insufficient_history_returns_limitation(self) -> None:
        observation = self.registry.execute(
            "compute_behavioral_baseline",
            self._context_for_alert(1005),
            {},
        )

        self.assertEqual(observation.computed_features["baseline_assessment"], "insufficient_data")
        self.assertIn("insufficient_history", observation.computed_features["assessment_factors"])
        self.assertIn("insufficient_history", {item.code for item in observation.limitations})

    def test_history_respects_max_rows_and_marks_truncated(self) -> None:
        observation = self.registry.execute(
            "compute_behavioral_baseline",
            self._context_for_alert(1003),
            {"max_rows": 5},
        )

        self.assertEqual(len(observation.facts["historical_transactions"]), 5)
        self.assertFalse(observation.data_completeness.complete)
        self.assertIn("history_truncated", {item.code for item in observation.limitations})


if __name__ == "__main__":
    unittest.main()
