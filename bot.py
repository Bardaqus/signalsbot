import os
import re
import time
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import InvalidToken, TelegramError
from data_router import get_price, get_candles, AssetClass, ForbiddenDataSourceError, get_data_router
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for Telegram send capability
_telegram_send_enabled = True

# Determine project root and .env path
_project_root = Path(__file__).resolve().parent
_dotenv_path = _project_root / ".env"


def load_telegram_token(dotenv_path: Optional[Path] = None) -> str:
    """
    Load and clean Telegram bot token from .env file.
    
    Args:
        dotenv_path: Path to .env file (defaults to project root/.env)
    
    Returns:
        Cleaned token string (empty string if invalid/missing)
    
    Side effects:
        - Loads .env file with override=True
        - Logs detailed diagnostics including repr() of raw/cleaned token parts
    """
    if dotenv_path is None:
        dotenv_path = _dotenv_path
    
    # Load .env file
    env_exists = dotenv_path.exists()
    logger.info(f"[TELEGRAM_TOKEN] Loading .env from: {dotenv_path} (exists={env_exists})")
    logger.info(f"[TELEGRAM_TOKEN] Reading key: TELEGRAM_BOT_TOKEN")
    
    load_dotenv(dotenv_path=dotenv_path, override=True, encoding="utf-8")
    
    # Get raw token from ENV (STRICT: only from .env, no fallback)
    raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    # Log raw token diagnostics (safe: only first/last chars with repr)
    raw_len = len(raw_token) if raw_token else 0
    raw_preview_start = repr(raw_token[:25]) if raw_token else "''"
    raw_preview_end = repr(raw_token[-10:]) if raw_token and len(raw_token) > 10 else "''"
    
    logger.info(f"[TELEGRAM_TOKEN] Raw token from ENV:")
    logger.info(f"   RAW_LEN={raw_len}")
    logger.info(f"   RAW_START={raw_preview_start}")
    logger.info(f"   RAW_END={raw_preview_end}")
    
    if not raw_token:
        logger.error("[TELEGRAM_TOKEN] ❌ Token is empty or not set in ENV")
        logger.error("[TELEGRAM_TOKEN] Set TELEGRAM_BOT_TOKEN in .env file")
        return ""
    
    # Clean token: remove BOM, CR, quotes, whitespace, comments
    cleaned = raw_token
    
    # Remove BOM (UTF-8 BOM: \ufeff)
    cleaned = cleaned.replace("\ufeff", "")
    
    # Remove carriage returns (CR)
    cleaned = cleaned.replace("\r", "")
    
    # Strip whitespace
    cleaned = cleaned.strip()
    
    # Remove quotes (single and double)
    cleaned = cleaned.strip('"').strip("'")
    
    # Remove comments (if token contains " #", "\t#", or " ;")
    if " #" in cleaned:
        cleaned = cleaned.split(" #")[0]
    if "\t#" in cleaned:
        cleaned = cleaned.split("\t#")[0]
    if " ;" in cleaned:
        cleaned = cleaned.split(" ;")[0]
    
    # Final strip after comment removal
    cleaned = cleaned.strip()
    
    # Log cleaned token diagnostics
    cleaned_len = len(cleaned) if cleaned else 0
    cleaned_preview_start = repr(cleaned[:25]) if cleaned else "''"
    cleaned_preview_end = repr(cleaned[-10:]) if cleaned and len(cleaned) > 10 else "''"
    
    logger.info(f"[TELEGRAM_TOKEN] Cleaned token:")
    logger.info(f"   CLEANED_LEN={cleaned_len}")
    logger.info(f"   CLEANED_START={cleaned_preview_start}")
    logger.info(f"   CLEANED_END={cleaned_preview_end}")
    
    # Validate token format: digits:alphanumeric_underscore_dash (min 30 chars after colon)
    token_pattern = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")
    
    if not cleaned:
        logger.error("[TELEGRAM_TOKEN] ❌ Token is empty after cleaning")
        return ""
    
    if not token_pattern.match(cleaned):
        logger.error("[TELEGRAM_TOKEN] ❌ Token format is invalid (does not match pattern)")
        logger.error("[TELEGRAM_TOKEN] Expected format: digits:alphanumeric_underscore_dash (min 30 chars after colon)")
        logger.error(f"[TELEGRAM_TOKEN] Actual cleaned token (first 30 chars): {repr(cleaned[:30])}")
        return ""
    
    # Safe logging: show length and preview (first 6 + last 4 chars)
    token_preview = f"{cleaned[:6]}...{cleaned[-4:]}" if cleaned_len > 10 else "***"
    
    logger.info(f"[TELEGRAM_TOKEN] ✅ Token loaded and validated successfully:")
    logger.info(f"   DOTENV_PATH={dotenv_path}")
    logger.info(f"   KEY=TELEGRAM_BOT_TOKEN")
    logger.info(f"   TOKEN_LEN={cleaned_len}")
    logger.info(f"   TOKEN_PREVIEW={token_preview}")
    
    return cleaned


# Load Telegram token at module level
TELEGRAM_BOT_TOKEN = load_telegram_token()

# Fallback to hardcoded token if .env loading failed
if not TELEGRAM_BOT_TOKEN:
    try:
        from config_hardcoded import HARDCODED_TELEGRAM
        TELEGRAM_BOT_TOKEN = HARDCODED_TELEGRAM.get('bot_token', '')
        if TELEGRAM_BOT_TOKEN:
            logger.warning("[TELEGRAM_TOKEN] ⚠️ Using hardcoded token from config_hardcoded.py (fallback)")
            logger.info(f"[TELEGRAM_TOKEN] Token preview: {TELEGRAM_BOT_TOKEN[:6]}...{TELEGRAM_BOT_TOKEN[-4:]}")
    except Exception as e:
        logger.error(f"[TELEGRAM_TOKEN] ❌ Failed to load token from .env and fallback: {e}")
        TELEGRAM_BOT_TOKEN = ""

# Load channel ID (with fallback)
try:
    from config_hardcoded import get_hardcoded_config
    _hardcoded_config = get_hardcoded_config()
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", _hardcoded_config.telegram_channel_id)
except ImportError:
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003118256304")

# Global Twelve Data client state (FOREX data source)
_twelve_data_client = None


async def safe_send_message(bot: Optional[Bot], chat_id: str, text: str, disable_web_page_preview: bool = True, parse_mode: Optional[str] = None) -> bool:
    """
    Safely send Telegram message with error handling.
    
    Args:
        bot: Telegram Bot instance
        chat_id: Chat/channel ID
        text: Message text
        disable_web_page_preview: Disable web page preview
        parse_mode: Optional parse mode (e.g., 'Markdown')
    
    Returns:
        True if sent successfully, False otherwise
    
    Side effects:
        - Sets _telegram_send_enabled=False on InvalidToken (one-time)
        - Logs errors but doesn't raise exceptions
    """
    global _telegram_send_enabled
    
    if bot is None:
        logger.debug("[TELEGRAM_SEND] Skipping send (bot is None)")
        return False
    
    if not _telegram_send_enabled:
        logger.debug("[TELEGRAM_SEND] Skipping send (send disabled)")
        return False
    
    try:
        kwargs = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview
        }
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        
        logger.info(f"[TELEGRAM_SEND] Sending message to chat_id={chat_id}, text_length={len(text)}")
        result = await bot.send_message(**kwargs)
        logger.info(f"[TELEGRAM_SEND] ✅ Message sent successfully to chat_id={chat_id}, message_id={result.message_id}")
        return True
    except InvalidToken as e:
        logger.error(f"[TELEGRAM_SEND] ❌ InvalidToken error: {e}")
        logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
        logger.error("[TELEGRAM_SEND] Disabling Telegram send for remainder of session")
        _telegram_send_enabled = False
        return False
    except TelegramError as e:
        logger.error(f"[TELEGRAM_SEND] ❌ Telegram error: {type(e).__name__}: {e}")
        logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
        logger.error(f"[TELEGRAM_SEND] Message preview: {text[:100]}...")
        return False
    except Exception as e:
        logger.error(f"[TELEGRAM_SEND] ❌ Unexpected error: {type(e).__name__}: {e}")
        logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
        import traceback
        logger.error(f"[TELEGRAM_SEND] Traceback: {traceback.format_exc()}")
        return False


async def create_telegram_bot_with_check(token: Optional[str] = None) -> Optional[Bot]:
    """
    Create Telegram Bot instance and verify token validity via getMe.
    
    Args:
        token: Bot token (defaults to TELEGRAM_BOT_TOKEN)
    
    Returns:
        Bot instance if valid, None otherwise
    
    Side effects:
        - Sets _telegram_send_enabled=False if token invalid
        - Logs bot info on success (@username and id)
    """
    global _telegram_send_enabled
    
    if token is None:
        token = TELEGRAM_BOT_TOKEN
    
    if not token:
        logger.error("[TELEGRAM_BOT] ❌ No token provided")
        logger.error("[TELEGRAM_BOT] Telegram disabled: invalid/missing token")
        _telegram_send_enabled = False
        return None
    
    try:
        bot = Bot(token=token)
        
        # Self-check: verify token by calling getMe
        try:
            me = await bot.get_me()
            logger.info(f"[TELEGRAM_BOT] ✅ Telegram OK: @{me.username} (id={me.id})")
            _telegram_send_enabled = True
            return bot
        except InvalidToken as e:
            logger.error(f"[TELEGRAM_BOT] ❌ Invalid TELEGRAM_BOT_TOKEN (getMe failed): {e!r}")
            logger.error("[TELEGRAM_BOT] Telegram disabled: getMe failed")
            _telegram_send_enabled = False
            return None
        except Exception as e:
            logger.error(f"[TELEGRAM_BOT] ❌ Telegram getMe failed: {type(e).__name__}: {e!r}")
            logger.error("[TELEGRAM_BOT] Telegram disabled: getMe failed")
            _telegram_send_enabled = False
            return None
            
    except Exception as e:
        logger.error(f"[TELEGRAM_BOT] ❌ Error creating Bot instance: {type(e).__name__}: {e!r}")
        logger.error("[TELEGRAM_BOT] Telegram disabled: bot creation failed")
        _telegram_send_enabled = False
        return None


# Forex pairs (without .FOREX suffix - will be handled by router)
# NOTE: XAUUSD is GOLD (Yahoo Finance), NOT FOREX - removed from this list
DEFAULT_PAIRS = [
    "EURUSD",
    "GBPUSD", 
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "GBPCAD",
    "GBPNZD",
]

# Crypto pairs (for crypto channels)
CRYPTO_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOTUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "MATICUSDT",
]

# Index pairs (for index channels)
INDEX_PAIRS = [
    "BRENT",
    "USOIL",
]

