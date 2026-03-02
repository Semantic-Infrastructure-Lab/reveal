"""N003: Nginx proxy location missing recommended headers.

Detects proxy_pass locations that lack important proxy headers
for proper client IP forwarding and protocol handling.

Example of violation:
    location /api {
        proxy_pass http://backend;
        # Missing: proxy_set_header X-Real-IP, X-Forwarded-For, etc.
    }
"""

import os
import re
from typing import List, Dict, Any, Optional, Set

from ..base import BaseRule, Detection, RulePrefix, Severity
from . import NGINX_FILE_PATTERNS


class N003(BaseRule):
    """Detect proxy locations missing recommended headers."""

    code = "N003"
    message = "Proxy location missing recommended headers"
    category = RulePrefix.N
    severity = Severity.MEDIUM
    file_patterns = NGINX_FILE_PATTERNS

    # Important headers for proxying
    RECOMMENDED_HEADERS = {
        'X-Real-IP': 'Forwards client IP to backend',
        'X-Forwarded-For': 'Forwards proxy chain to backend',
        'X-Forwarded-Proto': 'Forwards original protocol (http/https)',
        'Host': 'Preserves original Host header',
    }

    # Minimum headers that should be present
    MINIMUM_HEADERS = {'X-Real-IP', 'X-Forwarded-For'}

    # Match location blocks with proxy_pass
    LOCATION_PATTERN = re.compile(
        r'location\s+([^\{]+)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        re.MULTILINE | re.DOTALL
    )

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for proxy locations missing recommended headers."""
        detections: List[Detection] = []

        for match in self.LOCATION_PATTERN.finditer(content):
            location_path = match.group(1).strip()
            location_body = match.group(2)
            location_start = content[:match.start()].count('\n') + 1

            # Only check locations with proxy_pass
            if 'proxy_pass' not in location_body:
                continue

            # Find which headers are set (including via include files)
            present_headers = self._find_proxy_headers(location_body, file_path)

            # Check for minimum required headers
            missing_minimum = self.MINIMUM_HEADERS - present_headers

            if missing_minimum:
                # Find the proxy_pass line for accurate reporting
                proxy_line = self._find_proxy_pass_line(location_body, location_start)

                missing_list = ', '.join(sorted(missing_minimum))
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=proxy_line,
                    message=f"Proxy location '{location_path}' missing headers: {missing_list}",
                    suggestion=self._build_suggestion(missing_minimum),
                    context=f"location {location_path} {{ proxy_pass ...; }}"
                ))

        return detections

    # Pattern to find include directives
    INCLUDE_PATTERN = re.compile(r'include\s+([^;]+);', re.IGNORECASE)
    # Pattern to find proxy_set_header directives
    HEADER_PATTERN = re.compile(r'proxy_set_header\s+(\S+)', re.IGNORECASE)

    def _find_proxy_headers(self, location_body: str, file_path: str = "") -> Set[str]:
        """Find which proxy headers are set in the location block, including via includes."""
        present = set()

        for match in self.HEADER_PATTERN.finditer(location_body):
            present.add(match.group(1))

        # Resolve include directives and check included files for headers
        for inc_match in self.INCLUDE_PATTERN.finditer(location_body):
            include_path = inc_match.group(1).strip()
            resolved = self._resolve_include(include_path, file_path)
            if resolved is None:
                # Can't find the include file — assume it may satisfy the requirement
                present.update(self.MINIMUM_HEADERS)
                continue
            try:
                with open(resolved) as fh:
                    inc_content = fh.read()
                for hm in self.HEADER_PATTERN.finditer(inc_content):
                    present.add(hm.group(1))
            except OSError:
                # Can't read the file — suppress rather than false-positive
                present.update(self.MINIMUM_HEADERS)

        return present

    def _resolve_include(self, include_path: str, config_file: str) -> Optional[str]:
        """Resolve an nginx include path to an absolute path.

        Tries the include path relative to the config file's directory and then
        relative to the nginx root (one level up, e.g. /etc/nginx).
        Returns None if the file cannot be found.
        """
        if os.path.isabs(include_path):
            return include_path if os.path.exists(include_path) else None

        config_dir = os.path.dirname(os.path.abspath(config_file)) if config_file else ""
        nginx_root = os.path.dirname(config_dir) if config_dir else ""

        for base in filter(None, [config_dir, nginx_root]):
            candidate = os.path.join(base, include_path)
            if os.path.exists(candidate):
                return candidate

        return None

    def _find_proxy_pass_line(self, location_body: str, location_start: int) -> int:
        """Find the line number of the proxy_pass directive."""
        match = re.search(r'proxy_pass\s+', location_body)
        if match:
            return location_start + location_body[:match.start()].count('\n')
        return location_start

    def _build_suggestion(self, missing_headers: Set[str]) -> str:
        """Build suggestion text for missing headers."""
        suggestions = []
        if 'X-Real-IP' in missing_headers:
            suggestions.append("proxy_set_header X-Real-IP $remote_addr;")
        if 'X-Forwarded-For' in missing_headers:
            suggestions.append("proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;")
        if 'X-Forwarded-Proto' in missing_headers:
            suggestions.append("proxy_set_header X-Forwarded-Proto $scheme;")
        if 'Host' in missing_headers:
            suggestions.append("proxy_set_header Host $host;")

        return "Add: " + " ".join(suggestions)
