import os
import time
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

from telegram import Bot
from data_router import get_price, get_candles, AssetClass, ForbiddenDataSourceError
from config import Config


# Telegram configuration: HARDCODED PRIMARY, ENV override
# Import hardcoded config for Telegram
try:
    from config_hardcoded import get_hardcoded_config
    _hardcoded_config = get_hardcoded_config()
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", _hardcoded_config.telegram_bot_token)
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", _hardcoded_config.telegram_channel_id)
except ImportError:
    # Fallback if config_hardcoded not available
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003118256304")

# Global Twelve Data client state (FOREX data source)
_twelve_data_client = None


# Forex pairs (without .FOREX suffix - will be handled by router)
# NOTE: XAUUSD is GOLD (Yahoo Finance), NOT FOREX - removed from this list
DEFAULT_PAIRS = [
    "EURUSD",
    "GBPUSD", 
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "GBPCAD",
    "GBPNZD",
]

SIGNALS_FILE = "active_signals.json"
PERFORMANCE_FILE = "performance.json"
MAX_SIGNALS_PER_DAY = 5
PERFORMANCE_USER_ID = 615348532  # Telegram user ID for performance reports


def format_price(pair: str, price: float) -> str:
    # JPY pairs often quoted with 3 decimals; XAUUSD with 2 decimals; others 5
    if pair.endswith("JPY.FOREX"):
        return f"{price:,.3f}"
    elif pair == "XAUUSD.FOREX":
        return f"{price:,.2f}"
    return f"{price:,.5f}"


def fetch_realtime_price(symbol: str) -> Tuple[Optional[float], Dict]:
    """
    Get real-time price using data router (strict source policy)
    
    Returns:
        Tuple of (price: float or None, data_dict)
        If price is None, data_dict contains "reason" field
    
    Raises:
        ForbiddenDataSourceError: If attempting to use forbidden source
    """
    # Remove .FOREX suffix if present (legacy format)
    clean_symbol = symbol.replace(".FOREX", "")
    
    try:
        price, reason, source = get_price(clean_symbol)
        
        # Return in format expected by existing code
        result_data = {
            "close": price if price else None,
            "timestamp": int(time.time()),
            "source": source,
            "reason": reason if price is None else None
        }
        
        return price, result_data
    except ForbiddenDataSourceError as e:
        print(f"❌ [FORBIDDEN] {e}")
        raise
    except Exception as e:
        print(f"❌ Error fetching price for {clean_symbol}: {e}")
        return None, {"close": None, "timestamp": int(time.time()), "source": "ERROR", "reason": str(e)}


