#!/usr/bin/env python3
"""
Working Combined Trading Signals Bot
- Automatic signal generation (2-5 hour intervals)
- Interactive buttons for manual control
- Daily summary reports (24h)
- Weekly summary reports (Friday, 7 days)
- Fixed all asyncio issues
"""

# CRITICAL: Load .env FIRST, before any config imports
from pathlib import Path
from env_loader import load_env

# Compute absolute path to project root
_project_root = Path(__file__).resolve().parent

# Load .env with unified loader (includes diagnostics)
_dotenv_path = load_env(_project_root)

# Now safe to import Config and other modules
import asyncio
import time
import json
import random
import requests
import re
import traceback
from enum import Enum
from datetime import datetime, timezone, timedelta
import pytz
import sys
import httpx
from typing import Optional, Dict, Tuple, List, Any
from config import Config

# Fix APScheduler timezone issue: patch apscheduler.util.astimezone before APScheduler imports
# This prevents the "Only timezones from the pytz library are supported" error
def patch_apscheduler_timezone():
    """Patch APScheduler's astimezone function to handle zoneinfo timezones"""
    try:
        # Import apscheduler.util early and patch astimezone
        from apscheduler import util as apscheduler_util

        # Save original function
        original_astimezone = apscheduler_util.astimezone

        def patched_astimezone(tz):
            """Patched astimezone that converts zoneinfo to pytz"""
            if tz is None:
                return pytz.UTC
                # If already pytz, return as-is
            if isinstance(tz, pytz.BaseTzInfo):
                return tz
                # Convert zoneinfo to pytz if needed
            try:
                if hasattr(tz, 'key'):  # zoneinfo.ZoneInfo has a 'key' attribute
                    return pytz.timezone(tz.key)
            except (AttributeError, pytz.UnknownTimeZoneError):
                pass
            # Fallback to UTC
            return pytz.UTC

        # Replace the function
        apscheduler_util.astimezone = patched_astimezone
    except (ImportError, AttributeError):
        pass

# Apply patch before importing telegram (which imports APScheduler)
patch_apscheduler_timezone()

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import threading

# Configuration
BOT_TOKEN = "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY"
FOREX_CHANNEL = "-1001286609636"
FOREX_CHANNEL_3TP = "-1001220540048"  # New forex channel with 3 TPs
FOREX_CHANNEL_ADDITIONAL = "-1002987399941"  # Additional forex channel
CRYPTO_CHANNEL_LINGRID = "-1002978318746"  # Crypto Lingrid channel
CRYPTO_CHANNEL_GAINMUSE = "-1001411205299"  # Crypto Gain muse channel
SUMMARY_USER_ID = 615348532

# Allowed user IDs for interactive features
ALLOWED_USERS = [615348532, 501779863]

# Forex pairs
FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", 
    "USDCHF", "GBPCAD", "GBPNZD", "XAUUSD"
]

# Crypto pairs
CRYPTO_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
    "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"
]

# Index pairs (for indexes channel)
INDEX_PAIRS = ["USOIL", "BRENT", "XAUUSD"]  # Oil and Gold

# Signal storage
SIGNALS_FILE = "working_combined_signals.json"
PERFORMANCE_FILE = "working_combined_performance.json"
LAST_SIGNAL_TIME_FILE = "last_signal_time.json"  # Track last signal time for spacing (global - 5 min between channels)
CHANNEL_LAST_SIGNAL_FILE = "channel_last_signal_time.json"  # Track last signal time per channel (2h between same channel)
CHANNEL_PAIR_LAST_SIGNAL_FILE = "channel_pair_last_signal_time.json"  # Track last signal time per pair per channel (36h between same pair in same channel)

# Channel definitions
CHANNEL_DEGRAM = "-1001220540048"  # DeGRAM
CHANNEL_LINGRID_CRYPTO = "-1001411205299"  # Lingrid Crypto
CHANNEL_LINGRID_FOREX = "-1001286609636"  # Lingrid Forex
CHANNEL_GAINMUSE = "-1002978318746"  # GainMuse
CHANNEL_LINGRID_INDEXES = "-1001247341118"  # Lingrid Indexes
CHANNEL_GOLD_PRIVATE = "-1003506500177"  # GOLD Private

# Channel result files - one file per channel
# Maps all channel IDs (both old constants and new) to result files
CHANNEL_RESULTS = {
    # New channel IDs
    CHANNEL_DEGRAM: "results_degram.json",
    CHANNEL_LINGRID_CRYPTO: "results_lingrid_crypto.json",
    CHANNEL_LINGRID_FOREX: "results_lingrid_forex.json",
    CHANNEL_GAINMUSE: "results_gainmuse.json",
    CHANNEL_LINGRID_INDEXES: "results_lingrid_indexes.json",
    CHANNEL_GOLD_PRIVATE: "results_gold_private.json",
    # Old channel constants (for backward compatibility)
    FOREX_CHANNEL: "results_lingrid_forex.json",  # FOREX_CHANNEL = CHANNEL_LINGRID_FOREX
    FOREX_CHANNEL_3TP: "results_degram.json",  # FOREX_CHANNEL_3TP = CHANNEL_DEGRAM
    CRYPTO_CHANNEL_LINGRID: "results_gainmuse.json",  # CRYPTO_CHANNEL_LINGRID = CHANNEL_GAINMUSE
    CRYPTO_CHANNEL_GAINMUSE: "results_lingrid_crypto.json",  # CRYPTO_CHANNEL_GAINMUSE = CHANNEL_LINGRID_CRYPTO
    FOREX_CHANNEL_ADDITIONAL: "results_forex_additional_channel.json",  # Keep separate for now
    "-1001286609636": "results_lingrid_forex.json"  # Direct ID mapping
}

# Channel signal files - one file per channel for storing signals
CHANNEL_SIGNALS = {
    CHANNEL_DEGRAM: "signals_degram.json",
    CHANNEL_LINGRID_CRYPTO: "signals_lingrid_crypto.json",
    CHANNEL_LINGRID_FOREX: "signals_lingrid_forex.json",
    CHANNEL_GAINMUSE: "signals_gainmuse.json",
    CHANNEL_LINGRID_INDEXES: "signals_lingrid_indexes.json",
    CHANNEL_GOLD_PRIVATE: "signals_gold_private.json"
}

# Signal limits
MAX_FOREX_SIGNALS = 5  # Original forex channel
MAX_FOREX_3TP_SIGNALS = 5  # New forex channel with 3 TPs (changed to 5)
MAX_FOREX_ADDITIONAL_SIGNALS = 5  # Additional forex channel (different signals)
MAX_CRYPTO_SIGNALS_LINGRID = 5  # Lingrid Crypto channel
MAX_CRYPTO_SIGNALS_GAINMUSE = 10  # GainMuse Crypto channel (increased to 10 signals per day)
MAX_INDEX_SIGNALS = 5  # Index channel (5 signals per day)
MAX_GOLD_SIGNALS = 3  # Gold Private channel (3 signals per day)

# Time intervals (in hours)
MIN_INTERVAL = 3  # Changed to 3 hours minimum
MAX_INTERVAL = 5  # Keep 5 hours maximum

# Reason codes for signal rejection
class SignalRejectReason(Enum):
    """Structured reason codes for why a signal was rejected"""
    SUCCESS = "SUCCESS"
    THROTTLE_MIN_INTERVAL = "THROTTLE_MIN_INTERVAL"  # 5 min between channels
    THROTTLE_CHANNEL_INTERVAL = "THROTTLE_CHANNEL_INTERVAL"  # 2h for same channel
    RULE_36H = "RULE_36H"  # 36h rule for same pair in same channel
    DAILY_LIMIT = "DAILY_LIMIT"  # Daily signal limit reached
    WEEKEND_BLOCK = "WEEKEND_BLOCK"  # Weekend - no signals
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"  # Could not get price
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"  # Symbol not found in cTrader
    NO_SPOT_SUBSCRIPTION = "NO_SPOT_SUBSCRIPTION"  # Not subscribed to spot quotes
    INVALID_TICK = "INVALID_TICK"  # bid=0 or ask=0
    PARTIAL_TICK = "PARTIAL_TICK"  # Partial tick received, waiting for merge
    EXCEPTION = "EXCEPTION"  # Exception occurred
    GENERATION_FAILED = "GENERATION_FAILED"  # Signal generation failed
    CONFIG_INVALID_DEMO_ACCOUNT_ID = "CONFIG_INVALID_DEMO_ACCOUNT_ID"  # DEMO_ACCOUNT_ID is invalid/not numeric (deprecated, use CONFIG_INVALID_ACCOUNT_ID)
    CONFIG_INVALID_ACCOUNT_ID = "CONFIG_INVALID_ACCOUNT_ID"  # CTRADER_ACCOUNT_ID is invalid/not numeric or placeholder
    PRICE_UNAVAILABLE_CTRADER_ONLY = "PRICE_UNAVAILABLE_CTRADER_ONLY"  # Gold price unavailable, cTrader only mode


def parse_int_env(name: str, value: str) -> Optional[int]:
    """Parse integer from environment variable value
    
    Args:
        name: Environment variable name (for error messages)
        value: Environment variable value (string)
    
    Returns:
        int if value is valid numeric string, None if empty/None, raises ValueError if invalid
    
    Raises:
        ValueError: If value is not None/empty and not a valid integer string
    """
    if value is None or value == "":
        return None
    
    # Check if it's a placeholder/example value
    if value.lower() in ['your_demo_account_id', 'your_account_id', 'your_client_id', 
                         'your_client_secret', 'your_access_token', 'your_refresh_token',
                         'your_bot_token_here', 'your_test_channel', 'your_finnhub_api_key_here']:
        raise ValueError(f"{name}='{value}' appears to be a placeholder/example value, not a real value")
    
    # Try to parse as integer
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name}='{value}' is not numeric. Expected an integer (e.g., 123456789)")


# Gold symbol candidates for cTrader
GOLD_SYMBOL_CANDIDATES = ["XAUUSD", "GOLD", "XAUUSD.", "XAUUSDm", "XAUUSD.r", "XAU/USD"]

# Global cTrader-only mode flag (hardcoded, no .env)
CTRADER_ONLY_MODE = True  # If True, require cTrader connection before generating signals

# Global cTrader async client (no Twisted)
_ctrader_async_client = None
_gold_ctrader_connected = False  # Track if cTrader is connected and has prices

# Yahoo Finance price comparison tracking
_gold_price_comparison_stats = {
    "count": 0,
    "sum_diff_abs": 0.0,
    "max_diff_abs": 0.0,
    "sum_diff_bps": 0.0,
    "max_diff_bps": 0.0,
    "last_summary_date": None
}


async def get_gold_price_from_yahoo() -> Optional[Dict[str, Any]]:
    """Get gold price from Yahoo Finance using yfinance library
    
    Returns:
        Dict with keys: price (float), source (str), timestamp (str), meta (dict)
        or None if unavailable
    """
    try:
        import yfinance as yf
    except ImportError:
        print("[GOLD_YAHOO] yfinance not installed, install with: pip install yfinance")
        return None
    
    tickers_to_try = [
        ("XAUUSD=X", "yahoo_spot"),
        ("GC=F", "yahoo_futures")
    ]
    
    for ticker_symbol, source_type in tickers_to_try:
        try:
            # Use asyncio.to_thread to avoid blocking
            import asyncio
            ticker = yf.Ticker(ticker_symbol)
            
            # Get latest price (non-blocking)
            loop = asyncio.get_event_loop()
            info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ticker.history(period="1d", interval="1m")),
                timeout=10.0
            )
            
            if info is not None and not info.empty:
                # Get last close price
                last_price = float(info['Close'].iloc[-1])
                if last_price > 0:
                    return {
                        "price": last_price,
                        "source": source_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "meta": {"ticker": ticker_symbol}
                    }
            
            # Fallback: try info attribute
            info_dict = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ticker.info),
                timeout=5.0
            )
            
            if info_dict and 'regularMarketPrice' in info_dict:
                price = float(info_dict['regularMarketPrice'])
                if price > 0:
                    return {
                        "price": price,
                        "source": source_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "meta": {"ticker": ticker_symbol}
                    }
                    
        except asyncio.TimeoutError:
            print(f"[GOLD_YAHOO] Timeout getting price from {ticker_symbol}")
            continue
        except Exception as e:
            print(f"[GOLD_YAHOO] Error getting price from {ticker_symbol}: {e}")
            continue
    
    return None


def get_forex_price_ctrader(symbol: str) -> Tuple[Optional[float], Optional[str]]:
    """Get forex price STRICTLY from cTrader (no fallbacks)
    
    Args:
        symbol: Forex pair (e.g., "EURUSD", "GBPUSD", "USDJPY")
    
    Returns:
        Tuple of (price: float or None, reason: str or None)
        If price is None, reason contains error explanation
    """
    import time
    start_time = time.time()
    
    global _ctrader_async_client
    
    if not _ctrader_async_client:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[FOREX_PRICE] {symbol}: source=CTRADER, price=None, reason=client_not_initialized, latency={latency_ms}ms")
        return None, "client_not_initialized"
    
    try:
        price = _ctrader_async_client.get_last_price(symbol)
        latency_ms = int((time.time() - start_time) * 1000)
        
        if price and price > 0:
            print(f"[FOREX_PRICE] {symbol}: source=CTRADER, price={price:.5f}, latency={latency_ms}ms")
            return price, None
        else:
            print(f"[FOREX_PRICE] {symbol}: source=CTRADER, price=None, reason=no_quotes, latency={latency_ms}ms")
            return None, "no_quotes"
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[FOREX_PRICE] {symbol}: source=CTRADER, price=None, reason=exception ({type(e).__name__}: {str(e)[:50]}), latency={latency_ms}ms")
        return None, f"exception: {type(e).__name__}"


async def get_gold_price_yahoo() -> Tuple[Optional[float], Optional[str]]:
    """Get gold price STRICTLY from Yahoo Finance (no fallbacks)
    
    Returns:
        Tuple of (price: float or None, reason: str or None)
        If price is None, reason contains error explanation
    """
    import time
    start_time = time.time()
    
    yahoo_data = await get_gold_price_from_yahoo()
    latency_ms = int((time.time() - start_time) * 1000)
    
    if yahoo_data and yahoo_data["price"] > 0:
        ticker_used = yahoo_data["meta"].get("ticker", "unknown")
        source = yahoo_data["source"]
        price = yahoo_data["price"]
        print(f"[GOLD_PRICE] XAUUSD: source=YAHOO ({source}), price={price:.2f}, ticker={ticker_used}, latency={latency_ms}ms")
        return price, None
    else:
        print(f"[GOLD_PRICE] XAUUSD: source=YAHOO, price=None, reason=unavailable, latency={latency_ms}ms")
        return None, "unavailable"


async def get_index_price_yahoo(symbol: str) -> Tuple[Optional[float], Optional[str]]:
    """Get index price STRICTLY from Yahoo Finance (no fallbacks)
    
    Args:
        symbol: Index symbol (e.g., "BRENT", "USOIL")
    
    Returns:
        Tuple of (price: float or None, reason: str or None)
        If price is None, reason contains error explanation
    """
    import time
    start_time = time.time()
    
    try:
        import yfinance as yf
    except ImportError:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price=None, reason=yfinance_not_installed, latency={latency_ms}ms")
        return None, "yfinance_not_installed"
    
    # Map symbols to Yahoo Finance tickers
    ticker_map = {
        "BRENT": "BZ=F",  # Brent Crude Oil Futures
        "USOIL": "CL=F",  # WTI Crude Oil Futures
        "XAUUSD": "GC=F",  # Gold Futures (for consistency)
    }
    
    ticker_symbol = ticker_map.get(symbol.upper())
    if not ticker_symbol:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price=None, reason=unknown_symbol, latency={latency_ms}ms")
        return None, "unknown_symbol"
    
    try:
        import asyncio
        ticker = yf.Ticker(ticker_symbol)
        
        # Get latest price (non-blocking)
        loop = asyncio.get_event_loop()
        info = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: ticker.history(period="1d", interval="1m")),
            timeout=10.0
        )
        
        if info is not None and not info.empty:
            last_price = float(info['Close'].iloc[-1])
            if last_price > 0:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price={last_price:.2f}, ticker={ticker_symbol}, latency={latency_ms}ms")
                return last_price, None
        
        # Fallback: try info attribute
        info_dict = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: ticker.info),
            timeout=5.0
        )
        
        if info_dict and 'regularMarketPrice' in info_dict:
            price = float(info_dict['regularMarketPrice'])
            if price > 0:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price={price:.2f}, ticker={ticker_symbol}, latency={latency_ms}ms")
                return price, None
        
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price=None, reason=no_price_data, ticker={ticker_symbol}, latency={latency_ms}ms")
        return None, "no_price_data"
        
    except asyncio.TimeoutError:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price=None, reason=timeout, ticker={ticker_symbol}, latency={latency_ms}ms")
        return None, "timeout"
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        print(f"[INDEX_PRICE] {symbol}: source=YAHOO, price=None, reason=exception ({type(e).__name__}: {str(e)[:50]}), ticker={ticker_symbol}, latency={latency_ms}ms")
        return None, f"exception: {type(e).__name__}"


def _log_gold_price_comparison(ctrader_price: float, yahoo_price: float):
    """Log comparison between cTrader and Yahoo Finance prices"""
    global _gold_price_comparison_stats
    
    diff_abs = abs(ctrader_price - yahoo_price)
    diff_bps = (diff_abs / ctrader_price) * 10000  # Basis points
    
    # Update stats
    _gold_price_comparison_stats["count"] += 1
    _gold_price_comparison_stats["sum_diff_abs"] += diff_abs
    _gold_price_comparison_stats["max_diff_abs"] = max(_gold_price_comparison_stats["max_diff_abs"], diff_abs)
    _gold_price_comparison_stats["sum_diff_bps"] += diff_bps
    _gold_price_comparison_stats["max_diff_bps"] = max(_gold_price_comparison_stats["max_diff_bps"], diff_bps)
    
    # Log current comparison
    print(f"[GOLD_COMPARE] cTrader={ctrader_price:.2f}, Yahoo={yahoo_price:.2f}, diff_abs={diff_abs:.2f}, diff_bps={diff_bps:.2f} bps")
    
    # Daily summary
    today = datetime.now(timezone.utc).date()
    if _gold_price_comparison_stats["last_summary_date"] != today:
        if _gold_price_comparison_stats["count"] > 0:
            avg_diff_abs = _gold_price_comparison_stats["sum_diff_abs"] / _gold_price_comparison_stats["count"]
            avg_diff_bps = _gold_price_comparison_stats["sum_diff_bps"] / _gold_price_comparison_stats["count"]
            
            print(f"[GOLD_COMPARE_SUMMARY] Daily stats:")
            print(f"  Count: {_gold_price_comparison_stats['count']}")
            print(f"  Avg diff (abs): {avg_diff_abs:.2f}")
            print(f"  Max diff (abs): {_gold_price_comparison_stats['max_diff_abs']:.2f}")
            print(f"  Avg diff (bps): {avg_diff_bps:.2f} bps")
            print(f"  Max diff (bps): {_gold_price_comparison_stats['max_diff_bps']:.2f} bps")
        
        # Reset stats for new day
        _gold_price_comparison_stats = {
            "count": 0,
            "sum_diff_abs": 0.0,
            "max_diff_abs": 0.0,
            "sum_diff_bps": 0.0,
            "max_diff_bps": 0.0,
            "last_summary_date": today
        }


async def get_gold_price() -> Optional[Dict[str, Any]]:
    """Get gold price with fallback: cTrader -> Yahoo Finance
    
    Returns:
        Dict with keys: price (float), source (str), timestamp (str), meta (dict)
        or None if unavailable
    """
    # Try cTrader first
    ctrader_price = get_gold_price_from_ctrader()
    
    if ctrader_price is not None and ctrader_price > 0:
        # Try Yahoo Finance for comparison
        yahoo_data = await get_gold_price_from_yahoo()
        
        if yahoo_data and yahoo_data["price"] > 0:
            # Log comparison
            _log_gold_price_comparison(ctrader_price, yahoo_data["price"])
        
        return {
            "price": ctrader_price,
            "source": "ctrader",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meta": {}
        }
    
    # Fallback to Yahoo Finance
    print("[GOLD_PRICE] cTrader unavailable, trying Yahoo Finance...")
    yahoo_data = await get_gold_price_from_yahoo()
    
    if yahoo_data and yahoo_data["price"] > 0:
        print(f"[GOLD_PRICE] ✅ Got price from Yahoo Finance: {yahoo_data['price']:.2f} ({yahoo_data['source']})")
        return yahoo_data
    
    print("[GOLD_PRICE] ❌ Could not get gold price from any source")
    return None


