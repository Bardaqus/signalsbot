"""
Telegram bot for Signals_bot - handles channel management and signal distribution
"""
import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from config import Config
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType, ChannelConfig, TradingAccount
from binance_client import BinanceClient
from ctrader_api import CTraderAPI
from datetime import datetime, timedelta, timezone
import uuid
import json
import os


class BotStates(StatesGroup):
    """Bot state machine states"""
    waiting_for_channel_name = State()
    waiting_for_account_name = State()
    waiting_for_signal_symbol = State()
    waiting_for_signal_type = State()
    waiting_for_entry_price = State()
    waiting_for_stop_loss = State()
    waiting_for_take_profit = State()


class SignalsBot:
    """Main Telegram bot class for signal management"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.signal_processor = SignalProcessor()
        self.binance = BinanceClient()
        self.ctrader = CTraderAPI()
        self.cached_market: dict[str, dict] = {}
        # Short-term crypto signals config
        self.target_channel_id = "-1002978318746"
        self.admin_user_id = 615348532
        self.popular_symbols = ["BTC", "ETH", "SOL", "XRP", "ADA", "BNB"]
        self.active_signals: dict[str, dict] = {}
        self.history_dir = os.path.join(os.path.dirname(__file__), "data", "history")
        os.makedirs(self.history_dir, exist_ok=True)
        # Named history files per specific channels (user-defined)
        self.named_history_map: dict[str, str] = {
            "-1001286609636": "signals_history_lingrid_forex.json",
            "-1002978318746": "signals_history_gainmuse.json",
            "-1001220540048": "signals_history_degram.json",
            "-1001411205299": "signals_history_lingrid_crypto.json",
        }
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Setup bot command and message handlers"""
        
        # Start command
        @self.dp.message(CommandStart())
        async def start_command(message: Message):
            await message.answer(
                "🤖 **Welcome to Signals Bot!**\n\n"
                "I can help you manage trading signals and execute them automatically.\n\n"
                "**Available commands:**\n"
                "/setup - Setup channels and accounts\n"
                "/signal - Create a new trading signal\n"
                "/test - Send a test signal\n"
                "/status - Check bot status\n"
                "/help - Show this help message\n\n"
                "Let's get started! 😊",
                parse_mode="Markdown"
            )
        
        # Help command
        @self.dp.message(Command("help"))
        async def help_command(message: Message):
            await message.answer(
                "📖 **Signals Bot Help**\n\n"
                "**Setup Commands:**\n"
                "/setup - Configure channels and trading accounts\n\n"
                "**Signal Commands:**\n"
                "/signal - Create and send a trading signal\n"
                "/test - Send a test signal to verify everything works\n\n"
                "**Status Commands:**\n"
                "/status - View bot statistics and configuration\n"
                "/history - View recent signal history\n\n"
                "**Support:**\n"
                "Need help? Contact the developer! 😊",
                parse_mode="Markdown"
            )

        # Signals command (crypto, from Binance)
        @self.dp.message(Command("signals"))
        async def crypto_signals_command(message: Message):
            try:
                symbols = ["BTC", "ETH", "SOL", "XRP", "ADA", "BNB"]
                data = await self.binance.fetch_tickers(symbols)
                self.cached_market = data or self.cached_market

                if not data:
                    await message.answer("❌ Failed to fetch data from Binance. Try again later.")
                    return

                lines = ["📣 Crypto Signals (Binance)"]
                for sym in symbols:
                    d = data.get(sym)
                    if not d:
                        continue
                    direction = "BUY" if d.get("change_24h", 0) >= 0 else "SELL"
                    entry = d["price"]
                    # Simple TP/SL based on 3h range and direction
                    if direction == "BUY":
                        tp = max(entry, d["max_price"])  # conservative TP near 24h high
                        sl = min(entry, d["min_price"])  # SL near 24h low
                    else:
                        tp = min(entry, d["min_price"])  # TP near 24h low
                        sl = max(entry, d["max_price"])  # SL near 24h high

                    lines.append(
                        f"{sym}/USDT — {direction}\n"
                        f"• Entry: ${entry:,.2f}\n"
                        f"• TP: ${tp:,.2f}\n"
                        f"• SL: ${sl:,.2f}"
                    )

                await message.answer("\n\n".join(lines))
            except Exception as e:
                logger.error(f"Error in /signals: {e}")
                await message.answer("❌ Error generating signals. Please try again.")

        # Admin summary now
        @self.dp.message(Command("summary"))
        async def summary_now(message: Message):
            if message.from_user.id != self.admin_user_id:
                await message.answer("Access denied")
                return
            await self._send_daily_summary()

        # TestForex: send 3 FOREX signals (formatted), using cTrader quotes if available
        @self.dp.message(Command("TestForex"))
        @self.dp.message(Command("testforex"))
        async def test_forex(message: Message):
            pairs = ["EURUSD", "GBPUSD", "GBPCAD", "GBPNZD", "USDJPY", "AUDUSD"]
            idx = (datetime.now(timezone.utc).minute) % len(pairs)
            chosen = (pairs[idx:] + pairs[:idx])[:3]
            lines = []
            for sym in chosen:
                text = await self._build_forex_signal_text(sym)
                lines.append(text)
            await message.answer("\n\n\n".join(lines))

        # TEST MODE: send 4 signals now, then summaries to a target user
        @self.dp.message(Command("testmode"))
        async def test_mode(message: Message):
            # Optional override: /testmode <chat_id>
            try:
                parts = (message.text or "").split()
                target_chat = int(parts[1]) if len(parts) > 1 else 501779863
            except Exception:
                target_chat = 501779863

            await message.answer("🚧 Test mode: sending 4 short-term signals now…")

            # Choose 4 symbols and generate signals immediately
            chosen = self.popular_symbols[:]
            # simple rotation by minute to vary set
            idx = (datetime.now(timezone.utc).minute) % len(chosen)
            chosen = (chosen[idx:] + chosen[:idx])[:4]
            for sym in chosen:
                await self._generate_and_send_signal(sym)
                await asyncio.sleep(0.5)

            await message.answer("✅ Test signals sent. Preparing summaries…")

            # Send 2-day and 7-day summaries to the specified target chat
            await self._send_summary_for_days(2, target_chat)
            await self._send_summary_for_days(7, target_chat)
        
        # Setup command
        @self.dp.message(Command("setup"))
        async def setup_command(message: Message):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Add Channel", callback_data="add_channel")],
                [InlineKeyboardButton(text="🏦 Add Account", callback_data="add_account")],
                [InlineKeyboardButton(text="📊 View Status", callback_data="view_status")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]
            ])
            
            await message.answer(
                "⚙️ **Setup Configuration**\n\n"
                "Choose what you'd like to configure:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        
        # Signal command
        @self.dp.message(Command("signal"))
        async def signal_command(message: Message):
            if not self.signal_processor.channels:
                await message.answer(
                    "❌ **No channels configured!**\n\n"
                    "Please run /setup first to add channels and accounts.",
                    parse_mode="Markdown"
                )
                return
                
            await message.answer(
                "📈 **Create Trading Signal**\n\n"
                "Please send the signal in the following format:\n\n"
                "**Symbol Direction EP SL TP**\n\n"
                "**Example:**\n"
                "`EURUSD BUY 1.0650 1.0600 1.0750`\n\n"
                "Or use the guided setup by typing the symbol first:",
                parse_mode="Markdown"
            )
            await state.set_state(BotStates.waiting_for_signal_symbol)
        
        # Test command
        @self.dp.message(Command("test"))
        async def test_command(message: Message):
            if not self.signal_processor.channels:
                await message.answer(
                    "❌ **No channels configured!**\n\n"
                    "Please run /setup first to add channels and accounts.",
                    parse_mode="Markdown"
                )
                return
                
            try:
                # Create a test signal
                test_signal = self.signal_processor.create_test_signal()
                
                # Send signal to channel
                channel_id = test_signal.channel_id
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=test_signal.to_telegram_message(),
                    parse_mode="Markdown"
                )
                
                # Process the signal (execute trade)
                history = await self.signal_processor.process_signal(test_signal)
                
                if test_signal.status.value == "EXECUTED":
                    await message.answer(
                        "✅ **Test signal sent successfully!**\n\n"
                        f"📊 Symbol: {test_signal.symbol}\n"
                        f"📈 Direction: {test_signal.trade_type}\n"
                        f"💰 Entry: {test_signal.entry_price}\n"
                        f"🛑 Stop Loss: {test_signal.stop_loss}\n"
                        f"🎯 Take Profit: {test_signal.take_profit}\n\n"
                        f"⚡ Execution time: {history.execution_time_ms}ms",
                        parse_mode="Markdown"
                    )
                else:
                    await message.answer(
                        f"❌ **Test signal failed!**\n\n"
                        f"Error: {test_signal.error_message}",
                        parse_mode="Markdown"
                    )
                    
            except Exception as e:
                logger.error(f"Error in test command: {e}")
                await message.answer(
                    f"❌ **Error during test:** {str(e)}",
                    parse_mode="Markdown"
                )
        
        # Status command
        @self.dp.message(Command("status"))
        async def status_command(message: Message):
            stats = self.signal_processor.get_statistics()
            
            status_text = f"""
📊 **Bot Status**

**Configuration:**
• Channels: {stats['active_channels']}
• Accounts: {stats['active_accounts']}

**Signal Statistics:**
• Total Signals: {stats['total_signals']}
• Executed: {stats['executed_signals']}
• Failed: {stats['failed_signals']}
• Success Rate: {stats['success_rate']:.1f}%

**Performance:**
• Avg Execution Time: {stats['avg_execution_time_ms']:.0f}ms
"""
            
            await message.answer(status_text, parse_mode="Markdown")
        
        # History command
        @self.dp.message(Command("history"))
        async def history_command(message: Message):
            history = self.signal_processor.get_signal_history(limit=5)
            
            if not history:
                await message.answer("📝 **No signal history available**")
                return
            
            history_text = "📝 **Recent Signal History**\n\n"
            
            for h in history:
                signal = h.signal
                status_emoji = "✅" if signal.status.value == "EXECUTED" else "❌"
                history_text += f"{status_emoji} {signal.symbol} {signal.trade_type}\n"
                history_text += f"   Entry: {signal.entry_price} | "
                if signal.stop_loss:
                    history_text += f"SL: {signal.stop_loss} | "
                if signal.take_profit:
                    history_text += f"TP: {signal.take_profit}"
                history_text += f"\n   Time: {h.created_at.strftime('%H:%M:%S')}\n\n"
            
            await message.answer(history_text, parse_mode="Markdown")
        
        # Callback query handlers
        @self.dp.callback_query()
        async def handle_callback(callback: CallbackQuery, state: FSMContext):
            data = callback.data
            
            if data == "add_channel":
                await callback.message.answer(
                    "➕ **Add New Channel**\n\n"
                    "Please send the channel ID (e.g., @mychannel or -1001234567890):",
                    parse_mode="Markdown"
                )
                await state.set_state(BotStates.waiting_for_channel_name)
                
            elif data == "add_account":
                await callback.message.answer(
                    "🏦 **Add New Account**\n\n"
                    "Please send the account name:",
                    parse_mode="Markdown"
                )
                await state.set_state(BotStates.waiting_for_account_name)
                
            elif data == "view_status":
                stats = self.signal_processor.get_statistics()
                status_text = f"""
📊 **Configuration Status**

**Channels:** {stats['active_channels']}
**Accounts:** {stats['active_accounts']}
**Total Signals:** {stats['total_signals']}
**Success Rate:** {stats['success_rate']:.1f}%
"""
                await callback.message.answer(status_text, parse_mode="Markdown")
                
            elif data == "back_to_main":
                await callback.message.answer(
                    "🏠 **Main Menu**\n\n"
                    "Use /setup, /signal, /test, or /status to continue.",
                    parse_mode="Markdown"
                )
            
            await callback.answer()
        
        # State handlers for guided setup
        @self.dp.message(BotStates.waiting_for_channel_name)
        async def process_channel_name(message: Message, state: FSMContext):
            channel_id = message.text.strip()
            
            # For now, use a default account - in production this would be more sophisticated
            if not self.signal_processor.accounts:
                # Create a default account
                self.signal_processor.add_account("demo_account", "Demo Account")
            
            account_id = list(self.signal_processor.accounts.keys())[0]
            
            success = self.signal_processor.add_channel(
                channel_id, 
                f"Channel {channel_id}", 
                account_id
            )
            
            if success:
                await message.answer(
                    f"✅ **Channel added successfully!**\n\n"
                    f"Channel: {channel_id}\n"
                    f"Account: {account_id}",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ **Failed to add channel!**\n\n"
                    "Channel might already exist or account not found.",
                    parse_mode="Markdown"
                )
            
            await state.clear()
        
        @self.dp.message(BotStates.waiting_for_account_name)
        async def process_account_name(message: Message, state: FSMContext):
            account_name = message.text.strip()
            account_id = f"account_{len(self.signal_processor.accounts) + 1}"
            
            success = self.signal_processor.add_account(account_id, account_name)
            
            if success:
                await message.answer(
                    f"✅ **Account added successfully!**\n\n"
                    f"Account: {account_name}\n"
                    f"ID: {account_id}",
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    "❌ **Failed to add account!**\n\n"
                    "Account might already exist.",
                    parse_mode="Markdown"
                )
            
            await state.clear()
        
        # Signal parsing handler
        @self.dp.message()
        async def handle_message(message: Message):
            # Check if it's a signal format
            text = message.text.strip()
            parts = text.split()
            
            if len(parts) >= 3 and parts[1].upper() in ['BUY', 'SELL']:
                try:
                    # Parse signal: SYMBOL DIRECTION EP SL TP
                    symbol = parts[0].upper()
                    trade_type = parts[1].upper()
                    entry_price = float(parts[2])
                    
                    stop_loss = float(parts[3]) if len(parts) > 3 else None
                    take_profit = float(parts[4]) if len(parts) > 4 else None
                    
                    if not self.signal_processor.channels:
                        await message.answer(
                            "❌ **No channels configured!**\n\n"
                            "Please run /setup first.",
                            parse_mode="Markdown"
                        )
                        return
                    
                    # Create signal
                    channel_id = list(self.signal_processor.channels.keys())[0]
                    channel = self.signal_processor.channels[channel_id]
                    
                    signal = TradingSignal(
                        symbol=symbol,
                        trade_type=trade_type,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        comment="Manual signal",
                        channel_id=channel_id,
                        account_id=channel.account_id
                    )
                    
                    # Send to channel
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=signal.to_telegram_message(),
                        parse_mode="Markdown"
                    )
                    
                    # Process signal
                    history = await self.signal_processor.process_signal(signal)
                    
                    if signal.status.value == "EXECUTED":
                        await message.answer(
                            f"✅ **Signal sent and executed!**\n\n"
                            f"⚡ Execution time: {history.execution_time_ms}ms",
                            parse_mode="Markdown"
                        )
                    else:
                        await message.answer(
                            f"❌ **Signal failed to execute:** {signal.error_message}",
                            parse_mode="Markdown"
                        )
                        
                except (ValueError, IndexError) as e:
                    await message.answer(
                        "❌ **Invalid signal format!**\n\n"
                        "Please use: `SYMBOL DIRECTION EP SL TP`\n"
                        "Example: `EURUSD BUY 1.0650 1.0600 1.0750`",
                        parse_mode="Markdown"
                    )
    
    async def start(self):
        """Start the bot"""
        logger.info("Starting Signals Bot...")
        
        # Validate configuration
        if not Config.validate_config():
            logger.error("Configuration validation failed!")
            return
        
        # Start polling
        # Start background tasks
        asyncio.create_task(self._monitor_active_signals())
        asyncio.create_task(self._daily_signal_scheduler())
        asyncio.create_task(self._daily_report_loop())
        asyncio.create_task(self._weekly_report_loop())
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping Signals Bot...")
        try:
            await self.binance.close()
        except Exception:
            pass
        await self.bot.session.close()

    # ===== Short-term signals implementation =====
    def _get_channel_history_file(self, channel_id: str) -> str:
        safe_id = str(channel_id).replace("/", "_")
        return os.path.join(self.history_dir, f"{safe_id}.json")

    def _load_history(self, channel_id: Optional[str] = None) -> list[dict]:
        """Load history for a specific channel; defaults to target channel."""
        cid = channel_id or self.target_channel_id
        path = self._get_channel_history_file(cid)
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_history(self, history: list[dict], channel_id: Optional[str] = None):
        """Save history for a specific channel; defaults to target channel."""
        cid = channel_id or self.target_channel_id
        path = self._get_channel_history_file(cid)
        try:
            with open(path, 'w') as f:
                json.dump(history, f, indent=2)
            # Also write to named history file if mapping exists
            if cid in self.named_history_map:
                named_path = os.path.join(self.history_dir, self.named_history_map[cid])
                with open(named_path, 'w') as nf:
                    json.dump(history, nf, indent=2)
        except Exception as e:
            logger.error(f"Failed saving history for {cid}: {e}")

    async def _fetch_market(self, symbols: list[str]) -> dict[str, dict]:
        data = await self.binance.fetch_tickers(symbols)
        if data:
            self.cached_market = data
        return data or self.cached_market

    def _build_signal_levels(self, sym_data: dict, direction: str) -> tuple[float, float, float, float]:
        entry = float(sym_data["price"])
        rng = max(0.0000001, float(sym_data["max_price"]) - float(sym_data["min_price"]))
        step = 0.15 * rng  # short-term steps (TP1 distance)
        sl_mult = 1.8      # ensure |SL-entry| > |TP1-entry|
        if direction == "BUY":
            tp1 = entry + step
            tp2 = entry + 2 * step
            tp3 = entry + 3 * step
            sl = entry - sl_mult * step
        else:
            tp1 = entry - step
            tp2 = entry - 2 * step
            tp3 = entry - 3 * step
            sl = entry + sl_mult * step
        return entry, sl, tp1, tp2, tp3

    async def _build_forex_signal_text(self, symbol: str) -> str:
        entry = None
        try:
            q = await self.ctrader.get_current_quotes(symbol)
            if q:
                bid = float(q.get("bid", 0))
                ask = float(q.get("ask", 0))
                entry = (bid + ask) / 2 if bid and ask else (bid or ask)
        except Exception:
            entry = None

        is_jpy = symbol.endswith("JPY")
        pip = 0.01 if is_jpy else 0.0001
        if entry is None or entry == 0:
            base = 150.00 if is_jpy else 1.1000
            entry = base

        direction = "BUY" if (int(datetime.now().timestamp()) % 2 == 0) else "SELL"
        tp_pips = 150
        sl_pips = 90
        if direction == "BUY":
            tp = entry + tp_pips * pip
            sl = entry - sl_pips * pip
        else:
            tp = entry - tp_pips * pip
            sl = entry + sl_pips * pip

        prec = 2 if is_jpy else 5
        entry_s = f"{entry:.{prec}f}"
        sl_s = f"{sl:.{prec}f}"
        tp_s = f"{tp:.{prec}f}"

        return f"{symbol} {direction} {entry_s}\nSL {sl_s}\nTP {tp_s}"

    async def _generate_and_send_signal(self, symbol: str):
        market = await self._fetch_market([symbol])
        d = market.get(symbol)
        if not d:
            return
        direction = "BUY" if d.get("change_24h", 0) >= 0 else "SELL"
        entry, sl, tp1, tp2, tp3 = self._build_signal_levels(d, direction)
        sig_id = str(uuid.uuid4())
        record = {
            "id": sig_id,
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ACTIVE",
            "hits": {"tp1": False, "tp2": False, "tp3": False, "sl": False},
            "closed_at": None,
            "result_label": None,
            "channel_id": self.target_channel_id
        }
        self.active_signals[sig_id] = record

        msg = (
            f"📈 {symbol}/USDT {direction}\n\n"
            f"• Entry: ${entry:,.2f}\n"
            f"• TP1: ${tp1:,.2f}\n"
            f"• TP2: ${tp2:,.2f}\n"
            f"• TP3: ${tp3:,.2f}\n"
            f"• SL: ${sl:,.2f}\n\n"
            f"Short-term signal"
        )
        try:
            await self.bot.send_message(chat_id=self.target_channel_id, text=msg)
        except Exception as e:
            logger.error(f"Failed to send signal: {e}")

        # Persist to history immediately
        history = self._load_history(self.target_channel_id)
        history.append(record)
        self._save_history(history, self.target_channel_id)

    async def _monitor_active_signals(self):
        while True:
            try:
                # Collect symbols of active signals
                symbols = list({rec["symbol"] for rec in self.active_signals.values() if rec["status"] == "ACTIVE"})
                if symbols:
                    market = await self._fetch_market(symbols)
                    now_iso = datetime.now(timezone.utc).isoformat()
                    for sig_id, rec in list(self.active_signals.items()):
                        if rec["status"] != "ACTIVE":
                            continue
                        price = market.get(rec["symbol"], {}).get("price")
                        if price is None:
                            continue
                        p = float(price)
                        # Track hits
                        if rec["direction"] == "BUY":
                            if p >= rec["tp1"]: rec["hits"]["tp1"] = True
                            if p >= rec["tp2"]: rec["hits"]["tp2"] = True
                            if p >= rec["tp3"]: rec["hits"]["tp3"] = True
                            if p <= rec["sl"]: rec["hits"]["sl"] = True
                        else:
                            if p <= rec["tp1"]: rec["hits"]["tp1"] = True
                            if p <= rec["tp2"]: rec["hits"]["tp2"] = True
                            if p <= rec["tp3"]: rec["hits"]["tp3"] = True
                            if p >= rec["sl"]: rec["hits"]["sl"] = True

                        # Close rules
                        if rec["hits"]["sl"]:
                            # Determine which SL label per your rule
                            if rec["hits"]["tp3"]:
                                result_label = "SL after TP3 (count as 3rd SL hit)"
                            elif rec["hits"]["tp2"]:
                                result_label = "SL after TP2 (count as 2nd SL hit)"
                            elif rec["hits"]["tp1"]:
                                result_label = "SL after TP1 (count as 1st SL hit)"
                            else:
                                result_label = "SL (count as 1st SL hit)"
                            rec["status"] = "CLOSED"
                            rec["closed_at"] = now_iso
                            rec["result_label"] = result_label
                            # Realized exit at SL
                            exit_price = rec["sl"]
                            if rec["direction"] == "BUY":
                                pnl = (exit_price - rec["entry"]) / rec["entry"] * 100.0
                            else:
                                pnl = (rec["entry"] - exit_price) / rec["entry"] * 100.0
                            rec["exit_price"] = exit_price
                            rec["pnl_percent"] = round(pnl, 2)
                        elif rec["hits"]["tp3"]:
                            rec["status"] = "CLOSED"
                            rec["closed_at"] = now_iso
                            rec["result_label"] = "TP3 hit"
                            # Realized exit at TP3
                            exit_price = rec["tp3"]
                            if rec["direction"] == "BUY":
                                pnl = (exit_price - rec["entry"]) / rec["entry"] * 100.0
                            else:
                                pnl = (rec["entry"] - exit_price) / rec["entry"] * 100.0
                            rec["exit_price"] = exit_price
                            rec["pnl_percent"] = round(pnl, 2)
                        # else remain active

                # Persist active set to history file (update records)
                if symbols:
                    # Persist per channel
                    # Group records by channel_id
                    by_channel: dict[str, list[dict]] = {}
                    for rec in self.active_signals.values():
                        cid = rec.get("channel_id", self.target_channel_id)
                        by_channel.setdefault(cid, []).append(rec)
                    for cid, recs in by_channel.items():
                        history = self._load_history(cid)
                        idx = {h["id"]: i for i, h in enumerate(history)}
                        for r in recs:
                            if r["id"] in idx:
                                history[idx[r["id"]]] = r
                            else:
                                history.append(r)
                        self._save_history(history, cid)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
            await asyncio.sleep(30)  # check every 30s

    async def _daily_signal_scheduler(self):
        while True:
            try:
                # Determine remaining signals to send today
                now_utc = datetime.now(timezone.utc)
                start_day = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
                end_day = start_day + timedelta(days=1)
                history = self._load_history()
                sent_today = [h for h in history if start_day.isoformat() <= h.get("created_at", "") < end_day.isoformat()]
                target_count = 4  # between 3-5; aim 4
                remaining = max(0, target_count - len(sent_today))
                for _ in range(remaining):
                    sym = self.popular_symbols[(now_utc.minute + now_utc.second) % len(self.popular_symbols)]
                    await self._generate_and_send_signal(sym)
                    await asyncio.sleep(1800)  # spread ~30 min between signals when catching up
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            # Wake hourly to reconsider
            await asyncio.sleep(3600)

    async def _send_daily_summary(self):
        try:
            now_utc = datetime.now(timezone.utc)
            since = now_utc - timedelta(days=1)
            history = self._load_history()
            recent = [h for h in history if h.get("closed_at") and h["closed_at"] >= since.isoformat()]
            wins = sum(1 for h in recent if (h.get("result_label") or "").startswith("TP"))
            losses = len(recent) - wins
            msg = (
                "📊 Signals Summary (last 24h)\n\n"
                f"Total closed: {len(recent)}\n"
                f"Wins: {wins}\n"
                f"Losses: {losses}\n"
            )
            await self.bot.send_message(chat_id=self.admin_user_id, text=msg)
        except Exception as e:
            logger.error(f"Daily summary error: {e}")

    async def _send_summary_for_days(self, days: int, chat_id: int):
        """Send summary for the last N days to a chat id."""
        try:
            now_utc = datetime.now(timezone.utc)
            since = now_utc - timedelta(days=days)
            history = self._load_history()
            recent = [h for h in history if h.get("closed_at") and h["closed_at"] >= since.isoformat()]
            wins = sum(1 for h in recent if (h.get("result_label") or "").startswith("TP"))
            losses = len(recent) - wins

            # Optional breakdown per symbol
            per_symbol: dict[str, dict] = {}
            for h in recent:
                sym = h.get("symbol", "?")
                per_symbol.setdefault(sym, {"wins": 0, "losses": 0})
                if (h.get("result_label") or "").startsWith("TP") if hasattr(str, 'startsWith') else (h.get("result_label") or "").startswith("TP"):
                    per_symbol[sym]["wins"] += 1
                else:
                    per_symbol[sym]["losses"] += 1

            lines = [
                f"📊 Signals Summary (last {days} days)",
                "",
                f"Total closed: {len(recent)}",
                f"Wins: {wins}",
                f"Losses: {losses}",
            ]
            if per_symbol:
                lines.append("")
                lines.append("By symbol:")
                for sym, stats in sorted(per_symbol.items()):
                    lines.append(f"• {sym}: {stats['wins']}W/{stats['losses']}L")

            await self.bot.send_message(chat_id=chat_id, text="\n".join(lines))
        except Exception as e:
            logger.error(f"N-day summary error: {e}")

    async def _daily_report_loop(self):
        while True:
            now = datetime.now(timezone.utc)
            # Next 14:30 GMT
            target = datetime(now.year, now.month, now.day, 14, 30, tzinfo=timezone.utc)
            if now >= target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await self._send_daily_summary()

    async def _weekly_report_loop(self):
        while True:
            now = datetime.now(timezone.utc)
            # Friday = 4
            days_ahead = (4 - now.weekday()) % 7
            target = datetime(now.year, now.month, now.day, 14, 30, tzinfo=timezone.utc) + timedelta(days=days_ahead)
            if now >= target:
                target += timedelta(days=7)
            await asyncio.sleep((target - now).total_seconds())
            # Weekly summary for last 7 days
            try:
                since = datetime.now(timezone.utc) - timedelta(days=7)
                history = self._load_history()
                recent = [h for h in history if h.get("closed_at") and h["closed_at"] >= since.isoformat()]
                wins = sum(1 for h in recent if (h.get("result_label") or "").startswith("TP"))
                losses = len(recent) - wins
                msg = (
                    "📈 Weekly Signals Summary (7d)\n\n"
                    f"Total closed: {len(recent)}\n"
                    f"Wins: {wins}\n"
                    f"Losses: {losses}\n"
                )
                await self.bot.send_message(chat_id=self.admin_user_id, text=msg)
            except Exception as e:
                logger.error(f"Weekly summary error: {e}")


async def main():
    """Main function to run the bot"""
    bot = SignalsBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

