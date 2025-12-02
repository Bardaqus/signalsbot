#!/usr/bin/env python3
"""
Verification script for Auto Signals Bot setup
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def verify_setup():
    """Verify all components are ready"""
    print("🔍 Verifying Auto Signals Bot Setup...")
    print("=" * 50)
    
    # Check config file
    if os.path.exists('config_live.env'):
        print("✅ config_live.env found")
    else:
        print("❌ config_live.env not found")
        return False
    
    # Check required files
    required_files = [
        'config.py',
        'auto_signal_generator.py', 
        'start_auto_bot.py',
        'signal_processor.py',
        'ctrader_api.py',
        'models.py'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} not found")
            return False
    
    # Test configuration loading
    try:
        from config import Config
        print("\n🔧 Configuration Test:")
        print(f"  Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"  Client ID: {Config.CTRADER_CLIENT_ID[:20]}...")
        print(f"  Account ID: {Config.DEMO_ACCOUNT_ID}")
        print(f"  Channel: {Config.TEST_CHANNEL_ID}")
        print(f"  Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        print(f"  SL/TP: {Config.SL_PIPS}/{Config.TP_PIPS} pips")
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False
    
    # Test imports
    try:
        from auto_signal_generator import AutoSignalGenerator
        from signal_processor import SignalProcessor
        from ctrader_api import CTraderAPI
        print("✅ All modules imported successfully")
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False
    
    print("\n🎉 Setup Verification Complete!")
    print("\n📋 Ready to start:")
    print("  python3 start_auto_bot.py")
    print("\n📱 Your channel: https://t.me/+ZaJCtmMwXJthYzJi")
    print("🏦 Demo account: 9615885")
    print("⏰ Signals every: 4 minutes")
    print("🎯 Risk: 30 SL, 50 TP pips")
    
    return True

if __name__ == "__main__":
    if verify_setup():
        print("\n🚀 All systems ready! Start the bot now!")
    else:
        print("\n❌ Setup issues found. Please fix them first.")

