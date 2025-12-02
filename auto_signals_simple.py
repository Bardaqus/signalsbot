#!/usr/bin/env python3
"""
Simplified Auto Signals Bot - Telegram only (no cTrader trading)
"""
import asyncio
import random
import sys
import os
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from aiogram import Bot


class SimpleAutoSignals:
    """Simple auto signals bot for Telegram only"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.channel_id = Config.TEST_CHANNEL_ID
        self.is_running = False
        
        # Major currency pairs
        self.major_pairs = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", 
            "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
            "AUDJPY", "CHFJPY", "EURCHF", "GBPCHF", "AUDCAD"
        ]
        
        # Typical prices for demo
        self.demo_prices = {
            "EURUSD": 1.0650, "GBPUSD": 1.2500, "USDJPY": 150.00,
            "USDCHF": 0.9000, "AUDUSD": 0.6500, "USDCAD": 1.3500,
            "NZDUSD": 0.6000, "EURJPY": 160.00, "GBPJPY": 187.50,
            "AUDJPY": 97.50, "CHFJPY": 166.67, "EURGBP": 0.8520,
            "EURCHF": 0.9585, "GBPCHF": 1.1250, "AUDCAD": 0.8775
        }
    
    def generate_signal(self):
        """Generate a trading signal"""
        # Random pair and direction
        symbol = random.choice(self.major_pairs)
        trade_type = random.choice(["BUY", "SELL"])
        
        # Get demo price
        entry_price = self.demo_prices[symbol]
        
        # Add some randomness to price
        if "JPY" in symbol:
            price_variation = random.uniform(-0.5, 0.5)
            entry_price = round(entry_price + price_variation, 2)
        else:
            price_variation = random.uniform(-0.002, 0.002)
            entry_price = round(entry_price + price_variation, 4)
        
        # Calculate SL and TP
        if "JPY" in symbol:
            pip_value = 0.01
        else:
            pip_value = 0.0001
        
        sl_pips = Config.SL_PIPS
        tp_pips = Config.TP_PIPS
        
        if trade_type == "BUY":
            stop_loss = round(entry_price - (sl_pips * pip_value), 4 if "JPY" not in symbol else 2)
            take_profit = round(entry_price + (tp_pips * pip_value), 4 if "JPY" not in symbol else 2)
        else:
            stop_loss = round(entry_price + (sl_pips * pip_value), 4 if "JPY" not in symbol else 2)
            take_profit = round(entry_price - (tp_pips * pip_value), 4 if "JPY" not in symbol else 2)
        
        return {
            'symbol': symbol,
            'trade_type': trade_type,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'volume': 1.0,
            'sl_pips': sl_pips,
            'tp_pips': tp_pips
        }
    
    def format_signal_message(self, signal):
        """Format signal as Telegram message"""
        emoji = "🟢" if signal['trade_type'] == "BUY" else "🔴"
        
        message = f"""
{emoji} **TRADING SIGNAL**

**Symbol:** {signal['symbol']}
**Direction:** {signal['trade_type']}
**Entry Price:** {signal['entry_price']}

**Stop Loss:** {signal['stop_loss']} ({signal['sl_pips']} pips)
**Take Profit:** {signal['take_profit']} ({signal['tp_pips']} pips)

**Volume:** {signal['volume']}
**Comment:** Auto signal - {signal['sl_pips']} SL, {signal['tp_pips']} TP

📊 *Generated at {datetime.now().strftime('%H:%M:%S')}*

🤖 *Auto-generated signal*
⏰ *Next signal in {Config.AUTO_SIGNAL_INTERVAL//60} minutes*

⚠️ *Demo Mode - No actual trades executed*
"""
        return message.strip()
    
    async def send_signal(self, signal):
        """Send signal to Telegram channel"""
        try:
            message = self.format_signal_message(signal)
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode="Markdown"
            )
            
            print(f"✅ Signal sent: {signal['symbol']} {signal['trade_type']} @ {signal['entry_price']}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending signal: {e}")
            return False
    
    async def send_startup_message(self):
        """Send startup message"""
        try:
            message = f"""
🤖 **Auto Signals Bot Started!**

**Configuration:**
• Signal Interval: {Config.AUTO_SIGNAL_INTERVAL//60} minutes
• Stop Loss: {Config.SL_PIPS} pips
• Take Profit: {Config.TP_PIPS} pips
• Major Pairs: {len(self.major_pairs)} pairs

**Demo Mode Active** ⚠️
• No actual trades executed
• Signals for demonstration only
• Safe testing environment

**Next signal in {Config.AUTO_SIGNAL_INTERVAL//60} minutes...**

📊 Happy Trading! 🚀
"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode="Markdown"
            )
            
            print("✅ Startup message sent")
            
        except Exception as e:
            print(f"❌ Error sending startup message: {e}")
    
    async def start_signals(self):
        """Start generating signals"""
        if self.is_running:
            print("⚠️ Bot is already running!")
            return
        
        self.is_running = True
        print(f"🚀 Starting auto signals - Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        
        try:
            # Send startup message
            await self.send_startup_message()
            
            signal_count = 0
            
            while self.is_running:
                signal_count += 1
                print(f"\n🎯 Generating signal #{signal_count}...")
                
                # Generate and send signal
                signal = self.generate_signal()
                success = await self.send_signal(signal)
                
                if success:
                    print(f"📊 Signal #{signal_count} sent successfully")
                else:
                    print(f"❌ Signal #{signal_count} failed")
                
                # Wait for next signal
                print(f"⏳ Waiting {Config.AUTO_SIGNAL_INTERVAL} seconds for next signal...")
                await asyncio.sleep(Config.AUTO_SIGNAL_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n⏹️ Bot stopped by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            self.is_running = False
    
    def stop(self):
        """Stop the bot"""
        self.is_running = False
        print("⏹️ Stopping bot...")


async def main():
    """Main function"""
    print("🤖 Simple Auto Signals Bot")
    print("=" * 50)
    print(f"📱 Channel: {Config.TEST_CHANNEL_ID}")
    print(f"⏰ Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
    print(f"🎯 SL/TP: {Config.SL_PIPS}/{Config.TP_PIPS} pips")
    print("⚠️  Demo Mode - No actual trades")
    print()
    
    bot = SimpleAutoSignals()
    
    try:
        await bot.start_signals()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    finally:
        bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

