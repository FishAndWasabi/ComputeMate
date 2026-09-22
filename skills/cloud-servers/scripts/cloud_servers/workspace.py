"""Explicit project inventories, discovered without crossing repository boundaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from .common import Failure

DIRECTORY = ".cloud-servers"
CONFIG = "config.json"
DATABASE = "inventory.sqlite3"


def read_config(root: Path) -> dict:
    path = root / DIRECTORY / CONFIG
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise Failure(
            "workspace_not_initialized",
            f"Project is not initialized: {root}. Run cloud-servers init in that project.",
        ) from exc
    except (ValueError, OSError) as exc:
        raise Failure(
            "invalid_workspace", f"Cannot read project configuration: {path}"
        ) from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not all(
            isinstance(value.get(k), str) and value[k].strip() for k in ("id", "name")
        )
    ):
        raise Failure("invalid_workspace", f"Invalid project configuration: {path}")
    return value


def discover(cwd: Path) -> Path | None:
    for root in (cwd, *cwd.parents):
        if (root / DIRECTORY / CONFIG).exists():
            read_config(root)
            return root
        # A nested checkout/worktree must never inherit its parent project's data.
        if (root / ".git").exists():
            break
    return None


def resolve_db(db=None, workspace=None, *, cwd=None, environ=None) -> Path:
    cwd = Path(cwd or Path.cwd()).expanduser().resolve()
    env = os.environ if environ is None else environ
    if db and workspace:
        raise Failure("invalid_argument", "Use either --db or --workspace, not both")
    if db:
        path = Path(db).expanduser()
        return (path if path.is_absolute() else cwd / path).resolve()
    if workspace:
        path = Path(workspace).expanduser()
        root = (path if path.is_absolute() else cwd / path).resolve()
        read_config(root)
        return root / DIRECTORY / DATABASE
    root = discover(cwd)
    if root:
        return root / DIRECTORY / DATABASE
    if env.get("CLOUD_SERVERS_DB"):
        return resolve_db(env["CLOUD_SERVERS_DB"], cwd=cwd, environ={})
    raise Failure(
        "workspace_not_initialized",
        "No project inventory is bound. Run cloud-servers init in the project, or pass --workspace PATH / --db PATH explicitly.",
    )


def describe_db(db) -> dict:
    path = Path(db).expanduser().resolve()
    if path.parent.name == DIRECTORY and path.name == DATABASE:
        root = path.parent.parent
        value = read_config(root)
        return {
            "kind": "project",
            "id": value["id"],
            "name": value["name"],
            "root": str(root),
            "database": str(path),
        }
    return {"kind": "explicit", "name": path.stem, "root": None, "database": str(path)}


def initialize(path=".", name=None) -> dict:
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise Failure("invalid_argument", f"Project directory does not exist: {root}")
    folder = root / DIRECTORY
    folder.mkdir(mode=0o700, exist_ok=True)
    config = folder / CONFIG
    created = not config.exists()
    if created:
        value = {"schema_version": 1, "id": uuid.uuid4().hex, "name": name or root.name}
        if not value["name"].strip():
            raise Failure("invalid_argument", "Project name must not be empty")
        # Exclusive creation preserves an existing binding on repeated init.
        try:
            with config.open("x") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError:
            created = False
    read_config(root)
    ignore = folder / ".gitignore"
    if not ignore.exists():
        try:
            with ignore.open("x") as stream:
                stream.write("inventory.sqlite3*\nbackups/\n")
        except FileExistsError:
            pass
    from .store import Store

    store = Store(folder / DATABASE)
    store.close()
    return {**describe_db(folder / DATABASE), "created": created}
