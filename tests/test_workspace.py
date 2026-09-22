import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/cloud-servers/scripts/cloud_servers.py"
sys.path.insert(0, str(SCRIPT.parent))
from cloud_servers.common import Failure
from cloud_servers.workspace import initialize, resolve_db
from cloud_servers.api import invoke


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.a, self.b = self.root / "A", self.root / "B"
        self.a.mkdir()
        self.b.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k != "CLOUD_SERVERS_DB"}

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, cwd, *args, ok=True, env=None):
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", *args],
            cwd=cwd,
            env=env or self.env,
            text=True,
            capture_output=True,
        )
        value = json.loads(process.stdout)
        self.assertEqual(value["ok"], ok, value)
        self.assertEqual(process.returncode, 0 if ok else 1)
        return value

    def test_project_records_with_same_ids_are_isolated(self):
        for path, name in [(self.a, "Project A"), (self.b, "Project B")]:
            self.cli(path, "init", "--name", name)
            self.cli(
                path,
                "server",
                "add",
                "--id",
                "gpu",
                "--data",
                json.dumps({"name": name, "ssh": {"alias": "same-host"}}),
            )
        self.cli(self.a, "server", "update", "gpu", "--data", '{"name":"A changed"}')
        self.cli(self.a, "server", "remove", "gpu")
        self.assertEqual(self.cli(self.a, "server", "list")["data"]["total"], 0)
        self.assertEqual(
            self.cli(self.b, "server", "get", "gpu")["data"]["name"], "Project B"
        )
        a_scope = self.cli(self.a, "scope")["data"]
        b_scope = self.cli(self.b, "scope")["data"]
        self.assertNotEqual(a_scope["id"], b_scope["id"])
        self.assertEqual(self.cli(self.b, "snapshot")["data"]["workspace"], b_scope)

    def test_init_is_idempotent_and_child_discovery_beats_legacy_env(self):
        first = initialize(self.a, "A")
        second = initialize(self.a, "B")
        self.assertFalse(second["created"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["name"], "A")
        child = self.a / "src" / "nested"
        child.mkdir(parents=True)
        selected = resolve_db(
            cwd=child, environ={"CLOUD_SERVERS_DB": str(self.root / "legacy.db")}
        )
        self.assertEqual(str(selected), first["database"])
        self.assertEqual(self.cli(child, "scope")["data"]["root"], str(self.a))

    def test_missing_and_invalid_bindings_never_fall_back(self):
        failed = self.cli(self.a, "server", "list", ok=False)
        self.assertEqual(failed["error"]["code"], "workspace_not_initialized")
        self.assertFalse((self.a / ".cloud-servers").exists())
        self.assertTrue(self.cli(self.a, "operations")["ok"])
        self.assertFalse((self.a / ".cloud-servers").exists())
        initialize(self.a)
        (self.a / ".cloud-servers/config.json").write_text("broken")
        with self.assertRaises(Failure) as result:
            resolve_db(
                cwd=self.a, environ={"CLOUD_SERVERS_DB": str(self.root / "legacy.db")}
            )
        self.assertEqual(result.exception.code, "invalid_workspace")

    def test_nested_repository_does_not_inherit_parent(self):
        initialize(self.a)
        repo = self.a / "another-project"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: /a/worktree")
        with self.assertRaises(Failure):
            resolve_db(cwd=repo, environ={})
        initialize(repo)
        self.assertEqual(
            resolve_db(cwd=repo, environ={}), repo / ".cloud-servers/inventory.sqlite3"
        )

    def test_explicit_workspace_and_database_selection(self):
        self.cli(self.a, "--workspace", str(self.a), "init", str(self.b), ok=False)
        self.assertFalse((self.b / ".cloud-servers").exists())
        a = initialize(self.a)
        b = initialize(self.b)
        self.assertEqual(
            self.cli(self.a, "--workspace", str(self.b), "scope")["data"]["id"], b["id"]
        )
        self.assertEqual(
            resolve_db(
                workspace=self.a, cwd=self.b, environ={"CLOUD_SERVERS_DB": "legacy.db"}
            ),
            Path(a["database"]),
        )
        with self.assertRaises(Failure):
            resolve_db(db="legacy.db", workspace=self.a)
        missing = self.root / "missing"
        with self.assertRaises(Failure):
            resolve_db(workspace=missing, cwd=self.a)
        explicit = self.cli(self.a, "--db", str(self.root / "legacy.db"), "scope")[
            "data"
        ]
        self.assertEqual(explicit["kind"], "explicit")
        self.assertEqual(
            resolve_db(cwd=self.b, environ={"CLOUD_SERVERS_DB": "legacy.db"}),
            Path(b["database"]),
        )
        self.assertEqual(
            resolve_db(cwd=self.root, environ={"CLOUD_SERVERS_DB": "legacy.db"}),
            self.root / "legacy.db",
        )

    def test_rpc_uses_bound_project_after_cwd_changes(self):
        a = initialize(self.a)
        initialize(self.b)
        invoke(a["database"], "group.add", {"id": "lab", "data": {"name": "A only"}})
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(self.a), "rpc"],
            input=json.dumps({"operation": "snapshot"}),
            cwd=self.b,
            env=self.env,
            text=True,
            capture_output=True,
        )
        result = json.loads(process.stdout)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["workspace"]["id"], a["id"])
        self.assertEqual(result["data"]["groups"][0]["name"], "A only")


if __name__ == "__main__":
    unittest.main()
