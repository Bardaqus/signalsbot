"""
Main entry point for Signals_bot
"""
import asyncio
import sys
from loguru import logger
from config import Config
from telegram_bot import SignalsBot


def setup_logging():
    """Setup logging configuration"""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=Config.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        "logs/signals_bot.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 day",
        retention="30 days"
    )


async def main():
    """Main function"""
    setup_logging()
    
    logger.info("🚀 Starting Signals Bot...")
    
    # Validate configuration
    if not Config.validate_config():
        logger.error("❌ Configuration validation failed!")
        logger.error("Please check your .env file and ensure all required fields are set.")
        return
    
    logger.info("✅ Configuration validated successfully")
    
    # Create and start bot
    bot = SignalsBot()
    
    try:
        logger.info("🤖 Bot is running. Press Ctrl+C to stop.")
        await bot.start()
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        await bot.stop()
        logger.info("👋 Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

