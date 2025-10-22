# 🤖 Advanced Trading Signals Bot

A comprehensive Python bot that generates both **forex** and **crypto** trading signals with interactive Telegram controls. Features automatic signal generation, manual override capabilities, real-time price data, and comprehensive reporting.

## ✨ Features

### 🎯 **Signal Generation**
- **📊 Forex Signals**: 5 signals per day (9 pairs available)
- **🪙 Crypto Signals**: 5 signals per day (10 pairs available)
- **🚫 Duplicate Prevention**: No same pair twice per day
- **📈 Smart Distribution**: 73% BUY / 27% SELL for crypto
- **⏰ Random Intervals**: 2-5 hours between signals

### 📱 **Interactive Controls**
- **🎮 Telegram Buttons**: Manual signal generation via buttons
- **📊 Real-Time Status**: Check current signals and active pairs
- **📈 Performance Reports**: 24h and 7d analytics
- **🔐 User Authorization**: Secure access control
- **🔄 Manual Override**: Send additional signals anytime

### 💰 **Real-Time Data**
- **📊 Forex Prices**: Live data from forex APIs
- **🪙 Crypto Prices**: Real-time Binance public API
- **🛡️ Risk Management**: Automatic SL/TP calculation
- **📈 Multi-TP Levels**: 3 take profit levels for crypto
- **🔄 Signal Tracking**: Monitors TP hits and sends notifications

### 📊 **Reporting & Analytics**
- **📅 Daily Summaries**: 14:30 GMT (24h results)
- **📈 Weekly Summaries**: Friday 14:30 GMT (7 days results)
- **📋 Active Pairs Tracking**: Shows which pairs are active
- **📊 Performance Analytics**: BUY/SELL distribution tracking
- **👤 User Reports**: Sent to authorized users

## 📊 Signal Formats

### Forex Signal
```
EURUSD BUY 1.1633
SL 1.1623
TP 1.1643
```

### Crypto Signal
```
BTCUSDT BUY
Entry: 108014.98
SL: 105853.68
TP1: 110175.28
TP2: 112335.58
TP3: 114495.88
```

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/Bardaqus/signalsbot.git
cd signalsbot
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Bot Token

Edit the bot token in your preferred bot file:

```python
BOT_TOKEN = "your_telegram_bot_token"
FOREX_CHANNEL = "-1001286609636"  # Your forex channel
CRYPTO_CHANNEL = "-1002978318746"  # Your crypto channel
```

### 3. Run the Bot

#### 🎯 **Recommended: Working Combined Bot**
```bash
python3 start_working_combined_bot.py
```
**Best for production use:**
- Automatic signal generation (2-5 hour intervals)
- Interactive Telegram buttons for manual control
- Duplicate pair prevention
- Daily and weekly summary reports
- Real-time price data from live APIs
- Fixed asyncio issues with threading

## 🔧 Configuration

### Telegram Setup
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Add the bot to your channels as an admin
3. Get your channel IDs (start with -100)
4. **For interactive features**: Send `/start` to your bot to access control panel

### API Configuration
- **Forex**: Uses free public APIs (no API key needed)
- **Crypto**: Uses Binance public API (no API key needed)
- **Real-time**: All prices fetched from live market data

## 🎯 How It Works

1. **Automatic Generation**: Bot runs 24/7, sending signals every 2-5 hours
2. **Real-Time Pricing**: Fetches current market prices for accurate entry points
3. **Duplicate Prevention**: Never sends signals for the same pair twice per day
4. **Risk Management**: Calculates SL/TP based on real market conditions
5. **Interactive Control**: Manual override via Telegram buttons
6. **Smart Distribution**: Maintains 73% BUY / 27% SELL ratio for crypto
7. **Comprehensive Reporting**: Daily and weekly performance summaries

## 📊 Supported Pairs

### Forex (9 pairs)
- **Major Pairs**: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF
- **Cross Pairs**: GBPCAD, GBPNZD
- **Commodities**: XAUUSD (Gold)

### Crypto (10 pairs)
- **Major**: BTCUSDT, ETHUSDT, BNBUSDT
- **Altcoins**: ADAUSDT, SOLUSDT, XRPUSDT, DOTUSDT, DOGEUSDT, AVAXUSDT, MATICUSDT

## 📁 Bot Variants

