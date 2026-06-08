from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return to_plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(to_plain(value), sort_keys=True, default=str)


def stable_hash(value: Any) -> str:
    payload = json_dumps(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
