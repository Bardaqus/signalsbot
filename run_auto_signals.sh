#!/bin/bash

# Auto Signals Bot Startup Script

echo "🤖 Starting Auto Signals Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if config file exists
if [ ! -f "config_live.env" ]; then
    echo "⚠️  config_live.env file not found!"
    echo "📝 Please ensure your configuration file exists"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Run the auto signals bot
echo "🚀 Starting auto signals bot..."
echo "📊 Signal interval: 4 minutes"
echo "🎯 SL: 30 pips, TP: 50 pips"
echo "📱 Channel: https://t.me/+ZaJCtmMwXJthYzJi"
echo "🏦 Demo Account: 9615885"
echo ""
echo "Press Ctrl+C to stop the bot"
echo ""

python3 main_auto_signals.py

