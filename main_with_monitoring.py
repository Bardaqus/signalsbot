"""
Main entry point for Signals_bot with channel monitoring
"""
import asyncio
import sys
from loguru import logger
from config import Config
from telegram_bot import SignalsBot
from channel_monitor import ChannelMonitor


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
    """Main function with both management bot and channel monitoring"""
    setup_logging()
    
    logger.info("🚀 Starting Signals Bot with Channel Monitoring...")
    
    # Validate configuration
    if not Config.validate_config():
        logger.error("❌ Configuration validation failed!")
        logger.error("Please check your .env file and ensure all required fields are set.")
        return
    
    logger.info("✅ Configuration validated successfully")
    
    # Create bot instances
    management_bot = SignalsBot()
    channel_monitor = ChannelMonitor()
    
    try:
        logger.info("🤖 Starting management bot...")
        # Start management bot in background
        management_task = asyncio.create_task(management_bot.start())
        
        logger.info("🔍 Starting channel monitoring...")
        # Start channel monitoring in background
        monitor_task = asyncio.create_task(channel_monitor.start_monitoring())
        
        logger.info("✅ Both systems are running!")
        logger.info("📡 Monitoring channels for trading signals...")
        logger.info("🤖 Management bot ready for commands...")
        logger.info("Press Ctrl+C to stop all services.")
        
        # Wait for both tasks
        await asyncio.gather(management_task, monitor_task)
        
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        await management_bot.stop()
        await channel_monitor.stop()
        logger.info("👋 All services shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())



