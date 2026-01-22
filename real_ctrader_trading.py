"""
Real cTrader Trading - Actually opens positions using cTrader API
"""
import asyncio
import aiohttp
import json
import ssl
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from config import Config


class RealCTraderTrading:
    """Real cTrader trading that actually opens positions"""
    
    def __init__(self):
        self.access_token = Config.CTRADER_ACCESS_TOKEN
        self.refresh_token = "UVNGZPSDSbB-Vi81R2DX8NANvIkESfE_yXnNS6z1RC4"
        self.account_id = 44749280  # Internal account ID
        self.account_number = 9615885  # Display account number
        self.base_url = "https://openapi.ctrader.com"
        
    def _get_ssl_context(self):
        """Get SSL context that doesn't verify certificates"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
        
    async def test_connection(self):
        """Test connection to cTrader API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            logger.info("🔌 Testing cTrader API connection...")
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                # Test with a simple request
                async with session.get(
                    f"{self.base_url}/v1/accounts",
                    headers=headers
                ) as response:
                    logger.info(f"📊 Response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Connection successful! Data: {data}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Connection failed: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False
    
    async def get_account_info(self):
        """Get account information"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    f"{self.base_url}/v1/accounts",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"📊 Account info: {data}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to get account info: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting account info: {e}")
            return None
    
    async def place_trade(self, symbol: str, trade_type: str, volume: float, 
                         stop_loss: float, take_profit: float) -> Optional[Dict]:
        """Place a real trade using cTrader API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Create trade order
            trade_data = {
                "accountId": self.account_id,
                "symbol": symbol,
                "side": "BUY" if trade_type.upper() == "BUY" else "SELL",
                "volume": volume,
                "stopLoss": stop_loss,
                "takeProfit": take_profit,
                "comment": "Auto-generated signal"
            }
            
            logger.info(f"📤 Placing trade: {symbol} {trade_type} @ {volume} lots")
            logger.info(f"📊 Trade data: {trade_data}")
            
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{self.base_url}/v1/orders",
                    headers=headers,
                    json=trade_data
                ) as response:
                    logger.info(f"📊 Order response status: {response.status}")
                    
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


async def test_real_trading():
    """Test real trading functionality"""
    trading = RealCTraderTrading()
    
    try:
        # Test connection
        if await trading.test_connection():
            logger.info("✅ cTrader API connection successful!")
            
            # Get account info
            account_info = await trading.get_account_info()
            if account_info:
                logger.info("✅ Account info retrieved successfully!")
            
            # Test placing a trade
            result = await trading.place_trade(
                symbol="EURUSD",
                trade_type="BUY",
                volume=0.01,  # 0.01 lots
                stop_loss=1.0500,
                take_profit=1.0600
            )
            
            if result:
                logger.info("🎉 SUCCESS! Real trade placed in your cTrader account!")
            else:
                logger.error("❌ Failed to place trade")
        else:
            logger.error("❌ Failed to connect to cTrader API")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_real_trading())
