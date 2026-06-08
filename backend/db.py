from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compliance_agent.config import Settings


def _get_dsn() -> str:
    s = Settings.from_env()
    if not s.bank_source_dsn:
        raise RuntimeError(
            "BANK_SOURCE_DSN is not configured. "
            "Set it in .env or set DEMO_MODE=true to use the in-memory source."
        )
    return s.bank_source_dsn


@contextmanager
def ro_cursor() -> Iterator[psycopg2.extras.RealDictCursor]:
    conn = psycopg2.connect(_get_dsn())
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


@contextmanager
def rw_conn() -> Iterator[Any]:
    conn = psycopg2.connect(_get_dsn())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
