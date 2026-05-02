"""Trade-level PnL analytics."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.core.weather_strategy import trade_entry_cost, trade_quantity
from backend.models.database import Trade


def build_pnl_analysis(db: Session) -> Dict[str, Any]:
    """Return full PnL summary plus one row of analysis per trade."""
    trades = db.query(Trade).order_by(Trade.timestamp.asc()).all()
    rows: List[Dict[str, Any]] = []
    realized_pnls: List[float] = []
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    exposure_open = 0.0
    by_market_type = defaultdict(lambda: {"trades": 0, "pnl": 0.0, "open_exposure": 0.0})

    for trade in trades:
        cost = trade_entry_cost(trade)
        quantity = trade_quantity(trade)
        pnl = float(trade.pnl) if trade.pnl is not None else None
        expected_value = None
        if trade.edge_at_entry is not None:
            expected_value = round(quantity * float(trade.edge_at_entry), 4)

        return_on_cost = None
        if pnl is not None and cost:
            return_on_cost = pnl / cost

        market_type = trade.market_type or "unknown"
        by_market_type[market_type]["trades"] += 1

        if trade.settled and pnl is not None:
            realized_pnls.append(pnl)
            equity += pnl
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
            by_market_type[market_type]["pnl"] += pnl
        else:
            exposure_open += cost
            by_market_type[market_type]["open_exposure"] += cost

        rows.append({
            "id": trade.id,
            "timestamp": trade.timestamp.isoformat() if trade.timestamp else None,
            "market_ticker": trade.market_ticker,
            "event_slug": trade.event_slug,
            "platform": trade.platform,
            "market_type": market_type,
            "direction": trade.direction,
            "execution_mode": getattr(trade, "execution_mode", "paper"),
            "entry_price": trade.entry_price,
            "exit_price": getattr(trade, "exit_price", None),
            "exit_reason": getattr(trade, "exit_reason", None),
            "entry_cost": round(cost, 4),
            "quantity": round(quantity, 6),
            "model_probability": trade.model_probability,
            "market_price_at_entry": trade.market_price_at_entry,
            "edge_at_entry": trade.edge_at_entry,
            "expected_value_at_entry": expected_value,
            "settled": trade.settled,
            "result": trade.result,
            "pnl": pnl,
            "return_on_cost": return_on_cost,
            "analysis": trade.analysis,
        })

    wins = [p for p in realized_pnls if p > 0]
    losses = [p for p in realized_pnls if p < 0]
    total_pnl = sum(realized_pnls)
    avg_pnl = total_pnl / len(realized_pnls) if realized_pnls else 0.0
    loss_abs = abs(sum(losses))
    profit_factor = sum(wins) / loss_abs if loss_abs > 0 else None
    pnl_std = _sample_std(realized_pnls)
    sharpe_like = avg_pnl / pnl_std * math.sqrt(len(realized_pnls)) if pnl_std > 0 else None

    return {
        "summary": {
            "total_trades": len(trades),
            "realized_trades": len(realized_pnls),
            "open_trades": len(trades) - len(realized_pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(realized_pnls) if realized_pnls else 0.0,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl_per_realized_trade": round(avg_pnl, 4),
            "profit_factor": profit_factor,
            "max_drawdown_dollars": round(max_drawdown, 4),
            "open_exposure": round(exposure_open, 4),
            "sharpe_like_per_trade": sharpe_like,
        },
        "by_market_type": dict(by_market_type),
        "trades": rows,
    }


def _sample_std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)
