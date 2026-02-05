"""
Signals Bot - Telegram trading signals generator
Dependencies: python-telegram-bot, python-dotenv, httpx, yfinance (optional)
Install: py -m pip install python-telegram-bot python-dotenv httpx yfinance
"""
import os
import re
import time
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from dataclasses import dataclass

# Dependency check
try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ ERROR: python-dotenv not installed. Install with: py -m pip install python-dotenv")
    raise

try:
    from telegram import Bot
    from telegram.error import InvalidToken, TelegramError, BadRequest, Forbidden
except ImportError:
    print("❌ ERROR: python-telegram-bot not installed. Install with: py -m pip install python-telegram-bot")
    raise

try:
    from data_router import get_price, get_candles, AssetClass, ForbiddenDataSourceError, get_data_router
except ImportError:
    print("❌ ERROR: data_router module not found. Ensure data_router.py is in the same directory.")
    raise

try:
    from config import Config
except ImportError:
    print("⚠️ WARNING: config module not found. Some features may not work.")
    Config = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for Telegram send capability
_telegram_send_enabled = True

# Price cache with TTL (15-30 seconds)
_price_cache: Dict[str, Tuple[float, float]] = {}  # symbol -> (price, timestamp)
_PRICE_CACHE_TTL = 20.0  # 20 seconds TTL


def classify_telegram_error(e: Exception) -> str:
    """
    Classify Telegram error into categories for better error handling.
    
    Args:
        e: Exception instance (TelegramError, BadRequest, Forbidden, etc.)
    
    Returns:
        Category string: CHAT_NOT_FOUND, BOT_BLOCKED, FORBIDDEN, RATE_LIMIT, OTHER
    """
    error_str = str(e).lower()
    error_type = type(e).__name__
    
    # Chat not found patterns
    if "chat not found" in error_str or "chat_id is empty" in error_str:
        return "CHAT_NOT_FOUND"
    
    # Bot blocked patterns
    if "bot was blocked by the user" in error_str or "user is deactivated" in error_str:
        return "BOT_BLOCKED"
    
    # Forbidden patterns
    if isinstance(e, Forbidden) or "forbidden" in error_str or "not enough rights" in error_str:
        return "FORBIDDEN"
    
    # Rate limit patterns
    if "rate limit" in error_str or "too many requests" in error_str or "flood" in error_str:
        return "RATE_LIMIT"
    
    # Group chat upgraded
    if "group chat was upgraded" in error_str or "supergroup" in error_str:
        return "CHAT_NOT_FOUND"  # Treat as chat not found
    
    return "OTHER"


class PriceStatus(Enum):
    """Status of price retrieval result"""
    OK = "OK"  # price != None
    SKIPPED = "SKIPPED"  # price == None, but reason indicates intentional skip (cooldown/quota/circuit breaker)
    FAILED = "FAILED"  # price == None, real error occurred


@dataclass
class PriceResult:
    """Result of price retrieval with status and reason"""
    price: Optional[float]
    reason: Optional[str]
    source: str
    status: PriceStatus
    
    @classmethod
    def create(cls, price: Optional[float], reason: Optional[str], source: str) -> 'PriceResult':
        """Create PriceResult and determine status automatically"""
        if price is not None:
            status = PriceStatus.OK
        elif reason and reason in {
            "twelve_data_cooldown", "circuit_breaker_open", "quota_exceeded", 
            "rate_limited", "twelve_data_circuit_breaker_open", "cooldown"
        }:
            status = PriceStatus.SKIPPED
        else:
            status = PriceStatus.FAILED
        return cls(price=price, reason=reason, source=source, status=status)

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
TELEGRAM_TOKEN_SOURCE = "ENV"  # Track where token came from

# Fallback to hardcoded token if .env loading failed
if not TELEGRAM_BOT_TOKEN:
    try:
        from config_hardcoded import HARDCODED_TELEGRAM
        TELEGRAM_BOT_TOKEN = HARDCODED_TELEGRAM.get('bot_token', '')
        if TELEGRAM_BOT_TOKEN:
            TELEGRAM_TOKEN_SOURCE = "HARDCODED"
            logger.warning("[TELEGRAM_TOKEN] ⚠️ Using hardcoded token from config_hardcoded.py (fallback)")
            logger.info(f"[TELEGRAM_TOKEN] Token preview: {TELEGRAM_BOT_TOKEN[:6]}...{TELEGRAM_BOT_TOKEN[-4:]}")
    except Exception as e:
        logger.error(f"[TELEGRAM_TOKEN] ❌ Failed to load token from .env and fallback: {e}")
        TELEGRAM_BOT_TOKEN = ""
        TELEGRAM_TOKEN_SOURCE = "NONE"

