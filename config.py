"""
Configuration settings for Signals_bot
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Dict
from types import SimpleNamespace

# ============================================================================
# HARDCODED CTRADER CONFIGURATION (Source of Truth)
# ============================================================================
# Set to True to use hardcoded values instead of .env
CTRADER_HARDCODED_ENABLED = True

# Hardcoded cTrader configuration values
HARDCODED_CTRADER_CONFIG = {
    'is_demo': True,
    'account_id': 44749280,
    'client_id': '17667_hKA21RsOIjvIT45QG9Q9GTcot9Coiy7VeNOFaJQLFPeGyUQmBN',
    'client_secret': 'amV88gmO8jTayhPVR7t4Q2VsRmEqbW8Xg5A4dOF2Ag1E13d4Jl',
    'access_token': 'n_SuXHNX4TlMyekW05N_yqwNy4Y_Zc3DAIwEXVrp2os',
    'refresh_token': 'UVNGZPSDSbB-Vi81R2DX8NANvIkESfE_yXnNS6z1RC4',
    'ws_url_demo': 'wss://demo.ctraderapi.com:5035',
    'ws_url_live': 'wss://live.ctraderapi.com:5035',
    'gold_ctrader_only': True,
    'gold_symbol_name': None,  # Auto-detect from symbol list
    'gold_symbol_id': None,    # Auto-detect from symbol list
}

def _safe_preview(value: str, length: int = 8) -> str:
    """Create safe preview of sensitive value"""
    if not value:
        return "(not set)"
    if len(value) <= length:
        return value[:length] + "..."
    return value[:length] + "..."

# Determine project root (signalsbot directory)
# config.py is in project root, so __file__ is already there
_project_root = Path(__file__).resolve().parent
_dotenv_path = _project_root / ".env"
_config_live_path = _project_root / "config_live.env"

# Load environment variables from project root (override=True to ensure fresh load)
# Note: working_combined_bot.py loads .env first, but we reload here for safety
_env_loaded = load_dotenv(dotenv_path=_dotenv_path, override=True, encoding="utf-8")
_env_live_loaded = False
if _config_live_path.exists():
    _env_live_loaded = load_dotenv(dotenv_path=_config_live_path, override=True, encoding="utf-8")

# Debug: Print critical keys immediately after load_dotenv
print("[CONFIG] After load_dotenv:")
print(f"  CTRADER_IS_DEMO: {repr(os.getenv('CTRADER_IS_DEMO'))}")
print(f"  CTRADER_ACCOUNT_ID: {repr(os.getenv('CTRADER_ACCOUNT_ID'))}")
print(f"  CTRADER_DEMO_WS_URL: {repr(os.getenv('CTRADER_DEMO_WS_URL'))}")
print(f"  dotenv_path: {_dotenv_path} (exists={_dotenv_path.exists()})")
print()

# Helper functions for reading environment variables with validation
def get_env_str(name: str, default: Optional[str] = None, required: bool = False, strip: bool = True) -> Optional[str]:
    """Get environment variable as string with validation
    
    Args:
        name: Environment variable name
        default: Default value if not set (None if not provided)
        required: If True, raise ValueError if missing
        strip: If True, strip whitespace from value
    
    Returns:
        String value or None if not set and not required
    
    Raises:
        ValueError: If required=True and variable is missing or empty
    """
    value = os.getenv(name)
    
    if value is None:
        if required:
            raise ValueError(f"Required environment variable {name} is not set")
        return default
    
    if strip:
        value = value.strip()
    
    # Empty string after strip is treated as None
    if value == "":
        if required:
            raise ValueError(f"Required environment variable {name} is empty")
        return default
    
    return value

def get_env_bool(name: str, default: bool = False) -> bool:
    """Get environment variable as boolean
    
    Args:
        name: Environment variable name
        default: Default value if not set
    
    Returns:
        Boolean value
    """
    value = os.getenv(name)
    if not value:
        return default
    
    value = value.strip().lower()
    return value in ('true', '1', 'yes', 'on')

def get_env_int(name: str, default: int = 0, required: bool = False) -> int:
    """Get environment variable as integer with validation
    
    Args:
        name: Environment variable name
        default: Default value if not set
        required: If True, raise ValueError if missing or invalid
    
    Returns:
        Integer value
    
    Raises:
        ValueError: If required=True and variable is missing, empty, or not a valid integer
    """
    value = os.getenv(name)
    
    if not value or not value.strip():
        if required:
            raise ValueError(f"Required environment variable {name} is not set or empty")
        return default
    
    value = value.strip()
    
    # Check for placeholder values
    if value.lower() in ('your_demo_account_id', 'your_account_id', 'your_client_id', 
                         'your_client_secret', 'your_access_token', 'your_refresh_token',
                         'your_bot_token_here', 'your_test_channel', 'your_finnhub_api_key_here'):
        if required:
            raise ValueError(f"Environment variable {name} appears to be a placeholder: {value}")
        return default
    
    try:
        return int(value)
    except ValueError:
        if required:
            raise ValueError(f"Environment variable {name} is not a valid integer: {value}")
        return default


# Unified parser functions for Config class
def _parse_bool_env(name: str, default: bool = False) -> bool:
    """Parse boolean environment variable
    
    Args:
        name: Environment variable name
        default: Default value if not set
    
    Returns:
        Boolean value
    """
    return get_env_bool(name, default)


def _parse_int_env(name: str, default: Optional[int] = None, required: bool = False) -> int:
    """Parse integer environment variable
    
    Args:
        name: Environment variable name
        default: Default value if not set (None means 0)
        required: If True, raise ValueError if missing
    
    Returns:
        Integer value
    
    Raises:
        ValueError: If required=True and variable is missing or invalid
    """
    if default is None:
        default = 0
    return get_env_int(name, default=default, required=required)


def _get_str_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get string environment variable
    
    Args:
        name: Environment variable name
        default: Default value if not set
        required: If True, raise ValueError if missing
    
    Returns:
        String value or None
    
    Raises:
        ValueError: If required=True and variable is missing
    """
    return get_env_str(name, default=default, required=required, strip=True)

