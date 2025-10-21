# Running Both Forex and Crypto Bots

You have several options to run both forex and crypto signals simultaneously. Here are the different approaches:

## 🚀 Option 1: Unified Bot (Recommended)

**Run a single bot that handles both forex and crypto:**

```bash
python start_unified_bot.py
```

**Features:**
- ✅ Single process manages both forex and crypto
- ✅ Shared resources and error handling
- ✅ Easier to monitor and manage
- ✅ Both bots run every 5 minutes
- ✅ Automatic signal cleanup for both

## 🔄 Option 2: Parallel Bots

**Run both bots simultaneously in parallel:**

```bash
python run_both_bots.py
```

**Features:**
- ✅ Both bots run independently
- ✅ If one fails, the other continues
- ✅ Better isolation between forex and crypto
- ✅ Each bot has its own error handling

## 📊 Option 3: Separate Terminals

**Run each bot in its own terminal:**

**Terminal 1 (Forex):**
```bash
python start_bot.py
```

**Terminal 2 (Crypto):**
```bash
python start_crypto_bot.py
```

**Features:**
- ✅ Complete separation
- ✅ Easy to monitor each bot individually
- ✅ Can restart one without affecting the other

## 📋 Current Bot Configuration

### Forex Bot
- **Channel**: `-1003118256304`
- **Signals**: 5 per day
- **Pairs**: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, GBPCAD, GBPNZD, XAUUSD
- **Format**: Single TP/SL
- **Reports**: 14:00 GMT daily, Friday weekly

### Crypto Bot
- **Channel**: `-1002978318746`
- **Signals**: 5 per day
- **Pairs**: BTCUSDT, ETHUSDT, BNBUSDT, ADAUSDT, SOLUSDT, XRPUSDT, DOTUSDT, DOGEUSDT, AVAXUSDT, MATICUSDT
- **Format**: 3 TP levels + 1 SL
- **Reports**: 14:30 GMT daily, Friday weekly

## 🎯 Recommended Setup

**For Production Use:**
```bash
# Use the unified bot (Option 1)
python start_unified_bot.py
```

**For Development/Testing:**
```bash
# Use separate terminals (Option 3)
# Terminal 1: python start_bot.py
# Terminal 2: python start_crypto_bot.py
```

## 📊 Signal Output Examples

### Forex Signal
```
GBPUSD BUY 1.34230
SL 1.34213
TP 1.34265
```

### Crypto Signal
```
BTCUSDT BUY
Entry: 43250.500000
SL: 42385.490000
TP1: 44115.510000
TP2: 44980.520000
TP3: 45845.530000
```

## 🔧 Prerequisites

### For Forex Bot:
- ✅ EODHD API token (already configured)
- ✅ Telegram bot token (already configured)

### For Crypto Bot:
- ✅ Binance API key and secret
- ✅ Telegram bot token (same as forex)

### Environment Variables:
```bash
# Required for crypto bot
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"

# Already configured
export TELEGRAM_BOT_TOKEN="7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY"
```

## 📈 Performance Tracking

Both bots send reports to user ID `615348532`:

- **Forex Reports**: 14:00 GMT daily, Friday weekly
- **Crypto Reports**: 14:30 GMT daily, Friday weekly

## 🛠️ Monitoring

### Console Output
The unified bot shows:
```
⏰ 2025-01-21 10:30:00 UTC
📊 Today's signals:
  Forex: 3/5
  Crypto: 2/5
🎯 Need 2 more forex signals
🎯 Need 3 more crypto signals
```

### Log Files
- `active_signals.json` - Forex signals
- `crypto_signals.json` - Crypto signals
- `performance.json` - Forex performance
- `crypto_performance.json` - Crypto performance

## 🚨 Troubleshooting

### If Unified Bot Fails:
1. Check both API credentials
2. Verify Telegram bot permissions
3. Check network connectivity
4. Review console output for errors

### If One Bot Stops Working:
- Use Option 3 (separate terminals) to isolate the issue
- Check specific API credentials for the failing bot
- Restart only the affected bot

## 🎯 Quick Start

**To run both forex and crypto signals:**

1. **Set up Binance API** (if not already done):
   ```bash
   export BINANCE_API_KEY="your_api_key"
   export BINANCE_API_SECRET="your_api_secret"
   ```

2. **Run the unified bot**:
   ```bash
   python start_unified_bot.py
   ```

3. **Monitor the output** to ensure both bots are working

That's it! You'll now receive both forex and crypto signals in their respective channels. 🚀
