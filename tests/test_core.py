import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/cloud-servers/scripts"
sys.path.insert(0, str(SCRIPTS))
from cloud_servers.api import REGISTRY, invoke
from cloud_servers.common import Failure
from cloud_servers.transport import SSH, execute_local, in_environment, shell
from cloud_servers.remote import (
    fs_list,
    parse_probe,
    parse_slurm_table,
    slurm_submit,
    slurm_show,
    sync,
)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "inventory.db"

    def tearDown(self):
        self.temp.cleanup()

    def call(self, op, **args):
        value = invoke(self.db, op, args)
        self.assertTrue(value["ok"], value)
        return value["data"]

    def register(self):
        self.call("group.add", id="lab", data={"name": "实验组"})
        return self.call(
            "server.add",
            id="gpu",
            data={"name": "GPU", "ssh": {"alias": "test-gpu"}, "groups": ["lab"]},
        )

    def test_registry_archive_preserves_references(self):
        self.register()
        self.call(
            "environment.add",
            id="torch",
            data={
                "name": "Torch",
                "server": "gpu",
                "type": "conda",
                "selector": "torch",
            },
        )
        self.call("server.remove", id="gpu")
        self.assertEqual(self.call("server.list")["total"], 0)
        self.assertEqual(self.call("server.list", archived=True)["total"], 1)
        self.assertEqual(self.call("environment.get", id="torch")["server"], "gpu")

    def test_archived_group_does_not_prevent_server_edits(self):
        self.register()
        self.call("group.remove", id="lab")
        self.assertEqual(
            self.call("server.update", id="gpu", data={"name": "renamed"})["name"],
            "renamed",
        )

    def test_filters_and_pagination(self):
        self.register()
        self.call(
            "server.add",
            id="cpu",
            data={
                "name": "CPU",
                "ssh": {"host": "cpu.invalid"},
                "labels": ["inference"],
            },
        )
        self.assertEqual(self.call("server.list", group="lab")["total"], 1)
        self.assertEqual(
            self.call("server.list", query="inference")["items"][0]["id"], "cpu"
        )
        self.assertEqual(
            self.call("server.list", limit=1, offset=1)["items"][0]["id"], "gpu"
        )

    def test_optimistic_concurrency(self):
        self.register()

        def update(name):
            return invoke(
                self.db,
                "server.update",
                {"id": "gpu", "revision": 1, "data": {"name": name}},
            )

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(update, ["first", "second"]))
        self.assertEqual(sum(r["ok"] for r in results), 1)
        self.assertEqual(
            next(r for r in results if not r["ok"])["error"]["code"], "conflict"
        )
        self.assertEqual(self.call("server.get", id="gpu")["revision"], 2)

    def test_import_is_atomic_and_preserves_archive(self):
        self.register()
        document = {
            "schema_version": 1,
            "entities": {
                "group": [
                    {"id": "new", "name": "New"},
                    {"id": "lab", "name": "Existing"},
                ]
            },
        }
        result = invoke(self.db, "inventory.import", {"document": document})
        self.assertFalse(result["ok"])
        self.assertFalse(invoke(self.db, "group.get", {"id": "new"})["ok"])
        self.call("server.remove", id="gpu")
        exported = self.call("inventory.export")
        other = Path(self.temp.name) / "other.db"
        self.assertTrue(invoke(other, "inventory.import", {"document": exported})["ok"])
        self.assertTrue(invoke(other, "server.get", {"id": "gpu"})["data"]["archived"])

    def test_import_validates_references(self):
        result = invoke(
            self.db,
            "inventory.import",
            {
                "document": {
                    "schema_version": 1,
                    "entities": {
                        "server": [
                            {
                                "id": "bad",
                                "name": "bad",
                                "ssh": {"alias": "host"},
                                "groups": ["missing"],
                            }
                        ]
                    },
                }
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(self.call("server.list")["total"], 0)

    def test_failed_probe_retains_snapshot(self):
        self.register()
        with patch(
            "cloud_servers.remote.probe",
            return_value={"capabilities": [], "cpu_count": 32},
        ):
            self.call("probe", server="gpu")
        with patch(
            "cloud_servers.remote.probe",
            side_effect=Failure("connection_failed", "offline"),
        ):
            value = self.call("probe", server="gpu")
        self.assertFalse(value["reachable"])
        observation = value["observations"]["hardware"]
        self.assertEqual(observation["data"]["cpu_count"], 32)
        self.assertTrue(observation["stale"])
        self.assertEqual(observation["error"]["code"], "connection_failed")

    def test_selection_uses_fresh_compute_snapshots(self):
        self.register()
        data = {
            "cpu_count": 32,
            "memory": {"MemAvailable": 64 * 1024**3},
            "capabilities": [],
            "gpus": [
                {
                    "index": "0",
                    "name": "A100",
                    "memory_total_mib": 81920,
                    "memory_used_mib": 1000,
                    "utilization_percent": 0,
                }
            ],
        }
        with patch("cloud_servers.remote.probe", return_value=data):
            self.call("probe", server="gpu")
        self.assertEqual(
            self.call("server.select", min_gpus=1, min_gpu_memory_mib=40000)["total"], 1
        )
        self.call("server.update", id="gpu", data={"role": "login"})
        self.assertEqual(self.call("server.select", min_gpus=1)["total"], 0)

    def test_read_line_numbers_above_ten_thousand(self):
        self.register()
        with patch(
            "cloud_servers.remote.fs_read", return_value={"content": "late line"}
        ) as read:
            self.assertEqual(
                self.call(
                    "fs.read", server="gpu", path="/code", start=11000, end=11020
                )["content"],
                "late line",
            )
            self.assertEqual(read.call_args.args[2:4], (11000, 11020))

    def test_native_receipt_survives_local_registration_failure(self):
        self.register()
        with (
            patch(
                "cloud_servers.remote.slurm_submit",
                return_value={"backend": "slurm", "native_id": "123"},
            ),
            patch("cloud_servers.api.Context.native", side_effect=OSError("disk full")),
        ):
            value = self.call("slurm.submit", server="gpu", script="echo hi")
        self.assertEqual(value["native_id"], "123")
        self.assertIn("disk full", value["registration_error"])

    def test_docker_tmux_uses_container_cwd_only(self):
        self.register()
        self.call(
            "environment.add",
            id="container",
            data={
                "name": "container",
                "server": "gpu",
                "type": "docker",
                "selector": "training",
            },
        )
        with patch(
            "cloud_servers.remote.tmux_start",
            return_value={"backend": "tmux", "native_id": "docker-run"},
        ) as start:
            self.call(
                "tmux.start",
                server="gpu",
                environment="container",
                cwd="/inside/container",
                argv=["pwd"],
            )
            self.assertIsNone(start.call_args.args[3])
            self.assertIn("docker exec -w /inside/container", start.call_args.args[1])

    def test_cross_server_environment_rejected(self):
        self.register()
        self.call(
            "server.add", id="other", data={"name": "Other", "ssh": {"alias": "other"}}
        )
        self.call(
            "environment.add",
            id="env",
            data={"name": "Env", "server": "other", "type": "system"},
        )
        result = invoke(
            self.db, "exec", {"server": "gpu", "environment": "env", "argv": ["true"]}
        )
        self.assertEqual(result["error"]["code"], "invalid_argument")

    def test_conda_outside_path_preserves_literal_arguments(self):
        self.register()
        executable = Path(self.temp.name) / "Conda's executable"
        executable.write_text('#!/bin/sh\n[ "$1" = run ] || exit 80\nshift\n[ "$1" = --no-capture-output ] || exit 81\nshift\n[ "$1" = -p ] || exit 82\nshift\nexport CONDA_PREFIX="$1"\nshift\nexec "$@"\n')
        executable.chmod(0o700)
        prefix = "/env/a path's prefix; literal"
        environment = self.call("environment.add", id="explicit-conda", data={
            "name": "Conda outside PATH", "server": "gpu", "type": "conda",
            "selector": prefix, "conda_executable": str(executable),
        })
        payload = "literal; $(false) ' value"
        command = shell([sys.executable, "-c", "import json,os,sys; print(json.dumps([os.environ['CONDA_PREFIX'],sys.argv[1]]))", payload])
        result = execute_local(["bash", "-c", in_environment(command, environment)])
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(json.loads(result["stdout"]), [prefix, payload])
        for change in ({"conda_executable": "conda"}, {"type": "system"}):
            failed = invoke(self.db, "environment.update", {"id": "explicit-conda", "data": change})
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["error"]["code"], "invalid_argument")

    def test_invalid_values_return_json_errors(self):
        for args in (
            {"name": "bad", "ssh": {"alias": "-oProxyCommand=evil"}},
            {"name": "bad", "ssh": {"alias": "a; touch /tmp/bad"}},
            {"name": "bad", "ssh": {"alias": "ok"}, "groups": [42]},
        ):
            self.assertFalse(invoke(self.db, "server.add", {"data": args})["ok"])
        self.assertFalse(invoke(self.db, "server.list", {"limit": -1})["ok"])
        self.assertFalse(
            invoke(
                self.db, "fs.read", {"server": "x", "path": "a", "start": 10, "end": 1}
            )["ok"]
        )

    def test_cli_json_and_stdout_separation(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "cloud_servers.py"),
                "--db",
                str(self.db),
                "--json",
                "group",
                "add",
                "--id",
                "中文",
                "--data",
                '{"name":"组"}',
            ],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        value = json.loads(result.stdout)
        self.assertFalse(value["ok"])
        self.assertEqual(value["schema_version"], 1)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "cloud_servers.py"),
                "--db",
                str(self.db),
                "--json",
                "group",
                "add",
                "--id",
                "lab",
                "--data",
                '{"name":"组"}',
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["data"]["name"], "组")

    def test_all_described_operations_are_in_cli(self):
        from cloud_servers.cli import build_parser

        parser = build_parser()
        for name, spec in REGISTRY.items():
            args = name.split(".") + [
                "example" for f in spec["fields"].values() if f["positional"]
            ]
            self.assertEqual(vars(parser.parse_args(args))["action"], name)


