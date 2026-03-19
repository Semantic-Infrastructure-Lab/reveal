"""N010: Deprecated X-XSS-Protection header present.

X-XSS-Protection was removed from the W3C spec and is ignored by Chrome since
2019 and Firefox since 2023. Its presence signals an outdated config and can
actually introduce vulnerabilities in older IE/Edge versions.

The modern replacement is Content-Security-Policy.

When the header comes from a shared snippet, the snippet file path is surfaced
so the fix is obvious — editing one snippet fixes all affected sites.

Suppress with: # reveal:allow-xss-protection
"""

import os
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N010(BaseRule):
    """Detect deprecated X-XSS-Protection header in nginx configs."""

    code = "N010"
    message = "Deprecated X-XSS-Protection header present"
    category = RulePrefix.N
    severity = Severity.LOW
    file_patterns = NGINX_FILE_PATTERNS

    SERVER_BLOCK_PATTERN = re.compile(
        r'server\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
        re.MULTILINE | re.DOTALL
    )
    XSS_PROTECTION_PATTERN = re.compile(
        r'add_header\s+X-XSS-Protection\b', re.IGNORECASE
    )
    INCLUDE_PATTERN = re.compile(r'include\s+([^;]+);', re.IGNORECASE)
    SUPPRESS_PATTERN = re.compile(r'#\s*reveal:allow-xss-protection')

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        detections: List[Detection] = []
        reported_snippets: set = set()

        # Check the file itself
        if self.XSS_PROTECTION_PATTERN.search(content):
            if not self.SUPPRESS_PATTERN.search(content):
                line = self._find_pattern_line(content, self.XSS_PROTECTION_PATTERN)
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message="Deprecated X-XSS-Protection header — remove and add Content-Security-Policy instead",
                    suggestion="Remove X-XSS-Protection; add 'add_header Content-Security-Policy \"default-src \\'self\\'\";'",
                    context="add_header X-XSS-Protection ...",
                ))
                return detections  # reported inline, skip snippet scan

        # Check included snippets for any server block
        for match in self.SERVER_BLOCK_PATTERN.finditer(content):
            block = match.group(1)
            block_start = content[:match.start()].count('\n') + 1
            if self.SUPPRESS_PATTERN.search(block):
                continue
            for inc_match in self.INCLUDE_PATTERN.finditer(block):
                include_path = inc_match.group(1).strip()
                resolved = self._resolve_include(include_path, file_path)
                if resolved is None or resolved in reported_snippets:
                    continue
                try:
                    with open(resolved) as fh:
                        snippet = fh.read()
                    if self.XSS_PROTECTION_PATTERN.search(snippet):
                        reported_snippets.add(resolved)
                        snip_line = self._find_pattern_line(snippet, self.XSS_PROTECTION_PATTERN)
                        server_name = self._extract_server_name(block)
                        name_str = f"'{server_name}' via" if server_name else "via"
                        detections.append(self.create_detection(
                            file_path=resolved,
                            line=snip_line,
                            message=(
                                f"{name_str} {os.path.basename(resolved)}: "
                                "Deprecated X-XSS-Protection header — remove and add Content-Security-Policy instead"
                            ),
                            suggestion="Remove X-XSS-Protection line from snippet",
                            context=f"include {include_path}",
                        ))
                except OSError:
                    pass

        return detections

    def _resolve_include(self, include_path: str, config_file: str) -> Optional[str]:
        if os.path.isabs(include_path):
            return include_path if os.path.exists(include_path) else None
        config_dir = os.path.dirname(os.path.abspath(config_file)) if config_file else ""
        nginx_root = os.path.dirname(config_dir) if config_dir else ""
        for base in filter(None, [config_dir, nginx_root]):
            candidate = os.path.join(base, include_path)
            if os.path.exists(candidate):
                return candidate
        return None

    def _find_pattern_line(self, content: str, pattern: re.Pattern) -> int:
        m = pattern.search(content)
        if m:
            return content[:m.start()].count('\n') + 1
        return 1

    def _extract_server_name(self, block: str) -> Optional[str]:
        m = re.search(r'server_name\s+([^;]+);', block)
        if m:
            return m.group(1).strip().split()[0]
        return None
