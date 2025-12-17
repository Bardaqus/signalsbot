#!/usr/bin/env python3
"""
Setup script for real price APIs
This script helps you configure the bot to use real prices
"""

import os

def setup_binance_api():
    """Setup Binance API credentials"""
    print("🔑 Setting up Binance API for crypto prices...")
    print("=" * 50)
    print("1. Go to https://www.binance.com/en/my/settings/api-management")
    print("2. Create a new API key")
    print("3. Enable 'Enable Reading' permission")
    print("4. Copy your API Key and Secret")
    print("=" * 50)
    
    api_key = input("Enter your Binance API Key: ").strip()
    api_secret = input("Enter your Binance API Secret: ").strip()
    
    if api_key and api_secret:
        # Update the working_bot.py file
        with open("working_bot.py", "r") as f:
            content = f.read()
        
        content = content.replace('BINANCE_API_KEY = ""', f'BINANCE_API_KEY = "{api_key}"')
        content = content.replace('BINANCE_API_SECRET = ""', f'BINANCE_API_SECRET = "{api_secret}"')
        
        with open("working_bot.py", "w") as f:
            f.write(content)
        
        print("✅ Binance API credentials saved!")
        return True
    else:
        print("❌ API credentials not provided")
        return False

def setup_ctrader_api():
    """Setup cTrader API credentials"""
    print("\n🔑 Setting up cTrader API for forex prices...")
    print("=" * 50)
    print("1. Go to https://ctrader.com/")
    print("2. Create an account and get API access")
    print("3. Get your Client ID and Client Secret")
    print("=" * 50)
    
    client_id = input("Enter your cTrader Client ID (or press Enter to skip): ").strip()
    client_secret = input("Enter your cTrader Client Secret (or press Enter to skip): ").strip()
    
    if client_id and client_secret:
        # Update the working_bot.py file
        with open("working_bot.py", "r") as f:
            content = f.read()
        
        content = content.replace('CTRADER_CLIENT_ID = ""', f'CTRADER_CLIENT_ID = "{client_id}"')
        content = content.replace('CTRADER_CLIENT_SECRET = ""', f'CTRADER_CLIENT_SECRET = "{client_secret}"')
        
        with open("working_bot.py", "w") as f:
            f.write(content)
        
        print("✅ cTrader API credentials saved!")
        return True
    else:
        print("⚠️ cTrader API credentials skipped (using free forex API)")
        return False

def test_apis():
    """Test the API connections"""
    print("\n🧪 Testing API connections...")
    
    try:
        from working_bot import get_real_crypto_price, get_real_forex_price
        
        # Test crypto API
        print("Testing Binance API...")
        btc_price = get_real_crypto_price("BTCUSDT")
        if btc_price:
            print(f"✅ BTCUSDT price: ${btc_price:,.2f}")
        else:
            print("❌ Could not get crypto price")
        
        # Test forex API
        print("Testing Forex API...")
        eur_price = get_real_forex_price("EURUSD")
        if eur_price:
            print(f"✅ EURUSD price: {eur_price:.5f}")
        else:
            print("❌ Could not get forex price")
        
    except Exception as e:
        print(f"❌ Error testing APIs: {e}")

def main():
    """Main setup function"""
    print("🚀 Real Price API Setup")
    print("=" * 50)
    print("This script will help you configure real price APIs")
    print("for your trading signals bot.")
    print("=" * 50)
    
    # Setup Binance API
    binance_ok = setup_binance_api()
    
    # Setup cTrader API (optional)
    ctrader_ok = setup_ctrader_api()
    
    # Test APIs
    if binance_ok or ctrader_ok:
        test_apis()
    
    print("\n" + "=" * 50)
    print("✅ Setup complete!")
    print("📊 Your bot will now use REAL prices from:")
    if binance_ok:
        print("  • Binance API for crypto prices")
    if ctrader_ok:
        print("  • cTrader API for forex prices")
    else:
        print("  • Free forex API for forex prices")
    print("=" * 50)
    print("🚀 Run: python3 start_working_bot.py")

if __name__ == "__main__":
    main()