def get_real_forex_price(pair):
    """Get real forex price from real-time API with detailed logging
    
    For XAUUSD (gold), uses cTrader if available, otherwise falls back to external APIs.
    For other forex pairs, uses external free API.
    """
    try:
        if pair == "XAUUSD":
            # STRICT: Use cTrader only (GOLD_CTRADER_ONLY is always true with hardcoded config)
            gold_price = get_gold_price_from_ctrader()
            if gold_price is not None and gold_price > 0:
                return gold_price
            
            # No external fallback - cTrader only
            print("[FOREX_PRICE] XAUUSD: cTrader price unavailable, GOLD_CTRADER_ONLY=true - no external fallback")
            return None
            # Import robust HTTP client
            try:
                from http_client import get_http_session, log_request_error
                session = get_http_session()
            except ImportError:
                # Fallback to basic requests if http_client not available
                session = requests.Session()
                def log_request_error(name, url, exc, sess):
                    return f"{name}: {type(exc).__name__} - {str(exc)[:100]}"
            
            # STRICT: Check if cTrader-only mode is enabled - NEVER call external APIs for gold
            ctrader_config = Config.get_ctrader_config()
            gold_ctrader_only = ctrader_config.gold_ctrader_only
            
            if gold_ctrader_only:
                # Strict cTrader only - NEVER call external APIs
                # Check if cTrader async client is available
                global _gold_ctrader_connected, _ctrader_async_client
                if not _ctrader_async_client or not _gold_ctrader_connected:
                    reason = "ctrader_unavailable"
                    message = "cTrader async client not initialized or not connected"
                elif "XAUUSD" not in _ctrader_async_client.symbol_name_to_id:
                    reason = "ctrader_unavailable"
                    message = "Symbol not resolved (XAUUSD not found)"
                else:
                    # Check if we have quotes
                    symbol_name, _ = _gold_symbol_resolved
                    quote_cache = _gold_quote_cache.get(symbol_name.upper(), {})
                    if not quote_cache.get("bid") or not quote_cache.get("ask"):
                        reason = "ctrader_no_quotes"
                        message = "No quotes received from cTrader"
                    else:
                        reason = "ctrader_unavailable"
                        message = "Unknown cTrader issue"
                
                return None, "PRICE_UNAVAILABLE_CTRADER_ONLY", {
                    "reason": reason,
                    "message": message,
                    "gold_ctrader_only": True
                }
            
            # Only reach here if GOLD_CTRADER_ONLY=false (fallback mode)
            # Gold price from external APIs with detailed logging
            providers = [
                {
                    "name": "metals.live (gold)",
                    "url": "https://api.metals.live/v1/spot/gold",
                    "headers": None,
                },
                {
                    "name": "goldapi.io",
                    "url": "https://api.goldapi.io/api/XAU/USD",
                    "headers": {"x-access-token": "goldapi-1234567890abcdef"},
                },
                {
                    "name": "metals.live (silver estimate)",
                    "url": "https://api.metals.live/v1/spot/silver",
                    "headers": None,
                    "estimate_gold": True  # Estimate gold as 80x silver
                }
            ]
            
            errors = []
            for provider in providers:
                try:
                    print(f"[GOLD_PRICE] Trying {provider['name']}...")
                    print(f"   URL: {provider['url']}")
                    
                    response = session.get(
                        provider['url'], 
                        headers=provider.get('headers'),
                        timeout=(5, 10)
                    )
                    
                    print(f"   Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        response_preview = str(data)[:200]
                        print(f"   Response preview: {response_preview}")
                        
                        if provider.get('estimate_gold'):
                            # Estimate gold from silver
                            silver_price = float(data.get("price", 0))
                            if silver_price > 0:
                                gold_price = round(silver_price * 80, 2)
                                print(f"   ✅ Success: Estimated gold price = {gold_price} (from silver {silver_price})")
                                return gold_price
                        else:
                            price = float(data.get("price", 0))
                            if price > 0:
                                print(f"   ✅ Success: Gold price = {price}")
                                return price
                            else:
                                errors.append(f"{provider['name']}: price=0 in response")
                    else:
                        response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                        errors.append(f"{provider['name']}: HTTP {response.status_code} - {response_preview}")
                        print(f"   ❌ Failed: HTTP {response.status_code}")
                        print(f"   Response: {response_preview}")
                        
                except requests.exceptions.SSLError as e:
                    error_msg = log_request_error(provider['name'], provider['url'], e, session)
                    errors.append(error_msg)
                    print(f"   ❌ Failed: {error_msg}")
                except requests.exceptions.ConnectionError as e:
                    error_msg = log_request_error(provider['name'], provider['url'], e, session)
                    errors.append(error_msg)
                    print(f"   ❌ Failed: {error_msg}")
                except requests.exceptions.Timeout as e:
                    error_msg = log_request_error(provider['name'], provider['url'], e, session)
                    errors.append(error_msg)
                    print(f"   ❌ Failed: {error_msg}")
                except Exception as e:
                    error_msg = log_request_error(provider['name'], provider['url'], e, session)
                    errors.append(error_msg)
                    print(f"   ❌ Failed: {error_msg}")
            
            # All providers failed
            if len(providers) == 0:
                print("❌ [GOLD_PRICE] CONFIG_NO_GOLD_PRICE_PROVIDERS: No gold price providers configured")
                return None
            
            # Determine reason code
            has_ssl_errors = any('SSL' in err or 'SSLError' in err for err in errors)
            has_connection_errors = any('Connection' in err or 'ConnectionError' in err for err in errors)
            
            if has_ssl_errors:
                reason_code = "NETWORK_SSL_ERROR"
            elif has_connection_errors:
                reason_code = "NETWORK_CONNECTION_ERROR"
            else:
                reason_code = "PROVIDERS_UNAVAILABLE"
            
            print(f"❌ [GOLD_PRICE] All {len(providers)} gold price providers failed:")
            for error in errors:
                print(f"   - {error}")
            print(f"   Reason: {reason_code} (all {len(providers)} providers unavailable)")
            return None
        else:
            # Forex pairs from a free API
            url = f"https://api.fxratesapi.com/latest?base={pair[:3]}&symbols={pair[3:]}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "rates" in data and pair[3:] in data["rates"]:
                    return float(data["rates"][pair[3:]])
        
        print(f"❌ Could not get real forex price for {pair}")
        return None
        
    except Exception as e:
        print(f"❌ Error getting forex price for {pair}: {e}")
        return None


def get_real_crypto_price(pair):
    """Get real crypto price from Binance public API (no API key needed)"""
    try:
        # Use Binance public API - no authentication required
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
        else:
            print(f"❌ Error getting crypto price for {pair}: HTTP {response.status_code}")
            return None
        
    except Exception as e:
        print(f"❌ Error getting crypto price for {pair}: {e}")
        return None


# Finnhub.io Index Ticker Mapping (using ETF proxies - free tier)
# Note: ETF prices are approximate proxies for indices (typically 1/10th or 1/100th of index value)
FINNHUB_INDEX_TICKERS = {
    "S&P 500": "SPY",  # SPDR S&P 500 ETF Trust (proxy for ^GSPC)
    "Nasdaq 100": "QQQ",  # Invesco QQQ Trust (proxy for ^NDX)
    "Dow Jones": "DIA",  # SPDR Dow Jones Industrial Average ETF (proxy for ^DJI)
    # Additional common indices mapped to ETFs
    "US500": "SPY",  # S&P 500 alternative name -> SPY ETF
    "SPX500": "SPY",  # S&P 500 alternative name -> SPY ETF
    "USTEC": "QQQ",  # Nasdaq 100 alternative name -> QQQ ETF
    "US30": "DIA",  # Dow Jones alternative name -> DIA ETF
}


async def get_finnhub_index_price(symbol_name: str) -> float | None:
    """
    Fetch current index price from Finnhub.io API using ETF proxies
    
    Note: Uses ETF tickers (SPY, QQQ, DIA) as proxies for indices since direct
    index tickers require a paid subscription. ETF prices are approximate
    proxies (typically 1/10th or 1/100th of the actual index value).
    
    Args:
        symbol_name: Generic index name (e.g., "S&P 500", "Nasdaq 100", "Dow Jones")
                    or ticker symbol (e.g., "US500", "USTEC", "US30")
    
    Returns:
        Current ETF price (float) or None if error/not found
    """
    # Map generic name to ETF ticker
    ticker = FINNHUB_INDEX_TICKERS.get(symbol_name)
    if not ticker:
        # If not found in mapping, try using the symbol_name directly (might already be an ETF ticker)
        ticker = symbol_name
    
    api_key = Config.FINNHUB_API_KEY
    if not api_key:
        print(f"❌ Finnhub API key not configured")
        return None
    
    url = "https://finnhub.io/api/v1/quote"
    headers = {
        "X-Finnhub-Token": api_key
    }
    params = {
        "symbol": ticker
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for API errors
                if "error" in data:
                    print(f"❌ Finnhub API error for {symbol_name} ({ticker}): {data.get('error', 'Unknown error')}")
                    return None
                
                # Get current price from "c" field
                current_price = data.get("c")
                
                if current_price is None:
                    print(f"❌ No price data in Finnhub response for {symbol_name} ({ticker})")
                    return None
                
                if current_price <= 0:
                    print(f"⚠️ Invalid price from Finnhub for {symbol_name} ({ticker}): {current_price}")
                    return None
                
                print(f"✅ Index price available: {symbol_name} ({ticker} ETF) = {current_price} (from Finnhub - ETF proxy)")
                return float(current_price)
            
            elif response.status_code == 429:
                print(f"❌ Finnhub API rate limit reached for {symbol_name}")
                return None
            
            elif response.status_code == 401:
                print(f"❌ Finnhub API authentication failed - check API key")
                return None
            
            else:
                print(f"❌ Finnhub API error for {symbol_name}: HTTP {response.status_code}")
                return None
                
    except httpx.TimeoutException:
        print(f"❌ Finnhub API timeout for {symbol_name}")
        return None
    except httpx.RequestError as e:
        print(f"❌ Finnhub API request error for {symbol_name}: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error fetching Finnhub price for {symbol_name}: {e}")
        return None


def get_real_index_price(pair):
    """Get real index price (stock indices via Finnhub, or oil/gold via existing methods)"""
    try:
        # Check if it's a stock index that should use Finnhub
        stock_indices = ["US500", "USTEC", "US30", "SPX500", "S&P 500", "Nasdaq 100", "Dow Jones"]
        if pair in stock_indices or pair in FINNHUB_INDEX_TICKERS:
            # Use Finnhub for stock indices
            try:
                # Run async function in sync context
                # Try to get existing event loop, if none exists or it's closed, create new one
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    # If loop is already running, we need to use a different approach
                    # Create a new event loop in a thread
                    import concurrent.futures
                    import threading
                    
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            return new_loop.run_until_complete(get_finnhub_index_price(pair))
                        finally:
                            new_loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_in_thread)
                        price = future.result(timeout=10)
                else:
                    price = loop.run_until_complete(get_finnhub_index_price(pair))
                
                if price:
                    return price
            except Exception as e:
                print(f"⚠️ Finnhub API failed for {pair}: {e}")
                return None
        
        if pair == "XAUUSD":
            # Use existing gold price function
            price = get_real_forex_price("XAUUSD")
            if price:
                print(f"✅ Index price available: {pair} = {price}")
            else:
                print(f"❌ Index price NOT available: {pair}")
            return price
        elif pair == "USOIL":
            # WTI Crude Oil price from free APIs with multiple fallbacks
            # Try Method 1: Yahoo Finance API (free, no key required)
            try:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=1d"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "chart" in data and "result" in data["chart"]:
                        result = data["chart"]["result"]
                        if result and len(result) > 0:
                            meta = result[0].get("meta", {})
                            # Try multiple price fields
                            price = (meta.get("regularMarketPrice") or 
                                    meta.get("previousClose") or 
                                    meta.get("chartPreviousClose"))
                            if price and price > 0:
                                price_value = float(price)
                                print(f"✅ Index price available: USOIL = {price_value} (from Yahoo Finance)")
                                return price_value
                            # Try getting from quote array if meta doesn't have price
                            quote = result[0].get("indicators", {}).get("quote", [])
                            if quote and len(quote) > 0:
                                close_prices = quote[0].get("close", [])
                                if close_prices and len(close_prices) > 0:
                                    price = close_prices[-1]
                                    if price and price > 0:
                                        price_value = float(price)
                                        print(f"✅ Index price available: USOIL = {price_value} (from Yahoo Finance quote)")
                                        return price_value
            except Exception as e:
                print(f"⚠️ Yahoo Finance API failed: {e}")

            # Try Method 2: Investing.com via scraping (fallback)
            try:
                url = "https://www.investing.com/commodities/crude-oil"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Look for price pattern in HTML
                    price_match = re.search(r'data-test="instrument-price-last">([\d,]+\.?\d*)', response.text)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        if price > 0:
                            return price
            except Exception as e:
                print(f"⚠️ Investing.com scraping failed: {e}")

            # Try Method 3: Alpha Vantage (free tier, but needs API key - using demo)
            try:
                url = "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=CL1&apikey=demo"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "Global Quote" in data:
                        price_str = data["Global Quote"].get("05. price")
                        if price_str:
                            price = float(price_str)
                            if price > 0:
                                return price
            except Exception as e:
                print(f"⚠️ Alpha Vantage API failed: {e}")

            # Try Method 4: MarketStack (free tier, but needs API key - using demo)
            try:
                url = "https://api.marketstack.com/v1/eod/latest?symbols=CL1.XNYM&access_key=demo"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and len(data["data"]) > 0:
                        price = data["data"][0].get("close")
                        if price and price > 0:
                            return float(price)
            except Exception as e:
                print(f"⚠️ MarketStack API failed: {e}")

            print(f"❌ Index price NOT available: USOIL - Could not get price from any API source")
            return None
        elif pair == "BRENT":
            # Brent Crude Oil price from free APIs with multiple fallbacks
            # Try Method 1: Yahoo Finance API (free, no key required)
            try:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=1d"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "chart" in data and "result" in data["chart"]:
                        result = data["chart"]["result"]
                        if result and len(result) > 0:
                            meta = result[0].get("meta", {})
                            # Try multiple price fields
                            price = (meta.get("regularMarketPrice") or 
                                    meta.get("previousClose") or 
                                    meta.get("chartPreviousClose"))
                            if price and price > 0:
                                price_value = float(price)
                                print(f"✅ Index price available: BRENT = {price_value} (from Yahoo Finance)")
                                return price_value
                            # Try getting from quote array if meta doesn't have price
                            quote = result[0].get("indicators", {}).get("quote", [])
                            if quote and len(quote) > 0:
                                close_prices = quote[0].get("close", [])
                                if close_prices and len(close_prices) > 0:
                                    price = close_prices[-1]
                                    if price and price > 0:
                                        price_value = float(price)
                                        print(f"✅ Index price available: BRENT = {price_value} (from Yahoo Finance quote)")
                                        return price_value
            except Exception as e:
                print(f"⚠️ Yahoo Finance API failed for BRENT: {e}")

            # Try Method 2: Investing.com via scraping (fallback)
            try:
                url = "https://www.investing.com/commodities/brent-oil"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Look for price pattern in HTML
                    price_match = re.search(r'data-test="instrument-price-last">([\d,]+\.?\d*)', response.text)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '')
                        price = float(price_str)
                        if price > 0:
                            print(f"✅ Index price available: BRENT = {price} (from Investing.com)")
                            return price
            except Exception as e:
                print(f"⚠️ Investing.com scraping failed for BRENT: {e}")

            # Try Method 3: Alpha Vantage (free tier, but needs API key - using demo)
            try:
                url = "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=CO1&apikey=demo"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if "Global Quote" in data:
                        price_str = data["Global Quote"].get("05. price")
                        if price_str:
                            price = float(price_str)
                            if price > 0:
                                print(f"✅ Index price available: BRENT = {price} (from Alpha Vantage)")
                                return price
            except Exception as e:
                print(f"⚠️ Alpha Vantage API failed for BRENT: {e}")

            print(f"❌ Index price NOT available: BRENT - Could not get price from any API source")
            return None

        print(f"❌ Index price NOT available: {pair} - Unknown pair")
        return None

    except Exception as e:
        print(f"❌ Index price NOT available: {pair} - Error: {e}")
        return None


def load_signals():
    """Load today's signals"""
    try:
        with open(SIGNALS_FILE, 'r') as f:
            signals = json.load(f)
            # Ensure all required keys exist
            if "forex_3tp" not in signals:
                signals["forex_3tp"] = []
            if "forex_additional" not in signals:
                signals["forex_additional"] = []
            if "forwarded_forex" not in signals:
                signals["forwarded_forex"] = []
            if "tp_notifications" not in signals:
                signals["tp_notifications"] = []
            if "indexes" not in signals:
                signals["indexes"] = []
            if "crypto_lingrid" not in signals:
                signals["crypto_lingrid"] = []
            if "crypto_gainmuse" not in signals:
                signals["crypto_gainmuse"] = []
            if "gold_private" not in signals:
                signals["gold_private"] = []
            return signals
    except:
        return {
            "forex": [], 
            "forex_3tp": [], 
            "forex_additional": [],
            "crypto_lingrid": [],
            "crypto_gainmuse": [],
            "indexes": [],
            "gold_private": [],
            "forwarded_forex": [],
            "tp_notifications": [],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }


def save_signals(signals):
    """Save signals"""
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f, indent=2)


def get_last_signal_time():
    """Get the timestamp of the last signal sent"""
    try:
        with open(LAST_SIGNAL_TIME_FILE, 'r') as f:
            data = json.load(f)
            last_time_str = data.get("last_signal_time", "")
            if last_time_str:
                return datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
            return None
    except:
        return None


