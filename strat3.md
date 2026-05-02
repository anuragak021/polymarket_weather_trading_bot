# Polymarket 11-Bin Weather Temperature Markets AI Trading Bot Specification

**Source Post**: https://x.com/zostaff/status/2049152318742917594  
**Author**: @zostaff  
**Trading Profile**: https://polymarket.com/?r=zostaff  
**Telegram Channel**: https://t.me/zostaffsmartarc

---

## Core Thesis
Most Polymarket markets are noise (elections, sports, meme events). Prices there depend on Twitter, insiders, and crowd emotion. AI is useless there for the same reason it's useless in poker against drunks: you can't model irrationality.

**Weather markets are different.**  
Resolution comes from a specific weather station. NOAA and ECMWF forecasts are public, bins are fixed, emotion is zero. It's a rare category where outcome is determined by physics, not by mood.

Exactly the kind of problem AI solves better than humans: take six models, the meteorologist's forecast discussion text, the station's climatology, and synthesize one probability distribution. A human won't do that. A bot does it every day.

---

## The Setup
Polymarket runs **11-bin temperature markets**, resolved against NWS data.  
NOAA forecasts are public, market prices are public, bins are fixed.

If an AI builds a probability distribution that beats the market's pricing, there's edge. If not, there isn't.

---

## Three-Layer Strategy
1. **Core** – Enter bins where the model sees **>10pp edge** against market price.  
   Position size: **fractional Kelly** (25% of full Kelly).

2. **Hedge** – On high-uncertainty days, buy cheap tail-bins as insurance. Small stake, huge payout if it lands.

3. **Skip** – If model and market agree, do nothing.

---

## Backtesting & Validation (Must Be Implemented)
- 240-day backtest
- Train/test split (first 160 days train, last 80 days test)
- Walk-forward validation
- Sensitivity analysis
- Comparison vs ARIMA, XGBoost, and Ensemble baselines
- Full code must be reproducible (`weather_bot.py`)
- Every figure (calibration, equity curve, sensitivity heatmap, etc.) must be generated

---

## Claude Prompt Template (Critical – Feed This Exactly)
The prompt template that actually works (this is the exact thing missing from every other tutorial):

> [Insert the full Claude system prompt here – the post says “The Claude prompt. What actually goes to the API.” – the AI implementing this must create the complete, battle-tested prompt that includes:]
> - Recent forecast bias (last 14 days error)
> - Regime uncertainty signal
> - NWS discussion text parsing
> - Output format: Probability core (20 lines) + (mean, std) + regime_uncertainty

Key tricks built into the prompt:
- Recent forecast bias: feed the model its own error over the last 14 days. Claude corrects bias explicitly.
- `regime_uncertainty`: explicit signal of high uncertainty. On "high" the hedge layer activates automatically.
- NWS discussion text: Claude parses meteorologist notes about model disagreement, fronts, and risks better than any numerical model.

---

## Probability Distribution & Edge Calculation
The model's (mean, std) forecast becomes a bin distribution via the Gaussian CDF:

```math
P(bin_i) = \Phi\left(\frac{upper_i - \mu}{\sigma}\right) - \Phi\left(\frac{lower_i - \mu}{\sigma}\right)
For each bin, the edge against market price:
$$edge = model_prob - market_prob
$$
Only trade when edge > 0.10 (10 percentage points).

Calibration Check (Test Zero)
Before any edge or P&L:

When the model says “30%”, does the outcome actually happen ~30% of the time?
The AI model (cyan) must track the diagonal closely. Naive baseline (rose) falls apart at mid-range probabilities.

If calibration fails, nothing else matters.

Position Sizing: Fractional Kelly (25%)
Not flat-bet. Not all-in.
$$f = 0.25 \times \frac{edge}{b}
$$
where b is the payout multiple ($1 payout for a market_prob stake).
Larger edge → larger fraction. Tiny edge automatically sizes the bet near zero.

Hedge Layer Logic
Models are wrong sometimes. On fat-tail days (actual temperature lands in a corner bin both market and model underweighted), core bet loses.
Hedges only fire on high-uncertainty days:

Model's std is elevated, OR
Claude returns regime_uncertainty: "high"

On normal days → no hedges.
On uncertain days → buy a lot of tail coverage cheaply.

Risk & Performance Metrics (Professional Standard)
Must compute and display:

Sharpe ratio (mean daily return / std of daily returns, annualized)
Sortino ratio (only downside volatility)
Calmar ratio (annualized return / max drawdown)
Max drawdown
Equity curve with all drawdowns highlighted

Target (from backtest):

AI Sharpe: +1.09
Max drawdown: -4.05%
Naive baseline collapses (Sharpe -7.26, DD -25.89%)


Out-of-Sample & Robustness Tests

Train on first 160 days, test on last 80 days
AI edge survives (Sharpe train +1.25 → test +1.10)
Sensitivity heatmap: EV threshold (5pp–20pp) × Kelly fraction (0.10–0.75) → every cell must show positive Sharpe


Baseline Comparison
Compare against:

ARIMA(1) + climatology
XGBoost (multi-feature)
Ensemble (naive + ARIMA + XGBoost)

Metrics: Brier score + Sharpe

Full Pipeline Summary (Six Conceptual Steps)

Fetch NOAA ensembles + NWS discussion text
Run Claude forecast prompt
Build probability distribution + edge
Apply core / hedge / skip logic
Fractional Kelly sizing
Record trade, update bias history, log metrics


Deliverables Required
Generate the complete production-ready codebase following this specification exactly:

weather_bot.py – full backtest + live trading mode
claude_prompt.txt – the exact prompt template used
All charts (calibration, equity curve, edge histogram, sensitivity heatmap, etc.)
.env.example (NOAA API, Polymarket CLOB2, Anthropic key, etc.)
Dry-run / demo mode first
Live trading mode (replace mock functions with real API calls)
README with exact setup steps

Everything must be modular, type-hinted, and reproducible in under a minute on a normal machine (numpy + scipy + matplotlib + anthropic SDK).
Generate the complete solution following this specification exactly.
