#!/bin/bash

# Signals Bot Startup Script

echo "🤖 Starting Signals Bot..."

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

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "📝 Please copy config_example.env to .env and configure your settings"
    echo "   cp config_example.env .env"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Run the bot
echo "🚀 Starting bot..."
python main.py

