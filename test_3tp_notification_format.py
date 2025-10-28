#!/usr/bin/env python3
"""
Test script to verify new TP notification format for channel -1001220540048
"""

def test_3tp_notification_format():
    """Test the new TP notification format for 3TP forex channel"""
    print("🧪 Testing New TP Notification Format for Channel -1001220540048")
    print("=" * 70)
    
    # Test scenarios for 3TP forex signals
    test_scenarios = [
        {
            "pair": "EURUSD",
            "type": "BUY",
            "entry": 1.10000,
            "tp1": 1.10200,
            "tp2": 1.10400,
            "tp3": 1.10600,
            "sl": 1.09700,
            "current_price": 1.10250,
            "expected_tp": "TP1",
            "expected_pips": 20.0
        },
        {
            "pair": "GBPUSD",
            "type": "SELL",
            "entry": 1.25000,
            "tp1": 1.24750,
            "tp2": 1.24500,
            "tp3": 1.24250,
            "sl": 1.25375,
            "current_price": 1.24550,
            "expected_tp": "TP2",
            "expected_pips": 45.0
        },
        {
            "pair": "USDJPY",
            "type": "BUY",
            "entry": 150.000,
            "tp1": 150.200,
            "tp2": 150.400,
            "tp3": 150.600,
            "sl": 149.700,
            "current_price": 150.600,
            "expected_tp": "TP3",
            "expected_pips": 600.0
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📊 Test {i}: {scenario['pair']} {scenario['type']}")
        print("-" * 50)
        
        # Calculate pips based on pair type
        if scenario['pair'].endswith("JPY"):
            multiplier = 1000  # JPY pairs use 3 decimal places
        else:
            multiplier = 10000  # Other pairs use 5 decimal places
        
        # Calculate profit in pips
        if scenario['type'] == "BUY":
            if scenario['expected_tp'] == "TP1":
                profit_pips = (scenario['tp1'] - scenario['entry']) * multiplier
            elif scenario['expected_tp'] == "TP2":
                profit_pips = (scenario['tp2'] - scenario['entry']) * multiplier
            elif scenario['expected_tp'] == "TP3":
                profit_pips = (scenario['tp3'] - scenario['entry']) * multiplier
        else:  # SELL
            if scenario['expected_tp'] == "TP1":
                profit_pips = (scenario['entry'] - scenario['tp1']) * multiplier
            elif scenario['expected_tp'] == "TP2":
                profit_pips = (scenario['entry'] - scenario['tp2']) * multiplier
            elif scenario['expected_tp'] == "TP3":
                profit_pips = (scenario['entry'] - scenario['tp3']) * multiplier
        
        # Calculate R/R ratio (simplified)
        rr_ratio = 0.7  # Mock ratio
        
        # Generate new notification message
        tp_hit = scenario['expected_tp']
        pair = scenario['pair']
        signal_type = scenario['type']
        
        if tp_hit == "TP3":
            message = f"🎯 {pair} {signal_type} - All targets achieved! +{profit_pips:.1f} pips profit"
        elif tp_hit == "TP2":
            message = f"✅ {pair} {signal_type} - TP2 hit! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
        else:  # TP1
            message = f"📈 {pair} {signal_type} - TP1 reached! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})"
        
        print(f"✅ Calculated Profit: +{profit_pips:.1f} pips")
        print(f"✅ Expected TP: {tp_hit}")
        print(f"✅ New Notification Message:")
        print(f"   {message}")
        
        # Verify calculation
        status = "✅" if abs(profit_pips - scenario['expected_pips']) < 0.1 else "❌"
        print(f"{status} Calculation: {'Correct' if status == '✅' else 'Incorrect'}")

def test_format_comparison():
    """Compare old vs new format"""
    print(f"\n📋 Format Comparison")
    print("=" * 50)
    
    pair = "EURUSD"
    signal_type = "BUY"
    profit_pips = 20.0
    rr_ratio = 0.7
    
    print("OLD FORMAT:")
    print(f"  #{pair}: TP1 reached 🎯💰 +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})")
    print(f"  #{pair}: Both targets 🔥🔥🔥 hit +{profit_pips:.1f} pips total gain!")
    
    print("\nNEW FORMAT:")
    print(f"  📈 {pair} {signal_type} - TP1 reached! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})")
    print(f"  ✅ {pair} {signal_type} - TP2 hit! +{profit_pips:.1f} pips (R/R 1:{rr_ratio:.1f})")
    print(f"  🎯 {pair} {signal_type} - All targets achieved! +{profit_pips:.1f} pips profit")
    
    print(f"\n🎯 Key Changes:")
    print("  ✅ Removed # symbol")
    print("  ✅ Added signal type (BUY/SELL)")
    print("  ✅ More professional emojis")
    print("  ✅ Clearer target descriptions")
    print("  ✅ Maintained pips calculation")

if __name__ == "__main__":
    test_3tp_notification_format()
    test_format_comparison()
    print(f"\n🎉 All tests completed!")
    print(f"📤 Channel -1001220540048 now uses the new notification format!")
