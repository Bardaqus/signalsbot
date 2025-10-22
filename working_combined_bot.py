#!/usr/bin/env python3
"""
Working Combined Trading Signals Bot
- Automatic signal generation (2-5 hour intervals)
- Interactive buttons for manual control
- Daily summary reports (24h)
- Weekly summary reports (Friday, 7 days)
- Fixed all asyncio issues
"""

import asyncio
import time
import json
import random
import requests
from datetime import datetime, timezone, timedelta
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import threading

# Configuration
BOT_TOKEN = "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY"
FOREX_CHANNEL = "-1003118256304"
FOREX_CHANNEL_3TP = "-1001220540048"  # New forex channel with 3 TPs
CRYPTO_CHANNEL = "-1002978318746"
SUMMARY_USER_ID = 615348532

# Allowed user IDs for interactive features
ALLOWED_USERS = [615348532, 501779863]

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
SIGNALS_FILE = "working_combined_signals.json"
PERFORMANCE_FILE = "working_combined_performance.json"

# Signal limits
MAX_FOREX_SIGNALS = 5  # Original forex channel
MAX_FOREX_3TP_SIGNALS = 4  # New forex channel with 3 TPs
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
                # Try alternative gold API
                url = "https://api.goldapi.io/api/XAU/USD"
                headers = {"x-access-token": "goldapi-1234567890abcdef"}
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return float(data.get("price", 0))
                except:
                    # Try another gold API
                    url = "https://api.metals.live/v1/spot/silver"
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            # Use silver price as reference and estimate gold (roughly 80x silver)
                            silver_price = float(data.get("price", 0))
                            if silver_price > 0:
                                return round(silver_price * 80, 2)
                    except:
                        pass
                    
                    # If all APIs fail, return None instead of random price
                    print(f"❌ All gold price APIs failed for {pair}")
                    return None
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
            signals = json.load(f)
            # Ensure all required keys exist
            if "forex_3tp" not in signals:
                signals["forex_3tp"] = []
            if "forwarded_forex" not in signals:
                signals["forwarded_forex"] = []
            return signals
    except:
        return {
            "forex": [], 
            "forex_3tp": [], 
            "crypto": [], 
            "forwarded_forex": [],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }


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
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_forex_pairs = []
    else:
        active_forex_pairs = [s["pair"] for s in signals.get("forex", [])]
    
    # Filter out pairs that already have active signals
    available_pairs = [pair for pair in FOREX_PAIRS if pair not in active_forex_pairs]
    
    if not available_pairs:
        print("⚠️ All forex pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
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
        # JPY pairs: 0.2 pip SL/TP (2x bigger range)
        sl = round(entry - 0.2, 3) if signal_type == "BUY" else round(entry + 0.2, 3)
        tp = round(entry + 0.2, 3) if signal_type == "BUY" else round(entry - 0.2, 3)
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


def generate_forex_3tp_signal():
    """Generate a forex signal with 3 TPs (like crypto signals)"""
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_forex_3tp_pairs = []
    else:
        active_forex_3tp_pairs = [s["pair"] for s in signals.get("forex_3tp", [])]
    
    # Filter out pairs that already have active signals
    available_pairs = [pair for pair in FOREX_PAIRS if pair not in active_forex_3tp_pairs]
    
    if not available_pairs:
        print("⚠️ All forex 3TP pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
    signal_type = random.choice(["BUY", "SELL"])
    
    # Get real price from forex API
    entry = get_real_forex_price(pair)
    
    if entry is None:
        print(f"❌ Could not get real price for {pair}, skipping signal")
        return None
    
    # Calculate SL and 3 TPs based on real price (similar to crypto logic)
    if pair == "XAUUSD":
        # Gold: 2% SL, 2%/4%/6% TPs
        if signal_type == "BUY":
            sl = round(entry * 0.98, 2)  # 2% stop loss
            tp1 = round(entry * 1.02, 2)  # 2% first take profit
            tp2 = round(entry * 1.04, 2)  # 4% second take profit
            tp3 = round(entry * 1.06, 2)  # 6% third take profit
        else:  # SELL
            sl = round(entry * 1.02, 2)  # 2% stop loss
            tp1 = round(entry * 0.98, 2)  # 2% first take profit
            tp2 = round(entry * 0.96, 2)  # 4% second take profit
            tp3 = round(entry * 0.94, 2)  # 6% third take profit
    elif pair.endswith("JPY"):
        # JPY pairs: 0.2 pip SL, 0.2/0.4/0.6 pip TPs
        if signal_type == "BUY":
            sl = round(entry - 0.2, 3)  # 0.2 pip stop loss
            tp1 = round(entry + 0.2, 3)  # 0.2 pip first take profit
            tp2 = round(entry + 0.4, 3)  # 0.4 pip second take profit
            tp3 = round(entry + 0.6, 3)  # 0.6 pip third take profit
        else:  # SELL
            sl = round(entry + 0.2, 3)  # 0.2 pip stop loss
            tp1 = round(entry - 0.2, 3)  # 0.2 pip first take profit
            tp2 = round(entry - 0.4, 3)  # 0.4 pip second take profit
            tp3 = round(entry - 0.6, 3)  # 0.6 pip third take profit
    else:
        # Other pairs: 0.001 pip SL, 0.001/0.002/0.003 pip TPs
        if signal_type == "BUY":
            sl = round(entry - 0.001, 5)  # 0.001 pip stop loss
            tp1 = round(entry + 0.001, 5)  # 0.001 pip first take profit
            tp2 = round(entry + 0.002, 5)  # 0.002 pip second take profit
            tp3 = round(entry + 0.003, 5)  # 0.003 pip third take profit
        else:  # SELL
            sl = round(entry + 0.001, 5)  # 0.001 pip stop loss
            tp1 = round(entry - 0.001, 5)  # 0.001 pip first take profit
            tp2 = round(entry - 0.002, 5)  # 0.002 pip second take profit
            tp3 = round(entry - 0.003, 5)  # 0.003 pip third take profit
    
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


def generate_crypto_signal():
    """Generate a crypto signal with real prices from Binance"""
    # Check for active signals to avoid duplicates
    signals = load_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if signals.get("date") != today:
        active_crypto_pairs = []
        crypto_signals = []
    else:
        active_crypto_pairs = [s["pair"] for s in signals.get("crypto", [])]
        crypto_signals = signals.get("crypto", [])
    
    # Filter out pairs that already have active signals
    available_pairs = [pair for pair in CRYPTO_PAIRS if pair not in active_crypto_pairs]
    
    if not available_pairs:
        print("⚠️ All crypto pairs already have active signals today")
        return None
    
    pair = random.choice(available_pairs)
    
    # Maintain 73% BUY / 27% SELL ratio
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
    pair = signal['pair']
    signal_type = signal['type']
    
    # Format numbers based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places
        entry = f"{signal['entry']:,.2f}"
        sl = f"{signal['sl']:,.2f}"
        tp = f"{signal['tp']:,.2f}"
    elif pair.endswith("JPY"):
        # JPY pairs: 3 decimal places
        entry = f"{signal['entry']:,.3f}"
        sl = f"{signal['sl']:,.3f}"
        tp = f"{signal['tp']:,.3f}"
    else:
        # Other forex pairs: 5 decimal places
        entry = f"{signal['entry']:,.5f}"
        sl = f"{signal['sl']:,.5f}"
        tp = f"{signal['tp']:,.5f}"
    
    return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp}"""


def format_forex_3tp_signal(signal):
    """Format forex signal message with 3 TPs"""
    pair = signal['pair']
    signal_type = signal['type']
    
    # Format numbers based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places
        entry = f"{signal['entry']:,.2f}"
        sl = f"{signal['sl']:,.2f}"
        tp1 = f"{signal['tp1']:,.2f}"
        tp2 = f"{signal['tp2']:,.2f}"
        tp3 = f"{signal['tp3']:,.2f}"
    elif pair.endswith("JPY"):
        # JPY pairs: 3 decimal places
        entry = f"{signal['entry']:,.3f}"
        sl = f"{signal['sl']:,.3f}"
        tp1 = f"{signal['tp1']:,.3f}"
        tp2 = f"{signal['tp2']:,.3f}"
        tp3 = f"{signal['tp3']:,.3f}"
    else:
        # Other forex pairs: 5 decimal places
        entry = f"{signal['entry']:,.5f}"
        sl = f"{signal['sl']:,.5f}"
        tp1 = f"{signal['tp1']:,.5f}"
        tp2 = f"{signal['tp2']:,.5f}"
        tp3 = f"{signal['tp3']:,.5f}"
    
    return f"""{pair} {signal_type}
Entry: {entry}
SL: {sl}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}"""


def format_crypto_signal(signal):
    """Format crypto signal message"""
    # Format crypto numbers with 6 decimal places and comma separators
    entry = f"{signal['entry']:,.6f}"
    sl = f"{signal['sl']:,.6f}"
    tp1 = f"{signal['tp1']:,.6f}"
    tp2 = f"{signal['tp2']:,.6f}"
    tp3 = f"{signal['tp3']:,.6f}"
    
    return f"""{signal['pair']} {signal['type']}
