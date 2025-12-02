#!/usr/bin/env python3
"""
Simple startup script for Auto Signals Bot
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from auto_signal_generator import AutoSignalGenerator
from loguru import logger


async def main():
    """Main function"""
    print("🚀 Starting Auto Signals Bot...")
    print("=" * 50)
    
    # Test configuration
    try:
        print(f"📱 Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"🔑 Client ID: {Config.CTRADER_CLIENT_ID[:20]}...")
        print(f"🏦 Account: {Config.DEMO_ACCOUNT_ID}")
        print(f"📺 Channel: {Config.TEST_CHANNEL_ID}")
        print(f"⏰ Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        print(f"🎯 SL: {Config.SL_PIPS} pips, TP: {Config.TP_PIPS} pips")
        print()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return
    
    # Create generator
    generator = AutoSignalGenerator()
    
    try:
        print("🤖 Auto signal generator starting...")
        print("Press Ctrl+C to stop")
        print()
        
        # Send startup message
        await generator.send_startup_message()
        
        # Start auto signals
        await generator.start_auto_signals()
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        generator.stop_auto_signals()
        print("👋 Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

