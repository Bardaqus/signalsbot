#!/usr/bin/env python3
"""
Scheduler script to run the bot every minute
This ensures TP hits are checked frequently and reports are sent at the right time
"""

import asyncio
import time
from datetime import datetime, timezone
from bot import post_signals_once, DEFAULT_PAIRS

async def run_scheduler():
    """Run the bot every minute"""
    print("🕐 Starting scheduler - running every minute...")
    print("Press Ctrl+C to stop")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC - Running bot...")
            
            await post_signals_once(DEFAULT_PAIRS)
            
            # Wait 60 seconds before next run
            print("⏳ Waiting 60 seconds...")
            await asyncio.sleep(60)
            
        except KeyboardInterrupt:
            print("\n🛑 Scheduler stopped by user")
            break
        except Exception as e:
            print(f"❌ Error in scheduler: {e}")
            print("⏳ Waiting 60 seconds before retry...")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(run_scheduler())
