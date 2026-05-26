#!/usr/bin/env python3
"""
dashboard/state_writer.py — reads events from run.sh via stdin
and writes/updates data/state.json for the dashboard to consume.

Usage (called from run.sh):
    echo "$EVENT_JSON" | python3 dashboard/state_writer.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")
MAX_TRADES  = 200
MAX_ALERTS  = 50
MAX_COMMENTARY = 20

def load():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "status": "running",
        "trade_count": 0,
        "alert_count": 0,
        "pairs": ["BTC/USD", "ETH/USD", "DOG/USD"],
        "prices": {},
        "trades": [],
        "alerts": [],
        "portfolio": {},
        "futures_portfolio": {},
        "agent_commentary": []
    }

def save(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)

def now_str():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def process(event, state):
    t = event.get("type", "")

    if t == "trade":
        trade = {
            "symbol":     event.get("symbol"),
            "side":       event.get("side"),
            "price":      event.get("price"),
            "qty":        event.get("qty"),
            "volume_usd": event.get("volume_usd"),
            "timestamp":  now_str()
        }
        state["trades"].insert(0, trade)
        state["trades"] = state["trades"][:MAX_TRADES]
        state["trade_count"] = state.get("trade_count", 0) + 1

        # Update last price
        sym = event.get("symbol", "")
        if sym:
            state["prices"][sym] = event.get("price")

    elif t == "signal":
        alert = {
            "type":      event.get("signal_type"),
            "detail":    event.get("detail"),
            "pair":      event.get("pair"),
            "timestamp": now_str()
        }
        state["alerts"].insert(0, alert)
        state["alerts"] = state["alerts"][:MAX_ALERTS]
        state["alert_count"] = state.get("alert_count", 0) + 1

    elif t == "commentary":
        entry = {
            "signal":    event.get("signal"),
            "text":      event.get("text"),
            "timestamp": now_str()
        }
        state["agent_commentary"].insert(0, entry)
        state["agent_commentary"] = state["agent_commentary"][:MAX_COMMENTARY]

    elif t == "portfolio":
        state["portfolio"] = event.get("data", {})

    elif t == "futures_portfolio":
        state["futures_portfolio"] = event.get("data", {})

    return state

if __name__ == "__main__":
    state = load()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            state = process(event, state)
            save(state)
        except json.JSONDecodeError:
            pass
