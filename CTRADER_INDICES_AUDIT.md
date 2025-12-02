# cTrader Indices Subscription Audit Report

## Issues Found

### ✅ Issue #1: Symbol ID vs. Name - **CORRECT**
**Location**: `ctrader_stream.py` lines 52-63

**Status**: ✅ **WORKING CORRECTLY**

The code correctly:
- Maps symbol names to IDs using `ProtoOASymbolsListReq` (line 76)
- Uses numeric `symbolId` in `ProtoOASubscribeForSymbolQuotesReq` (line 59)
- Stores mapping in `symbol_name_to_id` dictionary

**Code**:
```python
async def subscribe(self, symbol_name: str):
    sym = symbol_name.upper()
    if sym not in self.symbol_name_to_id:
        logger.warning(f"Symbol {sym} not resolved yet; delaying subscribe")
        return
    sub_req = OACommon.ProtoOASubscribeForSymbolQuotesReq(
        ctidTraderAccountId=self.account_id,
        symbolId=self.symbol_name_to_id[sym],  # ✅ Using ID, not name
        subscribeToSpotTimestamp=True
    )
```

---

### ❌ Issue #2: Asset Class Filtering - **PROBLEM FOUND**
**Location**: `auto_signal_generator.py` lines 27-31

**Status**: ❌ **MAJOR ISSUE**

**Problem**: The `major_pairs` list only contains Forex pairs. Indices are **NOT included**, so they're never subscribed to.

**Current Code**:
```python
self.major_pairs = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", 
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP",
    "AUDJPY", "CHFJPY", "EURCHF", "GBPCHF", "AUDCAD"
]
# ❌ NO INDICES HERE!
```

**Impact**: Even if you try to subscribe to "US500", it's not in the list, so it's never attempted.

**Fix Required**: Add indices to the symbol list.

---

### ✅ Issue #3: Subscription Scope - **CORRECT**
**Location**: `ctrader_stream.py` line 57

**Status**: ✅ **WORKING CORRECTLY**

The code uses `ProtoOASubscribeForSymbolQuotesReq` which is correct for both:
- Forex pairs (spot quotes)
- Indices/CFDs (spot quotes)

This is the correct request type for real-time price data.

---

### ❌ Issue #4: Error Handling - **PROBLEM FOUND**
**Location**: `ctrader_stream.py` lines 52-63, `main_auto_signals.py` lines 66-70

**Status**: ❌ **MISSING ERROR HANDLING**

**Problems**:
1. No error handling for subscription failures
2. No logging of API error responses (UNKNOWN_SYMBOL, PERMISSION_DENIED)
3. No retry logic for failed subscriptions
4. Silent failures - if subscription fails, you won't know why

**Current Code**:
```python
async def subscribe(self, symbol_name: str):
    # ... subscription code ...
    await self.client.send(sub_req)  # ❌ No error handling
    logger.info(f"Subscribed to {sym}")  # ❌ Always logs success, even if it fails
```

**Fix Required**: Add comprehensive error handling and logging.

---

## Summary

| Issue | Status | Severity |
|-------|--------|----------|
| #1: Symbol ID vs Name | ✅ Correct | - |
| #2: Asset Class Filtering | ❌ **CRITICAL** | **HIGH** |
| #3: Subscription Scope | ✅ Correct | - |
| #4: Error Handling | ❌ **CRITICAL** | **HIGH** |

---

## Root Cause

**The main issue is Issue #2**: Your bot only subscribes to Forex pairs because `major_pairs` doesn't include indices. Even if indices are available in cTrader, they're never attempted for subscription.

**Secondary issue is Issue #4**: Without proper error handling, you can't see why subscriptions fail (if they do).

---

## Recommended Fixes

1. **Add indices to symbol list** in `auto_signal_generator.py`
2. **Add comprehensive error handling** in `ctrader_stream.py`
3. **Add error response logging** to catch API errors
4. **Add retry logic** for failed subscriptions

