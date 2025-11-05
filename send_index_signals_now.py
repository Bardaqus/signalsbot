#!/usr/bin/env python3
"""
Script to send index/gold signals immediately
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from working_combined_bot import send_manual_index_signals

async def main():
    print("🚀 Sending manual index/gold signals...")
    print("=" * 60)
    await send_manual_index_signals()
    print("=" * 60)
    print("✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())



