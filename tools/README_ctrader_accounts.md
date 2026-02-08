# cTrader Account List Diagnostic Tool

This diagnostic tool helps you identify the correct `DEMO_ACCOUNT_ID` (ctidTraderAccountId) for your cTrader Open API configuration.

## Purpose

When configuring the signals bot, you need to specify the `DEMO_ACCOUNT_ID` in your `.env` file. This tool connects to cTrader Open API and lists all available accounts, showing you which account ID to use.

## Prerequisites

1. **Python 3.7+** installed
2. **Required packages**:
   ```bash
   pip install grpcio grpcio-aio requests python-dotenv
   pip install --upgrade protobuf  # Important: protobuf >= 4.0.0 required
   ```
   
   **Note**: If you get `runtime_version` import errors, upgrade protobuf:
   ```bash
   pip install --upgrade protobuf
   # Or install specific version:
   pip install protobuf==4.25.0
   ```
3. **cTrader Application Credentials**:
   - `CLIENT_ID` - Your cTrader application client ID
   - `CLIENT_SECRET` - Your cTrader application client secret
   
   Get these from: https://openapi.ctrader.com (register your application)

## Configuration

### Required Environment Variables

Add these to your `.env` file (in the project root):

```env
# Required
CTRADER_CLIENT_ID=your_client_id_here
CTRADER_CLIENT_SECRET=your_client_secret_here

# Optional (will be obtained automatically if not set)
CTRADER_REDIRECT_URI=http://localhost:8080/callback
CTRADER_ACCESS_TOKEN=...  # Obtained via OAuth flow
CTRADER_REFRESH_TOKEN=...  # Obtained via OAuth flow
```

### Getting CLIENT_ID and CLIENT_SECRET

1. Go to https://openapi.ctrader.com
2. Register/log in to your account
3. Create a new application
4. Copy the `Client ID` and `Client Secret`
5. Add them to your `.env` file

## Usage

### Basic Usage

Run the script from the project root:

```bash
python tools/ctrader_accounts.py
```

### First Run (OAuth Authorization)

On first run, if you don't have an `ACCESS_TOKEN`:

1. The script will generate an authorization URL
2. Your browser will open automatically (or you'll see the URL in console)
3. Log in to your cTrader account
4. Authorize the application
5. You'll be redirected to a URL like: `http://localhost:8080/callback?code=AUTHORIZATION_CODE`
6. Copy the `code` parameter from the URL
7. Paste it into the script when prompted
8. The script will exchange the code for an access token

**Tip**: After first run, add the `CTRADER_ACCESS_TOKEN` and `CTRADER_REFRESH_TOKEN` to your `.env` file to avoid re-authorization.

### Subsequent Runs

If you already have `CTRADER_ACCESS_TOKEN` in your `.env`, the script will:
1. Use the existing token
2. Connect to cTrader
3. Authenticate the application
4. Retrieve and display the account list

## Example Output

```
================================================================================
🔍 cTrader Account List Diagnostic Tool
================================================================================

✅ Found access token in .env: n_SuXHNX4TlMyekW05N_yqwNy4Y...
🔌 Connecting to cTrader gRPC server...
   Server: demo.ctraderapi.com:5035
✅ Connected to cTrader gRPC server
🔐 Authenticating application...
   Client ID: 17667_hKA21RsOIjvIT...
✅ Application authentication successful
📊 Getting account list...
✅ Found 2 account(s)

================================================================================
📋 AVAILABLE ACCOUNTS
================================================================================

🟢 Account #1: DEMO
   Account ID (ctidTraderAccountId): 44749280
   Trader Login: 9615885
   Broker: IC Markets
   Broker Account: IC Markets - Demo
   Currency: USD
   Leverage: 1:500
   Balance: 10000.00 USD

🔴 Account #2: LIVE
   Account ID (ctidTraderAccountId): 12345678
   Trader Login: 8765432
   Broker: IC Markets
   Broker Account: IC Markets - Live
   Currency: USD
   Leverage: 1:100
   Balance: 5000.00 USD

================================================================================

💡 TO USE IN YOUR CONFIGURATION:

   For DEMO_ACCOUNT_ID, use one of these:
      DEMO_ACCOUNT_ID=44749280  # IC Markets Demo

   For LIVE accounts:
      LIVE_ACCOUNT_ID=12345678  # IC Markets Live

================================================================================
✅ Diagnostic completed successfully
```

## What to Copy

After running the script, copy the **Account ID (ctidTraderAccountId)** for your DEMO account and add it to your `.env`:

```env
DEMO_ACCOUNT_ID=44749280
```

Or if you prefer to use `CTRADER_ACCOUNT_ID`:

```env
CTRADER_ACCOUNT_ID=44749280
```

The bot will automatically use `CTRADER_ACCOUNT_ID` as a fallback if `DEMO_ACCOUNT_ID` is not set.

## Troubleshooting

### Error: "CTRADER_CLIENT_ID not found in .env"

**Solution**: Add `CTRADER_CLIENT_ID` to your `.env` file.

### Error: "Failed to connect to cTrader"

**Possible causes**:
- Network connectivity issues
- Firewall blocking gRPC connections
- cTrader API server is down

**Solution**: Check your internet connection and try again later.

### Error: "Application authentication failed"

**Possible causes**:
- Invalid `CLIENT_ID` or `CLIENT_SECRET`
- Credentials not properly set in `.env`

**Solution**: 
1. Verify your credentials at https://openapi.ctrader.com
2. Make sure there are no extra spaces in `.env` file
3. Restart the script

### Error: "Access token is required to get account list"

**Solution**: Complete the OAuth authorization flow (the script will guide you).

### Error: "Unexpected response type" when getting account list

**Possible causes**:
- Access token expired
- Access token invalid

**Solution**: 
1. Remove `CTRADER_ACCESS_TOKEN` from `.env`
2. Run the script again to get a new token
3. Update `.env` with the new token

### Error: "grpcio packages are required"

**Solution**: Install required packages:
```bash
pip install grpcio grpcio-aio requests python-dotenv
pip install --upgrade protobuf
```

### Error: "cannot import name 'runtime_version' from 'google.protobuf'"

**Cause**: Your protobuf version is too old. The generated protobuf files require protobuf >= 4.0.0.

**Solution**: Upgrade protobuf:
```bash
pip install --upgrade protobuf
# Or install specific version:
pip install protobuf==4.25.0
```

After upgrading, run the script again.

## Security Notes

- **Never commit your `.env` file** to version control
- Keep your `CLIENT_SECRET` and `ACCESS_TOKEN` secure
- The `ACCESS_TOKEN` expires after some time - you'll need to refresh it
- Use `REFRESH_TOKEN` to get a new `ACCESS_TOKEN` without re-authorization

## Related Files

- `config.py` - Configuration loader that reads from `.env`
- `ctrader_stream.py` - cTrader WebSocket client used by the bot
- `ctrader_api.py` - OAuth helper functions

## Support

If you encounter issues:
1. Check the error messages - they usually indicate what's wrong
2. Verify your `.env` configuration
3. Ensure all required packages are installed
4. Check cTrader API status: https://openapi.ctrader.com
