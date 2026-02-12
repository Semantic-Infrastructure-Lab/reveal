"""N004: Nginx ACME challenge path inconsistency detection.

Detects when multiple server blocks have different root paths for ACME challenge
locations. This can cause Let's Encrypt certificate renewal failures when some
domains point to different webroot directories.

Example of violation:
    server {
        server_name domain-a.com;
        location /.well-known/acme-challenge/ {
            root /home/user1/public_html;  # Path A
        }
    }
    server {
        server_name domain-b.com;
        location /.well-known/acme-challenge/ {
            root /home/user2/public_html;  # Path B - inconsistent!
        }
    }

Real-world context:
    This rule was developed to catch SSL renewal failures where nginx configs
    point ACME challenges to different directories than where validation files
    are written (e.g., by cPanel AutoSSL). When all domains should use the same
    webroot but some have diverged, this rule flags the inconsistency.
"""

import re
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N004(BaseRule):
    """Detect inconsistent ACME challenge root paths across server blocks."""

    code = "N004"
    message = "Inconsistent ACME challenge root paths detected"
    category = RulePrefix.N
    severity = Severity.HIGH
    file_patterns = NGINX_FILE_PATTERNS

    # Match server blocks
    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        re.MULTILINE | re.DOTALL
    )

    # Match acme-challenge location blocks
    ACME_LOCATION_PATTERN = re.compile(
        r'location\s+[~=]*\s*/?\.well-known/acme-challenge[/\s]*\{([^{}]*)\}',
        re.IGNORECASE
    )

    # Match root directive
    ROOT_PATTERN = re.compile(r'root\s+([^;]+);')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for inconsistent ACME challenge paths."""
        detections: List[Detection] = []

        # Collect all ACME challenge configs: path -> [(server_name, line)]
        acme_paths: Dict[str, List[tuple]] = defaultdict(list)
        servers_with_ssl_no_acme = []

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            server_body = match.group(1)
            server_start = content[:match.start()].count('\n') + 1

            # Get server_name for context
            server_name = self._get_server_name(server_body) or "unnamed"

            # Check if this is an SSL server
            is_ssl = self._is_ssl_server(server_body)

            # Find ACME challenge location
            acme_match = self.ACME_LOCATION_PATTERN.search(server_body)
            if acme_match:
                acme_body = acme_match.group(1)
                acme_line = server_start + server_body[:acme_match.start()].count('\n')

                # Find root directive
                root_match = self.ROOT_PATTERN.search(acme_body)
                if root_match:
                    root_path = root_match.group(1).strip()
                    acme_paths[root_path].append((server_name, acme_line))
            elif is_ssl:
                # SSL server without ACME challenge location
                listen_line = self._find_listen_line(server_body, server_start)
                servers_with_ssl_no_acme.append((server_name, listen_line))

        # Report inconsistent paths (more than one unique root path)
        if len(acme_paths) > 1:
            # Find the most common path (likely the "correct" one)
            path_counts = [(path, len(servers)) for path, servers in acme_paths.items()]
            path_counts.sort(key=lambda x: x[1], reverse=True)
            common_path, common_count = path_counts[0]

            # Report each divergent path
            for root_path, servers in acme_paths.items():
                if root_path != common_path:
                    # Get first server as example
                    example_server, line = servers[0]
                    server_count = len(servers)

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=line,
                        message=f"ACME challenge root '{root_path}' differs from common path '{common_path}' ({server_count} server(s) affected)",
                        suggestion=f"Verify this path is intentional. Most servers ({common_count}) use '{common_path}'",
                        context=f"Affected: {', '.join(s[0] for s in servers[:3])}" + (f" (+{server_count - 3} more)" if server_count > 3 else "")
                    ))

        # Optionally report SSL servers without ACME (info level, disabled by default)
        # This is often intentional (using DNS validation, or certs managed elsewhere)
        # Uncomment if you want this check:
        # for server_name, line in servers_with_ssl_no_acme[:5]:
        #     detections.append(self.create_detection(
        #         file_path=file_path,
        #         line=line,
        #         message=f"SSL server '{server_name}' has no ACME challenge location",
        #         suggestion="Verify SSL certificate renewal method (webroot, DNS, or external)",
        #         severity=Severity.INFO
        #     ))

        return detections

    def _is_ssl_server(self, server_body: str) -> bool:
        """Check if server block has SSL enabled."""
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
