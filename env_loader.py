"""
Unified environment variable loader with diagnostics
"""
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values
from typing import Dict, Optional

# Critical CTRADER keys to check
CRITICAL_CTRADER_KEYS = [
    'CTRADER_IS_DEMO',
    'CTRADER_ACCOUNT_ID',
    'CTRADER_DEMO_WS_URL',
    'CTRADER_LIVE_WS_URL',
    'GOLD_CTRADER_ONLY',
    'CTRADER_CLIENT_ID',
    'CTRADER_CLIENT_SECRET',
    'CTRADER_ACCESS_TOKEN',
    'CTRADER_REFRESH_TOKEN',
]


def load_env(project_root: Path) -> Path:
    """Load .env file with diagnostics
    
    Args:
        project_root: Project root directory (where .env should be)
    
    Returns:
        Path to the loaded .env file
    
    Raises:
        FileNotFoundError: If .env file doesn't exist
    """
    dotenv_path = project_root / ".env"
    
    if not dotenv_path.exists():
        print(f"[ENV_LOADER] WARNING: .env file not found at {dotenv_path}")
        return dotenv_path
    
    print("=" * 80)
    print("[ENV_LOADER] Loading .env file")
    print("=" * 80)
    print(f"dotenv_path: {dotenv_path}")
    print(f"exists: {dotenv_path.exists()}")
    print()
    
    # Load with explicit encoding and override
    env_loaded = load_dotenv(dotenv_path=dotenv_path, override=True, encoding="utf-8")
    print(f"load_dotenv returned: {env_loaded}")
    print()
    
    # Diagnostic: Check what python-dotenv sees
    print("[ENV_LOADER] Critical CTRADER keys status (os.getenv):")
    print("-" * 80)
    key_status: Dict[str, bool] = {}
    for key in CRITICAL_CTRADER_KEYS:
        value = os.getenv(key)
        is_set = value is not None and value.strip() != ''
        key_status[key] = is_set
        
        # Show preview for sensitive keys
        if key in ['CTRADER_CLIENT_ID', 'CTRADER_CLIENT_SECRET', 'CTRADER_ACCESS_TOKEN', 'CTRADER_REFRESH_TOKEN']:
            preview = value[:8] + "..." if value and len(value) > 8 else (value or "(not set)")
            print(f"  {key}: {'[OK]' if is_set else '[MISSING]'} (preview: {preview})")
        else:
            preview_val = repr(value) if value else '(not set)'
            print(f"  {key}: {'[OK]' if is_set else '[MISSING]'} (value: {preview_val})")
    print()
    
    # Compare with dotenv_values (what python-dotenv parsed from file)
    print("[ENV_LOADER] Comparing dotenv_values() vs os.environ:")
    print("-" * 80)
    try:
        file_values = dotenv_values(dotenv_path=dotenv_path)
        mismatches = []
        
        for key in CRITICAL_CTRADER_KEYS:
            file_val = file_values.get(key)
            env_val = os.getenv(key)
            
            file_set = file_val is not None and file_val.strip() != ''
            env_set = env_val is not None and env_val.strip() != ''
            
            if file_set and not env_set:
                # Key exists in file but not in os.environ - possible encoding/parsing issue
                mismatches.append((key, file_val, env_val))
                print(f"  {key}: WARNING - Found in file but NOT in os.environ")
                print(f"    File value: {repr(file_val)}")
                print(f"    Possible causes: encoding issue, invisible characters, or override")
            elif file_set and env_set:
                # Both set - check if values match
                if file_val.strip() != env_val.strip():
                    print(f"  {key}: WARNING - Values differ")
                    print(f"    File: {repr(file_val)}")
                    print(f"    Env:  {repr(env_val)}")
        
        if not mismatches:
            print("  All keys match between file and os.environ")
        else:
            print(f"\n  Found {len(mismatches)} mismatches - keys exist in file but not loaded to os.environ")
            print("  This may indicate encoding/BOM issues or invisible characters")
    except Exception as e:
        print(f"  ERROR comparing dotenv_values: {e}")
    
    print()
    print("=" * 80)
    print()
    
    return dotenv_path
