import os
import time
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from telegram import Bot


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")  # e.g. -1003118256304
EODHD_API_TOKEN = os.getenv("EODHD_API_TOKEN", "")

# Default to user's provided values if env vars not set
if not TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY"
if not TELEGRAM_CHANNEL_ID:
    TELEGRAM_CHANNEL_ID = "-1003118256304"
if not EODHD_API_TOKEN:
    EODHD_API_TOKEN = "65084a5c0c9bc3.41655158"


# EODHD forex symbol format typically: EURUSD.FOREX
DEFAULT_PAIRS = [
    "EURUSD.FOREX",
    "GBPUSD.FOREX", 
    "USDJPY.FOREX",
    "AUDUSD.FOREX",
    "USDCAD.FOREX",
    "USDCHF.FOREX",
    "GBPCAD.FOREX",
    "GBPNZD.FOREX",
]

SIGNALS_FILE = "active_signals.json"
PERFORMANCE_FILE = "performance.json"
MAX_SIGNALS_PER_DAY = 4
PERFORMANCE_USER_ID = 615348532  # Telegram user ID for performance reports


class EODHDError(Exception):
    pass


def format_price(pair: str, price: float) -> str:
    # JPY pairs often quoted with 3 decimals; others 5
    if pair.endswith("JPY.FOREX"):
        return f"{price:.3f}"
    return f"{price:.5f}"


