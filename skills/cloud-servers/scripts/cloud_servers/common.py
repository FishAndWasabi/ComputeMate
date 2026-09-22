from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_db() -> Path:
    from .workspace import resolve_db

    return resolve_db()


class Failure(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    def as_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


def envelope(data=None, error: Failure | None = None):
    return {
        "schema_version": 1,
        "ok": error is None,
        "data": data,
        "error": error.as_dict() if error else None,
        "meta": {"observed_at": now()},
    }


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2)
