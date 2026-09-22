"""Regression checks for first-run guidance and misleading status output."""
from contextlib import redirect_stdout
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/cloud-servers/scripts"
sys.path.insert(0, str(SCRIPTS))
from cloud_servers.cli import show, display_width
from cloud_servers.common import Failure
from cloud_servers.web import serve


class UsabilityTests(unittest.TestCase):
    def test_missing_web_build_fails_before_opening_a_server(self):
        with patch("cloud_servers.web.Path.is_file", return_value=False), patch("cloud_servers.web.WebServer") as server:
            with self.assertRaises(Failure) as result:
                serve("unused.db")
        self.assertEqual(result.exception.code, "web_assets_missing")
        self.assertIn("npm run build", result.exception.message)
        self.assertIn("uv tool install --reinstall .", result.exception.message)
        server.assert_not_called()

    def test_busy_web_port_explains_how_to_choose_a_free_port(self):
        with patch("cloud_servers.web.Path.is_file", return_value=True), patch(
            "cloud_servers.web.WebServer", side_effect=OSError(errno.EADDRINUSE, "occupied")
        ):
            with self.assertRaises(Failure) as result:
                serve("unused.db", 8765)
        self.assertEqual(result.exception.code, "port_in_use")
        self.assertIn("--port 0", result.exception.message)

    def test_snapshot_distinguishes_failed_stale_fresh_and_unobserved(self):
        output = io.StringIO()
        states = [
            {},
            {"hardware": {"stale": False, "error": None}},
            {"hardware": {"stale": True, "error": None}},
            {"hardware": {"stale": True, "error": {"message": "offline"}}},
        ]
        with redirect_stdout(output):
            show({"servers": [
                {"id": f"s{i}", "name": "实验服务器" if i % 2 else "GPU", "observations": obs}
                for i, obs in enumerate(states)
            ]})
        lines = output.getvalue().splitlines()[2:]
        for line, status in zip(lines, ("unobserved", "observed", "stale", "connection_failed")):
            self.assertIn(status, line)
        # Chinese and ASCII server names must align the subsequent columns.
        self.assertEqual(len({display_width(line.split("general")[0]) for line in lines}), 1)

    def test_initialization_explains_next_step_and_preserves_json_contract(self):
        with tempfile.TemporaryDirectory(prefix="computemate first project ") as root:
            command = [sys.executable, str(SCRIPTS / "computemate.py"), "--workspace", root]
            human = subprocess.run([*command, "init"], capture_output=True, text=True)
            self.assertEqual(human.returncode, 0, human.stderr)
            self.assertIn("computemate server add --help", human.stdout)
            machine = subprocess.run([*command, "--json", "init"], capture_output=True, text=True)
            self.assertEqual(machine.returncode, 0, machine.stderr)
            value = json.loads(machine.stdout)
            self.assertTrue(value["ok"])
            self.assertFalse(value["data"]["created"])


if __name__ == "__main__":
    unittest.main()
