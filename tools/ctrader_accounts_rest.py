#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cTrader Account List Diagnostic Tool (REST API version)

This script uses REST API to get account list - simpler and doesn't require CLIENT_ID/CLIENT_SECRET.
Only needs ACCESS_TOKEN from .env.

Usage:
    python tools/ctrader_accounts_rest.py
"""
import os
import sys
import json
from typing import Optional, List, Dict

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from dotenv import load_dotenv

try:
    import requests
except ImportError:
    print("[ERROR] requests package is required")
    print("   Install with: pip install requests")
    sys.exit(1)

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)
os.chdir(project_root)

# Load environment variables
load_dotenv('.env', override=False)
if os.path.exists('config_live.env'):
    load_dotenv('config_live.env', override=True)


class CTraderAccountListerREST:
    """cTrader Account List diagnostic tool using REST API"""
    
    def __init__(self):
        self.access_token = os.getenv('CTRADER_ACCESS_TOKEN', '').strip().strip('"').strip("'")
        self.api_url = os.getenv('CTRADER_API_URL', 'https://openapi.ctrader.com')
        
    def _validate_config(self) -> bool:
        """Validate that access token is present"""
        if not self.access_token:
            print("[ERROR] CTRADER_ACCESS_TOKEN not found in .env")
            print("   Set it in your .env file: CTRADER_ACCESS_TOKEN=your_access_token")
            print("   Or run OAuth flow first (see tools/ctrader_accounts.py)")
            return False
        
        # Check for placeholder
        if "your_access" in self.access_token.lower() or "placeholder" in self.access_token.lower():
            print("[ERROR] CTRADER_ACCESS_TOKEN appears to be a placeholder")
            print("   Please set a real ACCESS_TOKEN in your .env file")
            return False
        
        return True
    
    def get_accounts(self) -> Optional[List[Dict]]:
        """Get account list using REST API"""
        try:
            print("[INFO] Getting account list via REST API...")
            print(f"   API URL: {self.api_url}/accounts")
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.api_url}/accounts",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                accounts_data = response.json()
                print(f"[OK] Successfully retrieved account data")
                return accounts_data
            elif response.status_code == 401:
                print(f"[ERROR] Authentication failed (401 Unauthorized)")
                print("   Your ACCESS_TOKEN may be expired or invalid")
                print("   Try refreshing it or getting a new one via OAuth")
                return None
            else:
                error_text = response.text
                print(f"[ERROR] Failed to get accounts: HTTP {response.status_code}")
                print(f"   Response: {error_text[:200]}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def parse_accounts(self, accounts_data) -> List[Dict]:
        """Parse account data from REST API response"""
        accounts = []
        
        # REST API may return different formats, try to handle both
        if isinstance(accounts_data, list):
            # Direct list of accounts
            for acc in accounts_data:
                account = {
                    'ctidTraderAccountId': acc.get('ctidTraderAccountId') or acc.get('accountId') or acc.get('id'),
                    'isLive': acc.get('isLive', False),
                    'traderLogin': acc.get('traderLogin') or acc.get('login') or acc.get('accountNumber'),
                    'currency': acc.get('currency', 'USD'),
                    'brokerName': acc.get('brokerName') or acc.get('broker') or 'Unknown',
                    'leverage': acc.get('leverage', 0),
                    'balance': acc.get('balance') or acc.get('deposit'),
                    'brokerAccountName': acc.get('brokerAccountName') or acc.get('accountName') or '',
                }
                if account['ctidTraderAccountId']:
                    accounts.append(account)
        elif isinstance(accounts_data, dict):
            # Nested structure
            if 'accounts' in accounts_data:
                return self.parse_accounts(accounts_data['accounts'])
            elif 'data' in accounts_data:
                return self.parse_accounts(accounts_data['data'])
            else:
                # Single account
                account = {
                    'ctidTraderAccountId': accounts_data.get('ctidTraderAccountId') or accounts_data.get('accountId'),
                    'isLive': accounts_data.get('isLive', False),
                    'traderLogin': accounts_data.get('traderLogin') or accounts_data.get('login'),
                    'currency': accounts_data.get('currency', 'USD'),
                    'brokerName': accounts_data.get('brokerName') or accounts_data.get('broker') or 'Unknown',
                    'leverage': accounts_data.get('leverage', 0),
                    'balance': accounts_data.get('balance') or accounts_data.get('deposit'),
                    'brokerAccountName': accounts_data.get('brokerAccountName') or accounts_data.get('accountName') or '',
                }
                if account['ctidTraderAccountId']:
                    accounts.append(account)
        
        return accounts
    
    def print_accounts(self, accounts: List[Dict]):
        """Print account list in a formatted way"""
        if not accounts:
            print("[WARN] No accounts found in response")
            print("   Raw response data:")
            return
        
        print()
        print("=" * 80)
        print("[INFO] AVAILABLE ACCOUNTS")
        print("=" * 80)
        print()
        
        for i, account in enumerate(accounts, 1):
            account_type = "LIVE" if account.get('isLive', False) else "DEMO"
            account_type_marker = "[LIVE]" if account.get('isLive', False) else "[DEMO]"
            
            print(f"{account_type_marker} Account #{i}: {account_type}")
            print(f"   Account ID (ctidTraderAccountId): {account.get('ctidTraderAccountId', 'N/A')}")
            if account.get('traderLogin'):
                print(f"   Trader Login: {account['traderLogin']}")
            print(f"   Broker: {account.get('brokerName', 'Unknown')}")
            if account.get('brokerAccountName'):
                print(f"   Broker Account: {account['brokerAccountName']}")
            print(f"   Currency: {account.get('currency', 'USD')}")
            if account.get('leverage'):
                print(f"   Leverage: 1:{account['leverage']}")
            if account.get('balance'):
                balance = account['balance']
                # Convert from micro units if needed
                if balance > 1000000:
                    balance = balance / 1000000.0
                print(f"   Balance: {balance:.2f} {account.get('currency', 'USD')}")
            print()
        
        print("=" * 80)
        print()
        print("[TIP] TO USE IN YOUR CONFIGURATION:")
        print()
        
        # Find demo accounts
        demo_accounts = [acc for acc in accounts if not acc.get('isLive', False)]
        live_accounts = [acc for acc in accounts if acc.get('isLive', False)]
        
        if demo_accounts:
            print("   For DEMO_ACCOUNT_ID, use one of these:")
            for acc in demo_accounts:
                account_id = acc.get('ctidTraderAccountId', 'N/A')
                broker = acc.get('brokerName', 'Unknown')
                print(f"      DEMO_ACCOUNT_ID={account_id}  # {broker} Demo")
        else:
            print("   [WARN] No DEMO accounts found")
        
        if live_accounts:
            print()
            print("   For LIVE accounts:")
            for acc in live_accounts:
                account_id = acc.get('ctidTraderAccountId', 'N/A')
                broker = acc.get('brokerName', 'Unknown')
                print(f"      LIVE_ACCOUNT_ID={account_id}  # {broker} Live")
        
        print()
        print("=" * 80)
    
    def run(self):
        """Main execution flow"""
        print("=" * 80)
        print("cTrader Account List Diagnostic Tool (REST API)")
        print("=" * 80)
        print()
        
        # Validate configuration
        if not self._validate_config():
            return False
        
        print(f"[OK] Found access token: {self.access_token[:30]}...")
        print()
        
        # Get account list
        accounts_data = self.get_accounts()
        
        if accounts_data is None:
            print("[ERROR] Could not retrieve account list")
            return False
        
        # Parse accounts
        accounts = self.parse_accounts(accounts_data)
        
        if accounts:
            self.print_accounts(accounts)
            return True
        else:
            print("[WARN] No accounts parsed from response")
            print("   Raw response:")
            print(json.dumps(accounts_data, indent=2, default=str))
            return False


def main():
    """Main entry point"""
    lister = CTraderAccountListerREST()
    success = lister.run()
    
    if success:
        print("[OK] Diagnostic completed successfully")
        return 0
    else:
        print("[ERROR] Diagnostic failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[STOP] Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
