from __future__ import annotations

import datetime as dt
import json
import re
import shlex
import sqlite3
from dataclasses import dataclass

from . import remote as remote_ops
from .common import Failure, envelope, now
from .store import Store
from .workspace import describe_db
from .transport import SSH, in_environment, require_tool, shell, validate_connection


def field(
    kind="string",
    description="",
    *,
    required=False,
    default=None,
    choices=None,
    positional=False,
):
    return {
        "type": kind,
        "description": description,
        "required": required,
        "default": default,
        "choices": choices,
        "positional": positional,
    }


SERVER = field(description="Registered server ID", required=True, positional=True)
ID = field(description="Record ID", required=True, positional=True)
LIMIT = field("integer", "Maximum number of results", default=100)
OFFSET = field("integer", "Result offset", default=0)
MAX_BYTES = field("integer", "Maximum captured bytes per output stream", default=65536)
TIMEOUT = field("integer", "Connection/command timeout in seconds", default=60)
REGISTRY = {}


def operation(name, description, fields=None, mutating=False):
    def wrap(fn):
        REGISTRY[name] = {
            "name": name,
            "description": description,
            "fields": fields or {},
            "mutating": mutating,
            "handler": fn,
        }
        return fn

    return wrap


def descriptions():
    return [
        {k: v for k, v in spec.items() if k != "handler"} for spec in REGISTRY.values()
    ]


def check_strings(value):
    if isinstance(value, str) and "\x00" in value:
        raise Failure("invalid_argument", "NUL bytes are not allowed")
    if isinstance(value, dict):
        for k, v in value.items():
            check_strings(k)
            check_strings(v)
    if isinstance(value, list):
        for v in value:
            check_strings(v)


def validate_args(spec, arguments):
    if not isinstance(arguments, dict):
        raise Failure("invalid_argument", "Arguments must be an object")
    unknown = set(arguments) - set(spec["fields"])
    if unknown:
        raise Failure(
            "invalid_argument", f"Unknown arguments: {', '.join(sorted(unknown))}"
        )
    output = {}
    for name, f in spec["fields"].items():
        value = arguments.get(name, f["default"])
        if value is None:
            if f["required"]:
                raise Failure("invalid_argument", f"Missing argument: {name}")
            output[name] = None
            continue
        expected = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
        }[f["type"]]
        if type(value) is not expected:
            raise Failure("invalid_argument", f"{name} must be {f['type']}")
        if f["required"] and value == "":
            raise Failure("invalid_argument", f"{name} cannot be empty")
        if f["choices"] and value not in f["choices"]:
            raise Failure("invalid_argument", f"{name} must be one of {f['choices']}")
        if f["type"] == "integer" and value < (
            0
            if name == "offset"
            or name.startswith("min_")
            or name == "max_gpu_utilization"
            else 1
        ):
            raise Failure("invalid_argument", f"{name} is out of range")
        if (
            name in {"limit", "lines"}
            and value > 10000
            or name == "max_bytes"
            and value > 4 * 1024 * 1024
            or name == "timeout"
            and value > 86400
        ):
            raise Failure("invalid_argument", f"{name} exceeds the supported limit")
        check_strings(value)
        output[name] = value
    return output


@dataclass
class Context:
    store: Store

    def ssh(self, server):
        return SSH(self.store.get("server", server))

    def environment(self, server, environment):
        if not environment:
            return None
        record = self.store.get("environment", environment)
        if record["server"] != server:
            raise Failure(
                "invalid_argument", "Environment belongs to a different server"
            )
        return record

    def command(self, server, argv=None, script=None, cwd=None, environment=None):
        if bool(argv) == bool(script):
            raise Failure("invalid_argument", "Supply exactly one of argv or script")
        if argv and (not all(isinstance(x, str) for x in argv) or not argv[0]):
            raise Failure(
                "invalid_argument", "argv must be a non-empty array of strings"
            )
        return in_environment(
            shell(argv) if argv else script, self.environment(server, environment), cwd
        )

    def native(self, server, value):
        identifier = server + ":" + value["backend"] + ":" + value["native_id"]
        try:
            old = self.store.get("native", identifier, include_archived=True)
        except Failure:
            old = None
        return self.store.put(
            "native",
            {"server": server, **value},
            identifier=identifier,
            update=bool(old),
        )


