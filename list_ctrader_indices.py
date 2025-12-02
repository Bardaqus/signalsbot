#!/usr/bin/env python3
"""
cTrader Indices Finder Script

This script connects to cTrader Open API, fetches all available symbols,
and filters for indices (S&P 500, NASDAQ, DAX, etc.) to help you find
the correct ticker names for your broker.

Usage:
    python list_ctrader_indices.py
"""

import asyncio
import grpc
import ssl
from typing import List, Dict, Optional
from config import Config

# Import generated protobuf classes
import ctrader_service_pb2
import ctrader_service_pb2_grpc

# Try to import symbols messages from the new proto file
try:
    import ProtoOASymbols_pb2 as symbols_pb2
    HAS_SYMBOLS_PB2 = True
except ImportError:
    HAS_SYMBOLS_PB2 = False
    # Fallback: try to use ctrader_service_pb2 if it has the symbols messages
    symbols_pb2 = None


class CTraderIndicesFinder:
    """cTrader client to find indices symbols"""
    
    def __init__(self, access_token: str, account_id: int):
        self.access_token = access_token
        self.account_id = account_id
        self.client_id = Config.CTRADER_CLIENT_ID
        self.client_secret = Config.CTRADER_CLIENT_SECRET
        
        # Demo server for demo accounts, use "live.ctraderapi.com:5035" for live
        self.server_url = "demo.ctraderapi.com:5035"
        self.channel = None
        self.stub = None
        
        # Message counter
        self.msg_id = 0
    
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id += 1
        return self.msg_id
    
    async def connect(self):
        """Connect to cTrader gRPC server"""
        try:
            print(f"🔌 Connecting to cTrader gRPC server: {self.server_url}")
            
            # Use secure channel with SSL (required by cTrader)
            # Match the working bot exactly - no extra options
            self.channel = grpc.aio.secure_channel(
                self.server_url,
                grpc.ssl_channel_credentials()
            )
            
            # Create stub
            self.stub = ctrader_service_pb2_grpc.OpenApiServiceStub(self.channel)
            
            print("✅ Channel and stub created")
            
            # Authenticate application immediately (working bots do this)
            if not await self._authenticate_application():
                return False
            
            # Authenticate account
            if not await self._authenticate_account():
                return False
            
            return True
            
        except grpc.RpcError as e:
            print(f"❌ gRPC error connecting to cTrader: {e.code()} - {e.details()}")
            print(f"   Server: {self.server_url}")
            print(f"   Tip: Check if you're using the correct server (demo vs live)")
            return False
        except Exception as e:
            print(f"❌ Failed to connect to cTrader: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _authenticate_application(self):
        """Authenticate application with cTrader"""
        try:
            print("🔐 Authenticating application...")
            
            # Create application auth request
            auth_req = ctrader_service_pb2.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAApplicationAuthReq",
                clientMsgId=self._get_next_msg_id(),
                payload=auth_req.SerializeToString()
            )
            
            # Send request - let gRPC handle timeouts naturally
            # The working bots don't wrap this in asyncio.wait_for
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAApplicationAuthRes":
                auth_res = ctrader_service_pb2.ProtoOAApplicationAuthRes()
                auth_res.ParseFromString(response.payload)
                print(f"✅ Application authenticated")
                return True
            else:
                print(f"❌ Authentication failed: {response.payloadType}")
                return False
                
        except grpc.RpcError as e:
            print(f"❌ gRPC authentication error: {e.code()} - {e.details()}")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                print("   This usually means:")
                print("   - Server is unreachable or down")
                print("   - Network/firewall blocking the connection")
                print("   - Wrong server URL (demo vs live)")
            return False
        except Exception as e:
            print(f"❌ Application authentication error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _authenticate_account(self):
        """Authenticate account with access token"""
        try:
            print("🔐 Authenticating account...")
            
            # Create account auth request
            auth_req = ctrader_service_pb2.ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.account_id,
                accessToken=self.access_token
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAAccountAuthReq",
                clientMsgId=self._get_next_msg_id(),
                payload=auth_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAAccountAuthRes":
                auth_res = ctrader_service_pb2.ProtoOAAccountAuthRes()
                auth_res.ParseFromString(response.payload)
                print(f"✅ Account authenticated: {auth_res.ctidTraderAccountId}")
                return True
            else:
                print(f"❌ Account authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            print(f"❌ Account authentication error: {e}")
            return False
    
    def _is_index_symbol(self, symbol_name: str) -> bool:
        """
        Check if a symbol is likely an index based on common patterns
        """
        symbol_upper = symbol_name.upper()
        
        # Common index patterns
        index_keywords = [
            '500',      # S&P 500
            'US500',   # S&P 500
            'SPX',     # S&P 500
            'SP500',   # S&P 500
            'NAS',     # NASDAQ
            '100',     # NASDAQ 100, DAX 100
            'US100',   # NASDAQ 100
            'NDX',     # NASDAQ 100
            'DE30',    # DAX 30
            'DAX',     # DAX
            'UK100',   # FTSE 100
            'FTSE',    # FTSE
            'FR40',    # CAC 40
            'CAC',     # CAC
            'IT40',    # FTSE MIB
            'JP225',   # Nikkei 225
            'NIKKEI',  # Nikkei
            'AU200',   # ASX 200
            'ASX',     # ASX
            'INDEX',   # Generic index
            'IDX',     # Index abbreviation
            'IND',     # Index abbreviation
        ]
        
        # Check if symbol name contains any index keyword
        for keyword in index_keywords:
            if keyword in symbol_upper:
                return True
        
        # Check for patterns like .US500, .DE30, etc.
        if '.' in symbol_upper:
            parts = symbol_upper.split('.')
            for part in parts:
                if any(keyword in part for keyword in index_keywords):
                    return True
        
        return False
    
    def _get_asset_class(self, symbol_name: str, symbol_category_id: int) -> str:
        """
        Determine asset class based on symbol name and category ID
        """
        symbol_upper = symbol_name.upper()
        
        # Try to infer from symbol name patterns
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
    
    async def get_indices(self) -> List[Dict]:
        """Get all indices symbols"""
        try:
            print("\n📈 Fetching symbols list...")
            
            # Try to use ProtoOASymbolsListReq from the generated proto files
            symbols_req = None
            symbols_res_class = None
            
            # First try the new ProtoOASymbols_pb2 file
            if HAS_SYMBOLS_PB2:
                try:
                    symbols_req = symbols_pb2.ProtoOASymbolsListReq(
                        ctidTraderAccountId=self.account_id,
                        includeArchivedSymbols=False
                    )
                    symbols_res_class = symbols_pb2.ProtoOASymbolsListRes
                    print("✅ Using ProtoOASymbols_pb2 for symbols messages")
                except Exception as e:
                    print(f"⚠️  Error using ProtoOASymbols_pb2: {e}")
                    symbols_req = None
            
            # Fallback to ctrader_service_pb2 if available
            if symbols_req is None:
                try:
                    symbols_req = ctrader_service_pb2.ProtoOASymbolsListReq(
                        ctidTraderAccountId=self.account_id,
                        includeArchivedSymbols=False
                    )
                    symbols_res_class = ctrader_service_pb2.ProtoOASymbolsListRes
                    print("✅ Using ctrader_service_pb2 for symbols messages")
                except AttributeError:
                    print("❌ ProtoOASymbolsListReq not found in any protobuf module")
                    print("\n📝 SOLUTION:")
                    print("=" * 80)
                    print("The symbols proto file has been generated: ProtoOASymbols_pb2.py")
                    print("If you still see this error, make sure ProtoOASymbols_pb2.py exists")
                    print("and contains ProtoOASymbolsListReq and ProtoOASymbolsListRes")
                    print("=" * 80)
                    return []
            
            if symbols_req is None or symbols_res_class is None:
                print("❌ Failed to create symbols request")
                return []
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOASymbolsListReq",
                clientMsgId=self._get_next_msg_id(),
                payload=symbols_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOASymbolsListRes":
                symbols_res = symbols_res_class()
                symbols_res.ParseFromString(response.payload)
                
                print(f"✅ Found {len(symbols_res.symbol)} total symbols")
                
                # Filter for indices
                indices = []
                for symbol in symbols_res.symbol:
                    if self._is_index_symbol(symbol.symbolName):
                        asset_class = self._get_asset_class(
                            symbol.symbolName, 
                            symbol.symbolCategoryId if hasattr(symbol, 'symbolCategoryId') else 0
                        )
                        
                        indices.append({
                            'symbol_id': symbol.symbolId,
                            'symbol_name': symbol.symbolName,
                            'description': asset_class,
                            'asset_class': asset_class,
                            'enabled': symbol.enabled if hasattr(symbol, 'enabled') else True,
                            'category_id': symbol.symbolCategoryId if hasattr(symbol, 'symbolCategoryId') else 0
                        })
                
                print(f"📊 Found {len(indices)} index symbols")
                return indices
            else:
                print(f"❌ Get symbols failed: {response.payloadType}")
                print(f"   Response: {response}")
                return []
                
        except Exception as e:
            print(f"❌ Error getting symbols list: {e}")
            import traceback
            traceback.print_exc()
            return []
    
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
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.channel:
            await self.channel.close()
            print("\n🔌 Disconnected from cTrader")


async def main():
    """Main function"""
    print("=" * 100)
    print("cTRADER INDICES FINDER")
    print("=" * 100)
    print("\nThis script will:")
    print("  1. Connect to cTrader Open API")
    print("  2. Fetch all available symbols")
    print("  3. Filter for indices (S&P 500, NASDAQ, DAX, etc.)")
    print("  4. Display results in a clean table format")
    print()
    
    # Get credentials from config
    access_token = Config.CTRADER_ACCESS_TOKEN
    account_id = int(Config.DEMO_ACCOUNT_ID) if Config.DEMO_ACCOUNT_ID else None
    client_id = Config.CTRADER_CLIENT_ID
    client_secret = Config.CTRADER_CLIENT_SECRET
    
    if not access_token:
        print("❌ Error: CTRADER_ACCESS_TOKEN not found in config")
        print("   Please set it in your .env file or config_live.env")
        return
    
    if not account_id:
        print("❌ Error: DEMO_ACCOUNT_ID not found in config")
        print("   Please set it in your .env file or config_live.env")
        return
    
    if not client_id or not client_secret:
        print("❌ Error: CTRADER_CLIENT_ID or CTRADER_CLIENT_SECRET not found in config")
        print("   Please set them in your .env file or config_live.env")
        return
    
    print(f"📋 Configuration:")
    print(f"   Server: demo.ctraderapi.com:5035")
    print(f"   Account ID: {account_id}")
    print(f"   Client ID: {client_id[:10]}..." if client_id else "   Client ID: Not set")
    print()
    
    # Create finder instance
    finder = CTraderIndicesFinder(access_token, account_id)
    
    try:
        # Connect
        if await finder.connect():
            # Get indices
            indices = await finder.get_indices()
            
            # Print results
            finder.print_indices_table(indices)
        else:
            print("❌ Failed to connect to cTrader")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await finder.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