# DRY_RUN mode: if set to "1" or "true", bot will work without Telegram (for testing)
DRY_RUN = os.getenv("DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "on")

# Load channel ID (with fallback)
try:
    from config_hardcoded import get_hardcoded_config
    _hardcoded_config = get_hardcoded_config()
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", _hardcoded_config.telegram_channel_id)
except ImportError:
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003118256304")

# Global Twelve Data client state (FOREX data source)
_twelve_data_client = None


# Track Telegram errors per chat_id to avoid spam
_telegram_error_logged: Dict[str, float] = {}  # chat_id -> last_error_log_time
_TELEGRAM_ERROR_LOG_INTERVAL = 300.0  # Log same error max once per 5 minutes


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
        - Throttles error logging to avoid spam (max once per 5 minutes per chat_id)
    """
    global _telegram_send_enabled, _telegram_error_logged
    
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
        # Clear error flag on success
        if chat_id in _telegram_error_logged:
            del _telegram_error_logged[chat_id]
        return True
    except InvalidToken as e:
        logger.error(f"[TELEGRAM_SEND] ❌ InvalidToken error: {e}")
        logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
        logger.error("[TELEGRAM_SEND] Disabling Telegram send for remainder of session")
        _telegram_send_enabled = False
        return False
    except Forbidden as e:
        # Forbidden - log once per interval
        now = time.time()
        last_log = _telegram_error_logged.get(chat_id, 0)
        if now - last_log >= _TELEGRAM_ERROR_LOG_INTERVAL:
            logger.error(f"[TELEGRAM_SEND] ❌ Forbidden: Bot does not have permission to send messages to chat_id={chat_id}")
            logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
            logger.error(f"[TELEGRAM_SEND] Action: Ensure bot is admin in channel with 'post messages' permission")
            _telegram_error_logged[chat_id] = now
        return False
    except BadRequest as e:
        # BadRequest - handle chat not found and other bad request cases
        error_category = classify_telegram_error(e)
        
        now = time.time()
        last_log = _telegram_error_logged.get(chat_id, 0)
        should_log = (now - last_log >= _TELEGRAM_ERROR_LOG_INTERVAL)
        
        if error_category == "CHAT_NOT_FOUND":
            # Chat not found - log once per interval
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Chat not found: Chat ID {chat_id} not found or bot is not a member")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                logger.error(f"[TELEGRAM_SEND] Action: Ensure bot is added to channel as admin with 'post messages' permission")
                _telegram_error_logged[chat_id] = now
        elif error_category == "BOT_BLOCKED":
            # Bot blocked - log once per interval
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Bot blocked: Bot was blocked by user for chat_id={chat_id}")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                _telegram_error_logged[chat_id] = now
        elif error_category == "RATE_LIMIT":
            # Rate limit - log once per interval
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Rate limit: Too many requests for chat_id={chat_id}")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                _telegram_error_logged[chat_id] = now
        else:
            # Other BadRequest errors - log with details
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ BadRequest: Invalid request for chat_id={chat_id}")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                logger.error(f"[TELEGRAM_SEND] Message preview: {text[:100]}...")
                _telegram_error_logged[chat_id] = now
        return False
    except TelegramError as e:
        # Other Telegram errors - handle with classification
        error_category = classify_telegram_error(e)
        
        now = time.time()
        last_log = _telegram_error_logged.get(chat_id, 0)
        should_log = (now - last_log >= _TELEGRAM_ERROR_LOG_INTERVAL)
        
        if error_category == "CHAT_NOT_FOUND":
            # Chat not found - log once per interval
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Chat not found: Chat ID {chat_id} not found or bot is not a member")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                logger.error(f"[TELEGRAM_SEND] Action: Ensure bot is added to channel as admin with 'post messages' permission")
                _telegram_error_logged[chat_id] = now
        elif error_category == "RATE_LIMIT":
            # Rate limit - log once per interval
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Rate limit: Too many requests for chat_id={chat_id}")
                logger.error(f"[TELEGRAM_SEND] Error details: {type(e).__name__}: {e}")
                _telegram_error_logged[chat_id] = now
        else:
            # Other Telegram errors - log with details
            if should_log:
                logger.error(f"[TELEGRAM_SEND] ❌ Telegram error: {type(e).__name__}: {e}")
                logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
                logger.error(f"[TELEGRAM_SEND] Message preview: {text[:100]}...")
                import traceback
                logger.exception(f"[TELEGRAM_SEND] Full traceback:")
                _telegram_error_logged[chat_id] = now
        return False
    except Exception as e:
        # Unexpected errors - always log
        logger.error(f"[TELEGRAM_SEND] ❌ Unexpected error: {type(e).__name__}: {e}")
        logger.error(f"[TELEGRAM_SEND] Chat ID: {chat_id}")
        import traceback
        logger.exception(f"[TELEGRAM_SEND] Full traceback:")
        return False


async def create_telegram_bot_with_check(token: Optional[str] = None) -> Optional[Bot]:
    """
    Create Telegram Bot instance and verify token validity via getMe.
    
    Args:
        token: Bot token (defaults to TELEGRAM_BOT_TOKEN)
    
    Returns:
        Bot instance if valid, None otherwise (only if token is empty and DRY_RUN=False)
    
    Side effects:
        - Sets _telegram_send_enabled=False if token invalid
        - Logs bot info on success (@username and id)
        - Exits process if token provided but bot creation fails (unless DRY_RUN=True)
    """
    global _telegram_send_enabled
    
    if token is None:
        token = TELEGRAM_BOT_TOKEN
    
    # Diagnostic: log token source and status
    token_source = "ENV" if os.getenv("TELEGRAM_BOT_TOKEN") else ".env file"
    token_length = len(token) if token else 0
    token_preview = f"{token[:6]}...{token[-4:]}" if token and len(token) > 10 else "***"
    
    logger.info("[TELEGRAM_BOT] ===== Telegram Bot Initialization =====")
    logger.info(f"[TELEGRAM_BOT] Token source: {token_source}")
    logger.info(f"[TELEGRAM_BOT] Token length: {token_length}")
    logger.info(f"[TELEGRAM_BOT] Token preview: {token_preview}")
    logger.info(f"[TELEGRAM_BOT] DRY_RUN mode: {DRY_RUN}")
    
    if not token:
        if DRY_RUN:
            logger.warning("[TELEGRAM_BOT] ⚠️ No token provided - DRY_RUN mode enabled, continuing without Telegram")
            _telegram_send_enabled = False
            return None
        else:
            logger.error("[TELEGRAM_BOT] ❌ FATAL: No token provided and DRY_RUN=False")
            logger.error("[TELEGRAM_BOT] Set TELEGRAM_BOT_TOKEN in .env file or set DRY_RUN=1 to continue")
            logger.error("[TELEGRAM_BOT] Exiting with code 1")
            print("\n❌ FATAL ERROR: Telegram bot token is required!")
            print("   Set TELEGRAM_BOT_TOKEN in .env file or set DRY_RUN=1 to continue without Telegram")
            sys.exit(1)
    
    try:
        bot = Bot(token=token)
        
        # Self-check: verify token by calling getMe
        try:
            me = await bot.get_me()
            logger.info(f"[TELEGRAM_BOT] ✅ Telegram OK: @{me.username} (id={me.id})")
            logger.info("[TELEGRAM_BOT] Telegram enabled: True")
            _telegram_send_enabled = True
            return bot
        except InvalidToken as e:
            error_msg = f"Invalid TELEGRAM_BOT_TOKEN (getMe failed): {e!r}"
            logger.error(f"[TELEGRAM_BOT] ❌ {error_msg}")
            if DRY_RUN:
                logger.warning("[TELEGRAM_BOT] DRY_RUN mode: continuing without Telegram")
                _telegram_send_enabled = False
                return None
            else:
                logger.error("[TELEGRAM_BOT] Exiting with code 1")
                print(f"\n❌ FATAL ERROR: {error_msg}")
                print("   Check token in .env file or set DRY_RUN=1 to continue without Telegram")
                sys.exit(1)
        except (TelegramError, BadRequest, Forbidden) as e:
            error_msg = f"Telegram getMe failed: {type(e).__name__}: {e!r}"
            logger.error(f"[TELEGRAM_BOT] ❌ {error_msg}")
            if DRY_RUN:
                logger.warning("[TELEGRAM_BOT] DRY_RUN mode: continuing without Telegram")
                _telegram_send_enabled = False
                return None
            else:
                logger.error("[TELEGRAM_BOT] Exiting with code 1")
                print(f"\n❌ FATAL ERROR: {error_msg}")
                print("   Set DRY_RUN=1 to continue without Telegram")
                sys.exit(1)
        except Exception as e:
            error_msg = f"Telegram getMe failed (unexpected): {type(e).__name__}: {e!r}"
            logger.error(f"[TELEGRAM_BOT] ❌ {error_msg}")
            if DRY_RUN:
                logger.warning("[TELEGRAM_BOT] DRY_RUN mode: continuing without Telegram")
                _telegram_send_enabled = False
                return None
            else:
                logger.error("[TELEGRAM_BOT] Exiting with code 1")
                print(f"\n❌ FATAL ERROR: {error_msg}")
                print("   Set DRY_RUN=1 to continue without Telegram")
                sys.exit(1)
            
    except Exception as e:
        error_msg = f"Error creating Bot instance: {type(e).__name__}: {e!r}"
        logger.error(f"[TELEGRAM_BOT] ❌ {error_msg}")
        if DRY_RUN:
            logger.warning("[TELEGRAM_BOT] DRY_RUN mode: continuing without Telegram")
            _telegram_send_enabled = False
            return None
        else:
            logger.error("[TELEGRAM_BOT] Exiting with code 1")
            print(f"\n❌ FATAL ERROR: {error_msg}")
            print("   Set DRY_RUN=1 to continue without Telegram")
            sys.exit(1)


def send_telegram_message(channel_id: str, text: str, bot: Optional[Bot] = None) -> Tuple[bool, Optional[str]]:
    """
    Send Telegram message with error handling (synchronous wrapper for async function).
    
    Args:
        channel_id: Chat/channel ID
        text: Message text
        bot: Telegram Bot instance (if None, uses global bot)
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    if bot is None:
        return False, "Bot is None"
    
    try:
        # Run async function in event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, safe_send_message(bot, channel_id, text))
                success = future.result(timeout=10)
                return success, None
        else:
            success = loop.run_until_complete(safe_send_message(bot, channel_id, text))
            return success, None
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"[SEND_TELEGRAM] ❌ Failed to send message: {error_msg}")
        return False, error_msg


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

# Time constraints (in seconds) - CONFIGURABLE PER ASSET TYPE
MIN_TIME_BETWEEN_SIGNALS = 5 * 60  # 5 minutes between any signals (global)

