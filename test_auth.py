#!/usr/bin/env python3
"""
Test cTrader Authentication with provided code
"""
import asyncio
import sys
from ctrader_api import CTraderAPI
from config import Config

async def test_auth_with_code(auth_code):
    """Test authentication with provided code"""
    print("🔐 Testing cTrader Authentication")
    print("=" * 40)
    
    api = CTraderAPI()
    
    # Exchange code for token
    print("🔄 Exchanging code for access token...")
    success = await api.exchange_code_for_token(auth_code)
    
    if success:
        print("✅ Authentication successful!")
        print(f"🔑 Access token: {api.access_token[:30]}...")
        
        # Set account
        api.set_account_id(Config.DEMO_ACCOUNT_ID)
        print(f"🏦 Account set to: {Config.DEMO_ACCOUNT_ID}")
        
        # Test getting accounts
        print("📊 Testing account access...")
        accounts = await api.get_accounts()
        if accounts:
            print(f"✅ Found {len(accounts)} accounts")
            for account in accounts:
                print(f"  - {account.get('name', 'Unknown')} (ID: {account.get('id', 'No ID')})")
        else:
            print("⚠️  No accounts found")
        
        # Test placing a real trade
        print("\n🧪 Testing real trade placement...")
        trade_result = await api.place_trade(
            symbol_name="EURUSD",
            trade_type="BUY", 
            volume=0.01,
            stop_loss=1.0600,
            take_profit=1.0700,
            comment="Test trade from bot"
        )
        
        if trade_result:
            print("✅ Real trade placed successfully!")
            print(f"Trade ID: {trade_result.get('trade_id', 'Unknown')}")
            print(f"Symbol: {trade_result.get('symbol', 'Unknown')}")
            print(f"Type: {trade_result.get('trade_type', 'Unknown')}")
            print(f"Volume: {trade_result.get('volume', 'Unknown')}")
            print(f"Entry Price: {trade_result.get('entry_price', 'Unknown')}")
        else:
            print("❌ Trade placement failed")
        
        return True
    else:
        print("❌ Authentication failed")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 test_auth.py <authorization_code>")
        print("Example: python3 test_auth.py abc123def456")
        sys.exit(1)
    
    auth_code = sys.argv[1]
    asyncio.run(test_auth_with_code(auth_code))



