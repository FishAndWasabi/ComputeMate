from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .api import REGISTRY, invoke
from .common import Failure, envelope, json_text
from .workspace import initialize, resolve_db


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Failure("invalid_argument", message)


def show(data):
    if isinstance(data, dict) and "stdout" in data:
        print(data["stdout"], end="" if data["stdout"].endswith("\n") else "\n")
        if data.get("stderr"):
            print(data["stderr"], file=sys.stderr, end="\n")
        if data.get("truncated"):
            print(
                "Output truncated; increase --max-bytes or read a narrower range.",
                file=sys.stderr,
            )
        return
    rows = data.get("items") if isinstance(data, dict) else None
    if rows is None and isinstance(data, dict) and "servers" in data:
        rows = [
            {
                "id": s["id"],
                "name": s["name"],
                "role": s.get("role", "general"),
                "status": "unobserved"
                if not s.get("observations", {}).get("hardware")
                else "stale"
                if s["observations"]["hardware"]["stale"]
                else "observed",
                "groups": ",".join(s.get("groups", [])),
            }
            for s in data["servers"]
        ]
    if rows is not None and all(isinstance(row, dict) for row in rows):
        if not rows:
            print("No results.")
            return
        preferred = [
            "id",
            "name",
            "server",
            "role",
            "type",
            "session",
            "job_id",
            "state",
            "status",
            "path",
            "groups",
            "revision",
        ]
        columns = [
            c
            for c in preferred
            if any(c in r and not isinstance(r[c], (dict, list)) for r in rows)
        ]
        columns = columns or list(rows[0])[:6]
        display = [
            [str(r.get(c, ""))[:90].replace("\n", " ") for c in columns] for r in rows
        ]
        widths = [
            max(len(c), *(len(row[i]) for row in display))
            for i, c in enumerate(columns)
        ]
        print("  ".join(c.upper().ljust(widths[i]) for i, c in enumerate(columns)))
        print("  ".join("─" * n for n in widths))
        for row in display:
            print("  ".join(v.ljust(widths[i]) for i, v in enumerate(row)))
        if "total" in data:
            print(f"\n{len(rows)} of {data['total']} results")
        return
    print(json_text(data))


