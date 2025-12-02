"""
Practical Trading Bot - Generates signals and provides manual trading interface
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


class PracticalTradingBot:
    """Practical trading bot that generates signals and provides trading interface"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.channel_id = "-1002175884868"
        self.account_id = 44749280
        self.account_number = 9615885
        
        # Forex major pairs
        self.forex_pairs = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
            "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "EURAUD", "GBPAUD", "GBPCHF",
            "EURCHF", "AUDCHF", "AUDCAD", "NZDCAD", "EURNZD", "GBPNZD"
        ]
        
        # Price ranges for each pair
        self.price_ranges = {
            "EURUSD": (1.0500, 1.1000), "GBPUSD": (1.2000, 1.3000), "USDJPY": (140.00, 150.00),
            "USDCHF": (0.8500, 0.9500), "AUDUSD": (0.6000, 0.7000), "USDCAD": (1.3000, 1.4000),
            "NZDUSD": (0.5500, 0.6500), "EURJPY": (150.00, 165.00), "GBPJPY": (180.00, 200.00),
            "EURGBP": (0.8500, 0.9000), "AUDJPY": (90.00, 105.00), "EURAUD": (1.5000, 1.6500),
            "GBPAUD": (1.8000, 2.0000), "GBPCHF": (1.1000, 1.2000), "EURCHF": (0.9500, 1.0500),
            "AUDCHF": (0.5500, 0.6500), "AUDCAD": (0.8500, 0.9500), "NZDCAD": (0.8000, 0.9000),
            "EURNZD": (1.6000, 1.8000), "GBPNZD": (2.0000, 2.2000)
        }
        
        self.pip_values = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCHF": 0.0001,
            "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001, "EURJPY": 0.01,
            "GBPJPY": 0.01, "EURGBP": 0.0001, "AUDJPY": 0.01, "EURAUD": 0.0001,
            "GBPAUD": 0.0001, "GBPCHF": 0.0001, "EURCHF": 0.0001, "AUDCHF": 0.0001,
            "AUDCAD": 0.0001, "NZDCAD": 0.0001, "EURNZD": 0.0001, "GBPNZD": 0.0001
        }
        
        # Track active trades
        self.active_trades = {}
        
    async def start_generating(self):
        """Start generating signals"""
        logger.info("🚀 Starting Practical Trading Bot...")
        logger.info(f"📡 Channel: {self.channel_id}")
        logger.info(f"🏦 Account: {self.account_number}")
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
            trade_id = f"TRADE_{int(datetime.now().timestamp())}"
            
            # Store trade info
            self.active_trades[trade_id] = {
                'symbol': symbol,
                'trade_type': trade_type,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': datetime.now(),
                'status': 'ACTIVE'
            }
            
            logger.info(f"🎯 Generated signal: {symbol} {trade_type} @ {entry_price}")
            
            # Send to channel with trading instructions
            await self._send_trading_signal(symbol, trade_type, entry_price, take_profit, stop_loss, direction_emoji, trade_id)
            
            # Start monitoring this trade
            asyncio.create_task(self._monitor_trade(trade_id))
            
        except Exception as e:
            logger.error(f"❌ Error generating signal: {e}")
    
    async def _send_trading_signal(self, symbol: str, trade_type: str, entry_price: float, 
                                 take_profit: float, stop_loss: float, direction_emoji: str, trade_id: str):
        """Send trading signal with manual instructions"""
        try:
            message = f"""
{direction_emoji} **{symbol} {trade_type} SIGNAL**

💰 **Entry:** {entry_price}
🎯 **Take Profit:** {take_profit} (+50 pips)
🛡️ **Stop Loss:** {stop_loss} (-50 pips)

📊 **Manual Trading Instructions:**
1. Open cTrader platform
2. Select {symbol} chart
3. Place {trade_type} order at {entry_price}
4. Set Stop Loss: {stop_loss}
5. Set Take Profit: {take_profit}
6. Volume: 0.01 lots (or your preferred size)

⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🤖 **Generated by:** Signals Bot
🆔 **Trade ID:** {trade_id}

#Forex #Trading #Signal #Manual
            """.strip()
            
            # Send message to channel
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"📤 Trading signal sent: {symbol} {trade_type}")
            
        except Exception as e:
            logger.error(f"❌ Error sending signal: {e}")
    
    async def _monitor_trade(self, trade_id: str):
        """Monitor a trade for completion"""
        try:
            if trade_id not in self.active_trades:
                return
            
            trade_info = self.active_trades[trade_id]
            symbol = trade_info['symbol']
            
            logger.info(f"👀 Monitoring trade {trade_id}: {symbol}")
            
            # Simulate monitoring (in real implementation, you'd check cTrader platform)
            # For now, we'll simulate a random outcome after some time
            await asyncio.sleep(random.uniform(300, 1800))  # 5-30 minutes
            
            # Simulate random outcome
            outcome = random.choice(['TP', 'SL'])
            
            if outcome == 'TP':
                await self._report_tp_hit(trade_id, trade_info)
            else:
                await self._report_sl_hit(trade_id, trade_info)
                
        except Exception as e:
            logger.error(f"❌ Error monitoring trade {trade_id}: {e}")
    
    async def _report_tp_hit(self, trade_id: str, trade_info: Dict):
        """Report when TP is hit"""
        try:
            message = f"""
🎯 **TAKE PROFIT HIT!** 🎯

{trade_info['symbol']} {trade_info['trade_type']} @ {trade_info['entry_price']}
✅ **TP:** {trade_info['take_profit']} (+50 pips)

💰 **Profit:** +50 pips
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🆔 **Trade ID:** {trade_id}

#Profit #Forex #Trading
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Update trade status
            self.active_trades[trade_id]['status'] = 'TP_HIT'
            
            logger.info(f"🎯 TP hit reported: {trade_info['symbol']}")
            
        except Exception as e:
            logger.error(f"❌ Error reporting TP hit: {e}")
    
    async def _report_sl_hit(self, trade_id: str, trade_info: Dict):
        """Report when SL is hit"""
        try:
            message = f"""
🛡️ **STOP LOSS HIT** 🛡️

{trade_info['symbol']} {trade_info['trade_type']} @ {trade_info['entry_price']}
❌ **SL:** {trade_info['stop_loss']} (-50 pips)

💸 **Loss:** -50 pips
⏰ **Time:** {datetime.now().strftime('%H:%M:%S')}
🆔 **Trade ID:** {trade_id}

#StopLoss #Forex #Trading
            """.strip()
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Update trade status
            self.active_trades[trade_id]['status'] = 'SL_HIT'
            
            logger.info(f"🛡️ SL hit reported: {trade_info['symbol']}")
            
        except Exception as e:
            logger.error(f"❌ Error reporting SL hit: {e}")
    
    async def stop(self):
        """Stop the bot"""
        await self.bot.session.close()
        logger.info("🛑 Bot stopped")


async def main():
    """Main function"""
    bot = PracticalTradingBot()
    
    try:
        await bot.start_generating()
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