# Self-heal: if python-dotenv didn't load CTRADER_* keys, try manual parsing
def _self_heal_env_loading():
    """Self-heal .env loading if python-dotenv missed keys due to encoding/BOM issues"""
    # Check if critical keys are missing
    critical_keys = ['CTRADER_DEMO_WS_URL', 'CTRADER_IS_DEMO', 'CTRADER_ACCOUNT_ID']
    missing_keys = [key for key in critical_keys if not os.getenv(key)]
    
    if not missing_keys:
        return  # All critical keys loaded, no need to heal
    
    if not _dotenv_path.exists():
        return  # File doesn't exist
    
    try:
        # Read file as bytes
        with open(_dotenv_path, 'rb') as f:
            raw_bytes = f.read()
        
        # Try different encodings
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1251', 'latin-1']
        file_content = None
        detected_encoding = None
        
        for encoding in encodings_to_try:
            try:
                file_content = raw_bytes.decode(encoding)
                detected_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
        
        if not file_content:
            print(f"[ENV] Self-heal failed: Could not decode .env file")
            return
        
        # Manual parse (same logic as env_doctor.py)
        lines = file_content.splitlines()
        loaded_keys = []
        
        for line in lines:
            # Skip empty lines and comments
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            
            # Split by first '='
            if '=' not in stripped:
                continue
            
            parts = stripped.split('=', 1)
            if len(parts) != 2:
                continue
            
            key_raw = parts[0]
            value_raw = parts[1]
            
            # Normalize key (remove BOM, whitespace, \r\n)
            key_normalized = key_raw.strip().lstrip('\ufeff').rstrip('\r\n').rstrip()
            
            # Normalize value
            value_normalized = value_raw.strip()
            # Remove quotes
            if value_normalized.startswith('"') and value_normalized.endswith('"'):
                value_normalized = value_normalized[1:-1]
            elif value_normalized.startswith("'") and value_normalized.endswith("'"):
                value_normalized = value_normalized[1:-1]
            
            # Only set if not already in environment (python-dotenv takes precedence)
            if key_normalized.startswith('CTRADER_') and not os.getenv(key_normalized):
                os.environ[key_normalized] = value_normalized
                loaded_keys.append(key_normalized)
        
        if loaded_keys:
            print(f"[ENV] Fallback parser loaded keys: {', '.join(loaded_keys)}")
            print(f"[ENV] Used encoding: {detected_encoding}")
    
    except Exception as e:
        print(f"[ENV] Self-heal failed: {e}")
        import traceback
        print(traceback.format_exc())

