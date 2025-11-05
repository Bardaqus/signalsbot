"""
cTrader Official Trading Bot using Spotware OpenApiPy
This implements the correct flow: OAuth2 -> gRPC -> Trading
"""
import asyncio
import random
import time
from datetime import datetime, timedelta
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from loguru import logger

# Import Spotware OpenApiPy
import sys
sys.path.append('OpenApiPy')
from ctrader_open_api import Client, Protobuf, TcpProtocol, Auth, EndPoints
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

from config import Config
from aiogram import Bot


class CTraderOfficialBot:
    """Official cTrader trading bot using Spotware OpenApiPy"""
    
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
        self.symbol_ids = {}
        
        # Client state
        self.is_connected = False
        self.is_authenticated = False
        self.current_account_id = None
        
        # Trading state
        self.active_trades = {}
        
        # Create cTrader client
        self.client = Client(
            EndPoints.PROTOBUF_DEMO_HOST,  # Use demo for testing
            EndPoints.PROTOBUF_PORT,
            TcpProtocol
        )
        
        # Set callbacks
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)
        
        logger.info("🚀 Official cTrader Trading Bot initialized...")
        
    
    def _on_connected(self, client):
        """Called when connected to cTrader"""
        logger.info("✅ Connected to cTrader gRPC server")
        self.is_connected = True
        
        # Start authentication flow
        self._authenticate_application()
    
    def _on_disconnected(self, client, reason):
        """Called when disconnected from cTrader"""
        logger.info(f"❌ Disconnected from cTrader: {reason}")
        self.is_connected = False
        self.is_authenticated = False
    
    def _on_message_received(self, client, message):
        """Called when message is received from cTrader"""
        try:
            if message.payloadType == ProtoOAApplicationAuthRes().payloadType:
                self._handle_application_auth_response(message)
            elif message.payloadType == ProtoOAGetAccountListByAccessTokenRes().payloadType:
                self._handle_account_list_response(message)
            elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
                self._handle_account_auth_response(message)
            elif message.payloadType == ProtoOASymbolsListRes().payloadType:
                self._handle_symbols_list_response(message)
            elif message.payloadType == ProtoOANewOrderRes().payloadType:
                self._handle_new_order_response(message)
            elif message.payloadType == ProtoOAExecutionEvent().payloadType:
                self._handle_execution_event(message)
            else:
                logger.debug(f"📨 Received message: {message.payloadType}")
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}")
    
    def _authenticate_application(self):
        """Authenticate application with cTrader"""
        try:
            logger.info("🔐 Authenticating application...")
            
            request = ProtoOAApplicationAuthReq()
            request.clientId = self.client_id
            request.clientSecret = self.client_secret
            
            deferred = self.client.send(request)
            deferred.addErrback(self._on_error)
            
        except Exception as e:
            logger.error(f"❌ Application authentication error: {e}")
    
    def _handle_application_auth_response(self, message):
        """Handle application authentication response"""
        try:
            response = Protobuf.extract(message)
            logger.info("✅ Application authenticated successfully")
            
            # Get account list
            self._get_account_list()
            
        except Exception as e:
            logger.error(f"❌ Error handling application auth response: {e}")
    
    def _get_account_list(self):
        """Get account list using access token"""
        try:
            logger.info("📊 Getting account list...")
            
            request = ProtoOAGetAccountListByAccessTokenReq()
            request.accessToken = self.access_token
            
            deferred = self.client.send(request)
            deferred.addErrback(self._on_error)
            
        except Exception as e:
            logger.error(f"❌ Error getting account list: {e}")
    
    def _handle_account_list_response(self, message):
        """Handle account list response"""
        try:
            response = Protobuf.extract(message)
            logger.info(f"✅ Found {len(response.ctidTraderAccount)} accounts")
            
            for account in response.ctidTraderAccount:
                logger.info(f"  - Account {account.ctidTraderAccountId}: {account.brokerName} ({'Live' if account.isLive else 'Demo'})")
            
            # Authenticate with the first account
            if response.ctidTraderAccount:
                self.current_account_id = response.ctidTraderAccount[0].ctidTraderAccountId
                self._authenticate_account()
            
        except Exception as e:
            logger.error(f"❌ Error handling account list response: {e}")
    
    def _authenticate_account(self):
        """Authenticate account with access token"""
        try:
            logger.info(f"🔐 Authenticating account {self.current_account_id}...")
            
            request = ProtoOAAccountAuthReq()
            request.ctidTraderAccountId = self.current_account_id
            request.accessToken = self.access_token
            
            deferred = self.client.send(request)
            deferred.addErrback(self._on_error)
            
        except Exception as e:
            logger.error(f"❌ Error authenticating account: {e}")
    
    def _handle_account_auth_response(self, message):
        """Handle account authentication response"""
        try:
            response = Protobuf.extract(message)
            logger.info(f"✅ Account {response.ctidTraderAccountId} authenticated successfully")
            self.is_authenticated = True
            
            # Get symbols list
            self._get_symbols_list()
            
            # Start signal generation
            self._start_signal_generation()
            
        except Exception as e:
            logger.error(f"❌ Error handling account auth response: {e}")
    
    def _get_symbols_list(self):
        """Get symbols list"""
        try:
            logger.info("📈 Getting symbols list...")
            
            request = ProtoOASymbolsListReq()
            request.ctidTraderAccountId = self.current_account_id
            request.includeArchivedSymbols = False
            
            deferred = self.client.send(request)
            deferred.addErrback(self._on_error)
            
        except Exception as e:
            logger.error(f"❌ Error getting symbols list: {e}")
    
    def _handle_symbols_list_response(self, message):
        """Handle symbols list response"""
        try:
            response = Protobuf.extract(message)
            logger.info(f"✅ Found {len(response.symbol)} symbols")
            
            # Map symbol names to IDs
            for symbol in response.symbol:
                if symbol.symbolName in self.forex_pairs:
                    self.symbol_ids[symbol.symbolName] = symbol.symbolId
                    logger.info(f"  - {symbol.symbolName}: ID {symbol.symbolId}")
            
            logger.info("🎯 Ready for trading!")
            
        except Exception as e:
            logger.error(f"❌ Error handling symbols list response: {e}")
    
    def _start_signal_generation(self):
        """Start generating trading signals"""
        logger.info("🎲 Starting signal generation...")
        
        # Generate first signal immediately
        reactor.callLater(1, self._generate_and_send_signal)
        
        # Schedule next signal
        self._schedule_next_signal()
    
    def _schedule_next_signal(self):
        """Schedule the next signal"""
        # Random interval between 3.5-5 hours
        next_interval = random.uniform(3.5 * 3600, 5.0 * 3600)
        logger.info(f"⏰ Next signal in {next_interval/3600:.1f} hours")
        
        reactor.callLater(next_interval, self._generate_and_send_signal)
        reactor.callLater(next_interval, self._schedule_next_signal)
    
    def _generate_and_send_signal(self):
        """Generate and send a trading signal"""
        try:
            if not self.is_authenticated or not self.symbol_ids:
                logger.warning("⚠️ Not ready for trading yet")
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
            self._send_telegram_signal(symbol_name, trade_type, entry_price, take_profit, stop_loss, direction_emoji, trade_id)
            
            # Place trade on cTrader
            self._place_trade(symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id)
            
        except Exception as e:
            logger.error(f"❌ Error generating signal: {e}")
    
    def _send_telegram_signal(self, symbol_name, trade_type, entry_price, take_profit, stop_loss, direction_emoji, trade_id):
        """Send signal to Telegram channel"""
        try:
            message = f"""
{direction_emoji} **{symbol_name} {trade_type} SIGNAL** {direction_emoji}

💰 **Entry Price:** `{entry_price}`
🎯 **Take Profit:** `{take_profit}` (+50 pips)
🛡️ **Stop Loss:** `{stop_loss}` (-50 pips)

⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🤖 **Generated by:** Official cTrader Bot
🆔 **Trade ID:** `{trade_id}`

#Forex #Trading #Signal #cTrader
            """.strip()
            
            # Send message to channel
            reactor.callInThread(self._send_telegram_message, message)
            
        except Exception as e:
            logger.error(f"❌ Error sending Telegram signal: {e}")
    
    def _send_telegram_message(self, message):
        """Send message to Telegram (runs in thread)"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            ))
            loop.close()
        except Exception as e:
            logger.error(f"❌ Error sending Telegram message: {e}")
    
    def _place_trade(self, symbol_id, trade_type, entry_price, take_profit, stop_loss, trade_id):
        """Place trade on cTrader"""
        try:
            logger.info(f"💰 Placing trade: {trade_type} {symbol_id} @ {entry_price}")
            
            request = ProtoOANewOrderReq()
            request.ctidTraderAccountId = self.current_account_id
            request.symbolId = symbol_id
            request.orderType = ProtoOAOrderType.MARKET
            request.tradeSide = ProtoOATradeSide.BUY if trade_type == "BUY" else ProtoOATradeSide.SELL
            request.volume = 100  # 1 lot = 100 units
            request.stopLoss = int(stop_loss * 100000)  # Convert to micro units
            request.takeProfit = int(take_profit * 100000)  # Convert to micro units
            request.comment = f"Bot Signal {trade_id}"
            
            deferred = self.client.send(request)
            deferred.addErrback(self._on_error)
            
        except Exception as e:
            logger.error(f"❌ Error placing trade: {e}")
    
    def _handle_new_order_response(self, message):
        """Handle new order response"""
        try:
            response = Protobuf.extract(message)
            logger.info(f"✅ Order placed successfully! Order ID: {response.orderId}")
            
            # Update trade status
            for trade_id, trade_info in self.active_trades.items():
                if trade_info['status'] == 'PENDING':
                    trade_info['status'] = 'EXECUTED'
                    trade_info['order_id'] = response.orderId
                    break
            
        except Exception as e:
            logger.error(f"❌ Error handling new order response: {e}")
    
    def _handle_execution_event(self, message):
        """Handle execution event (trade filled, etc.)"""
        try:
            response = Protobuf.extract(message)
            logger.info(f"📊 Execution event: {response}")
            
            # Handle trade execution, position updates, etc.
            
        except Exception as e:
            logger.error(f"❌ Error handling execution event: {e}")
    
    def _on_error(self, failure):
        """Handle errors"""
        logger.error(f"❌ Error: {failure}")
    
    def stop(self):
        """Stop the bot"""
        if self.client:
            self.client.stopService()
        if reactor.running:
            reactor.stop()


def main():
    """Main function"""
    bot = CTraderOfficialBot()
    
    try:
        # Start the client
        bot.client.startService()
        
        # Start the reactor
        reactor.run()
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        bot.stop()


if __name__ == "__main__":
    main()
