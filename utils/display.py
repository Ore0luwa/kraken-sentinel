"""
utils/display.py — Rich terminal dashboard for Kraken Sentinel.

Layout (refreshes 4×/sec):
┌─────────────────────────────────────────────────────────────────────┐
│  KRAKEN SENTINEL  |  pairs  |  uptime  |  🐋 N  🤖 N  🚀/🔻 N     │
├──────────────────────────────┬──────────────────────────────────────┤
│  Live Trade Feed             │  Alert Log                           │
├──────────────────────────────┴──────────────────────────────────────┤
│  Per-Pair Statistics                                                │
└─────────────────────────────────────────────────────────────────────┘

Falls back to plain print() when rich is not installed.
"""

import time
import threading
from collections import deque

try:
    from rich.console import Console
    from rich.live    import Live
    from rich.table   import Table
    from rich.panel   import Panel
    from rich.layout  import Layout
    from rich         import box
    RICH = True
except ImportError:
    RICH = False

ALERT_HIST = 50
TRADE_HIST = 30


class Dashboard:
    def __init__(self, config: dict, quiet: bool = False):
        self.config  = config
        self.quiet   = quiet
        self.pairs   = config["pairs"]

        self.alerts        = deque(maxlen=ALERT_HIST)
        self.recent_trades = deque(maxlen=TRADE_HIST)
        self.alert_counts  = {"WHALE": 0, "BOT": 0, "SWEEP": 0}
        self.start_time    = time.time()
        self._stats        = {}
        self._lock         = threading.Lock()
        self._live         = None
        self._all_alerts   = []

        if not RICH:
            print("[WARN] `rich` not installed — plain output only. pip install rich")

    def start(self):
        if RICH and not self.quiet:
            self._console = Console()
            self._live = Live(
                self._render(),
                console=self._console,
                refresh_per_second=4,
                screen=False,
                transient=False,
            )
            self._live.start()
            self._start_refresh()

    def _start_refresh(self):
        def _loop():
            while True:
                time.sleep(0.25)
                if self._live and self._live.is_started:
                    with self._lock:
                        self._live.update(self._render())
        threading.Thread(target=_loop, daemon=True).start()

    # ------------------------------------------------------------------ #

    def on_trade(self, trade: dict, alerts: list, stats: dict):
        with self._lock:
            self.recent_trades.append(trade)
            self._stats = stats
            for a in alerts:
                self.alerts.append(a)
                self._all_alerts.append(a)
                t = a.get("type", "")
                if t in self.alert_counts:
                    self.alert_counts[t] += 1
                if self.quiet or not RICH:
                    print(f"[{a.get('timestamp_str','')}] {a['message']}")

    # ------------------------------------------------------------------ #
    #  Render                                                              #
    # ------------------------------------------------------------------ #

    def _render(self):
        uptime = int(time.time() - self.start_time)
        h, rem = divmod(uptime, 3600)
        m, s   = divmod(rem, 60)
        up_str = f"{h:02d}:{m:02d}:{s:02d}"

        header = (
            f"[bold cyan]⚡ KRAKEN SENTINEL[/bold cyan]  "
            f"[dim]│ pairs: {', '.join(self.pairs)}"
            f"  │ uptime: {up_str}"
            f"  │ 🐋 {self.alert_counts['WHALE']}"
            f"  🤖 {self.alert_counts['BOT']}"
            f"  🚀/🔻 {self.alert_counts['SWEEP']}[/dim]"
        )

        # ── Alert log ────────────────────────────────────────────────── #
        alert_tbl = Table(
            title="[bold magenta]Alert Log[/bold magenta]",
            box=box.SIMPLE, show_header=True,
            header_style="bold magenta", expand=True,
        )
        alert_tbl.add_column("Time",    style="dim", width=12)
        alert_tbl.add_column("Type",    width=10)
        alert_tbl.add_column("Sev",     width=8)
        alert_tbl.add_column("Details", overflow="fold")

        for a in reversed(list(self.alerts)):
            col = "red" if a.get("severity") in ("HIGH", "CRITICAL") else "yellow"
            alert_tbl.add_row(
                a.get("timestamp_str", ""),
                f"[bold]{a.get('emoji','')} {a.get('type','')}[/bold]",
                f"[{col}]{a.get('severity','')}[/{col}]",
                self._detail(a),
            )

        # ── Trade feed ───────────────────────────────────────────────── #
        trade_tbl = Table(
            title="[bold]Live Trades[/bold]",
            box=box.SIMPLE, show_header=True,
            header_style="bold white",
        )
        trade_tbl.add_column("Time",  style="dim", width=12)
        trade_tbl.add_column("Pair",  width=12)
        trade_tbl.add_column("Side",  width=7)
        trade_tbl.add_column("Price", justify="right")
        trade_tbl.add_column("Qty",   justify="right")
        trade_tbl.add_column("USD",   justify="right")

        for t in reversed(list(self.recent_trades)):
            side_str = "[green]▲ buy[/green]" if t["side"] == "buy" else "[red]▼ sell[/red]"
            trade_tbl.add_row(
                t["timestamp_str"],
                t["symbol"],
                side_str,
                f"${t['price']:,.4f}",
                f"{t['qty']:.4f}",
                f"${t['volume_usd']:,.0f}",
            )

        # ── Stats ────────────────────────────────────────────────────── #
        stats_tbl = Table(
            title="[bold cyan]Pair Statistics[/bold cyan]",
            box=box.SIMPLE, show_header=True,
            header_style="bold cyan", expand=True,
        )
        stats_tbl.add_column("Pair")
        stats_tbl.add_column("Trades",     justify="right")
        stats_tbl.add_column("Volume USD", justify="right")
        stats_tbl.add_column("Last Price", justify="right")
        stats_tbl.add_column("Last Side")

        for pair in self.pairs:
            s = self._stats.get(pair, {})
            last = self._last_trade_for(pair)
            price_str = f"${last['price']:,.4f}" if last else "—"
            side_str  = (
                "[green]▲ buy[/green]"  if last and last["side"] == "buy"  else
                "[red]▼ sell[/red]"     if last and last["side"] == "sell" else "—"
            )
            stats_tbl.add_row(
                f"[bold]{pair}[/bold]",
                str(s.get("trades", 0)),
                f"${s.get('volume_usd', 0):,.0f}",
                price_str,
                side_str,
            )

        # ── Compose layout ───────────────────────────────────────────── #
        layout = Layout()
        layout.split_column(
            Layout(Panel(header, style="bold"), size=3, name="header"),
            Layout(name="body"),
            Layout(stats_tbl, size=len(self.pairs) + 4, name="footer"),
        )
        layout["body"].split_row(
            Layout(trade_tbl, name="trades"),
            Layout(alert_tbl, name="alerts"),
        )
        return layout

    # ------------------------------------------------------------------ #

    def _detail(self, a: dict) -> str:
        t = a.get("type")
        if t == "WHALE":
            return (f"{a['symbol']} {a['side'].upper()} "
                    f"${a['volume_usd']:,.0f} @ ${a['price']:,.4f}")
        if t == "BOT":
            return (f"{a['symbol']} cv={a.get('cv',0):.4f} "
                    f"repeat={a.get('size_repeat_ratio',0):.0%} "
                    f"conf={a.get('confidence',0):.0%}")
        if t == "SWEEP":
            return (f"{a['symbol']} {a['side'].upper()} "
                    f"×{a.get('sweep_count')} "
                    f"vol=${a.get('sweep_volume_usd',0):,.0f} "
                    f"Δ{a.get('price_delta_pct',0):+.3f}%")
        return a.get("message", "")

    def _last_trade_for(self, pair: str) -> dict | None:
        for t in reversed(list(self.recent_trades)):
            if t["symbol"] == pair:
                return t
        return None

    # ------------------------------------------------------------------ #

    def print_summary(self):
        sep = "═" * 62
        print(f"\n{sep}")
        print("  KRAKEN SENTINEL — SESSION SUMMARY")
        print(sep)
        uptime = int(time.time() - self.start_time)
        print(f"  Uptime       : {uptime}s")
        print(f"  🐋 Whale     : {self.alert_counts['WHALE']}")
        print(f"  🤖 Bot       : {self.alert_counts['BOT']}")
        print(f"  🚀🔻 Sweep   : {self.alert_counts['SWEEP']}")
        print(f"  Total alerts : {sum(self.alert_counts.values())}")
        highs = [a for a in self._all_alerts if a.get("severity") in ("HIGH", "CRITICAL")]
        if highs:
            print(f"\n  Top HIGH/CRITICAL alerts ({len(highs)} total):")
            for a in highs[-5:]:
                print(f"    {a['message']}")
        print(sep + "\n")
