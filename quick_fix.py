#!/usr/bin/env python3
"""
Quick fix for channel access
"""
import asyncio
from config import Config
from aiogram import Bot


async def quick_fix():
    """Quick fix for channel access"""
    print("🔧 Quick Fix for Channel Access")
    print("=" * 50)
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    # Common channel ID formats to try
    channel_formats = [
        "+ZaJCtmMwXJthYzJi",  # Original format
        "-100" + "ZaJCtmMwXJthYzJi",  # Supergroup format
        "@+ZaJCtmMwXJthYzJi",  # With @
    ]
    
    print("🧪 Testing different channel ID formats...")
    
    for i, channel_id in enumerate(channel_formats, 1):
        print(f"\n{i}. Testing: {channel_id}")
        try:
            # Try to get chat info first
            chat = await bot.get_chat(channel_id)
            print(f"   ✅ Chat found: {chat.title}")
            print(f"   📱 Chat ID: {chat.id}")
            print(f"   📝 Chat Type: {chat.type}")
            
            # Try to send a test message
            await bot.send_message(
                chat_id=chat.id,
                text="✅ **Channel Access Fixed!**\n\nThis is the correct channel ID format.",
                parse_mode="Markdown"
            )
            
            print(f"   🎉 SUCCESS! Use this channel ID: {chat.id}")
            print(f"\n📝 Update your config_live.env file:")
            print(f"TEST_CHANNEL_ID={chat.id}")
            
            return chat.id
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    print("\n❌ All formats failed. Let's try a different approach...")
    
    # Alternative: Get updates to find the channel
    print("\n📋 Alternative method:")
    print("1. Send a message in your channel")
    print("2. Forward that message to your bot")
    print("3. Run this script again")
    
    try:
        updates = await bot.get_updates()
        if updates:
            print(f"\n📨 Found {len(updates)} updates")
            for update in updates[-3:]:  # Show last 3 updates
                if update.message:
                    print(f"   Message from: {update.message.chat.id} ({update.message.chat.title or 'Unknown'})")
    except Exception as e:
        print(f"Error getting updates: {e}")
    
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(quick_fix())

