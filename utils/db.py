"""utils/db.py — Optional SQLite persistence for all alerts."""

import json, os, sqlite3, time
from utils.logger import setup_logger

logger = setup_logger("db")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.db")

DDL = """
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT,
    severity    TEXT,
    symbol      TEXT,
    side        TEXT,
    volume_usd  REAL,
    price       REAL,
    confidence  REAL,
    message     TEXT,
    raw_json    TEXT,
    created_at  REAL
);
"""

class AlertDB:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._conn   = None
        if enabled:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            self._conn.execute(DDL)
            self._conn.commit()
            logger.info(f"Alert DB: {DB_PATH}")

    def save(self, alert: dict):
        if not self.enabled or not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT INTO alerts "
                "(type,severity,symbol,side,volume_usd,price,confidence,message,raw_json,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (alert.get("type"), alert.get("severity"), alert.get("symbol"),
                 alert.get("side"), alert.get("volume_usd"), alert.get("price"),
                 alert.get("confidence"), alert.get("message"),
                 json.dumps(alert), time.time()),
            )
            self._conn.commit()
        except Exception as e:
            logger.error(f"DB error: {e}")
