#!/usr/bin/env python3
"""
Quick cTrader Authentication Helper
"""
import asyncio
import webbrowser
from ctrader_api import CTraderAPI
from config import Config

async def quick_auth():
    """Quick authentication process"""
    print("🔐 Quick cTrader Authentication")
    print("=" * 40)
    
    api = CTraderAPI()
    
    # Generate auth URL
    auth_url = await api.get_auth_url()
    print(f"📱 Visit this URL: {auth_url}")
    print()
    
    # Open browser
    try:
        webbrowser.open(auth_url)
        print("🌐 Browser opened automatically")
    except:
        print("⚠️  Please open the URL manually")
    
    print("\n📋 Steps:")
    print("1. Log in to cTrader")
    print("2. Authorize the app")
    print("3. Copy the 'code' parameter from the redirect URL")
    print("4. Paste it below")
    print()
    
    # Get code
    auth_code = input("🔑 Authorization code: ").strip()
    
    if not auth_code:
        print("❌ No code provided")
        return False
    
    # Exchange for token
    print("🔄 Getting access token...")
    success = await api.exchange_code_for_token(auth_code)
    
    if success:
        print("✅ Authentication successful!")
        print(f"🔑 Token: {api.access_token[:30]}...")
        
        # Test with your account
        api.set_account_id(Config.DEMO_ACCOUNT_ID)
        print(f"🏦 Set account to: {Config.DEMO_ACCOUNT_ID}")
        
        # Test placing a trade
        print("🧪 Testing trade placement...")
        trade_result = await api.place_trade(
            symbol_name="EURUSD",
            trade_type="BUY", 
            volume=0.01,
            comment="Test trade from bot"
        )
        
        if trade_result:
            print("✅ Test trade successful!")
            print(f"Trade ID: {trade_result.get('trade_id', 'Unknown')}")
        else:
            print("❌ Test trade failed")
        
        return True
    else:
        print("❌ Authentication failed")
        return False

if __name__ == "__main__":
    asyncio.run(quick_auth())