# Channel constraints per asset type (in seconds) - CONFIGURABLE
CHANNEL_CONSTRAINT_INTERVALS = {
    "FOREX": 15 * 60,      # 15 minutes between signals in FOREX channels
    "CRYPTO": 10 * 60,     # 10 minutes between signals in CRYPTO channels
    "INDEX": 30 * 60,      # 30 minutes between signals in INDEX channels
    "GOLD": 30 * 60,       # 30 minutes between signals in GOLD channels
    "DEFAULT": 15 * 60     # Default: 15 minutes
}

# Legacy support (will be replaced by CHANNEL_CONSTRAINT_CONFIG)
MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MIN = 150 * 60  # Legacy: 2.5 hours (deprecated, use CHANNEL_CONSTRAINT_CONFIG)
MIN_TIME_BETWEEN_CHANNEL_SIGNALS_MAX = 180 * 60  # Legacy: 3 hours (deprecated, use CHANNEL_CONSTRAINT_CONFIG)
MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS = 24 * 60 * 60  # 24 hours between same pair+direction in same channel

# Active signal TTL configuration
ACTIVE_SIGNAL_TTL_MINUTES = int(os.getenv("ACTIVE_SIGNAL_TTL_MINUTES", "180"))  # 180 minutes (3 hours) default TTL
ACTIVE_SIGNAL_TTL_HOURS = ACTIVE_SIGNAL_TTL_MINUTES / 60  # Convert to hours for backward compatibility

# Allow multiple active signals per symbol (for channels with 1-2 symbols like GOLD/INDEXES)
# Set ALLOW_MULTIPLE_ACTIVE_PER_SYMBOL=1 to enable
ALLOW_MULTIPLE_ACTIVE_PER_SYMBOL = os.getenv("ALLOW_MULTIPLE_ACTIVE_PER_SYMBOL", "0").strip().lower() in ("1", "true", "yes", "on")

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
    """Load active signals from file and migrate old format signals"""
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, 'r') as f:
                signals = json.load(f)
            
            # Migration: Add publish_status="published" to old signals without this field
            needs_save = False
            for signal in signals:
                if "publish_status" not in signal:
                    signal["publish_status"] = "published"  # Assume old signals were published
                    needs_save = True
            
            if needs_save:
                save_active_signals(signals)
                logger.info(f"[MIGRATE_SIGNALS] Migrated {len([s for s in signals if 'publish_status' in s])} signals to include publish_status")
            
            return signals
    except Exception:
        pass
    return []


def save_active_signals(signals: List[Dict]) -> None:
    """Save active signals to file"""
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(signals, f, indent=2)
    except Exception as e:
        logger.error(f"[SAVE_ACTIVE_SIGNALS] Failed to save signals: {e}")


