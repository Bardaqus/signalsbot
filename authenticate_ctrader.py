#!/usr/bin/env python3
"""
cTrader Authentication Helper
"""
import asyncio
import webbrowser
from ctrader_api import CTraderAPI
from config import Config


async def authenticate_ctrader():
    """Help authenticate with cTrader API"""
    print("🔐 cTrader Authentication Helper")
    print("=" * 50)
    
    api = CTraderAPI()
    
    # Generate auth URL
    auth_url = await api.get_auth_url()
    print(f"📱 Please visit this URL to authorize the app:")
    print(f"🔗 {auth_url}")
    print()
    
    # Try to open browser
    try:
        webbrowser.open(auth_url)
        print("🌐 Opening browser...")
    except:
        print("⚠️  Could not open browser automatically")
    
    print("\n📋 Steps to authenticate:")
    print("1. Visit the URL above")
    print("2. Log in with your cTrader account")
    print("3. Authorize the application")
    print("4. Copy the authorization code from the redirect URL")
    print("5. Paste it below")
    print()
    
    # Get authorization code from user
    auth_code = input("🔑 Enter authorization code: ").strip()
    
    if not auth_code:
        print("❌ No authorization code provided")
        return False
    
    # Exchange code for token
    print("🔄 Exchanging code for access token...")
    success = await api.exchange_code_for_token(auth_code)
    
    if success:
        print("✅ Authentication successful!")
        print(f"🔑 Access token: {api.access_token[:20]}...")
        
        # Save token to config (in a real app, you'd save this securely)
        print("💾 Token saved for this session")
        
        # Test API connection
        print("\n🧪 Testing API connection...")
        accounts = await api.get_accounts()
        if accounts:
            print(f"✅ Found {len(accounts)} accounts")
            for account in accounts:
                print(f"  - {account.get('name', 'Unknown')} ({account.get('id', 'No ID')})")
        else:
            print("⚠️  No accounts found or API error")
        
        return True
    else:
        print("❌ Authentication failed")
        return False


async def test_connection():
    """Test the cTrader connection"""
    print("\n🔍 Testing cTrader Connection...")
    print("-" * 30)
    
    api = CTraderAPI()
    
    # Test without authentication first
    print("📊 Getting available symbols...")
    symbols = await api.get_symbols()
    if symbols:
        print(f"✅ Found {len(symbols)} symbols")
        # Show first few symbols
        for i, symbol in enumerate(symbols[:5]):
            print(f"  - {symbol.get('symbol', 'Unknown')}")
        if len(symbols) > 5:
            print(f"  ... and {len(symbols) - 5} more")
    else:
        print("❌ No symbols found")
    
    # Test quotes (this might require authentication)
    print("\n💰 Testing quote retrieval...")
    quote = await api.get_current_quotes("EURUSD")
    if quote:
        print(f"✅ EURUSD Quote: {quote}")
    else:
        print("⚠️  Quote retrieval failed (may require authentication)")


async def main():
    """Main function"""
    print("🚀 cTrader Setup Assistant")
    print("=" * 50)
    
    # Test basic connection
    await test_connection()
    
    print("\n" + "=" * 50)
    print("🔐 Authentication Required")
    print("To place trades, you need to authenticate with cTrader.")
    print("This is a one-time setup process.")
    print()
    
    response = input("🤔 Do you want to authenticate now? (y/N): ")
    
    if response.lower() == 'y':
        success = await authenticate_ctrader()
        if success:
            print("\n🎉 Setup complete! You can now run the auto signals bot.")
        else:
            print("\n❌ Authentication failed. Please try again.")
    else:
        print("\n⚠️  Authentication skipped.")
        print("The bot will work but won't be able to place actual trades.")
        print("You can authenticate later by running this script again.")


if __name__ == "__main__":
    asyncio.run(main())

