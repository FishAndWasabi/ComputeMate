from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from .common import Failure, now

KINDS = {"group", "server", "environment", "project", "artifact", "native"}


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=15)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("PRAGMA user_version").fetchone()[0] > 1:
            self.db.close()
            raise Failure(
                "unsupported_schema",
                "This inventory was created by a newer tool version",
            )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
              kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
              revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS observations (
              server_id TEXT NOT NULL, topic TEXT NOT NULL, data TEXT,
              observed_at TEXT, last_attempt TEXT NOT NULL, error TEXT,
              PRIMARY KEY(server_id,topic));
            PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    @staticmethod
    def decode(row):
        return {
            **json.loads(row["data"]),
            "id": row["id"],
            "revision": row["revision"],
            "archived": bool(row["archived"]),
            "updated_at": row["updated_at"],
        }

    def get(self, kind, identifier, include_archived=False):
        row = self.db.execute(
            "SELECT * FROM entities WHERE kind=? AND id=?", (kind, identifier)
        ).fetchone()
        if not row or (row["archived"] and not include_archived):
            raise Failure("not_found", f"{kind} {identifier!r} was not found")
        return self.decode(row)

    def list(
        self,
        kind,
        *,
        archived=False,
        query="",
        server=None,
        group=None,
        limit=100,
        offset=0,
    ):
        rows = self.db.execute(
            "SELECT * FROM entities WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()
        values = [self.decode(r) for r in rows if archived or not r["archived"]]
        if query:
            values = [
                v
                for v in values
                if query.lower() in json.dumps(v, ensure_ascii=False).lower()
            ]
        if server:
            values = [
                v
                for v in values
                if v.get("server") == server
                or any(p.get("server") == server for p in v.get("placements", []))
            ]
        if group:
            values = [v for v in values if group in v.get("groups", [])]
        return {
            "items": values[offset : offset + limit],
            "total": len(values),
            "offset": offset,
            "limit": limit,
        }

    def put(self, kind, data, *, identifier=None, update=False, revision=None):
        identifier = identifier or data.get("id") or f"{kind}-{uuid.uuid4().hex[:10]}"
        data = {
            k: v
            for k, v in data.items()
            if k not in {"id", "revision", "archived", "updated_at"}
        }
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT * FROM entities WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
            if update:
                if not row:
                    raise Failure("not_found", f"{kind} {identifier!r} was not found")
                if revision is not None and row["revision"] != revision:
                    raise Failure(
                        "conflict",
                        "Record changed; read its current revision and retry",
                        {"current_revision": row["revision"]},
                    )
                data = {**json.loads(row["data"]), **data}
                self.db.execute(
                    "UPDATE entities SET data=?,revision=revision+1,updated_at=? WHERE kind=? AND id=?",
                    (json.dumps(data), now(), kind, identifier),
                )
            else:
                if row:
                    raise Failure("conflict", f"{kind} {identifier!r} already exists")
                self.db.execute(
                    "INSERT INTO entities(kind,id,data,updated_at) VALUES (?,?,?,?)",
                    (kind, identifier, json.dumps(data), now()),
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get(kind, identifier, include_archived=True)

    def archive(self, kind, identifier, revision=None):
        with self.db:
            sql = "UPDATE entities SET archived=1,revision=revision+1,updated_at=? WHERE kind=? AND id=?"
            args = [now(), kind, identifier]
            if revision is not None:
                sql += " AND revision=?"
                args.append(revision)
            if self.db.execute(sql, args).rowcount != 1:
                raise Failure("conflict", "Record missing or revision changed")
        return self.get(kind, identifier, include_archived=True)

    def observe(self, server, topic, data=None, error=None):
        timestamp = now()
        with self.db:
            if error is None:
                self.db.execute(
                    """INSERT INTO observations VALUES (?,?,?,?,?,NULL)
                    ON CONFLICT(server_id,topic) DO UPDATE SET data=excluded.data,
                    observed_at=excluded.observed_at,last_attempt=excluded.last_attempt,error=NULL""",
                    (server, topic, json.dumps(data), timestamp, timestamp),
                )
            else:
                self.db.execute(
                    """INSERT INTO observations VALUES (?,?,NULL,NULL,?,?)
                    ON CONFLICT(server_id,topic) DO UPDATE SET last_attempt=excluded.last_attempt,error=excluded.error""",
                    (server, topic, timestamp, json.dumps(error)),
                )
        return self.observations(server).get(topic)

    def observations(self, server):
        return {
            r["topic"]: {
                "data": json.loads(r["data"]) if r["data"] else None,
                "source": "ssh",
                "observed_at": r["observed_at"],
                "last_attempt": r["last_attempt"],
                "error": json.loads(r["error"]) if r["error"] else None,
                "stale": bool(r["error"]),
            }
            for r in self.db.execute(
                "SELECT * FROM observations WHERE server_id=?", (server,)
            )
        }

    def export(self):
        return {
            "schema_version": 1,
            "entities": {
                kind: self.list(kind, archived=True, limit=1_000_000)["items"]
                for kind in sorted(KINDS)
                if kind != "native"
            },
        }