# Run self-heal
_self_heal_env_loading()

# Diagnostic: Log ENV keys status on startup
def _log_env_diagnostics():
    """Log ENV keys diagnostic on startup"""
    critical_keys = [
        'CTRADER_IS_DEMO',
        'CTRADER_ACCOUNT_ID',
        'CTRADER_CLIENT_ID',
        'CTRADER_CLIENT_SECRET',
        'CTRADER_ACCESS_TOKEN',
        'CTRADER_REFRESH_TOKEN',
        'CTRADER_DEMO_WS_URL',
        'CTRADER_LIVE_WS_URL',
        'GOLD_CTRADER_ONLY'
    ]
    
    print("=" * 80)
    print("[ENV_DIAGNOSTIC] cTrader Configuration Keys Status")
    print("=" * 80)
    print(f"dotenv_path: {_dotenv_path} (exists={_dotenv_path.exists()})")
    print(f"project_root: {_project_root}")
    print(f"cwd: {os.getcwd()}")
    print()
    
    key_status = {}
    for key in critical_keys:
        value = os.getenv(key)
        is_set = value is not None and value.strip() != ''
        key_status[key] = is_set
        # Show preview for sensitive keys (first 8 chars)
        def safe_preview(val: str, length: int = 8) -> str:
            """Create safe preview of sensitive value"""
            if not val:
                return "(not set)"
            if len(val) <= length:
                return val[:length] + "..."
            return val[:length] + "..."
        
        if key in ['CTRADER_CLIENT_ID', 'CTRADER_CLIENT_SECRET', 'CTRADER_ACCESS_TOKEN', 'CTRADER_REFRESH_TOKEN']:
            preview = safe_preview(value, 8) if value else "(not set)"
            print(f"  {key}: {'[OK]' if is_set else '[MISSING]'} (preview: {preview})")
        else:
            preview_val = safe_preview(value, 20) if value else '(not set)'
            print(f"  {key}: {'[OK]' if is_set else '[MISSING]'} (value: {preview_val})")
    
    print()
    missing_keys = [k for k, v in key_status.items() if not v and k != 'CTRADER_GOLD_SYMBOL_ID']  # GOLD_SYMBOL_ID is optional
    if missing_keys:
        print(f"[WARNING] Missing keys: {', '.join(missing_keys)}")
        print(f"  -> These keys will use defaults or cause initialization to fail")
    else:
        print("[OK] All critical keys are set")
    print("=" * 80)
    print()

# Run diagnostics on module load
_log_env_diagnostics()

# Log environment loading status
def _log_env_status():
    """Log environment loading status for diagnostics"""
    cwd = os.getcwd()
    print(f"[ENV] cwd={cwd}")
    print(f"[ENV] project_root={_project_root}")
    print(f"[ENV] dotenv_path={_dotenv_path} (exists={_dotenv_path.exists()})")
    print(f"[ENV] config_live_path={_config_live_path} (exists={_config_live_path.exists()})")
    
    # Check for key variables (only presence, not values)
    key_vars = [
        'CTRADER_DEMO_WS_URL',
        'CTRADER_LIVE_WS_URL',
        'CTRADER_IS_DEMO',
        'CTRADER_ACCOUNT_ID',
        'CTRADER_CLIENT_ID',
        'CTRADER_CLIENT_SECRET',
        'CTRADER_ACCESS_TOKEN',
    ]
    
    loaded_keys = {}
    for key in key_vars:
        value = os.getenv(key, '')
        loaded_keys[key] = bool(value and value.strip())
    
    print(f"[ENV] loaded_keys_present = {loaded_keys}")
    
    # Show preview of sensitive values (not full values)
    def _preview_val(key):
        val = os.getenv(key, '')
        if not val:
            return False
        if len(val) <= 10:
            return f"{val[:8]}..."
        return f"{val[:8]}..."
    
    print(f"[ENV] CTRADER_DEMO_WS_URL preview: {_preview_val('CTRADER_DEMO_WS_URL')}")
    print(f"[ENV] CTRADER_CLIENT_ID preview: {_preview_val('CTRADER_CLIENT_ID')}")

# Log on import (can be called again if needed)
_log_env_status()


