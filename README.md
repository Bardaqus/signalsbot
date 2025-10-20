# Telegram Forex Signals Bot

A Python bot that generates intraday forex trading signals and posts them to a Telegram channel. The bot uses real-time price data from EODHD API and implements SMA-based signal generation with automatic profit tracking.

## Features

- 🎯 **4 Signals Per Day** - Generates up to 4 trading signals daily
- 📊 **Real-Time Prices** - Uses current market prices for entry points
- 🔄 **Signal Tracking** - Monitors TP hits and sends profit notifications
- 📱 **Telegram Integration** - Posts formatted signals to your channel
- 🛡️ **Risk Management** - Automatic SL/TP calculation based on ATR

## Signal Format

```
GBPUSD BUY 1.34230
SL 1.34213
TP 1.34265
```

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/Bardaqus/signalsbot.git
cd signalsbot
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API Keys

Set your API credentials as environment variables:

```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export TELEGRAM_CHANNEL_ID="-1003118256304"  # Your channel ID
export EODHD_API_TOKEN="your_eodhd_api_token"
```

Or edit the defaults in `bot.py` directly.

### 3. Run the Bot

```bash
python bot.py
```

## Configuration

### Telegram Setup
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Add the bot to your channel as an admin
3. Get your channel ID (starts with -100)

### EODHD API
1. Sign up at [EODHD](https://eodhd.com/)
2. Get your API token from the dashboard
3. Add it to your environment variables

## How It Works

1. **Signal Generation**: Uses 3/7 period SMA crossover with momentum filters
2. **Real-Time Pricing**: Fetches current market prices for accurate entry points
3. **Risk Management**: Calculates SL/TP based on ATR (Average True Range)
4. **Tracking**: Monitors active signals and sends profit notifications
5. **Daily Limit**: Stops at 4 signals per day to avoid overtrading

## Supported Pairs

- EURUSD, GBPUSD, USDJPY
- AUDUSD, USDCAD, USDCHF
- GBPCAD, GBPNZD

## Files

- `bot.py` - Main bot logic
- `requirements.txt` - Python dependencies
- `active_signals.json` - Signal tracking (auto-generated)
- `.gitignore` - Git ignore rules

## Requirements

- Python 3.7+
- Telegram Bot Token
- EODHD API Token
- Internet connection

## License

MIT License - feel free to use and modify!

