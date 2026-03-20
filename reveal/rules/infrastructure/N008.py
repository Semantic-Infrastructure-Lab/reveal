"""N008: HTTPS server block missing Strict-Transport-Security header.

A server block listening on port 443 with no Strict-Transport-Security (HSTS)
header means browsers never learn to pin this site to HTTPS. An intercepted
first HTTP request can strip TLS for the entire session (SSL stripping).

Detection checks (in priority order):
1. The global nginx.conf http{} block and its one-level-deep includes.
2. The server block itself and any resolved includes one level deep.

If HSTS is set globally (http{} level), all vhosts are covered — no per-site
detections are emitted.

Suppress per-server with: # reveal:allow-no-hsts
Fix: add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
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


class N008(BaseRule):
    """Detect HTTPS server blocks without a Strict-Transport-Security header."""

    code = "N008"
    message = "HTTPS site missing Strict-Transport-Security header"
    category = RulePrefix.N
    severity = Severity.HIGH
    file_patterns = NGINX_FILE_PATTERNS

    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    SSL_LISTEN_PATTERN = re.compile(
        r'listen\s+(?:\[::\]:)?443\b', re.IGNORECASE
    )
    HSTS_PATTERN = re.compile(
        r'add_header\s+Strict-Transport-Security\b', re.IGNORECASE
    )
    SUPPRESS_PATTERN = re.compile(r'#\s*reveal:allow-no-hsts')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        detections: List[Detection] = []

        # If HSTS is set globally in nginx.conf http{}, all vhosts are covered.
        if self._has_global_hsts(file_path):
            return detections

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            block = match.group(1)
            block_start = content[:match.start()].count('\n') + 1

            if not self.SSL_LISTEN_PATTERN.search(block):
                continue

            if self.SUPPRESS_PATTERN.search(block):
                continue

            if self._has_hsts(block, file_path):
                continue

            listen_line = self._find_directive_line(block, block_start, 'listen')
            server_name = self._extract_server_name(block)
            name_str = f"'{server_name}'" if server_name else 'server block'

            detections.append(self.create_detection(
                file_path=file_path,
                line=listen_line,
                message=f"{name_str} (line {listen_line}): HTTPS site missing Strict-Transport-Security header",
                suggestion=(
                    'add_header Strict-Transport-Security '
                    '"max-age=31536000; includeSubDomains" always;'
                ),
                context=f"listen 443 ssl  (no Strict-Transport-Security)",
            ))

        return detections

    def _has_global_hsts(self, file_path: str) -> bool:
        """Return True if HSTS is set in the global nginx.conf http{} block.

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
            if self.HSTS_PATTERN.search(http_block):
                return True
            for inc_match in NGINX_INCLUDE_PATTERN.finditer(http_block):
                resolved = nginx_resolve_include(inc_match.group(1).strip(), nginx_conf)
                if resolved is None:
                    continue  # can't verify — don't suppress on uncertainty
                try:
                    with open(resolved) as fh:
                        if self.HSTS_PATTERN.search(fh.read()):
                            return True
                except OSError:
                    pass
        return False

    def _has_hsts(self, block: str, file_path: str) -> bool:
        """Return True if HSTS header is set in block or any included snippet."""
        if self.HSTS_PATTERN.search(block):
            return True
        for inc_match in NGINX_INCLUDE_PATTERN.finditer(block):
            resolved = nginx_resolve_include(inc_match.group(1).strip(), file_path)
            if resolved is None:
                return True  # can't verify — suppress rather than false-positive
            try:
                with open(resolved) as fh:
                    if self.HSTS_PATTERN.search(fh.read()):
                        return True
            except OSError:
                return True  # unreadable — suppress
        return False

    def _find_directive_line(self, block: str, block_start: int, directive: str) -> int:
        m = re.search(rf'{re.escape(directive)}\s', block, re.IGNORECASE)
        if m:
            return block_start + block[:m.start()].count('\n')
        return block_start

    def _extract_server_name(self, block: str) -> Optional[str]:
        m = re.search(r'server_name\s+([^;]+);', block)
        if m:
            return m.group(1).strip().split()[0]
        return None