def _normalize_env_var(key: str, fallbacks: list = None) -> str:
    """Normalize environment variable with fallbacks
    
    Args:
        key: Primary environment variable name
        fallbacks: List of fallback variable names to try
    
    Returns:
        First non-empty value found, or empty string
    """
    value = os.getenv(key, '').strip()
    if value:
        return value
    
    if fallbacks:
        for fallback in fallbacks:
            fallback_value = os.getenv(fallback, '').strip()
            if fallback_value:
                return fallback_value
    
    return ''


def _is_placeholder(value: str) -> bool:
    """Check if value looks like a placeholder/example value
    
    Args:
        value: Value to check
    
    Returns:
        True if value appears to be a placeholder
    """
    if not value:
        return False
    
    value_lower = value.lower()
    placeholder_patterns = [
        'your_',
        'example',
        'placeholder',
        'replace_me',
        'set_this',
    ]
    
    return any(pattern in value_lower for pattern in placeholder_patterns)


def _safe_preview(value: str, length: int = 8) -> str:
    """Create safe preview of sensitive value
    
    Args:
        value: Value to preview
        length: Number of characters to show
    
    Returns:
        Preview string (e.g., "abc12345...")
    """
    if not value:
        return "(not set)"
    if len(value) <= length:
        return value[:length] + "..."
    return value[:length] + "..."

def _parse_bool(value: str, default: bool = False) -> bool:
    """Parse boolean from string
    
    Args:
        value: String value to parse
        default: Default value if value is empty/None
    
    Returns:
        bool value
    """
    if not value:
        return default
    return value.lower().strip() in ('true', '1', 'yes', 'on')


def _parse_ctrader_is_demo() -> bool:
    """Parse CTRADER_IS_DEMO strictly from {"true","false","1","0","yes","no"} (case-insensitive)"""
    value = os.getenv('CTRADER_IS_DEMO', '').strip().lower()
    if value in ('true', '1', 'yes', 'on'):
        return True
    elif value in ('false', '0', 'no', 'off'):
        return False
    else:
        # Default to True if not set or invalid
        return True


