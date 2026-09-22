from __future__ import annotations

import base64
import csv
import json
import re
import shlex
import uuid
from pathlib import Path

from .common import Failure
from .transport import execute_local, require_tool, shell


PROBE = r"""set +e
printf '\n__CS_cpu__\n'
getconf _NPROCESSORS_ONLN
printf '\n__CS_model__\n'
awk -F: '/model name/ {sub(/^ +/,"",$2); print $2; exit}' /proc/cpuinfo
printf '\n__CS_memory__\n'
awk '/MemTotal:|MemAvailable:/ {print $1,$2}' /proc/meminfo
printf '\n__CS_disk__\n'
df -Pk / "$HOME" 2>/dev/null
printf '\n__CS_gpu__\n'
if command -v nvidia-smi >/dev/null; then
 nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits 2>/dev/null
else printf 'unavailable\n'; fi
printf '\n__CS_capabilities__\n'
for t in bash rsync git rg grep sed sha256sum tmux sbatch squeue sacct scontrol scancel sinfo conda docker python3; do
 command -v "$t" >/dev/null && printf '%s\n' "$t"
done
printf '\n__CS_os__\n'
uname -srm
exit 0
"""


def parse_probe(output):
    sections = {}
    current = None
    for line in output.splitlines():
        marker = re.fullmatch(r"__CS_(\w+)__", line)
        if marker:
            current = marker[1]
            sections[current] = []
        elif current and line:
            sections[current].append(line)

    def number(value):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    memory = {
        line.split()[0].rstrip(":"): int(line.split()[1]) * 1024
        for line in sections.get("memory", [])
        if len(line.split()) == 2 and line.split()[1].isdigit()
    }
    gpus = []
    for row in csv.reader(sections.get("gpu", []), skipinitialspace=True):
        if len(row) == 5:
            gpus.append(
                dict(
                    zip(
                        [
                            "index",
                            "name",
                            "memory_total_mib",
                            "memory_used_mib",
                            "utilization_percent",
                        ],
                        [
                            row[0],
                            row[1],
                            number(row[2]),
                            number(row[3]),
                            number(row[4]),
                        ],
                    )
                )
            )
    disks = []
    for line in sections.get("disk", [])[1:]:
        parts = line.split()
        if len(parts) >= 6 and parts[1].isdigit():
            disks.append(
                {
                    "mount": " ".join(parts[5:]),
                    "total_bytes": int(parts[1]) * 1024,
                    "available_bytes": int(parts[3]) * 1024,
                    "used_percent": parts[4],
                }
            )
    return {
        "cpu_count": number(next(iter(sections.get("cpu", [])), None)),
        "cpu_model": " ".join(sections.get("model", [])),
        "memory": memory,
        "disks": disks,
        "gpus": gpus,
        "gpu_observation": "available" if gpus else "unknown",
        "capabilities": sections.get("capabilities", []),
        "os": " ".join(sections.get("os", [])),
    }


def probe(ssh):
    return parse_probe(ssh.run(PROBE)["stdout"])


def discover_environments(ssh, paths):
    result = {"system": {"type": "system", "selector": ""}, "venvs": [], "warnings": []}
    script = "command -v conda >/dev/null && conda env list --json\n"
    conda = ssh.run(script, check=False)
    try:
        result["conda"] = (
            json.loads(conda["stdout"]).get("envs", [])
            if conda["exit_code"] == 0
            else []
        )
    except json.JSONDecodeError:
        result["conda"] = []
        result["warnings"].append("Conda returned non-JSON output")
    docker = ssh.run(
        "command -v docker >/dev/null && docker ps -a --format '{{json .}}'\n",
        check=False,
    )
    result["docker"] = []
    for line in docker["stdout"].splitlines():
        try:
            result["docker"].append(json.loads(line))
        except json.JSONDecodeError:
            result["warnings"].append("Unrecognized Docker output")
    if docker["exit_code"]:
        result["warnings"].append("Docker absent or inaccessible")
    for path in paths:
        check = ssh.run(
            f"test -f {shlex.quote(path.rstrip('/') + '/pyvenv.cfg')}\n", check=False
        )
        if check["exit_code"] == 0:
            result["venvs"].append({"type": "venv", "selector": path})
    cuda = ssh.run("command -v nvcc >/dev/null && nvcc --version\n", check=False)
    result["cuda"] = cuda["stdout"].strip() if cuda["exit_code"] == 0 else None
    return result