### 🎯 **Production Bots**
- `working_combined_bot.py` - **Main production bot** (recommended)
- `automatic_signals_bot.py` - Automatic signals only
- `simple_interactive_bot.py` - Interactive buttons only

### 🔧 **Legacy Bots**
- `bot.py` - Original forex bot
- `crypto_bot.py` - Original crypto bot
- `combined_bot.py` - Combined features (legacy)

### 📊 **Data Files**
- `working_combined_signals.json` - Signal tracking (auto-generated)
- `performance.json` - Performance data (auto-generated)
- `requirements.txt` - Python dependencies

## 🚀 Running Modes

### 🎯 **Recommended: Working Combined Bot**
```bash
python3 start_working_combined_bot.py
```
**Best for production use:**
- Automatic signal generation (2-5 hour intervals)
- Interactive Telegram buttons for manual control
- Duplicate pair prevention
- Daily and weekly summary reports
- Real-time price data from live APIs
- Fixed asyncio issues with threading

### 🤖 **Automatic Only**
```bash
python3 start_automatic_bot.py
```
**For automatic signals only:**
- Sends signals every 2-5 hours
- Daily and weekly reports
- No interactive features

### 📱 **Interactive Only**
```bash
python3 start_simple_interactive_bot.py
```
**For manual control only:**
- Telegram buttons for signal generation
- Status and report checking
- No automatic signals

### 🔧 **Legacy Modes**
```bash
python3 start_bot.py          # Original forex bot
python3 start_crypto_bot.py   # Original crypto bot
```

## 📋 Requirements

- **Python 3.7+**
- **Telegram Bot Token** (from @BotFather)
- **Internet connection**
- **No API keys needed** (uses public APIs)

## 🎮 Interactive Features

### Telegram Control Panel
Send `/start` to your bot to access:

```
🤖 Working Combined Trading Signals Bot Control Panel

📊 Send Forex Signal    🪙 Send Crypto Signal
📈 Forex Status         🪙 Crypto Status
📊 Forex Report 24h     🪙 Crypto Report 24h
📊 Forex Report 7d      🪙 Crypto Report 7d
🔄 Refresh
```

### Authorized Users
- **615348532** - Primary user
- **501779863** - Secondary user

## 📊 Performance Reports

### Daily Summary (14:30 GMT)
```
📊 Daily Trading Signals Summary (24h)
📅 Date: 2025-01-21

📈 Forex Signals
• Total: 5/5
• BUY: 3, SELL: 2
• Channel: -1001286609636

🪙 Crypto Signals
• Total: 5/5
• BUY: 4 (80.0%), SELL: 1 (20.0%)
• Target: 73% BUY / 27% SELL
• Channel: -1002978318746
```

### Weekly Summary (Friday 14:30 GMT)
- 7-day performance overview
- BUY/SELL distribution analysis
- Channel performance metrics

## 🔧 Troubleshooting

### Common Issues
- **"You are not authorized"** - Check if your user ID is in ALLOWED_USERS
- **"All pairs already have active signals"** - Normal when all pairs used
- **"Could not get real price"** - Check internet connection
- **Event loop errors** - Use `working_combined_bot.py` (fixed with threading)

### Getting Help
1. Check the comprehensive guides in the repository
2. Review the troubleshooting sections
3. Ensure proper bot token configuration
4. Verify channel permissions

## 📚 Documentation

- `UPDATED_WORKING_BOT_GUIDE.md` - Complete guide for the main bot
- `WORKING_COMBINED_BOT_GUIDE.md` - Detailed feature explanations
- `AUTOMATIC_BOT_GUIDE.md` - Automatic signals guide
- `FINAL_INTERACTIVE_BOT_GUIDE.md` - Interactive features guide

## 🎉 Features Summary

✅ **Automatic signal generation** with 2-5 hour intervals  
✅ **Interactive Telegram buttons** for manual control  
✅ **Duplicate pair prevention** (no same pair twice per day)  
✅ **Real-time price data** from live APIs  
✅ **Daily and weekly reports** with analytics  
✅ **73% BUY / 27% SELL** ratio for crypto  
✅ **Fixed asyncio issues** with threading  
✅ **User authorization** system  
✅ **Comprehensive documentation**  

## 📄 License

MIT License - feel free to use and modify!

---

**🚀 Ready to start? Run `python3 start_working_combined_bot.py` and enjoy your advanced trading signals bot!**

