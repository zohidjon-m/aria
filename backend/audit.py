from __future__ import annotations

import json
from typing import Any


def insert_audit(
    cur: Any,
    *,
    officer_id: int,
    action: str,
    entity_type: str,
    entity_id: int | str,
    case_id: int | None = None,
    alert_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO audit_log (
            officer_id, case_id, alert_id, action, entity_type,
            entity_id, details, ip_address, action_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            officer_id,
            case_id,
            alert_id,
            action,
            entity_type,
            str(entity_id),
            json.dumps(details) if details else None,
            ip_address,
        ),
    )
