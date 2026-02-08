"""
Robust HTTP client for external APIs with SSL/certificate support
"""
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any
import ssl

# Try to import certifi for CA bundle
try:
    import certifi
    _certifi_available = True
except ImportError:
    _certifi_available = False
    certifi = None


def _get_proxy_info() -> Dict[str, str]:
    """Get proxy information (hostnames only, no credentials)"""
    proxies = {}
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
    for var in proxy_vars:
        proxy_url = os.getenv(var)
        if proxy_url:
            # Extract hostname only (no credentials)
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if parsed.hostname:
                proxies[var] = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"
    return proxies


def create_http_session() -> requests.Session:
    """Create a robust HTTP session with SSL/certificate support
    
    Returns:
        Configured requests.Session
    """
    session = requests.Session()
    
    # Configure timeouts
    session.timeout = (5, 10)  # (connect_timeout, read_timeout)
    
    # Configure retries
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Configure SSL verification
    verify_ssl_env = os.getenv('GOLD_PRICE_VERIFY_SSL', 'true').lower()
    verify_ssl = verify_ssl_env in ('true', '1', 'yes')
    
    if verify_ssl:
        # Check for custom CA bundle first (corporate CA support)
        custom_ca_bundle = os.getenv('REQUESTS_CA_BUNDLE')
        if custom_ca_bundle:
            if os.path.exists(custom_ca_bundle):
                session.verify = custom_ca_bundle
                print(f"[HTTP_CLIENT] Using custom CA bundle: {custom_ca_bundle}")
            else:
                print(f"[HTTP_CLIENT] WARNING: REQUESTS_CA_BUNDLE={custom_ca_bundle} file not found, falling back to certifi")
                if _certifi_available:
                    session.verify = certifi.where()
                else:
                    session.verify = True
        else:
            # Use certifi CA bundle if available
            if _certifi_available:
                ca_bundle = certifi.where()
                session.verify = ca_bundle
            else:
                # Fallback to system default
                session.verify = True
    else:
        session.verify = False
        print("=" * 80)
        print("[HTTP_CLIENT] WARNING: SSL VERIFICATION IS DISABLED!")
        print("   GOLD_PRICE_VERIFY_SSL=false is set for diagnostics only.")
        print("   This is INSECURE and should NOT be used in production.")
        print("   If you see SSL errors, try:")
        print("   1. Set REQUESTS_CA_BUNDLE=/path/to/corporate/ca.pem")
        print("   2. Check proxy/antivirus settings")
        print("   3. Update certifi: pip install --upgrade certifi")
        print("=" * 80)
    
    # Set user agent
    session.headers.update({
        'User-Agent': 'SignalsBot/1.0 (Python/requests)'
    })
    
    return session


def log_request_error(
    provider_name: str,
    url: str,
    exception: Exception,
    session: requests.Session
) -> str:
    """Log detailed error information for HTTP requests
    
    Args:
        provider_name: Name of the provider
        url: URL that was requested
        exception: Exception that occurred
        session: requests.Session used
    
    Returns:
        Formatted error message
    """
    error_parts = []
    error_parts.append(f"{provider_name}: {type(exception).__name__}")
    
    # SSL-specific error details
    if isinstance(exception, requests.exceptions.SSLError):
        error_parts.append(f"SSL Error: {str(exception)[:300]}")
        
        # Try to extract underlying SSL error
        underlying_ssl_error = None
        if hasattr(exception, 'args') and exception.args:
            for arg in exception.args:
                if isinstance(arg, ssl.SSLError):
                    underlying_ssl_error = arg
                    break
                elif isinstance(arg, Exception):
                    # Sometimes SSL error is wrapped
                    error_parts.append(f"Wrapped error: {type(arg).__name__}: {str(arg)[:200]}")
        
        if underlying_ssl_error:
            error_parts.append(f"Underlying SSL error reason: {underlying_ssl_error.reason}")
            error_parts.append(f"Underlying SSL error string: {str(underlying_ssl_error)[:200]}")
        
        # Check for SNI-specific errors
        error_str = str(exception).lower()
        if 'tlsv1_unrecognized_name' in error_str or 'sni' in error_str:
            error_parts.append("SNI (Server Name Indication) error detected")
            error_parts.append("   -> This often indicates proxy/antivirus interference")
            error_parts.append("   -> Try: Set REQUESTS_CA_BUNDLE to corporate CA or disable SSL verification (GOLD_PRICE_VERIFY_SSL=false)")
    
    # Connection error details
    elif isinstance(exception, requests.exceptions.ConnectionError):
        error_parts.append(f"Connection Error: {str(exception)[:300]}")
    
    # Timeout details
    elif isinstance(exception, requests.exceptions.Timeout):
        error_parts.append(f"Timeout: {str(exception)[:200]}")
    
    # General exception
    else:
        error_parts.append(f"Error: {str(exception)[:300]}")
    
    # Add request context
    error_parts.append(f"URL: {url}")
    
    # Add proxy info (hostnames only, check env vars)
    proxy_env_vars = {}
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        proxy_url = os.getenv(var)
        if proxy_url:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            if parsed.hostname:
                proxy_env_vars[var] = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 80}"
    
    if proxy_env_vars:
        error_parts.append(f"Proxy env vars: {proxy_env_vars}")
    
    # Also check session proxies
    proxies = _get_proxy_info()
    if proxies:
        error_parts.append(f"Session proxies: {proxies}")
    
    # Add SSL verification info
    verify_mode = "ENABLED"
    ca_bundle_info = ""
    
    if isinstance(session.verify, str):
        verify_mode = "CUSTOM_CA_BUNDLE"
        ca_bundle_info = f"CA bundle: {session.verify}"
        if not os.path.exists(session.verify):
            ca_bundle_info += " ⚠️  FILE NOT FOUND!"
    elif session.verify:
        verify_mode = "ENABLED"
        if _certifi_available:
            ca_bundle_path = certifi.where()
            ca_bundle_info = f"CA bundle: certifi ({ca_bundle_path})"
            if not os.path.exists(ca_bundle_path):
                ca_bundle_info += " ⚠️  FILE NOT FOUND!"
        else:
            ca_bundle_info = "CA bundle: system default"
    else:
        verify_mode = "DISABLED"
        ca_bundle_info = "SSL verification: DISABLED [INSECURE!]"
    
    error_parts.append(f"Verify mode: {verify_mode}")
    error_parts.append(ca_bundle_info)
    
    return "\n   ".join(error_parts)


# Global session instance (reused for efficiency)
_http_session: Optional[requests.Session] = None


def get_http_session() -> requests.Session:
    """Get or create global HTTP session"""
    global _http_session
    if _http_session is None:
        _http_session = create_http_session()
    return _http_session
