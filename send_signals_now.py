#!/usr/bin/env python3
"""
Send signals immediately - for testing
"""

import asyncio
from working_bot import Bot, send_forex_signal, send_crypto_signal

async def send_signals_now():
    """Send one forex and one crypto signal immediately"""
    print("🚀 Sending signals immediately...")
    
    try:
        bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
        print("✅ Bot connected successfully")
        
        # Send forex signal
        print("📊 Sending forex signal...")
        await send_forex_signal(bot)
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Send crypto signal
        print("🪙 Sending crypto signal...")
        await send_crypto_signal(bot)
        
        print("✅ Both signals sent successfully!")
        print("📊 Check your Telegram channels:")
        print("  • Forex: -1003118256304")
        print("  • Crypto: -1002978318746")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(send_signals_now())
