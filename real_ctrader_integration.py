"""
Real cTrader Integration - Opens actual positions in your cTrader account
"""
import asyncio
import websockets
import json
import ssl
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from config import Config


class RealCTraderAPI:
    """Real cTrader Open API integration using WebSocket"""
    
    def __init__(self):
        self.access_token = Config.CTRADER_ACCESS_TOKEN
        self.refresh_token = "UVNGZPSDSbB-Vi81R2DX8NANvIkESfE_yXnNS6z1RC4"
        self.account_id = 44749280  # Internal account ID
        self.account_number = 9615885  # Display account number
        self.websocket = None
        self.connected = False
        
    def _get_ssl_context(self):
        """Get SSL context that doesn't verify certificates"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
        
    async def connect(self):
        """Connect to cTrader WebSocket API"""
        try:
            # cTrader Open API WebSocket endpoint
            ws_url = "wss://openapi.ctrader.com/OpenAPI/ws"
            
            logger.info("🔌 Connecting to cTrader WebSocket...")
            
            # Connect to WebSocket with SSL context
            self.websocket = await websockets.connect(
                ws_url, 
                ssl=self._get_ssl_context()
            )
            self.connected = True
            
            logger.info("✅ Connected to cTrader WebSocket")
            
            # Authenticate
            if await self._authenticate():
                # Get account info
                await self._get_account_info()
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to cTrader: {e}")
            return False
    
    async def _authenticate(self):
        """Authenticate with cTrader API"""
        try:
            auth_message = {
                "payloadType": "ProtoOAApplicationAuthReq",
                "payload": {
                    "clientId": Config.CTRADER_CLIENT_ID,
                    "clientSecret": Config.CTRADER_CLIENT_SECRET,
                    "accessToken": self.access_token
                }
            }
            
            await self.websocket.send(json.dumps(auth_message))
            logger.info("🔐 Authentication sent to cTrader")
            
            # Wait for authentication response
            response = await self.websocket.recv()
            auth_response = json.loads(response)
            
            if auth_response.get("payloadType") == "ProtoOAApplicationAuthRes":
                logger.info("✅ Successfully authenticated with cTrader")
                return True
            else:
                logger.error(f"❌ Authentication failed: {auth_response}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            return False
    
    async def _get_account_info(self):
        """Get account information"""
        try:
            account_message = {
                "payloadType": "ProtoOAGetAccountListByAccessTokenReq",
                "payload": {
                    "accessToken": self.access_token
                }
            }
            
            await self.websocket.send(json.dumps(account_message))
            response = await self.websocket.recv()
            account_data = json.loads(response)
            
            logger.info(f"📊 Account info received: {account_data}")
            return account_data
            
        except Exception as e:
            logger.error(f"❌ Error getting account info: {e}")
            return None
    
    async def open_position(self, symbol: str, trade_type: str, volume: float, 
                          stop_loss: float, take_profit: float) -> Optional[Dict]:
        """Open a real position in cTrader"""
        try:
            if not self.connected or not self.websocket:
                logger.error("❌ Not connected to cTrader")
                return None
            
            # Get symbol ID
            symbol_id = await self._get_symbol_id(symbol)
            if not symbol_id:
                logger.error(f"❌ Symbol {symbol} not found")
                return None
            
            # Create market order
            order_message = {
                "payloadType": "ProtoOANewOrderReq",
                "payload": {
                    "ctidTraderAccountId": self.account_id,
                    "symbolId": symbol_id,
                    "orderType": "MARKET",
                    "tradeSide": "BUY" if trade_type.upper() == "BUY" else "SELL",
                    "volume": int(volume * 100000),  # Convert to micro lots
                    "stopLoss": int(stop_loss * 100000),
                    "takeProfit": int(take_profit * 100000),
                    "comment": "Auto-generated signal"
                }
            }
            
            logger.info(f"📤 Sending order to cTrader: {symbol} {trade_type} @ {volume} lots")
            await self.websocket.send(json.dumps(order_message))
            
            # Wait for order response
            response = await self.websocket.recv()
            order_response = json.loads(response)
            
            if order_response.get("payloadType") == "ProtoOAExecutionEvent":
                logger.info(f"✅ Position opened successfully: {order_response}")
                return order_response
            else:
                logger.error(f"❌ Order failed: {order_response}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error opening position: {e}")
            return None
    
    async def _get_symbol_id(self, symbol: str) -> Optional[int]:
        """Get symbol ID for trading"""
        try:
            # Request symbol list
            symbol_message = {
                "payloadType": "ProtoOASymbolsListReq",
                "payload": {
                    "ctidTraderAccountId": self.account_id
                }
            }
            
            await self.websocket.send(json.dumps(symbol_message))
            response = await self.websocket.recv()
            symbols_data = json.loads(response)
            
            if symbols_data.get("payloadType") == "ProtoOASymbolsListRes":
                symbols = symbols_data.get("payload", {}).get("symbol", [])
                for sym in symbols:
                    if sym.get("symbolName") == symbol:
                        logger.info(f"📊 Found symbol {symbol} with ID: {sym.get('symbolId')}")
                        return sym.get('symbolId')
                
                logger.error(f"❌ Symbol {symbol} not found in available symbols")
                return None
            else:
                logger.error(f"❌ Failed to get symbols list: {symbols_data}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting symbol ID: {e}")
            return None
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            logger.info("🔌 Disconnected from cTrader")


async def test_ctrader_connection():
    """Test cTrader connection"""
    api = RealCTraderAPI()
    
    try:
        # Connect
        if await api.connect():
            logger.info("✅ cTrader connection successful!")
            
            # Test opening a position
            result = await api.open_position(
                symbol="EURUSD",
                trade_type="BUY",
                volume=0.01,  # 0.01 lots
                stop_loss=1.0500,
                take_profit=1.0600
            )
            
            if result:
                logger.info("✅ Test position opened successfully!")
            else:
                logger.error("❌ Failed to open test position")
        
        # Disconnect
        await api.disconnect()
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_ctrader_connection())
