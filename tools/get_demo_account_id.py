#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple script to get DEMO_ACCOUNT_ID using WebSocket (more reliable than gRPC)

Usage:
    python tools/get_demo_account_id.py
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
os.chdir(project_root)

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


async def get_accounts():
    """Get account list using WebSocket"""
    client_id = os.getenv('CTRADER_CLIENT_ID', '').strip().strip('"').strip("'")
    client_secret = os.getenv('CTRADER_CLIENT_SECRET', '').strip().strip('"').strip("'")
    access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip().strip('"').strip("'")
    
    print("=" * 80)
    print("cTrader Account List (WebSocket)")
    print("=" * 80)
    print()
    
    # Validate
    if not client_id or "your_client" in client_id.lower():
        print("[ERROR] CTRADER_CLIENT_ID not configured")
        return None
    
    if not client_secret or "your_client" in client_secret.lower():
        print("[ERROR] CTRADER_CLIENT_SECRET not configured")
        return None
    
    if not access_token:
        print("[ERROR] CTRADER_ACCESS_TOKEN not found")
        return None
    
    print(f"[OK] Client ID: {client_id[:30]}...")
    print(f"[OK] Access Token: {access_token[:30]}...")
    print()
    
    accounts_received = []
    auth_complete = False
    accounts_complete = False
    
    async def recv_loop():
        """Receive and process messages"""
        nonlocal auth_complete, accounts_complete, accounts_received
        
        try:
            async for pkt in client.packets():
                try:
                    # Check for application auth response
                    if pkt.payloadType == OACommon.ProtoOAApplicationAuthRes.DESCRIPTOR.full_name:
                        print("[OK] Application authenticated")
                        auth_complete = True
                        
                        # Request account list
                        print("[INFO] Requesting account list...")
                        accounts_req = OACommon.ProtoOAGetAccountListByAccessTokenReq(
                            accessToken=access_token
                        )
                        await client.send(accounts_req)
                        
                    # Check for account list response
                    elif pkt.payloadType == OACommon.ProtoOAGetAccountListByAccessTokenRes.DESCRIPTOR.full_name:
                        res = OACommon.ProtoOAGetAccountListByAccessTokenRes()
                        res.ParseFromString(pkt.payload)
                        
                        print("[OK] Account list received")
                        accounts_complete = True
                        
                        if hasattr(res, 'ctidTraderAccount'):
                            for account in res.ctidTraderAccount:
                                accounts_received.append({
                                    'id': account.ctidTraderAccountId,
                                    'isLive': account.isLive,
                                    'login': account.traderLogin,
                                    'broker': account.brokerName,
                                    'currency': account.currency,
                                })
                        
                        # Exit after receiving accounts
                        return
                        
                except Exception as e:
                    print(f"[ERROR] Error processing message: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                    
        except Exception as e:
            print(f"[ERROR] Error in receive loop: {e}")
            import traceback
            traceback.print_exc()
    
    try:
        print("[CONNECT] Connecting to cTrader WebSocket...")
        # Parse URL (same approach as list_ctrader_indices_websocket.py)
        from urllib.parse import urlparse
        parsed = urlparse(DEMO_WS)
        host = parsed.hostname
        port = parsed.port or 5035
        protocol = 'wss' if parsed.scheme == 'wss' else 'ws'
        
        # Create client with parsed components
        client = Client(host=host, port=port, protocol=protocol)
        
        await client.connect()
        print("[OK] Connected")
        
        # Start receive loop
        recv_task = asyncio.create_task(recv_loop())
        
        # Wait a moment
        await asyncio.sleep(1)
        
        # Application auth
        print("[AUTH] Authenticating application...")
        app_auth = OACommon.ProtoOAApplicationAuthReq(
            clientId=client_id,
            clientSecret=client_secret
        )
        await client.send(app_auth)
        
        # Wait for accounts (max 15 seconds)
        try:
            await asyncio.wait_for(recv_task, timeout=15.0)
        except asyncio.TimeoutError:
            print("[ERROR] Timeout waiting for account list")
            recv_task.cancel()
        
        if not auth_complete:
            print("[ERROR] Authentication timeout")
            return None
        
        if not accounts_complete:
            print("[ERROR] Account list timeout")
            return None
        
        await client.disconnect()
        
        return accounts_received
        
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")
        import traceback
        traceback.print_exc()
        return None


def print_accounts(accounts):
    """Print account list"""
    if not accounts:
        print("[WARN] No accounts found")
        return
    
    print()
    print("=" * 80)
    print("[RESULT] AVAILABLE ACCOUNTS")
    print("=" * 80)
    print()
    
    demo_accounts = [acc for acc in accounts if not acc.get('isLive', False)]
    live_accounts = [acc for acc in accounts if acc.get('isLive', False)]
    
    if demo_accounts:
        print("[DEMO] Accounts:")
        for acc in demo_accounts:
            print(f"   Account ID: {acc['id']}")
            print(f"   Login: {acc.get('login', 'N/A')}")
            print(f"   Broker: {acc.get('broker', 'Unknown')}")
            print(f"   Currency: {acc.get('currency', 'USD')}")
            print()
    
    if live_accounts:
        print("[LIVE] Accounts:")
        for acc in live_accounts:
            print(f"   Account ID: {acc['id']}")
            print(f"   Login: {acc.get('login', 'N/A')}")
            print(f"   Broker: {acc.get('broker', 'Unknown')}")
            print(f"   Currency: {acc.get('currency', 'USD')}")
            print()
    
    print("=" * 80)
    print()
    print("[TIP] Add to your .env file:")
    print()
    
    if demo_accounts:
        print("   # Use first DEMO account:")
        print(f"   DEMO_ACCOUNT_ID={demo_accounts[0]['id']}")
        print()
        if len(demo_accounts) > 1:
            print("   # Or choose another DEMO account:")
            for acc in demo_accounts[1:]:
                print(f"   # DEMO_ACCOUNT_ID={acc['id']}  # {acc.get('broker', 'Unknown')}")
    else:
        print("   [WARN] No DEMO accounts found!")
    
    print()
    print("=" * 80)


async def main():
    accounts = await get_accounts()
    if accounts:
        print_accounts(accounts)
        return 0
    else:
        print("[ERROR] Failed to get accounts")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
