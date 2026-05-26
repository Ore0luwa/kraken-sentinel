"""
detectors/whale.py — Detects large single trades above a USD threshold.

Flags any trade where price × qty > whale_threshold_usd.
Severity:
    CRITICAL  — > 10× threshold  (mega whale)
    HIGH      — > 5× threshold
    MEDIUM    — > 1× threshold
"""

from utils.logger import setup_logger

logger = setup_logger("whale")


class WhaleDetector:
    def __init__(self, config: dict):
        self.threshold = config.get("whale_threshold_usd", 50_000)

    def check(self, trade: dict) -> dict | None:
        vol = trade["volume_usd"]
        if vol < self.threshold:
            return None

        if vol >= self.threshold * 10:
            severity, emoji = "CRITICAL", "🐳"
        elif vol >= self.threshold * 5:
            severity, emoji = "HIGH", "🐋"
        else:
            severity, emoji = "MEDIUM", "🐋"

        return {
            "type":          "WHALE",
            "emoji":         emoji,
            "severity":      severity,
            "symbol":        trade["symbol"],
            "side":          trade["side"],
            "volume_usd":    vol,
            "price":         trade["price"],
            "qty":           trade["qty"],
            "ord_type":      trade["ord_type"],
            "trade_id":      trade["trade_id"],
            "timestamp":     trade["timestamp"],
            "timestamp_str": trade["timestamp_str"],
            "message": (
                f"{emoji} WHALE {severity} | {trade['symbol']} | "
                f"{trade['side'].upper()} ${vol:,.0f} "
                f"@ ${trade['price']:,.4f} | qty={trade['qty']:.4f}"
            ),
        }
