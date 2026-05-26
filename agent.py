#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║           KRAKEN SENTINEL AGENT  —  AI-Powered Trading Agent        ║
║                                                                      ║
║  Autonomous agent that loops continuously:                           ║
║    1. Pulls live market data via Kraken CLI                          ║
║    2. Detects whales, bots, and directional sweeps                   ║
║    3. Thinks out loud and makes trading decisions                    ║
║    4. Executes paper trades via Kraken CLI                           ║
║    5. Reports P&L after every cycle                                  ║
║                                                                      ║
║  Powered by: Kraken CLI + Claude Code                                ║
║  Built for:  Kraken Agent Zero Promotion — May 2026                  ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python3 agent.py                          # runs forever, Ctrl+C to stop
    python3 agent.py --cycles 5               # run 5 cycles then stop
    python3 agent.py --interval 30            # 30 seconds between cycles
    python3 agent.py --pairs BTCUSD ETHUSD DOGUSD
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.rule    import Rule
    from rich         import box
    from rich.table   import Table
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None

# ── Constants ─────────────────────────────────────────────────────────────── #

KRAKEN_BIN   = os.environ.get("KRAKEN_BIN", "kraken")
CLAUDE_BIN   = os.environ.get("CLAUDE_BIN", "claude")

# Kraken uses legacy pair names — normalise here
PAIR_MAP = {
    "BTC/USD":  "BTCUSD",
    "ETH/USD":  "ETHUSD",
    "DOG/USD":  "DOGUSD",
    "SOL/USD":  "SOLUSD",
    "XRP/USD":  "XRPUSD",
    "DOGE/USD": "DOGEUSD",
}

DEFAULT_PAIRS    = ["BTCUSD", "ETHUSD", "DOGUSD"]
DEFAULT_CYCLES   = 9999
DEFAULT_INTERVAL = 30

# ── Helpers ───────────────────────────────────────────────────────────────── #

def normalise_pair(pair: str) -> str:
    return PAIR_MAP.get(pair.upper(), pair.replace("/", "").upper())

def run_kraken(args: list) -> dict | list | str:
    """Run kraken CLI and return parsed JSON."""
    cmd = [KRAKEN_BIN] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw = r.stdout.strip()
        if not raw:
            return {"error": "empty response", "cmd": " ".join(args)}
        return json.loads(raw)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except json.JSONDecodeError:
        return {"error": "parse failed", "raw": r.stdout[:200]}
    except Exception as e:
        return {"error": str(e)}

def collect_market_data(pairs: list[str]) -> dict:
    """Pull all market data for a cycle via Kraken CLI."""
    data = {}

    # Ticker — all pairs at once
    ticker = run_kraken(["ticker"] + pairs + ["-o", "json"])
    data["ticker"] = ticker

    # Recent trades + orderbook per pair
    data["trades"]    = {}
    data["orderbook"] = {}
    data["ohlc"]      = {}

    for pair in pairs:
        trades = run_kraken(["trades", pair, "--count", "25", "-o", "json"])
        data["trades"][pair] = trades

        ob = run_kraken(["orderbook", pair, "--count", "10", "-o", "json"])
        data["orderbook"][pair] = ob

        ohlc = run_kraken(["ohlc", pair, "--interval", "5", "-o", "json"])
        # Trim to last 8 candles to save tokens
        if isinstance(ohlc, dict):
            for k, v in ohlc.items():
                if isinstance(v, list):
                    ohlc[k] = v[-8:]
        data["ohlc"][pair] = ohlc

    # Portfolio state
    data["portfolio"] = run_kraken(["paper", "status", "-o", "json"])

    return data

def build_claude_prompt(pairs: list[str], market_data: dict, cycle: int) -> str:
    """Build the structured prompt for Claude Code CLI."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    pairs_str = ", ".join(pairs)
    data_json = json.dumps(market_data, indent=2)

    return f"""You are KRAKEN SENTINEL — an expert autonomous crypto trading agent.
Cycle: {cycle} | Time: {now} | Pairs: {pairs_str}

You have been given live market data collected via the Kraken CLI.
Analyse it deeply and make one clear trading decision.

