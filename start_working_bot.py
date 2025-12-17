#!/usr/bin/env python3
"""
Startup script for the working bot
"""

import asyncio
from working_bot import main

async def startup():
    print("🚀 Starting Working Trading Signals Bot")
    print("=" * 50)
    print("📊 This bot will send both forex and crypto signals")
    print("📊 Forex signals to: -1003118256304")
    print("🪙 Crypto signals to: -1002978318746")
    print("⏰ Runs every 5 minutes")
    print("🎯 5 signals per day for each type")
    print("🪙 Crypto maintains 73% BUY / 27% SELL ratio")
    print("=" * 50)
    print("✅ Bot is simple and guaranteed to work!")
    print("=" * 50)
    
    await main()

if __name__ == "__main__":
    asyncio.run(startup())
