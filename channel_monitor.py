"""
Channel Monitor - Monitors Telegram channels for trading signals
"""
import asyncio
import re
import json
from datetime import datetime
from typing import Optional, Dict, List
from loguru import logger
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from config import Config
from signal_processor import SignalProcessor
from models import TradingSignal, TradeType, SignalStatus


class ChannelMonitor:
    """Monitors configured channels for trading signals"""
    
    def __init__(self):
        self.bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        self.signal_processor = SignalProcessor()
        self.monitored_channels = self._load_monitored_channels()
        self.signal_patterns = self._load_signal_patterns()
        
    def _load_monitored_channels(self) -> List[str]:
        """Load channels to monitor from configuration"""
        try:
            with open('data/channels.json', 'r') as f:
                channels = json.load(f)
            return [channel['channel_id'] for channel in channels if channel.get('is_active', True)]
        except Exception as e:
            logger.error(f"Failed to load channels: {e}")
            return []
    
    def _load_signal_patterns(self) -> Dict[str, str]:
        """Load regex patterns for detecting trading signals"""
        return {
            'buy_pattern': r'(?i)(buy|long).*?([A-Z]{3,6})/?([A-Z]{3,6})?.*?(\d+\.?\d*).*?(stop|sl|stoploss).*?(\d+\.?\d*).*?(target|tp|takeprofit).*?(\d+\.?\d*)',
            'sell_pattern': r'(?i)(sell|short).*?([A-Z]{3,6})/?([A-Z]{3,6})?.*?(\d+\.?\d*).*?(stop|sl|stoploss).*?(\d+\.?\d*).*?(target|tp|takeprofit).*?(\d+\.?\d*)',
            'symbol_pattern': r'([A-Z]{3,6})/?([A-Z]{3,6})?',
            'price_pattern': r'(\d+\.?\d*)',
        }
    
    async def start_monitoring(self):
        """Start monitoring all configured channels"""
        logger.info(f"🔍 Starting channel monitoring for {len(self.monitored_channels)} channels")
        
        for channel_id in self.monitored_channels:
            logger.info(f"📡 Monitoring channel: {channel_id}")
            asyncio.create_task(self._monitor_channel(channel_id))
    
    async def _monitor_channel(self, channel_id: str):
        """Monitor a specific channel for signals"""
        last_message_id = 0
        
        while True:
            try:
                # Get updates from the channel
                updates = await self.bot.get_updates(offset=last_message_id + 1, timeout=30)
                
                for update in updates:
                    if update.message and update.message.chat.id == int(channel_id):
                        last_message_id = update.update_id
                        await self._process_message(update.message, channel_id)
                
                await asyncio.sleep(1)  # Small delay to avoid rate limiting
                
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    logger.error(f"❌ Channel {channel_id} not found or bot not added to channel")
                    break
                else:
                    logger.error(f"❌ Telegram error monitoring channel {channel_id}: {e}")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ Error monitoring channel {channel_id}: {e}")
                await asyncio.sleep(5)
    
    async def _process_message(self, message: Message, channel_id: str):
        """Process a message from a monitored channel"""
        if not message.text:
            return
        
        logger.info(f"📨 New message from channel {channel_id}: {message.text[:100]}...")
        
        # Check if message contains trading signal
        signal = self._extract_signal(message.text, channel_id)
        
        if signal:
            logger.info(f"🎯 Signal detected: {signal.symbol} {signal.trade_type.value}")
            await self._process_signal(signal)
        else:
            logger.debug(f"📝 No signal pattern found in message")
    
    def _extract_signal(self, text: str, channel_id: str) -> Optional[TradingSignal]:
        """Extract trading signal from message text"""
        try:
            # Clean the text
            text = text.replace('\n', ' ').replace('\r', ' ')
            
            # Try to extract buy signal
            buy_match = re.search(self.signal_patterns['buy_pattern'], text)
            if buy_match:
                symbol = buy_match.group(2)
                if buy_match.group(3):
                    symbol += f"/{buy_match.group(3)}"
                entry_price = float(buy_match.group(4))
                stop_loss = float(buy_match.group(6))
                take_profit = float(buy_match.group(8))
                
                return TradingSignal(
                    channel_id=channel_id,
                    symbol=symbol,
                    trade_type=TradeType.BUY,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    message_text=text,
                    timestamp=datetime.now()
                )
            
            # Try to extract sell signal
            sell_match = re.search(self.signal_patterns['sell_pattern'], text)
            if sell_match:
                symbol = sell_match.group(2)
                if sell_match.group(3):
                    symbol += f"/{sell_match.group(3)}"
                entry_price = float(sell_match.group(4))
                stop_loss = float(sell_match.group(6))
                take_profit = float(sell_match.group(8))
                
                return TradingSignal(
                    channel_id=channel_id,
                    symbol=symbol,
                    trade_type=TradeType.SELL,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    message_text=text,
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error extracting signal from text: {e}")
            return None
    
    async def _process_signal(self, signal: TradingSignal):
        """Process a detected trading signal"""
        try:
            logger.info(f"🔄 Processing signal: {signal.symbol} {signal.trade_type.value} @ {signal.entry_price}")
            
            # Process signal through signal processor
            result = await self.signal_processor.process_signal(signal)
            
            if result.status == SignalStatus.SUCCESS:
                logger.info(f"✅ Signal processed successfully: {result.trade_id}")
            else:
                logger.error(f"❌ Signal processing failed: {result.error_message}")
                
        except Exception as e:
            logger.error(f"❌ Error processing signal: {e}")
    
    async def stop(self):
        """Stop the channel monitor"""
        await self.bot.session.close()
        logger.info("🛑 Channel monitor stopped")


async def main():
    """Main function for channel monitoring"""
    monitor = ChannelMonitor()
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("⏹️ Channel monitoring stopped by user")
    except Exception as e:
        logger.error(f"❌ Channel monitoring error: {e}")
    finally:
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