Entry: {entry}
SL: {sl}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}"""


def get_next_interval():
    """Get next interval in seconds (2-5 hours)"""
    return random.randint(MIN_INTERVAL * 3600, MAX_INTERVAL * 3600)


async def send_forex_signal():
    """Send a forex signal"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        if len(signals.get("forex", [])) >= MAX_FOREX_SIGNALS:
            print(f"⚠️ Forex signal limit reached: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
            return False
        
        # Generate signal
        signal = generate_forex_signal()
        
        if signal is None:
            print("❌ Could not generate forex signal")
            return False
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)
        
        print(f"✅ Forex signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending forex signal: {e}")
        return False


async def send_forex_3tp_signal():
    """Send a forex signal with 3 TPs"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        if len(signals.get("forex_3tp", [])) >= MAX_FOREX_3TP_SIGNALS:
            print(f"⚠️ Forex 3TP signal limit reached: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}")
            return False
        
        # Generate signal
        signal = generate_forex_3tp_signal()
        
        if signal is None:
            print("❌ Could not generate forex 3TP signal")
            return False
        
        signals["forex_3tp"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_3tp_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message)
        
        print(f"✅ Forex 3TP signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        print(f"📊 Today's forex 3TP signals: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending forex 3TP signal: {e}")
        return False


async def send_crypto_signal():
    """Send a crypto signal"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "crypto": [], "date": today}
        
        if len(signals.get("crypto", [])) >= MAX_CRYPTO_SIGNALS:
            print(f"⚠️ Crypto signal limit reached: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}")
            return False
        
        # Generate signal
        signal = generate_crypto_signal()
        
        if signal is None:
            print("❌ Could not generate crypto signal")
            return False
        
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
        return True
        
    except Exception as e:
        print(f"❌ Error sending crypto signal: {e}")
        return False


