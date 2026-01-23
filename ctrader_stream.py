import asyncio
from typing import Callable, Dict, Optional, Tuple, Set
from collections import defaultdict
import time

# Try to import loguru, fallback to standard logging if not available
try:
    from loguru import logger
    _logger_backend = "loguru"
except ImportError:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger("ctrader_stream")
    _logger_backend = "logging"

# Twisted Deferred to asyncio adapter
try:
    from twisted.internet import defer
    from twisted.python.failure import Failure
    
    async def await_deferred(d):
        """
        Convert Twisted Deferred to asyncio awaitable.
        This allows using Twisted-based cTrader client in asyncio event loop.
        """
        if not isinstance(d, defer.Deferred):
            return d
        
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        
        def _cb(res):
            """Callback for successful Deferred result"""
            if not fut.done():
                fut.set_result(res)
            return res
        
        def _eb(err):
            """Errback for failed Deferred"""
            if isinstance(err, Failure):
                exc = err.value
            else:
                exc = err
            if not fut.done():
                fut.set_exception(exc)
            return err
        
        d.addCallbacks(_cb, _eb)
        
        try:
            return await fut
        except asyncio.CancelledError:
            try:
                d.cancel()
            except Exception:
                pass
            raise
    
except ImportError:
    # Fallback if Twisted not available (shouldn't happen, but be safe)
    async def await_deferred(d):
        return d

from ctrader_open_api.client import Client
from ctrader_open_api.factory import Factory

# Import protobuf modules - classes are split across different pb2 files
try:
    from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon
    from ctrader_open_api.messages import OpenApiMessages_pb2 as OAMessages
    from ctrader_open_api.messages import OpenApiModelMessages_pb2 as OAModel
except ImportError as e:
    import logging
    logging.error(f"[GOLD_CTRADER][PROTO] Failed to import protobuf modules: {e}")
    raise

# Helper function to find proto class across modules
def find_proto_class(class_name: str, modules: list) -> tuple:
    """
    Find a protobuf class across multiple modules.
    Returns (module, class) tuple or (None, None) if not found.
    """
    for module in modules:
        if hasattr(module, class_name):
            return (module, getattr(module, class_name))
    return (None, None)

# Diagnostic: Check for required classes
_required_classes = [
    'ProtoOAApplicationAuthReq',
    'ProtoOAApplicationAuthRes',
    'ProtoOAAccountAuthReq',
    'ProtoOAAccountAuthRes',
    'ProtoOASymbolsListReq',
    'ProtoOASymbolsListRes',
    'ProtoOASubscribeSpotsReq',  # For spot quotes subscription
    'ProtoOASubscribeSpotsRes',
    'ProtoOASpotEvent',  # For spot quote events
]

_missing_classes = []
_available_modules = [OACommon, OAMessages, OAModel]

for class_name in _required_classes:
    module, cls = find_proto_class(class_name, _available_modules)
    if cls is None:
        _missing_classes.append(class_name)
        # Log available candidates
        candidates = []
        for mod in _available_modules:
            mod_classes = [x for x in dir(mod) if 'ProtoOA' in x and (class_name.split('Req')[0] in x or class_name.split('Res')[0] in x)]
            if mod_classes:
                candidates.extend([f"{mod.__name__}.{c}" for c in mod_classes])
        if candidates:
            logger.warning(f"[GOLD_CTRADER][PROTO] Missing {class_name}. Available candidates: {candidates[:5]}")

if _missing_classes:
    logger.error(f"[GOLD_CTRADER][PROTO] Missing required protobuf classes: {_missing_classes}")
    logger.error(f"[GOLD_CTRADER][PROTO] Please check protobuf module versions or imports")

# LIVE_WS is now obtained from Config.get_ctrader_ws_url()
# This constant is kept for backward compatibility but should not be used
_DEPRECATED_LIVE_WS = "wss://openapi.ctrader.com:5035"


# Custom exceptions with reason codes
class CTraderStreamerError(Exception):
    """Base exception for cTrader streamer errors"""
    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        self.message = message
        super().__init__(f"{reason_code}: {message}")


