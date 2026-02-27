"""N006: Nginx send_timeout too low relative to client_max_body_size.

When a server is configured to accept large uploads (client_max_body_size)
but the send_timeout or proxy_read_timeout is too short, large transfers
will be silently killed mid-flight by nginx.  The client sees a connection
reset, the application logs nothing, and the upload is lost.

The dangerous combination is any of:
  - send_timeout < 60s   AND client_max_body_size > 10m
  - proxy_read_timeout < 60s AND client_max_body_size > 10m

Real-world incident (Sociamonials, Feb 2026):
    send_timeout 30s + client_max_body_size 200m caused silent media upload
    failures.  Raising send_timeout to 300s resolved the issue.

Note: this rule checks both http{} directives and top-level (main context)
directives, since the two values are often split across nginx.conf and a
vhost include file.
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS

# Minimum timeout that is safe when large bodies are allowed (seconds).
_MIN_SAFE_TIMEOUT_S = 60.0

# Minimum body size that triggers timeout scrutiny (megabytes).
# Below 10 MB the risk is very low even with short timeouts.
_LARGE_BODY_THRESHOLD_MB = 10.0

# Directives that control how long nginx waits to *send* data to the client
# or read a response from the backend.  Any of these being too short is risky.
_TIMEOUT_DIRECTIVES = ('send_timeout', 'proxy_read_timeout', 'proxy_send_timeout')

# Size directives that define the maximum allowed request body.
_SIZE_DIRECTIVE = 'client_max_body_size'


def _parse_seconds(value: str) -> Optional[float]:
    """Convert nginx duration string to seconds.  Returns None if unparseable."""
    value = value.strip().lower()
    m = re.match(r'^(\d+(?:\.\d+)?)(ms|s|m|h)?$', value)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or 's'
    return num * {'ms': 0.001, 's': 1.0, 'm': 60.0, 'h': 3600.0}[unit]


def _parse_mb(value: str) -> Optional[float]:
    """Convert nginx size string to megabytes.  Returns None if unparseable."""
    value = value.strip().lower()
    # nginx treats '0' as unlimited
    if value in ('0', '0m', '0g'):
        return None
    m = re.match(r'^(\d+(?:\.\d+)?)\s*([kmg]?)$', value)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    return num * {'': 1 / (1024 * 1024), 'k': 1 / 1024, 'm': 1.0, 'g': 1024.0}.get(unit, 1 / (1024 * 1024))


def _extract_directives(content: str) -> Dict[str, str]:
    """Extract relevant directives from anywhere in the file.

    Looks inside http{} blocks and at the top level (main context) so the
    rule fires regardless of which file in an nginx setup holds each value.
    """
    directives: Dict[str, str] = {}
    interesting = set(_TIMEOUT_DIRECTIVES) | {_SIZE_DIRECTIVE}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        m = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
        if m and m.group(1) in interesting and m.group(1) not in directives:
            directives[m.group(1)] = m.group(2)
    return directives


class N006(BaseRule):
    """Detect dangerous combination of short timeout + large max body size."""

    code = "N006"
    message = "Timeout too short for configured max body size — large transfers will be silently killed"
    category = RulePrefix.N
    severity = Severity.HIGH
    file_patterns = NGINX_FILE_PATTERNS

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        """Flag mismatched timeout/body-size combinations."""
        detections: List[Detection] = []

        # Pull all relevant directives from the file content.
        directives = _extract_directives(content)

        # Also pull from parsed structure when available (main_directives or
        # the http-level directives dict).
        if structure:
            for key in ('main_directives', 'directives'):
                extra = structure.get(key) or {}
                for name, value in extra.items():
                    if name not in directives:
                        directives[name] = value

        body_size_raw = directives.get(_SIZE_DIRECTIVE)
        if not body_size_raw:
            return detections

        body_mb = _parse_mb(body_size_raw)
        if body_mb is None or body_mb <= _LARGE_BODY_THRESHOLD_MB:
            return detections

        for timeout_name in _TIMEOUT_DIRECTIVES:
            timeout_raw = directives.get(timeout_name)
            if not timeout_raw:
                continue
            timeout_s = _parse_seconds(timeout_raw)
            if timeout_s is None or timeout_s >= _MIN_SAFE_TIMEOUT_S:
                continue

            line = self._find_directive_line(content, timeout_name)
            detections.append(self.create_detection(
                file_path=file_path,
                line=line,
                message=(
                    f"{timeout_name} {timeout_raw} is too short for "
                    f"client_max_body_size {body_size_raw} — "
                    f"transfers larger than ~{self._estimate_max_mb(timeout_s):.0f} MB will time out silently"
                ),
                suggestion=(
                    f"Raise {timeout_name} to at least {int(_MIN_SAFE_TIMEOUT_S)}s, "
                    f"or to match your largest expected transfer time (e.g. 300s for 200 MB on slow links)"
                ),
                context=(
                    f"{timeout_name} {timeout_raw}  +  {_SIZE_DIRECTIVE} {body_size_raw}"
                ),
            ))

        return detections

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_directive_line(content: str, directive: str) -> int:
        """Return the 1-based line number of the first occurrence of a directive."""
        for i, line in enumerate(content.splitlines(), 1):
            if re.match(r'\s*' + re.escape(directive) + r'\s+', line):
                return i
        return 1

    @staticmethod
    def _estimate_max_mb(timeout_s: float, bandwidth_mbps: float = 10.0) -> float:
        """Rough estimate: how many MB can transfer before timeout at bandwidth_mbps."""
        # Default 10 Mbit/s ≈ 1.25 MB/s — conservative for internet uplinks.
        return timeout_s * (bandwidth_mbps / 8)
