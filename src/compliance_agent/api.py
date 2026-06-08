from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .adapters.fake_source import FakeBankSourceRepository
from .adapters.postgres_source import PostgresBankSourceRepository
from .adapters.sidecar_store import SidecarStore
from .adapters.source import SourceRecordNotFound
from .config import Settings
from .orchestrator import ComplianceOrchestrator


def build_orchestrator(settings: Settings) -> ComplianceOrchestrator:
    if settings.demo_mode or not settings.bank_source_dsn:
        source = FakeBankSourceRepository()
    else:
        source = PostgresBankSourceRepository(settings.bank_source_dsn)
    sidecar = SidecarStore(settings.sidecar_db_path)
    return ComplianceOrchestrator(source=source, sidecar=sidecar)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    orchestrator = build_orchestrator(settings)
    app = FastAPI(
        title="Open AML Compliance Sidecar",
        description="Read-only AML investigation sidecar with validated agent outputs.",
        version="0.1.0",
    )
    app.state.orchestrator = orchestrator
    app.state.sidecar = orchestrator.sidecar

    @app.get("/health")
    def health() -> dict[str, str]:
        mode = "demo" if settings.demo_mode or not settings.bank_source_dsn else "bank_source"
        return {"status": "healthy", "source_mode": mode}

    @app.post("/api/alerts/{alert_id}/triage")
    def triage_alert(alert_id: int) -> dict:
        try:
            return orchestrator.triage_alert(alert_id)
        except SourceRecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/alerts/{alert_id}/investigate")
    def investigate_alert(alert_id: int) -> dict:
        try:
            return orchestrator.investigate_alert(alert_id)
        except SourceRecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/customers/{customer_id}/risk-score")
    def score_customer(customer_id: int) -> dict:
        try:
            return orchestrator.score_customer(customer_id)
        except SourceRecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/cases/{case_id}/sar-draft")
    def draft_sar(case_id: int) -> dict:
        try:
            return orchestrator.draft_sar(case_id)
        except SourceRecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/sidecar/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        record = orchestrator.sidecar.get_run(run_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"run_id={run_id}")
        return record

    return app


app = create_app()
