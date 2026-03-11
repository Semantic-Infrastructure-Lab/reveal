"""N007: Nginx ssl_stapling enabled without a resolvable OCSP URL.

When ssl_stapling is on but the certificate has no OCSP responder URL
(Authority Information Access extension), nginx silently ignores stapling
and logs a warning:

    nginx: [warn] "ssl_stapling" ignored, no OCSP responder URL in the
    certificate "/etc/letsencrypt/live/example.org/fullchain.pem"

This is a silent performance degradation — TLS handshakes become slower
because clients must fetch OCSP responses directly instead of getting a
stapled response from nginx.

Common causes:
- Self-signed certificates (no OCSP infrastructure)
- Certain Let's Encrypt intermediate chains missing AIA extension
- Custom CA without OCSP service

Fix: either remove ssl_stapling or obtain a certificate with an OCSP URL.
"""

import re
import ssl
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N007(BaseRule):
    """Detect ssl_stapling directives on certs that lack an OCSP responder URL."""

    code = "N007"
    message = "ssl_stapling enabled but certificate has no OCSP responder URL"
    category = RulePrefix.N
    severity = Severity.LOW
    file_patterns = NGINX_FILE_PATTERNS

    # Match server blocks (handles one level of nesting for location blocks)
    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    SSL_STAPLING_ON = re.compile(r'ssl_stapling\s+on\s*;', re.IGNORECASE)
    SSL_CERT_PATTERN = re.compile(r'ssl_certificate\s+([^;]+);', re.IGNORECASE)

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for ssl_stapling on certs without OCSP URLs."""
        detections: List[Detection] = []

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            block = match.group(1)
            block_start = content[:match.start()].count('\n') + 1

            if not self.SSL_STAPLING_ON.search(block):
                continue

            cert_match = self.SSL_CERT_PATTERN.search(block)
            if not cert_match:
                continue

            cert_path = cert_match.group(1).strip()
            stapling_line = self._find_directive_line(block, block_start, 'ssl_stapling')

            ocsp_result = self._check_ocsp_url(cert_path)

            if ocsp_result == 'missing':
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=stapling_line,
                    message=f"ssl_stapling on, but '{cert_path}' has no OCSP responder URL",
                    suggestion="Remove ssl_stapling or replace with a cert that includes an AIA/OCSP URL.",
                    context=f"ssl_certificate {cert_path};"
                ))
            # 'present' → no issue; 'unreadable' → skip (cert may be on another host)

        return detections

    def _check_ocsp_url(self, cert_path: str) -> str:
        """Return 'present', 'missing', or 'unreadable'."""
        try:
            with open(cert_path, 'rb') as fh:
                cert_data = fh.read()
        except OSError:
            return 'unreadable'

        try:
            # Use ssl module to load the certificate
            cert = ssl.PEM_cert_to_DER_cert(cert_data.decode('ascii', errors='replace'))
            # Try cryptography library first (gives direct AIA access)
            try:
                from cryptography import x509
                loaded = x509.load_der_x509_certificate(cert)
                try:
                    aia = loaded.extensions.get_extension_for_class(
                        x509.AuthorityInformationAccess
                    )
                    has_ocsp = any(
                        isinstance(d.access_method, type(x509.AuthorityInformationAccessOID.OCSP))
                        or d.access_method == x509.AuthorityInformationAccessOID.OCSP
                        for d in aia.value
                    )
                    return 'present' if has_ocsp else 'missing'
                except x509.ExtensionNotFound:
                    return 'missing'
            except ImportError:
                # cryptography not available — fall back to string scan of DER
                # OCSP URIs in the AIA extension always start with "http"
                # The OID for id-ad-ocsp is 1.3.6.1.5.5.7.48.1
                # encoded as \x30\x25\x30\x23\x06\x08\x2b... but a string scan is reliable enough
                return 'present' if b'http' in cert and b'ocsp' in cert.lower() else 'missing'
        except Exception:
            return 'unreadable'

    def _find_directive_line(self, block: str, block_start: int, directive: str) -> int:
        """Return absolute line number of the first occurrence of a directive."""
        pattern = re.compile(rf'{re.escape(directive)}\s', re.IGNORECASE)
        m = pattern.search(block)
        if m:
            return block_start + block[:m.start()].count('\n')
        return block_start
