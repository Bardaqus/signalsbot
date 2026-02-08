"""
cTrader WebSocket client using websockets library (no Twisted dependency)
Provides simple async interface for getting gold prices from cTrader Open API
"""
import asyncio
import websockets
import ssl
import struct
from typing import Optional, Dict, Tuple
from datetime import datetime, timezone
import time

# Import protobuf modules
try:
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
    from ctrader_open_api.messages import OpenApiMessages_pb2 as OAMessages
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as OAModel
    _protobuf_modules = [OACommon, OAMessages, OAModel]
except ImportError:
    # Fallback to local protobuf
    try:
        import ctrader_service_pb2 as pb2
        _protobuf_modules = [pb2]
    except ImportError:
        raise ImportError("No protobuf modules available")

# Helper to find proto class
def _find_proto_class(class_name: str, modules: list) -> Optional[type]:
    """Find protobuf class across modules"""
    for module in modules:
        if hasattr(module, class_name):
            return getattr(module, class_name)
    return None

# Get required protobuf classes
ProtoOAApplicationAuthReq = _find_proto_class('ProtoOAApplicationAuthReq', _protobuf_modules)
ProtoOAApplicationAuthRes = _find_proto_class('ProtoOAApplicationAuthRes', _protobuf_modules)
ProtoOAAccountAuthReq = _find_proto_class('ProtoOAAccountAuthReq', _protobuf_modules)
ProtoOAAccountAuthRes = _find_proto_class('ProtoOAAccountAuthRes', _protobuf_modules)
ProtoOASymbolsListReq = _find_proto_class('ProtoOASymbolsListReq', _protobuf_modules)
ProtoOASymbolsListRes = _find_proto_class('ProtoOASymbolsListRes', _protobuf_modules)
ProtoOASubscribeSpotsReq = _find_proto_class('ProtoOASubscribeSpotsReq', _protobuf_modules)
ProtoOASubscribeSpotsRes = _find_proto_class('ProtoOASubscribeSpotsRes', _protobuf_modules)
ProtoOASpotEvent = _find_proto_class('ProtoOASpotEvent', _protobuf_modules)
ProtoMessage = _find_proto_class('ProtoMessage', _protobuf_modules)

if not all([ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes, ProtoOAAccountAuthReq, 
            ProtoOAAccountAuthRes, ProtoOASymbolsListReq, ProtoOASymbolsListRes,
            ProtoOASubscribeSpotsReq, ProtoOASpotEvent]):
    raise ImportError("Required protobuf classes not found")


class CTraderWebSocketError(Exception):
    """Exception for cTrader WebSocket errors"""
    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(f"{reason}: {message}")


