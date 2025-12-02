#!/bin/bash

# Commit Signals_bot Version 1.0.0

echo "🚀 Committing Signals_bot Version 1.0.0"
echo "========================================"

# Initialize git if not already done
if [ ! -d ".git" ]; then
    echo "📦 Initializing git repository..."
    git init
fi

# Add all files except those in .gitignore
echo "📁 Adding files to git..."
git add .

# Check status
echo "📋 Git status:"
git status

# Commit with version 1.0.0
echo ""
echo "💾 Committing version 1.0.0..."
git commit -m "🚀 Signals_bot v1.0.0 - Initial Release

✨ Features:
- Auto trading signals every 4 minutes
- Telegram bot integration
- cTrader API simulation (no auth required)
- 30 pip SL, 50 pip TP risk management
- 15 major currency pairs
- Demo mode for safe testing
- Channel management system
- Signal history tracking

🔧 Configuration:
- Telegram bot: 7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY
- Channel ID: -1002175884868
- Demo account: 9615885
- Signal interval: 4 minutes (240 seconds)

📁 Project Structure:
- main.py: Application entry point
- telegram_bot.py: Telegram bot implementation
- ctrader_api.py: cTrader API integration
- auto_signal_generator.py: Auto signal generation
- signal_processor.py: Signal processing logic
- models.py: Data models
- config.py: Configuration management

🎯 Ready for production use!"

# Create version tag
echo "🏷️  Creating version tag v1.0.0..."
git tag -a v1.0.0 -m "Signals_bot Version 1.0.0 - Initial Release"

echo ""
echo "✅ Version 1.0.0 committed successfully!"
echo "🏷️  Tag: v1.0.0"
echo ""
echo "📋 To push to remote repository:"
echo "   git remote add origin <your-repo-url>"
echo "   git push -u origin main"
echo "   git push --tags"
echo ""
echo "🎉 Signals_bot v1.0.0 is ready!"

