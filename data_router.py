"""
Unified Data Router - Strict source policy enforcement
FOREX -> cTrader only
CRYPTO -> Binance only  
GOLD/INDEXES -> Yahoo Finance only
"""
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
import time


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


def get_price(symbol: str, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[float], Optional[str], str]:
    """
    Get price for symbol using strict source policy
    
    Args:
        symbol: Symbol name (e.g., "EURUSD", "BTCUSDT", "XAUUSD", "BRENT")
        asset_class: Optional asset class override (auto-detected if None)
    
    Returns:
        Tuple of (price: float or None, reason: str or None, source: str)
        source will be "CTRADER", "BINANCE", or "YAHOO"
    
    Raises:
        ForbiddenDataSourceError: If attempting to use forbidden source
    """
    if asset_class is None:
        asset_class = _detect_asset_class(symbol)
    
    start_time = time.time()
    
    if asset_class == AssetClass.FOREX:
        # FOREX: cTrader only
        try:
            from working_combined_bot import get_forex_price_ctrader
            price, reason = get_forex_price_ctrader(symbol)
            latency_ms = int((time.time() - start_time) * 1000)
            if price:
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=CTRADER, price={price:.5f}, latency={latency_ms}ms")
            else:
                print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=CTRADER, price=None, reason={reason}, latency={latency_ms}ms")
            return price, reason, "CTRADER"
        except ImportError:
            raise ForbiddenDataSourceError(f"FOREX symbol {symbol} must use cTrader, but cTrader client not available")
    
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
            
            if asset_class == AssetClass.GOLD:
                # Gold: use Yahoo Finance
                from working_combined_bot import get_gold_price_from_yahoo
                yahoo_data = _run_async(get_gold_price_from_yahoo())
                
                latency_ms = int((time.time() - start_time) * 1000)
                if yahoo_data and yahoo_data.get("price"):
                    price = yahoo_data["price"]
                    source_type = yahoo_data.get("source", "yahoo")
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO ({source_type}), price={price:.2f}, latency={latency_ms}ms")
                    return price, None, f"YAHOO_{source_type.upper()}"
                else:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price=None, reason=yahoo_unavailable, latency={latency_ms}ms")
                    return None, "yahoo_unavailable", "YAHOO"
            else:
                # Index: use Yahoo Finance
                from working_combined_bot import get_index_price_yahoo
                price = _run_async(get_index_price_yahoo(symbol))
                
                latency_ms = int((time.time() - start_time) * 1000)
                if price:
                    print(f"[DATA_ROUTER] {symbol}: SOURCE_USED=YAHOO, price={price:.2f}, latency={latency_ms}ms")
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


def get_candles(symbol: str, timeframe: str = "1m", limit: int = 120, asset_class: Optional[AssetClass] = None) -> Tuple[Optional[List[Dict]], Optional[str], str]:
    """
    Get candles for symbol using strict source policy
    
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
        # FOREX: cTrader only (candles not implemented yet, return None)
        print(f"[DATA_ROUTER] {symbol}: CANDLES requested from CTRADER (not implemented yet)")
        return None, "candles_not_implemented", "CTRADER"
    
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
