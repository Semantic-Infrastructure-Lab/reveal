"""L002: Broken external links detector.

Detects external links in Markdown files that return HTTP errors (404, 403, etc.).
This rule requires network access and may be slower than L001.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import urllib.request
from urllib.error import URLError, HTTPError
import socket

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class L002(BaseRule):
    """Detect broken external links in Markdown files."""

    code = "L002"
    message = "Broken external link"
    category = RulePrefix.L
    severity = Severity.LOW  # Lower severity - external links can be transient
    file_patterns = ['.md', '.markdown']
    version = "1.0.0"

    # HTTP request timeout (seconds)
    TIMEOUT = 5

    # User agent to avoid bot blocking
    USER_AGENT = 'Mozilla/5.0 (compatible; Reveal/0.23; +https://github.com/Semantic-Infrastructure-Lab/reveal)'

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for broken external links in Markdown files.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure from markdown analyzer
            content: File content (used as fallback)

        Returns:
            List of detections for broken external links
        """
        detections: List[Dict[str, Any]] = []

        # Get links from structure (analyzer already parsed them)
        if structure and 'links' in structure:
            links = structure['links']
        else:
            # Fallback: extract links if not in structure
            from ...registry import get_analyzer
            analyzer_class = get_analyzer(file_path)
            if analyzer_class:
                analyzer = analyzer_class(file_path)
                links = analyzer._extract_links()
            else:
                return detections

        # Check each external link for issues
        for link in links:
            text = link.get('text', '')
            url = link.get('url', '')
            line_num = link.get('line', 1)

            # Only check external HTTP(S) links
            if not url.startswith(('http://', 'https://')):
                continue

            # Check if this external link is broken
            is_broken, reason, status = self._is_broken_link(url)

            if is_broken:
                message = f"{self.message}: {url}"
                suggestion = self._suggest_fix(url, reason, status)

                detections.append(Detection(
                    file_path=file_path,
                    line=line_num,
                    rule_code=self.code,
                    message=message,
                    column=1,  # Column not available from structure
                    suggestion=suggestion,
                    context=f"[{text}]({url})",
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _is_broken_link(self, url: str) -> Tuple[bool, str, Optional[int]]:
        """Check if an external link is broken using HTTP HEAD request.

        Args:
            url: External URL to validate

        Returns:
            Tuple of (is_broken, reason, status_code)
        """
        try:
            # Parse URL to validate format
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return (True, "invalid_url", None)

            # Create HEAD request with user agent
            request = urllib.request.Request(url, method='HEAD')
            request.add_header('User-Agent', self.USER_AGENT)

            # Try HEAD request first
            try:
                with urllib.request.urlopen(request, timeout=self.TIMEOUT) as response:
                    status = response.getcode()
                    if status and 200 <= status < 400:
                        return (False, "", status)
                    return (True, "http_error", status)

            except HTTPError as e:
                # Some servers don't support HEAD, try GET with range header
                if e.code == 405:  # Method Not Allowed
                    return self._try_get_request(url)
                return (True, "http_error", e.code)

        except socket.timeout:
            return (True, "timeout", None)
        except URLError as e:
            if isinstance(e.reason, socket.timeout):
                return (True, "timeout", None)
            return (True, "connection_error", None)
        except Exception as e:
            logger.debug(f"Error checking {url}: {e}")
            return (True, "validation_error", None)

    def _try_get_request(self, url: str) -> Tuple[bool, str, Optional[int]]:
        """Fallback to GET request with range header for servers that don't support HEAD.

        Args:
            url: External URL to validate

        Returns:
            Tuple of (is_broken, reason, status_code)
        """
        try:
            request = urllib.request.Request(url)
            request.add_header('User-Agent', self.USER_AGENT)
            request.add_header('Range', 'bytes=0-0')  # Request just 1 byte

            with urllib.request.urlopen(request, timeout=self.TIMEOUT) as response:
                status = response.getcode()
                if status and 200 <= status < 400:
                    return (False, "", status)
                return (True, "http_error", status)

        except HTTPError as e:
            return (True, "http_error", e.code)
        except Exception:
            return (True, "validation_error", None)

    def _suggest_fix(self, broken_url: str, reason: str, status: Optional[int]) -> str:
        """Generate helpful suggestion for fixing broken link.

        Args:
            broken_url: The broken URL
            reason: Reason why link is broken
            status: HTTP status code (if available)

        Returns:
            Suggestion string
        """
        suggestions = []

        if reason == "http_error" and status:
            if status == 404:
                suggestions.append("Page not found (404) - URL may have moved or been deleted")
            elif status == 403:
                suggestions.append("Access forbidden (403) - may require authentication")
            elif status == 401:
                suggestions.append("Authentication required (401)")
            elif status == 410:
                suggestions.append("Page permanently gone (410)")
            elif status == 500:
                suggestions.append("Server error (500) - temporary issue or broken server")
            elif status == 503:
                suggestions.append("Service unavailable (503) - may be temporary")
            else:
                suggestions.append(f"HTTP error {status}")

        elif reason == "timeout":
            suggestions.append(f"Request timed out after {self.TIMEOUT}s - server may be slow or down")

        elif reason == "connection_error":
            suggestions.append("Connection failed - check domain name and network")

        elif reason == "invalid_url":
            suggestions.append("URL format is invalid")

        elif reason == "validation_error":
            suggestions.append("Could not validate URL")

        # Check for common issues
        parsed = urlparse(broken_url)

        # Check for http vs https
        if parsed.scheme == 'http':
            https_url = broken_url.replace('http://', 'https://', 1)
            suggestions.append(f"Try HTTPS: {https_url}")

        # Check for missing www
        if parsed.netloc and not parsed.netloc.startswith('www.'):
            www_url = broken_url.replace(f'{parsed.scheme}://', f'{parsed.scheme}://www.', 1)
            suggestions.append(f"Try with www: {www_url}")

        if suggestions:
            return " | ".join(suggestions)
        return "External link appears broken"
