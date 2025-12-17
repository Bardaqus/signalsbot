#!/usr/bin/env python3
"""
Complete Bot - Automatic + Interactive
Runs both automatic signal generation and interactive button controls
"""

import asyncio
import os
from datetime import datetime, timezone
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bot import post_signals_once, DEFAULT_PAIRS, get_today_signals_count, MAX_SIGNALS_PER_DAY
from crypto_bot import post_crypto_signals_once, CRYPTO_PAIRS, get_today_crypto_signals_count, MAX_SIGNALS_PER_DAY as CRYPTO_MAX_SIGNALS

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7734435177:AAGeoSk7TChGNvaVf63R9DW8TELWRQB_rmY")
FOREX_CHANNEL_ID = "-1003118256304"
CRYPTO_CHANNEL_ID = "-1002978318746"
REPORT_USER_ID = 615348532

# Allowed user IDs
ALLOWED_USERS = [615348532]


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
            InlineKeyboardButton("📊 Forex Report", callback_data="forex_report"),
            InlineKeyboardButton("🪙 Crypto Report", callback_data="crypto_report")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Complete Trading Signals Bot**

**Automatic Features:**
• Runs every 5 minutes automatically
• Generates 5 forex signals daily
• Generates 5 crypto signals daily (73% BUY / 27% SELL)
• Sends performance reports

**Manual Controls:**
• Generate signals on demand
• Check real-time status
• View performance reports

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
    elif query.data == "forex_report":
        await handle_forex_report(query, context)
    elif query.data == "crypto_report":
        await handle_crypto_report(query, context)
    elif query.data == "refresh":
        await handle_refresh(query, context)