def clear_today_signals() -> int:
    """
    Clear all signals for today (called on bot startup to reset daily counters).
    
    Returns:
        Number of signals cleared
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    
    if not active_signals:
        return 0
    
    # Filter out signals for today
    signals_before = len(active_signals)
    signals_after_today = [s for s in active_signals if s.get("date") != today]
    cleared_count = signals_before - len(signals_after_today)
    
    if cleared_count > 0:
        save_active_signals(signals_after_today)
        logger.info(f"[CLEAR_TODAY] ✅ Cleared {cleared_count} signals for today ({today}) on bot startup")
        print(f"[CLEAR_TODAY] ✅ Cleared {cleared_count} signals for today ({today}) - counters reset")
    else:
        logger.info(f"[CLEAR_TODAY] No signals found for today ({today})")
    
    return cleared_count


def close_expired_signals() -> int:
    """
    Close expired signals (older than TTL) automatically.
    
    Returns:
        Number of signals closed
    """
    active_signals = load_active_signals()
    if not active_signals:
        return 0
    
    current_time = time.time()
    ttl_seconds = ACTIVE_SIGNAL_TTL_MINUTES * 60
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    closed_count = 0
    expired_signals = []
    updated_signals = []
    
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            signal_timestamp = signal.get("timestamp")
            if signal_timestamp:
                try:
                    # Parse ISO timestamp or Unix timestamp
                    if isinstance(signal_timestamp, (int, float)):
                        signal_time = float(signal_timestamp)
                    else:
                        # Try parsing ISO format
                        signal_dt = datetime.fromisoformat(signal_timestamp.replace('Z', '+00:00'))
                        signal_time = signal_dt.timestamp()
                    
                    age_seconds = current_time - signal_time
                    age_minutes = age_seconds / 60
                    
                    if age_seconds > ttl_seconds:
                        # Close expired signal
                        signal["status"] = "expired"
                        signal["closed_at"] = datetime.now(timezone.utc).isoformat()
                        signal["expired_reason"] = f"TTL exceeded (age: {age_minutes:.1f}min > {ACTIVE_SIGNAL_TTL_MINUTES}min)"
                        expired_signals.append({
                            "symbol": signal.get("symbol"),
                            "channel_id": signal.get("channel_id"),
                            "age_minutes": age_minutes
                        })
                        closed_count += 1
                        logger.info(f"[CLOSE_EXPIRED] Closed expired signal: {signal.get('symbol')} (channel: {signal.get('channel_id')}, age: {age_minutes:.1f}min)")
                except Exception as e:
                    logger.warning(f"[CLOSE_EXPIRED] Failed to parse timestamp for signal {signal.get('symbol')}: {e}")
        
        updated_signals.append(signal)
    
    if closed_count > 0:
        save_active_signals(updated_signals)
        logger.info(f"[CLOSE_EXPIRED] ✅ Closed {closed_count} expired signals (TTL: {ACTIVE_SIGNAL_TTL_MINUTES} minutes)")
        print(f"[CLOSE_EXPIRED] ✅ Closed {closed_count} expired signals:")
        for sig in expired_signals:
            print(f"   - {sig['symbol']} (channel: {sig['channel_id']}, age: {sig['age_minutes']:.1f}min)")
    
    return closed_count


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


def get_channel_constraint_interval(channel_id: str, asset_type: str = "DEFAULT") -> float:
    """Get channel constraint interval based on asset type
    
    Args:
        channel_id: Channel ID (for logging)
        asset_type: Asset type (FOREX, CRYPTO, INDEX, GOLD)
    
    Returns:
        Constraint interval in seconds
    """
    return CHANNEL_CONSTRAINT_INTERVALS.get(asset_type, CHANNEL_CONSTRAINT_INTERVALS["DEFAULT"])


def save_channel_last_signal_time(channel_id: str, asset_type: str = "DEFAULT") -> None:
    """Save current time as last signal time for channel with configured wait time
    
    Args:
        channel_id: Channel ID
        asset_type: Asset type (FOREX, CRYPTO, INDEX, GOLD) to determine wait time
    
    Saves structure: {channel_id: {"last_time": timestamp, "wait_time": wait_seconds}}
    """
    try:
        current_time = float(time.time())
        # Use configured wait time based on asset type
        wait_time = get_channel_constraint_interval(channel_id, asset_type)
        
        channel_times = load_channel_last_signal_times()
        channel_times[channel_id] = {
            "last_time": current_time,
            "wait_time": wait_time
        }
        
        with open(CHANNEL_LAST_SIGNAL_FILE, 'w') as f:
            json.dump(channel_times, f)
        
        wait_minutes = int(wait_time / 60)
        print(f"[SAVE_STATE] ✅ Saved channel_last_signal_time for {channel_id} (asset_type={asset_type}): wait_time={wait_minutes} minutes")
        logger.info(f"[SAVE_STATE] Channel {channel_id}: last_time={current_time}, wait_time={wait_time}s ({wait_minutes} min)")
    except Exception as e:
        print(f"[SAVE_STATE] ⚠️ Error saving channel_last_signal_time: {e}")
        logger.exception(f"[SAVE_STATE] Error saving channel_last_signal_time: {e}")


def load_channel_pair_direction_last_signal_times() -> Dict:
    """Load last signal times per channel+pair+direction from file with normalization
    
    Structure: {channel_id: {pair: {direction: timestamp}}}
    
    Handles migration from legacy format where pair_data could be float instead of dict.
    """
    try:
        if os.path.exists(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE):
            with open(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, 'r') as f:
                data = json.load(f)
                
                # Normalize all timestamps and migrate legacy formats
                needs_migration = False
                for channel_id, pairs_dict in data.items():
                    if not isinstance(pairs_dict, dict):
                        # Legacy: pairs_dict might be something else - skip or convert
                        print(f"[LOAD_STATE] ⚠️ Invalid structure for channel_id={channel_id}, expected dict, got {type(pairs_dict).__name__}")
                        continue
                    
                    for pair, directions_dict in pairs_dict.items():
                        # CRITICAL FIX: Handle legacy format where directions_dict might be float instead of dict
                        if not isinstance(directions_dict, dict):
                            if isinstance(directions_dict, (int, float)):
                                # Legacy format: pair -> float timestamp (apply to both BUY and SELL)
                                legacy_timestamp = normalize_timestamp(directions_dict, f"channel_pair_direction[{channel_id}][{pair}][LEGACY]")
                                print(f"[LOAD_STATE] Migrating legacy format: channel_id={channel_id}, pair={pair} (float -> dict)")
                                pairs_dict[pair] = {
                                    "BUY": legacy_timestamp,
                                    "SELL": legacy_timestamp
                                }
                                needs_migration = True
                            else:
                                print(f"[LOAD_STATE] ⚠️ Invalid structure for pair={pair}, expected dict or float, got {type(directions_dict).__name__}")
                                # Convert to empty dict to prevent AttributeError
                                pairs_dict[pair] = {}
                                needs_migration = True
                            continue
                        
                        # Normal format: directions_dict is dict {direction: timestamp}
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
                        print(f"[LOAD_STATE] ✅ Auto-migrated channel_pair_direction_last_signal_times (legacy format -> dict format)")
                    except Exception as e:
                        print(f"[LOAD_STATE] ⚠️ Failed to auto-migrate: {e}")
                
                return data
    except Exception as e:
        print(f"[LOAD_STATE] ⚠️ Error loading channel_pair_direction_last_signal_times: {e}")
        import traceback
        print(f"[LOAD_STATE] Traceback: {traceback.format_exc()}")
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
    if not isinstance(channel_data, dict):
        # Defensive: ensure channel_data is dict
        print(f"[CAN_SEND_PAIR_DIRECTION] ⚠️ Invalid channel_data type for {channel_id}: {type(channel_data).__name__}, using empty dict")
        channel_data = {}
        data[channel_id] = channel_data
    
    pair_data = channel_data.get(pair, {})
    # CRITICAL FIX: Handle legacy format where pair_data might be float instead of dict
    if not isinstance(pair_data, dict):
        if isinstance(pair_data, (int, float)):
            # Legacy format: convert float timestamp to dict with both directions
            legacy_timestamp = normalize_timestamp(pair_data, f"channel_pair_direction[{channel_id}][{pair}][LEGACY]")
            print(f"[CAN_SEND_PAIR_DIRECTION] Migrating legacy format: channel_id={channel_id}, pair={pair} (float -> dict)")
            pair_data = {
                "BUY": legacy_timestamp,
                "SELL": legacy_timestamp
            }
            channel_data[pair] = pair_data
            # Save migrated data back
            try:
                all_data = load_channel_pair_direction_last_signal_times()
                all_data[channel_id] = channel_data
                with open(CHANNEL_PAIR_DIRECTION_LAST_SIGNAL_FILE, 'w') as f:
                    json.dump(all_data, f)
            except Exception as e:
                print(f"[CAN_SEND_PAIR_DIRECTION] ⚠️ Failed to save migrated data: {e}")
        else:
            # Invalid type - use empty dict
            print(f"[CAN_SEND_PAIR_DIRECTION] ⚠️ Invalid pair_data type for {pair}: {type(pair_data).__name__}, using empty dict")
            pair_data = {}
            channel_data[pair] = pair_data
    
    last_time_raw = pair_data.get(direction, 0)
    last_time = normalize_timestamp(last_time_raw, f"channel_pair_direction[{channel_id}][{pair}][{direction}]")
    
    if last_time > 0:
        time_since_last = current_time - last_time
        if time_since_last < MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS:
            remaining_hours = (MIN_TIME_BETWEEN_PAIR_DIRECTION_SIGNALS - time_since_last) / 3600
            return False, f"Pair {pair} {direction} already sent to this channel {remaining_hours:.1f}h ago (24h rule)"
    
    return True, None


def can_send_signal(channel_id: str, asset_type: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Check if we can send a signal (time constraints)
    
    Args:
        channel_id: Channel ID to check
        asset_type: Asset type (FOREX, CRYPTO, INDEX, GOLD) to determine constraint interval
    
    Returns:
        Tuple of (can_send: bool, reason: Optional[str])
    """
    current_time = time.time()
    
    # Check global time constraint (5 minutes) - only if last signal was actually sent
    last_signal_times = load_last_signal_times()
    last_global_time_raw = last_signal_times.get("last_signal_time", 0)
    last_global_time = normalize_timestamp(last_global_time_raw, "last_global_time")
    
    if last_global_time > 0:
        elapsed = current_time - last_global_time
        if elapsed < MIN_TIME_BETWEEN_SIGNALS:
            remaining = MIN_TIME_BETWEEN_SIGNALS - elapsed
            remaining_minutes = max(0, int(remaining / 60))
            remaining_seconds = max(0, int(remaining % 60))
            logger.debug(f"[CONSTRAINT] Global: last={last_global_time:.0f}, now={current_time:.0f}, elapsed={elapsed/60:.1f}min, required={MIN_TIME_BETWEEN_SIGNALS/60}min, remaining={remaining_minutes}m{remaining_seconds}s")
            if remaining > 0:
                return False, f"Wait {remaining_minutes} minutes (global constraint: {int(MIN_TIME_BETWEEN_SIGNALS/60)} min interval)"
    
    # Check channel-specific time constraint (configurable per asset type)
    channel_times = load_channel_last_signal_times()
    channel_data = channel_times.get(channel_id)
    
    if channel_data is None:
        # No previous signal for this channel - allow sending
        logger.debug(f"[CONSTRAINT] Channel {channel_id}: No previous signal, allowing")
        return True, None
    
    # Determine constraint interval based on asset type
    if asset_type and asset_type in CHANNEL_CONSTRAINT_INTERVALS:
        required_interval = CHANNEL_CONSTRAINT_INTERVALS[asset_type]
    else:
        required_interval = CHANNEL_CONSTRAINT_INTERVALS["DEFAULT"]
    
    # Handle both new format (dict) and legacy format (float)
    if isinstance(channel_data, dict):
        # New format: {"last_time": timestamp, "wait_time": wait_seconds}
        last_channel_time_raw = channel_data.get("last_time", 0)
        # Use configured interval instead of saved wait_time
        wait_time = required_interval
    else:
        # Legacy format: just a timestamp - use configured interval
        last_channel_time_raw = channel_data
        wait_time = required_interval
    
    last_channel_time = normalize_timestamp(last_channel_time_raw, f"last_channel_time[{channel_id}]")
    
    if last_channel_time > 0:
        elapsed_minutes = (current_time - last_channel_time) / 60
        time_since_last = current_time - last_channel_time
        if time_since_last < wait_time:
            remaining = wait_time - time_since_last
            remaining_minutes = max(0, int(remaining / 60))
            remaining_seconds = max(0, int(remaining % 60))
            logger.debug(f"[CONSTRAINT] Channel {channel_id}: last={last_channel_time:.0f}, now={current_time:.0f}, elapsed={elapsed_minutes:.1f}min, required={wait_time/60:.1f}min, remaining={remaining_minutes}m{remaining_seconds}s")
            if remaining > 0:
                return False, f"Wait {remaining_minutes} minutes (channel constraint: {int(wait_time/60)} min interval)"
    
    logger.debug(f"[CONSTRAINT] Channel {channel_id}: All constraints passed")
    return True, None


