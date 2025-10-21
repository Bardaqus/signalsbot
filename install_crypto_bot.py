#!/usr/bin/env python3
"""
Installation script for crypto signals bot
This script helps set up the crypto bot with proper dependencies
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False

def check_binance_api():
    """Check if Binance API credentials are set"""
    print("🔑 Checking Binance API credentials...")
    
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    
    if not api_key or not api_secret:
        print("⚠️  Binance API credentials not found in environment variables")
        print("Please set the following environment variables:")
        print("export BINANCE_API_KEY='your_api_key'")
        print("export BINANCE_API_SECRET='your_api_secret'")
        return False
    else:
        print("✅ Binance API credentials found")
        return True

def check_telegram_config():
    """Check Telegram bot configuration"""
    print("📱 Checking Telegram configuration...")
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("⚠️  Telegram bot token not found")
        print("Please set: export TELEGRAM_BOT_TOKEN='your_bot_token'")
        return False
    else:
        print("✅ Telegram bot token found")
        return True

def test_imports():
    """Test if all required modules can be imported"""
    print("🧪 Testing imports...")
    
    try:
        import pandas
        import requests
        import telegram
        from binance.client import Client
        print("✅ All required modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def create_sample_config():
    """Create a sample configuration file"""
    print("📝 Creating sample configuration...")
    
    config_content = '''# Crypto Bot Configuration
# Copy this file to config.py and fill in your actual values

import os

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token_here"
CRYPTO_CHANNEL_ID = "-1002978318746"
REPORT_USER_ID = 615348532

# Binance API Configuration
BINANCE_API_KEY = "your_binance_api_key_here"
BINANCE_API_SECRET = "your_binance_api_secret_here"

# Signal Configuration
MAX_SIGNALS_PER_DAY = 5
MIN_SIGNALS_PER_DAY = 3
'''
    
    try:
        with open("crypto_config_sample.py", "w") as f:
            f.write(config_content)
        print("✅ Sample configuration created: crypto_config_sample.py")
        return True
    except Exception as e:
        print(f"❌ Failed to create sample config: {e}")
        return False

def main():
    """Main installation process"""
    print("🚀 Crypto Signals Bot Installation")
    print("=" * 40)
    
    # Install requirements
    if not install_requirements():
        print("❌ Installation failed at requirements step")
        return False
    
    # Test imports
    if not test_imports():
        print("❌ Installation failed at import test")
        return False
    
    # Check configuration
    binance_ok = check_binance_api()
    telegram_ok = check_telegram_config()
    
    # Create sample config
    create_sample_config()
    
    print("\n" + "=" * 40)
    if binance_ok and telegram_ok:
        print("✅ Installation completed successfully!")
        print("\n📋 Next steps:")
        print("1. Set up your Binance API credentials")
        print("2. Configure your Telegram bot")
        print("3. Run: python start_crypto_bot.py")
    else:
        print("⚠️  Installation completed with warnings")
        print("Please configure your API credentials before running the bot")
    
    print("\n📖 For detailed setup instructions, see CRYPTO_README.md")
    return True

if __name__ == "__main__":
    main()
