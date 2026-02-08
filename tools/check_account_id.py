#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick check: Is 44749280 a valid DEMO_ACCOUNT_ID?

This script tries to use the account ID directly to verify it works.
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
    sys.exit(1)


async def test_account_id():
    """Test if account ID 44749280 works"""
    account_id = 44749280
    access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip()
    client_id = os.getenv('CTRADER_CLIENT_ID', '').strip()
    client_secret = os.getenv('CTRADER_CLIENT_SECRET', '').strip()
    
    print("=" * 80)
    print("Quick Account ID Check")
    print("=" * 80)
    print()
    print(f"Testing Account ID: {account_id}")
    print(f"Access Token: {access_token[:30]}...")
    print()
    
    if not access_token:
        print("[ERROR] CTRADER_ACCESS_TOKEN not found")
        return False
    
    if not client_id or "your_client" in client_id.lower():
        print("[WARN] CLIENT_ID not configured properly")
        print("   This test requires CLIENT_ID and CLIENT_SECRET")
        print("   But Account ID 44749280 might still be correct")
        print()
        print("[TIP] Based on your .env file, you mentioned:")
        print(f"   CTRADER_ACCOUNT_ID=44749280")
        print()
        print("   You can try setting this directly:")
        print(f"   DEMO_ACCOUNT_ID={account_id}")
        print(f"   # or")
        print(f"   CTRADER_ACCOUNT_ID={account_id}")
        return False
    
    try:
        print("[CONNECT] Connecting to cTrader...")
        DEMO_WS = "wss://openapi.ctrader.com:5035"
        client = Client(Factory(DEMO_WS))
        await client.connect()
        print("[OK] Connected")
        
        # Application auth
        print("[AUTH] Authenticating application...")
        app_auth = OACommon.ProtoOAApplicationAuthReq(
            clientId=client_id,
            clientSecret=client_secret
        )
        await client.send(app_auth)
        await asyncio.sleep(1)
        
        # Account auth
        print(f"[AUTH] Authenticating account {account_id}...")
        acc_auth = OACommon.ProtoOAAccountAuthReq(
            ctidTraderAccountId=account_id,
            accessToken=access_token
        )
        await client.send(acc_auth)
        await asyncio.sleep(1)
        
        print("[OK] Account authentication successful!")
        print()
        print(f"[RESULT] Account ID {account_id} is VALID and can be used as DEMO_ACCOUNT_ID")
        print()
        print("Add to your .env:")
        print(f"   DEMO_ACCOUNT_ID={account_id}")
        
        await client.disconnect()
        return True
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        print()
        print("[INFO] Account ID might still be correct, but authentication failed")
        print("   This could be due to:")
        print("   - Invalid CLIENT_ID/CLIENT_SECRET")
        print("   - Expired ACCESS_TOKEN")
        print("   - Account ID belongs to different broker")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_account_id())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
