"""Optional real Polymarket CLOB execution adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from backend.config import settings


class PolymarketExecutionError(RuntimeError):
    """Raised when a real execution precondition fails."""


@dataclass(frozen=True)
class ExecutionResult:
    order_id: Optional[str]
    status: str
    raw: dict


async def check_geoblock() -> dict:
    """Return Polymarket's geoblock response for the current IP."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get("https://polymarket.com/api/geoblock")
        response.raise_for_status()
        return response.json()


def real_trading_configured() -> bool:
    """True only when all required real-trading config is present."""
    return bool(
        settings.REAL_TRADING_ENABLED
        and not settings.SIMULATION_MODE
        and settings.POLYMARKET_PRIVATE_KEY
        and settings.POLYMARKET_API_KEY
        and settings.POLYMARKET_API_SECRET
        and settings.POLYMARKET_API_PASSPHRASE
    )


class PolymarketExecutor:
    """Small wrapper around py-clob-client with safety checks."""

    def __init__(self):
        if not real_trading_configured():
            raise PolymarketExecutionError("Real trading is not fully configured")

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
        except ImportError as exc:
            raise PolymarketExecutionError("Install py-clob-client before real trading") from exc

        creds = ApiCreds(
            api_key=settings.POLYMARKET_API_KEY,
            api_secret=settings.POLYMARKET_API_SECRET,
            api_passphrase=settings.POLYMARKET_API_PASSPHRASE,
        )

        self._client = ClobClient(
            host=settings.POLYMARKET_CLOB_HOST,
            chain_id=settings.POLYMARKET_CHAIN_ID,
            key=settings.POLYMARKET_PRIVATE_KEY,
            creds=creds,
            signature_type=settings.POLYMARKET_SIGNATURE_TYPE,
            funder=settings.POLYMARKET_FUNDER_ADDRESS,
        )

    async def assert_can_trade(self) -> None:
        if not settings.POLYMARKET_CHECK_GEOBLOCK:
            return
        geo = await check_geoblock()
        if geo.get("blocked"):
            country = geo.get("country", "unknown")
            region = geo.get("region", "unknown")
            raise PolymarketExecutionError(f"Polymarket trading blocked from {country}/{region}")

    async def buy_limit(
        self,
        *,
        token_id: str,
        price: float,
        quantity: float,
        tick_size: float,
        neg_risk: bool,
    ) -> ExecutionResult:
        """Place an immediate-or-cancel buy limit order for outcome shares."""
        await self.assert_can_trade()
        return self._post_limit(token_id=token_id, price=price, quantity=quantity, side_name="BUY", tick_size=tick_size, neg_risk=neg_risk)

    async def sell_limit(
        self,
        *,
        token_id: str,
        price: float,
        quantity: float,
        tick_size: float,
        neg_risk: bool,
    ) -> ExecutionResult:
        """Place an immediate-or-cancel sell limit order for outcome shares."""
        await self.assert_can_trade()
        return self._post_limit(token_id=token_id, price=price, quantity=quantity, side_name="SELL", tick_size=tick_size, neg_risk=neg_risk)

    def _post_limit(
        self,
        *,
        token_id: str,
        price: float,
        quantity: float,
        side_name: str,
        tick_size: float,
        neg_risk: bool,
    ) -> ExecutionResult:
        if quantity < settings.POLYMARKET_MIN_ORDER_SIZE:
            raise PolymarketExecutionError(
                f"Order quantity {quantity:.4f} below configured Polymarket min shares {settings.POLYMARKET_MIN_ORDER_SIZE:.4f}"
            )
        if not token_id:
            raise PolymarketExecutionError("Missing CLOB token_id")

        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        side = BUY if side_name == "BUY" else SELL
        args = OrderArgs(token_id=token_id, price=price, size=quantity, side=side)
        options = {"tick_size": str(tick_size), "neg_risk": bool(neg_risk)}

        # FOK avoids unmanaged resting orders in this small-bankroll bot.
        response = self._client.create_and_post_order(args, options, OrderType.FOK)
        return ExecutionResult(
            order_id=response.get("orderID") or response.get("order_id"),
            status=response.get("status", "unknown"),
            raw=response,
        )