def invoke(db, name, arguments=None):
    store = None
    try:
        spec = REGISTRY.get(name)
        if spec is None:
            raise Failure("unknown_operation", f"Unknown operation: {name}")
        args = validate_args(spec, arguments or {})
        if name == "operations":
            return envelope(spec["handler"](None, **args))
        scope = describe_db(db)
        store = Store(db)
        result = envelope(spec["handler"](Context(store), **args))
        result["meta"]["scope"] = scope
        return result
    except Failure as exc:
        return envelope(error=exc)
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        return envelope(error=Failure("operation_failed", str(exc)))
    finally:
        if store:
            store.close()


SCHEMAS = {
    "group": {"name": str, "description": str, "labels": list},
    "server": {
        "name": str,
        "ssh": dict,
        "groups": list,
        "labels": list,
        "purpose": str,
        "role": str,
        "notes": str,
        "metadata": dict,
    },
    "environment": {
        "name": str,
        "server": str,
        "type": str,
        "selector": str,
        "conda_executable": str,
        "notes": str,
        "metadata": dict,
    },
    "project": {
        "name": str,
        "repo_url": str,
        "local_path": str,
        "placements": list,
        "notes": str,
        "metadata": dict,
    },
    "artifact": {
        "name": str,
        "server": str,
        "project": str,
        "path": str,
        "type": str,
        "native_ref": dict,
        "notes": str,
        "metadata": dict,
    },
}
REQUIRED = {
    "group": {"name"},
    "server": {"name", "ssh"},
    "environment": {"name", "server", "type"},
    "project": {"name"},
    "artifact": {"name", "server", "path", "type"},
}


def validate_entity(kind, data, store, lookup=None):
    if not isinstance(data, dict):
        raise Failure("invalid_argument", "data must be an object")
    check_strings(data)
    data = {
        k: v
        for k, v in data.items()
        if k not in {"id", "revision", "archived", "updated_at"}
    }
    for key, value in data.items():
        if key not in SCHEMAS[kind] or type(value) is not SCHEMAS[kind][key]:
            raise Failure("invalid_argument", f"Invalid {kind} field: {key}")
    for key in REQUIRED[kind]:
        if key not in data or data[key] in ("", None):
            raise Failure("invalid_argument", f"Missing {kind}.{key}")
    lookup = lookup or (lambda k, i: store.get(k, i))
    for key in ("labels", "groups"):
        if key in data and not all(isinstance(v, str) for v in data[key]):
            raise Failure("invalid_argument", f"{key} must contain strings")
    if kind == "server":
        validate_connection(data["ssh"])
        if data.get("role", "compute") not in {"compute", "login", "general"}:
            raise Failure("invalid_argument", "role must be compute, login or general")
        for group in data.get("groups", []):
            lookup("group", group)
    if kind in {"environment", "artifact"}:
        lookup("server", data["server"])
    if kind == "environment":
        if "conda_executable" in data and (
            data["type"] != "conda" or not data["conda_executable"].startswith("/")
        ):
            raise Failure(
                "invalid_argument", "conda_executable requires a Conda environment and an absolute remote path"
            )
        if data["type"] not in {"system", "conda", "venv", "docker"}:
            raise Failure(
                "invalid_argument",
                "Environment type must be system, conda, venv or docker",
            )
        if data["type"] != "system" and not data.get("selector"):
            raise Failure("invalid_argument", "This environment requires a selector")
        if data["type"] == "venv" and not data["selector"].startswith("/"):
            raise Failure(
                "invalid_argument", "venv selector must be an absolute remote path"
            )
    if kind == "artifact" and data.get("project"):
        lookup("project", data["project"])
    if kind == "project":
        for p in data.get("placements", []):
            if (
                not isinstance(p, dict)
                or not isinstance(p.get("server"), str)
                or not isinstance(p.get("path"), str)
            ):
                raise Failure("invalid_argument", "placements require server and path")
            if set(p) - {"server", "path", "environment"}:
                raise Failure("invalid_argument", "Unknown placement fields")
            lookup("server", p["server"])
            if p.get("environment"):
                env = lookup("environment", p["environment"])
                if env["server"] != p["server"]:
                    raise Failure(
                        "invalid_argument",
                        "Placement environment belongs to another server",
                    )
    return data


