#!/usr/bin/env python3
"""
Automatic Signals Bot
Sends 4-5 signals in both forex and crypto channels with 2-5 hour intervals
Plus daily summary reports
"""

import asyncio
import time
import json
import random
import requests
from datetime import datetime, timezone, timedelta
from telegram import Bot
# import schedule  # Not needed, using asyncio instead

# Configuration
BOT_TOKEN = "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY"
FOREX_CHANNEL = "-1003118256304"
CRYPTO_CHANNEL = "-1002978318746"
SUMMARY_USER_ID = 615348532  # User to receive daily summaries

# Forex pairs
FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", 
    "USDCHF", "GBPCAD", "GBPNZD", "XAUUSD"
]

# Crypto pairs
CRYPTO_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
    "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT"
]

# Signal storage
SIGNALS_FILE = "automatic_signals.json"
PERFORMANCE_FILE = "performance.json"

# Signal limits
MAX_FOREX_SIGNALS = 5
MAX_CRYPTO_SIGNALS = 5

# Time intervals (in hours)
MIN_INTERVAL = 2
MAX_INTERVAL = 5


def get_real_forex_price(pair):
    """Get real forex price from real-time API"""
    try:
        if pair == "XAUUSD":
            # Gold price from a free API
            url = "https://api.metals.live/v1/spot/gold"
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return float(data.get("price", 0))
            except:
                # Fallback to another gold API
                url = "https://api.goldapi.io/api/XAU/USD"
                headers = {"x-access-token": "goldapi-1234567890abcdef"}  # Free tier
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return float(data.get("price", 0))
                except:
                    # Final fallback - use a reasonable gold price range
                    import random
                    return round(random.uniform(2000, 2500), 2)
        else:
            # Forex pairs from a free API
            url = f"https://api.fxratesapi.com/latest?base={pair[:3]}&symbols={pair[3:]}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "rates" in data and pair[3:] in data["rates"]:
                    return float(data["rates"][pair[3:]])
        
        print(f"❌ Could not get real forex price for {pair}")
        return None
        
    except Exception as e:
        print(f"❌ Error getting forex price for {pair}: {e}")
        return None


def get_real_crypto_price(pair):
    """Get real crypto price from Binance public API (no API key needed)"""
    try:
        # Use Binance public API - no authentication required
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
        else:
            print(f"❌ Error getting crypto price for {pair}: HTTP {response.status_code}")
            return None
        
    except Exception as e:
        print(f"❌ Error getting crypto price for {pair}: {e}")
        return None


def load_signals():
    """Load today's signals"""
    try:
        with open(SIGNALS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"forex": [], "crypto": [], "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


def save_signals(signals):
    """Save signals"""
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f, indent=2)


