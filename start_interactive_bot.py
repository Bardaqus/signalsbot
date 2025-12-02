#!/usr/bin/env python3
"""
Startup script for the interactive bot with buttons
"""

import asyncio
import os
from interactive_bot import main

async def startup():
    print("🚀 Starting Interactive Trading Signals Bot")
    print("=" * 50)
    print("📱 Features:")
    print("  • Manual forex signal generation")
    print("  • Manual crypto signal generation")
    print("  • Real-time status monitoring")
    print("  • Performance reports")
    print("  • Interactive buttons")
    print("=" * 50)
    print("🔐 To use the bot:")
    print("  1. Send /start to your bot")
    print("  2. Use the buttons to control signals")
    print("  3. Check status and reports anytime")
    print("=" * 50)
    
    await main()

if __name__ == "__main__":
    asyncio.run(startup())