def get_today_channel_signals_count(channel_id: str) -> int:
    """Count ONLY published signals sent to channel today (including closed/completed signals)
    
    This ensures that if bot is restarted, it won't send more signals than daily limit.
    Only signals that were successfully published to Telegram are counted.
    
    Args:
        channel_id: Channel ID to count signals for
    
    Returns:
        Total count of PUBLISHED signals sent to this channel today (regardless of status)
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    
    # Count ONLY published signals for this channel today (including closed/completed)
    # Backward compatibility: if publish_status is missing, assume it's published (old format)
    published_signals = [
        s for s in active_signals 
        if s.get("channel_id") == channel_id 
        and s.get("date") == today
        and (s.get("publish_status") == "published" or s.get("publish_status") is None)  # None = old format, assume published
    ]
    count = len(published_signals)
    
    # Log for debugging
    if count > 0:
        # Count by status for detailed logging
        active_count = len([s for s in published_signals if s.get("status") == "active"])
        closed_count = count - active_count
        logger.info(f"[SIGNAL_COUNT] Channel {channel_id}: {count} published signals today ({active_count} active, {closed_count} closed)")
    
    return count


def get_today_signals_count() -> int:
    """Count ONLY published signals generated today"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    # Count only published signals (backward compatibility: None = published)
    return sum(1 for s in active_signals 
               if s.get("date") == today 
               and (s.get("publish_status") == "published" or s.get("publish_status") is None))


def get_active_pairs() -> List[str]:
    """Get pairs that currently have active signals"""
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    active_pairs = []
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            active_pairs.append(signal.get("symbol"))
    
    return active_pairs


def get_available_pairs(all_pairs: List[str], channel_id: Optional[str] = None, allow_multiple: bool = False) -> List[str]:
    """Get pairs that don't have active signals for the specified channel.
    
    Args:
        all_pairs: List of all pairs to check
        channel_id: If provided, only check for active signals in this channel.
                   If None, check globally (backward compatibility)
        allow_multiple: If True, allow multiple active signals per symbol (for channels with 1-2 symbols)
    
    Returns:
        List of available pairs (excluding pairs with active signals that are not expired)
    """
    # CRITICAL: Close expired signals BEFORE checking available pairs
    # This ensures expired signals are automatically closed and don't block generation
    expired_count = close_expired_signals()
    
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_time = time.time()
    ttl_seconds = ACTIVE_SIGNAL_TTL_MINUTES * 60
    
    # Get active pairs for this channel (or globally if channel_id is None)
    active_pairs = []
    expired_signals_found = 0
    
    # Track symbol counts if allow_multiple is True
    symbol_counts = {} if allow_multiple else None
    
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            # CRITICAL: Only consider published signals (backward compatibility: None = published)
            publish_status = signal.get("publish_status")
            if publish_status not in ("published", None):  # None = old format, assume published
                continue  # Skip failed/skipped signals
            
            signal_channel_id = signal.get("channel_id")
            signal_symbol = signal.get("symbol")
            
            # Defensive check: if signal is expired (should have been closed by close_expired_signals)
            signal_timestamp = signal.get("timestamp")
            is_expired = False
            if signal_timestamp:
                try:
                    # Parse ISO timestamp or Unix timestamp
                    if isinstance(signal_timestamp, (int, float)):
                        signal_time = float(signal_timestamp)
                    else:
                        # Try parsing ISO format
                        signal_dt = datetime.fromisoformat(signal_timestamp.replace('Z', '+00:00'))
                        signal_time = signal_dt.timestamp()
                    
                    age_seconds = current_time - signal_time
                    age_minutes = age_seconds / 60
                    if age_seconds > ttl_seconds:
                        is_expired = True
                        expired_signals_found += 1
                        logger.debug(f"[AVAILABLE_PAIRS] Signal for {signal_symbol} expired (age: {age_minutes:.1f}min > {ACTIVE_SIGNAL_TTL_MINUTES}min)")
                except Exception as e:
                    logger.warning(f"[AVAILABLE_PAIRS] Failed to parse timestamp for {signal_symbol}: {e}")
            
            if is_expired:
                continue
            
            # If allow_multiple=True, don't exclude pairs (for channels with 1-2 symbols)
            if allow_multiple:
                symbol_counts[signal_symbol] = symbol_counts.get(signal_symbol, 0) + 1
                continue
            
            # If channel_id is specified, only exclude pairs active in THIS channel
            # If channel_id is None, exclude pairs active in ANY channel (backward compatibility)
            if channel_id is None or signal_channel_id == channel_id:
                active_pairs.append(signal_symbol)
    
    # Log why pairs are excluded
    if active_pairs:
        logger.info(f"[AVAILABLE_PAIRS] Excluding {len(active_pairs)} pairs with active signals (channel_id={channel_id}, allow_multiple={allow_multiple})")
    if expired_count > 0:
        logger.info(f"[AVAILABLE_PAIRS] {expired_count} signals expired and closed (TTL={ACTIVE_SIGNAL_TTL_MINUTES}min), pairs available again")
    if allow_multiple and symbol_counts:
        logger.info(f"[AVAILABLE_PAIRS] Multiple active per symbol enabled - {len(symbol_counts)} symbols have active signals")
    
    available = [pair for pair in all_pairs if pair not in active_pairs]
    return available


def add_signal(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float = None, tp3: float = None, channel_id: str = None, publish_status: str = "published") -> None:
    """
    Add new signal to tracking with 2 or 3 TPs.
    
    Args:
        symbol: Trading pair symbol
        signal_type: BUY or SELL
        entry: Entry price
        sl: Stop loss price
        tp1: Take profit 1 price
        tp2: Optional take profit 2 price
        tp3: Optional take profit 3 price
        channel_id: Telegram channel ID
        publish_status: "published" | "failed" | "skipped"
                       Only signals with publish_status="published" are saved and counted.
    
    Note:
        Signals are saved ONLY if publish_status="published".
        Failed or skipped signals are NOT saved to prevent counting unpublished signals.
    """
    # CRITICAL: Only save signals that were successfully published to Telegram
    if publish_status != "published":
        logger.debug(f"[ADD_SIGNAL] Skipping save for {symbol} {signal_type} (publish_status={publish_status})")
        return
    
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
            "channel_id": channel_id,
            "publish_status": "published"  # Explicitly mark as published
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
            "channel_id": channel_id,
            "publish_status": "published"
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
            "channel_id": channel_id,
            "publish_status": "published"
        }
    active_signals = load_active_signals()
    active_signals.append(signal)
    save_active_signals(active_signals)
    logger.info(f"[ADD_SIGNAL] ✅ Saved published signal: {symbol} {signal_type} (channel_id={channel_id})")


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


# REMOVED: add_completed_signal() - Performance tracking disabled (depends on TP/SL monitoring)
# Bot now only generates signals without tracking completion status
def add_completed_signal(symbol: str, signal_type: str, entry: float, exit_price: float, status: str) -> None:
    """DISABLED: Performance tracking removed to reduce API usage"""
    # No-op: performance tracking disabled
    pass
    
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


# REMOVED: check_signal_hits() function - TP/SL monitoring disabled to reduce TwelveData API usage
# Bot now only generates and publishes signals, without monitoring TP/SL hits


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


# REMOVED: Performance reports disabled (depend on TP/SL data)
def get_performance_report(days: int = 1) -> str:
    """DISABLED: Performance reports removed (depend on TP/SL monitoring)"""
    return "📊 Performance reports disabled - TP/SL monitoring removed"
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