async def handle_forex_signal(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex signal generation"""
    await query.edit_message_text("🔄 Generating forex signal...")
    
    try:
        today_count = get_today_signals_count()
        
        if today_count >= MAX_SIGNALS_PER_DAY:
            await query.edit_message_text(
                f"⚠️ **Forex Signal Limit Reached**\n\n"
                f"Today's forex signals: {today_count}/{MAX_SIGNALS_PER_DAY}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        await post_signals_once(DEFAULT_PAIRS)
        new_count = get_today_signals_count()
        
        await query.edit_message_text(
            f"✅ **Forex Signal Generated**\n\n"
            f"📊 Today's forex signals: {new_count}/{MAX_SIGNALS_PER_DAY}\n"
            f"📤 Signal sent to forex channel",
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
    await query.edit_message_text("🔄 Generating crypto signal...")
    
    try:
        today_count = get_today_crypto_signals_count()
        
        if today_count >= CRYPTO_MAX_SIGNALS:
            await query.edit_message_text(
                f"⚠️ **Crypto Signal Limit Reached**\n\n"
                f"Today's crypto signals: {today_count}/{CRYPTO_MAX_SIGNALS}\n"
                f"Maximum signals per day reached.",
                parse_mode='Markdown'
            )
            return
        
        await post_crypto_signals_once(CRYPTO_PAIRS)
        new_count = get_today_crypto_signals_count()
        
        from crypto_bot import get_today_crypto_signal_distribution
        distribution = get_today_crypto_signal_distribution()
        total_signals = distribution["BUY"] + distribution["SELL"]
        buy_ratio = (distribution["BUY"] / total_signals * 100) if total_signals > 0 else 0
        sell_ratio = (distribution["SELL"] / total_signals * 100) if total_signals > 0 else 0
        
        await query.edit_message_text(
            f"✅ **Crypto Signal Generated**\n\n"
            f"📊 Today's crypto signals: {new_count}/{CRYPTO_MAX_SIGNALS}\n"
            f"📈 Distribution: BUY {distribution['BUY']} ({buy_ratio:.1f}%), SELL {distribution['SELL']} ({sell_ratio:.1f}%)\n"
            f"📤 Signal sent to crypto channel",
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
        today_count = get_today_signals_count()
        
        status_text = f"""
📈 **Forex Signals Status**

📊 Today's signals: {today_count}/{MAX_SIGNALS_PER_DAY}
📤 Channel: {FOREX_CHANNEL_ID}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if today_count < MAX_SIGNALS_PER_DAY else '⚠️ Daily limit reached'}
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
        today_count = get_today_crypto_signals_count()
        from crypto_bot import get_today_crypto_signal_distribution
        distribution = get_today_crypto_signal_distribution()
        total_signals = distribution["BUY"] + distribution["SELL"]
        buy_ratio = (distribution["BUY"] / total_signals * 100) if total_signals > 0 else 0
        sell_ratio = (distribution["SELL"] / total_signals * 100) if total_signals > 0 else 0
        
        status_text = f"""
🪙 **Crypto Signals Status**

📊 Today's signals: {today_count}/{CRYPTO_MAX_SIGNALS}
📈 Distribution: BUY {distribution['BUY']} ({buy_ratio:.1f}%), SELL {distribution['SELL']} ({sell_ratio:.1f}%)
📤 Channel: {CRYPTO_CHANNEL_ID}
⏰ Last updated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC

{'✅ Ready to generate more signals' if today_count < CRYPTO_MAX_SIGNALS else '⚠️ Daily limit reached'}
🎯 Target: 73% BUY / 27% SELL
        """
        
        await query.edit_message_text(status_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting crypto status**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_forex_report(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forex performance report"""
    try:
        from bot import get_performance_report
        report = get_performance_report(days=1)
        
        report_text = f"""
📊 **Forex Performance Report (24h)**

{report}

⏰ Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
        """
        
        await query.edit_message_text(report_text, parse_mode='Markdown')
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Error getting forex report**\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )


async def handle_crypto_report(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle crypto performance report"""
    try:
        from crypto_bot import get_crypto_performance_report
        report = get_crypto_performance_report(days=1)
        
        report_text = f"""
🪙 **Crypto Performance Report (24h)**

{report}

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
            InlineKeyboardButton("📊 Forex Report", callback_data="forex_report"),
            InlineKeyboardButton("🪙 Crypto Report", callback_data="crypto_report")
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
🤖 **Complete Trading Signals Bot**

**Automatic Features:**
• Runs every 5 minutes automatically
• Generates 5 forex signals daily
• Generates 5 crypto signals daily (73% BUY / 27% SELL)
• Sends performance reports

**Manual Controls:**
• Generate signals on demand
• Check real-time status
• View performance reports

*Click any button to proceed*
    """
    
    await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def automatic_signal_generation():
    """Run automatic signal generation every 5 minutes"""
    print("🤖 Starting automatic signal generation...")
    
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            print(f"\n⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC - Auto generation")
            
            # Check forex signals
            forex_count = get_today_signals_count()
            if forex_count < MAX_SIGNALS_PER_DAY:
                print(f"🎯 Auto-generating forex signal ({forex_count + 1}/{MAX_SIGNALS_PER_DAY})")
                await post_signals_once(DEFAULT_PAIRS)
            
            # Check crypto signals
            crypto_count = get_today_crypto_signals_count()
            if crypto_count < CRYPTO_MAX_SIGNALS:
                print(f"🎯 Auto-generating crypto signal ({crypto_count + 1}/{CRYPTO_MAX_SIGNALS})")
                await post_crypto_signals_once(CRYPTO_PAIRS)
            
            # Wait 5 minutes
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ Error in automatic generation: {e}")
            await asyncio.sleep(300)


async def main() -> None:
    """Start the complete bot with both automatic and interactive features"""
    print("🚀 Starting Complete Trading Signals Bot...")
    print("📱 Interactive features: /start command with buttons")
    print("🤖 Automatic features: Signal generation every 5 minutes")
    print("🔐 Authorized users:", ALLOWED_USERS)
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start automatic signal generation in background
    asyncio.create_task(automatic_signal_generation())
    
    print("✅ Complete bot started successfully!")
    print("📱 Send /start to your bot to see the control panel")
    print("🤖 Automatic signal generation is running in background")
    
    # Start the bot
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
