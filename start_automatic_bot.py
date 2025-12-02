#!/usr/bin/env python3
"""
Startup script for the automatic signals bot
"""

import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from automatic_signals_bot import main

if __name__ == "__main__":
    print("🚀 Starting Automatic Trading Signals Bot")
    print("=" * 60)
    print("📊 Features:")
    print("  • 4-5 forex signals per day")
    print("  • 4-5 crypto signals per day")
    print("  • 2-5 hour intervals between signals")
    print("  • Real prices from live markets")
    print("  • Daily summary reports at 14:30 GMT")
    print("  • 73% BUY / 27% SELL ratio for crypto")
    print("=" * 60)
    print("📤 Channels:")
    print("  • Forex: -1003118256304")
    print("  • Crypto: -1002978318746")
    print("=" * 60)
    print("📊 Summary Reports:")
    print("  • Sent to user: 615348532")
    print("  • Time: 14:30 GMT daily")
    print("=" * 60)
    print("🎯 Signal Limits:")
    print("  • Forex: 5 signals per day")
    print("  • Crypto: 5 signals per day")
    print("=" * 60)
    
    main()
