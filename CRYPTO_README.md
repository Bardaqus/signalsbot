# Crypto Signals Bot

A Python bot that generates short-term cryptocurrency trading signals using Binance data and posts them to a Telegram channel. The bot implements technical analysis with multiple take-profit levels and comprehensive performance tracking.

## Features

- 🎯 **3-5 Signals Per Day** - Generates up to 5 crypto trading signals daily
- 📊 **73% BUY / 27% SELL Ratio** - Maintains optimal signal distribution
- 🔄 **Multi-Level TP/SL** - 3 take-profit levels and 1 stop-loss per signal
- 📱 **Telegram Integration** - Posts formatted signals to your crypto channel
- 📈 **Performance Tracking** - Comprehensive result tracking and reporting
- ⏰ **Automated Reports** - Daily and weekly performance summaries

## Signal Format

```
BTCUSDT BUY
Entry: 43250.500000
SL: 42385.490000
TP1: 44115.510000
TP2: 44980.520000
TP3: 45845.530000
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Set up your environment variables:

```bash
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
```

Or create a `config.py` file based on `crypto_config.py`.

### 3. Binance API Setup

1. Create a Binance account at [binance.com](https://binance.com)
2. Go to API Management in your account settings
3. Create a new API key with read permissions
4. Copy your API key and secret

### 4. Telegram Setup

1. Create a bot using [@BotFather](https://t.me/botfather)
2. Add the bot to your crypto signals channel
3. Make the bot an admin with posting permissions
4. Update the channel ID in the configuration

## Usage

### One-time Run
```bash
python crypto_bot.py
```

### Continuous Monitoring (Recommended)
```bash
python start_crypto_bot.py
```

This runs the bot continuously, checking for signals every 5 minutes and ensuring 3-5 signals per day.

## Signal Generation Logic

The bot uses multiple technical indicators:

- **Moving Averages**: SMA 5, 10, 20
- **RSI**: Relative Strength Index (14 period)
- **MACD**: Moving Average Convergence Divergence
- **Bollinger Bands**: 20-period with 2 standard deviations

### Signal Conditions

**BUY Signals (73% target):**
- SMA 5 > SMA 10 > SMA 20
- RSI < 70
- MACD > MACD Signal
- Price > SMA 5

**SELL Signals (27% target):**
- SMA 5 < SMA 10 < SMA 20
- RSI > 30
- MACD < MACD Signal
- Price < SMA 5

### Signal Distribution Control

The bot automatically maintains a **73% BUY / 27% SELL** ratio by:
- Tracking daily signal distribution
- Preferring BUY signals when ratio is below 73%
- Preferring SELL signals when ratio is at or above 73%
- Using relaxed conditions when needed to maintain target ratio

## Risk Management

- **Stop Loss**: 2% from entry price
- **Take Profit Levels**:
  - TP1: 2% profit
  - TP2: 4% profit
  - TP3: 6% profit

## Performance Tracking

The bot tracks detailed results:

- **TP1 Hit**: First take-profit reached
- **TP2 Hit**: Second take-profit reached
- **TP3 Hit**: Third take-profit reached
- **TP1→SL**: TP1 hit, then stop-loss hit
- **TP2→SL**: TP2 hit, then stop-loss hit
- **TP3→SL**: TP3 hit, then stop-loss hit
- **SL Only**: Stop-loss hit without any TP

## Reporting

### Daily Reports (14:30 GMT)
- 24-hour performance summary
- Sent to user ID: 615348532

### Weekly Reports (Friday 14:30 GMT)
- 7-day performance summary
- Sent to user ID: 615348532

## Supported Cryptocurrencies

- BTCUSDT (Bitcoin)
- ETHUSDT (Ethereum)
- BNBUSDT (Binance Coin)
- ADAUSDT (Cardano)
- SOLUSDT (Solana)
- XRPUSDT (Ripple)
- DOTUSDT (Polkadot)
- DOGEUSDT (Dogecoin)
- AVAXUSDT (Avalanche)
- MATICUSDT (Polygon)

## Files

- `crypto_bot.py` - Main crypto signals bot
- `continuous_crypto_bot.py` - Continuous monitoring bot
- `start_crypto_bot.py` - Startup script
- `crypto_config.py` - Configuration template
- `crypto_signals.json` - Active signals storage
- `crypto_performance.json` - Performance tracking data

## Error Handling

The bot includes comprehensive error handling:
- API rate limiting
- Network connectivity issues
- Invalid data responses
- Automatic retries with exponential backoff

## Security Notes

- Keep your API keys secure
- Use environment variables for sensitive data
- Regularly rotate your API keys
- Monitor your API usage limits

## Troubleshooting

### Common Issues

1. **Binance API Errors**: Check your API key permissions
2. **Telegram Errors**: Verify bot token and channel permissions
3. **No Signals Generated**: Check market conditions and signal criteria
4. **Performance Issues**: Monitor API rate limits

### Logs

The bot provides detailed console output for monitoring:
- Signal generation attempts
- TP/SL hit notifications
- Error messages and retries
- Performance report status

## Support

For issues or questions:
1. Check the console output for error messages
2. Verify your API credentials
3. Ensure proper Telegram bot setup
4. Review the configuration settings
