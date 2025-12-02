# cTrader Indices Finder

This script helps you find the correct ticker names for indices (S&P 500, NASDAQ, DAX, etc.) in your cTrader broker account.

## Problem

Different brokers name indices differently:
- S&P 500: `US500`, `.US500`, `SPX500`, `SP500`
- NASDAQ: `NAS100`, `US100`, `NDX`, `.NAS100`
- DAX: `DE30`, `.DE30`, `DAX`

This script fetches all available symbols from your cTrader account and filters for indices, showing you the exact symbol names your broker uses.

## Prerequisites

1. **cTrader API Credentials**:
   - `CTRADER_CLIENT_ID`
   - `CTRADER_CLIENT_SECRET`
   - `CTRADER_ACCESS_TOKEN`
   - `DEMO_ACCOUNT_ID` (or `LIVE_ACCOUNT_ID`)

2. **Protobuf Files**: The script uses `ctrader_service_pb2` which should include `ProtoOASymbolsListReq` and `ProtoOASymbolsListRes`.

   The script automatically uses `ProtoOASymbols_pb2.py` which has been generated from `ProtoOASymbols.proto`.
   
   If you get an error about missing `ProtoOASymbolsListReq`, regenerate the symbols proto file:

   ```bash
   # Install grpc-tools if not already installed
   pip3 install grpcio-tools
   
   # Regenerate symbols protobuf file (this should already be done)
   python3 -m grpc_tools.protoc --proto_path=. --python_out=. ProtoOASymbols.proto
   ```
   
   **Note**: The main `ProtoOA.proto` file has duplicate field definitions and cannot be regenerated. 
   The script uses a separate clean `ProtoOASymbols.proto` file for symbols messages.

## Usage

1. **Set up your credentials** in `.env` or `config_live.env`:
   ```env
   CTRADER_CLIENT_ID=your_client_id
   CTRADER_CLIENT_SECRET=your_client_secret
   CTRADER_ACCESS_TOKEN=your_access_token
   DEMO_ACCOUNT_ID=your_account_id
   ```

2. **Run the script**:
   ```bash
   python3 list_ctrader_indices.py
   ```

## Output

The script will display a table like this:

```
====================================================================================================
INDICES FOUND IN YOUR cTRADER ACCOUNT
====================================================================================================
Symbol ID    | Symbol Name              | Description                    | Asset Class          | Enabled
----------------------------------------------------------------------------------------------------
12345678     | US500                    | S&P 500                        | S&P 500              | Yes
12345679     | .US500                   | S&P 500                        | S&P 500              | Yes
12345680     | NAS100                   | NASDAQ 100                      | NASDAQ 100           | Yes
12345681     | DE30                     | DAX 30                         | DAX 30               | Yes
====================================================================================================

Total indices found: 4

💡 Tip: Use the 'Symbol Name' column value in your config file
   Example: If you see 'US500', use 'US500' in your symbol subscription
```

## How It Works

1. **Connects** to cTrader gRPC server (demo or live)
2. **Authenticates** using your application credentials and access token
3. **Requests** all available symbols via `ProtoOASymbolsListReq`
4. **Filters** symbols by common index patterns:
   - `500`, `US500`, `SPX`, `SP500` → S&P 500
   - `NAS`, `NDX`, `US100`, `NAS100` → NASDAQ 100
   - `DE30`, `DAX` → DAX 30
   - `UK100`, `FTSE` → FTSE 100
   - `FR40`, `CAC` → CAC 40
   - `JP225`, `NIKKEI` → Nikkei 225
   - And more...
5. **Displays** results in a clean table format

## Troubleshooting

### Error: "ProtoOASymbolsListReq not found"

**Solution**: Regenerate protobuf files:
```bash
python3 -m grpc_tools.protoc --python_out=. --grpc_python_out=. ProtoOA.proto
```

### Error: "Authentication failed"

**Solution**: Check your credentials:
- Verify `CTRADER_CLIENT_ID` and `CTRADER_CLIENT_SECRET` are correct
- Verify `CTRADER_ACCESS_TOKEN` is valid and not expired
- Verify `DEMO_ACCOUNT_ID` matches your account

### Error: "No indices found"

**Possible reasons**:
- Your broker doesn't offer indices
- The index symbols use different naming conventions
- Try running the script and check all symbols (modify the filter if needed)

### Error: "Connection failed"

**Solution**:
- Check your internet connection
- Verify the server URL (demo vs live)
- Check if cTrader API is accessible from your network

## Customization

### Change Server (Demo vs Live)

Edit `list_ctrader_indices.py`:
```python
# For demo accounts
self.server_url = "demo.ctraderapi.com:5035"

# For live accounts
self.server_url = "live.ctraderapi.com:5035"
```

### Add More Index Patterns

Edit the `_is_index_symbol()` method to add more patterns:
```python
index_keywords = [
    '500',      # S&P 500
    'US500',    # S&P 500
    # Add your custom patterns here
    'CUSTOM',   # Your custom index
]
```

### Show All Symbols (Not Just Indices)

Modify `get_indices()` to return all symbols:
```python
# Remove the filter
for symbol in symbols_res.symbol:
    indices.append({...})  # Add all symbols, not just indices
```

## Example Output Interpretation

If you see:
- `Symbol Name: US500` → Use `"US500"` in your code
- `Symbol Name: .US500` → Use `".US500"` in your code
- `Symbol Name: SPX500` → Use `"SPX500"` in your code

The **Symbol ID** is the numeric identifier you can use instead of the symbol name if needed.

## Next Steps

After finding the correct symbol names:

1. **Update your config** with the symbol names:
   ```python
   INDEX_SYMBOLS = ["US500", "NAS100", "DE30"]
   ```

2. **Use in your subscription code**:
   ```python
   await subscribe_to_symbol("US500")  # Use the exact name from the table
   ```

3. **Test** with a small position first to verify the symbol works correctly.

