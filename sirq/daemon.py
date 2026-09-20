from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from .core import Observation
from .runtime import SIRQRuntime


class _Handler(BaseHTTPRequestHandler):
    runtime: SIRQRuntime

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send(200, {"status": "ok", "evaluator": "mock-jev"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/events":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            observation = Observation.from_dict(json.loads(self.rfile.read(length)))
            decision = self.runtime.process(observation)
            self._send(200, {"event": decision.event.to_dict(), "handler": decision.handler,
                             "allowed": decision.allowed, "reason": decision.reason})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def serve(runtime: SIRQRuntime, host: str = "127.0.0.1", port: int = 8099) -> ThreadingHTTPServer:
    handler = type("SIRQRequestHandler", (_Handler,), {"runtime": runtime})
    server = ThreadingHTTPServer((host, port), handler)
    return server
