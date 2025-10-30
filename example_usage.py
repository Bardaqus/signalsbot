#!/usr/bin/env python3
"""
Example usage of Signals_bot
"""
import asyncio
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType, SignalStatus


async def main():
    """Example of how to use the Signals_bot"""
    print("🤖 Signals Bot Example Usage")
    print("=" * 40)
    
    # Initialize signal processor
    processor = SignalProcessor()
    
    # Add a demo account
    processor.add_account("demo_account_1", "Demo Account 1")
    print("✅ Added demo account")
    
    # Add a test channel
    processor.add_channel("@test_signals", "Test Signals Channel", "demo_account_1")
    print("✅ Added test channel")
    
    # Create a trading signal
    signal = TradingSignal(
        symbol="EURUSD",
        trade_type="BUY",
        entry_price=1.0650,
        stop_loss=1.0600,
        take_profit=1.0750,
        volume=1.0,
        comment="Example signal",
        channel_id="@test_signals",
        account_id="demo_account_1"
    )
    
    print("\n📈 Created trading signal:")
    print(f"   Symbol: {signal.symbol}")
    print(f"   Type: {signal.trade_type}")
    print(f"   Entry: {signal.entry_price}")
    print(f"   SL: {signal.stop_loss}")
    print(f"   TP: {signal.take_profit}")
    
    # Format signal as Telegram message
    telegram_message = signal.to_telegram_message()
    print("\n📱 Telegram message format:")
    print(telegram_message)
    
    # Convert to trade parameters
    trade_params = signal.to_trade_params()
    print("\n🔧 Trade parameters for cTrader:")
    print(trade_params)
    
    # Get current statistics
    stats = processor.get_statistics()
    print("\n📊 Current statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n✅ Example completed!")
    print("\nTo run the actual bot:")
    print("1. Configure your .env file with real credentials")
    print("2. Run: python main.py")
    print("3. Use /test command in Telegram to send test signals")


if __name__ == "__main__":
    asyncio.run(main())