def build_parser():
    parser = Parser(
        description="ComputeMate: portable Skill, local inventory and native SSH helpers",
        epilog="Global options: --json (structured output), --workspace PATH (project), --db PATH (explicit inventory), --watch SECONDS (read-only polling). Place them before the '--' argument-vector separator.",
    )
    subs = parser.add_subparsers(dest="operation", required=True)
    groups = {}
    for name, spec in REGISTRY.items():
        parts = name.split(".")
        if len(parts) == 2:
            if parts[0] not in groups:
                group = subs.add_parser(parts[0], help=f"{parts[0]} operations")
                groups[parts[0]] = group.add_subparsers(
                    dest="suboperation", required=True
                )
            command = groups[parts[0]].add_parser(
                parts[1], help=spec["description"], description=spec["description"]
            )
        else:
            command = subs.add_parser(
                name, help=spec["description"], description=spec["description"]
            )
        command.set_defaults(action=name)
        for key, f in spec["fields"].items():
            kwargs = {"help": f["description"]}
            argname = key if f["positional"] else "--" + key.replace("_", "-")
            if not f["positional"]:
                kwargs["dest"] = key
            if f["type"] == "boolean":
                kwargs["action"] = argparse.BooleanOptionalAction
            elif f["type"] == "integer":
                kwargs["type"] = int
            elif f["type"] in {"object", "array"}:
                kwargs["type"] = json.loads
            if f["choices"]:
                kwargs["choices"] = f["choices"]
            if not f["positional"]:
                kwargs["default"] = argparse.SUPPRESS
            command.add_argument(argname, **kwargs)
            if f["type"] in {"string", "object", "array"} and key in {
                "script",
                "patch",
                "data",
                "document",
                "argv",
                "expected_hashes",
            }:
                command.add_argument(
                    "--" + key.replace("_", "-") + "-file",
                    dest=key + "_file",
                    help=f"Read {key} from a UTF-8 file; '-' reads stdin",
                )
    init = subs.add_parser("init", help="Bind a project to its own inventory")
    init.add_argument("path", nargs="?", default=None)
    init.add_argument("--name")
    init.set_defaults(action="init")
    rpc = subs.add_parser(
        "rpc", help="Read one {operation, arguments} JSON request from stdin"
    )
    rpc.set_defaults(action="rpc")
    serve = subs.add_parser("serve", help="Start the optional loopback web interface")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(action="serve")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    global_parser = Parser(add_help=False)
    global_parser.add_argument("--json", action="store_true")
    global_parser.add_argument("--db")
    global_parser.add_argument("--workspace")
    global_parser.add_argument(
        "--watch", type=int, help="Repeat a read-only operation every N seconds"
    )
    result = None
    json_mode = "--json" in argv
    try:
        tail = None
        if "--" in argv:
            cut = argv.index("--")
            tail, argv = argv[cut + 1 :], argv[:cut]
        options, remaining = global_parser.parse_known_args(argv)
        json_mode = options.json
        parser = build_parser()
        parsed = vars(parser.parse_args(remaining))
        action = parsed.pop("action")
        parsed.pop("operation", None)
        parsed.pop("suboperation", None)
        if action == "init":
            if options.db or options.watch or tail is not None:
                raise Failure("invalid_argument", "init does not accept --db, --watch or command arguments")
            if options.workspace and parsed["path"]:
                raise Failure("invalid_argument", "Choose the init path either positionally or with --workspace, not both")
            value = initialize(parsed["path"] or options.workspace or ".", parsed["name"])
            print(json_text(envelope(value)) if json_mode else json_text(value))
            return
        if action == "serve":
            from .web import serve

            serve(str(resolve_db(options.db, options.workspace)), parsed["port"], json_mode=json_mode)
            return
        if action == "rpc":
            json_mode = True
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise Failure("invalid_argument", "RPC request must be an object")
            action, parsed = request.get("operation"), request.get("arguments", {})
        else:
            for key in list(parsed):
                if key.endswith("_file"):
                    path = parsed.pop(key)
                    if path is None:
                        continue
                    name = key[:-5]
                    if name in parsed:
                        raise Failure(
                            "invalid_argument", f"Use either --{name} or --{name}-file"
                        )
                    content = (
                        sys.stdin.read()
                        if path == "-"
                        else Path(path).expanduser().read_text()
                    )
                    parsed[name] = (
                        json.loads(content)
                        if REGISTRY[action]["fields"][name]["type"]
                        in {"object", "array"}
                        else content
                    )
            if tail is not None:
                if "argv" not in REGISTRY[action]["fields"]:
                    raise Failure(
                        "invalid_argument",
                        "This operation does not accept an argument vector",
                    )
                if "argv" in parsed:
                    raise Failure("invalid_argument", "Do not combine --argv and --")
                parsed["argv"] = tail
        if options.watch is not None:
            if options.watch < 2:
                raise Failure("invalid_argument", "--watch must be at least 2 seconds")
            if action not in REGISTRY or REGISTRY[action]["mutating"]:
                raise Failure(
                    "invalid_argument", "--watch accepts read-only operations only"
                )
        db = None if action == "operations" else resolve_db(options.db, options.workspace)
        while True:
            result = invoke(db, action, parsed)
            if json_mode:
                print(json_text(result), flush=True)
            elif result["ok"]:
                show(result["data"])
            else:
                print(
                    f"{result['error']['code']}: {result['error']['message']}",
                    file=sys.stderr,
                )
                if result["error"]["details"]:
                    print(json_text(result["error"]["details"]), file=sys.stderr)
            if not options.watch:
                break
            time.sleep(options.watch)
    except Failure as exc:
        result = envelope(error=exc)
        if json_mode:
            print(json_text(result))
        else:
            print(f"{exc.code}: {exc.message}", file=sys.stderr)
    except (OSError, ValueError) as exc:
        result = envelope(error=Failure("invalid_argument", str(exc)))
        if json_mode:
            print(json_text(result))
        else:
            print(str(exc), file=sys.stderr)
    except KeyboardInterrupt:
        return
    if result and not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
