#!/usr/bin/env python3
"""
Utility to diagnose .env file loading issues
Dumps all CTRADER_* keys and shows raw file content for debugging
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

dotenv_path = project_root / ".env"

print("=" * 80)
print("ENV FILE DIAGNOSTICS")
print("=" * 80)
print(f"Project root: {project_root}")
print(f"dotenv_path: {dotenv_path}")
print(f"File exists: {dotenv_path.exists()}")
print(f"cwd: {os.getcwd()}")
print()

if not dotenv_path.exists():
    print("❌ .env file not found!")
    sys.exit(1)

# Read file as bytes to check encoding/BOM
print("=" * 80)
print("FILE ENCODING & BOM CHECK")
print("=" * 80)
with open(dotenv_path, 'rb') as f:
    raw_bytes = f.read()

# Check for BOM
has_bom = raw_bytes.startswith(b'\xef\xbb\xbf')
print(f"Has UTF-8 BOM: {has_bom}")

# Try to detect encoding
encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1251', 'latin-1', 'ascii']
detected_encoding = None
file_content = None

for encoding in encodings_to_try:
    try:
        file_content = raw_bytes.decode(encoding)
        detected_encoding = encoding
        print(f"Successfully decoded as: {encoding}")
        break
    except UnicodeDecodeError:
        continue

if not file_content:
    print("❌ Could not decode file with any encoding!")
    sys.exit(1)

print()

# Load with python-dotenv
print("=" * 80)
print("PYTHON-DOTENV LOADED KEYS")
print("=" * 80)
from dotenv import load_dotenv
load_dotenv(dotenv_path=dotenv_path, override=False)

ctrader_keys = {}
for key, value in os.environ.items():
    if key.startswith('CTRADER_'):
        ctrader_keys[key] = value

if ctrader_keys:
    print(f"Found {len(ctrader_keys)} CTRADER_* keys via python-dotenv:")
    for key in sorted(ctrader_keys.keys()):
        value = ctrader_keys[key]
        preview = value[:20] + "..." if len(value) > 20 else value
        print(f"  {key} = {preview}")
else:
    print("❌ No CTRADER_* keys found via python-dotenv!")

print()

# Manual parsing of .env file
print("=" * 80)
print("MANUAL PARSING (RAW FILE CONTENT)")
print("=" * 80)

lines = file_content.splitlines()
ctrader_lines = []
all_keys_manual = {}

for line_num, line in enumerate(lines, 1):
    # Skip comments and empty lines
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        continue
    
    # Try to parse KEY=VALUE
    if '=' in stripped:
        # Handle quoted values
        parts = stripped.split('=', 1)
        if len(parts) == 2:
            key_raw = parts[0]
            value_raw = parts[1]
            
            # Normalize key (remove BOM, whitespace, etc.)
            key_normalized = key_raw.strip().lstrip('\ufeff').rstrip('\r\n')
            
            # Remove quotes from value if present
            value_normalized = value_raw.strip()
            if value_normalized.startswith('"') and value_normalized.endswith('"'):
                value_normalized = value_normalized[1:-1]
            elif value_normalized.startswith("'") and value_normalized.endswith("'"):
                value_normalized = value_normalized[1:-1]
            
            if key_normalized.startswith('CTRADER_'):
                ctrader_lines.append((line_num, line, key_normalized, value_normalized))
                all_keys_manual[key_normalized] = value_normalized

if ctrader_lines:
    print(f"Found {len(ctrader_lines)} CTRADER_* lines in file:")
    for line_num, raw_line, key, value in ctrader_lines:
        preview = value[:30] + "..." if len(value) > 30 else value
        print(f"  Line {line_num}: {key} = {preview}")
        print(f"    Raw: {repr(raw_line)}")
        
        # Check for problematic characters
        if '\r' in raw_line:
            print(f"    ⚠️  Contains \\r (carriage return)")
        if '\ufeff' in raw_line:
            print(f"    ⚠️  Contains BOM character")
        if key != key.strip():
            print(f"    ⚠️  Key has whitespace: {repr(key)}")
        print()
else:
    print("❌ No CTRADER_* lines found in file!")

# Check specifically for CTRADER_DEMO_WS_URL
print("=" * 80)
print("CTRADER_DEMO_WS_URL SPECIFIC CHECK")
print("=" * 80)

# Check in python-dotenv loaded env
dotenv_value = os.getenv('CTRADER_DEMO_WS_URL')
print(f"python-dotenv: {dotenv_value is not None} (value: {dotenv_value})")

# Check in manual parsing
manual_value = all_keys_manual.get('CTRADER_DEMO_WS_URL')
print(f"Manual parsing: {manual_value is not None} (value: {manual_value})")

# Search for variations
variations = [
    'CTRADER_DEMO_WS_URL',
    'CTRADER_DEMO_WS_URL\r',
    'CTRADER_DEMO_WS_URL\n',
    '\ufeffCTRADER_DEMO_WS_URL',
    'CTRADER_DEMO_WS_URL ',
    ' CTRADER_DEMO_WS_URL',
]

print("\nSearching for variations:")
for var in variations:
    found = False
    for line_num, raw_line, key, value in ctrader_lines:
        if var in raw_line:
            # Use repr() to safely show special characters
            safe_repr = repr(raw_line[:100])
            print(f"  Found '{var}' in line {line_num}: {safe_repr}")
            found = True
    if not found:
        # Use ASCII-safe representation
        var_safe = var.encode('ascii', 'replace').decode('ascii')
        print(f"  '{var_safe}' not found")

print()
print("=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

if dotenv_value is None and manual_value:
    print("⚠️  Key exists in file but python-dotenv didn't load it!")
    print("   → Likely encoding/BOM/whitespace issue")
    print("   → Try: Remove BOM, ensure UTF-8 encoding, check for \\r characters")
elif dotenv_value is None and not manual_value:
    print("❌ Key not found in file at all!")
    print("   → Add CTRADER_DEMO_WS_URL=wss://demo.ctraderapi.com:5035 to .env")
else:
    print("✅ Key loaded successfully")