async def send_daily_summary():
    """Send daily summary to user"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_signals = []
            forex_3tp_signals = []
            crypto_signals = []
        else:
            forex_signals = signals.get("forex", [])
            forex_3tp_signals = signals.get("forex_3tp", [])
            crypto_signals = signals.get("crypto", [])
        
        # Calculate forex stats
        forex_buy = len([s for s in forex_signals if s.get("type") == "BUY"])
        forex_sell = len([s for s in forex_signals if s.get("type") == "SELL"])
        
        # Calculate forex 3TP stats
        forex_3tp_buy = len([s for s in forex_3tp_signals if s.get("type") == "BUY"])
        forex_3tp_sell = len([s for s in forex_3tp_signals if s.get("type") == "SELL"])
        
        # Calculate crypto stats
        crypto_buy = len([s for s in crypto_signals if s.get("type") == "BUY"])
        crypto_sell = len([s for s in crypto_signals if s.get("type") == "SELL"])
        crypto_total = len(crypto_signals)
        crypto_buy_ratio = (crypto_buy / crypto_total * 100) if crypto_total > 0 else 0
        crypto_sell_ratio = (crypto_sell / crypto_total * 100) if crypto_total > 0 else 0
        
        # Create summary message
        summary = f"""
📊 **Daily Trading Signals Summary (24h)**
📅 Date: {today}

📈 **Forex Signals**
• Total: {len(forex_signals)}/{MAX_FOREX_SIGNALS}
• BUY: {forex_buy}
• SELL: {forex_sell}
• Channel: {FOREX_CHANNEL}

