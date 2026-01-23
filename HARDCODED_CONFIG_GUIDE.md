# Hardcoded cTrader Configuration Guide

## Overview

The bot now uses **hardcoded cTrader configuration** instead of reading from `.env` file. This eliminates dependency on environment variable loading and ensures reliable operation.

## Configuration Source

All cTrader settings are defined in `config.py` at the top of the file:

```python
CTRADER_HARDCODED_ENABLED = True

HARDCODED_CTRADER_CONFIG = {
    'is_demo': True,
    'account_id': 44749280,
    'client_id': '17667_hKA21RsOIjvIT45QG9Q9GTcot9Coiy7VeNOFaJQLFPeGyUQmBN',
    'client_secret': 'amV88gmO8jTayhPVR7t4Q2VsRmEqbW8Xg5A4dOF2Ag1E13d4Jl',
    'access_token': 'n_SuXHNX4TlMyekW05N_yqwNy4Y_Zc3DAIwEXVrp2os',
    'refresh_token': 'UVNGZPSDSbB-Vi81R2DX8NANvIkESfE_yXnNS6z1RC4',
    'ws_url_demo': 'wss://demo.ctraderapi.com:5035',
    'ws_url_live': 'wss://live.ctraderapi.com:5035',
    'gold_ctrader_only': True,
    'gold_symbol_name': None,  # Auto-detect from symbol list
    'gold_symbol_id': None,    # Auto-detect from symbol list
}
```

## Key Features

1. **No .env dependency**: The bot does NOT read `CTRADER_*` keys from `.env` file
2. **Unified source**: Both Forex and Gold use the same cTrader configuration
3. **Strict cTrader-only for Gold**: `GOLD_CTRADER_ONLY=true` - no external APIs
4. **Source tracking**: All config values show `source: HARDCODED` in diagnostics

## Expected Logs on Startup

When the bot starts, you should see:

```
[ENV_DIAGNOSTIC] cTrader Configuration Keys Status
================================================================================
Mode: HARDCODED (CTRADER_HARDCODED_ENABLED=True)

Hardcoded values:
  CTRADER_IS_DEMO: [OK] (value: True)
  CTRADER_ACCOUNT_ID: [OK] (value: 44749280)
  CTRADER_DEMO_WS_URL: [OK] (value: wss://demo.ctraderapi.com:5035)
  CTRADER_LIVE_WS_URL: [OK] (value: wss://live.ctraderapi.com:5035)
  CTRADER_CLIENT_ID: [OK] (preview: 17667_hK...)
  CTRADER_CLIENT_SECRET: [OK] (preview: amV88gmO...)
  CTRADER_ACCESS_TOKEN: [OK] (preview: n_SuXHNX...)
  CTRADER_REFRESH_TOKEN: [OK] (preview: UVNGZPSD...)
  GOLD_CTRADER_ONLY: [OK] (value: True)

[OK] All critical keys are set (HARDCODED)
================================================================================

[GOLD_CTRADER] Config loaded from: HARDCODED
   account_id: 44749280
   is_demo: True
   ws_url: wss://demo.ctraderapi.com:5035 (source: HARDCODED)
```

## What Should NOT Appear

The following errors should **NOT** appear anymore:

- ❌ `CONFIG_MISSING_WS_URL: CTRADER_DEMO_WS_URL is not set`
- ❌ `CONFIG_INVALID_ACCOUNT_ID: CTRADER_ACCOUNT_ID is missing or invalid`
- ❌ `[INIT] Gold streamer DISABLED` (due to missing config)
- ❌ `Streamer not initialized` (due to config errors)
- ❌ `AttributeError: type object 'Config' has no attribute 'get_account_id_or_raise'`
- ❌ `UnboundLocalError: cannot access local variable 'Config'`

## Gold Streamer Behavior

- **Always enabled**: Gold streamer will attempt to connect to cTrader
- **No external APIs**: If cTrader is unavailable, gold signals will show `PRICE_UNAVAILABLE_CTRADER_ONLY` instead of falling back to external APIs
- **Detailed diagnostics**: If connection fails, logs will show exact reason (WS_CONNECT_TIMEOUT, AUTH_FAILED, SYMBOL_NOT_FOUND, etc.)

## Testing

To verify the configuration is working:

```bash
python -c "from config import Config; cfg = Config.get_ctrader_config(); print('account_id:', cfg.account_id); print('is_demo:', cfg.is_demo); print('gold_ctrader_only:', cfg.gold_ctrader_only); print('source:', cfg.source_map.get('account_id', 'UNKNOWN'))"
```

Expected output:
```
account_id: 44749280
is_demo: True
gold_ctrader_only: True
source: HARDCODED
```

## Disabling Hardcoded Config

To switch back to `.env`-based configuration:

1. Open `config.py`
2. Set `CTRADER_HARDCODED_ENABLED = False`
3. Ensure all required keys are in `.env` file

## Notes

- Other bot settings (Telegram token, channels, etc.) still use `.env` file
- Only cTrader-related configuration uses hardcoded values
- Tokens/secrets are never logged in full (only preview shown)
