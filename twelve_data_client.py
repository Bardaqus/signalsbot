"""
Twelve Data API Client
Asynchronous client for fetching FOREX prices and time series data
"""
import asyncio
import httpx
from typing import Optional, List, Dict, Any, Tuple
import time
import json
import random


# Configuration constants
TWELVE_MIN_INTERVAL_MS = 400  # Minimum interval between requests (milliseconds)
TWELVE_MAX_RETRIES = 3  # Maximum retry attempts
TWELVE_BACKOFF_BASE_MS = 500  # Base backoff time (milliseconds)
TWELVE_BACKOFF_MAX_MS = 5000  # Maximum backoff time (milliseconds)
TWELVE_MAX_REQUESTS_PER_MINUTE = 6  # Maximum requests per minute (to stay under 8/min limit)


class TwelveDataClient:
    """Asynchronous client for Twelve Data API with rate limiting and retry logic"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.twelvedata.com",
        timeout: int = 10,
        min_interval_ms: int = TWELVE_MIN_INTERVAL_MS,
        max_retries: int = TWELVE_MAX_RETRIES,
        backoff_base_ms: int = TWELVE_BACKOFF_BASE_MS,
        backoff_max_ms: int = TWELVE_BACKOFF_MAX_MS,
        **kwargs
    ):
        """
        Initialize Twelve Data client (lazy initialization)
        
        Args:
            api_key: Twelve Data API key
            base_url: Base URL for API (default: https://api.twelvedata.com)
            timeout: Request timeout in seconds (default: 10)
            min_interval_ms: Minimum interval between requests in milliseconds (default: 400)
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_base_ms: Base backoff time in milliseconds (default: 500)
            backoff_max_ms: Maximum backoff time in milliseconds (default: 5000)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        
        # Rate limiting configuration
        self.min_interval_ms = min_interval_ms
        self.min_interval = min_interval_ms / 1000.0  # Convert to seconds
        self.max_retries = max_retries
        self.backoff_base_ms = backoff_base_ms
        self.backoff_max_ms = backoff_max_ms
        
        # Throttling state (using monotonic time to avoid clock adjustments)
        # Created lazily in _ensure_started() to avoid event loop issues
        self._throttle_lock: Optional[asyncio.Lock] = None
        self._next_allowed_time = 0.0  # Monotonic time
        
        # Rate limiting: simple semaphore (max 8 concurrent requests)
        # Created lazily in _ensure_started() to avoid event loop issues
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        # Per-minute request tracking for throttling
        self._requests_per_minute: List[float] = []  # List of request timestamps
        self._rate_limit_cooldown_until = 0.0  # Timestamp when cooldown ends (0 = no cooldown)
        
        # Circuit breaker state
        self._circuit_breaker_errors = 0  # Consecutive error count
        self._circuit_breaker_open_until = 0.0  # Timestamp when breaker closes (0 = closed)
        self._circuit_breaker_cooldown_base = 120.0  # Base cooldown: 120 seconds (2 minutes)
        self._circuit_breaker_cooldown_max = 900.0  # Max cooldown: 900 seconds (15 minutes)
        self._circuit_breaker_threshold = 3  # Open after 3 consecutive errors
        self._circuit_breaker_last_log_time = 0.0  # Last time we logged breaker status (to avoid spam)
        
        # HTTP client (reused for connection pooling)
        # Created lazily in _ensure_started() to avoid event loop issues
        self._client: Optional[httpx.AsyncClient] = None
        
        # Closed flag to prevent double closing
        self._closed = False
    
    async def _ensure_started(self):
        """Ensure client, semaphore, and lock are initialized (must be called from running event loop)"""
        if self._closed:
            raise RuntimeError("TwelveDataClient is closed")
        
        # Create throttle lock if not exists (must be in running loop)
        if self._throttle_lock is None:
            self._throttle_lock = asyncio.Lock()
        
        # Create semaphore if not exists (must be in running loop)
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(8)
        
        # Create HTTP client if not exists (without async with - we manage lifecycle manually)
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
            print(f"[TWELVE_DATA] HTTP client created (will be closed only on shutdown)")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (ensures initialization)"""
        await self._ensure_started()
        return self._client
    
    async def close(self):
        """Close HTTP client (idempotent) - should only be called on shutdown"""
        if self._closed:
            return
        
        self._closed = True
        print(f"[TWELVE_DATA] Closing HTTP client (shutdown)...")
        
        if self._client:
            try:
                if not self._client.is_closed:
                    await self._client.aclose()
                    print(f"[TWELVE_DATA] ✅ HTTP client closed successfully")
                else:
                    print(f"[TWELVE_DATA] ⚠️ HTTP client was already closed")
            except Exception as e:
                print(f"[TWELVE_DATA] ⚠️ Error closing client: {type(e).__name__}: {e}")
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"[TWELVE_DATA] Exception closing client: {type(e).__name__}: {e}")
            finally:
                self._client = None
        
        self._semaphore = None
        self._throttle_lock = None
    
    def _safe_preview(self, value: str, length: int = 6) -> str:
        """Create safe preview of sensitive value"""
        if not value:
            return "(not set)"
        if len(value) <= length:
            return value[:length] + "..."
        return value[:length] + "..."
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is currently open"""
        if self._circuit_breaker_open_until == 0.0:
            return False
        return time.time() < self._circuit_breaker_open_until
    
    def before_request(self) -> bool:
        """
        Check if request is allowed (circuit breaker API)
        
        Returns:
            True if request is allowed, False if circuit breaker is open
        """
        return not self._is_circuit_breaker_open()
    
    def on_success(self):
        """Record a successful request and reset circuit breaker"""
        if self._circuit_breaker_errors > 0:
            print(f"[TWELVE_DATA] [CIRCUIT_BREAKER] ✅ CLOSED - success after {self._circuit_breaker_errors} errors")
        self._circuit_breaker_errors = 0
        self._circuit_breaker_open_until = 0.0
    
    def on_failure(self, reason: Optional[str] = None, exception: Optional[Exception] = None):
        """
        Record a failure and potentially open circuit breaker
        
        Args:
            reason: Optional reason string (e.g., "rate_limit", "timeout", "network_error")
            exception: Optional exception object
        """
        self._circuit_breaker_errors += 1
        
        if self._circuit_breaker_errors >= self._circuit_breaker_threshold:
            # Calculate exponential backoff cooldown
            cooldown_multiplier = min(2 ** (self._circuit_breaker_errors - self._circuit_breaker_threshold), 8)  # Max 8x
            cooldown = min(self._circuit_breaker_cooldown_base * cooldown_multiplier, self._circuit_breaker_cooldown_max)
            
            self._circuit_breaker_open_until = time.time() + cooldown
            reason_str = f" ({reason})" if reason else ""
            print(f"[TWELVE_DATA] [CIRCUIT_BREAKER] 🔴 OPENED after {self._circuit_breaker_errors} consecutive errors{reason_str}")
            print(f"[TWELVE_DATA] [CIRCUIT_BREAKER] Cooldown: {cooldown:.1f}s (until {time.strftime('%H:%M:%S', time.localtime(self._circuit_breaker_open_until))})")
    
    def _record_error(self):
        """Legacy method - use on_failure() instead"""
        self.on_failure()
    
    def _record_success(self):
        """Legacy method - use on_success() instead"""
        self.on_success()
    
    def _log_circuit_breaker_status(self, force: bool = False):
        """Log circuit breaker status (throttled to avoid spam)"""
        now = time.time()
        if not force and now - self._circuit_breaker_last_log_time < 30:
            return  # Don't log more than once per 30 seconds
        
        self._circuit_breaker_last_log_time = now
        
        if self._is_circuit_breaker_open():
            remaining = self._circuit_breaker_open_until - now
            print(f"[TWELVE_DATA] [CIRCUIT_BREAKER] 🔴 OPEN - remaining: {remaining:.1f}s (errors: {self._circuit_breaker_errors})")
        else:
            if self._circuit_breaker_errors > 0:
                print(f"[TWELVE_DATA] [CIRCUIT_BREAKER] 🟢 CLOSED (recent errors: {self._circuit_breaker_errors})")
            # Don't log if closed and no errors
    
    async def _throttle(self):
        """
        Throttle requests to respect minimum interval and per-minute limits
        Uses monotonic time and asyncio.Lock for thread-safe throttling
        
        Also checks for cooldown after 429 errors (60-90 seconds)
        """
        await self._ensure_started()
        
        async with self._throttle_lock:
            now = time.monotonic()
            now_wallclock = time.time()
            
            # Check circuit breaker first
            if self._is_circuit_breaker_open():
                self._log_circuit_breaker_status()
                remaining = self._circuit_breaker_open_until - now_wallclock
                raise RuntimeError(f"Circuit breaker OPEN - remaining: {remaining:.1f}s")
            
            # Check if we're in cooldown (after 429 error)
            if self._rate_limit_cooldown_until > now_wallclock:
                cooldown_remaining = self._rate_limit_cooldown_until - now_wallclock
                print(f"[TWELVE_DATA] [THROTTLE] In cooldown after 429 error, waiting {cooldown_remaining:.1f}s...")
                await asyncio.sleep(cooldown_remaining)
                # Reset cooldown after waiting
                self._rate_limit_cooldown_until = 0.0
            
            # Clean old requests (older than 1 minute)
            one_minute_ago = now_wallclock - 60
            self._requests_per_minute = [ts for ts in self._requests_per_minute if ts > one_minute_ago]
            
            # Check per-minute limit
            if len(self._requests_per_minute) >= TWELVE_MAX_REQUESTS_PER_MINUTE:
                # Calculate wait time until oldest request expires
                oldest_request = min(self._requests_per_minute)
                wait_until = oldest_request + 60
                wait_time = wait_until - now_wallclock
                if wait_time > 0:
                    print(f"[TWELVE_DATA] [THROTTLE] Per-minute limit reached ({len(self._requests_per_minute)}/{TWELVE_MAX_REQUESTS_PER_MINUTE}), waiting {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                    # Re-clean after wait
                    now_wallclock = time.time()
                    one_minute_ago = now_wallclock - 60
                    self._requests_per_minute = [ts for ts in self._requests_per_minute if ts > one_minute_ago]
            
            # Calculate how long to wait for minimum interval
            wait_time = self._next_allowed_time - now
            
            if wait_time > 0:
                wait_ms = int(wait_time * 1000)
                print(f"[TWELVE_DATA] [THROTTLE] Waiting {wait_ms}ms before next request (min_interval={self.min_interval_ms}ms)")
                await asyncio.sleep(wait_time)
            
            # Update next allowed time
            self._next_allowed_time = time.monotonic() + self.min_interval
            
            # Record this request timestamp
            self._requests_per_minute.append(time.time())
    
    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate backoff time with exponential backoff and jitter
        
        Args:
            attempt: Current attempt number (0-based)
        
        Returns:
            Backoff time in seconds
        """
        # Exponential backoff: base * 2^attempt
        backoff_ms = min(self.backoff_base_ms * (2 ** attempt), self.backoff_max_ms)
        
        # Add jitter (±20% random variation)
        jitter_ms = backoff_ms * 0.2 * (random.random() * 2 - 1)  # -20% to +20%
        total_ms = backoff_ms + jitter_ms
        
        return total_ms / 1000.0  # Convert to seconds
    
    def _is_rate_limit_error(self, response: httpx.Response) -> bool:
        """Check if response indicates rate limit"""
        if response.status_code == 429:
            return True
        
        # Check JSON response for rate limit indicators
        try:
            data = response.json()
            if isinstance(data, dict):
                message = str(data.get('message', '')).lower()
                status = str(data.get('status', '')).lower()
                code = str(data.get('code', '')).lower()
                
                rate_limit_indicators = ['rate limit', '429', 'limit', 'too many', 'quota', 'throttle']
                if any(indicator in message or indicator in status or indicator in code for indicator in rate_limit_indicators):
                    return True
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        
        return False
    
    def _is_permanent_error(self, response: httpx.Response) -> bool:
        """Check if error is permanent (should not retry)"""
        # 401, 403, 404 are permanent errors
        if response.status_code in [401, 403, 404]:
            return True
        
        # Check JSON response for permanent error indicators
        try:
            data = response.json()
            if isinstance(data, dict):
                message = str(data.get('message', '')).lower()
                code = str(data.get('code', '')).lower()
                
                permanent_indicators = [
                    'invalid api key', 'permission', 'unauthorized', 'forbidden',
                    'symbol not found', 'invalid symbol', 'not found'
                ]
                if any(indicator in message or indicator in code for indicator in permanent_indicators):
                    return True
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        
        return False
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any], max_retries: Optional[int] = None, single_shot: bool = False) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Make HTTP request with throttling, retry logic, backoff, and circuit breaker
        
        Args:
            endpoint: API endpoint (e.g., "/price")
            params: Query parameters
            max_retries: Maximum number of retries (default: self.max_retries)
            single_shot: If True, disable retries (for signal generation)
        
        Returns:
            Tuple of (JSON response dict or None, reason: str or None)
            reason can be: "cooldown", "http_error_429", "timeout", "network_error", "parse_error", "unknown_exception", etc.
        """
        # Check circuit breaker first (before any network calls)
        if self._is_circuit_breaker_open():
            self._log_circuit_breaker_status()
            return None, "cooldown"
        
        if max_retries is None:
            max_retries = self.max_retries
        
        # For single-shot mode (signal generation): disable retries
        if single_shot or max_retries == 0:
            max_retries = 0
        
        # Treat max_retries as "number of retries" and compute total attempts
        # max_retries=0 means 1 attempt (initial) + 0 retries = 1 total attempt
        # max_retries=3 means 1 attempt (initial) + 3 retries = 4 total attempts
        attempts = max_retries + 1
        
        # Ensure client is initialized (must be in running loop)
        await self._ensure_started()
        
        url = f"{self.base_url}{endpoint}"
        params['apikey'] = self.api_key
        
        client = await self._get_client()
        
        # Check if client is closed (should not happen, but defensive check)
        if client.is_closed:
            error_msg = "HTTP client is closed"
            print(f"[TWELVE_DATA] ❌ {error_msg}")
            self.on_failure(reason="client_closed")
            return None, f"exception:RuntimeError:{error_msg}"
        
        # Track if we got a successful response
        success = False
        
        # Loop: attempts = max_retries + 1, so max_retries=0 -> attempts=1 (one HTTP request)
        for attempt in range(attempts):
            try:
                # Throttle: ensure minimum interval between requests
                await self._throttle()
                
                # Make request with semaphore (concurrency limit)
                async with self._semaphore:
                    # Actual HTTP request happens here - log it
                    print(f"[TWELVE_DATA] [HTTP_REQUEST] GET {url}?symbol={params.get('symbol', 'N/A')}")
                    response = await client.get(url, params=params)
                    
                    # Check status code
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # Check for Twelve Data error response
                            if isinstance(data, dict) and data.get('status') == 'error':
                                error_code = data.get('code', 'UNKNOWN')
                                error_message = data.get('message', 'No error message')
                                
                                # Check if it's a rate limit error in JSON
                                if self._is_rate_limit_error(response):
                                    # Record error for circuit breaker
                                    self.on_failure(reason="rate_limit_json")
                                    # Check if we can retry (attempt is 0-based, so attempt < max_retries means we can retry)
                                    if attempt < max_retries:
                                        backoff_time = self._calculate_backoff(attempt)
                                        print(f"[TWELVE_DATA] ⚠️ Rate limit detected (JSON error), waiting {backoff_time:.2f}s before retry {attempt + 1}/{attempts}")
                                        await asyncio.sleep(backoff_time)
                                        continue
                                    else:
                                        # Log response details for diagnostics
                                        response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                                        print(f"[TWELVE_DATA] ❌ Rate limit after {attempts} attempt(s): code={error_code}, message={error_message}")
                                        print(f"[TWELVE_DATA] Response preview: {response_preview}")
                                        return None, "rate_limit_429"
                                
                                # Check if it's a permanent error
                                if self._is_permanent_error(response):
                                    # Don't record permanent errors (like invalid API key) - they won't recover
                                    response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                                    print(f"[TWELVE_DATA] ❌ Permanent error (no retry): code={error_code}, message={error_message}")
                                    print(f"[TWELVE_DATA] Response preview: {response_preview}")
                                    return None, "invalid_api_key" if "api key" in error_message.lower() else f"permanent_error_{error_code}"
                                
                                # Other errors: record for circuit breaker
                                self.on_failure(reason=f"api_error_{error_code}")
                                response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                                print(f"[TWELVE_DATA] ❌ API error: code={error_code}, message={error_message}")
                                print(f"[TWELVE_DATA] Response preview: {response_preview}")
                                return None, f"api_error_{error_code}"
                            
                            # Success - reset circuit breaker (will be called in get_price)
                            success = True
                            # Log successful HTTP response
                            print(f"[TWELVE_DATA] [HTTP_RESPONSE] GET {url} -> {response.status_code} OK")
                            return data, None
                        except json.JSONDecodeError as e:
                            print(f"[TWELVE_DATA] ❌ Invalid JSON response: {e}")
                            print(f"[TWELVE_DATA] Response preview: {response.text[:200]}")
                            self.on_failure(reason="parse_error", exception=e)
                            return None, "parse_error"
                    
                    elif self._is_rate_limit_error(response):
                        # Rate limit (429) - record error and activate cooldown
                        self.on_failure(reason="rate_limit_429")
                        import random
                        cooldown_seconds = random.uniform(60, 90)  # 60-90 seconds cooldown
                        self._rate_limit_cooldown_until = time.time() + cooldown_seconds
                        print(f"[TWELVE_DATA] ⚠️ Rate limit (429) detected - activating cooldown for {cooldown_seconds:.1f}s")
                        print(f"[TWELVE_DATA] Skipping symbol (will resume after cooldown)")
                        return None, "http_error_429"
                    
                    elif 500 <= response.status_code < 600:
                        # Server error - record error and retry with backoff
                        self.on_failure(reason=f"server_error_{response.status_code}")
                        response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                        # Check if we can retry (attempt < max_retries means we can retry)
                        if attempt < max_retries:
                            backoff_time = self._calculate_backoff(attempt)
                            print(f"[TWELVE_DATA] ⚠️ Server error {response.status_code}, waiting {backoff_time:.2f}s before retry {attempt + 1}/{attempts}")
                            print(f"[TWELVE_DATA] Response preview: {response_preview}")
                            await asyncio.sleep(backoff_time)
                            continue
                        else:
                            print(f"[TWELVE_DATA] ❌ Server error {response.status_code} after {attempts} attempt(s)")
                            print(f"[TWELVE_DATA] Response preview: {response_preview}")
                            return None, f"server_error_{response.status_code}"
                    
                    elif self._is_permanent_error(response):
                        # Permanent error - don't retry, don't record (won't recover)
                        response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                        print(f"[TWELVE_DATA] ❌ Permanent error {response.status_code}: {response_preview}")
                        return None, "invalid_api_key" if response.status_code == 401 else f"permanent_error_{response.status_code}"
                    
                    else:
                        # Other client error (4xx) - record error and log response details
                        self.on_failure(reason=f"client_error_{response.status_code}")
                        response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
                        print(f"[TWELVE_DATA] ❌ HTTP {response.status_code}: {response_preview}")
                        # Try to parse JSON error if available
                        try:
                            error_json = response.json()
                            if isinstance(error_json, dict):
                                error_code = error_json.get('code', 'UNKNOWN')
                                error_message = error_json.get('message', 'No message')
                                print(f"[TWELVE_DATA] JSON error details: code={error_code}, message={error_message}")
                        except:
                            pass
                        return None, f"client_error_{response.status_code}"
                        
            except httpx.TimeoutException as e:
                # Timeout - record error
                self.on_failure(reason="timeout", exception=e)
                # Check if we can retry (attempt < max_retries means we can retry)
                if attempt < max_retries:
                    backoff_time = self._calculate_backoff(attempt)
                    print(f"[TWELVE_DATA] ⚠️ Timeout, waiting {backoff_time:.2f}s before retry {attempt + 1}/{attempts}")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Timeout after {attempts} attempt(s): {type(e).__name__}: {e}")
                    return None, "timeout"
                    
            except (httpx.RequestError, httpx.TransportError) as e:
                # Network error - record error
                self.on_failure(reason="network_error", exception=e)
                # Check if we can retry (attempt < max_retries means we can retry)
                if attempt < max_retries:
                    backoff_time = self._calculate_backoff(attempt)
                    print(f"[TWELVE_DATA] ⚠️ Network error {type(e).__name__}: {e}, waiting {backoff_time:.2f}s before retry {attempt + 1}/{attempts}")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Network error after {attempts} attempt(s): {type(e).__name__}: {e}")
                    return None, "network_error"
                    
            except RuntimeError as e:
                # Circuit breaker error - don't record (already recorded in _throttle)
                if "Circuit breaker" in str(e):
                    return None, "cooldown"
                # Other runtime errors - record
                self.on_failure(reason="runtime_error", exception=e)
                print(f"[TWELVE_DATA] ❌ Runtime error: {type(e).__name__}: {e}")
                import traceback
                print(f"[TWELVE_DATA] Traceback: {traceback.format_exc()}")
                return None, f"runtime_error: {str(e)}"
                    
            except Exception as e:
                # Unexpected error - record with full details
                error_type = type(e).__name__
                error_msg = str(e)
                self.on_failure(reason=f"exception_{error_type}", exception=e)
                print(f"[TWELVE_DATA] ❌ Unexpected error: {error_type}: {error_msg}")
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"[TWELVE_DATA] Unexpected exception in _make_request: {error_type}: {error_msg}")
                import traceback
                print(f"[TWELVE_DATA] Traceback: {traceback.format_exc()}")
                return None, f"exception:{error_type}:{error_msg}"
        
        # If we get here, all attempts failed and success was never True
        # This should not happen - all error paths should return above
        # But if it does, log it as an exception
        if not success:
            error_msg = f"All {attempts} attempt(s) exhausted without returning (max_retries={max_retries})"
            print(f"[TWELVE_DATA] ❌ {error_msg}")
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[TWELVE_DATA] {error_msg} - this should not happen, all error paths should return")
            return None, f"exception:RuntimeError:{error_msg}"
    
    @staticmethod
    def normalize_forex_symbol(symbol: str) -> str:
        """
        Normalize FOREX symbol for Twelve Data API
        
        Args:
            symbol: Symbol like "EURUSD", "GBPUSD", etc.
        
        Returns:
            Normalized symbol like "EUR/USD", "GBP/USD", etc.
        """
        symbol_upper = symbol.upper().replace('/', '')
        
        # Common FOREX pairs mapping
        if len(symbol_upper) == 6:
            # Standard 6-char pairs: EURUSD -> EUR/USD
            base = symbol_upper[:3]
            quote = symbol_upper[3:]
            return f"{base}/{quote}"
        elif symbol_upper == "XAUUSD":
            return "XAU/USD"
        else:
            # Return as-is if already normalized or unknown format
            return symbol_upper
    
    async def get_price(self, symbol: str, max_retries_override: Optional[int] = None) -> Tuple[Optional[float], Optional[str]]:
        """
        Get current price for symbol with circuit breaker protection
        
        Args:
            symbol: Symbol name (e.g., "EURUSD" or "EUR/USD")
            max_retries_override: Override max_retries (use 0 for signal generation - no retries)
        
        Returns:
            Tuple of (price: float or None, reason: str or None)
            reason will be "twelve_data_cooldown" if circuit breaker is open
        """
        # Check circuit breaker FIRST (before any logging or network calls)
        if not self.before_request():
            self._log_circuit_breaker_status()
            return None, "cooldown"
        
        normalized_symbol = self.normalize_forex_symbol(symbol)
        
        # Log ONLY if we're actually going to make HTTP request
        # Note: single-shot mode (retries=0) will make exactly 1 HTTP request (attempts = 0 + 1 = 1)
        retries = max_retries_override if max_retries_override is not None else self.max_retries
        attempts_expected = retries + 1
        print(f"[TWELVE_DATA] [GET_PRICE] Requesting price for {symbol} (normalized: {normalized_symbol}, attempts={attempts_expected}, retries={retries})")
        
        params = {
            'symbol': normalized_symbol,
        }
        
        # For signal generation: use max_retries=0 (no retries, single-shot = 1 HTTP request)
        # For other uses: use default max_retries
        try:
            data, request_reason = await self._make_request('/price', params, max_retries=retries, single_shot=(retries == 0))
        except RuntimeError as e:
            # Circuit breaker error from _throttle
            error_type = type(e).__name__
            error_msg = str(e)
            if "Circuit breaker" in error_msg or "closed" in error_msg.lower():
                print(f"[TWELVE_DATA] [GET_PRICE] ❌ Circuit breaker/client closed error: {error_type}: {error_msg}")
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"[TWELVE_DATA] RuntimeError in get_price: {error_type}: {error_msg}")
                return None, "cooldown"
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ RuntimeError: {error_type}: {error_msg}")
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"[TWELVE_DATA] RuntimeError in get_price: {error_type}: {error_msg}")
            import traceback
            print(f"[TWELVE_DATA] [GET_PRICE] Traceback: {traceback.format_exc()}")
            return None, f"exception:{error_type}:{error_msg}"
        except Exception as e:
            # Catch any other exceptions
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ Exception: {error_type}: {error_msg}")
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"[TWELVE_DATA] Exception in get_price: {error_type}: {error_msg}")
            import traceback
            print(f"[TWELVE_DATA] [GET_PRICE] Traceback: {traceback.format_exc()}")
            return None, f"exception:{error_type}:{error_msg}"
        
        if not data:
            # Check if circuit breaker opened during request
            if self._is_circuit_breaker_open():
                return None, "cooldown"
            
            # Use detailed reason from _make_request
            detailed_reason = request_reason or "exception:UnknownError:No reason provided"
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ Failed to get price for {symbol}, reason={detailed_reason}")
            
            # Map internal reasons to external reason codes
            if detailed_reason == "cooldown":
                return None, "cooldown"
            elif detailed_reason == "http_error_429":
                return None, "rate_limit_429"
            elif detailed_reason == "timeout":
                return None, "timeout"
            elif detailed_reason == "network_error":
                return None, "network_error"
            elif detailed_reason == "parse_error":
                return None, "parse_error"
            elif detailed_reason.startswith("no_key") or detailed_reason.startswith("permanent_error_401"):
                return None, "invalid_api_key"
            elif detailed_reason.startswith("exception:"):
                # Already formatted as exception:Type:message
                return None, detailed_reason
            else:
                # Wrap unknown reasons
                return None, f"exception:UnknownError:{detailed_reason}"
        
        # Parse price from response
        # Twelve Data /price endpoint returns: {"price": "1.12345", "symbol": "EUR/USD"}
        try:
            price_str = data.get('price')
            if price_str:
                price = float(price_str)
                print(f"[TWELVE_DATA] [GET_PRICE] ✅ {symbol}: {price}")
                # Record success for circuit breaker
                self.on_success()
                return price, None
            else:
                print(f"[TWELVE_DATA] [GET_PRICE] ❌ No 'price' field in response for {symbol}")
                self.on_failure(reason="no_price_field")
                return None, "parse_error"
        except (ValueError, TypeError, KeyError) as e:
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ Parse error for {symbol}: {type(e).__name__}: {e}")
            print(f"[TWELVE_DATA] [GET_PRICE] Response: {data}")
            self.on_failure(reason="parse_error", exception=e)
            import traceback
            print(f"[TWELVE_DATA] [GET_PRICE] Traceback: {traceback.format_exc()}")
            return None, "parse_error"
    
    async def get_time_series(self, symbol: str, interval: str = "1h", outputsize: int = 200) -> List[Dict]:
        """
        Get time series (candles) for symbol
        
        Args:
            symbol: Symbol name (e.g., "EURUSD" or "EUR/USD")
            interval: Time interval (1m, 5m, 15m, 30m, 45m, 1h, 2h, 4h, 1day, 1week, 1month)
            outputsize: Number of candles to return (default: 200)
        
        Returns:
            List of candle dicts with keys: datetime, open, high, low, close, volume
            Returns empty list on error
        """
        normalized_symbol = self.normalize_forex_symbol(symbol)
        
        print(f"[TWELVE_DATA] [GET_TIMESERIES] Requesting candles for {symbol} (normalized: {normalized_symbol}), interval={interval}, outputsize={outputsize}")
        
        params = {
            'symbol': normalized_symbol,
            'interval': interval,
            'outputsize': outputsize,
        }
        
        data = await self._make_request('/time_series', params)
        
        if not data:
            print(f"[TWELVE_DATA] [GET_TIMESERIES] ❌ Failed to get time series for {symbol}")
            return []
        
        # Parse candles from response
        # Twelve Data /time_series returns: {"meta": {...}, "values": [{"datetime": "...", "open": "...", ...}, ...]}
        try:
            values = data.get('values', [])
            if not values:
                print(f"[TWELVE_DATA] [GET_TIMESERIES] ⚠️ No 'values' in response for {symbol}")
                return []
            
            candles = []
            for candle in values:
                try:
                    candle_dict = {
                        'datetime': candle.get('datetime'),
                        'open': float(candle.get('open', 0)),
                        'high': float(candle.get('high', 0)),
                        'low': float(candle.get('low', 0)),
                        'close': float(candle.get('close', 0)),
                        'volume': float(candle.get('volume', 0)),
                    }
                    candles.append(candle_dict)
                except (ValueError, TypeError) as e:
                    print(f"[TWELVE_DATA] [GET_TIMESERIES] ⚠️ Skipping invalid candle: {type(e).__name__}: {e}")
                    continue
            
            print(f"[TWELVE_DATA] [GET_TIMESERIES] ✅ {symbol}: {len(candles)} candles")
            return candles
            
        except (KeyError, TypeError) as e:
            print(f"[TWELVE_DATA] [GET_TIMESERIES] ❌ Parse error for {symbol}: {type(e).__name__}: {e}")
            print(f"[TWELVE_DATA] [GET_TIMESERIES] Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
            return []
