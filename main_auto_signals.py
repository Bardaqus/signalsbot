"""
Main entry point for Auto Signals Bot
"""
import asyncio
import sys
from loguru import logger
from config import Config
from auto_signal_generator import AutoSignalGenerator
from ctrader_stream import CTraderStreamer


def setup_logging():
    """Setup logging configuration"""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=Config.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        "logs/auto_signals_bot.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 day",
        retention="30 days"
    )


async def main():
    """Main function"""
    setup_logging()
    
    logger.info("🚀 Starting Auto Signals Bot...")
    
    # Validate configuration
    if not Config.validate_config():
        logger.error("❌ Configuration validation failed!")
        logger.error("Please check your config_live.env file and ensure all required fields are set.")
        return
    
    logger.info("✅ Configuration validated successfully")
    logger.info(f"📊 Signal interval: {Config.AUTO_SIGNAL_INTERVAL} seconds ({Config.AUTO_SIGNAL_INTERVAL//60} minutes)")
    logger.info(f"🎯 SL: {Config.SL_PIPS} pips, TP: {Config.TP_PIPS} pips")
    logger.info(f"📱 Channel: {Config.TEST_CHANNEL_ID}")
    logger.info(f"🏦 Account: {Config.DEMO_ACCOUNT_ID}")
    
    # Create and start auto signal generator
    generator = AutoSignalGenerator()
    streamer_task = None
    
    # Start live price streamer if tokens are available
    if Config.CTRADER_ACCESS_TOKEN and Config.CTRADER_CLIENT_ID and Config.CTRADER_CLIENT_SECRET and Config.DEMO_ACCOUNT_ID:
        try:
            streamer = CTraderStreamer(
                access_token=Config.CTRADER_ACCESS_TOKEN,
                client_id=Config.CTRADER_CLIENT_ID,
                client_secret=Config.CTRADER_CLIENT_SECRET,
                account_id=int(Config.DEMO_ACCOUNT_ID),
            )
            streamer.set_on_quote(generator.update_live_quote)
            
            async def start_stream_and_subscribe():
                await streamer.start()
                # Allow time to resolve symbols (wait longer for symbols list)
                logger.info("⏳ Waiting for symbols list to be received...")
                await asyncio.sleep(5)  # Increased wait time for symbols resolution
                
                # Subscribe to Forex pairs
                logger.info(f"📊 Subscribing to {len(generator.major_pairs)} Forex pairs...")
                forex_success = 0
                forex_failed = 0
                for sym in generator.major_pairs:
                    try:
                        success = await streamer.subscribe(sym)
                        if success:
                            forex_success += 1
                        else:
                            forex_failed += 1
                        await asyncio.sleep(0.2)  # Small delay between subscriptions
                    except Exception as e:
                        logger.error(f"❌ Subscribe failed for {sym}: {e}")
                        forex_failed += 1
                
                logger.info(f"✅ Forex subscriptions: {forex_success} succeeded, {forex_failed} failed")
                
                # Subscribe to Indices
                logger.info(f"📈 Subscribing to {len(generator.index_symbols)} Indices...")
                index_success = 0
                index_failed = 0
                for sym in generator.index_symbols:
                    try:
                        success = await streamer.subscribe(sym)
                        if success:
                            index_success += 1
                            logger.info(f"   ✅ Successfully subscribed to {sym}")
                        else:
                            index_failed += 1
                            logger.warning(f"   ⚠️ Failed to subscribe to {sym} (check symbol name)")
                        await asyncio.sleep(0.2)  # Small delay between subscriptions
                    except Exception as e:
                        logger.error(f"❌ Subscribe failed for {sym}: {e}")
                        index_failed += 1
                
                logger.info(f"✅ Index subscriptions: {index_success} succeeded, {index_failed} failed")
                
                if index_failed > 0:
                    logger.warning(f"⚠️ {index_failed} indices failed to subscribe. Check:")
                    logger.warning(f"   1. Symbol names match your broker's exact tickers")
                    logger.warning(f"   2. Your account has permission to trade indices")
                    logger.warning(f"   3. Symbols are available in your account")
            
            streamer_task = asyncio.create_task(start_stream_and_subscribe())
            logger.info("📡 Live price streamer started; using actual prices when available")
        except Exception as e:
            logger.warning(f"Live streamer init failed, falling back to API/demo quotes: {e}")
    else:
        logger.warning("No cTrader access token/client creds; will use API/demo quotes for prices")
    
    try:
        logger.info("🤖 Auto signal generator is running. Press Ctrl+C to stop.")
        
        # Send startup message
        await generator.send_startup_message()
        
        # Start auto signals
        await generator.start_auto_signals()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        generator.stop_auto_signals()
        if streamer_task:
            try:
                streamer_task.cancel()
            except Exception:
                pass
        logger.info("👋 Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

