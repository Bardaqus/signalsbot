#!/usr/bin/env python3
"""
cTrader Indices Finder Script (WebSocket Version)

This script uses WebSocket connection instead of gRPC, which may be more reliable.
It connects to cTrader Open API, fetches all available symbols,
and filters for indices (S&P 500, NASDAQ, DAX, etc.) to help you find
the correct ticker names for your broker.

Usage:
    python list_ctrader_indices_websocket.py
"""

import asyncio
import sys
from typing import List, Dict
from config import Config

# Try to import ctrader_open_api library
try:
    from ctrader_open_api.client import Client
    from ctrader_open_api.factory import Factory
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
    HAS_CTRADER_OPEN_API = True
except ImportError:
    HAS_CTRADER_OPEN_API = False
    print("❌ ctrader_open_api library not found")
    print("   Please install it or use the gRPC version: list_ctrader_indices.py")
    sys.exit(1)


class CTraderIndicesFinderWebSocket:
    """cTrader client to find indices symbols using WebSocket"""
    
    def __init__(self, access_token: str, client_id: str, client_secret: str, account_id: int):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = account_id
        self.client = None
        self.symbols_received = False
        self.all_symbols = []
        
    def _is_index_symbol(self, symbol_name: str) -> bool:
        """Check if a symbol is likely an index based on common patterns"""
        symbol_upper = symbol_name.upper()
        
        index_keywords = [
            '500', 'US500', 'SPX', 'SP500',
            'NAS', 'NDX', 'US100', 'NAS100',
            'DE30', 'DAX',
            'UK100', 'FTSE',
            'FR40', 'CAC',
            'IT40',
            'JP225', 'NIKKEI',
            'AU200', 'ASX',
            'INDEX', 'IDX', 'IND',
        ]
        
        for keyword in index_keywords:
            if keyword in symbol_upper:
                return True
        
        if '.' in symbol_upper:
            parts = symbol_upper.split('.')
            for part in parts:
                if any(keyword in part for keyword in index_keywords):
                    return True
        
        return False
    
    def _get_asset_class(self, symbol_name: str) -> str:
        """Determine asset class based on symbol name"""
        symbol_upper = symbol_name.upper()
        
        if any(x in symbol_upper for x in ['500', 'SPX', 'SP500', 'US500']):
            return "S&P 500"
        elif any(x in symbol_upper for x in ['NAS', 'NDX', 'US100', 'NAS100']):
            return "NASDAQ 100"
        elif any(x in symbol_upper for x in ['DE30', 'DAX']):
            return "DAX 30"
        elif any(x in symbol_upper for x in ['UK100', 'FTSE']):
            return "FTSE 100"
        elif any(x in symbol_upper for x in ['FR40', 'CAC']):
            return "CAC 40"
        elif any(x in symbol_upper for x in ['IT40']):
            return "FTSE MIB"
        elif any(x in symbol_upper for x in ['JP225', 'NIKKEI']):
            return "Nikkei 225"
        elif any(x in symbol_upper for x in ['AU200', 'ASX']):
            return "ASX 200"
        else:
            return "Index"
    
    async def start(self):
        """Start WebSocket connection and authentication"""
        try:
            # Use demo WebSocket endpoint
            DEMO_WS = "wss://openapi.ctrader.com:5035"
            
            print(f"🔌 Connecting to cTrader WebSocket: {DEMO_WS}")
            # Parse URL: wss://openapi.ctrader.com:5035
            # Client expects: host, port, protocol
            from urllib.parse import urlparse
            parsed = urlparse(DEMO_WS)
            host = parsed.hostname
            port = parsed.port or 5035
            protocol = 'wss' if parsed.scheme == 'wss' else 'ws'
            
            # Create client with parsed components
            self.client = Client(host=host, port=port, protocol=protocol)
            # Create factory with client (Factory expects client= keyword)
            factory = Factory(client=self.client)
            
            await self.client.connect()
            print("✅ Connected to cTrader WebSocket")
            
            # Application auth
            print("🔐 Authenticating application...")
            app_auth = OACommon.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            await self.client.send(app_auth)
            print("✅ Application auth sent")
            
            # Wait a bit for response
            await asyncio.sleep(1)
            
            # Account auth
            print("🔐 Authenticating account...")
            acc_auth = OACommon.ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.account_id,
                accessToken=self.access_token
            )
            await self.client.send(acc_auth)
            print("✅ Account auth sent")
            
            # Wait a bit for response
            await asyncio.sleep(1)
            
            # Request symbols list
            print("📈 Requesting symbols list...")
            sym_list_req = OACommon.ProtoOASymbolsListReq(
                ctidTraderAccountId=self.account_id
            )
            await self.client.send(sym_list_req)
            print("✅ Symbols list request sent")
            
            # Start receiving messages
            await self._recv_loop()
            
        except Exception as e:
            print(f"❌ Error connecting: {e}")
            import traceback
            traceback.print_exc()
    
    async def _recv_loop(self):
        """Receive and process messages"""
        try:
            timeout_count = 0
            max_timeout = 30  # Wait up to 30 seconds for symbols
            
            async for pkt in self.client.packets():
                try:
                    # Check for symbols list response
                    if pkt.payloadType == OACommon.ProtoOASymbolsListRes.DESCRIPTOR.full_name:
                        res = OACommon.ProtoOASymbolsListRes()
                        res.ParseFromString(pkt.payload)
                        
                        print(f"✅ Received {len(res.symbol)} symbols")
                        
                        # Filter for indices
                        indices = []
                        for symbol in res.symbol:
                            if self._is_index_symbol(symbol.symbolName):
                                asset_class = self._get_asset_class(symbol.symbolName)
                                
                                indices.append({
                                    'symbol_id': symbol.symbolId,
                                    'symbol_name': symbol.symbolName,
                                    'description': asset_class,
                                    'asset_class': asset_class,
                                    'enabled': symbol.enabled if hasattr(symbol, 'enabled') else True,
                                    'category_id': symbol.symbolCategoryId if hasattr(symbol, 'symbolCategoryId') else 0
                                })
                        
                        # Print results
                        self.print_indices_table(indices)
                        
                        # Exit after receiving symbols
                        return
                    
                    timeout_count = 0  # Reset timeout on any message
                    
                except Exception as e:
                    print(f"⚠️  Error processing message: {e}")
                    continue
            
        except asyncio.TimeoutError:
            print("❌ Timeout waiting for symbols list response")
        except Exception as e:
            print(f"❌ Error in receive loop: {e}")
            import traceback
            traceback.print_exc()
    
    def print_indices_table(self, indices: List[Dict]):
        """Print indices in a clean table format"""
        if not indices:
            print("\n❌ No indices found")
            return
        
        print("\n" + "=" * 100)
        print("INDICES FOUND IN YOUR cTRADER ACCOUNT")
        print("=" * 100)
        print(f"{'Symbol ID':<12} | {'Symbol Name':<25} | {'Description':<30} | {'Asset Class':<20} | {'Enabled':<8}")
        print("-" * 100)
        
        # Sort by symbol name for easier reading
        sorted_indices = sorted(indices, key=lambda x: x['symbol_name'])
        
        for idx in sorted_indices:
            enabled_str = "Yes" if idx['enabled'] else "No"
            print(f"{idx['symbol_id']:<12} | {idx['symbol_name']:<25} | {idx['description']:<30} | {idx['asset_class']:<20} | {enabled_str:<8}")
        
        print("=" * 100)
        print(f"\nTotal indices found: {len(indices)}")
        print("\n💡 Tip: Use the 'Symbol Name' column value in your config file")
        print("   Example: If you see 'US500', use 'US500' in your symbol subscription")