def register_entities():
    for kind in SCHEMAS:

        def add(ctx, data, id=None, _kind=kind):
            if id and not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", id):
                raise Failure(
                    "invalid_argument",
                    "IDs use letters, numbers, dots, hyphens and underscores",
                )
            return ctx.store.put(
                _kind, validate_entity(_kind, data, ctx.store), identifier=id
            )

        operation(
            f"{kind}.add",
            f"Register {kind}",
            {
                "data": field("object", f"{kind} fields", required=True),
                "id": field(description="Optional stable ID"),
            },
            True,
        )(add)

        def update(ctx, id, data, revision=None, _kind=kind):
            old = ctx.store.get(_kind, id)
            merged = validate_entity(
                _kind,
                {**old, **data},
                ctx.store,
                lookup=lambda k, i: ctx.store.get(k, i, include_archived=True),
            )
            return ctx.store.put(
                _kind,
                merged,
                identifier=id,
                update=True,
                revision=revision if revision is not None else old["revision"],
            )

        operation(
            f"{kind}.update",
            f"Update {kind}; merges top-level fields",
            {
                "id": ID,
                "data": field("object", required=True),
                "revision": field("integer", "Expected revision"),
            },
            True,
        )(update)

        def get(ctx, id, _kind=kind):
            return ctx.store.get(_kind, id, include_archived=True)

        operation(f"{kind}.get", f"Read {kind}", {"id": ID})(get)

        def remove(ctx, id, revision=None, _kind=kind):
            return ctx.store.archive(_kind, id, revision)

        operation(
            f"{kind}.remove",
            f"Archive {kind}; preserves remote files and related records",
            {"id": ID, "revision": field("integer", "Expected revision")},
            True,
        )(remove)

        def listing(
            ctx,
            query="",
            server=None,
            group=None,
            archived=False,
            limit=100,
            offset=0,
            _kind=kind,
        ):
            return ctx.store.list(
                _kind,
                query=query,
                server=server,
                group=group,
                archived=archived,
                limit=limit,
                offset=offset,
            )

        operation(
            f"{kind}.list",
            f"List and filter {kind} records",
            {
                "query": field(default=""),
                "server": field(),
                "group": field(),
                "archived": field("boolean", default=False),
                "limit": LIMIT,
                "offset": OFFSET,
            },
        )(listing)


register_entities()


@operation(
    "operations", "Describe every public operation, arguments and entity schemas"
)
def operations(ctx):
    return {
        "operations": descriptions(),
        "entities": {
            kind: {
                "fields": {k: t.__name__ for k, t in fields.items()},
                "required": sorted(REQUIRED[kind]),
            }
            for kind, fields in SCHEMAS.items()
        },
    }


@operation("scope", "Show the bound project and inventory path")
def scope(ctx):
    return describe_db(ctx.store.path)


@operation(
    "probe",
    "Refresh host hardware and capabilities, plus available Slurm resources",
    {"server": SERVER},
)
def probe(ctx, server):
    ssh = ctx.ssh(server)
    try:
        data = remote_ops.probe(ssh)
        ctx.store.observe(server, "hardware", data)
        if "sinfo" in data["capabilities"]:
            try:
                ctx.store.observe(server, "slurm", remote_ops.slurm_resources(ssh))
            except Failure as exc:
                ctx.store.observe(server, "slurm", error=exc.as_dict())
    except Failure as exc:
        ctx.store.observe(server, "hardware", error=exc.as_dict())
        return {
            "server": server,
            "reachable": False,
            "observations": observations(ctx, server),
        }
    return {
        "server": server,
        "reachable": True,
        "observations": observations(ctx, server),
    }


def observations(ctx, server):
    values = ctx.store.observations(server)
    for value in values.values():
        if value["observed_at"]:
            age = (
                dt.datetime.now(dt.timezone.utc)
                - dt.datetime.fromisoformat(value["observed_at"])
            ).total_seconds()
            value["age_seconds"] = round(age)
            value["stale"] = value["stale"] or age > 300
    return values


