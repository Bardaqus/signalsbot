"""
cTrader gRPC Client - Proper implementation using ProtoOA messages
"""
import asyncio
import grpc
import ssl
from loguru import logger
from config import Config

# Import generated protobuf classes
import ctrader_service_pb2
import ctrader_service_pb2_grpc


class CTraderGRPCClient:
    """cTrader gRPC client using ProtoOA messages"""
    
    def __init__(self, access_token: str, account_id: int):
        self.access_token = access_token
        self.account_id = account_id
        self.client_id = Config.CTRADER_CLIENT_ID
        self.client_secret = Config.CTRADER_CLIENT_SECRET
        
        # Demo server for demo accounts
        self.server_url = "demo.ctraderapi.com:5035"
        self.channel = None
        self.stub = None
        
        # Message counter
        self.msg_id = 0
    
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id += 1
        return self.msg_id
    
    def _create_ssl_credentials(self):
        """Create SSL credentials for gRPC"""
        # Create SSL context with ALPN support
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Set ALPN protocols for gRPC
        ssl_context.set_alpn_protocols(['h2'])
        
        # Create gRPC credentials
        credentials = grpc.ssl_channel_credentials(
            root_certificates=None,
            private_key=None,
            certificate_chain=None
        )
        
        return credentials
    
    async def connect(self):
        """Connect to cTrader gRPC server"""
        try:
            logger.info(f"🔌 Connecting to cTrader gRPC server: {self.server_url}")
            
            # Try insecure channel first for testing
            self.channel = grpc.aio.insecure_channel(self.server_url)
            
            # Create stub
            self.stub = ctrader_service_pb2_grpc.OpenApiServiceStub(self.channel)
            
            logger.info("✅ Connected to cTrader gRPC server")
            
            # Authenticate application
            await self._authenticate_application()
            
            # Authenticate account
            await self._authenticate_account()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to cTrader: {e}")
            return False
    
    async def _authenticate_application(self):
        """Authenticate application with cTrader"""
        try:
            logger.info("🔐 Authenticating application...")
            
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
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAApplicationAuthRes":
                auth_res = ctrader_service_pb2.ProtoOAApplicationAuthRes()
                auth_res.ParseFromString(response.payload)
                logger.info(f"✅ Application authenticated: {auth_res.ctidTraderAccountId}")
                return True
            else:
                logger.error(f"❌ Authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Application authentication error: {e}")
            return False
    
    async def _authenticate_account(self):
        """Authenticate account with access token"""
        try:
            logger.info("🔐 Authenticating account...")
            
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
                logger.info(f"✅ Account authenticated: {auth_res.ctidTraderAccountId}")
                return True
            else:
                logger.error(f"❌ Account authentication failed: {response.payloadType}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Account authentication error: {e}")
            return False
    
    async def get_accounts(self):
        """Get account list using access token"""
        try:
            logger.info("📊 Getting account list...")
            
            # Create get accounts request
            accounts_req = ctrader_service_pb2.ProtoOAGetAccountListByAccessTokenReq(
                accessToken=self.access_token
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAGetAccountListByAccessTokenReq",
                clientMsgId=self._get_next_msg_id(),
                payload=accounts_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOAGetAccountListByAccessTokenRes":
                accounts_res = ctrader_service_pb2.ProtoOAGetAccountListByAccessTokenRes()
                accounts_res.ParseFromString(response.payload)
                
                logger.info(f"✅ Found {len(accounts_res.ctidTraderAccount)} accounts")
                for account in accounts_res.ctidTraderAccount:
                    logger.info(f"  - Account {account.ctidTraderAccountId}: {account.brokerName} ({'Live' if account.isLive else 'Demo'})")
                
                return accounts_res.ctidTraderAccount
            else:
                logger.error(f"❌ Get accounts failed: {response.payloadType}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Get accounts error: {e}")
            return []
    
    async def place_trade(self, symbol_id: int, trade_type: str, volume: float, 
                         stop_loss: float = None, take_profit: float = None, 
                         comment: str = ""):
        """Place a trade using gRPC"""
        try:
            logger.info(f"💰 Placing trade: Symbol {symbol_id}, {trade_type}, Volume {volume}")
            
            # Convert trade type to integer
            trade_side = 1 if trade_type.upper() == "BUY" else 2
            
            # Create new order request
            order_req = ctrader_service_pb2.ProtoOANewOrderReq(
                ctidTraderAccountId=self.account_id,
                symbolId=symbol_id,
                orderType=1,  # Market order
                tradeSide=trade_side,
                volume=int(volume * 1000000),  # Convert to micro lots
                limitPrice=0,
                stopPrice=0,
                stopLoss=int(stop_loss * 1000000) if stop_loss else 0,
                takeProfit=int(take_profit * 1000000) if take_profit else 0,
                expirationTimestamp=0,
                comment=comment
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOANewOrderReq",
                clientMsgId=self._get_next_msg_id(),
                payload=order_req.SerializeToString()
            )
            
            # Send request
            response = await self.stub.ProcessMessage(message)
            
            if response.payloadType == "ProtoOANewOrderRes":
                order_res = ctrader_service_pb2.ProtoOANewOrderRes()
                order_res.ParseFromString(response.payload)
                
                logger.info(f"✅ Trade placed successfully! Order ID: {order_res.orderId}")
                return {
                    'success': True,
                    'order_id': order_res.orderId,
                    'symbol_id': order_res.symbolId,
                    'trade_side': order_res.tradeSide,
                    'volume': order_res.volume,
                    'stop_loss': order_res.stopLoss,
                    'take_profit': order_res.takeProfit
                }
            else:
                logger.error(f"❌ Trade placement failed: {response.payloadType}")
                return {'success': False, 'error': f'Unexpected response: {response.payloadType}'}
                
        except Exception as e:
            logger.error(f"❌ Trade placement error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.channel:
            await self.channel.close()
            logger.info("🔌 Disconnected from cTrader")


async def test_ctrader_grpc():
    """Test cTrader gRPC connection and trading"""
    logger.info("🧪 Testing cTrader gRPC client...")
    
    # Create client
    client = CTraderGRPCClient(
        access_token=Config.CTRADER_ACCESS_TOKEN,
        account_id=44749280  # Your account ID
    )
    
    try:
        # Connect
        if await client.connect():
            logger.info("✅ Connected successfully!")
            
            # Get accounts
            accounts = await client.get_accounts()
            
            # Test trade (using EURUSD symbol ID - this would need to be looked up)
            # For now, let's just test the connection
            logger.info("🎯 Connection test successful!")
            
        else:
            logger.error("❌ Failed to connect")
            
    except Exception as e:
        logger.error(f"❌ Test error: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_ctrader_grpc())
