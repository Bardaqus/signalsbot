"""
cTrader Async Client using websockets library (no Twisted dependency)
Unified client for FOREX + GOLD + INDEX prices from cTrader Open API
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


class CTraderAsyncError(Exception):
    """Exception for cTrader async client errors"""
    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(f"{reason}: {message}")


class CTraderAsyncClient:
    """Unified cTrader async client using websockets library (no Twisted)"""
    
    CONNECT_TIMEOUT = 20.0
    AUTH_TIMEOUT = 10.0
    SYMBOL_RESOLVE_TIMEOUT = 10.0
    
    def __init__(self, ws_url: str, client_id: str, client_secret: str, 
                 access_token: str, account_id: int, is_demo: bool = True):
        """Initialize client with hardcoded credentials"""
        self.ws_url = ws_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = account_id
        self.is_demo = is_demo
        
        self.websocket = None
        self.connected = False
        self.authenticated = False
        self.msg_id_counter = 0
        self.reader_task = None
        
        # Symbol management
        self.symbol_name_to_id: Dict[str, int] = {}
        self.symbol_id_to_name: Dict[int, str] = {}
        
        # Quote storage: {symbol_id: {"bid": float, "ask": float, "timestamp": datetime}}
        self.last_quotes: Dict[int, Dict] = {}
        
        # Response waiting: {msg_id: asyncio.Event}
        self.pending_responses: Dict[int, Tuple[asyncio.Event, Optional[str]]] = {}
        self.response_data: Dict[int, Tuple[str, bytes]] = {}  # {msg_id: (payload_type, payload)}
        
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id_counter += 1
        return self.msg_id_counter
    
    def _as_int(self, x, field_name: str, default: Optional[int] = None) -> int:
        """Normalize value to int for protobuf fields
        
        Args:
            x: Value to normalize (can be int, str, None, UUID, etc.)
            field_name: Field name for error messages
            default: Default value if x is None (if None, raises ValueError)
        
        Returns:
            int: Normalized integer value
        
        Raises:
            ValueError: If x cannot be normalized to int
        """
        # Handle None
        if x is None:
            if default is not None:
                return default
            raise ValueError(f"{field_name} cannot be None")
        
        # If already int, return as-is
        if isinstance(x, int):
            return x
        
        # If string, try to convert
        if isinstance(x, str):
            # Try numeric string
            if x.isdigit() or (x.startswith('-') and x[1:].isdigit()):
                return int(x)
            # Try UUID or other hashable types
            try:
                return hash(x) % (2**63)  # Convert hash to positive int64 range
            except Exception:
                raise ValueError(f"{field_name} cannot be converted to int: {x!r} (type={type(x).__name__})")
        
        # Try direct conversion
        try:
            return int(x)
        except (TypeError, ValueError) as e:
            # Try hash-based conversion for hashable types
            try:
                return hash(x) % (2**63)
            except Exception:
                raise ValueError(f"{field_name} cannot be converted to int: {x!r} (type={type(x).__name__}): {e}")
    
    def _get_payload_type_name(self, proto_class) -> str:
        """Get payload type name from protobuf class"""
        if hasattr(proto_class, 'DESCRIPTOR') and hasattr(proto_class.DESCRIPTOR, 'full_name'):
            return proto_class.DESCRIPTOR.full_name
        return proto_class.__name__
    
    def _normalize_payload_type(self, payload_type) -> int:
        """Normalize payload_type to int
        
        Args:
            payload_type: Can be int, str (numeric), or str (message name)
        
        Returns:
            int: Normalized payload type ID
        
        Raises:
            ValueError: If payload_type cannot be normalized
        """
        # If already int, return as-is
        if isinstance(payload_type, int):
            return payload_type
        
        # If string is numeric, convert to int
        if isinstance(payload_type, str):
            # Try to convert numeric string to int
            if payload_type.isdigit():
                return int(payload_type)
            
            # Try to find in mapping (message name -> payload type ID)
            # Note: cTrader Open API uses numeric payload type IDs
            # Common mappings (if using numeric IDs):
            payload_type_mapping = {
                # Application Auth
                "ProtoOAApplicationAuthReq": 2100,
                "spotware.ProtoOAApplicationAuthReq": 2100,
                "ProtoOAApplicationAuthRes": 2101,
                "spotware.ProtoOAApplicationAuthRes": 2101,
                # Account Auth
                "ProtoOAAccountAuthReq": 2102,
                "spotware.ProtoOAAccountAuthReq": 2102,
                "ProtoOAAccountAuthRes": 2103,
                "spotware.ProtoOAAccountAuthRes": 2103,
                # Symbols List
                "ProtoOASymbolsListReq": 2104,
                "spotware.ProtoOASymbolsListReq": 2104,
                "ProtoOASymbolsListRes": 2105,
                "spotware.ProtoOASymbolsListRes": 2105,
                # Subscribe Spots
                "ProtoOASubscribeSpotsReq": 2106,
                "spotware.ProtoOASubscribeSpotsReq": 2106,
                "ProtoOASubscribeSpotsRes": 2107,
                "spotware.ProtoOASubscribeSpotsRes": 2107,
                # Spot Event
                "ProtoOASpotEvent": 2131,
                "spotware.ProtoOASpotEvent": 2131,
            }
            
            if payload_type in payload_type_mapping:
                return payload_type_mapping[payload_type]
            
            # If not found in mapping, raise error with details
            raise ValueError(
                f"Unknown payload_type: {payload_type!r} (type={type(payload_type).__name__}). "
                f"Expected int or known message name. Available mappings: {list(payload_type_mapping.keys())[:5]}..."
            )
        
        # Unknown type
        raise ValueError(
            f"Invalid payload_type type: {type(payload_type).__name__}, value={payload_type!r}. "
            f"Expected int or str."
        )
    
    def _create_proto_message(self, payload_type, payload_bytes: bytes, client_msg_id: Optional[int] = None) -> bytes:
        """Create ProtoMessage wrapper
        
        Args:
            payload_type: Can be int, str (numeric), or str (message name)
            payload_bytes: Serialized protobuf payload
            client_msg_id: Optional message ID
        
        Returns:
            bytes: Serialized ProtoMessage
        """
        # Normalize client_msg_id to int (protobuf expects int64 for clientMsgId)
        if client_msg_id is None:
            client_msg_id = self._get_next_msg_id()
        
        client_msg_id_normalized = self._as_int(client_msg_id, "client_msg_id")
        
        # Normalize payload_type to int (protobuf expects int for payloadType)
        payload_type_normalized = self._normalize_payload_type(payload_type)
        
        # Debug log
        print(f"[CTRADER_ASYNC] _create_proto_message payload_type={payload_type_normalized} (original={payload_type!r}, type={type(payload_type).__name__}), client_msg_id={client_msg_id_normalized} (original={client_msg_id!r}, type={type(client_msg_id).__name__})")
        
        if ProtoMessage:
            msg = ProtoMessage()
            
            # DETAILED DEBUG: Log protobuf message structure
            print(f"[CTRADER_ASYNC] _create_proto_message DEBUG:")
            print(f"  ProtoMessage class: {ProtoMessage}")
            print(f"  msg instance type: {type(msg)}")
            if hasattr(msg, 'DESCRIPTOR'):
                print(f"  msg.DESCRIPTOR.full_name: {msg.DESCRIPTOR.full_name}")
                print(f"  msg.DESCRIPTOR.fields:")
                for field in msg.DESCRIPTOR.fields:
                    print(f"    - field.name='{field.name}', field.number={field.number}, field.type={field.type}, field.cpp_type={field.cpp_type}")
                    if field.name == 'clientMsgId':
                        print(f"      >>> clientMsgId field found: type={field.type}, cpp_type={field.cpp_type}")
            
            # Check if clientMsgId field exists and get its name
            client_msg_id_field_name = None
            if hasattr(msg, 'clientMsgId'):
                client_msg_id_field_name = 'clientMsgId'
            elif hasattr(msg, 'client_msg_id'):
                client_msg_id_field_name = 'client_msg_id'
            elif hasattr(msg, 'clientMsgId'):
                client_msg_id_field_name = 'clientMsgId'
            else:
                # Try to find by field number (2)
                if hasattr(msg, 'DESCRIPTOR'):
                    for field in msg.DESCRIPTOR.fields:
                        if field.number == 2:
                            client_msg_id_field_name = field.name
                            print(f"  Found clientMsgId field by number: '{field.name}'")
                            break
            
            if not client_msg_id_field_name:
                print(f"  WARNING: clientMsgId field not found in ProtoMessage!")
                print(f"  Available attributes: {[attr for attr in dir(msg) if not attr.startswith('_')]}")
            
            # Check if payloadType field exists
            payload_type_field_name = None
            if hasattr(msg, 'payloadType'):
                payload_type_field_name = 'payloadType'
            elif hasattr(msg, 'payload_type'):
                payload_type_field_name = 'payload_type'
            else:
                if hasattr(msg, 'DESCRIPTOR'):
                    for field in msg.DESCRIPTOR.fields:
                        if field.number == 1:
                            payload_type_field_name = field.name
                            break
            
            # Set payloadType
            if payload_type_field_name:
                try:
                    # Try int first (if protobuf expects numeric payload type)
                    setattr(msg, payload_type_field_name, payload_type_normalized)
                    print(f"  Set {payload_type_field_name}={payload_type_normalized} (int)")
                except (TypeError, ValueError) as e:
                    # If int fails, try string (fallback for string-based protobuf)
                    if isinstance(payload_type, str) and not payload_type.isdigit():
                        setattr(msg, payload_type_field_name, payload_type)
                        print(f"  Set {payload_type_field_name}={payload_type} (string)")
                    else:
                        raise ValueError(f"Cannot set {payload_type_field_name}: {e}, payload_type={payload_type!r}, normalized={payload_type_normalized}")
            else:
                print(f"  WARNING: payloadType field not found, skipping")
            
            # Set clientMsgId (check field type and convert accordingly)
            if client_msg_id_field_name:
                # Determine field type from DESCRIPTOR
                client_msg_id_field_type = None
                if hasattr(msg, 'DESCRIPTOR'):
                    for field in msg.DESCRIPTOR.fields:
                        if field.name == client_msg_id_field_name:
                            client_msg_id_field_type = field.type
                            print(f"  clientMsgId field type: {field.type} (TYPE_STRING=9, TYPE_INT64=3, TYPE_INT32=5)")
                            break
                
                try:
                    # TYPE_STRING = 9, TYPE_INT64 = 3, TYPE_INT32 = 5
                    if client_msg_id_field_type == 9:  # TYPE_STRING
                        # Convert int to string
                        client_msg_id_value = str(client_msg_id_normalized)
                        setattr(msg, client_msg_id_field_name, client_msg_id_value)
                        print(f"  Set {client_msg_id_field_name}={client_msg_id_value} (string, converted from int {client_msg_id_normalized})")
                    else:
                        # Use int directly for int64/int32
                        setattr(msg, client_msg_id_field_name, client_msg_id_normalized)
                        print(f"  Set {client_msg_id_field_name}={client_msg_id_normalized} (int, type={type(client_msg_id_normalized).__name__})")
                except (TypeError, ValueError) as e:
                    # Fallback: try string if int failed
                    try:
                        client_msg_id_value = str(client_msg_id_normalized)
                        setattr(msg, client_msg_id_field_name, client_msg_id_value)
                        print(f"  Set {client_msg_id_field_name}={client_msg_id_value} (string, fallback conversion)")
                    except Exception as e2:
                        print(f"  ERROR setting {client_msg_id_field_name}: {e} (int), {e2} (string)")
                        print(f"    client_msg_id_normalized={client_msg_id_normalized!r}, type={type(client_msg_id_normalized).__name__}")
                        print(f"    field_type={client_msg_id_field_type}")
                        raise ValueError(f"Cannot set {client_msg_id_field_name}: int failed ({e}), string failed ({e2}), client_msg_id_normalized={client_msg_id_normalized!r}")
            else:
                print(f"  WARNING: clientMsgId field not found, skipping (message may be invalid)")
            
            # Set payload
            if hasattr(msg, 'payload'):
                msg.payload = payload_bytes
                print(f"  Set payload={len(payload_bytes)} bytes")
            else:
                print(f"  WARNING: payload field not found")
            
            return msg.SerializeToString()
        else:
            # Fallback: simple binary format
            payload_type_bytes = payload_type.encode('utf-8')
            msg_bytes = struct.pack('>I', len(payload_type_bytes))
            msg_bytes += payload_type_bytes
            msg_bytes += struct.pack('>Q', client_msg_id_normalized)  # Use normalized int
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
        if self.connected:
            return
        
        print(f"[CTRADER_ASYNC] Connecting to {self.ws_url}...")
        
        try:
            # Create SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.ws_url, ssl=ssl_context, ping_interval=None),
                timeout=self.CONNECT_TIMEOUT
            )
            self.connected = True
            print(f"[CTRADER_ASYNC] ✅ Connected")
            
            # Start reader task
            self.reader_task = asyncio.create_task(self._reader_loop())
            
        except asyncio.TimeoutError:
            raise CTraderAsyncError("CONNECT_TIMEOUT", f"Connection timeout after {self.CONNECT_TIMEOUT}s")
        except Exception as e:
            raise CTraderAsyncError("CONNECT_FAILED", f"Connection failed: {type(e).__name__}: {e}")
    
    async def _reader_loop(self):
        """Background task to read messages from WebSocket"""
        try:
            while self.connected and self.websocket:
                try:
                    data = await self.websocket.recv()
                    payload_type, payload, msg_id = self._parse_proto_message(data)
                    
                    # Handle spot events
                    if payload_type == self._get_payload_type_name(ProtoOASpotEvent):
                        self._handle_spot_event(payload)
                    else:
                        # Store response for waiting requests
                        if msg_id in self.pending_responses:
                            event, expected_type = self.pending_responses[msg_id]
                            if expected_type is None or payload_type == expected_type:
                                self.response_data[msg_id] = (payload_type, payload)
                                event.set()
                except websockets.exceptions.ConnectionClosed:
                    print("[CTRADER_ASYNC] WebSocket connection closed")
                    self.connected = False
                    break
                except Exception as e:
                    print(f"[CTRADER_ASYNC] Reader loop error: {e}")
                    self.connected = False
                    break
        except Exception as e:
            print(f"[CTRADER_ASYNC] Reader loop fatal error: {e}")
            self.connected = False
    
    def _handle_spot_event(self, payload: bytes):
        """Handle ProtoOASpotEvent"""
        try:
            event = ProtoOASpotEvent()
            event.ParseFromString(payload)
            
            symbol_id = event.symbolId
            bid = event.bid / 1e5 if event.bid > 0 else None  # Convert from long to float
            ask = event.ask / 1e5 if event.ask > 0 else None
            
            if symbol_id not in self.last_quotes:
                self.last_quotes[symbol_id] = {}
            
            # Update bid/ask (handle partial ticks)
            if bid is not None:
                self.last_quotes[symbol_id]["bid"] = bid
            if ask is not None:
                self.last_quotes[symbol_id]["ask"] = ask
            
            self.last_quotes[symbol_id]["timestamp"] = datetime.now(timezone.utc)
            
            # Log for gold
            symbol_name = self.symbol_id_to_name.get(symbol_id, f"ID{symbol_id}")
            if "XAU" in symbol_name.upper() or "GOLD" in symbol_name.upper():
                print(f"[CTRADER_ASYNC] SpotEvent received for {symbol_name} bid={bid:.2f if bid else 'N/A'} ask={ask:.2f if ask else 'N/A'}")
                
        except Exception as e:
            print(f"[CTRADER_ASYNC] Error handling spot event: {e}")
    
    async def _send_message(self, payload_type, payload_bytes: bytes, client_msg_id: Optional[int] = None, wait_for_response: Optional[str] = None) -> Tuple[int, Optional[Tuple[str, bytes]]]:
        """Send protobuf message and optionally wait for response
        
        Args:
            payload_type: Can be int, str (numeric), or str (message name)
            payload_bytes: Serialized protobuf payload
            client_msg_id: Optional message ID
            wait_for_response: Optional expected response type name
        """
        if not self.connected or not self.websocket:
            raise CTraderAsyncError("NOT_CONNECTED", "WebSocket not connected")
        
        # Normalize msg_id to int (ensure it's always int)
        if client_msg_id is not None:
            msg_id = self._as_int(client_msg_id, "client_msg_id")
        else:
            msg_id = self._get_next_msg_id()
        
        # Ensure msg_id is int (double-check)
        assert isinstance(msg_id, int), f"msg_id must be int, got {type(msg_id).__name__}: {msg_id!r}"
        
        # Debug log before creating message
        print(f"[CTRADER_ASYNC] _send_message payload_type={payload_type!r} (type={type(payload_type).__name__}), msg_id={msg_id} (type={type(msg_id).__name__})")
        
        msg_bytes = self._create_proto_message(payload_type, payload_bytes, msg_id)
        
        # Set up response waiting if needed
        response_data = None
        if wait_for_response:
            event = asyncio.Event()
            self.pending_responses[msg_id] = (event, wait_for_response)
            await self.websocket.send(msg_bytes)
            
            try:
                await asyncio.wait_for(event.wait(), timeout=self.AUTH_TIMEOUT)
                response_data = self.response_data.pop(msg_id, None)
            except asyncio.TimeoutError:
                self.pending_responses.pop(msg_id, None)
                raise CTraderAsyncError("RESPONSE_TIMEOUT", f"Response timeout for {payload_type}")
            finally:
                self.pending_responses.pop(msg_id, None)
        else:
            await self.websocket.send(msg_bytes)
        
        return msg_id, response_data
    
    async def auth_application(self):
        """Send ApplicationAuth request"""
        print("[CTRADER_ASYNC] ApplicationAuth...")
        
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        
        payload_type = self._get_payload_type_name(ProtoOAApplicationAuthReq)
        expected_res_type = self._get_payload_type_name(ProtoOAApplicationAuthRes)
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("AUTH_FAILED", "No response to ApplicationAuth")
        
        res_payload_type, res_payload = response
        res = ProtoOAApplicationAuthRes()
        res.ParseFromString(res_payload)
        
        print(f"[CTRADER_ASYNC] ✅ ApplicationAuth OK (account_id={res.ctidTraderAccountId})")
    
    async def auth_account(self):
        """Send AccountAuth request"""
        print("[CTRADER_ASYNC] AccountAuth...")
        
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self.account_id
        req.accessToken = self.access_token
        
        payload_type = self._get_payload_type_name(ProtoOAAccountAuthReq)
        expected_res_type = self._get_payload_type_name(ProtoOAAccountAuthRes)
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("ACCOUNT_AUTH_FAILED", "No response to AccountAuth")
        
        res_payload_type, res_payload = response
        res = ProtoOAAccountAuthRes()
        res.ParseFromString(res_payload)
        
        self.authenticated = True
        print(f"[CTRADER_ASYNC] ✅ AccountAuth OK (account_id={res.ctidTraderAccountId})")
    
    async def ensure_symbol_id(self, symbol_name: str) -> Optional[int]:
        """Resolve symbol name to symbol ID with fallback candidates"""
        symbol_name_upper = symbol_name.upper()
        
        # Check cache first
        if symbol_name_upper in self.symbol_name_to_id:
            return self.symbol_name_to_id[symbol_name_upper]
        
        # Request symbols list
        print(f"[CTRADER_ASYNC] Resolving symbol: {symbol_name}...")
        
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self.account_id
        req.includeArchivedSymbols = False
        
        payload_type = self._get_payload_type_name(ProtoOASymbolsListReq)
        expected_res_type = self._get_payload_type_name(ProtoOASymbolsListRes)
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("SYMBOL_RESOLVE_FAILED", "No response to SymbolsListReq")
        
        res_payload_type, res_payload = response
        res = ProtoOASymbolsListRes()
        res.ParseFromString(res_payload)
        
        # Build symbol maps
        for sym in res.symbol:
            sym_name_upper = sym.symbolName.upper()
            self.symbol_name_to_id[sym_name_upper] = sym.symbolId
            self.symbol_id_to_name[sym.symbolId] = sym.symbolName
        
        # Try exact match first
        if symbol_name_upper in self.symbol_name_to_id:
            symbol_id = self.symbol_name_to_id[symbol_name_upper]
            print(f"[CTRADER_ASYNC] ✅ Symbol resolved: {symbol_name} -> {symbol_id}")
            return symbol_id
        
        # Try fallback candidates (for gold)
        if symbol_name_upper == "XAUUSD":
            candidates = ["XAUUSD", "XAUUSD.", "XAUUSDm", "XAUUSD.r", "XAU/USD", "GOLD"]
            for candidate in candidates:
                candidate_upper = candidate.upper()
                if candidate_upper in self.symbol_name_to_id:
                    symbol_id = self.symbol_name_to_id[candidate_upper]
                    print(f"[CTRADER_ASYNC] ✅ Symbol resolved via candidate: {candidate} -> {symbol_id}")
                    return symbol_id
            
            # Search by mask
            matches = []
            for sym_name, sym_id in self.symbol_name_to_id.items():
                if "XAU" in sym_name or "GOLD" in sym_name:
                    matches.append((sym_name, sym_id))
            
            if matches:
                print(f"[CTRADER_ASYNC] Found {len(matches)} potential gold symbols:")
                for sym_name, sym_id in matches[:10]:
                    print(f"   - {sym_name} (ID: {sym_id})")
                
                # Prefer XAUUSD variants
                for sym_name, sym_id in matches:
                    if "XAUUSD" in sym_name:
                        print(f"[CTRADER_ASYNC] ✅ Symbol resolved via mask: {sym_name} -> {sym_id}")
                        return sym_id
                
                # Fallback to first match
                sym_name, sym_id = matches[0]
                print(f"[CTRADER_ASYNC] ✅ Symbol resolved (first match): {sym_name} -> {sym_id}")
                return sym_id
        
        # Not found
        print(f"[CTRADER_ASYNC] ❌ Symbol not found: {symbol_name}")
        print(f"[CTRADER_ASYNC] Available symbols (first 20): {list(self.symbol_name_to_id.keys())[:20]}")
        return None
    
    async def subscribe_spot(self, symbol_id: int):
        """Subscribe to spot events for symbol"""
        print(f"[CTRADER_ASYNC] Subscribing to spots for symbol_id={symbol_id}...")
        
        req = ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        
        # Handle different field names
        if hasattr(req, 'symbolId'):
            if hasattr(req.symbolId, 'append'):
                req.symbolId.append(symbol_id)
            else:
                req.symbolId = [symbol_id]
        elif hasattr(req, 'symbolIds'):
            if hasattr(req.symbolIds, 'append'):
                req.symbolIds.append(symbol_id)
            else:
                req.symbolIds = [symbol_id]
        
        payload_type = self._get_payload_type_name(ProtoOASubscribeSpotsReq)
        
        msg_id, _ = await self._send_message(
            payload_type,
            req.SerializeToString()
        )
        
        print(f"[CTRADER_ASYNC] ✅ Subscribed spots for id={symbol_id}")
    
    def get_last_price(self, symbol_name: str) -> Optional[float]:
        """Get last mid price for symbol"""
        symbol_name_upper = symbol_name.upper()
        
        # Find symbol ID
        if symbol_name_upper not in self.symbol_name_to_id:
            return None
        
        symbol_id = self.symbol_name_to_id[symbol_name_upper]
        
        # Get quote
        if symbol_id not in self.last_quotes:
            return None
        
        quote = self.last_quotes[symbol_id]
        bid = quote.get("bid")
        ask = quote.get("ask")
        
        if bid is None or ask is None:
            return None
        
        return (bid + ask) / 2.0
    
    def get_last_quote(self, symbol_name: str) -> Optional[Dict]:
        """Get last quote (bid, ask, timestamp) for symbol"""
        symbol_name_upper = symbol_name.upper()
        
        if symbol_name_upper not in self.symbol_name_to_id:
            return None
        
        symbol_id = self.symbol_name_to_id[symbol_name_upper]
        
        if symbol_id not in self.last_quotes:
            return None
        
        quote = self.last_quotes[symbol_id].copy()
        return quote
    
    async def close(self):
        """Close WebSocket connection"""
        self.connected = False
        
        if self.reader_task:
            self.reader_task.cancel()
            try:
                await self.reader_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        print("[CTRADER_ASYNC] Connection closed")
