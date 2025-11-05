"""
Lightweight Binance API client for fetching crypto market data.
"""
import aiohttp
import ssl
from typing import Dict, List

BINANCE_TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"


class BinanceClient:
    """Fetches market data from Binance public API"""

    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch 24h ticker data for the specified symbols (USDT pairs)."""
        # Binance uses symbols like BTCUSDT; ensure formatting
        wanted = {f"{s.upper()}USDT" for s in symbols}
        session = await self._get_session()
        async with session.get(BINANCE_TICKER_24H, timeout=20) as resp:
            resp.raise_for_status()
            data = await resp.json()
            result: Dict[str, Dict] = {}
            for item in data:
                symbol = item.get("symbol", "")
                if symbol in wanted:
                    base = symbol[:-4]
                    try:
                        result[base] = {
                            "price": float(item["lastPrice"]),
                            "min_price": float(item["lowPrice"]),
                            "max_price": float(item["highPrice"]),
                            "volume": float(item["volume"]),
                            "change_24h": float(item["priceChangePercent"]),
                        }
                    except (KeyError, ValueError, TypeError):
                        # Skip malformed rows
                        continue
            return result




