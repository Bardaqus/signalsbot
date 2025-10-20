#!/usr/bin/env python3
"""
Continuous bot that ensures 4 signals per day
Runs every 5 minutes to check for signals and TP/SL hits
"""

import asyncio
import time
from datetime import datetime, timezone
from bot import post_signals_once, DEFAULT_PAIRS, get_today_signals_count, MAX_SIGNALS_PER_DAY

async def run_continuous_bot():
    """Run the bot continuously to ensure 4 signals per day"""
    print("🤖 Starting continuous bot...")
    print("📊 Target: 5 signals per day")
    print("⏰ Running every 5 minutes")
    print("Press Ctrl+C to stop")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            # Check current signal count
            today_count = get_today_signals_count()
            print(f"📊 Today's signals: {today_count}/{MAX_SIGNALS_PER_DAY}")
            
            if today_count < MAX_SIGNALS_PER_DAY:
                print(f"🎯 Need {MAX_SIGNALS_PER_DAY - today_count} more signals")
                await post_signals_once(DEFAULT_PAIRS)
            else:
                print("✅ Already have 5 signals for today")
                # Still check for TP hits even if we have 4 signals
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
            
        except KeyboardInterrupt:
            print("\n🛑 Continuous bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in continuous bot: {e}")
            print("⏳ Waiting 5 minutes before retry...")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(run_continuous_bot())
