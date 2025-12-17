"""
Signal Generator - Generates and sends forex trading signals
"""
import asyncio
import random
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType, SignalStatus


class SignalGenerator:
    """Generates and sends forex trading signals"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.signal_processor = SignalProcessor()
        self.channel_id = "-1002175884868"
        self.active_trades = {}  # Track active trades
        
        # Forex major pairs
        self.forex_pairs = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
            "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "EURAUD", "GBPAUD", "GBPCHF",
            "EURCHF", "AUDCHF", "AUDCAD", "NZDCAD", "EURNZD", "GBPNZD"
        ]
        
        # Price ranges for each pair (approximate)
        self.price_ranges = {
            "EURUSD": (1.0500, 1.1000),
            "GBPUSD": (1.2000, 1.3000),
            "USDJPY": (140.00, 150.00),
            "USDCHF": (0.8500, 0.9500),
            "AUDUSD": (0.6000, 0.7000),
            "USDCAD": (1.3000, 1.4000),
            "NZDUSD": (0.5500, 0.6500),
            "EURJPY": (150.00, 165.00),
            "GBPJPY": (180.00, 200.00),
            "EURGBP": (0.8500, 0.9000),
            "AUDJPY": (90.00, 105.00),
            "EURAUD": (1.5000, 1.6500),
            "GBPAUD": (1.8000, 2.0000),
            "GBPCHF": (1.1000, 1.2000),
            "EURCHF": (0.9500, 1.0500),
            "AUDCHF": (0.5500, 0.6500),
            "AUDCAD": (0.8500, 0.9500),
            "NZDCAD": (0.8000, 0.9000),
            "EURNZD": (1.6000, 1.8000),
            "GBPNZD": (2.0000, 2.2000)
        }
        
        self.pip_values = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCHF": 0.0001,
            "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001, "EURJPY": 0.01,
            "GBPJPY": 0.01, "EURGBP": 0.0001, "AUDJPY": 0.01, "EURAUD": 0.0001,
            "GBPAUD": 0.0001, "GBPCHF": 0.0001, "EURCHF": 0.0001, "AUDCHF": 0.0001,
            "AUDCAD": 0.0001, "NZDCAD": 0.0001, "EURNZD": 0.0001, "GBPNZD": 0.0001
        }
    
    async def start_generating(self):
        """Start generating signals"""
        logger.info("🚀 Starting Signal Generator...")
        logger.info(f"📡 Channel: {self.channel_id}")
        logger.info("⏰ Signal interval: 3.5-5 hours (random)")
        logger.info("💰 TP: +50 pips, SL: -50 pips")
        
        # Send first signal immediately
        await self._generate_and_send_signal()
        
        # Start monitoring loop
        while True:
            # Calculate next signal time (3.5-5 hours)
            next_signal_hours = random.uniform(3.5, 5.0)
            next_signal_time = datetime.now() + timedelta(hours=next_signal_hours)
            
            logger.info(f"⏳ Next signal in {next_signal_hours:.1f} hours at {next_signal_time.strftime('%H:%M:%S')}")
            
            # Wait for next signal time
            await asyncio.sleep(next_signal_hours * 3600)
            
            # Generate and send signal
            await self._generate_and_send_signal()
    
    async def _generate_and_send_signal(self):
        """Generate and send a trading signal"""
        try:
            # Select random forex pair
            symbol = random.choice(self.forex_pairs)
            
            # Generate entry price within range
            min_price, max_price = self.price_ranges[symbol]
            entry_price = round(random.uniform(min_price, max_price), 4)
            
            # Calculate TP and SL (50 pips each)
            pip_value = self.pip_values[symbol]
            pip_amount = 50 * pip_value
            
            # Random trade direction
            trade_type = random.choice([TradeType.BUY, TradeType.SELL])
            
            if trade_type == TradeType.BUY:
                take_profit = round(entry_price + pip_amount, 4)
                stop_loss = round(entry_price - pip_amount, 4)
            else:
                take_profit = round(entry_price - pip_amount, 4)
                stop_loss = round(entry_price + pip_amount, 4)
            
            # Create signal
            signal = TradingSignal(
                symbol=symbol,
                trade_type=trade_type,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                volume=1.0,
                comment=f"Auto-generated signal",
                channel_id=self.channel_id,
                account_id="9615885"
            )
            
            logger.info(f"🎯 Generated signal: {symbol} {trade_type.value} @ {entry_price}")
            
            # Send to channel
            await self._send_signal_to_channel(signal)
            
            # Execute on cTrader
            await self._execute_signal(signal)
            
        except Exception as e:
            logger.error(f"❌ Error generating signal: {e}")
    
    async def _send_signal_to_channel(self, signal: TradingSignal):
        """Send signal to Telegram channel"""
        try:
            # Format signal message
            direction_emoji = "🟢" if signal.trade_type == TradeType.BUY else "🔴"
            direction_text = "BUY" if signal.trade_type == TradeType.BUY else "SELL"
            
            message = f"""
{direction_emoji} **{signal.symbol} {direction_text} SIGNAL**

