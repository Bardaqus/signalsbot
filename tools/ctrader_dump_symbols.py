#!/usr/bin/env python3
"""
Dump all symbols from cTrader account to find gold symbol name
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / ".env", override=True)

# Import cTrader modules
try:
    from ctrader_open_api.client import Client
    from ctrader_open_api.factory import Factory
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
    from ctrader_open_api.messages import OpenApiMessages_pb2 as OAMessages
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as OAModel
except ImportError as e:
    print(f"ERROR: Failed to import cTrader modules: {e}")
    print("Install ctrader_open_api package first")
    sys.exit(1)

import asyncio
from urllib.parse import urlparse

# Get credentials from env
client_id = os.getenv('CTRADER_CLIENT_ID', '').strip()
client_secret = os.getenv('CTRADER_CLIENT_SECRET', '').strip()
access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip()
account_id_str = os.getenv('CTRADER_ACCOUNT_ID', '').strip()

# Try DEMO_ACCOUNT_ID as fallback
if not account_id_str:
    account_id_str = os.getenv('DEMO_ACCOUNT_ID', '').strip()

if not all([client_id, client_secret, access_token, account_id_str]):
    print("ERROR: Missing required credentials in .env:")
    print(f"  CTRADER_CLIENT_ID: {'[OK]' if client_id else '[MISSING]'}")
    print(f"  CTRADER_CLIENT_SECRET: {'[OK]' if client_secret else '[MISSING]'}")
    print(f"  CTRADER_ACCESS_TOKEN: {'[OK]' if access_token else '[MISSING]'}")
    print(f"  CTRADER_ACCOUNT_ID: {'[OK]' if account_id_str else '[MISSING]'}")
    sys.exit(1)

try:
    account_id = int(account_id_str)
except ValueError:
    print(f"ERROR: Invalid CTRADER_ACCOUNT_ID: {repr(account_id_str)}")
    sys.exit(1)

# Get WebSocket URL
is_demo = os.getenv('CTRADER_IS_DEMO', 'true').strip().lower() in ('true', '1', 'yes', 'on')
if is_demo:
    ws_url = os.getenv('CTRADER_DEMO_WS_URL', 'wss://demo.ctraderapi.com:5035').strip()
else:
    ws_url = os.getenv('CTRADER_LIVE_WS_URL', 'wss://live.ctraderapi.com:5035').strip()

if not ws_url:
    ws_url = "wss://demo.ctraderapi.com:5035" if is_demo else "wss://live.ctraderapi.com:5035"

print("=" * 80)
print("CTRADER SYMBOLS DUMP")
print("=" * 80)
print(f"Account ID: {account_id}")
print(f"Is Demo: {is_demo}")
print(f"WebSocket URL: {ws_url}")
print()

# Parse URL
parsed = urlparse(ws_url)
host = parsed.hostname
port = parsed.port or 5035
protocol = 'wss' if parsed.scheme == 'wss' else 'ws'

print(f"Connecting to {host}:{port} ({protocol})...")
print()

# Twisted Deferred to asyncio adapter
try:
    from twisted.internet import defer
    from twisted.python.failure import Failure
    
    async def await_deferred(d):
        if not isinstance(d, defer.Deferred):
            return d
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        
        def _cb(res):
            if not fut.done():
                fut.set_result(res)
            return res
        
        def _eb(err):
            if isinstance(err, Failure):
                exc = err.value
            else:
                exc = err
            if not fut.done():
                fut.set_exception(exc)
            return err
        
        d.addCallbacks(_cb, _eb)
        return await fut
except ImportError:
    async def await_deferred(d):
        return d

async def main():
    """Connect to cTrader and dump symbols"""
    # Create client
    client = Client(host=host, port=port, protocol=protocol)
    factory = Factory(client=client)
    
    # Connection state
    connection_established = asyncio.Event()
    
    def on_connected():
        print("Connected to cTrader WebSocket")
        connection_established.set()
    
    def on_disconnected():
        print("Disconnected from cTrader WebSocket")
        connection_established.clear()
    
    client.setConnectedCallback(on_connected)
    client.setDisconnectedCallback(on_disconnected)
    
    # Start service
    print("Starting Twisted service...")
    client.startService()
    
    # Wait for connection
    try:
        await asyncio.wait_for(connection_established.wait(), timeout=30.0)
        print("Connection established")
    except asyncio.TimeoutError:
        print("ERROR: Connection timeout")
        client.stopService()
        return
    
    # Application Auth
    print("\nStep 1: Application Authentication...")
    try:
        ProtoOAApplicationAuthReq = None
        ProtoOAApplicationAuthRes = None
        
        # Try to find in different modules
        for module in [OACommon, OAMessages, OAModel]:
            if hasattr(module, 'ProtoOAApplicationAuthReq'):
                ProtoOAApplicationAuthReq = getattr(module, 'ProtoOAApplicationAuthReq')
            if hasattr(module, 'ProtoOAApplicationAuthRes'):
                ProtoOAApplicationAuthRes = getattr(module, 'ProtoOAApplicationAuthRes')
        
        if not ProtoOAApplicationAuthReq:
            print("ERROR: ProtoOAApplicationAuthReq not found")
            client.stopService()
            return
        
        app_auth = ProtoOAApplicationAuthReq(
            clientId=client_id,
            clientSecret=client_secret
        )
        
        await await_deferred(client.send(app_auth))
        print("ApplicationAuth sent")
        
        # Wait a bit for response
        await asyncio.sleep(2)
        
    except Exception as e:
        print(f"ERROR in ApplicationAuth: {e}")
        import traceback
        traceback.print_exc()
        client.stopService()
        return
    
    # Account Auth
    print("\nStep 2: Account Authentication...")
    try:
        ProtoOAAccountAuthReq = None
        ProtoOAAccountAuthRes = None
        
        for module in [OACommon, OAMessages, OAModel]:
            if hasattr(module, 'ProtoOAAccountAuthReq'):
                ProtoOAAccountAuthReq = getattr(module, 'ProtoOAAccountAuthReq')
            if hasattr(module, 'ProtoOAAccountAuthRes'):
                ProtoOAAccountAuthRes = getattr(module, 'ProtoOAAccountAuthRes')
        
        if not ProtoOAAccountAuthReq:
            print("ERROR: ProtoOAAccountAuthReq not found")
            client.stopService()
            return
        
        acc_auth = ProtoOAAccountAuthReq(
            ctidTraderAccountId=account_id,
            accessToken=access_token
        )
        
        await await_deferred(client.send(acc_auth))
        print("AccountAuth sent")
        
        # Wait a bit for response
        await asyncio.sleep(2)
        
    except Exception as e:
        print(f"ERROR in AccountAuth: {e}")
        import traceback
        traceback.print_exc()
        client.stopService()
        return
    
    # Request Symbols List
    print("\nStep 3: Requesting Symbols List...")
    try:
        ProtoOASymbolsListReq = None
        ProtoOASymbolsListRes = None
        
        for module in [OACommon, OAMessages, OAModel]:
            if hasattr(module, 'ProtoOASymbolsListReq'):
                ProtoOASymbolsListReq = getattr(module, 'ProtoOASymbolsListReq')
            if hasattr(module, 'ProtoOASymbolsListRes'):
                ProtoOASymbolsListRes = getattr(module, 'ProtoOASymbolsListRes')
        
        if not ProtoOASymbolsListReq:
            print("ERROR: ProtoOASymbolsListReq not found")
            client.stopService()
            return
        
        sym_list_req = ProtoOASymbolsListReq(
            ctidTraderAccountId=account_id
        )
        
        await await_deferred(client.send(sym_list_req))
        print("SymbolsList request sent")
        
        # Wait for response
        await asyncio.sleep(3)
        
        # Try to receive response
        symbols_received = []
        message_count = 0
        
        try:
            async for pkt in client.packets():
                message_count += 1
                if message_count > 50:  # Limit to avoid infinite loop
                    break
                
                # Try to parse as ProtoOASymbolsListRes
                if hasattr(pkt, 'symbol'):
                    symbols_received = list(pkt.symbol)
                    break
                elif hasattr(pkt, 'payloadType'):
                    # Try to parse payload
                    try:
                        if ProtoOASymbolsListRes:
                            res = ProtoOASymbolsListRes()
                            if hasattr(pkt, 'payload'):
                                res.ParseFromString(pkt.payload)
                                if hasattr(res, 'symbol'):
                                    symbols_received = list(res.symbol)
                                    break
                    except:
                        pass
        except Exception as e:
            print(f"Warning: Error receiving symbols: {e}")
        
        if not symbols_received:
            print("WARNING: No symbols received. Trying alternative method...")
            # Alternative: just print what we got
            print(f"Received {message_count} messages")
        
    except Exception as e:
        print(f"ERROR requesting symbols: {e}")
        import traceback
        traceback.print_exc()
        client.stopService()
        return
    
    # Process and display symbols
    print("\n" + "=" * 80)
    print("ALL SYMBOLS")
    print("=" * 80)
    
    if symbols_received:
        print(f"Total symbols: {len(symbols_received)}")
        print()
        print(f"{'SymbolId':<12} {'SymbolName':<30} {'Description':<50}")
        print("-" * 100)
        
        for sym in symbols_received[:100]:  # Show first 100
            sym_id = getattr(sym, 'symbolId', 'N/A')
            sym_name = getattr(sym, 'symbolName', 'N/A')
            description = getattr(sym, 'description', 'N/A')[:50]
            print(f"{sym_id:<12} {sym_name:<30} {description:<50}")
        
        if len(symbols_received) > 100:
            print(f"... and {len(symbols_received) - 100} more symbols")
    else:
        print("No symbols found in response")
    
    # Find metals candidates
    print("\n" + "=" * 80)
    print("METALS CANDIDATES (XAU/GOLD)")
    print("=" * 80)
    
    if symbols_received:
        metals_candidates = []
        for sym in symbols_received:
            sym_name = getattr(sym, 'symbolName', '').upper()
            if 'XAU' in sym_name or 'GOLD' in sym_name:
                sym_id = getattr(sym, 'symbolId', 'N/A')
                description = getattr(sym, 'description', 'N/A')
                asset_class = getattr(sym, 'assetClass', 'N/A')
                enabled = getattr(sym, 'enabled', True)
                trading_allowed = getattr(sym, 'tradingAllowed', True)
                
                metals_candidates.append({
                    'id': sym_id,
                    'name': getattr(sym, 'symbolName', 'N/A'),
                    'description': description,
                    'asset_class': asset_class,
                    'enabled': enabled,
                    'trading_allowed': trading_allowed
                })
        
        if metals_candidates:
            print(f"Found {len(metals_candidates)} metal-related symbols:")
            print()
            print(f"{'SymbolId':<12} {'SymbolName':<30} {'AssetClass':<15} {'Enabled':<10} {'Trading':<10} {'Description':<30}")
            print("-" * 120)
            
            for cand in metals_candidates:
                print(f"{cand['id']:<12} {cand['name']:<30} {str(cand['asset_class']):<15} {str(cand['enabled']):<10} {str(cand['trading_allowed']):<10} {cand['description'][:30]:<30}")
            
            print()
            print("RECOMMENDATION:")
            best = metals_candidates[0]
            print(f"  Use: {best['name']} (ID: {best['id']})")
            print(f"  Set in .env: CTRADER_GOLD_SYMBOL_ID={best['id']}")
            print(f"  Or: GOLD_SYMBOL_NAME={best['name']}")
        else:
            print("No metal-related symbols found!")
            print("Check if your account has access to gold/metals trading")
    else:
        print("Cannot find metals - symbols list not received")
    
    # Cleanup
    print("\nDisconnecting...")
    client.stopService()
    await asyncio.sleep(1)
    print("Done")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
