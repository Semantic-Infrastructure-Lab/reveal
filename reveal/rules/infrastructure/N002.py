"""N002: Nginx SSL server missing certificate configuration.

Detects SSL/TLS servers that lack required certificate directives.

Example of violation:
    server {
        listen 443 ssl;
        server_name example.com;
        # Missing ssl_certificate and ssl_certificate_key!
    }
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N002(BaseRule):
    """Detect SSL servers missing certificate configuration."""

    code = "N002"
    message = "SSL server block missing certificate configuration"
    category = RulePrefix.N
    severity = Severity.CRITICAL
    file_patterns = NGINX_FILE_PATTERNS

    # Match server blocks
    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        re.MULTILINE | re.DOTALL
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for SSL servers missing certificate directives."""
        detections: List[Dict[str, Any]] = []

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            server_body = match.group(1)
            server_start = content[:match.start()].count('\n') + 1

            # Check if this is an SSL server
            if not self._is_ssl_server(server_body):
                continue

            # Get server_name for better error messages
            server_name = self._get_server_name(server_body) or "unnamed"

            # Check for certificate directives
            has_cert = 'ssl_certificate ' in server_body or 'ssl_certificate\t' in server_body
            has_key = 'ssl_certificate_key ' in server_body or 'ssl_certificate_key\t' in server_body

            # Find the listen directive line for accurate reporting
            listen_line = self._find_listen_line(server_body, server_start)

            if not has_cert and not has_key:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=listen_line,
                    message=f"SSL server '{server_name}' missing both ssl_certificate and ssl_certificate_key",
                    suggestion="Add ssl_certificate and ssl_certificate_key directives",
                    context=f"server {{ listen ... ssl; server_name {server_name}; }}"
                ))
            elif not has_cert:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=listen_line,
                    message=f"SSL server '{server_name}' missing ssl_certificate",
                    suggestion="Add ssl_certificate directive pointing to your certificate file"
                ))
            elif not has_key:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=listen_line,
                    message=f"SSL server '{server_name}' missing ssl_certificate_key",
                    suggestion="Add ssl_certificate_key directive pointing to your private key file"
                ))

        return detections

    def _is_ssl_server(self, server_body: str) -> bool:
        """Check if server block has SSL enabled."""
        # Check for 'listen ... ssl' or 'listen 443'
        listen_pattern = re.compile(r'listen\s+[^;]*(?:ssl|443)[^;]*;', re.IGNORECASE)
        return bool(listen_pattern.search(server_body))

    def _get_server_name(self, server_body: str) -> Optional[str]:
        """Extract server_name from server block."""
        match = re.search(r'server_name\s+([^;]+);', server_body)
        if match:
            names = match.group(1).strip().split()
            return names[0] if names else None
        return None

    def _find_listen_line(self, server_body: str, server_start: int) -> int:
        """Find the line number of the listen directive."""
        match = re.search(r'listen\s+', server_body)
        if match:
            return server_start + server_body[:match.start()].count('\n')
        return server_start