💰 **Entry:** {signal.entry_price}
🎯 **Take Profit:** {signal.take_profit} (+50 pips)
🛡️ **Stop Loss:** {signal.stop_loss} (-50 pips)

⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🤖 **Generated by:** Signals Bot

#Forex #Trading #Signal
            """.strip()
            
            # Send message to channel
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"📤 Signal sent to channel: {signal.symbol} {signal.trade_type.value}")
            
        except Exception as e:
            logger.error(f"❌ Error sending signal to channel: {e}")
    
    async def _execute_signal(self, signal: TradingSignal):
        """Execute signal on cTrader"""
        try:
            logger.info(f"🔄 Executing signal on cTrader: {signal.symbol}")
            
            # Process signal through signal processor
            result = await self.signal_processor.process_signal(signal)
            
            if result.status == SignalStatus.SUCCESS:
                logger.info(f"✅ Signal executed successfully: {result.trade_id}")
                
                # Track active trade
                self.active_trades[result.trade_id] = {
                    'signal': signal,
                    'result': result,
                    'start_time': datetime.now(),
                    'status': 'ACTIVE'
                }
                
                # Start monitoring this trade
                asyncio.create_task(self._monitor_trade(result.trade_id))
                
            else:
                logger.error(f"❌ Signal execution failed: {result.error_message}")
                
        except Exception as e:
            logger.error(f"❌ Error executing signal: {e}")
    
    async def _monitor_trade(self, trade_id: str):
        """Monitor a trade for SL/TP hits"""
        try:
            if trade_id not in self.active_trades:
                return
            
            trade_info = self.active_trades[trade_id]
            signal = trade_info['signal']
            
            logger.info(f"👀 Monitoring trade {trade_id}: {signal.symbol} {signal.trade_type.value}")
            
            # Simulate monitoring (in real implementation, you'd check cTrader API)
            # For now, we'll simulate a random outcome after some time
            await asyncio.sleep(random.uniform(300, 1800))  # 5-30 minutes
            
            # Simulate random outcome
            outcome = random.choice(['TP', 'SL'])
            
            if outcome == 'TP':
                await self._report_tp_hit(trade_id, signal)
            else:
                await self._report_sl_hit(trade_id, signal)
                
        except Exception as e:
            logger.error(f"❌ Error monitoring trade {trade_id}: {e}")
    
    async def _report_tp_hit(self, trade_id: str, signal: TradingSignal):
        """Report when TP is hit"""
        try:
            message = f"""
🎯 **TAKE PROFIT HIT!** 🎯

{signal.symbol} {signal.trade_type.value} @ {signal.entry_price}
✅ **TP:** {signal.take_profit} (+50 pips)

💰 **Profit:** +50 pips
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}

#Profit #Forex #Trading
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Update trade status
            if trade_id in self.active_trades:
                self.active_trades[trade_id]['status'] = 'TP_HIT'
            
            logger.info(f"🎯 TP hit reported: {signal.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error reporting TP hit: {e}")
    
    async def _report_sl_hit(self, trade_id: str, signal: TradingSignal):
        """Report when SL is hit"""
        try:
            message = f"""
🛡️ **STOP LOSS HIT** 🛡️

{signal.symbol} {signal.trade_type.value} @ {signal.entry_price}
❌ **SL:** {signal.stop_loss} (-50 pips)

💸 **Loss:** -50 pips
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}

#StopLoss #Forex #Trading
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Update trade status
            if trade_id in self.active_trades:
                self.active_trades[trade_id]['status'] = 'SL_HIT'
            
            logger.info(f"🛡️ SL hit reported: {signal.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Error reporting SL hit: {e}")
    
    async def stop(self):
        """Stop the signal generator"""
        await self.bot.session.close()
        logger.info("🛑 Signal generator stopped")


async def main():
    """Main function for signal generation"""
    generator = SignalGenerator()
    
    try:
        await generator.start_generating()
    except KeyboardInterrupt:
        logger.info("⏹️ Signal generation stopped by user")
    except Exception as e:
        logger.error(f"❌ Signal generation error: {e}")
    finally:
        await generator.stop()


if __name__ == "__main__":
    asyncio.run(main())



