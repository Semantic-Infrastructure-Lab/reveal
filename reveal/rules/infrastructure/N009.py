"""N009: server_tokens not disabled.

nginx defaults to advertising its version in Server response headers and error
pages (e.g. "Server: nginx/1.18.0"). This gives attackers a free vulnerability
shortlist for the exact version.

Two lines in nginx.conf http{} block fix all sites at once:
    server_tokens off;

Detection: a server block has no 'server_tokens off' AND the main nginx.conf
http{} block also lacks it. We check for 'server_tokens off' in the file
globally (since http{} and server{} directives are both present in the same
files we scan). Fires once per file that has a server block but no
server_tokens directive anywhere.

Suppress with: # reveal:allow-server-tokens
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N009(BaseRule):
    """Detect nginx configs where server_tokens is not disabled."""

    code = "N009"
    message = "server_tokens not disabled — nginx version exposed in headers"
    category = RulePrefix.N
    severity = Severity.MEDIUM
    file_patterns = NGINX_FILE_PATTERNS

    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    SERVER_TOKENS_OFF = re.compile(r'server_tokens\s+off\s*;', re.IGNORECASE)
    SUPPRESS_PATTERN = re.compile(r'#\s*reveal:allow-server-tokens')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        # Only check files that contain at least one server block
        if not self.SERVER_BLOCK_PATTERN.search(content):
            return []

        if self.SUPPRESS_PATTERN.search(content):
            return []

        # If server_tokens off appears anywhere in the file (http{} or server{}),
        # consider it covered
        if self.SERVER_TOKENS_OFF.search(content):
            return []

        # Fire once at line 1 — it's a file-level config gap, not per-server
        return [self.create_detection(
            file_path=file_path,
            line=1,
            message="server_tokens not disabled — nginx version exposed in Server header",
            suggestion="Add 'server_tokens off;' to the http{} block in nginx.conf",
            context="nginx.conf http { server_tokens off; }",
        )]
