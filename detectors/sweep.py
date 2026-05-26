"""
detectors/sweep.py — Detects directional trade sweeps.

A sweep = N or more trades on the SAME side within a rolling time window.
This signals coordinated accumulation (buy sweep) or distribution (sell sweep).

Extra metrics reported:
    sweep_volume_usd   total notional of the sweep trades
    price_delta_pct    price movement from first to last trade in sweep
    acceleration       fraction of recent trades that are one-sided (0–1)

Cooldown prevents the same symbol+side from re-alerting within window/2 seconds.
"""

import time
from collections import deque
from utils.logger import setup_logger

logger = setup_logger("sweep")

MAX_HISTORY = 500


class SweepDetector:
    def __init__(self, config: dict):
        self.window    = config.get("sweep_window_seconds", 60)
        self.min_count = config.get("sweep_min_count", 5)
        self._history:    dict[str, deque] = {}
        self._last_alert: dict[str, float] = {}

    def check(self, trade: dict) -> dict | None:
        sym = trade["symbol"]
        self._history.setdefault(sym, deque(maxlen=MAX_HISTORY))
        self._history[sym].append(trade)

        now    = trade["timestamp"]
        cutoff = now - self.window
        recent = [t for t in self._history[sym] if t["timestamp"] >= cutoff]

        buys  = [t for t in recent if t["side"] == "buy"]
        sells = [t for t in recent if t["side"] == "sell"]

        for side, group in [("buy", buys), ("sell", sells)]:
            if len(group) < self.min_count:
                continue
            key  = f"{sym}:{side}"
            last = self._last_alert.get(key, 0)
            if now - last < self.window / 2:
                continue
            self._last_alert[key] = now
            return self._build_alert(sym, side, group, recent, now)

        return None

    def _build_alert(self, symbol, side, group, recent, now):
        sweep_vol     = sum(t["volume_usd"] for t in group)
        prices        = [t["price"] for t in group]
        price_delta   = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] else 0
        acceleration  = len(group) / max(len(recent), 1)
        severity      = "HIGH" if acceleration > 0.80 else "MEDIUM"
        emoji         = "🚀" if side == "buy" else "🔻"

        return {
            "type":             "SWEEP",
            "emoji":            emoji,
            "severity":         severity,
            "symbol":           symbol,
            "side":             side,
            "sweep_count":      len(group),
            "total_recent":     len(recent),
            "sweep_volume_usd": sweep_vol,
            "price_start":      prices[0],
            "price_end":        prices[-1],
            "price_delta_pct":  price_delta,
            "acceleration":     acceleration,
            "window_seconds":   self.window,
            "timestamp":        now,
            "timestamp_str":    group[-1]["timestamp_str"],
            "message": (
                f"{emoji} SWEEP {severity} | {symbol} | "
                f"{side.upper()} ×{len(group)} in {self.window}s | "
                f"vol=${sweep_vol:,.0f} | "
                f"Δprice={price_delta:+.3f}% | "
                f"accel={acceleration:.0%}"
            ),
        }