@operation(
    "snapshot",
    "Unified inventory snapshot; refresh is explicit",
    {
        "server": field(),
        "refresh": field("boolean", default=False),
        "limit": LIMIT,
        "offset": OFFSET,
    },
)
def snapshot(ctx, server=None, refresh=False, limit=100, offset=0):
    servers = (
        [ctx.store.get("server", server)]
        if server
        else ctx.store.list("server", limit=limit, offset=offset)["items"]
    )
    if refresh:
        for s in servers:
            probe(ctx, s["id"])
    return {
        "workspace": describe_db(ctx.store.path),
        "servers": [{**s, "observations": observations(ctx, s["id"])} for s in servers],
        "groups": ctx.store.list("group", limit=limit)["items"],
        "environments": ctx.store.list("environment", server=server, limit=limit)[
            "items"
        ],
        "projects": ctx.store.list("project", server=server, limit=limit)["items"],
        "artifacts": ctx.store.list("artifact", server=server, limit=limit)["items"],
        "native_refs": ctx.store.list("native", server=server, limit=limit)["items"],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "server_total": ctx.store.list("server", limit=1)["total"],
        },
    }


@operation(
    "capabilities",
    "Inspect remote tools",
    {"server": SERVER, "refresh": field("boolean", default=False)},
)
def capabilities(ctx, server, refresh=False):
    ctx.store.get("server", server)
    if refresh:
        probe(ctx, server)
    sample = observations(ctx, server).get("hardware")
    return {
        "server": server,
        "tools": sample["data"].get("capabilities", [])
        if sample and sample["data"]
        else [],
        "observation": sample,
    }


@operation(
    "server.select",
    "Filter fresh SSH host snapshots; Slurm allocation is queried separately",
    {
        "group": field(),
        "label": field(),
        "min_gpus": field("integer"),
        "min_gpu_memory_mib": field("integer"),
        "min_memory_gib": field("integer"),
        "max_gpu_utilization": field("integer", default=10),
        "include_stale": field("boolean", default=False),
        "limit": LIMIT,
    },
)
def select(
    ctx,
    group=None,
    label=None,
    min_gpus=None,
    min_gpu_memory_mib=None,
    min_memory_gib=None,
    max_gpu_utilization=10,
    include_stale=False,
    limit=100,
):
    matches = []
    for s in ctx.store.list("server", group=group, limit=10000)["items"]:
        if s.get("role") == "login" or label and label not in s.get("labels", []):
            continue
        sample = observations(ctx, s["id"]).get("hardware")
        if (
            not sample
            or not sample["data"]
            or sample["error"]
            or sample["stale"]
            and not include_stale
        ):
            continue
        data = sample["data"]
        free = [
            g
            for g in data["gpus"]
            if g["utilization_percent"] is not None
            and g["utilization_percent"] <= max_gpu_utilization
            and (
                min_gpu_memory_mib is None
                or g["memory_total_mib"] is not None
                and g["memory_used_mib"] is not None
                and g["memory_total_mib"] - g["memory_used_mib"] >= min_gpu_memory_mib
            )
        ]
        required_gpus = (
            min_gpus if min_gpus is not None else (1 if min_gpu_memory_mib else 0)
        )
        if len(free) < required_gpus:
            continue
        available = data["memory"].get("MemAvailable", 0)
        if min_memory_gib and available < min_memory_gib * 1024**3:
            continue
        matches.append(
            {
                "server": s,
                "eligible_gpus": free,
                "available_memory_bytes": available,
                "observation": sample,
            }
        )
    return {
        "items": matches[:limit],
        "total": len(matches),
        "allocation": "observational_only",
    }


@operation(
    "environment.discover",
    "Discover Conda, Docker, CUDA and explicitly supplied venv paths",
    {"server": SERVER, "paths": field("array", default=[])},
)
def environment_discover(ctx, server, paths):
    if not all(isinstance(p, str) for p in paths):
        raise Failure("invalid_argument", "paths must contain strings")
    try:
        result = remote_ops.discover_environments(ctx.ssh(server), paths)
        return ctx.store.observe(server, "environments", result)
    except Failure as exc:
        ctx.store.observe(server, "environments", error=exc.as_dict())
        raise


COMMAND_FIELDS = {
    "server": SERVER,
    "argv": field("array", "Argument vector; alternative to script"),
    "script": field(description="Explicit Bash script"),
    "cwd": field(description="Remote working directory"),
    "environment": field(description="Registered environment ID"),
}


