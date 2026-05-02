"""Read-only Polymarket price helpers used by paper exits."""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger("trading_bot")


def _parse_outcome_prices(raw_prices) -> Optional[dict]:
    if isinstance(raw_prices, str):
        try:
            raw_prices = json.loads(raw_prices)
        except Exception:
            return None

    if not isinstance(raw_prices, list) or len(raw_prices) < 2:
        return None

    try:
        return {
            "yes": float(raw_prices[0]),
            "no": float(raw_prices[1]),
        }
    except (TypeError, ValueError):
        return None


def _prices_from_market(market: dict) -> Optional[dict]:
    prices = _parse_outcome_prices(market.get("outcomePrices", []))
    if not prices:
        return None

    return {
        **prices,
        "closed": bool(market.get("closed", False)),
        "market_id": str(market.get("id", "")),
        "question": market.get("question") or market.get("groupItemTitle") or "",
    }


async def fetch_polymarket_market_prices(
    market_id: str,
    event_slug: Optional[str] = None,
) -> Optional[dict]:
    """Fetch current YES/NO prices from Gamma for one market."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if event_slug:
                response = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={"slug": event_slug},
                )
                response.raise_for_status()
                events = response.json()
                event = events[0] if isinstance(events, list) and events else events

                if isinstance(event, dict):
                    for market in event.get("markets", []):
                        if str(market.get("id")) == str(market_id):
                            return _prices_from_market(market)

            response = await client.get(f"https://gamma-api.polymarket.com/markets/{market_id}")
            response.raise_for_status()
            market = response.json()
            if isinstance(market, dict):
                return _prices_from_market(market)

    except Exception as exc:
        logger.warning(f"Failed to fetch Polymarket prices for {event_slug or market_id}: {exc}")

    return None
