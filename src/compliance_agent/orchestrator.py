from __future__ import annotations

from typing import Any

from .adapters.sidecar_store import SidecarStore
from .adapters.source import BankSourceRepository
from .agents.investigation import InvestigationAgent
from .agents.pre_screen import PreScreenGate
from .agents.risk import RiskScoringAgent
from .agents.sar import SARDraftingAgent
from .agents.triage import TriageAgent
from .agents.validation import ComplianceValidationAgent
from .domain import AgentResult, ValidationReport
from .utils import new_id, to_plain


class ComplianceOrchestrator:
    def __init__(
        self,
        source: BankSourceRepository,
        sidecar: SidecarStore,
        triage_agent: TriageAgent | None = None,
        pre_screen_gate: PreScreenGate | None = None,
        investigation_agent: InvestigationAgent | None = None,
        risk_agent: RiskScoringAgent | None = None,
        sar_agent: SARDraftingAgent | None = None,
        validation_agent: ComplianceValidationAgent | None = None,
    ) -> None:
        self.source = source
        self.sidecar = sidecar
        self.triage_agent = triage_agent or TriageAgent()
        self.pre_screen_gate = pre_screen_gate or PreScreenGate()
        self.investigation_agent = investigation_agent or InvestigationAgent()
        self.risk_agent = risk_agent or RiskScoringAgent()
        self.sar_agent = sar_agent or SARDraftingAgent()
        self.validation_agent = validation_agent or ComplianceValidationAgent()

    def triage_alert(self, alert_id: int) -> dict[str, Any]:
        context = self.source.get_alert_context(alert_id)
        pre_screen = self.pre_screen_gate.run(self.source, alert_id)
        if pre_screen.gate_decision in {"obvious_clear", "obvious_escalate"}:
            result = pre_screen.to_agent_result()
        else:
            result = self.triage_agent.run(context)
            result.details["triage_path"] = "pre_screen_ambiguous_fallback"
            result.details["pre_screen_gate"] = pre_screen.to_details()
            result.details["baseline_assessment"] = pre_screen.baseline_assessment
            result.details["reason_codes"] = list(pre_screen.reason_codes)
            result.details["selected_typology_signals"] = dict(
                pre_screen.selected_typology_signals
            )
            result.details["human_required"] = True
        return self._validate_and_persist(context, result)

    def investigate_alert(self, alert_id: int) -> dict[str, Any]:
        context = self.source.get_alert_context(alert_id)
        result = self.investigation_agent.run(context)
        return self._validate_and_persist(context, result)

    def score_customer(self, customer_id: int) -> dict[str, Any]:
        context = self.source.get_customer_context(customer_id)
        result = self.risk_agent.run(context)
        return self._validate_and_persist(context, result)

    def draft_sar(self, case_id: int) -> dict[str, Any]:
        context = self.source.get_case_context(case_id)
        result = self.sar_agent.run(context)
        return self._validate_and_persist(context, result)

    def _validate_and_persist(
        self,
        input_payload: dict[str, Any],
        result: AgentResult,
    ) -> dict[str, Any]:
        validation = self.validation_agent.validate(result)
        if validation.status != "passed":
            result.details["validation_blocked"] = True
        run_id = new_id("run")
        self.sidecar.save_result(run_id, input_payload, result, validation)
        return self._response(run_id, result, validation)

    def _response(
        self,
        run_id: str,
        result: AgentResult,
        validation: ValidationReport,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "result": to_plain(result),
            "validation": to_plain(validation),
        }