def fs_list(ssh, path, limit, offset):
    if not path.startswith("/"):
        path = "./" + path
    result = ssh.run(
        # Let find decode the escapes: Bash drops literal NUL bytes in its input.
        shell(["find", path, "-mindepth", "1", "-maxdepth", "1", "-printf", r"%y\t%p\0"])
    )
    rows = []
    for record in result["stdout"].split("\0"):
        if "\t" in record:
            kind, name = record.split("\t", 1)
            rows.append({"type": kind, "path": name})
    rows.sort(key=lambda x: x["path"])
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "truncated": result["truncated"],
    }


def fs_read(ssh, path, start, end, max_bytes):
    result = ssh.run(
        shell(["sed", "-n", f"{start},{end}p"]) + " < " + shlex.quote(path),
        limit=max_bytes,
    )
    checksum = ssh.run(shell(["sha256sum", "--", path]), check=False)
    return {
        "path": path,
        "start": start,
        "end": end,
        "content": result["stdout"],
        "sha256": checksum["stdout"].split()[0] if checksum["exit_code"] == 0 else None,
        "truncated": result["truncated"],
    }


def fs_search(ssh, path, pattern, limit, max_bytes):
    script = "if command -v rg >/dev/null; then\n" + shell(
        [
            "rg",
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--max-count",
            str(limit),
            "-e",
            pattern,
            "--",
            path,
        ]
    )
    script += (
        "\nelse\n"
        + shell(["grep", "-RInI", "-m", str(limit), "--", pattern, path])
        + "\nfi\n"
    )
    result = ssh.run(script, check=False, limit=max_bytes)
    if result["exit_code"] not in (0, 1):
        raise Failure("remote_error", "Search failed", result)
    lines = result["stdout"].splitlines()
    return {
        "matches": lines[:limit],
        "truncated": result["truncated"] or len(lines) > limit,
    }


def fs_patch(ssh, cwd, patch, expected_revision=None, expected_hashes=None):
    encoded = base64.b64encode(patch.encode()).decode()
    script = require_tool("git") + f"set -e\ncd -- {shlex.quote(cwd)}\n"
    script += """lock=$(git rev-parse --git-path cloud-servers-patch.lock 2>/dev/null || printf '.cloud-servers-patch.lock')
mkdir "$lock" 2>/dev/null || { echo 'Another patch is in progress; inspect the patch lock' >&2; exit 73; }
tmp=$(mktemp)
trap 'rm -f "$tmp"; rmdir "$lock"' EXIT
"""
    if expected_revision:
        script += f"test \"$(git rev-parse HEAD)\" = {shlex.quote(expected_revision)} || {{ echo 'Git revision changed' >&2; exit 73; }}\n"
    for path, digest in (expected_hashes or {}).items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise Failure(
                "invalid_argument", "expected_hashes values must be SHA-256 hex digests"
            )
        script += f"test \"$(sha256sum -- {shlex.quote(path)} | cut -d ' ' -f1)\" = {shlex.quote(digest)} || {{ echo 'File content changed' >&2; exit 73; }}\n"
    script += f'printf %s {shlex.quote(encoded)} | base64 -d > "$tmp"\n'
    script += "git apply --check -- \"$tmp\" || { echo 'Patch context conflicts' >&2; exit 73; }\ngit apply -- \"$tmp\"\nprintf 'Patch applied\\n'\n"
    return ssh.run(script, mutating=True)


