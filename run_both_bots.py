#!/usr/bin/env python3
"""
Run both Forex and Crypto bots in parallel
This script starts both bots simultaneously using asyncio
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone

async def run_forex_bot():
    """Run the forex bot"""
    print("🤖 Starting Forex Bot...")
    try:
        from continuous_bot import run_continuous_bot
        await run_continuous_bot()
    except Exception as e:
        print(f"❌ Forex bot error: {e}")

async def run_crypto_bot():
    """Run the crypto bot"""
    print("🤖 Starting Crypto Bot...")
    try:
        from continuous_crypto_bot import run_continuous_crypto_bot
        await run_continuous_crypto_bot()
    except Exception as e:
        print(f"❌ Crypto bot error: {e}")

async def main():
    """Run both bots in parallel"""
    print("🚀 Starting Both Forex and Crypto Bots")
    print("=" * 50)
    print("📊 Forex Channel: -1003118256304")
    print("📊 Crypto Channel: -1002978318746")
    print("📊 Reports User: 615348532")
    print("=" * 50)
    print("Press Ctrl+C to stop both bots")
    
    # Create tasks for both bots
    forex_task = asyncio.create_task(run_forex_bot())
    crypto_task = asyncio.create_task(run_crypto_bot())
    
    try:
        # Wait for both tasks to complete
        await asyncio.gather(forex_task, crypto_task)
    except KeyboardInterrupt:
        print("\n🛑 Stopping both bots...")
        forex_task.cancel()
        crypto_task.cancel()
        
        # Wait for tasks to finish cancellation
        try:
            await asyncio.gather(forex_task, crypto_task, return_exceptions=True)
        except Exception:
            pass
        
        print("✅ Both bots stopped successfully")

if __name__ == "__main__":
    asyncio.run(main())
