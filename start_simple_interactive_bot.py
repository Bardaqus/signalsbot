#!/usr/bin/env python3
"""
Startup script for the simple interactive bot with buttons
"""

import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from simple_interactive_bot import main

if __name__ == "__main__":
    print("🚀 Starting Simple Interactive Trading Signals Bot")
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
    
    main()
