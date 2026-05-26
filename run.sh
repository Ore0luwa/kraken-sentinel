#!/bin/bash
# ============================================================
# KRAKEN SENTINEL — Event-Driven AI Trading Agent
# Architecture:
#   kraken ws trades (real-time stream) → signal detector →
#   Claude analyses → kraken paper buy/sell + futures paper
# Built per CLAUDE.md + AGENTS.md official guidance
# ============================================================
export PATH="$HOME/.npm-global/bin:$HOME/.cargo/bin:$PATH"
PYTHON=$(command -v python3 || command -v python)
WRITER="$HOME/kraken-sentinel/dashboard/state_writer.py"

emit() {
  [ -n "$PYTHON" ] && echo "$1" | $PYTHON "$WRITER" 2>/dev/null &
}

# ── Per-pair spot thresholds ─────────────────────────────────
BTC_WHALE=15000;  ETH_WHALE=3000;  DOG_WHALE=500
BTC_SWEEP=7;      ETH_SWEEP=5;     DOG_SWEEP=5
BTC_BOT=6;        ETH_BOT=4;       DOG_BOT=4
COOLDOWN=120

# ── State ────────────────────────────────────────────────────
declare -A LAST_SIDE
declare -A CONSEC_COUNT
declare -A LAST_ALERT_TIME
declare -A SIZE_BUFFER
TRADE_COUNT=0
ALERT_COUNT=0
START_TIME=$(date +%s)

# ── Display helpers ──────────────────────────────────────────
print_header() {
  local now=$(date -u '+%H:%M:%S UTC')
  local elapsed=$(( $(date +%s) - START_TIME ))
  local mins=$(( elapsed / 60 ))
  local secs=$(( elapsed % 60 ))
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  ⚡ KRAKEN SENTINEL  │  ${now}  │  up ${mins}m${secs}s"
  echo "║  trades: ${TRADE_COUNT}  │  alerts: ${ALERT_COUNT}  │  SPOT + FUTURES"
  echo "╚══════════════════════════════════════════════════════════════╝"
}

print_signal() {
  local ts=$(date -u '+%H:%M:%S')
  echo ""
  echo "  [$ts] 🚨 $1: $2"
  echo ""
}

print_trade() {
  local pair=$1 side=$2 price=$3 qty=$4 vol_usd=$5
  if [ "$side" = "buy" ]; then
    printf "  ▲ %-10s buy  @ \$%-14s qty=%-14s \$%s\n" "$pair" "$price" "$qty" "$vol_usd"
  else
    printf "  ▼ %-10s sell @ \$%-14s qty=%-14s \$%s\n" "$pair" "$price" "$qty" "$vol_usd"
  fi
}

# ── Per-pair thresholds ──────────────────────────────────────
get_thresholds() {
  if [[ "$1" == *"BTC"* ]]; then
    WHALE_USD=$BTC_WHALE; SWEEP_NEEDED=$BTC_SWEEP; BOT_NEEDED=$BTC_BOT
  elif [[ "$1" == *"ETH"* ]]; then
    WHALE_USD=$ETH_WHALE; SWEEP_NEEDED=$ETH_SWEEP; BOT_NEEDED=$ETH_BOT
  else
    WHALE_USD=$DOG_WHALE; SWEEP_NEEDED=$DOG_SWEEP; BOT_NEEDED=$DOG_BOT
  fi
}

