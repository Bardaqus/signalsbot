"""
Unified Data Router - Strict source policy enforcement
FOREX -> Twelve Data only
CRYPTO -> Binance only  
GOLD/INDEXES -> Yahoo Finance only
"""
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
import time

# Global DataRouter instance (set via Dependency Injection)
_data_router_instance: Optional['DataRouter'] = None


class AssetClass(Enum):
    """Asset class enumeration"""
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"
    GOLD = "GOLD"
    INDEX = "INDEX"


class ForbiddenDataSourceError(Exception):
    """Raised when attempting to use a forbidden data source"""
    pass


# Yahoo Finance ticker mappings
YAHOO_TICKER_MAP = {
    "XAUUSD": ["XAUUSD=X", "GC=F"],  # Gold: spot first, then futures
    "BRENT": ["BZ=F"],  # Brent crude oil futures
    "USOIL": ["CL=F"],  # WTI crude oil futures
    "SPX": ["^GSPC"],  # S&P 500
    "NDX": ["^NDX"],   # NASDAQ 100
    "DJI": ["^DJI"],   # Dow Jones
}


def normalize_price(value: Any) -> Optional[float]:
    """
    Normalize price value to float or None.
    
    Handles various input types:
    - None -> None
    - tuple/list -> take first element, then convert to float
    - int/float -> convert to float
    - str -> try to parse as float
    - other -> return None
    
    Args:
        value: Price value (can be any type)
    
    Returns:
        float: Normalized price as float, or None if cannot normalize
    """
    if value is None:
        return None
    
    # Handle tuple/list - take first element
    if isinstance(value, (tuple, list)):
        if len(value) == 0:
            return None
        value = value[0]
    
    # Handle int/float
    if isinstance(value, (int, float)):
        result = float(value)
        return result if result > 0 else None
    
    # Handle string
    if isinstance(value, str):
        try:
            result = float(value)
            return result if result > 0 else None
        except (ValueError, TypeError):
            return None
    
    # Unknown type
    return None


def _detect_asset_class(symbol: str) -> AssetClass:
    """Detect asset class from symbol name"""
    symbol_upper = symbol.upper()
    
    # Gold
    if symbol_upper in ["XAUUSD", "GOLD", "XAU/USD"]:
        return AssetClass.GOLD
    
    # Indexes
    if symbol_upper in ["BRENT", "USOIL", "SPX", "NDX", "DJI", "US500", "NAS100", "DOW"]:
        return AssetClass.INDEX
    
    # Crypto (common patterns)
    crypto_suffixes = ["USDT", "BTC", "ETH", "BNB", "ADA", "SOL", "XRP", "DOT", "DOGE", "AVAX", "MATIC"]
    if any(symbol_upper.endswith(suffix) for suffix in crypto_suffixes):
        return AssetClass.CRYPTO
    
    # Default to FOREX
    return AssetClass.FOREX


