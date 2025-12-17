#!/usr/bin/env python3
"""
Find the correct channel ID for the bot
"""
import asyncio
from config import Config
from aiogram import Bot


async def find_channel_id():
    """Find the correct channel ID"""
    print("🔍 Finding Correct Channel ID...")
    print("=" * 50)
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    # Get bot info
    try:
        bot_info = await bot.get_me()
        print(f"🤖 Bot: @{bot_info.username}")
        print(f"📱 Bot ID: {bot_info.id}")
    except Exception as e:
        print(f"❌ Error getting bot info: {e}")
        return
    
    print("\n📋 Instructions:")
    print("1. Go to your channel: https://t.me/+ZaJCtmMwXJthYzJi")
    print("2. Forward ANY message from the channel to your bot")
    print("3. The bot will show you the correct channel ID")
    print("4. Press Enter when you've forwarded a message...")
    
    input("\nPress Enter after forwarding a message to the bot...")
    
    # Get updates to find the channel ID
    try:
        updates = await bot.get_updates()
        
        if not updates:
            print("❌ No messages received. Make sure you forwarded a message to the bot.")
            return
        
        # Find the latest message
        latest_update = updates[-1]
        
        if latest_update.message and latest_update.message.forward_from_chat:
            chat = latest_update.message.forward_from_chat
            print(f"\n✅ Found Channel!")
            print(f"📱 Channel Title: {chat.title}")
            print(f"🆔 Channel ID: {chat.id}")
            print(f"📝 Channel Type: {chat.type}")
            
            # Test sending a message to this ID
            print(f"\n🧪 Testing message to channel ID: {chat.id}")
            
            try:
                await bot.send_message(
                    chat_id=chat.id,
                    text="✅ **Channel ID Found!**\n\nThis is the correct channel ID for the bot.",
                    parse_mode="Markdown"
                )
                print("✅ Test message sent successfully!")
                print(f"\n🎯 Use this channel ID: {chat.id}")
                
                # Update the config
                print(f"\n📝 Update your config_live.env file:")
                print(f"TEST_CHANNEL_ID={chat.id}")
                
            except Exception as e:
                print(f"❌ Error sending test message: {e}")
                
        else:
            print("❌ No forwarded message found. Please forward a message from your channel to the bot.")
            
    except Exception as e:
        print(f"❌ Error getting updates: {e}")
    
    finally:
        await bot.session.close()


async def test_different_formats():
    """Test different channel ID formats"""
    print("\n🧪 Testing Different Channel ID Formats...")
    print("-" * 50)
    
    bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
    
    # Different formats to try
    formats_to_test = [
        "+ZaJCtmMwXJthYzJi",
        "-100" + "ZaJCtmMwXJthYzJi",  # Sometimes private channels have this format
        "@+ZaJCtmMwXJthYzJi",
        "https://t.me/+ZaJCtmMwXJthYzJi"
    ]
    
    for channel_id in formats_to_test:
        try:
            print(f"Testing: {channel_id}")
            await bot.send_message(
                chat_id=channel_id,
                text="🧪 Test message - checking channel access"
            )
            print(f"✅ SUCCESS with format: {channel_id}")
            break
        except Exception as e:
            print(f"❌ Failed: {e}")
    
    await bot.session.close()


async def main():
    """Main function"""
    print("🚀 Channel ID Finder")
    print("=" * 50)
    
    choice = input("Choose option:\n1. Find channel ID by forwarding message\n2. Test different formats\nEnter choice (1 or 2): ")
    
    if choice == "1":
        await find_channel_id()
    elif choice == "2":
        await test_different_formats()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())

