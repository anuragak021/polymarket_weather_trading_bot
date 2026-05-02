"""Weather data fetcher using Open-Meteo Ensemble API and NWS observations."""
import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import statistics
import time

logger = logging.getLogger("trading_bot")

# Cap concurrent Open-Meteo ensemble requests to stay below the public free-tier limits.
_ENSEMBLE_SEMAPHORE = asyncio.Semaphore(3)

# City configurations with lat/lon and NWS station identifiers
CITY_CONFIG: Dict[str, dict] = {
    "houston": {
        "name": "Houston",
        "lat": 29.76328,
        "lon": -95.36327,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "austin": {
        "name": "Austin",
        "lat": 30.26715,
        "lon": -97.74306,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "chicago": {
        "name": "Chicago",
        "lat": 41.85003,
        "lon": -87.65005,
        "nws_station": "KORD",
        "nws_office": "LOT",
        "nws_gridpoint": "LOT/75,72",
    },
    "dallas": {
        "name": "Dallas",
        "lat": 32.78306,
        "lon": -96.80667,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "hong_kong": {
        "name": "Hong Kong",
        "lat": 22.27832,
        "lon": 114.17469,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "london": {
        "name": "London",
        "lat": 51.50853,
        "lon": -0.12574,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "denver": {
        "name": "Denver",
        "lat": 39.73915,
        "lon": -104.9847,
        "nws_station": "KDEN",
        "nws_office": "BOU",
        "nws_gridpoint": "BOU/62,60",
    },
    "lucknow": {
        "name": "Lucknow",
        "lat": 26.83928,
        "lon": 80.92313,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "jakarta": {
        "name": "Jakarta",
        "lat": -6.21462,
        "lon": 106.84513,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "seoul": {
        "name": "Seoul",
        "lat": 37.566,
        "lon": 126.9784,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "paris": {
        "name": "Paris",
        "lat": 48.85341,
        "lon": 2.3488,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "amsterdam": {
        "name": "Amsterdam",
        "lat": 52.37403,
        "lon": 4.88969,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "munich": {
        "name": "Munich",
        "lat": 48.13743,
        "lon": 11.57549,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "milan": {
        "name": "Milan",
        "lat": 45.46427,
        "lon": 9.18951,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "shanghai": {
        "name": "Shanghai",
        "lat": 31.22222,
        "lon": 121.45806,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "wellington": {
        "name": "Wellington",
        "lat": -41.28664,
        "lon": 174.77557,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "singapore": {
        "name": "Singapore",
        "lat": 1.28967,
        "lon": 103.85007,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "tokyo": {
        "name": "Tokyo",
        "lat": 35.6895,
        "lon": 139.69171,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "nyc": {
        "name": "NYC",
        "lat": 40.71427,
        "lon": -74.00597,
        "nws_station": "KNYC",
        "nws_office": "OKX",
        "nws_gridpoint": "OKX/33,37",
    },
    "toronto": {
        "name": "Toronto",
        "lat": 43.70643,
        "lon": -79.39864,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "mexico_city": {
        "name": "Mexico City",
        "lat": 19.42847,
        "lon": -99.12766,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "beijing": {
        "name": "Beijing",
        "lat": 39.9075,
        "lon": 116.39723,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "atlanta": {
        "name": "Atlanta",
        "lat": 33.749,
        "lon": -84.38798,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "miami": {
        "name": "Miami",
        "lat": 25.77427,
        "lon": -80.19366,
        "nws_station": "KMIA",
        "nws_office": "MFL",
        "nws_gridpoint": "MFL/75,53",
    },
    "chengdu": {
        "name": "Chengdu",
        "lat": 30.66667,
        "lon": 104.06667,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "moscow": {
        "name": "Moscow",
        "lat": 55.75222,
        "lon": 37.61556,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "warsaw": {
        "name": "Warsaw",
        "lat": 52.22977,
        "lon": 21.01178,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "jeddah": {
        "name": "Jeddah",
        "lat": 21.49012,
        "lon": 39.18624,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "los_angeles": {
        "name": "Los Angeles",
        "lat": 34.05223,
        "lon": -118.24368,
        "nws_station": "KLAX",
        "nws_office": "LOX",
        "nws_gridpoint": "LOX/154,44",
    },
    "seattle": {
        "name": "Seattle",
        "lat": 47.60621,
        "lon": -122.33207,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "shenzhen": {
        "name": "Shenzhen",
        "lat": 22.54554,
        "lon": 114.0683,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "buenos_aires": {
        "name": "Buenos Aires",
        "lat": -34.61315,
        "lon": -58.37723,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "istanbul": {
        "name": "Istanbul",
        "lat": 41.01384,
        "lon": 28.94966,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "madrid": {
        "name": "Madrid",
        "lat": 40.4165,
        "lon": -3.70256,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "taipei": {
        "name": "Taipei",
        "lat": 25.05306,
        "lon": 121.52639,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "guangzhou": {
        "name": "Guangzhou",
        "lat": 23.11667,
        "lon": 113.25,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "karachi": {
        "name": "Karachi",
        "lat": 24.8608,
        "lon": 67.0104,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "chongqing": {
        "name": "Chongqing",
        "lat": 29.56026,
        "lon": 106.55771,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "san_francisco": {
        "name": "San Francisco",
        "lat": 37.77493,
        "lon": -122.41942,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "lagos": {
        "name": "Lagos",
        "lat": 6.45407,
        "lon": 3.39467,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "wuhan": {
        "name": "Wuhan",
        "lat": 30.58333,
        "lon": 114.26667,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "ankara": {
        "name": "Ankara",
        "lat": 39.91987,
        "lon": 32.85427,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "tel_aviv": {
        "name": "Tel Aviv",
        "lat": 32.08088,
        "lon": 34.78057,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "manila": {
        "name": "Manila",
        "lat": 14.6042,
        "lon": 120.9822,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "helsinki": {
        "name": "Helsinki",
        "lat": 60.16952,
        "lon": 24.93545,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "kuala_lumpur": {
        "name": "Kuala Lumpur",
        "lat": 3.1412,
        "lon": 101.68653,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "busan": {
        "name": "Busan",
        "lat": 35.10168,
        "lon": 129.03004,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "sao_paulo": {
        "name": "Sao Paulo",
        "lat": -23.5475,
        "lon": -46.63611,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "panama_city": {
        "name": "Panama City",
        "lat": 8.9936,
        "lon": -79.51973,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "cape_town": {
        "name": "Cape Town",
        "lat": -33.92584,
        "lon": 18.42322,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    },
    "qingdao": {
        "name": "Qingdao",
        "lat": 36.06488,
        "lon": 120.38042,
        "nws_station": "UNKNOWN",
        "nws_office": "UNKNOWN",
        "nws_gridpoint": "UNKNOWN",
    }
}


@dataclass
class EnsembleForecast:
    """Ensemble weather forecast with per-member data."""
    city_key: str
    city_name: str
    target_date: date
    member_highs: List[float]  # Daily max temps (F) per ensemble member
    member_lows: List[float]   # Daily min temps (F) per ensemble member
    mean_high: float = 0.0
    std_high: float = 0.0
    mean_low: float = 0.0
    std_low: float = 0.0
    num_members: int = 0
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.member_highs:
            self.mean_high = statistics.mean(self.member_highs)
            self.std_high = statistics.stdev(self.member_highs) if len(self.member_highs) > 1 else 0.0
            self.num_members = len(self.member_highs)
        if self.member_lows:
            self.mean_low = statistics.mean(self.member_lows)
            self.std_low = statistics.stdev(self.member_lows) if len(self.member_lows) > 1 else 0.0

    def probability_high_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high above threshold."""
        if not self.member_highs:
            return 0.5
        count = sum(1 for h in self.member_highs if h > threshold_f)
        return count / len(self.member_highs)

    def probability_high_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high below threshold."""
        return 1.0 - self.probability_high_above(threshold_f)

    def probability_low_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low above threshold."""
        if not self.member_lows:
            return 0.5
        count = sum(1 for l in self.member_lows if l > threshold_f)
        return count / len(self.member_lows)

    def probability_low_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low below threshold."""
        return 1.0 - self.probability_low_above(threshold_f)

    @property
    def ensemble_agreement(self) -> float:
        """How one-sided the ensemble is (0.5 = split, 1.0 = unanimous)."""
        if not self.member_highs:
            return 0.5
        median = statistics.median(self.member_highs)
        above = sum(1 for h in self.member_highs if h > median)
        frac = above / len(self.member_highs)
        return max(frac, 1 - frac)


# Simple cache: (city_key, target_date_str) -> (timestamp, EnsembleForecast)
_forecast_cache: Dict[str, tuple] = {}
_CACHE_TTL = 1800  # 30 minutes between refresh attempts on success
_NEGATIVE_CACHE_TTL = 120  # back off 2 minutes after a 429/error before retrying


def get_cached_forecast(city_key: str, target_date: Optional[date] = None) -> Optional["EnsembleForecast"]:
    """Return the most recent cached forecast for a city without triggering a fetch."""
    if target_date is None:
        target_date = date.today()
    cache_key = f"{city_key}_{target_date.isoformat()}"
    entry = _forecast_cache.get(cache_key)
    if not entry:
        return None
    _, cached_forecast = entry
    return cached_forecast


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


async def fetch_ensemble_forecast(city_key: str, target_date: Optional[date] = None) -> Optional[EnsembleForecast]:
    """
    Fetch ensemble forecast from Open-Meteo Ensemble API (free, 31-member GFS).
    Returns per-member daily max/min temperatures in Fahrenheit.
    """
    if city_key not in CITY_CONFIG:
        logger.warning(f"Unknown city key: {city_key}")
        return None

    if target_date is None:
        target_date = date.today()

    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    cached_entry = _forecast_cache.get(cache_key)
    if cached_entry is not None:
        cached_time, cached_forecast = cached_entry
        if cached_forecast is not None and now - cached_time < _CACHE_TTL:
            return cached_forecast
        # Negative cache: a recent failure (cached_forecast is None). Skip the call.
        if cached_forecast is None and now - cached_time < _NEGATIVE_CACHE_TTL:
            return None

    city = CITY_CONFIG[city_key]
    last_known: Optional[EnsembleForecast] = None
    if cached_entry is not None and cached_entry[1] is not None:
        last_known = cached_entry[1]

    try:
        async with _ENSEMBLE_SEMAPHORE:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Open-Meteo Ensemble API — GFS ensemble with 31 members
                params = {
                    "latitude": city["lat"],
                    "longitude": city["lon"],
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "temperature_unit": "fahrenheit",
                    "start_date": target_date.isoformat(),
                    "end_date": target_date.isoformat(),
                    "models": "gfs_seamless",
                }

                response = await client.get(
                    "https://ensemble-api.open-meteo.com/v1/ensemble",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

        daily = data.get("daily", {})

        # Open-Meteo returns each ensemble member as a separate key:
        #   temperature_2m_max (control), temperature_2m_max_member01, ..., _member30
        # Collect all member values for highs and lows
        member_highs = []
        member_lows = []

        for key, values in daily.items():
            if not isinstance(values, list) or not values:
                continue
            val = values[0]
            if val is None:
                continue
            if "temperature_2m_max" in key:
                member_highs.append(float(val))
            elif "temperature_2m_min" in key:
                member_lows.append(float(val))

        if not member_highs:
            logger.warning(f"No ensemble data for {city_key} on {target_date}")
            return last_known

        forecast = EnsembleForecast(
            city_key=city_key,
            city_name=city["name"],
            target_date=target_date,
            member_highs=member_highs,
            member_lows=member_lows,
        )

        _forecast_cache[cache_key] = (now, forecast)
        logger.info(f"Ensemble forecast for {city['name']} on {target_date}: "
                    f"High {forecast.mean_high:.1f}F +/- {forecast.std_high:.1f}F "
                    f"({forecast.num_members} members)")

        return forecast

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Negative-cache the rate limit so we don't hammer the API.
            _forecast_cache[cache_key] = (now, None)
            if last_known is not None:
                logger.warning(f"Open-Meteo 429 for {city_key}; serving stale forecast")
                return last_known
            logger.warning(f"Open-Meteo 429 for {city_key}; no stale forecast available")
            return None
        logger.warning(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return last_known
    except Exception as e:
        logger.warning(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return last_known


async def fetch_nws_observed_temperature(city_key: str, target_date: Optional[date] = None) -> Optional[Dict[str, float]]:
    """
    Fetch observed temperature from NWS API for settlement.
    Returns dict with 'high' and 'low' in Fahrenheit, or None if not available.
    """
    if city_key not in CITY_CONFIG:
        return None

    city = CITY_CONFIG[city_key]
    if target_date is None:
        target_date = date.today()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # NWS observations endpoint
            station = city["nws_station"]
            url = f"https://api.weather.gov/stations/{station}/observations"
            headers = {"User-Agent": "(trading-bot, contact@example.com)"}

            # Get observations for the target date
            start = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
            end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

            response = await client.get(url, params={"start": start, "end": end}, headers=headers)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return None

            temps = []
            for obs in features:
                props = obs.get("properties", {})
                temp_c = props.get("temperature", {}).get("value")
                if temp_c is not None:
                    temps.append(_celsius_to_fahrenheit(temp_c))

            if not temps:
                return None

            return {
                "high": max(temps),
                "low": min(temps),
            }

    except Exception as e:
        logger.warning(f"Failed to fetch NWS observations for {city_key}: {e}")
        return None
