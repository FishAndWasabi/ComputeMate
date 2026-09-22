#!/usr/bin/env python3
"""Run a VS Code development host using disposable settings and extension directories."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = shutil.which("code")
if not code:
    raise SystemExit("VS Code CLI not found; extension host smoke test cannot run")
with tempfile.TemporaryDirectory(prefix="cloud-servers-vscode-") as directory:
    work = Path(directory)
    recorder = root / "tests/recording-python.py"
    recorder.chmod(0o755)
    for name in ("Project-A", "Project-B"):
        folder = work / name
        folder.mkdir()
        script = root / "skills/cloud-servers/scripts/cloud_servers.py"
        subprocess.run([__import__("sys").executable, str(script), "init", str(folder)], check=True, capture_output=True)
        subprocess.run([__import__("sys").executable, str(script), "--workspace", str(folder), "server", "add", "--id", "gpu", "--data", json.dumps({"name": name, "ssh": {"alias": "test.invalid"}})], check=True, capture_output=True)
    (work / "Project-New").mkdir()
    # Only the disposable test profile trusts these generated fixture folders.
    settings = work / "profile/User/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"security.workspace.trust.enabled": False}))
    workspace = work / "isolated.code-workspace"
    workspace.write_text(json.dumps({"folders": [{"path": str(work / name)} for name in ("Project-A", "Project-B", "Project-New")]}))
    env = {
        **os.environ,
        "CLOUD_SERVERS_TEST_ROOT": str(work),
        "CLOUD_SERVERS_TEST_PYTHON": str(recorder),
        "CLOUD_SERVERS_DB": str(work / "wrong-global.sqlite3"),
    }
    electron = Path("/Applications/Visual Studio Code.app/Contents/MacOS/Code")
    executable = str(electron) if electron.exists() else code
    result = subprocess.run(
        [
            executable,
            "--new-window",
            "--skip-welcome",
            "--skip-release-notes",
            "--user-data-dir",
            str(work / "profile"),
            "--extensions-dir",
            str(work / "extensions"),
            "--extensionDevelopmentPath=" + str(root / "extensions/vscode"),
            "--extensionTestsPath=" + str(root / "tests/vscode-smoke.cjs"),
            "--disable-extensions",
            str(workspace),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    proof = work / "result.json"
    if result.returncode or not proof.exists():
        for name in ("requests.jsonl", "result.json"):
            diagnostic = work / name
            if diagnostic.exists(): print(diagnostic.read_text()[-5000:])
        print("\n".join(line for line in result.stdout.splitlines() if any(word in line for word in ("Assertion", "Error", "Expected", "actual", "expected", "vscode-smoke"))))
        print(result.stderr[-8000:])
        for log in (work / "profile/logs").rglob("exthost.log"):
            print(log.read_text()[-6000:])
        raise SystemExit("Extension host smoke test failed")
    print(json.dumps(json.loads(proof.read_text()), indent=2))
