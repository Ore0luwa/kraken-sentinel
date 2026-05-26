"""
detectors/bot.py — Detects bot / algorithmic trading fingerprints.

Two independent signals must BOTH fire to generate an alert
(reduces false positives from naturally fast liquid markets):

  1. TIMING REGULARITY
     Coefficient of variation (std/mean) of inter-trade arrival times
     across the last N trades for a symbol. Bots are unnaturally precise;
     humans are not. CV < bot_variance_threshold → suspicious.

  2. SIZE REPETITION
     Bots reuse exact lot sizes. If one rounded qty value accounts for
     > SIZE_REPEAT_RATIO of the last N trades → suspicious.

Confidence score 0–1 is computed from how extreme each signal is.
"""

import statistics
from collections import deque, Counter
from utils.logger import setup_logger

logger = setup_logger("bot")

WINDOW           = 20    # rolling trade window per symbol
SIZE_REPEAT_RATIO = 0.60  # fraction of trades with same size = suspicious


class BotDetector:
    def __init__(self, config: dict):
        self.variance_threshold = config.get("bot_variance_threshold", 0.08)
        self._timestamps: dict[str, deque] = {}
        self._sizes:      dict[str, deque] = {}

    def check(self, trade: dict) -> dict | None:
        sym = trade["symbol"]
        self._timestamps.setdefault(sym, deque(maxlen=WINDOW))
        self._sizes.setdefault(sym, deque(maxlen=WINDOW))

        self._timestamps[sym].append(trade["timestamp"])
        self._sizes[sym].append(round(trade["qty"], 4))

        if len(self._timestamps[sym]) < WINDOW:
            return None

        timing = self._check_timing(sym)
        sizing = self._check_size(sym)

        if not (timing and sizing):
            return None

        cv        = timing["cv"]
        top_size  = sizing["top_size"]
        top_ratio = sizing["ratio"]
        confidence = self._confidence(cv, top_ratio)

        severity = "HIGH" if confidence >= 0.85 else "MEDIUM"

        return {
            "type":              "BOT",
            "emoji":             "🤖",
            "severity":          severity,
            "symbol":            trade["symbol"],
            "side":              trade["side"],
            "volume_usd":        trade["volume_usd"],
            "price":             trade["price"],
            "qty":               trade["qty"],
            "trade_id":          trade["trade_id"],
            "timestamp":         trade["timestamp"],
            "timestamp_str":     trade["timestamp_str"],
            "confidence":        confidence,
            "cv":                cv,
            "repeated_size":     top_size,
            "size_repeat_ratio": top_ratio,
            "message": (
                f"🤖 BOT PATTERN {severity} | {trade['symbol']} | "
                f"timing_cv={cv:.4f}  size_repeat={top_ratio:.0%} "
                f"(qty={top_size})  confidence={confidence:.0%}"
            ),
        }

    # ------------------------------------------------------------------ #

    def _check_timing(self, sym: str) -> dict | None:
        ts        = list(self._timestamps[sym])
        intervals = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
        if not intervals:
            return None
        mean = statistics.mean(intervals)
        if mean == 0:
            return None
        stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0
        cv = stdev / mean
        return {"cv": cv} if cv <= self.variance_threshold else None

    def _check_size(self, sym: str) -> dict | None:
        counts = Counter(self._sizes[sym])
        top_size, top_count = counts.most_common(1)[0]
        ratio = top_count / len(self._sizes[sym])
        return {"top_size": top_size, "ratio": ratio} if ratio >= SIZE_REPEAT_RATIO else None

    @staticmethod
    def _confidence(cv: float, size_ratio: float) -> float:
        timing_score = max(0.0, 1.0 - (cv / 0.08))
        size_score   = min(1.0, (size_ratio - 0.60) / 0.40)
        return round(timing_score * 0.6 + size_score * 0.4, 3)