def save_last_signal_time():
    """Save the current time as the last signal time (global - for 5 min between channels)"""
    current_time = datetime.now(timezone.utc)
    data = {"last_signal_time": current_time.isoformat()}
    with open(LAST_SIGNAL_TIME_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_channel_last_signal_time(channel_id):
    """Get the timestamp of the last signal sent to a specific channel"""
    try:
        with open(CHANNEL_LAST_SIGNAL_FILE, 'r') as f:
            data = json.load(f)
            channel_times = data.get("channel_times", {})
            last_time_str = channel_times.get(channel_id, "")
            if last_time_str:
                return datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
            return None
    except:
        return None


def save_channel_last_signal_time(channel_id):
    """Save the current time as the last signal time for a specific channel (for 2h between same channel)"""
    current_time = datetime.now(timezone.utc)
    try:
        with open(CHANNEL_LAST_SIGNAL_FILE, 'r') as f:
            data = json.load(f)
    except:
        data = {"channel_times": {}}

    if "channel_times" not in data:
        data["channel_times"] = {}

    data["channel_times"][channel_id] = current_time.isoformat()

    with open(CHANNEL_LAST_SIGNAL_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_channel_pair_last_signal_time(channel_id, pair):
    """Get the timestamp of the last signal sent for a specific pair in a specific channel"""
    try:
        with open(CHANNEL_PAIR_LAST_SIGNAL_FILE, 'r') as f:
            data = json.load(f)
            channel_data = data.get("channel_pairs", {})
            channel_pairs = channel_data.get(channel_id, {})
            last_time_str = channel_pairs.get(pair, "")
            if last_time_str:
                return datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
            return None
    except:
        return None


def save_channel_pair_last_signal_time(channel_id, pair):
    """Save the current time as the last signal time for a specific pair in a specific channel (36h between same pair)"""
    current_time = datetime.now(timezone.utc)
    try:
        with open(CHANNEL_PAIR_LAST_SIGNAL_FILE, 'r') as f:
            data = json.load(f)
    except:
        data = {"channel_pairs": {}}

    if "channel_pairs" not in data:
        data["channel_pairs"] = {}

    if channel_id not in data["channel_pairs"]:
        data["channel_pairs"][channel_id] = {}

    data["channel_pairs"][channel_id][pair] = current_time.isoformat()

    with open(CHANNEL_PAIR_LAST_SIGNAL_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def can_send_pair_signal_to_channel(channel_id, pair, return_reason=False):
    """Check if 36 hours have passed since last signal for this pair in this channel
    
    Args:
        channel_id: Channel ID
        pair: Trading pair (e.g., "XAUUSD")
        return_reason: If True, returns (bool, reason_code, details_dict) instead of just bool
    
    Returns:
        If return_reason=False: bool
        If return_reason=True: (bool, SignalRejectReason, dict with details)
    """
    current_time = datetime.now(timezone.utc)
    pair_last_time = get_channel_pair_last_signal_time(channel_id, pair)
    
    details = {
        "channel_id": channel_id,
        "pair": pair,
        "current_time": current_time.isoformat(),
        "pair_last_time": pair_last_time.isoformat() if pair_last_time else None,
        "time_diff_seconds": None,
        "required_wait_seconds": None
    }
    
    if pair_last_time is not None:
        time_diff = (current_time - pair_last_time).total_seconds()
        details["time_diff_seconds"] = time_diff
        min_pair_interval_seconds = 36 * 60 * 60  # 36 hours minimum between same pair in same channel

        if time_diff < min_pair_interval_seconds:
            remaining_seconds = min_pair_interval_seconds - time_diff
            remaining_hours = remaining_seconds / 3600
            details["required_wait_seconds"] = remaining_seconds
            details["remaining_hours"] = remaining_hours
            
            if return_reason:
                return False, SignalRejectReason.RULE_36H, details
            
            print(f"⏰ Cannot send signal for {pair} to channel {channel_id}: 36-hour interval not met. Wait {remaining_hours:.2f} more hours.")
            return False
    
    if return_reason:
        return True, SignalRejectReason.SUCCESS, details
    return True


def can_send_signal_now(channel_id=None, return_reason=False):
    """Check if enough time has passed:
    - 5 minutes since last signal from ANY channel (different channels)
    - 2 hours since last signal from SAME channel (if channel_id provided)
    
    Args:
        channel_id: Channel ID to check
        return_reason: If True, returns (bool, reason_code, details_dict) instead of just bool
    
    Returns:
        If return_reason=False: bool
        If return_reason=True: (bool, SignalRejectReason, dict with details)
    """
    current_time = datetime.now(timezone.utc)
    details = {
        "channel_id": channel_id,
        "current_time": current_time.isoformat(),
        "last_signal_time": None,
        "channel_last_time": None,
        "time_diff_seconds": None,
        "required_wait_seconds": None
    }

    # Check 5 minutes between different channels
    last_time = get_last_signal_time()
    details["last_signal_time"] = last_time.isoformat() if last_time else None
    
    if last_time is not None:
        time_diff = (current_time - last_time).total_seconds()
        details["time_diff_seconds"] = time_diff
        min_interval_seconds = 5 * 60  # 5 minutes minimum between signals from different channels

        if time_diff < min_interval_seconds:
            remaining_seconds = min_interval_seconds - time_diff
            remaining_minutes = remaining_seconds / 60
            details["required_wait_seconds"] = remaining_seconds
            details["remaining_minutes"] = remaining_minutes
            
            if return_reason:
                return False, SignalRejectReason.THROTTLE_MIN_INTERVAL, details
            
            print(f"⏰ Minimum 5-minute interval between channels not met. Wait {remaining_minutes:.1f} more minutes.")
            return False

    # Check 2 hours between same channel (if channel_id provided)
    if channel_id is not None:
        channel_last_time = get_channel_last_signal_time(channel_id)
        details["channel_last_time"] = channel_last_time.isoformat() if channel_last_time else None
        
        if channel_last_time is not None:
            time_diff = (current_time - channel_last_time).total_seconds()
            details["channel_time_diff_seconds"] = time_diff
            min_channel_interval_seconds = 2 * 60 * 60  # 2 hours minimum between signals from same channel

            if time_diff < min_channel_interval_seconds:
                remaining_seconds = min_channel_interval_seconds - time_diff
                remaining_hours = remaining_seconds / 3600
                details["required_wait_seconds"] = remaining_seconds
                details["remaining_hours"] = remaining_hours
                
                if return_reason:
                    return False, SignalRejectReason.THROTTLE_CHANNEL_INTERVAL, details
                
                print(f"⏰ Minimum 2-hour interval for this channel not met. Wait {remaining_hours:.2f} more hours.")
                return False

    if return_reason:
        return True, SignalRejectReason.SUCCESS, details
    return True


def load_performance():
    """Load performance data"""
    try:
        with open(PERFORMANCE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"forex": [], "crypto": [], "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


def calculate_signal_profit(signal, current_price):
    """Calculate profit for a signal with proper units (pips for forex, % for crypto)"""
    try:
        pair = signal.get("pair", "")
        signal_type = signal.get("type", "")
        entry = signal.get("entry", 0)
        sl = signal.get("sl", 0)
        
        # Determine if it's crypto or forex
        is_crypto = pair in CRYPTO_PAIRS
        
        if is_crypto:
            # Crypto signals: Calculate profit in percentage
            if signal_type == "BUY":
                profit_pct = ((current_price - entry) / entry) * 100
            else:  # SELL
                profit_pct = ((entry - current_price) / entry) * 100
            return profit_pct
        else:
            # Forex signals: Calculate profit in pips
            if pair.endswith("JPY"):
                # JPY pairs use 3 decimal places, so multiply by 1000
                multiplier = 1000
            else:
                # Other pairs use 5 decimal places, so multiply by 10000
                multiplier = 10000
            
            if signal_type == "BUY":
                profit_pips = (current_price - entry) * multiplier
            else:  # SELL
                profit_pips = (entry - current_price) * multiplier
            
            return profit_pips
                    
    except Exception as e:
        print(f"❌ Error calculating profit for {pair}: {e}")
        return 0


def get_performance_summary(signals_list, days=1):
    """Get comprehensive performance summary for signals"""
    try:
        if not signals_list:
            return {
                "total_signals": 0,
                "profit_signals": 0,
                "loss_signals": 0,
                "total_profit": 0,
                "avg_profit_per_signal": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "signals_detail": []
            }
        
        # Filter signals by date range
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        filtered_signals = []
        
        for signal in signals_list:
            try:
                signal_date = datetime.fromisoformat(signal.get("timestamp", "").replace("Z", "+00:00"))
                if signal_date >= cutoff_date:
                    filtered_signals.append(signal)
            except:
                # If timestamp parsing fails, include the signal
                filtered_signals.append(signal)
        
        if not filtered_signals:
            return {
                "total_signals": 0,
                "profit_signals": 0,
                "loss_signals": 0,
                "total_profit": 0,
                "avg_profit_per_signal": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "signals_detail": []
            }
        
        # Calculate performance for each signal
        signals_detail = []
        total_profit = 0
        profit_count = 0
        loss_count = 0
        profit_values = []
        loss_values = []
        
        for signal in filtered_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            
            # Get current price
            if pair in CRYPTO_PAIRS:
                current_price = get_real_crypto_price(pair)
            else:
                current_price = get_real_forex_price(pair)
            
            if current_price is None:
                continue
            
            # Calculate profit
            profit_value = calculate_signal_profit(signal, current_price)
            
            # Determine unit and format display
            is_crypto = pair in CRYPTO_PAIRS
            if is_crypto:
                # Crypto: profit in percentage
                unit = "%"
                profit_display = f"{profit_value:+.2f}{unit}"
            else:
                # Forex: profit in pips
                unit = " pips"
                profit_display = f"{profit_value:+.1f}{unit}"
            
            if profit_value > 0:
                profit_count += 1
                total_profit += profit_value
                profit_values.append(profit_value)
                signals_detail.append(f"✅ {pair} {signal_type}: {profit_display}")
            elif profit_value < 0:
                loss_count += 1
                total_profit += profit_value
                loss_values.append(abs(profit_value))
                signals_detail.append(f"❌ {pair} {signal_type}: {profit_display}")
            else:
                signals_detail.append(f"➖ {pair} {signal_type}: 0.00{unit}")
        
        # Calculate advanced statistics
        total_signals = len(filtered_signals)
        avg_profit_per_signal = total_profit / total_signals if total_signals > 0 else 0
        win_rate = (profit_count / total_signals * 100) if total_signals > 0 else 0
        avg_profit = sum(profit_values) / len(profit_values) if profit_values else 0
        avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0
        
        # Calculate profit factor
        total_profit_sum = sum(profit_values) if profit_values else 0
        total_loss_sum = sum(loss_values) if loss_values else 0
        profit_factor = total_profit_sum / total_loss_sum if total_loss_sum > 0 else float('inf')
        
        return {
            "total_signals": total_signals,
            "profit_signals": profit_count,
            "loss_signals": loss_count,
            "total_profit": total_profit,
            "avg_profit_per_signal": avg_profit_per_signal,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "signals_detail": signals_detail
        }
        
    except Exception as e:
        print(f"❌ Error calculating performance summary: {e}")
        return {
            "total_signals": 0,
            "profit_signals": 0,
            "loss_signals": 0,
            "total_profit": 0,
            "avg_profit_per_signal": 0,
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "signals_detail": []
        }


def save_performance(performance):
    """Save performance data"""
    with open(PERFORMANCE_FILE, 'w') as f:
        json.dump(performance, f, indent=2)


def load_channel_results(channel_id):
    """Load results for a specific channel"""
    results_file = CHANNEL_RESULTS.get(channel_id, f"results_{channel_id}.json")
    try:
        with open(results_file, 'r') as f:
            return json.load(f)
    except:
        return []


def load_channel_signals(channel_id):
    """Load signals for a specific channel"""
    signals_file = CHANNEL_SIGNALS.get(channel_id, f"signals_{channel_id}.json")
    try:
        with open(signals_file, 'r') as f:
            data = json.load(f)
            return data.get("signals", [])
    except:
        return []


def save_channel_signal(channel_id, signal_data):
    """Save a signal to channel-specific file"""
    signals_file = CHANNEL_SIGNALS.get(channel_id, f"signals_{channel_id}.json")
    signals = load_channel_signals(channel_id)

    # Add signal with metadata
    signal_entry = {
        **signal_data,
        "channel_id": channel_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    signals.append(signal_entry)

    # Save to file
    data = {
        "channel_id": channel_id,
        "signals": signals,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }

    with open(signals_file, 'w') as f:
        json.dump(data, f, indent=2)


def save_channel_result(channel_id, result_data):
    """Save a result to channel-specific file with improved tracking"""
    results_file = CHANNEL_RESULTS.get(channel_id, f"results_{channel_id}.json")
    results = load_channel_results(channel_id)

    # Check if we already have a result for this signal timestamp
    signal_timestamp = result_data.get("timestamp", "")
    existing_idx = None
    for idx, existing in enumerate(results):
        if existing.get("timestamp") == signal_timestamp:
            existing_idx = idx
            break

    if existing_idx is not None:
        # Update existing result - apply logic: if TP hit then SL hit, keep the TP
        existing_result = results[existing_idx]
        new_hit_type = result_data.get("hit_type", "")

        # Logic: If TP was hit and now SL hit, keep the TP
        if existing_result.get("hit_type", "").startswith("TP") and new_hit_type == "SL":
            # Keep the TP result, don't update
            return
        elif new_hit_type.startswith("TP"):
            # If new TP is higher than existing TP, update
            existing_tp = existing_result.get("hit_type", "")
            tp_order = {"TP1": 1, "TP2": 2, "TP3": 3, "TP": 1}
            if tp_order.get(new_hit_type, 0) > tp_order.get(existing_tp, 0):
                results[existing_idx] = result_data
        else:
            # Update with new result
            results[existing_idx] = result_data
    else:
        # New result
        results.append(result_data)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)


async def check_and_notify_tp_hits():
    """Check all active signals for TP/SL hits every 30 minutes and send notifications"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            return  # No signals for today
        
        bot = Bot(token=BOT_TOKEN)
        notifications_sent = signals.get("tp_notifications", [])
        
        # Check forex signals (2 TPs for main pairs, 1 TP for XAUUSD)
        forex_signals = signals.get("forex", [])
        for signal in forex_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
                # Check for SL first (priority)
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                    sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                    sl_hit = True

                # Check for TP hits based on pair type (only if SL not hit)
            tp_hit = None
            profit_percent = 0
            
            if not sl_hit:

            
                if pair == "XAUUSD":
                    # XAUUSD: Single TP
                    tp = signal.get("tp", 0)
                    if signal_type == "BUY" and current_price >= tp:
                        tp_hit = "TP"
                        profit_percent = ((tp - entry) / entry) * 100
                    elif signal_type == "SELL" and current_price <= tp:
                        tp_hit = "TP"
                        profit_percent = ((entry - tp) / entry) * 100
                else:
                    # Main forex pairs: 2 TPs
                    tp1 = signal.get("tp1", 0)
                    tp2 = signal.get("tp2", 0)
                    
                    if signal_type == "BUY":
                        if current_price >= tp2:
                            tp_hit = "TP2"
                            profit_percent = ((tp2 - entry) / entry) * 100
                        elif current_price >= tp1:
                            tp_hit = "TP1"
                            profit_percent = ((tp1 - entry) / entry) * 100
                    else:  # SELL
                        if current_price <= tp2:
                            tp_hit = "TP2"
                            profit_percent = ((entry - tp2) / entry) * 100
                        elif current_price <= tp1:
                            tp_hit = "TP1"
                            profit_percent = ((entry - tp1) / entry) * 100
            
                            # Process SL hit
            if sl_hit and timestamp not in notifications_sent:
                # Calculate loss in pips for forex
                if pair.endswith("JPY"):
                    multiplier = 1000
                else:
                    multiplier = 10000

                if signal_type == "BUY":
                    loss_pips = (sl - entry) * multiplier
                else:  # SELL
                    loss_pips = (entry - sl) * multiplier

                    # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": "SL",
                    "current_price": current_price,
                    "loss_pips": loss_pips,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": FOREX_CHANNEL
                }
                save_channel_result(FOREX_CHANNEL, result_data)

                notifications_sent.append(timestamp)
                print(f"❌ SL hit for {pair} {signal_type}: -{abs(loss_pips):.1f} pips (saved to results file)")

            # Process TP hit
            elif tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forex
                if pair.endswith("JPY"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    if tp_hit == "TP1":
                        profit_pips = (signal.get("tp1", 0) - entry) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (signal.get("tp2", 0) - entry) * multiplier
                    else:  # Single TP
                        profit_pips = (signal.get("tp", 0) - entry) * multiplier
                else:  # SELL
                    if tp_hit == "TP1":
                        profit_pips = (entry - signal.get("tp1", 0)) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (entry - signal.get("tp2", 0)) * multiplier
                    else:  # Single TP
                        profit_pips = (entry - signal.get("tp", 0)) * multiplier
                
                # Calculate R/R ratio for forex
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((signal.get("tp1", 0) - entry) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((signal.get("tp2", 0) - entry) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((signal.get("tp", 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((entry - signal.get("tp1", 0)) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((entry - signal.get("tp2", 0)) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((entry - signal.get("tp", 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to forex channels
                if tp_hit == "TP2":
                    message = f"#{pair}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                else:
                    message = f"#{pair}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                    # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": tp_hit,
                    "current_price": current_price,
                    "profit_pips": profit_pips,
                    "rr_ratio": rr_ratio,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": FOREX_CHANNEL
                }
                save_channel_result(FOREX_CHANNEL, result_data)

                await bot.send_message(chat_id=FOREX_CHANNEL, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_pips:.1f} pips (saved to results file)")
        
        # Check forex additional channel signals
        forex_additional_signals = signals.get("forex_additional", [])
        for signal in forex_additional_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
                # Check for SL first (priority)
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                    sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                    sl_hit = True

                # Check for TP hits based on pair type (only if SL not hit)
            tp_hit = None
            profit_percent = 0
            
            if not sl_hit:

            
                if pair == "XAUUSD":
                    # XAUUSD: Single TP
                    tp = signal.get("tp", 0)
                    if signal_type == "BUY" and current_price >= tp:
                        tp_hit = "TP"
                        profit_percent = ((tp - entry) / entry) * 100
                    elif signal_type == "SELL" and current_price <= tp:
                        tp_hit = "TP"
                        profit_percent = ((entry - tp) / entry) * 100
            else:
                # Main forex pairs: 2 TPs
                tp1 = signal.get("tp1", 0)
                tp2 = signal.get("tp2", 0)
                
                if signal_type == "BUY":
                    if current_price >= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((tp2 - entry) / entry) * 100
                    elif current_price >= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((tp1 - entry) / entry) * 100
                else:  # SELL
                    if current_price <= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((entry - tp2) / entry) * 100
                    elif current_price <= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((entry - tp1) / entry) * 100
            
                        # Process SL hit
            if sl_hit and timestamp not in notifications_sent:
                # Calculate loss in pips for forex additional
                if pair.endswith("JPY"):
                    multiplier = 1000
                else:
                    multiplier = 10000

                if signal_type == "BUY":
                    loss_pips = (sl - entry) * multiplier
                else:  # SELL
                    loss_pips = (entry - sl) * multiplier

                    # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": "SL",
                    "current_price": current_price,
                    "loss_pips": loss_pips,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": FOREX_CHANNEL_ADDITIONAL
                }
                save_channel_result(FOREX_CHANNEL_ADDITIONAL, result_data)

                notifications_sent.append(timestamp)
                print(f"❌ SL hit for additional {pair} {signal_type}: -{abs(loss_pips):.1f} pips (saved to results file)")

            # Process TP hit
            elif tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forex additional
                if pair.endswith("JPY"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    if tp_hit == "TP1":
                        profit_pips = (signal.get("tp1", 0) - entry) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (signal.get("tp2", 0) - entry) * multiplier
                    else:  # Single TP
                        profit_pips = (signal.get("tp", 0) - entry) * multiplier
                else:  # SELL
                    if tp_hit == "TP1":
                        profit_pips = (entry - signal.get("tp1", 0)) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (entry - signal.get("tp2", 0)) * multiplier
                    else:  # Single TP
                        profit_pips = (entry - signal.get("tp", 0)) * multiplier
                
                # Calculate R/R ratio for forex additional
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((signal.get("tp1", 0) - entry) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((signal.get("tp2", 0) - entry) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((signal.get("tp", 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((entry - signal.get("tp1", 0)) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((entry - signal.get("tp2", 0)) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((entry - signal.get("tp", 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to additional forex channel
                if tp_hit == "TP2":
                    message = f"#{pair}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                else:
                    message = f"#{pair}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                    # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": tp_hit,
                    "current_price": current_price,
                    "profit_pips": profit_pips,
                    "rr_ratio": rr_ratio,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": FOREX_CHANNEL_ADDITIONAL
                }
                save_channel_result(FOREX_CHANNEL_ADDITIONAL, result_data)

                await bot.send_message(chat_id=FOREX_CHANNEL_ADDITIONAL, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for additional {pair} {signal_type}: +{profit_pips:.1f} pips (saved to results file)")
        
        # Check forex 3TP signals
        forex_3tp_signals = signals.get("forex_3tp", [])
        for signal in forex_3tp_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp1 = signal.get("tp1", 0)
            tp2 = signal.get("tp2", 0)
            tp3 = signal.get("tp3", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
                # Check for SL first (priority)
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                    sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                    sl_hit = True

                # Check for TP hits (only if SL not hit)
            tp_hit = None
            profit_percent = 0
            
            if not sl_hit:
                if signal_type == "BUY":
                    if current_price >= tp3:
                        tp_hit = "TP3"
                        profit_percent = ((tp3 - entry) / entry) * 100
                    elif current_price >= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((tp2 - entry) / entry) * 100
                    elif current_price >= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((tp1 - entry) / entry) * 100
                else:  # SELL
                    if current_price <= tp3:
                        tp_hit = "TP3"
                        profit_percent = ((entry - tp3) / entry) * 100
                    elif current_price <= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((entry - tp2) / entry) * 100
                    elif current_price <= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((entry - tp1) / entry) * 100
            
                    # Process SL hit
                    if sl_hit and timestamp not in notifications_sent:
                        # Calculate loss in pips for forex 3TP
                        if pair.endswith("JPY"):
                            multiplier = 1000
                        else:
                            multiplier = 10000

                        if signal_type == "BUY":
                            loss_pips = (sl - entry) * multiplier
                        else:  # SELL
                            loss_pips = (entry - sl) * multiplier

                        # Save result to channel file
                        result_data = {
                            "pair": pair,
                            "type": signal_type,
                            "entry": entry,
                            "sl": sl,
                            "hit_type": "SL",
                            "current_price": current_price,
                            "loss_pips": loss_pips,
                            "timestamp": timestamp,
                            "hit_time": datetime.now(timezone.utc).isoformat(),
                            "channel": FOREX_CHANNEL_3TP
                        }
                        save_channel_result(FOREX_CHANNEL_3TP, result_data)

                        notifications_sent.append(timestamp)
                        print(f"❌ SL hit for 3TP {pair} {signal_type}: -{abs(loss_pips):.1f} pips (saved to results file)")

            # Process TP hit
            elif tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forex 3TP
                if pair.endswith("JPY"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    profit_pips = (signal.get(tp_hit.lower(), 0) - entry) * multiplier
                else:  # SELL
                    profit_pips = (entry - signal.get(tp_hit.lower(), 0)) * multiplier
                
                # Calculate R/R ratio for forex 3TP
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    reward_pips = ((signal.get(tp_hit.lower(), 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    reward_pips = ((entry - signal.get(tp_hit.lower(), 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to forex 3TP channel
                if tp_hit == "TP3":
                    message = f"🎯 {pair} {signal_type} - All targets achieved! +{profit_pips:.1f} pips profit"
                elif tp_hit == "TP2":
                    message = f"✅ {pair} {signal_type} - TP2 hit! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                else:  # TP1
                    message = f"📈 {pair} {signal_type} - TP1 reached! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                    # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": tp_hit,
                    "current_price": current_price,
                    "profit_pips": profit_pips,
                    "rr_ratio": rr_ratio,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": FOREX_CHANNEL_3TP
                }
                save_channel_result(FOREX_CHANNEL_3TP, result_data)

                await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_pips:.1f} pips (saved to results file)")
        
        # Check crypto signals
        crypto_signals = signals.get("crypto", [])
        for signal in crypto_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp1 = signal.get("tp1", 0)
            tp2 = signal.get("tp2", 0)
            tp3 = signal.get("tp3", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_crypto_price(pair)
            if current_price is None:
                continue
            
                # Check for SL first (priority)
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                    sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                    sl_hit = True

                # Check for TP hits (only if SL not hit)
            tp_hit = None
            profit_percent = 0
            
            if not sl_hit:
                if signal_type == "BUY":
                    if current_price >= tp3:
                        tp_hit = "TP3"
                        profit_percent = ((tp3 - entry) / entry) * 100
                    elif current_price >= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((tp2 - entry) / entry) * 100
                    elif current_price >= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((tp1 - entry) / entry) * 100
                else:  # SELL
                    if current_price <= tp3:
                        tp_hit = "TP3"
                        profit_percent = ((entry - tp3) / entry) * 100
                    elif current_price <= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((entry - tp2) / entry) * 100
                    elif current_price <= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((entry - tp1) / entry) * 100
            
                    # Process SL hit
                    if sl_hit and timestamp not in notifications_sent:
                        # Calculate loss percentage for crypto
                        if signal_type == "BUY":
                            loss_percent = ((sl - entry) / entry) * 100
                        else:  # SELL
                            loss_percent = ((entry - sl) / entry) * 100

                    # Save result to both crypto channel files
                    result_data_lingrid = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": "SL",
                    "current_price": current_price,
                    "loss_percent": loss_percent,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": CRYPTO_CHANNEL_LINGRID
                }
                result_data_gainmuse = result_data_lingrid.copy()
                result_data_gainmuse["channel"] = CRYPTO_CHANNEL_GAINMUSE

                save_channel_result(CRYPTO_CHANNEL_LINGRID, result_data_lingrid)
                save_channel_result(CRYPTO_CHANNEL_GAINMUSE, result_data_gainmuse)

                notifications_sent.append(timestamp)
                print(f"❌ SL hit for {pair} {signal_type}: -{abs(loss_percent):.2f}% (saved to results files)")

            # Process TP hit
            elif tp_hit and timestamp not in notifications_sent:
                # Calculate R/R ratio for crypto
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    reward_pips = ((signal.get(tp_hit.lower(), 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    reward_pips = ((entry - signal.get(tp_hit.lower(), 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to crypto channels
                if tp_hit == "TP3":
                    message = f"#{pair}: Both targets 🚀🚀 hit +{profit_percent:.1f}% total gain!"
                else:
                    message = f"#{pair}: TP{tp_hit[-1]} reached ⚡️ +{profit_percent:.1f}% (R/R 1:{rr_ratio:.1f})"
                
                    # Save result to both crypto channel files
                result_data_lingrid = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": tp_hit,
                    "current_price": current_price,
                    "profit_percent": profit_percent,
                    "rr_ratio": rr_ratio,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": CRYPTO_CHANNEL_LINGRID
                }
                result_data_gainmuse = result_data_lingrid.copy()
                result_data_gainmuse["channel"] = CRYPTO_CHANNEL_GAINMUSE

                save_channel_result(CRYPTO_CHANNEL_LINGRID, result_data_lingrid)
                save_channel_result(CRYPTO_CHANNEL_GAINMUSE, result_data_gainmuse)

                await bot.send_message(chat_id=CRYPTO_CHANNEL_LINGRID, text=message, parse_mode='Markdown')
                await bot.send_message(chat_id=CRYPTO_CHANNEL_GAINMUSE, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_percent:.2f}% (saved to results files)")
        
        # Check forwarded forex signals
        forwarded_signals = signals.get("forwarded_forex", [])
        for signal in forwarded_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp = signal.get("tp", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
                # Check for SL first (priority)
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                    sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                    sl_hit = True

                # Check for TP hit (only if SL not hit)
            tp_hit = False
            profit_percent = 0
            if not sl_hit:
                if signal_type == "BUY" and current_price >= tp:
                    tp_hit = True
                    profit_percent = ((tp - entry) / entry) * 100
                elif signal_type == "SELL" and current_price <= tp:
                    tp_hit = True
                    profit_percent = ((entry - tp) / entry) * 100
            
            # Process SL hit
            if sl_hit and timestamp not in notifications_sent:
                # Calculate loss in pips for forwarded forex
                if pair.endswith("JPY"):
                    multiplier = 1000
                else:
                    multiplier = 10000

                if signal_type == "BUY":
                    loss_pips = (sl - entry) * multiplier
                else:  # SELL
                    loss_pips = (entry - sl) * multiplier

                    # Save result to channel file
                    result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": "SL",
                    "current_price": current_price,
                    "loss_pips": loss_pips,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": "-1001286609636"
                    }
                    save_channel_result("-1001286609636", result_data)

                    notifications_sent.append(timestamp)
                    print(f"❌ SL hit for forwarded {pair} {signal_type}: -{abs(loss_pips):.1f} pips (saved to results file)")

                    # Process TP hit
            elif tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forwarded forex
                if pair.endswith("JPY"):
                    multiplier = 1000
                else:
                    multiplier = 10000

                if signal_type == "BUY":
                    profit_pips = (tp - entry) * multiplier
                else:  # SELL
                    profit_pips = (entry - tp) * multiplier

                    # Calculate R/R ratio
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    reward_pips = ((tp - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    reward_pips = ((entry - tp) / entry) * 100

                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0

                # Send TP hit notification to the forwarded channel (-1001286609636)
                message = f"🎯 **TP HIT!**\n\n"
                message += f"**{pair} {signal_type}**\n"
                message += f"Entry: {entry:,.5f}\n"
                message += f"TP: {tp:,.5f}\n"
                message += f"Current: {current_price:,.5f}\n"
                message += f"**Profit: +{profit_pips:.1f} pips**\n\n"
                message += f"⏰ Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"

                # Save result to channel file
                result_data = {
                    "pair": pair,
                    "type": signal_type,
                    "entry": entry,
                    "sl": sl,
                    "hit_type": "TP",
                    "current_price": current_price,
                    "profit_pips": profit_pips,
                    "rr_ratio": rr_ratio,
                    "timestamp": timestamp,
                    "hit_time": datetime.now(timezone.utc).isoformat(),
                    "channel": "-1001286609636"
                }
                save_channel_result("-1001286609636", result_data)
                
                await bot.send_message(chat_id="-1001286609636", text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ TP hit notification sent for forwarded {pair} {signal_type}: +{profit_pips:.1f} pips (saved to results file)")
        
        # Save updated notifications list
        signals["tp_notifications"] = notifications_sent
        save_signals(signals)
        
    except Exception as e:
        print(f"❌ Error checking TP hits: {e}")


def generate_forex_signal():
    """Generate a forex signal with real prices"""
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_forex_pairs = []
    else:
        active_forex_pairs = [s["pair"] for s in signals.get("forex", [])]
    
    # Filter out pairs that already have active signals
    available_pairs = [pair for pair in FOREX_PAIRS if pair not in active_forex_pairs]
    
    if not available_pairs:
        print("⚠️ All forex pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
    signal_type = random.choice(["BUY", "SELL"])
    
    # STRICT: Forex pairs ONLY from cTrader (no fallbacks)
    entry, reason = get_forex_price_ctrader(pair)
    
    if entry is None:
        print(f"❌ [FOREX_GEN] Could not get price for {pair} from cTrader (reason: {reason})")
        print(f"   Reject reason: PRICE_UNAVAILABLE_CTRADER")
        return None
    
    # Calculate SL and TP based on real price with 2 TPs
    if pair == "XAUUSD":
        # Gold: TP close to entry, SL further away
        tp_percent = random.uniform(0.01, 0.02)  # 1-2% TP (same as before)
        sl_percent = random.uniform(0.015, 0.025)  # 1.5-2.5% SL (increased, further away)
        
        if signal_type == "BUY":
            tp = round(entry * (1 + tp_percent), 2)
            sl = round(entry * (1 - sl_percent), 2)
        else:  # SELL
            tp = round(entry * (1 - tp_percent), 2)
            sl = round(entry * (1 + sl_percent), 2)
        
        return {
            "pair": pair,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Main forex pairs: 2 TPs - TP1 close to entry, SL further away
        # Calculate using pip distances for more control
        if pair.endswith("JPY"):
            # JPY pairs: 3 decimal places, use pip multiplier of 1000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            sl_distance = sl_pips / 1000
            tp1_distance = tp1_pips / 1000
            tp2_distance = tp2_pips / 1000
        else:
            # Other forex pairs: 5 decimal places, use pip multiplier of 10000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            sl_distance = sl_pips / 10000
            tp1_distance = tp1_pips / 10000
            tp2_distance = tp2_pips / 10000

        if signal_type == "BUY":
            sl = round(entry - sl_distance, 5)
            tp1 = round(entry + tp1_distance, 5)
            tp2 = round(entry + tp2_distance, 5)
        else:  # SELL
            sl = round(entry + sl_distance, 5)
            tp1 = round(entry - tp1_distance, 5)
            tp2 = round(entry - tp2_distance, 5)
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_forex_additional_signal():
    """Generate a forex signal for additional channel with different parameters"""
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_additional_pairs = []
    else:
        active_additional_pairs = [s["pair"] for s in signals.get("forex_additional", [])]
    
    # Filter out pairs that already have active signals in this channel
    available_pairs = [pair for pair in FOREX_PAIRS if pair not in active_additional_pairs]
    
    if not available_pairs:
        print("⚠️ All forex additional pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
    signal_type = random.choice(["BUY", "SELL"])
    
    # Get real price from forex API
    entry = get_real_forex_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and TP with different ranges (more aggressive targets)
    if pair == "XAUUSD":
        # Gold: TP close to entry, SL further away
        tp_percent = random.uniform(0.015, 0.03)  # 1.5-3% TP (same as before)
        sl_percent = random.uniform(0.02, 0.03)  # 2-3% SL (increased, further away)
        
        if signal_type == "BUY":
            tp = round(entry * (1 + tp_percent), 2)
            sl = round(entry * (1 - sl_percent), 2)
        else:  # SELL
            tp = round(entry * (1 - tp_percent), 2)
            sl = round(entry * (1 + sl_percent), 2)
        
        return {
            "pair": pair,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Main forex pairs: TP1 close to entry, SL further away
        # Calculate using pip distances for more control
        if pair.endswith("JPY"):
            # JPY pairs: 3 decimal places, use pip multiplier of 1000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            sl_distance = sl_pips / 1000
            tp1_distance = tp1_pips / 1000
            tp2_distance = tp2_pips / 1000
        else:
            # Other forex pairs: 5 decimal places, use pip multiplier of 10000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            sl_distance = sl_pips / 10000
            tp1_distance = tp1_pips / 10000
            tp2_distance = tp2_pips / 10000

        if signal_type == "BUY":
            sl = round(entry - sl_distance, 5)
            tp1 = round(entry + tp1_distance, 5)
            tp2 = round(entry + tp2_distance, 5)
        else:  # SELL
            sl = round(entry + sl_distance, 5)
            tp1 = round(entry - tp1_distance, 5)
            tp2 = round(entry - tp2_distance, 5)
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_forex_3tp_signal():
    """Generate a forex signal with 3 TPs (like crypto signals)"""
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_forex_3tp_pairs = []
    else:
        active_forex_3tp_pairs = [s["pair"] for s in signals.get("forex_3tp", [])]
    
    # Filter out pairs that already have active signals
    available_pairs = [pair for pair in FOREX_PAIRS if pair not in active_forex_3tp_pairs]
    
    if not available_pairs:
        print("⚠️ All forex 3TP pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
    signal_type = random.choice(["BUY", "SELL"])
    
    # Get real price from forex API
    entry = get_real_forex_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and 3 TPs based on real price with new ranges
    if pair == "XAUUSD":
        # Gold: TP1 close to entry, SL further away
        sl_percent = random.uniform(0.015, 0.025)  # 1.5-2.5% SL (increased, further away)
        tp1_percent = random.uniform(0.01, 0.02)  # 1-2% TP1 (same as before)
        tp2_percent = random.uniform(0.015, 0.025)  # 1.5-2.5% TP2
        tp3_percent = random.uniform(0.02, 0.03)  # 2-3% TP3
        
        if signal_type == "BUY":
            sl = round(entry * (1 - sl_percent), 2)
            tp1 = round(entry * (1 + tp1_percent), 2)
            tp2 = round(entry * (1 + tp2_percent), 2)
            tp3 = round(entry * (1 + tp3_percent), 2)
        else:  # SELL
            sl = round(entry * (1 + sl_percent), 2)
            tp1 = round(entry * (1 - tp1_percent), 2)
            tp2 = round(entry * (1 - tp2_percent), 2)
            tp3 = round(entry * (1 - tp3_percent), 2)
    else:
        # Main forex pairs: 3 TPs - TP1 close to entry, SL further away
        # Calculate using pip distances for more control
        if pair.endswith("JPY"):
            # JPY pairs: 3 decimal places, use pip multiplier of 1000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            tp3_pips = random.uniform(80, 110)  # TP3: 80-110 pips
            sl_distance = sl_pips / 1000
            tp1_distance = tp1_pips / 1000
            tp2_distance = tp2_pips / 1000
            tp3_distance = tp3_pips / 1000
        else:
            # Other forex pairs: 5 decimal places, use pip multiplier of 10000
            sl_pips = random.uniform(50, 60)  # SL: 50-60 pips
            tp1_pips = random.uniform(25, 35)  # TP1: 25-35 pips
            tp2_pips = random.uniform(50, 60)  # TP2: 50-60 pips
            tp3_pips = random.uniform(80, 110)  # TP3: 80-110 pips
            sl_distance = sl_pips / 10000
            tp1_distance = tp1_pips / 10000
            tp2_distance = tp2_pips / 10000
            tp3_distance = tp3_pips / 10000

        if signal_type == "BUY":
            sl = round(entry - sl_distance, 5)
            tp1 = round(entry + tp1_distance, 5)
            tp2 = round(entry + tp2_distance, 5)
            tp3 = round(entry + tp3_distance, 5)
        else:  # SELL
            sl = round(entry + sl_distance, 5)
            tp1 = round(entry - tp1_distance, 5)
            tp2 = round(entry - tp2_distance, 5)
            tp3 = round(entry - tp3_distance, 5)
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def get_all_active_pairs_across_channels():
    """Get all active pairs across all channels to prevent duplicates"""
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if signals.get("date") != today:
        return set()

    active_pairs = set()

    # Add pairs from forex channels
    for signal in signals.get("forex", []):
        active_pairs.add(signal.get("pair"))
    for signal in signals.get("forex_3tp", []):
        active_pairs.add(signal.get("pair"))
    for signal in signals.get("forex_additional", []):
        active_pairs.add(signal.get("pair"))

    # Add pairs from crypto channels
    # Check both crypto channels
    for signal in signals.get("crypto_lingrid", []):
        active_pairs.add(signal.get("pair"))
    for signal in signals.get("crypto_gainmuse", []):
        active_pairs.add(signal.get("pair"))

    # Add pairs from indexes channel
    for signal in signals.get("indexes", []):
        active_pairs.add(signal.get("pair"))

    return active_pairs


def generate_crypto_signal(channel="lingrid"):
    """Generate a crypto signal with real prices from Binance
    Args:
        channel: "lingrid" or "gainmuse" - determines which channel's signals to check
    """
    # Check for active signals to avoid duplicates across both channels
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_crypto_pairs = []
        crypto_signals = []
    else:
        # Check both channels for active pairs
        active_crypto_pairs = []
        active_crypto_pairs.extend([s["pair"] for s in signals.get("crypto_lingrid", [])])
        active_crypto_pairs.extend([s["pair"] for s in signals.get("crypto_gainmuse", [])])
        # Get signals for the specific channel to maintain ratio
        if channel == "lingrid":
            crypto_signals = signals.get("crypto_lingrid", [])
        else:
            crypto_signals = signals.get("crypto_gainmuse", [])

            # Filter out pairs that already have active signals in ANY channel
    available_pairs = [pair for pair in CRYPTO_PAIRS if pair not in active_crypto_pairs]
    
    if not available_pairs:
        print(f"⚠️ All crypto pairs already have active signals today in {channel} channel")
        return None
    
    pair = random.choice(available_pairs)
    
    # Random BUY or SELL (no distribution ratio enforced)
    signal_type = random.choice(["BUY", "SELL"])
    
    # Get REAL price from Binance API
    entry = get_real_crypto_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and TP based on real price with new ranges (2-10% TP, 4% SL)
    # Random TP percentages between 2-10%
    tp1_percent = random.uniform(0.02, 0.04)  # 2-4% TP1
    tp2_percent = random.uniform(0.05, 0.07)  # 5-7% TP2
    tp3_percent = random.uniform(0.08, 0.10)  # 8-10% TP3
    
    if signal_type == "BUY":
        sl = round(entry * 0.96, 6)  # 4% stop loss
        tp1 = round(entry * (1 + tp1_percent), 6)  # 2-4% first take profit
        tp2 = round(entry * (1 + tp2_percent), 6)  # 5-7% second take profit
        tp3 = round(entry * (1 + tp3_percent), 6)  # 8-10% third take profit
    else:  # SELL
        sl = round(entry * 1.04, 6)  # 4% stop loss
        tp1 = round(entry * (1 - tp1_percent), 6)  # 2-4% first take profit
        tp2 = round(entry * (1 - tp2_percent), 6)  # 5-7% second take profit
        tp3 = round(entry * (1 - tp3_percent), 6)  # 8-10% third take profit
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def generate_index_signal():
    """Generate an index signal (USOIL, BRENT, or XAUUSD) - only Buy now signals"""
    # Get all active pairs across all channels to ensure uniqueness
    all_active_pairs = get_all_active_pairs_across_channels()

    # Check for active signals in indexes channel specifically
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if signals.get("date") != today:
        active_index_pairs = []
    else:
        active_index_pairs = [s["pair"] for s in signals.get("indexes", [])]

        # Filter out pairs that are already active in indexes channel
        # Also exclude pairs that are active in other channels (for uniqueness)
    available_pairs = [
        pair for pair in INDEX_PAIRS 
        if pair not in active_index_pairs and pair not in all_active_pairs
    ]

    if not available_pairs:
        print("⚠️ All index pairs already have active signals today or are used in other channels")
        return None

    pair = random.choice(available_pairs)
    signal_type = "Buy"  # Only Buy now signals

    # STRICT: Index prices ONLY from Yahoo Finance (no fallbacks)
    # Note: XAUUSD in indexes channel also uses Yahoo Finance (not cTrader)
    entry, reason = await get_index_price_yahoo(pair)
    
    if entry is None:
        print(f"❌ [INDEX_GEN] Could not get price for {pair} from Yahoo Finance (reason: {reason})")
        return None
    
    # Strict type check: entry must be float or int
    if not isinstance(entry, (int, float)):
        print(f"❌ Invalid price type for {pair}: got {type(entry).__name__}, expected float/int. Value: {repr(entry)}")
        return None
    
    # Ensure entry is float
    try:
        entry = float(entry)
    except (ValueError, TypeError) as e:
        print(f"❌ Cannot convert price to float for {pair}: {e}. Value: {repr(entry)}")
        return None
    
    if entry <= 0:
        print(f"❌ Invalid price value for {pair}: {entry} (must be > 0)")
        return None

    # Calculate SL and TP based on real price
    # For indexes, use reasonable percentages: 1-3% TP, 1-2% SL
    if pair == "XAUUSD":
        # Gold: 1-2% TP, 1-2% SL
        tp_percent = random.uniform(0.01, 0.02)  # 1-2%
        sl_percent = random.uniform(0.01, 0.02)  # 1-2%
        tp = round(entry * (1 + tp_percent), 2)
        sl = round(entry * (1 - sl_percent), 2)

        return {
            "pair": pair,
            "type": signal_type,
            "entry": None,  # "Buy now" - no entry price
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Oil pairs: 1-3% TP, 1-2% SL
        tp_percent = random.uniform(0.01, 0.03)  # 1-3%
        sl_percent = random.uniform(0.01, 0.02)  # 1-2%
        tp = round(entry * (1 + tp_percent), 2)
        sl = round(entry * (1 - sl_percent), 2)

        return {
            "pair": pair,
            "type": signal_type,
            "entry": None,  # "Buy now" - no entry price
            "sl": sl,
            "tp": tp,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def format_forex_signal(signal):
    """Format forex signal message with 2 TPs"""
    pair = signal['pair']
    signal_type = signal['type']
    
    # Format numbers based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places (single TP)
        entry = f"{signal['entry']:,.2f}"
        sl = f"{signal['sl']:,.2f}"
        tp = f"{signal['tp']:,.2f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp}"""
    elif pair.endswith("JPY"):
        # JPY pairs: 3 decimal places (2 TPs)
        entry = f"{signal['entry']:,.3f}"
        sl = f"{signal['sl']:,.3f}"
        tp1 = f"{signal['tp1']:,.3f}"
        tp2 = f"{signal['tp2']:,.3f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP1 {tp1}
TP2 {tp2}"""
    else:
        # Other forex pairs: 5 decimal places (2 TPs)
        entry = f"{signal['entry']:,.5f}"
        sl = f"{signal['sl']:,.5f}"
        tp1 = f"{signal['tp1']:,.5f}"
        tp2 = f"{signal['tp2']:,.5f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP1 {tp1}
TP2 {tp2}"""


def format_forex_3tp_signal(signal):
    """Format forex signal message with 3 TPs"""
    pair = signal['pair']
    signal_type = signal['type']
    
    # Format numbers based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places
        entry = f"{signal['entry']:,.2f}"
        sl = f"{signal['sl']:,.2f}"
        tp1 = f"{signal['tp1']:,.2f}"
        tp2 = f"{signal['tp2']:,.2f}"
        tp3 = f"{signal['tp3']:,.2f}"
    elif pair.endswith("JPY"):
        # JPY pairs: 3 decimal places
        entry = f"{signal['entry']:,.3f}"
        sl = f"{signal['sl']:,.3f}"
        tp1 = f"{signal['tp1']:,.3f}"
        tp2 = f"{signal['tp2']:,.3f}"
        tp3 = f"{signal['tp3']:,.3f}"
    else:
        # Other forex pairs: 5 decimal places
        entry = f"{signal['entry']:,.5f}"
        sl = f"{signal['sl']:,.5f}"
        tp1 = f"{signal['tp1']:,.5f}"
        tp2 = f"{signal['tp2']:,.5f}"
        tp3 = f"{signal['tp3']:,.5f}"
    
    return f"""{pair} {signal_type}
Entry: {entry}
SL: {sl}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}"""


def format_crypto_signal(signal):
    """Format crypto signal message"""
    # Format crypto numbers with 6 decimal places and comma separators
    entry = f"{signal['entry']:,.6f}"
    sl = f"{signal['sl']:,.6f}"
    tp1 = f"{signal['tp1']:,.6f}"
    tp2 = f"{signal['tp2']:,.6f}"
    tp3 = f"{signal['tp3']:,.6f}"
    
    return f"""{signal['pair']} {signal['type']}
Entry: {entry}
SL: {sl}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}"""


def format_index_signal(signal):
    """Format index signal message (oil and gold) - only Buy now signals"""
    pair = signal['pair']
    signal_type = signal['type']

    # All index signals are "Buy now" - no entry price needed
    entry = "Buy now"

    # Format based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places
        sl = f"{signal['sl']:,.2f}"
        if 'tp' in signal and signal.get('tp'):
            tp = f"{signal['tp']:,.2f}"
            return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp}"""
        else:
            tp1 = f"{signal.get('tp1', signal.get('tp', 0)):,.2f}"
            return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp1}"""
    else:
        # Oil pairs: 2 decimal places
        sl = f"{signal['sl']:,.2f}"
        if 'tp' in signal and signal.get('tp'):
            tp = f"{signal['tp']:,.2f}"
            return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp}"""
        else:
            tp1 = f"{signal.get('tp1', signal.get('tp', 0)):,.2f}"
            return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp1}"""


def is_trading_hours():
    """Check if current time is within trading hours (4 GMT - 23 GMT)"""
    current_time = datetime.now(timezone.utc)
    current_hour = current_time.hour
    return 4 <= current_hour < 23


def is_weekend():
    """Check if current day is weekend (Saturday = 5, Sunday = 6)"""
    current_time = datetime.now(timezone.utc)
    weekday = current_time.weekday()  # Monday = 0, Sunday = 6
    return weekday >= 5  # Saturday (5) or Sunday (6)


def get_next_interval():
    """Get next interval in seconds (3-5 hours)"""
    return random.randint(MIN_INTERVAL * 3600, MAX_INTERVAL * 3600)


async def send_forex_signal():
    """Send a forex signal"""
    try:
        # Check if weekend - don't send forex signals on weekends
        if is_weekend():
            print("📅 Weekend detected - skipping forex signal")
            return False

            # Check if enough time has passed since last signal (5 min between channels, 2h for same channel)
        if not can_send_signal_now(CHANNEL_LINGRID_FOREX):
            return False

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        if len(signals.get("forex", [])) >= MAX_FOREX_SIGNALS:
            print(f"⚠️ Forex signal limit reached: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
            return False
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(FOREX_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_forex_signal()
            if signal is None:
                print("❌ Could not generate forex signal")
                return False
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(CHANNEL_LINGRID_FOREX, signal['pair']):
                break
            else:
                # Remove this pair from available pairs temporarily to try another one
                attempts += 1
                if attempts >= max_attempts:
                    print(f"⚠️ All forex pairs have been sent in last 36 hours for channel {CHANNEL_LINGRID_FOREX}")
                    return False
                signal = None
                # Note: generate_forex_signal will pick a different pair on next call
                continue
        
        if signal is None:
            print("❌ Could not find available forex pair (all pairs sent in last 36h)")
            return False
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)

        # Save signal to channel file (FOREX_CHANNEL = Lingrid Forex)
        save_channel_signal(CHANNEL_LINGRID_FOREX, signal)

        # Update last signal time (global, channel-specific, and pair-specific)
        save_last_signal_time()
        save_channel_last_signal_time(CHANNEL_LINGRID_FOREX)
        save_channel_pair_last_signal_time(CHANNEL_LINGRID_FOREX, signal['pair'])
        
        print(f"✅ Forex signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending forex signal: {e}")
        return False


async def send_forex_additional_signal():
    """Send a forex signal to additional channel with different parameters"""
    try:
        # Check if weekend - don't send forex signals on weekends
        if is_weekend():
            print("📅 Weekend detected - skipping forex additional signal")
            return False

            # Check if enough time has passed since last signal (5 min between channels, 2h for same channel)
            # Note: FOREX_CHANNEL_ADDITIONAL is not in our main channels, using a placeholder
        if not can_send_signal_now(FOREX_CHANNEL_ADDITIONAL):
            return False

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto": [], "date": today}
        
        if len(signals.get("forex_additional", [])) >= MAX_FOREX_ADDITIONAL_SIGNALS:
            print(f"⚠️ Forex additional signal limit reached: {len(signals['forex_additional'])}/{MAX_FOREX_ADDITIONAL_SIGNALS}")
            return False
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(FOREX_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_forex_additional_signal()
            if signal is None:
                print("❌ Could not generate forex additional signal")
                return False
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(FOREX_CHANNEL_ADDITIONAL, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    print(f"⚠️ All forex pairs have been sent in last 36 hours for channel {FOREX_CHANNEL_ADDITIONAL}")
                    return False
                signal = None
                continue
        
        if signal is None:
            print("❌ Could not find available forex pair (all pairs sent in last 36h)")
            return False
        
        signals["forex_additional"].append(signal)
        save_signals(signals)
        
        # Send to additional channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL_ADDITIONAL, text=message)

        # Update last signal time (global, channel-specific, and pair-specific)
        save_last_signal_time()
        save_channel_last_signal_time(FOREX_CHANNEL_ADDITIONAL)
        save_channel_pair_last_signal_time(FOREX_CHANNEL_ADDITIONAL, signal['pair'])
        
        print(f"✅ Forex additional signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex additional signals: {len(signals['forex_additional'])}/{MAX_FOREX_ADDITIONAL_SIGNALS}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending forex additional signal: {e}")
        return False


async def send_forex_3tp_signal():
    """Send a forex signal with 3 TPs"""
    try:
        # Check if weekend - don't send forex signals on weekends
        if is_weekend():
            print("📅 Weekend detected - skipping forex 3TP signal")
            return False

            # Check if enough time has passed since last signal (5 min between channels, 2h for same channel)
        if not can_send_signal_now(CHANNEL_DEGRAM):
            return False

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto": [], "date": today}
        
        if len(signals.get("forex_3tp", [])) >= MAX_FOREX_3TP_SIGNALS:
            print(f"⚠️ Forex 3TP signal limit reached: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}")
            return False
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(FOREX_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_forex_3tp_signal()
            if signal is None:
                print("❌ Could not generate forex 3TP signal")
                return False
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(CHANNEL_DEGRAM, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    print(f"⚠️ All forex pairs have been sent in last 36 hours for channel {CHANNEL_DEGRAM}")
                    return False
                signal = None
                continue
        
        if signal is None:
            print("❌ Could not find available forex pair (all pairs sent in last 36h)")
            return False
        
        signals["forex_3tp"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_3tp_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message)

        # Save signal to channel file (FOREX_CHANNEL_3TP = DeGRAM)
        save_channel_signal(CHANNEL_DEGRAM, signal)

        # Update last signal time (global, channel-specific, and pair-specific)
        save_last_signal_time()
        save_channel_last_signal_time(CHANNEL_DEGRAM)
        save_channel_pair_last_signal_time(CHANNEL_DEGRAM, signal['pair'])
        
        print(f"✅ Forex 3TP signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex 3TP signals: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending forex 3TP signal: {e}")
        return False


async def send_crypto_signal(channel="lingrid"):
    """Send a crypto signal to a specific channel
    Args:
        channel: "lingrid" or "gainmuse" - determines which channel to send to
    """
    try:
        # Determine which channel to send to
        if channel == "lingrid":
            channel_id = CHANNEL_LINGRID_CRYPTO
            channel_name = "Lingrid Crypto"
        else:
            channel_id = CHANNEL_GAINMUSE
            channel_name = "GainMuse Crypto"

            # Check if enough time has passed since last signal (5 min between channels, 2h for same channel)
        if not can_send_signal_now(channel_id):
            return False

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto_lingrid": [], "crypto_gainmuse": [], "indexes": [], "date": today}

            # Check limit for specific channel
        if channel == "lingrid":
            channel_signals = signals.get("crypto_lingrid", [])
            max_signals = MAX_CRYPTO_SIGNALS_LINGRID
        else:
            channel_signals = signals.get("crypto_gainmuse", [])
            max_signals = MAX_CRYPTO_SIGNALS_GAINMUSE

        if len(channel_signals) >= max_signals:
            print(f"⚠️ {channel_name} signal limit reached: {len(channel_signals)}/{max_signals}")
            return False
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(CRYPTO_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_crypto_signal(channel)
            if signal is None:
                print(f"❌ Could not generate crypto signal for {channel_name}")
                return False
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(channel_id, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    print(f"⚠️ All crypto pairs have been sent in last 36 hours for channel {channel_id}")
                    return False
                signal = None
                continue
        
        if signal is None:
            print(f"❌ Could not find available crypto pair (all pairs sent in last 36h) for {channel_name}")
            return False
        
            # Add to appropriate channel array
        if channel == "lingrid":
            signals["crypto_lingrid"].append(signal)
        else:
            signals["crypto_gainmuse"].append(signal)
        save_signals(signals)
        
        # Send to specific channel
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=channel_id, text=message)

        # Save signal to channel file
        save_channel_signal(channel_id, signal)

        # Update last signal time (global, channel-specific, and pair-specific)
        save_last_signal_time()
        save_channel_last_signal_time(channel_id)
        save_channel_pair_last_signal_time(channel_id, signal['pair'])

        # Calculate distribution for this channel
        buy_count = len([s for s in channel_signals if s.get("type") == "BUY"])
        total_crypto = len(channel_signals)
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        
        print(f"✅ {channel_name} signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's {channel_name} signals: {len(channel_signals) + 1}/{max_signals}")
        print(f"📈 Distribution: BUY {buy_count + (1 if signal['type'] == 'BUY' else 0)} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count + (1 if signal['type'] == 'SELL' else 0)} ({100 - buy_ratio:.1f}%)")
        return True
        
    except Exception as e:
        print(f"❌ Error sending crypto signal: {e}")
        return False


# Twisted removed - using async client instead

async def init_ctrader_async_client():
    """Initialize cTrader async client (no Twisted)"""
    global _ctrader_async_client, _gold_ctrader_connected
    
    if _ctrader_async_client and _ctrader_async_client.connected:
        return True
    
    try:
        from ctrader_async_client import CTraderAsyncClient, CTraderAsyncError
        
        print("[CTRADER_ASYNC] Initializing cTrader async client...")
        
        # Get cTrader config from Config (source of truth)
        ctrader_config = Config.get_ctrader_config()
        
        # Get WebSocket URL
        ws_url, ws_source = ctrader_config.get_ws_url()
        
        # Extract config values
        account_id = ctrader_config.account_id
        client_id = ctrader_config.client_id
        client_secret = ctrader_config.client_secret
        access_token = ctrader_config.access_token
        refresh_token = ctrader_config.refresh_token
        is_demo = ctrader_config.is_demo
        
        # Log config before creating client
        print(f"[CTRADER_ASYNC] Using config: ws_url={ws_url}, is_demo={is_demo}, account_id={account_id}")
        
        # Create client with config from Config
        _ctrader_async_client = CTraderAsyncClient(
            ws_url=ws_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            account_id=account_id,
            is_demo=is_demo
        )
        
        # Connect
        await _ctrader_async_client.connect()
        
        # Authenticate
        await _ctrader_async_client.auth_application()
        await _ctrader_async_client.auth_account()
        
        # Resolve and subscribe to FOREX pairs only (not XAUUSD - gold uses Yahoo Finance)
        forex_pairs = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
        for pair in forex_pairs:
            symbol_id = await _ctrader_async_client.ensure_symbol_id(pair)
            if symbol_id:
                await _ctrader_async_client.subscribe_spot(symbol_id)
                print(f"[CTRADER_ASYNC] ✅ {pair} subscribed")
            else:
                print(f"[CTRADER_ASYNC] ⚠️ {pair} symbol not found")
        
        return True
        
    except CTraderAsyncError as e:
        print(f"[CTRADER_ASYNC] ❌ Error: {e.reason}: {e.message}")
        _gold_ctrader_connected = False
        return False
    except Exception as e:
        print(f"[CTRADER_ASYNC] ❌ Error initializing: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        _gold_ctrader_connected = False
        return False


def get_gold_price_from_ctrader() -> Optional[float]:
    """Get current gold price from cTrader async client (no Twisted)
    
    Returns:
        Mid price (bid+ask)/2 or None if unavailable
    """
    global _gold_ctrader_connected, _ctrader_async_client
    
    if not _ctrader_async_client:
        return None
    
    try:
        price = _ctrader_async_client.get_last_price("XAUUSD")
        if price and price > 0:
            _gold_ctrader_connected = True
        else:
            _gold_ctrader_connected = False
        return price
    except Exception as e:
        print(f"❌ [GOLD_PRICE] Error getting price from cTrader: {e}")
        _gold_ctrader_connected = False
        return None


def get_active_gold_signal_direction(channel_id):
    """Get the direction (BUY/SELL) of active gold signal in the channel that hasn't reached SL or final TP
    Returns None if no active signal or signal has reached SL/final TP
    """
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            return None
        
        # Get gold signals for this channel
        gold_signals = signals.get("gold_private", [])
        
        # STRICT: Get current gold price ONLY from Yahoo Finance
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, use a thread executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(get_gold_price_yahoo()))
                    current_price, _ = future.result(timeout=10)
            else:
                current_price, _ = loop.run_until_complete(get_gold_price_yahoo())
        except Exception as e:
            print(f"❌ Error getting gold price for active signal check: {e}")
            return None
        
        if current_price is None:
            return None
        
        # Check all gold signals for this channel
        for signal in gold_signals:
            if signal.get("pair") != "XAUUSD":
                continue
            
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            sl = signal.get("sl", 0)
            tp = signal.get("tp", 0)
            tp1 = signal.get("tp1", 0)
            tp2 = signal.get("tp2", 0)
            tp3 = signal.get("tp3", 0)
            
            # Check if SL was hit
            sl_hit = False
            if signal_type == "BUY" and current_price <= sl:
                sl_hit = True
            elif signal_type == "SELL" and current_price >= sl:
                sl_hit = True
            
            # Check if final TP was hit
            final_tp_hit = False
            if signal_type == "BUY":
                # Check for final TP (tp3 if exists, else tp2, else tp)
                if tp3 > 0 and current_price >= tp3:
                    final_tp_hit = True
                elif tp2 > 0 and current_price >= tp2:
                    final_tp_hit = True
                elif tp > 0 and current_price >= tp:
                    final_tp_hit = True
            else:  # SELL
                if tp3 > 0 and current_price <= tp3:
                    final_tp_hit = True
                elif tp2 > 0 and current_price <= tp2:
                    final_tp_hit = True
                elif tp > 0 and current_price <= tp:
                    final_tp_hit = True
            
            # If signal hasn't reached SL or final TP, return its direction
            if not sl_hit and not final_tp_hit:
                return signal_type
        
        return None
    except Exception as e:
        print(f"❌ Error checking active gold signal: {e}")
        return None


async def generate_gold_signal():
    """Generate a gold (XAUUSD) signal for GOLD Private channel
    IMPORTANT: If there's an active signal that hasn't reached SL or final TP,
    the new signal must be in the same direction (BUY or SELL)
    
    STRICT: Uses ONLY Yahoo Finance (no cTrader fallback).
    
    Returns:
        Signal dict or None if generation failed
    """
    try:
        # Check for active gold signal in GOLD Private channel
        active_direction = get_active_gold_signal_direction(CHANNEL_GOLD_PRIVATE)
        
        # STRICT: Gold price ONLY from Yahoo Finance (no fallbacks)
        entry, reason = await get_gold_price_yahoo()
        
        if entry is None or entry <= 0:
            print(f"[GOLD_GEN] Could not get gold price from Yahoo Finance (reason: {reason})")
            return None
        
        price_source = "yahoo"
        is_fallback = False  # Yahoo is primary source, not fallback
        
        print(f"✅ [GOLD_GEN] Got gold price: {entry:.2f} (source: {price_source})")
        
        # Determine signal type
        if active_direction:
            # If there's an active signal, use the same direction
            signal_type = active_direction
            print(f"📊 Active gold signal found ({active_direction}), new signal will be in same direction")
        else:
            # No active signal, choose randomly
            signal_type = random.choice(["BUY", "SELL"])
        
        # Calculate entry range: ±1.5 USD from price
        entry_range_min = round(entry - 1.5, 2)
        entry_range_max = round(entry + 1.5, 2)
        
        # Calculate SL and TP for gold
        # For fallback sources, add extra buffer for safety
        sl_buffer = 0.002 if is_fallback else 0.0  # Extra 0.2% buffer for Yahoo
        tp_buffer = 0.001 if is_fallback else 0.0  # Extra 0.1% buffer for Yahoo
        
        sl_percent = random.uniform(0.015, 0.025) + sl_buffer  # 1.5-2.5% SL (+ buffer)
        tp1_percent = random.uniform(0.01, 0.02) + tp_buffer  # 1-2% TP1 (+ buffer)
        tp2_percent = random.uniform(0.015, 0.025) + tp_buffer  # 1.5-2.5% TP2 (+ buffer)
        
        if signal_type == "BUY":
            sl = round(entry * (1 - sl_percent), 2)
            tp1 = round(entry * (1 + tp1_percent), 2)
            tp2 = round(entry * (1 + tp2_percent), 2)
        else:  # SELL
            sl = round(entry * (1 + sl_percent), 2)
            tp1 = round(entry * (1 - tp1_percent), 2)
            tp2 = round(entry * (1 - tp2_percent), 2)
        
        return {
            "pair": "XAUUSD",
            "type": signal_type,
            "entry": entry,
            "entry_range_min": entry_range_min,
            "entry_range_max": entry_range_max,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "price_source": price_source,
            "is_fallback": is_fallback,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"❌ Error generating gold signal: {e}")
        import traceback
        print(traceback.format_exc())
        return None


def format_gold_signal(signal):
    """Format gold signal message with entry range and 2 TPs
    
    Uses HTML parse_mode for reliable formatting
    """
    pair = signal['pair']
    signal_type = signal['type']
    entry = signal['entry']
    entry_range_min = signal.get('entry_range_min', entry - 1.5)
    entry_range_max = signal.get('entry_range_max', entry + 1.5)
    sl = signal['sl']
    tp1 = signal['tp1']
    tp2 = signal['tp2']
    is_fallback = signal.get('is_fallback', False)
    
    direction_emoji = "🥇" if signal_type == "BUY" else "🥇"
    fallback_note = " (fallback quotes)" if is_fallback else ""
    
    # Use HTML formatting to avoid Markdown parsing issues
    message = f"""\
{direction_emoji} <b>{pair} {signal_type}</b>{fallback_note}

📌 <b>Entry:</b> <code>{entry_range_max:.2f} - {entry_range_min:.2f}</code>
🛡️ <b>Stop Loss:</b> <code>{sl:.2f}</code>
🎯 <b>Take Profit 1:</b> <code>{tp1:.2f}</code>
🎯 <b>Take Profit 2:</b> <code>{tp2:.2f}</code>"""
    
    return message


async def send_gold_signal(return_reason=False, skip_throttle=False):
    """Send a gold (XAUUSD) signal to GOLD Private channel
    
    Args:
        return_reason: If True, returns (bool, reason_code, details_dict) instead of just bool
        skip_throttle: If True, skips throttle checks (for startup initial signal)
    
    Returns:
        If return_reason=False: bool
        If return_reason=True: (bool, SignalRejectReason, dict with details)
    """
    details = {
        "channel_id": CHANNEL_GOLD_PRIVATE,
        "pair": "XAUUSD",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skip_throttle": skip_throttle
    }
    
    try:
        # Check throttle: 5 min between channels, 2h for same channel (unless skipped for startup)
        if not skip_throttle:
            can_send, throttle_reason, throttle_details = can_send_signal_now(CHANNEL_GOLD_PRIVATE, return_reason=True)
            details["throttle_check"] = throttle_details
            
            if not can_send:
                details["reject_reason"] = throttle_reason.value
                details["reject_details"] = throttle_details
                
                if return_reason:
                    return False, throttle_reason, details
                
                reason_msg = f"⏰ [GOLD_SEND] Throttle blocked: {throttle_reason.value}"
                if throttle_reason == SignalRejectReason.THROTTLE_MIN_INTERVAL:
                    wait_mins = throttle_details.get("remaining_minutes", 0)
                    reason_msg += f" - Wait {wait_mins:.1f} more minutes"
                elif throttle_reason == SignalRejectReason.THROTTLE_CHANNEL_INTERVAL:
                    wait_hours = throttle_details.get("remaining_hours", 0)
                    reason_msg += f" - Wait {wait_hours:.2f} more hours"
                print(reason_msg)
                return False
        else:
            details["throttle_check"] = {"skipped": True, "reason": "startup_initial_signal"}
            print("🚀 [GOLD_SEND] Throttle checks SKIPPED for startup initial signal")

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto_lingrid": [], "crypto_gainmuse": [], "indexes": [], "gold_private": [], "date": today}
        
        # Check daily limit
        gold_signals_today = signals.get("gold_private", [])
        gold_count = len(gold_signals_today)
        details["gold_count"] = gold_count
        details["max_gold_signals"] = MAX_GOLD_SIGNALS
        
        if gold_count >= MAX_GOLD_SIGNALS:
            details["reject_reason"] = SignalRejectReason.DAILY_LIMIT.value
            print(f"⛔ [GOLD_REJECT] DAILY_LIMIT: Gold signal limit reached: {gold_count}/{MAX_GOLD_SIGNALS}")
            print(f"   Counter NOT incremented (already at limit)")
            if return_reason:
                return False, SignalRejectReason.DAILY_LIMIT, details
            return False
        
        # Generate signal (will respect active signal direction if exists)
        signal = await generate_gold_signal()
        details["signal_generated"] = signal is not None
        
        if signal is None:
            # STRICT: Gold uses ONLY Yahoo Finance - no cTrader fallback
            details["reject_reason"] = SignalRejectReason.GENERATION_FAILED.value
            details["reject_details"] = {"reason": "Yahoo Finance price unavailable"}
            print(f"⛔ [GOLD_REJECT] GENERATION_FAILED: Could not get gold price from Yahoo Finance")
            print(f"   Counter NOT incremented (current: {gold_count}/{MAX_GOLD_SIGNALS})")
            if return_reason:
                return False, SignalRejectReason.GENERATION_FAILED, details
            return False
        
        details["signal_type"] = signal.get("type")
        details["signal_entry"] = signal.get("entry")
        
        # Check 36-hour rule for this pair in this channel
        can_send_pair, pair_reason, pair_details = can_send_pair_signal_to_channel(
            CHANNEL_GOLD_PRIVATE, signal['pair'], return_reason=True
        )
        details["pair_36h_check"] = pair_details
        
        if not can_send_pair:
            details["reject_reason"] = pair_reason.value
            details["reject_details"] = pair_details
            
            wait_hours = pair_details.get("remaining_hours", 0)
            print(f"⛔ [GOLD_REJECT] RULE_36H: Cannot send gold signal - 36-hour interval not met. Wait {wait_hours:.2f} more hours.")
            print(f"   Counter NOT incremented (current: {gold_count}/{MAX_GOLD_SIGNALS})")
            
            if return_reason:
                return False, pair_reason, details
            return False
        
        # All checks passed - send signal
        # IMPORTANT: Do NOT increment counter before sending - only after successful send
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_gold_signal(signal)
        
        try:
            sent_message = await bot.send_message(chat_id=CHANNEL_GOLD_PRIVATE, text=message, parse_mode='HTML')
            message_id = sent_message.message_id if sent_message else None
            
            # ONLY increment counter AFTER successful send
            signals["gold_private"].append(signal)
            save_signals(signals)
            
            # Save signal to channel file
            save_channel_signal(CHANNEL_GOLD_PRIVATE, signal)

            # Update last signal time (global, channel-specific, and pair-specific)
            save_last_signal_time()
            save_channel_last_signal_time(CHANNEL_GOLD_PRIVATE)
            save_channel_pair_last_signal_time(CHANNEL_GOLD_PRIVATE, signal['pair'])

            details["sent"] = True
            details["sent_at"] = datetime.now(timezone.utc).isoformat()
            details["message_id"] = message_id
            
            new_gold_count = len(signals.get("gold_private", []))
            
            print(f"✅ [GOLD_SENT] Gold signal sent successfully: {signal['pair']} {signal['type']} at {signal['entry']}")
            print(f"   Channel: {CHANNEL_GOLD_PRIVATE}, Message ID: {message_id}")
            print(f"📌 [GOLD_COUNTER_INCREMENTED] {gold_count} -> {new_gold_count}/{MAX_GOLD_SIGNALS}")
            
        except Exception as send_error:
            # Send failed - do NOT increment counter
            details["send_exception"] = str(send_error)
            details["reject_reason"] = SignalRejectReason.EXCEPTION.value
            details["reject_details"] = {"send_error": str(send_error), "error_type": type(send_error).__name__}
            
            print(f"⛔ [GOLD_REJECT] EXCEPTION: Failed to send message to Telegram")
            print(f"   Error: {type(send_error).__name__}: {send_error}")
            print(f"   Counter NOT incremented (current: {gold_count}/{MAX_GOLD_SIGNALS})")
            
            if return_reason:
                return False, SignalRejectReason.EXCEPTION, details
            return False
        
        if return_reason:
            return True, SignalRejectReason.SUCCESS, details
        return True

    except Exception as e:
        details["exception"] = str(e)
        details["traceback"] = traceback.format_exc()
        details["reject_reason"] = SignalRejectReason.EXCEPTION.value
        
        # Get current gold count for logging
        try:
            signals_check = load_signals()
            gold_count_check = len(signals_check.get("gold_private", []))
        except:
            gold_count_check = "unknown"
        
        print(f"⛔ [GOLD_REJECT] EXCEPTION: Error in send_gold_signal: {e}")
        print(f"   Counter NOT incremented (current: {gold_count_check}/{MAX_GOLD_SIGNALS})")
        print(traceback.format_exc())
        
        if return_reason:
            return False, SignalRejectReason.EXCEPTION, details
        return False


async def send_index_signal(signal_data=None):
    """Send an index/gold signal to the indexes channel"""
    try:
        # Check if weekend - don't send index signals on weekends
        if is_weekend():
            print("📅 Weekend detected - skipping index signal")
            return False

            # Check if enough time has passed since last signal (only for automatic signals)
            # 5 min between channels, 2h for same channel
        if signal_data is None and not can_send_signal_now(CHANNEL_LINGRID_INDEXES):
            return False

        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto": [], "indexes": [], "gold_private": [], "date": today}

        # Check limit before generating/sending signal
        if len(signals.get("indexes", [])) >= MAX_INDEX_SIGNALS:
            print(f"⚠️ Index signal limit reached: {len(signals.get('indexes', []))}/{MAX_INDEX_SIGNALS}")
            return False

            # Generate signal if not provided (will try different pairs until one passes 36h check)
        if signal_data is None:
            max_attempts = len(INDEX_PAIRS) * 2
            attempts = 0
            signal_data = None
            
            while attempts < max_attempts:
                signal_data = await generate_index_signal()
                if signal_data is None:
                    print("❌ Could not generate index signal")
                    return False
                
                # Check 36-hour rule for this pair in this channel
                pair = signal_data.get('pair', '')
                if pair and can_send_pair_signal_to_channel(CHANNEL_LINGRID_INDEXES, pair):
                    break
                else:
                    attempts += 1
                    if attempts >= max_attempts:
                        print(f"⚠️ All index pairs have been sent in last 36 hours for channel {CHANNEL_LINGRID_INDEXES}")
                        return False
                    signal_data = None
                    continue
            
            if signal_data is None:
                print("❌ Could not find available index pair (all pairs sent in last 36h)")
                return False

                # Ensure signal has timestamp
        if "timestamp" not in signal_data:
            signal_data["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Check 36-hour rule if signal_data was provided manually (but allow manual override)
        pair = signal_data.get('pair', '')
        if pair and signal_data is not None and not can_send_pair_signal_to_channel(CHANNEL_LINGRID_INDEXES, pair):
            # For manual signals, we still check but allow override if it's a manual call
            # However, we should respect the 36h rule even for manual signals
            print(f"⚠️ Cannot send {pair} signal: 36-hour interval not met for this pair in channel {CHANNEL_LINGRID_INDEXES}")
            print(f"   Counter NOT incremented")
            return False

        # IMPORTANT: Do NOT increment counter before sending - only after successful send
        index_count_before = len(signals.get("indexes", []))

        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_index_signal(signal_data)
        
        try:
            sent_message = await bot.send_message(chat_id=CHANNEL_LINGRID_INDEXES, text=message)
            message_id = sent_message.message_id if sent_message else None
            
            # ONLY increment counter AFTER successful send
            signals["indexes"].append(signal_data)
            save_signals(signals)

            # Save signal to channel file
            save_channel_signal(CHANNEL_LINGRID_INDEXES, signal_data)

            # Update last signal time (global, channel-specific, and pair-specific)
            save_last_signal_time()
            save_channel_last_signal_time(CHANNEL_LINGRID_INDEXES)
            if pair:
                save_channel_pair_last_signal_time(CHANNEL_LINGRID_INDEXES, pair)

            signal_type = signal_data.get('type', '')
            index_count_after = len(signals.get("indexes", []))

            print(f"✅ [INDEX_SENT] Index signal sent successfully: {pair} {signal_type} Buy now")
            print(f"   Channel: {CHANNEL_LINGRID_INDEXES}, Message ID: {message_id}")
            print(f"📌 [INDEX_COUNTER_INCREMENTED] {index_count_before} -> {index_count_after}/{MAX_INDEX_SIGNALS}")
            return True
            
        except Exception as send_error:
            # Send failed - do NOT increment counter
            print(f"⛔ [INDEX_REJECT] EXCEPTION: Failed to send message to Telegram")
            print(f"   Error: {type(send_error).__name__}: {send_error}")
            print(f"   Counter NOT incremented (current: {index_count_before}/{MAX_INDEX_SIGNALS})")
            return False

    except Exception as e:
        print(f"❌ Error sending index signal: {e}")
        import traceback
        print(traceback.format_exc())
        return False


async def send_manual_index_signals():
    """Send the manual index/gold signals provided by the user - Only Buy now signals"""
    try:
        # Signal 1: USOIL Buy now, TP 62.80, SL 58.50
        signal1 = {
            "pair": "USOIL",
            "type": "Buy",
            "entry": None,  # "Buy now" - no entry price
            "sl": 58.50,
            "tp": 62.80
        }
        await send_index_signal(signal1)
        await asyncio.sleep(1)  # Small delay between signals

        # Signal 2: BRENT Buy now, SL 62.50, TP 66.79
        signal2 = {
            "pair": "BRENT",
            "type": "Buy",
            "entry": None,  # "Buy now" - no entry price
            "sl": 62.50,
            "tp": 66.79
        }
        await send_index_signal(signal2)
        await asyncio.sleep(1)

        # Signal 3: USOIL Buy now (converted from Buy Stop), TP 62.80, SL 58.00
        # Note: Converted to "Buy now" as per requirements
        signal3 = {
            "pair": "USOIL",
            "type": "Buy",
            "entry": None,  # "Buy now" - no entry price (converted from Buy Stop)
            "sl": 58.00,
            "tp": 62.80
        }
        await send_index_signal(signal3)
        await asyncio.sleep(1)

        # Note: Gold signals can be added here when provided
        # Example structure:
        # signal4 = {
        #     "pair": "XAUUSD",
        #     "type": "Buy",
        #     "entry": None,  # "Buy now"
        #     "sl": 2650.00,
        #     "tp": 2680.00
        # }
        # await send_index_signal(signal4)

        print("✅ All manual index signals sent successfully!")
        return True

    except Exception as e:
        print(f"❌ Error sending manual index signals: {e}")
        return False


async def send_daily_summary():
    """Send comprehensive daily summary with performance data"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_signals = []
            forex_3tp_signals = []
            crypto_signals = []
        else:
            forex_signals = signals.get("forex", [])
            forex_3tp_signals = signals.get("forex_3tp", [])
            crypto_signals = signals.get("crypto", [])
        
        # Calculate performance for each channel
        forex_performance = get_performance_summary(forex_signals, 1)
        forex_3tp_performance = get_performance_summary(forex_3tp_signals, 1)
        crypto_performance = get_performance_summary(crypto_signals, 1)
        
        # Create comprehensive summary message
        summary = f"""📊 **Daily Trading Signals Summary (24h)**
📅 Date: {today}

📈 **Forex Signals**
• Total: {len(forex_signals)}/{MAX_FOREX_SIGNALS}
• Performance: {forex_performance['total_profit']:+.2f}% total
• Win Rate: {forex_performance['win_rate']:.1f}%
• Profit Factor: {forex_performance['profit_factor']:.2f if forex_performance['profit_factor'] != float('inf') else '∞'}

📈 **Forex 3TP Signals**
• Total: {len(forex_3tp_signals)}/{MAX_FOREX_3TP_SIGNALS}
• Performance: {forex_3tp_performance['total_profit']:+.2f}% total
• Win Rate: {forex_3tp_performance['win_rate']:.1f}%
• Profit Factor: {forex_3tp_performance['profit_factor']:.2f if forex_3tp_performance['profit_factor'] != float('inf') else '∞'}

🪙 **Crypto Signals**
• Total: {len(crypto_signals)}/{MAX_CRYPTO_SIGNALS}
• Performance: {crypto_performance['total_profit']:+.2f}% total
• Win Rate: {crypto_performance['win_rate']:.1f}%
• Profit Factor: {crypto_performance['profit_factor']:.2f if crypto_performance['profit_factor'] != float('inf') else '∞'}

💰 **OVERALL PERFORMANCE**
• Total Signals: {forex_performance['total_signals'] + forex_3tp_performance['total_signals'] + crypto_performance['total_signals']}
• Combined Profit: {forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']:+.2f}%
• Average Win Rate: {(forex_performance['win_rate'] + forex_3tp_performance['win_rate'] + crypto_performance['win_rate']) / 3:.1f}%

⏰ Generated at: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"""
        
        # Send to user
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=SUMMARY_USER_ID, text=summary, parse_mode='Markdown')
        
        print(f"✅ Daily summary sent to user {SUMMARY_USER_ID}")
        
    except Exception as e:
        print(f"❌ Error sending daily summary: {e}")


async def send_weekly_summary():
    """Send comprehensive weekly summary with performance data"""
    try:
        # Get signals from last 7 days
        today = datetime.now(timezone.utc)
        week_ago = today - timedelta(days=7)
        
        # Load current signals
        signals = load_signals()
        
        # Get all signals from the last 7 days (we'll need to load from performance data)
        # For now, let's use the current signals and calculate performance
        forex_signals = signals.get("forex", [])
        forex_3tp_signals = signals.get("forex_3tp", [])
        crypto_signals = signals.get("crypto", [])
        
        # Calculate performance for each channel over 7 days
        forex_performance = get_performance_summary(forex_signals, 7)
        forex_3tp_performance = get_performance_summary(forex_3tp_signals, 7)
        crypto_performance = get_performance_summary(crypto_signals, 7)
        
        # Create comprehensive weekly summary message
        summary = f"""📊 **Weekly Trading Signals Summary (7 days)**
📅 Period: {week_ago.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}

📈 **Forex Signals**
• Total: {forex_performance['total_signals']}
• Performance: {forex_performance['total_profit']:+.2f}% total
• Win Rate: {forex_performance['win_rate']:.1f}%
• Profit Factor: {forex_performance['profit_factor']:.2f if forex_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {forex_performance['avg_profit']:+.2f}%
• Average Loss: {forex_performance['avg_loss']:+.2f}%

📈 **Forex 3TP Signals**
• Total: {forex_3tp_performance['total_signals']}
• Performance: {forex_3tp_performance['total_profit']:+.2f}% total
• Win Rate: {forex_3tp_performance['win_rate']:.1f}%
• Profit Factor: {forex_3tp_performance['profit_factor']:.2f if forex_3tp_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {forex_3tp_performance['avg_profit']:+.2f}%
• Average Loss: {forex_3tp_performance['avg_loss']:+.2f}%

🪙 **Crypto Signals**
• Total: {crypto_performance['total_signals']}
• Performance: {crypto_performance['total_profit']:+.2f}% total
• Win Rate: {crypto_performance['win_rate']:.1f}%
• Profit Factor: {crypto_performance['profit_factor']:.2f if crypto_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {crypto_performance['avg_profit']:+.2f}%
• Average Loss: {crypto_performance['avg_loss']:+.2f}%

💰 **OVERALL WEEKLY PERFORMANCE**
• Total Signals: {forex_performance['total_signals'] + forex_3tp_performance['total_signals'] + crypto_performance['total_signals']}
• Combined Profit: {forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']:+.2f}%
• Average Win Rate: {(forex_performance['win_rate'] + forex_3tp_performance['win_rate'] + crypto_performance['win_rate']) / 3:.1f}%
• Daily Average: {(forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']) / 7:+.2f}%

⏰ Generated at: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"""
        
        # Send to user
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=SUMMARY_USER_ID, text=summary, parse_mode='Markdown')
        
        print(f"✅ Weekly summary sent to user {SUMMARY_USER_ID}")
        
    except Exception as e:
        print(f"❌ Error sending weekly summary: {e}")


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    return user_id in ALLOWED_USERS


async def debug_gold_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /debug_gold command - show cTrader async client status"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    try:
        global _ctrader_async_client
        
        if _ctrader_async_client:
            try:
                # Get connection status
                connected = _ctrader_async_client.connected and _ctrader_async_client.authenticated
                
                # Get symbol ID
                symbol_id = None
                if "XAUUSD" in _ctrader_async_client.symbol_name_to_id:
                    symbol_id = _ctrader_async_client.symbol_name_to_id["XAUUSD"]
                
                # Get last quote
                quote = _ctrader_async_client.get_last_quote("XAUUSD")
                
                # Build response
                response_lines = [
                    "🔍 **cTrader Gold Debug**",
                    "",
                    f"**Connection:** {'✅ Connected' if connected else '❌ Not connected'}",
                    f"**Authenticated:** {'✅ Yes' if _ctrader_async_client.authenticated else '❌ No'}",
                    "",
                ]
                
                if symbol_id:
                    response_lines.append(f"**Symbol ID:** {symbol_id}")
                else:
                    response_lines.append("**Symbol ID:** ❌ Not found")
                    # Show available symbols
                    if _ctrader_async_client.symbol_name_to_id:
                        gold_symbols = [name for name in _ctrader_async_client.symbol_name_to_id.keys() 
                                       if "XAU" in name.upper() or "GOLD" in name.upper()]
                        if gold_symbols:
                            response_lines.append(f"**Available gold symbols:** {', '.join(gold_symbols[:10])}")
                
                response_lines.append("")
                
                if quote:
                    bid = quote.get("bid")
                    ask = quote.get("ask")
                    timestamp = quote.get("timestamp")
                    
                    if bid and ask:
                        mid = (bid + ask) / 2.0
                        age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds() if timestamp else None
                        
                        response_lines.extend([
                            f"**Bid:** {bid:.2f}",
                            f"**Ask:** {ask:.2f}",
                            f"**Mid:** {mid:.2f}",
                        ])
                        
                        if age_seconds is not None:
                            response_lines.append(f"**Age:** {age_seconds:.1f}s")
                    else:
                        response_lines.append("**Quote:** ⚠️ Partial (bid or ask missing)")
                else:
                    response_lines.append("**Quote:** ❌ No quotes received yet")
                
                response_text = "\n".join(response_lines)
                await update.message.reply_text(response_text, parse_mode='Markdown')
                
            except Exception as e:
                await update.message.reply_text(f"❌ Error getting debug info: {e}")
        else:
            await update.message.reply_text("❌ cTrader async client not initialized")
        
    except Exception as e:
        error_msg = f"❌ Error in debug_gold: {e}\n\n{traceback.format_exc()[:1000]}"
        await update.message.reply_text(error_msg)
        
        # 2. cTrader subscription status
        debug_info.append("\n📡 **cTrader Subscription:**")
        if _ctrader_async_client:
            if "XAUUSD" in _ctrader_async_client.symbol_name_to_id:
                symbol_id = _ctrader_async_client.symbol_name_to_id["XAUUSD"]
                is_subscribed = symbol_id in _ctrader_async_client.last_quotes
                last_quote = _ctrader_async_client.last_quotes.get(symbol_id, {})
                debug_info.append(f"✅ Async client initialized")
                debug_info.append(f"   Symbol ID: {symbol_id}")
                debug_info.append(f"   Subscription: {'✅ Subscribed' if is_subscribed else '❌ Not subscribed'}")
                if last_quote:
                    debug_info.append(f"   Last quote: bid={last_quote.get('bid', 'N/A')}, ask={last_quote.get('ask', 'N/A')}")
            else:
                debug_info.append("⚠️ Async client initialized but symbol not resolved")
        else:
            debug_info.append("❌ Async client not initialized")
            ctrader_config = Config.get_ctrader_config()
            if not all([ctrader_config.access_token, ctrader_config.client_id, ctrader_config.client_secret]) or not ctrader_config.account_id:
                debug_info.append("   → cTrader credentials not configured")
        
        # 3. Current quotes
        debug_info.append("\n💰 **Current Quotes:**")
        if _gold_symbol_resolved:
            symbol_name, _ = _gold_symbol_resolved
            symbol_upper = symbol_name.upper()
            if symbol_upper in _gold_quote_cache:
                quote_data = _gold_quote_cache[symbol_upper]
                bid = quote_data.get("bid", 0.0)
                ask = quote_data.get("ask", 0.0)
                timestamp = quote_data.get("timestamp", "N/A")
                first_tick = quote_data.get("first_tick_at", "N/A")
                partial_count = quote_data.get("partial_count", 0)
                merged_count = quote_data.get("merged_count", 0)
                
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2.0
                    debug_info.append(f"✅ Bid: {bid:.2f}, Ask: {ask:.2f}, Mid: {mid:.2f}")
                    debug_info.append(f"   Last update: {timestamp}")
                    debug_info.append(f"   First tick: {first_tick}")
                    debug_info.append(f"   Partial ticks: {partial_count}, Merged: {merged_count}")
                else:
                    debug_info.append(f"⚠️ Invalid tick: bid={bid}, ask={ask}")
                    if bid == 0 and ask == 0:
                        debug_info.append("   → No quotes received yet")
                    else:
                        debug_info.append(f"   → Partial tick (partial_count={partial_count})")
            else:
                debug_info.append("❌ No quotes in cache")
        else:
            debug_info.append("⚠️ Cannot check quotes - symbol not resolved")
        
        # 4. Last send attempt
        debug_info.append("\n📤 **Last Send Attempt:**")
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        gold_signals = signals.get("gold_private", []) if signals.get("date") == today else []
        debug_info.append(f"Today's signals: {len(gold_signals)}/{MAX_GOLD_SIGNALS}")
        
        # Check throttle
        can_send, throttle_reason, throttle_details = can_send_signal_now(CHANNEL_GOLD_PRIVATE, return_reason=True)
        debug_info.append(f"Throttle check: {'✅ Can send' if can_send else f'❌ {throttle_reason.value}'}")
        if not can_send:
            if throttle_reason == SignalRejectReason.THROTTLE_MIN_INTERVAL:
                wait_mins = throttle_details.get("remaining_minutes", 0)
                debug_info.append(f"   → Wait {wait_mins:.1f} more minutes (5 min interval)")
            elif throttle_reason == SignalRejectReason.THROTTLE_CHANNEL_INTERVAL:
                wait_hours = throttle_details.get("remaining_hours", 0)
                debug_info.append(f"   → Wait {wait_hours:.2f} more hours (2h interval)")
        
        # Check 36h rule
        can_send_pair, pair_reason, pair_details = can_send_pair_signal_to_channel(
            CHANNEL_GOLD_PRIVATE, "XAUUSD", return_reason=True
        )
        debug_info.append(f"36h rule check: {'✅ Can send' if can_send_pair else f'❌ {pair_reason.value}'}")
        if not can_send_pair:
            wait_hours = pair_details.get("remaining_hours", 0)
            debug_info.append(f"   → Wait {wait_hours:.2f} more hours")
        
        # 5. Test signal generation
        debug_info.append("\n🧪 **Test Signal Generation:**")
        test_signal = await generate_gold_signal()
        if test_signal:
            debug_info.append(f"✅ Generated: {test_signal['type']} @ {test_signal['entry']:.2f}")
        else:
            debug_info.append("❌ Generation failed")
        
        # 6. Price source
        debug_info.append("\n📊 **Price Source:**")
        ctrader_price = get_gold_price_from_ctrader()
        external_price = get_real_forex_price("XAUUSD")
        if ctrader_price:
            debug_info.append(f"✅ cTrader: {ctrader_price:.2f}")
        else:
            debug_info.append("❌ cTrader: Not available")
        if external_price:
            debug_info.append(f"✅ External API: {external_price:.2f}")
        else:
            debug_info.append("❌ External API: Not available")
        
        debug_text = "\n".join(debug_info)
        await update.message.reply_text(debug_text, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = f"❌ Error in debug_gold: {e}\n\n{traceback.format_exc()}"
        await update.message.reply_text(error_msg[:4000])  # Telegram limit


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    # Main menu: Channel selection buttons
    keyboard = [
        [InlineKeyboardButton("📊 Forex 3TP", callback_data="channel_forex_3tp")],
        [InlineKeyboardButton("📈 Forex", callback_data="channel_forex")],
        [InlineKeyboardButton("🪙 Crypto Lingrid", callback_data="channel_crypto_lingrid")],
        [InlineKeyboardButton("💎 Crypto Gain Muse", callback_data="channel_crypto_gainmuse")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Trading Signals Bot Control Panel**

**Select a channel to manage:**

📊 **Forex 3TP** - Forex signals with 3 take profit levels
📈 **Forex** - Standard forex signals
🪙 **Crypto Lingrid** - Crypto channel 1
💎 **Crypto Gain Muse** - Crypto channel 2

*Click any channel button to proceed*
    """
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_authorized(user_id):
        await query.answer("❌ You are not authorized to use this bot.")
        return
    
    await query.answer()
    
    # Channel selection (level 1)
    if query.data.startswith("channel_"):
        channel_type = query.data.replace("channel_", "")
        await show_channel_menu(query, context, channel_type)
    # Channel actions (level 2)
    elif query.data.startswith("result_24h_"):
        channel_type = query.data.replace("result_24h_", "")
        await handle_performance_report(query, context, channel_type, days=1)
    elif query.data.startswith("result_7d_"):
        channel_type = query.data.replace("result_7d_", "")
        await handle_performance_report(query, context, channel_type, days=7)
    elif query.data.startswith("give_signal_"):
        channel_type = query.data.replace("give_signal_", "")
        await handle_give_signal(query, context, channel_type)
    elif query.data == "back_to_main":
        await show_main_menu(query, context)
    # Legacy handlers for backward compatibility
    elif query.data == "forex_signal":
        await handle_forex_signal(query, context)
    elif query.data == "forex_3tp_signal":
        await handle_forex_3tp_signal(query, context)
    elif query.data == "crypto_signal":
        await handle_crypto_signal(query, context)
    elif query.data == "forex_performance":
        await handle_performance_report(query, context, "forex", days=1)
    elif query.data == "forex_3tp_performance":
        await handle_performance_report(query, context, "forex_3tp", days=1)
    elif query.data == "crypto_performance":
        await handle_performance_report(query, context, "crypto", days=1)
    elif query.data == "forex_status":
        await handle_forex_status(query, context)
    elif query.data == "forex_3tp_status":
        await handle_forex_3tp_status(query, context)
    elif query.data == "crypto_status":
        await handle_crypto_status(query, context)
    elif query.data == "forward_forex":
        await handle_forward_forex(query, context)
    elif query.data == "refresh":
        await show_main_menu(query, context)


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with channel selection"""
    keyboard = [
        [InlineKeyboardButton("📊 Forex 3TP", callback_data="channel_forex_3tp")],
        [InlineKeyboardButton("📈 Forex", callback_data="channel_forex")],
        [InlineKeyboardButton("🪙 Crypto Lingrid", callback_data="channel_crypto_lingrid")],
        [InlineKeyboardButton("💎 Crypto Gain Muse", callback_data="channel_crypto_gainmuse")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Trading Signals Bot Control Panel**

**Select a channel to manage:**

📊 **Forex 3TP** - Forex signals with 3 take profit levels
📈 **Forex** - Standard forex signals
🪙 **Crypto Lingrid** - Crypto channel 1
💎 **Crypto Gain Muse** - Crypto channel 2

*Click any channel button to proceed*
    """
    
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_channel_menu(query, context: ContextTypes.DEFAULT_TYPE, channel_type: str) -> None:
    """Show channel-specific menu with actions"""
    # Channel names mapping
    channel_names = {
        "forex_3tp": "Forex 3TP",
        "forex": "Forex",
        "crypto_lingrid": "Crypto Lingrid",
        "crypto_gainmuse": "Crypto Gain Muse"
    }
    
    channel_name = channel_names.get(channel_type, channel_type)
    
    keyboard = [
        [InlineKeyboardButton("📊 Result 24h", callback_data=f"result_24h_{channel_type}")],
        [InlineKeyboardButton("📈 Result 7 days", callback_data=f"result_7d_{channel_type}")],
        [InlineKeyboardButton("🚀 Give signal", callback_data=f"give_signal_{channel_type}")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = f"""
📺 **{channel_name} Channel**

**Available actions:**

📊 **Result 24h** - Check profit from all signals in last 24 hours
📈 **Result 7 days** - Check profit from all signals in last 7 days
🚀 **Give signal** - Generate and send a signal to this channel

*Select an action*
    """
    
    await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_give_signal(query, context: ContextTypes.DEFAULT_TYPE, channel_type: str) -> None:
    """Handle signal generation for a specific channel"""
    await query.edit_message_text("🔄 Generating signal with real price...")
    
    try:
        if channel_type == "forex_3tp":
            await handle_forex_3tp_signal(query, context)
        elif channel_type == "forex":
            await handle_forex_signal(query, context)
        elif channel_type == "crypto_lingrid":
            await handle_crypto_signal_for_channel(query, context, CRYPTO_CHANNEL_LINGRID, "crypto_lingrid")
        elif channel_type == "crypto_gainmuse":
            await handle_crypto_signal_for_channel(query, context, CRYPTO_CHANNEL_GAINMUSE, "crypto_gainmuse")
        else:
            await query.edit_message_text(
                f"❌ **Unknown channel type:** {channel_type}",
                parse_mode='Markdown'
            )
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating signal:**\n\n{str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_signal_for_channel(query, context: ContextTypes.DEFAULT_TYPE, channel_id: str, channel_type: str) -> None:
    """Handle crypto signal generation for a specific channel"""
    await query.edit_message_text("🔄 Generating crypto signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        # Determine which channel array to check
        if channel_type == "crypto_lingrid":
            channel_signals = signals.get("crypto_lingrid", [])
            max_signals = MAX_CRYPTO_SIGNALS_LINGRID
        else:
            channel_signals = signals.get("crypto_gainmuse", [])
            max_signals = MAX_CRYPTO_SIGNALS_GAINMUSE
        
        if len(channel_signals) >= max_signals:
            await query.edit_message_text(
                f"⚠️ **Crypto Signal Limit Reached**\n\n"
                f"Today's crypto signals: {len(channel_signals)}/{max_signals}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Determine channel name for generate_crypto_signal
        channel_name = "lingrid" if channel_type == "crypto_lingrid" else "gainmuse"
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(CRYPTO_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_crypto_signal(channel_name)
            if signal is None:
                await query.edit_message_text(
                    f"❌ **Error generating crypto signal**\n\n"
                    f"Could not get real price from Binance API or all pairs already have active signals today",
                    parse_mode='Markdown'
                )
                return
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(channel_id, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    await query.edit_message_text(
                        f"⚠️ **Cannot send signal**\n\n"
                        f"All crypto pairs have been sent in last 36 hours for this channel.",
                        parse_mode='Markdown'
                    )
                    return
                signal = None
                continue
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating crypto signal**\n\n"
                f"Could not find available pair (all pairs sent in last 36h)",
                parse_mode='Markdown'
            )
            return
        
        # Add to appropriate channel array
        if channel_type == "crypto_lingrid":
            signals["crypto_lingrid"].append(signal)
        else:
            signals["crypto_gainmuse"].append(signal)
        save_signals(signals)
        
        # Send to specified channel
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=channel_id, text=message)

        # Save signal to channel file
        save_channel_signal(channel_id, signal)
        
        # Update pair-specific last signal time
        save_channel_pair_last_signal_time(channel_id, signal['pair'])
        
        # Calculate distribution
        buy_count = len([s for s in channel_signals if s.get("type") == "BUY"])
        total_crypto = len(channel_signals)
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        # Show channel menu again
        await show_channel_menu(query, context, channel_type)
        
        print(f"✅ Crypto signal sent to {channel_id}: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating crypto signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex signal generation"""
    await query.edit_message_text("🔄 Generating forex signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "forwarded_forex": [], "date": today}
        
        if len(signals.get("forex", [])) >= MAX_FOREX_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Forex Signal Limit Reached**\n\n"
                f"Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(FOREX_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_forex_signal()
            if signal is None:
                await query.edit_message_text(
                    f"❌ **Error generating forex signal**\n\n"
                    f"Could not get real price from forex API or all pairs already have active signals today",
                    parse_mode='Markdown'
                )
                return
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(CHANNEL_LINGRID_FOREX, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    await query.edit_message_text(
                        f"⚠️ **Cannot send signal**\n\n"
                        f"All forex pairs have been sent in last 36 hours for this channel.",
                        parse_mode='Markdown'
                    )
                    return
                signal = None
                continue
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating forex signal**\n\n"
                f"Could not find available pair (all pairs sent in last 36h)",
                parse_mode='Markdown'
            )
            return
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)

        # Save signal to channel file (FOREX_CHANNEL = Lingrid Forex)
        save_channel_signal(CHANNEL_LINGRID_FOREX, signal)
        
        # Update pair-specific last signal time
        save_channel_pair_last_signal_time(CHANNEL_LINGRID_FOREX, signal['pair'])
        
        # Show channel menu again
        await show_channel_menu(query, context, "forex")
        
        print(f"✅ Forex signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating forex signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_3tp_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex 3TP signal generation"""
    await query.edit_message_text("🔄 Generating forex 3TP signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "forwarded_forex": [], "date": today}
        
        if len(signals.get("forex_3tp", [])) >= MAX_FOREX_3TP_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Forex 3TP Signal Limit Reached**\n\n"
                f"Today's forex 3TP signals: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal (will try different pairs until one passes 36h check)
        max_attempts = len(FOREX_PAIRS) * 2
        attempts = 0
        signal = None
        
        while attempts < max_attempts:
            signal = generate_forex_3tp_signal()
            if signal is None:
                await query.edit_message_text(
                    "❌ **Could not generate forex 3TP signal**\n\n"
                    "All forex pairs may already have active signals today.",
                    parse_mode='Markdown'
                )
                return
            
            # Check 36-hour rule for this pair in this channel
            if can_send_pair_signal_to_channel(CHANNEL_DEGRAM, signal['pair']):
                break
            else:
                attempts += 1
                if attempts >= max_attempts:
                    await query.edit_message_text(
                        f"⚠️ **Cannot send signal**\n\n"
                        f"All forex pairs have been sent in last 36 hours for this channel.",
                        parse_mode='Markdown'
                    )
                    return
                signal = None
                continue
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Could not generate forex 3TP signal**\n\n"
                f"Could not find available pair (all pairs sent in last 36h)",
                parse_mode='Markdown'
            )
            return
        
        signals["forex_3tp"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_3tp_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message)

        # Save signal to channel file (FOREX_CHANNEL_3TP = DeGRAM)
        save_channel_signal(CHANNEL_DEGRAM, signal)
        
        # Update pair-specific last signal time
        save_channel_pair_last_signal_time(CHANNEL_DEGRAM, signal['pair'])
        
        # Show channel menu again
        await show_channel_menu(query, context, "forex_3tp")
        
        print(f"✅ Forex 3TP signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error sending forex 3TP signal:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
        print(f"❌ Error sending forex 3TP signal: {e}")


def get_analytics_from_results(channel_id, days: int):
    """Calculate analytics from saved result files with improved logic"""
    results = load_channel_results(channel_id)

    if not results:
        return {
            "total_signals": 0,
            "profit_signals": 0,
            "loss_signals": 0,
            "total_profit": 0,
            "avg_profit_per_signal": 0,
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "signals_detail": []
        }

    # Filter by date range
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    filtered_results = []

    for result in results:
        try:
            hit_time = result.get("hit_time", "")
            if hit_time:
                hit_date = datetime.fromisoformat(hit_time.replace("Z", "+00:00"))
                if hit_date >= cutoff_date:
                    filtered_results.append(result)
        except:
            continue

    if not filtered_results:
        return {
            "total_signals": 0,
            "profit_signals": 0,
            "loss_signals": 0,
            "total_profit": 0,
            "avg_profit_per_signal": 0,
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "signals_detail": []
        }

    # Group results by timestamp (same signal)
    signal_groups = {}
    for result in filtered_results:
        timestamp = result.get("timestamp", "")
        if timestamp not in signal_groups:
            signal_groups[timestamp] = []
        signal_groups[timestamp].append(result)

    # Process each signal - apply logic: if TP hit then SL hit, count TP
    processed_signals = []
    for timestamp, group_results in signal_groups.items():
        # Sort by hit_time to get chronological order
        group_results.sort(key=lambda x: x.get("hit_time", ""))

        # Find the best result (highest TP before SL, or SL if no TP)
        best_result = None
        highest_tp_result = None
        tp_order_map = {"TP1": 1, "TP2": 2, "TP3": 3, "TP": 1}
        sl_result = None

        for result in group_results:
            hit_type = result.get("hit_type", "")
            if hit_type.startswith("TP"):
                # Track highest TP
                if highest_tp_result is None:
                    highest_tp_result = result
            else:
                    current_order = tp_order_map.get(hit_type, 0)
                    existing_order = tp_order_map.get(highest_tp_result.get("hit_type", ""), 0)
                    if current_order > existing_order:
                        highest_tp_result = result
            if hit_type == "SL":
                sl_result = result

                # Logic: If any TP hit, use the highest TP (even if SL hit later)
                # If no TP hit but SL hit, use SL
        if highest_tp_result:
            best_result = highest_tp_result
        elif sl_result:
            best_result = sl_result

        if best_result:
            processed_signals.append(best_result)

            # Calculate statistics
    total_signals = len(processed_signals)
    profit_count = 0
    loss_count = 0
    profit_values = []
    loss_values = []
    signals_detail = []
    total_profit = 0

    # Determine if forex or crypto based on channel
    is_forex = channel_id in [FOREX_CHANNEL, FOREX_CHANNEL_3TP, FOREX_CHANNEL_ADDITIONAL, "-1001286609636"]

    for result in processed_signals:
        pair = result.get("pair", "")
        hit_type = result.get("hit_type", "")

        if is_forex:
            # Forex: calculate in pips
            if hit_type.startswith("TP"):
                profit_pips = result.get("profit_pips", 0)
                if profit_pips > 0:
                    profit_count += 1
                    total_profit += profit_pips
                    profit_values.append(profit_pips)
                    signals_detail.append(f"✅ {pair} {hit_type}: +{profit_pips:.1f} pips")
                else:
                    loss_count += 1
                    loss_values.append(abs(profit_pips))
                    signals_detail.append(f"❌ {pair} {hit_type}: {profit_pips:.1f} pips")
            if hit_type == "SL":
                loss_pips = result.get("loss_pips", 0)
                loss_count += 1
                total_profit += loss_pips  # negative
                loss_values.append(abs(loss_pips))
                signals_detail.append(f"❌ {pair} SL: -{abs(loss_pips):.1f} pips")
        else:
            # Crypto: calculate in percentage
            if hit_type.startswith("TP"):
                profit_percent = result.get("profit_percent", 0)
                if profit_percent > 0:
                    profit_count += 1
                    total_profit += profit_percent
                    profit_values.append(profit_percent)
                    signals_detail.append(f"✅ {pair} {hit_type}: +{profit_percent:.2f}%")
                else:
                    loss_count += 1
                    loss_values.append(abs(profit_percent))
                    signals_detail.append(f"❌ {pair} {hit_type}: {profit_percent:.2f}%")
            if hit_type == "SL":
                loss_percent = result.get("loss_percent", 0)
                loss_count += 1
                total_profit += loss_percent  # negative
                loss_values.append(abs(loss_percent))
                signals_detail.append(f"❌ {pair} SL: -{abs(loss_percent):.2f}%")

                # Calculate final statistics
    avg_profit_per_signal = total_profit / total_signals if total_signals > 0 else 0
    win_rate = (profit_count / total_signals * 100) if total_signals > 0 else 0
    avg_profit = sum(profit_values) / len(profit_values) if profit_values else 0
    avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0

    total_profit_sum = sum(profit_values) if profit_values else 0
    total_loss_sum = sum(loss_values) if loss_values else 0
    profit_factor = total_profit_sum / total_loss_sum if total_loss_sum > 0 else float('inf')

    return {
        "total_signals": total_signals,
        "profit_signals": profit_count,
        "loss_signals": loss_count,
        "total_profit": total_profit,
        "avg_profit_per_signal": avg_profit_per_signal,
        "win_rate": win_rate,
        "avg_profit": avg_profit,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "signals_detail": signals_detail,
        "is_forex": is_forex
    }


async def handle_performance_report(query, context: ContextTypes.DEFAULT_TYPE, signal_type: str, days: int) -> None:
    """Handle performance report for specific signal type - using saved results"""
    await query.edit_message_text(f"🔄 Calculating {signal_type} performance for last {days} day(s) from saved results...")

    try:
        # Map signal type to channel ID
        channel_id_map = {
            "forex": FOREX_CHANNEL,
            "forex_3tp": FOREX_CHANNEL_3TP,
            "crypto_lingrid": CRYPTO_CHANNEL_LINGRID,
            "crypto_gainmuse": CRYPTO_CHANNEL_GAINMUSE,
            "crypto": CRYPTO_CHANNEL_LINGRID  # Default to lingrid
        }

        channel_id = channel_id_map.get(signal_type)

        # Channel names
        channel_names = {
            "forex": "Forex",
            "forex_3tp": "Forex 3TP",
            "crypto_lingrid": "Crypto Lingrid",
            "crypto_gainmuse": "Crypto Gain Muse",
            "crypto": "Crypto"
        }

        channel_name = channel_names.get(signal_type, signal_type)

        if not channel_id:
            await query.edit_message_text("❌ Invalid signal type")
            return
        
            # Calculate performance from saved results
        performance = get_analytics_from_results(channel_id, days)
        
        # Create back button
        keyboard = [[InlineKeyboardButton("⬅️ Back to Channel Menu", callback_data=f"channel_{signal_type}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if performance["total_signals"] == 0:
            await query.edit_message_text(
                f"📊 **{channel_name} Performance Report**\n\n"
                f"📅 **Period:** Last {days} day(s)\n"
                f"📈 **Total Signals:** 0\n\n"
                f"No signals found for this period.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Format comprehensive performance report
        report = f"📊 **{channel_name} Performance Report**\n\n"
        report += f"📅 **Period:** Last {days} day(s)\n\n"
        
        # Summary statistics
        report += "📈 **SUMMARY**\n"
        report += f"Total Signals: {performance['total_signals']}\n"
        report += f"Winning Signals: {performance['profit_signals']} ({performance['win_rate']:.1f}%)\n"
        report += f"Losing Signals: {performance['loss_signals']} ({100-performance['win_rate']:.1f}%)\n\n"
        
        # Profit/Loss details - use correct units (pips for forex, % for crypto)
        report += "💰 **PROFIT/LOSS**\n"
        if performance.get('is_forex', False):
            # Forex: pips
            report += f"Total Profit: {performance['total_profit']:+.1f} pips\n"
            report += f"Average per Signal: {performance['avg_profit_per_signal']:+.1f} pips\n"
            if performance['profit_signals'] > 0:
                report += f"Average Win: {performance['avg_profit']:+.1f} pips\n"
            if performance['loss_signals'] > 0:
                report += f"Average Loss: {performance['avg_loss']:+.1f} pips\n"
        else:
            # Crypto: percentage
            report += f"Total Profit: {performance['total_profit']:+.2f}%\n"
            report += f"Average per Signal: {performance['avg_profit_per_signal']:+.2f}%\n"
            if performance['profit_signals'] > 0:
                report += f"Average Win: {performance['avg_profit']:+.2f}%\n"
            if performance['loss_signals'] > 0:
                report += f"Average Loss: {performance['avg_loss']:+.2f}%\n"
            if performance['profit_factor'] != float('inf'):
                report += f"Profit Factor: {performance['profit_factor']:.2f}\n"
            else:
                report += "Profit Factor: ∞\n"
        report += "\n"
        
        # Individual signal results (only for short periods)
        if days <= 3 and performance['signals_detail']:
            report += "📋 **INDIVIDUAL SIGNALS**\n"
        for signal_detail in performance["signals_detail"]:
            report += f"{signal_detail}\n"
            report += "\n"
        
        # Performance rating
        win_rate = performance['win_rate']
        profit_factor = performance['profit_factor']
        
        if win_rate >= 70 and profit_factor >= 2.0:
            rating = "🏆 EXCELLENT"
        elif win_rate >= 60 and profit_factor >= 1.5:
            rating = "🥇 VERY GOOD"
        elif win_rate >= 50 and profit_factor >= 1.0:
            rating = "🥈 GOOD"
        elif win_rate >= 40:
            rating = "🥉 FAIR"
        else:
            rating = "⚠️ NEEDS IMPROVEMENT"
        
        report += f"🎯 **PERFORMANCE RATING: {rating}**"
        
        await query.edit_message_text(report, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error calculating performance:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
        print(f"❌ Error calculating performance: {e}")


async def handle_forex_3tp_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex 3TP status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_3tp_signals = []
        else:
            forex_3tp_signals = signals.get("forex_3tp", [])
        
        forex_3tp_count = len(forex_3tp_signals)
        active_pairs = [s["pair"] for s in forex_3tp_signals]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        await query.edit_message_text(
            f"📈 **Forex 3TP Status**\n\n"
            f"📊 Today's signals: {forex_3tp_count}/{MAX_FOREX_3TP_SIGNALS}\n"
            f"📋 Active pairs: {active_pairs_text}\n\n"
            f"{'✅ Ready to generate more signals' if forex_3tp_count < MAX_FOREX_3TP_SIGNALS else '⚠️ Daily limit reached'}\n"
            f"🤖 Automatic signals: Running in background",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error checking forex 3TP status:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
        signal = generate_forex_signal()
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating forex signal**\n\n"
                f"Could not get real price from forex API or all pairs already have active signals today",
                parse_mode='Markdown'
            )
            return
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)
        
        await query.edit_message_text(
            f"✅ **Forex Signal Generated**\n\n"
            f"📊 {signal['pair']} {signal['type']} at {signal['entry']}\n"
            f"📤 Signal sent to forex channel\n"
            f"📊 Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating forex signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle crypto signal generation"""
    await query.edit_message_text("🔄 Generating crypto signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto": [], "date": today}
        
        if len(signals.get("crypto", [])) >= MAX_CRYPTO_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Crypto Signal Limit Reached**\n\n"
                f"Today's crypto signals: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal
        signal = generate_crypto_signal()
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating crypto signal**\n\n"
                f"Could not get real price from Binance API or all pairs already have active signals today",
                parse_mode='Markdown'
            )
            return
        
        signals["crypto"].append(signal)
        save_signals(signals)
        
        # Send to both crypto channels
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_LINGRID, text=message)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_GAINMUSE, text=message)
        
        # Calculate distribution
        crypto_signals = signals.get("crypto", [])
        buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
        total_crypto = len(crypto_signals)
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        await query.edit_message_text(
            f"✅ **Crypto Signal Generated**\n\n"
            f"🪙 {signal['pair']} {signal['type']} at {signal['entry']}\n"
            f"📤 Signal sent to crypto channel\n"
            f"📊 Today's crypto signals: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}\n"
            f"📈 Distribution: BUY {buy_count} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count} ({sell_ratio:.1f}%)",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating crypto signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_count = 0
        else:
            forex_count = len(signals.get("forex", []))
        
        # Get active pairs
        active_pairs = [s["pair"] for s in signals.get("forex", [])]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        status_text = f"""
📈 **Forex Signals Status**

📊 Today's signals: {forex_count}/{MAX_FOREX_SIGNALS}
📋 Active pairs: {active_pairs_text}
📤 Channel: {FOREX_CHANNEL}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if forex_count < MAX_FOREX_SIGNALS else '⚠️ Daily limit reached'}
🤖 Automatic signals: Running in background
        """
        
        await query.edit_message_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting forex status**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle crypto status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            crypto_count = 0
            buy_count = 0
        else:
            crypto_signals = signals.get("crypto", [])
            crypto_count = len(crypto_signals)
            buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
        
        total_crypto = crypto_count
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        # Get active pairs
        active_pairs = [s["pair"] for s in signals.get("crypto", [])]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        status_text = f"""
🪙 **Crypto Signals Status**

📊 Today's signals: {crypto_count}/{MAX_CRYPTO_SIGNALS}
📋 Active pairs: {active_pairs_text}
📈 Distribution: BUY {buy_count} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count} ({sell_ratio:.1f}%)
📤 Channel: {CRYPTO_CHANNEL}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if crypto_count < MAX_CRYPTO_SIGNALS else '⚠️ Daily limit reached'}
🤖 Automatic signals: Running in background
        """
        
        await query.edit_message_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting crypto status**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_report(query, context: ContextTypes.DEFAULT_TYPE, days: int = 1) -> None:
    """Handle forex performance report"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_signals = []
        else:
            forex_signals = signals.get("forex", [])
        
        if not forex_signals:
            report_text = f"""
📊 **Forex Performance Report ({days} day{'s' if days > 1 else ''})**

No forex signals found for the period.

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        else:
            report_text = f"""
📊 **Forex Performance Report ({days} day{'s' if days > 1 else ''})**

📈 Total signals: {len(forex_signals)}
📊 BUY signals: {len([s for s in forex_signals if s.get('type') == 'BUY'])}
📊 SELL signals: {len([s for s in forex_signals if s.get('type') == 'SELL'])}

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        
        await query.edit_message_text(report_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting forex report**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_report(query, context: ContextTypes.DEFAULT_TYPE, days: int = 1) -> None:
    """Handle crypto performance report"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            crypto_signals = []
        else:
            crypto_signals = signals.get("crypto", [])
        
        if not crypto_signals:
            report_text = f"""
🪙 **Crypto Performance Report ({days} day{'s' if days > 1 else ''})**

No crypto signals found for the period.

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        else:
            buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
            sell_count = len([s for s in crypto_signals if s.get("type") == "SELL"])
            total_signals = len(crypto_signals)
            buy_ratio = (buy_count / total_signals * 100) if total_signals > 0 else 0
            sell_ratio = (sell_count / total_signals * 100) if total_signals > 0 else 0
            
            report_text = f"""
🪙 **Crypto Performance Report ({days} day{'s' if days > 1 else ''})**

📊 Total signals: {total_signals}
📈 BUY signals: {buy_count} ({buy_ratio:.1f}%)
📉 SELL signals: {sell_count} ({sell_ratio:.1f}%)

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        
        await query.edit_message_text(report_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting crypto report**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_refresh(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle refresh - go back to main menu"""
    await show_main_menu(query, context)


async def handle_forward_forex(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forwarding forex signals from original channel to new channel"""
    user_id = query.from_user.id
    
    # Only allow admin users to use this feature
    if user_id not in ALLOWED_USERS:
        await query.edit_message_text("❌ You are not authorized to use this feature.")
        return
    
    await query.edit_message_text("🔄 Forwarding forex signal to new channel...")
    
    try:
        # Generate a new forex signal (with 1 TP)
        signal = generate_forex_signal()
        
        if signal is None:
            await query.edit_message_text(
                "❌ Could not generate forex signal. All pairs may be active today.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
                ]])
            )
            return
        
        # Send to the new channel (-1001286609636)
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id="-1001286609636", text=message)
        
        # Update signals data (don't count towards daily limit since it's a forward)
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        # Add to forwarded signals (separate tracking)
        if "forwarded_forex" not in signals:
            signals["forwarded_forex"] = []
        
        signals["forwarded_forex"].append(signal)
        save_signals(signals)
        
        await query.edit_message_text(
            f"✅ **Forex Signal Forwarded Successfully!**\n\n"
            f"📊 **Signal Details:**\n"
            f"• Pair: {signal['pair']}\n"
            f"• Type: {signal['type']}\n"
            f"• Entry: {signal['entry']:,.5f}\n"
            f"• SL: {signal['sl']:,.5f}\n"
            f"• TP: {signal['tp']:,.5f}\n\n"
            f"📤 **Sent to:** -1001286609636\n"
            f"⏰ **Time:** {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
            ]]),
            parse_mode='Markdown'
        )
        
        print(f"✅ Forex signal forwarded by admin user {user_id}: {signal['pair']} {signal['type']} to -1001286609636")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error forwarding forex signal:**\n\n"
            f"Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
            ]]),
            parse_mode='Markdown'
        )
        print(f"❌ Error forwarding forex signal: {e}")


def hourly_tp_check_loop():
    """TP/SL hit monitoring loop - checks every 30 minutes (runs in separate thread)"""
    print("⏰ Starting TP/SL hit monitoring loop (every 30 minutes)...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def async_loop():
        while True:
            try:
                # Check for TP/SL hits every 30 minutes
                print(f"🔍 Checking for TP/SL hits at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}...")
                await check_and_notify_tp_hits()
                
                # Wait 30 minutes (1800 seconds) until next check
                print(f"⏰ Next TP/SL check in 30 minutes...")
                await asyncio.sleep(1800)
                
            except Exception as e:
                print(f"❌ Error in hourly TP check loop: {e}")
                print("⏳ Waiting 5 minutes before retry...")
                await asyncio.sleep(300)
    
    loop.run_until_complete(async_loop())


def automatic_signal_loop():
    """Automatic signal generation loop (runs in separate thread)"""
    print("🤖 Starting automatic signal generation loop...")
    print("🚀 Bot will start sending signals immediately (no initial delay)")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Send initial signals on startup
    async def send_initial_signals():
        """Send initial signals when bot starts"""
        try:
            # Wait a moment for bot to fully initialize
            await asyncio.sleep(3)
            
            # Initialize cTrader for FOREX pairs only (not for gold/index)
            # Gold and Index use Yahoo Finance, so no cTrader initialization needed for them
            try:
                account_id = Config.get_account_id_or_raise()
                ctrader_config = Config.get_ctrader_config()
                if all([ctrader_config.access_token, ctrader_config.client_id, ctrader_config.client_secret]) and account_id > 0:
                    print("\n[INIT] Initializing cTrader for FOREX quotes...")
                    ctrader_ok = await init_ctrader_async_client()
                    if ctrader_ok:
                        print("[INIT] cTrader initialized for FOREX")
                    else:
                        print("[INIT] cTrader initialization failed")
                else:
                    print("[INIT] cTrader credentials not configured, skipping cTrader initialization")
            except ValueError as e:
                print(f"[INIT] Config error: {e}")
                print(f"[INIT] cTrader initialization skipped")
            
            # Send 1 gold signal to GOLD Private channel (WITH throttle exception for startup)
            # Gold uses Yahoo Finance, no connection check needed
            print("\n🥇 [INIT] Attempting to send initial gold signal to GOLD Private channel...")
            print("   → Throttle rules EXEMPTED for startup initial signal")
            print("   → Using Yahoo Finance as price source")
            gold_success, gold_reason, gold_details = await send_gold_signal(return_reason=True, skip_throttle=True)
            
            if gold_success:
                print("✅ [INIT] Initial gold signal sent successfully")
            else:
                if gold_reason:
                    # Detailed reason logging with exact reason code
                    reason = gold_reason.value
                    print(f"❌ [INIT] Could not send initial gold signal")
                    print(f"   Reason Code: {reason}")
                    
                    # Log specific reason details
                    if reason == SignalRejectReason.DAILY_LIMIT.value:
                        gold_count = gold_details.get("gold_count", 0)
                        max_signals = gold_details.get("max_gold_signals", MAX_GOLD_SIGNALS)
                        print(f"   → DAILY_LIMIT: Already sent {gold_count}/{max_signals} gold signals today")
                    
                    elif reason == SignalRejectReason.RULE_36H.value:
                        pair_details = gold_details.get("pair_36h_check", {})
                        wait_hours = pair_details.get("remaining_hours", 0)
                        pair_last_time = pair_details.get("pair_last_time", "N/A")
                        print(f"   → RULE_36H: 36-hour interval not met for XAUUSD in this channel")
                        print(f"   → Last signal sent at: {pair_last_time}")
                        print(f"   → Need to wait {wait_hours:.2f} more hours")
                    
                    elif reason == SignalRejectReason.GENERATION_FAILED.value:
                        print(f"   → GENERATION_FAILED: Could not generate gold signal")
                        print(f"   → Possible causes:")
                        print(f"      - Price unavailable (check cTrader connection and symbol resolution)")
                        print(f"      - External APIs failed")
                    
                    elif reason == SignalRejectReason.PRICE_UNAVAILABLE.value:
                        print(f"   → PRICE_UNAVAILABLE: Could not get gold price from any source")
                    elif reason == SignalRejectReason.PRICE_UNAVAILABLE_CTRADER_ONLY.value:
                        print(f"   → PRICE_UNAVAILABLE_CTRADER_ONLY: cTrader price not available (GOLD_CTRADER_ONLY=true)")
                        print(f"   → Check:")
                        print(f"      - cTrader connection status")
                        print(f"      - Symbol resolution (use /debug_gold to check)")
                        print(f"      - External API availability")
                    
                    elif reason == SignalRejectReason.SYMBOL_NOT_FOUND.value:
                        print(f"   → SYMBOL_NOT_FOUND: Gold symbol not found in cTrader")
                        print(f"   → Check available symbols and symbol name")
                    
                    elif reason == SignalRejectReason.NO_SPOT_SUBSCRIPTION.value:
                        print(f"   → NO_SPOT_SUBSCRIPTION: Not subscribed to spot quotes")
                        print(f"   → Check subscription status")
                    
                    elif reason == SignalRejectReason.INVALID_TICK.value:
                        print(f"   → INVALID_TICK: Received invalid tick (bid=0 or ask=0)")
                        print(f"   → Check quote data quality")
                    
                    elif reason == SignalRejectReason.EXCEPTION.value:
                        exception_msg = gold_details.get("exception", "Unknown")
                        print(f"   → EXCEPTION: {exception_msg}")
                        traceback_str = gold_details.get("traceback", "")
                        if traceback_str:
                            print(f"   → Traceback:\n{traceback_str}")
                    
                    else:
                        print(f"   → Unknown reason: {reason}")
                    
                    # Always print full details for debugging
                    print(f"\n   Full details:")
                    print(json.dumps(gold_details, indent=4, default=str))
            
            # Send 1 index signal
            print("\n📊 [INIT] Sending initial index signal on startup...")
            index_success = await send_index_signal()
            if index_success:
                print("✅ [INIT] Initial index signal sent successfully")
            else:
                print("⚠️ [INIT] Could not send initial index signal (may be weekend, limit reached, or price unavailable)")
        except Exception as e:
            print(f"⚠️ [INIT] Error sending initial signals: {e}")
            print(traceback.format_exc())
    
    # Run initial signals first, then start the main loop
    async def async_loop():
        # Send initial signals first (with delay to avoid conflicts)
        try:
            await asyncio.sleep(2)  # Small delay to let PTB initialize
            await send_initial_signals()
        except Exception as e:
            print(f"⚠️ [INIT] Error in send_initial_signals: {e}")
            print(traceback.format_exc())
        
        # Main signal generation loop
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                current_hour = current_time.hour
                
                # Check if we're in trading hours (4 GMT - 23 GMT)
                if not is_trading_hours():
                    print(f"🌙 Outside trading hours ({current_hour}:00 GMT). Market closed.")
                    # TP/SL monitoring disabled
                    # await check_and_notify_tp_hits()  # DISABLED
                    
                    # Wait until trading hours start
                    if current_hour < 4:
                        # Wait until 4 GMT
                        next_trading_time = current_time.replace(hour=4, minute=0, second=0, microsecond=0)
                    else:  # current_hour >= 23
                        # Wait until 4 GMT next day
                        next_trading_time = (current_time + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
                    
                    wait_seconds = (next_trading_time - current_time).total_seconds()
                    print(f"⏰ Waiting {wait_seconds/3600:.1f} hours until trading hours...")
                    await asyncio.sleep(wait_seconds)
                    continue
                
                # Check if we need to send signals
                signals = load_signals()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                if signals.get("date") != today:
                    signals = {"forex": [], "forex_3tp": [], "forex_additional": [], "crypto_lingrid": [], "crypto_gainmuse": [], "indexes": [], "gold_private": [], "forwarded_forex": [], "tp_notifications": [], "date": today}
                    save_signals(signals)
                    print(f"📅 New day: {today}")
                
                forex_count = len(signals.get("forex", []))
                forex_3tp_count = len(signals.get("forex_3tp", []))
                forex_additional_count = len(signals.get("forex_additional", []))
                crypto_lingrid_count = len(signals.get("crypto_lingrid", []))
                crypto_gainmuse_count = len(signals.get("crypto_gainmuse", []))
                index_count = len(signals.get("indexes", []))
                gold_count = len(signals.get("gold_private", []))

                print(f"📊 Current signals: Forex {forex_count}/{MAX_FOREX_SIGNALS}, Forex 3TP {forex_3tp_count}/{MAX_FOREX_3TP_SIGNALS}, Forex Additional {forex_additional_count}/{MAX_FOREX_ADDITIONAL_SIGNALS}, Crypto Lingrid {crypto_lingrid_count}/{MAX_CRYPTO_SIGNALS_LINGRID}, Crypto GainMuse {crypto_gainmuse_count}/{MAX_CRYPTO_SIGNALS_GAINMUSE}, Indexes {index_count}/{MAX_INDEX_SIGNALS}, Gold {gold_count}/{MAX_GOLD_SIGNALS}")

                # Only send one signal per iteration to ensure minimum 5-minute spacing between channels
                # Prioritize channels that haven't reached their limit
                signals_sent = 0
                
                # Send forex signal if needed
                if forex_count < MAX_FOREX_SIGNALS and signals_sent == 0:
                    success = await send_forex_signal()
                    if success:
                        signals_sent = 1
                    elif not success and not is_weekend():
                        print("⚠️ Could not send forex signal (all pairs may be active or waiting for interval)")
                
                # Send forex 3TP signal if needed
                if forex_3tp_count < MAX_FOREX_3TP_SIGNALS and signals_sent == 0:
                    success = await send_forex_3tp_signal()
                    if success:
                        signals_sent = 1
                    elif not success and not is_weekend():
                        print("⚠️ Could not send forex 3TP signal (all pairs may be active or waiting for interval)")
                
                # Send forex additional signal if needed
                if forex_additional_count < MAX_FOREX_ADDITIONAL_SIGNALS and signals_sent == 0:
                    success = await send_forex_additional_signal()
                    if success:
                        signals_sent = 1
                    elif not success and not is_weekend():
                        print("⚠️ Could not send forex additional signal (all pairs may be active or waiting for interval)")

                        # Send crypto signal to Lingrid if needed
                if crypto_lingrid_count < MAX_CRYPTO_SIGNALS_LINGRID and signals_sent == 0:
                    success = await send_crypto_signal("lingrid")
                    if success:
                        signals_sent = 1
                    elif not success:
                        print("⚠️ Could not send crypto signal to Lingrid (all pairs may be active or waiting for interval)")

                        # Send crypto signal to GainMuse if needed
                if crypto_gainmuse_count < MAX_CRYPTO_SIGNALS_GAINMUSE and signals_sent == 0:
                    success = await send_crypto_signal("gainmuse")
                    if success:
                        signals_sent = 1
                    elif not success:
                        print("⚠️ Could not send crypto signal to GainMuse (all pairs may be active or waiting for interval)")

                        # Send gold signal if needed (and under limit)
                if gold_count < MAX_GOLD_SIGNALS and signals_sent == 0:
                    success, reason, details = await send_gold_signal(return_reason=True)
                    if success:
                        signals_sent = 1
                    else:
                        reason_str = reason.value
                        print(f"⚠️ [AUTO] Could not send gold signal: {reason_str}")
                        if reason == SignalRejectReason.THROTTLE_MIN_INTERVAL:
                            wait_mins = details.get("throttle_check", {}).get("remaining_minutes", 0)
                            print(f"   → Throttle: Wait {wait_mins:.1f} more minutes")
                        elif reason == SignalRejectReason.THROTTLE_CHANNEL_INTERVAL:
                            wait_hours = details.get("throttle_check", {}).get("remaining_hours", 0)
                            print(f"   → Throttle: Wait {wait_hours:.2f} more hours")
                        elif reason == SignalRejectReason.RULE_36H:
                            wait_hours = details.get("pair_36h_check", {}).get("remaining_hours", 0)
                            print(f"   → 36h rule: Wait {wait_hours:.2f} more hours")
                        elif reason == SignalRejectReason.PRICE_UNAVAILABLE or reason == SignalRejectReason.GENERATION_FAILED:
                            print(f"   → Price/generation issue - check cTrader connection and symbol resolution")
                        else:
                            print(f"   → Full details: {json.dumps(details, indent=2, default=str)}")

                        # Send index signal if needed (and under limit)
                if index_count < MAX_INDEX_SIGNALS and signals_sent == 0:
                    success = await send_index_signal()
                    if success:
                        signals_sent = 1
                    elif not success and not is_weekend():
                        print("⚠️ Could not send index signal (all pairs may be active, used in other channels, or waiting for interval)")

                if signals_sent == 0:
                    # No signal sent - might be waiting for interval or all limits reached
                    print("⏸️ No signal sent this iteration (checking conditions...)")

                    # TP/SL monitoring disabled - bot should not calculate profits or send TP hit notifications
                    # await check_and_notify_tp_hits()  # DISABLED
                
                # Check if all signals sent for today
                    # Note: Index signals are optional (no strict limit), so we don't include them in the "all done" check
                if (forex_count >= MAX_FOREX_SIGNALS and 
                    forex_3tp_count >= MAX_FOREX_3TP_SIGNALS and 
                    forex_additional_count >= MAX_FOREX_ADDITIONAL_SIGNALS and
                    crypto_lingrid_count >= MAX_CRYPTO_SIGNALS_LINGRID and
                    crypto_gainmuse_count >= MAX_CRYPTO_SIGNALS_GAINMUSE and
                    gold_count >= MAX_GOLD_SIGNALS):
                    print("✅ All signals sent for today. Waiting until tomorrow...")
                    # Wait until next day
                    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                    tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
                    wait_seconds = (tomorrow - datetime.now(timezone.utc)).total_seconds()
                    print(f"⏰ Waiting {wait_seconds/3600:.1f} hours until tomorrow...")
                    await asyncio.sleep(wait_seconds)
                else:
                    # Check frequently (every 1-2 minutes) to see if we can send signals
                    # Timing rules (2h same channel, 5min different channels) are enforced in can_send_signal_now()
                    check_interval = random.randint(60, 120)  # 1-2 minutes
                    print(f"⏰ Checking again in {check_interval} seconds...")
                    await asyncio.sleep(check_interval)
                
                # Check if it's time for daily summary (14:30 GMT)
                now = datetime.now(timezone.utc)
                if now.hour == 14 and now.minute == 30:
                    await send_daily_summary()
                
                # Check if it's Friday for weekly summary (14:30 GMT)
                if now.weekday() == 4 and now.hour == 14 and now.minute == 30:  # Friday = 4
                    await send_weekly_summary()
                
            except Exception as e:
                print(f"❌ Error in automatic loop: {e}")
                print("⏳ Waiting 5 minutes before retry...")
                await asyncio.sleep(300)
    
    loop.run_until_complete(async_loop())


def main():
    """Main function to run the bot"""
    print("🚀 Starting Working Combined Trading Signals Bot...")
    print("=" * 60)
    print("📱 Interactive features: /start command with buttons")
    print("🤖 Automatic features: Signal generation every 3-5 hours")
    print("⚠️ TP/SL Monitoring: DISABLED - no profit calculations or notifications")
    print("📁 Channel Results: Separate files for each channel")
    print("📊 Daily summaries: 14:30 GMT")
    print("📈 Weekly summaries: Friday 14:30 GMT")
    print("🔐 Authorized users:", ALLOWED_USERS)
    print("📊 Signal limits: 5 forex per channel, 5 crypto per channel")
    print("📅 Forex signals: No signals on weekends")
    print("=" * 60)
    
    # Create application for interactive features FIRST
    # This must be done before starting any threads to avoid event loop conflicts
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add interactive handlers
    async def debug_env_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /debug_env command - show environment configuration"""
        user_id = update.effective_user.id
        
        if not is_authorized(user_id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        try:
            import os
            from env_loader import CRITICAL_CTRADER_KEYS
            
            message = "🔍 Environment Configuration Diagnostic\n\n"
            message += "Critical CTRADER keys:\n"
            
            for key in CRITICAL_CTRADER_KEYS:
                value = os.getenv(key)
                is_set = value is not None and value.strip() != ''
                status = "✅" if is_set else "❌"
                
                if key in ['CTRADER_CLIENT_ID', 'CTRADER_CLIENT_SECRET', 'CTRADER_ACCESS_TOKEN', 'CTRADER_REFRESH_TOKEN']:
                    preview = value[:8] + "..." if value and len(value) > 8 else (value or "(not set)")
                    message += f"{status} {key}: {preview}\n"
                else:
                    preview_val = repr(value) if value else '(not set)'
                    message += f"{status} {key}: {preview_val}\n"
            
            # Get config and source map
            try:
                ctrader_config = Config.get_ctrader_config()
                message += "\n📊 Config source map:\n"
                for key, source in ctrader_config.source_map.items():
                    message += f"  {key}: {source}\n"
            except Exception as e:
                message += f"\n❌ Error getting config: {e}\n"
            
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("debug_gold", debug_gold_command))
    application.add_handler(CommandHandler("debug_env", debug_env_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add post_init callback to log bot info after initialization
    async def post_init(application: Application) -> None:
        """Called after bot is initialized"""
        try:
            bot_info = await application.bot.get_me()
            print(f"✅ Bot initialized: @{bot_info.username} (ID: {bot_info.id})")
        except Exception as e:
            print(f"⚠️ Could not get bot info: {e}")
    
    # Set post_init callback
    application.post_init = post_init
    
    # Start automatic signal generation in separate thread AFTER application is created
    # (Initial index signal will be sent automatically when the loop starts)
    automatic_thread = threading.Thread(target=automatic_signal_loop, daemon=True)
    automatic_thread.start()
    
    # TP/SL monitoring disabled - bot should not calculate profits or send TP hit notifications
    # tp_check_thread = threading.Thread(target=hourly_tp_check_loop, daemon=True)
    # tp_check_thread.start()
    
    print("✅ Working combined bot started successfully!")
    print("📱 Send /start to your bot to see the control panel")
    print("🤖 Automatic signal generation is running in background")
    print("⚠️ TP/SL monitoring disabled - no profit calculations or notifications")
    print("🔄 Starting polling...")
    
    # Start the interactive bot (blocking call)
    application.run_polling(allowed_updates=None, drop_pending_updates=True)


async def self_test_ctrader_ws():
    """Self-test function for cTrader WebSocket connection
    
    Tests connection to cTrader WebSocket without starting Telegram bot.
    Uses only HARDCODED config (no .env).
    """
    print("=" * 80)
    print("[WS_TEST] cTrader WebSocket Connection Self-Test")
    print("=" * 80)
    print()
    
    try:
        # Get hardcoded config (no .env)
        from config import Config
        ctrader_config = Config.get_ctrader_config()
        
        print("[WS_TEST] Configuration:")
        print(f"  Source: {ctrader_config.source_map.get('account_id', 'UNKNOWN')}")
        print(f"  is_demo: {ctrader_config.is_demo}")
        print(f"  account_id: {ctrader_config.account_id}")
        ws_url, ws_source = ctrader_config.get_ws_url()
        print(f"  ws_url: {ws_url} (source: {ws_source})")
        print(f"  client_id: {ctrader_config.client_id[:20]}...")
        print()
        
        # Create streamer
        from ctrader_stream import CTraderStreamer
        print("[WS_TEST] Creating CTraderStreamer instance...")
        streamer = CTraderStreamer()
        print("[WS_TEST] ✅ Streamer created")
        print()
        
        # Attempt connection
        print("[WS_TEST] Attempting connection...")
        print("-" * 80)
        try:
            await streamer.start()
            print("-" * 80)
            print("[WS_TEST] ✅ SUCCESS: Connection established")
            print(f"[WS_TEST]   Endpoint: {streamer.connection_endpoint}")
            print(f"[WS_TEST]   Connected: {streamer.is_connected}")
            print()
            
            # Clean shutdown
            print("[WS_TEST] Closing connection...")
            try:
                if streamer.client:
                    streamer.client.stopService()
                if streamer.recv_task:
                    streamer.recv_task.cancel()
            except Exception as close_error:
                print(f"[WS_TEST] Warning during shutdown: {close_error}")
            
            print("[WS_TEST] ✅ Test completed successfully")
            return 0
            
        except Exception as conn_error:
            print("-" * 80)
            print(f"[WS_TEST] ❌ FAIL: Connection failed")
            print(f"[WS_TEST]   Error type: {type(conn_error).__name__}")
            print(f"[WS_TEST]   Error message: {str(conn_error)}")
            
            # Extract reason code if CTraderStreamerError
            if hasattr(conn_error, 'reason_code'):
                print(f"[WS_TEST]   Reason code: {conn_error.reason_code}")
            
            import traceback
            print(f"[WS_TEST]   Full traceback:")
            print(traceback.format_exc())
            print()
            print("[WS_TEST] ❌ Test failed")
            return 1
            
    except Exception as test_error:
        print(f"[WS_TEST] ❌ FATAL: Test setup failed: {test_error}")
        import traceback
        print(traceback.format_exc())
        return 1


async def ws_smoke_test():
    """Smoke test for WebSocket connection to cTrader (no Twisted, no protobuf)
    
    Tests only WebSocket handshake and TLS connection.
    """
    print("=" * 80)
    print("[SMOKE] WebSocket Connection Smoke Test")
    print("=" * 80)
    print()
    
    # Check dependency
    try:
        import websockets
        print(f"[SMOKE] websockets library: OK (version: {websockets.__version__ if hasattr(websockets, '__version__') else 'unknown'})")
    except ImportError:
        print("[SMOKE] ❌ websockets library not installed")
        print("[SMOKE] Install with: pip install websockets")
        return 1
    
    uri = "wss://demo.ctraderapi.com:5035"
    print(f"[SMOKE] Target: {uri}")
    print(f"[SMOKE] Test: WebSocket handshake + TLS (no protobuf)")
    print()
    
    try:
        import ssl
        
        # Create SSL context
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        print(f"[SMOKE] Connecting...")
        print(f"[SMOKE]   SSL context: default")
        print(f"[SMOKE]   Timeout: 10s")
        
        # Connect with timeout
        websocket = await asyncio.wait_for(
            websockets.connect(
                uri,
                ssl=ssl_ctx,
                open_timeout=10,
                close_timeout=5,
                ping_interval=None
            ),
            timeout=10.0
        )
        
        print(f"[SMOKE] ✅ CONNECT OK")
        print(f"[SMOKE]   Remote: {websocket.remote_address}")
        print(f"[SMOKE]   Local: {websocket.local_address}")
        print(f"[SMOKE]   Protocol: {websocket.subprotocol}")
        print()
        
        # Keep connection alive for 2 seconds
        print(f"[SMOKE] Keeping connection alive for 2 seconds...")
        await asyncio.sleep(2)
        
        # Close gracefully
        print(f"[SMOKE] Closing connection...")
        await websocket.close()
        print(f"[SMOKE] ✅ CLOSED OK")
        print()
        print("[SMOKE] ✅ Smoke test PASSED")
        print("[SMOKE]   WebSocket handshake and TLS work correctly")
        print("[SMOKE]   Issue is likely in Twisted or protobuf layer, not network/SSL")
        return 0
        
    except asyncio.TimeoutError:
        print(f"[SMOKE] ❌ FAIL: Connection timeout (10s)")
        print("[SMOKE]   Possible causes:")
        print("[SMOKE]     - Firewall blocking port 5035")
        print("[SMOKE]     - Proxy blocking WebSocket upgrade")
        print("[SMOKE]     - Network connectivity issue")
        return 1
    except ssl.SSLError as e:
        print(f"[SMOKE] ❌ FAIL: SSL Error")
        print(f"[SMOKE]   Type: {type(e).__name__}")
        print(f"[SMOKE]   Message: {str(e)}")
        if hasattr(e, 'reason'):
            print(f"[SMOKE]   Reason: {e.reason}")
        if hasattr(e, 'library'):
            print(f"[SMOKE]   Library: {e.library}")
        print("[SMOKE]   Possible causes:")
        print("[SMOKE]     - SSL/TLS handshake failed")
        print("[SMOKE]     - Certificate validation issue")
        print("[SMOKE]     - SSL inspection/proxy interfering")
        return 1
    except Exception as e:
        print(f"[SMOKE] ❌ FAIL: {type(e).__name__}")
        print(f"[SMOKE]   Message: {str(e)}")
        import traceback
        print(f"[SMOKE]   Traceback:")
        print(traceback.format_exc())
        return 1


async def self_test_gold_ws():
    """Self-test function for gold WebSocket connection (no Twisted)"""
    print("=" * 80)
    print("[WS_TEST_GOLD] cTrader Gold WebSocket Connection Test")
    print("=" * 80)
    print()
    
    try:
        # Get hardcoded config
        from config import Config
        ctrader_config = Config.get_ctrader_config()
        
        print("[WS_TEST_GOLD] Configuration:")
        print(f"  Source: {ctrader_config.source_map.get('account_id', 'UNKNOWN')}")
        print(f"  is_demo: {ctrader_config.is_demo}")
        print(f"  account_id: {ctrader_config.account_id}")
        ws_url, ws_source = ctrader_config.get_ws_url()
        print(f"  ws_url: {ws_url} (source: {ws_source})")
        print()
        
        # Create WebSocket client
        from ctrader_websocket import CTraderWebSocketClient, CTraderWebSocketError
        print("[WS_TEST_GOLD] Creating WebSocket client...")
        client = CTraderWebSocketClient(
            client_id=ctrader_config.client_id,
            client_secret=ctrader_config.client_secret,
            access_token=ctrader_config.access_token,
            account_id=ctrader_config.account_id
        )
        print("[WS_TEST_GOLD] ✅ Client created")
        print()
        
        # Test connection
        print("[WS_TEST_GOLD] Testing connection...")
        print("-" * 80)
        try:
            await client.connect()
            print("[WS_TEST_GOLD] ✅ Connection: OK")
            
            await client.authenticate()
            print("[WS_TEST_GOLD] ✅ Auth: OK")
            
            symbol_id = await client.resolve_symbol("XAUUSD")
            if symbol_id:
                print(f"[WS_TEST_GOLD] ✅ Symbol ID: {symbol_id}")
            else:
                print("[WS_TEST_GOLD] ❌ Symbol: NOT FOUND")
                return 1
            
            await client.subscribe_spots(symbol_id)
            print("[WS_TEST_GOLD] ✅ Subscription: OK")
            
            bid, ask = await client.wait_for_first_tick("XAUUSD")
            mid = (bid + ask) / 2.0
            print(f"[WS_TEST_GOLD] ✅ First tick received:")
            print(f"   Bid: {bid:.2f}")
            print(f"   Ask: {ask:.2f}")
            print(f"   Mid: {mid:.2f}")
            print("-" * 80)
            print("[WS_TEST_GOLD] ✅ Test completed successfully")
            return 0
            
        except CTraderWebSocketError as e:
            print("-" * 80)
            print(f"[WS_TEST_GOLD] ❌ FAIL: {e.reason}")
            print(f"[WS_TEST_GOLD]   Message: {e.message}")
            return 1
        except Exception as e:
            print("-" * 80)
            print(f"[WS_TEST_GOLD] ❌ FAIL: {type(e).__name__}: {e}")
            import traceback
            print(traceback.format_exc())
            return 1
        finally:
            await client.close()
            
    except Exception as test_error:
        print(f"[WS_TEST_GOLD] ❌ FATAL: {test_error}")
        import traceback
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    import sys
    
    # Check for --ws-smoke-test flag (first priority - simplest test)
    if "--ws-smoke-test" in sys.argv:
        print("Running WebSocket smoke test (no Telegram bot, no protobuf)...")
        print()
        exit_code = asyncio.run(ws_smoke_test())
        sys.exit(exit_code)
    # Check for --ws-test flag
    elif "--ws-test" in sys.argv:
        print("Running WebSocket connection test (no Telegram bot)...")
        print()
        exit_code = asyncio.run(self_test_ctrader_ws())
        sys.exit(exit_code)
    elif "--ws-test-gold" in sys.argv:
        print("Running gold WebSocket connection test (no Telegram bot)...")
        print()
        exit_code = asyncio.run(self_test_gold_ws())
        sys.exit(exit_code)
    else:
        main()
