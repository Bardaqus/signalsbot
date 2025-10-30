#!/usr/bin/env python3
"""
Simple channel test
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import Config
    from aiogram import Bot
    
    async def test():
        print("🧪 Testing Channel Access...")
        print(f"Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"Channel ID: {Config.TEST_CHANNEL_ID}")
        
        bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        
        try:
            # Try to get chat info
            chat = await bot.get_chat(Config.TEST_CHANNEL_ID)
            print(f"✅ Chat found: {chat.title}")
            print(f"📱 Chat ID: {chat.id}")
            print(f"📝 Chat Type: {chat.type}")
            
            # Try to send message
            await bot.send_message(
                chat_id=chat.id,
                text="✅ **Channel Test Successful!**\n\nBot can access this channel!",
                parse_mode="Markdown"
            )
            print("✅ Message sent successfully!")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            
            # Try alternative formats
            print("\n🔄 Trying alternative formats...")
            
            alternatives = [
                "-100" + Config.TEST_CHANNEL_ID.replace("+", ""),
                Config.TEST_CHANNEL_ID.replace("+", "-100"),
                "@" + Config.TEST_CHANNEL_ID
            ]
            
            for alt in alternatives:
                try:
                    print(f"Testing: {alt}")
                    chat = await bot.get_chat(alt)
                    print(f"✅ Found with: {alt}")
                    print(f"   Title: {chat.title}")
                    print(f"   ID: {chat.id}")
                    
                    await bot.send_message(
                        chat_id=chat.id,
                        text="✅ **Alternative Format Works!**\n\nUse this channel ID in config.",
                        parse_mode="Markdown"
                    )
                    print(f"✅ SUCCESS! Use: {alt}")
                    break
                    
                except Exception as e2:
                    print(f"❌ Failed: {e2}")
        
        finally:
            await bot.session.close()
    
    asyncio.run(test())
    
except Exception as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the correct directory and config files exist.")