async def main():
    """Main function"""
    print("=" * 100)
    print("cTRADER INDICES FINDER (WebSocket Version)")
    print("=" * 100)
    print("\nThis script will:")
    print("  1. Connect to cTrader Open API via WebSocket")
    print("  2. Fetch all available symbols")
    print("  3. Filter for indices (S&P 500, NASDAQ, DAX, etc.)")
    print("  4. Display results in a clean table format")
    print()
    
    if not HAS_CTRADER_OPEN_API:
        print("❌ ctrader_open_api library not available")
        print("   Please install it or use the gRPC version")
        return
    
    # Get credentials from config
    access_token = Config.CTRADER_ACCESS_TOKEN
    account_id = int(Config.DEMO_ACCOUNT_ID) if Config.DEMO_ACCOUNT_ID else None
    client_id = Config.CTRADER_CLIENT_ID
    client_secret = Config.CTRADER_CLIENT_SECRET
    
    if not access_token:
        print("❌ Error: CTRADER_ACCESS_TOKEN not found in config")
        return
    
    if not account_id:
        print("❌ Error: DEMO_ACCOUNT_ID not found in config")
        return
    
    if not client_id or not client_secret:
        print("❌ Error: CTRADER_CLIENT_ID or CTRADER_CLIENT_SECRET not found in config")
        return
    
    print(f"📋 Configuration:")
    print(f"   Server: wss://openapi.ctrader.com:5035")
    print(f"   Account ID: {account_id}")
    print(f"   Client ID: {client_id[:10]}..." if client_id else "   Client ID: Not set")
    print()
    
    # Create finder instance
    finder = CTraderIndicesFinderWebSocket(access_token, client_id, client_secret, account_id)
    
    try:
        await finder.start()
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

