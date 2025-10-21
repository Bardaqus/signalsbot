# Interactive Buttons Bot Guide

Your bot now has **interactive buttons** for manual control! You can send signals manually and view reports directly through Telegram.

## 🎉 **What's New**

### **Interactive Buttons** 📱
- **📊 Send Forex Signal** - Generate and send forex signal with real price
- **🪙 Send Crypto Signal** - Generate and send crypto signal with real price
- **📈 Forex Status** - Check current forex signal count
- **🪙 Crypto Status** - Check current crypto signal count and distribution
- **📊 Forex Report 24h** - View 24-hour forex performance
- **🪙 Crypto Report 24h** - View 24-hour crypto performance
- **📊 Forex Report 7d** - View 7-day forex performance
- **🪙 Crypto Report 7d** - View 7-day crypto performance
- **🔄 Refresh** - Return to main menu

## 🚀 **How to Use**

### **Step 1: Start the Bot**
```bash
python3 start_interactive_working_bot.py
```

### **Step 2: Open Telegram**
1. Find your bot in Telegram
2. Send `/start` command
3. You'll see a control panel with buttons

### **Step 3: Use the Buttons**
The bot will show you these options:

```
🤖 Trading Signals Bot Control Panel

📊 Send Forex Signal    🪙 Send Crypto Signal
📈 Forex Status         🪙 Crypto Status
📊 Forex Report 24h     🪙 Crypto Report 24h
📊 Forex Report 7d      🪙 Crypto Report 7d
🔄 Refresh
```

## 🎯 **Button Functions**

### **📊 Send Forex Signal**
- Generates and sends 1 forex signal immediately
- Uses real price from forex API
- Checks daily limit (5 signals max)
- Sends to forex channel: `-1003118256304`

### **🪙 Send Crypto Signal**
- Generates and sends 1 crypto signal immediately
- Uses real price from Binance public API
- Maintains 73% BUY / 27% SELL ratio
- Sends to crypto channel: `-1002978318746`

### **📈 Forex Status**
Shows current forex signal status:
```
📈 Forex Signals Status

📊 Today's signals: 3/5
📤 Channel: -1003118256304
⏰ Last updated: 14:30:25 UTC

✅ Ready to generate more signals
```

### **🪙 Crypto Status**
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

### **📊 Forex Report 24h**
Shows 24-hour forex performance:
```
📊 Forex Performance Report (1 day)

📈 Total signals: 3
📊 BUY signals: 2
📊 SELL signals: 1

⏰ Generated: 2025-01-21 14:30:25 UTC
```

### **🪙 Crypto Report 24h**
Shows 24-hour crypto performance:
```
🪙 Crypto Performance Report (1 day)

📊 Total signals: 2
📈 BUY signals: 1 (50.0%)
📉 SELL signals: 1 (50.0%)
🎯 Target: 73% BUY / 27% SELL

⏰ Generated: 2025-01-21 14:30:25 UTC
```

### **📊 Forex Report 7d**
Shows 7-day forex performance (same format as 24h)

### **🪙 Crypto Report 7d**
Shows 7-day crypto performance (same format as 24h)

### **🔄 Refresh**
Returns to the main control panel

## 🔐 **Security**

- Only authorized users can use the bot
- Current authorized user: `615348532`
- To add more users, edit `ALLOWED_USERS` in `working_bot.py`

## 📊 **Signal Limits**

### **Forex Signals**
- **Daily limit**: 5 signals
- **Channel**: `-1003118256304`
- **Format**: Single TP/SL
- **Prices**: Real prices from forex APIs

### **Crypto Signals**
- **Daily limit**: 5 signals
- **Channel**: `-1002978318746`
- **Format**: 3 TP levels + 1 SL
- **Ratio**: 73% BUY / 27% SELL
- **Prices**: Real prices from Binance public API

## 🎯 **Use Cases**

### **Interactive Bot Only**
- **Best for**: Manual control only
- **Use when**: You want to generate signals manually
- **Features**: Buttons only, no automatic generation

### **Complete Bot (Automatic + Interactive)**
- **Best for**: Full automation with manual override
- **Use when**: You want both automatic and manual control
- **Features**: Everything included

## 🚀 **Quick Start**

### **Interactive Bot Only**
```bash
python3 start_interactive_working_bot.py
```

### **Complete Bot (Automatic + Interactive)**
```bash
python3 start_working_bot.py
```

## 📱 **Example Usage**

1. **Generate a forex signal**:
   - Click "📊 Send Forex Signal"
   - Bot generates and sends signal with real price
   - Shows updated count

2. **Check crypto status**:
   - Click "🪙 Crypto Status"
   - See current distribution
   - Check if more signals needed

3. **View performance**:
   - Click "📊 Forex Report 24h" or "🪙 Crypto Report 24h"
   - See 24-hour performance
   - Check BUY/SELL distribution

## 🎉 **Benefits**

- ✅ **Manual control**: Generate signals when you want
- ✅ **Real-time status**: Check counts and distribution
- ✅ **Performance tracking**: View reports instantly
- ✅ **Real prices**: All signals use live market prices
- ✅ **Flexible**: Use automatic, manual, or both
- ✅ **Secure**: Only authorized users can control
- ✅ **User-friendly**: Simple button interface

## 🔧 **Troubleshooting**

### **"You are not authorized"**
- Check if your user ID is in `ALLOWED_USERS`
- Current authorized user: `615348532`

### **"Signal limit reached"**
- Daily limit is 5 signals per type
- Wait until next day or check status

### **"Could not get real price"**
- Check internet connection
- API might be temporarily down
- Bot will retry automatically

## 🎯 **Ready to Use**

Your bot now has:
- ✅ **Interactive buttons** for manual control
- ✅ **Real prices** from live markets
- ✅ **Status monitoring** with distribution tracking
- ✅ **Performance reports** for 24h and 7d
- ✅ **Secure access** for authorized users only

**Just run `python3 start_interactive_working_bot.py` and send `/start` to your bot to see the control panel!** 🚀
