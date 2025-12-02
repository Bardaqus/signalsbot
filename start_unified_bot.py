#!/usr/bin/env python3
"""
Startup script for the unified bot (Forex + Crypto)
Clears old signals and starts fresh daily
"""

import os
import asyncio
from datetime import datetime, timezone
from unified_bot import run_unified_bot

def clear_old_signals():
    """Clear signals from previous days for both forex and crypto"""
    try:
        # Clear forex signals
        if os.path.exists("active_signals.json"):
            import json
            with open("active_signals.json", "r") as f:
                signals = json.load(f)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_signals = [s for s in signals if s.get("date") == today]
            
            with open("active_signals.json", "w") as f:
                json.dump(today_signals, f, indent=2)
            
            print(f"🧹 Cleared old forex signals, kept {len(today_signals)} from today")
    except Exception as e:
        print(f"⚠️ Could not clear old forex signals: {e}")
    
    try:
        # Clear crypto signals
        if os.path.exists("crypto_signals.json"):
            import json
            with open("crypto_signals.json", "r") as f:
                signals = json.load(f)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_signals = [s for s in signals if s.get("date") == today]
            
            with open("crypto_signals.json", "w") as f:
                json.dump(today_signals, f, indent=2)
            
            print(f"🧹 Cleared old crypto signals, kept {len(today_signals)} from today")
    except Exception as e:
        print(f"⚠️ Could not clear old crypto signals: {e}")

async def main():
    print("🚀 Starting Unified Telegram Signals Bot (Forex + Crypto)")
    print("=" * 60)
    print("📊 Forex Channel: -1003118256304")
    print("📊 Crypto Channel: -1002978318746")
    print("📊 Reports User: 615348532")
    print("=" * 60)
    
    # Clear old signals
    clear_old_signals()
    
    # Start unified bot
    await run_unified_bot()

if __name__ == "__main__":
    asyncio.run(main())