SIGNALS_FILE = "active_signals.json"
PERFORMANCE_FILE = "performance.json"
MAX_SIGNALS_PER_DAY = 5
PERFORMANCE_USER_ID = 615348532  # Telegram user ID for performance reports

# Channel definitions
CHANNEL_DEGRAM = "-1001220540048"  # PREMIUM Signals DeGRAM (Forex)
CHANNEL_LINGRID_FOREX = "-1001286609636"  # Lingrid private signals (Forex)
CHANNEL_GAINMUSE_CRYPTO = "-1001411205299"  # GainMuse Crypto Signals / Lingrid Crypto signals
CHANNEL_LINGRID_INDEXES = "-1001247341118"  # Lingrid private Indexes
CHANNEL_GOLD_PRIVATE = "-1003506500177"  # GOLD Private
CHANNEL_DEGRAM_INDEX = "-1001453338906"  # DeGRAM index

# Signal limits per channel per day
MAX_GOLD_SIGNALS = 3  # Updated to 3 per user request
MAX_FOREX_SIGNALS_PER_CHANNEL = 5  # Per Degram and Lingrid Forex
MAX_GAINMUSE_CRYPTO_SIGNALS = 5
MAX_INDEX_SIGNALS = 5
MAX_DEGRAM_INDEX_SIGNALS = 5

# Time constraints (in seconds)
MIN_TIME_BETWEEN_SIGNALS = 5 * 60  # 5 minutes between any signals
MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN = 150 * 60  # 2.5 hours (150 minutes) minimum between signals in same channel
MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MAX = 180 * 60  # 3 hours (180 minutes) maximum between signals in same channel
MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS = 24 * 60 * 60  # 24 hours between same pair+direction in same channel

# Files for tracking signal times
LAST_SIGNAL_TIME_FILE = "last_signal_time.json"  # Global last signal time
CHANNEL_LAST_SIGNAL_FILE = "channel_last_signal_time.json"  # Last signal time per channel
CHANNEL_PAIR_LAST_SIGNAL_FILE = "channel_pair_last_signal_time.json"  # Last signal time per pair per channel
CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE = "channel_pair_direction_last_signal_time.json"  # Last signal time per pair+direction per channel


def format_price(pair: str, price: float) -> str:
    # JPY pairs often quoted with 3 decimals; XAUUSD with 2 decimals; others 5
    if pair.endswith("JPY.FOREX"):
        return f"{price:,.3f}"
    elif pair == "XAUUSD.FOREX":
        return f"{price:,.2f}"
    return f"{price:,.5f}"


def fetch_realtime_price(symbol: str) -> Tuple[Optional[float], Dict]:
    """
    Get real-time price using data router (strict source policy)
    
    Returns:
        Tuple of (price: float or None, data_dict)
        If price is None, data_dict contains "reason" field
    
    Raises:
        ForbiddenDataSourceError: If attempting to use forbidden source
    """
    # Remove .FOREX suffix if present (legacy format)
    clean_symbol = symbol.replace(".FOREX", "")
    
    try:
        price, reason, source = get_price(clean_symbol)
        
        # Return in format expected by existing code
        result_data = {
            "close": price if price else None,
            "timestamp": int(time.time()),
            "source": source,
            "reason": reason if price is None else None
        }
        
        return price, result_data
    except ForbiddenDataSourceError as e:
        print(f"❌ [FORBIDDEN] {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching price for {clean_symbol}: {e}")
        return None, {"close": None, "timestamp": int(time.time()), "source": "ERROR", "reason": str(e)}


def fetch_intraday_bars(symbol: str, interval: str = "1m", limit: int = 120) -> List[Dict]:
    """
    Get intraday bars using data router (strict source policy)
    
    NOTE: Currently candles are not fully implemented in router.
    For now, this function will raise an error to prevent using forbidden sources.
    
    Raises:
        ForbiddenDataSourceError: If attempting to use forbidden source (EODHD, etc.)
        NotImplementedError: If candles not available for this asset class
    """
    # Remove .FOREX suffix if present
    clean_symbol = symbol.replace(".FOREX", "")
    
    # Check if this is a FOREX symbol trying to use forbidden intraday endpoint
    if symbol.endswith(".FOREX") or clean_symbol in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "GBPCAD", "GBPNZD"]:
        raise ForbiddenDataSourceError(
            f"FOREX symbol {clean_symbol} cannot use intraday endpoints. "
            f"Use Twelve Data API for candles. "
            f"EODHD and other HTTP intraday endpoints are FORBIDDEN for FOREX."
        )
    
    # Try to get candles from router
    candles, reason, source = get_candles(clean_symbol, interval, limit)
    
    if candles is None:
        raise NotImplementedError(
            f"Candles not available for {clean_symbol} from {source}. "
            f"Reason: {reason}. "
            f"FOREX candles must come from Twelve Data, GOLD/INDEX from Yahoo Finance."
        )
    
    return candles


