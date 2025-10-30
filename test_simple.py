#!/usr/bin/env python3
"""
Simple test script
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all modules can be imported"""
    try:
        from config import Config
        print("✅ Config imported")
        
        from ctrader_api import CTraderAPI
        print("✅ cTrader API imported")
        
        from auto_signal_generator import AutoSignalGenerator
        print("✅ Auto signal generator imported")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_config():
    """Test configuration"""
    try:
        from config import Config
        print(f"✅ Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"✅ Channel ID: {Config.TEST_CHANNEL_ID}")
        print(f"✅ Account ID: {Config.DEMO_ACCOUNT_ID}")
        print(f"✅ Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        return True
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False

def main():
    print("🧪 Simple Test Script")
    print("=" * 30)
    
    if test_imports():
        print("✅ All imports successful")
    else:
        print("❌ Import issues")
        return
    
    if test_config():
        print("✅ Configuration loaded")
    else:
        print("❌ Configuration issues")
        return
    
    print("\n🎉 All tests passed!")
    print("🚀 Ready to run the bot!")

if __name__ == "__main__":
    main()

