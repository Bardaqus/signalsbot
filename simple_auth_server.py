#!/usr/bin/env python3
"""
Simple authentication server for cTrader OAuth callback
"""
import asyncio
import webbrowser
from aiohttp import web
from ctrader_api import CTraderAPI
from config import Config

# Global variable to store the authorization code
auth_code = None

async def handle_callback(request):
    """Handle the OAuth callback"""
    global auth_code
    
    # Get the code from query parameters
    code = request.query.get('code')
    if code:
        auth_code = code
        print(f"\n✅ Authorization code received: {code}")
        print("🔐 You can now close this browser tab and return to the terminal.")
        return web.Response(text="Authentication successful! You can close this tab and return to the terminal.")
    else:
        error = request.query.get('error', 'Unknown error')
        print(f"\n❌ Authentication error: {error}")
        return web.Response(text=f"Authentication failed: {error}")

async def start_server():
    """Start the local server"""
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    
    print("🌐 Local server started on http://localhost:8080")
    return runner

async def main():
    """Main authentication flow"""
    print("🔐 cTrader Authentication with Local Server")
    print("=" * 50)
    
    # Start local server
    runner = await start_server()
    
    try:
        # Create API instance and get auth URL
        api = CTraderAPI()
        auth_url = await api.get_auth_url()
        
        print(f"\n📱 Please visit this URL:")
        print(f"🔗 {auth_url}")
        print()
        
        # Open browser
        try:
            webbrowser.open(auth_url)
            print("🌐 Browser opened automatically")
        except:
            print("⚠️  Please open the URL manually")
        
        print("\n📋 Steps:")
        print("1. Log in to cTrader")
        print("2. Authorize the application")
        print("3. You'll be redirected to localhost:8080/callback")
        print("4. The code will be captured automatically")
        print("\n⏳ Waiting for authorization...")
        
        # Wait for the callback
        while auth_code is None:
            await asyncio.sleep(1)
        
        # Exchange code for token
        print("\n🔄 Exchanging code for access token...")
        success = await api.exchange_code_for_token(auth_code)
        
        if success:
            print("✅ Authentication successful!")
            print(f"🔑 Access token: {api.access_token[:30]}...")
            
            # Set account
            api.set_account_id(Config.DEMO_ACCOUNT_ID)
            print(f"🏦 Account set to: {Config.DEMO_ACCOUNT_ID}")
            
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
                print("\n🎉 Your bot is now ready to place real trades!")
            else:
                print("❌ Trade placement failed")
        else:
            print("❌ Authentication failed")
            
    finally:
        # Clean up
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())