def fetch_intraday_bars(symbol: str, interval: str = "1m", limit: int = 120) -> List[Dict]:
    """
    Get intraday bars using data router (strict source policy)
    
    NOTE: Currently candles are not fully implemented in router.
    For now, this function will raise an error to prevent using forbidden sources.
    
    Raises:
        ForbiddenDataSourceError: If attempting to use forbidden source (EODHD, etc.)
        NotImplementedError: If candles not available for this asset class
    """
    # Remove .FOREX suffix if present
    clean_symbol = symbol.replace(".FOREX", "")
    
    # Check if this is a FOREX symbol trying to use forbidden intraday endpoint
    if symbol.endswith(".FOREX") or clean_symbol in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "GBPCAD", "GBPNZD"]:
        raise ForbiddenDataSourceError(
            f"FOREX symbol {clean_symbol} cannot use intraday endpoints. "
            f"Use Twelve Data API for candles. "
            f"EODHD and other HTTP intraday endpoints are FORBIDDEN for FOREX."
        )
    
    # Try to get candles from router
    candles, reason, source = get_candles(clean_symbol, interval, limit)
    
    if candles is None:
        raise NotImplementedError(
            f"Candles not available for {clean_symbol} from {source}. "
            f"Reason: {reason}. "
            f"FOREX candles must come from Twelve Data, GOLD/INDEX from Yahoo Finance."
        )
    
    return candles


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
            current_price, price_data = fetch_realtime_price(signal["symbol"])
            
            # CRITICAL: Skip if price is None (source unavailable)
            if current_price is None:
                reason = price_data.get("reason", "unknown")
                source = price_data.get("source", "unknown")
                print(f"⏸️ Skipping TP/SL check for {signal['symbol']}: price unavailable (source={source}, reason={reason})")
                # Keep signal active - will check again next time
                updated_signals.append(signal)
                continue
            
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
    
    # FOREX signals now use Twelve Data (no cTrader dependency)
    
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
            # Get real-time price using data router (strict source policy)
            try:
                rt_price, price_data = fetch_realtime_price(sym)
                entry = rt_price
                source = price_data.get("source", "UNKNOWN")
                
                # Check if price unavailable (skip this pair)
                if entry is None:
                    reason = price_data.get("reason", "unknown")
                    print(f"  ⏸️ Price unavailable for {sym}: {reason} (will retry next loop)")
                    continue
                
                print(f"  Real-time entry price: {entry} (source: {source})")
            except ForbiddenDataSourceError as e:
                print(f"  ❌ FORBIDDEN DATA SOURCE: {e}")
                print(f"  Skipping {sym} - cannot use forbidden source")
                continue
            except Exception as e:
                print(f"  Failed to get real-time price: {e}")
                print(f"  Skipping {sym}")
                continue
            
            # Simple signal generation based on price only (no historical bars needed)
            # For FOREX: use Twelve Data price (via router)
            # For GOLD: use Yahoo Finance price directly
            # Generate random signal direction for now (can be improved with trend detection)
            import random
            signal_type = random.choice(["BUY", "SELL"])
            
            # Use different TP/SL logic for XAUUSD vs forex pairs
            clean_sym = sym.replace(".FOREX", "")
            if clean_sym == "XAUUSD":
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
                if clean_sym.endswith("JPY"):
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


