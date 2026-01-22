# Gold Price via cTrader Open API - Setup Guide

## Overview
This bot uses **strictly cTrader Open API** for gold (XAUUSD) prices. External APIs are disabled by default (`GOLD_CTRADER_ONLY=true`).

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

Required packages:
- `service_identity>=24.1.0` - TLS hostname verification
- `pyopenssl>=24.0.0` - SSL/TLS support
- `cryptography>=42.0.0` - Cryptographic primitives

### 2. Configure Environment Variables

Add to `.env`:
```env
# Required
CTRADER_IS_DEMO=true
CTRADER_ACCOUNT_ID=44749280
CTRADER_CLIENT_ID=your_client_id
CTRADER_CLIENT_SECRET=your_client_secret
CTRADER_ACCESS_TOKEN=your_access_token
CTRADER_REFRESH_TOKEN=your_refresh_token

# Optional (defaults provided)
CTRADER_DEMO_WS_URL=wss://demo.ctraderapi.com:5035
CTRADER_LIVE_WS_URL=wss://live.ctraderapi.com:5035
GOLD_CTRADER_ONLY=true

# Optional: Manual symbol ID override (if auto-detection fails)
CTRADER_GOLD_SYMBOL_ID=123456
```

### 3. Verify Configuration

On startup, the bot will print:
```
[ENV_DIAGNOSTIC] cTrader Configuration Keys Status
  CTRADER_IS_DEMO: [OK] or [MISSING]
  CTRADER_ACCOUNT_ID: [OK] or [MISSING]
  ...
```

### 4. Debug Gold Symbol

If gold symbol is not found automatically, use Telegram command:
```
/debug_gold
```

This will:
1. Connect to cTrader
2. Authenticate (ApplicationAuth + AccountAuth)
3. Request symbols list
4. Find gold-related symbols (XAU, GOLD, METAL)
5. Show top 20 matches with symbol IDs
6. Recommend best match

Example output:
```
🔍 **GOLD Symbol Debug Results**
📊 Total symbols: 1500
🔎 Found 3 gold-related symbols:

1. **XAUUSD** (ID: 123456)
2. **XAUUSDm** (ID: 123457)
3. **GOLD** (ID: 123458)

✅ **Recommended:** XAUUSD (ID: 123456)

💡 Set in .env: CTRADER_GOLD_SYMBOL_ID=123456
```

### 5. Check Connection Status

The bot logs detailed WebSocket events:
```
[GOLD_CTRADER] [WS_EVENT] DNS resolution: demo.ctraderapi.com...
[GOLD_CTRADER] [WS_EVENT] DNS resolved: demo.ctraderapi.com -> 1.2.3.4
[GOLD_CTRADER] [WS_EVENT] TCP precheck: connecting to demo.ctraderapi.com:5035...
[GOLD_CTRADER] [WS_EVENT] TCP precheck OK: demo.ctraderapi.com:5035 is reachable
[GOLD_CTRADER] [WS_EVENT] WebSocket handshake starting...
[GOLD_CTRADER] [WS_EVENT] WebSocket OPEN - connection established
[GOLD_CTRADER] [WS_EVENT] onMessage #1: payloadType=...
```

## Troubleshooting

### ENV_MISSING
**Problem:** Keys not loaded from `.env`
**Solution:**
1. Check `.env` file exists in project root
2. Run `python tools/env_doctor.py` to diagnose encoding/BOM issues
3. Verify keys are set (no typos, no extra spaces)

### WS_CONNECT_FAILED
**Problem:** WebSocket handshake timeout
**Diagnostics:**
- Check TCP precheck status (should be OK)
- Check firewall/proxy settings
- Verify `CTRADER_DEMO_WS_URL` or `CTRADER_LIVE_WS_URL` is correct
- Check if `service_identity` is installed

**Solution:**
```bash
pip install service_identity pyopenssl cryptography
```

### AUTH_FAILED
**Problem:** ApplicationAuth or AccountAuth failed
**Diagnostics:**
- Check `CTRADER_CLIENT_ID` and `CTRADER_CLIENT_SECRET` are correct
- Check `CTRADER_ACCESS_TOKEN` is valid (not expired)
- Check `CTRADER_ACCOUNT_ID` matches the account for the access token

### SYMBOL_NOT_FOUND
**Problem:** Gold symbol (XAUUSD) not found in symbols list
**Solution:**
1. Run `/debug_gold` command in Telegram
2. Check if any gold-related symbols exist
3. If found, set `CTRADER_GOLD_SYMBOL_ID` in `.env` with the symbol ID
4. Restart bot

### NO_TICKS_RECEIVED
**Problem:** Subscription successful but no quotes received
**Diagnostics:**
- Check if symbol is tradeable
- Check if market is open
- Verify symbol ID is correct

## Architecture

### Connection Flow
1. **ENV Load** → Read configuration from `.env`
2. **DNS Resolution** → Resolve hostname to IP
3. **TCP Precheck** → Test raw TCP connection (5s timeout)
4. **WebSocket Handshake** → TLS + WebSocket upgrade (60s timeout, 3 retries)
5. **ApplicationAuth** → Authenticate application (15s timeout)
6. **AccountAuth** → Authenticate account (15s timeout)
7. **Symbol Resolution** → Request symbols list, find gold symbol (20s timeout)
8. **Subscribe** → Subscribe to gold symbol quotes
9. **First Tick** → Wait for first valid quote (20s timeout)

### Error Codes
- `ENV_MISSING` - Configuration keys not found
- `WS_DNS_ERROR` - DNS resolution failed
- `CTRADER_TCP_BLOCKED` - TCP connection blocked (firewall/proxy)
- `CTRADER_WS_CONNECT_FAILED` - WebSocket handshake timeout
- `AUTH_TIMEOUT` - ApplicationAuth/AccountAuth timeout
- `ACCOUNT_AUTH_FAILED` - Account authentication failed
- `SYMBOL_LIST_FAILED` - Failed to get symbols list
- `SYMBOL_NOT_FOUND` - Gold symbol not found (use `/debug_gold`)
- `SYMBOL_PARSE_ERROR` - Error parsing symbols list
- `SUBSCRIBE_FAILED` - Failed to subscribe to symbol
- `NO_TICKS_RECEIVED` - No quotes received after subscription

## Testing

### Test Connection
```bash
python -c "from config import Config; cfg = Config.get_ctrader_config(); print(f'WS URL: {cfg.get_ws_url()[0]}')"
```

### Test ENV Loading
```bash
python tools/env_doctor.py
```

### Test Gold Symbol Resolution
1. Start bot
2. Send `/debug_gold` in Telegram
3. Check output for gold symbols

## Notes

- **Strict Mode:** `GOLD_CTRADER_ONLY=true` disables all external APIs
- **Defaults:** If `CTRADER_DEMO_WS_URL` is missing, uses `wss://demo.ctraderapi.com:5035`
- **Manual Override:** Set `CTRADER_GOLD_SYMBOL_ID` to bypass auto-detection
- **Logging:** All WebSocket events are logged with `[WS_EVENT]` prefix for easy filtering
