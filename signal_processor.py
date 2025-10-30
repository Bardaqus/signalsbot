"""
Signal processing and channel management
"""
import asyncio
import json
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
from models import TradingSignal, ChannelConfig, TradingAccount, SignalHistory, SignalStatus
from ctrader_api import CTraderAPI


class SignalProcessor:
    """Processes trading signals and manages channel-to-account mapping"""
    
    def __init__(self):
        self.ctrader_api = CTraderAPI()
        self.channels: Dict[str, ChannelConfig] = {}
        self.accounts: Dict[str, TradingAccount] = {}
        self.signal_history: List[SignalHistory] = []
        # Execution toggle: when False, we only send signals (no trade placement)
        self.execute_trades: bool = False
        self._load_configurations()
    
    def _load_configurations(self):
        """Load channel and account configurations"""
        # For now, load from config file - later this can be from database
        try:
            with open('data/channels.json', 'r') as f:
                channels_data = json.load(f)
                for channel_data in channels_data:
                    channel = ChannelConfig(
                        channel_id=channel_data['channel_id'],
                        channel_name=channel_data['channel_name'],
                        account_id=channel_data['account_id'],
                        is_active=channel_data.get('is_active', True),
                        created_at=datetime.fromisoformat(channel_data.get('created_at', datetime.now().isoformat()))
                    )
                    self.channels[channel.channel_id] = channel
                    
            with open('data/accounts.json', 'r') as f:
                accounts_data = json.load(f)
                for account_data in accounts_data:
                    account = TradingAccount(
                        account_id=account_data['account_id'],
                        account_name=account_data['account_name'],
                        broker=account_data.get('broker', 'IC Markets'),
                        account_type=account_data.get('account_type', 'DEMO'),
                        balance=account_data.get('balance'),
                        currency=account_data.get('currency', 'USD'),
                        is_active=account_data.get('is_active', True),
                        access_token=account_data.get('access_token'),
                        created_at=datetime.fromisoformat(account_data.get('created_at', datetime.now().isoformat()))
                    )
                    self.accounts[account.account_id] = account
                    
            logger.info(f"Loaded {len(self.channels)} channels and {len(self.accounts)} accounts")
            
        except FileNotFoundError:
            logger.info("No existing configuration files found, starting with empty configuration")
    
    def _save_configurations(self):
        """Save channel and account configurations"""
        try:
            # Save channels
            channels_data = [channel.dict() for channel in self.channels.values()]
            with open('data/channels.json', 'w') as f:
                json.dump(channels_data, f, indent=2, default=str)
            
            # Save accounts
            accounts_data = [account.dict() for account in self.accounts.values()]
            with open('data/accounts.json', 'w') as f:
                json.dump(accounts_data, f, indent=2, default=str)
                
            logger.info("Configuration saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save configurations: {e}")
    
    def add_channel(self, channel_id: str, channel_name: str, account_id: str) -> bool:
        """Add a new channel configuration"""
        if channel_id in self.channels:
            logger.warning(f"Channel {channel_id} already exists")
            return False
            
        if account_id not in self.accounts:
            logger.error(f"Account {account_id} not found")
            return False
            
        channel = ChannelConfig(
            channel_id=channel_id,
            channel_name=channel_name,
            account_id=account_id
        )
        
        self.channels[channel_id] = channel
        self._save_configurations()
        logger.info(f"Added channel {channel_name} ({channel_id}) linked to account {account_id}")
        return True
    
    def add_account(self, account_id: str, account_name: str, 
                   broker: str = "IC Markets", account_type: str = "DEMO") -> bool:
        """Add a new trading account"""
        if account_id in self.accounts:
            logger.warning(f"Account {account_id} already exists")
            return False
            
        account = TradingAccount(
            account_id=account_id,
            account_name=account_name,
            broker=broker,
            account_type=account_type
        )
        
        self.accounts[account_id] = account
        self._save_configurations()
        logger.info(f"Added account {account_name} ({account_id})")
        return True
    
    def get_account_for_channel(self, channel_id: str) -> Optional[TradingAccount]:
        """Get the trading account associated with a channel"""
        if channel_id not in self.channels:
            logger.error(f"Channel {channel_id} not found")
            return None
            
        channel = self.channels[channel_id]
        account_id = channel.account_id
        
        if account_id not in self.accounts:
            logger.error(f"Account {account_id} not found for channel {channel_id}")
            return None
            
        return self.accounts[account_id]
    
    async def process_signal(self, signal: TradingSignal) -> SignalHistory:
        """Process a trading signal"""
        signal_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        logger.info(f"Processing signal {signal_id}: {signal.symbol} {signal.trade_type}")
        
        # Create signal history record
        history = SignalHistory(
            signal_id=signal_id,
            signal=signal
        )
        
        try:
            # Get account for the channel
            account = self.get_account_for_channel(signal.channel_id)
            if not account:
                signal.status = SignalStatus.FAILED
                signal.error_message = f"No account found for channel {signal.channel_id}"
                logger.error(signal.error_message)
                return history
            
            # Set account ID in cTrader API (for context even if we skip placing)
            self.ctrader_api.set_account_id(account.account_id)

            if not self.execute_trades:
                # Skip real execution, mark as executed (Telegram-only mode)
                signal.status = SignalStatus.EXECUTED
                signal.executed_at = datetime.now()
                history.execution_result = {
                    'status': 'SKIPPED',
                    'reason': 'Telegram-only mode: trade placement disabled',
                    'symbol': signal.symbol,
                    'trade_type': signal.trade_type.value,
                    'entry_price': signal.entry_price,
                    'stop_loss': signal.stop_loss,
                    'take_profit': signal.take_profit,
                    'account_id': account.account_id
                }
                logger.info(f"Signal {signal_id} marked executed (no trade placed)")
            else:
                # Place the trade via API (may fail if REST placeholder)
                trade_result = await self.ctrader_api.place_trade(**signal.to_trade_params())
                if trade_result:
                    signal.status = SignalStatus.EXECUTED
                    signal.executed_at = datetime.now()
                    signal.trade_id = trade_result.get('trade_id')
                    history.execution_result = trade_result
                    logger.info(f"Successfully executed signal {signal_id}")
                else:
                    signal.status = SignalStatus.FAILED
                    signal.error_message = "Failed to place trade via cTrader API"
                    logger.error(f"Failed to execute signal {signal_id}")
            
        except Exception as e:
            signal.status = SignalStatus.FAILED
            signal.error_message = str(e)
            logger.error(f"Error processing signal {signal_id}: {e}")
        
        # Calculate execution time
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds() * 1000
        history.execution_time_ms = int(execution_time)
        
        # Add to history
        self.signal_history.append(history)
        
        return history
    
    async def get_current_quote(self, symbol: str) -> Optional[Dict]:
        """Get current quote for a symbol"""
        return await self.ctrader_api.get_current_quotes(symbol)
    
    def get_signal_history(self, channel_id: Optional[str] = None, 
                          limit: int = 100) -> List[SignalHistory]:
        """Get signal execution history"""
        history = self.signal_history.copy()
        
        if channel_id:
            history = [h for h in history if h.signal.channel_id == channel_id]
        
        # Sort by creation time (newest first) and limit
        history.sort(key=lambda x: x.created_at, reverse=True)
        return history[:limit]
    
    def create_test_signal(self, symbol: str = "EURUSD", 
                          trade_type: str = "BUY",
                          entry_price: float = 1.0650,
                          stop_loss: float = 1.0600,
                          take_profit: float = 1.0750,
                          volume: float = 1.0) -> TradingSignal:
        """Create a test signal for testing purposes"""
        # Use the first available channel and account for testing
        if not self.channels:
            raise ValueError("No channels configured. Please add a channel first.")
            
        channel_id = list(self.channels.keys())[0]
        channel = self.channels[channel_id]
        
        signal = TradingSignal(
            symbol=symbol,
            trade_type=trade_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=volume,
            comment="Test signal",
            channel_id=channel_id,
            account_id=channel.account_id
        )
        
        return signal
    
    def get_statistics(self) -> Dict:
        """Get processing statistics"""
        total_signals = len(self.signal_history)
        executed_signals = len([h for h in self.signal_history if h.signal.status == SignalStatus.EXECUTED])
        failed_signals = len([h for h in self.signal_history if h.signal.status == SignalStatus.FAILED])
        
        avg_execution_time = 0
        if executed_signals > 0:
            execution_times = [h.execution_time_ms for h in self.signal_history 
                             if h.execution_time_ms is not None]
            if execution_times:
                avg_execution_time = sum(execution_times) / len(execution_times)
        
        return {
            'total_signals': total_signals,
            'executed_signals': executed_signals,
            'failed_signals': failed_signals,
            'success_rate': (executed_signals / total_signals * 100) if total_signals > 0 else 0,
            'avg_execution_time_ms': avg_execution_time,
            'active_channels': len([c for c in self.channels.values() if c.is_active]),
            'active_accounts': len([a for a in self.accounts.values() if a.is_active])
        }