class Config:
    """Configuration class for the Signals bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # cTrader API Configuration (STRICT: only CTRADER_* keys, no fallbacks)
    CTRADER_CLIENT_ID: str = os.getenv('CTRADER_CLIENT_ID', '')
    CTRADER_CLIENT_SECRET: str = os.getenv('CTRADER_CLIENT_SECRET', '')
    CTRADER_REDIRECT_URI: str = os.getenv('CTRADER_REDIRECT_URI', 'http://localhost:8080/callback')
    CTRADER_ACCESS_TOKEN: str = os.getenv('CTRADER_ACCESS_TOKEN', '')
    CTRADER_REFRESH_TOKEN: str = os.getenv('CTRADER_REFRESH_TOKEN', '')
    CTRADER_API_URL: str = 'https://openapi.ctrader.com'
    CTRADER_AUTH_URL: str = 'https://connect.spotware.com/apps'
    
    # Account Configuration (STRICT: only CTRADER_ACCOUNT_ID)
    CTRADER_ACCOUNT_ID: str = os.getenv('CTRADER_ACCOUNT_ID', '')
    
    # WebSocket URLs (optional, with safe defaults)
    CTRADER_DEMO_WS_URL: str = os.getenv('CTRADER_DEMO_WS_URL', '')
    CTRADER_LIVE_WS_URL: str = os.getenv('CTRADER_LIVE_WS_URL', '')
    CTRADER_IS_DEMO: bool = _parse_bool(os.getenv('CTRADER_IS_DEMO', 'true'), default=True)
    
    # Gold symbol configuration (optional override)
    GOLD_SYMBOL_NAME: str = os.getenv('GOLD_SYMBOL_NAME', '').strip()  # Manual override (e.g., "GOLD", "XAUUSDm")
    
    # Gold price source (strictly cTrader only by default)
    GOLD_CTRADER_ONLY: bool = _parse_bool(os.getenv('GOLD_CTRADER_ONLY', 'true'), default=True)
    
    # cTrader WebSocket connection timeout (seconds)
    CTRADER_WS_CONNECT_TIMEOUT: int = int(os.getenv('CTRADER_WS_CONNECT_TIMEOUT', '60'))
    CTRADER_WS_RETRY_COUNT: int = int(os.getenv('CTRADER_WS_RETRY_COUNT', '3'))
    
    @classmethod
    def get_ctrader_ws_url(cls) -> tuple[str, str]:
        """Get cTrader WebSocket URL (delegates to unified config)
        
        Returns:
            Tuple of (ws_url, source_var_name)
        """
        config = cls.get_ctrader_config()
        return config.get_ws_url()
    
    # Legacy: DEMO_ACCOUNT_ID (deprecated, use CTRADER_ACCOUNT_ID)
    # Kept for backward compatibility - returns CTRADER_ACCOUNT_ID
    @property
    def DEMO_ACCOUNT_ID(self) -> str:
        """Legacy property for backward compatibility"""
        return self.CTRADER_ACCOUNT_ID
    
    # Channel Configuration
    TEST_CHANNEL_ID: str = os.getenv('TEST_CHANNEL_ID', '')
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Finnhub API Configuration
    FINNHUB_API_KEY: str = os.getenv('FINNHUB_API_KEY', 'd4n9uthr01qsn6gach50d4n9uthr01qsn6gach5g')
    
    # Auto Signal Configuration
    AUTO_SIGNAL_INTERVAL: int = int(os.getenv('AUTO_SIGNAL_INTERVAL', '240'))  # 4 minutes
    SL_PIPS: int = int(os.getenv('SL_PIPS', '30'))
    TP_PIPS: int = int(os.getenv('TP_PIPS', '50'))
    
    # Feature flag for hardcoded config (TEMP ONLY — remove before production)
    USE_HARDCODED_CTRADER_CONFIG: bool = os.getenv('USE_HARDCODED_CTRADER_CONFIG', 'false').lower() in ('true', '1', 'yes')
    
    @classmethod
    def _parse_ctrader_is_demo(cls) -> bool:
        """Parse CTRADER_IS_DEMO - returns hardcoded value if enabled, otherwise parses from env"""
        if CTRADER_HARDCODED_ENABLED:
            return HARDCODED_CTRADER_CONFIG['is_demo']
        return _parse_ctrader_is_demo()  # Call module-level function
    
    @classmethod
    def validate_account_id(cls) -> tuple[Optional[int], Optional[str]]:
        """Validate account ID and return parsed value or error reason
        
        Returns:
            Tuple of (account_id_int, error_reason_code)
            - If valid: (int, None)
            - If invalid: (None, reason_code)
        """
        # Priority 1: Hardcoded config
        if CTRADER_HARDCODED_ENABLED:
            account_id = HARDCODED_CTRADER_CONFIG['account_id']
            if account_id <= 0:
                return None, "CONFIG_INVALID_ACCOUNT_ID"
            return account_id, None
        
        # Priority 2: Environment variables
        account_id_str = os.getenv('CTRADER_ACCOUNT_ID', '').strip()
        
        # Check if empty
        if not account_id_str:
            return None, "CONFIG_INVALID_ACCOUNT_ID"
        
        # Check if placeholder
        if _is_placeholder(account_id_str):
            return None, "CONFIG_INVALID_ACCOUNT_ID"
        
        # Try to parse as integer
        try:
            account_id = int(account_id_str)
            if account_id <= 0:
                return None, "CONFIG_INVALID_ACCOUNT_ID"
            return account_id, None
        except ValueError:
            return None, "CONFIG_INVALID_ACCOUNT_ID"
    
    @classmethod
    def get_account_id_or_raise(cls) -> int:
        """Get account ID or raise ValueError if missing/invalid"""
        account_id, error_reason = cls.validate_account_id()
        if error_reason:
            raw_value = os.getenv('CTRADER_ACCOUNT_ID')
            raise ValueError(f"CTRADER_ACCOUNT_ID is missing or invalid. Got: {repr(raw_value)}")
        return account_id
    
    @classmethod
    def get_ws_url_or_raise(cls, is_demo: bool) -> str:
        """Get WebSocket URL or raise ValueError if missing
        
        Args:
            is_demo: If True, use CTRADER_DEMO_WS_URL, else CTRADER_LIVE_WS_URL
        
        Returns:
            WebSocket URL string
        
        Raises:
            ValueError: If the required WS URL is missing or empty
        """
        if is_demo:
            ws_url = os.getenv('CTRADER_DEMO_WS_URL', '').strip()
            key_name = 'CTRADER_DEMO_WS_URL'
            default_url = "wss://demo.ctraderapi.com:5035"
        else:
            ws_url = os.getenv('CTRADER_LIVE_WS_URL', '').strip()
            key_name = 'CTRADER_LIVE_WS_URL'
            default_url = "wss://live.ctraderapi.com:5035"
        
        if not ws_url:
            # Use default but log warning
            print(f"[CONFIG] {key_name} missing -> using default {default_url}")
            return default_url
        
        return ws_url
    
    @classmethod
    def get_ctrader_config(cls):
        """Get unified cTrader configuration object (hardcoded or from ENV)
        
        Returns:
            CTraderConfig-like object with all cTrader settings and source_map
        """
        # Priority 1: Hardcoded config (if enabled)
        if CTRADER_HARDCODED_ENABLED:
            return cls._get_hardcoded_ctrader_config()
        
        # Priority 2: Legacy hardcoded config file (if USE_HARDCODED_CTRADER_CONFIG flag is set)
        if cls.USE_HARDCODED_CTRADER_CONFIG:
            try:
                from config_hardcoded import _hardcoded_config
                return _hardcoded_config
            except ImportError:
                print("[CONFIG] WARNING: USE_HARDCODED_CTRADER_CONFIG=true but config_hardcoded.py not found, falling back to ENV")
                return cls._get_env_ctrader_config()
        
        # Priority 3: Environment variables
        return cls._get_env_ctrader_config()
    
    @classmethod
    def _get_hardcoded_ctrader_config(cls):
        """Get hardcoded cTrader configuration (source of truth)
        
        Returns:
            SimpleNamespace object with all cTrader settings and source_map
        """
        config = SimpleNamespace()
        
        # Copy all hardcoded values
        config.is_demo = HARDCODED_CTRADER_CONFIG['is_demo']
        config.account_id = HARDCODED_CTRADER_CONFIG['account_id']
        config.client_id = HARDCODED_CTRADER_CONFIG['client_id']
        config.client_secret = HARDCODED_CTRADER_CONFIG['client_secret']
        config.access_token = HARDCODED_CTRADER_CONFIG['access_token']
        config.refresh_token = HARDCODED_CTRADER_CONFIG['refresh_token']
        config.ws_url_demo = HARDCODED_CTRADER_CONFIG['ws_url_demo']
        config.ws_url_live = HARDCODED_CTRADER_CONFIG['ws_url_live']
        config.gold_ctrader_only = HARDCODED_CTRADER_CONFIG['gold_ctrader_only']
        config.gold_symbol_name_override = HARDCODED_CTRADER_CONFIG.get('gold_symbol_name')
        config.gold_symbol_id = HARDCODED_CTRADER_CONFIG.get('gold_symbol_id')
        
        # API URLs (hardcoded)
        config.base_url = cls.CTRADER_API_URL
        config.api_url = cls.CTRADER_API_URL
        config.auth_url = cls.CTRADER_AUTH_URL
        config.token_url = f"{cls.CTRADER_API_URL}/oauth/token"
        config.redirect_uri = cls.CTRADER_REDIRECT_URI
        
        # Source map (all from HARDCODED)
        config.source_map = {
            'is_demo': 'HARDCODED',
            'account_id': 'HARDCODED',
            'client_id': 'HARDCODED',
            'client_secret': 'HARDCODED',
            'access_token': 'HARDCODED',
            'refresh_token': 'HARDCODED',
            'ws_url_demo': 'HARDCODED',
            'ws_url_live': 'HARDCODED',
            'gold_ctrader_only': 'HARDCODED',
            'gold_symbol_name': 'HARDCODED' if config.gold_symbol_name_override else 'AUTO',
        }
        
        # get_ws_url method
        def get_ws_url():
            """Get WebSocket URL based on is_demo flag"""
            if config.is_demo:
                ws_url = config.ws_url_demo
                source = "HARDCODED"
            else:
                ws_url = config.ws_url_live
                source = "HARDCODED"
            
            config.source_map['ws_url'] = source
            print(f"[CTRADER_CONFIG] Using WS URL: {ws_url} (source={source})")
            return ws_url, source
        
        config.get_ws_url = get_ws_url
        
        # log_preview method
        def log_preview():
            """Log configuration preview"""
            print("[CTRADER_CONFIG] cTrader config loaded from: HARDCODED")
            try:
                ws_url, source = config.get_ws_url()
                print(f"   Endpoint: {ws_url} (source={source})")
            except ValueError as e:
                print(f"   Endpoint: ERROR - {str(e)}")
            print(f"   Is Demo: {config.is_demo}")
            print(f"   Account ID: {config.account_id}")
            print(f"   Client ID: {_safe_preview(config.client_id)}")
            print(f"   Client Secret: {_safe_preview(config.client_secret)}")
            print(f"   Access Token: {_safe_preview(config.access_token)}")
            print(f"   Refresh Token: {_safe_preview(config.refresh_token)}")
            print(f"   Gold cTrader Only: {config.gold_ctrader_only}")
        
        config.log_preview = log_preview
        
        return config
    
    @classmethod
    def _get_env_ctrader_config(cls):
        """Get cTrader config from environment variables (normalized)"""
        # Create a simple object that mimics CTraderHardcodedConfig interface
        class EnvCTraderConfig:
            def __init__(self):
                # Track source of each value for diagnostics
                self.source_map: Dict[str, str] = {}
                
                # STRICT: Read only CTRADER_* keys (no fallbacks)
                # Use _parse_bool_env for proper parsing
                try:
                    self.is_demo = _parse_bool_env('CTRADER_IS_DEMO', default=True)
                    self.source_map['is_demo'] = 'ENV' if os.getenv('CTRADER_IS_DEMO') else 'DEFAULT'
                except Exception as e:
                    print(f"[CONFIG] ERROR parsing CTRADER_IS_DEMO: {e}, using default=True")
                    self.is_demo = True
                    self.source_map['is_demo'] = 'ERROR_DEFAULT'
                
                # Validate account_id - use _parse_int_env with required=False (we'll check later)
                try:
                    self.account_id = _parse_int_env('CTRADER_ACCOUNT_ID', default=0, required=False)
                    if self.account_id <= 0:
                        self.source_map['account_id'] = 'ERROR'
                    else:
                        self.source_map['account_id'] = 'ENV'
                except ValueError as e:
                    # Log error but don't raise - let caller handle
                    print(f"[CONFIG] ERROR: {e}")
                    self.account_id = 0
                    self.source_map['account_id'] = 'ERROR'
                
                # Read WS URLs using _get_str_env
                ws_url_demo_raw = _get_str_env('CTRADER_DEMO_WS_URL', default='', required=False)
                self.ws_url_demo = ws_url_demo_raw or ''
                self.source_map['ws_url_demo'] = 'ENV' if ws_url_demo_raw else 'MISSING'
                
                ws_url_live_raw = _get_str_env('CTRADER_LIVE_WS_URL', default='', required=False)
                self.ws_url_live = ws_url_live_raw or ''
                self.source_map['ws_url_live'] = 'ENV' if ws_url_live_raw else 'MISSING'
                
                # Read credentials using _get_str_env
                self.client_id = _get_str_env('CTRADER_CLIENT_ID', default='', required=False) or ''
                self.source_map['client_id'] = 'ENV' if self.client_id else 'MISSING'
                
                self.client_secret = _get_str_env('CTRADER_CLIENT_SECRET', default='', required=False) or ''
                self.source_map['client_secret'] = 'ENV' if self.client_secret else 'MISSING'
                
                self.access_token = _get_str_env('CTRADER_ACCESS_TOKEN', default='', required=False) or ''
                self.source_map['access_token'] = 'ENV' if self.access_token else 'MISSING'
                
                self.refresh_token = _get_str_env('CTRADER_REFRESH_TOKEN', default='', required=False) or ''
                self.source_map['refresh_token'] = 'ENV' if self.refresh_token else 'MISSING'
                
                # API URLs (hardcoded)
                self.base_url = cls.CTRADER_API_URL
                self.api_url = cls.CTRADER_API_URL
                self.auth_url = cls.CTRADER_AUTH_URL
                self.token_url = f"{cls.CTRADER_API_URL}/oauth/token"
                self.redirect_uri = cls.CTRADER_REDIRECT_URI
                
                # Gold symbol name override from env
                gold_symbol_name_raw = _get_str_env('GOLD_SYMBOL_NAME', default='', required=False)
                self.gold_symbol_name_override = gold_symbol_name_raw if gold_symbol_name_raw else None
                self.source_map['gold_symbol_name'] = 'ENV' if gold_symbol_name_raw else 'MISSING'
            
            def get_ws_url(self):
                """Get WebSocket URL based on is_demo flag (with safe defaults)
                
                Returns:
                    Tuple of (ws_url, source) where source is 'ENV', 'DEFAULT', or 'ERROR'
                """
                if self.is_demo:
                    ws_url_raw = self.ws_url_demo
                    source_var = "CTRADER_DEMO_WS_URL"
                    default_url = "wss://demo.ctraderapi.com:5035"
                else:
                    ws_url_raw = self.ws_url_live
                    source_var = "CTRADER_LIVE_WS_URL"
                    default_url = "wss://live.ctraderapi.com:5035"
                
                # Use default if not set (check ALLOW_WS_DEFAULT flag)
                allow_default = get_env_bool('ALLOW_WS_DEFAULT', default=True)
                
                if not ws_url_raw:
                    if allow_default:
                        ws_url = default_url
                        source = "DEFAULT"
                        print(f"[CTRADER_CONFIG] {source_var} missing -> using default {default_url} (source={source})")
                    else:
                        raise ValueError(f"{source_var} is required but not set. Set ALLOW_WS_DEFAULT=true to use defaults.")
                else:
                    ws_url = ws_url_raw
                    source = "ENV"
                    print(f"[CTRADER_CONFIG] Using {source_var}={ws_url} (source={source})")
                
                # Update source_map
                self.source_map['ws_url'] = source
                
                return ws_url, source
                
                # Validate URL is not a REST API endpoint (only if custom URL provided)
                if ws_url != default_url:
                    forbidden_hosts = ['openapi.ctrader.com', 'api.ctrader.com', 'connect.spotware.com']
                    from urllib.parse import urlparse
                    parsed = urlparse(ws_url)
                    if parsed.hostname in forbidden_hosts and parsed.scheme == 'https':
                        print(f"[CTRADER_CONFIG] WARNING: {ws_url} appears to be a REST API endpoint, not WebSocket. Using default instead.")
                        ws_url = default_url
                        source_var = f"{source_var}_fallback"
                
                # Validate it's a WebSocket URL
                if not ws_url.startswith(('ws://', 'wss://')):
                    print(f"[CTRADER_CONFIG] WARNING: {ws_url} must start with ws:// or wss://. Using default instead.")
                    ws_url = default_url
                    source_var = f"{source_var}_fallback"
                
                return ws_url, source_var
            
            def log_preview(self):
                """Log configuration preview"""
                print("[CTRADER_CONFIG] cTrader config loaded from: ENV")
                try:
                    ws_url, source_var = self.get_ws_url()
                    print(f"   Endpoint: {ws_url} (source={source_var})")
                except ValueError as e:
                    print(f"   Endpoint: ERROR - {str(e)}")
                print(f"   Is Demo: {self.is_demo}")
                print(f"   Account ID: {self.account_id if self.account_id else '(invalid/not set)'}")
                print(f"   Client ID: {_safe_preview(self.client_id)}")
                print(f"   Client Secret: {_safe_preview(self.client_secret)}")
                print(f"   Access Token: {_safe_preview(self.access_token)}")
                print(f"   Refresh Token: {_safe_preview(self.refresh_token)}")
        
        return EnvCTraderConfig()
    
    @classmethod
    def log_config_safe(cls):
        """Log configuration safely (without exposing full tokens/secrets)"""
        config = cls.get_ctrader_config()
        config.log_preview()
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate that required configuration is present"""
        required_fields = [
            cls.TELEGRAM_BOT_TOKEN,
            cls.CTRADER_CLIENT_ID,
            cls.CTRADER_CLIENT_SECRET,
        ]
        
        missing_fields = [field for field in required_fields if not field]
        
        if missing_fields:
            print(f"Missing required configuration: {missing_fields}")
            return False
        
        # Validate account ID
        account_id, error_reason = cls.validate_account_id()
        if error_reason:
            print(f"Invalid account ID: {error_reason}")
            print(f"   Set CTRADER_ACCOUNT_ID in .env (e.g., CTRADER_ACCOUNT_ID=44749280)")
            return False
        
        return True
