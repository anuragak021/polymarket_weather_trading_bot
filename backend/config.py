"""Configuration settings for the prediction-market trading bot."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (SQLite for Phase 1, PostgreSQL for production)
    DATABASE_URL: str = "sqlite:///./tradingbot.db"

    # API Keys (optional)
    POLYMARKET_API_KEY: Optional[str] = None

    # Polymarket execution. Keep real trading disabled unless explicitly enabled.
    REAL_TRADING_ENABLED: bool = False
    POLYMARKET_CLOB_HOST: str = "https://clob.polymarket.com"
    POLYMARKET_CHAIN_ID: int = 137
    POLYMARKET_PRIVATE_KEY: Optional[str] = None
    POLYMARKET_API_SECRET: Optional[str] = None
    POLYMARKET_API_PASSPHRASE: Optional[str] = None
    POLYMARKET_SIGNATURE_TYPE: int = 0
    POLYMARKET_FUNDER_ADDRESS: Optional[str] = None
    POLYMARKET_CHECK_GEOBLOCK: bool = True
    POLYMARKET_MIN_ORDER_SIZE: float = 5.0  # CLOB minimum is in shares, not dollars.

    # Kalshi API
    KALSHI_API_KEY_ID: Optional[str] = None
    KALSHI_PRIVATE_KEY_PATH: Optional[str] = None
    KALSHI_ENABLED: bool = True

    # AI API Keys
    GROQ_API_KEY: Optional[str] = None

    # AI Model Configuration
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # AI Feature Flags
    AI_LOG_ALL_CALLS: bool = True
    AI_DAILY_BUDGET_USD: float = 1.0

    # Bot settings
    STRATEGY_MODE: str = "weather"  # weather, btc, or all
    SIMULATION_MODE: bool = True
    INITIAL_BANKROLL: float = 3.0
    KELLY_FRACTION: float = 1.0  # Full Kelly for aggressive growth

    # BTC 5-min specific settings
    SCAN_INTERVAL_SECONDS: int = 60  # Scan every minute
    SETTLEMENT_INTERVAL_SECONDS: int = 120  # Check settlements every 2 min
    BTC_PRICE_SOURCE: str = "coinbase"
    MIN_EDGE_THRESHOLD: float = 0.02  # 2% edge required — these are 50/50 markets
    MAX_ENTRY_PRICE: float = 0.55  # Enter up to 55c
    MAX_TRADES_PER_WINDOW: int = 1
    MAX_TOTAL_PENDING_TRADES: int = 20

    # Risk management
    DAILY_LOSS_LIMIT: float = 3.00  # Allow full initial bankroll loss
    MAX_TRADE_SIZE: float = 150.0
    MIN_TIME_REMAINING: int = 60  # Don't trade windows closing in < 60s
    MAX_TIME_REMAINING: int = 1800  # Trade windows up to 30min out

    # Indicator weights for composite signal (must sum to ~1.0)
    WEIGHT_RSI: float = 0.20
    WEIGHT_MOMENTUM: float = 0.35
    WEIGHT_VWAP: float = 0.20
    WEIGHT_SMA: float = 0.15
    WEIGHT_MARKET_SKEW: float = 0.10

    # Volume filter
    MIN_MARKET_VOLUME: float = 100.0  # Low volume for 5-min markets

    # Weather trading settings
    WEATHER_ENABLED: bool = True
    WEATHER_POLYMARKET_ONLY: bool = True
    WEATHER_SCAN_INTERVAL_SECONDS: int = 120  # 2 min (scan faster)
    WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800  # 30 min
    WEATHER_EXIT_CHECK_INTERVAL_SECONDS: int = 60
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.03  # Lower edge threshold to take more trades
    WEATHER_MIN_ENTRY_PRICE: float = 0.10  # Broaden entry prices
    WEATHER_MAX_ENTRY_PRICE: float = 0.90
    WEATHER_MIN_TRADE_SIZE: float = 0.50
    WEATHER_MAX_TRADE_SIZE: float = 150.0  # Allow large trades
    WEATHER_MAX_TRADE_FRACTION: float = 1.0  # Allow full bankroll per trade
    WEATHER_ALLOW_MIN_SIZE_ROUND_UP: bool = True
    WEATHER_MAX_OPEN_TRADES: int = 10  # More concurrent trades
    WEATHER_MAX_ALLOCATION: float = 150.0  # Max total allocation
    WEATHER_TAKE_PROFIT_PRICE: float = 0.85
    WEATHER_STOP_LOSS_PRICE: float = 0.15
    WEATHER_EXIT_SLIPPAGE: float = 0.02  # Account for slippage/fees
    WEATHER_CITIES: str = "houston,austin,chicago,dallas,hong_kong,london,denver,lucknow,jakarta,seoul,paris,amsterdam,munich,milan,shanghai,wellington,singapore,tokyo,nyc,toronto,mexico_city,beijing,atlanta,miami,chengdu,moscow,warsaw,jeddah,los_angeles,seattle,shenzhen,buenos_aires,istanbul,madrid,taipei,guangzhou,karachi,chongqing,san_francisco,lagos,wuhan,ankara,tel_aviv,manila,helsinki,kuala_lumpur,busan,sao_paulo,panama_city,cape_town,qingdao"

    class Config:
        env_file = ".env"


settings = Settings()
