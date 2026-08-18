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
from . import (
    NGINX_FILE_PATTERNS,
    NGINX_INCLUDE_PATTERN,
    nginx_extract_http_blocks,
    nginx_find_nginx_conf,
    nginx_resolve_include,
    nginx_strip_comments,
)


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
    CERT_PATTERN = re.compile(r'ssl_certificate\s', re.IGNORECASE)
    KEY_PATTERN = re.compile(r'ssl_certificate_key\s', re.IGNORECASE)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for SSL servers missing certificate directives."""
        detections: List[Detection] = []
        content = nginx_strip_comments(content)

        # A cert set globally (http{} level, e.g. a shared ssl-params.conf
        # included once) covers every vhost that doesn't override it
        # (BACK-1103).
        global_has_cert = self._has_global_directive(content, file_path, self.CERT_PATTERN)
        global_has_key = self._has_global_directive(content, file_path, self.KEY_PATTERN)

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            server_body = match.group(1)
            server_start = content[:match.start()].count('\n') + 1

            # Check if this is an SSL server
            if not self._is_ssl_server(server_body):
                continue

            # Get server_name for better error messages
            server_name = self._get_server_name(server_body) or "unnamed"

            # Check for certificate directives -- inline, via an include
            # resolved from this block, or inherited from http{} level.
            has_cert = global_has_cert or self._has_directive(server_body, file_path, self.CERT_PATTERN)
            has_key = global_has_key or self._has_directive(server_body, file_path, self.KEY_PATTERN)

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

    def _has_directive(self, block: str, file_path: str, pattern: re.Pattern) -> bool:
        """Return True if `pattern` matches in `block` or any include it resolves.

        Mirrors N008's `_has_hsts` — when an include can't be resolved or
        read, treat it as possibly-satisfying (suppress rather than
        false-positive on an unreadable/relative-to-elsewhere path).
        """
        if pattern.search(block):
            return True
        for inc_match in NGINX_INCLUDE_PATTERN.finditer(block):
            resolved = nginx_resolve_include(inc_match.group(1).strip(), file_path)
            if resolved is None:
                return True  # can't verify — suppress rather than false-positive
            try:
                with open(resolved) as fh:
                    if pattern.search(nginx_strip_comments(fh.read())):
                        return True
            except OSError:
                return True  # unreadable — suppress
        return False

    def _http_blocks_have_directive(self, source: str, base_path: str, pattern: re.Pattern) -> bool:
        """Return True if `pattern` matches any http{} block in `source`, or
        an include resolved from one (relative to `base_path`)."""
        for http_block in nginx_extract_http_blocks(source):
            if pattern.search(http_block):
                return True
            for inc_match in NGINX_INCLUDE_PATTERN.finditer(http_block):
                resolved = nginx_resolve_include(inc_match.group(1).strip(), base_path)
                if resolved is None:
                    continue  # can't verify — don't assume a global setting exists
                try:
                    with open(resolved) as fh:
                        if pattern.search(nginx_strip_comments(fh.read())):
                            return True
                except OSError:
                    pass
        return False

    def _has_global_directive(self, content: str, file_path: str, pattern: re.Pattern) -> bool:
        """Return True if `pattern` is set at http{} level -- either this
        file's own http{} block (a single-file config, common in the
        `include ssl-common.conf; server { ... }` idiom -- BACK-1103) or a
        separately discovered nginx.conf's http{} block and its includes
        (mirrors N008's `_has_global_hsts`). When neither source has the
        directive or nginx.conf can't be found/read, returns False (no
        suppression) rather than assuming a global setting exists.
        """
        if self._http_blocks_have_directive(content, file_path, pattern):
            return True
        nginx_conf = nginx_find_nginx_conf(file_path)
        if nginx_conf is None:
            return False
        try:
            with open(nginx_conf) as fh:
                conf_content = nginx_strip_comments(fh.read())
        except OSError:
            return False
        return self._http_blocks_have_directive(conf_content, nginx_conf, pattern)

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
