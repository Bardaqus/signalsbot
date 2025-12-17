#!/usr/bin/env python3
"""
Startup script for the complete bot (Automatic + Interactive)
"""

import asyncio
import os
from complete_bot import main

async def startup():
    print("🚀 Starting Complete Trading Signals Bot")
    print("=" * 60)
    print("🤖 Automatic Features:")
    print("  • Generates 5 forex signals daily")
    print("  • Generates 5 crypto signals daily (73% BUY / 27% SELL)")
    print("  • Runs every 5 minutes automatically")
    print("  • Sends performance reports")
    print("")
    print("📱 Interactive Features:")
    print("  • Manual signal generation via buttons")
    print("  • Real-time status monitoring")
    print("  • Performance reports on demand")
    print("  • Telegram control panel")
    print("=" * 60)
    print("🔐 To use interactive features:")
    print("  1. Send /start to your bot")
    print("  2. Use the buttons to control signals")
    print("  3. Check status and reports anytime")
    print("=" * 60)
    print("📊 Channels:")
    print(f"  • Forex: {os.getenv('TELEGRAM_CHANNEL_ID', '-1003118256304')}")
    print(f"  • Crypto: -1002978318746")
    print("=" * 60)
    
    await main()

if __name__ == "__main__":
    asyncio.run(startup())
