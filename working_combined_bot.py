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
FOREX_CHANNEL = "-1001286609636"
FOREX_CHANNEL_3TP = "-1001220540048"  # New forex channel with 3 TPs
CRYPTO_CHANNEL_LINGRID = "-1002978318746"  # Crypto Lingrid channel
CRYPTO_CHANNEL_GAINMUSE = "-1001411205299"  # Crypto Gain muse channel
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
MIN_INTERVAL = 3  # Changed to 3 hours minimum
MAX_INTERVAL = 5  # Keep 5 hours maximum


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
            if "tp_notifications" not in signals:
                signals["tp_notifications"] = []
            return signals
    except:
        return {
            "forex": [], 
            "forex_3tp": [], 
            "crypto": [], 
            "forwarded_forex": [],
            "tp_notifications": [],
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


def calculate_signal_profit(signal, current_price):
    """Calculate profit for a signal with proper units (pips for forex, % for crypto)"""
    try:
        pair = signal.get("pair", "")
        signal_type = signal.get("type", "")
        entry = signal.get("entry", 0)
        sl = signal.get("sl", 0)
        
        # Determine if it's crypto or forex
        is_crypto = pair in CRYPTO_PAIRS
        
        if is_crypto:
            # Crypto signals: Calculate profit in percentage
            if signal_type == "BUY":
                profit_pct = ((current_price - entry) / entry) * 100
            else:  # SELL
                profit_pct = ((entry - current_price) / entry) * 100
            return profit_pct
        else:
            # Forex signals: Calculate profit in pips
            if pair.endswith("JPY"):
                # JPY pairs use 3 decimal places, so multiply by 1000
                multiplier = 1000
            else:
                # Other pairs use 5 decimal places, so multiply by 10000
                multiplier = 10000
            
            if signal_type == "BUY":
                profit_pips = (current_price - entry) * multiplier
            else:  # SELL
                profit_pips = (entry - current_price) * multiplier
            
            return profit_pips
                    
    except Exception as e:
        print(f"❌ Error calculating profit for {pair}: {e}")
        return 0


def get_performance_summary(signals_list, days=1):
    """Get comprehensive performance summary for signals"""
    try:
        if not signals_list:
            return {
                "total_signals": 0,
                "profit_signals": 0,
                "loss_signals": 0,
                "total_profit": 0,
                "avg_profit_per_signal": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "signals_detail": []
            }
        
        # Filter signals by date range
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        filtered_signals = []
        
        for signal in signals_list:
            try:
                signal_date = datetime.fromisoformat(signal.get("timestamp", "").replace("Z", "+00:00"))
                if signal_date >= cutoff_date:
                    filtered_signals.append(signal)
            except:
                # If timestamp parsing fails, include the signal
                filtered_signals.append(signal)
        
        if not filtered_signals:
            return {
                "total_signals": 0,
                "profit_signals": 0,
                "loss_signals": 0,
                "total_profit": 0,
                "avg_profit_per_signal": 0,
                "win_rate": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "signals_detail": []
            }
        
        # Calculate performance for each signal
        signals_detail = []
        total_profit = 0
        profit_count = 0
        loss_count = 0
        profit_values = []
        loss_values = []
        
        for signal in filtered_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            
            # Get current price
            if pair in CRYPTO_PAIRS:
                current_price = get_real_crypto_price(pair)
            else:
                current_price = get_real_forex_price(pair)
            
            if current_price is None:
                continue
            
            # Calculate profit
            profit_value = calculate_signal_profit(signal, current_price)
            
            # Determine unit and format display
            is_crypto = pair in CRYPTO_PAIRS
            if is_crypto:
                # Crypto: profit in percentage
                unit = "%"
                profit_display = f"{profit_value:+.2f}{unit}"
            else:
                # Forex: profit in pips
                unit = " pips"
                profit_display = f"{profit_value:+.1f}{unit}"
            
            if profit_value > 0:
                profit_count += 1
                total_profit += profit_value
                profit_values.append(profit_value)
                signals_detail.append(f"✅ {pair} {signal_type}: {profit_display}")
            elif profit_value < 0:
                loss_count += 1
                total_profit += profit_value
                loss_values.append(abs(profit_value))
                signals_detail.append(f"❌ {pair} {signal_type}: {profit_display}")
            else:
                signals_detail.append(f"➖ {pair} {signal_type}: 0.00{unit}")
        
        # Calculate advanced statistics
        total_signals = len(filtered_signals)
        avg_profit_per_signal = total_profit / total_signals if total_signals > 0 else 0
        win_rate = (profit_count / total_signals * 100) if total_signals > 0 else 0
        avg_profit = sum(profit_values) / len(profit_values) if profit_values else 0
        avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0
        
        # Calculate profit factor
        total_profit_sum = sum(profit_values) if profit_values else 0
        total_loss_sum = sum(loss_values) if loss_values else 0
        profit_factor = total_profit_sum / total_loss_sum if total_loss_sum > 0 else float('inf')
        
        return {
            "total_signals": total_signals,
            "profit_signals": profit_count,
            "loss_signals": loss_count,
            "total_profit": total_profit,
            "avg_profit_per_signal": avg_profit_per_signal,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "signals_detail": signals_detail
        }
        
    except Exception as e:
        print(f"❌ Error calculating performance summary: {e}")
        return {
            "total_signals": 0,
            "profit_signals": 0,
            "loss_signals": 0,
            "total_profit": 0,
            "avg_profit_per_signal": 0,
            "win_rate": 0,
            "avg_profit": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "signals_detail": []
        }


def save_performance(performance):
    """Save performance data"""
    with open(PERFORMANCE_FILE, 'w') as f:
        json.dump(performance, f, indent=2)


async def check_and_notify_tp_hits():
    """Check all active signals for TP hits and send notifications"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            return  # No signals for today
        
        bot = Bot(token=BOT_TOKEN)
        notifications_sent = signals.get("tp_notifications", [])
        
        # Check forex signals (2 TPs for main pairs, 1 TP for XAUUSD)
        forex_signals = signals.get("forex", [])
        for signal in forex_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
            # Check for TP hits based on pair type
            tp_hit = None
            profit_percent = 0
            
            if pair == "XAUUSD":
                # XAUUSD: Single TP
                tp = signal.get("tp", 0)
                if signal_type == "BUY" and current_price >= tp:
                    tp_hit = "TP"
                    profit_percent = ((tp - entry) / entry) * 100
                elif signal_type == "SELL" and current_price <= tp:
                    tp_hit = "TP"
                    profit_percent = ((entry - tp) / entry) * 100
            else:
                # Main forex pairs: 2 TPs
                tp1 = signal.get("tp1", 0)
                tp2 = signal.get("tp2", 0)
                
                if signal_type == "BUY":
                    if current_price >= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((tp2 - entry) / entry) * 100
                    elif current_price >= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((tp1 - entry) / entry) * 100
                else:  # SELL
                    if current_price <= tp2:
                        tp_hit = "TP2"
                        profit_percent = ((entry - tp2) / entry) * 100
                    elif current_price <= tp1:
                        tp_hit = "TP1"
                        profit_percent = ((entry - tp1) / entry) * 100
            
            if tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forex
                if pair.endswith("JPY"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    if tp_hit == "TP1":
                        profit_pips = (signal.get("tp1", 0) - entry) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (signal.get("tp2", 0) - entry) * multiplier
                    else:  # Single TP
                        profit_pips = (signal.get("tp", 0) - entry) * multiplier
                else:  # SELL
                    if tp_hit == "TP1":
                        profit_pips = (entry - signal.get("tp1", 0)) * multiplier
                    elif tp_hit == "TP2":
                        profit_pips = (entry - signal.get("tp2", 0)) * multiplier
                    else:  # Single TP
                        profit_pips = (entry - signal.get("tp", 0)) * multiplier
                
                # Calculate R/R ratio for forex
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((signal.get("tp1", 0) - entry) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((signal.get("tp2", 0) - entry) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((signal.get("tp", 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    if tp_hit == "TP1":
                        reward_pips = ((entry - signal.get("tp1", 0)) / entry) * 100
                    elif tp_hit == "TP2":
                        reward_pips = ((entry - signal.get("tp2", 0)) / entry) * 100
                    else:  # Single TP
                        reward_pips = ((entry - signal.get("tp", 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to forex channel
                if tp_hit == "TP2":
                    message = f"#{pair}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                else:
                    message = f"#{pair}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                await bot.send_message(chat_id=FOREX_CHANNEL, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_pips:.1f} pips")
        
        # Check forex 3TP signals
        forex_3tp_signals = signals.get("forex_3tp", [])
        for signal in forex_3tp_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp1 = signal.get("tp1", 0)
            tp2 = signal.get("tp2", 0)
            tp3 = signal.get("tp3", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
            # Check for TP hits
            tp_hit = None
            profit_percent = 0
            
            if signal_type == "BUY":
                if current_price >= tp3:
                    tp_hit = "TP3"
                    profit_percent = ((tp3 - entry) / entry) * 100
                elif current_price >= tp2:
                    tp_hit = "TP2"
                    profit_percent = ((tp2 - entry) / entry) * 100
                elif current_price >= tp1:
                    tp_hit = "TP1"
                    profit_percent = ((tp1 - entry) / entry) * 100
            else:  # SELL
                if current_price <= tp3:
                    tp_hit = "TP3"
                    profit_percent = ((entry - tp3) / entry) * 100
                elif current_price <= tp2:
                    tp_hit = "TP2"
                    profit_percent = ((entry - tp2) / entry) * 100
                elif current_price <= tp1:
                    tp_hit = "TP1"
                    profit_percent = ((entry - tp1) / entry) * 100
            
            if tp_hit and timestamp not in notifications_sent:
                # Calculate profit in pips for forex 3TP
                if pair.endswith("JPY"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    profit_pips = (signal.get(tp_hit.lower(), 0) - entry) * multiplier
                else:  # SELL
                    profit_pips = (entry - signal.get(tp_hit.lower(), 0)) * multiplier
                
                # Calculate R/R ratio for forex 3TP
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    reward_pips = ((signal.get(tp_hit.lower(), 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    reward_pips = ((entry - signal.get(tp_hit.lower(), 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to forex 3TP channel
                if tp_hit == "TP3":
                    message = f"#{pair}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                else:
                    message = f"#{pair}: TP{tp_hit[-1]} reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_pips:.1f} pips")
        
        # Check crypto signals
        crypto_signals = signals.get("crypto", [])
        for signal in crypto_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp1 = signal.get("tp1", 0)
            tp2 = signal.get("tp2", 0)
            tp3 = signal.get("tp3", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_crypto_price(pair)
            if current_price is None:
                continue
            
            # Check for TP hits
            tp_hit = None
            profit_percent = 0
            
            if signal_type == "BUY":
                if current_price >= tp3:
                    tp_hit = "TP3"
                    profit_percent = ((tp3 - entry) / entry) * 100
                elif current_price >= tp2:
                    tp_hit = "TP2"
                    profit_percent = ((tp2 - entry) / entry) * 100
                elif current_price >= tp1:
                    tp_hit = "TP1"
                    profit_percent = ((tp1 - entry) / entry) * 100
            else:  # SELL
                if current_price <= tp3:
                    tp_hit = "TP3"
                    profit_percent = ((entry - tp3) / entry) * 100
                elif current_price <= tp2:
                    tp_hit = "TP2"
                    profit_percent = ((entry - tp2) / entry) * 100
                elif current_price <= tp1:
                    tp_hit = "TP1"
                    profit_percent = ((entry - tp1) / entry) * 100
            
            if tp_hit and timestamp not in notifications_sent:
                # Calculate R/R ratio for crypto
                if signal_type == "BUY":
                    risk_pips = ((entry - sl) / entry) * 100
                    reward_pips = ((signal.get(tp_hit.lower(), 0) - entry) / entry) * 100
                else:  # SELL
                    risk_pips = ((sl - entry) / entry) * 100
                    reward_pips = ((entry - signal.get(tp_hit.lower(), 0)) / entry) * 100
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Send TP hit notification to crypto channels
                if tp_hit == "TP3":
                    message = f"#{pair}: Both targets 🚀🚀 hit +{profit_percent:.1f}% total gain!"
                else:
                    message = f"#{pair}: TP{tp_hit[-1]} reached ⚡️ +{profit_percent:.1f}% (R/R 1:{rr_ratio:.1f})"
                
                await bot.send_message(chat_id=CRYPTO_CHANNEL_LINGRID, text=message, parse_mode='Markdown')
                await bot.send_message(chat_id=CRYPTO_CHANNEL_GAINMUSE, text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ {tp_hit} hit notification sent for {pair} {signal_type}: +{profit_percent:.2f}%")
        
        # Check forwarded forex signals
        forwarded_signals = signals.get("forwarded_forex", [])
        for signal in forwarded_signals:
            pair = signal.get("pair", "")
            signal_type = signal.get("type", "")
            entry = signal.get("entry", 0)
            tp = signal.get("tp", 0)
            sl = signal.get("sl", 0)
            timestamp = signal.get("timestamp", "")
            
            # Get current price
            current_price = get_real_forex_price(pair)
            if current_price is None:
                continue
            
            # Check for TP hit
            tp_hit = False
            if signal_type == "BUY" and current_price >= tp:
                tp_hit = True
                profit_percent = ((tp - entry) / entry) * 100
            elif signal_type == "SELL" and current_price <= tp:
                tp_hit = True
                profit_percent = ((entry - tp) / entry) * 100
            
            if tp_hit and timestamp not in notifications_sent:
                # Send TP hit notification to the forwarded channel (-1001286609636)
                message = f"🎯 **TP HIT!**\n\n"
                message += f"**{pair} {signal_type}**\n"
                message += f"Entry: {entry:,.5f}\n"
                message += f"TP: {tp:,.5f}\n"
                message += f"Current: {current_price:,.5f}\n"
                message += f"**Profit: +{profit_percent:.2f}%**\n\n"
                message += f"⏰ Time: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
                
                await bot.send_message(chat_id="-1001286609636", text=message, parse_mode='Markdown')
                notifications_sent.append(timestamp)
                print(f"✅ TP hit notification sent for forwarded {pair} {signal_type}: +{profit_percent:.2f}%")
        
        # Save updated notifications list
        signals["tp_notifications"] = notifications_sent
        save_signals(signals)
        
    except Exception as e:
        print(f"❌ Error checking TP hits: {e}")


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
    
    # Calculate SL and TP based on real price with 2 TPs
    if pair == "XAUUSD":
        # Gold: 1-2% TP, 1-2% SL (single TP for XAUUSD)
        tp_percent = random.uniform(0.01, 0.02)  # 1-2%
        sl_percent = random.uniform(0.01, 0.02)  # 1-2%
        
        if signal_type == "BUY":
            tp = round(entry * (1 + tp_percent), 2)
            sl = round(entry * (1 - sl_percent), 2)
        else:  # SELL
            tp = round(entry * (1 - tp_percent), 2)
            sl = round(entry * (1 + sl_percent), 2)
        
        return {
            "pair": pair,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        # Main forex pairs: 2 TPs with doubled distances
        if signal_type == "BUY":
            sl = round(entry * 0.997, 5)  # 0.3% SL (doubled from 0.15%)
            tp1 = round(entry * 1.002, 5)  # 0.2% TP1 (doubled from 0.1%)
            tp2 = round(entry * 1.004, 5)  # 0.4% TP2 (doubled from 0.2%)
        else:  # SELL
            sl = round(entry * 1.003, 5)  # 0.3% SL (doubled from 0.15%)
            tp1 = round(entry * 0.998, 5)  # 0.2% TP1 (doubled from 0.1%)
            tp2 = round(entry * 0.996, 5)  # 0.4% TP2 (doubled from 0.2%)
    
    return {
        "pair": pair,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
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
    
    # Calculate SL and 3 TPs based on real price with new ranges
    if pair == "XAUUSD":
        # Gold: 1-2% SL, 1-2% TPs (randomized)
        sl_percent = random.uniform(0.01, 0.02)  # 1-2% SL
        tp1_percent = random.uniform(0.01, 0.02)  # 1-2% TP1
        tp2_percent = random.uniform(0.015, 0.025)  # 1.5-2.5% TP2
        tp3_percent = random.uniform(0.02, 0.03)  # 2-3% TP3
        
        if signal_type == "BUY":
            sl = round(entry * (1 - sl_percent), 2)
            tp1 = round(entry * (1 + tp1_percent), 2)
            tp2 = round(entry * (1 + tp2_percent), 2)
            tp3 = round(entry * (1 + tp3_percent), 2)
        else:  # SELL
            sl = round(entry * (1 + sl_percent), 2)
            tp1 = round(entry * (1 - tp1_percent), 2)
            tp2 = round(entry * (1 - tp2_percent), 2)
            tp3 = round(entry * (1 - tp3_percent), 2)
    else:
        # Main forex pairs: 0.2% TP1, 0.3% TP2, 0.4% TP3, 0.3% SL (doubled)
        if signal_type == "BUY":
            sl = round(entry * 0.997, 5)  # 0.3% SL (doubled from 0.15%)
            tp1 = round(entry * 1.002, 5)  # 0.2% TP1 (doubled from 0.1%)
            tp2 = round(entry * 1.003, 5)  # 0.3% TP2 (doubled from 0.15%)
            tp3 = round(entry * 1.004, 5)  # 0.4% TP3 (doubled from 0.2%)
        else:  # SELL
            sl = round(entry * 1.003, 5)  # 0.3% SL (doubled from 0.15%)
            tp1 = round(entry * 0.998, 5)  # 0.2% TP1 (doubled from 0.1%)
            tp2 = round(entry * 0.997, 5)  # 0.3% TP2 (doubled from 0.15%)
            tp3 = round(entry * 0.996, 5)  # 0.4% TP3 (doubled from 0.2%)
    
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
    
    # Calculate SL and TP based on real price with new ranges (2-10% TP, 4% SL)
    # Random TP percentages between 2-10%
    tp1_percent = random.uniform(0.02, 0.04)  # 2-4% TP1
    tp2_percent = random.uniform(0.05, 0.07)  # 5-7% TP2
    tp3_percent = random.uniform(0.08, 0.10)  # 8-10% TP3
    
    if signal_type == "BUY":
        sl = round(entry * 0.96, 6)  # 4% stop loss
        tp1 = round(entry * (1 + tp1_percent), 6)  # 2-4% first take profit
        tp2 = round(entry * (1 + tp2_percent), 6)  # 5-7% second take profit
        tp3 = round(entry * (1 + tp3_percent), 6)  # 8-10% third take profit
    else:  # SELL
        sl = round(entry * 1.04, 6)  # 4% stop loss
        tp1 = round(entry * (1 - tp1_percent), 6)  # 2-4% first take profit
        tp2 = round(entry * (1 - tp2_percent), 6)  # 5-7% second take profit
        tp3 = round(entry * (1 - tp3_percent), 6)  # 8-10% third take profit
    
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
    """Format forex signal message with 2 TPs"""
    pair = signal['pair']
    signal_type = signal['type']
    
    # Format numbers based on pair type
    if pair == "XAUUSD":
        # Gold: 2 decimal places (single TP)
        entry = f"{signal['entry']:,.2f}"
        sl = f"{signal['sl']:,.2f}"
        tp = f"{signal['tp']:,.2f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP {tp}"""
    elif pair.endswith("JPY"):
        # JPY pairs: 3 decimal places (2 TPs)
        entry = f"{signal['entry']:,.3f}"
        sl = f"{signal['sl']:,.3f}"
        tp1 = f"{signal['tp1']:,.3f}"
        tp2 = f"{signal['tp2']:,.3f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP1 {tp1}
TP2 {tp2}"""
    else:
        # Other forex pairs: 5 decimal places (2 TPs)
        entry = f"{signal['entry']:,.5f}"
        sl = f"{signal['sl']:,.5f}"
        tp1 = f"{signal['tp1']:,.5f}"
        tp2 = f"{signal['tp2']:,.5f}"
        return f"""{pair} {signal_type} {entry}
SL {sl}
TP1 {tp1}
TP2 {tp2}"""


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


def is_trading_hours():
    """Check if current time is within trading hours (4 GMT - 23 GMT)"""
    current_time = datetime.now(timezone.utc)
    current_hour = current_time.hour
    return 4 <= current_hour < 23


def get_next_interval():
    """Get next interval in seconds (3-5 hours)"""
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
        
        # Send to both crypto channels
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_LINGRID, text=message)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_GAINMUSE, text=message)
        
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
    """Send comprehensive daily summary with performance data"""
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
        
        # Calculate performance for each channel
        forex_performance = get_performance_summary(forex_signals, 1)
        forex_3tp_performance = get_performance_summary(forex_3tp_signals, 1)
        crypto_performance = get_performance_summary(crypto_signals, 1)
        
        # Create comprehensive summary message
        summary = f"""📊 **Daily Trading Signals Summary (24h)**
📅 Date: {today}

📈 **Forex Signals**
• Total: {len(forex_signals)}/{MAX_FOREX_SIGNALS}
• Performance: {forex_performance['total_profit']:+.2f}% total
• Win Rate: {forex_performance['win_rate']:.1f}%
• Profit Factor: {forex_performance['profit_factor']:.2f if forex_performance['profit_factor'] != float('inf') else '∞'}

📈 **Forex 3TP Signals**
• Total: {len(forex_3tp_signals)}/{MAX_FOREX_3TP_SIGNALS}
• Performance: {forex_3tp_performance['total_profit']:+.2f}% total
• Win Rate: {forex_3tp_performance['win_rate']:.1f}%
• Profit Factor: {forex_3tp_performance['profit_factor']:.2f if forex_3tp_performance['profit_factor'] != float('inf') else '∞'}

🪙 **Crypto Signals**
• Total: {len(crypto_signals)}/{MAX_CRYPTO_SIGNALS}
• Performance: {crypto_performance['total_profit']:+.2f}% total
• Win Rate: {crypto_performance['win_rate']:.1f}%
• Profit Factor: {crypto_performance['profit_factor']:.2f if crypto_performance['profit_factor'] != float('inf') else '∞'}

💰 **OVERALL PERFORMANCE**
• Total Signals: {forex_performance['total_signals'] + forex_3tp_performance['total_signals'] + crypto_performance['total_signals']}
• Combined Profit: {forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']:+.2f}%
• Average Win Rate: {(forex_performance['win_rate'] + forex_3tp_performance['win_rate'] + crypto_performance['win_rate']) / 3:.1f}%

⏰ Generated at: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"""
        
        # Send to user
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=SUMMARY_USER_ID, text=summary, parse_mode='Markdown')
        
        print(f"✅ Daily summary sent to user {SUMMARY_USER_ID}")
        
    except Exception as e:
        print(f"❌ Error sending daily summary: {e}")


async def send_weekly_summary():
    """Send comprehensive weekly summary with performance data"""
    try:
        # Get signals from last 7 days
        today = datetime.now(timezone.utc)
        week_ago = today - timedelta(days=7)
        
        # Load current signals
        signals = load_signals()
        
        # Get all signals from the last 7 days (we'll need to load from performance data)
        # For now, let's use the current signals and calculate performance
        forex_signals = signals.get("forex", [])
        forex_3tp_signals = signals.get("forex_3tp", [])
        crypto_signals = signals.get("crypto", [])
        
        # Calculate performance for each channel over 7 days
        forex_performance = get_performance_summary(forex_signals, 7)
        forex_3tp_performance = get_performance_summary(forex_3tp_signals, 7)
        crypto_performance = get_performance_summary(crypto_signals, 7)
        
        # Create comprehensive weekly summary message
        summary = f"""📊 **Weekly Trading Signals Summary (7 days)**
📅 Period: {week_ago.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}

📈 **Forex Signals**
• Total: {forex_performance['total_signals']}
• Performance: {forex_performance['total_profit']:+.2f}% total
• Win Rate: {forex_performance['win_rate']:.1f}%
• Profit Factor: {forex_performance['profit_factor']:.2f if forex_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {forex_performance['avg_profit']:+.2f}%
• Average Loss: {forex_performance['avg_loss']:+.2f}%

📈 **Forex 3TP Signals**
• Total: {forex_3tp_performance['total_signals']}
• Performance: {forex_3tp_performance['total_profit']:+.2f}% total
• Win Rate: {forex_3tp_performance['win_rate']:.1f}%
• Profit Factor: {forex_3tp_performance['profit_factor']:.2f if forex_3tp_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {forex_3tp_performance['avg_profit']:+.2f}%
• Average Loss: {forex_3tp_performance['avg_loss']:+.2f}%

🪙 **Crypto Signals**
• Total: {crypto_performance['total_signals']}
• Performance: {crypto_performance['total_profit']:+.2f}% total
• Win Rate: {crypto_performance['win_rate']:.1f}%
• Profit Factor: {crypto_performance['profit_factor']:.2f if crypto_performance['profit_factor'] != float('inf') else '∞'}
• Average Win: {crypto_performance['avg_profit']:+.2f}%
• Average Loss: {crypto_performance['avg_loss']:+.2f}%

💰 **OVERALL WEEKLY PERFORMANCE**
• Total Signals: {forex_performance['total_signals'] + forex_3tp_performance['total_signals'] + crypto_performance['total_signals']}
• Combined Profit: {forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']:+.2f}%
• Average Win Rate: {(forex_performance['win_rate'] + forex_3tp_performance['win_rate'] + crypto_performance['win_rate']) / 3:.1f}%
• Daily Average: {(forex_performance['total_profit'] + forex_3tp_performance['total_profit'] + crypto_performance['total_profit']) / 7:+.2f}%

⏰ Generated at: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"""
        
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
    
    # Main menu: Channel selection buttons
    keyboard = [
        [InlineKeyboardButton("📊 Forex 3TP", callback_data="channel_forex_3tp")],
        [InlineKeyboardButton("📈 Forex", callback_data="channel_forex")],
        [InlineKeyboardButton("🪙 Crypto Lingrid", callback_data="channel_crypto_lingrid")],
        [InlineKeyboardButton("💎 Crypto Gain Muse", callback_data="channel_crypto_gainmuse")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Trading Signals Bot Control Panel**

**Select a channel to manage:**

📊 **Forex 3TP** - Forex signals with 3 take profit levels
📈 **Forex** - Standard forex signals
🪙 **Crypto Lingrid** - Crypto channel 1
💎 **Crypto Gain Muse** - Crypto channel 2

*Click any channel button to proceed*
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
    
    # Channel selection (level 1)
    if query.data.startswith("channel_"):
        channel_type = query.data.replace("channel_", "")
        await show_channel_menu(query, context, channel_type)
    # Channel actions (level 2)
    elif query.data.startswith("result_24h_"):
        channel_type = query.data.replace("result_24h_", "")
        await handle_performance_report(query, context, channel_type, days=1)
    elif query.data.startswith("result_7d_"):
        channel_type = query.data.replace("result_7d_", "")
        await handle_performance_report(query, context, channel_type, days=7)
    elif query.data.startswith("give_signal_"):
        channel_type = query.data.replace("give_signal_", "")
        await handle_give_signal(query, context, channel_type)
    elif query.data == "back_to_main":
        await show_main_menu(query, context)
    # Legacy handlers for backward compatibility
    elif query.data == "forex_signal":
        await handle_forex_signal(query, context)
    elif query.data == "forex_3tp_signal":
        await handle_forex_3tp_signal(query, context)
    elif query.data == "crypto_signal":
        await handle_crypto_signal(query, context)
    elif query.data == "forex_performance":
        await handle_performance_report(query, context, "forex", days=1)
    elif query.data == "forex_3tp_performance":
        await handle_performance_report(query, context, "forex_3tp", days=1)
    elif query.data == "crypto_performance":
        await handle_performance_report(query, context, "crypto", days=1)
    elif query.data == "forex_status":
        await handle_forex_status(query, context)
    elif query.data == "forex_3tp_status":
        await handle_forex_3tp_status(query, context)
    elif query.data == "crypto_status":
        await handle_crypto_status(query, context)
    elif query.data == "forward_forex":
        await handle_forward_forex(query, context)
    elif query.data == "refresh":
        await show_main_menu(query, context)


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu with channel selection"""
    keyboard = [
        [InlineKeyboardButton("📊 Forex 3TP", callback_data="channel_forex_3tp")],
        [InlineKeyboardButton("📈 Forex", callback_data="channel_forex")],
        [InlineKeyboardButton("🪙 Crypto Lingrid", callback_data="channel_crypto_lingrid")],
        [InlineKeyboardButton("💎 Crypto Gain Muse", callback_data="channel_crypto_gainmuse")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Trading Signals Bot Control Panel**

**Select a channel to manage:**

📊 **Forex 3TP** - Forex signals with 3 take profit levels
📈 **Forex** - Standard forex signals
🪙 **Crypto Lingrid** - Crypto channel 1
💎 **Crypto Gain Muse** - Crypto channel 2

*Click any channel button to proceed*
    """
    
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_channel_menu(query, context: ContextTypes.DEFAULT_TYPE, channel_type: str) -> None:
    """Show channel-specific menu with actions"""
    # Channel names mapping
    channel_names = {
        "forex_3tp": "Forex 3TP",
        "forex": "Forex",
        "crypto_lingrid": "Crypto Lingrid",
        "crypto_gainmuse": "Crypto Gain Muse"
    }
    
    channel_name = channel_names.get(channel_type, channel_type)
    
    keyboard = [
        [InlineKeyboardButton("📊 Result 24h", callback_data=f"result_24h_{channel_type}")],
        [InlineKeyboardButton("📈 Result 7 days", callback_data=f"result_7d_{channel_type}")],
        [InlineKeyboardButton("🚀 Give signal", callback_data=f"give_signal_{channel_type}")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = f"""
📺 **{channel_name} Channel**

**Available actions:**

📊 **Result 24h** - Check profit from all signals in last 24 hours
📈 **Result 7 days** - Check profit from all signals in last 7 days
🚀 **Give signal** - Generate and send a signal to this channel

*Select an action*
    """
    
    await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_give_signal(query, context: ContextTypes.DEFAULT_TYPE, channel_type: str) -> None:
    """Handle signal generation for a specific channel"""
    await query.edit_message_text("🔄 Generating signal with real price...")
    
    try:
        if channel_type == "forex_3tp":
            await handle_forex_3tp_signal(query, context)
        elif channel_type == "forex":
            await handle_forex_signal(query, context)
        elif channel_type == "crypto_lingrid":
            await handle_crypto_signal_for_channel(query, context, CRYPTO_CHANNEL_LINGRID, "crypto_lingrid")
        elif channel_type == "crypto_gainmuse":
            await handle_crypto_signal_for_channel(query, context, CRYPTO_CHANNEL_GAINMUSE, "crypto_gainmuse")
        else:
            await query.edit_message_text(
                f"❌ **Unknown channel type:** {channel_type}",
                parse_mode='Markdown'
            )
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating signal:**\n\n{str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_signal_for_channel(query, context: ContextTypes.DEFAULT_TYPE, channel_id: str, channel_type: str) -> None:
    """Handle crypto signal generation for a specific channel"""
    await query.edit_message_text("🔄 Generating crypto signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "date": today}
        
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
        
        # Send to specified channel
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=channel_id, text=message)
        
        # Calculate distribution
        crypto_signals = signals.get("crypto", [])
        buy_count = len([s for s in crypto_signals if s.get("type") == "BUY"])
        total_crypto = len(crypto_signals)
        buy_ratio = (buy_count / total_crypto * 100) if total_crypto > 0 else 0
        sell_ratio = ((total_crypto - buy_count) / total_crypto * 100) if total_crypto > 0 else 0
        
        # Show channel menu again
        await show_channel_menu(query, context, channel_type)
        
        print(f"✅ Crypto signal sent to {channel_id}: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating crypto signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex signal generation"""
    await query.edit_message_text("🔄 Generating forex signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "forwarded_forex": [], "date": today}
        
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
        
        # Show channel menu again
        await show_channel_menu(query, context, "forex")
        
        print(f"✅ Forex signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error generating forex signal**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_3tp_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex 3TP signal generation"""
    await query.edit_message_text("🔄 Generating forex 3TP signal with real price...")
    
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            signals = {"forex": [], "forex_3tp": [], "crypto": [], "forwarded_forex": [], "date": today}
        
        if len(signals.get("forex_3tp", [])) >= MAX_FOREX_3TP_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Forex 3TP Signal Limit Reached**\n\n"
                f"Today's forex 3TP signals: {len(signals['forex_3tp'])}/{MAX_FOREX_3TP_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        # Generate signal
        signal = generate_forex_3tp_signal()
        
        if signal is None:
            await query.edit_message_text(
                "❌ **Could not generate forex 3TP signal**\n\n"
                "All forex pairs may already have active signals today.",
                parse_mode='Markdown'
            )
            return
        
        signals["forex_3tp"].append(signal)
        save_signals(signals)
        
        # Send to channel
        bot = Bot(token=BOT_TOKEN)
        message = format_forex_3tp_signal(signal)
        await bot.send_message(chat_id=FOREX_CHANNEL_3TP, text=message)
        
        # Show channel menu again
        await show_channel_menu(query, context, "forex_3tp")
        
        print(f"✅ Forex 3TP signal sent: {signal['pair']} {signal['type']} at {signal['entry']}")
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error sending forex 3TP signal:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
        print(f"❌ Error sending forex 3TP signal: {e}")


async def handle_performance_report(query, context: ContextTypes.DEFAULT_TYPE, signal_type: str, days: int) -> None:
    """Handle performance report for specific signal type"""
    await query.edit_message_text(f"🔄 Calculating {signal_type} performance for last {days} day(s)...")
    
    try:
        signals = load_signals()
        
        # Get signals for the specified type
        if signal_type == "forex":
            signals_list = signals.get("forex", [])
            channel_name = "Forex"
        elif signal_type == "forex_3tp":
            signals_list = signals.get("forex_3tp", [])
            channel_name = "Forex 3TP"
        elif signal_type == "crypto" or signal_type == "crypto_lingrid" or signal_type == "crypto_gainmuse":
            signals_list = signals.get("crypto", [])
            if signal_type == "crypto_lingrid":
                channel_name = "Crypto Lingrid"
            elif signal_type == "crypto_gainmuse":
                channel_name = "Crypto Gain Muse"
            else:
                channel_name = "Crypto"
        else:
            await query.edit_message_text("❌ Invalid signal type")
            return
        
        # Calculate performance
        performance = get_performance_summary(signals_list, days)
        
        # Create back button
        keyboard = [[InlineKeyboardButton("⬅️ Back to Channel Menu", callback_data=f"channel_{signal_type}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if performance["total_signals"] == 0:
            await query.edit_message_text(
                f"📊 **{channel_name} Performance Report**\n\n"
                f"📅 **Period:** Last {days} day(s)\n"
                f"📈 **Total Signals:** 0\n\n"
                f"No signals found for this period.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Format comprehensive performance report
        report = f"📊 **{channel_name} Performance Report**\n\n"
        report += f"📅 **Period:** Last {days} day(s)\n\n"
        
        # Summary statistics
        report += "📈 **SUMMARY**\n"
        report += f"Total Signals: {performance['total_signals']}\n"
        report += f"Winning Signals: {performance['profit_signals']} ({performance['win_rate']:.1f}%)\n"
        report += f"Losing Signals: {performance['loss_signals']} ({100-performance['win_rate']:.1f}%)\n\n"
        
        # Profit/Loss details
        report += "💰 **PROFIT/LOSS**\n"
        report += f"Total Profit: {performance['total_profit']:+.2f}%\n"
        report += f"Average per Signal: {performance['avg_profit_per_signal']:+.2f}%\n"
        if performance['profit_signals'] > 0:
            report += f"Average Win: {performance['avg_profit']:+.2f}%\n"
        if performance['loss_signals'] > 0:
            report += f"Average Loss: {performance['avg_loss']:+.2f}%\n"
        if performance['profit_factor'] != float('inf'):
            report += f"Profit Factor: {performance['profit_factor']:.2f}\n"
        else:
            report += "Profit Factor: ∞\n"
        report += "\n"
        
        # Individual signal results (only for short periods)
        if days <= 3 and performance['signals_detail']:
            report += "📋 **INDIVIDUAL SIGNALS**\n"
        for signal_detail in performance["signals_detail"]:
            report += f"{signal_detail}\n"
            report += "\n"
        
        # Performance rating
        win_rate = performance['win_rate']
        profit_factor = performance['profit_factor']
        
        if win_rate >= 70 and profit_factor >= 2.0:
            rating = "🏆 EXCELLENT"
        elif win_rate >= 60 and profit_factor >= 1.5:
            rating = "🥇 VERY GOOD"
        elif win_rate >= 50 and profit_factor >= 1.0:
            rating = "🥈 GOOD"
        elif win_rate >= 40:
            rating = "🥉 FAIR"
        else:
            rating = "⚠️ NEEDS IMPROVEMENT"
        
        report += f"🎯 **PERFORMANCE RATING: {rating}**"
        
        await query.edit_message_text(report, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error calculating performance:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
        print(f"❌ Error calculating performance: {e}")


async def handle_forex_3tp_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex 3TP status check"""
    try:
        signals = load_signals()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if signals.get("date") != today:
            forex_3tp_signals = []
        else:
            forex_3tp_signals = signals.get("forex_3tp", [])
        
        forex_3tp_count = len(forex_3tp_signals)
        active_pairs = [s["pair"] for s in forex_3tp_signals]
        active_pairs_text = ", ".join(active_pairs) if active_pairs else "None"
        
        await query.edit_message_text(
            f"📈 **Forex 3TP Status**\n\n"
            f"📊 Today's signals: {forex_3tp_count}/{MAX_FOREX_3TP_SIGNALS}\n"
            f"📋 Active pairs: {active_pairs_text}\n\n"
            f"{'✅ Ready to generate more signals' if forex_3tp_count < MAX_FOREX_3TP_SIGNALS else '⚠️ Daily limit reached'}\n"
            f"🤖 Automatic signals: Running in background",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error checking forex 3TP status:**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )
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
        
        # Send to both crypto channels
        bot = Bot(token=BOT_TOKEN)
        message = format_crypto_signal(signal)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_LINGRID, text=message)
        await bot.send_message(chat_id=CRYPTO_CHANNEL_GAINMUSE, text=message)
        
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
    await show_main_menu(query, context)


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
                current_time = datetime.now(timezone.utc)
                current_hour = current_time.hour
                
                # Check if we're in trading hours (4 GMT - 23 GMT)
                if not is_trading_hours():
                    print(f"🌙 Outside trading hours ({current_hour}:00 GMT). Market closed.")
                    # Still check for TP hits
                    await check_and_notify_tp_hits()
                    
                    # Wait until trading hours start
                    if current_hour < 4:
                        # Wait until 4 GMT
                        next_trading_time = current_time.replace(hour=4, minute=0, second=0, microsecond=0)
                    else:  # current_hour >= 23
                        # Wait until 4 GMT next day
                        next_trading_time = (current_time + timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
                    
                    wait_seconds = (next_trading_time - current_time).total_seconds()
                    print(f"⏰ Waiting {wait_seconds/3600:.1f} hours until trading hours...")
                    await asyncio.sleep(wait_seconds)
                    continue
                
                # Check if we need to send signals
                signals = load_signals()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                if signals.get("date") != today:
                    signals = {"forex": [], "forex_3tp": [], "crypto": [], "forwarded_forex": [], "tp_notifications": [], "date": today}
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
                
                # Check for TP hits and send notifications
                await check_and_notify_tp_hits()
                
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
