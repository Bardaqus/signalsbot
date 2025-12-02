#!/usr/bin/env python3
"""
Continuous bot that ensures signals per day with time restrictions
Runs every 5 minutes to check for signals and TP/SL hits
Only sends signals between 4 GMT and 23 GMT with random 3-5 hour intervals
"""

import asyncio
import time
import random
from datetime import datetime, timezone, timedelta
from bot import post_signals_once, DEFAULT_PAIRS, get_today_signals_count, MAX_SIGNALS_PER_DAY

async def run_continuous_bot():
    """Run the bot continuously with time restrictions and random intervals"""
    print("🤖 Starting continuous bot...")
    print("📊 Target: Signals between 4 GMT - 23 GMT")
    print("⏰ Random intervals: 3-5 hours between signals")
    print("🔄 Running every 5 minutes")
    print("Press Ctrl+C to stop")
    
    # Track last signal time
    last_signal_time = None
    next_signal_time = None
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            current_hour = current_time.hour
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            # Check if it's weekend (forex market is closed)
            weekday = current_time.weekday()  # 0=Monday, 6=Sunday
            if weekday >= 5:  # Saturday (5) or Sunday (6)
                print("🏖️ Weekend detected - Forex market is closed. Skipping forex signal generation.")
                # Still check for TP hits even on weekends
                from bot import check_signal_hits, Bot
                bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
                
                # Check for TP hits
                profit_messages = check_signal_hits()
                if profit_messages:
                    print(f"🎯 Found {len(profit_messages)} TP hits")
                    for msg in profit_messages:
                        print(f"📤 Sending TP message: {msg}")
                        await bot.send_message(chat_id="-1003118256304", text=msg, disable_web_page_preview=True)
                        await asyncio.sleep(0.4)
                else:
                    print("🔍 No TP hits found")
                
                # Wait 5 minutes before next check
                print("⏳ Waiting 5 minutes...")
                await asyncio.sleep(300)  # 5 minutes
                continue
            
            # Check if we're in trading hours (4 GMT - 23 GMT)
            if current_hour < 4 or current_hour >= 23:
                print(f"🌙 Outside trading hours ({current_hour}:00 GMT). Market closed.")
                # Still check for TP hits
                from bot import check_signal_hits, Bot
                bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
                
                profit_messages = check_signal_hits()
                if profit_messages:
                    print(f"🎯 Found {len(profit_messages)} TP hits")
                    for msg in profit_messages:
                        print(f"📤 Sending TP message: {msg}")
                        await bot.send_message(chat_id="-1003118256304", text=msg, disable_web_page_preview=True)
                        await asyncio.sleep(0.4)
                else:
                    print("🔍 No TP hits found")
                
                # Wait 5 minutes before next check
                print("⏳ Waiting 5 minutes...")
                await asyncio.sleep(300)  # 5 minutes
                continue
            
            # Check if it's time for next signal (random 3-5 hour intervals)
            if next_signal_time is None or current_time >= next_signal_time:
                print("🎯 Time for next signal!")
                await post_signals_once(DEFAULT_PAIRS)
                
                # Set next signal time (random 3-5 hours from now)
                next_interval_hours = random.uniform(3, 5)
                next_signal_time = current_time + timedelta(hours=next_interval_hours)
                last_signal_time = current_time
                
                print(f"⏰ Next signal scheduled for: {next_signal_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                print(f"📊 Interval: {next_interval_hours:.1f} hours")
            else:
                time_until_next = next_signal_time - current_time
                hours_until = time_until_next.total_seconds() / 3600
                print(f"⏳ Next signal in {hours_until:.1f} hours ({next_signal_time.strftime('%H:%M:%S')} UTC)")
            
            # Always check for TP hits
            from bot import check_signal_hits, Bot
            bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
            
            profit_messages = check_signal_hits()
            if profit_messages:
                print(f"🎯 Found {len(profit_messages)} TP hits")
                for msg in profit_messages:
                    print(f"📤 Sending TP message: {msg}")
                    await bot.send_message(chat_id="-1003118256304", text=msg, disable_web_page_preview=True)
                    await asyncio.sleep(0.4)
            else:
                print("🔍 No TP hits found")
            
            # Wait 5 minutes before next check
            print("⏳ Waiting 5 minutes...")
            await asyncio.sleep(300)  # 5 minutes
            
        except KeyboardInterrupt:
            print("\n🛑 Continuous bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in continuous bot: {e}")
            print("⏳ Waiting 5 minutes before retry...")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(run_continuous_bot())
