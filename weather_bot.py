"""Standalone weather strategy backtest and reporting CLI.

This script is intentionally self-contained so the strategy can be tested
without starting the FastAPI app.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.core.weather_strategy import size_weather_position


DEFAULT_OUTPUT_DIR = Path("artifacts/weather_strategy")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


@dataclass(frozen=True)
class BacktestConfig:
    initial_bankroll: float = 3.0
    edge_threshold: float = 0.10
    kelly_fraction: float = 0.25
    min_entry_price: float = 0.40
    max_entry_price: float = 0.60
    min_trade_size: float = 0.50
    max_trade_size: float = 0.50
    max_trade_fraction: float = 0.20
    allow_min_size_round_up: bool = True
    take_profit_price: float = 0.75
    stop_loss_price: float = 0.35
    exit_slippage: float = 0.01
    conservative_intraday_order: bool = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather strategy backtester")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest_parser = subparsers.add_parser("backtest", help="Run a weather strategy backtest")
    backtest_parser.add_argument("--input", type=Path, help="CSV with historical model/market rows")
    backtest_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    backtest_parser.add_argument("--bankroll", type=float, default=3.0)
    backtest_parser.add_argument("--edge-threshold", type=float, default=0.10)
    backtest_parser.add_argument("--kelly", type=float, default=0.25)
    backtest_parser.add_argument("--min-entry-price", type=float, default=0.40)
    backtest_parser.add_argument("--max-trade-size", type=float, default=0.50)
    backtest_parser.add_argument("--min-trade-size", type=float, default=0.50)
    backtest_parser.add_argument("--demo-days", type=int, default=240)
    backtest_parser.add_argument("--seed", type=int, default=7)

    args = parser.parse_args()

    if args.command == "backtest":
        config = BacktestConfig(
            initial_bankroll=args.bankroll,
            edge_threshold=args.edge_threshold,
            kelly_fraction=args.kelly,
            min_entry_price=args.min_entry_price,
            min_trade_size=args.min_trade_size,
            max_trade_size=args.max_trade_size,
        )
        if args.input:
            rows = load_backtest_csv(args.input)
            data_source = str(args.input)
        else:
            rows = generate_demo_history(days=args.demo_days, seed=args.seed)
            data_source = "deterministic_demo_data"

        report = run_full_backtest(rows, config, args.output_dir, data_source=data_source)
        print(json.dumps(report["summary"], indent=2))


def load_backtest_csv(path: Path) -> pd.DataFrame:
    """Load user-recorded historical data."""
    df = pd.read_csv(path)
    required = {"date", "model_yes_prob", "market_yes_price", "settlement_value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"]).dt.date
    for column in [
        "model_yes_prob",
        "market_yes_price",
        "settlement_value",
        "max_yes_price_after_entry",
        "min_yes_price_after_entry",
        "prob_arima",
        "prob_xgboost",
        "prob_ensemble",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "market_id" not in df.columns:
        df["market_id"] = [f"row_{idx}" for idx in range(len(df))]
    if "city" not in df.columns:
        df["city"] = "unknown"
    if "regime_uncertainty" not in df.columns:
        df["regime_uncertainty"] = "normal"

    return df


def generate_demo_history(days: int = 240, seed: int = 7) -> pd.DataFrame:
    """
    Generate deterministic demo rows.

    This is not proof of edge. It exists so the pipeline, reporting, calibration,
    and sensitivity machinery can be reproduced before real tick data exists.
    """
    rng = np.random.default_rng(seed)
    cities = ["nyc", "chicago", "miami", "los_angeles", "denver"]
    start = date.today() - timedelta(days=days)
    rows: List[dict] = []

    city_base = {
        "nyc": 70,
        "chicago": 66,
        "miami": 84,
        "los_angeles": 73,
        "denver": 68,
    }

    for day_idx in range(days):
        current_date = start + timedelta(days=day_idx)
        seasonal = 14 * math.sin(2 * math.pi * day_idx / 365)
        for city in cities:
            true_mean = city_base[city] + seasonal + rng.normal(0, 4.0)
            threshold = round(true_mean + rng.normal(0, 3.5))
            settlement_value = 1.0 if true_mean + rng.normal(0, 2.0) > threshold else 0.0

            latent_prob = _normal_cdf((true_mean - threshold) / 4.5)
            model_yes_prob = _clip(latent_prob + rng.normal(0, 0.060), 0.03, 0.97)
            market_yes_price = _clip(latent_prob + rng.normal(0, 0.090), 0.05, 0.95)

            max_price = _clip(market_yes_price + rng.uniform(0.02, 0.22), 0.01, 0.99)
            min_price = _clip(market_yes_price - rng.uniform(0.02, 0.22), 0.01, 0.99)
            regime = "high" if rng.random() < 0.18 else "normal"

            rows.append({
                "date": current_date,
                "market_id": f"demo_{city}_{current_date.isoformat()}",
                "city": city,
                "metric": "high",
                "direction": "above",
                "threshold_f": threshold,
                "model_yes_prob": round(model_yes_prob, 4),
                "market_yes_price": round(market_yes_price, 4),
                "max_yes_price_after_entry": round(max_price, 4),
                "min_yes_price_after_entry": round(min_price, 4),
                "settlement_value": settlement_value,
                "regime_uncertainty": regime,
                "prob_arima": round(_clip(latent_prob + rng.normal(0, 0.13), 0.03, 0.97), 4),
                "prob_xgboost": round(_clip(latent_prob + rng.normal(0, 0.10), 0.03, 0.97), 4),
                "prob_ensemble": round(_clip(latent_prob + rng.normal(0, 0.085), 0.03, 0.97), 4),
            })

    return pd.DataFrame(rows)


def run_full_backtest(
    rows: pd.DataFrame,
    config: BacktestConfig,
    output_dir: Path,
    *,
    data_source: str,
) -> Dict[str, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = rows.sort_values(["date", "market_id"]).reset_index(drop=True)

    trades = simulate_strategy(rows, config)
    daily = build_daily_equity(trades, config.initial_bankroll)
    metrics = compute_metrics(trades, daily, config.initial_bankroll)
    split = train_test_split_metrics(trades, rows, config.initial_bankroll)
    baselines = compute_baseline_metrics(rows)
    sensitivity = run_sensitivity(rows, config)

    trades.to_csv(output_dir / "trades.csv", index=False)
    daily.to_csv(output_dir / "daily_equity.csv", index=False)
    sensitivity.to_csv(output_dir / "sensitivity.csv", index=False)

    chart_paths = generate_charts(rows, trades, daily, sensitivity, output_dir)
    summary = {
        "data_source": data_source,
        "rows": int(len(rows)),
        "trades": int(len(trades)),
        "config": config.__dict__,
        "metrics": metrics,
        "train_test": split,
        "baselines": baselines,
        "charts": chart_paths,
        "trade_ledger": str(output_dir / "trades.csv"),
        "daily_equity": str(output_dir / "daily_equity.csv"),
        "sensitivity": str(output_dir / "sensitivity.csv"),
    }

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    return {"summary": summary, "trades": trades, "daily": daily}


def simulate_strategy(rows: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    bankroll = config.initial_bankroll
    trade_rows: List[dict] = []

    for _, row in rows.iterrows():
        decision = choose_side(row, config)
        if decision is None:
            continue

        side, win_prob, entry_price, edge = decision
        sized = size_weather_position(
            model_yes_probability=float(row["model_yes_prob"]),
            entry_price=entry_price,
            direction=side,
            bankroll=bankroll,
            min_trade_size=config.min_trade_size,
            max_trade_size=config.max_trade_size,
            max_trade_fraction=config.max_trade_fraction,
            allow_min_size_round_up=config.allow_min_size_round_up,
            kelly_fraction=config.kelly_fraction,
        )
        if not sized.can_trade:
            continue

        exit_price, exit_reason = choose_exit(row, side, config)
        if exit_price is None:
            settlement_value = float(row["settlement_value"])
            side_won = (side == "yes" and settlement_value == 1.0) or (side == "no" and settlement_value == 0.0)
            pnl = sized.quantity - sized.cash if side_won else -sized.cash
            exit_price = 1.0 if side_won else 0.0
            exit_reason = "settlement"
        else:
            pnl = sized.quantity * exit_price - sized.cash

        pnl = round(float(pnl), 4)
        bankroll += pnl
        result = "win" if pnl > 0 else "loss" if pnl < 0 else "push"
        settlement_value = float(row["settlement_value"])
        actual_win = (side == "yes" and settlement_value == 1.0) or (side == "no" and settlement_value == 0.0)

        trade_rows.append({
            "date": row["date"],
            "market_id": row["market_id"],
            "city": row.get("city", "unknown"),
            "side": side,
            "model_yes_prob": row["model_yes_prob"],
            "market_yes_price": row["market_yes_price"],
            "win_prob": round(win_prob, 4),
            "entry_price": round(entry_price, 4),
            "edge": round(edge, 4),
            "cash": sized.cash,
            "quantity": sized.quantity,
            "exit_price": round(exit_price, 4),
            "exit_reason": exit_reason,
            "settlement_value": row["settlement_value"],
            "actual_win": bool(actual_win),
            "pnl": pnl,
            "bankroll_after": round(bankroll, 4),
            "return_on_cost": round(pnl / sized.cash, 4) if sized.cash else 0.0,
            "result": result,
            "regime_uncertainty": row.get("regime_uncertainty", "normal"),
        })

    return pd.DataFrame(trade_rows)


def choose_side(row: pd.Series, config: BacktestConfig) -> Optional[Tuple[str, float, float, float]]:
    model_yes = float(row["model_yes_prob"])
    market_yes = float(row["market_yes_price"])
    yes_edge = model_yes - market_yes
    no_edge = (1.0 - model_yes) - (1.0 - market_yes)

    if yes_edge >= no_edge:
        side = "yes"
        win_prob = model_yes
        entry_price = market_yes
        edge = yes_edge
    else:
        side = "no"
        win_prob = 1.0 - model_yes
        entry_price = 1.0 - market_yes
        edge = no_edge

    if edge < config.edge_threshold:
        return None
    if entry_price < config.min_entry_price or entry_price > config.max_entry_price:
        return None
    return side, win_prob, entry_price, edge


def choose_exit(row: pd.Series, side: str, config: BacktestConfig) -> Tuple[Optional[float], Optional[str]]:
    if side == "yes":
        max_price = row.get("max_yes_price_after_entry")
        min_price = row.get("min_yes_price_after_entry")
    else:
        yes_max = row.get("max_yes_price_after_entry")
        yes_min = row.get("min_yes_price_after_entry")
        max_price = 1.0 - yes_min if pd.notna(yes_min) else np.nan
        min_price = 1.0 - yes_max if pd.notna(yes_max) else np.nan

    hit_target = pd.notna(max_price) and float(max_price) >= config.take_profit_price
    hit_stop = pd.notna(min_price) and float(min_price) <= config.stop_loss_price

    if hit_target and hit_stop and config.conservative_intraday_order:
        return max(0.0, config.stop_loss_price - config.exit_slippage), "stop_loss_conservative"
    if hit_target:
        return max(0.0, config.take_profit_price - config.exit_slippage), "take_profit"
    if hit_stop:
        return max(0.0, config.stop_loss_price - config.exit_slippage), "stop_loss"
    return None, None


def build_daily_equity(trades: pd.DataFrame, initial_bankroll: float) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["date", "daily_pnl", "equity", "drawdown"])

    daily = trades.groupby("date", as_index=False)["pnl"].sum().rename(columns={"pnl": "daily_pnl"})
    daily["equity"] = initial_bankroll + daily["daily_pnl"].cumsum()
    daily["peak"] = daily["equity"].cummax()
    daily["drawdown"] = daily["equity"] - daily["peak"]
    return daily


def compute_metrics(trades: pd.DataFrame, daily: pd.DataFrame, initial_bankroll: float) -> Dict[str, float]:
    if trades.empty:
        return {
            "total_pnl": 0.0,
            "roi": 0.0,
            "win_rate": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "brier_score": 0.0,
        }

    total_pnl = float(trades["pnl"].sum())
    returns = daily["daily_pnl"] / initial_bankroll if not daily.empty else pd.Series(dtype=float)
    sharpe = _annualized_sharpe(returns)
    sortino = _annualized_sortino(returns)
    max_drawdown = float(daily["drawdown"].min()) if not daily.empty else 0.0
    annual_return = returns.mean() * 252 if len(returns) else 0.0
    calmar = annual_return / abs(max_drawdown / initial_bankroll) if max_drawdown < 0 else 0.0
    brier = float(((trades["win_prob"] - trades["actual_win"].astype(float)) ** 2).mean())

    return {
        "total_pnl": round(total_pnl, 4),
        "roi": round(total_pnl / initial_bankroll, 4),
        "win_rate": round(float((trades["pnl"] > 0).mean()), 4),
        "trade_count": int(len(trades)),
        "avg_pnl": round(float(trades["pnl"].mean()), 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "max_drawdown": round(max_drawdown, 4),
        "brier_score": round(brier, 4),
    }


def train_test_split_metrics(trades: pd.DataFrame, rows: pd.DataFrame, initial_bankroll: float) -> Dict[str, dict]:
    ordered_dates = sorted(rows["date"].unique())
    train_dates = set(ordered_dates[:160])
    test_dates = set(ordered_dates[160:])

    output = {}
    for name, date_set in [("train_first_160_days", train_dates), ("test_last_80_days", test_dates)]:
        subset = trades[trades["date"].isin(date_set)].copy()
        daily = build_daily_equity(subset, initial_bankroll)
        output[name] = compute_metrics(subset, daily, initial_bankroll)
    return output


def compute_baseline_metrics(rows: pd.DataFrame) -> Dict[str, dict]:
    baselines = {}
    candidates = {
        "market": "market_yes_price",
        "arima_proxy": "prob_arima",
        "xgboost_proxy": "prob_xgboost",
        "ensemble_proxy": "prob_ensemble",
        "strategy_model": "model_yes_prob",
    }
    actual = rows["settlement_value"].astype(float)
    for name, column in candidates.items():
        if column not in rows.columns:
            continue
        probs = rows[column].astype(float).clip(0.01, 0.99)
        brier = float(((probs - actual) ** 2).mean())
        log_loss = float((-(actual * np.log(probs) + (1.0 - actual) * np.log(1.0 - probs))).mean())
        baselines[name] = {
            "brier_score": round(brier, 4),
            "log_loss": round(log_loss, 4),
        }
    return baselines


def run_sensitivity(rows: pd.DataFrame, base_config: BacktestConfig) -> pd.DataFrame:
    thresholds = np.round(np.arange(0.05, 0.201, 0.025), 3)
    kelly_values = np.round(np.arange(0.10, 0.751, 0.10), 3)
    records = []
    for threshold in thresholds:
        for kelly in kelly_values:
            config = BacktestConfig(
                initial_bankroll=base_config.initial_bankroll,
                edge_threshold=float(threshold),
                kelly_fraction=float(kelly),
                min_entry_price=base_config.min_entry_price,
                max_entry_price=base_config.max_entry_price,
                min_trade_size=base_config.min_trade_size,
                max_trade_size=base_config.max_trade_size,
                max_trade_fraction=base_config.max_trade_fraction,
                allow_min_size_round_up=base_config.allow_min_size_round_up,
                take_profit_price=base_config.take_profit_price,
                stop_loss_price=base_config.stop_loss_price,
                exit_slippage=base_config.exit_slippage,
            )
            trades = simulate_strategy(rows, config)
            daily = build_daily_equity(trades, config.initial_bankroll)
            metrics = compute_metrics(trades, daily, config.initial_bankroll)
            records.append({
                "edge_threshold": threshold,
                "kelly_fraction": kelly,
                "sharpe": metrics["sharpe"],
                "total_pnl": metrics["total_pnl"],
                "trade_count": metrics["trade_count"],
            })
    return pd.DataFrame(records)


def generate_charts(
    rows: pd.DataFrame,
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    sensitivity: pd.DataFrame,
    output_dir: Path,
) -> Dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = {}

    if not daily.empty:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(pd.to_datetime(daily["date"]), daily["equity"], color="#0f766e", linewidth=2)
        ax.set_title("Equity Curve")
        ax.set_ylabel("Bankroll ($)")
        ax.grid(True, alpha=0.25)
        paths["equity_curve"] = _save_plot(fig, output_dir / "equity_curve.png")

        fig, ax = plt.subplots(figsize=(9, 3))
        ax.fill_between(pd.to_datetime(daily["date"]), daily["drawdown"], 0, color="#dc2626", alpha=0.35)
        ax.set_title("Drawdown")
        ax.set_ylabel("Drawdown ($)")
        ax.grid(True, alpha=0.25)
        paths["drawdown"] = _save_plot(fig, output_dir / "drawdown.png")

    if not trades.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(trades["edge"], bins=24, color="#1d4ed8", alpha=0.80)
        ax.set_title("Traded Edge Histogram")
        ax.set_xlabel("Model probability - market price")
        ax.grid(True, alpha=0.25)
        paths["edge_histogram"] = _save_plot(fig, output_dir / "edge_histogram.png")

        paths["calibration"] = _plot_calibration(trades, output_dir / "calibration.png")

    if not sensitivity.empty:
        pivot = sensitivity.pivot(index="edge_threshold", columns="kelly_fraction", values="sharpe")
        fig, ax = plt.subplots(figsize=(9, 5))
        image = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([f"{c:.2f}" for c in pivot.columns], rotation=45)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([f"{i:.3f}" for i in pivot.index])
        ax.set_title("Sensitivity Heatmap: Sharpe")
        ax.set_xlabel("Kelly fraction")
        ax.set_ylabel("Edge threshold")
        fig.colorbar(image, ax=ax)
        paths["sensitivity_heatmap"] = _save_plot(fig, output_dir / "sensitivity_heatmap.png")

    if not rows.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(rows["model_yes_prob"] - rows["market_yes_price"], bins=30, color="#475569", alpha=0.8)
        ax.axvline(0.10, color="#16a34a", linestyle="--", label="10pp threshold")
        ax.set_title("All Candidate Edges")
        ax.set_xlabel("Model YES probability - market YES price")
        ax.legend()
        ax.grid(True, alpha=0.25)
        paths["candidate_edge_histogram"] = _save_plot(fig, output_dir / "candidate_edge_histogram.png")

    return paths


def _plot_calibration(trades: pd.DataFrame, path: Path) -> str:
    import matplotlib.pyplot as plt

    calibration = trades.copy()
    calibration["bucket"] = pd.cut(calibration["win_prob"], bins=np.linspace(0, 1, 11), include_lowest=True)
    grouped = calibration.groupby("bucket", observed=True).agg(
        predicted=("win_prob", "mean"),
        actual=("actual_win", "mean"),
        count=("result", "size"),
    )

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], color="#64748b", linestyle="--", label="perfect")
    ax.scatter(grouped["predicted"], grouped["actual"], s=grouped["count"] * 12, color="#0891b2", alpha=0.8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Calibration")
    ax.set_xlabel("Predicted win probability")
    ax.set_ylabel("Actual win rate")
    ax.grid(True, alpha=0.25)
    ax.legend()
    return _save_plot(fig, path)


def _save_plot(fig, path: Path) -> str:
    import matplotlib.pyplot as plt

    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return str(path)


def _annualized_sharpe(returns: pd.Series) -> float:
    if len(returns) < 2 or returns.std(ddof=1) == 0:
        return 0.0
    return float(returns.mean() / returns.std(ddof=1) * math.sqrt(252))


def _annualized_sortino(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if len(downside) < 2 or downside.std(ddof=1) == 0:
        return 0.0
    return float(returns.mean() / downside.std(ddof=1) * math.sqrt(252))


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


if __name__ == "__main__":
    main()
