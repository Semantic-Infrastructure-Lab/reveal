"""N001: Nginx duplicate backend detection.

Detects when multiple upstreams point to the same backend server:port.
This is a common misconfiguration that can cause traffic routing issues.

Example of violation:
    upstream app1 {
        server 127.0.0.1:8000;
    }
    upstream app2 {
        server 127.0.0.1:8000;  # Same as app1!
    }
"""

import re
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N001(BaseRule):
    """Detect duplicate backend servers across nginx upstreams."""

    code = "N001"
    message = "Multiple upstreams point to the same backend server"
    category = RulePrefix.N
    severity = Severity.HIGH
    file_patterns = NGINX_FILE_PATTERNS

    # Regex to match upstream blocks and their servers
    UPSTREAM_PATTERN = re.compile(
        r'upstream\s+(\w+)\s*\{([^}]+)\}',
        re.MULTILINE | re.DOTALL
    )
    SERVER_PATTERN = re.compile(
        r'server\s+([^;]+);'
    )

    _INTENT_WORDS = re.compile(r'intentional|by design|same host', re.IGNORECASE)

    def _has_intent_comment(self, content: str, upstream_start_line: int) -> bool:
        """Return True if the 3 lines before upstream_start_line contain an intent comment."""
        lines = content.splitlines()
        check_from = max(0, upstream_start_line - 4)
        check_to = upstream_start_line - 1
        for line in lines[check_from:check_to]:
            stripped = line.lstrip()
            if stripped.startswith('#') and self._INTENT_WORDS.search(stripped):
                return True
        return False

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for duplicate backend servers across upstreams."""
        detections: List[Detection] = []

        # Parse all upstreams and their servers
        backend_to_upstreams: Dict[str, List[tuple]] = defaultdict(list)

        for match in self.UPSTREAM_PATTERN.finditer(content):
            upstream_name = match.group(1)
            upstream_body = match.group(2)
            upstream_start = content[:match.start()].count('\n') + 1

            # Skip upstreams explicitly marked as intentionally sharing a backend
            if 'reveal:allow-shared-backend' in upstream_body:
                continue

            # Find all server directives in this upstream
            for server_match in self.SERVER_PATTERN.finditer(upstream_body):
                server_spec = server_match.group(1).strip()
                # Normalize: remove weight, backup, etc. - just get host:port
                backend = self._normalize_server(server_spec)
                if backend:
                    server_line = upstream_start + upstream_body[:server_match.start()].count('\n')
                    backend_to_upstreams[backend].append((upstream_name, server_line, upstream_start))

        # Find duplicates
        for backend, upstreams in backend_to_upstreams.items():
            if len(upstreams) > 1:
                first_upstream = upstreams[0][0]
                for upstream_name, line, upstream_start in upstreams[1:]:
                    suggestion = (
                        "Verify this is intentional. If so, add"
                        " '# reveal:allow-shared-backend' inside the upstream block to suppress."
                    )
                    if self._has_intent_comment(content, upstream_start):
                        suggestion += (
                            " (A nearby comment signals intent — if confirmed,"
                            " add the suppression marker to formally acknowledge it.)"
                        )
                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=line,
                        message=f"Upstream '{upstream_name}' shares backend {backend} with '{first_upstream}'",
                        suggestion=suggestion,
                        context=f"Both '{first_upstream}' and '{upstream_name}' → {backend}"
                    ))

        return detections

    def _normalize_server(self, server_spec: str) -> Optional[str]:
        """Extract host:port from server directive, ignoring options."""
        # Remove common options: weight=N, backup, down, max_fails=N, etc.
        parts = server_spec.split()
        if not parts:
            return None

        host_port = parts[0]

        # Handle unix sockets
        if host_port.startswith('unix:'):
            return host_port

        # Ensure we have a port (default to 80 if not specified)
        if ':' not in host_port:
            host_port = f"{host_port}:80"

        return host_port