@operation(
    "exec",
    "Execute a foreground SSH command; never automatically retried",
    {**COMMAND_FIELDS, "timeout": TIMEOUT, "max_bytes": MAX_BYTES},
    True,
)
def execute(
    ctx,
    server,
    argv=None,
    script=None,
    cwd=None,
    environment=None,
    timeout=60,
    max_bytes=65536,
):
    result = ctx.ssh(server).run(
        ctx.command(server, argv, script, cwd, environment),
        timeout=timeout,
        limit=max_bytes,
        mutating=True,
        check=False,
    )
    if result["exit_code"]:
        raise Failure("command_failed", "Remote command exited unsuccessfully", result)
    return result


@operation(
    "project.status",
    "Query Git status at a registered project placement",
    {"id": ID, "server": field(required=True)},
)
def project_status(ctx, id, server):
    project = ctx.store.get("project", id)
    placement = next(
        (p for p in project.get("placements", []) if p["server"] == server), None
    )
    if not placement:
        raise Failure("not_found", "Project has no placement on this server")
    result = ctx.ssh(server).run(
        require_tool("git")
        + shell(["git", "-C", placement["path"], "status", "--short", "--branch"])
    )
    return {"project": id, "server": server, "path": placement["path"], **result}


@operation(
    "fs.list",
    "Browse one remote directory",
    {"server": SERVER, "path": field(required=True), "limit": LIMIT, "offset": OFFSET},
)
def fs_list(ctx, server, path, limit, offset):
    return remote_ops.fs_list(ctx.ssh(server), path, limit, offset)


@operation(
    "fs.read",
    "Read a bounded line range and content hash",
    {
        "server": SERVER,
        "path": field(required=True),
        "start": field("integer", default=1),
        "end": field("integer", default=200),
        "max_bytes": MAX_BYTES,
    },
)
def fs_read(ctx, server, path, start, end, max_bytes):
    if end < start:
        raise Failure("invalid_argument", "end must be >= start")
    if end - start + 1 > 10000:
        raise Failure("invalid_argument", "Read at most 10000 lines at a time")
    return remote_ops.fs_read(ctx.ssh(server), path, start, end, max_bytes)


@operation(
    "fs.search",
    "Search remote code with bounded output",
    {
        "server": SERVER,
        "path": field(required=True),
        "pattern": field(required=True),
        "limit": LIMIT,
        "max_bytes": MAX_BYTES,
    },
)
def fs_search(ctx, server, path, pattern, limit, max_bytes):
    return remote_ops.fs_search(ctx.ssh(server), path, pattern, limit, max_bytes)


@operation(
    "fs.patch",
    "Apply a contextual Git patch with optional revision/hash preconditions",
    {
        "server": SERVER,
        "cwd": field(required=True),
        "patch": field(required=True),
        "expected_revision": field(),
        "expected_hashes": field("object"),
    },
    True,
)
def fs_patch(ctx, server, cwd, patch, expected_revision=None, expected_hashes=None):
    return remote_ops.fs_patch(
        ctx.ssh(server), cwd, patch, expected_revision, expected_hashes
    )


@operation(
    "sync",
    "Preview or apply one-way rsync; never deletes destination extras by default",
    {
        "server": SERVER,
        "local": field(required=True),
        "remote": field(required=True),
        "direction": field(required=True, choices=["push", "pull"]),
        "apply": field("boolean", default=False),
        "delete": field("boolean", default=False),
        "exclude": field("array", default=[]),
        "timeout": field("integer", default=300),
    },
    True,
)
def sync(
    ctx,
    server,
    local,
    remote,
    direction,
    apply=False,
    delete=False,
    exclude=None,
    timeout=300,
):
    if not all(isinstance(x, str) for x in exclude or []):
        raise Failure("invalid_argument", "exclude must contain strings")
    return remote_ops.sync(
        ctx.ssh(server), local, remote, direction, apply, delete, exclude, timeout
    )


@operation(
    "transfer.get",
    "Download a remote file or directory",
    {
        "server": SERVER,
        "path": field(required=True),
        "local": field(required=True),
        "timeout": field("integer", default=300),
    },
    True,
)
def transfer_get(ctx, server, path, local, timeout=300):
    return remote_ops.sync(
        ctx.ssh(server), local, path, "pull", apply=True, timeout=timeout
    )