# REMOVED: send_performance_report() - Performance reports disabled
async def send_performance_report(bot: Optional[Bot], days: int = 1) -> None:
    """DISABLED: Performance reports removed (depend on TP/SL monitoring)"""
    # No-op: performance reports disabled
    pass


# REMOVED: check_and_send_reports() - Performance reports disabled (depend on TP/SL data)
# Bot now only generates signals without tracking TP/SL hits


# REMOVED: post_signals_once() function - replaced by main_async() infinite loop
# TP/SL checking and performance reports removed to reduce API usage


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
        
        # Test connection with a simple price request (single-shot: max_retries=0 -> 1 HTTP request)
        print("[STARTUP] Testing Twelve Data connection (single-shot mode: 1 HTTP request expected)...")
        test_price, test_reason = await _twelve_data_client.get_price("EURUSD", max_retries_override=0)
        if test_price:
            print(f"[STARTUP] ✅ Twelve Data connection test successful (EURUSD={test_price:.5f}, single-shot: 1 HTTP request made)")
        else:
            print(f"[STARTUP] ⚠️ Twelve Data connection test failed (reason={test_reason}), but client initialized (will retry on demand)")
        
        # Create DataRouter with injected Twelve Data client
        from data_router import DataRouter, set_data_router
        data_router = DataRouter(twelve_data_client=_twelve_data_client)
        set_data_router(data_router)
        print("[STARTUP] ✅ DataRouter initialized with Twelve Data client")
        
        # Self-check: verify router can get price (use async version since we're in async context)
        # This uses max_retries=0 (single-shot) -> should make exactly 1 HTTP request
        print("[STARTUP] Self-check: testing DataRouter.get_price_async('EURUSD') with single-shot mode (1 HTTP request expected)...")
        try:
            check_price, check_reason, check_source = await data_router.get_price_async("EURUSD")
            if check_price:
                print(f"[STARTUP] ✅ Self-check passed: EURUSD={check_price:.5f} (source={check_source}, single-shot: 1 HTTP request made)")
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


