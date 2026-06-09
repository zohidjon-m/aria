from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import health, officers, alerts, customers, cases, audit_log, agent_runs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

app = FastAPI(title="AML Officer Workbench API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(officers.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(audit_log.router, prefix="/api")
app.include_router(agent_runs.router, prefix="/api")
