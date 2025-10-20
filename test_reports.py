#!/usr/bin/env python3
"""
Test script to manually trigger performance reports
"""

import asyncio
from bot import send_performance_report, Bot

async def test_reports():
    """Test performance reports"""
    bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
    
    print("🧪 Testing performance reports...")
    
    # Test daily report
    print("\n📊 Testing daily report...")
    await send_performance_report(bot, days=1)
    
    # Test weekly report
    print("\n📊 Testing weekly report...")
    await send_performance_report(bot, days=7)
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_reports())
