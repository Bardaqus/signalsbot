"""
Data models for trading signals and channel management
"""
from typing import Optional, Dict, List
from enum import Enum
from datetime import datetime


class TradeType(str, Enum):
    """Trade type enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class SignalStatus(str, Enum):
    """Signal status enumeration"""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TradingSignal:
    """Trading signal model"""
    
    def __init__(self, symbol: str, trade_type: str, entry_price: float, 
                 stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                 volume: float = 1.0, comment: str = "", channel_id: str = "",
                 account_id: str = "", status: SignalStatus = SignalStatus.PENDING,
                 created_at: Optional[datetime] = None, executed_at: Optional[datetime] = None,
                 trade_id: Optional[str] = None, error_message: Optional[str] = None,
                 message_text: str = "", timestamp: Optional[datetime] = None):
        self.symbol = symbol
        self.trade_type = TradeType(trade_type) if isinstance(trade_type, str) else trade_type
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.volume = volume
        self.comment = comment
        self.channel_id = channel_id
        self.account_id = account_id
        self.status = status
        self.created_at = created_at or datetime.now()
        self.executed_at = executed_at
        self.trade_id = trade_id
        self.error_message = error_message
        self.message_text = message_text
        self.timestamp = timestamp or datetime.now()
    
    def to_telegram_message(self) -> str:
        """Format signal as Telegram message"""
        signal_emoji = "🟢" if self.trade_type == TradeType.BUY else "🔴"
        direction = "BUY" if self.trade_type == TradeType.BUY else "SELL"
        
        message = f"""
{signal_emoji} **TRADING SIGNAL**

**Symbol:** {self.symbol}
**Direction:** {direction}
**Entry Price:** {self.entry_price}

"""
        
        if self.stop_loss:
            message += f"**Stop Loss:** {self.stop_loss}\n"
        if self.take_profit:
            message += f"**Take Profit:** {self.take_profit}\n"
            
        message += f"\n**Volume:** {self.volume}"
        
        if self.comment:
            message += f"\n**Comment:** {self.comment}"
            
        message += f"\n\n📊 *Generated at {self.created_at.strftime('%H:%M:%S')}*"
        
        return message.strip()
    
    def to_trade_params(self) -> Dict:
        """Convert signal to trade parameters for cTrader API"""
        return {
            'symbol_name': self.symbol,
            'trade_type': self.trade_type.value,
            'volume': self.volume,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'comment': f"Signal: {self.comment}" if self.comment else "Auto-generated signal"
        }


class ChannelConfig:
    """Channel configuration model"""
    
    def __init__(self, channel_id: str, channel_name: str, account_id: str, 
                 is_active: bool = True, created_at: Optional[datetime] = None):
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.account_id = account_id
        self.is_active = is_active
        self.created_at = created_at or datetime.now()
    
    def dict(self):
        return {
            'channel_id': self.channel_id,
            'channel_name': self.channel_name,
            'account_id': self.account_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat()
        }


class TradingAccount:
    """Trading account model"""
    
    def __init__(self, account_id: str, account_name: str, broker: str = "IC Markets",
                 account_type: str = "DEMO", balance: Optional[float] = None,
                 currency: str = "USD", is_active: bool = True,
                 access_token: Optional[str] = None, created_at: Optional[datetime] = None):
        self.account_id = account_id
        self.account_name = account_name
        self.broker = broker
        self.account_type = account_type
        self.balance = balance
        self.currency = currency
        self.is_active = is_active
        self.access_token = access_token
        self.created_at = created_at or datetime.now()
    
    def dict(self):
        return {
            'account_id': self.account_id,
            'account_name': self.account_name,
            'broker': self.broker,
            'account_type': self.account_type,
            'balance': self.balance,
            'currency': self.currency,
            'is_active': self.is_active,
            'access_token': self.access_token,
            'created_at': self.created_at.isoformat()
        }


class SignalHistory:
    """Signal execution history"""
    
    def __init__(self, signal_id: str, signal: TradingSignal,
                 execution_result: Optional[Dict] = None,
                 telegram_message_id: Optional[int] = None,
                 execution_time_ms: Optional[int] = None,
                 status: SignalStatus = SignalStatus.PENDING,
                 created_at: Optional[datetime] = None):
        self.signal_id = signal_id
        self.signal = signal
        self.execution_result = execution_result
        self.telegram_message_id = telegram_message_id
        self.execution_time_ms = execution_time_ms
        self.status = status
        self.created_at = created_at or datetime.now()
