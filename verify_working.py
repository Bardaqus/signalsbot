#!/usr/bin/env python3
"""
Verify everything is working
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("🔍 Verifying Auto Signals Bot Setup...")
    print("=" * 50)
    
    try:
        from config import Config
        print("✅ Configuration loaded")
        print(f"   Bot Token: {Config.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"   Channel ID: {Config.TEST_CHANNEL_ID}")
        print(f"   Interval: {Config.AUTO_SIGNAL_INTERVAL} seconds")
        print(f"   SL/TP: {Config.SL_PIPS}/{Config.TP_PIPS} pips")
        
        from aiogram import Bot
        print("✅ aiogram imported")
        
        from auto_signals_simple import SimpleAutoSignals
        print("✅ Auto signals module imported")
        
        print("\n🎉 All components ready!")
        print("\n📋 Your configuration:")
        print(f"   📱 Channel: {Config.TEST_CHANNEL_ID}")
        print(f"   ⏰ Signals every: {Config.AUTO_SIGNAL_INTERVAL//60} minutes")
        print(f"   🎯 Risk: {Config.SL_PIPS} SL, {Config.TP_PIPS} TP pips")
        print(f"   🏦 Demo account: {Config.DEMO_ACCOUNT_ID}")
        
        print("\n🚀 Ready to start!")
        print("   python3 auto_signals_simple.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if main():
        print("\n✅ Setup verification complete!")
    else:
        print("\n❌ Setup issues found.")