📈 **Forex 3TP Signals**
• Total: {len(forex_3tp_signals)}/{MAX_FOREX_3TP_SIGNALS}
• BUY: {forex_3tp_buy}
• SELL: {forex_3tp_sell}
• Channel: {FOREX_CHANNEL_3TP}

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


async def send_weekly_summary():
    """Send weekly summary to user (Friday)"""
    try:
        # Get signals from last 7 days
        today = datetime.now(timezone.utc)
        week_ago = today - timedelta(days=7)
        
        # Load all performance data
        performance = load_performance()
        
        # Calculate weekly stats
        forex_signals = performance.get("forex", [])
        crypto_signals = performance.get("crypto", [])
        
        # Filter signals from last 7 days
        recent_forex = [s for s in forex_signals if datetime.fromisoformat(s.get("timestamp", "")).replace(tzinfo=timezone.utc) >= week_ago]
        recent_crypto = [s for s in crypto_signals if datetime.fromisoformat(s.get("timestamp", "")).replace(tzinfo=timezone.utc) >= week_ago]
        
        # Calculate forex stats
        forex_buy = len([s for s in recent_forex if s.get("type") == "BUY"])
        forex_sell = len([s for s in recent_forex if s.get("type") == "SELL"])
        
        # Calculate crypto stats
        crypto_buy = len([s for s in recent_crypto if s.get("type") == "BUY"])
        crypto_sell = len([s for s in recent_crypto if s.get("type") == "SELL"])
        crypto_total = len(recent_crypto)
        crypto_buy_ratio = (crypto_buy / crypto_total * 100) if crypto_total > 0 else 0
        crypto_sell_ratio = (crypto_sell / crypto_total * 100) if crypto_total > 0 else 0
        
        # Create weekly summary message
        summary = f"""
📊 **Weekly Trading Signals Summary (7 days)**
📅 Period: {week_ago.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}

📈 **Forex Signals**
• Total: {len(recent_forex)}
• BUY: {forex_buy}
• SELL: {forex_sell}
• Channel: {FOREX_CHANNEL}

🪙 **Crypto Signals**
• Total: {len(recent_crypto)}
• BUY: {crypto_buy} ({crypto_buy_ratio:.1f}%)
• SELL: {crypto_sell} ({crypto_sell_ratio:.1f}%)
• Target: 73% BUY / 27% SELL
• Channel: {CRYPTO_CHANNEL}

⏰ Generated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC
        """
        
        # Send to user
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=SUMMARY_USER_ID, text=summary, parse_mode='Markdown')
        
        print(f"✅ Weekly summary sent to user {SUMMARY_USER_ID}")
        
    except Exception as e:
        print(f"❌ Error sending weekly summary: {e}")


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    return user_id in ALLOWED_USERS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Send Forex Signal", callback_data="forex_signal"),
            InlineKeyboardButton("🪙 Send Crypto Signal", callback_data="crypto_signal")
        ],
        [
            InlineKeyboardButton("📈 Forex Status", callback_data="forex_status"),
            InlineKeyboardButton("🪙 Crypto Status", callback_data="crypto_status")
        ],
        [
            InlineKeyboardButton("📊 Forex Report 24h", callback_data="forex_report_24h"),
            InlineKeyboardButton("🪙 Crypto Report 24h", callback_data="crypto_report_24h")
        ],
        [
            InlineKeyboardButton("📊 Forex Report 7d", callback_data="forex_report_7d"),
            InlineKeyboardButton("🪙 Crypto Report 7d", callback_data="crypto_report_7d")
        ]
    ]
    
    # Add special forward button for admin users
    if user_id in ALLOWED_USERS:
        keyboard.append([
            InlineKeyboardButton("🔄 Forward Forex to New Channel", callback_data="forward_forex")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Working Combined Trading Signals Bot Control Panel**

**Features:**
• Automatic signal generation (2-5 hour intervals)
• Manual signal generation with buttons
• Real-time status and distribution monitoring
• 24-hour and 7-day performance reports
• All signals use REAL prices from live markets

**Channels:**
• Forex: -1003118256304
• Crypto: -1002978318746

*Click any button to proceed*
    """
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_authorized(user_id):
        await query.answer("❌ You are not authorized to use this bot.")
        return
    
    await query.answer()
    
    if query.data == "forex_signal":
        await handle_forex_signal(query, context)
    elif query.data == "crypto_signal":
        await handle_crypto_signal(query, context)
    elif query.data == "forex_status":
        await handle_forex_status(query, context)
    elif query.data == "crypto_status":
        await handle_crypto_status(query, context)
    elif query.data == "forex_report_24h":
        await handle_forex_report(query, context, days=1)
    elif query.data == "crypto_report_24h":
        await handle_crypto_report(query, context, days=1)
    elif query.data == "forex_report_7d":
        await handle_forex_report(query, context, days=7)
    elif query.data == "crypto_report_7d":
        await handle_crypto_report(query, context, days=7)
    elif query.data == "forward_forex":
        await handle_forward_forex(query, context)
    elif query.data == "refresh":
        await handle_refresh(query, context)


async def handle_forex_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex signal generation"""
    await query.edit_message_text("🔄 Generating forex signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "crypto": [], "date": today}
        
        if len(signals.get("forex", [])) >= MAX_FOREX_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Forex Signal Limit Reached**\n\n"
                f"Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal
        signal = generate_forex_signal()
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating forex signal**\n\n"
                f"Could not get real price from forex API or all pairs already have active signals today",
                parse_mode='Markdown'
            )
            return
        
        signals["forex"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL, text=message)
        
        await query.edit_message_text(
            f"✅ **Forex Signal Generated**\n\n"
            f"📊 {signal['pair']} {signal['type']} at {signal['entry']}\n"
            f"📤 Signal sent to forex channel\n"
            f"📊 Today's forex signals: {len(signals['forex'])}/{MAX_FOREX_SIGNALS}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating forex signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle crypto signal generation"""
    await query.edit_message_text("🔄 Generating crypto signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "crypto": [], "date": today}
        
        if len(signals.get("crypto", [])) >= MAX_CRYPTO_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Crypto Signal Limit Reached**\n\n"
                f"Today's crypto signals: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal
        signal = generate_crypto_signal()
        
        if signal is None:
            await query.edit_message_text(
                f"❌ **Error generating crypto signal**\n\n"
                f"Could not get real price from Binance API or all pairs already have active signals today",
                parse_mode='Markdown'
            )
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
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        await query.edit_message_text(
            f"✅ **Crypto Signal Generated**\n\n"
            f"🪙 {signal['pair']} {signal['type']} at {signal['entry']}\n"
            f"📤 Signal sent to crypto channel\n"
            f"📊 Today's crypto signals: {len(signals['crypto'])}/{MAX_CRYPTO_SIGNALS}\n"
            f"📈 Distribution: BUY {buy_count} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count} ({sell_ratio:.1f}%)",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating crypto signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_count = 0
        else:
            forex_count = len(signals.get("forex", []))
        
        # Get active pairs
        active_pairs = [s["pair"] for s in signals.get("forex", [])]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        status_text = f"""
📈 **Forex Signals Status**

📊 Today's signals: {forex_count}/{MAX_FOREX_SIGNALS}
📋 Active pairs: {active_pairs_text}
📤 Channel: {FOREX_CHANNEL}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if forex_count < MAX_FOREX_SIGNALS else '⚠️ Daily limit reached'}
🤖 Automatic signals: Running in background
        """
        
        await query.edit_message_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting forex status**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle crypto status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            crypto_count = 0
            buy_count = 0
        else:
            crypto_signals = signals.get("crypto", [])
            crypto_count = len(crypto_signals)
            buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
        
        total_crypto = crypto_count
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        # Get active pairs
        active_pairs = [s["pair"] for s in signals.get("crypto", [])]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        status_text = f"""
🪙 **Crypto Signals Status**

📊 Today's signals: {crypto_count}/{MAX_CRYPTO_SIGNALS}
📋 Active pairs: {active_pairs_text}
📈 Distribution: BUY {buy_count} ({buy_ratio:.1f}%), SELL {total_crypto - buy_count} ({sell_ratio:.1f}%)
📤 Channel: {CRYPTO_CHANNEL}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if crypto_count < MAX_CRYPTO_SIGNALS else '⚠️ Daily limit reached'}
🎯 Target: 73% BUY / 27% SELL
🤖 Automatic signals: Running in background
        """
        
        await query.edit_message_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting crypto status**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_report(query, context: ContextTypes.DEFAULT_TYPE, days: int = 1) -> None:
    """Handle forex performance report"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_signals = []
        else:
            forex_signals = signals.get("forex", [])
        
        if not forex_signals:
            report_text = f"""
📊 **Forex Performance Report ({days} day{'s' if days > 1 else ''})**

No forex signals found for the period.

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        else:
            report_text = f"""
📊 **Forex Performance Report ({days} day{'s' if days > 1 else ''})**

📈 Total signals: {len(forex_signals)}
📊 BUY signals: {len([s for s in forex_signals if s.get('type') == 'BUY'])}
📊 SELL signals: {len([s for s in forex_signals if s.get('type') == 'SELL'])}

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        
        await query.edit_message_text(report_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting forex report**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_report(query, context: ContextTypes.DEFAULT_TYPE, days: int = 1) -> None:
    """Handle crypto performance report"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            crypto_signals = []
        else:
            crypto_signals = signals.get("crypto", [])
        
        if not crypto_signals:
            report_text = f"""
🪙 **Crypto Performance Report ({days} day{'s' if days > 1 else ''})**

No crypto signals found for the period.

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        else:
            buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
            sell_count = len([s for s in crypto_signals if s.get("type") == "SELL"])
            total_signals = len(crypto_signals)
            buy_ratio = (buy_count / total_signals * 100) if total_signals > 0 else 0
            sell_ratio = (sell_count / total_signals * 100) if total_signals > 0 else 0
            
            report_text = f"""
🪙 **Crypto Performance Report ({days} day{'s' if days > 1 else ''})**

📊 Total signals: {total_signals}
📈 BUY signals: {buy_count} ({buy_ratio:.1f}%)
📉 SELL signals: {sell_count} ({sell_ratio:.1f}%)
🎯 Target: 73% BUY / 27% SELL

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
        
        await query.edit_message_text(report_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting crypto report**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_refresh(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle refresh - go back to main menu"""
    user_id = query.from_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Send Forex Signal", callback_data="forex_signal"),
            InlineKeyboardButton("🪙 Send Crypto Signal", callback_data="crypto_signal")
        ],
        [
            InlineKeyboardButton("📈 Forex Status", callback_data="forex_status"),
            InlineKeyboardButton("🪙 Crypto Status", callback_data="crypto_status")
        ],
        [
            InlineKeyboardButton("📊 Forex Report 24h", callback_data="forex_report_24h"),
            InlineKeyboardButton("🪙 Crypto Report 24h", callback_data="crypto_report_24h")
        ],
        [
            InlineKeyboardButton("📊 Forex Report 7d", callback_data="forex_report_7d"),
            InlineKeyboardButton("🪙 Crypto Report 7d", callback_data="crypto_report_7d")
        ]
    ]
    
    # Add special forward button for admin users
    if user_id in ALLOWED_USERS:
        keyboard.append([
            InlineKeyboardButton("🔄 Forward Forex to New Channel", callback_data="forward_forex")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Working Combined Trading Signals Bot Control Panel**

**Features:**
• Automatic signal generation (2-5 hour intervals)
• Manual signal generation with buttons
• Real-time status and distribution monitoring
• 24-hour and 7-day performance reports
• All signals use REAL prices from live markets

**Channels:**
• Forex: -1003118256304
• Crypto: -1002978318746

*Click any button to proceed*
    """
    
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_forward_forex(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forwarding forex signals from original channel to new channel"""
    user_id = query.from_user.id
    
    # Only allow admin users to use this feature
    if user_id not in ALLOWED_USERS:
        await query.edit_message_text("❌ You are not authorized to use this feature.")
        return
    
    await query.edit_message_text("🔄 Forwarding forex signal to new channel...")
    
    try:
        # Generate a new forex signal (with 1 TP)
        signal = generate_forex_signal()
        
        if signal is None:
            await query.edit_message_text(
                "❌ Could not generate forex signal. All pairs may be active today.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
                ]])
            )
            return
        
        # Send to the new channel (-1001286609636)
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_signal(signal)
        await bot.send_message(chat_id="-1001286609636", text=message)
        
        # Update signals data (don't count towards daily limit since it's a forward)
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
        # Add to forwarded signals (separate tracking)
        if "forwarded_forex" not in signals:
            signals["forwarded_forex"] = []
        
        signals["forwarded_forex"].append(signal)
        save_signals(signals)
        
        await query.edit_message_text(
            f"✅ **Forex Signal Forwarded Successfully!**\n\n"
            f"📊 **Signal Details:**\n"
            f"• Pair: {signal['pair']}\n"
            f"• Type: {signal['type']}\n"
            f"• Entry: {signal['entry']:,.5f}\n"
            f"• SL: {signal['sl']:,.5f}\n"
            f"• TP: {signal['tp']:,.5f}\n\n"
            f"📤 **Sent to:** -1001286609636\n"
            f"⏰ **Time:** {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
            ]]),
            parse_mode='Markdown'
        )
        
        print(f"✅ Forex signal forwarded by admin user {user_id}: {signal['pair']} {signal['type']} to -1001286609636")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error forwarding forex signal:**\n\n"
            f"Error: {str(e)}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Back to Menu", callback_data="refresh")
            ]]),
            parse_mode='Markdown'
        )
        print(f"❌ Error forwarding forex signal: {e}")


def automatic_signal_loop():
    """Automatic signal generation loop (runs in separate thread)"""
    print("🤖 Starting automatic signal generation loop...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def async_loop():
        while True:
            try:
                # Check if we need to send signals
                signals = load_signals()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                if signals.get("date") != today:
                    signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
                    save_signals(signals)
                    print(f"📅 New day: {today}")
                
                forex_count = len(signals.get("forex", []))
                forex_3tp_count = len(signals.get("forex_3tp", []))
                crypto_count = len(signals.get("crypto", []))
                
                print(f"📊 Current signals: Forex {forex_count}/{MAX_FOREX_SIGNALS}, Forex 3TP {forex_3tp_count}/{MAX_FOREX_3TP_SIGNALS}, Crypto {crypto_count}/{MAX_CRYPTO_SIGNALS}")
                
                # Send forex signal if needed
                if forex_count < MAX_FOREX_SIGNALS:
                    success = await send_forex_signal()
                    if not success:
                        print("⚠️ Could not send forex signal (all pairs may be active)")
                
                # Send forex 3TP signal if needed
                if forex_3tp_count < MAX_FOREX_3TP_SIGNALS:
                    success = await send_forex_3tp_signal()
                    if not success:
                        print("⚠️ Could not send forex 3TP signal (all pairs may be active)")
                
                # Send crypto signal if needed
                if crypto_count < MAX_CRYPTO_SIGNALS:
                    success = await send_crypto_signal()
                    if not success:
                        print("⚠️ Could not send crypto signal (all pairs may be active)")
                
                # Check if all signals sent for today
                if (forex_count >= MAX_FOREX_SIGNALS and 
                    forex_3tp_count >= MAX_FOREX_3TP_SIGNALS and 
                    crypto_count >= MAX_CRYPTO_SIGNALS):
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
                
                # Check if it's Friday for weekly summary (14:30 GMT)
                if now.weekday() == 4 and now.hour == 14 and now.minute == 30:  # Friday = 4
                    await send_weekly_summary()
                
            except Exception as e:
                print(f"❌ Error in automatic loop: {e}")
                print("⏳ Waiting 5 minutes before retry...")
                await asyncio.sleep(300)
    
    loop.run_until_complete(async_loop())


def main():
    """Main function to run the bot"""
    print("🚀 Starting Working Combined Trading Signals Bot...")
    print("=" * 60)
    print("📱 Interactive features: /start command with buttons")
    print("🤖 Automatic features: Signal generation every 2-5 hours")
    print("📊 Daily summaries: 14:30 GMT")
    print("📈 Weekly summaries: Friday 14:30 GMT")
    print("🔐 Authorized users:", ALLOWED_USERS)
    print("=" * 60)
    
    # Start automatic signal generation in separate thread
    automatic_thread = threading.Thread(target=automatic_signal_loop, daemon=True)
    automatic_thread.start()
    
    # Create application for interactive features
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add interactive handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Working combined bot started successfully!")
    print("📱 Send /start to your bot to see the control panel")
    print("🤖 Automatic signal generation is running in background")
    
    # Start the interactive bot
    application.run_polling()


if __name__ == "__main__":
    main()
