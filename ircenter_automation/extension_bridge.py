"""Authenticated loopback bridge for the user's installed Chrome extension."""

import json
import queue
import re
import secrets
import threading
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import EXTENSION_VERSION
from .errors import WorkflowError
from .manual_entry import ManualEntryGuide


PORT = 38417
_EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")


class ExtensionBridge:
    def __init__(self, token: str | None, guide: ManualEntryGuide):
        if not token:
            raise WorkflowError("The browser extension has no pairing token; restart the app")
        self.token = token
        self.job_id = secrets.token_urlsafe(12)
        first, surname = guide.child_name.split(" ", 1)
        self.job = {
            "id": self.job_id,
            "child": {"first": first, "surname": surname},
            "fields": [{"name": field.portal_name, "value": field.value} for field in guide.fields],
        }
        self.statuses: queue.Queue[tuple[str, str]] = queue.Queue()
        self._claimed = False
        self._lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "ExtensionBridge":
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def _send(self, status: int, value: dict) -> None:
                encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                origin = self.headers.get("Origin", "")
                if _EXTENSION_ORIGIN.fullmatch(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _authorized(self) -> bool:
                return compare_digest(self.headers.get("Authorization", ""), f"Bearer {bridge.token}")

            def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib API
                self.send_response(204)
                origin = self.headers.get("Origin", "")
                if _EXTENSION_ORIGIN.fullmatch(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-IRCenter-Extension-Version")
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802 - stdlib API
                if not self._authorized():
                    self._send(403, {"error": "Forbidden"})
                    return
                target = urlparse(self.path)
                if target.path == "/version":
                    self._send(200, {"extensionVersion": EXTENSION_VERSION})
                elif target.path == "/alive":
                    job_id = parse_qs(target.query).get("id", [""])[0]
                    self._send(200, {"active": compare_digest(job_id, bridge.job_id)})
                elif target.path == "/job":
                    if self.headers.get("X-IRCenter-Extension-Version") != EXTENSION_VERSION:
                        bridge.statuses.put(("error", "Chrome extension is outdated. Load it from the installed app folder."))
                        self._send(409, {"error": "Chrome extension version does not match"})
                        return
                    with bridge._lock:
                        job = None if bridge._claimed else bridge.job
                        bridge._claimed = True
                    self._send(200, {"job": job})
                else:
                    self._send(404, {"error": "Not found"})

            def do_POST(self) -> None:  # noqa: N802 - stdlib API
                if not self._authorized():
                    self._send(403, {"error": "Forbidden"})
                    return
                if self.path != "/status":
                    self._send(404, {"error": "Not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2048:
                    self._send(400, {"error": "Invalid status"})
                    return
                try:
                    value = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeDecodeError):
                    self._send(400, {"error": "Invalid JSON"})
                    return
                if not isinstance(value, dict) or value.get("id") != bridge.job_id:
                    self._send(400, {"error": "Unknown job"})
                    return
                kind = value.get("type")
                detail = value.get("detail", "")
                if kind not in ("progress", "ready", "error") or not isinstance(detail, str) or len(detail) > 160:
                    self._send(400, {"error": "Invalid status"})
                    return
                bridge.statuses.put((kind, detail))
                self._send(200, {"ok": True})

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        except OSError as exc:
            raise WorkflowError(f"Local extension bridge port {PORT} is unavailable") from exc
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def next_status(self, timeout: float = 0.2) -> tuple[str, str] | None:
        try:
            return self.statuses.get(timeout=timeout)
        except queue.Empty:
            return None

    def __exit__(self, *_args) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=2)
