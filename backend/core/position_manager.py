"""Paper position management for intraday weather exits."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.core.weather_strategy import calculate_mark_to_market_pnl, trade_entry_cost, trade_quantity
from backend.data.polymarket_prices import fetch_polymarket_market_prices
from backend.models.database import BotState, Trade

logger = logging.getLogger("trading_bot")


def _direction_price_key(direction: str) -> str:
    return "yes" if direction in ("yes", "up") else "no"


async def _current_exit_price(trade: Trade) -> Optional[float]:
    if (trade.platform or "polymarket").lower() != "polymarket":
        return None

    prices = await fetch_polymarket_market_prices(
        str(trade.market_ticker),
        event_slug=trade.event_slug,
    )
    if not prices or prices.get("closed"):
        return None

    key = _direction_price_key(trade.direction)
    raw_price = prices.get(key)
    if raw_price is None:
        return None

    # Gamma prices are not guaranteed executable bid prices, so haircut them.
    return round(max(0.0, min(1.0, float(raw_price) - settings.WEATHER_EXIT_SLIPPAGE)), 4)


def _exit_reason(exit_price: float) -> Optional[str]:
    if exit_price >= settings.WEATHER_TAKE_PROFIT_PRICE:
        return "take_profit"
    if exit_price <= settings.WEATHER_STOP_LOSS_PRICE:
        return "stop_loss"
    return None


async def manage_open_weather_positions(db: Session) -> List[Trade]:
    """
    Close simulated weather trades before resolution when target/stop is hit.

    This is paper accounting only. Real orders require CLOB fills and are not
    marked closed here until execution is confirmed.
    """
    pending = db.query(Trade).filter(
        Trade.settled == False,
        Trade.market_type == "weather",
    ).all()

    if not pending:
        return []

    closed: List[Trade] = []
    state = db.query(BotState).first()

    for trade in pending:
        exit_price = await _current_exit_price(trade)
        if exit_price is None:
            continue

        reason = _exit_reason(exit_price)
        if not reason:
            continue

        if getattr(trade, "execution_mode", "paper") == "real" and not settings.SIMULATION_MODE:
            if not await _close_real_position(trade, exit_price):
                continue

        pnl = calculate_mark_to_market_pnl(trade, exit_price)
        trade.settled = True
        trade.settlement_time = datetime.utcnow()
        trade.exit_price = exit_price
        trade.exit_reason = reason
        trade.pnl = pnl
        trade.result = "win" if pnl > 0 else "loss" if pnl < 0 else "push"
        trade.analysis = {
            **(trade.analysis or {}),
            "entry_cost": trade_entry_cost(trade),
            "quantity": trade_quantity(trade),
            "entry_price": trade.entry_price,
            "exit_price": exit_price,
            "exit_reason": reason,
            "return_on_cost": pnl / trade_entry_cost(trade) if trade_entry_cost(trade) else 0.0,
            "model_probability": trade.model_probability,
            "market_price_at_entry": trade.market_price_at_entry,
            "edge_at_entry": trade.edge_at_entry,
        }

        if state and pnl is not None:
            state.total_pnl += pnl
            state.bankroll += pnl
            if pnl > 0:
                state.winning_trades += 1

        closed.append(trade)
        logger.info(
            "Paper weather exit %s: %s @ %.2f, PnL $%+.4f",
            trade.id,
            reason,
            exit_price,
            pnl,
        )

    if closed:
        db.commit()

    return closed


async def _close_real_position(trade: Trade, exit_price: float) -> bool:
    """Attempt a real CLOB sell before marking a real position closed."""
    if not settings.REAL_TRADING_ENABLED:
        return False

    try:
        from backend.execution.polymarket_executor import PolymarketExecutor

        analysis = trade.analysis or {}
        executor = PolymarketExecutor()
        result = await executor.sell_limit(
            token_id=trade.asset_id or "",
            price=exit_price,
            quantity=trade_quantity(trade),
            tick_size=float(analysis.get("tick_size") or 0.01),
            neg_risk=bool(analysis.get("neg_risk") or False),
        )
        if result.status.lower() != "matched":
            logger.warning("Real weather exit not filled for trade %s: status=%s", trade.id, result.status)
            return False
        trade.exit_order_id = result.order_id
        return True
    except Exception as exc:
        logger.warning("Real weather exit skipped for trade %s: %s", trade.id, exc)
        return False
