from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
import os
import logging

# Ensure project root is on sys.path when running from a subdirectory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.routes import chat, customers, alerts, cases
from backend.agent import ARIAAgent
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AML Compliance Intelligence Platform")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
app.state.agent = ARIAAgent()

# Mount routes
app.include_router(chat.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(cases.router, prefix="/api")

@app.get("/")
def read_root():
    return {"status": "AML Backend is running"}

@app.get("/health")
def health_check():
    from mcp_server.db import query
    try:
        query("SELECT 1")
        return {"db": "ok", "status": "healthy"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        from fastapi import Response
        return Response(
            content='{"db": "error", "status": "unhealthy"}',
            status_code=503,
            media_type="application/json",
        )
