# ⚡ Kraken Sentinel

**Event-driven AI trading agent built with Kraken CLI + Claude Code**

Submitted for the [Kraken Agent Zero Promotion](https://support.kraken.com/articles/agent-zero-promotion)

## What it does

Watches live Kraken markets in real time using `kraken ws trades`.
When a signal fires — whale trade, directional sweep, or bot pattern —
Claude Code CLI instantly analyses the market and executes a paper trade.

## Tools used

- **Kraken CLI** — all market data and trade execution
- **Claude Code CLI** — AI reasoning and decision making

## Signals detected

| Signal | Description |
|---|---|
| 🐳 Whale | Single trade above USD threshold |
| 🚀🔻 Sweep | 5+ consecutive same-side trades |
| 🤖 Bot | Repeated identical order sizes |

## Run it

```bash
# Install Kraken CLI
curl --proto '=https' --tlsv1.2 -LsSf \
  https://github.com/krakenfx/kraken-cli/releases/latest/download/kraken-cli-installer.sh | sh

# Install Claude Code
npm install -g @anthropic-ai/claude-code --prefix ~/.npm-global

# Run
chmod +x run.sh
./run.sh
```

## Architecture

```
kraken ws trades BTC/USD ETH/USD DOG/USD
         ↓ real-time
   Signal detector (bash)
         ↓ on signal
   Claude Code analyses via Kraken CLI tools
         ↓
   kraken paper buy/sell executes
         ↓
   Returns to stream
```
