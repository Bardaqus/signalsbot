# Interactive Trading Signals Bot Guide

Your trading signals bot now has **interactive buttons** for manual control! You can generate signals on demand, check status, and view reports directly through Telegram.

## 🚀 **Available Bot Options**

### 1. **Complete Bot (RECOMMENDED)**
```bash
python3 start_complete_bot.py
```
**✅ Best choice** - Combines automatic + interactive features
- 🤖 **Automatic**: Generates signals every 5 minutes
- 📱 **Interactive**: Manual control via buttons
- 📊 **Full functionality**: Status, reports, manual signals

### 2. **Interactive Bot Only**
```bash
python3 start_interactive_bot.py
```
**✅ For manual control only** - No automatic generation
- 📱 **Interactive**: Manual control via buttons
- 🎯 **On-demand**: Generate signals when you want
- 📊 **Status monitoring**: Check counts and distribution

### 3. **Automatic Bot Only**
```bash
python3 start_unified_bot.py
```
**✅ For automatic only** - No interactive features
- 🤖 **Automatic**: Generates signals every 5 minutes
- 📊 **Background**: Runs without user interaction

## 📱 **How to Use Interactive Features**

### Step 1: Start the Bot
```bash
python3 start_complete_bot.py
```

### Step 2: Open Telegram
1. Find your bot in Telegram
2. Send `/start` command
3. You'll see a control panel with buttons

### Step 3: Use the Buttons
The bot will show you these options:

```
🤖 Complete Trading Signals Bot

📊 Send Forex Signal    🪙 Send Crypto Signal
📈 Forex Status         🪙 Crypto Status  
📊 Forex Report         🪙 Crypto Report
🔄 Refresh
```

## 🎯 **Button Functions**

### 📊 **Send Forex Signal**
- Generates and sends 1 forex signal immediately
- Checks daily limit (5 signals max)
- Sends to forex channel: `-1003118256304`

### 🪙 **Send Crypto Signal**
- Generates and sends 1 crypto signal immediately
- Maintains 73% BUY / 27% SELL ratio
- Sends to crypto channel: `-1002978318746`

### 📈 **Forex Status**
Shows current forex signal status:
```
📈 Forex Signals Status

📊 Today's signals: 3/5
📤 Channel: -1003118256304
⏰ Last updated: 14:30:25 UTC

✅ Ready to generate more signals
```

### 🪙 **Crypto Status**
Shows current crypto signal status:
```
🪙 Crypto Signals Status

📊 Today's signals: 2/5
📈 Distribution: BUY 1 (50.0%), SELL 1 (50.0%)
📤 Channel: -1002978318746
⏰ Last updated: 14:30:25 UTC

✅ Ready to generate more signals
🎯 Target: 73% BUY / 27% SELL
```

### 📊 **Forex Report**
Shows 24-hour forex performance:
```
📊 Forex Performance Report (24h)

GBPUSD +2.15% (tp1)
EURUSD -1.50% (sl)
USDJPY +3.20% (tp2)

📊 Summary:
Total signals: 3
In profit: 2
In loss: 1
Profit: 3.85%
```

### 🪙 **Crypto Report**
Shows 24-hour crypto performance:
```
🪙 Crypto Performance Report (24h)

BTCUSDT +2.15% (tp1)
ETHUSDT +4.32% (tp2)
ADAUSDT -2.00% (sl)

📊 Summary:
Total signals: 3
BUY signals: 2 (66.7%)
SELL signals: 1 (33.3%)
TP1 hits: 1
TP2 hits: 1
TP3 hits: 0
TP1→SL: 0
TP2→SL: 0
TP3→SL: 0
SL only: 1
Total profit: 4.47%
```

### 🔄 **Refresh**
Returns to the main control panel

## 🔐 **Security**

- Only authorized users can use the bot
- Current authorized user: `615348532`
- To add more users, edit `ALLOWED_USERS` in the bot files

## 📊 **Signal Limits**

### Forex Signals
- **Daily limit**: 5 signals
- **Channel**: `-1003118256304`
- **Format**: Single TP/SL

### Crypto Signals
- **Daily limit**: 5 signals
- **Channel**: `-1002978318746`
- **Format**: 3 TP levels + 1 SL
- **Ratio**: 73% BUY / 27% SELL

## 🎯 **Use Cases**

### **Complete Bot** (Recommended)
- **Best for**: Full automation with manual override
- **Use when**: You want both automatic and manual control
- **Features**: Everything included

### **Interactive Bot Only**
- **Best for**: Manual control only
- **Use when**: You want to generate signals manually
- **Features**: Buttons only, no automatic generation

### **Automatic Bot Only**
- **Best for**: Set and forget
- **Use when**: You want full automation
- **Features**: Background generation only

## 🚀 **Quick Start**

1. **Set up API credentials**:
   ```bash
   export BINANCE_API_KEY="your_binance_api_key"
   export BINANCE_API_SECRET="your_binance_api_secret"
   export TELEGRAM_BOT_TOKEN="your_bot_token"
   ```

2. **Start the complete bot**:
   ```bash
   python3 start_complete_bot.py
   ```

3. **Use the bot**:
   - Send `/start` to your bot
   - Use buttons to control signals
   - Check status and reports anytime

## 📱 **Example Usage**

1. **Generate a forex signal**:
   - Click "📊 Send Forex Signal"
   - Bot generates and sends signal
   - Shows updated count

2. **Check crypto status**:
   - Click "🪙 Crypto Status"
   - See current distribution
   - Check if more signals needed

3. **View performance**:
   - Click "📊 Forex Report" or "🪙 Crypto Report"
   - See 24-hour performance
   - Check BUY/SELL distribution

## 🎉 **Benefits**

- ✅ **Manual control**: Generate signals when you want
- ✅ **Real-time status**: Check counts and distribution
- ✅ **Performance tracking**: View reports instantly
- ✅ **Flexible**: Use automatic, manual, or both
- ✅ **Secure**: Only authorized users can control
- ✅ **User-friendly**: Simple button interface

Your trading signals bot is now fully interactive! 🚀