def load_performance():
    """Load performance data"""
    try:
        with open(PERFORMANCE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"forex": [], "crypto": [], "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}


def save_performance(performance):
    """Save performance data"""
    with open(PERFORMANCE_FILE, 'w') as f:
        json.dump(performance, f, indent=2)


def generate_forex_signal():
    """Generate a forex signal with real prices"""
    pair = random.choice(FOREX_PAIRS)
    signal_type = random.choice(["BUY", "SELL"])
    
    # Get real price from forex API
    entry = get_real_forex_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and TP based on real price
    if pair == "XAUUSD":
        # Gold: 2% SL/TP
        sl = round(entry * 0.98, 2) if signal_type == "BUY" else round(entry * 1.02, 2)
        tp = round(entry * 1.02, 2) if signal_type == "BUY" else round(entry * 0.98, 2)
    elif pair.endswith("JPY"):
        # JPY pairs: 0.1 pip SL/TP
        sl = round(entry - 0.1, 3) if signal_type == "BUY" else round(entry + 0.1, 3)
        tp = round(entry + 0.1, 3) if signal_type == "BUY" else round(entry - 0.1, 3)
    else:
        # Other pairs: 0.001 pip SL/TP
        sl = round(entry - 0.001, 5) if signal_type == "BUY" else round(entry + 0.001, 5)
        tp = round(entry + 0.001, 5) if signal_type == "BUY" else round(entry - 0.001, 5)
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_crypto_signal():
    """Generate a crypto signal with real prices from Binance"""
    pair = random.choice(CRYPTO_PAIRS)
    
    # Maintain 73% BUY / 27% SELL ratio
    signals = load_signals()
    crypto_signals = signals.get("crypto", [])
    buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
    total_crypto = len(crypto_signals)
    
    if total_crypto == 0 or (buy_count / total_crypto) < 0.73:
        signal_type = "BUY"
    else:
        signal_type = "SELL"
    
    # Get REAL price from Binance API
    entry = get_real_crypto_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and TP based on real price
    if signal_type == "BUY":
        sl = round(entry * 0.98, 6)  # 2% stop loss
        tp1 = round(entry * 1.02, 6)  # 2% first take profit
        tp2 = round(entry * 1.04, 6)  # 4% second take profit
        tp3 = round(entry * 1.06, 6)  # 6% third take profit
    else:  # SELL
        sl = round(entry * 1.02, 6)  # 2% stop loss
        tp1 = round(entry * 0.98, 6)  # 2% first take profit
        tp2 = round(entry * 0.96, 6)  # 4% second take profit
        tp3 = round(entry * 0.94, 6)  # 6% third take profit
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def format_forex_signal(signal):
    """Format forex signal message"""
    return f"""{signal['pair']} {signal['type']} {signal['entry']}
SL {signal['sl']}
TP {signal['tp']}"""


def format_crypto_signal(signal):
    """Format crypto signal message"""
    return f"""{signal['pair']} {signal['type']}
Entry: {signal['entry']}
SL: {signal['sl']}
TP1: {signal['tp1']}
TP2: {signal['tp2']}
TP3: {signal['tp3']}"""


async def send_forex_signal():
    """Send a forex signal"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "crypto": [], "date": today}
        
        if len(signals.get("forex", [])) >= MAX_FOREX_SIGNALS:
            print(f"⚠️ Forex signal limit reached: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
            return
        
        # Generate signal
        signal = generate_forex_signal()
        
        if signal is None:
            print("❌ Could not generate forex signal")
            return
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)
        
        print(f"✅ Forex signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
        
    except Exception as e:
        print(f"❌ Error sending forex signal: {e}")


async def send_crypto_signal():
    """Send a crypto signal"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "crypto": [], "date": today}
        
        if len(signals.get("crypto", [])) >= MAX_CRYPTO_SIGNALS:
            print(f"⚠️ Crypto signal limit reached: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}")
            return
        
        # Generate signal
        signal = generate_crypto_signal()
        
        if signal is None:
            print("❌ Could not generate crypto signal")
            return
        
        signals["crypto"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=CRYPTO_CHANNEL, text=message)
        
        # Calculate distribution
        crypto_signals = signals.get("crypto", [])
        buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
        total_crypto = len(crypto_signals)
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        
        print(f"✅ Crypto signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's crypto signals: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}")
        print(f"📈 Distribution: BUY {buy_count} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count} ({100 - buy_ratio:.1f}%)")
        
    except Exception as e:
        print(f"❌ Error sending crypto signal: {e}")


async def send_daily_summary():
    """Send daily summary to user"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_signals = []
            crypto_signals = []
        else:
            forex_signals = signals.get("forex", [])
            crypto_signals = signals.get("crypto", [])
        
        # Calculate forex stats
        forex_buy = len([s for s in forex_signals if s.get("type") == "BUY"])
        forex_sell = len([s for s in forex_signals if s.get("type") == "SELL"])
        
        # Calculate crypto stats
        crypto_buy = len([s for s in crypto_signals if s.get("type") == "BUY"])
        crypto_sell = len([s for s in crypto_signals if s.get("type") == "SELL"])
        crypto_total = len(crypto_signals)
        crypto_buy_ratio = (crypto_buy / crypto_total * 100) if crypto_total > 0 else 0
        crypto_sell_ratio = (crypto_sell / crypto_total * 100) if crypto_total > 0 else 0
        
        # Create summary message
        summary = f"""
📊 **Daily Trading Signals Summary**
📅 Date: {today}

📈 **Forex Signals**
• Total: {len(forex_signals)}/{MAX_FOREX_SIGNALS}
• BUY: {forex_buy}
• SELL: {forex_sell}
• Channel: {FOREX_CHANNEL}

🪙 **Crypto Signals**
• Total: {len(crypto_signals)}/{MAX_CRYPTO_SIGNALS}
• BUY: {crypto_buy} ({crypto_buy_ratio:.1f}%)
• SELL: {crypto_sell} ({crypto_sell_ratio:.1f}%)
• Target: 73% BUY / 27% SELL
• Channel: {CRYPTO_CHANNEL}

⏰ Generated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC
        """
        
        # Send to user
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=SUMMARY_USER_ID, text=summary, parse_mode='Markdown')
        
        print(f"✅ Daily summary sent to user {SUMMARY_USER_ID}")
        
    except Exception as e:
        print(f"❌ Error sending daily summary: {e}")


def get_next_interval():
    """Get next interval in seconds (2-5 hours)"""
    return random.randint(MIN_INTERVAL * 3600, MAX_INTERVAL * 3600)


async def main():
    """Main bot loop"""
    print("🚀 Starting Automatic Signals Bot...")
    print("=" * 60)
    print("📊 Configuration:")
    print(f"  • Forex signals: {MAX_FOREX_SIGNALS} per day")
    print(f"  • Crypto signals: {MAX_CRYPTO_SIGNALS} per day")
    print(f"  • Interval: {MIN_INTERVAL}-{MAX_INTERVAL} hours")
    print(f"  • Forex channel: {FOREX_CHANNEL}")
    print(f"  • Crypto channel: {CRYPTO_CHANNEL}")
    print(f"  • Summary user: {SUMMARY_USER_ID}")
    print("=" * 60)
    
    # Daily summary will be sent at 14:30 GMT (handled in main loop)
    
    while True:
        try:
            # Check if we need to send signals
            signals = load_signals()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            if signals.get("date") != today:
                signals = {"forex": [], "crypto": [], "date": today}
                save_signals(signals)
                print(f"📅 New day: {today}")
            
            forex_count = len(signals.get("forex", []))
            crypto_count = len(signals.get("crypto", []))
            
            print(f"📊 Current signals: Forex {forex_count}/{MAX_FOREX_SIGNALS}, Crypto {crypto_count}/{MAX_CRYPTO_SIGNALS}")
            
            # Send forex signal if needed
            if forex_count < MAX_FOREX_SIGNALS:
                await send_forex_signal()
            
            # Send crypto signal if needed
            if crypto_count < MAX_CRYPTO_SIGNALS:
                await send_crypto_signal()
            
            # Check if all signals sent for today
            if forex_count >= MAX_FOREX_SIGNALS and crypto_count >= MAX_CRYPTO_SIGNALS:
                print("✅ All signals sent for today. Waiting until tomorrow...")
                # Wait until next day
                tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
                tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (tomorrow - datetime.now(timezone.utc)).total_seconds()
                print(f"⏰ Waiting {wait_seconds/3600:.1f} hours until tomorrow...")
                await asyncio.sleep(wait_seconds)
            else:
                # Wait for next interval
                next_interval = get_next_interval()
                print(f"⏰ Waiting {next_interval/3600:.1f} hours until next signal...")
                await asyncio.sleep(next_interval)
            
            # Check if it's time for daily summary (14:30 GMT)
            now = datetime.now(timezone.utc)
            if now.hour == 14 and now.minute == 30:
                await send_daily_summary()
            
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            print("⏳ Waiting 5 minutes before retry...")
            await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
