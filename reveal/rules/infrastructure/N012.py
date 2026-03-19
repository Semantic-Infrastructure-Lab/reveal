"""N012: No rate limiting on server block.

Without limit_req, server blocks are open to flood attacks and credential
stuffing at full connection speed.

Two-level detection:
- MEDIUM: no limit_req_zone defined anywhere in the file — rate limiting is
  completely absent from this config.
- LOW: limit_req_zone is defined but this server block uses no limit_req
  directive at server or location level.

Suppress per-server with: # reveal:allow-no-rate-limit
"""

import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N012(BaseRule):
    """Detect server blocks with no rate limiting applied."""

    code = "N012"
    message = "No rate limiting applied to server block"
    category = RulePrefix.N
    severity = Severity.LOW
    file_patterns = NGINX_FILE_PATTERNS

    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    LIMIT_REQ_ZONE = re.compile(r'limit_req_zone\s+', re.IGNORECASE)
    LIMIT_REQ = re.compile(r'limit_req\s+', re.IGNORECASE)
    SUPPRESS_PATTERN = re.compile(r'#\s*reveal:allow-no-rate-limit')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        detections: List[Detection] = []

        has_zone = bool(self.LIMIT_REQ_ZONE.search(content))

        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            block = match.group(1)
            block_start = content[:match.start()].count('\n') + 1

            if self.SUPPRESS_PATTERN.search(block):
                continue

            if self.LIMIT_REQ.search(block):
                continue

            server_name = self._extract_server_name(block)
            name_str = f"'{server_name}'" if server_name else "server block"

            if not has_zone:
                # No rate limiting infrastructure at all — escalate to MEDIUM
                detection = self.create_detection(
                    file_path=file_path,
                    line=block_start,
                    message=f"{name_str}: no rate limiting configured (no limit_req_zone defined)",
                    suggestion=(
                        "Add to http{}: limit_req_zone $binary_remote_addr zone=default:10m rate=10r/s;\n"
                        "Add to server{}: limit_req zone=default burst=20 nodelay;"
                    ),
                    context="no limit_req_zone or limit_req",
                    severity=Severity.MEDIUM,
                )
            else:
                detection = self.create_detection(
                    file_path=file_path,
                    line=block_start,
                    message=f"{name_str}: limit_req_zone is configured but not applied to this server block",
                    suggestion="Add 'limit_req zone=<your_zone> burst=20 nodelay;' to the server or location block",
                    context="limit_req_zone defined but no limit_req in server block",
                )

            detections.append(detection)

        return detections

    def _extract_server_name(self, block: str) -> Optional[str]:
        m = re.search(r'server_name\s+([^;]+);', block)
        if m:
            return m.group(1).strip().split()[0]
        return None
