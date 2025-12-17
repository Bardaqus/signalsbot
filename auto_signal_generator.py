"""
Automatic signal generator for trading signals every 4 minutes
"""
import asyncio
import random
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from config import Config
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType, SignalStatus
from ctrader_api import CTraderAPI


class AutoSignalGenerator:
    """Generates automatic trading signals every 4 minutes"""
    
    def __init__(self):
        self.signal_processor = SignalProcessor()
        self.ctrader_api = CTraderAPI()
        self.is_running = False
        # Live quotes cache: symbol -> {"bid": float, "ask": float, "timestamp": int}
        self.latest_quotes: Dict[str, Dict[str, float]] = {}
        
        # Major currency pairs for trading
        self.major_pairs = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", 
            "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
            "AUDJPY", "CHFJPY", "EURCHF", "GBPCHF", "AUDCAD"
        ]
        
        # Indices for trading (using known ticker symbols)
        self.index_symbols = [
            "US500",   # S&P 500
            "USTEC",   # Nasdaq 100 (NOT US100!)
            "US30",    # Dow Jones 30
            "DE40",    # DAX 40
            "UK100",   # FTSE 100
            "F40",     # CAC 40
            "JP225",   # Nikkei 225
            "AUS200",  # ASX 200
            "HK50",    # Hang Seng
            "EU50"     # Euro Stoxx 50
        ]
        
        # All symbols (Forex + Indices) for subscription
        self.all_symbols = self.major_pairs + self.index_symbols
        
        # Typical pip values for major pairs (in USD)
        self.pip_values = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
            "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
            "USDJPY": 0.01, "EURJPY": 0.01, "GBPJPY": 0.01,
            "AUDJPY": 0.01, "CHFJPY": 0.01, "EURGBP": 0.0001,
            "EURCHF": 0.0001, "GBPCHF": 0.0001, "AUDCAD": 0.0001,
            # Indices pip values (typically 1 point = 1 pip for indices)
            "US500": 1.0, "USTEC": 1.0, "US30": 1.0,
            "DE40": 1.0, "UK100": 1.0, "F40": 1.0,
            "JP225": 1.0, "AUS200": 1.0, "HK50": 1.0, "EU50": 1.0
        }
        
        # Setup default channel and account
        self._setup_default_configuration()
    
    def _setup_default_configuration(self):
        """Setup default channel and account configuration"""
        # Add demo account
        self.signal_processor.add_account(
            Config.DEMO_ACCOUNT_ID, 
            "Demo Account", 
            "IC Markets", 
            "DEMO"
        )
        
        # Add channel
        channel_id = Config.TEST_CHANNEL_ID.replace("@", "").replace("https://t.me/", "")
        self.signal_processor.add_channel(
            channel_id, 
            "Trading Signals Channel", 
            Config.DEMO_ACCOUNT_ID
        )
        
        logger.info(f"Setup default configuration - Account: {Config.DEMO_ACCOUNT_ID}, Channel: {channel_id}")
    
    def update_live_quote(self, symbol: str, bid: float, ask: float, timestamp: int) -> None:
        """Update cached live quote coming from the cTrader streamer."""
        sym = symbol.upper()
        self.latest_quotes[sym] = {"bid": float(bid), "ask": float(ask), "timestamp": int(timestamp)}
        logger.debug(f"Live quote updated: {sym} bid={bid} ask={ask} ts={timestamp}")

    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol"""
        try:
            # Prefer live streamer quote if available
            cached = self.latest_quotes.get(symbol.upper())
            if cached:
                bid = float(cached.get('bid', 0))
                ask = float(cached.get('ask', 0))
                if bid and ask:
                    return (bid + ask) / 2

            quote = await self.ctrader_api.get_current_quotes(symbol)
            if quote:
                # Return mid price (average of bid and ask)
                bid = float(quote.get('bid', 0))
                ask = float(quote.get('ask', 0))
                return (bid + ask) / 2
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
        
        # Fallback prices for demo purposes
        fallback_prices = {
            "EURUSD": 1.0650, "GBPUSD": 1.2500, "USDJPY": 150.00,
            "USDCHF": 0.9000, "AUDUSD": 0.6500, "USDCAD": 1.3500,
            "NZDUSD": 0.6000, "EURJPY": 160.00, "GBPJPY": 187.50,
            "AUDJPY": 97.50, "CHFJPY": 166.67, "EURGBP": 0.8520,
            "EURCHF": 0.9585, "GBPCHF": 1.1250, "AUDCAD": 0.8775
        }
        return fallback_prices.get(symbol, 1.0000)
    
    def calculate_pip_move(self, symbol: str, price: float, pips: int) -> float:
        """Calculate price movement for given pips"""
        pip_value = self.pip_values.get(symbol, 0.0001)
        return pips * pip_value
    
    async def generate_random_signal(self) -> TradingSignal:
        """Generate a random trading signal"""
        # Select random currency pair
        symbol = random.choice(self.major_pairs)
        
        # Random trade direction
        trade_type = random.choice([TradeType.BUY, TradeType.SELL])
        
        # Get current price
        entry_price = await self.get_current_price(symbol)
        
        # Calculate SL and TP based on pips
        pip_move = self.calculate_pip_move(symbol, entry_price, 1)
        
        if trade_type == TradeType.BUY:
            stop_loss = entry_price - (Config.SL_PIPS * pip_move)
            take_profit = entry_price + (Config.TP_PIPS * pip_move)
        else:
            stop_loss = entry_price + (Config.SL_PIPS * pip_move)
            take_profit = entry_price - (Config.TP_PIPS * pip_move)
        
        # Round prices to appropriate decimal places
        if "JPY" in symbol:
            entry_price = round(entry_price, 2)
            stop_loss = round(stop_loss, 2)
            take_profit = round(take_profit, 2)
        else:
            entry_price = round(entry_price, 4)
            stop_loss = round(stop_loss, 4)
            take_profit = round(take_profit, 4)
        
        # Create signal
        channel_id = Config.TEST_CHANNEL_ID.replace("@", "").replace("https://t.me/", "")
        
        signal = TradingSignal(
            symbol=symbol,
            trade_type=trade_type.value,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=1.0,
            comment=f"Auto signal - {Config.SL_PIPS} SL, {Config.TP_PIPS} TP",
            channel_id=channel_id,
            account_id=Config.DEMO_ACCOUNT_ID
        )
        
        return signal
    
    async def send_signal_to_channel(self, signal: TradingSignal):
        """Send signal to Telegram channel"""
        try:
            from telegram_bot import SignalsBot
            bot_instance = SignalsBot()
            
            message_text = signal.to_telegram_message()
            
            # Add additional info for auto signals
            message_text += f"\n\n🤖 *Auto-generated signal*"
            message_text += f"\n⏰ *Next signal in {Config.AUTO_SIGNAL_INTERVAL//60} minutes*"
            
            await bot_instance.bot.send_message(
                chat_id=signal.channel_id,
                text=message_text,
                parse_mode="Markdown"
            )
            
            logger.info(f"Sent signal to channel: {signal.symbol} {signal.trade_type}")
            
        except Exception as e:
            logger.error(f"Error sending signal to channel: {e}")
    
    async def execute_signal(self, signal: TradingSignal):
        """Execute the trading signal"""
        try:
            # Process the signal (place trade)
            history = await self.signal_processor.process_signal(signal)
            
            if signal.status == SignalStatus.EXECUTED:
                logger.info(f"✅ Signal executed successfully: {signal.symbol} {signal.trade_type}")
            else:
                logger.error(f"❌ Signal execution failed: {signal.error_message}")
                
            return history
            
        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            return None
    
    async def generate_and_send_signal(self):
        """Generate and send a single signal"""
        try:
            logger.info("🎯 Generating new trading signal...")
            
            # Generate random signal
            signal = await self.generate_random_signal()
            
            logger.info(f"📊 Generated signal: {signal.symbol} {signal.trade_type} @ {signal.entry_price}")
            
            # Send to Telegram channel
            await self.send_signal_to_channel(signal)
            
            # Execute trade
            await self.execute_signal(signal)
            
            # Log statistics
            stats = self.signal_processor.get_statistics()
            logger.info(f"📈 Stats - Total: {stats['total_signals']}, Success: {stats['success_rate']:.1f}%")
            
        except Exception as e:
            logger.error(f"Error in signal generation: {e}")
    
    async def start_auto_signals(self):
        """Start automatic signal generation"""
        if self.is_running:
            logger.warning("Auto signal generator is already running!")
            return
        
        self.is_running = True
        logger.info(f"🚀 Starting auto signal generator - Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        
        try:
            while self.is_running:
                # Generate and send signal
                await self.generate_and_send_signal()
                
                # Wait for next signal
                logger.info(f"⏳ Waiting {Config.AUTO_SIGNAL_INTERVAL} seconds for next signal...")
                await asyncio.sleep(Config.AUTO_SIGNAL_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("⏹️ Auto signal generator stopped by user")
        except Exception as e:
            logger.error(f"❌ Error in auto signal generator: {e}")
        finally:
            self.is_running = False
    
    def stop_auto_signals(self):
        """Stop automatic signal generation"""
        self.is_running = False
        logger.info("⏹️ Stopping auto signal generator...")
    
    async def send_startup_message(self):
        """Send startup message to channel"""
        try:
            from telegram_bot import SignalsBot
            bot_instance = SignalsBot()
            
            channel_id = Config.TEST_CHANNEL_ID.replace("@", "").replace("https://t.me/", "")
            
            message = f"""
🤖 **Signals Bot Started!**

**Configuration:**
• Signal Interval: {Config.AUTO_SIGNAL_INTERVAL//60} minutes
• Stop Loss: {Config.SL_PIPS} pips
• Take Profit: {Config.TP_PIPS} pips
• Major Pairs: {len(self.major_pairs)} pairs

**Next signal in {Config.AUTO_SIGNAL_INTERVAL//60} minutes...**

📊 Happy Trading! 🚀
"""
            
            await bot_instance.bot.send_message(
                chat_id=channel_id,
                text=message,
                parse_mode="Markdown"
            )
            
            logger.info("Sent startup message to channel")
            
        except Exception as e:
            logger.error(f"Error sending startup message: {e}")


async def main():
    """Main function to run auto signal generator"""
    generator = AutoSignalGenerator()
    
    try:
        # Send startup message
        await generator.send_startup_message()
        
        # Start auto signals
        await generator.start_auto_signals()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        generator.stop_auto_signals()


if __name__ == "__main__":
    asyncio.run(main())

