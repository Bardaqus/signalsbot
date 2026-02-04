# Fix TwelveDataClient Single-Shot Mode (max_retries=0)

## Problem

When `max_retries_override=0` (single-shot mode), the code was making **zero HTTP requests** instead of **exactly one HTTP request**.

### Root Cause

In `_make_request()`, line 379:
```python
for attempt in range(max_retries):
```

When `max_retries=0`, `range(0)` is empty, so the loop never executes, and we fall through to the end where it returns `None, "unknown_error"` without making any HTTP request.

## Solution

### Change 1: Treat `max_retries` as "number of retries" and compute `attempts = max_retries + 1`

**File:** `twelve_data_client.py`  
**Lines:** ~354-379

**Before:**
```python
if max_retries is None:
    max_retries = self.max_retries

# For single-shot mode (signal generation): disable retries
if single_shot or max_retries == 0:
    max_retries = 0

# ... later ...
for attempt in range(max_retries):  # BUG: range(0) is empty!
```

**After:**
```python
if max_retries is None:
    max_retries = self.max_retries

# For single-shot mode (signal generation): disable retries
if single_shot or max_retries == 0:
    max_retries = 0

# Treat max_retries as "number of retries" and compute total attempts
# max_retries=0 means 1 attempt (initial) + 0 retries = 1 total attempt
# max_retries=3 means 1 attempt (initial) + 3 retries = 4 total attempts
attempts = max_retries + 1

# ... later ...
for attempt in range(attempts):  # FIXED: range(1) = [0] -> one HTTP request
```

### Change 2: Update retry condition checks

**File:** `twelve_data_client.py`  
**Lines:** ~404, ~448, ~471, ~483

**Before:**
```python
if attempt < max_retries - 1:  # BUG: when max_retries=0, this is attempt < -1 (never true)
    # retry logic
```

**After:**
```python
if attempt < max_retries:  # FIXED: when max_retries=0, this is attempt < 0 (never true, no retries)
    # retry logic
```

**Logic:**
- `attempt` is 0-based: 0, 1, 2, ...
- `max_retries=0` → `attempts=1` → `attempt` can only be `0`
- `attempt < max_retries` → `0 < 0` → `False` → no retries ✓
- `max_retries=3` → `attempts=4` → `attempt` can be `0, 1, 2, 3`
- `attempt < max_retries` → `0,1,2 < 3` → retry on attempts 0,1,2 ✓

### Change 3: Improve error diagnostics

**File:** `twelve_data_client.py`  
**Lines:** ~396-422, ~435-466

**Added:**
- Log response `status_code` for all non-200 responses
- Log response body preview (first 200 chars) for all errors
- Parse and log JSON error details (`code`, `message`) when available
- Update reason codes: `"no_key"` → `"invalid_api_key"`, `"http_error_429"` → `"rate_limit_429"`

**Example:**
```python
# Before:
print(f"[TWELVE_DATA] ❌ API error: code={error_code}, message={error_message}")

# After:
response_preview = response.text[:200] if hasattr(response, 'text') else str(response)[:200]
print(f"[TWELVE_DATA] ❌ API error: code={error_code}, message={error_message}")
print(f"[TWELVE_DATA] Response preview: {response_preview}")
```

### Change 4: Update logging to show attempts vs retries

**File:** `twelve_data_client.py`  
**Lines:** ~545-550

**Before:**
```python
print(f"[TWELVE_DATA] [GET_PRICE] Requesting price for {symbol} (normalized: {normalized_symbol})")
```

**After:**
```python
retries = max_retries_override if max_retries_override is not None else self.max_retries
attempts_expected = retries + 1
print(f"[TWELVE_DATA] [GET_PRICE] Requesting price for {symbol} (normalized: {normalized_symbol}, attempts={attempts_expected}, retries={retries})")
```

### Change 5: Update startup test logging

**File:** `bot.py`  
**Lines:** ~1345-1350, ~1360-1365

**Added:** Logging to confirm single-shot mode makes 1 HTTP request

## Summary of Changes

### `twelve_data_client.py`:

1. **Line ~357-361**: Added `attempts = max_retries + 1` calculation
2. **Line ~379**: Changed `for attempt in range(max_retries)` → `for attempt in range(attempts)`
3. **Line ~404**: Changed `attempt < max_retries - 1` → `attempt < max_retries`
4. **Line ~410**: Updated log message to show `{attempts} attempt(s)` instead of `{max_retries} attempts`
5. **Line ~416-417**: Added response preview logging for permanent errors
6. **Line ~421-422**: Added response preview logging for API errors
7. **Line ~448**: Changed `attempt < max_retries - 1` → `attempt < max_retries`
8. **Line ~450**: Updated log message to show `{attempts} attempt(s)`
9. **Line ~454**: Added response preview logging for server errors
10. **Line ~459**: Added response preview logging for permanent errors
11. **Line ~465**: Added response preview logging and JSON error parsing for client errors
12. **Line ~471**: Changed `attempt < max_retries - 1` → `attempt < max_retries`
13. **Line ~473**: Updated log message to show `{attempts} attempt(s)`
14. **Line ~477**: Updated log message to show `{attempts} attempt(s)`
15. **Line ~483**: Changed `attempt < max_retries - 1` → `attempt < max_retries`
16. **Line ~485**: Updated log message to show `{attempts} attempt(s)`
17. **Line ~489**: Updated log message to show `{attempts} attempt(s)`
18. **Line ~520**: Updated error message to show `{attempts} attempt(s)` and `max_retries`
19. **Line ~545-550**: Added logging of `attempts_expected` and `retries` in get_price

### `bot.py`:

1. **Line ~1347**: Added logging to confirm single-shot mode in startup test
2. **Line ~1361**: Added logging to confirm single-shot mode in self-check

## Verification

### Before Fix:
```
max_retries=0 → range(0) → [] → no HTTP request → "unknown_error"
```

### After Fix:
```
max_retries=0 → attempts=1 → range(1) → [0] → 1 HTTP request → success or detailed error
```

### Expected Logs:

**Single-shot mode (max_retries=0):**
```
[TWELVE_DATA] [GET_PRICE] Requesting price for EURUSD (normalized: EUR/USD, attempts=1, retries=0)
[TWELVE_DATA] [HTTP_REQUEST] GET https://api.twelvedata.com/price?symbol=EUR/USD
[TWELVE_DATA] [HTTP_RESPONSE] GET https://api.twelvedata.com/price -> 200 OK
```

**With retries (max_retries=3):**
```
[TWELVE_DATA] [GET_PRICE] Requesting price for EURUSD (normalized: EUR/USD, attempts=4, retries=3)
[TWELVE_DATA] [HTTP_REQUEST] GET https://api.twelvedata.com/price?symbol=EUR/USD
... (up to 4 attempts)
```

## Testing

The fix ensures:
- ✅ `max_retries=0` → exactly 1 HTTP request (no retries)
- ✅ `max_retries=3` → up to 4 HTTP requests (1 initial + 3 retries)
- ✅ All error paths log response status_code and body preview
- ✅ Request counter increments only after successful HTTP requests
- ✅ No "unknown_error" without details
