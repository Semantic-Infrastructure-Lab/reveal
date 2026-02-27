"""N005: Nginx dangerous timeout configuration detection.

Flags http{} timeout and buffer directives that are outside safe operational
ranges.  Extreme values cause either silent data loss (timeouts too short) or
resource exhaustion / denial-of-service exposure (timeouts too long or buffers
too large).

Examples of violations:

    http {
        send_timeout 3s;          # N005 – below minimum of 10s
        proxy_read_timeout 600s;  # N005 – above maximum of 300s
        client_body_buffer_size 512m;  # N005 – above maximum of 64m
    }

Real-world context:
    Developed from Issue #21: reveal showed empty output for main nginx.conf
    files that contained only http{} directives with no server{} blocks.
    The --check bonus surfaces misconfigurations in those global timeout
    settings that are otherwise invisible to tooling focused on virtual hosts.
"""

import re
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


def _parse_duration_seconds(value: str) -> Optional[float]:
    """Convert nginx duration string to seconds.

    Handles: plain integers (ms implied by nginx? No – bare integers are
    seconds in nginx timeout directives), s/m/h suffixes, and ms suffix.

    Returns None if the value cannot be parsed as a duration.
    """
    value = value.strip().lower()
    match = re.match(r'^(\d+(?:\.\d+)?)(ms|s|m|h)?$', value)
    if not match:
        return None
    num = float(match.group(1))
    unit = match.group(2) or 's'
    multipliers = {'ms': 0.001, 's': 1.0, 'm': 60.0, 'h': 3600.0}
    return num * multipliers[unit]


def _parse_size_mb(value: str) -> Optional[float]:
    """Convert nginx size string to megabytes.

    Handles: k/K (kilobytes), m/M (megabytes), g/G (gigabytes),
    bare integers (bytes).

    Returns None if the value cannot be parsed as a size.
    """
    value = value.strip().lower()
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([kmg]?)$', value)
    if not match:
        return None
    num = float(match.group(1))
    unit = match.group(2)
    multipliers = {'': 1 / (1024 * 1024), 'k': 1 / 1024, 'm': 1.0, 'g': 1024.0}
    return num * multipliers.get(unit, 1 / (1024 * 1024))


# Directive thresholds: (min_seconds, max_seconds, description)
# None means no bound on that side.
_TIMEOUT_THRESHOLDS: Dict[str, Tuple[Optional[float], Optional[float], str]] = {
    'send_timeout':           (10.0, 300.0, 'send timeout'),
    'proxy_read_timeout':     (10.0, 300.0, 'proxy read timeout'),
    'proxy_send_timeout':     (10.0, 300.0, 'proxy send timeout'),
    'proxy_connect_timeout':  (2.0,  75.0,  'proxy connect timeout'),
    'keepalive_timeout':      (5.0,  120.0, 'keepalive timeout'),
    'client_body_timeout':    (5.0,  120.0, 'client body timeout'),
    'client_header_timeout':  (5.0,  120.0, 'client header timeout'),
}

# Size directive thresholds: (min_mb, max_mb, description)
_SIZE_THRESHOLDS: Dict[str, Tuple[Optional[float], Optional[float], str]] = {
    'client_body_buffer_size':   (None, 64.0,  'client body buffer size'),
    'client_max_body_size':      (None, 2048.0, 'client max body size'),
    'proxy_buffers':             (None, None,   None),  # complex – handled separately
    'proxy_buffer_size':         (None, 32.0,   'proxy buffer size'),
    'large_client_header_buffers': (None, None, None),  # complex – handled separately
}

# Simple size directives (single value, not "count size" format)
_SIMPLE_SIZE_DIRECTIVES = {k for k, v in _SIZE_THRESHOLDS.items() if v[2] is not None}


class N005(BaseRule):
    """Detect nginx timeout and buffer directives outside safe operational ranges."""

    code = "N005"
    message = "Nginx directive value outside safe operational range"
    category = RulePrefix.N
    severity = Severity.MEDIUM
    file_patterns = NGINX_FILE_PATTERNS

    # Match the http{} block (non-greedy, single-level only)
    _HTTP_BLOCK_RE = re.compile(
        r'\bhttp\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        re.MULTILINE | re.DOTALL,
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for dangerous timeout and buffer values in http{} block."""
        detections: List[Detection] = []

        directives = (structure or {}).get('directives')
        if not directives:
            # Fall back to regex extraction when structure is unavailable
            directives = self._extract_http_directives_from_content(content)
        if not directives:
            return detections

        for name, value in directives.items():
            detection = self._check_timeout(file_path, content, name, value)
            if detection:
                detections.append(detection)
                continue
            detection = self._check_size(file_path, content, name, value)
            if detection:
                detections.append(detection)

        return detections

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_http_directives_from_content(self, content: str) -> Dict[str, str]:
        """Extract top-level http{} directives from raw content (fallback)."""
        directives: Dict[str, str] = {}
        match = self._HTTP_BLOCK_RE.search(content)
        if not match:
            return directives
        body = match.group(1)
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '{' in stripped:
                continue
            m = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
            if m:
                directives[m.group(1)] = m.group(2)
        return directives

    def _find_directive_line(self, content: str, directive: str) -> int:
        """Find the line number of a directive inside http{}."""
        for i, line in enumerate(content.splitlines(), 1):
            if re.match(r'\s*' + re.escape(directive) + r'\s+', line):
                return i
        return 1

    def _check_timeout(self, file_path: str, content: str,
                       name: str, value: str) -> Optional[Detection]:
        """Return a Detection if the timeout value is outside safe bounds."""
        if name not in _TIMEOUT_THRESHOLDS:
            return None
        min_s, max_s, desc = _TIMEOUT_THRESHOLDS[name]
        seconds = _parse_duration_seconds(value)
        if seconds is None:
            return None

        if min_s is not None and seconds < min_s:
            line = self._find_directive_line(content, name)
            return self.create_detection(
                file_path=file_path,
                line=line,
                message=f"{desc} '{value}' is below the minimum recommended value of {int(min_s)}s",
                suggestion=f"Set {name} to at least {int(min_s)}s to avoid premature connection drops",
            )
        if max_s is not None and seconds > max_s:
            line = self._find_directive_line(content, name)
            return self.create_detection(
                file_path=file_path,
                line=line,
                message=f"{desc} '{value}' exceeds the maximum recommended value of {int(max_s)}s",
                suggestion=f"Set {name} to at most {int(max_s)}s to limit resource exhaustion risk",
            )
        return None

    def _check_size(self, file_path: str, content: str,
                    name: str, value: str) -> Optional[Detection]:
        """Return a Detection if the size value is outside safe bounds."""
        if name not in _SIMPLE_SIZE_DIRECTIVES:
            return None
        _, max_mb, desc = _SIZE_THRESHOLDS[name]
        mb = _parse_size_mb(value)
        if mb is None:
            return None

        if max_mb is not None and mb > max_mb:
            line = self._find_directive_line(content, name)
            return self.create_detection(
                file_path=file_path,
                line=line,
                message=f"{desc} '{value}' exceeds the maximum recommended value of {int(max_mb)}m",
                suggestion=f"Set {name} to at most {int(max_mb)}m to avoid memory pressure",
            )
        return None
