"""
Configuration settings for Signals_bot
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

# Determine project root (signalsbot directory)
# config.py is in project root, so __file__ is already there
_project_root = Path(__file__).resolve().parent
_dotenv_path = _project_root / ".env"
_config_live_path = _project_root / "config_live.env"

# Load environment variables from project root (override=True to ensure fresh load)
_env_loaded = load_dotenv(dotenv_path=_dotenv_path, override=True)
_env_live_loaded = False
if _config_live_path.exists():
    _env_live_loaded = load_dotenv(dotenv_path=_config_live_path, override=True)

# Debug: Print critical keys immediately after load_dotenv
print("[ENV_LOAD] After load_dotenv:")
print(f"  CTRADER_IS_DEMO: {repr(os.getenv('CTRADER_IS_DEMO'))}")
print(f"  CTRADER_ACCOUNT_ID: {repr(os.getenv('CTRADER_ACCOUNT_ID'))}")
print(f"  CTRADER_DEMO_WS_URL: {repr(os.getenv('CTRADER_DEMO_WS_URL'))}")
print(f"  dotenv_path: {_dotenv_path} (exists={_dotenv_path.exists()})")
print()

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
        """Parse CTRADER_IS_DEMO strictly from {"true","false","1","0","yes","no"} (case-insensitive)"""
        return _parse_ctrader_is_demo()  # Call module-level function
    
    @classmethod
    def validate_account_id(cls) -> tuple[Optional[int], Optional[str]]:
        """Validate account ID and return parsed value or error reason
        
        Returns:
            Tuple of (account_id_int, error_reason_code)
            - If valid: (int, None)
            - If invalid: (None, reason_code)
        """
        # Read directly from os.getenv (not from cls.CTRADER_ACCOUNT_ID which is evaluated at class definition time)
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
        """Get unified cTrader configuration object (either from ENV or hardcoded)
        
        Returns:
            CTraderConfig-like object with all cTrader settings
        """
        if cls.USE_HARDCODED_CTRADER_CONFIG:
            try:
                from config_hardcoded import _hardcoded_config
                return _hardcoded_config
            except ImportError:
                print("[CONFIG] WARNING: USE_HARDCODED_CTRADER_CONFIG=true but config_hardcoded.py not found, falling back to ENV")
                return cls._get_env_ctrader_config()
        else:
            return cls._get_env_ctrader_config()
    
    @classmethod
    def _get_env_ctrader_config(cls):
        """Get cTrader config from environment variables (normalized)"""
        # Create a simple object that mimics CTraderHardcodedConfig interface
        class EnvCTraderConfig:
            def __init__(self):
                # STRICT: Read only CTRADER_* keys (no fallbacks)
                self.is_demo = cls._parse_ctrader_is_demo()
                # Validate account_id - read directly from os.getenv
                account_id, error_reason = cls.validate_account_id()
                if error_reason:
                    # Don't raise here - let caller check account_id and handle
                    self.account_id = 0
                else:
                    self.account_id = account_id
                # Read WS URLs directly from os.getenv (not from class properties)
                self.ws_url_demo = os.getenv('CTRADER_DEMO_WS_URL', '').strip()
                self.ws_url_live = os.getenv('CTRADER_LIVE_WS_URL', '').strip()
                self.client_id = cls.CTRADER_CLIENT_ID
                self.client_secret = cls.CTRADER_CLIENT_SECRET
                self.access_token = cls.CTRADER_ACCESS_TOKEN
                self.refresh_token = cls.CTRADER_REFRESH_TOKEN
                self.base_url = cls.CTRADER_API_URL
                self.api_url = cls.CTRADER_API_URL
                self.auth_url = cls.CTRADER_AUTH_URL
                self.token_url = f"{cls.CTRADER_API_URL}/oauth/token"
                self.redirect_uri = cls.CTRADER_REDIRECT_URI
            
            def get_ws_url(self):
                """Get WebSocket URL based on is_demo flag (with safe defaults)"""
                if self.is_demo:
                    ws_url_raw = os.getenv('CTRADER_DEMO_WS_URL', '').strip()
                    source_var = "CTRADER_DEMO_WS_URL"
                    default_url = "wss://demo.ctraderapi.com:5035"
                else:
                    ws_url_raw = os.getenv('CTRADER_LIVE_WS_URL', '').strip()
                    source_var = "CTRADER_LIVE_WS_URL"
                    default_url = "wss://live.ctraderapi.com:5035"
                
                # Use default if not set (never fail with CONFIG_MISSING_WS_URL)
                if not ws_url_raw:
                    ws_url = default_url
                    source = f"{source_var}_default"
                    print(f"[CTRADER_CONFIG] {source_var} missing -> using default {default_url} (source={source})")
                else:
                    ws_url = ws_url_raw
                    source = source_var
                    print(f"[CTRADER_CONFIG] Using {source_var}={ws_url} (source={source})")
                
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