# ── Trigger Claude analysis ──────────────────────────────────
trigger_claude() {
  local signal_type=$1
  local signal_detail=$2
  local trigger_pair=$3

  ALERT_COUNT=$((ALERT_COUNT + 1))
  print_header

  echo "  🤖 Triggering Claude analysis..."
  echo "  Signal: ${signal_type} on ${trigger_pair}"
  echo ""

  # Collect fresh snapshot — spot + futures
  local TICKER=$(kraken ticker BTCUSD ETHUSD DOGUSD -o json 2>/dev/null)
  local TRADES_BTC=$(kraken trades BTCUSD --count 20 -o json 2>/dev/null)
  local TRADES_ETH=$(kraken trades ETHUSD --count 20 -o json 2>/dev/null)
  local TRADES_DOG=$(kraken trades DOGUSD --count 20 -o json 2>/dev/null)
  local OB_BTC=$(kraken orderbook BTCUSD --count 10 -o json 2>/dev/null)
  local OB_ETH=$(kraken orderbook ETHUSD --count 10 -o json 2>/dev/null)
  local OB_DOG=$(kraken orderbook DOGUSD --count 10 -o json 2>/dev/null)
  local OHLC_BTC=$(kraken ohlc BTCUSD --interval 5 -o json 2>/dev/null)

  # Spot paper portfolio
  local SPOT_PORTFOLIO=$(kraken paper status -o json 2>/dev/null)
  local SPOT_HISTORY=$(kraken paper history -o json 2>/dev/null)

  # Futures paper portfolio
  local FUT_PORTFOLIO=$(kraken futures paper status -o json 2>/dev/null)
  local FUT_POSITIONS=$(kraken futures paper positions -o json 2>/dev/null)

  # Futures market data
  local FUT_BTC_TICKER=$(kraken futures ticker PF_XBTUSD -o json 2>/dev/null)
  local FUT_ETH_TICKER=$(kraken futures ticker PF_ETHUSD -o json 2>/dev/null)

  local PROMPT="You are KRAKEN SENTINEL — an autonomous AI trading agent on Kraken.
A real-time market signal was just detected. Analyse and act immediately.

SIGNAL: ${signal_type}
DETAIL: ${signal_detail}
TRIGGER PAIR: ${trigger_pair}
TIME: $(date -u '+%Y-%m-%d %H:%M:%S UTC')

═══════════════════════════════════════
SPOT MARKET DATA (via Kraken CLI)
═══════════════════════════════════════
TICKER: ${TICKER}
BTC TRADES (last 20): ${TRADES_BTC}
ETH TRADES (last 20): ${TRADES_ETH}
DOG TRADES (last 20): ${TRADES_DOG}
BTC ORDERBOOK: ${OB_BTC}
ETH ORDERBOOK: ${OB_ETH}
DOG ORDERBOOK: ${OB_DOG}
BTC OHLC (5min): ${OHLC_BTC}

═══════════════════════════════════════
FUTURES MARKET DATA (via Kraken CLI)
═══════════════════════════════════════
BTC PERP (PF_XBTUSD): ${FUT_BTC_TICKER}
ETH PERP (PF_ETHUSD): ${FUT_ETH_TICKER}

═══════════════════════════════════════
PORTFOLIOS
═══════════════════════════════════════
SPOT PAPER PORTFOLIO: ${SPOT_PORTFOLIO}
SPOT TRADE HISTORY: ${SPOT_HISTORY}
FUTURES PAPER PORTFOLIO: ${FUT_PORTFOLIO}
FUTURES OPEN POSITIONS: ${FUT_POSITIONS}

═══════════════════════════════════════
INVOCATION RULES (per CLAUDE.md)
═══════════════════════════════════════
- All commands: kraken <cmd> -o json 2>/dev/null
- Spot paper: kraken paper buy BTCUSD <vol> -o json 2>/dev/null
- Futures paper: kraken futures paper buy PF_XBTUSD <contracts> --leverage 5 --type market -o json 2>/dev/null
- Never use: kraken order buy/sell (live trading)
- Spot max 15% portfolio per trade
- Futures max 10% portfolio per position (leverage amplifies risk)
- Only trade if expected move > 0.52% spot or > 0.1% futures
- Always state invalidation price

SPOT MINIMUMS: BTCUSD=0.001 | ETHUSD=0.1 | DOGUSD=100000
FUTURES CONTRACTS: PF_XBTUSD (BTC perp) | PF_ETHUSD (ETH perp)
FUTURES LEVERAGE: use 3-5x maximum for safety

YOUR ANALYSIS:

1. SIGNAL CONFIRMATION
   Is the ${signal_type} on ${trigger_pair} real or noise?
   Support with data from trades and orderbook.

2. MARKET ANALYSIS (all pairs)
   BTC spot vs BTC futures — any basis divergence?
   ETH spot vs ETH futures — any basis divergence?
   DOG spot — trend and key levels?

3. WHALE / BOT / SWEEP FINDINGS
   Report any patterns across ALL pairs.

4. SPOT DECISIONS
   BTC: BUY/SELL/HOLD — reason — size — invalidation
   ETH: BUY/SELL/HOLD — reason — size — invalidation
   DOG: BUY/SELL/HOLD — reason — size — invalidation

5. FUTURES DECISIONS
   PF_XBTUSD: LONG/SHORT/HOLD — reason — contracts — leverage — invalidation
   PF_ETHUSD: LONG/SHORT/HOLD — reason — contracts — leverage — invalidation

6. EXECUTION
   Execute ALL spot decisions:
     kraken paper buy/sell <PAIR> <VOL> -o json 2>/dev/null

   Execute ALL futures decisions:
     kraken futures paper buy/sell PF_XBTUSD <contracts> --leverage <x> --type market -o json 2>/dev/null

   Then check both portfolios:
     kraken paper status -o json 2>/dev/null
     kraken futures paper status -o json 2>/dev/null

7. PORTFOLIO UPDATE
   Show spot + futures P&L before vs after.
   State what you are watching next on ALL pairs."

  echo "$PROMPT" | claude --allowedTools "Bash(kraken*)" -p "$(cat)"

  # Update portfolio state for dashboard
  local P=$(kraken paper status -o json 2>/dev/null)
  local FP=$(kraken futures paper status -o json 2>/dev/null)
  [ -n "$P" ]  && emit "{\"type\":\"portfolio\",\"data\":$P}"
  [ -n "$FP" ] && emit "{\"type\":\"futures_portfolio\",\"data\":$FP}"

  echo ""
  echo "  ── Resuming real-time stream ──"
  echo ""
}

