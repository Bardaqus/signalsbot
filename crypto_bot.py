#!/usr/bin/env python3
"""
Crypto Signals Bot
Generates short-term crypto trading signals using Binance data
Sends signals to Telegram channel and tracks performance
"""

import os
import time
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from telegram import Bot
from binance.client import Client
from binance.exceptions import BinanceAPIException


# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
CRYPTO_CHANNEL_ID = "-1002978318746"  # Crypto signals channel
REPORT_USER_ID = 615348532  # User ID for performance reports

# Binance API (you'll need to set these as environment variables)
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# Crypto pairs to monitor
CRYPTO_PAIRS = [
    "BTCUSDT",
    "ETHUSDT", 
    "BNBUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOTUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "MATICUSDT"
]

# Signal configuration
MAX_SIGNALS_PER_DAY = 5
MIN_SIGNALS_PER_DAY = 3

# Files
CRYPTO_SIGNALS_FILE = "crypto_signals.json"
CRYPTO_PERFORMANCE_FILE = "crypto_performance.json"


class BinanceError(Exception):
    pass


def initialize_binance_client() -> Client:
    """Initialize Binance client"""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise BinanceError("Binance API credentials not provided")
    
    try:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        # Test connection
        client.get_account()
        return client
    except Exception as e:
        raise BinanceError(f"Failed to initialize Binance client: {e}")


