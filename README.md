# Signals Bot 🤖📈

A Telegram bot that automatically sends trading signals to channels and executes trades via cTrader Open API.

## Features

- **Telegram Integration**: Send trading signals to multiple channels
- **cTrader API**: Execute trades automatically on IC Markets demo accounts
- **Channel Management**: Link channels to specific trading accounts
- **Signal Processing**: Format and distribute trading signals with EP, SL, TP
- **Real-time Execution**: Place trades automatically when signals are generated

## Project Structure

```
Signals_bot/
├── config.py              # Configuration management
├── ctrader_api.py         # cTrader Open API integration
├── models.py              # Data models for signals and accounts
├── signal_processor.py    # Signal processing and channel management
├── telegram_bot.py        # Main Telegram bot implementation
├── main.py                # Application entry point
├── test_bot.py            # Test script
├── requirements.txt       # Python dependencies
├── config_example.env     # Environment variables template
├── data/                  # Configuration and data storage
└── logs/                  # Application logs
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `config_example.env` to `.env` and fill in your credentials:

```bash
cp config_example.env .env
```

Edit `.env` file:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here

# cTrader API Configuration
CTRADER_CLIENT_ID=your_client_id_here
CTRADER_CLIENT_SECRET=your_client_secret_here
CTRADER_REDIRECT_URI=http://localhost:8080/callback

# Demo Account Configuration
DEMO_ACCOUNT_ID=your_demo_account_id

# Channel Configuration
TEST_CHANNEL_ID=@your_test_channel

# Logging
LOG_LEVEL=INFO
```

### 3. Get Telegram Bot Token

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Get your bot token and add it to `.env`

### 4. Get cTrader API Credentials

1. Register at [Spotware Connect](https://connect.spotware.com/)
2. Create a new application
3. Get Client ID and Client Secret
4. Add them to `.env`

### 5. Setup Demo Account

1. Open a demo account with IC Markets
2. Get your account ID from cTrader platform
3. Add it to `.env`

## Usage

### Start the Bot

```bash
python main.py
```

### Bot Commands

- `/start` - Welcome message and help
- `/setup` - Configure channels and accounts
- `/signal` - Create and send trading signals
- `/test` - Send a test signal
- `/status` - View bot statistics
- `/history` - View recent signal history
- `/help` - Show help message

### Creating Signals

You can create signals in two ways:

#### 1. Quick Format
Send a message in this format:
```
EURUSD BUY 1.0650 1.0600 1.0750
```

#### 2. Interactive Setup
Use `/signal` command for guided setup.

### Example Signal

```
🟢 TRADING SIGNAL

Symbol: EURUSD
Direction: BUY
Entry Price: 1.0650

Stop Loss: 1.0600
Take Profit: 1.0750

Volume: 1.0

📊 Generated at 14:30:25
```

## Testing

Run the test suite to verify everything is working:

```bash
python test_bot.py
```

This will test:
- Signal processing
- cTrader API integration
- Telegram bot initialization

## Configuration

### Channel Setup

1. Add your bot to a Telegram channel as admin
2. Use `/setup` command to add the channel
3. Link it to a trading account

### Account Management

- Each channel can be linked to one trading account
- Multiple channels can use the same account
- Demo accounts are recommended for testing

## Architecture

### Signal Flow

1. **Signal Creation**: Bot receives signal data
2. **Processing**: Signal processor formats and validates
3. **Channel Distribution**: Signal sent to Telegram channel
4. **Trade Execution**: Trade placed via cTrader API
5. **History Tracking**: Execution recorded for monitoring

### Key Components

- **SignalProcessor**: Manages signals and channel-account mapping
- **CTraderAPI**: Handles cTrader Open API communication
- **TelegramBot**: Manages Telegram interactions and commands
- **Models**: Data structures for signals, accounts, and channels

## Security Notes

- Never commit your `.env` file to version control
- Use demo accounts for testing
- Validate all signal data before execution
- Monitor execution logs regularly

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check bot token and network connection
2. **API errors**: Verify cTrader credentials and account status
3. **Signal failures**: Check channel permissions and account linking

### Logs

Check `logs/signals_bot.log` for detailed execution logs.

## Development

### Adding New Features

1. Update models in `models.py`
2. Add API methods in `ctrader_api.py`
3. Extend signal processing in `signal_processor.py`
4. Update bot commands in `telegram_bot.py`

### Testing

Always test new features with:
- Demo accounts only
- Test channels
- Small trade volumes

## License

This project is for educational and testing purposes. Use at your own risk.

## Support

For issues and questions, please check the logs and ensure all configuration is correct.

