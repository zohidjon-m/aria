from __future__ import annotations

import logging
import os
import sys

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from compliance_agent.api import build_orchestrator
from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.adapters.source import SourceRecordNotFound
from compliance_agent.config import Settings

from ..audit import insert_audit
from ..db import ro_cursor, rw_conn
from ..rbac import require_view

logger = logging.getLogger(__name__)
router = APIRouter()


class TriageRunBody(BaseModel):
    alert_id: int


@router.post("/agent-runs/triage")
def run_triage(body: TriageRunBody, officer: dict = Depends(require_view)) -> dict:
    with ro_cursor() as cur:
        cur.execute("SELECT alert_id FROM alerts WHERE alert_id = %s", (body.alert_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Alert {body.alert_id} not found")

    settings = Settings.from_env()
    try:
        orchestrator = build_orchestrator(settings)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Agent configuration error: {exc}") from exc

    try:
        result = orchestrator.triage_alert(body.alert_id)
    except SourceRecordNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Agent triage failed for alert %s", body.alert_id)
        raise HTTPException(status_code=503, detail=f"Agent run failed: {type(exc).__name__}: {exc}") from exc

    try:
        with rw_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                insert_audit(cur, officer_id=officer["officer_id"], action="agent_triage",
                             entity_type="alert", entity_id=body.alert_id, alert_id=body.alert_id,
                             details={"run_id": result.get("run_id")})
    except Exception:
        logger.exception("Audit log insert failed for agent_triage on alert %s", body.alert_id)

    return result


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: str, officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    record = store.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    return record


@router.get("/agent-runs/{run_id}/trace")
def get_agent_trace(run_id: str, officer: dict = Depends(require_view)) -> dict:
    settings = Settings.from_env()
    store = SidecarStore(settings.sidecar_db_path)
    trace = store.get_trace(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Agent run not found: {run_id}")
    return trace
