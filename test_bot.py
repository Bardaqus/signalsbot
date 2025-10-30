"""
Test script for Signals_bot functionality
"""
import asyncio
import os
from loguru import logger
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType


async def test_signal_processing():
    """Test signal processing functionality"""
    logger.info("🧪 Testing signal processing...")
    
    processor = SignalProcessor()
    
    # Add test account and channel
    processor.add_account("test_account", "Test Demo Account")
    processor.add_channel("@test_channel", "Test Channel", "test_account")
    
    # Create test signal
    test_signal = processor.create_test_signal(
        symbol="EURUSD",
        trade_type="BUY",
        entry_price=1.0650,
        stop_loss=1.0600,
        take_profit=1.0750
    )
    
    logger.info(f"Created test signal: {test_signal.symbol} {test_signal.trade_type}")
    
    # Test signal formatting
    telegram_message = test_signal.to_telegram_message()
    logger.info(f"Telegram message:\n{telegram_message}")
    
    # Test trade parameters
    trade_params = test_signal.to_trade_params()
    logger.info(f"Trade parameters: {trade_params}")
    
    # Get statistics
    stats = processor.get_statistics()
    logger.info(f"Processor statistics: {stats}")
    
    logger.info("✅ Signal processing test completed")


async def test_ctrader_api():
    """Test cTrader API functionality (without actual API calls)"""
    logger.info("🧪 Testing cTrader API integration...")
    
    from ctrader_api import CTraderAPI
    
    api = CTraderAPI()
    
    # Test auth URL generation
    auth_url = await api.get_auth_url()
    logger.info(f"Auth URL: {auth_url}")
    
    # Test configuration
    logger.info(f"Client ID: {api.client_id}")
    logger.info(f"API URL: {api.api_url}")
    
    logger.info("✅ cTrader API test completed")


async def test_telegram_bot():
    """Test Telegram bot initialization (without starting)"""
    logger.info("🧪 Testing Telegram bot initialization...")
    
    try:
        from telegram_bot import SignalsBot
        bot = SignalsBot()
        logger.info("✅ Telegram bot initialized successfully")
        
        # Test signal processor
        stats = bot.signal_processor.get_statistics()
        logger.info(f"Bot statistics: {stats}")
        
    except Exception as e:
        logger.error(f"❌ Telegram bot test failed: {e}")
    
    logger.info("✅ Telegram bot test completed")


async def run_all_tests():
    """Run all tests"""
    logger.info("🚀 Starting all tests...")
    
    try:
        await test_signal_processing()
        await test_ctrader_api()
        await test_telegram_bot()
        
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")


if __name__ == "__main__":
    # Setup basic logging
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"
    )
    
    asyncio.run(run_all_tests())