class CTraderWebSocketClient:
    """Simple cTrader WebSocket client using websockets library"""
    
    # Hardcoded configuration (no .env)
    WS_URL = "wss://demo.ctraderapi.com:5035"
    CONNECT_TIMEOUT = 20.0
    AUTH_TIMEOUT = 10.0
    SYMBOL_RESOLVE_TIMEOUT = 10.0
    FIRST_TICK_TIMEOUT = 15.0
    
    def __init__(self, client_id: str, client_secret: str, access_token: str, account_id: int):
        """Initialize client with credentials"""
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = account_id
        
        self.websocket = None
        self.connected = False
        self.msg_id_counter = 0
        self.symbol_name_to_id: Dict[str, int] = {}
        self.quote_cache: Dict[str, Dict] = {}  # {symbol_name: {"bid": float, "ask": float, "timestamp": datetime}}
        self.pending_partial_ticks: Dict[str, Dict] = {}  # For merging partial ticks
        
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id_counter += 1
        return self.msg_id_counter
    
    def _create_proto_message(self, payload_type: str, payload_bytes: bytes, client_msg_id: Optional[int] = None) -> bytes:
        """Create ProtoMessage wrapper"""
        if client_msg_id is None:
            client_msg_id = self._get_next_msg_id()
        
        if ProtoMessage:
            msg = ProtoMessage()
            msg.payloadType = payload_type
            msg.clientMsgId = client_msg_id
            msg.payload = payload_bytes
            return msg.SerializeToString()
        else:
            # Fallback: simple binary format (if ProtoMessage not available)
            # Format: [payload_type_len:4][payload_type][client_msg_id:8][payload_len:4][payload]
            payload_type_bytes = payload_type.encode('utf-8')
            msg_bytes = struct.pack('>I', len(payload_type_bytes))
            msg_bytes += payload_type_bytes
            msg_bytes += struct.pack('>Q', client_msg_id)
            msg_bytes += struct.pack('>I', len(payload_bytes))
            msg_bytes += payload_bytes
            return msg_bytes
    
    def _parse_proto_message(self, data: bytes) -> Tuple[str, bytes, int]:
        """Parse ProtoMessage wrapper"""
        if ProtoMessage:
            msg = ProtoMessage()
            msg.ParseFromString(data)
            return (msg.payloadType, msg.payload, msg.clientMsgId)
        else:
            # Fallback parsing
            offset = 0
            payload_type_len = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            payload_type = data[offset:offset+payload_type_len].decode('utf-8')
            offset += payload_type_len
            client_msg_id = struct.unpack('>Q', data[offset:offset+8])[0]
            offset += 8
            payload_len = struct.unpack('>I', data[offset:offset+4])[0]
            offset += 4
            payload = data[offset:offset+payload_len]
            return (payload_type, payload, client_msg_id)
    
    async def connect(self):
        """Connect to cTrader WebSocket"""
        print(f"[CTRADER_WS] Connecting to {self.WS_URL}...")
        
        try:
            # Create SSL context (accept self-signed certs for demo)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.WS_URL, ssl=ssl_context),
                timeout=self.CONNECT_TIMEOUT
            )
            self.connected = True
            print(f"[CTRADER_WS] ✅ Connected to {self.WS_URL}")
            
        except asyncio.TimeoutError:
            raise CTraderWebSocketError("CONNECT_TIMEOUT", f"Connection timeout after {self.CONNECT_TIMEOUT}s")
        except Exception as e:
            raise CTraderWebSocketError("CONNECT_FAILED", f"Connection failed: {type(e).__name__}: {e}")
    
    async def _send_message(self, payload_type: str, payload_bytes: bytes, client_msg_id: Optional[int] = None) -> int:
        """Send protobuf message"""
        if not self.connected or not self.websocket:
            raise CTraderWebSocketError("NOT_CONNECTED", "WebSocket not connected")
        
        msg_id = client_msg_id if client_msg_id is not None else self._get_next_msg_id()
        msg_bytes = self._create_proto_message(payload_type, payload_bytes, msg_id)
        
        await self.websocket.send(msg_bytes)
        return msg_id
    
    async def _receive_message(self, timeout: float) -> Tuple[str, bytes, int]:
        """Receive and parse protobuf message"""
        if not self.connected or not self.websocket:
            raise CTraderWebSocketError("NOT_CONNECTED", "WebSocket not connected")
        
        try:
            data = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            return self._parse_proto_message(data)
        except asyncio.TimeoutError:
            raise CTraderWebSocketError("RECEIVE_TIMEOUT", f"Receive timeout after {timeout}s")
    
    async def authenticate(self):
        """Authenticate with cTrader (ApplicationAuth + AccountAuth)"""
        # Step 1: ApplicationAuth
        print("[CTRADER_WS] Step 1: ApplicationAuth...")
        app_auth_req = ProtoOAApplicationAuthReq()
        app_auth_req.clientId = self.client_id
        app_auth_req.clientSecret = self.client_secret
        
        # Get payload type name
        payload_type_name = ProtoOAApplicationAuthReq.DESCRIPTOR.full_name if hasattr(ProtoOAApplicationAuthReq, 'DESCRIPTOR') else "ProtoOAApplicationAuthReq"
        
        req_msg_id = await self._send_message(
            payload_type_name,
            app_auth_req.SerializeToString()
        )
        print(f"[CTRADER_WS] ✅ ApplicationAuth sent (msg_id={req_msg_id})")
        
        # Wait for response
        payload_type, payload, resp_msg_id = await self._receive_message(self.AUTH_TIMEOUT)
        
        expected_res_type = ProtoOAApplicationAuthRes.DESCRIPTOR.full_name if hasattr(ProtoOAApplicationAuthRes, 'DESCRIPTOR') else "ProtoOAApplicationAuthRes"
        if payload_type != expected_res_type:
            raise CTraderWebSocketError("AUTH_FAILED", f"Unexpected response: {payload_type} (expected {expected_res_type})")
        
        app_auth_res = ProtoOAApplicationAuthRes()
        app_auth_res.ParseFromString(payload)
        print(f"[CTRADER_WS] ✅ ApplicationAuth OK (account_id={app_auth_res.ctidTraderAccountId})")
        
        # Step 2: AccountAuth
        print("[CTRADER_WS] Step 2: AccountAuth...")
        acc_auth_req = ProtoOAAccountAuthReq()
        acc_auth_req.ctidTraderAccountId = self.account_id
        acc_auth_req.accessToken = self.access_token
        
        # Get payload type name
        payload_type_name = ProtoOAAccountAuthReq.DESCRIPTOR.full_name if hasattr(ProtoOAAccountAuthReq, 'DESCRIPTOR') else "ProtoOAAccountAuthReq"
        
        req_msg_id = await self._send_message(
            payload_type_name,
            acc_auth_req.SerializeToString()
        )
        print(f"[CTRADER_WS] ✅ AccountAuth sent (msg_id={req_msg_id})")
        
        # Wait for response
        payload_type, payload, resp_msg_id = await self._receive_message(self.AUTH_TIMEOUT)
        
        expected_res_type = ProtoOAAccountAuthRes.DESCRIPTOR.full_name if hasattr(ProtoOAAccountAuthRes, 'DESCRIPTOR') else "ProtoOAAccountAuthRes"
        if payload_type != expected_res_type:
            raise CTraderWebSocketError("ACCOUNT_AUTH_FAILED", f"Unexpected response: {payload_type} (expected {expected_res_type})")
        
        acc_auth_res = ProtoOAAccountAuthRes()
        acc_auth_res.ParseFromString(payload)
        print(f"[CTRADER_WS] ✅ AccountAuth OK (account_id={acc_auth_res.ctidTraderAccountId})")
    
    async def resolve_symbol(self, symbol_name: str) -> Optional[int]:
        """Resolve symbol name to symbol ID"""
        print(f"[CTRADER_WS] Resolving symbol: {symbol_name}...")
        
        # Request symbols list
        sym_list_req = ProtoOASymbolsListReq()
        payload_type_name = ProtoOASymbolsListReq.DESCRIPTOR.full_name if hasattr(ProtoOASymbolsListReq, 'DESCRIPTOR') else "ProtoOASymbolsListReq"
        
        req_msg_id = await self._send_message(
            payload_type_name,
            sym_list_req.SerializeToString()
        )
        
        # Wait for response
        payload_type, payload, resp_msg_id = await self._receive_message(self.SYMBOL_RESOLVE_TIMEOUT)
        
        expected_res_type = ProtoOASymbolsListRes.DESCRIPTOR.full_name if hasattr(ProtoOASymbolsListRes, 'DESCRIPTOR') else "ProtoOASymbolsListRes"
        if payload_type != expected_res_type:
            raise CTraderWebSocketError("SYMBOL_RESOLVE_FAILED", f"Unexpected response: {payload_type} (expected {expected_res_type})")
        
        sym_list_res = ProtoOASymbolsListRes()
        sym_list_res.ParseFromString(payload)
        
        # Build symbol map
        symbol_name_upper = symbol_name.upper()
        symbol_candidates = [
            symbol_name_upper,
            symbol_name_upper + ".",
            symbol_name_upper + "m",
            "GOLD",
            "XAU/USD",
        ]
        
        for sym in sym_list_res.symbol:
            sym_name_upper = sym.symbolName.upper()
            self.symbol_name_to_id[sym_name_upper] = sym.symbolId
            
            # Check if matches any candidate
            for candidate in symbol_candidates:
                if candidate in sym_name_upper or sym_name_upper in candidate:
                    print(f"[CTRADER_WS] ✅ Symbol resolved: {sym.symbolName} -> {sym.symbolId}")
                    return sym.symbolId
        
        # Not found
        print(f"[CTRADER_WS] ❌ Symbol not found: {symbol_name}")
        print(f"[CTRADER_WS] Available symbols (first 20): {list(self.symbol_name_to_id.keys())[:20]}")
        return None
    
    async def subscribe_spots(self, symbol_id: int):
        """Subscribe to spot events for symbol"""
        print(f"[CTRADER_WS] Subscribing to spots for symbol_id={symbol_id}...")
        
        sub_req = ProtoOASubscribeSpotsReq()
        if hasattr(sub_req, 'symbolId'):
            if hasattr(sub_req.symbolId, 'append'):
                sub_req.symbolId.append(symbol_id)
            else:
                sub_req.symbolId = [symbol_id]
        else:
            # Try alternative field name
            if hasattr(sub_req, 'symbolIds'):
                if hasattr(sub_req.symbolIds, 'append'):
                    sub_req.symbolIds.append(symbol_id)
                else:
                    sub_req.symbolIds = [symbol_id]
        
        payload_type_name = ProtoOASubscribeSpotsReq.DESCRIPTOR.full_name if hasattr(ProtoOASubscribeSpotsReq, 'DESCRIPTOR') else "ProtoOASubscribeSpotsReq"
        
        req_msg_id = await self._send_message(
            payload_type_name,
            sub_req.SerializeToString()
        )
        print(f"[CTRADER_WS] ✅ SubscribeSpots sent (msg_id={req_msg_id})")
    
    async def wait_for_first_tick(self, symbol_name: str, timeout: float = None) -> Tuple[float, float]:
        """Wait for first valid tick and return bid/ask"""
        if timeout is None:
            timeout = self.FIRST_TICK_TIMEOUT
        
        start_time = time.time()
        print(f"[CTRADER_WS] Waiting for first tick (timeout={timeout}s)...")
        
        while time.time() - start_time < timeout:
            try:
                payload_type, payload, msg_id = await self._receive_message(2.0)  # 2s per message
                
                expected_spot_type = ProtoOASpotEvent.DESCRIPTOR.full_name if hasattr(ProtoOASpotEvent, 'DESCRIPTOR') else "ProtoOASpotEvent"
                if payload_type == expected_spot_type:
                    spot_event = ProtoOASpotEvent()
                    spot_event.ParseFromString(payload)
                    
                    symbol_id = spot_event.symbolId
                    bid = spot_event.bid if hasattr(spot_event, 'bid') else 0.0
                    ask = spot_event.ask if hasattr(spot_event, 'ask') else 0.0
                    timestamp = spot_event.timestamp if hasattr(spot_event, 'timestamp') else 0
                    
                    # Handle partial ticks (merge within 2 seconds)
                    is_partial = (bid == 0.0 and ask > 0.0) or (bid > 0.0 and ask == 0.0)
                    
                    if is_partial:
                        # Merge with cached partial tick
                        cache_key = f"{symbol_id}"
                        if cache_key not in self.pending_partial_ticks:
                            self.pending_partial_ticks[cache_key] = {"bid": 0.0, "ask": 0.0, "timestamp": time.time()}
                        
                        if bid > 0.0:
                            self.pending_partial_ticks[cache_key]["bid"] = bid
                        if ask > 0.0:
                            self.pending_partial_ticks[cache_key]["ask"] = ask
                        
                        # Check if we have both bid and ask now
                        partial = self.pending_partial_ticks[cache_key]
                        if partial["bid"] > 0.0 and partial["ask"] > 0.0:
                            bid = partial["bid"]
                            ask = partial["ask"]
                            del self.pending_partial_ticks[cache_key]
                            print(f"[CTRADER_WS] ✅ Merged partial tick: bid={bid:.2f} ask={ask:.2f}")
                            return (bid, ask)
                        else:
                            print(f"[CTRADER_WS] Partial tick received: bid={bid:.2f} ask={ask:.2f} (waiting for merge)...")
                            continue
                    
                    # Full tick
                    if bid > 0.0 and ask > 0.0:
                        print(f"[CTRADER_WS] ✅ First tick received: bid={bid:.2f} ask={ask:.2f}")
                        return (bid, ask)
                    
            except CTraderWebSocketError as e:
                if e.reason == "RECEIVE_TIMEOUT":
                    continue  # Continue waiting
                else:
                    raise
        
        raise CTraderWebSocketError("FIRST_TICK_TIMEOUT", f"No tick received within {timeout}s")
    
    async def get_gold_price(self) -> Optional[float]:
        """Get current gold price (XAUUSD) from cTrader"""
        try:
            # Connect
            await self.connect()
            
            # Authenticate
            await self.authenticate()
            
            # Resolve symbol
            symbol_id = await self.resolve_symbol("XAUUSD")
            if not symbol_id:
                raise CTraderWebSocketError("SYMBOL_NOT_FOUND", "XAUUSD symbol not found")
            
            # Subscribe
            await self.subscribe_spots(symbol_id)
            
            # Wait for first tick
            bid, ask = await self.wait_for_first_tick("XAUUSD")
            
            # Calculate mid price
            mid_price = (bid + ask) / 2.0
            
            # Store in cache
            self.quote_cache["XAUUSD"] = {
                "bid": bid,
                "ask": ask,
                "mid": mid_price,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return mid_price
            
        except CTraderWebSocketError as e:
            print(f"[CTRADER_WS] ❌ Error: {e.reason}: {e.message}")
            return None
        except Exception as e:
            print(f"[CTRADER_WS] ❌ Unexpected error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            await self.close()
    
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            try:
                await self.websocket.close()
                print("[CTRADER_WS] Connection closed")
            except:
                pass
            self.websocket = None
            self.connected = False


# Global client instance
_gold_ws_client: Optional[CTraderWebSocketClient] = None
_gold_price_cache: Optional[float] = None
_gold_price_timestamp: Optional[datetime] = None


async def get_gold_price_async() -> Optional[float]:
    """Get gold price asynchronously (creates new connection each time)"""
    from config import Config
    ctrader_config = Config.get_ctrader_config()
    
    client = CTraderWebSocketClient(
        client_id=ctrader_config.client_id,
        client_secret=ctrader_config.client_secret,
        access_token=ctrader_config.access_token,
        account_id=ctrader_config.account_id
    )
    
    return await client.get_gold_price()


def get_gold_price_from_ctrader() -> Optional[float]:
    """Get gold price synchronously (wrapper for async function)"""
    global _gold_price_cache, _gold_price_timestamp
    
    # Check cache (valid for 5 seconds)
    if _gold_price_cache and _gold_price_timestamp:
        age = (datetime.now(timezone.utc) - _gold_price_timestamp).total_seconds()
        if age < 5.0:
            return _gold_price_cache
    
    # Get new price
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, get_gold_price_async())
                price = future.result(timeout=60.0)
        else:
            price = loop.run_until_complete(get_gold_price_async())
        
        if price:
            _gold_price_cache = price
            _gold_price_timestamp = datetime.now(timezone.utc)
        
        return price
    except Exception as e:
        print(f"[GOLD_PRICE] Error: {e}")
        return None