class DataRouter:
    """Data router with dependency injection for data sources"""
    
    def __init__(self, twelve_data_client: Optional[Any] = None):
        """
        Initialize DataRouter with injected dependencies
        
        Args:
            twelve_data_client: TwelveDataClient instance (required for FOREX)
        """
        self.twelve_data_client = twelve_data_client
    
    def get_price(self, symbol: str, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[float], Optional[str], str]:
        """
        Get price for symbol using strict source policy
        
        Args:
            symbol: Symbol name (e.g., "EURUSD", "BTCUSDT", "XAUUSD", "BRENT")
            asset_class: Optional asset class override (auto-detected if None)
        
        Returns:
            Tuple of (price: float or None, reason: str or None, source: str)
            source will be "TWELVE_DATA", "BINANCE", or "YAHOO"
        
        Raises:
            ForbiddenDataSourceError: If attempting to use forbidden source
        """
        if asset_class is None:
            asset_class = _detect_asset_class(symbol)
        
        # STRICT ENFORCEMENT: Verify detected class matches symbol patterns
        symbol_upper = symbol.upper()
        if asset_class == AssetClass.FOREX:
            # FOREX symbols must NOT be Gold/Index/Crypto
            if symbol_upper in ["XAUUSD", "GOLD", "XAU/USD"]:
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as FOREX but is actually GOLD. Use GOLD asset class.")
            if any(symbol_upper.endswith(suffix) for suffix in ["USDT", "BTC", "ETH"]):
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as FOREX but is actually CRYPTO. Use CRYPTO asset class.")
        elif asset_class == AssetClass.GOLD:
            # GOLD must NOT be treated as FOREX
            if symbol_upper not in ["XAUUSD", "GOLD", "XAU/USD"]:
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as GOLD but doesn't match gold patterns.")
        elif asset_class == AssetClass.CRYPTO:
            # CRYPTO must have crypto suffixes
            if not any(symbol_upper.endswith(suffix) for suffix in ["USDT", "BTC", "ETH", "BNB", "ADA", "SOL", "XRP", "DOT", "DOGE", "AVAX", "MATIC"]):
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as CRYPTO but doesn't match crypto patterns.")
        
        start_time = time.time()
        
        if asset_class == AssetClass.FOREX:
            # FOREX: Twelve Data only
            if not self.twelve_data_client:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason=twelve_data_client_not_initialized, latency={latency_ms}ms")
                return None, "twelve_data_client_not_initialized", "TWELVE_DATA"
            
            try:
                import asyncio
                
                # Get price from Twelve Data (async call)
                # IMPORTANT: This sync method should NOT be called from async context
                # If called from async context, use get_price_async() instead
                # For sync calls, we need to create a new event loop (but this is problematic)
                # The proper solution: all callers should use async version
                try:
                    # Check if we're in async context
                    asyncio.get_running_loop()
                    # We're in async context - this is an error
                    raise RuntimeError("Cannot call sync get_price() from async context. Use async get_price_async() instead.")
                except RuntimeError:
                    # No running loop - we're in sync context
                    # Create a new loop ONLY if no loop exists
                    # This is the problematic case, but necessary for backward compatibility
                    price, reason = asyncio.run(self.twelve_data_client.get_price(symbol))
                except Exception as e:
                    # If get_running_loop() raised different error, re-raise
                    if "no running event loop" not in str(e).lower():
                        raise
                    # No running loop - create new one
                    price, reason = asyncio.run(self.twelve_data_client.get_price(symbol))
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                if price is not None:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price={price:.5f}, latency={latency_ms}ms")
                    return price, None, "TWELVE_DATA"
                else:
                    # Use reason from get_price (can be "twelve_data_cooldown" or "twelve_data_unavailable")
                    final_reason = reason or "twelve_data_unavailable"
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason={final_reason}, latency={latency_ms}ms")
                    return None, final_reason, "TWELVE_DATA"
            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, ERROR: {type(e).__name__}: {e}, latency={latency_ms}ms")
                return None, f"twelve_data_error: {type(e).__name__}", "TWELVE_DATA"
        
        elif asset_class == AssetClass.CRYPTO:
            # CRYPTO: Binance only
            try:
                from working_combined_bot import get_real_crypto_price
                price = get_real_crypto_price(symbol)
                latency_ms = int((time.time() - start_time) * 1000)
                if price:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=BINANCE, price={price:.6f}, latency={latency_ms}ms")
                else:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=BINANCE, price=None, latency={latency_ms}ms")
                return price, None if price else "binance_unavailable", "BINANCE"
            except ImportError:
                raise ForbiddenDataSourceError(f"CRYPTO symbol {symbol} must use Binance API")
        
        elif asset_class in [AssetClass.GOLD, AssetClass.INDEX]:
            # GOLD/INDEX: Yahoo Finance only
            try:
                # Use synchronous wrapper for async functions
                # This avoids event loop conflicts
                import asyncio
                import concurrent.futures
                
                def _run_async(coro):
                    """Run async function in new event loop"""
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Loop is running - use thread executor
                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(asyncio.run, coro)
                                return future.result(timeout=15)
                        else:
                            return asyncio.run(coro)
                    except RuntimeError:
                        # No event loop - create new one
                        return asyncio.run(coro)
                
                def _validate_price(symbol: str, price: Optional[float], asset_class: AssetClass) -> Tuple[bool, Optional[str]]:
                    """Validate price is within reasonable range (wide sanity check)
                    
                    Args:
                        symbol: Symbol name
                        price: Price value (can be None, tuple, list, int, float, str)
                        asset_class: Asset class
                    
                    Returns:
                        Tuple of (is_valid: bool, reason: str or None)
                    """
                    # CRITICAL: Normalize price first (handles tuple/list/str/etc)
                    price = normalize_price(price)
                    
                    # CRITICAL: Handle None price first - never compare None with numbers
                    if price is None:
                        return False, "yahoo_no_price: price is None or cannot normalize"
                    
                    # Basic sanity: price must be > 0
                    if price <= 0:
                        return False, f"yahoo_invalid_price: {price:.2f} is not positive"
                    
                    if asset_class == AssetClass.GOLD:
                        # Gold: wide sanity range 50-20000 USD/oz (allows for extreme market conditions)
                        # Note: For Yahoo futures (GC=F), price can be higher than spot, so range is wide
                        if price < 50 or price > 20000:
                            return False, f"yahoo_invalid_price: {price:.2f} outside sanity range [50, 20000]"
                        return True, None
                    elif asset_class == AssetClass.INDEX:
                        # Indexes: reasonable range depends on symbol
                        if symbol.upper() in ["BRENT", "USOIL"]:
                            # Oil: wide sanity range 1-1000 USD/barrel
                            if price < 1 or price > 1000:
                                return False, f"yahoo_invalid_price: {price:.2f} outside sanity range [1, 1000]"
                        else:
                            # Other indexes: wide sanity range 1-100000
                            if price < 1 or price > 100000:
                                return False, f"yahoo_invalid_price: {price:.2f} outside sanity range [1, 100000]"
                        return True, None
                    return True, None
                
                if asset_class == AssetClass.GOLD:
                    # Gold: use Yahoo Finance with validation
                    from working_combined_bot import get_gold_price_from_yahoo
                    yahoo_data = _run_async(get_gold_price_from_yahoo())
                    
                    latency_ms = int((time.time() - start_time) * 1000)
                    if yahoo_data and isinstance(yahoo_data, dict) and yahoo_data.get("price"):
                        try:
                            # Normalize price first (handles tuple/list/str/etc)
                            raw_price = yahoo_data["price"]
                            price = normalize_price(raw_price)
                            
                            if price is None:
                                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price=None, reason=yahoo_price_normalize_failed (raw={raw_price!r}), latency={latency_ms}ms")
                                return None, "yahoo_price_normalize_failed", "YAHOO"
                            
                            source_type = yahoo_data.get("source", "yahoo")
                            ticker = yahoo_data.get("meta", {}).get("ticker", "unknown")
                            
                            # Validate price (sanity check)
                            is_valid, validation_reason = _validate_price(symbol, price, asset_class)
                            if not is_valid:
                                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO ({source_type}), ticker={ticker}, price={price:.2f}, valid=False, reason={validation_reason}, latency={latency_ms}ms")
                                return None, validation_reason, f"YAHOO_{source_type.upper()}"
                            
                            print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO ({source_type}), ticker={ticker}, price={price:.2f}, valid=True, latency={latency_ms}ms")
                            return price, None, f"YAHOO_{source_type.upper()}"
                        except (ValueError, TypeError, KeyError) as e:
                            print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price=None, reason=yahoo_parse_error ({type(e).__name__}: {e}), latency={latency_ms}ms")
                            return None, f"yahoo_parse_error: {type(e).__name__}", "YAHOO"
                    else:
                        print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price=None, reason=yahoo_unavailable, latency={latency_ms}ms")
                        return None, "yahoo_unavailable", "YAHOO"
                else:
                    # Index: use Yahoo Finance with validation
                    from working_combined_bot import get_index_price_yahoo
                    raw_price = _run_async(get_index_price_yahoo(symbol))
                    
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    # Normalize price first (handles tuple/list/str/etc)
                    price = normalize_price(raw_price)
                    
                    if price is not None:
                        # Validate price (handles None internally, but double-check here)
                        is_valid, validation_reason = _validate_price(symbol, price, asset_class)
                        if not is_valid:
                            print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price={price:.2f if price else None}, valid=False, reason={validation_reason}, latency={latency_ms}ms")
                            return None, validation_reason, "YAHOO"
                        
                        print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price={price:.2f}, valid=True, latency={latency_ms}ms")
                        return price, None, "YAHOO"
                    else:
                        print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price=None, reason=yahoo_unavailable, latency={latency_ms}ms")
                        return None, "yahoo_unavailable", "YAHOO"
            except ImportError:
                raise ForbiddenDataSourceError(f"{asset_class.value} symbol {symbol} must use Yahoo Finance")
            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, ERROR: {type(e).__name__}: {e}, latency={latency_ms}ms")
                return None, f"yahoo_error: {type(e).__name__}", "YAHOO"
        
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")
    
    async def get_price_async(self, symbol: str, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[float], Optional[str], str]:
        """
        Async version of get_price - must be called from async context
        
        Args:
            symbol: Symbol name (e.g., "EURUSD", "BTCUSDT", "XAUUSD", "BRENT")
            asset_class: Optional asset class override (auto-detected if None)
        
        Returns:
            Tuple of (price: float or None, reason: str or None, source: str)
        """
        if asset_class is None:
            asset_class = _detect_asset_class(symbol)
        
        # STRICT ENFORCEMENT: Verify detected class matches symbol patterns
        symbol_upper = symbol.upper()
        if asset_class == AssetClass.FOREX:
            # FOREX symbols must NOT be Gold/Index/Crypto
            if symbol_upper in ["XAUUSD", "GOLD", "XAU/USD"]:
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as FOREX but is actually GOLD. Use GOLD asset class.")
            if any(symbol_upper.endswith(suffix) for suffix in ["USDT", "BTC", "ETH"]):
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as FOREX but is actually CRYPTO. Use CRYPTO asset class.")
        elif asset_class == AssetClass.GOLD:
            # GOLD must NOT be treated as FOREX
            if symbol_upper not in ["XAUUSD", "GOLD", "XAU/USD"]:
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as GOLD but doesn't match gold patterns.")
        elif asset_class == AssetClass.CRYPTO:
            # CRYPTO must have crypto suffixes
            if not any(symbol_upper.endswith(suffix) for suffix in ["USDT", "BTC", "ETH", "BNB", "ADA", "SOL", "XRP", "DOT", "DOGE", "AVAX", "MATIC"]):
                raise ForbiddenDataSourceError(f"Symbol {symbol} detected as CRYPTO but doesn't match crypto patterns.")
        
        start_time = time.time()
        
        if asset_class == AssetClass.FOREX:
            # FOREX: Twelve Data only
            # CRITICAL: For signal generation, use max_retries=0 (single-shot, no retries)
            if not self.twelve_data_client:
                latency_ms = int((time.time() - start_time) * 1000)
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason=twelve_data_client_not_initialized, latency={latency_ms}ms")
                return None, "twelve_data_client_not_initialized", "TWELVE_DATA"
            
            try:
                # Direct async call - no loop creation needed
                # Use max_retries=0 for signal generation (single-shot, no retries)
                # get_price now returns (price, reason) tuple
                price, reason = await self.twelve_data_client.get_price(symbol, max_retries_override=0)
                latency_ms = int((time.time() - start_time) * 1000)
                
                if price is not None:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price={price:.5f}, latency={latency_ms}ms, requests=1")
                    return price, None, "TWELVE_DATA"
                else:
                    # Use detailed reason from get_price
                    final_reason = reason or "exception:UnknownError:No reason provided"
                    # Normalize reason codes for backward compatibility
                    if final_reason == "cooldown":
                        final_reason = "twelve_data_cooldown"
                    elif final_reason == "rate_limit_429":
                        final_reason = "rate_limit_429"
                    elif final_reason in ["timeout", "network_error", "parse_error", "invalid_api_key"]:
                        # Keep detailed reasons as-is
                        pass
                    elif final_reason.startswith("exception:"):
                        # Already formatted as exception:Type:message - keep as-is
                        pass
                    elif final_reason.startswith("twelve_data_unavailable"):
                        # Already has prefix, keep as-is
                        pass
                    else:
                        # Unknown reason - wrap it as exception
                        final_reason = f"exception:UnknownError:{final_reason}"
                    
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason={final_reason}, latency={latency_ms}ms")
                    return None, final_reason, "TWELVE_DATA"
            except RuntimeError as e:
                # Circuit breaker error from _throttle or client closed
                error_type = type(e).__name__
                error_msg = str(e)
                latency_ms = int((time.time() - start_time) * 1000)
                if "Circuit breaker" in error_msg or "closed" in error_msg.lower():
                    reason = "twelve_data_cooldown"
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason={reason}, latency={latency_ms}ms, exception={error_type}: {error_msg}")
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.exception(f"[DATA_ROUTER] RuntimeError: {error_type}: {error_msg}")
                    return None, reason, "TWELVE_DATA"
                # Other RuntimeError
                reason = f"exception:{error_type}:{error_msg}"
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason={reason}, latency={latency_ms}ms")
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"[DATA_ROUTER] RuntimeError: {error_type}: {error_msg}")
                import traceback
                print(f"[DATA_ROUTER] Traceback: {traceback.format_exc()}")
                return None, reason, "TWELVE_DATA"
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                latency_ms = int((time.time() - start_time) * 1000)
                reason = f"exception:{error_type}:{error_msg}"
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=TWELVE_DATA, price=None, reason={reason}, latency={latency_ms}ms")
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"[DATA_ROUTER] Exception: {error_type}: {error_msg}")
                import traceback
                print(f"[DATA_ROUTER] Traceback: {traceback.format_exc()}")
                return None, reason, "TWELVE_DATA"
        
        # For non-FOREX, delegate to sync version (they don't use async)
        # This is a bit of a hack, but keeps the code simpler
        return self.get_price(symbol, asset_class)
    
    def get_candles(self, symbol: str, timeframe: str = "1m", limit: int = 120, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[List[Dict]], Optional[str], str]:
        """
        Get candles for symbol using strict source policy (sync version)
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe (e.g., "1m", "5m", "1h")
            limit: Number of candles to return
            asset_class: Optional asset class override
        
        Returns:
            Tuple of (candles: List[Dict] or None, reason: str or None, source: str)
        
        Raises:
            ForbiddenDataSourceError: If attempting to use forbidden source
        """
        if asset_class is None:
            asset_class = _detect_asset_class(symbol)
        
        if asset_class == AssetClass.FOREX:
            # FOREX: Twelve Data candles
            if not self.twelve_data_client:
                return None, "twelve_data_client_not_initialized", "TWELVE_DATA"
            
            try:
                import asyncio
                
                # Map timeframe to Twelve Data interval
                interval_map = {
                    '1m': '1min',
                    '5m': '5min',
                    '15m': '15min',
                    '30m': '30min',
                    '1h': '1h',
                    '4h': '4h',
                    '1d': '1day',
                    '1day': '1day',
                }
                interval = interval_map.get(timeframe, '1h')
                
                # IMPORTANT: This sync method should NOT be called from async context
                # If called from async context, use get_candles_async() instead
                try:
                    # Check if we're in async context
                    asyncio.get_running_loop()
                    # We're in async context - this is an error
                    raise RuntimeError("Cannot call sync get_candles() from async context. Use async get_candles_async() instead.")
                except RuntimeError:
                    # No running loop - we're in sync context
                    # Create a new loop ONLY if no loop exists
                    candles = asyncio.run(self.twelve_data_client.get_time_series(symbol, interval=interval, outputsize=limit))
                except Exception as e:
                    # If get_running_loop() raised different error, re-raise
                    if "no running event loop" not in str(e).lower():
                        raise
                    # No running loop - create new one
                    candles = asyncio.run(self.twelve_data_client.get_time_series(symbol, interval=interval, outputsize=limit))
                
                if candles:
                    print(f"[DATA_ROUTER] {symbol}: CANDLES from TWELVE_DATA: {len(candles)} candles, interval={interval}")
                    return candles, None, "TWELVE_DATA"
                else:
                    return None, "twelve_data_candles_unavailable", "TWELVE_DATA"
            except Exception as e:
                print(f"[DATA_ROUTER] {symbol}: CANDLES from TWELVE_DATA, ERROR: {type(e).__name__}: {e}")
                return None, f"twelve_data_candles_error: {type(e).__name__}", "TWELVE_DATA"
        
        elif asset_class == AssetClass.CRYPTO:
            # CRYPTO: Binance only (candles not implemented yet)
            print(f"[DATA_ROUTER] {symbol}: CANDLES requested from BINANCE (not implemented yet)")
            return None, "candles_not_implemented", "BINANCE"
        
        elif asset_class in [AssetClass.GOLD, AssetClass.INDEX]:
            # GOLD/INDEX: Yahoo Finance only (candles not implemented yet)
            print(f"[DATA_ROUTER] {symbol}: CANDLES requested from YAHOO (not implemented yet)")
            return None, "candles_not_implemented", "YAHOO"
        
        else:
            raise ValueError(f"Unknown asset class: {asset_class}")


