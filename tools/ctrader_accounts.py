#!/usr/bin/env python3
"""
cTrader Account List Diagnostic Tool

This script connects to cTrader Open API and retrieves a list of available accounts
to help identify the correct DEMO_ACCOUNT_ID (ctidTraderAccountId) for configuration.

Usage:
    python tools/ctrader_accounts.py

Required environment variables (.env):
    CTRADER_CLIENT_ID=...
    CTRADER_CLIENT_SECRET=...
    
Optional environment variables:
    CTRADER_ACCESS_TOKEN=...  (if already obtained)
    CTRADER_REFRESH_TOKEN=...  (if already obtained)
    CTRADER_REDIRECT_URI=http://localhost:8080/callback
"""
import asyncio
import os
import sys
import webbrowser
from typing import Optional
from dotenv import load_dotenv

# Add parent directory to path to import project modules
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

# Change to project root directory to ensure relative imports work
os.chdir(project_root)

# Load environment variables
load_dotenv()
load_dotenv('config_live.env')

try:
    import grpc
    import grpc.aio
except ImportError:
    print("[ERROR] grpcio and grpcio-aio packages are required")
    print("   Install with: pip install grpcio grpcio-aio")
    sys.exit(1)

try:
    import ctrader_service_pb2
    import ctrader_service_pb2_grpc
except ImportError as e:
    error_msg = str(e)
    print("[ERROR] ctrader_service_pb2 modules not found")
    print(f"   Import error: {error_msg}")
    print(f"   Current directory: {os.getcwd()}")
    print(f"   Project root: {project_root}")
    pb2_file = os.path.join(project_root, 'ctrader_service_pb2.py')
    print(f"   Looking for: {pb2_file}")
    
    if not os.path.exists(pb2_file):
        print("   File not found! Make sure you're running from the project root directory")
    elif "runtime_version" in error_msg or "protobuf" in error_msg.lower():
        print("   Protobuf version issue detected!")
        print("   Try upgrading protobuf:")
        print("   pip install --upgrade protobuf")
        print("   Or install specific version:")
        print("   pip install protobuf==4.25.0")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Unexpected error importing ctrader_service_pb2: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[ERROR] requests package is required")
    print("   Install with: pip install requests")
    sys.exit(1)


