"""Weather temperature market fetcher from Polymarket."""
import httpx
import re
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

logger = logging.getLogger("trading_bot")

# Map city names/variants found in market titles to our city keys
CITY_ALIASES = {
    "new york": "nyc",
    "nyc": "nyc",
    "new york city": "nyc",
    "chicago": "chicago",
    "miami": "miami",
    "los angeles": "los_angeles",
    "la": "los_angeles",
    "denver": "denver",
}

# Month name to number
MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class WeatherMarket:
    """A weather temperature prediction market."""
    slug: str
    market_id: str
    platform: str
    title: str
    city_key: str
    city_name: str
    target_date: date
    threshold_f: float       # Temperature threshold in Fahrenheit, or midpoint for range bins
    metric: str              # "high" or "low"
    direction: str           # "above", "below", or "range"
    yes_price: float         # Price of YES outcome (0-1)
    no_price: float          # Price of NO outcome (0-1)
    lower_f: Optional[float] = None
    upper_f: Optional[float] = None
    volume: float = 0.0
    closed: bool = False
    condition_id: Optional[str] = None
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    tick_size: Optional[float] = None
    neg_risk: bool = False


def _parse_weather_market_title(title: str) -> Optional[dict]:
    """
    Parse a weather market title to extract city, threshold, metric, date.

    Handles patterns like:
    - "Will the high temperature in New York exceed 75°F on March 5?"
    - "NYC high temperature above 80°F on March 10, 2026"
    - "Chicago daily high over 60°F on March 3"
    - "Will Miami's low be above 65°F on March 7?"
    - "Temperature in Denver above 70°F on March 5, 2026"
    """
    title_lower = title.lower()

    # Must be temperature-related
    if not any(kw in title_lower for kw in ["temperature", "temp", "°f", "degrees", "high", "low"]):
        return None

    # Extract city
    city_key = None
    city_name = None
    for alias, key in sorted(CITY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in title_lower:
            city_key = key
            from backend.data.weather import CITY_CONFIG
            city_name = CITY_CONFIG[key]["name"]
            break

    if not city_key:
        return None

    # Determine metric (high vs low)
    metric = "high"  # default
    if "low" in title_lower:
        metric = "low"

    lower_f = None
    upper_f = None
    threshold_f = None
    direction = "above"

    # Range/bin markets: "75-76°F", "between 75 and 76", "75 to 76 degrees".
    range_patterns = [
        r'(\d+)\s*(?:-|to)\s*(\d+)\s*°?\s*f',
        r'between\s+(\d+)\s+(?:and|to)\s+(\d+)',
    ]
    for pattern in range_patterns:
        match = re.search(pattern, title_lower)
        if match:
            lower_f = float(match.group(1))
            upper_f = float(match.group(2))
            threshold_f = (lower_f + upper_f) / 2.0
            direction = "range"
            break

    if threshold_f is None:
        temp_match = re.search(r'(\d+)\s*°?\s*f', title_lower)
        if not temp_match:
            temp_match = re.search(r'(\d+)\s*degrees', title_lower)
        if not temp_match:
            return None
        threshold_f = float(temp_match.group(1))

        if any(kw in title_lower for kw in ["below", "under", "less than", "drop below", "or lower", "or less"]):
            direction = "below"
            upper_f = threshold_f
        elif any(kw in title_lower for kw in ["above", "over", "greater than", "exceed", "or higher", "or more"]):
            direction = "above"
            lower_f = threshold_f

    # Extract date
    target_date = _extract_date(title_lower)
    if not target_date:
        return None

    return {
        "city_key": city_key,
        "city_name": city_name,
        "threshold_f": threshold_f,
        "lower_f": lower_f,
        "upper_f": upper_f,
        "metric": metric,
        "direction": direction,
        "target_date": target_date,
    }


def _extract_date(text: str) -> Optional[date]:
    """Extract a date from market title text."""
    today = date.today()

    # Build month name pattern for precise matching
    month_names = "|".join(MONTH_MAP.keys())

    # Pattern: "March 5, 2026" or "March 5 2026" or "March 5"
    for match in re.finditer(rf'({month_names})\s+(\d{{1,2}})(?:\s*,?\s*(\d{{4}}))?', text):
        month_str = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year

        month = MONTH_MAP.get(month_str)
        if month and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                continue

    # Pattern: "3/5/2026" or "03/05"
    match = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', text)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


async def fetch_polymarket_weather_markets(city_keys: Optional[List[str]] = None) -> List[WeatherMarket]:
    """
    Search Polymarket for weather temperature markets.
    Searches for temperature/weather events and parses their titles.
    """
    markets = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Search for weather/temperature events
            for search_term in ["temperature", "weather high", "weather low"]:
                try:
                    response = await client.get(
                        "https://gamma-api.polymarket.com/events",
                        params={
                            "closed": "false",
                            "limit": 100,
                            "tag": "Weather",
                        }
                    )
                    response.raise_for_status()
                    events = response.json()

                    for event in events:
                        event_slug = event.get("slug", "")
                        for market_data in event.get("markets", []):
                            market = _parse_polymarket_weather(market_data, event_slug, city_keys)
                            if market:
                                markets.append(market)

                except Exception as e:
                    logger.debug(f"Weather market search for '{search_term}' failed: {e}")

            # Also try slug-based search for known patterns
            for slug_pattern in ["weather", "temperature", "temp-"]:
                try:
                    response = await client.get(
                        "https://gamma-api.polymarket.com/events",
                        params={
                            "closed": "false",
                            "limit": 100,
                            "slug_contains": slug_pattern,
                        }
                    )
                    response.raise_for_status()
                    events = response.json()

                    for event in events:
                        event_slug = event.get("slug", "")
                        for market_data in event.get("markets", []):
                            market = _parse_polymarket_weather(market_data, event_slug, city_keys)
                            if market and not any(m.market_id == market.market_id for m in markets):
                                markets.append(market)

                except Exception as e:
                    logger.debug(f"Weather slug search for '{slug_pattern}' failed: {e}")

    except Exception as e:
        logger.warning(f"Failed to fetch weather markets: {e}")

    logger.info(f"Found {len(markets)} weather temperature markets")
    return markets


def _parse_polymarket_weather(
    market_data: dict,
    event_slug: str,
    city_keys: Optional[List[str]] = None,
) -> Optional[WeatherMarket]:
    """Parse a Polymarket market dict into a WeatherMarket if it's a temp market."""
    question = market_data.get("question", "") or market_data.get("groupItemTitle", "")
    if not question:
        return None

    parsed = _parse_weather_market_title(question)
    if not parsed:
        return None

    # Filter by requested cities
    if city_keys and parsed["city_key"] not in city_keys:
        return None

    # Only trade markets for dates in the future (or today)
    if parsed["target_date"] < date.today():
        return None

    # Parse prices
    outcome_prices = market_data.get("outcomePrices", [])
    if isinstance(outcome_prices, str):
        import json
        try:
            outcome_prices = json.loads(outcome_prices)
        except Exception:
            outcome_prices = []

    if not outcome_prices or len(outcome_prices) < 2:
        return None

    try:
        yes_price = float(outcome_prices[0])
        no_price = float(outcome_prices[1])
    except (ValueError, IndexError):
        return None

    # Skip resolved markets
    if market_data.get("closed", False):
        return None
    if yes_price > 0.98 or yes_price < 0.02:
        return None

    volume = float(market_data.get("volume", 0) or 0)
    token_ids = _parse_token_ids(market_data)

    return WeatherMarket(
        slug=event_slug,
        market_id=str(market_data.get("id", "")),
        platform="polymarket",
        title=question,
        city_key=parsed["city_key"],
        city_name=parsed["city_name"],
        target_date=parsed["target_date"],
        threshold_f=parsed["threshold_f"],
        lower_f=parsed["lower_f"],
        upper_f=parsed["upper_f"],
        metric=parsed["metric"],
        direction=parsed["direction"],
        yes_price=yes_price,
        no_price=no_price,
        volume=volume,
        condition_id=market_data.get("conditionId") or market_data.get("condition_id"),
        yes_token_id=token_ids[0] if len(token_ids) > 0 else None,
        no_token_id=token_ids[1] if len(token_ids) > 1 else None,
        tick_size=_parse_float(market_data.get("minimum_tick_size") or market_data.get("minimumTickSize")),
        neg_risk=bool(market_data.get("negRisk") or market_data.get("neg_risk") or False),
    )


def _parse_token_ids(market_data: dict) -> List[str]:
    raw = market_data.get("clobTokenIds") or market_data.get("clobTokenIDs") or []
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    if not isinstance(raw, list):
        return []
    return [str(token) for token in raw if token]


def _parse_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
