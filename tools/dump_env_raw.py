#!/usr/bin/env python3
"""
Raw .env file diagnostic tool - shows exactly what's in the file
"""
import os
import sys
from pathlib import Path
from dotenv import dotenv_values

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

dotenv_path = project_root / ".env"

print("=" * 80)
print("RAW .env FILE DIAGNOSTIC")
print("=" * 80)
print(f"dotenv_path: {dotenv_path}")
print(f"exists: {dotenv_path.exists()}")
print()

if not dotenv_path.exists():
    print("ERROR: .env file does not exist!")
    sys.exit(1)

# 1. Read raw bytes
print("=" * 80)
print("1. RAW BYTES (first 200 bytes in hex)")
print("=" * 80)
with open(dotenv_path, 'rb') as f:
    raw_bytes = f.read()
    print(f"Total file size: {len(raw_bytes)} bytes")
    print(f"First 200 bytes (hex): {raw_bytes[:200].hex()}")
    print()

# 2. Read as text and show first 30 lines
print("=" * 80)
print("2. FIRST 30 LINES (with repr)")
print("=" * 80)
encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1251', 'latin-1']
file_content = None
detected_encoding = None

for encoding in encodings_to_try:
    try:
        file_content = raw_bytes.decode(encoding)
        detected_encoding = encoding
        print(f"Successfully decoded as: {encoding}")
        break
    except UnicodeDecodeError:
        continue

if not file_content:
    print("ERROR: Could not decode file with any encoding!")
    sys.exit(1)

lines = file_content.splitlines()
print(f"Total lines: {len(lines)}")
print()
for i, line in enumerate(lines[:30], 1):
    print(f"Line {i:3d}: {repr(line)}")
print()

# 3. Find lines containing 'CTRADER'
print("=" * 80)
print("3. LINES CONTAINING 'CTRADER'")
print("=" * 80)
ctrader_lines = []
for i, line in enumerate(lines, 1):
    if 'CTRADER' in line.upper():
        ctrader_lines.append((i, line))

if not ctrader_lines:
    print("WARNING: No lines containing 'CTRADER' found!")
else:
    for line_num, line in ctrader_lines:
        print(f"Line {line_num:3d}: {repr(line)}")
        
        # Show character analysis for KEY part (before '=')
        if '=' in line:
            key_part = line.split('=', 1)[0]
            print(f"         KEY part: {repr(key_part)}")
            print(f"         KEY chars: ", end="")
            for j, char in enumerate(key_part):
                print(f"[{j}]{repr(char)}(ord={ord(char)}) ", end="")
            print()
            print(f"         KEY stripped: {repr(key_part.strip())}")
            print(f"         KEY lstrip(BOM): {repr(key_part.lstrip(chr(0xFEFF)))}")
        print()

# 4. Use dotenv_values to see what python-dotenv sees
print("=" * 80)
print("4. python-dotenv dotenv_values() RESULTS")
print("=" * 80)
try:
    env_values = dotenv_values(dotenv_path=dotenv_path)
    print(f"Total keys found by dotenv_values: {len(env_values)}")
    print()
    
    ctrader_keys_found = []
    for key, value in env_values.items():
        if 'CTRADER' in key.upper() or key == 'GOLD_CTRADER_ONLY':
            ctrader_keys_found.append((key, value))
    
    if not ctrader_keys_found:
        print("WARNING: No CTRADER_* keys found by dotenv_values!")
    else:
        print("CTRADER_* keys found by dotenv_values:")
        for key, value in ctrader_keys_found:
            print(f"  {repr(key)}: {repr(value)}")
    
    print()
    print("Critical keys check:")
    critical_keys = ['CTRADER_IS_DEMO', 'CTRADER_ACCOUNT_ID', 'CTRADER_DEMO_WS_URL']
    for key in critical_keys:
        if key in env_values:
            print(f"  {key}: {repr(env_values[key])} [FOUND]")
        else:
            print(f"  {key}: [NOT FOUND]")
    
except Exception as e:
    print(f"ERROR calling dotenv_values: {e}")
    import traceback
    traceback.print_exc()

# 5. Check os.getenv after load_dotenv
print("=" * 80)
print("5. os.getenv() AFTER load_dotenv")
print("=" * 80)
from dotenv import load_dotenv
load_dotenv(dotenv_path=dotenv_path, override=True)

critical_keys = ['CTRADER_IS_DEMO', 'CTRADER_ACCOUNT_ID', 'CTRADER_DEMO_WS_URL']
for key in critical_keys:
    value = os.getenv(key)
    print(f"  {key}: {repr(value)}")

print()
print("=" * 80)
