from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import ro_cursor

router = APIRouter()


@router.get("/health")
def health() -> dict:
    try:
        with ro_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "healthy", "db": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
