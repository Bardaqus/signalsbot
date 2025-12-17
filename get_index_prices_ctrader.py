#!/usr/bin/env python3
"""
cTrader Index Prices Fetcher

This script connects to cTrader and fetches real-time prices for major indices
using the known ticker symbols.

Usage:
    python get_index_prices_ctrader.py
"""

import asyncio
import sys
from datetime import datetime
from config import Config

# Index tickers mapping
INDEX_TICKERS = {
    "S&P 500": "US500",
    "Nasdaq 100": "USTEC",
    "Dow Jones 30": "US30",
    "DAX 40": "DE40",
    "FTSE 100": "UK100",
    "CAC 40": "F40",
    "Nikkei 225": "JP225",
    "ASX 200": "AUS200",
    "Hang Seng": "HK50",
    "Euro Stoxx 50": "EU50",
}


def try_grpc_approach():
    """Try using gRPC approach"""
    try:
        import grpc
        import ctrader_service_pb2
        import ctrader_service_pb2_grpc
        return True, grpc, ctrader_service_pb2, ctrader_service_pb2_grpc
    except ImportError:
        return False, None, None, None


def try_websocket_approach():
    """Try using WebSocket approach"""
    try:
        from ctrader_open_api.client import Client
        from ctrader_open_api.factory import Factory
        from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
        return True, Client, Factory, OACommon
    except ImportError:
        return False, None, None, None


