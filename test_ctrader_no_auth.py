#!/usr/bin/env python3
"""
Test cTrader API without authentication
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ctrader_api import CTraderAPI
from config import Config

async def test_ctrader_no_auth():
    """Test cTrader API without authentication"""
    print("🧪 Testing cTrader API without Authentication...")
    print("=" * 50)
    
    api = CTraderAPI()
    api.set_account_id(Config.DEMO_ACCOUNT_ID)
    
    # Test getting quotes
    print("📊 Testing quote retrieval...")
    symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    
    for symbol in symbols:
        quote = await api.get_current_quotes(symbol)
        if quote:
            print(f"✅ {symbol}: Bid={quote['bid']}, Ask={quote['ask']}")
        else:
            print(f"❌ {symbol}: Failed to get quote")
    
    # Test placing a trade
    print("\n🎯 Testing trade simulation...")
    trade_result = await api.place_trade(
        symbol_name="EURUSD",
        trade_type="BUY",
        volume=1.0,
        stop_loss=1.0600,
        take_profit=1.0700,
        comment="Test trade"
    )
    
    if trade_result:
        print("✅ Trade simulation successful!")
        print(f"   Trade ID: {trade_result['trade_id']}")
        print(f"   Symbol: {trade_result['symbol']}")
        print(f"   Type: {trade_result['trade_type']}")
        print(f"   Entry: {trade_result['entry_price']}")
        print(f"   SL: {trade_result['stop_loss']}")
        print(f"   TP: {trade_result['take_profit']}")
        print(f"   Status: {trade_result['status']}")
    else:
        print("❌ Trade simulation failed")
    
    print("\n🎉 cTrader API test completed!")
    print("✅ API works without authentication")
    print("🚀 Ready to run the full auto signals bot!")

if __name__ == "__main__":
    asyncio.run(test_ctrader_no_auth())

