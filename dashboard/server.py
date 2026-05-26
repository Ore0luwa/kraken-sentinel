#!/usr/bin/env python3
"""
dashboard/server.py — Kraken Sentinel data server.
Reads data/state.json written by run.sh and serves it
to the React dashboard over HTTP with CORS enabled.

Run: python3 dashboard/server.py
Dashboard: open dashboard/index.html in browser
"""

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")
PORT = 7373

DEFAULT_STATE = {
    "status": "waiting",
    "uptime": 0,
    "trade_count": 0,
    "alert_count": 0,
    "pairs": ["BTC/USD", "ETH/USD", "DOG/USD"],
    "prices": {},
    "trades": [],
    "alerts": [],
    "portfolio": {},
    "futures_portfolio": {},
    "signals": [],
    "agent_commentary": []
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/state":
            self._serve_state()
        elif self.path == "/health":
            self._json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _serve_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
            else:
                data = DEFAULT_STATE
        except Exception:
            data = DEFAULT_STATE
        self._json(data)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        pass  # silence access logs


if __name__ == "__main__":
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    print(f"✓ Kraken Sentinel data server running on http://localhost:{PORT}")
    print(f"  Serving: {STATE_FILE}")
    print(f"  Open dashboard/index.html in your browser")
    HTTPServer(("localhost", PORT), Handler).serve_forever()
