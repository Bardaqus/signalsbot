#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cTrader Account List Diagnostic Tool (WebSocket version)

This script uses WebSocket to get account list via cTrader Open API.
Requires CLIENT_ID, CLIENT_SECRET, and ACCESS_TOKEN from .env.

Usage:
    python tools/ctrader_accounts_websocket.py
"""
import asyncio
import os
import sys
from typing import Optional, List, Dict

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from dotenv import load_dotenv

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
os.chdir(project_root)

# Load environment variables
load_dotenv('.env', override=False)
if os.path.exists('config_live.env'):
    load_dotenv('config_live.env', override=True)

try:
    from ctrader_open_api.client import Client
    from ctrader_open_api.factory import Factory
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
except ImportError:
    print("[ERROR] ctrader_open_api library not found")
    print("   Make sure OpenApiPy directory exists in project root")
    sys.exit(1)


DEMO_WS = "wss://openapi.ctrader.com:5035"


class CTraderAccountListerWebSocket:
    """cTrader Account List diagnostic tool using WebSocket"""
    
    def __init__(self):
        self.client_id = os.getenv('CTRADER_CLIENT_ID', '').strip().strip('"').strip("'")
        self.client_secret = os.getenv('CTRADER_CLIENT_SECRET', '').strip().strip('"').strip("'")
        self.access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip().strip('"').strip("'")
        self.client: Optional[Client] = None
        self.accounts_received = []
        self.auth_complete = False
        self.accounts_complete = False
        
    def _validate_config(self) -> bool:
        """Validate that required configuration is present"""
        if not self.client_id or "your_client" in self.client_id.lower():
            print("[ERROR] CTRADER_CLIENT_ID not found or is placeholder in .env")
            print("   Set it in your .env file: CTRADER_CLIENT_ID=your_real_client_id")
            print("   Get it from: https://openapi.ctrader.com")
            return False
        
        if not self.client_secret or "your_client" in self.client_secret.lower():
            print("[ERROR] CTRADER_CLIENT_SECRET not found or is placeholder in .env")
            print("   Set it in your .env file: CTRADER_CLIENT_SECRET=your_real_client_secret")
            return False
        
        if not self.access_token:
            print("[ERROR] CTRADER_ACCESS_TOKEN not found in .env")
            print("   Set it in your .env file: CTRADER_ACCESS_TOKEN=your_access_token")
            return False
        
        return True
    
    async def _message_handler(self, message):
        """Handle incoming messages from cTrader"""
        try:
            if hasattr(message, 'payloadType'):
                payload_type = message.payloadType
                
                if payload_type == "ProtoOAApplicationAuthRes":
                    print("[OK] Application authentication successful")
                    self.auth_complete = True
                    
                    # Now request account list
                    print("[INFO] Requesting account list...")
                    accounts_req = OACommon.ProtoOAGetAccountListByAccessTokenReq(
                        accessToken=self.access_token
                    )
                    await self.client.send(accounts_req)
                    
                elif payload_type == "ProtoOAGetAccountListByAccessTokenRes":
                    print("[OK] Account list received")
                    self.accounts_complete = True
                    
                    # Extract accounts
                    if hasattr(message, 'ctidTraderAccount'):
                        for account in message.ctidTraderAccount:
                            self.accounts_received.append({
                                'ctidTraderAccountId': account.ctidTraderAccountId,
                                'isLive': account.isLive,
                                'traderLogin': account.traderLogin,
                                'currency': account.currency,
                                'brokerName': account.brokerName,
                                'leverage': account.leverage,
                                'balance': account.balance,
                                'brokerAccountName': account.brokerAccountName,
                            })
                    elif hasattr(message, 'account'):
                        # Single account
                        acc = message.account
                        self.accounts_received.append({
                            'ctidTraderAccountId': acc.ctidTraderAccountId,
                            'isLive': acc.isLive,
                            'traderLogin': acc.traderLogin,
                            'currency': acc.currency,
                            'brokerName': acc.brokerName,
                            'leverage': acc.leverage,
                            'balance': acc.balance,
                            'brokerAccountName': acc.brokerAccountName,
                        })
                    
                elif payload_type.endswith("Res") and "Error" in payload_type:
                    print(f"[ERROR] Received error response: {payload_type}")
                    if hasattr(message, 'errorMsg'):
                        print(f"   Error message: {message.errorMsg}")
                    self.accounts_complete = True
                    
        except Exception as e:
            print(f"[ERROR] Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    async def connect_and_get_accounts(self) -> bool:
        """Connect to cTrader and get account list"""
        try:
            print("[CONNECT] Connecting to cTrader WebSocket...")
            print(f"   Server: {DEMO_WS}")
            
            # Create client
            self.client = Client(Factory(DEMO_WS))
            
            # Set message handler
            self.client.set_on_message(self._message_handler)
            
            # Connect
            await self.client.connect()
            print("[OK] Connected to cTrader WebSocket")
            
            # Wait a moment for connection to stabilize
            await asyncio.sleep(1)
            
            # Application auth
            print("[AUTH] Authenticating application...")
            print(f"   Client ID: {self.client_id[:20]}...")
            app_auth = OACommon.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            await self.client.send(app_auth)
            print("[INFO] Application auth request sent")
            
            # Wait for authentication and account list (max 10 seconds)
            timeout = 10
            elapsed = 0
            while elapsed < timeout and not self.accounts_complete:
                await asyncio.sleep(0.5)
                elapsed += 0.5
                if self.auth_complete and not self.accounts_complete and elapsed > 2:
                    # If auth succeeded but no accounts yet, wait a bit more
                    pass
            
            if not self.auth_complete:
                print("[ERROR] Application authentication timeout")
                return False
            
            if not self.accounts_complete:
                print("[ERROR] Account list request timeout")
                return False
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def print_accounts(self, accounts: List[Dict]):
        """Print account list in a formatted way"""
        if not accounts:
            print("[WARN] No accounts found")
            return
        
        print()
        print("=" * 80)
        print("[INFO] AVAILABLE ACCOUNTS")
        print("=" * 80)
        print()
        
        for i, account in enumerate(accounts, 1):
            account_type = "LIVE" if account.get('isLive', False) else "DEMO"
            account_type_marker = "[LIVE]" if account.get('isLive', False) else "[DEMO]"
            
            print(f"{account_type_marker} Account #{i}: {account_type}")
            print(f"   Account ID (ctidTraderAccountId): {account.get('ctidTraderAccountId', 'N/A')}")
            if account.get('traderLogin'):
                print(f"   Trader Login: {account['traderLogin']}")
            print(f"   Broker: {account.get('brokerName', 'Unknown')}")
            if account.get('brokerAccountName'):
                print(f"   Broker Account: {account['brokerAccountName']}")
            print(f"   Currency: {account.get('currency', 'USD')}")
            if account.get('leverage'):
                print(f"   Leverage: 1:{account['leverage']}")
            if account.get('balance'):
                balance = account['balance']
                # Convert from micro units if needed
                if balance > 1000000:
                    balance = balance / 1000000.0
                print(f"   Balance: {balance:.2f} {account.get('currency', 'USD')}")
            print()
        
        print("=" * 80)
        print()
        print("[TIP] TO USE IN YOUR CONFIGURATION:")
        print()
        
        # Find demo accounts
        demo_accounts = [acc for acc in accounts if not acc.get('isLive', False)]
        live_accounts = [acc for acc in accounts if acc.get('isLive', False)]
        
        if demo_accounts:
            print("   For DEMO_ACCOUNT_ID, use one of these:")
            for acc in demo_accounts:
                account_id = acc.get('ctidTraderAccountId', 'N/A')
                broker = acc.get('brokerName', 'Unknown')
                print(f"      DEMO_ACCOUNT_ID={account_id}  # {broker} Demo")
        else:
            print("   [WARN] No DEMO accounts found")
        
        if live_accounts:
            print()
            print("   For LIVE accounts:")
            for acc in live_accounts:
                account_id = acc.get('ctidTraderAccountId', 'N/A')
                broker = acc.get('brokerName', 'Unknown')
                print(f"      LIVE_ACCOUNT_ID={account_id}  # {broker} Live")
        
        print()
        print("=" * 80)
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.client:
            try:
                await self.client.disconnect()
                print("[CONNECT] Disconnected from cTrader")
            except:
                pass
    
    async def run(self):
        """Main execution flow"""
        print("=" * 80)
        print("cTrader Account List Diagnostic Tool (WebSocket)")
        print("=" * 80)
        print()
        
        # Validate configuration
        if not self._validate_config():
            return False
        
        print(f"[OK] Found access token: {self.access_token[:30]}...")
        print()
        
        try:
            # Connect and get accounts
            success = await self.connect_and_get_accounts()
            
            if success and self.accounts_received:
                self.print_accounts(self.accounts_received)
                return True
            else:
                print("[ERROR] Could not retrieve account list")
                if not self.auth_complete:
                    print("   Application authentication failed")
                elif not self.accounts_complete:
                    print("   Account list request failed or timeout")
                return False
                
        finally:
            await self.disconnect()


async def main():
    """Main entry point"""
    lister = CTraderAccountListerWebSocket()
    success = await lister.run()
    
    if success:
        print("[OK] Diagnostic completed successfully")
        return 0
    else:
        print("[ERROR] Diagnostic failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[STOP] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
