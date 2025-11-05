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
        sym = symbol_name.upper()
        if sym not in self.symbol_name_to_id:
            logger.warning(f"Symbol {sym} not resolved yet; delaying subscribe")
            return
        sub_req = OACommon.ProtoOASubscribeForSymbolQuotesReq(
            ctidTraderAccountId=self.account_id,
            symbolId=self.symbol_name_to_id[sym],
            subscribeToSpotTimestamp=True
        )
        await self.client.send(sub_req)
        logger.info(f"Subscribed to {sym}")

    def set_on_quote(self, cb: Callable[[str, float, float, int], None]):
        self.on_quote = cb

    async def _recv_loop(self):
        async for pkt in self.client.packets():
            try:
                # Determine type by descriptor
                if pkt.payloadType == OACommon.ProtoOASymbolsListRes.DESCRIPTOR.full_name:
                    res = OACommon.ProtoOASymbolsListRes()
                    res.ParseFromString(pkt.payload)
                    for sym in res.symbol:
                        self.symbol_name_to_id[sym.symbolName.upper()] = sym.symbolId
                    logger.info(f"Resolved {len(self.symbol_name_to_id)} symbols")
                elif pkt.payloadType == OACommon.ProtoOAQuoteMsg.DESCRIPTOR.full_name:
                    quote = OACommon.ProtoOAQuoteMsg()
                    quote.ParseFromString(pkt.payload)
                    # reverse map id -> name
                    name = None
                    for k, v in self.symbol_name_to_id.items():
                        if v == quote.symbolId:
                            name = k
                            break
                    if name and self.on_quote:
                        bid = quote.bid
                        ask = quote.ask
                        self.on_quote(name, bid, ask, quote.timestamp)
                else:
                    # other messages ignored for now
                    pass
            except Exception as e:
                logger.error(f"Stream parse error: {e}")




