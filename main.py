#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║              KRAKEN SENTINEL  —  v1.0                           ║
║     Whale · Bot · Directional Sweep Detector                    ║
║     Powered entirely by the Kraken CLI (github.com/krakenfx/kraken-cli) ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
    python main.py                              # BTC/USD, ETH/USD, DOGE/USD
    python main.py --pairs BTC/USD DOG/USD SOL/USD
    python main.py --whale 100000 --window 45 --sweep 6
    python main.py --paper                      # paper-trade mode demo
    python main.py --export                     # save alerts to data/alerts.db
    python main.py --quiet                      # plain output, no dashboard

Requirements:
    pip install rich
    curl --proto '=https' --tlsv1.2 -LsSf \\
      https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh
"""

import asyncio
import argparse
import signal
import sys

from utils.logger import setup_logger
from utils.cli_check import check_kraken_cli
from utils.display import Dashboard
from core.stream import KrakenCLIStream

logger = setup_logger("main")


def parse_args():
    p = argparse.ArgumentParser(
        description="Kraken Sentinel — Real-time Whale & Anomaly Detector via Kraken CLI"
    )
    p.add_argument(
        "--pairs", nargs="+",
        default=["BTC/USD", "ETH/USD", "DOGE/USD"],
        help="Pairs to monitor (default: BTC/USD ETH/USD DOGE/USD)",
    )
    p.add_argument("--whale", type=float, default=50_000,
                   help="Whale USD threshold (default: 50000)")
    p.add_argument("--window", type=int, default=60,
                   help="Sweep detection window seconds (default: 60)")
    p.add_argument("--sweep", type=int, default=5,
                   help="Min same-side trades for sweep (default: 5)")
    p.add_argument("--bot-variance", type=float, default=0.08,
                   help="Max timing CV to flag bot (default: 0.08)")
    p.add_argument("--paper", action="store_true",
                   help="Run paper-trade demo alongside monitoring")
    p.add_argument("--export", action="store_true",
                   help="Save alerts to data/alerts.db (SQLite)")
    p.add_argument("--quiet", action="store_true",
                   help="No dashboard, plain alert lines only")
    return p.parse_args()


async def main():
    args = parse_args()

    # Gate: make sure kraken CLI is installed
    check_kraken_cli()

    config = {
        "pairs": args.pairs,
        "whale_threshold_usd": args.whale,
        "sweep_window_seconds": args.window,
        "sweep_min_count": args.sweep,
        "bot_variance_threshold": args.bot_variance,
        "paper_mode": args.paper,
        "export_db": args.export,
        "quiet": args.quiet,
    }

    dashboard = Dashboard(config, quiet=args.quiet)
    stream = KrakenCLIStream(config, dashboard)

    def shutdown(sig, frame):
        logger.info("Shutting down…")
        dashboard.print_summary()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await stream.run()


if __name__ == "__main__":
    asyncio.run(main())
