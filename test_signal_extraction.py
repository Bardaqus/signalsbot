"""
Test signal extraction from channel messages
"""
import asyncio
from channel_monitor import ChannelMonitor

async def test_signal_extraction():
    """Test signal extraction with sample messages"""
    monitor = ChannelMonitor()
    
    # Test messages
    test_messages = [
        "BUY EURUSD @ 1.0850 SL: 1.0800 TP: 1.0900",
        "SELL GBPUSD @ 1.2650 SL: 1.2700 TP: 1.2550",
        "Long BTC/USDT Entry: 45000 Stop: 44000 Target: 47000",
        "Short ETH/USDT Entry: 3000 Stop: 3100 Target: 2800",
        "Regular message without signal",
        "BUY XAUUSD @ 2000 SL: 1990 TP: 2020",
    ]
    
    print("🧪 Testing Signal Extraction")
    print("=" * 50)
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📨 Test {i}: {message}")
        
        signal = monitor._extract_signal(message, "-1002175884868")
        
        if signal:
            print(f"✅ Signal detected:")
            print(f"   Symbol: {signal.symbol}")
            print(f"   Type: {signal.trade_type.value}")
            print(f"   Entry: {signal.entry_price}")
            print(f"   Stop Loss: {signal.stop_loss}")
            print(f"   Take Profit: {signal.take_profit}")
        else:
            print("❌ No signal detected")

if __name__ == "__main__":
    asyncio.run(test_signal_extraction())