@operation(
    "transfer.put",
    "Upload a local file or directory",
    {
        "server": SERVER,
        "local": field(required=True),
        "path": field(required=True),
        "timeout": field("integer", default=300),
    },
    True,
)
def transfer_put(ctx, server, local, path, timeout=300):
    return remote_ops.sync(
        ctx.ssh(server), local, path, "push", apply=True, timeout=timeout
    )


@operation(
    "artifact.fetch",
    "Download a registered artifact",
    {"id": ID, "local": field(required=True)},
    True,
)
def artifact_fetch(ctx, id, local):
    artifact = ctx.store.get("artifact", id)
    return transfer_get(ctx, artifact["server"], artifact["path"], local)


@operation(
    "tmux.start",
    "Start a native tmux session with a persistent log file",
    {**COMMAND_FIELDS, "name": field(), "log_path": field()},
    True,
)
def tmux_start(
    ctx,
    server,
    argv=None,
    script=None,
    cwd=None,
    environment=None,
    name=None,
    log_path=None,
):
    env = ctx.environment(server, environment)
    host_cwd = None if env and env["type"] == "docker" else cwd
    result = remote_ops.tmux_start(
        ctx.ssh(server),
        ctx.command(server, argv, script, cwd, environment),
        name,
        host_cwd,
        log_path,
    )
    try:
        ctx.native(server, result)
    except (Failure, sqlite3.Error, OSError) as exc:
        result["registration_error"] = str(exc)
    return result


@operation(
    "tmux.list",
    "List native tmux panes and native exit information",
    {"server": SERVER},
)
def tmux_list(ctx, server):
    return remote_ops.tmux_list(ctx.ssh(server))


@operation(
    "tmux.show",
    "Read a native tmux session",
    {"server": SERVER, "name": field(required=True)},
)
def tmux_show(ctx, server, name):
    return remote_ops.tmux_list(ctx.ssh(server), name)


@operation(
    "tmux.logs",
    "Read registered logs or capture an existing native pane",
    {
        "server": SERVER,
        "name": field(required=True),
        "path": field(),
        "lines": field("integer", default=200),
        "max_bytes": MAX_BYTES,
    },
)
def tmux_logs(ctx, server, name, path=None, lines=200, max_bytes=65536):
    remote_ops.validate_session(name)
    if not path:
        try:
            path = ctx.store.get("native", server + ":tmux:" + name).get("log_path")
        except Failure:
            pass
    cmd = (
        shell(["tail", "-n", str(lines)]) + " < " + shlex.quote(path)
        if path
        else require_tool("tmux")
        + shell(
            [
                "tmux",
                "capture-pane",
                "-p",
                "-t",
                "=" + name + ":",
                "-S",
                "-" + str(lines),
            ]
        )
    )
    return {"path": path, **ctx.ssh(server).run(cmd, limit=max_bytes)}


@operation(
    "tmux.stop",
    "End the specified native tmux session (kill-session semantics)",
    {"server": SERVER, "name": field(required=True)},
    True,
)
def tmux_stop(ctx, server, name):
    remote_ops.validate_session(name)
    return ctx.ssh(server).run(
        require_tool("tmux") + shell(["tmux", "kill-session", "-t", "=" + name]),
        mutating=True,
    )


@operation(
    "slurm.submit",
    "Submit the Agent's batch script and return the native Job ID",
    {
        "server": SERVER,
        "script": field(required=True),
        "options": field("object", default={}),
        "cwd": field(),
    },
    True,
)
def slurm_submit(ctx, server, script, options, cwd=None):
    result = remote_ops.slurm_submit(ctx.ssh(server), script, options, cwd)
    try:
        ctx.native(server, result)
    except (Failure, sqlite3.Error, OSError) as exc:
        result["registration_error"] = str(exc)
    return result


@operation(
    "slurm.list",
    "Query squeue using native Slurm states",
    {"server": SERVER, "user": field(), "limit": LIMIT},
)
def slurm_list(ctx, server, user=None, limit=100):
    return remote_ops.slurm_list(ctx.ssh(server), user, limit)


