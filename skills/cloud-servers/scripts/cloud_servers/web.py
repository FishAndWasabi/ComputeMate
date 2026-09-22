from __future__ import annotations

import hmac
import json
import mimetypes
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .api import invoke
from .common import Failure, envelope, json_text


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db, token=None, assets=None):
        self.db_path = db
        self.token = token or secrets.token_urlsafe(32)
        self.assets = Path(assets) if assets else Path(__file__).parent / "web_dist"
        super().__init__(address, Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server_version = "CloudServers/0.1"

    def log_message(self, fmt, *args):
        # Never log URL query/fragment data or authorization headers.
        print(
            f"web: {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}",
            file=sys.stderr,
        )

    def respond(self, status, data, content_type="application/json; charset=utf-8"):
        body = (
            json.dumps(data, ensure_ascii=False).encode()
            if not isinstance(data, bytes)
            else data
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            self.respond(
                403, envelope(error=Failure("forbidden", "Invalid Host header"))
            )
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self.respond(
                403, envelope(error=Failure("forbidden", "Origin is not allowed"))
            )
            return False
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(token.encode(), self.server.token.encode()):
            self.respond(
                401,
                envelope(
                    error=Failure(
                        "unauthorized", "A valid local access token is required"
                    )
                ),
            )
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            if not self.authorized():
                return
            op = {
                "/api/v1/operations": "operations",
                "/api/v1/snapshot": "snapshot",
            }.get(path)
            if not op:
                self.respond(
                    404, envelope(error=Failure("not_found", "Unknown API route"))
                )
                return
            self.respond(200, invoke(self.server.db_path, op))
            return
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            self.respond(403, b"Invalid host", "text/plain")
            return
        root = self.server.assets.resolve()
        candidate = (
            root / ("index.html" if path == "/" else path.lstrip("/"))
        ).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            self.respond(
                404,
                b"Web assets unavailable. Run npm ci and npm run build at the project root.",
                "text/plain; charset=utf-8",
            )
            return
        self.respond(
            200,
            candidate.read_bytes(),
            mimetypes.guess_type(candidate.name)[0] or "application/octet-stream",
        )

    def do_POST(self):
        if not self.authorized():
            return
        if urlparse(self.path).path != "/api/v1/invoke":
            self.respond(404, envelope(error=Failure("not_found", "Unknown API route")))
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 2 * 1024 * 1024:
                raise ValueError("Request must contain 1 byte to 2 MiB")
            request = json.loads(self.rfile.read(size))
            if not isinstance(request, dict) or not isinstance(
                request.get("operation"), str
            ):
                raise ValueError("Expected operation and arguments")
            response = invoke(
                self.server.db_path, request["operation"], request.get("arguments", {})
            )
            self.respond(200, response)
        except (ValueError, UnicodeDecodeError) as exc:
            self.respond(400, envelope(error=Failure("invalid_argument", str(exc))))


def serve(db, port=8765, json_mode=False):
    if not 0 <= port <= 65535:
        raise Failure("invalid_argument", "Invalid TCP port")
    server = WebServer(("127.0.0.1", port), db)
    url = server.origin + "/#token=" + server.token
    print(
        json_text(envelope({"url": url}))
        if json_mode
        else f"ComputeMate: {url}\nPress Ctrl+C to stop.",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
