"""N009: server_tokens not disabled.

nginx defaults to advertising its version in Server response headers and error
pages (e.g. "Server: nginx/1.18.0"). This gives attackers a free vulnerability
shortlist for the exact version.

Two lines in nginx.conf http{} block fix all sites at once:
    server_tokens off;

Detection: a file contains a server block, AND server_tokens is absent both in
the file itself AND in the global nginx.conf http{} block (and its includes).
Fires once per file — it's a config gap, not a per-server issue.

Suppress with: # reveal:allow-server-tokens
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import (
    NGINX_FILE_PATTERNS,
    NGINX_HTTP_BLOCK_PATTERN,
    NGINX_INCLUDE_PATTERN,
    nginx_find_nginx_conf,
    nginx_resolve_include,
)


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

        # Also check the global nginx.conf http{} block — a global setting covers
        # all vhosts and should not trigger per-vhost detections.
        if self._has_global_server_tokens(file_path):
            return []

        # Fire once at line 1 — it's a file-level config gap, not per-server
        return [self.create_detection(
            file_path=file_path,
            line=1,
            message="server_tokens not disabled — nginx version exposed in Server header",
            suggestion="Add 'server_tokens off;' to the http{} block in nginx.conf",
            context="nginx.conf http { server_tokens off; }",
        )]

    def _has_global_server_tokens(self, file_path: str) -> bool:
        """Return True if server_tokens off is set in the global nginx.conf http{} block.

        Checks the http{} block and one level of includes from it.  When nginx.conf
        cannot be found or read, returns False (no suppression).
        """
        nginx_conf = nginx_find_nginx_conf(file_path)
        if nginx_conf is None:
            return False
        try:
            with open(nginx_conf) as fh:
                conf_content = fh.read()
        except OSError:
            return False
        for match in NGINX_HTTP_BLOCK_PATTERN.finditer(conf_content):
            http_block = match.group(1)
            if self.SERVER_TOKENS_OFF.search(http_block):
                return True
            for inc_match in NGINX_INCLUDE_PATTERN.finditer(http_block):
                resolved = nginx_resolve_include(inc_match.group(1).strip(), nginx_conf)
                if resolved is None:
                    continue
                try:
                    with open(resolved) as fh:
                        if self.SERVER_TOKENS_OFF.search(fh.read()):
                            return True
                except OSError:
                    pass
        return False
