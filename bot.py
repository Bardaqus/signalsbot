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
    "XAUUSD.FOREX",  # Gold
]

SIGNALS_FILE = "active_signals.json"
PERFORMANCE_FILE = "performance.json"
MAX_SIGNALS_PER_DAY = 5
PERFORMANCE_USER_ID = 615348532  # Telegram user ID for performance reports


class EODHDError(Exception):
    pass


def format_price(pair: str, price: float) -> str:
    # JPY pairs often quoted with 3 decimals; XAUUSD with 2 decimals; others 5
    if pair.endswith("JPY.FOREX"):
        return f"{price:,.3f}"
    elif pair == "XAUUSD.FOREX":
        return f"{price:,.2f}"
    return f"{price:,.5f}"


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


def generate_signal_from_bars(bars: List[Dict], symbol: str = "") -> Tuple[str, Dict[str, float]]:
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

    # Use different TP/SL logic for XAUUSD vs forex pairs
    if symbol == "XAUUSD.FOREX":
        # XAUUSD: 3-5% profit target, same for SL
        profit_pct = 0.04  # 4% average (between 3-5%)
        sl_pct = 0.04  # 4% SL (same as TP)
        
        if signal == "BUY":
            entry = last
            sl = entry * (1 - sl_pct)  # 4% below entry
            tp = entry * (1 + profit_pct)  # 4% above entry
        else:  # SELL
            entry = last
            sl = entry * (1 + sl_pct)  # 4% above entry
            tp = entry * (1 - profit_pct)  # 4% below entry
    else:
        # Forex pairs: fixed pip distances (doubled) with 2 TPs
        sl_pips = 192  # Average SL distance (doubled from 96)
        tp1_pips = 103  # First TP distance (original)
        tp2_pips = 206  # Second TP distance (doubled)
        
        # Adjust for JPY pairs (3 decimal places) - 2x bigger range
        if symbol.endswith("JPY.FOREX"):
            sl_distance = (sl_pips * 2) / 1000  # JPY pairs use 3 decimals, 2x bigger range
            tp1_distance = (tp1_pips * 2) / 1000
            tp2_distance = (tp2_pips * 2) / 1000
        else:
            sl_distance = sl_pips / 10000  # Other pairs use 5 decimals
            tp1_distance = tp1_pips / 10000
            tp2_distance = tp2_pips / 10000
        
        if signal == "BUY":
            entry = last
            sl = entry - sl_distance
            tp1 = entry + tp1_distance
            tp2 = entry + tp2_distance
        else:  # SELL
            entry = last
            sl = entry + sl_distance
            tp1 = entry - tp1_distance
            tp2 = entry - tp2_distance

    return signal, {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
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


def add_signal(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float = None) -> None:
    """Add new signal to tracking with 2 TPs"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if tp2 is not None:
        # Forex signals with 2 TPs
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "date": today,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active"  # active, hit_sl, hit_tp1, hit_tp2
        }
    else:
        # XAUUSD signals with 1 TP (backward compatibility)
        signal = {
            "symbol": symbol,
            "type": signal_type,
            "entry": entry,
            "sl": sl,
            "tp": tp1,
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
    """Add completed signal to performance tracking with proper units"""
    performance_data = load_performance_data()
    
    # Determine if it's crypto or forex based on symbol
    is_crypto = not symbol.endswith(".FOREX")
    
    if is_crypto:
        # Crypto signals: Calculate profit in percentage
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
            "profit_pips": None,  # Not applicable for crypto
            "unit": "percentage",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
    else:
        # Forex signals: Calculate profit in pips
        if symbol.endswith("JPY.FOREX"):
            # JPY pairs use 3 decimal places, so multiply by 1000
            multiplier = 1000
        else:
            # Other pairs use 5 decimal places, so multiply by 10000
            multiplier = 10000
        
        if signal_type == "BUY":
            profit_pips = (exit_price - entry) * multiplier
        else:  # SELL
            profit_pips = (entry - exit_price) * multiplier
        
        # Also calculate percentage for consistency
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
            "profit_pips": profit_pips,
            "unit": "pips",
            "status": status,
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
            
            hit_sl = False
            hit_tp = None
            
            # Check for 2 TPs (forex signals)
            if "tp1" in signal and "tp2" in signal:
                tp1 = signal["tp1"]
                tp2 = signal["tp2"]
                
                if signal_type == "BUY":
                    hit_sl = current_price <= sl
                    if current_price >= tp2:
                        hit_tp = "TP2"
                    elif current_price >= tp1:
                        hit_tp = "TP1"
                else:  # SELL
                    hit_sl = current_price >= sl
                    if current_price <= tp2:
                        hit_tp = "TP2"
                    elif current_price <= tp1:
                        hit_tp = "TP1"
            else:
                # Single TP (XAUUSD signals - backward compatibility)
                tp = signal["tp"]
                
                if signal_type == "BUY":
                    hit_sl = current_price <= sl
                    hit_tp = "TP" if current_price >= tp else None
                else:  # SELL
                    hit_sl = current_price >= sl
                    hit_tp = "TP" if current_price <= tp else None
            
            if hit_tp:
                # Calculate profit - adjust multiplier for JPY pairs
                if signal["symbol"].endswith("JPY.FOREX"):
                    # JPY pairs use 3 decimal places, so multiply by 1000
                    multiplier = 1000
                else:
                    # Other pairs use 5 decimal places, so multiply by 10000
                    multiplier = 10000
                
                if signal_type == "BUY":
                    profit_pips = (current_price - entry) * multiplier
                else:  # SELL
                    profit_pips = (entry - current_price) * multiplier
                
                # Build original signal message for reply
                if "tp1" in signal and "tp2" in signal:
                    original_signal_msg = build_signal_message(signal["symbol"], signal_type, entry, sl, signal["tp1"], signal["tp2"])
                else:
                    original_signal_msg = build_signal_message(signal["symbol"], signal_type, entry, sl, signal["tp"])
                
                # Calculate R/R ratio
                if signal_type == "BUY":
                    risk_pips = (entry - sl) * multiplier
                    if hit_tp == "TP1":
                        reward_pips = (signal["tp1"] - entry) * multiplier
                    elif hit_tp == "TP2":
                        reward_pips = (signal["tp2"] - entry) * multiplier
                    else:  # Single TP
                        reward_pips = (signal["tp"] - entry) * multiplier
                else:  # SELL
                    risk_pips = (sl - entry) * multiplier
                    if hit_tp == "TP1":
                        reward_pips = (entry - signal["tp1"]) * multiplier
                    elif hit_tp == "TP2":
                        reward_pips = (entry - signal["tp2"]) * multiplier
                    else:  # Single TP
                        reward_pips = (entry - signal["tp"]) * multiplier
                
                rr_ratio = reward_pips / risk_pips if risk_pips > 0 else 0
                
                # Create TP hit message
                if hit_tp == "TP2":
                    profit_msg = f"#{signal['symbol'].replace('.FOREX', '')}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!"
                else:
                    profit_msg = f"#{signal['symbol'].replace('.FOREX', '')}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
                
                profit_messages.append(profit_msg)
                
                # Add to performance tracking
                add_completed_signal(signal["symbol"], signal_type, entry, current_price, f"hit_{hit_tp.lower()}")
                
                signal["status"] = f"hit_{hit_tp.lower()}"
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


def build_signal_message(symbol: str, signal_type: str, entry: float, sl: float, tp1: float, tp2: float = None) -> str:
    """Build signal message in the requested format with 2 TPs"""
    # Remove .FOREX suffix for display
    display_symbol = symbol.replace(".FOREX", "")
    
    if tp2 is not None:
        # Forex signals with 2 TPs
        return f"""{display_symbol} {signal_type} {format_price(symbol, entry)}
SL {format_price(symbol, sl)}
TP1 {format_price(symbol, tp1)}
TP2 {format_price(symbol, tp2)}"""
    else:
        # XAUUSD signals with 1 TP (backward compatibility)
        return f"""{display_symbol} {signal_type} {format_price(symbol, entry)}
SL {format_price(symbol, sl)}
TP {format_price(symbol, tp1)}"""


def get_performance_report(days: int = 1) -> str:
    """Generate comprehensive performance report for specified number of days"""
    performance_data = load_performance_data()
    now = datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    
    # Filter signals for the period
    recent_signals = [
        s for s in performance_data["completed_signals"]
        if s["date"] >= cutoff_date
    ]
    
    if not recent_signals:
        return f"📊 **No completed signals in the last {days} day(s)**"
    
    # Calculate statistics
    total_signals = len(recent_signals)
    profit_signals = [s for s in recent_signals if s["profit_pct"] > 0]
    loss_signals = [s for s in recent_signals if s["profit_pct"] <= 0]
    
    # Calculate totals
    total_profit_pct = sum(s["profit_pct"] for s in recent_signals)
    avg_profit_per_signal = total_profit_pct / total_signals if total_signals > 0 else 0
    
    # Calculate win rate
    win_rate = (len(profit_signals) / total_signals * 100) if total_signals > 0 else 0
    
    # Calculate average profit and loss
    avg_profit = sum(s["profit_pct"] for s in profit_signals) / len(profit_signals) if profit_signals else 0
    avg_loss = sum(s["profit_pct"] for s in loss_signals) / len(loss_signals) if loss_signals else 0
    
    # Calculate profit factor
    total_profit = sum(s["profit_pct"] for s in profit_signals)
    total_loss = abs(sum(s["profit_pct"] for s in loss_signals))
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    # Build report
    period = "24h" if days == 1 else f"{days} days"
    report_lines = [
        f"📊 **Performance Report - {period}**",
        f"📅 Period: {cutoff_date} to {now.strftime('%Y-%m-%d')}",
        "",
        "📈 **SUMMARY**",
        f"Total Signals: {total_signals}",
        f"Winning Signals: {len(profit_signals)} ({win_rate:.1f}%)",
        f"Losing Signals: {len(loss_signals)} ({100-win_rate:.1f}%)",
        "",
        "💰 **PROFIT/LOSS**",
        f"Total Profit: {total_profit_pct:+.2f}%",
        f"Average per Signal: {avg_profit_per_signal:+.2f}%",
        f"Average Win: {avg_profit:+.2f}%" if profit_signals else "Average Win: N/A",
        f"Average Loss: {avg_loss:+.2f}%" if loss_signals else "Average Loss: N/A",
        f"Profit Factor: {profit_factor:.2f}" if profit_factor != float('inf') else "Profit Factor: ∞",
        ""
    ]
    
    # Add individual signal results
    if days <= 3:  # Only show individual signals for short periods
        report_lines.append("📋 **INDIVIDUAL SIGNALS**")
        for signal in sorted(recent_signals, key=lambda x: x["timestamp"], reverse=True):
            symbol = signal["symbol"]
            signal_type = signal["type"]
            profit_pct = signal["profit_pct"]
            profit_pips = signal.get("profit_pips")
            unit = signal.get("unit", "percentage")
            status = "✅" if "hit_tp" in signal["status"] else "❌"
            sign = "+" if profit_pct > 0 else ""
            
            if unit == "pips" and profit_pips is not None:
                # Forex signals: show pips
                report_lines.append(f"{status} {symbol} {signal_type}: {sign}{profit_pips:.1f} pips ({sign}{profit_pct:.2f}%)")
            else:
                # Crypto signals: show percentage
                report_lines.append(f"{status} {symbol} {signal_type}: {sign}{profit_pct:.2f}%")
        report_lines.append("")
    
    # Add daily breakdown for weekly reports
    if days >= 7:
        report_lines.append("📅 **DAILY BREAKDOWN**")
        daily_stats = {}
        for signal in recent_signals:
            date = signal["date"]
            if date not in daily_stats:
                daily_stats[date] = {"total": 0, "profit": 0, "wins": 0, "losses": 0}
            daily_stats[date]["total"] += 1
            daily_stats[date]["profit"] += signal["profit_pct"]
            if signal["profit_pct"] > 0:
                daily_stats[date]["wins"] += 1
            else:
                daily_stats[date]["losses"] += 1
        
        for date in sorted(daily_stats.keys(), reverse=True):
            stats = daily_stats[date]
            win_rate_daily = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
            report_lines.append(f"{date}: {stats['total']} signals, {win_rate_daily:.0f}% win rate, {stats['profit']:+.2f}% total")
        report_lines.append("")
    
    # Add performance rating
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
    
    report_lines.append(f"🎯 **PERFORMANCE RATING: {rating}**")
    
    return "\n".join(report_lines)


async def send_performance_report(bot: Bot, days: int = 1) -> None:
    """Send comprehensive performance report to user and channels"""
    try:
        report = get_performance_report(days)
        period = "24h" if days == 1 else f"{days} days"
        
        # Send to user
        await bot.send_message(
            chat_id=PERFORMANCE_USER_ID,
            text=report,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        print(f"📊 Sent {period} performance report to user {PERFORMANCE_USER_ID}")
        
        # Send to forex channel as well
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=report,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        print(f"📊 Sent {period} performance report to forex channel")
        
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
    
    # Check if it's weekend (forex market is closed)
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    if weekday >= 5:  # Saturday (5) or Sunday (6)
        print("🏖️ Weekend detected - Forex market is closed. Skipping forex signal generation.")
        # Still check for TP hits and reports even on weekends
        await check_and_send_reports(bot)
        print("🔍 Checking for TP hits...")
        profit_messages = check_signal_hits()
        print(f"Found {len(profit_messages)} TP hits")
        for msg in profit_messages:
            print(f"Sending TP message: {msg}")
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
            await asyncio.sleep(0.4)
        return
    
    # Check if we're in trading hours (4 GMT - 23 GMT)
    current_hour = now.hour
    if current_hour < 4 or current_hour >= 23:
        print(f"🌙 Outside trading hours ({current_hour}:00 GMT). Market closed. Skipping forex signal generation.")
        # Still check for TP hits and reports even outside trading hours
        await check_and_send_reports(bot)
        print("🔍 Checking for TP hits...")
        profit_messages = check_signal_hits()
        print(f"Found {len(profit_messages)} TP hits")
        for msg in profit_messages:
            print(f"Sending TP message: {msg}")
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, disable_web_page_preview=True)
            await asyncio.sleep(0.4)
        return
    
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
            signal_type, metrics = generate_signal_from_bars(bars, sym)
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
                
                # Use different TP/SL logic for XAUUSD vs forex pairs
                if sym == "XAUUSD.FOREX":
                    # XAUUSD: 3-5% profit target, same for SL (single TP)
                    profit_pct = 0.04  # 4% average (between 3-5%)
                    sl_pct = 0.04  # 4% SL (same as TP)
                    
                    if signal_type == "BUY":
                        sl = entry * (1 - sl_pct)  # 4% below entry
                        tp = entry * (1 + profit_pct)  # 4% above entry
                    else:  # SELL
                        sl = entry * (1 + sl_pct)  # 4% above entry
                        tp = entry * (1 - profit_pct)  # 4% below entry
                    
                    print(f"  Entry: {entry}, SL: {sl}, TP: {tp}")
                    
                    # Add signal to tracking (single TP)
                    add_signal(sym, signal_type, entry, sl, tp)
                    
                    # Send signal message (single TP)
                    msg = build_signal_message(sym, signal_type, entry, sl, tp)
                else:
                    # Forex pairs: fixed pip distances with 2 TPs
                    sl_pips = 192  # Average SL distance (doubled from 96)
                    tp1_pips = 103  # First TP distance (original)
                    tp2_pips = 206  # Second TP distance (doubled)
                    
                    # Adjust for JPY pairs (3 decimal places) - 2x bigger range
                    if sym.endswith("JPY.FOREX"):
                        sl_distance = (sl_pips * 2) / 1000  # JPY pairs use 3 decimals, 2x bigger range
                        tp1_distance = (tp1_pips * 2) / 1000
                        tp2_distance = (tp2_pips * 2) / 1000
                    else:
                        sl_distance = sl_pips / 10000  # Other pairs use 5 decimals
                        tp1_distance = tp1_pips / 10000
                        tp2_distance = tp2_pips / 10000
                    
                    if signal_type == "BUY":
                        sl = entry - sl_distance
                        tp1 = entry + tp1_distance
                        tp2 = entry + tp2_distance
                    else:  # SELL
                        sl = entry + sl_distance
                        tp1 = entry - tp1_distance
                        tp2 = entry - tp2_distance
                    
                    print(f"  Entry: {entry}, SL: {sl}, TP1: {tp1}, TP2: {tp2}")
                    
                    # Add signal to tracking (2 TPs)
                    add_signal(sym, signal_type, entry, sl, tp1, tp2)
                    
                    # Send signal message (2 TPs)
                    msg = build_signal_message(sym, signal_type, entry, sl, tp1, tp2)
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