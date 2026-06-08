from __future__ import annotations

import json
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
from compliance_agent.agents.llm_planner import LLMPlanner
from compliance_agent.agents.react_runtime import (
    SCHEMA_ERROR,
    PlannerOutputError,
    ReActRuntime,
    ReActState,
)
from compliance_agent.agents.typology_router import TypologyRouter
from compliance_agent.api import _build_react_runtime
from compliance_agent.config import Settings


class MockLLMProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        *,
        messages,
        model,
        response_schema,
        timeout_seconds,
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "response_schema": response_schema,
                "timeout_seconds": timeout_seconds,
            }
        )
        if not self.responses:
            raise AssertionError("MockLLMProvider has no response queued")
        return self.responses.pop(0)


class Phase7LLMPlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FakeBankSourceRepository()

    def _state(self, alert_id: int = 1005) -> ReActState:
        alert_context = self.source.get_alert_context(alert_id)
        route = TypologyRouter().route(alert_context)
        return ReActState(
            alert_context=alert_context,
            route=route,
            observations={},
            tool_call_count=0,
            step_number=1,
        )

    def test_llm_planner_accepts_strict_allowed_tool_action(self) -> None:
        provider = MockLLMProvider(
            [
                json.dumps(
                    {
                        "thought": "Need the behavioral baseline first.",
                        "next_tool": "compute_behavioral_baseline",
                        "tool_args": {"lookback_days": 180},
                        "stop": False,
                    }
                )
            ]
        )
        planner = LLMPlanner(provider=provider, model_id="mock-model")

        action = planner.next_action(self._state())

        self.assertEqual(action.next_tool, "compute_behavioral_baseline")
        self.assertEqual(action.tool_args["lookback_days"], 180)
        self.assertEqual(action.tool_args["max_rows"], 100)
        self.assertEqual(provider.calls[0]["model"], "mock-model")
        prompt_payload = json.loads(provider.calls[0]["messages"][1]["content"])
        self.assertIn("allowed_tools", prompt_payload)
        self.assertIn("tool_schemas", prompt_payload)

    def test_runtime_uses_mocked_llm_planner_without_live_calls(self) -> None:
        provider = MockLLMProvider(
            [
                json.dumps(
                    {
                        "thought": "Need baseline facts.",
                        "next_tool": "compute_behavioral_baseline",
                        "tool_args": {},
                        "stop": False,
                    }
                ),
                json.dumps(
                    {
                        "thought": "The baseline is insufficient; stop for safe handling.",
                        "next_tool": None,
                        "tool_args": {},
                        "stop": True,
                    }
                ),
            ]
        )
        runtime = ReActRuntime(
            planner=LLMPlanner(provider=provider, model_id="mock-model")
        )

        result = runtime.run_triage(self.source, 1005)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(result.details["react_runtime"]["planner"], "llm")
        self.assertEqual(
            result.details["react_runtime"]["planner_metadata"]["model_id"],
            "mock-model",
        )
        self.assertEqual(len(provider.calls), 2)

    def test_malformed_llm_output_maps_to_schema_error(self) -> None:
        runtime = ReActRuntime(
            planner=LLMPlanner(
                provider=MockLLMProvider(["not json"]),
                model_id="mock-model",
            )
        )

        result = runtime.run_triage(self.source, 1005)

        self.assertEqual(result.recommendation, "investigate")
        self.assertEqual(
            result.details["react_runtime"]["stop_reason"],
            SCHEMA_ERROR,
        )
        self.assertEqual(result.details["react_runtime"]["tool_call_count"], 0)

    def test_llm_output_with_confidence_field_is_rejected(self) -> None:
        planner = LLMPlanner(
            provider=MockLLMProvider(
                [
                    json.dumps(
                        {
                            "thought": "I want to self-certify.",
                            "next_tool": "compute_behavioral_baseline",
                            "tool_args": {},
                            "stop": False,
                            "confidence": 0.99,
                        }
                    )
                ]
            ),
            model_id="mock-model",
        )

        with self.assertRaises(PlannerOutputError):
            planner.next_action(self._state())

    def test_llm_cannot_select_skipped_tool_or_supply_entity_ids(self) -> None:
        skipped_tool_runtime = ReActRuntime(
            planner=LLMPlanner(
                provider=MockLLMProvider(
                    [
                        json.dumps(
                            {
                                "thought": "Try a skipped geography tool.",
                                "next_tool": "run_geography_check",
                                "tool_args": {},
                                "stop": False,
                            }
                        )
                    ]
                ),
                model_id="mock-model",
            )
        )

        skipped_result = skipped_tool_runtime.run_triage(self.source, 1005)

        self.assertEqual(
            skipped_result.details["react_runtime"]["stop_reason"],
            SCHEMA_ERROR,
        )

        entity_id_runtime = ReActRuntime(
            planner=LLMPlanner(
                provider=MockLLMProvider(
                    [
                        json.dumps(
                            {
                                "thought": "Try an arbitrary customer id.",
                                "next_tool": "get_recent_transactions",
                                "tool_args": {"customer_id": 999999},
                                "stop": False,
                            }
                        )
                    ]
                ),
                model_id="mock-model",
            )
        )

        entity_id_result = entity_id_runtime.run_triage(self.source, 1005)

        self.assertEqual(
            entity_id_result.details["react_runtime"]["stop_reason"],
            SCHEMA_ERROR,
        )

    def test_llm_runtime_config_requires_explicit_provider_settings(self) -> None:
        with self.assertRaises(ValueError):
            _build_react_runtime(
                Settings(
                    demo_mode=True,
                    bank_source_dsn=None,
                    sidecar_db_path=":memory:",
                    planner_type="llm",
                    llm_model=None,
                    llm_api_key="key",
                )
            )
        with self.assertRaises(ValueError):
            _build_react_runtime(
                Settings(
                    demo_mode=True,
                    bank_source_dsn=None,
                    sidecar_db_path=":memory:",
                    planner_type="llm",
                    llm_model="mock-model",
                    llm_api_key=None,
                )
            )

        runtime = _build_react_runtime(
            Settings(
                demo_mode=True,
                bank_source_dsn=None,
                sidecar_db_path=":memory:",
                planner_type="llm",
                llm_model="mock-model",
                llm_api_key="key",
            )
        )

        self.assertEqual(runtime.planner.planner_type, "llm")


if __name__ == "__main__":
    unittest.main()
