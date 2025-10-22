#!/usr/bin/env python3
"""
Startup script for the working combined trading signals bot
"""

import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from working_combined_bot import main

if __name__ == "__main__":
    print("🚀 Starting Working Combined Trading Signals Bot")
    print("=" * 60)
    print("📊 Features:")
    print("  • Automatic signal generation (2-5 hour intervals)")
    print("  • Manual signal generation with buttons")
    print("  • Real-time status and distribution monitoring")
    print("  • 24-hour and 7-day performance reports")
    print("  • Daily summary reports (14:30 GMT)")
    print("  • Weekly summary reports (Friday 14:30 GMT)")
    print("  • All signals use REAL prices from live markets")
    print("  • Fixed all asyncio issues with threading")
    print("=" * 60)
    print("📤 Channels:")
    print("  • Forex: -1003118256304")
    print("  • Crypto: -1002978318746")
    print("=" * 60)
    print("📊 Summary Reports:")
    print("  • Daily: 14:30 GMT (24h results)")
    print("  • Weekly: Friday 14:30 GMT (7 days results)")
    print("  • Sent to user: 615348532")
    print("=" * 60)
    print("🎯 Signal Limits:")
    print("  • Forex: 5 signals per day")
    print("  • Crypto: 5 signals per day")
    print("  • Crypto distribution: 73% BUY / 27% SELL")
    print("=" * 60)
    print("🔐 Authorized Users:")
    print("  • 615348532")
    print("  • 501779863")
    print("=" * 60)
    print("📱 To use interactive features:")
    print("  1. Send /start to your bot")
    print("  2. Use the buttons to control signals")
    print("  3. Check status and reports anytime")
    print("=" * 60)
    
    main()
