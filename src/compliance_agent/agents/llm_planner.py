from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .react_runtime import (
    PlannerAction,
    PlannerOutputError,
    PlannerProviderError,
    ReActState,
)
from .tooling import FORBIDDEN_PLANNER_ENTITY_FIELDS, UnknownToolError


PROMPT_VERSION = "llm_planner_v1"


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_schema: dict[str, Any],
        timeout_seconds: float,
    ) -> str:
        ...


class OpenAICompatibleChatProvider:
    """Small standard-library provider for OpenAI-compatible chat endpoints."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        response_schema: dict[str, Any],
        timeout_seconds: float,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise PlannerProviderError(str(exc)) from exc

        try:
            decoded = json.loads(raw)
            return str(decoded["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise PlannerProviderError("LLM provider response did not contain message content.") from exc


class PlannerActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str = Field(min_length=1, max_length=2000)
    next_tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    stop: bool = False

    @model_validator(mode="after")
    def ensure_action_shape(self) -> "PlannerActionPayload":
        if self.stop:
            if self.next_tool is not None:
                raise ValueError("stop actions must not include next_tool")
            if self.tool_args:
                raise ValueError("stop actions must not include tool_args")
        elif not self.next_tool:
            raise ValueError("non-stop actions must include next_tool")
        return self


class LLMPlanner:
    """LLM-backed planner behind the same planner interface as heuristics."""

    planner_type = "llm"
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        provider: LLMProvider,
        model_id: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not model_id:
            raise ValueError("model_id is required for LLMPlanner")
        self.provider = provider
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds

    def next_action(self, state: ReActState) -> PlannerAction:
        messages = self._messages(state)
        raw = self.provider.complete(
            messages=messages,
            model=self.model_id,
            response_schema=PlannerActionPayload.model_json_schema(),
            timeout_seconds=self.timeout_seconds,
        )
        payload = self._parse_payload(raw)
        self._validate_against_runtime(payload, state)
        return PlannerAction(
            thought=payload.thought,
            next_tool=payload.next_tool,
            tool_args=dict(payload.tool_args),
            stop=payload.stop,
        )

    def _parse_payload(self, raw: str) -> PlannerActionPayload:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlannerOutputError("Planner output was not strict JSON.") from exc
        try:
            return PlannerActionPayload.model_validate(decoded)
        except ValidationError as exc:
            raise PlannerOutputError(str(exc)) from exc

    def _validate_against_runtime(
        self,
        payload: PlannerActionPayload,
        state: ReActState,
    ) -> None:
        if payload.stop:
            return
        assert payload.next_tool is not None
        try:
            definition = state.route.registry.get(payload.next_tool)
        except UnknownToolError as exc:
            raise PlannerOutputError(
                f"Planner selected unavailable tool: {payload.next_tool}"
            ) from exc

        forbidden_paths = _find_forbidden_entity_args(payload.tool_args)
        if forbidden_paths:
            raise PlannerOutputError(
                "Planner supplied forbidden scoped entity field(s): "
                + ", ".join(forbidden_paths)
            )

        try:
            parsed_args = definition.args_model.model_validate(payload.tool_args)
        except ValidationError as exc:
            raise PlannerOutputError(str(exc)) from exc
        payload.tool_args = parsed_args.model_dump()

    def _messages(self, state: ReActState) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a bounded AML investigation planner. Return one strict "
                    "JSON object only. You may choose only an allowed tool, provide "
                    "only schema-valid bounded tool_args, or stop. You must not "
                    "provide entity IDs such as customer_id, account_id, "
                    "transaction_id, alert_id, or case_id. You must not request SQL, "
                    "mutate source data, choose a final disposition, or provide "
                    "confidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "prompt_version": self.prompt_version,
                        "required_json_schema": PlannerActionPayload.model_json_schema(),
                        "allowed_tools": sorted(state.route.registry.names),
                        "tool_schemas": self._tool_schemas(state),
                        "typology_route": state.route.to_details(),
                        "alert_summary": self._alert_summary(state.alert_context),
                        "observed_tools": sorted(state.observations),
                        "observations": self._observation_summaries(state),
                        "tool_call_count": state.tool_call_count,
                        "step_number": state.step_number,
                    },
                    sort_keys=True,
                    default=str,
                ),
            },
        ]

    def _tool_schemas(self, state: ReActState) -> dict[str, Any]:
        schemas = {}
        for tool_name in sorted(state.route.registry.names):
            definition = state.route.registry.get(tool_name)
            schemas[tool_name] = {
                "purpose": definition.purpose,
                "args_schema": definition.args_model.model_json_schema(),
            }
        return schemas

    def _alert_summary(self, alert_context: dict[str, Any]) -> dict[str, Any]:
        alert = alert_context.get("alert") or {}
        rule = alert_context.get("rule") or {}
        transaction = alert_context.get("transaction") or {}
        customer = alert_context.get("customer") or {}
        return {
            "alert": {
                "severity": alert.get("severity"),
                "status": alert.get("status"),
            },
            "rule": {
                "rule_type": rule.get("rule_type"),
                "rule_name": rule.get("rule_name"),
                "severity": rule.get("severity"),
            },
            "transaction": {
                "transaction_type": transaction.get("transaction_type"),
                "amount_usd": transaction.get("amount_usd"),
                "destination_country": transaction.get("destination_country"),
                "has_counterparty": transaction.get("counterparty_account_id") is not None,
            },
            "customer": {
                "risk_level": customer.get("risk_level"),
                "kyc_status": customer.get("kyc_status"),
            },
        }

    def _observation_summaries(self, state: ReActState) -> dict[str, Any]:
        summaries = {}
        for tool_name, observation in state.observations.items():
            summaries[tool_name] = {
                "fact_keys": sorted(observation.facts),
                "computed_features": dict(observation.computed_features),
                "source_refs": [
                    ref.model_dump(mode="json")
                    for ref in observation.source_refs
                ],
                "data_completeness": observation.data_completeness.model_dump(mode="json"),
                "limitations": [
                    limitation.model_dump(mode="json")
                    for limitation in observation.limitations
                ],
            }
        return summaries


def _find_forbidden_entity_args(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_PLANNER_ENTITY_FIELDS:
                found.append(child_path)
            found.extend(_find_forbidden_entity_args(nested_value, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_entity_args(item, f"{path}[{index}]"))
    return found
