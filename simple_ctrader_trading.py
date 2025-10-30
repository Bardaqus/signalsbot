"""
Simple cTrader Trading - Uses REST API to place real trades
"""
import asyncio
import aiohttp
import json
import ssl
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from config import Config


class SimpleCTraderTrading:
    """Simple cTrader trading using REST API"""
    
    def __init__(self):
        self.access_token = Config.CTRADER_ACCESS_TOKEN
        self.account_id = 44749280  # Internal account ID
        self.account_number = 9615885  # Display account number
        self.base_url = "https://openapi.ctrader.com"
        
    def _get_ssl_context(self):
        """Get SSL context that doesn't verify certificates"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
        
    async def place_trade(self, symbol: str, trade_type: str, volume: float, 
                         stop_loss: float, take_profit: float) -> Optional[Dict]:
        """Place a real trade using cTrader API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # First, get account info to verify connection
            account_info = await self._get_account_info()
            if not account_info:
                logger.error("❌ Failed to get account info")
                return None
            
            # Get symbol info
            symbol_info = await self._get_symbol_info(symbol)
            if not symbol_info:
                logger.error(f"❌ Symbol {symbol} not found")
                return None
            
            # Place the trade
            trade_data = {
                "accountId": self.account_id,
                "symbolId": symbol_info.get('symbolId'),
                "orderType": "MARKET",
                "tradeSide": "BUY" if trade_type.upper() == "BUY" else "SELL",
                "volume": int(volume * 100000),  # Convert to micro lots
                "stopLoss": int(stop_loss * 100000),
                "takeProfit": int(take_profit * 100000),
                "comment": "Auto-generated signal"
            }
            
            logger.info(f"📤 Placing trade: {symbol} {trade_type} @ {volume} lots")
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{self.base_url}/trading/orders",
                    headers=headers,
                    json=trade_data
                ) as response:
                    if response.status in [200, 201]:
                        trade_response = await response.json()
                        logger.info(f"✅ Trade placed successfully: {trade_response}")
                        return trade_response
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Trade failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error placing trade: {e}")
            return None
    
    async def _get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    f"{self.base_url}/accounts",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        account_data = await response.json()
                        logger.info(f"📊 Account info: {account_data}")
                        return account_data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to get account info: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting account info: {e}")
            return None
    
    async def _get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get symbol information"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    f"{self.base_url}/symbols",
                    headers=headers,
                    params={'accountId': self.account_id}
                ) as response:
                    if response.status == 200:
                        symbols_data = await response.json()
                        symbols = symbols_data.get('data', [])
                        for sym in symbols:
                            if sym.get('symbolName') == symbol:
                                logger.info(f"📊 Found symbol {symbol}: {sym}")
                                return sym
                        
                        logger.error(f"❌ Symbol {symbol} not found")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to get symbols: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting symbol info: {e}")
            return None


async def test_trading():
    """Test trading functionality"""
    trading = SimpleCTraderTrading()
    
    try:
        # Test placing a trade
        result = await trading.place_trade(
            symbol="EURUSD",
            trade_type="BUY",
            volume=0.01,  # 0.01 lots
            stop_loss=1.0500,
            take_profit=1.0600
        )
        
        if result:
            logger.info("✅ Test trade placed successfully!")
        else:
            logger.error("❌ Failed to place test trade")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_trading())
