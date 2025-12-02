"""
cTrader Open API integration for trading operations
"""
import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from config import Config


class CTraderAPI:
    """cTrader Open API client for trading operations"""
    
    def __init__(self):
        self.client_id = Config.CTRADER_CLIENT_ID
        self.client_secret = Config.CTRADER_CLIENT_SECRET
        self.redirect_uri = Config.CTRADER_REDIRECT_URI
        self.api_url = Config.CTRADER_API_URL
        self.auth_url = Config.CTRADER_AUTH_URL
        self.access_token: Optional[str] = Config.CTRADER_ACCESS_TOKEN
        self.refresh_token: Optional[str] = Config.CTRADER_REFRESH_TOKEN or None
        self.account_id: Optional[str] = None
        
    def _get_ssl_context(self):
        """Get SSL context that doesn't verify certificates"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
        
    async def get_auth_url(self) -> str:
        """Generate OAuth2 authorization URL with proper URL encoding"""
        from urllib.parse import urlencode, urljoin

        # Ensure base ends with '/'
        base = self.auth_url if self.auth_url.endswith('/') else self.auth_url + '/'
        path = urljoin(base, 'authorize')

        auth_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'trading'
        }

        query = urlencode(auth_params, safe=':/')
        auth_url = f"{path}?{query}"
        logger.info(f"Generated auth URL: {auth_url}")
        return auth_url
    
    async def exchange_code_for_token(self, authorization_code: str) -> bool:
        """Exchange authorization code for access token"""
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'code': authorization_code
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/oauth/token",
                    data=token_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                ) as response:
                    if response.status == 200:
                        token_response = await response.json()
                        self.access_token = token_response.get('access_token')
                        self.refresh_token = token_response.get('refresh_token')
                        
                        logger.info("Successfully obtained access token")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to exchange code for token: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return False
    
    async def refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False
            
        token_data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/oauth/token",
                    data=token_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                ) as response:
                    if response.status == 200:
                        token_response = await response.json()
                        self.access_token = token_response.get('access_token')
                        self.refresh_token = token_response.get('refresh_token')
                        
                        logger.info("Successfully refreshed access token")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to refresh token: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False
    
    async def get_accounts(self) -> List[Dict]:
        """Get list of trading accounts"""
        if not self.access_token:
            logger.error("No access token available")
            return []
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/accounts",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        accounts_data = await response.json()
                        logger.info(f"Retrieved {len(accounts_data)} accounts")
                        return accounts_data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get accounts: {response.status} - {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
    
    async def get_symbols(self) -> List[Dict]:
        """Get available trading symbols"""
        if not self.access_token:
            logger.error("No access token available")
            return []
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/symbols",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        symbols_data = await response.json()
                        logger.info(f"Retrieved {len(symbols_data)} symbols")
                        return symbols_data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get symbols: {response.status} - {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return []
    
    async def get_current_quotes(self, symbol_name: str) -> Optional[Dict]:
        """Get current quote for a symbol"""
        # For demo purposes, return mock quotes without authentication
        if not self.access_token:
            logger.info("No access token - using demo quotes")
            return self._get_demo_quote(symbol_name)
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        params = {'symbol': symbol_name}
        
        try:
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    f"{self.api_url}/quotes",
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        quotes_data = await response.json()
                        if quotes_data:
                            logger.info(f"Retrieved quote for {symbol_name}: {quotes_data[0]}")
                            return quotes_data[0]
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get quotes: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting quotes: {e}")
            return None
    
    async def place_trade(self, symbol_name: str, trade_type: str, volume: float, 
                         stop_loss: Optional[float] = None, 
                         take_profit: Optional[float] = None,
                         comment: str = "") -> Optional[Dict]:
        """
        Place a trade order
        
        Args:
            symbol_name: Trading symbol (e.g., 'EURUSD')
            trade_type: 'BUY' or 'SELL'
            volume: Trade volume
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            comment: Trade comment (optional)
        """
        if not self.access_token:
            logger.info("No access token - simulating trade execution")
            return self._simulate_trade(symbol_name, trade_type, volume, stop_loss, take_profit, comment)
            
        if not self.account_id:
            logger.error("No account ID set")
            return None
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        trade_data = {
            'symbol': symbol_name,
            'trade_type': trade_type.upper(),
            'volume': volume,
            'account_id': self.account_id,
            'comment': comment
        }
        
        if stop_loss:
            trade_data['stop_loss'] = stop_loss
        if take_profit:
            trade_data['take_profit'] = take_profit
            
        try:
            connector = aiohttp.TCPConnector(ssl=self._get_ssl_context())
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    f"{self.api_url}/trades",
                    headers=headers,
                    json=trade_data
                ) as response:
                    if response.status in [200, 201]:
                        trade_response = await response.json()
                        logger.info(f"Successfully placed {trade_type} trade for {symbol_name}")
                        return trade_response
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to place trade: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error placing trade: {e}")
            return None
    
    async def get_positions(self) -> List[Dict]:
        """Get current open positions"""
        if not self.access_token:
            logger.error("No access token available")
            return []
            
        if not self.account_id:
            logger.error("No account ID set")
            return []
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/positions",
                    headers=headers,
                    params={'account_id': self.account_id}
                ) as response:
                    if response.status == 200:
                        positions_data = await response.json()
                        logger.info(f"Retrieved {len(positions_data)} positions")
                        return positions_data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get positions: {response.status} - {error_text}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def set_account_id(self, account_id: str):
        """Set the account ID for trading operations"""
        self.account_id = account_id
        logger.info(f"Set account ID to: {account_id}")
    
    def _get_demo_quote(self, symbol_name: str) -> Dict:
        """Get demo quote for a symbol without authentication"""
        import random
        import time
        
        # Base prices for major pairs
        base_prices = {
            "EURUSD": 1.0650, "GBPUSD": 1.2500, "USDJPY": 150.00,
            "USDCHF": 0.9000, "AUDUSD": 0.6500, "USDCAD": 1.3500,
            "NZDUSD": 0.6000, "EURJPY": 160.00, "GBPJPY": 187.50,
            "AUDJPY": 97.50, "CHFJPY": 166.67, "EURGBP": 0.8520,
            "EURCHF": 0.9585, "GBPCHF": 1.1250, "AUDCAD": 0.8775
        }
        
        base_price = base_prices.get(symbol_name, 1.0000)
        
        # Add some randomness to simulate market movement
        if "JPY" in symbol_name:
            variation = random.uniform(-0.5, 0.5)
            price = round(base_price + variation, 2)
            spread = 0.02
        else:
            variation = random.uniform(-0.002, 0.002)
            price = round(base_price + variation, 4)
            spread = 0.0002
        
        # Create bid/ask spread
        bid = round(price - spread/2, 4 if "JPY" not in symbol_name else 2)
        ask = round(price + spread/2, 4 if "JPY" not in symbol_name else 2)
        
        return {
            'symbol': symbol_name,
            'bid': bid,
            'ask': ask,
            'timestamp': int(time.time() * 1000),
            'source': 'demo'
        }
    
    def _simulate_trade(self, symbol_name: str, trade_type: str, volume: float, 
                       stop_loss: Optional[float] = None, 
                       take_profit: Optional[float] = None,
                       comment: str = "") -> Dict:
        """Simulate trade execution without authentication"""
        import random
        import time
        
        # Generate a mock trade ID
        trade_id = f"DEMO_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Get current quote for entry price
        quote = self._get_demo_quote(symbol_name)
        entry_price = (quote['bid'] + quote['ask']) / 2
        
        # Simulate trade execution
        trade_result = {
            'trade_id': trade_id,
            'symbol': symbol_name,
            'trade_type': trade_type,
            'volume': volume,
            'entry_price': round(entry_price, 4 if "JPY" not in symbol_name else 2),
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'comment': comment,
            'status': 'EXECUTED',
            'timestamp': int(time.time() * 1000),
            'account_id': self.account_id or 'demo_account',
            'source': 'demo_simulation'
        }
        
        logger.info(f"Simulated trade: {trade_type} {volume} {symbol_name} @ {trade_result['entry_price']}")
        
        return trade_result
