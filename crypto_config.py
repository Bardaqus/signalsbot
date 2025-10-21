#!/usr/bin/env python3
"""
Configuration file for crypto signals bot
Copy this file and rename to config.py, then fill in your API keys
"""

import os

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
CRYPTO_CHANNEL_ID = "-1002978318746"  # Crypto signals channel
REPORT_USER_ID = 615348532  # User ID for performance reports

# Binance API Configuration
# Set these as environment variables or replace with your actual keys
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Signal Configuration
MAX_SIGNALS_PER_DAY = 5
MIN_SIGNALS_PER_DAY = 3

# Crypto pairs to monitor
CRYPTO_PAIRS = [
    "BTCUSDT",
    "ETHUSDT", 
    "BNBUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOTUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "MATICUSDT"
]

# Files
CRYPTO_SIGNALS_FILE = "crypto_signals.json"
CRYPTO_PERFORMANCE_FILE = "crypto_performance.json"
