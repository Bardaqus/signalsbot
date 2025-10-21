#!/usr/bin/env python3
"""
Test script to verify the bot works
"""

import asyncio
from working_bot import Bot, send_forex_signal, send_crypto_signal

async def test_bot():
    """Test the bot functionality"""
    print("🧪 Testing Working Bot...")
    
    try:
        # Test bot creation
        bot = Bot(token="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
        print("✅ Bot created successfully")
        
        # Test forex signal generation
        print("🎯 Testing forex signal generation...")
        await send_forex_signal(bot)
        
        # Test crypto signal generation
        print("🎯 Testing crypto signal generation...")
        await send_crypto_signal(bot)
        
        print("✅ All tests passed! Bot is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot())