=== LIVE MARKET DATA (from Kraken CLI) ===
{data_json}
===========================================

YOUR ANALYSIS MUST COVER:

1. WHALE DETECTION
   - Identify any single trades with unusually large USD volume
   - Flag if volume > 5x the average trade size
   - Note the direction (buy/sell) and timing

2. BOT PATTERN DETECTION  
   - Look for repeated identical trade sizes
   - Look for inhuman timing regularity (many trades in milliseconds)
   - Flag if >60% of recent trades share the same size

3. DIRECTIONAL SWEEP DETECTION
   - Count consecutive same-side trades in the last 60 seconds
   - Calculate total sweep volume and price delta
   - Flag if 5+ consecutive buys or sells

4. ORDER BOOK ANALYSIS
   - Compare total bid depth vs ask depth
   - Identify large walls (support/resistance)
   - Note any thin liquidity zones

5. TREND (from OHLC)
   - Is price trending up, down, or sideways over last 8 candles?
   - Any momentum acceleration or exhaustion?

TRADING DECISION:
Based on your analysis, you MUST do one of:
   A) BUY — run: kraken paper buy <PAIR> <VOLUME> -o json
   B) SELL — run: kraken paper sell <PAIR> <VOLUME> -o json  
   C) HOLD — explain clearly why no trade is better than trading

