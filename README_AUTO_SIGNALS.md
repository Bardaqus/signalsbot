# Auto Signals Bot 🤖📈

**Automated Trading Signals Bot for Private Channel**

This bot automatically generates and sends trading signals every 4 minutes to your private Telegram channel, while simultaneously executing trades on your cTrader demo account.

## 🎯 Features

- **Automatic Signal Generation**: Every 4 minutes
- **Random Major Pairs**: 15 major currency pairs
- **Fixed Risk Management**: 30 pips SL, 50 pips TP
- **Dual Execution**: Sends to Telegram + Executes on cTrader
- **Real-time Trading**: Live demo account integration

## 📊 Configuration

**Your Setup:**
- **Telegram Channel**: https://t.me/+ZaJCtmMwXJthYzJi
- **Bot Token**: 7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY
- **cTrader Demo Account**: 9615885
- **Client ID**: 17667_hKA21RsOIjvIT45QG9Q9GTcot9Coiy7VeNOFaJQLFPeGyUQmBN
- **Client Secret**: amV88gmO8jTayhPVR7t4Q2VsRmEqbW8Xg5A4dOF2Ag1E13d4Jl

## 🚀 Quick Start

### 1. Start the Bot
```bash
cd /Users/dgramovich/Signals_bot
python3 start_auto_bot.py
```

### 2. Or Use the Startup Script
```bash
./run_auto_signals.sh
```

## 📱 Signal Format

Each signal will look like this:

```
🟢 **TRADING SIGNAL**

**Symbol:** EURUSD
**Direction:** BUY
**Entry Price:** 1.0650

**Stop Loss:** 1.0620
**Take Profit:** 1.0700

**Volume:** 1.0
**Comment:** Auto signal - 30 SL, 50 TP

📊 *Generated at 14:30:25*

🤖 *Auto-generated signal*
⏰ *Next signal in 4 minutes*
```

## 🎲 Trading Pairs

The bot randomly selects from these 15 major pairs:
- EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD
- USDCAD, NZDUSD, EURJPY, GBPJPY, EURGBP
- AUDJPY, CHFJPY, EURCHF, GBPCHF, AUDCAD

## ⚙️ Settings

- **Signal Interval**: 4 minutes (240 seconds)
- **Stop Loss**: 30 pips
- **Take Profit**: 50 pips
- **Volume**: 1.0 (standard lot)
- **Account**: Demo account for safety

## 🔧 Manual Commands

While the bot is running, you can also use these commands in the channel:

- `/start` - Bot information
- `/status` - Current statistics
- `/test` - Send a test signal immediately
- `/history` - View recent signal history

## 📊 Monitoring

The bot provides real-time statistics:
- Total signals sent
- Success rate
- Execution time
- Channel and account status

## 🛡️ Safety Features

- **Demo Account Only**: All trades on demo account
- **Fixed Risk**: Consistent 30/50 pip risk management
- **Error Handling**: Comprehensive error logging
- **Graceful Shutdown**: Ctrl+C to stop safely

## 📝 Logs

All activity is logged to:
- Console output (real-time)
- `logs/auto_signals_bot.log` (detailed logs)

## 🔄 How It Works

1. **Every 4 minutes**:
   - Bot selects random major pair
   - Generates BUY/SELL signal
   - Calculates SL/TP based on current price
   - Sends formatted message to Telegram channel
   - Executes trade on cTrader demo account
   - Logs execution results

2. **Signal Processing**:
   - Real-time price fetching from cTrader API
   - Automatic pip calculation for different pairs
   - Risk management with fixed SL/TP ratios
   - Dual execution (Telegram + Trading)

## 🚨 Important Notes

- **Demo Account**: All trades are on demo account for safety
- **4-Minute Interval**: Signals generated every 4 minutes
- **30/50 Pips**: Fixed risk management
- **Major Pairs Only**: Focus on liquid currency pairs
- **Private Channel**: Only your channel receives signals

## 🛠️ Troubleshooting

### Bot Not Starting
- Check `config_live.env` file exists
- Verify all credentials are correct
- Ensure Python dependencies are installed

### No Signals
- Check bot has admin rights in channel
- Verify channel ID is correct
- Check cTrader API credentials

### Trade Execution Issues
- Verify demo account credentials
- Check cTrader API connection
- Review logs for specific errors

## 📞 Support

If you encounter any issues:
1. Check the logs in `logs/auto_signals_bot.log`
2. Verify all credentials are correct
3. Ensure the bot has proper permissions in your channel

## 🎉 Ready to Trade!

Your auto signals bot is configured and ready to:
- Generate signals every 4 minutes
- Send to your private channel
- Execute trades on demo account
- Provide consistent 30/50 pip risk management

**Start the bot and watch the signals flow! 🚀**

