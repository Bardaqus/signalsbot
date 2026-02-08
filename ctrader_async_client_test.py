"""
Smoke test for cTrader async client
Usage: python -m ctrader_async_client_test
"""
import asyncio
import sys
from config import Config
from ctrader_async_client import CTraderAsyncClient, CTraderAsyncError


async def smoke_test():
    """Run smoke test: connect -> ApplicationAuth -> AccountAuth"""
    print("=" * 80)
    print("[SMOKE_TEST] Starting cTrader async client smoke test...")
    print("=" * 80)
    
    try:
        # Get config
        ctrader_config = Config.get_ctrader_config()
        ws_url, ws_source = ctrader_config.get_ws_url()
        
        account_id = ctrader_config.account_id
        client_id = ctrader_config.client_id
        client_secret = ctrader_config.client_secret
        access_token = ctrader_config.access_token
        refresh_token = getattr(ctrader_config, 'refresh_token', None)
        is_demo = ctrader_config.is_demo
        token_url = getattr(ctrader_config, 'token_url', None)
        
        print(f"[SMOKE_TEST] Config:")
        print(f"   ws_url: {ws_url} (source: {ws_source})")
        print(f"   is_demo: {is_demo}")
        print(f"   account_id: {account_id}")
        print(f"   client_id: {client_id[:8]}...")
        print(f"   access_token: {access_token[:4]}...")
        print(f"   refresh_token: {'SET' if refresh_token else 'NOT SET'}")
        print()
        
        # Validate config
        if not account_id or account_id <= 0:
            print("[SMOKE_TEST] ❌ Invalid account_id")
            return False
        
        if not access_token:
            print("[SMOKE_TEST] ❌ Missing access_token")
            return False
        
        # Create client
        print("[SMOKE_TEST] Creating client...")
        client = CTraderAsyncClient(
            ws_url=ws_url,
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            account_id=account_id,
            is_demo=is_demo,
            refresh_token=refresh_token,
            token_url=token_url
        )
        
        # Step 1: Connect
        print("[SMOKE_TEST] Step 1: Connecting to WebSocket...")
        try:
            await client.connect()
            print("[SMOKE_TEST] ✅ Connected")
        except Exception as e:
            print(f"[SMOKE_TEST] ❌ Connect failed: {type(e).__name__}: {e}")
            return False
        
        # Step 2: ApplicationAuth
        print("[SMOKE_TEST] Step 2: ApplicationAuth...")
        try:
            await client.auth_application()
            print("[SMOKE_TEST] ✅ ApplicationAuth OK")
        except CTraderAsyncError as e:
            print(f"[SMOKE_TEST] ❌ ApplicationAuth failed: {e.reason}: {e.message}")
            await client.close()
            return False
        except Exception as e:
            print(f"[SMOKE_TEST] ❌ ApplicationAuth error: {type(e).__name__}: {e}")
            await client.close()
            return False
        
        # Step 3: AccountAuth
        print("[SMOKE_TEST] Step 3: AccountAuth...")
        try:
            await client.auth_account(retry_on_error=True)
            print("[SMOKE_TEST] ✅ AccountAuth OK")
        except CTraderAsyncError as e:
            if e.reason == "TOKEN_INVALID":
                print(f"[SMOKE_TEST] ❌ AccountAuth failed: Token invalid")
                print(f"[SMOKE_TEST] ⚠️ Please update CTRADER_ACCESS_TOKEN and CTRADER_REFRESH_TOKEN in .env")
            else:
                print(f"[SMOKE_TEST] ❌ AccountAuth failed: {e.reason}: {e.message}")
            await client.close()
            return False
        except Exception as e:
            print(f"[SMOKE_TEST] ❌ AccountAuth error: {type(e).__name__}: {e}")
            await client.close()
            return False
        
        # Step 4: Try to get a price (EURUSD)
        print("[SMOKE_TEST] Step 4: Testing price fetch (EURUSD)...")
        try:
            symbol_id = await client.ensure_symbol_id("EURUSD")
            if symbol_id:
                await client.subscribe_spot(symbol_id)
                print(f"[SMOKE_TEST] ✅ Subscribed to EURUSD (symbol_id={symbol_id})")
                
                # Wait a bit for spot event
                await asyncio.sleep(2)
                
                quote = client.get_last_quote(symbol_id)
                if quote:
                    bid = quote.get("bid")
                    ask = quote.get("ask")
                    print(f"[SMOKE_TEST] ✅ Got quote: bid={bid}, ask={ask}")
                else:
                    print(f"[SMOKE_TEST] ⚠️ No quote received yet (may need more time)")
            else:
                print(f"[SMOKE_TEST] ⚠️ EURUSD symbol not found")
        except Exception as e:
            print(f"[SMOKE_TEST] ⚠️ Price fetch test error: {type(e).__name__}: {e}")
        
        # Cleanup
        print("[SMOKE_TEST] Cleaning up...")
        await client.close()
        
        print()
        print("=" * 80)
        print("[SMOKE_TEST] ✅ Smoke test PASSED")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"[SMOKE_TEST] ❌ Fatal error: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = asyncio.run(smoke_test())
    sys.exit(0 if success else 1)
