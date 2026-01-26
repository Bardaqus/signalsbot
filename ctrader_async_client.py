"""
cTrader Async Client using websockets library (no Twisted dependency)
Unified client for FOREX + GOLD + INDEX prices from cTrader Open API
"""
import asyncio
import websockets
import ssl
import struct
from typing import Optional, Dict, Tuple, Any
from datetime import datetime, timezone
import time
import aiohttp
import json
import os

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
ProtoOAGetAccountListByAccessTokenReq = _find_proto_class('ProtoOAGetAccountListByAccessTokenReq', _protobuf_modules)
ProtoOAGetAccountListByAccessTokenRes = _find_proto_class('ProtoOAGetAccountListByAccessTokenRes', _protobuf_modules)
ProtoOACtidTraderAccount = _find_proto_class('ProtoOACtidTraderAccount', _protobuf_modules)
ProtoOASymbolsListReq = _find_proto_class('ProtoOASymbolsListReq', _protobuf_modules)
ProtoOASymbolsListRes = _find_proto_class('ProtoOASymbolsListRes', _protobuf_modules)
ProtoOASubscribeSpotsReq = _find_proto_class('ProtoOASubscribeSpotsReq', _protobuf_modules)
ProtoOASubscribeSpotsRes = _find_proto_class('ProtoOASubscribeSpotsRes', _protobuf_modules)
ProtoOASpotEvent = _find_proto_class('ProtoOASpotEvent', _protobuf_modules)
ProtoOAErrorRes = _find_proto_class('ProtoOAErrorRes', _protobuf_modules)  # May not exist in all proto versions
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
    AUTH_TIMEOUT = 20.0  # Increased from 10s to 20s after correlation fix
    SYMBOL_RESOLVE_TIMEOUT = 10.0
    
    def __init__(self, ws_url: str, client_id: str, client_secret: str, 
                 access_token: str, account_id: int, is_demo: bool = True,
                 refresh_token: Optional[str] = None, token_url: Optional[str] = None):
        """Initialize client with credentials
        
        Args:
            ws_url: WebSocket URL
            client_id: cTrader client ID
            client_secret: cTrader client secret
            access_token: Current access token
            account_id: Account ID
            is_demo: True for demo, False for live
            refresh_token: Refresh token for token refresh (optional)
            token_url: OAuth token endpoint URL (optional, defaults to standard cTrader endpoint)
        """
        self.ws_url = ws_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.account_id = account_id
        self.is_demo = is_demo
        
        # OAuth token endpoint base URL - official cTrader Open API endpoint
        # Official endpoint: https://openapi.ctrader.com/apps/token (GET with query params)
        # Format: GET https://openapi.ctrader.com/apps/token?grant_type=refresh_token&refresh_token=...&client_id=...&client_secret=...
        self.token_url_base = token_url or "https://openapi.ctrader.com"
        
        # OAuth timeout (seconds)
        self.oauth_timeout = int(os.getenv('CTRADER_OAUTH_TIMEOUT', '10'))
        
        # Flag to control writing tokens to .env on refresh
        # Check both CTRADER_PERSIST_TOKENS and SAVE_TOKENS_TO_ENV for compatibility
        persist_env = os.getenv('CTRADER_PERSIST_TOKENS', '') or os.getenv('SAVE_TOKENS_TO_ENV', '')
        self.persist_tokens = persist_env.lower() in ('true', '1', 'yes')
        
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
        
        # Response waiting: {msg_id: (event, expected_payload_type_int)}
        # expected_payload_type_int is Optional[int] - numeric payload type ID, or None to accept any
        self.pending_responses: Dict[int, Tuple[asyncio.Event, Optional[int]]] = {}
        self.response_data: Dict[int, Tuple[int, bytes]] = {}  # {msg_id: (payload_type_int, payload)}
        
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
                # Get Account List By Access Token
                "ProtoOAGetAccountListByAccessTokenReq": 2108,
                "spotware.ProtoOAGetAccountListByAccessTokenReq": 2108,
                "ProtoOAGetAccountListByAccessTokenRes": 2109,
                "spotware.ProtoOAGetAccountListByAccessTokenRes": 2109,
                # Spot Event
                "ProtoOASpotEvent": 2131,
                "spotware.ProtoOASpotEvent": 2131,
                # Error Response
                "ProtoOAErrorRes": 2142,
                "spotware.ProtoOAErrorRes": 2142,
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
            # CRITICAL: ProtoMessage is required - no fallback framing allowed
            raise CTraderAsyncError(
                "PROTOBUF_MISSING",
                f"ProtoMessage class not found. Cannot create message without protobuf envelope. "
                f"payload_type={payload_type}, msg_id={client_msg_id_normalized}"
            )
    
    def _parse_proto_message(self, data: bytes) -> Tuple[int, bytes, int]:
        """Parse ProtoMessage wrapper
        
        Returns:
            Tuple of (payload_type_int, payload_bytes, msg_id_int)
            All values are normalized to int (msg_id always int, payload_type converted from string if needed)
        """
        if ProtoMessage:
            msg = ProtoMessage()
            msg.ParseFromString(data)
            
            # Normalize payloadType: if string, convert to int using mapping
            payload_type_raw = msg.payloadType
            if isinstance(payload_type_raw, str):
                # Try to convert numeric string to int
                if payload_type_raw.isdigit():
                    payload_type_int = int(payload_type_raw)
                else:
                    # Convert message name to numeric ID
                    payload_type_int = self._normalize_payload_type(payload_type_raw)
            else:
                payload_type_int = int(payload_type_raw)
            
            # Normalize clientMsgId: ProtoMessage.clientMsgId is TYPE_STRING (9) in our pb2
            # So it comes as string, but we need int for correlation
            msg_id_raw = msg.clientMsgId
            if isinstance(msg_id_raw, str):
                # String digits -> int
                if msg_id_raw.isdigit() or (msg_id_raw.startswith('-') and msg_id_raw[1:].isdigit()):
                    msg_id_int = int(msg_id_raw)
                else:
                    # Non-numeric string -> hash to int
                    msg_id_int = hash(msg_id_raw) % (2**63)
            elif isinstance(msg_id_raw, bytes):
                # Bytes -> decode and convert
                try:
                    msg_id_str = msg_id_raw.decode('utf-8')
                    if msg_id_str.isdigit():
                        msg_id_int = int(msg_id_str)
                    else:
                        msg_id_int = hash(msg_id_str) % (2**63)
                except:
                    msg_id_int = hash(msg_id_raw) % (2**63)
            else:
                # Already int or can be converted
                msg_id_int = self._as_int(msg_id_raw, "clientMsgId")
            
            print(f"[CTRADER_ASYNC] _parse_proto_message: payload_type_raw={payload_type_raw!r} -> payload_type_int={payload_type_int}, msg_id_raw={msg_id_raw!r} (type={type(msg_id_raw).__name__}) -> msg_id_int={msg_id_int}")
            
            return (payload_type_int, msg.payload, msg_id_int)
        else:
            # CRITICAL: ProtoMessage is required - no fallback parsing allowed
            raise CTraderAsyncError(
                "PROTOBUF_MISSING",
                f"ProtoMessage class not found. Cannot parse message without protobuf envelope. "
                f"data_length={len(data)}"
            )
    
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
                    payload_type_int, payload, msg_id_int = self._parse_proto_message(data)
                    
                    # Handle spot events (numeric ID: 2131)
                    spot_event_type_id = self._normalize_payload_type("ProtoOASpotEvent")
                    if payload_type_int == spot_event_type_id:
                        self._handle_spot_event(payload)
                        continue
                    
                    # Handle error responses (payloadType 2142 or other error codes)
                    # Common error payloadType: 2142 (ProtoOAErrorRes)
                    ERROR_PAYLOAD_TYPE = 2142
                    if payload_type_int == ERROR_PAYLOAD_TYPE:
                        # Try to parse as error message
                        error_info = self._parse_error_response(payload)
                        print(f"[CTRADER_ASYNC] [ERROR_RESPONSE] msg_id={msg_id_int}, payload_type={payload_type_int}, error_info={error_info}")
                        
                        # If this error is for a pending request, complete it (so caller can handle the error)
                        if msg_id_int in self.pending_responses:
                            event, expected_type_int = self.pending_responses[msg_id_int]
                            print(f"[CTRADER_ASYNC] [ERROR_FOR_PENDING] msg_id={msg_id_int}, expected={expected_type_int}, error={error_info}")
                            # Store error response so caller can check payload_type_int == 2142
                            self.response_data[msg_id_int] = (payload_type_int, payload)
                            event.set()
                        continue
                    
                    # Store response for waiting requests
                    # Match by msg_id_int and payload_type_int (both are int now)
                    if msg_id_int in self.pending_responses:
                        event, expected_type_int = self.pending_responses[msg_id_int]
                        # expected_type_int is Optional[int] - None means accept any, otherwise must match
                        if expected_type_int is None or payload_type_int == expected_type_int:
                            print(f"[CTRADER_ASYNC] [RESPONSE_MATCHED] msg_id={msg_id_int}, payload_type={payload_type_int}, expected={expected_type_int}")
                            self.response_data[msg_id_int] = (payload_type_int, payload)
                            event.set()
                        else:
                            print(f"[CTRADER_ASYNC] [RESPONSE_MISMATCH] msg_id={msg_id_int}, payload_type={payload_type_int}, expected={expected_type_int}")
                    else:
                        print(f"[CTRADER_ASYNC] [UNEXPECTED_RESPONSE] msg_id={msg_id_int}, payload_type={payload_type_int} (not in pending_responses)")
                except websockets.exceptions.ConnectionClosed:
                    print("[CTRADER_ASYNC] WebSocket connection closed")
                    self.connected = False
                    break
                except Exception as e:
                    print(f"[CTRADER_ASYNC] Reader loop error: {e}")
                    import traceback
                    print(traceback.format_exc())
                    self.connected = False
                    break
        except Exception as e:
            print(f"[CTRADER_ASYNC] Reader loop fatal error: {e}")
            import traceback
            print(traceback.format_exc())
            self.connected = False
    
    def _parse_error_response(self, payload: bytes) -> Dict[str, Any]:
        """Parse error response payload and extract error information
        
        Returns:
            Dict with errorCode, description, and other fields if available
        """
        error_info = {"raw_payload_length": len(payload)}
        
        # Try to find ProtoOAErrorRes class
        ProtoOAErrorRes = _find_proto_class('ProtoOAErrorRes', _protobuf_modules)
        if ProtoOAErrorRes:
            try:
                error_msg = ProtoOAErrorRes()
                error_msg.ParseFromString(payload)
                
                # Extract all available fields
                if hasattr(error_msg, 'DESCRIPTOR'):
                    for field in error_msg.DESCRIPTOR.fields:
                        field_name = field.name
                        if hasattr(error_msg, field_name):
                            try:
                                error_info[field_name] = getattr(error_msg, field_name)
                            except:
                                pass
            except Exception as e:
                error_info["parse_error"] = f"{type(e).__name__}: {e}"
        else:
            # If ProtoOAErrorRes not found, try to parse as generic message
            # Common error fields: errorCode (int), description (string)
            try:
                # Try to decode as text (fallback)
                error_info["raw_payload_preview"] = payload[:100].hex() if len(payload) > 0 else "empty"
            except:
                pass
        
        return error_info
    
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
    
    async def _send_message(self, payload_type, payload_bytes: bytes, client_msg_id: Optional[int] = None, wait_for_response: Optional[int] = None) -> Tuple[int, Optional[Tuple[int, bytes]]]:
        """Send protobuf message and optionally wait for response
        
        Args:
            payload_type: Can be int, str (numeric), or str (message name)
            payload_bytes: Serialized protobuf payload
            client_msg_id: Optional message ID
            wait_for_response: Optional expected response payloadType as int (numeric ID)
        
        Returns:
            Tuple of (msg_id_int, response_data) where response_data is (payload_type_int, payload_bytes) or None
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
        
        # Normalize wait_for_response to int if provided
        expected_type_int = None
        if wait_for_response is not None:
            if isinstance(wait_for_response, str):
                expected_type_int = self._normalize_payload_type(wait_for_response)
            else:
                expected_type_int = int(wait_for_response)
        
        # Debug log before creating message
        print(f"[CTRADER_ASYNC] [SEND_MESSAGE] payload_type={payload_type!r}, msg_id={msg_id}, wait_for_response={expected_type_int}")
        
        msg_bytes = self._create_proto_message(payload_type, payload_bytes, msg_id)
        
        # Set up response waiting if needed
        response_data = None
        if expected_type_int is not None:
            event = asyncio.Event()
            print(f"[CTRADER_ASYNC] [PENDING_ADD] msg_id={msg_id}, expected_type={expected_type_int}")
            self.pending_responses[msg_id] = (event, expected_type_int)
            await self.websocket.send(msg_bytes)
            
            try:
                await asyncio.wait_for(event.wait(), timeout=self.AUTH_TIMEOUT)
                response_data = self.response_data.pop(msg_id, None)
                if response_data:
                    res_payload_type_int, res_payload = response_data
                    # Error responses (2142) are valid responses - they match pending request
                    # Caller will check payload_type_int == 2142 and handle accordingly
                    print(f"[CTRADER_ASYNC] [PENDING_REMOVE] msg_id={msg_id}, response_received=True, payload_type={res_payload_type_int}")
                else:
                    print(f"[CTRADER_ASYNC] [PENDING_REMOVE] msg_id={msg_id}, response_received=False")
            except asyncio.TimeoutError:
                self.pending_responses.pop(msg_id, None)
                print(f"[CTRADER_ASYNC] [PENDING_TIMEOUT] msg_id={msg_id}, expected_type={expected_type_int}")
                raise CTraderAsyncError("RESPONSE_TIMEOUT", f"Response timeout for payload_type={payload_type}, msg_id={msg_id}")
            finally:
                self.pending_responses.pop(msg_id, None)
        else:
            await self.websocket.send(msg_bytes)
        
        return msg_id, response_data
    
    async def auth_application(self):
        """Send ApplicationAuth request"""
        print("[CTRADER_ASYNC] [AUTH_APP_START] Starting ApplicationAuth...")
        
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        
        # Use numeric payloadType IDs for matching
        payload_type = self._normalize_payload_type("ProtoOAApplicationAuthReq")  # 2100
        expected_res_type = self._normalize_payload_type("ProtoOAApplicationAuthRes")  # 2101
        
        print(f"[CTRADER_ASYNC] [AUTH_APP] payload_type={payload_type}, expected_res_type={expected_res_type}")
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("AUTH_FAILED", "No response to ApplicationAuth")
        
        res_payload_type_int, res_payload = response
        res = ProtoOAApplicationAuthRes()
        res.ParseFromString(res_payload)
        
        # Safely extract all fields using helper
        field_values = self._get_proto_fields_dict(res)
        account_id_from_res = field_values.get('ctidTraderAccountId')
        
        print(f"[CTRADER_ASYNC] [AUTH_APP_SUCCESS] ✅ ApplicationAuth OK (msg_id={msg_id})")
        if field_values:
            print(f"[CTRADER_ASYNC] [AUTH_APP_RESPONSE_FIELDS] {field_values}")
        if account_id_from_res:
            print(f"[CTRADER_ASYNC] [AUTH_APP_ACCOUNT_ID] {account_id_from_res}")
    
    async def get_account_list_by_access_token(self, retry_on_error: bool = True) -> Optional[list]:
        """Get account list using access token (official auth flow step 2)
        
        Args:
            retry_on_error: If True, attempt token refresh and retry on token errors
        
        Returns:
            List of account dicts with ctidTraderAccountId, isLive, etc., or None on error
        """
        if not ProtoOAGetAccountListByAccessTokenReq or not ProtoOAGetAccountListByAccessTokenRes:
            print("[CTRADER_ASYNC] [GET_ACCOUNTS] ❌ ProtoOAGetAccountListByAccessTokenReq/Res not available")
            return None
        
        print("[CTRADER_ASYNC] [GET_ACCOUNTS_START] Getting account list by access token...")
        print(f"[CTRADER_ASYNC] [GET_ACCOUNTS] access_token_preview={self._safe_preview(self.access_token, 6)}")
        
        req = ProtoOAGetAccountListByAccessTokenReq()
        req.accessToken = self.access_token
        
        # Use numeric payloadType IDs for matching
        payload_type = self._normalize_payload_type("ProtoOAGetAccountListByAccessTokenReq")
        expected_res_type = self._normalize_payload_type("ProtoOAGetAccountListByAccessTokenRes")
        
        print(f"[CTRADER_ASYNC] [GET_ACCOUNTS] payload_type={payload_type}, expected_res_type={expected_res_type}")
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("GET_ACCOUNTS_FAILED", "No response to GetAccountListByAccessToken")
        
        res_payload_type_int, res_payload = response
        
        # Check if we got an error response (2142) instead of success
        ERROR_PAYLOAD_TYPE = 2142
        if res_payload_type_int == ERROR_PAYLOAD_TYPE:
            error_info = self._parse_error_response(res_payload)
            error_code = error_info.get("errorCode", "UNKNOWN")
            error_description = error_info.get("description", error_info.get("message", "No description"))
            
            # Check if it's a token error that can be fixed by refresh
            token_errors = ["CH_ACCESS_TOKEN_INVALID", "CH_ACCESS_TOKEN_EXPIRED", "INVALID_ACCESS_TOKEN", "EXPIRED_ACCESS_TOKEN"]
            is_token_error = any(err in str(error_code).upper() or err in str(error_description).upper() for err in token_errors)
            
            if is_token_error and retry_on_error and self.refresh_token:
                print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_ERROR] ❌ Token error detected: errorCode={error_code}")
                print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_ERROR] Attempting token refresh and retry...")
                
                # Try to refresh token
                refresh_success = await self.refresh_access_token()
                if refresh_success:
                    print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_RETRY] Retrying GetAccountListByAccessToken with new token...")
                    # Retry once with new token
                    return await self.get_account_list_by_access_token(retry_on_error=False)
                else:
                    print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_ERROR] ❌ Token refresh failed, cannot retry")
                    raise CTraderAsyncError("GET_ACCOUNTS_FAILED", f"Token error: {error_code}, refresh failed")
            else:
                error_msg = f"GetAccountListByAccessToken failed with errorCode={error_code}, description={error_description}"
                print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_ERROR] ❌ {error_msg}")
                raise CTraderAsyncError("GET_ACCOUNTS_FAILED", error_msg)
        
        # Parse success response
        if res_payload_type_int != expected_res_type:
            raise CTraderAsyncError(
                "GET_ACCOUNTS_FAILED",
                f"Unexpected response type: got {res_payload_type_int}, expected {expected_res_type}"
            )
        
        res = ProtoOAGetAccountListByAccessTokenRes()
        res.ParseFromString(res_payload)
        
        # Extract account list
        accounts = []
        if hasattr(res, 'ctidTraderAccount') and res.ctidTraderAccount:
            for account in res.ctidTraderAccount:
                account_dict = self._get_proto_fields_dict(account)
                accounts.append(account_dict)
        
        print(f"[CTRADER_ASYNC] [GET_ACCOUNTS_SUCCESS] ✅ Found {len(accounts)} account(s)")
        for acc in accounts:
            acc_id = acc.get('ctidTraderAccountId', 'N/A')
            is_live = acc.get('isLive', False)
            broker = acc.get('brokerName', 'N/A')
            print(f"[CTRADER_ASYNC] [GET_ACCOUNTS]   Account {acc_id}: {broker} ({'Live' if is_live else 'Demo'})")
        
        return accounts
    
    async def refresh_access_token(self) -> bool:
        """Refresh access token using refresh_token via official cTrader Open API endpoint
        
        Uses POST request to: https://openapi.ctrader.com/apps/token
        Form data: grant_type=refresh_token&refresh_token=...&client_id=...&client_secret=...
        
        Returns:
            True if refresh successful, False otherwise
        """
        if not self.refresh_token:
            print("[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ No refresh_token available")
            return False
        
        # Build official endpoint URL
        token_endpoint = f"{self.token_url_base}/apps/token"
        
        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Starting token refresh...")
        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Using endpoint: {token_endpoint}")
        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Refresh token preview: {self._safe_preview(self.refresh_token, 5)}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use form-urlencoded format (standard OAuth2 refresh token flow)
                form_data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                }
                
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Accept': 'application/json'
                }
                
                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Sending POST request to: {token_endpoint}")
                async with session.post(
                    token_endpoint,
                    data=form_data,  # aiohttp will encode form data
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.oauth_timeout)
                ) as resp:
                    response_text = await resp.text()
                    
                    if resp.status == 200:
                        try:
                            result = await resp.json()
                            
                            # Check for errorCode in response (cTrader API may return errorCode even with 200)
                            error_code = result.get('errorCode')
                            if error_code:
                                error_description = result.get('description', result.get('message', 'No description'))
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ API returned error: errorCode={error_code}, description={error_description}")
                                return False
                            
                            # Parse response fields (cTrader uses camelCase: accessToken, refreshToken, expiresIn, tokenType)
                            new_access_token = result.get('accessToken') or result.get('access_token')
                            new_refresh_token = result.get('refreshToken') or result.get('refresh_token')
                            expires_in = result.get('expiresIn') or result.get('expires_in')
                            token_type = result.get('tokenType') or result.get('token_type', 'Bearer')
                            
                            if new_access_token:
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ✅ Token refreshed successfully")
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Access token preview: {self._safe_preview(new_access_token, 4)}")
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Token type: {token_type}")
                                if expires_in:
                                    print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Expires in: {expires_in} seconds ({expires_in // 3600:.1f} hours)")
                                
                                # Update tokens in memory
                                self.access_token = new_access_token
                                if new_refresh_token:
                                    self.refresh_token = new_refresh_token
                                    print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Refresh token also updated")
                                
                                # Optionally persist tokens if flag is set
                                if self.persist_tokens:
                                    self._persist_tokens(new_access_token, new_refresh_token)
                                
                                return True
                            else:
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ No accessToken/access_token in response JSON")
                                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Response preview: {response_text[:200]}")
                                return False
                        except json.JSONDecodeError as e:
                            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ Invalid JSON response: {e}")
                            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Response preview: {response_text[:200]}")
                            return False
                    else:
                        # Non-200 status
                        error_preview = response_text[:200] if len(response_text) > 200 else response_text
                        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ HTTP {resp.status} from {token_endpoint}")
                        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Response preview: {error_preview}")
                        
                        # Try to parse error JSON if available
                        try:
                            error_json = await resp.json()
                            error_code = error_json.get('errorCode')
                            error_description = error_json.get('description', error_json.get('message', 'No description'))
                            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] Error details: errorCode={error_code}, description={error_description}")
                        except:
                            pass
                        
                        return False
        except aiohttp.ClientError as e:
            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ Network error: {type(e).__name__}: {e}")
            return False
        except Exception as e:
            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ❌ Error: {type(e).__name__}: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def _persist_tokens(self, access_token: str, refresh_token: Optional[str] = None):
        """Persist tokens to file (tokens.json or .env based on flag)"""
        try:
            # Try to write to tokens.json first (safer, doesn't modify .env)
            tokens_json_path = os.path.join(os.path.dirname(__file__), 'tokens.json')
            try:
                import json
                tokens_data = {
                    'CTRADER_ACCESS_TOKEN': access_token,
                    'CTRADER_REFRESH_TOKEN': refresh_token or self.refresh_token,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
                with open(tokens_json_path, 'w', encoding='utf-8') as f:
                    json.dump(tokens_data, f, indent=2)
                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ✅ Tokens saved to tokens.json")
            except Exception as json_err:
                print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ⚠️ Could not write tokens.json: {json_err}")
            
            # Also try .env if explicitly requested (persist_tokens flag must be True)
            if self.persist_tokens:
                env_path = os.path.join(os.path.dirname(__file__), '.env')
                if os.path.exists(env_path):
                    try:
                        # Read current .env
                        with open(env_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # Update tokens
                        updated = False
                        new_lines = []
                        for line in lines:
                            if line.startswith('CTRADER_ACCESS_TOKEN='):
                                new_lines.append(f'CTRADER_ACCESS_TOKEN={access_token}\n')
                                updated = True
                            elif refresh_token and line.startswith('CTRADER_REFRESH_TOKEN='):
                                new_lines.append(f'CTRADER_REFRESH_TOKEN={refresh_token}\n')
                                updated = True
                            else:
                                new_lines.append(line)
                        
                        # Add tokens if they don't exist
                        if not any(line.startswith('CTRADER_ACCESS_TOKEN=') for line in new_lines):
                            new_lines.append(f'CTRADER_ACCESS_TOKEN={access_token}\n')
                            updated = True
                        if refresh_token and not any(line.startswith('CTRADER_REFRESH_TOKEN=') for line in new_lines):
                            new_lines.append(f'CTRADER_REFRESH_TOKEN={refresh_token}\n')
                            updated = True
                        
                        # Write back
                        if updated:
                            with open(env_path, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ✅ Tokens also written to .env")
                    except Exception as env_err:
                        print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ⚠️ Could not update .env: {env_err}")
                else:
                    print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ⚠️ .env file not found, skipping .env update")
        except Exception as e:
            print(f"[CTRADER_ASYNC] [REFRESH_TOKEN] ⚠️ Error persisting tokens: {e}")
    
    def _safe_preview(self, value: str, length: int = 6) -> str:
        """Create safe preview of sensitive value"""
        if not value:
            return "(not set)"
        if len(value) <= length:
            return value[:length] + "..."
        return value[:length] + "..."
    
    def _get_proto_fields_dict(self, msg) -> Dict[str, Any]:
        """Safely extract all fields from protobuf message
        
        Args:
            msg: Protobuf message object
        
        Returns:
            Dict with field_name -> field_value for all existing fields
        """
        fields_dict = {}
        if hasattr(msg, 'DESCRIPTOR'):
            for field in msg.DESCRIPTOR.fields:
                field_name = field.name
                if hasattr(msg, field_name):
                    try:
                        field_value = getattr(msg, field_name)
                        fields_dict[field_name] = field_value
                    except (AttributeError, TypeError):
                        pass
        return fields_dict
    
    async def auth_account(self, retry_on_error: bool = True):
        """Send AccountAuth request with automatic token refresh on error
        
        Args:
            retry_on_error: If True, attempt token refresh and retry on token errors
        """
        print("[CTRADER_ASYNC] [AUTH_ACCOUNT_START] Starting AccountAuth...")
        print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT] is_demo={self.is_demo}, account_id={self.account_id}, access_token_preview={self._safe_preview(self.access_token, 6)}")
        
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self.account_id
        req.accessToken = self.access_token
        
        # Use numeric payloadType IDs for matching
        payload_type = self._normalize_payload_type("ProtoOAAccountAuthReq")  # 2102
        expected_res_type = self._normalize_payload_type("ProtoOAAccountAuthRes")  # 2103
        
        print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT] payload_type={payload_type}, expected_res_type={expected_res_type}")
        
        msg_id, response = await self._send_message(
            payload_type,
            req.SerializeToString(),
            wait_for_response=expected_res_type
        )
        
        if not response:
            raise CTraderAsyncError("ACCOUNT_AUTH_FAILED", "No response to AccountAuth")
        
        res_payload_type_int, res_payload = response
        
        # Check if we got an error response (2142) instead of success (2103)
        ERROR_PAYLOAD_TYPE = 2142
        if res_payload_type_int == ERROR_PAYLOAD_TYPE:
            error_info = self._parse_error_response(res_payload)
            error_code = error_info.get("errorCode", "UNKNOWN")
            error_description = error_info.get("description", error_info.get("message", "No description"))
            
            # Check if it's a token error that can be fixed by refresh
            token_errors = ["CH_ACCESS_TOKEN_INVALID", "CH_ACCESS_TOKEN_EXPIRED", "INVALID_ACCESS_TOKEN", "EXPIRED_ACCESS_TOKEN"]
            is_token_error = any(err in str(error_code).upper() or err in str(error_description).upper() for err in token_errors)
            
            if is_token_error and retry_on_error and self.refresh_token:
                print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] ❌ Token error detected: errorCode={error_code}")
                print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] Attempting token refresh and retry...")
                
                # Try to refresh token
                refresh_success = await self.refresh_access_token()
                if refresh_success:
                    print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_RETRY] Retrying AccountAuth with new token...")
                    # Retry once with new token
                    return await self.auth_account(retry_on_error=False)
                else:
                    print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] ❌ Token refresh failed, cannot retry")
                    raise CTraderAsyncError("ACCOUNT_AUTH_FAILED", f"Token error: {error_code}, refresh failed")
            else:
                error_msg = f"AccountAuth failed with errorCode={error_code}, description={error_description}"
                print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] ❌ {error_msg}")
                print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR_DETAILS] {error_info}")
                
                if is_token_error:
                    if not self.refresh_token:
                        print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] ⚠️ Token error but no refresh_token available")
                        print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ERROR] ⚠️ Please update CTRADER_ACCESS_TOKEN and CTRADER_REFRESH_TOKEN in .env")
                    raise CTraderAsyncError("TOKEN_INVALID", error_msg)
                else:
                    raise CTraderAsyncError("ACCOUNT_AUTH_FAILED", error_msg)
        
        # Parse success response
        if res_payload_type_int != expected_res_type:
            raise CTraderAsyncError(
                "ACCOUNT_AUTH_FAILED",
                f"Unexpected response type: got {res_payload_type_int}, expected {expected_res_type}"
            )
        
        res = ProtoOAAccountAuthRes()
        res.ParseFromString(res_payload)
        
        # Safely extract all fields using helper
        field_values = self._get_proto_fields_dict(res)
        account_id_from_res = field_values.get('ctidTraderAccountId')
        
        self.authenticated = True
        print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_SUCCESS] ✅ AccountAuth OK (msg_id={msg_id})")
        if field_values:
            print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_RESPONSE_FIELDS] {field_values}")
        if account_id_from_res:
            print(f"[CTRADER_ASYNC] [AUTH_ACCOUNT_ACCOUNT_ID] {account_id_from_res}")
    
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
        
        payload_type = self._normalize_payload_type("ProtoOASymbolsListReq")  # 2104
        expected_res_type = self._normalize_payload_type("ProtoOASymbolsListRes")  # 2105
        
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
        
        payload_type = self._normalize_payload_type("ProtoOASubscribeSpotsReq")  # 2106
        
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
