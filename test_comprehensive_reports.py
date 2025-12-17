#!/usr/bin/env python3
"""
Test script to demonstrate comprehensive performance reporting
"""

import asyncio
from bot import send_performance_report, Bot, get_performance_report
from working_combined_bot import send_daily_summary, send_weekly_summary

async def test_comprehensive_reports():
    """Test comprehensive performance reports"""
    bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
    
    print("🧪 Testing comprehensive performance reports...")
    
    # Test bot.py reports
    print("\n📊 Testing bot.py daily report...")
    daily_report = get_performance_report(1)
    print("Daily Report Preview:")
    print(daily_report[:500] + "..." if len(daily_report) > 500 else daily_report)
    
    print("\n📊 Testing bot.py weekly report...")
    weekly_report = get_performance_report(7)
    print("Weekly Report Preview:")
    print(weekly_report[:500] + "..." if len(weekly_report) > 500 else weekly_report)
    
    # Test working_combined_bot.py reports
    print("\n📊 Testing working_combined_bot.py daily summary...")
    await send_daily_summary()
    
    print("\n📊 Testing working_combined_bot.py weekly summary...")
    await send_weekly_summary()
    
    print("\n✅ Comprehensive reports test completed!")

if __name__ == "__main__":
    asyncio.run(test_comprehensive_reports())