def sync(
    ssh, local, remote, direction, apply=False, delete=False, exclude=None, timeout=300
):
    local_path = str(Path(local).expanduser().absolute())
    if local.endswith("/") and not local_path.endswith("/"):
        local_path += "/"
    if "\n" in remote or "\r" in remote:
        raise Failure("invalid_argument", "rsync paths cannot contain newlines")
    args = ["rsync", "-az", "--itemize-changes", "--partial", "-e", shell(ssh.base())]
    if not apply:
        args.append("--dry-run")
    if delete:
        args.append("--delete")
    for pattern in exclude or []:
        args += ["--exclude", pattern]
    remote_spec = f"{ssh.target}:{shlex.quote(remote)}"
    args += [
        "--",
        *(
            [local_path, remote_spec]
            if direction == "push"
            else [remote_spec, local_path]
        ),
    ]
    result = execute_local(args, timeout=timeout, mutating=apply)
    if result["exit_code"]:
        raise Failure(
            "uncertain" if apply else "transfer_failed",
            "rsync did not complete",
            result,
        )
    return {
        **result,
        "preview": not apply,
        "direction": direction,
        "local": local_path,
        "remote": remote,
    }


def validate_session(name):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name):
        raise Failure(
            "invalid_argument",
            "Session names may contain letters, numbers, underscores and hyphens",
        )


def tmux_start(ssh, command, name=None, cwd=None, log_path=None):
    name = name or "cs-" + uuid.uuid4().hex[:12]
    validate_session(name)
    script = require_tool("tmux") + "set -e\n"
    if log_path:
        if not log_path.startswith("/"):
            raise Failure("invalid_argument", "log_path must be absolute")
        script += f"log_path={shlex.quote(log_path)}\n"
    else:
        script += f'log_path="${{XDG_STATE_HOME:-$HOME/.local/state}}/cloud-servers/{name}.log"\n'
    script += 'mkdir -p -- "$(dirname -- "$log_path")"\n'
    create = ["tmux", "new-session", "-d", "-s", name]
    if cwd:
        create += ["-c", cwd]
    script += shell(create + ["sleep 86400"]) + "\n"
    script += f"trap {shlex.quote(shell(['tmux', 'kill-session', '-t', '=' + name]) + ' 2>/dev/null || true')} ERR\n"
    script += (
        shell(
            ["tmux", "set-option", "-w", "-t", "=" + name + ":", "remain-on-exit", "on"]
        )
        + "\n"
    )
    # The pathname is expanded once by the remote shell, then quoted for the inner shell.
    script += 'printf -v quoted_log %q "$log_path"\n'
    script += f'cmd={shlex.quote("exec bash -c " + shlex.quote(command))}\ncmd="$cmd > $quoted_log 2>&1"\n'
    script += (
        shell(["tmux", "respawn-pane", "-k", "-t", "=" + name + ":"]) + ' "$cmd"\n'
    )
    script += "trap - ERR\nprintf '%s\\n' \"$log_path\"\n"
    result = ssh.run(script, mutating=True)
    return {"backend": "tmux", "native_id": name, "log_path": result["stdout"].strip()}


def tmux_list(ssh, name=None):
    if name:
        validate_session(name)
    args = [
        "tmux",
        "list-panes",
        *(["-t", "=" + name + ":"] if name else ["-a"]),
        "-F",
        "#{session_name}|#{pane_id}|#{pane_dead}|#{pane_dead_status}|#{pane_current_command}",
    ]
    result = ssh.run(require_tool("tmux") + shell(args), check=False)
    if result["exit_code"]:
        if (
            "no server running" in result["stderr"]
            or "no sessions" in result["stderr"]
            or "error connecting" in result["stderr"]
            and "No such file" in result["stderr"]
        ):
            return {"items": [], "native_state": "no_sessions"}
        raise Failure(
            "missing_dependency" if result["exit_code"] == 127 else "remote_error",
            result["stderr"],
            result,
        )
    items = []
    for line in result["stdout"].splitlines():
        row = line.split("|", 4)
        if len(row) == 5:
            items.append(
                {
                    "session": row[0],
                    "pane": row[1],
                    "pane_dead": row[2] == "1",
                    "exit_code": int(row[3]) if row[3].isdigit() else None,
                    "command": row[4],
                }
            )
    return {"items": items}


def validate_job(job):
    if not re.fullmatch(r"[0-9]+(?:_[0-9]+)?(?:\.[A-Za-z0-9]+)?", str(job)):
        raise Failure(
            "invalid_argument", "Expected a numeric Slurm job ID or array task ID"
        )


