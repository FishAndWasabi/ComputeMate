#!/usr/bin/env python3
"""Test-only interpreter shim; records the actual inventory returned by RPC."""
import json
import os
from pathlib import Path
import subprocess
import sys

request = sys.stdin.buffer.read()
result = subprocess.run([sys.executable, *sys.argv[1:]], input=request, capture_output=True)
try:
    operation = json.loads(request).get("operation")
    response = json.loads(result.stdout)
    record = {"operation": operation, "argv": sys.argv[1:], "cwd": os.getcwd(), "ok": response.get("ok"), "scope": response.get("meta", {}).get("scope"), "servers": [r["name"] for r in (response.get("data") or {}).get("servers", [])]}
    with (Path(os.environ["CLOUD_SERVERS_TEST_ROOT"]) / "requests.jsonl").open("a") as log:
        log.write(json.dumps(record) + "\n")
except (ValueError, KeyError):
    pass
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
