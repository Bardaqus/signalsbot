#!/usr/bin/env python3
"""
Test script for Finnhub.io index price fetching (using ETF proxies)
Run this to verify the Finnhub API integration works correctly

Note: Uses ETF tickers (SPY, QQQ, DIA) as proxies for indices since direct
index tickers require a paid subscription. ETF prices are approximate
proxies (typically 1/10th or 1/100th of the actual index value).
"""

import asyncio
import sys
from config import Config
from working_combined_bot import get_finnhub_index_price, FINNHUB_INDEX_TICKERS

async def test_finnhub_indices():
    """Test fetching prices for various indices using ETF proxies"""
    print("=" * 60)
    print("FINNHUB.IO INDEX PRICE FETCHER - TEST (ETF Proxies)")
    print("=" * 60)
    print(f"\nAPI Key: {Config.FINNHUB_API_KEY[:10]}..." if Config.FINNHUB_API_KEY else "❌ API Key not configured!")
    print(f"\n⚠️  Note: Using ETF proxies (SPY, QQQ, DIA) for free tier access")
    print(f"   ETF prices are approximate (typically 1/10th or 1/100th of index value)\n")
    print(f"Available index mappings:")
    for name, ticker in FINNHUB_INDEX_TICKERS.items():
        print(f"  • {name:20} → {ticker} (ETF)")
    
    print("\n" + "=" * 60)
    print("Testing index price fetching...")
    print("=" * 60 + "\n")
    
    # Test indices
    test_indices = [
        "S&P 500",
        "Nasdaq 100", 
        "Dow Jones",
        "US500",  # Alternative name
        "USTEC",  # Alternative name
        "US30",   # Alternative name
    ]
    
    results = []
    for index_name in test_indices:
        print(f"📊 Fetching price for: {index_name}")
        try:
            price = await get_finnhub_index_price(index_name)
            if price:
                results.append((index_name, price, "✅ Success"))
                print(f"   ✅ Price: ${price:,.2f}\n")
            else:
                results.append((index_name, None, "❌ Failed"))
                print(f"   ❌ Failed to get price\n")
        except Exception as e:
            results.append((index_name, None, f"❌ Error: {e}"))
            print(f"   ❌ Error: {e}\n")
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for index_name, price, status in results:
        if price:
            etf_ticker = FINNHUB_INDEX_TICKERS.get(index_name, "N/A")
            print(f"{status} {index_name:20} → ${price:,.2f} ({etf_ticker} ETF)")
        else:
            print(f"{status} {index_name:20} → No price")
    
    successful = sum(1 for _, price, _ in results if price)
    print(f"\n✅ Successful: {successful}/{len(results)}")
    
    if successful == 0:
        print("\n⚠️  No prices fetched. Check:")
        print("   - API key is correct")
        print("   - Internet connection")
        print("   - Finnhub API status")
        sys.exit(1)
    else:
        print("\n✅ Test completed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(test_finnhub_indices())