# ── Signal detection ─────────────────────────────────────────
check_signals() {
  local pair=$1 side=$2 price=$3 qty=$4 vol_usd=$5
  local now=$(date +%s)
  local key="${pair//\//_}"
  get_thresholds "$pair"

  # 1. WHALE
  local whale_int=${vol_usd%.*}
  if [ "${whale_int:-0}" -ge "$WHALE_USD" ] 2>/dev/null; then
    local last=${LAST_ALERT_TIME["whale_${key}"]:-0}
    if [ $(( now - last )) -ge "$COOLDOWN" ]; then
      LAST_ALERT_TIME["whale_${key}"]=$now
      print_signal "WHALE" "${side^^} \$${vol_usd} on ${pair} @ \$${price}"
      emit "{\"type\":\"signal\",\"signal_type\":\"WHALE TRADE\",\"detail\":\"${side^^} \$${vol_usd} on ${pair} @ \$${price}\",\"pair\":\"$pair\"}"
      trigger_claude "WHALE TRADE" \
        "${side^^} of \$${vol_usd} on ${pair} @ \$${price} — single large trade" "$pair"
      return
    fi
  fi

  # 2. SWEEP
  if [ "${LAST_SIDE[$key]}" = "$side" ]; then
    CONSEC_COUNT[$key]=$(( ${CONSEC_COUNT[$key]:-0} + 1 ))
  else
    CONSEC_COUNT[$key]=1
    LAST_SIDE[$key]="$side"
  fi

  if [ "${CONSEC_COUNT[$key]}" -ge "$SWEEP_NEEDED" ]; then
    local last=${LAST_ALERT_TIME["sweep_${key}"]:-0}
    if [ $(( now - last )) -ge "$COOLDOWN" ]; then
      LAST_ALERT_TIME["sweep_${key}"]=$now
      CONSEC_COUNT[$key]=0
      print_signal "SWEEP" "${SWEEP_NEEDED}+ consecutive ${side^^}S on ${pair}"
      emit "{\"type\":\"signal\",\"signal_type\":\"SWEEP ${side^^}\",\"detail\":\"${SWEEP_NEEDED}+ consecutive ${side} trades on ${pair}\",\"pair\":\"$pair\"}"
      trigger_claude "DIRECTIONAL SWEEP" \
        "${SWEEP_NEEDED}+ consecutive ${side} trades on ${pair}" "$pair"
      return
    fi
  fi

  # 3. BOT
  local rounded_qty=$(echo "$qty" | awk '{printf "%.4f", $1}')
  local buf="${SIZE_BUFFER[$key]}|${rounded_qty}"
  local count=$(echo "$buf" | tr '|' '\n' | grep -c .)
  if [ "$count" -gt 20 ]; then
    buf=$(echo "$buf" | tr '|' '\n' | tail -20 | tr '\n' '|')
  fi
  SIZE_BUFFER[$key]="$buf"
  local repeat=$(echo "$buf" | tr '|' '\n' | grep -c "^${rounded_qty}$")
  if [ "${repeat:-0}" -ge "$BOT_NEEDED" ] 2>/dev/null; then
    local last=${LAST_ALERT_TIME["bot_${key}"]:-0}
    if [ $(( now - last )) -ge "$COOLDOWN" ]; then
      LAST_ALERT_TIME["bot_${key}"]=$now
      print_signal "BOT PATTERN" "qty=${rounded_qty} repeated ${repeat}x on ${pair}"
      emit "{\"type\":\"signal\",\"signal_type\":\"BOT PATTERN\",\"detail\":\"Size ${rounded_qty} repeated ${repeat}x on ${pair}\",\"pair\":\"$pair\"}"
      trigger_claude "BOT PATTERN" \
        "Size ${rounded_qty} repeated ${repeat}x in last 20 trades on ${pair}" "$pair"
      return
    fi
  fi
}

