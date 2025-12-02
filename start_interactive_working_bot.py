#!/usr/bin/env python3
"""
Startup script for the interactive working bot with buttons
"""

import asyncio
from working_bot import run_interactive_bot

async def startup():
    print("🚀 Starting Interactive Working Bot with Buttons")
    print("=" * 60)
    print("📱 Features:")
    print("  • Manual forex signal generation")
    print("  • Manual crypto signal generation")
    print("  • Real-time status monitoring")
    print("  • 24-hour and 7-day performance reports")
    print("  • Interactive buttons")
    print("  • REAL prices from live markets")
    print("=" * 60)
    print("🔐 To use the bot:")
    print("  1. Send /start to your bot")
    print("  2. Use the buttons to control signals")
    print("  3. Check status and reports anytime")
    print("=" * 60)
    print("📊 Channels:")
    print("  • Forex: -1003118256304")
    print("  • Crypto: -1002978318746")
    print("=" * 60)
    
    await run_interactive_bot()

if __name__ == "__main__":
    asyncio.run(startup())