def slurm_submit(ssh, script, options, cwd=None):
    args = ["sbatch", "--parsable"]
    allowed = {
        "partition",
        "account",
        "qos",
        "nodes",
        "ntasks",
        "cpus-per-task",
        "gpus",
        "mem",
        "time",
        "job-name",
        "output",
        "error",
        "constraint",
    }
    for key, value in options.items():
        if (
            key not in allowed
            or not isinstance(value, (str, int))
            or isinstance(value, bool)
        ):
            raise Failure("invalid_argument", f"Unsupported sbatch option: {key}")
        args.append(f"--{key}={value}")
    if not script.startswith("#!"):
        script = "#!/bin/bash\n" + script
    marker = "CS_SCRIPT_" + uuid.uuid4().hex
    command = require_tool("sbatch") + (
        f"cd -- {shlex.quote(cwd)} || exit\n" if cwd else ""
    )
    command += shell(args) + f" <<'{marker}'\n{script}\n{marker}\n"
    result = ssh.run(command, mutating=True)
    value = (
        result["stdout"].strip().splitlines()[-1] if result["stdout"].strip() else ""
    )
    job, _, cluster = value.partition(";")
    if not job.isdigit():
        raise Failure(
            "uncertain",
            "sbatch returned an unrecognized job ID; inspect the queue before resubmitting",
            result,
        )
    return {"backend": "slurm", "native_id": job, "cluster": cluster or None}


def parse_slurm_table(output, keys):
    items = []
    for line in output.splitlines():
        row = line.strip().split("|", len(keys) - 1)
        if len(row) == len(keys):
            items.append(dict(zip(keys, row)))
    return items


def slurm_list(ssh, user=None, limit=100):
    args = ["squeue", "--noheader", "--format=%i|%j|%T|%P|%u|%M|%R"]
    if user:
        args += ["--user", user]
    result = ssh.run(require_tool("squeue") + shell(args))
    rows = parse_slurm_table(
        result["stdout"],
        ["job_id", "name", "state", "partition", "user", "elapsed", "reason_or_nodes"],
    )
    return {
        "items": rows[:limit],
        "truncated": result["truncated"] or len(rows) > limit,
    }


def slurm_resources(ssh):
    result = ssh.run(
        require_tool("sinfo")
        + shell(["sinfo", "-N", "--noheader", "--format=%N|%P|%t|%c|%m|%G"])
    )
    return {
        "items": parse_slurm_table(
            result["stdout"],
            ["node", "partition", "state", "cpus", "memory_mib", "gres"],
        ),
        "source": "slurm",
        "truncated": result["truncated"],
    }


def slurm_show(ssh, job):
    validate_job(job)
    control = ssh.run(
        require_tool("scontrol")
        + shell(["scontrol", "show", "job", "--oneliner", job]),
        check=False,
    )
    accounting = ssh.run(
        require_tool("sacct")
        + shell(
            [
                "sacct",
                "--noheader",
                "--parsable2",
                "--jobs",
                job,
                "--format=JobID,JobName,State,ExitCode,Elapsed,NodeList",
            ]
        ),
        check=False,
    )
    return {
        "job_id": job,
        "control": control,
        "accounting": parse_slurm_table(
            accounting["stdout"],
            ["job_id", "name", "state", "exit_code", "elapsed", "nodes"],
        )
        if accounting["exit_code"] == 0
        else [],
        "accounting_error": accounting["stderr"] if accounting["exit_code"] else None,
        "availability": "observed"
        if control["exit_code"] == 0 or accounting["stdout"].strip()
        else "unknown",
    }


def slurm_log_path(ssh, job, stream):
    validate_job(job)
    result = ssh.run(
        require_tool("scontrol") + shell(["scontrol", "show", "job", "--oneliner", job])
    )
    fields = dict(
        re.findall(r"(?:^|\s)(\w+)=(.*?)(?=\s\w+=|$)", result["stdout"].strip())
    )
    path = fields.get("StdErr" if stream == "stderr" else "StdOut")
    if not path or path in ("(null)", "(none)") or "%" in path:
        raise Failure("not_found", "Log path is unavailable; supply path explicitly")
    return path