def to_float_safe(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def simple_sma(values: List[float], window: int) -> float:
    if len(values) < window or window <= 0:
        return float("nan")
    return sum(values[-window:]) / window


def calculate_atr_proxy(bars: List[Dict], last_price: float) -> float:
    """Calculate ATR-like proxy for stop loss and take profit calculation"""
    ranges = []
    for b in bars[-14:]:
        h = to_float_safe(b.get("high"))
        l = to_float_safe(b.get("low"))
        if h is None and l is None:
            ranges.append(0.0)
            continue
        if h is None:
            h = to_float_safe(b.get("close")) or last_price
        if l is None:
            l = to_float_safe(b.get("close")) or last_price
        ranges.append(abs(h - l))
    return sum(ranges) / len(ranges) if ranges else 0.0


def generate_signal_from_bars(bars: List[Dict], symbol: str = "") -> Tuple[str, Dict[str, float]]:
    closes: List[float] = []
    for b in bars:
        c = to_float_safe(b.get("close"))
        if c is not None:
            closes.append(c)
    if len(closes) < 5:  # Very low minimum requirement
        return "NO_SIGNAL", {}
    
    last = closes[-1]
    
    # Very simple and sensitive signal generation
    # Use just 3 and 7 period SMAs for more signals
    sma_fast = simple_sma(closes, 3)   # Very fast SMA
    sma_slow = simple_sma(closes, 7)   # Fast SMA
    
    if not all(map(lambda x: x == x, [sma_fast, sma_slow, last])):  # check for NaN
        return "NO_SIGNAL", {}

    # Calculate previous SMAs for crossover detection
    prev_fast = simple_sma(closes[:-1], 3) if len(closes) > 3 else sma_fast
    prev_slow = simple_sma(closes[:-1], 7) if len(closes) > 7 else sma_slow

    signal = "NO_SIGNAL"
    
    # Very sensitive crossover conditions
    if prev_fast <= prev_slow and sma_fast > sma_slow:
        signal = "BUY"
    elif prev_fast >= prev_slow and sma_fast < sma_slow:
        signal = "SELL"
    
    # Even more sensitive momentum conditions
    elif sma_fast > sma_slow and last > sma_fast:
        signal = "BUY"
    elif sma_fast < sma_slow and last < sma_fast:
        signal = "SELL"
    
    # Price momentum conditions
    elif len(closes) >= 3:
        recent_change = (last - closes[-3]) / closes[-3]
        if recent_change > 0.0001:  # 0.01% upward momentum
            signal = "BUY"
        elif recent_change < -0.0001:  # 0.01% downward momentum
            signal = "SELL"

    if signal == "NO_SIGNAL":
        return signal, {}

    # Use different TP/SL logic for XAUUSD vs forex pairs
    if symbol == "XAUUSD.FOREX":
        # XAUUSD: 3-5% profit target, same for SL
        profit_pct = 0.04  # 4% average (between 3-5%)
        sl_pct = 0.04  # 4% SL (same as TP)
        
        if signal == "BUY":
            entry = last
            sl = entry * (1 - sl_pct)  # 4% below entry
            tp = entry * (1 + profit_pct)  # 4% above entry
        else:  # SELL
            entry = last
            sl = entry * (1 + sl_pct)  # 4% above entry
            tp = entry * (1 - profit_pct)  # 4% below entry
    else:
        # Forex pairs: fixed pip distances (doubled) with 2 TPs
        sl_pips = 192  # Average SL distance (doubled from 96)
        tp1_pips = 103  # First TP distance (original)
        tp2_pips = 206  # Second TP distance (doubled)
        
        # Adjust for JPY pairs (3 decimal places) - 2x bigger range
        if symbol.endswith("JPY.FOREX"):
            sl_distance = (sl_pips * 2) / 1000  # JPY pairs use 3 decimals, 2x bigger range
            tp1_distance = (tp1_pips * 2) / 1000
            tp2_distance = (tp2_pips * 2) / 1000
        else:
            sl_distance = sl_pips / 10000  # Other pairs use 5 decimals
            tp1_distance = tp1_pips / 10000
            tp2_distance = tp2_pips / 10000
        
        if signal == "BUY":
            entry = last
            sl = entry - sl_distance
            tp1 = entry + tp1_distance
            tp2 = entry + tp2_distance
        else:  # SELL
            entry = last
            sl = entry + sl_distance
            tp1 = entry - tp1_distance
            tp2 = entry - tp2_distance

    return signal, {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
    }


def load_active_signals() -> List[Dict]:
    """Load active signals from file"""
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_active_signals(signals: List[Dict]) -> None:
    """Save active signals to file"""
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(signals, f, indent=2)
    except Exception:
        pass


def normalize_timestamp(value: Any, field_name: str = "timestamp") -> float:
    """
    Normalize timestamp value to float (Unix timestamp)
    
    Handles various input types:
    - None -> 0.0
    - str -> try to parse as float or ISO datetime
    - int/float -> convert to float
    - other -> log warning and return 0.0
    
    Args:
        value: Timestamp value (can be any type)
        field_name: Field name for logging purposes
    
    Returns:
        float: Unix timestamp as float
    """
    if value is None:
        return 0.0
    
    if isinstance(value, (int, float)):
        result = float(value)
        if result < 0:
            print(f"[NORMALIZE_TIMESTAMP] ⚠️ {field_name}: Negative timestamp {result}, using 0.0")
            return 0.0
        return result
    
    if isinstance(value, str):
        # Try to parse as float first (most common case)
        try:
            result = float(value)
            if result < 0:
                print(f"[NORMALIZE_TIMESTAMP] ⚠️ {field_name}: Negative timestamp {result}, using 0.0")
                return 0.0
            print(f"[NORMALIZE_TIMESTAMP] ✅ {field_name}: Converted string '{value}' to float {result}")
            return result
        except ValueError:
            pass
        
        # Try to parse as ISO datetime string
        try:
            from dateutil import parser as date_parser
            dt = date_parser.isoparse(value)
            result = dt.timestamp()
            print(f"[NORMALIZE_TIMESTAMP] ✅ {field_name}: Converted ISO datetime '{value}' to timestamp {result}")
            return result
        except (ValueError, ImportError):
            try:
                # Fallback: try datetime.fromisoformat (Python 3.7+)
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                result = dt.timestamp()
                print(f"[NORMALIZE_TIMESTAMP] ✅ {field_name}: Converted ISO datetime '{value}' to timestamp {result}")
                return result
            except (ValueError, AttributeError):
                pass
        
        # If all parsing fails, log and return 0.0
        print(f"[NORMALIZE_TIMESTAMP] ⚠️ {field_name}: Cannot parse string '{value}', using 0.0")
        return 0.0
    
    # Unknown type
    print(f"[NORMALIZE_TIMESTAMP] ⚠️ {field_name}: Unknown type {type(value).__name__} with value {value}, using 0.0")
    return 0.0


def load_last_signal_times() -> Dict:
    """Load last signal times from file with normalization"""
    try:
        if os.path.exists(LAST_SIGNAL_TIME_FILE):
            with open(LAST_SIGNAL_TIME_FILE, 'r') as f:
                data = json.load(f)
                
                # Log loaded data for debugging
                if "last_signal_time" in data:
                    raw_value = data["last_signal_time"]
                    print(f"[LOAD_STATE] last_signal_time: type={type(raw_value).__name__}, value={raw_value}")
                    
                    # Normalize and update
                    normalized = normalize_timestamp(raw_value, "last_signal_time")
                    if normalized != raw_value:
                        data["last_signal_time"] = normalized
                        # Auto-migrate: save normalized value back
                        try:
                            with open(LAST_SIGNAL_TIME_FILE, 'w') as wf:
                                json.dump(data, wf)
                            print(f"[LOAD_STATE] ✅ Auto-migrated last_signal_time to float format")
                        except Exception as e:
                            print(f"[LOAD_STATE] ⚠️ Failed to auto-migrate: {e}")
                
                return data
    except Exception as e:
        print(f"[LOAD_STATE] ⚠️ Error loading last_signal_times: {e}")
    return {}


def save_last_signal_time() -> None:
    """Save current time as last signal time (always as float)"""
    try:
        current_time = float(time.time())
        with open(LAST_SIGNAL_TIME_FILE, 'w') as f:
            json.dump({"last_signal_time": current_time}, f)
    except Exception as e:
        print(f"[SAVE_STATE] ⚠️ Error saving last_signal_time: {e}")


def load_channel_last_signal_times() -> Dict:
    """Load last signal times and wait times per channel from file with normalization
    
    Returns:
        Dict with structure: {channel_id: {"last_time": float, "wait_time": float}}
        Or legacy format: {channel_id: float} (for backward compatibility)
    """
    try:
        if os.path.exists(CHANNEL_LAST_SIGNAL_FILE):
            with open(CHANNEL_LAST_SIGNAL_FILE, 'r') as f:
                data = json.load(f)
                
                # Normalize all channel timestamps and migrate to new format if needed
                needs_migration = False
                for channel_id, raw_value in data.items():
                    if raw_value is None:
                        continue
                    
                    # Check if it's legacy format (just a timestamp) or new format (dict)
                    if isinstance(raw_value, dict):
                        # New format: {"last_time": timestamp, "wait_time": wait_seconds}
                        if "last_time" in raw_value:
                            normalized_time = normalize_timestamp(raw_value["last_time"], f"channel_last_signal[{channel_id}].last_time")
                            if normalized_time != raw_value["last_time"]:
                                data[channel_id]["last_time"] = normalized_time
                                needs_migration = True
                        # wait_time should already be a float, but normalize just in case
                        if "wait_time" in raw_value:
                            wait_time = raw_value["wait_time"]
                            if not isinstance(wait_time, (int, float)):
                                data[channel_id]["wait_time"] = float(wait_time) if wait_time else MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN
                                needs_migration = True
                    else:
                        # Legacy format: just a timestamp - migrate to new format
                        print(f"[LOAD_STATE] Migrating channel_last_signal[{channel_id}] from legacy format")
                        normalized_time = normalize_timestamp(raw_value, f"channel_last_signal[{channel_id}]")
                        # Generate random wait time for legacy data
                        import random
                        wait_time = random.uniform(MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN, MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MAX)
                        data[channel_id] = {
                            "last_time": normalized_time,
                            "wait_time": wait_time
                        }
                        needs_migration = True
                
                # Auto-migrate if needed
                if needs_migration:
                    try:
                        with open(CHANNEL_LAST_SIGNAL_FILE, 'w') as wf:
                            json.dump(data, wf)
                        print(f"[LOAD_STATE] ✅ Auto-migrated channel_last_signal_times to new format with wait_time")
                    except Exception as e:
                        print(f"[LOAD_STATE] ⚠️ Failed to auto-migrate: {e}")
                
                return data
    except Exception as e:
        print(f"[LOAD_STATE] ⚠️ Error loading channel_last_signal_times: {e}")
    return {}


def save_channel_last_signal_time(channel_id: str) -> None:
    """Save current time as last signal time for channel with random wait time (50-80 minutes)
    
    Saves structure: {channel_id: {"last_time": timestamp, "wait_time": random_wait_seconds}}
    """
    try:
        import random
        current_time = float(time.time())
        # Generate random wait time between 50 and 80 minutes
        wait_time = random.uniform(MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN, MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MAX)
        
        channel_times = load_channel_last_signal_times()
        channel_times[channel_id] = {
            "last_time": current_time,
            "wait_time": wait_time
        }
        
        with open(CHANNEL_LAST_SIGNAL_FILE, 'w') as f:
            json.dump(channel_times, f)
        
        wait_minutes = int(wait_time / 60)
        print(f"[SAVE_STATE] ✅ Saved channel_last_signal_time for {channel_id}: wait_time={wait_minutes} minutes")
    except Exception as e:
        print(f"[SAVE_STATE] ⚠️ Error saving channel_last_signal_time: {e}")


def load_channel_pair_direction_last_signal_times() -> Dict:
    """Load last signal times per channel+pair+direction from file with normalization
    
    Structure: {channel_id: {pair: {direction: timestamp}}}
    """
    try:
        if os.path.exists(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE):
            with open(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, 'r') as f:
                data = json.load(f)
                
                # Normalize all timestamps
                needs_migration = False
                for channel_id, pairs_dict in data.items():
                    if not isinstance(pairs_dict, dict):
                        continue
                    for pair, directions_dict in pairs_dict.items():
                        if not isinstance(directions_dict, dict):
                            continue
                        for direction, raw_value in directions_dict.items():
                            if raw_value is not None:
                                normalized = normalize_timestamp(raw_value, f"channel_pair_direction[{channel_id}][{pair}][{direction}]")
                                if normalized != raw_value:
                                    directions_dict[direction] = normalized
                                    needs_migration = True
                
                # Auto-migrate if needed
                if needs_migration:
                    try:
                        with open(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, 'w') as wf:
                            json.dump(data, wf)
                        print(f"[LOAD_STATE] ✅ Auto-migrated channel_pair_direction_last_signal_times to float format")
                    except Exception as e:
                        print(f"[LOAD_STATE] ⚠️ Failed to auto-migrate: {e}")
                
                return data
    except Exception as e:
        print(f"[LOAD_STATE] ⚠️ Error loading channel_pair_direction_last_signal_times: {e}")
    return {}


def save_channel_pair_direction_last_signal_time(channel_id: str, pair: str, direction: str) -> None:
    """Save current time as last signal time for channel+pair+direction (always as float)"""
    try:
        current_time = float(time.time())
        data = load_channel_pair_direction_last_signal_times()
        
        if channel_id not in data:
            data[channel_id] = {}
        if pair not in data[channel_id]:
            data[channel_id][pair] = {}
        
        data[channel_id][pair][direction] = current_time
        
        with open(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[SAVE_STATE] ⚠️ Error saving channel_pair_direction_last_signal_time: {e}")


def can_send_pair_direction_signal(channel_id: str, pair: str, direction: str) -> Tuple[bool, Optional[str]]:
    """Check if we can send a signal for this pair+direction in this channel (24 hour rule)
    
    Args:
        channel_id: Channel ID
        pair: Trading pair (e.g., "EURUSD", "XAUUSD")
        direction: Signal direction ("BUY" or "SELL")
    
    Returns:
        Tuple of (can_send: bool, reason: Optional[str])
    """
    current_time = time.time()
    
    # Load last signal times for this channel+pair+direction
    data = load_channel_pair_direction_last_signal_times()
    
    channel_data = data.get(channel_id, {})
    pair_data = channel_data.get(pair, {})
    last_time_raw = pair_data.get(direction, 0)
    last_time = normalize_timestamp(last_time_raw, f"channel_pair_direction[{channel_id}][{pair}][{direction}]")
    
    if last_time > 0:
        time_since_last = current_time - last_time
        if time_since_last < MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS:
            remaining_hours = (MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS - time_since_last) / 3600
            return False, f"Pair {pair} {direction} already sent to this channel {remaining_hours:.1f}h ago (24h rule)"
    
    return True, None


def can_send_signal(channel_id: str) -> Tuple[bool, Optional[str]]:
    """Check if we can send a signal (time constraints)
    
    Uses random wait time (50-80 minutes) per channel that was saved when last signal was sent.
    """
    current_time = time.time()
    
    # Check global time constraint (5 minutes)
    last_signal_times = load_last_signal_times()
    last_global_time_raw = last_signal_times.get("last_signal_time", 0)
    last_global_time = normalize_timestamp(last_global_time_raw, "last_global_time")
    
    if current_time - last_global_time < MIN_TIME_BETWEEN_SIGNALS:
        remaining = MIN_TIME_BETWEEN_SIGNALS - (current_time - last_global_time)
        return False, f"Wait {int(remaining/60)} minutes (global constraint)"
    
    # Check channel-specific time constraint (random 50-80 minutes)
    channel_times = load_channel_last_signal_times()
    channel_data = channel_times.get(channel_id)
    
    if channel_data is None:
        # No previous signal for this channel - allow sending
        return True, None
    
    # Handle both new format (dict) and legacy format (float)
    if isinstance(channel_data, dict):
        # New format: {"last_time": timestamp, "wait_time": wait_seconds}
        last_channel_time_raw = channel_data.get("last_time", 0)
        wait_time = channel_data.get("wait_time", MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN)
    else:
        # Legacy format: just a timestamp - use minimum wait time
        last_channel_time_raw = channel_data
        wait_time = MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN
    
    last_channel_time = normalize_timestamp(last_channel_time_raw, f"last_channel_time[{channel_id}]")
    
    if last_channel_time > 0:
        time_since_last = current_time - last_channel_time
        if time_since_last < wait_time:
            remaining = wait_time - time_since_last
            remaining_minutes = int(remaining / 60)
            return False, f"Wait {remaining_minutes} minutes (channel constraint: {int(wait_time/60)} min interval)"
    
    return True, None


def get_today_channel_signals_count(channel_id: str) -> int:
    """Count ALL signals sent to channel today (including closed/completed signals)
    
    This ensures that if bot is restarted, it won't send more signals than daily limit.
    
    Args:
        channel_id: Channel ID to count signals for
    
    Returns:
        Total count of signals sent to this channel today (regardless of status)
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    
    # Count ALL signals for this channel today (including closed/completed)
    # This is important: if bot restarts, it should know how many signals were already sent
    count = len([s for s in active_signals 
                 if s.get("channel_id") == channel_id and s.get("date") == today])
    
    # Log for debugging
    if count > 0:
        # Count by status for detailed logging
        active_count = len([s for s in active_signals 
                           if s.get("channel_id") == channel_id 
                           and s.get("date") == today 
                           and s.get("status") == "active"])
        closed_count = count - active_count
        logger.info(f"[SIGNAL_COUNT] Channel {channel_id}: {count} total signals today ({active_count} active, {closed_count} closed)")
    
    return count


def get_today_signals_count() -> int:
    """Count signals generated today"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    return sum(1 for s in active_signals if s.get("date") == today)


def get_active_pairs() -> List[str]:
    """Get pairs that currently have active signals"""
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    active_pairs = []
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            active_pairs.append(signal.get("symbol"))
    
    return active_pairs


def get_available_pairs(all_pairs: List[str], channel_id: Optional[str] = None) -> List[str]:
    """Get pairs that don't have active signals for the specified channel.
    
    Args:
        all_pairs: List of all pairs to check
        channel_id: If provided, only check for active signals in this channel.
                   If None, check globally (backward compatibility)
    """
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Get active pairs for this channel (or globally if channel_id is None)
    active_pairs = []
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            signal_channel_id = signal.get("channel_id")
            # If channel_id is specified, only exclude pairs active in THIS channel
            # If channel_id is None, exclude pairs active in ANY channel (backward compatibility)
            if channel_id is None or signal_channel_id == channel_id:
                active_pairs.append(signal.get("symbol"))
    
    return [pair for pair in all_pairs if pair not in active_pairs]


def add_signal(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float = None, tp3: float = None, channel_id: str = None) -> None:
    """Add new signal to tracking with 2 or 3 TPs"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if tp3 is not None:
        # Signals with 3 TPs (Forex, Crypto, Index, Gold)
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "date": today,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active",  # active, hit_sl, hit_tp1, hit_tp2, hit_tp3
            "channel_id": channel_id
        }
    elif tp2 is not None:
        # Signals with 2 TPs (backward compatibility)
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "date": today,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active",  # active, hit_sl, hit_tp1, hit_tp2
            "channel_id": channel_id
        }
    else:
        # Signals with 1 TP (backward compatibility)
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp": tp1,
            "date": today,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active",  # active, hit_sl, hit_tp
            "channel_id": channel_id
        }
    active_signals = load_active_signals()
    active_signals.append(signal)
    save_active_signals(active_signals)


def load_performance_data() -> Dict:
    """Load performance tracking data"""
    try:
        if os.path.exists(PERFORMANCE_FILE):
            with open(PERFORMANCE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"completed_signals": []}


def save_performance_data(data: Dict) -> None:
    """Save performance tracking data"""
    try:
        with open(PERFORMANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def add_completed_signal(symbol: str, signal_type: str, entry: float, exit_price: float, status: str) -> None:
    """Add completed signal to performance tracking with proper units"""
    performance_data = load_performance_data()
    
    # Determine if it's crypto or forex based on symbol
    is_crypto = not symbol.endswith(".FOREX")
    
    if is_crypto:
        # Crypto signals: Calculate profit in percentage
        if signal_type == "BUY":
            profit_pct = ((exit_price - entry) / entry) * 100
        else:  # SELL
            profit_pct = ((entry - exit_price) / entry) * 100
        
        completed_signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "exit_price": exit_price,
            "profit_pct": profit_pct,
            "profit_pips": None,  # Not applicable for crypto
            "unit": "percentage",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
    else:
        # Forex signals: Calculate profit in pips
        if symbol.endswith("JPY.FOREX"):
            # JPY pairs use 3 decimal places, so multiply by 1000
            multiplier = 1000
        else:
            # Other pairs use 5 decimal places, so multiply by 10000
            multiplier = 10000
        
        if signal_type == "BUY":
            profit_pips = (exit_price - entry) * multiplier
        else:  # SELL
            profit_pips = (entry - exit_price) * multiplier
        
        # Also calculate percentage for consistency
        if signal_type == "BUY":
            profit_pct = ((exit_price - entry) / entry) * 100
        else:  # SELL
            profit_pct = ((entry - exit_price) / entry) * 100
        
        completed_signal = {
            "symbol": symbol.replace(".FOREX", ""),  # Remove .FOREX for display
            "type": signal_type,
            "entry": entry,
            "exit_price": exit_price,
            "profit_pct": profit_pct,
            "profit_pips": profit_pips,
            "unit": "pips",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
    
    performance_data["completed_signals"].append(completed_signal)
    save_performance_data(performance_data)


async def check_signal_hits() -> List[Dict]:
    """Check for SL/TP hits and return profit messages"""
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    profit_messages = []
    updated_signals = []
    
    for signal in active_signals:
        if signal.get("status") != "active":
            updated_signals.append(signal)
            continue
            
        try:
            # Get price using DataRouter (async version)
            clean_symbol = signal["symbol"].replace(".FOREX", "")
            
            data_router = get_data_router()
            if data_router:
                price, reason, source = await data_router.get_price_async(clean_symbol)
            else:
                # Fallback to sync version (creates new loop, but works)
                price, reason, source = get_price(clean_symbol)
            
            # Build price_data dict for compatibility
            price_data = {
                "close": price if price else None,
                "timestamp": int(time.time()),
                "source": source,
                "reason": reason if price is None else None
            }
            current_price = price
            
            # CRITICAL: Skip if price is None (source unavailable)
            if current_price is None:
                reason_str = price_data.get("reason", "unknown")
                source_str = price_data.get("source", "unknown")
                print(f"⏸️ Skipping TP/SL check for {signal['symbol']}: price unavailable (source={source_str}, reason={reason_str})")
                # Keep signal active - will check again next time
                updated_signals.append(signal)
                continue
            
            signal_type = signal["type"]
            entry = signal["entry"]
            sl = signal["sl"]
            
            hit_sl = False
            hit_tp = None
            
            # Check for 3 TPs (forex, crypto, index, gold signals)
            if "tp1" in signal and "tp2" in signal and "tp3" in signal:
                tp1 = signal["tp1"]
                tp2 = signal["tp2"]
                tp3 = signal["tp3"]
                
                if signal_type == "BUY":
                    hit_sl = current_price <= sl
                    if current_price >= tp3:
                        hit_tp = "TP3"
                    elif current_price >= tp2:
                        hit_tp = "TP2"
                    elif current_price >= tp1:
                        hit_tp = "TP1"
                else:  # SELL
                    hit_sl = current_price >= sl
                    if current_price <= tp3:
                        hit_tp = "TP3"
                    elif current_price <= tp2:
                        hit_tp = "TP2"
                    elif current_price <= tp1:
                        hit_tp = "TP1"
            elif "tp1" in signal and "tp2" in signal:
                # 2 TPs (backward compatibility)
                tp1 = signal["tp1"]
                tp2 = signal["tp2"]
                
                if signal_type == "BUY":
                    hit_sl = current_price <= sl
                    if current_price >= tp2:
                        hit_tp = "TP2"
                    elif current_price >= tp1:
                        hit_tp = "TP1"
                else:  # SELL
                    hit_sl = current_price >= sl
                    if current_price <= tp2:
                        hit_tp = "TP2"
                    elif current_price <= tp1:
                        hit_tp = "TP1"
            else:
                # Single TP (backward compatibility)
                tp = signal["tp"]
                
                if signal_type == "BUY":
                    hit_sl = current_price <= sl
                    hit_tp = "TP" if current_price >= tp else None
                else:  # SELL
                    hit_sl = current_price >= sl
                    hit_tp = "TP" if current_price <= tp else None
            
            if hit_tp:
                # Calculate profit - adjust multiplier for JPY pairs
                if signal["symbol"].endswith("JPY.FOREX"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    profit_pips = (current_price - entry) * multiplier
                else:  # SELL
                    profit_pips = (entry - current_price) * multiplier
                
                # Build original signal message for reply
                # Determine if it's crypto based on symbol (ends with USDT or doesn't end with .FOREX)
                signal_symbol = signal["symbol"]
                is_crypto_signal = signal_symbol.endswith("USDT") or (not signal_symbol.endswith(".FOREX") and not signal_symbol in ["XAUUSD", "BRENT", "USOIL"])
                
                if "tp1" in signal and "tp2" in signal and "tp3" in signal:
                    original_signal_msg = build_signal_message(signal["symbol"], signal_type, entry, sl, signal["tp1"], signal["tp2"], tp3=signal["tp3"], is_crypto=is_crypto_signal)
                elif "tp1" in signal and "tp2" in signal:
                    original_signal_msg = build_signal_message(signal["symbol"], signal_type, entry, sl, signal["tp1"], signal["tp2"], is_crypto=is_crypto_signal)
                else:
                    original_signal_msg = build_signal_message(signal["symbol"], signal_type, entry, sl, signal.get("tp", signal["tp1"]), is_crypto=is_crypto_signal)
                
                # Calculate R/R ratio
                if signal_type == "BUY":
                    risk_pips = (entry - sl) * multiplier
                    if hit_tp == "TP1":
                        reward_pips = (signal["tp1"] - entry) * multiplier
                    elif hit_tp == "TP2":
                        reward_pips = (signal["tp2"] - entry) * multiplier
                    elif hit_tp == "TP3":
                        reward_pips = (signal["tp3"] - entry) * multiplier
                    else:  # Single TP (backward compatibility)
                        reward_pips = (signal.get("tp", signal["tp1"]) - entry) * multiplier
                else:  # SELL
                    risk_pips = (sl - entry) * multiplier
                    if hit_tp == "TP1":
                        reward_pips = (entry - signal["tp1"]) * multiplier
                    elif hit_tp == "TP2":
                        reward_pips = (entry - signal["tp2"]) * multiplier
                    elif hit_tp == "TP3":
                        reward_pips = (entry - signal["tp3"]) * multiplier
                    else:  # Single TP (backward compatibility)
                        reward_pips = (entry - signal.get("tp", signal["tp1"])) * multiplier
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Create TP hit message
                if hit_tp == "TP3":
                    profit_msg = f"#{signal['symbol'].replace('.FOREX', '')}: All targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                elif hit_tp == "TP2":
                    profit_msg = f"#{signal['symbol'].replace('.FOREX', '')}: TP2 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                else:
                    profit_msg = f"#{signal['symbol'].replace('.FOREX', '')}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                profit_messages.append(profit_msg)
                
                # Add to performance tracking
                add_completed_signal(signal["symbol"], signal_type, entry, current_price, f"hit_{hit_tp.lower()}")
                
                signal["status"] = f"hit_{hit_tp.lower()}"
                signal["exit_price"] = current_price
                signal["profit_pips"] = profit_pips
                
            elif hit_sl:
                # Add to performance tracking (no message for SL hits)
                add_completed_signal(signal["symbol"], signal_type, entry, current_price, "hit_sl")
                
                signal["status"] = "hit_sl"
                signal["exit_price"] = current_price
            
            updated_signals.append(signal)
            
        except Exception as e:
            print(f"❌ Error checking signal {signal['symbol']}: {e}")
            # Keep signal active if we can't check price
            updated_signals.append(signal)
    
    save_active_signals(updated_signals)
    return profit_messages


def build_signal_message(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float = None, tp3: float = None, is_crypto: bool = False) -> str:
    """Build signal message in the requested format
    
    Args:
        symbol: Symbol name (e.g., "EURUSD", "BTCUSDT", "XAUUSD")
        signal_type: Signal direction ("BUY" or "SELL")
        entry: Entry price
        sl: Stop loss price
        tp1: Take profit 1 price
        tp2: Take profit 2 price (optional)
        tp3: Take profit 3 price (optional)
        is_crypto: Whether this is a crypto signal (adds "USE x5 margin" footer)
    """
    # Remove .FOREX suffix for display
    display_symbol = symbol.replace(".FOREX", "")
    
    # Format prices as simple numbers (no special formatting, but keep reasonable precision)
    def format_simple(price: float) -> str:
        # For JPY pairs (3 decimals), for others (5 decimals)
        if display_symbol.endswith("JPY"):
            return f"{price:.3f}".rstrip('0').rstrip('.')
        elif display_symbol == "XAUUSD":
            return f"{price:.2f}".rstrip('0').rstrip('.')
        elif is_crypto or display_symbol.endswith("USDT"):
            # Crypto pairs: more precision (6 decimals)
            return f"{price:.6f}".rstrip('0').rstrip('.')
        else:
            return f"{price:.5f}".rstrip('0').rstrip('.')
    
    # Build main message
    if tp3 is not None:
        # Signals with 3 TPs (Forex, Crypto, Index, Gold)
        msg = f"""{display_symbol} {signal_type} {format_simple(entry)}
SL {format_simple(sl)}
TP1 {format_simple(tp1)}
TP2 {format_simple(tp2)}
TP3 {format_simple(tp3)}"""
    elif tp2 is not None:
        # Signals with 2 TPs (backward compatibility)
        msg = f"""{display_symbol} {signal_type} {format_simple(entry)}
SL {format_simple(sl)}
TP1 {format_simple(tp1)}
TP2 {format_simple(tp2)}"""
    else:
        # Signals with 1 TP (backward compatibility)
        msg = f"""{display_symbol} {signal_type} {format_simple(entry)}
SL {format_simple(sl)}
TP1 {format_simple(tp1)}"""
    
    # Add "USE x5 margin" footer for crypto signals
    if is_crypto:
        msg += "\n\nUSE x5 margin"
    
    return msg


def get_performance_report(days: int = 1) -> str:
    """Generate comprehensive performance report for specified number of days"""
    performance_data = load_performance_data()
    now = datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Filter signals for the period
    recent_signals = [
        s for s in performance_data["completed_signals"]
        if s["date"] >= cutoff_date
    ]
    
    if not recent_signals:
        return f"📊 **No completed signals in the last {days} day(s)**"
    
    # Calculate statistics
    total_signals = len(recent_signals)
    profit_signals = [s for s in recent_signals if s["profit_pct"] > 0]
    loss_signals = [s for s in recent_signals if s["profit_pct"] <= 0]
    
    # Calculate totals
    total_profit_pct = sum(s["profit_pct"] for s in recent_signals)
    avg_profit_per_signal = total_profit_pct / total_signals if total_signals > 0 else 0
    
    # Calculate win rate
    win_rate = (len(profit_signals) / total_signals * 100) if total_signals > 0 else 0
    
    # Calculate average profit and loss
    avg_profit = sum(s["profit_pct"] for s in profit_signals) / len(profit_signals) if profit_signals else 0
    avg_loss = sum(s["profit_pct"] for s in loss_signals) / len(loss_signals) if loss_signals else 0
    
    # Calculate profit factor
    total_profit = sum(s["profit_pct"] for s in profit_signals)
    total_loss = abs(sum(s["profit_pct"] for s in loss_signals))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    # Build report
    period = "24h" if days == 1 else f"{days} days"
    report_lines = [
        f"📊 **Performance Report - {period}**",
        f"📅 Period: {cutoff_date} to {now.strftime('%Y-%m-%d')}",
        "",
        "📈 **SUMMARY**",
        f"Total Signals: {total_signals}",
        f"Winning Signals: {len(profit_signals)} ({win_rate:.1f}%)",
        f"Losing Signals: {len(loss_signals)} ({100-win_rate:.1f}%)",
        "",
        "💰 **PROFIT/LOSS**",
        f"Total Profit: {total_profit_pct:+.2f}%",
        f"Average per Signal: {avg_profit_per_signal:+.2f}%",
        f"Average Win: {avg_profit:+.2f}%" if profit_signals else "Average Win: N/A",
        f"Average Loss: {avg_loss:+.2f}%" if loss_signals else "Average Loss: N/A",
        f"Profit Factor: {profit_factor:.2f}" if profit_factor != float('inf') else "Profit Factor: ∞",
        ""
    ]
    
    # Add individual signal results
    if days <= 3:  # Only show individual signals for short periods
        report_lines.append("📋 **INDIVIDUAL SIGNALS**")
        for signal in sorted(recent_signals, key=lambda x: x["timestamp"], reverse=True):
            symbol = signal["symbol"]
            signal_type = signal["type"]
            profit_pct = signal["profit_pct"]
            profit_pips = signal.get("profit_pips")
            unit = signal.get("unit", "percentage")
            status = "✅" if "hit_tp" in signal["status"] else "❌"
            sign = "+" if profit_pct > 0 else ""
            
            if unit == "pips" and profit_pips is not None:
                # Forex signals: show pips
                report_lines.append(f"{status} {symbol} {signal_type}: {sign}{profit_pips:.1f} pips ({sign}{profit_pct:.2f}%)")
            else:
                # Crypto signals: show percentage
                report_lines.append(f"{status} {symbol} {signal_type}: {sign}{profit_pct:.2f}%")
        report_lines.append("")
    
    # Add daily breakdown for weekly reports
    if days >= 7:
        report_lines.append("📅 **DAILY BREAKDOWN**")
        daily_stats = {}
        for signal in recent_signals:
            date = signal["date"]
            if date not in daily_stats:
                daily_stats[date] = {"total": 0, "profit": 0, "wins": 0, "losses": 0}
            daily_stats[date]["total"] += 1
            daily_stats[date]["profit"] += signal["profit_pct"]
            if signal["profit_pct"] > 0:
                daily_stats[date]["wins"] += 1
            else:
                daily_stats[date]["losses"] += 1
        
        for date in sorted(daily_stats.keys(), reverse=True):
            stats = daily_stats[date]
            win_rate_daily = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
            report_lines.append(f"{date}: {stats['total']} signals, {win_rate_daily:.0f}% win rate, {stats['profit']:+.2f}% total")
        report_lines.append("")
    
    # Add performance rating
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
    
    report_lines.append(f"🎯 **PERFORMANCE RATING: {rating}**")
    
    return "\n".join(report_lines)


async def send_performance_report(bot: Optional[Bot], days: int = 1) -> None:
    """Send comprehensive performance report to user and channels"""
    if bot is None:
        logger.debug("[PERFORMANCE_REPORT] Bot is None, skipping report")
        return
    
    try:
        report = get_performance_report(days)
        period = "24h" if days == 1 else f"{days} days"
        
        # Send to user
        send_success = await safe_send_message(
            bot, 
            chat_id=str(PERFORMANCE_USER_ID), 
            text=report, 
            disable_web_page_preview=True,
            parse_mode='Markdown'
        )
        if send_success:
            print(f"📊 Sent {period} performance report to user {PERFORMANCE_USER_ID}")
        else:
            logger.warning(f"[PERFORMANCE_REPORT] Failed to send {period} report to user {PERFORMANCE_USER_ID}")
        
        # Send to forex channel as well
        send_success = await safe_send_message(
            bot, 
            chat_id=TELEGRAM_CHANNEL_ID, 
            text=report, 
            disable_web_page_preview=True,
            parse_mode='Markdown'
        )
        if send_success:
            print(f"📊 Sent {period} performance report to forex channel")
        else:
            logger.warning(f"[PERFORMANCE_REPORT] Failed to send {period} report to forex channel")
        
    except Exception as e:
        print(f"❌ Failed to send performance report: {e}")


async def check_and_send_reports(bot: Optional[Bot]) -> None:
    """Check if it's time to send performance reports"""
    now = datetime.now(timezone.utc)
    
    # Check if it's 14:00 GMT
    if now.hour == 14 and now.minute == 0:
        # Daily report (every day)
        await send_performance_report(bot, days=1)
        
        # Weekly report (Fridays only)
        if now.weekday() == 4:  # Friday
            await send_performance_report(bot, days=7)


async def post_signals_once(pairs: List[str]) -> None:
    print("🤖 Starting bot...")
    bot = await create_telegram_bot_with_check()
    if not bot:
        logger.error("[MAIN] ❌ Failed to create Telegram bot - continuing without Telegram send")
        logger.error("[MAIN] Bot will generate signals but not send them to Telegram")
    
    # Check if it's weekend (forex market is closed)
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    if weekday >= 5:  # Saturday (5) or Sunday (6)
        print("🏖️ Weekend detected - Forex market is closed. Skipping forex signal generation.")
        # Still check for TP hits and reports even on weekends
        await check_and_send_reports(bot)
        print("🔍 Checking for TP hits...")
        profit_messages = await check_signal_hits()
        print(f"Found {len(profit_messages)} TP hits")
        for msg in profit_messages:
            print(f"Sending TP message: {msg}")
            await safe_send_message(bot, chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
            await asyncio.sleep(0.4)
        return
    
    # Check if we're in trading hours (4 GMT - 23 GMT)
    current_hour = now.hour
    if current_hour < 4 or current_hour >= 23:
        print(f"🌙 Outside trading hours ({current_hour}:00 GMT). Market closed. Skipping forex signal generation.")
        # Still check for TP hits and reports even outside trading hours
        await check_and_send_reports(bot)
        print("🔍 Checking for TP hits...")
        profit_messages = await check_signal_hits()
        print(f"Found {len(profit_messages)} TP hits")
        for msg in profit_messages:
            print(f"Sending TP message: {msg}")
            await safe_send_message(bot, chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
            await asyncio.sleep(0.4)
        return
    
    # Check for performance reports first
    await check_and_send_reports(bot)
    
    # Then check for TP hits
    print("🔍 Checking for TP hits...")
    profit_messages = await check_signal_hits()
    print(f"Found {len(profit_messages)} TP hits")
    for msg in profit_messages:
        print(f"Sending TP message: {msg}")
        await safe_send_message(bot, chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
        await asyncio.sleep(0.4)
    
    # Generate signals for different channels
    await generate_channel_signals(bot, pairs)


async def startup_init():
    """Initialize Twelve Data client for FOREX data"""
    global _twelve_data_client
    
    print("[STARTUP] Initializing Twelve Data client for FOREX...")
    
    try:
        from twelve_data_client import TwelveDataClient
        from config_hardcoded import get_hardcoded_config
        
        config = get_hardcoded_config()
        
        def safe_preview(value: str, length: int = 6) -> str:
            if not value:
                return "(not set)"
            if len(value) <= length:
                return value[:length] + "..."
            return value[:length] + "..."
        
        print(f"[STARTUP] [TWELVE_DATA] Config loaded:")
        print(f"   api_key={safe_preview(config.twelve_data_api_key, 6)} (source={config.source_map.get('twelve_data_api_key', 'HARDCODED')})")
        print(f"   base_url={config.twelve_data_base_url}")
        print(f"   timeout={config.twelve_data_timeout}s")
        print(f"   min_interval_ms={getattr(config, 'twelve_data_min_interval_ms', 400)}ms")
        print(f"   max_retries={getattr(config, 'twelve_data_max_retries', 3)}")
        print(f"   backoff_base_ms={getattr(config, 'twelve_data_backoff_base_ms', 500)}ms")
        print(f"   backoff_max_ms={getattr(config, 'twelve_data_backoff_max_ms', 5000)}ms")
        
        # Create Twelve Data client with rate limiting configuration
        # Use inspect to filter kwargs to only supported parameters (defensive programming)
        import inspect
        client_kwargs = {
            'api_key': config.twelve_data_api_key,
            'base_url': config.twelve_data_base_url,
            'timeout': config.twelve_data_timeout,
            'min_interval_ms': getattr(config, 'twelve_data_min_interval_ms', 400),
            'max_retries': getattr(config, 'twelve_data_max_retries', 3),
            'backoff_base_ms': getattr(config, 'twelve_data_backoff_base_ms', 500),
            'backoff_max_ms': getattr(config, 'twelve_data_backoff_max_ms', 5000)
        }
        
        # Filter kwargs to only include parameters supported by TwelveDataClient.__init__
        sig = inspect.signature(TwelveDataClient.__init__)
        supported_params = set(sig.parameters.keys())
        filtered_kwargs = {k: v for k, v in client_kwargs.items() if k in supported_params}
        
        _twelve_data_client = TwelveDataClient(**filtered_kwargs)
        
        # Test connection with a simple price request
        print("[STARTUP] Testing Twelve Data connection...")
        test_price = await _twelve_data_client.get_price("EURUSD")
        if test_price:
            print(f"[STARTUP] ✅ Twelve Data connection test successful (EURUSD={test_price:.5f})")
        else:
            print("[STARTUP] ⚠️ Twelve Data connection test failed, but client initialized (will retry on demand)")
        
        # Create DataRouter with injected Twelve Data client
        from data_router import DataRouter, set_data_router
        data_router = DataRouter(twelve_data_client=_twelve_data_client)
        set_data_router(data_router)
        print("[STARTUP] ✅ DataRouter initialized with Twelve Data client")
        
        # Self-check: verify router can get price (use async version since we're in async context)
        print("[STARTUP] Self-check: testing DataRouter.get_price_async('EURUSD')...")
        try:
            check_price, check_reason, check_source = await data_router.get_price_async("EURUSD")
            if check_price:
                print(f"[STARTUP] ✅ Self-check passed: EURUSD={check_price:.5f} (source={check_source})")
            else:
                print(f"[STARTUP] ⚠️ Self-check warning: EURUSD=None (reason={check_reason}, source={check_source})")
        except Exception as e:
            print(f"[STARTUP] ⚠️ Self-check error: {type(e).__name__}: {e}")
            import traceback
            print(traceback.format_exc())
        
        print("[STARTUP] ✅ Twelve Data client initialized - FOREX signals enabled")
        return True
        
    except ImportError as e:
        print(f"[STARTUP] ❌ Failed to import twelve_data_client: {type(e).__name__}: {e}")
        print(f"[STARTUP] ⚠️ FOREX signals will be unavailable")
        _twelve_data_client = None
        return False
    except Exception as e:
        print(f"[STARTUP] ❌ Error initializing Twelve Data: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        _twelve_data_client = None
        return False


async def generate_channel_signals(bot: Optional[Bot], pairs: List[str]) -> None:
    """Generate signals for different channels with proper limits and time constraints.
    
    If bot is None, signals are still generated and logged locally, but not sent to Telegram.
    """
    if bot is None:
        logger.warning("[GENERATE_SIGNALS] Bot is None - signals will be generated and logged locally, but NOT sent to Telegram")
    
    # Check if it's weekend (Saturday or Sunday)
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
    is_weekend = weekday >= 5  # Saturday (5) or Sunday (6)
    
    if is_weekend:
        logger.info(f"[GENERATE_SIGNALS] Weekend detected (weekday={weekday}) - Forex and Index markets are closed")
    
    # Define channel configurations
    logger.info("[GENERATE_SIGNALS] Channel configuration:")
    logger.info(f"  GOLD_PRIVATE: {CHANNEL_GOLD_PRIVATE}")
    logger.info(f"  DEGRAM (Forex): {CHANNEL_DEGRAM}")
    logger.info(f"  LINGRID_FOREX: {CHANNEL_LINGRID_FOREX}")
    logger.info(f"  GAINMUSE_CRYPTO: {CHANNEL_GAINMUSE_CRYPTO}")
    logger.info(f"  LINGRID_INDEXES: {CHANNEL_LINGRID_INDEXES}")
    logger.info(f"  DEGRAM_INDEX: {CHANNEL_DEGRAM_INDEX}")
    
    # Define channel configurations
    # STRICT: Each channel type gets ONLY its designated asset class
    channel_configs = [
        {
            "name": "GOLD",
            "channel_id": CHANNEL_GOLD_PRIVATE,
            "symbols": ["XAUUSD"],  # ONLY Gold
            "max_signals": MAX_GOLD_SIGNALS,
            "has_tp2": False,
            "asset_type": "GOLD"
        },
        {
            "name": "FOREX_DEGRAM",
            "channel_id": CHANNEL_DEGRAM,
            "symbols": pairs,  # ONLY Forex pairs
            "max_signals": MAX_FOREX_SIGNALS_PER_CHANNEL,
            "has_tp2": True,
            "asset_type": "FOREX"
        },
        {
            "name": "FOREX_LINGRID",
            "channel_id": CHANNEL_LINGRID_FOREX,
            "symbols": pairs,  # ONLY Forex pairs
            "max_signals": MAX_FOREX_SIGNALS_PER_CHANNEL,
            "has_tp2": True,
            "has_tp3": False,  # Special: only 2 TPs for Lingrid forex
            "asset_type": "FOREX"
        },
        {
            "name": "GAINMUSE_CRYPTO",
            "channel_id": CHANNEL_GAINMUSE_CRYPTO,
            "symbols": CRYPTO_PAIRS,  # ONLY Crypto pairs
            "max_signals": MAX_GAINMUSE_CRYPTO_SIGNALS,
            "has_tp2": True,
            "asset_type": "CRYPTO"
        },
        {
            "name": "INDEXES_LINGRID",
            "channel_id": CHANNEL_LINGRID_INDEXES,
            "symbols": INDEX_PAIRS,  # ONLY Index pairs (BRENT, USOIL) - NO XAUUSD
            "max_signals": MAX_INDEX_SIGNALS,
            "has_tp2": True,
            "asset_type": "INDEX"
        },
        {
            "name": "INDEXES_DEGRAM",
            "channel_id": CHANNEL_DEGRAM_INDEX,
            "symbols": INDEX_PAIRS,  # ONLY Index pairs (BRENT, USOIL) - NO XAUUSD
            "max_signals": MAX_DEGRAM_INDEX_SIGNALS,
            "has_tp2": True,
            "asset_type": "INDEX"
        }
    ]
    
    for config in channel_configs:
        channel_id = config["channel_id"]
        channel_name = config["name"]
        symbols = config["symbols"]
        max_signals = config["max_signals"]
        has_tp2 = config["has_tp2"]
        asset_type = config.get("asset_type", "FOREX")
        
        # Log channel configuration for debugging
        logger.info(f"[GENERATE_SIGNALS] Processing channel: {channel_name} (ID: {channel_id}, Type: {asset_type}, Symbols: {len(symbols)} pairs)")
        
        # Skip Forex and Index channels on weekends (Saturday and Sunday)
        if is_weekend and asset_type in ["FOREX", "INDEX"]:
            print(f"🏖️ {channel_name}: Skipping signal generation - weekend (Forex/Index markets closed)")
            logger.info(f"[GENERATE_SIGNALS] {channel_name}: Skipping - weekend (asset_type={asset_type})")
            continue
        
        # Check channel limit - CRITICAL: count ALL signals sent today (including closed)
        # This prevents bot from sending more than daily limit if restarted
        today_count = get_today_channel_signals_count(channel_id)
        
        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Checking daily limit - current: {today_count}/{max_signals} signals today")
        
        if today_count >= max_signals:
            print(f"✅ {channel_name}: Daily limit reached - Already have {today_count}/{max_signals} signals today")
            logger.info(f"[GENERATE_SIGNALS] {channel_name}: Skipping - daily limit reached ({today_count}/{max_signals})")
            continue
        
        signals_needed = max_signals - today_count
        print(f"🎯 {channel_name}: Need {signals_needed} more signals (current: {today_count}/{max_signals} today)")
        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Will generate up to {signals_needed} more signals to reach daily limit of {max_signals}")
        
        # Get available pairs for this channel (check only this channel's active signals)
        available_pairs = get_available_pairs(symbols, channel_id=channel_id)
        if not available_pairs:
            print(f"⚠️ {channel_name}: No available pairs (all pairs already have active signals in this channel)")
            continue
        
        signals_generated = 0
        attempts = 0
        max_attempts = len(available_pairs) * 3
        
        while signals_generated < signals_needed and attempts < max_attempts:
            # Check time constraints
            can_send, reason = can_send_signal(channel_id)
            if not can_send:
                print(f"  ⏸️ {channel_name}: {reason}")
                await asyncio.sleep(10)  # Wait a bit before retry
                attempts += 1
                continue
            
            # Cycle through available pairs
            sym = available_pairs[attempts % len(available_pairs)]
            attempts += 1
            
            print(f"📊 {channel_name}: Analyzing {sym} (attempt {attempts})...")
            try:
                # Get real-time price using data router
                # For crypto, use Binance; for others, use data router
                asset_type = config.get("asset_type", "FOREX")
                is_crypto_channel = asset_type == "CRYPTO"
                
                try:
                    if is_crypto_channel:
                        # Crypto: use Binance directly
                        from working_combined_bot import get_real_crypto_price
                        rt_price = get_real_crypto_price(sym)
                        if rt_price:
                            source = "BINANCE"
                            reason = None
                        else:
                            rt_price = None
                            reason = "binance_unavailable"
                            source = "BINANCE"
                    else:
                        # Forex/Index/Gold: use data router
                        data_router = get_data_router()
                        if data_router:
                            rt_price, reason, source = await data_router.get_price_async(sym)
                        else:
                            rt_price, reason, source = get_price(sym)
                    
                    if rt_price is None:
                        print(f"  ⏸️ Price unavailable for {sym}: {reason}")
                        continue
                    
                    entry = rt_price
                    print(f"  Real-time entry price: {entry} (source: {source})")
                except Exception as e:
                    print(f"  Failed to get price for {sym}: {e}")
                    continue
                
                # Generate signal direction - check 24h rule first
                import random
                clean_sym = sym.replace(".FOREX", "")
                
                # Try both directions, checking 24h rule
                directions = ["BUY", "SELL"]
                random.shuffle(directions)  # Randomize order
                
                signal_type = None
                for direction in directions:
                    can_send_pair_dir, reason_pair_dir = can_send_pair_direction_signal(channel_id, clean_sym, direction)
                    if can_send_pair_dir:
                        signal_type = direction
                        break
                    else:
                        print(f"  ⏸️ {channel_name}: {reason_pair_dir}")
                
                # If both directions are blocked, skip this pair
                if signal_type is None:
                    print(f"  ⏸️ {channel_name}: Cannot send {clean_sym} (both BUY and SELL blocked by 24h rule)")
                    continue
                
                # Calculate TP/SL based on asset type
                asset_type = config.get("asset_type", "FOREX")  # Get asset type from config
                has_tp3 = config.get("has_tp3", True)  # Default to 3 TPs, unless specified False
                
                # Special handling for Lingrid Forex channel: only 2 TPs with random values
                is_lingrid_forex = channel_id == CHANNEL_LINGRID_FOREX
                
                # Check if it's an index (BRENT, USOIL), gold, or crypto
                is_index = clean_sym in ["BRENT", "USOIL"]
                is_gold = clean_sym == "XAUUSD"
                is_crypto = asset_type == "CRYPTO" or clean_sym.endswith("USDT")
                
                if is_lingrid_forex:
                    # Special logic for Lingrid Forex: 2 TPs with random values
                    # TP1: 25-30 pips, TP2: 45-50 pips, SL: 50 pips
                    # For JPY pairs: multiply by 10
                    import random
                    
                    if clean_sym.endswith("JPY"):
                        # JPY pairs: 10x larger pip values
                        tp1_pips = random.randint(250, 300)  # 25-30 * 10
                        tp2_pips = random.randint(450, 500)  # 45-50 * 10
                        sl_pips = 500  # 50 * 10
                        # JPY pairs use 3 decimals, so divide by 1000
                        tp1_distance = tp1_pips / 1000
                        tp2_distance = tp2_pips / 1000
                        sl_distance = sl_pips / 1000
                    else:
                        # Other pairs: standard pip values
                        tp1_pips = random.randint(25, 30)  # Random between 25-30 pips
                        tp2_pips = random.randint(45, 50)  # Random between 45-50 pips
                        sl_pips = 50  # Fixed 50 pips
                        # Other pairs use 5 decimals, so divide by 10000
                        tp1_distance = tp1_pips / 10000
                        tp2_distance = tp2_pips / 10000
                        sl_distance = sl_pips / 10000
                    
                    if signal_type == "BUY":
                        sl = entry - sl_distance
                        tp1 = entry + tp1_distance
                        tp2 = entry + tp2_distance
                        tp3 = None  # Only 2 TPs for Lingrid forex
                    else:  # SELL
                        sl = entry + sl_distance
                        tp1 = entry - tp1_distance
                        tp2 = entry - tp2_distance
                        tp3 = None  # Only 2 TPs for Lingrid forex
                    
                    logger.info(f"[LINGRID_FOREX] {clean_sym} {signal_type}: TP1={tp1_pips} pips, TP2={tp2_pips} pips, SL={sl_pips} pips")
                elif is_gold:
                    # Gold (XAUUSD): percentage-based with 3 TPs
                    # SL: 3%, TP1: 1%, TP2: 3%, TP3: 5% (similar to crypto/index)
                    sl_pct = 0.03  # 3% stop loss
                    profit_pct1 = 0.01  # 1% for TP1
                    profit_pct2 = 0.03  # 3% for TP2
                    profit_pct3 = 0.05  # 5% for TP3
                    
                    if signal_type == "BUY":
                        sl = entry * (1 - sl_pct)
                        tp1 = entry * (1 + profit_pct1)
                        tp2 = entry * (1 + profit_pct2)
                        tp3 = entry * (1 + profit_pct3)
                    else:  # SELL
                        sl = entry * (1 + sl_pct)
                        tp1 = entry * (1 - profit_pct1)
                        tp2 = entry * (1 - profit_pct2)
                        tp3 = entry * (1 - profit_pct3)
                elif is_crypto:
                    # Crypto pairs: percentage-based with 3 TPs
                    # SL: 3%, TP1: 1%, TP2: 3%, TP3: 5%
                    sl_pct = 0.03  # 3% stop loss
                    profit_pct1 = 0.01  # 1% for TP1
                    profit_pct2 = 0.03  # 3% for TP2
                    profit_pct3 = 0.05  # 5% for TP3
                    
                    if signal_type == "BUY":
                        sl = round(entry * (1 - sl_pct), 6)
                        tp1 = round(entry * (1 + profit_pct1), 6)
                        tp2 = round(entry * (1 + profit_pct2), 6)
                        tp3 = round(entry * (1 + profit_pct3), 6)
                    else:  # SELL
                        sl = round(entry * (1 + sl_pct), 6)
                        tp1 = round(entry * (1 - profit_pct1), 6)
                        tp2 = round(entry * (1 - profit_pct2), 6)
                        tp3 = round(entry * (1 - profit_pct3), 6)
                elif is_index:
                    # Index pairs (BRENT, USOIL): percentage-based with 3 TPs
                    # SL: 3%, TP1: 1%, TP2: 3%, TP3: 5% (similar to crypto)
                    sl_pct = 0.03  # 3% stop loss
                    profit_pct1 = 0.01  # 1% for TP1
                    profit_pct2 = 0.03  # 3% for TP2
                    profit_pct3 = 0.05  # 5% for TP3
                    
                    if signal_type == "BUY":
                        sl = entry * (1 - sl_pct)
                        tp1 = entry * (1 + profit_pct1)
                        tp2 = entry * (1 + profit_pct2)
                        tp3 = entry * (1 + profit_pct3)
                    else:  # SELL
                        sl = entry * (1 + sl_pct)
                        tp1 = entry * (1 - profit_pct1)
                        tp2 = entry * (1 - profit_pct2)
                        tp3 = entry * (1 - profit_pct3)
                else:
                    # Forex pairs: fixed pip distances with 3 TPs
                    # TP1: 20 pips, SL: 50 pips, TP2: 60 pips, TP3: 100 pips
                    # For JPY pairs: multiply by 10 (TP1: 200 pips, SL: 500 pips, TP2: 600 pips, TP3: 1000 pips)
                    if clean_sym.endswith("JPY"):
                        # JPY pairs: 10x larger pip values
                        sl_pips = 500  # 50 * 10
                        tp1_pips = 200  # 20 * 10
                        tp2_pips = 600  # 60 * 10
                        tp3_pips = 1000  # 100 * 10
                        # JPY pairs use 3 decimals, so divide by 1000
                        sl_distance = sl_pips / 1000
                        tp1_distance = tp1_pips / 1000
                        tp2_distance = tp2_pips / 1000
                        tp3_distance = tp3_pips / 1000
                    else:
                        # Other pairs: standard pip values
                        sl_pips = 50
                        tp1_pips = 20
                        tp2_pips = 60
                        tp3_pips = 100
                        # Other pairs use 5 decimals, so divide by 10000
                        sl_distance = sl_pips / 10000
                        tp1_distance = tp1_pips / 10000
                        tp2_distance = tp2_pips / 10000
                        tp3_distance = tp3_pips / 10000
                    
                    if signal_type == "BUY":
                        sl = entry - sl_distance
                        tp1 = entry + tp1_distance
                        tp2 = entry + tp2_distance
                        tp3 = entry + tp3_distance
                    else:  # SELL
                        sl = entry + sl_distance
                        tp1 = entry - tp1_distance
                        tp2 = entry - tp2_distance
                        tp3 = entry - tp3_distance
                
                # Build message (pass is_crypto flag for crypto signals)
                # Lingrid Forex has only 2 TPs, others have 3 TPs
                msg = build_signal_message(sym, signal_type, entry, sl, tp1, tp2, tp3=tp3, is_crypto=is_crypto)
                
                # Try to send to Telegram (if bot available)
                send_success = False
                if bot is not None:
                    print(f"📤 {channel_name}: Sending signal to Telegram (channel_id={channel_id}): {msg}")
                    logger.info(f"[GENERATE_SIGNALS] Attempting to send signal to {channel_name} (ID: {channel_id})")
                    send_success = await safe_send_message(bot, chat_id=channel_id, text=msg, disable_web_page_preview=True)
                    if send_success:
                        print(f"✅ {channel_name}: Signal sent successfully to Telegram")
                        logger.info(f"[GENERATE_SIGNALS] ✅ Signal sent successfully to {channel_name} (ID: {channel_id})")
                    else:
                        print(f"❌ {channel_name}: Failed to send signal to Telegram (check logs for details)")
                        logger.warning(f"[GENERATE_SIGNALS] ❌ Failed to send signal to {channel_name} (ID: {channel_id}) via Telegram")
                        # Skip saving if Telegram send failed (signal not actually published)
                        continue
                else:
                    print(f"📝 {channel_name}: Generated signal (Telegram disabled): {msg}")
                    logger.info(f"[GENERATE_SIGNALS] Signal generated for {channel_name} (local only, bot=None): {sym} {signal_type} @ {entry}")
                    # If bot is None, we still save for local logging
                    send_success = True
                
                # Only save signal if send was successful (or bot is None for local generation)
                if send_success:
                    # Save signal BEFORE updating counters to ensure it's counted
                    # All signals now have 3 TPs (forex, crypto, index, gold)
                    add_signal(sym, signal_type, entry, sl, tp1, tp2, tp3=tp3, channel_id=channel_id)
                    
                    # Verify signal was saved and counted
                    new_count = get_today_channel_signals_count(channel_id)
                    logger.info(f"[GENERATE_SIGNALS] {channel_name}: Signal saved - total today: {new_count}/{max_signals}")
                    
                    # Update time constraints only after successful send
                    save_last_signal_time()
                    save_channel_last_signal_time(channel_id)
                    save_channel_pair_direction_last_signal_time(channel_id, clean_sym, signal_type)
                    
                    signals_generated += 1
                    print(f"✅ {channel_name}: Generated signal {signals_generated}/{signals_needed}: {sym} {signal_type} (total today: {new_count}/{max_signals})")
                    
                    # Double-check: if we've reached the limit, stop generating for this channel
                    if new_count >= max_signals:
                        print(f"✅ {channel_name}: Daily limit reached after this signal ({new_count}/{max_signals})")
                        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Daily limit reached, stopping generation for this channel")
                        break
                else:
                    # Signal send failed - don't count it
                    logger.warning(f"[GENERATE_SIGNALS] {channel_name}: Signal send failed for {sym}, not counting towards daily limit")
                
                # Remove pair from available
                if sym in available_pairs:
                    available_pairs.remove(sym)
                
                # Wait before next signal (respect time constraints)
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"❌ {channel_name}: Error processing {sym}: {e}")
                import traceback
                print(traceback.format_exc())
                await asyncio.sleep(1)
        
        print(f"🏁 {channel_name}: Finished. Generated {signals_generated}/{signals_needed} signals.")


def migrate_state_files() -> None:
    """
    Migrate state files to ensure all timestamps are stored as float (Unix timestamp)
    This function can be called at startup to fix old format files
    """
    print("[MIGRATE_STATE] Starting state files migration...")
    
    files_to_migrate = [
        (LAST_SIGNAL_TIME_FILE, "last_signal_time"),
        (CHANNEL_LAST_SIGNAL_FILE, None),  # None means it's a dict with channel_id keys
        (CHANNEL_PAIR_LAST_SIGNAL_FILE, None),  # Dict with nested structure
        (CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, None),  # Dict with nested structure: {channel_id: {pair: {direction: timestamp}}}
    ]
    
    for file_path, timestamp_key in files_to_migrate:
        if not os.path.exists(file_path):
            print(f"[MIGRATE_STATE] ⏭️ {file_path}: File does not exist, skipping")
            continue
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            needs_migration = False
            
            if timestamp_key:
                # Simple structure: {"last_signal_time": value}
                if timestamp_key in data:
                    raw_value = data[timestamp_key]
                    normalized = normalize_timestamp(raw_value, f"{file_path}[{timestamp_key}]")
                    if normalized != raw_value:
                        data[timestamp_key] = normalized
                        needs_migration = True
            else:
                # Dict structure: {key: timestamp_value} or {key: {nested_key: timestamp_value}}
                for key, value in data.items():
                    if isinstance(value, dict):
                        # Nested structure (e.g., channel_pair_last_signal: {channel_id: {pair: timestamp}})
                        for nested_key, nested_value in value.items():
                            normalized = normalize_timestamp(nested_value, f"{file_path}[{key}][{nested_key}]")
                            if normalized != nested_value:
                                value[nested_key] = normalized
                                needs_migration = True
                    else:
                        # Direct timestamp value
                        normalized = normalize_timestamp(value, f"{file_path}[{key}]")
                        if normalized != value:
                            data[key] = normalized
                            needs_migration = True
            
            if needs_migration:
                with open(file_path, 'w') as f:
                    json.dump(data, f)
                print(f"[MIGRATE_STATE] ✅ Migrated {file_path} to float timestamp format")
            else:
                print(f"[MIGRATE_STATE] ✅ {file_path}: Already in correct format")
                
        except Exception as e:
            print(f"[MIGRATE_STATE] ⚠️ Error migrating {file_path}: {type(e).__name__}: {e}")
    
    print("[MIGRATE_STATE] Migration completed")


async def main_async():
    """Main async entrypoint - runs forever until interrupted (Ctrl+C)"""
    # Migrate state files first (fix old format if needed)
    migrate_state_files()
    
    # Initialize Twelve Data client for FOREX
    twelve_data_init_success = await startup_init()
    
    if not twelve_data_init_success:
        print("⚠️ [MAIN] Twelve Data initialization failed - FOREX signals may be unavailable")
        print("   Bot will continue working, but FOREX pairs may fail")
    
    # Create Telegram bot once
    bot = await create_telegram_bot_with_check()
    if not bot:
        logger.warning("[MAIN] ❌ Failed to create Telegram bot - continuing without Telegram send")
        logger.warning("[MAIN] Bot will generate signals but not send them to Telegram")
    
    pairs = DEFAULT_PAIRS
    
    # Track last execution times for periodic tasks
    last_tp_check_time = 0.0
    last_signal_generation_time = 0.0
    
    # TP hits check interval: 20 seconds
    TP_CHECK_INTERVAL = 20.0
    
    # Signal generation interval: 60 seconds
    SIGNAL_GENERATION_INTERVAL = 60.0
    
    print("[MAIN] 🤖 Bot started - running forever (Ctrl+C to stop)")
    print(f"[MAIN] TP check interval: {TP_CHECK_INTERVAL}s")
    print(f"[MAIN] Signal generation interval: {SIGNAL_GENERATION_INTERVAL}s")
    
    try:
        while True:
            try:
                current_time = time.time()
                
                # Check for TP hits every 20 seconds
                if current_time - last_tp_check_time >= TP_CHECK_INTERVAL:
                    try:
                        print("[MAIN] 🔍 Checking for TP hits...")
                        profit_messages = await check_signal_hits()
                        if profit_messages:
                            print(f"[MAIN] Found {len(profit_messages)} TP hits")
                            for msg in profit_messages:
                                print(f"[MAIN] Sending TP message: {msg}")
                                await safe_send_message(bot, chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
                                await asyncio.sleep(0.4)
                        last_tp_check_time = current_time
                    except Exception as e:
                        logger.exception(f"[MAIN] Error in TP check: {type(e).__name__}: {e}")
                        # Continue loop even if TP check fails
                
                # Check for performance reports
                try:
                    await check_and_send_reports(bot)
                except Exception as e:
                    logger.exception(f"[MAIN] Error in report check: {type(e).__name__}: {e}")
                    # Continue loop even if report check fails
                
                # Generate signals every 60 seconds
                if current_time - last_signal_generation_time >= SIGNAL_GENERATION_INTERVAL:
                    try:
                        print("[MAIN] 📊 Generating signals for all channels...")
                        await generate_channel_signals(bot, pairs)
                        last_signal_generation_time = current_time
                    except Exception as e:
                        logger.exception(f"[MAIN] Error in signal generation: {type(e).__name__}: {e}")
                        # Continue loop even if signal generation fails
                
                # Sleep 1 second between iterations to prevent high CPU usage
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                # Ctrl+C - break out of loop gracefully
                print("\n[MAIN] ⏹️ Received KeyboardInterrupt (Ctrl+C) - shutting down gracefully...")
                break
            except Exception as e:
                # Catch any unexpected exceptions and log them, but continue running
                logger.exception(f"[MAIN] Unexpected error in main loop: {type(e).__name__}: {e}")
                print(f"[MAIN] ⚠️ Error occurred, waiting 5 seconds before continuing...")
                await asyncio.sleep(5)
                
    finally:
        # Cleanup: close Twelve Data client only at the very end (in same event loop)
        # This happens only on process termination (Ctrl+C or exception that breaks loop)
        global _twelve_data_client
        if _twelve_data_client:
            try:
                await _twelve_data_client.close()
                print("[MAIN] ✅ Twelve Data client closed")
            except Exception as e:
                print(f"[MAIN] ⚠️ Error closing Twelve Data client: {type(e).__name__}: {e}")
        
        print("[MAIN] 👋 Bot stopped")


async def ctrader_auth_test():
    """Test cTrader authentication flow without starting full bot"""
    print("[CTRADER_AUTH_TEST] Starting cTrader authentication test...")
    
    try:
        from ctrader_async_client import CTraderAsyncClient, CTraderAsyncError
        from config import Config
        
        # Get cTrader config
        ctrader_config = Config.get_ctrader_config()
        ws_url, ws_source = ctrader_config.get_ws_url()
        
        print(f"[CTRADER_AUTH_TEST] Config: ws_url={ws_url}, account_id={ctrader_config.account_id}, is_demo={ctrader_config.is_demo}")
        
        # Create client
        client = CTraderAsyncClient(
            ws_url=ws_url,
            client_id=ctrader_config.client_id,
            client_secret=ctrader_config.client_secret,
            access_token=ctrader_config.access_token,
            account_id=ctrader_config.account_id,
            is_demo=ctrader_config.is_demo
        )
        
        # Connect
        print("[CTRADER_AUTH_TEST] Step 1: Connecting to WebSocket...")
        await client.connect()
        print("[CTRADER_AUTH_TEST] ✅ WebSocket connected")
        
        # ApplicationAuth
        print("[CTRADER_AUTH_TEST] Step 2: ApplicationAuth...")
        await client.auth_application()
        print("[CTRADER_AUTH_TEST] ✅ ApplicationAuth succeeded")
        
        # AccountAuth
        print("[CTRADER_AUTH_TEST] Step 3: AccountAuth...")
        await client.auth_account()
        print("[CTRADER_AUTH_TEST] ✅ AccountAuth succeeded")
        
        # Test price fetch
        print("[CTRADER_AUTH_TEST] Step 4: Testing price fetch for EURUSD...")
        price = client.get_last_price("EURUSD")
        if price:
            print(f"[CTRADER_AUTH_TEST] ✅ Price fetch OK: EURUSD = {price:.5f}")
        else:
            print("[CTRADER_AUTH_TEST] ⚠️ Price fetch returned None (symbol may need subscription)")
        
        # Close
        await client.close()
        print("[CTRADER_AUTH_TEST] ✅ Test completed successfully")
        return True
        
    except CTraderAsyncError as e:
        print(f"[CTRADER_AUTH_TEST] ❌ FAILED: {e.reason}: {e.message}")
        import traceback
        print(traceback.format_exc())
        return False
    except Exception as e:
        print(f"[CTRADER_AUTH_TEST] ❌ FAILED: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    import sys
    if "--ctrader-auth-test" in sys.argv:
        # Run authentication test only
        success = asyncio.run(ctrader_auth_test())
        sys.exit(0 if success else 1)
    else:
        # Run normal bot
        asyncio.run(main_async())