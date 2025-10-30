"""
Working cTrader Trading Bot - Simplified Approach
This implements the correct flow: OAuth2 -> gRPC -> Trading
"""
import asyncio
import random
import time
import ssl
import grpc
from datetime import datetime
from loguru import logger
from aiogram import Bot
from config import Config

# Import our generated proto files
import ctrader_service_pb2
import ctrader_service_pb2_grpc


class CTraderWorkingBot:
    """Working cTrader trading bot using proper gRPC flow"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.channel_id = "-1002175884868"
        
        # cTrader configuration
        self.client_id = Config.CTRADER_CLIENT_ID
        self.client_secret = Config.CTRADER_CLIENT_SECRET
        self.access_token = Config.CTRADER_ACCESS_TOKEN
        self.account_id = 44749280  # Your account ID
        
        # Trading configuration
        self.forex_pairs = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
            "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "EURAUD", "GBPAUD", "GBPCHF",
            "EURCHF", "AUDCHF", "AUDCAD", "NZDCAD", "EURNZD", "GBPNZD"
        ]
        
        # Symbol mapping (would need to be populated from cTrader)
        self.symbol_ids = {
            "EURUSD": 1,  # Placeholder IDs
            "GBPUSD": 2,
            "USDJPY": 3,
            "USDCHF": 4,
            "AUDUSD": 5,
            "USDCAD": 6,
            "NZDUSD": 7,
            "EURJPY": 8,
            "GBPJPY": 9,
            "EURGBP": 10,
            "AUDJPY": 11,
            "EURAUD": 12,
            "GBPAUD": 13,
            "GBPCHF": 14,
            "EURCHF": 15,
            "AUDCHF": 16,
            "AUDCAD": 17,
            "NZDCAD": 18,
            "EURNZD": 19,
            "GBPNZD": 20
        }
        
        # Client state
        self.channel = None
        self.stub = None
        self.is_connected = False
        self.is_authenticated = False
        self.current_account_id = None
        
        # Trading state
        self.active_trades = {}
        self.msg_id = 0
        
        logger.info("🚀 Working cTrader Trading Bot initialized...")
    
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id += 1
        return self.msg_id
    
    async def connect(self):
        """Connect to cTrader gRPC server"""
        try:
            logger.info("🔌 Connecting to cTrader gRPC server...")
            
            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create gRPC channel
            self.channel = grpc.aio.secure_channel(
                "demo.ctraderapi.com:5035",
                grpc.ssl_channel_credentials()
            )
            
            # Create stub
            self.stub = ctrader_service_pb2_grpc.OpenApiServiceStub(self.channel)
            
            logger.info("✅ Connected to cTrader gRPC server")
            self.is_connected = True
            
            # Start authentication flow
            await self._authenticate_application()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to cTrader: {e}")
            return False
    
    async def _authenticate_application(self):
        """Authenticate application with cTrader"""
        try:
            logger.info("🔐 Authenticating application...")
            
            # Create application auth request
            auth_req = ctrader_service_pb2.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAApplicationAuthReq",
                clientMsgId=self._get_next_msg_id(),
                payload=auth_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAApplicationAuthRes":
                auth_res = ctrader_service_pb2.ProtoOAApplicationAuthRes()
                auth_res.ParseFromString(response.payload)
                logger.info("✅ Application authenticated successfully")
                
                # Get account list
                await self._get_account_list()
                return True
            else:
                logger.error(f"❌ Authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Application authentication error: {e}")
            return False
    
    async def _get_account_list(self):
        """Get account list using access token"""
        try:
            logger.info("📊 Getting account list...")
            
            # Create get accounts request
            accounts_req = ctrader_service_pb2.ProtoOAGetAccountListByAccessTokenReq(
                accessToken=self.access_token
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAGetAccountListByAccessTokenReq",
                clientMsgId=self._get_next_msg_id(),
                payload=accounts_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAGetAccountListByAccessTokenRes":
                accounts_res = ctrader_service_pb2.ProtoOAGetAccountListByAccessTokenRes()
                accounts_res.ParseFromString(response.payload)
                
                logger.info(f"✅ Found {len(accounts_res.ctidTraderAccount)} accounts")
                for account in accounts_res.ctidTraderAccount:
                    logger.info(f"  - Account {account.ctidTraderAccountId}: {account.brokerName} ({'Live' if account.isLive else 'Demo'})")
                
                # Authenticate with the first account
                if accounts_res.ctidTraderAccount:
                    self.current_account_id = accounts_res.ctidTraderAccount[0].ctidTraderAccountId
                    await self._authenticate_account()
                
                return accounts_res.ctidTraderAccount
            else:
                logger.error(f"❌ Get accounts failed: {response.payloadType}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Get accounts error: {e}")
            return []
    
    async def _authenticate_account(self):
        """Authenticate account with access token"""
        try:
            logger.info(f"🔐 Authenticating account {self.current_account_id}...")
            
            # Create account auth request
            auth_req = ctrader_service_pb2.ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.current_account_id,
                accessToken=self.access_token
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAAccountAuthReq",
                clientMsgId=self._get_next_msg_id(),
                payload=auth_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAAccountAuthRes":
                auth_res = ctrader_service_pb2.ProtoOAAccountAuthRes()
                auth_res.ParseFromString(response.payload)
                logger.info(f"✅ Account {auth_res.ctidTraderAccountId} authenticated successfully")
                self.is_authenticated = True
                
                # Start signal generation
                await self._start_signal_generation()
                return True
            else:
                logger.error(f"❌ Account authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Account authentication error: {e}")
            return False
    
    async def _start_signal_generation(self):
        """Start generating trading signals"""
        logger.info("🎲 Starting signal generation...")
        
        # Generate first signal immediately
        await self._generate_and_send_signal()
        
        # Schedule next signal
        await self._schedule_next_signal()
    
    async def _schedule_next_signal(self):
        """Schedule the next signal"""
        while True:
            # Random interval between 3.5-5 hours
            next_interval = random.uniform(3.5 * 3600, 5.0 * 3600)
            logger.info(f"⏰ Next signal in {next_interval/3600:.1f} hours")
            
            await asyncio.sleep(next_interval)
            await self._generate_and_send_signal()
    
    async def _generate_and_send_signal(self):
        """Generate and send a trading signal"""
        try:
            if not self.is_authenticated:
                logger.warning("⚠️ Not authenticated yet")
                return
            
            # Select random forex pair
            symbol_name = random.choice(list(self.symbol_ids.keys()))
            symbol_id = self.symbol_ids[symbol_name]
            
            # Generate entry price (simplified)
            entry_price = random.uniform(1.0500, 1.1000) if symbol_name == "EURUSD" else random.uniform(1.2000, 1.3000)
            
            # Calculate TP and SL (50 pips each)
            pip_value = 0.0001 if "JPY" not in symbol_name else 0.01
            pip_amount = 50 * pip_value
            
            # Random trade direction
            trade_type = random.choice(["BUY", "SELL"])
            
            if trade_type == "BUY":
                take_profit = round(entry_price + pip_amount, 4)
                stop_loss = round(entry_price - pip_amount, 4)
                direction_emoji = "🟢"
            else:
                take_profit = round(entry_price - pip_amount, 4)
                stop_loss = round(entry_price + pip_amount, 4)
                direction_emoji = "🔴"
            
            # Create trade ID
            trade_id = f"TRADE_{int(time.time())}"
            
            # Store trade info
            self.active_trades[trade_id] = {
                'symbol_name': symbol_name,
                'symbol_id': symbol_id,
                'trade_type': trade_type,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': datetime.now(),
                'status': 'PENDING'
            }
            
            logger.info(f"🎯 Generated signal: {symbol_name} {trade_type} @ {entry_price}")
            
            # Send to Telegram
            await self._send_telegram_signal(symbol_name, trade_type, entry_price, take_profit, stop_loss, direction_emoji, trade_id)
            
            # Place trade on cTrader
            await self._place_trade(symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id)
            
        except Exception as e:
            logger.error(f"❌ Error generating signal: {e}")
    
    async def _send_telegram_signal(self, symbol_name, trade_type, entry_price, take_profit, stop_loss, direction_emoji, trade_id):
        """Send signal to Telegram channel"""
        try:
            message = f"""
{direction_emoji} **{symbol_name} {trade_type} SIGNAL** {direction_emoji}