class CTraderAccountLister:
    """cTrader Account List diagnostic tool"""
    
    def __init__(self):
        # Load from environment, removing any quotes or whitespace
        client_id_raw = os.getenv('CTRADER_CLIENT_ID', '').strip()
        client_secret_raw = os.getenv('CTRADER_CLIENT_SECRET', '').strip()
        
        # Remove quotes if present
        self.client_id = client_id_raw.strip('"').strip("'").strip()
        self.client_secret = client_secret_raw.strip('"').strip("'").strip()
        self.redirect_uri = os.getenv('CTRADER_REDIRECT_URI', 'http://localhost:8080/callback')
        self.access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip()
        self.refresh_token = os.getenv('CTRADER_REFRESH_TOKEN', '').strip()
        self.api_url = os.getenv('CTRADER_API_URL', 'https://openapi.ctrader.com')
        self.auth_url = os.getenv('CTRADER_AUTH_URL', 'https://connect.spotware.com/apps')
        
        self.channel = None
        self.stub = None
        self.msg_id = 0
        
    def _get_next_msg_id(self) -> int:
        """Get next message ID"""
        self.msg_id += 1
        return self.msg_id
    
    def _validate_config(self) -> bool:
        """Validate that required configuration is present"""
        if not self.client_id:
            print("[ERROR] CTRADER_CLIENT_ID not found in .env")
            print("   Set it in your .env file: CTRADER_CLIENT_ID=your_client_id")
            return False
        
        if not self.client_secret:
            print("[ERROR] CTRADER_CLIENT_SECRET not found in .env")
            print("   Set it in your .env file: CTRADER_CLIENT_SECRET=your_client_secret")
            return False
        
        return True
    
    def _get_auth_url(self) -> str:
        """Generate OAuth2 authorization URL"""
        from urllib.parse import urlencode, urljoin
        
        base = self.auth_url if self.auth_url.endswith('/') else self.auth_url + '/'
        path = urljoin(base, 'authorize')
        
        auth_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'trading'
        }
        
        query = urlencode(auth_params, safe=':/')
        auth_url = f"{path}?{query}"
        return auth_url
    
    def _exchange_code_for_token(self, authorization_code: str) -> bool:
        """Exchange authorization code for access token"""
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'code': authorization_code
        }
        
        try:
            response = requests.post(
                f"{self.api_url}/oauth/token",
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                self.access_token = token_response.get('access_token', '')
                self.refresh_token = token_response.get('refresh_token', '')
                
                print(f"[OK] Successfully obtained access token")
                print(f"   Access Token: {self.access_token[:30]}...")
                if self.refresh_token:
                    print(f"   Refresh Token: {self.refresh_token[:30]}...")
                return True
            else:
                error_text = response.text
                print(f"[ERROR] Failed to exchange code for token: {response.status_code}")
                print(f"   Error: {error_text}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error exchanging code for token: {e}")
            return False
    
    async def _ensure_access_token(self) -> bool:
        """Ensure we have a valid access token, performing OAuth if needed"""
        if self.access_token:
            print(f"[OK] Found access token in .env: {self.access_token[:30]}...")
            return True
        
        print("[WARN] No access token found in .env")
        print("   Performing OAuth authorization...")
        print()
        
        # Generate auth URL
        auth_url = self._get_auth_url()
        print(f"[URL] Please visit this URL to authorize the application:")
        print(f"   {auth_url}")
        print()
        
        # Try to open browser
        try:
            webbrowser.open(auth_url)
            print("[BROWSER] Opening browser automatically...")
        except:
            print("[WARN] Could not open browser automatically")
        
        print("\n[STEPS] Steps to authorize:")
        print("1. Visit the URL above in your browser")
        print("2. Log in with your cTrader account")
        print("3. Authorize the application")
        print("4. After authorization, you'll be redirected to a URL like:")
        print(f"   {self.redirect_uri}?code=AUTHORIZATION_CODE")
        print("5. Copy the 'code' parameter from the redirect URL")
        print()
        
        # Get authorization code from user
        auth_code = input("[CODE] Enter authorization code: ").strip()
        
        if not auth_code:
            print("[ERROR] No authorization code provided")
            return False
        
        # Exchange code for token
        print("[EXCHANGE] Exchanging code for access token...")
        success = self._exchange_code_for_token(auth_code)
        
        if success:
            print()
            print("[TIP] Tip: Add these to your .env file to avoid re-authorization:")
            print(f"   CTRADER_ACCESS_TOKEN={self.access_token}")
            if self.refresh_token:
                print(f"   CTRADER_REFRESH_TOKEN={self.refresh_token}")
            print()
            return True
        else:
            return False
    
    async def connect(self) -> bool:
        """Connect to cTrader gRPC server"""
        try:
            print("[CONNECT] Connecting to cTrader gRPC server...")
            print("   Server: demo.ctraderapi.com:5035")
            
            # Try insecure channel first (more reliable on Windows)
            print("   Using insecure channel (more reliable)")
            self.channel = grpc.aio.insecure_channel("demo.ctraderapi.com:5035")
            
            # Create stub
            self.stub = ctrader_service_pb2_grpc.OpenApiServiceStub(self.channel)
            
            print("[OK] Connected to cTrader gRPC server")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to connect to cTrader: {e}")
            error_str = str(e)
            if "ALPN" in error_str or "missing selected ALPN" in error_str:
                print("\n[TIP] ALPN error detected. This is a known issue with some gRPC versions.")
                print("   Solutions:")
                print("   1. Update grpcio: pip install --upgrade grpcio grpcio-aio")
                print("   2. Check CLIENT_ID and CLIENT_SECRET are real values (not placeholders)")
                print("   3. The script will try insecure channel as fallback")
            else:
                print(f"\n[TIP] Troubleshooting:")
                print("   1. Check your internet connection")
                print("   2. Verify CLIENT_ID and CLIENT_SECRET in .env are correct")
                print("   3. Check if CLIENT_ID shows 'your_client_id_here' - replace with real value")
            return False
    
    async def authenticate_application(self) -> bool:
        """Authenticate application with cTrader"""
        try:
            print("[AUTH] Authenticating application...")
            
            # Check if client_id or client_secret are placeholders
            if "your_client" in self.client_id.lower() or "placeholder" in self.client_id.lower() or not self.client_id or len(self.client_id) < 10:
                print(f"   [ERROR] CLIENT_ID appears to be invalid or placeholder: {self.client_id[:50]}")
                print("   Please set a real CLIENT_ID in your .env file")
                print("   Get it from: https://openapi.ctrader.com")
                return False
            
            # Check if client_secret is a placeholder
            if "your_client" in self.client_secret.lower() or "placeholder" in self.client_secret.lower() or not self.client_secret or len(self.client_secret) < 10:
                print(f"   [ERROR] CLIENT_SECRET appears to be invalid or placeholder: {self.client_secret[:50] if self.client_secret else 'EMPTY'}")
                print("   Please set a real CLIENT_SECRET in your .env file")
                print("   Get it from: https://openapi.ctrader.com")
                return False
            
            print(f"   Client ID: {self.client_id[:20]}...")
            
            # Create application auth request
            app_auth_req = ctrader_service_pb2.ProtoOAApplicationAuthReq(
                clientId=self.client_id,
                clientSecret=self.client_secret
            )
            
            # Wrap in ProtoMessage
            message = ctrader_service_pb2.ProtoMessage(
                payloadType="ProtoOAApplicationAuthReq",
                clientMsgId=self._get_next_msg_id(),
                payload=app_auth_req.SerializeToString()
            )
            
            # Send request - handle ALPN errors by retrying with insecure channel
            try:
                response = await self.stub.ProcessMessage(message)
            except Exception as rpc_error:
                error_str = str(rpc_error)
                if "ALPN" in error_str or "missing selected ALPN" in error_str:
                    print(f"   [WARN] ALPN error during RPC call: {rpc_error}")
                    print("   Retrying with insecure channel...")
                    # Close current channel
                    if self.channel:
                        await self.channel.close()
                    # Try insecure channel
                    self.channel = grpc.aio.insecure_channel("demo.ctraderapi.com:5035")
                    self.stub = ctrader_service_pb2_grpc.OpenApiServiceStub(self.channel)
                    # Retry request
                    response = await self.stub.ProcessMessage(message)
                else:
                    raise
            
            if response.payloadType == "ProtoOAApplicationAuthRes":
                app_auth_res = ctrader_service_pb2.ProtoOAApplicationAuthRes()
                app_auth_res.ParseFromString(response.payload)
                print("[OK] Application authentication successful")
                return True
            else:
                print(f"[ERROR] Unexpected response type: {response.payloadType}")
                return False
                
        except Exception as e:
            print(f"[ERROR] Application authentication failed: {e}")
            return False
    
    async def get_account_list(self) -> Optional[list]:
        """Get account list using access token"""
        try:
            print("[INFO] Getting account list...")
            
            if not self.access_token:
                print("[ERROR] Access token is required to get account list")
                return None
            
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
                
                accounts = []
                for account in accounts_res.ctidTraderAccount:
                    accounts.append({
                        'ctidTraderAccountId': account.ctidTraderAccountId,
                        'isLive': account.isLive,
                        'traderLogin': account.traderLogin,
                        'currency': account.currency,
                        'brokerName': account.brokerName,
                        'leverage': account.leverage,
                        'balance': account.balance,
                        'brokerAccountName': account.brokerAccountName,
                    })
                
                print(f"[OK] Found {len(accounts)} account(s)")
                return accounts
            else:
                print(f"[ERROR] Unexpected response type: {response.payloadType}")
                print(f"   This might indicate an authentication issue")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to get account list: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def print_accounts(self, accounts: list):
        """Print account list in a formatted way"""
        if not accounts:
            print("[WARN] No accounts found")
            return
        
        print()
        print("=" * 80)
        print("[INFO] AVAILABLE ACCOUNTS")
        print("=" * 80)
        print()
        
        for i, account in enumerate(accounts, 1):
            account_type = "LIVE" if account['isLive'] else "DEMO"
            account_type_marker = "[LIVE]" if account['isLive'] else "[DEMO]"
            
            print(f"{account_type_marker} Account #{i}: {account_type}")
            print(f"   Account ID (ctidTraderAccountId): {account['ctidTraderAccountId']}")
            print(f"   Trader Login: {account['traderLogin']}")
            print(f"   Broker: {account['brokerName']}")
            if account['brokerAccountName']:
                print(f"   Broker Account: {account['brokerAccountName']}")
            print(f"   Currency: {account['currency']}")
            print(f"   Leverage: 1:{account['leverage']}")
            if account['balance']:
                balance = account['balance'] / 1000000.0  # Convert from micro units
                print(f"   Balance: {balance:.2f} {account['currency']}")
            print()
        
        print("=" * 80)
        print()
        print("[TIP] TO USE IN YOUR CONFIGURATION:")
        print()
        
        # Find demo accounts
        demo_accounts = [acc for acc in accounts if not acc['isLive']]
        live_accounts = [acc for acc in accounts if acc['isLive']]
        
        if demo_accounts:
            print("   For DEMO_ACCOUNT_ID, use one of these:")
            for acc in demo_accounts:
                print(f"      DEMO_ACCOUNT_ID={acc['ctidTraderAccountId']}  # {acc['brokerName']} Demo")
        else:
            print("   [WARN] No DEMO accounts found")
        
        if live_accounts:
            print()
            print("   For LIVE accounts:")
            for acc in live_accounts:
                print(f"      LIVE_ACCOUNT_ID={acc['ctidTraderAccountId']}  # {acc['brokerName']} Live")
        
        print()
        print("=" * 80)
    
    async def disconnect(self):
        """Disconnect from cTrader"""
        if self.channel:
            await self.channel.close()
            print("[CONNECT] Disconnected from cTrader")
    
    async def run(self):
        """Main execution flow"""
        print("=" * 80)
        print("cTrader Account List Diagnostic Tool")
        print("=" * 80)
        print()
        
        # Validate configuration
        if not self._validate_config():
            return False
        
        # Ensure we have access token
        if not await self._ensure_access_token():
            return False
        
        # Connect to cTrader
        if not await self.connect():
            return False
        
        try:
            # Authenticate application
            if not await self.authenticate_application():
                return False
            
            # Get account list
            accounts = await self.get_account_list()
            
            if accounts:
                self.print_accounts(accounts)
                return True
            else:
                print("[ERROR] Could not retrieve account list")
                return False
                
        finally:
            await self.disconnect()


async def main():
    """Main entry point"""
    lister = CTraderAccountLister()
    success = await lister.run()
    
    if success:
        print("[OK] Diagnostic completed successfully")
        return 0
    else:
        print("[ERROR] Diagnostic failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[STOP] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
