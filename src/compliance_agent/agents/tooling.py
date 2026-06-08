from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field as dataclass_field, replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..adapters.source import BankSourceRepository


class ToolRegistryError(RuntimeError):
    """Base error for planner-facing tool execution."""


class UnknownToolError(ToolRegistryError):
    pass


class ToolArgumentError(ToolRegistryError):
    pass


class ToolOutputError(ToolRegistryError):
    pass


class ScopeViolationError(ToolRegistryError):
    pass


FORBIDDEN_PLANNER_ENTITY_FIELDS = {
    "alert_id",
    "customer_id",
    "account_id",
    "transaction_id",
    "case_id",
}


class StrictToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyToolArgs(StrictToolArgs):
    pass


class LookbackToolArgs(StrictToolArgs):
    lookback_days: int = Field(default=180, ge=1, le=365)


class BehavioralBaselineArgs(StrictToolArgs):
    lookback_days: int = Field(default=180, ge=1, le=365)
    max_rows: int = Field(default=100, ge=1, le=100)
    amount_tolerance_pct: float = Field(default=15.0, ge=1.0, le=50.0)


class RowLimitToolArgs(StrictToolArgs):
    max_rows: int = Field(default=100, ge=1, le=100)
    lookback_days: int = Field(default=180, ge=1, le=365)


class TraceMoneyFlowArgs(StrictToolArgs):
    max_hops: int = Field(default=1, ge=1, le=4)
    max_rows: int = Field(default=25, ge=1, le=100)


class SourceRefRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str
    key: str
    columns: list[str] = Field(default_factory=list)


class TrustedGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_transaction_id: int
    source_account_id: int
    counterparty_account_id: int
    evidence_refs: list[SourceRefRecord] = Field(default_factory=list)


class DataCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookback_days_requested: int | None = None
    lookback_days_available: int | None = None
    rows_requested: int | None = None
    rows_returned: int | None = None
    missing_segments: list[str] = Field(default_factory=list)
    complete: bool = True


class ToolLimitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    severity: str = "info"


class ToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any] = Field(default_factory=dict)
    computed_features: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRefRecord] = Field(default_factory=list)
    data_completeness: DataCompleteness = Field(default_factory=DataCompleteness)
    limitations: list[ToolLimitation] = Field(default_factory=list)


class InvestigationScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: int
    customer_id: int
    account_id: int
    transaction_id: int
    allowed_customer_ids: set[int] = Field(default_factory=set)
    allowed_account_ids: set[int] = Field(default_factory=set)
    allowed_transaction_ids: set[int] = Field(default_factory=set)
    trusted_graph_edges: list[TrustedGraphEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_root_ids_are_allowed(self) -> "InvestigationScope":
        self.allowed_customer_ids.add(self.customer_id)
        self.allowed_account_ids.add(self.account_id)
        self.allowed_transaction_ids.add(self.transaction_id)
        return self

    @classmethod
    def from_alert_context(cls, alert_context: dict[str, Any]) -> "InvestigationScope":
        alert = alert_context["alert"]
        customer = alert_context["customer"]
        account = alert_context["account"]
        transaction = alert_context["transaction"]
        return cls(
            alert_id=int(alert["alert_id"]),
            customer_id=int(customer["customer_id"]),
            account_id=int(account["account_id"]),
            transaction_id=int(transaction["transaction_id"]),
        )

    def assert_root_allowed(self) -> None:
        if self.customer_id not in self.allowed_customer_ids:
            raise ScopeViolationError(f"Customer {self.customer_id} is outside allowed scope.")
        if self.account_id not in self.allowed_account_ids:
            raise ScopeViolationError(f"Account {self.account_id} is outside allowed scope.")
        if self.transaction_id not in self.allowed_transaction_ids:
            raise ScopeViolationError(
                f"Transaction {self.transaction_id} is outside allowed scope."
            )

    def with_trusted_graph_edges(
        self,
        edges: list[TrustedGraphEdge],
    ) -> "InvestigationScope":
        allowed_account_ids = set(self.allowed_account_ids)
        allowed_transaction_ids = set(self.allowed_transaction_ids)
        trusted_graph_edges = list(self.trusted_graph_edges)
        existing = {
            (
                edge.source_transaction_id,
                edge.source_account_id,
                edge.counterparty_account_id,
            )
            for edge in trusted_graph_edges
        }

        for edge in edges:
            if edge.source_account_id not in allowed_account_ids:
                raise ScopeViolationError("Graph edge source account is outside allowed scope.")
            allowed_transaction_ids.add(edge.source_transaction_id)
            allowed_account_ids.add(edge.counterparty_account_id)
            key = (
                edge.source_transaction_id,
                edge.source_account_id,
                edge.counterparty_account_id,
            )
            if key not in existing:
                trusted_graph_edges.append(edge)
                existing.add(key)

        return self.model_copy(
            update={
                "allowed_account_ids": allowed_account_ids,
                "allowed_transaction_ids": allowed_transaction_ids,
                "trusted_graph_edges": trusted_graph_edges,
            },
            deep=True,
        )


class ScopePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "root_alert"
    requires_root_scope: bool = True
    allow_graph_expansion: bool = False
    allowed_planner_entity_fields: set[str] = Field(default_factory=set)

    @classmethod
    def root_alert(cls) -> "ScopePolicy":
        return cls(name="root_alert")

    @classmethod
    def graph_expandable(cls) -> "ScopePolicy":
        return cls(name="graph_expandable", allow_graph_expansion=True)


@dataclass(frozen=True)
class ToolExecutionContext:
    source: BankSourceRepository
    scope: InvestigationScope

    def with_observation(self, observation: ToolObservation) -> "ToolExecutionContext":
        raw_edges = observation.computed_features.get("trusted_graph_edges", [])
        if not raw_edges:
            return self
        edges = [TrustedGraphEdge.model_validate(edge) for edge in raw_edges]
        return replace(self, scope=self.scope.with_trusted_graph_edges(edges))


ToolHandler = Callable[[ToolExecutionContext, BaseModel], ToolObservation | dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    purpose: str
    args_model: type[BaseModel]
    handler: ToolHandler
    scope_policy: ScopePolicy = dataclass_field(default_factory=ScopePolicy.root_alert)


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition] | None = None) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    @property
    def names(self) -> set[str]:
        return set(self._definitions)

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._definitions:
            raise ToolRegistryError(f"Tool already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def subset(self, allowed_names: set[str] | list[str] | tuple[str, ...]) -> "ToolRegistry":
        allowed = set(allowed_names)
        missing = sorted(allowed - self.names)
        if missing:
            raise UnknownToolError(f"Unknown tool(s): {', '.join(missing)}")
        return ToolRegistry(
            [
                definition
                for name, definition in self._definitions.items()
                if name in allowed
            ]
        )

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise UnknownToolError(f"Unknown tool: {name}") from exc

    def execute(
        self,
        name: str,
        context: ToolExecutionContext,
        args: dict[str, Any] | None = None,
    ) -> ToolObservation:
        return self._execute(name, context, args)

    def execute_with_context(
        self,
        name: str,
        context: ToolExecutionContext,
        args: dict[str, Any] | None = None,
    ) -> tuple[ToolObservation, ToolExecutionContext]:
        observation = self._execute(name, context, args)
        return observation, context.with_observation(observation)

    def _execute(
        self,
        name: str,
        context: ToolExecutionContext,
        args: dict[str, Any] | None = None,
    ) -> ToolObservation:
        definition = self.get(name)
        raw_args = args or {}
        self._reject_forbidden_entity_args(definition, raw_args)
        self._enforce_scope_policy(definition, context)
        try:
            parsed_args = definition.args_model.model_validate(raw_args)
        except ValidationError as exc:
            raise ToolArgumentError(str(exc)) from exc

        raw_observation = definition.handler(context, parsed_args)
        try:
            return ToolObservation.model_validate(raw_observation)
        except ValidationError as exc:
            raise ToolOutputError(str(exc)) from exc

    def _reject_forbidden_entity_args(
        self,
        definition: ToolDefinition,
        args: dict[str, Any],
    ) -> None:
        allowed_fields = definition.scope_policy.allowed_planner_entity_fields
        forbidden_paths = list(_find_forbidden_entity_args(args, allowed_fields))
        if forbidden_paths:
            joined = ", ".join(forbidden_paths)
            raise ScopeViolationError(
                f"Planner supplied forbidden scoped entity field(s): {joined}"
            )

    def _enforce_scope_policy(
        self,
        definition: ToolDefinition,
        context: ToolExecutionContext,
    ) -> None:
        if definition.scope_policy.requires_root_scope:
            context.scope.assert_root_allowed()


def _find_forbidden_entity_args(
    value: Any,
    allowed_fields: set[str],
    path: str = "$",
) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_PLANNER_ENTITY_FIELDS and key not in allowed_fields:
                found.append(child_path)
            found.extend(_find_forbidden_entity_args(nested_value, allowed_fields, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_forbidden_entity_args(item, allowed_fields, f"{path}[{index}]"))
    return found
