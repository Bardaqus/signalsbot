"""
Configuration settings for Signals_bot
"""
import os
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()
# Try to load live config if available
load_dotenv('config_live.env')

class Config:
    """Configuration class for the Signals bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # cTrader API Configuration
    CTRADER_CLIENT_ID: str = os.getenv('CTRADER_CLIENT_ID', '')
    CTRADER_CLIENT_SECRET: str = os.getenv('CTRADER_CLIENT_SECRET', '')
    CTRADER_REDIRECT_URI: str = os.getenv('CTRADER_REDIRECT_URI', 'http://localhost:8080/callback')
    CTRADER_ACCESS_TOKEN: str = os.getenv('CTRADER_ACCESS_TOKEN', '')
    CTRADER_REFRESH_TOKEN: str = os.getenv('CTRADER_REFRESH_TOKEN', '')
    CTRADER_API_URL: str = 'https://openapi.ctrader.com'
    CTRADER_AUTH_URL: str = 'https://connect.spotware.com/apps'
    
    # Demo Account Configuration
    DEMO_ACCOUNT_ID: str = os.getenv('DEMO_ACCOUNT_ID', '')
    
    # Channel Configuration
    TEST_CHANNEL_ID: str = os.getenv('TEST_CHANNEL_ID', '')
    
    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Auto Signal Configuration
    AUTO_SIGNAL_INTERVAL: int = int(os.getenv('AUTO_SIGNAL_INTERVAL', '240'))  # 4 minutes
    SL_PIPS: int = int(os.getenv('SL_PIPS', '30'))
    TP_PIPS: int = int(os.getenv('TP_PIPS', '50'))
    
    @classmethod
    def validate_config(cls) -> bool:
        """Validate that required configuration is present"""
        required_fields = [
            cls.TELEGRAM_BOT_TOKEN,
            cls.CTRADER_CLIENT_ID,
            cls.CTRADER_CLIENT_SECRET,
            cls.DEMO_ACCOUNT_ID,
            cls.TEST_CHANNEL_ID
        ]
        
        missing_fields = [field for field in required_fields if not field]
        
        if missing_fields:
            print(f"Missing required configuration: {missing_fields}")
            return False
        
        return True
