# Weather Strategy Runbook

This repo is now configured as a weather-first Polymarket paper-trading bot. BTC and Kalshi code still exists, but `STRATEGY_MODE=weather` and `WEATHER_POLYMARKET_ONLY=true` keep this strategy focused on Polymarket weather markets.

## Strategy

The bot looks for weather temperature markets where the model probability differs from the market price by at least 10 percentage points.

Core rules:

- Trade only weather temperature markets discovered from Polymarket Gamma.
- Estimate YES probability from the Open-Meteo ensemble distribution.
- Support both threshold markets, such as "above 75F", and bin/range markets, such as "75-76F".
- Buy YES when `model_yes_probability - yes_price >= 0.10`.
- Buy NO when `(1 - model_yes_probability) - no_price >= 0.10`.
- Enter only when the side price is between `WEATHER_MIN_ENTRY_PRICE=0.40` and `WEATHER_MAX_ENTRY_PRICE=0.60`.
- Size with quarter-Kelly, capped by `WEATHER_MAX_TRADE_SIZE=0.50`.
- For the requested tiny bankroll, paper trades use `WEATHER_MIN_TRADE_SIZE=0.50`.
- Take profit when the held side reaches `WEATHER_TAKE_PROFIT_PRICE=0.75`.
- Stop out when the held side falls to `WEATHER_STOP_LOSS_PRICE=0.35`.
- Do not wait for settlement if the take-profit or stop-loss rule triggers first.

Important implementation detail: `Trade.size` is now dollars spent, not shares. The bot records `quantity = size / entry_price`, then calculates PnL from quantity, entry price, exit price, and settlement.

## Current Safety Defaults

The `.env.example` defaults are intentionally paper-first:

```env
STRATEGY_MODE=weather
SIMULATION_MODE=true
REAL_TRADING_ENABLED=false
INITIAL_BANKROLL=3
WEATHER_MIN_EDGE_THRESHOLD=0.10
WEATHER_MIN_ENTRY_PRICE=0.40
WEATHER_MIN_TRADE_SIZE=0.50
WEATHER_MAX_TRADE_SIZE=0.50
WEATHER_TAKE_PROFIT_PRICE=0.75
WEATHER_STOP_LOSS_PRICE=0.35
KALSHI_ENABLED=false
```

Real trading requires both `SIMULATION_MODE=false` and `REAL_TRADING_ENABLED=true`. If either is not set correctly, the bot will not submit real orders.

## Backtesting

Run the reproducible demo backtest:

```bash
python3 weather_bot.py backtest --output-dir artifacts/weather_strategy --bankroll 3 --edge-threshold 0.10 --kelly 0.25 --min-entry-price 0.40 --max-trade-size 0.50 --min-trade-size 0.50
```

Generated outputs:

- `artifacts/weather_strategy/summary.json`
- `artifacts/weather_strategy/trades.csv`
- `artifacts/weather_strategy/daily_equity.csv`
- `artifacts/weather_strategy/sensitivity.csv`
- `artifacts/weather_strategy/equity_curve.png`
- `artifacts/weather_strategy/drawdown.png`
- `artifacts/weather_strategy/calibration.png`
- `artifacts/weather_strategy/edge_histogram.png`
- `artifacts/weather_strategy/sensitivity_heatmap.png`

The built-in demo data is deterministic and useful for testing the machinery only. It is not evidence of live edge. A serious backtest must use recorded Polymarket orderbook snapshots, fills, and historical forecast rows.

CSV input schema for real backtests:

```csv
date,market_id,city,metric,direction,threshold_f,model_yes_prob,market_yes_price,max_yes_price_after_entry,min_yes_price_after_entry,settlement_value,regime_uncertainty,prob_arima,prob_xgboost,prob_ensemble
2026-05-01,example_market,nyc,high,above,75,0.62,0.49,0.78,0.41,1,normal,0.55,0.59,0.61
```

Required columns are `date`, `model_yes_prob`, `market_yes_price`, and `settlement_value`. The optional max/min columns make intraday take-profit and stop-loss testing more realistic.

## Paper Trading For One Week

Setup:

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn backend.api.main:app --reload --port 8000
```

Run one scan:

```bash
curl -X POST http://localhost:8000/api/run-scan
```

Start scheduled paper trading:

```bash
curl -X POST http://localhost:8000/api/bot/start
```

Stop it:

```bash
curl -X POST http://localhost:8000/api/bot/stop
```

Inspect all PnL and trade analysis:

```bash
curl http://localhost:8000/api/pnl-analysis
```

The scheduler scans weather markets every 5 minutes and checks paper exits every 60 seconds. Open paper positions close automatically when the target or stop is hit.

Minimum one-week promotion checklist:

- Run at least 7 calendar days in paper mode.
- Record at least 20 paper trades or keep collecting data if trade frequency is lower.
- Review `GET /api/pnl-analysis` every day.
- Confirm there are no repeated stale-price, parser, or API errors in `GET /api/events`.
- Confirm the strategy is profitable after slippage assumptions, not just before them.
- Confirm max drawdown is survivable with the planned real bankroll.
- Confirm the bot does not overtrade correlated bins from the same weather event.

## Real Money After One Week

Do not switch to real money unless the checklist above passes. With a planned real bankroll of about `$3`, the most important issue is Polymarket's share-based minimum order size. A `$0.50` paper trade at `$0.50` buys 1 share. Polymarket orderbooks can report `min_order_size` such as 5 shares, so the same real order may be rejected or force much larger risk than intended.

Real trading environment variables:

```env
SIMULATION_MODE=false
REAL_TRADING_ENABLED=true
POLYMARKET_PRIVATE_KEY=...
POLYMARKET_API_KEY=...
POLYMARKET_API_SECRET=...
POLYMARKET_API_PASSPHRASE=...
POLYMARKET_SIGNATURE_TYPE=0
POLYMARKET_FUNDER_ADDRESS=
POLYMARKET_CHECK_GEOBLOCK=true
POLYMARKET_MIN_ORDER_SIZE=5
```

The executor checks Polymarket's geoblock endpoint before real order placement. If your current location is blocked, orders should not be placed and you should not bypass geoblocking.

Real orders use fill-or-kill CLOB orders so the bot does not leave unmanaged resting orders on the book. A real trade is recorded only when the entry order reports a matched fill; real exits are marked closed only after the sell order reports a matched fill.

Practical real-money recommendation:

- Keep `REAL_TRADING_ENABLED=false` until the 7-day paper report is reviewed.
- If you only have `$3`, expect real order-size constraints to be the blocker.
- If a real market minimum forces more than `$0.50` risk, skip the trade.
- Never disable `POLYMARKET_CHECK_GEOBLOCK` to bypass location restrictions.

## Sources To Verify Before Real Trading

- Polymarket API overview: https://docs.polymarket.com/api-reference
- CLOB clients and Python SDK: https://docs.polymarket.com/developers/CLOB/clients
- CLOB order and tick-size rules: https://docs.polymarket.com/developers/CLOB/orders/onchain-order-info
- CLOB orderbook and `min_order_size`: https://docs.polymarket.com/trading/orderbook
- Geoblock check: https://docs.polymarket.com/developers/CLOB/geoblock
