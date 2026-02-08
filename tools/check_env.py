#!/usr/bin/env python3
"""
Check environment configuration and cTrader config
Exit code 0 if all required fields are present, 1 otherwise
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Load env FIRST
from env_loader import load_env
load_env(project_root)

# Now import Config
from config import Config

print("=" * 80)
print("[CHECK_ENV] Testing Config.get_ctrader_config()")
print("=" * 80)

try:
    ctrader_config = Config.get_ctrader_config()
    
    print("\nConfiguration values:")
    print(f"  is_demo: {ctrader_config.is_demo} (source: {ctrader_config.source_map.get('is_demo', 'UNKNOWN')})")
    print(f"  account_id: {ctrader_config.account_id} (source: {ctrader_config.source_map.get('account_id', 'UNKNOWN')})")
    
    # Get WS URL
    try:
        ws_url, ws_source = ctrader_config.get_ws_url()
        print(f"  ws_url: {ws_url} (source: {ws_source})")
    except Exception as e:
        print(f"  ws_url: ERROR - {e}")
        ws_url = None
        ws_source = "ERROR"
    
    print(f"  client_id: {'[SET]' if ctrader_config.client_id else '[MISSING]'} (source: {ctrader_config.source_map.get('client_id', 'UNKNOWN')})")
    print(f"  client_secret: {'[SET]' if ctrader_config.client_secret else '[MISSING]'} (source: {ctrader_config.source_map.get('client_secret', 'UNKNOWN')})")
    print(f"  access_token: {'[SET]' if ctrader_config.access_token else '[MISSING]'} (source: {ctrader_config.source_map.get('access_token', 'UNKNOWN')})")
    print(f"  refresh_token: {'[SET]' if ctrader_config.refresh_token else '[MISSING]'} (source: {ctrader_config.source_map.get('refresh_token', 'UNKNOWN')})")
    
    print("\nSource map:")
    for key, source in ctrader_config.source_map.items():
        print(f"  {key}: {source}")
    
    # Validate required fields
    print("\n" + "=" * 80)
    print("[CHECK_ENV] Validation")
    print("=" * 80)
    
    required_fields = {
        'account_id': ctrader_config.account_id > 0,
        'ws_url': ws_url is not None and ws_source != 'ERROR',
        'is_demo': ctrader_config.is_demo is not None,
        'client_id': bool(ctrader_config.client_id),
        'client_secret': bool(ctrader_config.client_secret),
        'access_token': bool(ctrader_config.access_token),
    }
    
    all_ok = True
    for field, is_ok in required_fields.items():
        status = "OK" if is_ok else "MISSING"
        print(f"  {field}: {status}")
        if not is_ok:
            all_ok = False
    
    print()
    if all_ok:
        print("[CHECK_ENV] SUCCESS: All required fields are present")
        sys.exit(0)
    else:
        print("[CHECK_ENV] FAILURE: Some required fields are missing")
        print("  -> Check .env file and ensure CTRADER_* keys are set correctly")
        sys.exit(1)
        
except Exception as e:
    print(f"[CHECK_ENV] ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
