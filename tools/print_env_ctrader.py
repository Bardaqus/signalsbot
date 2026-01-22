#!/usr/bin/env python3
"""
Print cTrader environment variables for diagnostics
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Load .env the same way as config.py
from dotenv import load_dotenv

dotenv_path = project_root / ".env"
config_live_path = project_root / "config_live.env"

print("=" * 80)
print("CTRADER ENV Variables Diagnostic")
print("=" * 80)
print(f"Project root: {project_root}")
print(f"dotenv_path: {dotenv_path} (exists={dotenv_path.exists()})")
print(f"config_live_path: {config_live_path} (exists={config_live_path.exists()})")
print(f"cwd: {os.getcwd()}")
print()

# Load .env
print("Loading .env...")
env_loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
print(f"load_dotenv returned: {env_loaded}")
print()

# Load config_live.env if exists
if config_live_path.exists():
    print("Loading config_live.env...")
    live_loaded = load_dotenv(dotenv_path=config_live_path, override=True)
    print(f"load_dotenv returned: {live_loaded}")
    print()

# Print all CTRADER_* and GOLD_CTRADER_ONLY keys
ctrader_keys = [
    'CTRADER_IS_DEMO',
    'CTRADER_ACCOUNT_ID',
    'CTRADER_CLIENT_ID',
    'CTRADER_CLIENT_SECRET',
    'CTRADER_ACCESS_TOKEN',
    'CTRADER_REFRESH_TOKEN',
    'CTRADER_DEMO_WS_URL',
    'CTRADER_LIVE_WS_URL',
    'CTRADER_GOLD_SYMBOL_ID',
    'GOLD_CTRADER_ONLY'
]

print("=" * 80)
print("CTRADER Environment Variables:")
print("=" * 80)

for key in ctrader_keys:
    value = os.getenv(key)
    if value is None:
        print(f"{key}: None (not set)")
    else:
        value_str = str(value)
        length = len(value_str)
        # Show preview for sensitive keys
        if key in ['CTRADER_CLIENT_ID', 'CTRADER_CLIENT_SECRET', 'CTRADER_ACCESS_TOKEN', 'CTRADER_REFRESH_TOKEN']:
            preview = value_str[:8] + "..." if length > 8 else value_str
            print(f"{key}: {repr(value)} (length={length}, preview={preview})")
        else:
            print(f"{key}: {repr(value)} (length={length})")

print()
print("=" * 80)
print("Raw os.environ check (all CTRADER_* keys):")
print("=" * 80)
ctrader_env_keys = [k for k in os.environ.keys() if k.startswith('CTRADER_') or k == 'GOLD_CTRADER_ONLY']
if ctrader_env_keys:
    for key in sorted(ctrader_env_keys):
        value = os.environ[key]
        print(f"{key}: {repr(value)}")
else:
    print("No CTRADER_* keys found in os.environ")

print()
print("=" * 80)
