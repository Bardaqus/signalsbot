"""
Twelve Data API Client
Asynchronous client for fetching FOREX prices and time series data
"""
import asyncio
import httpx
from typing import Optional, List, Dict, Any
import time
import json


class TwelveDataClient:
    """Asynchronous client for Twelve Data API"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.twelvedata.com", timeout: int = 10):
        """
        Initialize Twelve Data client
        
        Args:
            api_key: Twelve Data API key
            base_url: Base URL for API (default: https://api.twelvedata.com)
            timeout: Request timeout in seconds (default: 10)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        
        # Rate limiting: simple semaphore (max 8 concurrent requests)
        self.semaphore = asyncio.Semaphore(8)
        
        # Last request time for rate limiting (min 0.1s between requests)
        self.last_request_time = 0.0
        self.min_request_interval = 0.1
        
        # HTTP client (reused for connection pooling)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client
    
    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _safe_preview(self, value: str, length: int = 6) -> str:
        """Create safe preview of sensitive value"""
        if not value:
            return "(not set)"
        if len(value) <= length:
            return value[:length] + "..."
        return value[:length] + "..."
    
    async def _rate_limit(self):
        """Simple rate limiting: ensure minimum interval between requests"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any], max_retries: int = 3) -> Optional[Dict]:
        """
        Make HTTP request with retry logic
        
        Args:
            endpoint: API endpoint (e.g., "/price")
            params: Query parameters
            max_retries: Maximum number of retries (default: 3)
        
        Returns:
            JSON response dict or None on failure
        """
        url = f"{self.base_url}{endpoint}"
        params['apikey'] = self.api_key
        
        # Rate limiting
        async with self.semaphore:
            await self._rate_limit()
        
        client = await self._get_client()
        
        for attempt in range(max_retries):
            try:
                async with self.semaphore:
                    response = await client.get(url, params=params)
                    
                    # Check status code
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # Check for Twelve Data error response
                            if isinstance(data, dict) and data.get('status') == 'error':
                                error_code = data.get('code', 'UNKNOWN')
                                error_message = data.get('message', 'No error message')
                                print(f"[TWELVE_DATA] ❌ API error: code={error_code}, message={error_message}")
                                return None
                            
                            return data
                        except json.JSONDecodeError as e:
                            print(f"[TWELVE_DATA] ❌ Invalid JSON response: {e}")
                            print(f"[TWELVE_DATA] Response preview: {response.text[:200]}")
                            return None
                    
                    elif response.status_code == 429:
                        # Rate limit - wait and retry
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        print(f"[TWELVE_DATA] ⚠️ Rate limit (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    elif 500 <= response.status_code < 600:
                        # Server error - retry with backoff
                        wait_time = 2 ** attempt
                        print(f"[TWELVE_DATA] ⚠️ Server error {response.status_code}, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    else:
                        # Client error (4xx) - don't retry
                        print(f"[TWELVE_DATA] ❌ HTTP {response.status_code}: {response.text[:200]}")
                        return None
                        
            except httpx.TimeoutException:
                wait_time = 2 ** attempt
                print(f"[TWELVE_DATA] ⚠️ Timeout, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Timeout after {max_retries} attempts")
                    return None
                    
            except httpx.RequestError as e:
                wait_time = 2 ** attempt
                print(f"[TWELVE_DATA] ⚠️ Request error: {type(e).__name__}: {e}, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"[TWELVE_DATA] ❌ Request failed after {max_retries} attempts: {type(e).__name__}: {e}")
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
