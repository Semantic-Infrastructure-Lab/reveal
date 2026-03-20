"""HTTP probe for redirect chain verification and live security header checks.

Used by ssl:// (--probe-http) and nginx:// (--probe) to verify live server
behavior: HTTP → HTTPS redirect presence, redirect chain, and security headers
at the final HTTPS endpoint.
"""

import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

_SECURITY_HEADERS = [
    ('Strict-Transport-Security', 'hsts'),
    ('X-Content-Type-Options', 'xcto'),
    ('X-Frame-Options', 'xfo'),
    ('Content-Security-Policy', 'csp'),
]

_MAX_REDIRECTS = 10
_DEFAULT_TIMEOUT = 10


def _build_opener():
    """Build a urllib opener that does NOT follow redirects."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            return None  # suppress redirect following

    return urllib.request.build_opener(_NoRedirect)


def probe_http_redirect(
    host: str,
    port: int = 80,
    timeout: int = _DEFAULT_TIMEOUT,
    _opener: Optional[Any] = None,
) -> Dict[str, Any]:
    """Follow the redirect chain from http://{host}:{port}/ and check security headers.

    Security headers are captured from the final non-redirect HTTPS response
    directly — no second request is made.

    Args:
        host: Hostname or IP to probe.
        port: TCP port to connect on (default 80).
        timeout: Socket timeout in seconds.
        _opener: Optional urllib opener override (for testing).

    Returns:
        Dict with keys:
          host, start_url, redirect_chain, final_url, redirects_to_https,
          hop_count, https_headers, error
    """

    opener = _opener if _opener is not None else _build_opener()
    start_url = f"http://{host}/" if port == 80 else f"http://{host}:{port}/"
    chain: List[Dict[str, Any]] = []
    url = start_url
    error: Optional[str] = None
    https_headers: Dict[str, Any] = {}

    for _ in range(_MAX_REDIRECTS):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'reveal-probe/1.0'})
            resp = opener.open(req, timeout=timeout)
            status = resp.getcode()
            chain.append({'url': url, 'status': status})
            # Capture security headers from the final HTTPS endpoint directly
            if url.startswith('https://'):
                for header_name, key in _SECURITY_HEADERS:
                    value = resp.headers.get(header_name)
                    https_headers[key] = value or None
            break
        except urllib.error.HTTPError as exc:
            status = exc.code
            chain.append({'url': url, 'status': status})
            if status in (301, 302, 303, 307, 308):
                location = exc.headers.get('Location', '')
                if not location:
                    break
                url = _resolve_location(url, location)
            else:
                break
        except urllib.error.URLError as exc:
            error = str(exc.reason)
            break
        except (socket.timeout, OSError) as exc:
            error = str(exc)
            break
    else:
        error = f"Too many redirects (>{_MAX_REDIRECTS})"

    final_url = chain[-1]['url'] if chain else url
    redirects_to_https = final_url.startswith('https://')

    return {
        'host': host,
        'start_url': start_url,
        'redirect_chain': chain,
        'final_url': final_url,
        'redirects_to_https': redirects_to_https,
        'hop_count': len(chain),
        'https_headers': https_headers,
        'error': error,
    }


def _resolve_location(base_url: str, location: str) -> str:
    """Resolve a Location header value against the base URL."""
    if location.startswith('http://') or location.startswith('https://'):
        return location
    parsed = urlparse(base_url)
    if location.startswith('/'):
        return f"{parsed.scheme}://{parsed.netloc}{location}"
    return f"{parsed.scheme}://{parsed.netloc}/{location}"



def render_probe_text(probe: Dict[str, Any]) -> None:
    """Print a human-readable HTTP probe summary."""
    host = probe.get('host', '')
    error = probe.get('error')
    chain = probe.get('redirect_chain', [])
    final_url = probe.get('final_url', '')
    redirects_to_https = probe.get('redirects_to_https', False)
    https_headers = probe.get('https_headers', {})

    print(f"HTTP Probe: {host}")

    if error and not chain:
        print(f"  ❌  Connection failed: {error}")
        return

    # Redirect chain
    parts = []
    for hop in chain:
        parts.append(f"{hop['url']} ({hop['status']})")
    if len(parts) > 1:
        chain_str = ' → '.join(parts)
        print(f"  Chain: {chain_str}")
    elif parts:
        print(f"  {parts[0]}")

    # HTTPS redirect verdict
    if redirects_to_https:
        print(f"  ✅  Redirects to HTTPS  ({final_url})")
    else:
        print(f"  ❌  Does NOT redirect to HTTPS  (final: {final_url})")

    # Security headers (only when HTTPS was reached)
    if https_headers:
        print()
        print("  Security headers at HTTPS endpoint:")
        _HEADER_LABELS = {
            'hsts': 'Strict-Transport-Security',
            'xcto': 'X-Content-Type-Options',
            'xfo': 'X-Frame-Options',
            'csp': 'Content-Security-Policy',
        }
        for key, label in _HEADER_LABELS.items():
            value = https_headers.get(key)
            icon = '✅' if value else '—'
            if value:
                display = value[:60] + ('…' if len(value) > 60 else '')
                print(f"  {icon}  {label}: {display}")
            else:
                print(f"  {icon}  {label}: missing")
