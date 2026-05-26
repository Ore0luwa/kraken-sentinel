# ⚡ Kraken Sentinel Agent

An **autonomous AI trading agent** built with the Kraken CLI for the [Agent Zero Promotion](https://support.kraken.com/articles/agent-zero-promotion).

Claude thinks. Kraken CLI acts.

---

## How it works

Every cycle the agent:
1. **Calls Kraken CLI tools** — ticker, trades, orderbook, OHLC
2. **Thinks out loud** — spots whales, bots, sweeps, order book imbalance
3. **Makes a decision** — buy, sell, or hold with clear reasoning
4. **Executes via paper trading** — `kraken paper buy / sell`
5. **Reports P&L** — tracks performance across cycles

---

## Quickstart (5 minutes)

### 1 — Install Kraken CLI
```bash
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh
```

### 2 — Get Anthropic API key
https://console.anthropic.com → Create API key

### 3 — Install Python deps
```bash
python3 -m venv ~/sentinel-env
source ~/sentinel-env/bin/activate
pip install anthropic rich
```

### 4 — Run the agent
```bash
export ANTHROPIC_API_KEY="sk-ant-..."

# Default: BTC/USD, ETH/USD, DOG/USD — cycles every 20s
python3 agent.py

# Custom pairs + faster cycles (great for demo video)
python3 agent.py --pairs BTC/USD ETH/USD DOG/USD --cycles 10 --interval 15

# Run the anomaly detector alongside the agent (two terminals)
python3 main.py --pairs BTC/USD ETH/USD DOG/USD --whale 5000 --sweep 3
```

---

## What the agent sees

```
🔧 get_ticker({"pairs":["BTCUSD","ETHUSD","DOGUSD"]})
🔧 get_recent_trades({"pair":"BTCUSD","count":20})
🔧 get_orderbook({"pair":"BTCUSD","depth":10})
🔧 paper_status({})
🔧 paper_buy({"pair":"BTCUSD","volume":"0.001"})

╭─────────────────────────────────────────────────────╮
│ 📊 MARKET ANALYSIS                                  │
│ BTC at $74,724 — I spotted 9 consecutive buys in   │
│ 60s with $41,200 swept. Large bid wall at $74,500. │
│                                                     │
│ 🎯 SIGNAL: BUY SWEEP HIGH + order book support     │
│                                                     │
│ 💡 DECISION: Bought 0.001 BTC @ market             │
│ Risk: $74.72 (0.7% of portfolio) — within limits   │
│                                                     │
│ 📈 PORTFOLIO: $9,987 USD + 0.001 BTC               │
│ Unrealised P&L: +$0.21                             │
╰─────────────────────────────────────────────────────╯
```

---

## Project structure

```
kraken-sentinel/
├── agent.py        ← AI agent (Claude + Kraken CLI tools)  ← MAIN SUBMISSION
├── main.py         ← Anomaly detector dashboard (companion tool)
├── requirements.txt
├── README.md
├── core/
│   └── stream.py   ← kraken ws trades stream handler
├── detectors/
│   ├── whale.py    ← large trade detection
│   ├── bot.py      ← bot fingerprinting
│   └── sweep.py    ← directional sweep detection
└── utils/
    ├── cli.py      ← kraken CLI subprocess helpers
    ├── display.py  ← rich terminal dashboard
    └── db.py       ← SQLite alert persistence
```

---

## Kraken CLI commands used

| Tool | CLI command |
|---|---|
| Current prices | `kraken ticker BTCUSD ETHUSD DOGUSD -o json` |
| Recent trades | `kraken trades BTCUSD --count 20 -o json` |
| Order book | `kraken orderbook BTCUSD --count 10 -o json` |
| Candlesticks | `kraken ohlc BTCUSD --interval 5 -o json` |
| Portfolio | `kraken paper status -o json` |
| Paper buy | `kraken paper buy BTCUSD 0.001 -o json` |
| Paper sell | `kraken paper sell BTCUSD 0.001 -o json` |
| Init account | `kraken paper init --balance 10000 -o json` |
| Live stream | `kraken ws trades BTC/USD ETH/USD -o json` |

---

Built for the Kraken Agent Zero Promotion — May 2026 | MIT License
