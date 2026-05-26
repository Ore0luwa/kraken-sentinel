"""
core/stream.py — Live trade stream powered entirely by the Kraken CLI.

Uses:
    kraken ws trades <PAIR...> -o json

The CLI outputs NDJSON (one JSON object per line) to stdout.
Each line is a Kraken WebSocket v2 trade event envelope.

On startup we also call:
    kraken ticker <PAIRS> -o json      → seed last price / 24h stats
    kraken paper init --balance 10000  → if paper mode enabled

Reconnection: if the subprocess exits we restart it automatically
with exponential backoff (max 30s).
"""

import asyncio
import json
import time
import shlex
from datetime import datetime, timezone

from detectors.whale import WhaleDetector
from detectors.bot import BotDetector
from detectors.sweep import SweepDetector
from utils.logger import setup_logger
from utils.db import AlertDB
from utils.cli import kraken_json, kraken_stream_proc

logger = setup_logger("stream")

RECONNECT_BASE = 3
RECONNECT_MAX  = 30


class KrakenCLIStream:
    def __init__(self, config: dict, dashboard):
        self.config    = config
        self.dashboard = dashboard
        self.pairs     = config["pairs"]

        self.whale = WhaleDetector(config)
        self.bot   = BotDetector(config)
        self.sweep = SweepDetector(config)

        self.db    = AlertDB(config["export_db"])
        self.stats = {p: {"trades": 0, "volume_usd": 0.0, "last_price": 0.0} for p in self.pairs}

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    async def run(self):
        await self._seed_ticker()
        if self.config.get("paper_mode"):
            await self._paper_init()

        self.dashboard.start()

        delay = RECONNECT_BASE
        attempt = 0
        while True:
            attempt += 1
            logger.info(f"Starting kraken ws trades (attempt {attempt}) …")
            try:
                await self._stream_loop()
                delay = RECONNECT_BASE          # clean exit → reset backoff
            except Exception as exc:
                logger.error(f"Stream error: {exc}")

            logger.info(f"Reconnecting in {delay}s …")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    # ------------------------------------------------------------------ #
    #  Seed: pull snapshot via `kraken ticker` & `kraken trades`          #
    # ------------------------------------------------------------------ #

    async def _seed_ticker(self):
        """Use `kraken ticker` to get 24h stats and last price for each pair."""
        # kraken ticker takes pairs without slash: BTCUSD ETHUSD etc.
        flat_pairs = [p.replace("/", "") for p in self.pairs]
        args = ["ticker"] + flat_pairs + ["-o", "json"]
        data = await kraken_json(args)
        if not data:
            logger.warning("Ticker seed returned no data — will fill from stream")
            return

        for pair, info in data.items():
            # Normalise pair key back to PAIR/USD format for lookup
            matched = self._match_pair(pair)
            if matched and isinstance(info, dict):
                last = float(info.get("c", [0])[0] or 0)
                self.stats[matched]["last_price"] = last
                logger.info(f"Seeded {matched} last_price={last}")

    async def _paper_init(self):
        """Initialise paper trading account via Kraken CLI."""
        logger.info("Initialising paper trading account …")
        result = await kraken_json(["paper", "init", "--balance", "10000", "-o", "json"])
        if result:
            logger.info(f"Paper account ready: {result}")
        else:
            logger.warning("Paper init returned no data")

    # ------------------------------------------------------------------ #
    #  Main stream loop: `kraken ws trades <pairs> -o json`               #
    # ------------------------------------------------------------------ #

    async def _stream_loop(self):
        """
        Spawn: kraken ws trades BTC/USD ETH/USD DOGE/USD -o json
        Read NDJSON lines and dispatch each trade event.
        """
        cmd_args = ["ws", "trades"] + self.pairs + ["-o", "json"]
        proc = await kraken_stream_proc(cmd_args)

        logger.info(f"CLI PID {proc.pid} streaming {self.pairs}")

        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    # EOF — process ended
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                await self._handle_line(line)
        finally:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()

    # ------------------------------------------------------------------ #
    #  Parse NDJSON line from kraken ws trades                            #
    # ------------------------------------------------------------------ #

    async def _handle_line(self, line: str):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON line: {line[:120]}")
            return

        channel  = msg.get("channel")
        msg_type = msg.get("type")

        if channel != "trade":
            return
        if msg_type not in ("snapshot", "update"):
            return

        for trade_raw in msg.get("data", []):
            await self._process_trade(trade_raw)

    # ------------------------------------------------------------------ #
    #  Process a single trade event                                        #
    # ------------------------------------------------------------------ #

    async def _process_trade(self, raw: dict):
        symbol   = raw.get("symbol", "?")
        side     = raw.get("side", "?")
        price    = float(raw.get("price", 0))
        qty      = float(raw.get("qty", 0))
        ord_type = raw.get("ord_type", "?")
        trade_id = raw.get("trade_id", 0)
        ts_str   = raw.get("timestamp", "")

        try:
            ts       = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_unix  = ts.timestamp()
        except Exception:
            ts_unix  = time.time()
            ts       = datetime.now(timezone.utc)

        volume_usd = price * qty

        # Update per-pair stats
        if symbol in self.stats:
            self.stats[symbol]["trades"]     += 1
            self.stats[symbol]["volume_usd"] += volume_usd
            self.stats[symbol]["last_price"]  = price

        trade = {
            "symbol":        symbol,
            "side":          side,
            "price":         price,
            "qty":           qty,
            "ord_type":      ord_type,
            "trade_id":      trade_id,
            "timestamp":     ts_unix,
            "timestamp_str": ts.strftime("%H:%M:%S.%f")[:-3],
            "volume_usd":    volume_usd,
        }

        alerts = []
        for detector in (self.whale, self.bot, self.sweep):
            result = detector.check(trade)
            if result:
                alerts.append(result)

        self.dashboard.on_trade(trade, alerts, self.stats)
        for alert in alerts:
            self.db.save(alert)
            # If paper mode: react to whale buys with a paper trade demo
            if self.config.get("paper_mode") and alert["type"] == "WHALE":
                asyncio.create_task(self._paper_react(alert))

    # ------------------------------------------------------------------ #
    #  Paper trade reaction to whale alerts                               #
    # ------------------------------------------------------------------ #

    async def _paper_react(self, alert: dict):
        """
        When a whale BUY is detected: place a small paper buy to demonstrate
        the CLI's paper trading capability in the video demo.
        """
        if alert["side"] != "buy":
            return
        pair_no_slash = alert["symbol"].replace("/", "")
        # Buy a tiny fraction — demo only
        args = ["paper", "buy", pair_no_slash, "0.001", "-o", "json"]
        result = await kraken_json(args)
        if result:
            logger.info(f"[PAPER] Followed whale on {alert['symbol']}: {result}")

    # ------------------------------------------------------------------ #
    #  Helper                                                              #
    # ------------------------------------------------------------------ #

    def _match_pair(self, raw_key: str) -> str | None:
        """Match a raw ticker key like 'XXBTZUSD' back to 'BTC/USD'."""
        clean = raw_key.upper().replace("X", "").replace("Z", "")
        for pair in self.pairs:
            base = pair.replace("/", "").upper()
            if clean == base or raw_key.upper() == base:
                return pair
        # fuzzy: last 3 chars match USD/EUR etc.
        for pair in self.pairs:
            if pair.replace("/", "") in raw_key.upper():
                return pair
        return None
