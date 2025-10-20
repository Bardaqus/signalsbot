#!/usr/bin/env python3
"""
Startup script for the continuous bot
Clears old signals and starts fresh daily
"""

import os
import asyncio
from datetime import datetime, timezone
from continuous_bot import run_continuous_bot

def clear_old_signals():
    """Clear signals from previous days"""
    try:
        if os.path.exists("active_signals.json"):
            import json
            with open("active_signals.json", "r") as f:
                signals = json.load(f)
            
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_signals = [s for s in signals if s.get("date") == today]
            
            with open("active_signals.json", "w") as f:
                json.dump(today_signals, f, indent=2)
            
            print(f"🧹 Cleared old signals, kept {len(today_signals)} from today")
    except Exception as e:
        print(f"⚠️ Could not clear old signals: {e}")

async def main():
    print("🚀 Starting Telegram Forex Signals Bot")
    print("=" * 50)
    
    # Clear old signals
    clear_old_signals()
    
    # Start continuous bot
    await run_continuous_bot()

if __name__ == "__main__":
    asyncio.run(main())
