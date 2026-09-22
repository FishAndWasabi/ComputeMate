"""Real loopback SSH, rsync, Git and tmux; all keys/data live in a temporary directory.

Skips only when a local sshd/tool is unavailable. Does not modify ~/.ssh or user sessions.
"""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/cloud-servers/scripts")
)
from cloud_servers.api import invoke
from cloud_servers.transport import SSH


class SSHIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sshd = shutil.which("sshd") or "/usr/sbin/sshd"
        if not Path(cls.sshd).exists() or not shutil.which("ssh-keygen"):
            raise unittest.SkipTest("Local sshd/ssh-keygen unavailable")
        cls.temp = tempfile.TemporaryDirectory(prefix="cs-ssh-test-")
        cls.root = Path(cls.temp.name)
        cls.tmux_root = cls.root / "tmux"
        cls.tmux_root.mkdir(mode=0o700)
        for key in ("host", "client"):
            subprocess.run(
                [
                    "ssh-keygen",
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-f",
                    str(cls.root / key),
                ],
                check=True,
            )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.config = cls.root / "sshd_config"
        cls.config.write_text(f"""Port {cls.port}
ListenAddress 127.0.0.1
HostKey {cls.root}/host
AuthorizedKeysFile {cls.root}/client.pub
StrictModes no
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
PidFile {cls.root}/pid
LogLevel ERROR
""")
        public = (cls.root / "host.pub").read_text().split()
        cls.known = cls.root / "known_hosts"
        cls.known.write_text(f"[127.0.0.1]:{cls.port} {public[0]} {public[1]}\n")
        cls.log = open(cls.root / "sshd.log", "w")
        cls.process = subprocess.Popen(
            [cls.sshd, "-D", "-e", "-f", str(cls.config)],
            stdout=cls.log,
            stderr=cls.log,
        )
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            cls.process.terminate()
            cls.process.wait()
            cls.log.close()
            cls.temp.cleanup()
            raise unittest.SkipTest("Unable to start unprivileged local sshd")
        original_base = SSH.base
        original_run = SSH.run
        cls.base_patch = patch.object(
            SSH,
            "base",
            lambda self: (
                original_base(self) + ["-o", "UserKnownHostsFile=" + str(cls.known)]
            ),
        )
        cls.run_patch = patch.object(
            SSH,
            "run",
            lambda self, script, **kw: original_run(
                self,
                f"export TMUX_TMPDIR={str(cls.tmux_root)!r}\nexport PATH=/usr/local/bin:/opt/homebrew/bin:$PATH\n"
                + script,
                **kw,
            ),
        )
        cls.base_patch.start()
        cls.run_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.base_patch.stop()
        cls.run_patch.stop()
        if shutil.which("tmux"):
            env = {**os.environ, "TMUX_TMPDIR": str(cls.tmux_root)}
            subprocess.run(["tmux", "kill-server"], env=env, capture_output=True)
        cls.process.terminate()
        cls.process.wait()
        cls.log.close()
        cls.temp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="work-", dir=self.root))
        self.db = self.work / "inventory.db"
        self.call(
            "server.add",
            id="local-test",
            data={
                "name": "isolated SSH fixture",
                "ssh": {
                    "host": "127.0.0.1",
                    "port": self.port,
                    "identity_file": str(self.root / "client"),
                },
            },
        )

    def call(self, operation, **args):
        result = invoke(self.db, operation, args)
        self.assertTrue(result["ok"], result)
        return result["data"]

    def test_argument_quoting_and_nonzero_exit(self):
        dangerous = "spaces ; $(touch should-not-exist) ' quotes"
        result = self.call(
            "exec",
            server="local-test",
            cwd=str(self.work),
            argv=["printf", "%s", dangerous],
        )
        self.assertEqual(result["stdout"], dangerous)
        self.assertFalse((self.work / "should-not-exist").exists())
        result = invoke(
            self.db,
            "exec",
            {"server": "local-test", "script": "echo intentional >&2; exit 7"},
        )
        self.assertEqual(result["error"]["details"]["exit_code"], 7)

    def test_contextual_patch_read_and_conflict(self):
        project = self.work / "project ' with spaces"
        project.mkdir()
        file = project / "hello.txt"
        file.write_text("before\n")
        patch_text = "diff --git a/hello.txt b/hello.txt\n--- a/hello.txt\n+++ b/hello.txt\n@@ -1 +1 @@\n-before\n+after\n"
        self.call("fs.patch", server="local-test", cwd=str(project), patch=patch_text)
        self.assertEqual(file.read_text(), "after\n")
        value = self.call(
            "fs.read", server="local-test", path=str(file), start=1, end=1
        )
        self.assertEqual(value["content"], "after\n")
        conflict = invoke(
            self.db,
            "fs.patch",
            {"server": "local-test", "cwd": str(project), "patch": patch_text},
        )
        self.assertEqual(conflict["error"]["code"], "conflict")

    @unittest.skipUnless(shutil.which("rsync"), "rsync unavailable")
    def test_rsync_preview_apply_pull_and_preserve_extras(self):
        local = self.work / "local"
        local.mkdir()
        (local / "code.txt").write_text("version 1\n")
        remote = self.work / "remote ' with spaces"
        remote.mkdir()
        (remote / "keep.txt").write_text("keep")
        args = {
            "server": "local-test",
            "local": str(local) + "/",
            "remote": str(remote) + "/",
            "direction": "push",
        }
        self.call("sync", **args)
        self.assertFalse((remote / "code.txt").exists())
        self.call("sync", **args, apply=True)
        self.assertEqual((remote / "code.txt").read_text(), "version 1\n")
        self.assertTrue((remote / "keep.txt").exists())
        download = self.work / "download.txt"
        self.call(
            "transfer.get",
            server="local-test",
            path=str(remote / "code.txt"),
            local=str(download),
        )
        self.assertEqual(download.read_text(), "version 1\n")

    @unittest.skipUnless(shutil.which("tmux"), "tmux unavailable")
    def test_tmux_survives_ssh_and_keeps_logs_and_exit_code(self):
        log = self.work / "run ' log.txt"
        result = self.call(
            "tmux.start",
            server="local-test",
            name="cs-integration",
            cwd=str(self.work),
            script="sleep 1; echo completed; exit 3",
            log_path=str(log),
        )
        self.assertEqual(result["native_id"], "cs-integration")
        try:
            for _ in range(30):
                panes = self.call(
                    "tmux.show", server="local-test", name="cs-integration"
                )["items"]
                if panes and panes[0]["pane_dead"]:
                    break
                time.sleep(0.1)
            self.assertTrue(panes[0]["pane_dead"])
            self.assertEqual(panes[0]["exit_code"], 3)
            logs = self.call("tmux.logs", server="local-test", name="cs-integration")
            self.assertIn("completed", logs["stdout"])
        finally:
            self.call("tmux.stop", server="local-test", name="cs-integration")


if __name__ == "__main__":
    unittest.main()