async def startup_init():
    """Initialize Twelve Data client for FOREX data"""
    global _twelve_data_client
    
    print("[STARTUP] Initializing Twelve Data client for FOREX...")
    
    try:
        from twelve_data_client import TwelveDataClient
        from config_hardcoded import get_hardcoded_config
        
        config = get_hardcoded_config()
        
        def safe_preview(value: str, length: int = 6) -> str:
            if not value:
                return "(not set)"
            if len(value) <= length:
                return value[:length] + "..."
            return value[:length] + "..."
        
        print(f"[STARTUP] [TWELVE_DATA] Config loaded:")
        print(f"   api_key={safe_preview(config.twelve_data_api_key, 6)} (source={config.source_map.get('twelve_data_api_key', 'HARDCODED')})")
        print(f"   base_url={config.twelve_data_base_url}")
        print(f"   timeout={config.twelve_data_timeout}s")
        
        # Create Twelve Data client
        _twelve_data_client = TwelveDataClient(
            api_key=config.twelve_data_api_key,
            base_url=config.twelve_data_base_url,
            timeout=config.twelve_data_timeout
        )
        
        # Test connection with a simple price request
        print("[STARTUP] Testing Twelve Data connection...")
        test_price = await _twelve_data_client.get_price("EURUSD")
        if test_price:
            print(f"[STARTUP] ✅ Twelve Data connection test successful (EURUSD={test_price:.5f})")
        else:
            print("[STARTUP] ⚠️ Twelve Data connection test failed, but client initialized (will retry on demand)")
        
        # Create DataRouter with injected Twelve Data client
        from data_router import DataRouter, set_data_router
        data_router = DataRouter(twelve_data_client=_twelve_data_client)
        set_data_router(data_router)
        print("[STARTUP] ✅ DataRouter initialized with Twelve Data client")
        
        # Self-check: verify router can get price
        print("[STARTUP] Self-check: testing DataRouter.get_price('EURUSD')...")
        try:
            check_price, check_reason, check_source = data_router.get_price("EURUSD")
            if check_price:
                print(f"[STARTUP] ✅ Self-check passed: EURUSD={check_price:.5f} (source={check_source})")
            else:
                print(f"[STARTUP] ⚠️ Self-check warning: EURUSD=None (reason={check_reason}, source={check_source})")
        except Exception as e:
            print(f"[STARTUP] ⚠️ Self-check error: {type(e).__name__}: {e}")
        
        print("[STARTUP] ✅ Twelve Data client initialized - FOREX signals enabled")
        return True
        
    except ImportError as e:
        print(f"[STARTUP] ❌ Failed to import twelve_data_client: {type(e).__name__}: {e}")
        print(f"[STARTUP] ⚠️ FOREX signals will be unavailable")
        _twelve_data_client = None
        return False
    except Exception as e:
        print(f"[STARTUP] ❌ Error initializing Twelve Data: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        _twelve_data_client = None
        return False


async def main_async():
    # Initialize Twelve Data client for FOREX
    twelve_data_init_success = await startup_init()
    
    if not twelve_data_init_success:
        print("⚠️ [MAIN] Twelve Data initialization failed - FOREX signals may be unavailable")
        print("   Bot will continue working, but FOREX pairs may fail")
    
    # Generate signals (client stays open during execution)
    pairs = DEFAULT_PAIRS
    await post_signals_once(pairs)
    
    # Cleanup: close Twelve Data client only at the very end
    global _twelve_data_client
    if _twelve_data_client:
        await _twelve_data_client.close()
        print("[MAIN] ✅ Twelve Data client closed")


async def ctrader_auth_test():
    """Test cTrader authentication flow without starting full bot"""
    print("[CTRADER_AUTH_TEST] Starting cTrader authentication test...")
    
    try:
        from ctrader_async_client import CTraderAsyncClient, CTraderAsyncError
        from config import Config
        
        # Get cTrader config
        ctrader_config = Config.get_ctrader_config()
        ws_url, ws_source = ctrader_config.get_ws_url()
        
        print(f"[CTRADER_AUTH_TEST] Config: ws_url={ws_url}, account_id={ctrader_config.account_id}, is_demo={ctrader_config.is_demo}")
        
        # Create client
        client = CTraderAsyncClient(
            ws_url=ws_url,
            client_id=ctrader_config.client_id,
            client_secret=ctrader_config.client_secret,
            access_token=ctrader_config.access_token,
            account_id=ctrader_config.account_id,
            is_demo=ctrader_config.is_demo
        )
        
        # Connect
        print("[CTRADER_AUTH_TEST] Step 1: Connecting to WebSocket...")
        await client.connect()
        print("[CTRADER_AUTH_TEST] ✅ WebSocket connected")
        
        # ApplicationAuth
        print("[CTRADER_AUTH_TEST] Step 2: ApplicationAuth...")
        await client.auth_application()
        print("[CTRADER_AUTH_TEST] ✅ ApplicationAuth succeeded")
        
        # AccountAuth
        print("[CTRADER_AUTH_TEST] Step 3: AccountAuth...")
        await client.auth_account()
        print("[CTRADER_AUTH_TEST] ✅ AccountAuth succeeded")
        
        # Test price fetch
        print("[CTRADER_AUTH_TEST] Step 4: Testing price fetch for EURUSD...")
        price = client.get_last_price("EURUSD")
        if price:
            print(f"[CTRADER_AUTH_TEST] ✅ Price fetch OK: EURUSD = {price:.5f}")
        else:
            print("[CTRADER_AUTH_TEST] ⚠️ Price fetch returned None (symbol may need subscription)")
        
        # Close
        await client.close()
        print("[CTRADER_AUTH_TEST] ✅ Test completed successfully")
        return True
        
    except CTraderAsyncError as e:
        print(f"[CTRADER_AUTH_TEST] ❌ FAILED: {e.reason}: {e.message}")
        import traceback
        print(traceback.format_exc())
        return False
    except Exception as e:
        print(f"[CTRADER_AUTH_TEST] ❌ FAILED: {type(e).__name__}: {e}")
        import traceback
        print(traceback.format_exc())
        return False


if __name__ == "__main__":
    import sys
    if "--ctrader-auth-test" in sys.argv:
        # Run authentication test only
        success = asyncio.run(ctrader_auth_test())
        sys.exit(0 if success else 1)
    else:
        # Run normal bot
        asyncio.run(main_async())