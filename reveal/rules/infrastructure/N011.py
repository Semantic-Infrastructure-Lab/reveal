"""N011: SSL listener missing http2.

'listen 443 ssl' without 'http2' on the same line disables HTTP/2 for the
site. Certbot's --nginx plugin consistently strips 'http2' when it rewrites
listen directives, making this a repeat pattern across Let's Encrypt sites.

HTTP/2 brings header compression, multiplexing, and server push — meaningful
latency wins for modern browsers. The fix is one word per listen directive.

Note: nginx 1.25.1+ uses a separate 'http2 on;' directive instead of
'listen 443 ssl http2'. This rule only fires on the inline form where http2
is absent from the listen line; standalone 'http2 on;' suppresses the finding.

Suppress per-server with: # reveal:allow-no-http2
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N011(BaseRule):
    """Detect SSL listener lines missing http2."""

    code = "N011"
    message = "SSL listener missing http2"
    category = RulePrefix.N
    severity = Severity.LOW
    file_patterns = NGINX_FILE_PATTERNS

    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    # Listen line that has 443 + ssl but NOT http2
    SSL_NO_HTTP2 = re.compile(
        r'^(\s*listen\s+(?:\[::\]:)?443\s+ssl(?!\s+http2)\b[^;]*;)',
        re.MULTILINE | re.IGNORECASE
    )
    # Modern form: 'http2 on;' as a standalone directive
    HTTP2_ON = re.compile(r'http2\s+on\s*;', re.IGNORECASE)
    SUPPRESS_PATTERN = re.compile(r'#\s*reveal:allow-no-http2')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        detections: List[Detection] = []

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            block = match.group(1)
            block_start = content[:match.start()].count('\n') + 1

            if self.SUPPRESS_PATTERN.search(block):
                continue

            # 'http2 on;' directive covers all listen lines in the block
            if self.HTTP2_ON.search(block):
                continue

            for listen_match in self.SSL_NO_HTTP2.finditer(block):
                listen_line = block_start + block[:listen_match.start()].count('\n')
                listen_text = listen_match.group(1).strip()
                fixed = listen_text.rstrip(';').rstrip() + ' http2;'
                server_name = self._extract_server_name(block)
                name_str = f"'{server_name}' " if server_name else ""

                detections.append(self.create_detection(
                    file_path=file_path,
                    line=listen_line,
                    message=f"{name_str}(line {listen_line}): SSL listener missing http2",
                    suggestion=(
                        f"{listen_text}  →  {fixed}\n"
                        "(Certbot strips http2 when it rewrites listen directives — re-add after certbot runs)"
                    ),
                    context=listen_text,
                ))

        return detections

    def _extract_server_name(self, block: str) -> Optional[str]:
        m = re.search(r'server_name\s+([^;]+);', block)
        if m:
            return m.group(1).strip().split()[0]
        return None
