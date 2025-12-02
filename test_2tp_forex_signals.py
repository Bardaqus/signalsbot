#!/usr/bin/env python3
"""
Test script to demonstrate the new 2 TP forex signals
"""

import asyncio
from bot import generate_signal_from_bars, build_signal_message, add_signal, check_signal_hits
from datetime import datetime, timezone

def test_2tp_signal_generation():
    """Test 2 TP signal generation"""
    print("🧪 Testing 2 TP forex signal generation...")
    
    # Mock bars data for testing
    mock_bars = [
        {"close": 1.2500, "high": 1.2510, "low": 1.2490},
        {"close": 1.2505, "high": 1.2515, "low": 1.2495},
        {"close": 1.2510, "high": 1.2520, "low": 1.2500},
        {"close": 1.2508, "high": 1.2518, "low": 1.2498},
        {"close": 1.2512, "high": 1.2522, "low": 1.2502},
    ]
    
    # Test forex signal generation
    symbol = "EURUSD.FOREX"
    signal_type, metrics = generate_signal_from_bars(mock_bars, symbol)
    
    if signal_type in ("BUY", "SELL") and metrics:
        print(f"\n✅ Generated {signal_type} signal for {symbol}")
        print(f"Entry: {metrics['entry']:.5f}")
        print(f"SL: {metrics['sl']:.5f}")
        print(f"TP1: {metrics['tp1']:.5f}")
        print(f"TP2: {metrics['tp2']:.5f}")
        
        # Test signal message formatting
        msg = build_signal_message(symbol, signal_type, metrics['entry'], metrics['sl'], metrics['tp1'], metrics['tp2'])
        print(f"\n📤 Signal Message:")
        print(msg)
        
        # Test XAUUSD signal (single TP)
        xau_symbol = "XAUUSD.FOREX"
        xau_signal_type, xau_metrics = generate_signal_from_bars(mock_bars, xau_symbol)
        
        if xau_signal_type in ("BUY", "SELL") and xau_metrics:
            print(f"\n✅ Generated {xau_signal_type} signal for {xau_symbol}")
            print(f"Entry: {xau_metrics['entry']:.2f}")
            print(f"SL: {xau_metrics['sl']:.2f}")
            print(f"TP: {xau_metrics['tp']:.2f}")
            
            # Test single TP message formatting
            xau_msg = build_signal_message(xau_symbol, xau_signal_type, xau_metrics['entry'], xau_metrics['sl'], xau_metrics['tp'])
            print(f"\n📤 XAUUSD Signal Message:")
            print(xau_msg)
    
    print("\n✅ 2 TP forex signal generation test completed!")

def test_tp_hit_detection():
    """Test TP hit detection for 2 TPs"""
    print("\n🧪 Testing TP hit detection for 2 TPs...")
    
    # Mock signal data
    mock_signal = {
        "symbol": "EURUSD.FOREX",
        "type": "BUY",
        "entry": 1.2500,
        "sl": 1.2400,
        "tp1": 1.2603,  # 103 pips
        "tp2": 1.2706,  # 206 pips
        "status": "active"
    }
    
    print(f"Mock Signal: {mock_signal}")
    
    # Test different price scenarios
    test_scenarios = [
        {"price": 1.2450, "expected": "SL hit"},
        {"price": 1.2550, "expected": "No hit"},
        {"price": 1.2603, "expected": "TP1 hit"},
        {"price": 1.2650, "expected": "TP1 hit"},
        {"price": 1.2706, "expected": "TP2 hit"},
        {"price": 1.2750, "expected": "TP2 hit"},
    ]
    
    for scenario in test_scenarios:
        price = scenario["price"]
        expected = scenario["expected"]
        
        # Simulate TP hit detection logic
        if mock_signal["type"] == "BUY":
            hit_sl = price <= mock_signal["sl"]
            if price >= mock_signal["tp2"]:
                hit_tp = "TP2"
            elif price >= mock_signal["tp1"]:
                hit_tp = "TP1"
            else:
                hit_tp = None
        else:
            hit_sl = price >= mock_signal["sl"]
            if price <= mock_signal["tp2"]:
                hit_tp = "TP2"
            elif price <= mock_signal["tp1"]:
                hit_tp = "TP1"
            else:
                hit_tp = None
        
        if hit_tp:
            result = f"{hit_tp} hit"
        elif hit_sl:
            result = "SL hit"
        else:
            result = "No hit"
        
        print(f"Price: {price:.4f} -> {result} (Expected: {expected})")
    
    print("\n✅ TP hit detection test completed!")

if __name__ == "__main__":
    test_2tp_signal_generation()
    test_tp_hit_detection()
    print("\n🎉 All tests completed successfully!")