async def generate_channel_signals(bot: Optional[Bot], pairs: List[str], request_counter_ref: Optional[Dict] = None) -> None:
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
    
    # Track if FOREX source is unavailable (circuit breaker open)
    forex_unavailable = False
    
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
        
        # Skip FOREX channels if FOREX source is unavailable (circuit breaker)
        if asset_type == "FOREX" and forex_unavailable:
            print(f"⏸️ {channel_name}: Skipping - TwelveData cooldown active (FOREX source unavailable)")
            logger.info(f"[GENERATE_SIGNALS] {channel_name}: Skipping - TwelveData cooldown active")
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
        # For channels with few symbols (GOLD/INDEXES), allow multiple active signals per symbol
        allow_multiple = ALLOW_MULTIPLE_ACTIVE_PER_SYMBOL and len(symbols) <= 2
        available_pairs = get_available_pairs(symbols, channel_id=channel_id, allow_multiple=allow_multiple)
        if not available_pairs:
            print(f"⚠️ {channel_name}: No available pairs (all pairs already have active signals in this channel)")
            logger.warning(f"[GENERATE_SIGNALS] {channel_name}: No available pairs - all {len(symbols)} symbols have active signals")
            continue
        
        signals_generated = 0
        attempts = 0
        pairs_tried = set()  # Track which pairs we've actually tried (not just skipped)
        # Limit attempts: max 1 pass through all symbols, or signals_needed * 2 (whichever is smaller)
        max_attempts = min(len(available_pairs), signals_needed * 2) if signals_needed > 0 else len(available_pairs)
        
        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Starting generation - need {signals_needed} signals, max {max_attempts} attempts (from {len(available_pairs)} available pairs)")
        
        while signals_generated < signals_needed and attempts < max_attempts:
            # Check time constraints BEFORE requesting price
            can_send, reason = can_send_signal(channel_id, asset_type=asset_type)
            if not can_send:
                # Log explicit reason for skipping ONCE and exit channel generation
                logger.info(f"[GENERATE_SIGNALS] {channel_name}: Channel constraint active - {reason}, skipping channel generation")
                print(f"  ⏸️ {channel_name}: Skipping channel - constraint: {reason}")
                # Exit immediately - don't continue attempts or sleep in loop
                break
            
            # Cycle through available pairs (round-robin)
            sym = available_pairs[attempts % len(available_pairs)]
            attempts += 1
            pairs_tried.add(sym)
            
            print(f"📊 {channel_name}: Analyzing {sym} (attempt {attempts}/{max_attempts})...")
            try:
                # Get real-time price using data router
                # CRITICAL: Only 1 request to TwelveData per signal (no retries in generation)
                # For crypto, use Binance; for others, use data router
                asset_type = config.get("asset_type", "FOREX")
                is_crypto_channel = asset_type == "CRYPTO"
                
                # Track requests for this signal (must be exactly 1 for non-crypto)
                # PriceResult will be created below
                price_result = None
                
                try:
                    if is_crypto_channel:
                        # Crypto: use Binance directly (no TwelveData)
                        from working_combined_bot import get_real_crypto_price
                        rt_price = get_real_crypto_price(sym)
                        if rt_price:
                            source = "BINANCE"
                            reason = None
                        else:
                            rt_price = None
                            reason = "binance_unavailable"
                            source = "BINANCE"
                        
                        # Create PriceResult for crypto (always OK or FAILED, never SKIPPED)
                        price_result = PriceResult.create(rt_price, reason, source)
                    else:
                        # Forex/Index/Gold: use data router (TwelveData/Yahoo)
                        # CRITICAL: Only 1 request, no retries
                        data_router = get_data_router()
                        if data_router:
                            # Single request - no retries for signal generation
                            rt_price, reason, source = await data_router.get_price_async(sym)
                            
                            # Create PriceResult to determine status
                            price_result = PriceResult.create(rt_price, reason, source)
                            
                            # Update global request counter ONLY if we got a price (HTTP request succeeded)
                            # For TwelveData, increment only if price is not None (successful HTTP request)
                            if price_result.status == PriceStatus.OK and source == "TWELVE_DATA":
                                if request_counter_ref is not None:
                                    request_counter_ref["count"] = request_counter_ref.get("count", 0) + 1
                                    logger.debug(f"[GENERATE_SIGNALS] Request counter updated: {request_counter_ref['count']} (after successful HTTP request)")
                        else:
                            rt_price, reason, source = get_price(sym)
                            price_result = PriceResult.create(rt_price, reason, source)
                    
                    # Handle price result based on status
                    if price_result.status == PriceStatus.SKIPPED:
                        # SKIPPED: cooldown/quota/circuit breaker - not an error, just skip this symbol
                        reason_msg = f"Price skipped: {price_result.reason}"
                        if price_result.reason in {"twelve_data_cooldown", "circuit_breaker_open", "twelve_data_circuit_breaker_open", "cooldown"}:
                            reason_msg = f"Circuit breaker/cooldown active - TwelveData temporarily disabled"
                            # For FOREX channels: mark as unavailable and break from channel loop
                            if asset_type == "FOREX":
                                forex_unavailable = True
                                print(f"  ⏸️ {channel_name}: TwelveData cooldown active, skipping channel (will skip remaining FOREX channels)")
                                logger.info(f"[GENERATE_SIGNALS] {channel_name}: TwelveData cooldown active, stopping channel generation")
                                break  # Break from while loop for this channel
                        elif price_result.reason in {"rate_limit_429", "quota_exceeded", "rate_limited"}:
                            reason_msg = f"Rate limit/quota exceeded - TwelveData temporarily unavailable"
                            # For FOREX channels: mark as unavailable and break from channel loop
                            if asset_type == "FOREX":
                                forex_unavailable = True
                                print(f"  ⏸️ {channel_name}: TwelveData rate limited, skipping channel (will skip remaining FOREX channels)")
                                logger.info(f"[GENERATE_SIGNALS] {channel_name}: TwelveData rate limited, stopping channel generation")
                                break  # Break from while loop for this channel
                        
                        # Log skip (not error) and continue to next symbol
                        print(f"  ⏸️ {channel_name}: Skipping {sym} - {reason_msg}")
                        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Skipping {sym} - status=SKIPPED, reason={price_result.reason}")
                        continue
                    
                    elif price_result.status == PriceStatus.FAILED:
                        # FAILED: real error occurred - log and skip
                        reason_msg = f"Price unavailable: {price_result.reason}"
                        if price_result.reason == "twelve_data_unavailable":
                            reason_msg = f"TwelveData unavailable (error)"
                            # For FOREX channels: mark as unavailable and break from channel loop
                            if asset_type == "FOREX":
                                forex_unavailable = True
                                print(f"  ⏸️ {channel_name}: TwelveData unavailable, skipping channel (will skip remaining FOREX channels)")
                                logger.warning(f"[GENERATE_SIGNALS] {channel_name}: TwelveData unavailable, stopping channel generation")
                                break  # Break from while loop for this channel
                        elif price_result.reason == "binance_unavailable":
                            reason_msg = f"Binance unavailable"
                        elif price_result.reason == "yahoo_unavailable":
                            reason_msg = f"Yahoo Finance unavailable"
                        
                        print(f"  ⏸️ {channel_name}: Skipping {sym} - {reason_msg}")
                        logger.warning(f"[GENERATE_SIGNALS] {channel_name}: Skipping {sym} - status=FAILED, reason={price_result.reason}")
                        continue
                    
                    # OK: price is available
                    if price_result.price is None:
                        # This should not happen if status == OK, but defensive check
                        logger.error(f"[GENERATE_SIGNALS] {channel_name}: PriceResult.status=OK but price is None for {sym}")
                        continue
                    
                    rt_price = price_result.price
                    
                    entry = rt_price
                    # Determine request count for logging (only for successful HTTP requests)
                    request_count_for_log = 1 if (price_result.status == PriceStatus.OK and source == "TWELVE_DATA" and not is_crypto_channel) else 0
                    logger.info(f"[GENERATE_SIGNALS] {channel_name}: {sym} price={entry:.5f} (source={source}, status={price_result.status.value}, requests={request_count_for_log})")
                    print(f"  Real-time entry price: {entry} (source: {source}, status: {price_result.status.value})")
                except Exception as e:
                    logger.exception(f"[GENERATE_SIGNALS] {channel_name}: Failed to get price for {sym}: {type(e).__name__}: {e}")
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
                    reason_msg = f"Cannot send {clean_sym} - both BUY and SELL blocked by 24h rule"
                    print(f"  ⏸️ {channel_name}: Skipping {clean_sym} - reason=active_signal, {reason_msg}")
                    logger.info(f"[GENERATE_SIGNALS] {channel_name}: Skipping {clean_sym} - reason=active_signal, {reason_msg}")
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
                
                # CRITICAL: Determine publish status BEFORE attempting to send
                # Order: 1) Generate draft, 2) Try to publish, 3) Save only if published
                publish_status = "skipped"  # Default: skipped (will be updated based on result)
                publish_reason = None
                telegram_sent = False
                
                if bot is not None:
                    print(f"📤 {channel_name}: Sending signal to Telegram (channel_id={channel_id}): {msg}")
                    logger.info(f"[PUBLISH] {channel_name}: Attempting to publish signal (channel_id={channel_id})")
                    try:
                        send_success = await safe_send_message(bot, chat_id=channel_id, text=msg, disable_web_page_preview=True)
                        if send_success:
                            publish_status = "published"
                            publish_reason = "success"
                            telegram_sent = True
                            print(f"✅ {channel_name}: Signal published successfully to Telegram")
                            logger.info(f"[PUBLISH] {channel_name}: status=published, reason=success")
                        else:
                            publish_status = "failed"
                            publish_reason = "send_message_returned_false"
                            print(f"❌ {channel_name}: Failed to publish signal to Telegram (send_message returned False)")
                            logger.warning(f"[PUBLISH] {channel_name}: status=failed, reason={publish_reason}")
                            # Skip saving if Telegram send failed (signal not actually published)
                            continue
                    except Exception as e:
                        publish_status = "failed"
                        publish_reason = f"exception_{type(e).__name__}"
                        print(f"❌ {channel_name}: Exception while publishing signal: {type(e).__name__}: {e}")
                        logger.error(f"[PUBLISH] {channel_name}: status=failed, reason={publish_reason}, error={e!r}")
                        # Skip saving if exception occurred (signal not actually published)
                        continue
                else:
                    publish_status = "skipped"
                    publish_reason = "bot_is_none"
                    print(f"📝 {channel_name}: Generated signal draft (Telegram disabled, bot=None): {msg}")
                    logger.warning(f"[PUBLISH] {channel_name}: status=skipped, reason={publish_reason}")
                    # Skip saving if bot is None (signal not actually published)
                    continue
                
                # CRITICAL: Save signal ONLY if successfully published (publish_status == "published")
                if publish_status == "published":
                    # Save signal with explicit publish_status
                    add_signal(sym, signal_type, entry, sl, tp1, tp2, tp3=tp3, channel_id=channel_id, publish_status="published")
                    
                    # Verify signal was saved and counted
                    new_count = get_today_channel_signals_count(channel_id)
                    logger.info(f"[GENERATE_SIGNALS] {channel_name}: Signal saved - total published today: {new_count}/{max_signals}")
                    
                    # Update time constraints ONLY after successful publication
                    save_last_signal_time()
                    save_channel_last_signal_time(channel_id, asset_type=asset_type)
                    save_channel_pair_direction_last_signal_time(channel_id, clean_sym, signal_type)
                    logger.info(f"[GENERATE_SIGNALS] {channel_name}: Constraints updated after successful publication")
                    
                    signals_generated += 1
                    print(f"✅ {channel_name}: Published signal {signals_generated}/{signals_needed}: {sym} {signal_type} (total published today: {new_count}/{max_signals})")
                    
                    # Double-check: if we've reached the limit, stop generating for this channel
                    if new_count >= max_signals:
                        print(f"✅ {channel_name}: Daily limit reached after this signal ({new_count}/{max_signals})")
                        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Daily limit reached, stopping generation for this channel")
                        break
                else:
                    # Signal was not published - log but don't save
                    logger.warning(f"[GENERATE_SIGNALS] {channel_name}: Signal NOT saved (publish_status={publish_status}, reason={publish_reason})")
                    print(f"⚠️ {channel_name}: Signal draft generated but NOT published (status={publish_status}, reason={publish_reason})")
                
                # Remove pair from available (even if not published, to avoid retrying same pair immediately)
                if sym in available_pairs:
                    available_pairs.remove(sym)
                
                # Wait before next signal (respect time constraints)
                await asyncio.sleep(5)
                
            except Exception as e:
                error_msg = f"Error processing {sym}: {type(e).__name__}: {e}"
                print(f"  ❌ {channel_name}: {error_msg}")
                logger.exception(f"[GENERATE_SIGNALS] {channel_name}: {error_msg}")
                # Continue to next pair (don't break the loop)
                await asyncio.sleep(1)
        
        # Log summary for this channel
        logger.info(f"[GENERATE_SIGNALS] {channel_name}: Finished - generated {signals_generated}/{signals_needed} signals, attempts={attempts}, pairs_tried={len(pairs_tried)}")
        print(f"🏁 {channel_name}: Finished. Generated {signals_generated}/{signals_needed} signals (attempts: {attempts}, pairs tried: {len(pairs_tried)})")


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