def set_data_router(router: DataRouter):
    """Set global DataRouter instance (Dependency Injection)"""
    global _data_router_instance
    _data_router_instance = router


def get_data_router() -> Optional[DataRouter]:
    """Get global DataRouter instance"""
    return _data_router_instance


def get_price(symbol: str, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[float], Optional[str], str]:
    """
    Get price for symbol (wrapper function for backward compatibility)
    
    Uses global DataRouter instance if set, otherwise creates temporary one
    
    WARNING: This sync function creates a new event loop for FOREX (Twelve Data).
    If called from async context, use get_price_async() instead.
    """
    global _data_router_instance
    if _data_router_instance:
        return _data_router_instance.get_price(symbol, asset_class)
    else:
        # Fallback: create temporary router (will fail for FOREX without client)
        router = DataRouter(twelve_data_client=None)
        return router.get_price(symbol, asset_class)


def get_candles(symbol: str, timeframe: str = "1m", limit: int = 120, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[List[Dict]], Optional[str], str]:
    """
    Get candles for symbol (wrapper function for backward compatibility)
    
    Uses global DataRouter instance if set, otherwise creates temporary one
    """
    global _data_router_instance
    if _data_router_instance:
        return _data_router_instance.get_candles(symbol, timeframe, limit, asset_class)
    else:
        # Fallback: create temporary router (will fail for FOREX without client)
        router = DataRouter(twelve_data_client=None)
        return router.get_candles(symbol, timeframe, limit, asset_class)
