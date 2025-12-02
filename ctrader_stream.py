import asyncio
from typing import Callable, Dict, Optional
from loguru import logger

from ctrader_open_api.client import Client
from ctrader_open_api.factory import Factory
from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as OACommon

LIVE_WS = "wss://openapi.ctrader.com:5035"


class CTraderStreamer:
    def __init__(self, access_token: str, client_id: str, client_secret: str, account_id: int):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_id = account_id
        self.client: Optional[Client] = None
        self.symbol_name_to_id: Dict[str, int] = {}
        self.subscription_status: Dict[str, str] = {}  # Track subscription status: "pending", "subscribed", "failed", "error"
        self.on_quote: Optional[Callable[[str, float, float, int], None]] = None

    async def start(self):
        logger.info("Connecting to cTrader WebSocket...")
        self.client = Client(Factory(LIVE_WS))
        await self.client.connect()

        # Application auth
        app_auth = OACommon.ProtoOAApplicationAuthReq(
            clientId=self.client_id,
            clientSecret=self.client_secret
        )
        await self.client.send(app_auth)
        logger.info("Application auth sent")

        # Account auth
        acc_auth = OACommon.ProtoOAAccountAuthReq(
            ctidTraderAccountId=self.account_id,
            accessToken=self.access_token
        )
        await self.client.send(acc_auth)
        logger.info("Account auth sent")

        # Request symbols list
        sym_list_req = OACommon.ProtoOASymbolsListReq(
            ctidTraderAccountId=self.account_id
        )
        await self.client.send(sym_list_req)
        logger.info("Requested symbols list")

        asyncio.create_task(self._recv_loop())

    async def subscribe(self, symbol_name: str):
        """Subscribe to symbol quotes with comprehensive error handling"""
        sym = symbol_name.upper()
        
        # Check if symbol is in mapping
        if sym not in self.symbol_name_to_id:
            logger.error(f"❌ Symbol {sym} not found in symbol list. Available symbols: {list(self.symbol_name_to_id.keys())[:10]}...")
            logger.error(f"   This usually means:")
            logger.error(f"   - Symbol name is incorrect (check broker's exact ticker)")
            logger.error(f"   - Symbol not available for your account")
            logger.error(f"   - Symbols list not yet received (wait a few seconds)")
            return False
        
        symbol_id = self.symbol_name_to_id[sym]
        logger.info(f"📡 Attempting to subscribe to {sym} (ID: {symbol_id})...")
        
        # Mark as pending
        self.subscription_status[sym] = "pending"
        
        try:
            sub_req = OACommon.ProtoOASubscribeForSymbolQuotesReq(
                ctidTraderAccountId=self.account_id,
                symbolId=symbol_id,
                subscribeToSpotTimestamp=True
            )
            await self.client.send(sub_req)
            
            # Wait a moment to see if we get an error response
            await asyncio.sleep(0.5)
            
            # Check if subscription was rejected (status will be updated in _recv_loop)
            if self.subscription_status.get(sym) == "failed":
                logger.error(f"❌ Subscription failed for {sym} (ID: {symbol_id}) - check error logs above")
                return False
            
            # If still pending or changed to subscribed, assume success
            if self.subscription_status.get(sym) in ["pending", "subscribed"]:
                logger.info(f"✅ Subscription request sent for {sym} (ID: {symbol_id})")
                self.subscription_status[sym] = "subscribed"
                return True
            else:
                logger.warning(f"⚠️ Subscription status unclear for {sym}: {self.subscription_status.get(sym)}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Failed to send subscription request for {sym}: {e}")
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
        return self.subscription_status.get(symbol_name.upper()) == "subscribed"

    async def _recv_loop(self):
        """Receive and process messages with comprehensive error handling"""
        async for pkt in self.client.packets():
            try:
                # Determine type by descriptor
                if pkt.payloadType == OACommon.ProtoOASymbolsListRes.DESCRIPTOR.full_name:
                    res = OACommon.ProtoOASymbolsListRes()
                    res.ParseFromString(pkt.payload)
                    
                    # Store all symbols (Forex, Indices, CFDs, etc.)
                    for sym in res.symbol:
                        symbol_name_upper = sym.symbolName.upper()
                        self.symbol_name_to_id[symbol_name_upper] = sym.symbolId
                        
                        # Log indices for debugging
                        if any(keyword in symbol_name_upper for keyword in ['500', 'US500', 'USTEC', 'US30', 'DE40', 'UK100', 'F40', 'JP225', 'AUS200', 'HK50', 'EU50']):
                            logger.info(f"📊 Found index symbol: {sym.symbolName} (ID: {sym.symbolId})")
                    
                    logger.info(f"✅ Resolved {len(self.symbol_name_to_id)} total symbols (Forex + Indices + CFDs)")
                    
                elif pkt.payloadType == OACommon.ProtoOAQuoteMsg.DESCRIPTOR.full_name:
                    quote = OACommon.ProtoOAQuoteMsg()
                    quote.ParseFromString(pkt.payload)
                    # reverse map id -> name
                    name = None
                    for k, v in self.symbol_name_to_id.items():
                        if v == quote.symbolId:
                            name = k
                            # Mark as successfully subscribed when we receive quotes
                            if self.subscription_status.get(k) == "pending":
                                self.subscription_status[k] = "subscribed"
                                logger.info(f"✅ Confirmed subscription to {k} - receiving quotes")
                            break
                    if name and self.on_quote:
                        bid = quote.bid
                        ask = quote.ask
                        self.on_quote(name, bid, ask, quote.timestamp)
                
                # Check for error responses
                elif "Error" in pkt.payloadType or "Reject" in pkt.payloadType:
                    logger.error(f"❌ API Error Response: {pkt.payloadType}")
                    try:
                        # Try to parse error message
                        error_msg = pkt.payload.decode('utf-8', errors='ignore') if isinstance(pkt.payload, bytes) else str(pkt.payload)
                        logger.error(f"   Error details: {error_msg[:200]}")
                    except:
                        pass
                
                # Check for subscription rejection or error responses
                # Try to detect error messages in payload
                elif "Error" in pkt.payloadType or "Reject" in pkt.payloadType or "error" in pkt.payloadType.lower():
                    logger.error(f"❌ API Error Response received: {pkt.payloadType}")
                    try:
                        # Try to parse as error response if available
                        if hasattr(OACommon, 'ProtoOAErrorRes'):
                            try:
                                error_res = OACommon.ProtoOAErrorRes()
                                error_res.ParseFromString(pkt.payload)
                                error_code = getattr(error_res, 'errorCode', None)
                                error_desc = getattr(error_res, 'description', 'Unknown error')
                                
                                logger.error(f"   Error Code: {error_code}")
                                logger.error(f"   Error Description: {error_desc}")
                                
                                # Try to identify which symbol failed
                                if "UNKNOWN_SYMBOL" in str(error_desc).upper() or error_code == 1:
                                    logger.error(f"   → UNKNOWN_SYMBOL: Symbol ID not found")
                                    logger.error(f"   → Check if symbol exists for your account")
                                    # Mark all pending subscriptions as failed if we can't identify which one
                                    for sym, status in self.subscription_status.items():
                                        if status == "pending":
                                            self.subscription_status[sym] = "failed"
                                
                                elif "PERMISSION_DENIED" in str(error_desc).upper() or error_code == 2:
                                    logger.error(f"   → PERMISSION_DENIED: Account doesn't have permission")
                                    logger.error(f"   → Check account permissions for indices/CFDs")
                                
                            except:
                                # If parsing fails, log raw payload
                                error_msg = pkt.payload.decode('utf-8', errors='ignore') if isinstance(pkt.payload, bytes) else str(pkt.payload)
                                logger.error(f"   Raw error: {error_msg[:500]}")
                    except Exception as parse_error:
                        logger.error(f"   Could not parse error response: {parse_error}")
                        # Log raw payload type and size
                        logger.error(f"   Payload type: {pkt.payloadType}, Size: {len(pkt.payload) if hasattr(pkt.payload, '__len__') else 'unknown'}")
                
                else:
                    # Log unknown message types for debugging
                    logger.debug(f"Received message type: {pkt.payloadType}")
                    
            except Exception as e:
                logger.error(f"❌ Stream parse error: {e}")
                import traceback
                logger.error(traceback.format_exc())




