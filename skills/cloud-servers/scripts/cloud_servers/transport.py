from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from .common import Failure


def shell(argv):
    return shlex.join([str(a) for a in argv])


def execute_local(argv, *, stdin=None, timeout=60, limit=65536, mutating=False):
    """Spool output to disk so a verbose remote command cannot exhaust memory."""
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                result = subprocess.run(
                    argv,
                    input=stdin.encode() if isinstance(stdin, str) else stdin,
                    stdout=out,
                    stderr=err,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise Failure(
                    "uncertain" if mutating else "timeout",
                    "Connection timed out; remote execution may continue"
                    if mutating
                    else "Operation timed out",
                )
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read(limit + 1), err.read(limit + 1)
            data = {
                "stdout": stdout[:limit].decode("utf-8", "replace"),
                "stderr": stderr[:limit].decode("utf-8", "replace"),
                "exit_code": result.returncode,
                "truncated": len(stdout) > limit or len(stderr) > limit,
            }
            return data
    except FileNotFoundError as exc:
        raise Failure("missing_dependency", f"Executable not found: {argv[0]}") from exc


class SSH:
    def __init__(self, server):
        self.server = server
        self.connection = server["ssh"]

    def base(self):
        c = self.connection
        args = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
        for key, flag in (
            ("port", "-p"),
            ("user", "-l"),
            ("identity_file", "-i"),
            ("proxy_jump", "-J"),
        ):
            if c.get(key):
                args += [
                    flag,
                    str(Path(c[key]).expanduser())
                    if key == "identity_file"
                    else str(c[key]),
                ]
        return args

    @property
    def target(self):
        return self.connection.get("alias") or self.connection["host"]

    def run(self, script, *, timeout=60, limit=65536, mutating=False, check=True):
        result = execute_local(
            self.base() + [self.target, "bash -s"],
            stdin=script,
            timeout=timeout,
            limit=limit,
            mutating=mutating,
        )
        if result["exit_code"] == 255:
            raise Failure(
                "uncertain" if mutating else "connection_failed",
                "SSH connection failed; remote outcome is unknown"
                if mutating
                else "SSH connection failed",
                result,
            )
        if check and result["exit_code"]:
            code = (
                "missing_dependency" if result["exit_code"] == 127 else "remote_error"
            )
            if result["exit_code"] == 73:
                code = "conflict"
            raise Failure(
                code, result["stderr"].strip() or "Remote command failed", result
            )
        return result


def validate_connection(connection):
    if not isinstance(connection, dict):
        raise Failure("invalid_argument", "ssh must be an object")
    if set(connection) - {
        "alias",
        "host",
        "port",
        "user",
        "identity_file",
        "proxy_jump",
    }:
        raise Failure("invalid_argument", "Unknown SSH connection fields")
    target = connection.get("alias") or connection.get("host")
    if not isinstance(target, str) or not re.fullmatch(
        r"[A-Za-z0-9_][A-Za-z0-9_.:@%\[\]-]*", target
    ):
        raise Failure(
            "invalid_argument", "ssh.alias or ssh.host must be a valid SSH destination"
        )
    if "port" in connection and (
        type(connection["port"]) is not int or not 1 <= connection["port"] <= 65535
    ):
        raise Failure("invalid_argument", "SSH port must be between 1 and 65535")
    for key in ("user", "identity_file", "proxy_jump"):
        if key in connection and (
            not isinstance(connection[key], str)
            or any(x in connection[key] for x in "\n\r\x00")
        ):
            raise Failure("invalid_argument", f"Invalid SSH {key}")


def require_tool(name):
    return f"command -v {shlex.quote(name)} >/dev/null || {{ echo 'Missing dependency: {name}' >&2; exit 127; }}\n"


def in_environment(command, environment=None, cwd=None):
    if environment:
        kind, selector = environment["type"], environment.get("selector", "")
        if kind == "conda":
            flag = "-p" if selector.startswith("/") else "-n"
            command = shell(
                [
                    environment.get("conda_executable", "conda"),
                    "run",
                    "--no-capture-output",
                    flag,
                    selector,
                    "bash",
                    "-c",
                    command,
                ]
            )
        elif kind == "venv":
            command = f'export VIRTUAL_ENV={shlex.quote(selector)}\nexport PATH="$VIRTUAL_ENV/bin:$PATH"\n{command}'
        elif kind == "docker":
            command = shell(
                [
                    "docker",
                    "exec",
                    *(["-w", cwd] if cwd else []),
                    selector,
                    "bash",
                    "-c",
                    command,
                ]
            )
            cwd = None
        elif kind != "system":
            raise Failure("invalid_argument", f"Unsupported environment type: {kind}")
    if cwd:
        command = f"cd -- {shlex.quote(cwd)} || exit\n{command}"
    return command