💰 **Entry Price:** `{entry_price}`
🎯 **Take Profit:** `{take_profit}` (+50 pips)
🛡️ **Stop Loss:** `{stop_loss}` (-50 pips)

⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🤖 **Generated by:** Working cTrader Bot
🆔 **Trade ID:** `{trade_id}`

#Forex #Trading #Signal #cTrader
            """.strip()
            
            # Send message to channel
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"📤 Signal sent to Telegram: {symbol_name} {trade_type}")
            
        except Exception as e:
            logger.error(f"❌ Error sending Telegram signal: {e}")
    
    async def _place_trade(self, symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id):
        """Place trade on cTrader"""
        try:
            logger.info(f"💰 Placing trade: {trade_type} {symbol_id} @ {entry_price}")
            
            # Create new order request
            order_req = ctrader_service_pb2.ProtoOANewOrderReq(
                ctidTraderAccountId=self.current_account_id,
                symbolId=symbol_id,
                orderType=1,  # Market order
                tradeSide=1 if trade_type == "BUY" else 2,
                volume=100,  # 1 lot
                limitPrice=0,
                stopPrice=0,
                stopLoss=int(stop_loss * 100000),  # Convert to micro units
                takeProfit=int(take_profit * 100000),  # Convert to micro units
                expirationTimestamp=0,
                comment=f"Bot Signal {trade_id}"
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOANewOrderReq",
                clientMsgId=self._get_next_msg_id(),
                payload=order_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOANewOrderRes":
                order_res = ctrader_service_pb2.ProtoOANewOrderRes()
                order_res.ParseFromString(response.payload)
                
                logger.info(f"✅ Trade placed successfully! Order ID: {order_res.orderId}")
                
                # Update trade status
                for trade_id_key, trade_info in self.active_trades.items():
                    if trade_info['status'] == 'PENDING':
                        trade_info['status'] = 'EXECUTED'
                        trade_info['order_id'] = order_res.orderId
                        break
                
                return True
            else:
                logger.error(f"❌ Trade placement failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing trade: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.channel:
            await self.channel.close()
            logger.info("🔌 Disconnected from cTrader")
    
    async def run(self):
        """Run the bot"""
        try:
            # Connect to cTrader
            if await self.connect():
                logger.info("✅ Bot connected and ready!")
                
                # Keep running
                while True:
                    await asyncio.sleep(60)  # Check every minute
            else:
                logger.error("❌ Failed to connect to cTrader")
                
        except KeyboardInterrupt:
            logger.info("⏹️ Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
        finally:
            await self.disconnect()


async def main():
    """Main function"""
    bot = CTraderWorkingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())



