#!/usr/bin/env python3
"""
Continuous crypto bot that ensures 3-5 signals per day
Runs every 5 minutes to check for signals and TP/SL hits
"""

import asyncio
import time
from datetime import datetime, timezone
from crypto_bot import post_crypto_signals_once, CRYPTO_PAIRS, get_today_crypto_signals_count, MAX_SIGNALS_PER_DAY

async def run_continuous_crypto_bot():
    """Run the crypto bot continuously to ensure 3-5 signals per day"""
    print("🤖 Starting continuous crypto bot...")
    print("📊 Target: 3-5 signals per day")
    print("⏰ Running every 5 minutes")
    print("Press Ctrl+C to stop")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            # Check current signal count and distribution
            today_count = get_today_crypto_signals_count()
            from crypto_bot import get_today_crypto_signal_distribution
            distribution = get_today_crypto_signal_distribution()
            total_signals = distribution["BUY"] + distribution["SELL"]
            buy_ratio = (distribution["BUY"] / total_signals * 100) if total_signals > 0 else 0
            sell_ratio = (distribution["SELL"] / total_signals * 100) if total_signals > 0 else 0
            
            print(f"📊 Today's crypto signals: {today_count}/{MAX_SIGNALS_PER_DAY}")
            print(f"📈 Signal distribution: BUY {distribution['BUY']} ({buy_ratio:.1f}%), SELL {distribution['SELL']} ({sell_ratio:.1f}%)")
            
            if today_count < MAX_SIGNALS_PER_DAY:
                print(f"🎯 Need {MAX_SIGNALS_PER_DAY - today_count} more crypto signals")
                await post_crypto_signals_once(CRYPTO_PAIRS)
            else:
                print("✅ Already have enough crypto signals for today")
                # Still check for TP hits even if we have enough signals
                from crypto_bot import check_crypto_signal_hits, Bot, TELEGRAM_BOT_TOKEN, CRYPTO_CHANNEL_ID
                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                
                # Check for TP hits
                profit_messages = check_crypto_signal_hits()
                if profit_messages:
                    print(f"🎯 Found {len(profit_messages)} crypto TP hits")
                    for msg in profit_messages:
                        print(f"📤 Sending crypto TP message: {msg}")
                        await bot.send_message(chat_id=CRYPTO_CHANNEL_ID, text=msg, disable_web_page_preview=True)
                        await asyncio.sleep(0.4)
                else:
                    print("🔍 No crypto TP hits found")
            
            # Wait 5 minutes before next check
            print("⏳ Waiting 5 minutes...")
            await asyncio.sleep(300)  # 5 minutes
            
        except KeyboardInterrupt:
            print("\n🛑 Continuous crypto bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in continuous crypto bot: {e}")
            print("⏳ Waiting 5 minutes before retry...")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(run_continuous_crypto_bot())
