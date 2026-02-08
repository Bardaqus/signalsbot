#!/usr/bin/env python3
"""
Environment file doctor - diagnose why python-dotenv doesn't see CTRADER_DEMO_WS_URL
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

dotenv_path = project_root / ".env"

print("=" * 80)
print("ENV DOCTOR - CTRADER_DEMO_WS_URL Diagnostics")
print("=" * 80)
print(f"Project root: {project_root}")
print(f"dotenv_path: {dotenv_path}")
print(f"File exists: {dotenv_path.exists()}")
print(f"cwd: {os.getcwd()}")
print()

if not dotenv_path.exists():
    print("[ERROR] .env file not found!")
    sys.exit(1)

# 1) Read file as bytes and check BOM
print("=" * 80)
print("1. RAW FILE ANALYSIS (bytes)")
print("=" * 80)
with open(dotenv_path, 'rb') as f:
    raw_bytes = f.read()

file_size = len(raw_bytes)
print(f"File size: {file_size} bytes")

# Check BOM (first 3 bytes)
first_3_bytes = raw_bytes[:3]
print(f"First 3 bytes (hex): {first_3_bytes.hex()}")
print(f"First 3 bytes (repr): {repr(first_3_bytes)}")

if first_3_bytes == b'\xef\xbb\xbf':
    print("[DETECTED] UTF-8 BOM detected")
else:
    print("[OK] No UTF-8 BOM")

# Show first 200 bytes in hex
print(f"\nFirst 200 bytes (hex):")
hex_str = raw_bytes[:200].hex()
# Format as hex pairs with line breaks every 32 bytes
for i in range(0, min(200, len(raw_bytes)), 32):
    chunk = raw_bytes[i:i+32]
    hex_chunk = chunk.hex()
    # Format as pairs
    hex_pairs = ' '.join(hex_chunk[j:j+2] for j in range(0, len(hex_chunk), 2))
    print(f"  {i:04x}: {hex_pairs}")

print()

# 2) Read file as text and find CTRADER_DEMO/CTRADER_IS_DEMO/CTRADER_ACCOUNT_ID lines
print("=" * 80)
print("2. TEXT ANALYSIS (lines containing CTRADER_DEMO/CTRADER_IS_DEMO/CTRADER_ACCOUNT_ID)")
print("=" * 80)

# Read as text with utf-8, errors='replace'
try:
    file_content = raw_bytes.decode('utf-8', errors='replace')
except Exception as e:
    print(f"[ERROR] Failed to decode as UTF-8: {e}")
    # Try utf-8-sig to handle BOM
    try:
        file_content = raw_bytes.decode('utf-8-sig', errors='replace')
        print("[INFO] Decoded as UTF-8-sig (BOM removed)")
    except Exception as e2:
        print(f"[ERROR] Failed to decode as UTF-8-sig: {e2}")
        sys.exit(1)

lines = file_content.splitlines()
print(f"Total lines in file: {len(lines)}")

# Find lines containing target patterns
target_patterns = ['CTRADER_DEMO', 'CTRADER_IS_DEMO', 'CTRADER_ACCOUNT_ID']
matching_lines = []

for line_num, line in enumerate(lines, 1):
    for pattern in target_patterns:
        if pattern in line:
            matching_lines.append((line_num, line, pattern))
            break

if matching_lines:
    print(f"\nFound {len(matching_lines)} matching lines:")
    for line_num, line, pattern in matching_lines:
        print(f"\n  Line {line_num} (pattern: {pattern}):")
        print(f"    repr(): {repr(line)}")
        print(f"    Raw: {line}")
        
        # Check for problematic characters
        issues = []
        if '\r' in line:
            issues.append("contains \\r (carriage return)")
        if '\t' in line:
            issues.append("contains \\t (tab)")
        if '\ufeff' in line:
            issues.append("contains BOM character (\\ufeff)")
        if line.strip() != line:
            issues.append("has leading/trailing whitespace")
        
        if issues:
            print(f"    [WARN] Issues: {', '.join(issues)}")
else:
    print("\n[ERROR] No lines found containing CTRADER_DEMO, CTRADER_IS_DEMO, or CTRADER_ACCOUNT_ID")

print()

# 3) Compare dotenv vs manual parser
print("=" * 80)
print("3. COMPARISON: python-dotenv vs manual parser")
print("=" * 80)

# Clear environment first
for key in list(os.environ.keys()):
    if key.startswith('CTRADER_'):
        del os.environ[key]

# A) Load with python-dotenv
print("\nA) python-dotenv:")
from dotenv import load_dotenv
load_dotenv(dotenv_path=dotenv_path, override=False)

dotenv_results = {}
target_keys = ['CTRADER_DEMO_WS_URL', 'CTRADER_IS_DEMO', 'CTRADER_ACCOUNT_ID']
for key in target_keys:
    value = os.getenv(key)
    dotenv_results[key] = value
    found = value is not None and value.strip() != ''
    print(f"  {key}: {'[OK] Found' if found else '[FAIL] Not found'} (value: {repr(value)})")

# B) Manual parser
print("\nB) Manual parser:")
manual_results = {}

# Parse manually
for line in lines:
    # Skip empty lines and comments
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        continue
    
    # Split by first '='
    if '=' not in stripped:
        continue
    
    parts = stripped.split('=', 1)
    if len(parts) != 2:
        continue
    
    key_raw = parts[0]
    value_raw = parts[1]
    
    # Normalize key (remove BOM, whitespace, \r\n)
    key_normalized = key_raw.strip().lstrip('\ufeff').rstrip('\r\n').rstrip()
    
    # Normalize value
    value_normalized = value_raw.strip()
    # Remove quotes
    if value_normalized.startswith('"') and value_normalized.endswith('"'):
        value_normalized = value_normalized[1:-1]
    elif value_normalized.startswith("'") and value_normalized.endswith("'"):
        value_normalized = value_normalized[1:-1]
    
    if key_normalized in target_keys:
        manual_results[key_normalized] = value_normalized
        print(f"  {key_normalized}: [OK] Found (value: {repr(value_normalized)})")

# Show keys found by manual but not by dotenv
for key in target_keys:
    if key not in manual_results:
        print(f"  {key}: [FAIL] Not found")

print()

# 4) Final summary
print("=" * 80)
print("4. SUMMARY")
print("=" * 80)

for key in target_keys:
    dotenv_sees = dotenv_results.get(key) is not None and dotenv_results.get(key).strip() != ''
    manual_sees = key in manual_results
    
    print(f"\n{key}:")
    print(f"  dotenv sees: {dotenv_sees} (value: {repr(dotenv_results.get(key))})")
    print(f"  manual sees: {manual_sees} (value: {repr(manual_results.get(key) if manual_sees else None)})")
    
    if not dotenv_sees and manual_sees:
        print(f"  [WARN] Key exists in file but python-dotenv didn't load it!")
        print(f"         -> Fallback parser should load it automatically")
    elif not dotenv_sees and not manual_sees:
        print(f"  [ERROR] Key not found in file at all!")
        print(f"          -> Add {key}=<value> to .env file")

print()
print("=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

missing_in_both = [k for k in target_keys if (not dotenv_results.get(k) or dotenv_results.get(k).strip() == '') and k not in manual_results]
found_in_manual_only = [k for k in target_keys if (not dotenv_results.get(k) or dotenv_results.get(k).strip() == '') and k in manual_results]
all_found = all((dotenv_results.get(k) and dotenv_results.get(k).strip() != '') or k in manual_results for k in target_keys)

if found_in_manual_only:
    print(f"[INFO] Keys found by manual parser but not by python-dotenv: {found_in_manual_only}")
    print("        -> These will be loaded by fallback parser automatically")
    print("        -> Check for encoding/BOM/whitespace issues in .env file")
elif missing_in_both:
    print(f"[ERROR] Keys not found in file: {missing_in_both}")
    print("         -> Add these keys to .env file:")
    for key in missing_in_both:
        if key == 'CTRADER_DEMO_WS_URL':
            print(f"            {key}=wss://demo.ctraderapi.com:5035")
        elif key == 'CTRADER_IS_DEMO':
            print(f"            {key}=true")
        elif key == 'CTRADER_ACCOUNT_ID':
            print(f"            {key}=44749280")
elif all_found:
    print("[OK] All keys loaded successfully")
else:
    print("[WARN] Some keys may have issues - check output above")
