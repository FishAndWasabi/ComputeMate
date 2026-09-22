import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import sys

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/cloud-servers/scripts")
)
from cloud_servers.web import WebServer
from cloud_servers.api import invoke
from cloud_servers.workspace import initialize


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        assets = Path(self.temp.name) / "assets"
        assets.mkdir()
        (assets / "index.html").write_text("<html>test</html>")
        project = Path(self.temp.name) / "Project-A"
        project.mkdir()
        self.binding = initialize(project)
        self.server = WebServer(
            ("127.0.0.1", 0), self.binding["database"], "test-token", assets
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, *, token="test-token", origin=None, body=None, host=None):
        headers = {"Authorization": "Bearer " + token}
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            self.server.origin + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        return urlopen(req)

    def test_token_origin_and_host_required(self):
        for kwargs, code in [
            ({"token": ""}, 401),
            ({"origin": "https://evil.example"}, 403),
            ({"host": "evil.example"}, 403),
        ]:
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/v1/snapshot", **kwargs)
            self.assertEqual(caught.exception.code, code)

    def test_shared_operations_and_mutation(self):
        with self.request("/api/v1/operations") as response:
            catalog = json.load(response)
        self.assertTrue(catalog["ok"])
        self.assertGreater(len(catalog["data"]["operations"]), 50)
        with self.request(
            "/api/v1/invoke",
            origin=self.server.origin,
            body={
                "operation": "group.add",
                "arguments": {"id": "lab", "data": {"name": "实验组"}},
            },
        ) as response:
            self.assertTrue(json.load(response)["ok"])
        with self.request("/api/v1/snapshot") as response:
            self.assertEqual(json.load(response)["data"]["groups"][0]["name"], "实验组")

    def test_static_traversal_and_api_validation(self):
        with self.assertRaises(HTTPError):
            self.request("/../db")
        with self.request(
            "/api/v1/invoke",
            body={"operation": "group.add", "arguments": {"data": {"name": 42}}},
        ) as response:
            self.assertFalse(json.load(response)["ok"])
        with self.request("/") as response:
            self.assertIn(
                "frame-ancestors", response.headers["Content-Security-Policy"]
            )

    def test_http_remains_bound_when_another_project_uses_the_same_id(self):
        other = Path(self.temp.name) / "Project-B"
        other.mkdir()
        other_db = initialize(other)["database"]
        invoke(other_db, "group.add", {"id": "lab", "data": {"name": "B"}})
        with self.request("/api/v1/invoke", body={
            "operation": "group.add", "arguments": {"id": "lab", "data": {"name": "A"}}
        }) as response:
            result = json.load(response)
        self.assertTrue(result["ok"])
        self.assertEqual(result["meta"]["scope"]["id"], self.binding["id"])
        with self.request("/api/v1/snapshot") as response:
            snapshot = json.load(response)["data"]
        self.assertEqual(snapshot["workspace"]["name"], "Project-A")
        self.assertEqual(snapshot["groups"][0]["name"], "A")
        self.assertEqual(invoke(other_db, "group.get", {"id": "lab"})["data"]["name"], "B")


if __name__ == "__main__":
    unittest.main()