async def smoke_test(test_chat_id: Optional[str] = None) -> bool:
    """
    Smoke test: verify Telegram bot and signal generation.
    
    Args:
        test_chat_id: Optional test chat ID to send test message
    
    Returns:
        True if all tests passed, False otherwise
    """
    print("\n" + "="*60)
    print("[SMOKE_TEST] Starting smoke test...")
    print("="*60)
    
    # Test 1: Telegram bot initialization
    print("\n[SMOKE_TEST] Test 1: Telegram bot initialization")
    try:
        bot = await create_telegram_bot_with_check()
        if bot:
            print("  ✅ Telegram bot initialized successfully")
            telegram_enabled = True
        else:
            print("  ⚠️ Telegram bot is None (DRY_RUN mode or no token)")
            telegram_enabled = False
    except RuntimeError as e:
        print(f"  ❌ Telegram bot initialization failed: {e}")
        telegram_enabled = False
    
    # Test 2: Send test message (if test_chat_id provided)
    if telegram_enabled and test_chat_id:
        print(f"\n[SMOKE_TEST] Test 2: Sending test message to {test_chat_id}")
        try:
            test_msg = "🧪 Smoke test message from signalsbot"
            success = await safe_send_message(bot, chat_id=test_chat_id, text=test_msg)
            if success:
                print("  ✅ Test message sent successfully")
            else:
                print("  ❌ Failed to send test message")
        except Exception as e:
            print(f"  ❌ Error sending test message: {type(e).__name__}: {e}")
    
    # Test 3: Check active signals and TTL
    print("\n[SMOKE_TEST] Test 3: Active signals TTL check")
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_signals = [s for s in active_signals if s.get("date") == today]
    active_count = len([s for s in today_signals if s.get("status") == "active"])
    expired_count = close_expired_signals()
    print(f"  Total signals today: {len(today_signals)}")
    print(f"  Active signals: {active_count}")
    print(f"  Expired signals closed: {expired_count}")
    print(f"  TTL: {ACTIVE_SIGNAL_TTL_MINUTES} minutes")
    
    # Test 4: Available pairs check
    print("\n[SMOKE_TEST] Test 4: Available pairs check")
    test_pairs = ["EURUSD", "GBPUSD", "USDJPY"]
    available_before = get_available_pairs(test_pairs, channel_id=None, allow_multiple=False)
    print(f"  Test pairs: {test_pairs}")
    print(f"  Available pairs (before TTL): {len(available_before)} - {available_before}")
    
    # Close expired and check again
    close_expired_signals()
    available_after = get_available_pairs(test_pairs, channel_id=None, allow_multiple=False)
    print(f"  Available pairs (after TTL): {len(available_after)} - {available_after}")
    
    print("\n" + "="*60)
    print("[SMOKE_TEST] Smoke test completed")
    print("="*60 + "\n")
    
    return telegram_enabled


async def main_async():
    """
    Main async entrypoint - runs forever until interrupted (Ctrl+C)
    
    Bot operates as a service:
    - Infinite loop (while True) - never exits unless Ctrl+C
    - Generates signals every 60 seconds
    - All exceptions are caught and logged, bot continues running
    - TP/SL monitoring is DISABLED (only signal generation)
    - TwelveData circuit breaker prevents excessive requests when API is down
    - Client cleanup only happens in finally block (on process termination)
    
    Error handling:
    - Signal generation errors: logged, wait 10s, continue
    - Unexpected errors: logged, wait 10s, continue
    - KeyboardInterrupt (Ctrl+C): graceful shutdown
    """
    # Migrate state files first (fix old format if needed)
    migrate_state_files()
    
    # CRITICAL: Clear signals for today on bot startup to reset daily counters
    # This ensures that when bot is restarted, it starts with fresh counters for the day
    cleared_count = clear_today_signals()
    if cleared_count > 0:
        print(f"[STARTUP] Daily counters reset: {cleared_count} signals cleared for today")
    
    # Initialize Twelve Data client for FOREX
    twelve_data_init_success = await startup_init()
    
    if not twelve_data_init_success:
        print("⚠️ [MAIN] Twelve Data initialization failed - FOREX signals may be unavailable")
        print("   Bot will continue working, but FOREX pairs may fail")
    
    # Create Telegram bot once (with strict validation)
    bot = await create_telegram_bot_with_check()
    if not bot:
        if DRY_RUN:
            logger.warning("[MAIN] ⚠️ Telegram bot not available - DRY_RUN mode, continuing without Telegram send")
        else:
            # This should not happen if token is provided (create_telegram_bot_with_check exits on error)
            logger.error("[MAIN] ❌ FATAL: Telegram bot is None but token was provided")
            logger.error("[MAIN] This should not happen - bot creation should have failed earlier")
            sys.exit(1)
    
    pairs = DEFAULT_PAIRS
    
    # Track last execution time for signal generation
    last_signal_generation_time = 0.0
    
    # Signal generation interval: 60 seconds
    SIGNAL_GENERATION_INTERVAL = 60.0
    
    # Global counter for TwelveData requests per cycle
    twelve_data_requests_count = 0
    
    print("[MAIN] 🤖 Bot started - running forever (Ctrl+C to stop)")
    print("[MAIN] ⚠️ TP/SL monitoring DISABLED - only signal generation enabled")
    print(f"[MAIN] Signal generation interval: {SIGNAL_GENERATION_INTERVAL}s")
    
    try:
        while True:
            try:
                current_time = time.time()
                
                # Generate signals every 60 seconds
                if current_time - last_signal_generation_time >= SIGNAL_GENERATION_INTERVAL:
                    try:
                        print("[MAIN] 📊 Generating signals for all channels...")
                        logger.info("[MAIN] Starting signal generation cycle")
                        
                        # Pass mutable dict for request counter
                        request_counter = {"count": 0}
                        await generate_channel_signals(bot, pairs, request_counter_ref=request_counter)
                        
                        # Log request count after generation
                        actual_count = request_counter.get("count", 0)
                        logger.info(f"[MAIN] ✅ Cycle completed: TwelveData requests used: {actual_count}")
                        print(f"[MAIN] ✅ Cycle completed: TwelveData requests: {actual_count}")
                        print(f"[MAIN] Bot is alive and running (next cycle in {SIGNAL_GENERATION_INTERVAL}s)")
                        
                        last_signal_generation_time = current_time
                    except Exception as e:
                        logger.exception(f"[MAIN] Error in signal generation: {type(e).__name__}: {e}")
                        print(f"[MAIN] ⚠️ Error in signal generation, waiting 10 seconds before next cycle...")
                        await asyncio.sleep(10)  # Wait before retrying next cycle
                        # Continue loop even if signal generation fails
                    finally:
                        # Ensure we wait full interval before next cycle
                        # This prevents rapid retries if generation completes quickly
                        pass
                
                # Sleep 1 second between iterations to prevent high CPU usage
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                # Ctrl+C - break out of loop gracefully
                print("\n[MAIN] ⏹️ Received KeyboardInterrupt (Ctrl+C) - shutting down gracefully...")
                break
            except Exception as e:
                # Catch any unexpected exceptions and log them, but continue running
                logger.exception(f"[MAIN] Unexpected error in main loop: {type(e).__name__}: {e}")
                print(f"[MAIN] ⚠️ Error occurred: {type(e).__name__}: {e}")
                print(f"[MAIN] Waiting 10 seconds before continuing...")
                await asyncio.sleep(10)  # Wait 10 seconds before retrying
                
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
    # Check for smoke test mode
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "smoke_test":
        # Run smoke test
        test_chat_id = os.getenv("TEST_CHAT_ID")
        asyncio.run(smoke_test(test_chat_id=test_chat_id))
        sys.exit(0)
    
    # Run normal bot
    import sys
    if "--ctrader-auth-test" in sys.argv:
        # Run authentication test only
        success = asyncio.run(ctrader_auth_test())
        sys.exit(0 if success else 1)
    else:
        # Run normal bot
        asyncio.run(main_async())