class NativeTests(unittest.TestCase):
    def test_directory_listing_preserves_record_boundaries_and_special_names(self):
        from unittest.mock import Mock

        names = ["/code/tab\tname", "/code/new\nline", "/code/plain"]

        def remote_find(script):
            # Check the format after real Bash parsing, as the remote host sees it.
            received = execute_local(
                ["bash", "-s"],
                stdin='find() { printf "%s" "${@: -1}"; }\n' + script,
            )
            self.assertEqual(received["stdout"], r"%y\t%p\0")
            return {"stdout": "".join("f\t" + p + "\0" for p in names), "truncated": False}

        ssh = Mock()
        ssh.run.side_effect = remote_find
        result = fs_list(ssh, "/code", limit=2, offset=1)
        self.assertEqual(result["total"], 3)
        self.assertEqual([r["path"] for r in result["items"]], sorted(names)[1:])

    def test_ssh_error_is_uncertain_for_mutation_and_not_retried(self):
        ssh = SSH({"ssh": {"alias": "host"}})
        with patch(
            "cloud_servers.transport.execute_local",
            return_value={
                "exit_code": 255,
                "stdout": "",
                "stderr": "lost",
                "truncated": False,
            },
        ) as run:
            with self.assertRaises(Failure) as caught:
                ssh.run("sbatch x", mutating=True)
            self.assertEqual(caught.exception.code, "uncertain")
            self.assertEqual(run.call_count, 1)

    def test_native_command_timeout_is_uncertain(self):
        with self.assertRaises(Failure) as caught:
            execute_local(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                timeout=0.02,
                mutating=True,
            )
        self.assertEqual(caught.exception.code, "uncertain")

    def test_output_is_bounded(self):
        result = execute_local([sys.executable, "-c", 'print("x" * 1000)'], limit=40)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["stdout"]), 40)

    def test_probe_parser_handles_partial_metrics(self):
        sample = "\n__CS_cpu__\n16\n__CS_memory__\nMemTotal: 1000\nMemAvailable: 500\n__CS_gpu__\n0, NVIDIA A100, 81920, 1000, 3\n1, Other, N/A, N/A, N/A\n__CS_capabilities__\nbash\ntmux\n"
        value = parse_probe(sample)
        self.assertEqual(value["cpu_count"], 16)
        self.assertEqual(value["memory"]["MemAvailable"], 512000)
        self.assertIsNone(value["gpus"][1]["memory_total_mib"])

    def test_slurm_parsers_and_submission(self):
        from unittest.mock import Mock

        ssh = Mock()
        ssh.run.return_value = {
            "stdout": "998;clusterA\n",
            "stderr": "",
            "exit_code": 0,
        }
        result = slurm_submit(
            ssh,
            "python train.py",
            {"gpus": 2, "partition": "gpu"},
            "/project with spaces",
        )
        self.assertEqual(result["native_id"], "998")
        self.assertEqual(result["cluster"], "clusterA")
        self.assertIn("--parsable", ssh.run.call_args.args[0])
        self.assertIn("--gpus=2", ssh.run.call_args.args[0])
        ssh.run.return_value = {
            "stdout": "unexpected output",
            "stderr": "",
            "exit_code": 0,
        }
        with self.assertRaises(Failure) as caught:
            slurm_submit(ssh, "true", {})
        self.assertEqual(caught.exception.code, "uncertain")
        self.assertEqual(
            parse_slurm_table("998|RUNNING|node001\n", ["id", "state", "node"])[0][
                "state"
            ],
            "RUNNING",
        )

    def test_missing_slurm_accounting_stays_unknown(self):
        from unittest.mock import Mock

        ssh = Mock()
        ssh.run.return_value = {"stdout": "", "stderr": "not found", "exit_code": 1}
        result = slurm_show(ssh, "123")
        self.assertEqual(result["availability"], "unknown")
        self.assertEqual(result["accounting"], [])

    def test_rsync_is_preview_by_default_and_quotes_paths(self):
        ssh = SSH({"ssh": {"alias": "lab", "proxy_jump": "jump"}})
        with patch(
            "cloud_servers.remote.execute_local",
            return_value={
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "truncated": False,
            },
        ) as run:
            result = sync(ssh, "/tmp/code/", "/tmp/a ' b/", "push")
            argv = run.call_args.args[0]
            self.assertIn("--dry-run", argv)
            self.assertNotIn("--delete", argv)
            self.assertIn("-J jump", argv[argv.index("-e") + 1])
            self.assertTrue(result["preview"])


if __name__ == "__main__":
    unittest.main()