@retry(
    retry=retry_if_exception_type(EODHDError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
)
def fetch_realtime_price(symbol: str) -> Tuple[float, Dict]:
    url = (
        f"https://eodhd.com/api/real-time/{symbol}?api_token={EODHD_API_TOKEN}&fmt=json"
    )
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        raise EODHDError(f"HTTP {resp.status_code} for {symbol}")
    data = resp.json()
    # Expected fields: close, timestamp etc
    if not isinstance(data, dict) or "close" not in data:
        raise EODHDError(f"Unexpected payload for {symbol}: {data}")
    return float(data["close"]), data


def fetch_intraday_bars(symbol: str, interval: str = "1m", limit: int = 120) -> List[Dict]:
    # EODHD intraday endpoint
    url = (
        f"https://eodhd.com/api/intraday/{symbol}?api_token={EODHD_API_TOKEN}&interval={interval}&fmt=json"
    )
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        raise EODHDError(f"HTTP {resp.status_code} for intraday {symbol}")
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise EODHDError(f"No intraday data for {symbol}")
    # Return last `limit` bars
    return data[-limit:]


def to_float_safe(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def simple_sma(values: List[float], window: int) -> float:
    if len(values) < window or window <= 0:
        return float("nan")
    return sum(values[-window:]) / window


def calculate_atr_proxy(bars: List[Dict], last_price: float) -> float:
    """Calculate ATR-like proxy for stop loss and take profit calculation"""
    ranges = []
    for b in bars[-14:]:
        h = to_float_safe(b.get("high"))
        l = to_float_safe(b.get("low"))
        if h is None and l is None:
            ranges.append(0.0)
            continue
        if h is None:
            h = to_float_safe(b.get("close")) or last_price
        if l is None:
            l = to_float_safe(b.get("close")) or last_price
        ranges.append(abs(h - l))
    return sum(ranges) / len(ranges) if ranges else 0.0


def generate_signal_from_bars(bars: List[Dict]) -> Tuple[str, Dict[str, float]]:
    closes: List[float] = []
    for b in bars:
        c = to_float_safe(b.get("close"))
        if c is not None:
            closes.append(c)
    if len(closes) < 5:  # Very low minimum requirement
        return "NO_SIGNAL", {}
    
    last = closes[-1]
    
    # Very simple and sensitive signal generation
    # Use just 3 and 7 period SMAs for more signals
    sma_fast = simple_sma(closes, 3)   # Very fast SMA
    sma_slow = simple_sma(closes, 7)   # Fast SMA
    
    if not all(map(lambda x: x == x, [sma_fast, sma_slow, last])):  # check for NaN
        return "NO_SIGNAL", {}

    # Calculate previous SMAs for crossover detection
    prev_fast = simple_sma(closes[:-1], 3) if len(closes) > 3 else sma_fast
    prev_slow = simple_sma(closes[:-1], 7) if len(closes) > 7 else sma_slow

    signal = "NO_SIGNAL"
    
    # Very sensitive crossover conditions
    if prev_fast <= prev_slow and sma_fast > sma_slow:
        signal = "BUY"
    elif prev_fast >= prev_slow and sma_fast < sma_slow:
        signal = "SELL"
    
    # Even more sensitive momentum conditions
    elif sma_fast > sma_slow and last > sma_fast:
        signal = "BUY"
    elif sma_fast < sma_slow and last < sma_fast:
        signal = "SELL"
    
    # Price momentum conditions
    elif len(closes) >= 3:
        recent_change = (last - closes[-3]) / closes[-3]
        if recent_change > 0.0001:  # 0.01% upward momentum
            signal = "BUY"
        elif recent_change < -0.0001:  # 0.01% downward momentum
            signal = "SELL"

    if signal == "NO_SIGNAL":
        return signal, {}

    # Calculate ATR proxy for better SL/TP
    atr_proxy = calculate_atr_proxy(bars, last)
    
    # Conservative SL/TP ratios
    if signal == "BUY":
        entry = last
        sl = entry - 1.0 * atr_proxy
        tp = entry + 2.0 * atr_proxy
    else:  # SELL
        entry = last
        sl = entry + 1.0 * atr_proxy
        tp = entry - 2.0 * atr_proxy

    return signal, {
        "entry": entry,
        "sl": sl,
        "tp": tp,
    }


def load_active_signals() -> List[Dict]:
    """Load active signals from file"""
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_active_signals(signals: List[Dict]) -> None:
    """Save active signals to file"""
    try:
        with open(SIGNALS_FILE, 'w') as f:
            json.dump(signals, f, indent=2)
    except Exception:
        pass


def get_today_signals_count() -> int:
    """Count signals generated today"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    active_signals = load_active_signals()
    return sum(1 for s in active_signals if s.get("date") == today)


def get_active_pairs() -> List[str]:
    """Get pairs that currently have active signals"""
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    active_pairs = []
    for signal in active_signals:
        if signal.get("status") == "active" and signal.get("date") == today:
            active_pairs.append(signal.get("symbol"))
    
    return active_pairs


def get_available_pairs(all_pairs: List[str]) -> List[str]:
    """Get pairs that don't have active signals"""
    active_pairs = get_active_pairs()
    return [pair for pair in all_pairs if pair not in active_pairs]


def add_signal(symbol: str, signal_type: str, entry: float, sl: float, tp: float) -> None:
    """Add new signal to tracking"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signal = {
        "symbol": symbol,
        "type": signal_type,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "date": today,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "active"  # active, hit_sl, hit_tp
    }
    active_signals = load_active_signals()
    active_signals.append(signal)
    save_active_signals(active_signals)


def load_performance_data() -> Dict:
    """Load performance tracking data"""
    try:
        if os.path.exists(PERFORMANCE_FILE):
            with open(PERFORMANCE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"completed_signals": []}


def save_performance_data(data: Dict) -> None:
    """Save performance tracking data"""
    try:
        with open(PERFORMANCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def add_completed_signal(symbol: str, signal_type: str, entry: float, exit_price: float, status: str) -> None:
    """Add completed signal to performance tracking"""
    performance_data = load_performance_data()
    
    # Calculate profit percentage
    if signal_type == "BUY":
        profit_pct = ((exit_price - entry) / entry) * 100
    else:  # SELL
        profit_pct = ((entry - exit_price) / entry) * 100
    
    completed_signal = {
        "symbol": symbol.replace(".FOREX", ""),  # Remove .FOREX for display
        "type": signal_type,
        "entry": entry,
        "exit_price": exit_price,
        "profit_pct": profit_pct,
        "status": status,  # "hit_tp" or "hit_sl"
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    }
    
    performance_data["completed_signals"].append(completed_signal)
    save_performance_data(performance_data)


def check_signal_hits() -> List[Dict]:
    """Check for SL/TP hits and return profit messages"""
    active_signals = load_active_signals()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    profit_messages = []
    updated_signals = []
    
    for signal in active_signals:
        if signal.get("status") != "active":
            updated_signals.append(signal)
            continue
            
        try:
            current_price, _ = fetch_realtime_price(signal["symbol"])
            signal_type = signal["type"]
            entry = signal["entry"]
            sl = signal["sl"]
            tp = signal["tp"]
            
            hit_sl = False
            hit_tp = False
            
            if signal_type == "BUY":
                hit_sl = current_price <= sl
                hit_tp = current_price >= tp
            else:  # SELL
                hit_sl = current_price >= sl
                hit_tp = current_price <= tp
            
            if hit_tp:
                # Calculate profit
                if signal_type == "BUY":
                    profit_pips = (current_price - entry) * 10000
                else:  # SELL
                    profit_pips = (entry - current_price) * 10000
                
                profit_msg = f"🎯 TP HIT! {signal['symbol'].replace('.FOREX', '')} {signal_type} - Profit: {profit_pips:.1f} pips"
                profit_messages.append(profit_msg)
                
                # Add to performance tracking
                add_completed_signal(signal["symbol"], signal_type, entry, current_price, "hit_tp")
                
                signal["status"] = "hit_tp"
                signal["exit_price"] = current_price
                signal["profit_pips"] = profit_pips
                
            elif hit_sl:
                # Add to performance tracking (no message for SL hits)
                add_completed_signal(signal["symbol"], signal_type, entry, current_price, "hit_sl")
                
                signal["status"] = "hit_sl"
                signal["exit_price"] = current_price
            
            updated_signals.append(signal)
            
        except Exception as e:
            print(f"❌ Error checking signal {signal['symbol']}: {e}")
            # Keep signal active if we can't check price
            updated_signals.append(signal)
    
    save_active_signals(updated_signals)
    return profit_messages


def build_signal_message(symbol: str, signal_type: str, entry: float, sl: float, tp: float) -> str:
    """Build signal message in the requested format"""
    # Remove .FOREX suffix for display
    display_symbol = symbol.replace(".FOREX", "")
    
    return f"""{display_symbol} {signal_type} {format_price(symbol, entry)}
SL {format_price(symbol, sl)}
TP {format_price(symbol, tp)}"""


def get_performance_report(days: int = 1) -> str:
    """Generate performance report for specified number of days"""
    performance_data = load_performance_data()
    now = datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Filter signals for the period
    recent_signals = [
        s for s in performance_data["completed_signals"]
        if s["date"] >= cutoff_date
    ]
    
    if not recent_signals:
        return f"No completed signals in the last {days} day(s)"
    
    # Build report
    lines = []
    total_signals = len(recent_signals)
    profit_signals = [s for s in recent_signals if s["profit_pct"] > 0]
    loss_signals = [s for s in recent_signals if s["profit_pct"] <= 0]
    
    # Individual signal results
    for signal in recent_signals:
        symbol = signal["symbol"]
        profit_pct = signal["profit_pct"]
        sign = "+" if profit_pct > 0 else ""
        lines.append(f"{symbol} {sign}{profit_pct:.1f}%")
    
    # Summary
    lines.append(f"\nTotal signals {total_signals}")
    lines.append(f"In profit: {len(profit_signals)}")
    lines.append(f"In loss: {len(loss_signals)}")
    
    # Calculate total profit percentage
    if total_signals > 0:
        total_profit = sum(s["profit_pct"] for s in recent_signals)
        lines.append(f"Profit: {total_profit:.1f}%")
    
    return "\n".join(lines)


async def send_performance_report(bot: Bot, days: int = 1) -> None:
    """Send performance report to user"""
    try:
        report = get_performance_report(days)
        period = "24h" if days == 1 else f"{days} days"
        title = f"📊 Performance Report - {period}\n\n"
        
        await bot.send_message(
            chat_id=PERFORMANCE_USER_ID,
            text=title + report,
            disable_web_page_preview=True
        )
        print(f"📊 Sent {period} performance report to user {PERFORMANCE_USER_ID}")
    except Exception as e:
        print(f"❌ Failed to send performance report: {e}")


async def check_and_send_reports(bot: Bot) -> None:
    """Check if it's time to send performance reports"""
    now = datetime.now(timezone.utc)
    
    # Check if it's 14:00 GMT
    if now.hour == 14 and now.minute == 0:
        # Daily report (every day)
        await send_performance_report(bot, days=1)
        
        # Weekly report (Fridays only)
        if now.weekday() == 4:  # Friday
            await send_performance_report(bot, days=7)


async def post_signals_once(pairs: List[str]) -> None:
    print("🤖 Starting bot...")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Check for performance reports first
    await check_and_send_reports(bot)
    
    # Then check for TP hits
    print("🔍 Checking for TP hits...")
    profit_messages = check_signal_hits()
    print(f"Found {len(profit_messages)} TP hits")
    for msg in profit_messages:
        print(f"Sending TP message: {msg}")
        await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
        await asyncio.sleep(0.4)
    
    # Check if we've already generated max signals today
    today_count = get_today_signals_count()
    print(f"Today's signal count: {today_count}/{MAX_SIGNALS_PER_DAY}")
    if today_count >= MAX_SIGNALS_PER_DAY:
        print(f"Already generated {today_count} signals today (max: {MAX_SIGNALS_PER_DAY})")
        return
    
    # Generate new signals
    signals_needed = MAX_SIGNALS_PER_DAY - today_count
    print(f"🎯 Generating new signals (need {signals_needed} more)...")
    
    if signals_needed <= 0:
        print("✅ Already have 4 signals for today")
        return
    
    # Get available pairs (no active signals)
    available_pairs = get_available_pairs(pairs)
    print(f"📊 Available pairs: {len(available_pairs)} (active pairs excluded)")
    
    if not available_pairs:
        print("⚠️ No available pairs - all pairs have active signals")
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
            bars = fetch_intraday_bars(sym, interval="1m", limit=120)
            print(f"  Got {len(bars)} bars for {sym}")
            signal_type, metrics = generate_signal_from_bars(bars)
            print(f"  Signal: {signal_type}")
            
            if signal_type in ("BUY", "SELL") and metrics:
                # Use real-time price as entry point instead of historical close
                try:
                    rt_price, _ = fetch_realtime_price(sym)
                    entry = rt_price
                    print(f"  Real-time entry price: {entry}")
                except Exception as e:
                    print(f"  Failed to get real-time price, using historical: {e}")
                    entry = metrics["entry"]
                
                # Recalculate SL and TP based on real-time entry price
                atr_proxy = calculate_atr_proxy(bars, entry)
                if signal_type == "BUY":
                    sl = entry - 1.0 * atr_proxy
                    tp = entry + 2.0 * atr_proxy
                else:  # SELL
                    sl = entry + 1.0 * atr_proxy
                    tp = entry - 2.0 * atr_proxy
                
                print(f"  Entry: {entry}, SL: {sl}, TP: {tp}")
                
                # Add signal to tracking
                add_signal(sym, signal_type, entry, sl, tp)
                
                # Send signal message
                msg = build_signal_message(sym, signal_type, entry, sl, tp)
                print(f"📤 Sending signal: {msg}")
                await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
                
                signals_generated += 1
                print(f"✅ Generated signal {signals_generated}: {sym} {signal_type}")
                
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
    
    print(f"🏁 Finished. Generated {signals_generated} new signals.")


async def main_async():
    pairs = DEFAULT_PAIRS
    await post_signals_once(pairs)


if __name__ == "__main__":
    asyncio.run(main_async())