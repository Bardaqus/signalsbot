#!/usr/bin/env python3
"""
Test script for live configuration
"""
import asyncio
from config import Config
from auto_signal_generator import AutoSignalGenerator


async def test_configuration():
    """Test the live configuration"""
    print("🔧 Testing Live Configuration...")
    print("=" * 50)
    
    # Test config loading
    print(f"Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"Client ID: {Config.CTRADER_CLIENT_ID[:20]}...")
    print(f"Account ID: {Config.DEMO_ACCOUNT_ID}")
    print(f"Channel: {Config.TEST_CHANNEL_ID}")
    print(f"Signal Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
    print(f"SL Pips: {Config.SL_PIPS}")
    print(f"TP Pips: {Config.TP_PIPS}")
    
    # Test signal generation
    print("\n🎯 Testing Signal Generation...")
    print("=" * 50)
    
    generator = AutoSignalGenerator()
    signal = await generator.generate_random_signal()
    
    print(f"Generated Signal:")
    print(f"  Symbol: {signal.symbol}")
    print(f"  Type: {signal.trade_type}")
    print(f"  Entry: {signal.entry_price}")
    print(f"  SL: {signal.stop_loss}")
    print(f"  TP: {signal.take_profit}")
    
    print("\n📱 Telegram Message Format:")
    print("-" * 30)
    print(signal.to_telegram_message())
    
    print("\n🔧 Trade Parameters:")
    print("-" * 30)
    trade_params = signal.to_trade_params()
    for key, value in trade_params.items():
        print(f"  {key}: {value}")
    
    print("\n✅ All tests completed successfully!")
    print("\n🚀 Ready to start the auto signals bot!")


if __name__ == "__main__":
    asyncio.run(test_configuration())