class CTraderIndexPriceFetcher:
    """Fetch index prices from cTrader"""
    
    def __init__(self, access_token: str, client_id: str, client_secret: str, account_id: int):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = account_id
        self.prices = {}
        self.symbol_ids = {}  # Map symbol name to symbol ID
        
    async def fetch_prices_grpc(self):
        """Fetch prices using gRPC"""
        grpc_available, grpc, pb2, pb2_grpc = try_grpc_approach()
        if not grpc_available:
            return False
        
        try:
            print("🔌 Connecting via gRPC...")
            channel = grpc.aio.secure_channel(
                "demo.ctraderapi.com:5035",
                grpc.ssl_channel_credentials()
            )
            stub = pb2_grpc.OpenApiServiceStub(channel)
            
            # Authenticate
            print("🔐 Authenticating...")
            auth_req = pb2.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            message = pb2.ProtoMessage(
                payloadType="ProtoOAApplicationAuthReq",
                clientMsgId=1,
                payload=auth_req.SerializeToString()
            )
            await stub.ProcessMessage(message)
            
            # Account auth
            acc_auth_req = pb2.ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.account_id,
                accessToken=self.access_token
            )
            message = pb2.ProtoMessage(
                payloadType="ProtoOAAccountAuthReq",
                clientMsgId=2,
                payload=acc_auth_req.SerializeToString()
            )
            await stub.ProcessMessage(message)
            
            print("✅ Authenticated via gRPC")
            print("⚠️  Note: gRPC approach may have connection issues")
            print("   Consider using WebSocket approach if this fails")
            
            await channel.close()
            return True
            
        except Exception as e:
            print(f"❌ gRPC approach failed: {e}")
            return False
    
    async def fetch_prices_websocket(self):
        """Fetch prices using WebSocket"""
        ws_available, Client, Factory, OACommon = try_websocket_approach()
        if not ws_available:
            print("❌ ctrader_open_api library not available")
            print("   Install it or use a different approach")
            return False
        
        try:
            print("🔌 Connecting via WebSocket...")
            
            # Parse WebSocket URL
            from urllib.parse import urlparse
            DEMO_WS = "wss://openapi.ctrader.com:5035"
            parsed = urlparse(DEMO_WS)
            host = parsed.hostname
            port = parsed.port or 5035
            protocol = 'wss' if parsed.scheme == 'wss' else 'ws'
            
            # Create client
            client = Client(host=host, port=port, protocol=protocol)
            factory = Factory(client=client)
            await client.connect()
            print("✅ Connected to WebSocket")
            
            # Application auth
            print("🔐 Authenticating application...")
            app_auth = OACommon.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            await client.send(app_auth)
            await asyncio.sleep(1)
            
            # Account auth
            print("🔐 Authenticating account...")
            acc_auth = OACommon.ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.account_id,
                accessToken=self.access_token
            )
            await client.send(acc_auth)
            await asyncio.sleep(1)
            
            # Request symbols list to get symbol IDs
            print("📈 Requesting symbols list...")
            sym_list_req = OACommon.ProtoOASymbolsListReq(
                ctidTraderAccountId=self.account_id
            )
            await client.send(sym_list_req)
            
            # Receive symbols and find our indices
            print("📊 Waiting for symbols list...")
            symbols_received = False
            timeout = 0
            max_timeout = 10
            
            async for pkt in client.packets():
                if pkt.payloadType == OACommon.ProtoOASymbolsListRes.DESCRIPTOR.full_name:
                    res = OACommon.ProtoOASymbolsListRes()
                    res.ParseFromString(pkt.payload)
                    
                    print(f"✅ Received {len(res.symbol)} symbols")
                    
                    # Find our index symbols
                    found_symbols = []
                    for symbol in res.symbol:
                        symbol_name = symbol.symbolName.upper()
                        for index_name, ticker in INDEX_TICKERS.items():
                            if symbol_name == ticker.upper():
                                self.symbol_ids[ticker] = symbol.symbolId
                                found_symbols.append((index_name, ticker, symbol.symbolId))
                                break
                    
                    if found_symbols:
                        print(f"\n✅ Found {len(found_symbols)} index symbols:")
                        for index_name, ticker, symbol_id in found_symbols:
                            print(f"   {index_name:20} → {ticker:10} (ID: {symbol_id})")
                    
                    symbols_received = True
                    break
                
                timeout += 1
                if timeout > max_timeout:
                    print("❌ Timeout waiting for symbols list")
                    break
            
            if not symbols_received:
                print("❌ Did not receive symbols list")
                return False
            
            # Subscribe to quotes for found symbols
            if self.symbol_ids:
                print(f"\n📡 Subscribing to {len(self.symbol_ids)} index symbols...")
                for ticker, symbol_id in self.symbol_ids.items():
                    try:
                        sub_req = OACommon.ProtoOASubscribeForSymbolQuotesReq(
                            ctidTraderAccountId=self.account_id,
                            symbolId=symbol_id,
                            subscribeToSpotTimestamp=True
                        )
                        await client.send(sub_req)
                        print(f"   ✅ Subscribed to {ticker}")
                    except Exception as e:
                        print(f"   ❌ Failed to subscribe to {ticker}: {e}")
                
                await asyncio.sleep(2)
                
                # Receive quotes
                print("\n💰 Waiting for price quotes (10 seconds)...")
                quote_timeout = 0
                max_quote_timeout = 10
                
                async for pkt in client.packets():
                    if pkt.payloadType == OACommon.ProtoOAQuoteMsg.DESCRIPTOR.full_name:
                        quote = OACommon.ProtoOAQuoteMsg()
                        quote.ParseFromString(pkt.payload)
                        
                        # Find which symbol this quote is for
                        for ticker, symbol_id in self.symbol_ids.items():
                            if symbol_id == quote.symbolId:
                                bid = quote.bid / 100000.0 if quote.bid > 1000 else quote.bid
                                ask = quote.ask / 100000.0 if quote.ask > 1000 else quote.ask
                                mid = (bid + ask) / 2
                                
                                self.prices[ticker] = {
                                    'bid': bid,
                                    'ask': ask,
                                    'mid': mid,
                                    'timestamp': quote.timestamp
                                }
                                break
                        
                        # If we have all prices, we can exit early
                        if len(self.prices) >= len(self.symbol_ids):
                            break
                    
                    quote_timeout += 1
                    if quote_timeout > max_quote_timeout * 10:  # Check every 0.1s
                        break
                    await asyncio.sleep(0.1)
            
            await client.disconnect()
            return True
            
        except Exception as e:
            print(f"❌ WebSocket approach failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def print_prices_table(self):
        """Print prices in a clean table"""
        if not self.prices:
            print("\n❌ No prices received")
            return
        
        print("\n" + "=" * 80)
        print("INDEX PRICES FROM cTRADER")
        print("=" * 80)
        print(f"{'Index Name':<20} | {'Ticker':<10} | {'Bid':<12} | {'Ask':<12} | {'Mid Price':<12}")
        print("-" * 80)
        
        for index_name, ticker in INDEX_TICKERS.items():
            if ticker in self.prices:
                price_data = self.prices[ticker]
                print(f"{index_name:<20} | {ticker:<10} | {price_data['bid']:<12.5f} | {price_data['ask']:<12.5f} | {price_data['mid']:<12.5f}")
            else:
                print(f"{index_name:<20} | {ticker:<10} | {'N/A':<12} | {'N/A':<12} | {'N/A':<12}")
        
        print("=" * 80)
        print(f"\n✅ Received prices for {len(self.prices)}/{len(INDEX_TICKERS)} indices")
        print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


async def main():
    """Main function"""
    print("=" * 80)
    print("cTRADER INDEX PRICES FETCHER")
    print("=" * 80)
    print("\nThis script will fetch real-time prices for major indices:")
    for index_name, ticker in INDEX_TICKERS.items():
        print(f"  • {index_name:20} → {ticker}")
    print()
    
    # Get credentials
    access_token = Config.CTRADER_ACCESS_TOKEN
    account_id = int(Config.DEMO_ACCOUNT_ID) if Config.DEMO_ACCOUNT_ID else None
    client_id = Config.CTRADER_CLIENT_ID
    client_secret = Config.CTRADER_CLIENT_SECRET
    
    if not all([access_token, account_id, client_id, client_secret]):
        print("❌ Missing credentials in config")
        print("   Required: CTRADER_ACCESS_TOKEN, DEMO_ACCOUNT_ID, CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET")
        return
    
    print(f"📋 Configuration:")
    print(f"   Account ID: {account_id}")
    print(f"   Client ID: {client_id[:10]}...")
    print()
    
    # Create fetcher
    fetcher = CTraderIndexPriceFetcher(access_token, client_id, client_secret, account_id)
    
    # Try WebSocket first (more reliable)
    print("🚀 Attempting WebSocket connection...")
    success = await fetcher.fetch_prices_websocket()
    
    if not success:
        print("\n⚠️  WebSocket failed, trying gRPC...")
        success = await fetcher.fetch_prices_grpc()
    
    if success and fetcher.prices:
        fetcher.print_prices_table()
    else:
        print("\n❌ Failed to fetch prices")
        print("   Check your credentials and network connection")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")

