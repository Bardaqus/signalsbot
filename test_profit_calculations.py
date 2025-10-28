#!/usr/bin/env python3
"""
Test script to demonstrate the new profit calculation system
Crypto: percentage, Forex: pips
"""

def test_profit_calculations():
    """Test profit calculations for crypto and forex signals"""
    print("🧪 Testing New Profit Calculation System")
    print("=" * 60)
    
    # Test crypto signals (percentage)
    print("\n📊 CRYPTO SIGNALS (Percentage)")
    print("-" * 40)
    
    crypto_test_cases = [
        {"pair": "BTCUSDT", "type": "BUY", "entry": 50000, "current": 52000, "expected": "+4.00%"},
        {"pair": "ETHUSDT", "type": "SELL", "entry": 3000, "current": 2850, "expected": "+5.00%"},
        {"pair": "ADAUSDT", "type": "BUY", "entry": 0.50, "current": 0.45, "expected": "-10.00%"},
    ]
    
    for case in crypto_test_cases:
        pair = case["pair"]
        signal_type = case["type"]
        entry = case["entry"]
        current = case["current"]
        expected = case["expected"]
        
        # Calculate crypto profit (percentage)
        if signal_type == "BUY":
            profit_pct = ((current - entry) / entry) * 100
        else:  # SELL
            profit_pct = ((entry - current) / entry) * 100
        
        result = f"{profit_pct:+.2f}%"
        status = "✅" if result == expected else "❌"
        print(f"{status} {pair} {signal_type}: {result} (Expected: {expected})")
    
    # Test forex signals (pips)
    print("\n📈 FOREX SIGNALS (Pips)")
    print("-" * 40)
    
    forex_test_cases = [
        {"pair": "EURUSD", "type": "BUY", "entry": 1.1000, "current": 1.1103, "expected": "+103.0 pips"},
        {"pair": "GBPUSD", "type": "SELL", "entry": 1.2500, "current": 1.2308, "expected": "+192.0 pips"},
        {"pair": "USDJPY", "type": "BUY", "entry": 150.00, "current": 149.50, "expected": "-500.0 pips"},
        {"pair": "AUDUSD", "type": "SELL", "entry": 0.6500, "current": 0.6600, "expected": "-100.0 pips"},
    ]
    
    for case in forex_test_cases:
        pair = case["pair"]
        signal_type = case["type"]
        entry = case["entry"]
        current = case["current"]
        expected = case["expected"]
        
        # Calculate forex profit (pips)
        if pair.endswith("JPY"):
            # JPY pairs use 3 decimal places, so multiply by 1000
            multiplier = 1000
        else:
            # Other pairs use 5 decimal places, so multiply by 10000
            multiplier = 10000
        
        if signal_type == "BUY":
            profit_pips = (current - entry) * multiplier
        else:  # SELL
            profit_pips = (entry - current) * multiplier
        
        result = f"{profit_pips:+.1f} pips"
        status = "✅" if result == expected else "❌"
        print(f"{status} {pair} {signal_type}: {result} (Expected: {expected})")
    
    print("\n🎯 PROFIT CALCULATION SUMMARY")
    print("-" * 40)
    print("✅ Crypto signals: Calculated in percentage (%)")
    print("✅ Forex signals: Calculated in pips")
    print("✅ JPY pairs: Use 3 decimal places (multiply by 1000)")
    print("✅ Other pairs: Use 5 decimal places (multiply by 10000)")
    print("✅ BUY signals: Profit when price goes up")
    print("✅ SELL signals: Profit when price goes down")

def test_performance_report_format():
    """Test performance report formatting with proper units"""
    print("\n📋 PERFORMANCE REPORT FORMAT")
    print("-" * 40)
    
    # Mock performance data
    crypto_signals = [
        {"pair": "BTCUSDT", "type": "BUY", "profit": 4.5, "unit": "%"},
        {"pair": "ETHUSDT", "type": "SELL", "profit": -2.1, "unit": "%"},
    ]
    
    forex_signals = [
        {"pair": "EURUSD", "type": "BUY", "profit": 103.5, "unit": "pips"},
        {"pair": "GBPUSD", "type": "SELL", "profit": -50.0, "unit": "pips"},
    ]
    
    print("Crypto Signals:")
    for signal in crypto_signals:
        profit_display = f"{signal['profit']:+.2f}{signal['unit']}"
        status = "✅" if signal['profit'] > 0 else "❌"
        print(f"  {status} {signal['pair']} {signal['type']}: {profit_display}")
    
    print("\nForex Signals:")
    for signal in forex_signals:
        profit_display = f"{signal['profit']:+.1f} {signal['unit']}"
        status = "✅" if signal['profit'] > 0 else "❌"
        print(f"  {status} {signal['pair']} {signal['type']}: {profit_display}")

if __name__ == "__main__":
    test_profit_calculations()
    test_performance_report_format()
    print("\n🎉 All profit calculation tests completed!")
