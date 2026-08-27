"""Read-only HTTP surface for the isolated paper service."""

from __future__ import annotations

import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .service import StandalonePaperBot


class _Handler(BaseHTTPRequestHandler):
    bot: StandalonePaperBot

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "service": "astral-market-swarm", "mode": "paper"})
            return
        if path == "/api/state":
            self._send_json(self.bot.snapshot().public_dict())
            return
        if path == "/":
            state = self.bot.snapshot()
            self._send_html(
                "<!doctype html><html><head><title>Astral Market Swarm</title></head>"
                "<body><h1>Astral Market Swarm</h1>"
                f"<p>paper only · {state.demo_cash} {state.display_currency} demo cash</p>"
                f"<p>mode: {state.mode} · symbol: {state.symbol} · interval: {state.interval}</p>"
                f"<p>equity: {state.equity} · position: {state.position_quantity}</p>"
                f"<p>last signal: {state.last_signal}</p></body></html>"
            )
            return
        self.send_error(404)

    def _send_json(self, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body_text: str) -> None:
        body = body_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def create_http_server(
    bot: StandalonePaperBot,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Create a read-only server bound to the supplied bot instance."""

    class BoundHandler(_Handler):
        pass

    BoundHandler.bot = bot
    server = ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    return server