@operation(
    "slurm.resources",
    "Query Slurm compute nodes and partitions, separately from login hardware",
    {"server": SERVER},
)
def slurm_resources(ctx, server):
    try:
        value = remote_ops.slurm_resources(ctx.ssh(server))
        ctx.store.observe(server, "slurm", value)
        return value
    except Failure as exc:
        ctx.store.observe(server, "slurm", error=exc.as_dict())
        raise


@operation(
    "slurm.show",
    "Query scontrol and sacct; missing accounting remains unknown",
    {"server": SERVER, "job": field(required=True)},
)
def slurm_show(ctx, server, job):
    return remote_ops.slurm_show(ctx.ssh(server), job)


@operation(
    "slurm.logs",
    "Tail a Slurm stdout/stderr file or an explicit path",
    {
        "server": SERVER,
        "job": field(required=True),
        "stream": field(default="stdout", choices=["stdout", "stderr"]),
        "path": field(),
        "lines": field("integer", default=200),
        "max_bytes": MAX_BYTES,
    },
)
def slurm_logs(
    ctx, server, job, stream="stdout", path=None, lines=200, max_bytes=65536
):
    ssh = ctx.ssh(server)
    remote_ops.validate_job(job)
    path = path or remote_ops.slurm_log_path(ssh, job, stream)
    return {
        "path": path,
        **ssh.run(
            shell(["tail", "-n", str(lines)]) + " < " + shlex.quote(path),
            limit=max_bytes,
        ),
    }


@operation(
    "slurm.cancel",
    "Cancel a native Slurm job",
    {"server": SERVER, "job": field(required=True)},
    True,
)
def slurm_cancel(ctx, server, job):
    remote_ops.validate_job(job)
    return ctx.ssh(server).run(
        require_tool("scancel") + shell(["scancel", job]), mutating=True
    )


@operation(
    "inventory.export",
    "Export manual inventory, excluding runtime observations and native handles",
)
def inventory_export(ctx):
    return ctx.store.export()


@operation(
    "inventory.import",
    "Validate and transactionally import an inventory export",
    {
        "document": field("object", required=True),
        "overwrite": field("boolean", default=False),
    },
    True,
)
def inventory_import(ctx, document, overwrite=False):
    if document.get("ok") is True and isinstance(document.get("data"), dict):
        document = document["data"]
    if document.get("schema_version") != 1 or not isinstance(
        document.get("entities"), dict
    ):
        raise Failure(
            "invalid_argument",
            "Expected an inventory document with schema_version 1 and entities",
        )
    prepared = {}
    for kind, records in document["entities"].items():
        if kind not in SCHEMAS or not isinstance(records, list):
            raise Failure("invalid_argument", f"Invalid entity collection: {kind}")
        for record in records:
            if (
                not isinstance(record, dict)
                or not isinstance(record.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", record["id"])
            ):
                raise Failure(
                    "invalid_argument", "Every imported record needs a valid ID"
                )
            key = (kind, record["id"])
            if key in prepared:
                raise Failure("conflict", "Duplicate imported ID")
            prepared[key] = record

    def lookup(kind, identifier):
        return prepared.get((kind, identifier)) or ctx.store.get(
            kind, identifier, include_archived=True
        )

    validated = {
        key: validate_entity(key[0], record, ctx.store, lookup)
        for key, record in prepared.items()
    }
    try:
        ctx.store.db.execute("BEGIN IMMEDIATE")
        for (kind, identifier), data in validated.items():
            old = ctx.store.db.execute(
                "SELECT revision FROM entities WHERE kind=? AND id=?",
                (kind, identifier),
            ).fetchone()
            if old and not overwrite:
                raise Failure(
                    "conflict",
                    f"{kind} {identifier} already exists; use overwrite explicitly",
                )
            archived = int(bool(prepared[(kind, identifier)].get("archived", False)))
            ctx.store.db.execute(
                """INSERT INTO entities VALUES (?,?,?,?,?,?) ON CONFLICT(kind,id)
                DO UPDATE SET data=excluded.data,revision=entities.revision+1,archived=excluded.archived,updated_at=excluded.updated_at""",
                (kind, identifier, json.dumps(data), 1, archived, now()),
            )
        ctx.store.db.commit()
    except Exception:
        ctx.store.db.rollback()
        raise
    return {"imported": len(validated)}