class CTraderStreamer:
    def __init__(self, access_token: str = None, client_id: str = None, client_secret: str = None, account_id: int = None):
        """Initialize cTrader streamer
        
        Args:
            access_token: Access token (if None, will be loaded from config)
            client_id: Client ID (if None, will be loaded from config)
            client_secret: Client secret (if None, will be loaded from config)
            account_id: Account ID (if None, will be loaded from config)
        """
        # Get unified config
        from config import Config
        ctrader_config = Config.get_ctrader_config()
        
        # Use provided values or fallback to config
        self.access_token = access_token or ctrader_config.access_token
        self.client_id = client_id or ctrader_config.client_id
        self.client_secret = client_secret or ctrader_config.client_secret
        self.account_id = account_id or ctrader_config.account_id
        self.ctrader_config = ctrader_config
        
        self.client: Optional[Client] = None
        self.symbol_name_to_id: Dict[str, int] = {}
        self.subscription_status: Dict[str, str] = {}  # Track subscription status: "pending", "subscribed", "failed", "error"
        self.on_quote: Optional[Callable[[str, float, float, int], None]] = None
        
        # Message queue for await_response
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.recv_task: Optional[asyncio.Task] = None
        self.msg_id_counter = 0
        self.is_connected = False
        self.connection_endpoint = None

    def _get_next_msg_id(self) -> int:
        """Get next message ID for correlation"""
        self.msg_id_counter += 1
        return self.msg_id_counter

    async def await_response(self, payload_types: Set[str], correlation_id: Optional[int] = None, timeout_sec: float = 10.0) -> Tuple[str, bytes]:
        """
        Wait for a response message matching payload_types.
        Note: correlation_id is logged but not strictly enforced, as cTrader may not return it.
        Returns (payload_type, payload_bytes) or raises CTraderStreamerError on timeout.
        """
        start_time = time.time()
        last_log_time = start_time
        messages_received = 0
        
        while time.time() - start_time < timeout_sec:
            try:
                # Wait for message with short timeout to allow periodic logging
                try:
                    payload_type, payload, msg_corr_id = await asyncio.wait_for(
                        self.message_queue.get(), 
                        timeout=1.0
                    )
                    messages_received += 1
                except asyncio.TimeoutError:
                    # Log progress every 3 seconds
                    elapsed = time.time() - last_log_time
                    if elapsed >= 3.0:
                        remaining = timeout_sec - (time.time() - start_time)
                        logger.debug(f"[GOLD_CTRADER] Waiting for response {payload_types} (corr_id={correlation_id}), {remaining:.1f}s remaining, received {messages_received} messages so far...")
                        last_log_time = time.time()
                    continue
                
                # Check if this message matches payload_type (primary match)
                if payload_type in payload_types:
                    logger.info(f"[GOLD_CTRADER] RECV {payload_type} corr_id={msg_corr_id} status=OK (matched from {messages_received} messages)")
                    return (payload_type, payload)
                else:
                    # Not the message we're waiting for, log it and continue
                    if messages_received <= 3:
                        logger.debug(f"[GOLD_CTRADER] Received unexpected message: {payload_type} (waiting for {payload_types})")
                    # Don't put back - we've consumed it, continue waiting
                    
            except Exception as e:
                logger.error(f"[GOLD_CTRADER] Error in await_response: {e}")
                raise
        
        # Timeout
        elapsed = time.time() - start_time
        reason_code = "AUTH_TIMEOUT" if "ApplicationAuth" in str(payload_types) else "ACCOUNT_AUTH_TIMEOUT" if "AccountAuth" in str(payload_types) else "RESPONSE_TIMEOUT"
        error_msg = f"No incoming messages matching {payload_types} from cTrader for {elapsed:.1f} seconds. Received {messages_received} total messages."
        logger.error(f"[GOLD_CTRADER] {reason_code}: {error_msg}")
        logger.error(f"[GOLD_CTRADER] Endpoint: {self.connection_endpoint}")
        if messages_received == 0:
            logger.error(f"[GOLD_CTRADER] NO_INCOMING_MESSAGES: No messages received at all - connection may not be working")
        raise CTraderStreamerError(reason_code, error_msg)

    async def _recv_loop(self):
        """Receive and process messages, putting them in queue"""
        logger.info("[GOLD_CTRADER] Receive loop started")
        message_count = 0
        
        try:
            async for pkt in self.client.packets():
                try:
                    message_count += 1
                    payload_type = pkt.payloadType if hasattr(pkt, 'payloadType') else str(pkt)
                    payload = pkt.payload if hasattr(pkt, 'payload') else b''
                    client_msg_id = getattr(pkt, 'clientMsgId', None)
                    
                    # Log first few messages for debugging
                    if message_count <= 5:
                        logger.info(f"[GOLD_CTRADER] RECV message #{message_count}: payloadType={payload_type}, size={len(payload) if isinstance(payload, bytes) else 'N/A'}, corr_id={client_msg_id}")
                    
                    # Put message in queue for await_response
                    await self.message_queue.put((payload_type, payload, client_msg_id))
                    
                    # Also process for internal state updates
                    await self._process_message(payload_type, payload)
                    
                except Exception as e:
                    logger.error(f"[GOLD_CTRADER] Error processing packet: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Receive loop error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.is_connected = False

    async def _process_message(self, payload_type: str, payload: bytes):
        """Process message for internal state updates (symbols, subscriptions, quotes)"""
        try:
            # Find required classes for message handling
            _, ProtoOASymbolsListRes = find_proto_class('ProtoOASymbolsListRes', _available_modules)
            _, ProtoOASpotEvent = find_proto_class('ProtoOASpotEvent', _available_modules)
            _, ProtoOASubscribeSpotsRes = find_proto_class('ProtoOASubscribeSpotsRes', _available_modules)
            
            if ProtoOASymbolsListRes and payload_type == ProtoOASymbolsListRes.DESCRIPTOR.full_name:
                res = ProtoOASymbolsListRes()
                res.ParseFromString(payload)
                
                # Store all symbols
                for sym in res.symbol:
                    symbol_name_upper = sym.symbolName.upper()
                    self.symbol_name_to_id[symbol_name_upper] = sym.symbolId
                
                logger.info(f"[GOLD_CTRADER] Resolved {len(self.symbol_name_to_id)} total symbols")
                
            elif ProtoOASubscribeSpotsRes and payload_type == ProtoOASubscribeSpotsRes.DESCRIPTOR.full_name:
                res = ProtoOASubscribeSpotsRes()
                res.ParseFromString(payload)
                # Handle subscription response
                if hasattr(res, 'symbolId'):
                    symbol_ids = [res.symbolId] if isinstance(res.symbolId, int) else res.symbolId
                elif hasattr(res, 'symbolIds'):
                    symbol_ids = res.symbolIds
                else:
                    symbol_ids = []
                
                for symbol_id in symbol_ids:
                    symbol_name = None
                    for name, sid in self.symbol_name_to_id.items():
                        if sid == symbol_id:
                            symbol_name = name
                            break
                    if symbol_name:
                        if hasattr(res, 'errorCode') and res.errorCode:
                            logger.error(f"[GOLD_CTRADER] Subscription error for {symbol_name}: {res.errorCode}")
                            self.subscription_status[symbol_name.upper()] = "failed"
                        else:
                            logger.info(f"[GOLD_CTRADER] Subscription confirmed for {symbol_name}")
                            self.subscription_status[symbol_name.upper()] = "subscribed"
                            
            elif ProtoOASpotEvent and payload_type == ProtoOASpotEvent.DESCRIPTOR.full_name:
                spot_event = ProtoOASpotEvent()
                spot_event.ParseFromString(payload)
                
                symbol_id = spot_event.symbolId if hasattr(spot_event, 'symbolId') else None
                if not symbol_id:
                    return
                
                # Reverse map id -> name
                name = None
                for k, v in self.symbol_name_to_id.items():
                    if v == symbol_id:
                        name = k
                        if self.subscription_status.get(k) == "pending":
                            self.subscription_status[k] = "subscribed"
                            logger.info(f"[GOLD_CTRADER] First tick received for {k} - subscription confirmed")
                        break
                
                if name and self.on_quote:
                    bid = spot_event.bid if hasattr(spot_event, 'bid') else None
                    ask = spot_event.ask if hasattr(spot_event, 'ask') else None
                    timestamp = spot_event.timestamp if hasattr(spot_event, 'timestamp') else 0
                    
                    if bid is not None and ask is not None and bid > 0 and ask > 0:
                        # Log first valid tick
                        if self.subscription_status.get(name) != "receiving_quotes":
                            logger.info(f"[GOLD_CTRADER] First valid tick received bid={bid:.2f} ask={ask:.2f} for {name}")
                            self.subscription_status[name] = "receiving_quotes"
                        self.on_quote(name, bid, ask, timestamp)
                        
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Error in _process_message: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    async def start(self):
        """Start cTrader streamer with strict protocol sequence"""
        logger.info("[GOLD_CTRADER] Starting cTrader streamer...")
        
        # Get unified cTrader config (with safe defaults - never fails)
        try:
            from config import Config
            ctrader_config = Config.get_ctrader_config()
            ws_url, source_var = ctrader_config.get_ws_url()
            
            # Log startup configuration
            logger.info("=" * 80)
            logger.info("[GOLD_CTRADER] STARTUP CONFIGURATION")
            logger.info("=" * 80)
            logger.info(f"  is_demo: {ctrader_config.is_demo}")
            logger.info(f"  account_id: {ctrader_config.account_id}")
            logger.info(f"  ws_url: {ws_url} (source={source_var})")
            if hasattr(ctrader_config, 'gold_symbol_name_override') and ctrader_config.gold_symbol_name_override:
                logger.info(f"  gold_symbol_name_override: {ctrader_config.gold_symbol_name_override}")
            logger.info("=" * 80)
            
            # Store config for later use
            self.ctrader_config = ctrader_config
        except Exception as e:
            # Fallback to defaults if config fails (should never happen, but be safe)
            logger.error(f"[GOLD_CTRADER] Failed to get WS URL from config: {e}, using defaults")
            import traceback
            logger.error(traceback.format_exc())
            ws_url = "wss://demo.ctraderapi.com:5035"
            source_var = "fallback_default"
            logger.info(f"[GOLD_CTRADER] Using fallback WS endpoint={ws_url}")
        
        # Parse URL
        from urllib.parse import urlparse
        try:
            parsed = urlparse(ws_url)
            host = parsed.hostname
            port = parsed.port or 5035
            protocol = 'wss' if parsed.scheme == 'wss' else 'ws'
            self.connection_endpoint = f"{protocol}://{host}:{port}"
            
            logger.info(f"[GOLD_CTRADER] Parsed endpoint: host={host}, port={port}, protocol={protocol}")
            logger.info(f"[GOLD_CTRADER] Using endpoint={self.connection_endpoint}, Transport=WebSocket")
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to parse WS URL '{ws_url}': {e}")
            raise CTraderStreamerError("CONFIG_INVALID_WS_URL", f"Invalid WS URL format: {ws_url}")
        
        # Create client
        self.client = Client(host=host, port=port, protocol=protocol)
        factory = Factory(client=self.client)
        
        # Connection state
        connection_established = asyncio.Event()
        connection_error = None
        
        # WebSocket event callbacks with detailed logging
        def on_connected():
            """Callback when WebSocket connection is established (OPEN event)"""
            logger.info("[GOLD_CTRADER] [WS_EVENT] WebSocket OPEN - connection established")
            logger.info(f"[GOLD_CTRADER] [WS_EVENT] Transport: {protocol}://{host}:{port}")
            self.is_connected = True
            connection_established.set()
        
        def on_disconnected():
            """Callback when WebSocket is disconnected"""
            logger.warning("[GOLD_CTRADER] [WS_EVENT] WebSocket CLOSED - disconnected")
            self.is_connected = False
            connection_established.clear()
        
        # Set callbacks
        self.client.setConnectedCallback(on_connected)
        self.client.setDisconnectedCallback(on_disconnected)
        
        # Log WebSocket handshake start
        logger.info(f"[GOLD_CTRADER] [WS_EVENT] WebSocket handshake starting...")
        logger.info(f"[GOLD_CTRADER] [WS_EVENT] Protocol: {protocol}, Host: {host}, Port: {port}")
        
        # Start the service
        logger.info("[GOLD_CTRADER] Starting Twisted service...")
        self.client.startService()
        
        # TCP precheck before WebSocket connection
        import socket
        logger.info(f"[GOLD_CTRADER] [WS_EVENT] DNS resolution: {host}...")
        try:
            resolved_ip = socket.gethostbyname(host)
            logger.info(f"[GOLD_CTRADER] [WS_EVENT] DNS resolved: {host} -> {resolved_ip}")
        except socket.gaierror as dns_error:
            logger.error(f"[GOLD_CTRADER] [WS_EVENT] DNS resolution failed: {host} -> {dns_error}")
            raise CTraderStreamerError("WS_DNS_ERROR", f"DNS resolution failed for {host}: {dns_error}")
        
        # TCP precheck: try raw TCP connection
        logger.info(f"[GOLD_CTRADER] [WS_EVENT] TCP precheck: connecting to {host}:{port}...")
        try:
            tcp_socket = socket.create_connection((host, port), timeout=5)
            tcp_socket.close()
            logger.info(f"[GOLD_CTRADER] [WS_EVENT] TCP precheck OK: {host}:{port} is reachable")
        except socket.timeout:
            logger.error(f"[GOLD_CTRADER] [WS_EVENT] CTRADER_TCP_BLOCKED: TCP connection timeout to {host}:{port}")
            logger.error(f"   -> Possible causes: firewall blocking port {port}, proxy misconfiguration, or network issue")
            raise CTraderStreamerError("CTRADER_TCP_BLOCKED", f"TCP connection timeout to {host}:{port} - check firewall/proxy")
        except (socket.error, OSError) as tcp_error:
            logger.error(f"[GOLD_CTRADER] [WS_EVENT] CTRADER_TCP_BLOCKED: Cannot connect to {host}:{port}: {tcp_error}")
            logger.error(f"   -> Exception type: {type(tcp_error).__name__}")
            logger.error(f"   -> Possible causes: firewall blocking port {port}, proxy misconfiguration, or network issue")
            raise CTraderStreamerError("CTRADER_TCP_BLOCKED", f"Cannot connect to {host}:{port}: {tcp_error}")
        
        logger.info(f"[GOLD_CTRADER] [WS_EVENT] TLS handshake will start after WebSocket connection...")
        
        # Get connection timeout from config
        from config import Config
        connection_timeout = float(Config.CTRADER_WS_CONNECT_TIMEOUT)
        reconnect_attempts = Config.CTRADER_WS_RETRY_COUNT
        last_error = None
        
        # Backoff delays: 2s, 5s
        backoff_delays = [2, 5]
        
        for attempt in range(1, reconnect_attempts + 1):
            try:
                logger.info(f"[GOLD_CTRADER] WebSocket connection attempt {attempt}/{reconnect_attempts} to {host}:{port} (timeout={connection_timeout}s)...")
                
                await asyncio.wait_for(connection_established.wait(), timeout=connection_timeout)
                logger.info("[GOLD_CTRADER] WebSocket connection confirmed")
                break
                
            except asyncio.TimeoutError:
                last_error = f"WebSocket handshake timeout after {connection_timeout}s"
                logger.warning(f"[GOLD_CTRADER] Connection attempt {attempt} failed: {last_error}")
                
                if attempt < reconnect_attempts:
                    backoff = backoff_delays[min(attempt - 1, len(backoff_delays) - 1)]
                    logger.info(f"[GOLD_CTRADER] Retrying connection in {backoff} seconds...")
                    await asyncio.sleep(backoff)
                    # Reset connection event
                    connection_established.clear()
                    try:
                        self.client.stopService()
                    except:
                        pass
                    # Restart service
                    self.client.startService()
                else:
                    # Final attempt failed - detailed diagnostics
                    logger.error(f"[GOLD_CTRADER] CTRADER_WS_CONNECT_FAILED: All {reconnect_attempts} connection attempts failed")
                    logger.error(f"[GOLD_CTRADER] Endpoint: {self.connection_endpoint} (host={host}, port={port})")
                    logger.error(f"[GOLD_CTRADER] DNS: {host} -> {resolved_ip}")
                    logger.error(f"[GOLD_CTRADER] TCP precheck: PASSED (connection was reachable)")
                    logger.error(f"[GOLD_CTRADER] WebSocket handshake timeout: {connection_timeout}s per attempt")
                    logger.error(f"[GOLD_CTRADER] Protocol: {protocol}")
                    logger.error(f"[GOLD_CTRADER] Possible causes:")
                    logger.error(f"   - WebSocket handshake failed (TLS/SSL issue)")
                    logger.error(f"   - Proxy blocking WebSocket upgrade")
                    logger.error(f"   - Server not responding to WebSocket protocol")
                    logger.error("[GOLD_CTRADER] Closing connection and failing...")
                    import traceback
                    logger.error(f"[GOLD_CTRADER] Stacktrace:\n{traceback.format_exc()}")
                    try:
                        self.client.stopService()
                    except Exception as stop_error:
                        logger.error(f"[GOLD_CTRADER] Error stopping service: {stop_error}")
                    raise CTraderStreamerError(
                        "CTRADER_WS_CONNECT_FAILED", 
                        f"WebSocket handshake to {self.connection_endpoint} (host={host}, port={port}) timed out after {reconnect_attempts} attempts. TCP precheck passed, but WebSocket handshake failed."
                    )
            except Exception as e:
                last_error = str(e)
                logger.error(f"[GOLD_CTRADER] Connection attempt {attempt} error: {type(e).__name__}: {last_error}")
                if attempt < reconnect_attempts:
                    logger.info(f"[GOLD_CTRADER] Retrying connection in 2 seconds...")
                    await asyncio.sleep(2)
                    connection_established.clear()
                    try:
                        self.client.stopService()
                    except:
                        pass
                    self.client.startService()
                else:
                    raise CTraderStreamerError("WS_CONNECTION_ERROR", f"Connection failed: {type(e).__name__}: {last_error}")
        
        if not self.is_connected:
            raise CTraderStreamerError("WS_NOT_CONNECTED", "Connection callback fired but is_connected=False")
        
        # Start receive loop BEFORE sending any messages
        logger.info("[GOLD_CTRADER] Starting receive loop...")
        self.recv_task = asyncio.create_task(self._recv_loop())
        await asyncio.sleep(0.5)  # Give receive loop time to start
        
        # === STRICT PROTOCOL SEQUENCE ===
        
        # Step 1: Application Auth
        logger.info("[GOLD_CTRADER] Step 1: ApplicationAuth")
        app_auth_module, ProtoOAApplicationAuthReq = find_proto_class('ProtoOAApplicationAuthReq', _available_modules)
        if ProtoOAApplicationAuthReq is None:
            raise CTraderStreamerError("PROTO_CLASS_NOT_FOUND", "ProtoOAApplicationAuthReq not found")
        
        _, ProtoOAApplicationAuthRes = find_proto_class('ProtoOAApplicationAuthRes', _available_modules)
        if ProtoOAApplicationAuthRes is None:
            raise CTraderStreamerError("PROTO_CLASS_NOT_FOUND", "ProtoOAApplicationAuthRes not found")
        
        corr_id_1 = self._get_next_msg_id()
        app_auth = ProtoOAApplicationAuthReq(
            clientId=self.client_id,
            clientSecret=self.client_secret
        )
        
        logger.info(f"[GOLD_CTRADER] SENT ProtoOAApplicationAuthReq corr_id={corr_id_1}")
        try:
            await await_deferred(self.client.send(app_auth))
            logger.info(f"[GOLD_CTRADER] ApplicationAuth request sent successfully")
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to send ApplicationAuth: {e}")
            raise CTraderStreamerError("SEND_FAILED", f"Failed to send ApplicationAuth: {e}")
        
        # Wait for ApplicationAuthRes with timeout
        try:
            payload_type, payload = await self.await_response(
                {ProtoOAApplicationAuthRes.DESCRIPTOR.full_name},
                correlation_id=corr_id_1,
                timeout_sec=15.0
            )
            auth_res = ProtoOAApplicationAuthRes()
            auth_res.ParseFromString(payload)
            logger.info(f"[GOLD_CTRADER] ApplicationAuth response received, ctidTraderAccountId={getattr(auth_res, 'ctidTraderAccountId', 'N/A')}")
        except CTraderStreamerError as e:
            logger.error(f"[GOLD_CTRADER] ApplicationAuth failed: {e.reason_code}")
            raise
        
        # Step 2: Account Auth
        logger.info("[GOLD_CTRADER] Step 2: AccountAuth")
        _, ProtoOAAccountAuthReq = find_proto_class('ProtoOAAccountAuthReq', _available_modules)
        if ProtoOAAccountAuthReq is None:
            raise CTraderStreamerError("PROTO_CLASS_NOT_FOUND", "ProtoOAAccountAuthReq not found")
        
        _, ProtoOAAccountAuthRes = find_proto_class('ProtoOAAccountAuthRes', _available_modules)
        if ProtoOAAccountAuthRes is None:
            raise CTraderStreamerError("PROTO_CLASS_NOT_FOUND", "ProtoOAAccountAuthRes not found")
        
        corr_id_2 = self._get_next_msg_id()
        acc_auth = ProtoOAAccountAuthReq(
            ctidTraderAccountId=self.account_id,
            accessToken=self.access_token
        )
        
        logger.info(f"[GOLD_CTRADER] SENT ProtoOAAccountAuthReq corr_id={corr_id_2}")
        try:
            await await_deferred(self.client.send(acc_auth))
            logger.info(f"[GOLD_CTRADER] AccountAuth request sent successfully")
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to send AccountAuth: {e}")
            raise CTraderStreamerError("SEND_FAILED", f"Failed to send AccountAuth: {e}")
        
        # Wait for AccountAuthRes
        try:
            payload_type, payload = await self.await_response(
                {ProtoOAAccountAuthRes.DESCRIPTOR.full_name},
                correlation_id=corr_id_2,
                timeout_sec=15.0
            )
            acc_res = ProtoOAAccountAuthRes()
            acc_res.ParseFromString(payload)
            logger.info(f"[GOLD_CTRADER] AccountAuth response received, ctidTraderAccountId={getattr(acc_res, 'ctidTraderAccountId', 'N/A')}")
        except CTraderStreamerError as e:
            logger.error(f"[GOLD_CTRADER] AccountAuth failed: {e.reason_code}")
            raise CTraderStreamerError("ACCOUNT_AUTH_FAILED", str(e))
        
        # Step 3: Request symbols list and resolve gold symbol
        logger.info("[GOLD_CTRADER] Step 3: Request symbols list and resolve gold symbol")
        _, ProtoOASymbolsListReq = find_proto_class('ProtoOASymbolsListReq', _available_modules)
        if ProtoOASymbolsListReq is None:
            raise CTraderStreamerError("PROTO_CLASS_NOT_FOUND", "ProtoOASymbolsListReq not found")
        
        corr_id_3 = self._get_next_msg_id()
        sym_list_req = ProtoOASymbolsListReq(
            ctidTraderAccountId=self.account_id
        )
        
        logger.info(f"[GOLD_CTRADER] SENT ProtoOASymbolsListReq corr_id={corr_id_3}")
        try:
            await await_deferred(self.client.send(sym_list_req))
            logger.info(f"[GOLD_CTRADER] SymbolsList request sent successfully")
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to send SymbolsList: {e}")
            raise CTraderStreamerError("SEND_FAILED", f"Failed to send SymbolsList: {e}")
        
        # Wait for symbols list (with longer timeout)
        _, ProtoOASymbolsListRes = find_proto_class('ProtoOASymbolsListRes', _available_modules)
        try:
            payload_type, payload = await self.await_response(
                {ProtoOASymbolsListRes.DESCRIPTOR.full_name},
                correlation_id=corr_id_3,
                timeout_sec=20.0
            )
            logger.info("[GOLD_CTRADER] Symbols list received")
        except CTraderStreamerError as e:
            logger.error(f"[GOLD_CTRADER] Symbols list request failed: {e.reason_code}")
            raise CTraderStreamerError("SYMBOL_LIST_FAILED", f"Failed to get symbols list: {e.reason_code}")
        
        # Parse symbols list and resolve gold symbol
        try:
            sym_list_res = ProtoOASymbolsListRes()
            sym_list_res.ParseFromString(payload)
            
            # Build symbol map
            self.symbol_name_to_id = {}
            
            # Get gold symbol name override from config (if set)
            gold_symbol_name_override = None
            if hasattr(self, 'ctrader_config') and self.ctrader_config:
                gold_symbol_name_override = getattr(self.ctrader_config, 'gold_symbol_name_override', None)
            
            # If GOLD_SYMBOL_NAME env var is set, use it as primary candidate
            if gold_symbol_name_override:
                symbol_candidates = [gold_symbol_name_override]
                logger.info(f"[GOLD_CTRADER] Using GOLD_SYMBOL_NAME override: {gold_symbol_name_override}")
            else:
                # Default candidates: flexible search (try common gold symbol names)
                symbol_candidates = [
                    "XAUUSD",      # Most common
                    "XAUUSD.",     # With dot suffix
                    "XAUUSDm",     # Mini variant
                    "GOLD",        # Generic name
                    "XAU/USD",     # With slash
                    "XAUUSDm.",    # Mini with dot
                    "XAUUSD.r",    # Round variant
                    "GOLD.",       # Generic with dot
                    "GOLDm",       # Generic mini
                    "XAU/USD.",    # Slash with dot
                ]
            
            gold_matches = []
            
            # Process symbols from response
            if hasattr(sym_list_res, 'symbol'):
                for symbol in sym_list_res.symbol:
                    symbol_id = symbol.symbolId if hasattr(symbol, 'symbolId') else None
                    symbol_name = symbol.symbolName if hasattr(symbol, 'symbolName') else ""
                    description = symbol.description if hasattr(symbol, 'description') else ""
                    
                    if symbol_id and symbol_name:
                        self.symbol_name_to_id[symbol_name.upper()] = symbol_id
                        
                        # Check if this matches gold candidates
                        symbol_upper = symbol_name.upper()
                        
                        # If override is set, try exact match first, then contains
                        if gold_symbol_name_override:
                            override_upper = gold_symbol_name_override.upper()
                            if override_upper == symbol_upper:
                                gold_matches.append((symbol_name, symbol_id, description, "exact_override"))
                            elif override_upper in symbol_upper or symbol_upper in override_upper:
                                if "XAU" in symbol_upper or "GOLD" in symbol_upper:
                                    gold_matches.append((symbol_name, symbol_id, description, "contains_override"))
                        else:
                            # Default search: exact match, then contains with XAU/USD or GOLD
                            for candidate in symbol_candidates:
                                candidate_upper = candidate.upper()
                                if candidate_upper == symbol_upper:
                                    gold_matches.append((symbol_name, symbol_id, description, "exact"))
                                elif candidate_upper in symbol_upper or symbol_upper in candidate_upper:
                                    # Contains match - only if it's actually a metal symbol
                                    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
                                        gold_matches.append((symbol_name, symbol_id, description, "contains"))
                            
                            # Also search for any symbol containing XAU and USD, or GOLD
                            if ("XAU" in symbol_upper and "USD" in symbol_upper) or symbol_upper == "GOLD":
                                # Check if not already added
                                already_added = any(sym_id == symbol_id for _, sym_id, _, _ in gold_matches)
                                if not already_added:
                                    gold_matches.append((symbol_name, symbol_id, description, "pattern_match"))
            
            logger.info(f"[GOLD_CTRADER] Loaded {len(self.symbol_name_to_id)} symbols from list")
            
            # Check if CTRADER_GOLD_SYMBOL_ID is set (manual override)
            if hasattr(self, 'ctrader_config') and self.ctrader_config and hasattr(self.ctrader_config, 'gold_symbol_id') and self.ctrader_config.gold_symbol_id:
                manual_symbol_id = self.ctrader_config.gold_symbol_id
                # Find symbol name by ID
                manual_symbol_name = None
                for sym_name, sym_id in self.symbol_name_to_id.items():
                    if sym_id == manual_symbol_id:
                        manual_symbol_name = sym_name
                        break
                
                if manual_symbol_name:
                    logger.info(f"[GOLD_CTRADER] Using manual symbol ID from CTRADER_GOLD_SYMBOL_ID: {manual_symbol_name} (ID: {manual_symbol_id})")
                    self.gold_symbol_name = manual_symbol_name
                    self.gold_symbol_id = manual_symbol_id
                else:
                    logger.warning(f"[GOLD_CTRADER] CTRADER_GOLD_SYMBOL_ID={manual_symbol_id} not found in symbols list, falling back to auto-search")
                    # Fall through to auto-search
            
            # Find best gold match (if not using manual symbol ID)
            if not hasattr(self, 'gold_symbol_name') or not self.gold_symbol_name:
                if gold_matches:
                    # Sort: exact matches first, then contains
                    gold_matches.sort(key=lambda x: (x[3] != "exact", x[0]))
                    
                    # Show top 10 matches
                    logger.info(f"[GOLD_CTRADER] Found {len(gold_matches)} potential gold symbols:")
                    for i, (name, sym_id, desc, match_type) in enumerate(gold_matches[:10], 1):
                        logger.info(f"   {i}. {name} (ID: {sym_id}, match: {match_type}, desc: {desc[:50] if desc else 'N/A'})")
                    
                    # Select best match
                    selected_name, selected_id, selected_desc, match_type = gold_matches[0]
                    logger.info(f"[GOLD_CTRADER] Selected gold symbol: {selected_name} (ID: {selected_id}, match: {match_type})")
                    
                    # Store resolved symbol
                    self.gold_symbol_name = selected_name
                    self.gold_symbol_id = selected_id
                else:
                    # No matches found - show closest symbols
                    logger.error(f"[GOLD_CTRADER] Symbol not found: No gold symbol found in {len(self.symbol_name_to_id)} symbols")
                    logger.error(f"[GOLD_CTRADER] Candidates tried: {symbol_candidates}")
                
                # Find symbols containing XAU or GOLD
                similar_symbols = []
                for sym_name, sym_id in self.symbol_name_to_id.items():
                    if "XAU" in sym_name or "GOLD" in sym_name:
                        similar_symbols.append((sym_name, sym_id))
                
                if similar_symbols:
                    logger.error(f"[GOLD_CTRADER] Found {len(similar_symbols)} similar symbols (containing XAU or GOLD):")
                    for i, (name, sym_id) in enumerate(similar_symbols[:20], 1):
                        logger.error(f"   {i}. {name} (ID: {sym_id})")
                else:
                    logger.error(f"[GOLD_CTRADER] No symbols containing XAU or GOLD found")
                    logger.error(f"[GOLD_CTRADER] Sample available symbols (first 20):")
                    sample_symbols = list(self.symbol_name_to_id.items())[:20]
                    for i, (name, sym_id) in enumerate(sample_symbols, 1):
                        logger.error(f"   {i}. {name} (ID: {sym_id})")
                
                raise CTraderStreamerError("SYMBOL_NOT_FOUND", f"Gold symbol not found. Tried: {symbol_candidates}")
                
        except CTraderStreamerError:
            raise
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Error parsing symbols list: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise CTraderStreamerError("SYMBOL_PARSE_ERROR", f"Failed to parse symbols list: {e}")
        
        # Step 4: Subscribe to gold symbol and wait for first tick
        logger.info(f"[GOLD_CTRADER] Step 4: Subscribing to {self.gold_symbol_name} (ID: {self.gold_symbol_id})")
        
        try:
            await self.subscribe(self.gold_symbol_name)
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to subscribe to gold symbol: {e}")
            raise CTraderStreamerError("SUBSCRIBE_FAILED", f"Failed to subscribe to {self.gold_symbol_name}: {e}")
        
        # Wait for first tick with timeout
        logger.info(f"[GOLD_CTRADER] Waiting for first tick from {self.gold_symbol_name}...")
        tick_received = asyncio.Event()
        first_tick_data = {}
        
        def on_first_tick(name, bid, ask, timestamp):
            if name.upper() == self.gold_symbol_name.upper():
                first_tick_data['bid'] = bid
                first_tick_data['ask'] = ask
                first_tick_data['timestamp'] = timestamp
                tick_received.set()
        
        # Temporarily set callback for first tick
        original_callback = self.on_quote
        self.on_quote = on_first_tick
        
        try:
            await asyncio.wait_for(tick_received.wait(), timeout=20.0)
            logger.info(f"[GOLD_CTRADER] First tick received: bid={first_tick_data.get('bid'):.2f} ask={first_tick_data.get('ask'):.2f}")
        except asyncio.TimeoutError:
            # Extended diagnostics for NO_MARKETDATA
            logger.error("=" * 80)
            logger.error("[GOLD_CTRADER] NO_MARKETDATA: No valid ticks received")
            logger.error("=" * 80)
            logger.error(f"  Symbol: {self.gold_symbol_name} (ID: {self.gold_symbol_id})")
            logger.error(f"  Timeout: 20 seconds")
            logger.error(f"  Possible reasons:")
            logger.error(f"    1. Symbol {self.gold_symbol_name} is disabled/not tradeable")
            logger.error(f"    2. Market is closed or symbol has no liquidity")
            logger.error(f"    3. Account does not have access to this symbol")
            logger.error(f"    4. Subscription succeeded but no market data is flowing")
            logger.error(f"  Subscription status: {self.subscription_status.get(self.gold_symbol_name.upper(), 'unknown')}")
            logger.error(f"  Quote cache keys: {list(self.quote_cache.keys())}")
            logger.error("=" * 80)
            raise CTraderStreamerError("NO_TICKS_RECEIVED", f"No valid ticks received for {self.gold_symbol_name} within 20 seconds. Check symbol access and market hours.")
        finally:
            # Restore original callback
            self.on_quote = original_callback
        
        logger.info("=" * 80)
        logger.info("[GOLD_CTRADER] STREAMER READY")
        logger.info("=" * 80)
        logger.info(f"  symbol_name: {self.gold_symbol_name}")
        logger.info(f"  symbol_id: {self.gold_symbol_id}")
        logger.info(f"  bid: {first_tick_data.get('bid'):.2f}")
        logger.info(f"  ask: {first_tick_data.get('ask'):.2f}")
        logger.info(f"  mid: {(first_tick_data.get('bid', 0) + first_tick_data.get('ask', 0)) / 2:.2f}")
        logger.info("=" * 80)
        logger.info("[GOLD_CTRADER] Protocol sequence completed successfully")

    async def subscribe(self, symbol_name: str):
        """Subscribe to symbol quotes"""
        sym = symbol_name.upper()
        
        # Check if symbol is in mapping
        if sym not in self.symbol_name_to_id:
            logger.error(f"[GOLD_CTRADER] Symbol {sym} not found in symbol list")
            return False
        
        symbol_id = self.symbol_name_to_id[sym]
        logger.info(f"[GOLD_CTRADER] Subscribing to spots for symbolId={symbol_id} ({sym})...")
        
        self.subscription_status[sym] = "pending"
        
        try:
            _, ProtoOASubscribeSpotsReq = find_proto_class('ProtoOASubscribeSpotsReq', _available_modules)
            if ProtoOASubscribeSpotsReq is None:
                logger.error("[GOLD_CTRADER] ProtoOASubscribeSpotsReq not found")
                return False
            
            # Create subscription request
            if hasattr(ProtoOASubscribeSpotsReq, 'symbolId'):
                sub_req = ProtoOASubscribeSpotsReq(
                ctidTraderAccountId=self.account_id,
                    symbolId=[symbol_id]
                )
            else:
                sub_req = ProtoOASubscribeSpotsReq(
                    ctidTraderAccountId=self.account_id
                )
                if hasattr(sub_req, 'symbolId'):
                    sub_req.symbolId = [symbol_id]
                elif hasattr(sub_req, 'symbolIds'):
                    sub_req.symbolIds.append(symbol_id)
            
            corr_id = self._get_next_msg_id()
            logger.info(f"[GOLD_CTRADER] SENT ProtoOASubscribeSpotsReq corr_id={corr_id} symbolId={symbol_id}")
            await await_deferred(self.client.send(sub_req))
            
            # Wait for subscription response or first tick
            await asyncio.sleep(2.0)
            
            if self.subscription_status.get(sym) in ["subscribed", "receiving_quotes"]:
                logger.info(f"[GOLD_CTRADER] Subscription successful for {sym}")
                return True
            else:
                logger.warning(f"[GOLD_CTRADER] Subscription status unclear for {sym}: {self.subscription_status.get(sym)}")
                return False
            
        except Exception as e:
            logger.error(f"[GOLD_CTRADER] Failed to subscribe to {sym}: {e}")
            self.subscription_status[sym] = "error"
            return False

    def set_on_quote(self, cb: Callable[[str, float, float, int], None]):
        self.on_quote = cb
    
    def get_subscription_status(self, symbol_name: str = None) -> Dict[str, str]:
        """Get subscription status for a symbol or all symbols"""
        if symbol_name:
            return {symbol_name.upper(): self.subscription_status.get(symbol_name.upper(), "not_subscribed")}
        return self.subscription_status.copy()
    
    def is_subscribed(self, symbol_name: str) -> bool:
        """Check if a symbol is successfully subscribed"""
        return self.subscription_status.get(symbol_name.upper()) in ["subscribed", "receiving_quotes"]
