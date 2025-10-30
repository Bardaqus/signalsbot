#!/usr/bin/env python3
"""
Test channel access for the bot
"""
import asyncio
from config import Config
from aiogram import Bot


async def test_channel():
    """Test if bot can access the channel"""
    print("🧪 Testing Channel Access...")
    print(f"📱 Channel ID: {Config.TEST_CHANNEL_ID}")
    print(f"🤖 Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    try:
        # Test sending a message
        message = """
🧪 **Channel Access Test**

✅ Bot can access this channel!
🚀 Ready to send trading signals

**Next:** Run the auto signals bot
"""
        
        await bot.send_message(
            chat_id=Config.TEST_CHANNEL_ID,
            text=message,
            parse_mode="Markdown"
        )
        
        print("✅ Channel access successful!")
        print("📱 Test message sent to channel")
        
    except Exception as e:
        print(f"❌ Channel access failed: {e}")
        print("\n🔧 Possible solutions:")
        print("1. Make sure the bot is added to the channel as admin")
        print("2. Check the channel ID is correct")
        print("3. Verify the bot token is valid")
    
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(test_channel())