# ── Parse NDJSON trade line ──────────────────────────────────
parse_trade_line() {
  local line=$1
  local channel=$(echo "$line" | jq -r '.channel // empty' 2>/dev/null)
  [ "$channel" != "trade" ] && return
  local msg_type=$(echo "$line" | jq -r '.type // empty' 2>/dev/null)
  [ "$msg_type" != "update" ] && [ "$msg_type" != "snapshot" ] && return
  local trade_count=$(echo "$line" | jq '.data | length' 2>/dev/null)
  [ -z "$trade_count" ] || [ "$trade_count" = "0" ] && return

  for i in $(seq 0 $(( trade_count - 1 ))); do
    local symbol=$(echo "$line" | jq -r ".data[$i].symbol // empty" 2>/dev/null)
    local side=$(echo "$line"   | jq -r ".data[$i].side // empty"   2>/dev/null)
    local price=$(echo "$line"  | jq -r ".data[$i].price // 0"      2>/dev/null)
    local qty=$(echo "$line"    | jq -r ".data[$i].qty // 0"        2>/dev/null)
    [ -z "$symbol" ] || [ -z "$side" ] && continue
    TRADE_COUNT=$((TRADE_COUNT + 1))
    local vol_usd=$(echo "$price $qty" | awk '{printf "%.2f", $1 * $2}')
    print_trade "$symbol" "$side" "$price" "$qty" "$vol_usd"
    emit "{\"type\":\"trade\",\"symbol\":\"$symbol\",\"side\":\"$side\",\"price\":\"$price\",\"qty\":\"$qty\",\"volume_usd\":\"$vol_usd\"}"
    check_signals "$symbol" "$side" "$price" "$qty" "$vol_usd"
  done
}

# ── Startup ──────────────────────────────────────────────────
clear
echo ""
echo "  ╔══════════════════════════════════════════════════════════════╗"
echo "  ║        ⚡ KRAKEN SENTINEL — EVENT-DRIVEN AGENT              ║"
echo "  ║    Real-time stream → Signal detection → Claude trades      ║"
echo "  ║    SPOT: BTC/USD  ETH/USD  DOG/USD                          ║"
echo "  ║    FUTURES: PF_XBTUSD  PF_ETHUSD  (paper, up to 5x)        ║"
echo "  ║    Press Ctrl+C to stop                                     ║"
echo "  ╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check jq
if ! command -v jq &>/dev/null; then
  echo "  Installing jq..."
  sudo apt-get install -y jq -q
fi

# Check claude
if ! command -v claude &>/dev/null; then
  echo "  ERROR: claude not found. Run: export PATH=\$HOME/.npm-global/bin:\$PATH"
  exit 1
fi

# Check kraken
if ! command -v kraken &>/dev/null; then
  echo "  ERROR: kraken not found. Run: export PATH=\$HOME/.cargo/bin:\$PATH"
  exit 1
fi

echo "  ✓ kraken $(kraken --version 2>/dev/null)"
echo "  ✓ claude $(claude --version 2>/dev/null | head -1)"
echo ""

# Init spot paper account
echo "  Initialising spot paper account..."
kraken paper init --balance 10000 -o json 2>/dev/null | \
  jq -r '"  Spot paper: \(.action // "ready") — $\(.starting_balance // 10000)"' 2>/dev/null \
  || echo "  Spot paper: ready (already initialised)"

# Init futures paper account
echo "  Initialising futures paper account..."
kraken futures paper init --balance 10000 -o json 2>/dev/null | \
  jq -r '"  Futures paper: \(.action // "ready") — $\(.starting_balance // 10000)"' 2>/dev/null \
  || echo "  Futures paper: ready (already initialised)"

echo ""
echo "  ── Thresholds ─────────────────────────────────────────────────"
echo "  Whale:   BTC>\$${BTC_WHALE}  ETH>\$${ETH_WHALE}  DOG>\$${DOG_WHALE}"
echo "  Sweep:   BTC=${BTC_SWEEP} consecutive  ETH=${ETH_SWEEP}  DOG=${DOG_SWEEP}"
echo "  Bot:     BTC=${BTC_BOT} repeats  ETH=${ETH_BOT}  DOG=${DOG_BOT}"
echo "  Cooldown: ${COOLDOWN}s per pair"
echo "  ───────────────────────────────────────────────────────────────"
echo ""
echo "  Live trades (BTC/USD  ETH/USD  DOG/USD):"
echo ""

# ── Main stream loop ─────────────────────────────────────────
while true; do
  kraken ws trades BTC/USD ETH/USD DOG/USD -o json 2>/dev/null | while IFS= read -r line; do
    [ -z "$line" ] && continue
    parse_trade_line "$line"
  done
  echo ""
  echo "  [$(date -u '+%H:%M:%S')] Stream disconnected — reconnecting in 3s..."
  sleep 3
done
