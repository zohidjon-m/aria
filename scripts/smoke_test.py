from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from compliance_agent.adapters.fake_source import FakeBankSourceRepository
from compliance_agent.adapters.sidecar_store import SidecarStore
from compliance_agent.orchestrator import ComplianceOrchestrator


def main() -> None:
    db_path = os.path.join(tempfile.gettempdir(), "aml_sidecar_smoke.sqlite3")
    if os.path.exists(db_path):
        os.remove(db_path)

    orchestrator = ComplianceOrchestrator(
        source=FakeBankSourceRepository(),
        sidecar=SidecarStore(db_path),
    )

    triage = orchestrator.triage_alert(1001)
    risk = orchestrator.score_customer(501)
    sar = orchestrator.draft_sar(9001)

    print("triage:", triage["result"]["recommendation"], triage["validation"]["status"])
    print("risk:", risk["result"]["details"]["level"], risk["validation"]["status"])
    print("sar:", sar["result"]["recommendation"], sar["validation"]["status"])
    print("sidecar_db:", db_path)


if __name__ == "__main__":
    main()
