"""
Twelve Data API Client
Asynchronous client for fetching FOREX prices and time series data
"""
import asyncio
import httpx
from typing import Optional, List, Dict, Any
import time
import json
import random


# Configuration constants
TWELVE_MIN_INTERVAL_MS = 400  # Minimum interval between requests (milliseconds)
TWELVE_MAX_RETRIES = 3  # Maximum retry attempts
TWELVE_BACKOFF_BASE_MS = 500  # Base backoff time (milliseconds)
TWELVE_BACKOFF_MAX_MS = 5000  # Maximum backoff time (milliseconds)


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
        
        # Create HTTP client if not exists
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client (ensures initialization)"""
        await self._ensure_started()
        return self._client
    
    async def close(self):
        """Close HTTP client (idempotent)"""
        if self._closed:
            return
        
        self._closed = True
        
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                print(f"[TWELVE_DATA] ⚠️ Error closing client: {type(e).__name__}: {e}")
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
    
    async def _throttle(self):
        """
        Throttle requests to respect minimum interval between requests
        Uses monotonic time and asyncio.Lock for thread-safe throttling
        """
        await self._ensure_started()
        
        async with self._throttle_lock:
            now = time.monotonic()
            
            # Calculate how long to wait
            wait_time = self._next_allowed_time - now
            
            if wait_time > 0:
                wait_ms = int(wait_time * 1000)
                print(f"[TWELVE_DATA] [THROTTLE] Waiting {wait_ms}ms before next request (min_interval={self.min_interval_ms}ms)")
                await asyncio.sleep(wait_time)
            
            # Update next allowed time
            self._next_allowed_time = time.monotonic() + self.min_interval
    
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
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any], max_retries: Optional[int] = None) -> Optional[Dict]:
        """
        Make HTTP request with throttling, retry logic, and backoff
        
        Args:
            endpoint: API endpoint (e.g., "/price")
            params: Query parameters
            max_retries: Maximum number of retries (default: self.max_retries)
        
        Returns:
            JSON response dict or None on failure
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        # Ensure client is initialized (must be in running loop)
        await self._ensure_started()
        
        url = f"{self.base_url}{endpoint}"
        params['apikey'] = self.api_key
        
        client = await self._get_client()
        
        for attempt in range(max_retries):
            try:
                # Throttle: ensure minimum interval between requests
                await self._throttle()
                
                # Make request with semaphore (concurrency limit)
                async with self._semaphore:
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
                                    if attempt < max_retries - 1:
                                        backoff_time = self._calculate_backoff(attempt)
                                        print(f"[TWELVE_DATA] ⚠️ Rate limit detected (JSON error), waiting {backoff_time:.2f}s before retry {attempt + 1}/{max_retries}")
                                        await asyncio.sleep(backoff_time)
                                        continue
                                    else:
                                        print(f"[TWELVE_DATA] ❌ Rate limit after {max_retries} attempts: code={error_code}, message={error_message}")
                                        return None
                                
                                # Check if it's a permanent error
                                if self._is_permanent_error(response):
                                    print(f"[TWELVE_DATA] ❌ Permanent error (no retry): code={error_code}, message={error_message}")
                                    return None
                                
                                # Other errors: don't retry
                                print(f"[TWELVE_DATA] ❌ API error: code={error_code}, message={error_message}")
                                return None
                            
                            return data
                        except json.JSONDecodeError as e:
                            print(f"[TWELVE_DATA] ❌ Invalid JSON response: {e}")
                            print(f"[TWELVE_DATA] Response preview: {response.text[:200]}")
                            return None
                    
                    elif self._is_rate_limit_error(response):
                        # Rate limit (429) - wait until next minute
                        # Calculate wait time: wait until next minute + 0.2s buffer
                        wait_seconds = 60 - (time.time() % 60) + 0.2
                        print(f"[TWELVE_DATA] ⚠️ Rate limit (429), waiting {wait_seconds:.2f}s until next minute")
                        await asyncio.sleep(wait_seconds)
                        
                        # After waiting, try one more time (single retry after minute wait)
                        # Only retry if we haven't exhausted all attempts
                        if attempt < max_retries - 1:
                            # Make one final attempt after minute wait
                            try:
                                await self._throttle()
                                async with self._semaphore:
                                    response = await client.get(url, params=params)
                                    if response.status_code == 200:
                                        try:
                                            data = response.json()
                                            if isinstance(data, dict) and data.get('status') == 'error':
                                                error_code = data.get('code', 'UNKNOWN')
                                                error_message = data.get('message', 'No error message')
                                                if self._is_rate_limit_error(response):
                                                    print(f"[TWELVE_DATA] ❌ Still rate limited after minute wait: code={error_code}, message={error_message}")
                                                    print(f"[TWELVE_DATA] Skipping symbol (rate limit persists)")
                                                    return None
                                            return data
                                        except json.JSONDecodeError:
                                            return None
                                    elif self._is_rate_limit_error(response):
                                        # Still rate limited after minute wait - skip symbol
                                        print(f"[TWELVE_DATA] ❌ Still rate limited (429) after minute wait - skipping symbol")
                                        return None
                            except Exception as e:
                                print(f"[TWELVE_DATA] ❌ Error on retry after minute wait: {type(e).__name__}: {e}")
                                return None
                        else:
                            # Already exhausted retries - skip symbol
                            print(f"[TWELVE_DATA] ❌ Rate limit (429) - skipping symbol (max retries reached)")
                            return None
                    
                    elif 500 <= response.status_code < 600:
                        # Server error - retry with backoff
                        if attempt < max_retries - 1:
                            backoff_time = self._calculate_backoff(attempt)
                            print(f"[TWELVE_DATA] ⚠️ Server error {response.status_code}, waiting {backoff_time:.2f}s before retry {attempt + 1}/{max_retries}")
                            await asyncio.sleep(backoff_time)
                            continue
                        else:
                            print(f"[TWELVE_DATA] ❌ Server error {response.status_code} after {max_retries} attempts")
                            return None
                    
                    elif self._is_permanent_error(response):
                        # Permanent error - don't retry
                        print(f"[TWELVE_DATA] ❌ Permanent error {response.status_code}: {response.text[:200]}")
                        return None
                    
                    else:
                        # Other client error (4xx) - don't retry
                        print(f"[TWELVE_DATA] ❌ HTTP {response.status_code}: {response.text[:200]}")
                        return None
                        
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    backoff_time = self._calculate_backoff(attempt)
                    print(f"[TWELVE_DATA] ⚠️ Timeout, waiting {backoff_time:.2f}s before retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Timeout after {max_retries} attempts")
                    return None
                    
            except (httpx.RequestError, httpx.TransportError) as e:
                if attempt < max_retries - 1:
                    backoff_time = self._calculate_backoff(attempt)
                    print(f"[TWELVE_DATA] ⚠️ Network error {type(e).__name__}: {e}, waiting {backoff_time:.2f}s before retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(backoff_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Network error after {max_retries} attempts: {type(e).__name__}: {e}")
                    return None
                    
            except Exception as e:
                print(f"[TWELVE_DATA] ❌ Unexpected error: {type(e).__name__}: {e}")
                return None
        
        return None
    
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
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for symbol
        
        Args:
            symbol: Symbol name (e.g., "EURUSD" or "EUR/USD")
        
        Returns:
            Price as float or None on error
        """
        normalized_symbol = self.normalize_forex_symbol(symbol)
        
        print(f"[TWELVE_DATA] [GET_PRICE] Requesting price for {symbol} (normalized: {normalized_symbol})")
        
        params = {
            'symbol': normalized_symbol,
        }
        
        data = await self._make_request('/price', params)
        
        if not data:
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ Failed to get price for {symbol}")
            return None
        
        # Parse price from response
        # Twelve Data /price endpoint returns: {"price": "1.12345", "symbol": "EUR/USD"}
        try:
            price_str = data.get('price')
            if price_str:
                price = float(price_str)
                print(f"[TWELVE_DATA] [GET_PRICE] ✅ {symbol}: {price}")
                return price
            else:
                print(f"[TWELVE_DATA] [GET_PRICE] ❌ No 'price' field in response for {symbol}")
                return None
        except (ValueError, TypeError, KeyError) as e:
            print(f"[TWELVE_DATA] [GET_PRICE] ❌ Parse error for {symbol}: {type(e).__name__}: {e}")
            print(f"[TWELVE_DATA] [GET_PRICE] Response: {data}")
            return None
    
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
