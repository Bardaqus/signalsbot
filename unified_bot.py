#!/usr/bin/env python3
"""
Unified Bot - Runs both Forex and Crypto signals simultaneously
Manages both forex and crypto signal generation and tracking
"""

import asyncio
import time
from datetime import datetime, timezone
from bot import post_signals_once, DEFAULT_PAIRS, get_today_signals_count, MAX_SIGNALS_PER_DAY
from crypto_bot import post_crypto_signals_once, CRYPTO_PAIRS, get_today_crypto_signals_count, MAX_SIGNALS_PER_DAY as CRYPTO_MAX_SIGNALS

async def run_unified_bot():
    """Run both forex and crypto bots simultaneously"""
    print("🤖 Starting Unified Bot (Forex + Crypto)...")
    print("📊 Forex Target: 5 signals per day")
    print("📊 Crypto Target: 5 signals per day")
    print("⏰ Running every 5 minutes")
    print("Press Ctrl+C to stop")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            # Check current signal counts
            forex_count = get_today_signals_count()
            crypto_count = get_today_crypto_signals_count()
            
            # Get crypto signal distribution
            from crypto_bot import get_today_crypto_signal_distribution
            crypto_distribution = get_today_crypto_signal_distribution()
            crypto_total = crypto_distribution["BUY"] + crypto_distribution["SELL"]
            crypto_buy_ratio = (crypto_distribution["BUY"] / crypto_total * 100) if crypto_total > 0 else 0
            crypto_sell_ratio = (crypto_distribution["SELL"] / crypto_total * 100) if crypto_total > 0 else 0
            
            print(f"📊 Today's signals:")
            print(f"  Forex: {forex_count}/{MAX_SIGNALS_PER_DAY}")
            print(f"  Crypto: {crypto_count}/{CRYPTO_MAX_SIGNALS}")
            print(f"  Crypto distribution: BUY {crypto_distribution['BUY']} ({crypto_buy_ratio:.1f}%), SELL {crypto_distribution['SELL']} ({crypto_sell_ratio:.1f}%)")
            
            # Run forex bot if needed
            if forex_count < MAX_SIGNALS_PER_DAY:
                print(f"🎯 Need {MAX_SIGNALS_PER_DAY - forex_count} more forex signals")
                await post_signals_once(DEFAULT_PAIRS)
            else:
                print("✅ Already have enough forex signals for today")
                # Still check for forex TP hits
                from bot import check_signal_hits, Bot, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                
                profit_messages = check_signal_hits()
                if profit_messages:
                    print(f"🎯 Found {len(profit_messages)} forex TP hits")
                    for msg in profit_messages:
                        print(f"📤 Sending forex TP message: {msg}")
                        await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
                        await asyncio.sleep(0.4)
                else:
                    print("🔍 No forex TP hits found")
            
            # Run crypto bot if needed
            if crypto_count < CRYPTO_MAX_SIGNALS:
                print(f"🎯 Need {CRYPTO_MAX_SIGNALS - crypto_count} more crypto signals")
                await post_crypto_signals_once(CRYPTO_PAIRS)
            else:
                print("✅ Already have enough crypto signals for today")
                # Still check for crypto TP hits
                from crypto_bot import check_crypto_signal_hits, Bot, TELEGRAM_BOT_TOKEN, CRYPTO_CHANNEL_ID
                bot = Bot(token=TELEGRAM_BOT_TOKEN)
                
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
            print("\n🛑 Unified bot stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in unified bot: {e}")
            print("⏳ Waiting 5 minutes before retry...")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(run_unified_bot())