@retry(
    retry=retry_if_exception_type(BinanceError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def get_crypto_price(symbol: str) -> float:
    """Get current crypto price from Binance"""
    try:
        client = initialize_binance_client()
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        raise BinanceError(f"Failed to get price for {symbol}: {e}")


@retry(
    retry=retry_if_exception_type(BinanceError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def get_crypto_klines(symbol: str, interval: str = "1m", limit: int = 100) -> List[List]:
    """Get crypto kline data from Binance"""
    try:
        client = initialize_binance_client()
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        return klines
    except Exception as e:
        raise BinanceError(f"Failed to get klines for {symbol}: {e}")


def calculate_technical_indicators(klines: List[List]) -> Dict:
    """Calculate technical indicators for signal generation"""
    if len(klines) < 20:
        return {}
    
    # Convert to DataFrame
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    # Convert to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    # Calculate indicators
    df['sma_5'] = df['close'].rolling(window=5).mean()
    df['sma_10'] = df['close'].rolling(window=10).mean()
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()
    
    # RSI calculation
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    
    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    
    return df.iloc[-1].to_dict()


def generate_crypto_signal(symbol: str) -> Tuple[str, Dict]:
    """Generate crypto trading signal based on technical analysis"""
    try:
        klines = get_crypto_klines(symbol, interval="1m", limit=100)
        indicators = calculate_technical_indicators(klines)
        
        if not indicators:
            return "NO_SIGNAL", {}
        
        current_price = indicators['close']
        sma_5 = indicators['sma_5']
        sma_10 = indicators['sma_10']
        sma_20 = indicators['sma_20']
        rsi = indicators['rsi']
        macd = indicators['macd']
        macd_signal = indicators['macd_signal']
        bb_upper = indicators['bb_upper']
        bb_lower = indicators['bb_lower']
        
        signal = "NO_SIGNAL"
        
        # Check if we should prefer BUY or SELL based on 73% BUY / 27% SELL ratio
        prefer_buy = should_generate_buy_signal()
        
        # Signal generation logic with ratio control
        # Bullish conditions
        if (sma_5 > sma_10 > sma_20 and 
            rsi < 70 and 
            macd > macd_signal and 
            current_price > sma_5):
            signal = "BUY"
        
        # Bearish conditions  
        elif (sma_5 < sma_10 < sma_20 and 
              rsi > 30 and 
              macd < macd_signal and 
              current_price < sma_5):
            signal = "SELL"
        
        # Additional momentum signals
        elif (current_price > bb_upper and rsi > 60 and macd > 0):
            signal = "BUY"
        elif (current_price < bb_lower and rsi < 40 and macd < 0):
            signal = "SELL"
        
        # If we have a signal but it doesn't match our preferred ratio, adjust
        if signal != "NO_SIGNAL":
            if prefer_buy and signal == "SELL":
                # Check if we can generate a BUY signal instead
                if (rsi < 80 and macd > -0.1):  # Relaxed BUY conditions
                    signal = "BUY"
            elif not prefer_buy and signal == "BUY":
                # Check if we can generate a SELL signal instead
                if (rsi > 20 and macd < 0.1):  # Relaxed SELL conditions
                    signal = "SELL"
        
        if signal == "NO_SIGNAL":
            return signal, {}
        
        # Calculate TP and SL levels
        if signal == "BUY":
            entry = current_price
            sl = entry * 0.98  # 2% stop loss
            tp1 = entry * 1.02  # 2% first take profit
            tp2 = entry * 1.04  # 4% second take profit  
            tp3 = entry * 1.06  # 6% third take profit
        else:  # SELL
            entry = current_price
            sl = entry * 1.02  # 2% stop loss
            tp1 = entry * 0.98  # 2% first take profit
            tp2 = entry * 0.96  # 4% second take profit
            tp3 = entry * 0.94  # 6% third take profit
        
        return signal, {
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3
        }
        
    except Exception as e:
        print(f"Error generating signal for {symbol}: {e}")
        return "NO_SIGNAL", {}


def load_crypto_signals() -> List[Dict]:
    """Load active crypto signals from file"""
    try:
        if os.path.exists(CRYPTO_SIGNALS_FILE):
            with open(CRYPTO_SIGNALS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_crypto_signals(signals: List[Dict]) -> None:
    """Save active crypto signals to file"""
    try:
        with open(CRYPTO_SIGNALS_FILE, 'w') as f:
            json.dump(signals, f, indent=2)
    except Exception:
        pass


def load_crypto_performance() -> Dict:
    """Load crypto performance data"""
    try:
        if os.path.exists(CRYPTO_PERFORMANCE_FILE):
            with open(CRYPTO_PERFORMANCE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"completed_signals": []}


def save_crypto_performance(data: Dict) -> None:
    """Save crypto performance data"""
    try:
        with open(CRYPTO_PERFORMANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_today_crypto_signals_count() -> int:
    """Count crypto signals generated today"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_crypto_signals()
    return sum(1 for s in active_signals if s.get("date") == today)


def get_today_crypto_signal_distribution() -> Dict[str, int]:
    """Get today's crypto signal distribution (BUY vs SELL)"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_crypto_signals()
    
    buy_count = sum(1 for s in active_signals if s.get("date") == today and s.get("type") == "BUY")
    sell_count = sum(1 for s in active_signals if s.get("date") == today and s.get("type") == "SELL")
    
    return {"BUY": buy_count, "SELL": sell_count}


def should_generate_buy_signal() -> bool:
    """Determine if next signal should be BUY based on 73% BUY / 27% SELL ratio"""
    distribution = get_today_crypto_signal_distribution()
    total_signals = distribution["BUY"] + distribution["SELL"]
    
    if total_signals == 0:
        return True  # First signal should be BUY
    
    buy_ratio = distribution["BUY"] / total_signals
    
    # If BUY ratio is less than 73%, prefer BUY
    if buy_ratio < 0.73:
        return True
    
    # If BUY ratio is 73% or higher, prefer SELL
    return False


def get_active_crypto_pairs() -> List[str]:
    """Get crypto pairs that currently have active signals"""
    active_signals = load_crypto_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    active_pairs = []
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            active_pairs.append(signal.get("symbol"))
    
    return active_pairs


def add_crypto_signal(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float, tp3: float) -> None:
    """Add new crypto signal to tracking"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal = {
        "symbol": symbol,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "sl_hit": False
    }
    active_signals = load_crypto_signals()
    active_signals.append(signal)
    save_crypto_signals(active_signals)


def check_crypto_signal_hits() -> List[Dict]:
    """Check for SL/TP hits and return profit messages"""
    active_signals = load_crypto_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    profit_messages = []
    updated_signals = []
    
    for signal in active_signals:
        if signal.get("status") != "active":
            updated_signals.append(signal)
            continue
            
        try:
            current_price = get_crypto_price(signal["symbol"])
            signal_type = signal["type"]
            entry = signal["entry"]
            sl = signal["sl"]
            tp1 = signal["tp1"]
            tp2 = signal["tp2"]
            tp3 = signal["tp3"]
            
            # Check TP hits first
            tp_hit = None
            if signal_type == "BUY":
                if current_price >= tp3 and not signal.get("tp3_hit"):
                    tp_hit = "tp3"
                elif current_price >= tp2 and not signal.get("tp2_hit"):
                    tp_hit = "tp2"
                elif current_price >= tp1 and not signal.get("tp1_hit"):
                    tp_hit = "tp1"
            else:  # SELL
                if current_price <= tp3 and not signal.get("tp3_hit"):
                    tp_hit = "tp3"
                elif current_price <= tp2 and not signal.get("tp2_hit"):
                    tp_hit = "tp2"
                elif current_price <= tp1 and not signal.get("tp1_hit"):
                    tp_hit = "tp1"
            
            # Check SL hit
            sl_hit = False
            if signal_type == "BUY":
                sl_hit = current_price <= sl
            else:  # SELL
                sl_hit = current_price >= sl
            
            if tp_hit:
                # Mark TP as hit
                signal[f"{tp_hit}_hit"] = True
                
                # Calculate profit percentage
                if signal_type == "BUY":
                    profit_pct = ((current_price - entry) / entry) * 100
                else:  # SELL
                    profit_pct = ((entry - current_price) / entry) * 100
                
                profit_msg = f"🎯 {tp_hit.upper()} HIT! {signal['symbol']} {signal_type} - Profit: {profit_pct:.2f}%"
                profit_messages.append(profit_msg)
                
                # Add to performance tracking
                add_completed_crypto_signal(signal["symbol"], signal_type, entry, current_price, tp_hit)
                
            elif sl_hit:
                # Determine which TP level was hit before SL
                if signal.get("tp3_hit"):
                    result = "tp3_sl"
                elif signal.get("tp2_hit"):
                    result = "tp2_sl"
                elif signal.get("tp1_hit"):
                    result = "tp1_sl"
                else:
                    result = "sl"
                
                # Calculate result
                if signal_type == "BUY":
                    profit_pct = ((current_price - entry) / entry) * 100
                else:  # SELL
                    profit_pct = ((entry - current_price) / entry) * 100
                
                # Add to performance tracking
                add_completed_crypto_signal(signal["symbol"], signal_type, entry, current_price, result)
                
                signal["status"] = "completed"
                signal["exit_price"] = current_price
                signal["result"] = result
            
            updated_signals.append(signal)
            
        except Exception as e:
            print(f"❌ Error checking signal {signal['symbol']}: {e}")
            updated_signals.append(signal)
    
    save_crypto_signals(updated_signals)
    return profit_messages


def add_completed_crypto_signal(symbol: str, signal_type: str, entry: float, exit_price: float, result: str) -> None:
    """Add completed crypto signal to performance tracking"""
    performance_data = load_crypto_performance()
    
    # Calculate profit percentage
    if signal_type == "BUY":
        profit_pct = ((exit_price - entry) / entry) * 100
    else:  # SELL
        profit_pct = ((entry - exit_price) / entry) * 100
    
    completed_signal = {
        "symbol": symbol,
        "type": signal_type,
        "entry": entry,
        "exit_price": exit_price,
        "profit_pct": profit_pct,
        "result": result,  # tp1, tp2, tp3, tp1_sl, tp2_sl, tp3_sl, sl
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    }
    
    performance_data["completed_signals"].append(completed_signal)
    save_crypto_performance(performance_data)


def build_crypto_signal_message(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float, tp3: float) -> str:
    """Build crypto signal message"""
    return f"""{symbol} {signal_type}
Entry: {entry:.6f}
SL: {sl:.6f}
TP1: {tp1:.6f}
TP2: {tp2:.6f}
TP3: {tp3:.6f}"""


def get_crypto_performance_report(days: int = 1) -> str:
    """Generate crypto performance report for specified number of days"""
    performance_data = load_crypto_performance()
    now = datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Filter signals for the period
    recent_signals = [
        s for s in performance_data["completed_signals"]
        if s["date"] >= cutoff_date
    ]
    
    if not recent_signals:
        return f"No completed crypto signals in the last {days} day(s)"
    
    # Build report
    lines = []
    total_signals = len(recent_signals)
    
    # Count results by type
    tp1_count = len([s for s in recent_signals if s["result"] == "tp1"])
    tp2_count = len([s for s in recent_signals if s["result"] == "tp2"])
    tp3_count = len([s for s in recent_signals if s["result"] == "tp3"])
    tp1_sl_count = len([s for s in recent_signals if s["result"] == "tp1_sl"])
    tp2_sl_count = len([s for s in recent_signals if s["result"] == "tp2_sl"])
    tp3_sl_count = len([s for s in recent_signals if s["result"] == "tp3_sl"])
    sl_count = len([s for s in recent_signals if s["result"] == "sl"])
    
    # Individual signal results
    for signal in recent_signals:
        symbol = signal["symbol"]
        profit_pct = signal["profit_pct"]
        result = signal["result"]
        sign = "+" if profit_pct > 0 else ""
        lines.append(f"{symbol} {sign}{profit_pct:.2f}% ({result})")
    
    # Count BUY vs SELL signals
    buy_signals = len([s for s in recent_signals if s["type"] == "BUY"])
    sell_signals = len([s for s in recent_signals if s["type"] == "SELL"])
    buy_ratio = (buy_signals / total_signals * 100) if total_signals > 0 else 0
    sell_ratio = (sell_signals / total_signals * 100) if total_signals > 0 else 0
    
    # Summary
    lines.append(f"\n📊 Summary:")
    lines.append(f"Total signals: {total_signals}")
    lines.append(f"BUY signals: {buy_signals} ({buy_ratio:.1f}%)")
    lines.append(f"SELL signals: {sell_signals} ({sell_ratio:.1f}%)")
    lines.append(f"TP1 hits: {tp1_count}")
    lines.append(f"TP2 hits: {tp2_count}")
    lines.append(f"TP3 hits: {tp3_count}")
    lines.append(f"TP1→SL: {tp1_sl_count}")
    lines.append(f"TP2→SL: {tp2_sl_count}")
    lines.append(f"TP3→SL: {tp3_sl_count}")
    lines.append(f"SL only: {sl_count}")
    
    # Calculate total profit percentage
    if total_signals > 0:
        total_profit = sum(s["profit_pct"] for s in recent_signals)
        lines.append(f"Total profit: {total_profit:.2f}%")
    
    return "\n".join(lines)


async def send_crypto_performance_report(bot: Bot, days: int = 1) -> None:
    """Send crypto performance report to user"""
    try:
        report = get_crypto_performance_report(days)
        period = "24h" if days == 1 else f"{days} days"
        title = f"📊 Crypto Signals Report - {period}\n\n"
        
        await bot.send_message(
            chat_id=REPORT_USER_ID,
            text=title + report,
            disable_web_page_preview=True
        )
        print(f"📊 Sent {period} crypto performance report to user {REPORT_USER_ID}")
    except Exception as e:
        print(f"❌ Failed to send crypto performance report: {e}")


async def check_and_send_crypto_reports(bot: Bot) -> None:
    """Check if it's time to send crypto performance reports"""
    now = datetime.now(timezone.utc)
    
    # Check if it's 14:30 GMT
    if now.hour == 14 and now.minute == 30:
        # Daily report (every day)
        await send_crypto_performance_report(bot, days=1)
        
        # Weekly report (Fridays only)
        if now.weekday() == 4:  # Friday
            await send_crypto_performance_report(bot, days=7)


async def post_crypto_signals_once(pairs: List[str]) -> None:
    """Generate and post crypto signals once"""
    print("🤖 Starting crypto bot...")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Check for performance reports first
    await check_and_send_crypto_reports(bot)
    
    # Then check for TP hits
    print("🔍 Checking for crypto TP hits...")
    profit_messages = check_crypto_signal_hits()
    print(f"Found {len(profit_messages)} crypto TP hits")
    for msg in profit_messages:
        print(f"Sending TP message: {msg}")
        await bot.send_message(chat_id=CRYPTO_CHANNEL_ID, text=msg, disable_web_page_preview=True)
        await asyncio.sleep(0.4)
    
    # Check if we've already generated enough signals today
    today_count = get_today_crypto_signals_count()
    print(f"Today's crypto signal count: {today_count}/{MAX_SIGNALS_PER_DAY}")
    
    if today_count >= MAX_SIGNALS_PER_DAY:
        print(f"Already generated {today_count} crypto signals today (max: {MAX_SIGNALS_PER_DAY})")
        return
    
    # Generate new signals
    signals_needed = MAX_SIGNALS_PER_DAY - today_count
    print(f"🎯 Generating new crypto signals (need {signals_needed} more)...")
    
    if signals_needed <= 0:
        print("✅ Already have enough crypto signals for today")
        return
    
    # Get available pairs (no active signals)
    active_pairs = get_active_crypto_pairs()
    available_pairs = [pair for pair in pairs if pair not in active_pairs]
    print(f"📊 Available crypto pairs: {len(available_pairs)} (active pairs excluded)")
    
    if not available_pairs:
        print("⚠️ No available crypto pairs - all pairs have active signals")
        return
    
    signals_generated = 0
    attempts = 0
    max_attempts = len(available_pairs) * 2  # Try each pair twice max
    
    while signals_generated < signals_needed and attempts < max_attempts:
        # Cycle through available pairs
        sym = available_pairs[attempts % len(available_pairs)]
        attempts += 1
        
        print(f"📊 Analyzing {sym} (attempt {attempts})...")
        try:
            signal_type, metrics = generate_crypto_signal(sym)
            print(f"  Signal: {signal_type}")
            
            if signal_type in ("BUY", "SELL") and metrics:
                entry = metrics["entry"]
                sl = metrics["sl"]
                tp1 = metrics["tp1"]
                tp2 = metrics["tp2"]
                tp3 = metrics["tp3"]
                
                print(f"  Entry: {entry}, SL: {sl}, TP1: {tp1}, TP2: {tp2}, TP3: {tp3}")
                
                # Add signal to tracking
                add_crypto_signal(sym, signal_type, entry, sl, tp1, tp2, tp3)
                
                # Send signal message
                msg = build_crypto_signal_message(sym, signal_type, entry, sl, tp1, tp2, tp3)
                print(f"📤 Sending crypto signal: {msg}")
                await bot.send_message(chat_id=CRYPTO_CHANNEL_ID, text=msg, disable_web_page_preview=True)
                
                signals_generated += 1
                print(f"✅ Generated crypto signal {signals_generated}: {sym} {signal_type}")
                
                # Remove this pair from available pairs since it now has an active signal
                if sym in available_pairs:
                    available_pairs.remove(sym)
                    print(f"  Removed {sym} from available pairs (now has active signal)")
                
            else:
                print(f"  No signal generated for {sym}")
                
            time.sleep(0.5)  # polite pacing for API calls
            
        except Exception as e:
            print(f"❌ Error processing {sym}: {e}")
            time.sleep(0.5)
    
    print(f"🏁 Finished. Generated {signals_generated} new crypto signals.")


async def main_crypto_async():
    """Main async function for crypto bot"""
    pairs = CRYPTO_PAIRS
    await post_crypto_signals_once(pairs)


if __name__ == "__main__":
    asyncio.run(main_crypto_async())
