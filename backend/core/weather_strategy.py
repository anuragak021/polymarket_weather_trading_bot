"""Weather strategy sizing and PnL helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.config import settings


@dataclass(frozen=True)
class SizedPosition:
    """A cash-sized prediction-market position."""

    cash: float
    quantity: float
    kelly_fraction: float
    skipped_reason: Optional[str] = None

    @property
    def can_trade(self) -> bool:
        return self.skipped_reason is None and self.cash > 0 and self.quantity > 0


def clamp_probability(value: float) -> float:
    """Keep model probabilities away from impossible 0/1 extremes."""
    return max(0.01, min(0.99, value))


def outcome_win_probability(model_yes_probability: float, direction: str) -> float:
    """Return the win probability for the specific YES/NO side being bought."""
    if direction in ("yes", "up"):
        return clamp_probability(model_yes_probability)
    return clamp_probability(1.0 - model_yes_probability)


def size_weather_position(
    *,
    model_yes_probability: float,
    entry_price: float,
    direction: str,
    bankroll: float,
    min_trade_size: Optional[float] = None,
    max_trade_size: Optional[float] = None,
    max_trade_fraction: Optional[float] = None,
    allow_min_size_round_up: Optional[bool] = None,
    kelly_fraction: Optional[float] = None,
) -> SizedPosition:
    """
    Size a weather position in dollars spent, not shares.

    Polymarket limit-order ``size`` is shares. The bot's ``Trade.size`` is cash
    at risk because the dashboard and bankroll accounting are dollar based.
    """
    if bankroll <= 0:
        return SizedPosition(0.0, 0.0, 0.0, "bankroll_exhausted")
    if entry_price <= 0 or entry_price >= 1:
        return SizedPosition(0.0, 0.0, 0.0, "invalid_entry_price")

    min_size = settings.WEATHER_MIN_TRADE_SIZE if min_trade_size is None else min_trade_size
    max_size = settings.WEATHER_MAX_TRADE_SIZE if max_trade_size is None else max_trade_size
    max_fraction = settings.WEATHER_MAX_TRADE_FRACTION if max_trade_fraction is None else max_trade_fraction
    round_up = settings.WEATHER_ALLOW_MIN_SIZE_ROUND_UP if allow_min_size_round_up is None else allow_min_size_round_up
    kelly_mult = settings.KELLY_FRACTION if kelly_fraction is None else kelly_fraction

    win_prob = outcome_win_probability(model_yes_probability, direction)
    odds = (1.0 - entry_price) / entry_price
    lose_prob = 1.0 - win_prob
    full_kelly = (win_prob * odds - lose_prob) / odds
    fractional_kelly = max(0.0, full_kelly * kelly_mult)

    if fractional_kelly <= 0:
        return SizedPosition(0.0, 0.0, 0.0, "negative_kelly")

    cap = min(max_size, bankroll * max_fraction, bankroll)
    cash = min(fractional_kelly * bankroll, cap)

    if cash < min_size:
        if not round_up or bankroll < min_size or cap < min_size:
            return SizedPosition(0.0, 0.0, fractional_kelly, "below_min_trade_size")
        cash = min_size

    cash = round(max(0.0, min(cash, cap)), 2)
    quantity = round(cash / entry_price, 6)
    return SizedPosition(cash, quantity, fractional_kelly)


def trade_entry_cost(trade) -> float:
    """Return cash spent for a trade, compatible with older rows."""
    if getattr(trade, "entry_cost", None) is not None:
        return float(trade.entry_cost)
    return float(trade.size or 0.0)


def trade_quantity(trade) -> float:
    """Return outcome shares/contracts for a trade, compatible with older rows."""
    if getattr(trade, "quantity", None) is not None:
        return float(trade.quantity)
    entry_price = float(trade.entry_price or 0.0)
    if entry_price <= 0:
        return 0.0
    return trade_entry_cost(trade) / entry_price


def calculate_mark_to_market_pnl(trade, exit_price: float) -> float:
    """Calculate realized PnL when selling before resolution."""
    quantity = trade_quantity(trade)
    cost = trade_entry_cost(trade)
    return round(quantity * exit_price - cost, 4)


def calculate_settlement_pnl_from_cash(trade, settlement_value: float) -> float:
    """Calculate settlement PnL using cash-at-risk semantics."""
    direction = getattr(trade, "direction", "")
    if direction == "up":
        direction = "yes"
    elif direction == "down":
        direction = "no"

    quantity = trade_quantity(trade)
    cost = trade_entry_cost(trade)

    position_won = (direction == "yes" and settlement_value == 1.0) or (
        direction == "no" and settlement_value == 0.0
    )
    if position_won:
        return round(quantity - cost, 4)
    return round(-cost, 4)