RISK RULES:
- Never risk more than 15% of portfolio on one trade
- Always state your invalidation level (where you'd exit if wrong)
- State expected reward vs risk ratio

REPORT FORMAT (use exactly this structure):
📊 MARKET ANALYSIS
   [your findings for each pair]

🎯 SIGNALS DETECTED
   [list each whale/bot/sweep/imbalance found]

💡 DECISION: [BUY/SELL/HOLD]
   Pair: [pair]
   Size: [volume and USD value]
   Reason: [1-2 sentences]
   Invalidation: [price level]
   Risk/Reward: [ratio]

📈 PORTFOLIO UPDATE
   [show before/after if you traded]

After your analysis, execute your decision using the kraken CLI,
then run kraken paper status -o json to confirm the trade.
"""

def run_claude(prompt: str) -> bool:
    """Pass prompt to Claude Code CLI and stream output."""
    cmd = [CLAUDE_BIN, "-p", prompt]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            print(line, end="", flush=True)
        proc.wait()
        return proc.returncode == 0
    except FileNotFoundError:
        print(f"ERROR: '{CLAUDE_BIN}' not found. Is Claude Code installed?")
        return False
    except Exception as e:
        print(f"ERROR running Claude: {e}")
        return False

# ── Display ───────────────────────────────────────────────────────────────── #

def print_cycle_header(cycle: int, total: int, pairs: list[str]):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    if RICH:
        console.print(Rule(
            f"[bold cyan]⚡ KRAKEN SENTINEL[/bold cyan]  "
            f"[dim]cycle {cycle}/{total}  │  {', '.join(pairs)}  │  {now}[/dim]",
            style="cyan"
        ))
    else:
        print(f"\n{'='*70}")
        print(f"KRAKEN SENTINEL | cycle {cycle}/{total} | {', '.join(pairs)} | {now}")
        print('='*70)

def print_collecting():
    if RICH:
        console.print("[dim]📡 Collecting live market data via Kraken CLI…[/dim]")
    else:
        print("Collecting market data via Kraken CLI…")

def print_summary(cycle: int, start_time: float):
    portfolio = run_kraken(["paper", "status", "-o", "json"])
    elapsed   = int(time.time() - start_time)
    h, rem    = divmod(elapsed, 3600)
    m, s      = divmod(rem, 60)

    if RICH:
        console.print(Rule("[bold cyan]SESSION SUMMARY[/bold cyan]", style="cyan"))
        if isinstance(portfolio, dict) and "current_value" in portfolio:
            t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
            t.add_column("Metric")
            t.add_column("Value", justify="right")
            t.add_row("Cycles completed", str(cycle))
            t.add_row("Runtime",          f"{h:02d}:{m:02d}:{s:02d}")
            t.add_row("Starting balance", f"${portfolio.get('starting_balance', 0):,.2f}")
            t.add_row("Current value",    f"${portfolio.get('current_value', 0):,.2f}")
            t.add_row("Unrealised P&L",   f"${portfolio.get('unrealized_pnl', 0):,.2f}")
            t.add_row("Total trades",     str(portfolio.get('total_trades', 0)))
            console.print(t)
        else:
            console.print_json(json.dumps(portfolio))
    else:
        print(f"\nSESSION SUMMARY")
        print(f"Cycles: {cycle} | Runtime: {h:02d}:{m:02d}:{s:02d}")
        print(json.dumps(portfolio, indent=2))

# ── Pre-flight ────────────────────────────────────────────────────────────── #

def preflight(pairs: list[str]):
    import shutil

    errors = []
    if not shutil.which(KRAKEN_BIN):
        errors.append(f"'{KRAKEN_BIN}' CLI not found — install from github.com/krakenfx/kraken-cli")
    if not shutil.which(CLAUDE_BIN):
        errors.append(f"'{CLAUDE_BIN}' not found — run: npm install -g @anthropic-ai/claude-code --prefix ~/.npm-global")

    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    # Smoke test
    kr = subprocess.run([KRAKEN_BIN, "--version"], capture_output=True, text=True, timeout=5)
    cl = subprocess.run([CLAUDE_BIN, "--version"], capture_output=True, text=True, timeout=5)

    if RICH:
        console.print(f"[green]✓[/green] Kraken CLI: {kr.stdout.strip()}")
        console.print(f"[green]✓[/green] Claude Code: {cl.stdout.strip()}")
    else:
        print(f"✓ Kraken CLI: {kr.stdout.strip()}")
        print(f"✓ Claude Code: {cl.stdout.strip()}")

    # Init paper account
    r = run_kraken(["paper", "init", "--balance", "10000", "-o", "json"])
    if RICH:
        console.print(f"[dim]Paper account: {json.dumps(r)}[/dim]")
    else:
        print(f"Paper account: {json.dumps(r)}")

# ── Main loop ─────────────────────────────────────────────────────────────── #

def parse_args():
    p = argparse.ArgumentParser(description="Kraken Sentinel Agent")
    p.add_argument("--pairs",    nargs="+", default=DEFAULT_PAIRS,
                   help="Pairs to monitor e.g. BTCUSD ETHUSD DOGUSD")
    p.add_argument("--cycles",   type=int,  default=DEFAULT_CYCLES,
                   help=f"Number of cycles (default: {DEFAULT_CYCLES})")
    p.add_argument("--interval", type=int,  default=DEFAULT_INTERVAL,
                   help=f"Seconds between cycles (default: {DEFAULT_INTERVAL})")
    return p.parse_args()

def main():
    args   = parse_args()
    pairs  = [normalise_pair(p) for p in args.pairs]
    start  = time.time()

    preflight(pairs)

    if RICH:
        console.print(
            f"\n[bold green]✓ Agent running[/bold green]  "
            f"[dim]pairs={pairs}  cycles={args.cycles}  interval={args.interval}s[/dim]\n"
        )
    else:
        print(f"\n✓ Agent running | pairs={pairs} | cycles={args.cycles} | interval={args.interval}s\n")

    cycle = 0
    try:
        while cycle < args.cycles:
            cycle += 1
            print_cycle_header(cycle, args.cycles, pairs)

            # Step 1: collect all market data via Kraken CLI
            print_collecting()
            market_data = collect_market_data(pairs)

            # Step 2: build structured prompt
            prompt = build_claude_prompt(pairs, market_data, cycle)

            # Step 3: pass to Claude Code CLI — it reasons + executes trades
            run_claude(prompt)

            # Step 4: wait before next cycle
            if cycle < args.cycles:
                if RICH:
                    console.print(f"\n[dim]⏳ Next cycle in {args.interval}s …[/dim]\n")
                else:
                    print(f"\nNext cycle in {args.interval}s …\n")
                time.sleep(args.interval)

    except KeyboardInterrupt:
        if RICH:
            console.print("\n[yellow]Stopped by user[/yellow]")
        else:
            print("\nStopped.")

    finally:
        print_summary(cycle, start)

if __name__ == "__main__":
    main()
