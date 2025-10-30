"""
Real cTrader Trading Bot - Opens actual positions
This implements real trading using cTrader Open API with gRPC
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


class RealCTraderTradingBot:
    """Real cTrader trading bot that opens actual positions"""
    
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
        
        # Symbol mapping (will be populated from cTrader)
        self.symbol_ids = {}
        
        # Client state
        self.channel = None
        self.stub = None
        self.is_connected = False
        self.is_authenticated = False
        self.current_account_id = None
        
        # Trading state
        self.active_trades = {}
        self.msg_id = 0
        
        logger.info("🚀 Real cTrader Trading Bot initialized...")
    
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id += 1
        return self.msg_id
    
    async def connect(self):
        """Connect to cTrader gRPC server"""
        try:
            logger.info("🔌 Connecting to cTrader gRPC server...")
            
            # Create gRPC channel with SSL
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
                
                # Get symbols list
                await self._get_symbols_list()
                
                # Start signal generation
                await self._start_signal_generation()
                
                return True
            else:
                logger.error(f"❌ Account authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Account authentication error: {e}")
            return False
    
    async def _get_symbols_list(self):
        """Get symbols list"""
        try:
            logger.info("📈 Getting symbols list...")
            
            # Create symbols list request
            symbols_req = ctrader_service_pb2.ProtoOASymbolsListReq(
                ctidTraderAccountId=self.current_account_id,
                includeArchivedSymbols=False
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOASymbolsListReq",
                clientMsgId=self._get_next_msg_id(),
                payload=symbols_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOASymbolsListRes":
                symbols_res = ctrader_service_pb2.ProtoOASymbolsListRes()
                symbols_res.ParseFromString(response.payload)
                
                logger.info(f"✅ Found {len(symbols_res.symbol)} symbols")
                
                # Map symbol names to IDs
                for symbol in symbols_res.symbol:
                    if symbol.symbolName in self.forex_pairs:
                        self.symbol_ids[symbol.symbolName] = symbol.symbolId
                        logger.info(f"  - {symbol.symbolName}: ID {symbol.symbolId}")
                
                logger.info("🎯 Ready for real trading!")
                
            else:
                logger.error(f"❌ Get symbols failed: {response.payloadType}")
                
        except Exception as e:
            logger.error(f"❌ Error getting symbols list: {e}")
    
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
            if not self.is_authenticated or not self.symbol_ids:
                logger.warning("⚠️ Not ready for trading yet")
                return
            
            # Select random forex pair
            symbol_name = random.choice(list(self.symbol_ids.keys()))
            symbol_id = self.symbol_ids[symbol_name]
            
            # Generate realistic entry price based on symbol
            if symbol_name == "EURUSD":
                entry_price = random.uniform(1.0500, 1.1000)
            elif symbol_name == "GBPUSD":
                entry_price = random.uniform(1.2000, 1.3000)
            elif "JPY" in symbol_name:
                entry_price = random.uniform(140.00, 160.00)
            else:
                entry_price = random.uniform(1.0000, 1.5000)
            
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
            
            # Place real trade on cTrader
            await self._place_real_trade(symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id)
            
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
🤖 **Generated by:** Real cTrader Bot
🆔 **Trade ID:** `{trade_id}`

📋 **Real Trading:** Position will be opened automatically in cTrader!

#Forex #Trading #Signal #cTrader #RealTrading
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
    
    async def _place_real_trade(self, symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id):
        """Place real trade on cTrader"""
        try:
            logger.info(f"💰 Placing REAL trade: {trade_type} {symbol_id} @ {entry_price}")
            
            # Create new order request
            order_req = ctrader_service_pb2.ProtoOANewOrderReq(
                ctidTraderAccountId=self.current_account_id,
                symbolId=symbol_id,
                orderType=1,  # Market order
                tradeSide=1 if trade_type == "BUY" else 2,  # 1=BUY, 2=SELL
                volume=100,  # 1 lot = 100 units
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
                
                logger.info(f"✅ REAL TRADE EXECUTED! Order ID: {order_res.orderId}")
                
                # Update trade status
                for trade_id_key, trade_info in self.active_trades.items():
                    if trade_info['status'] == 'PENDING':
                        trade_info['status'] = 'EXECUTED'
                        trade_info['order_id'] = order_res.orderId
                        break
                
                # Send success message to Telegram
                await self._send_trade_success_message(trade_id, order_res.orderId)
                
                return True
            else:
                logger.error(f"❌ Trade placement failed: {response.payloadType}")
                await self._send_trade_error_message(trade_id, f"Failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error placing real trade: {e}")
            await self._send_trade_error_message(trade_id, str(e))
            return False
    
    async def _send_trade_success_message(self, trade_id, order_id):
        """Send trade success message to Telegram"""
        try:
            trade_info = self.active_trades[trade_id]
            symbol_name = trade_info['symbol_name']
            trade_type = trade_info['trade_type']
            
            message = f"""
✅ **REAL TRADE EXECUTED!** ✅

📊 **{symbol_name}** - {trade_type}
🆔 **Order ID:** `{order_id}`
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}

🎯 **Position opened in your cTrader account!**

#RealTrading #cTrader #Success
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Error sending trade success message: {e}")
    
    async def _send_trade_error_message(self, trade_id, error_msg):
        """Send trade error message to Telegram"""
        try:
            trade_info = self.active_trades[trade_id]
            symbol_name = trade_info['symbol_name']
            trade_type = trade_info['trade_type']
            
            message = f"""
❌ **TRADE FAILED** ❌

📊 **{symbol_name}** - {trade_type}
🚫 **Error:** {error_msg}
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}

#Error #cTrader
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"❌ Error sending trade error message: {e}")
    
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
                logger.info("✅ Bot connected and ready for REAL trading!")
                
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
    bot = RealCTraderTradingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
