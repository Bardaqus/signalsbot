#!/usr/bin/env python3
"""
Final test with correct channel ID
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from aiogram import Bot

async def test():
    print("🧪 Testing Channel Access with Correct ID...")
    print(f"📱 Channel ID: {Config.TEST_CHANNEL_ID}")
    print(f"🤖 Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    try:
        # Test sending a message
        message = """
✅ **Channel Access Test - SUCCESS!**

🎉 The bot can now access your channel!

**Configuration:**
• Channel ID: -1002175884868
• Signal Interval: 4 minutes
• SL/TP: 30/50 pips
• Demo Mode: Active

**Ready to start auto signals!** 🚀
"""
        
        await bot.send_message(
            chat_id=Config.TEST_CHANNEL_ID,
            text=message,
            parse_mode="Markdown"
        )
        
        print("✅ SUCCESS! Message sent to channel")
        print("🎉 Channel access is working!")
        print("\n🚀 You can now start the auto signals bot:")
        print("   python3 auto_signals_simple.py")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n🔧 Possible issues:")
        print("1. Bot not added to channel as admin")
        print("2. Bot doesn't have 'Post Messages' permission")
        print("3. Channel ID is incorrect")
    
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test())

