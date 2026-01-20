"""Centralized regex patterns for Reveal.

Compiling patterns once and reusing them improves performance
and ensures consistency across the codebase.

Usage:
    from reveal.utils.patterns import Patterns

    if Patterns.ERROR_LINE_START.search(content):
        # Handle error...
"""

import re
from functools import lru_cache


class Patterns:
    """Pre-compiled patterns for common matches.

    All patterns are compiled once at import time for performance.
    """

    # ========== Error Detection (claude adapter) ==========

    # Strong error patterns at line start - traceback, exception, etc.
    # Used by: adapters/claude/adapter.py (was duplicated at lines 601 and 1057)
    ERROR_LINE_START = re.compile(
        r'^\s*(?:traceback|exception|error:|fatal:|panic:)',
        re.IGNORECASE | re.MULTILINE
    )

    # Exit code extraction - "exit code N"
    # Used by: adapters/claude/adapter.py
    EXIT_CODE = re.compile(r'exit code (\d+)', re.IGNORECASE)

    # ========== Nginx Patterns ==========

    # Server block detection
    # Used by: rules/infrastructure/N002.py, N004.py
    NGINX_SERVER_BLOCK = re.compile(
        r'server\s*\{',
        re.MULTILINE
    )

    # SSL/443 listen directive
    # Used by: rules/infrastructure/N002.py:88, N004.py:135
    NGINX_LISTEN_SSL = re.compile(
        r'listen\s+[^;]*(?:ssl|443)[^;]*;',
        re.IGNORECASE
    )

    # Location block
    # Used by: rules/infrastructure/N003.py
    NGINX_LOCATION = re.compile(
        r'location\s+([^\s{]+)\s*\{',
        re.MULTILINE
    )

    # Root directive
    # Used by: rules/infrastructure/N004.py
    NGINX_ROOT = re.compile(r'root\s+([^;]+);')

    # ACME challenge location
    # Used by: rules/infrastructure/N004.py
    NGINX_ACME_LOCATION = re.compile(
        r'location\s+[~=]*\s*[\'"]?/\.well-known/acme-challenge',
        re.IGNORECASE
    )

    # Upstream block
    # Used by: rules/infrastructure/N001.py
    NGINX_UPSTREAM = re.compile(
        r'upstream\s+(\w+)\s*\{([^}]+)\}',
        re.MULTILINE | re.DOTALL
    )

    # ========== Code Patterns ==========

    # Python class definition
    PYTHON_CLASS = re.compile(r'^\s*class\s+(\w+)\s*[:\(]', re.MULTILINE)

    # Python function definition
    PYTHON_FUNCTION = re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE)

    # Version patterns (semver)
    SEMVER = re.compile(r'(\d+)\.(\d+)\.(\d+)(?:-(\w+))?')

    # GitHub HTTP URL (should be HTTPS)
    GITHUB_HTTP = re.compile(
        r'http://github\.com/([^/]+/[^/\s]+)',
        re.IGNORECASE
    )


@lru_cache(maxsize=128)
def compile_pattern(pattern: str, flags: int = 0) -> re.Pattern:
    """Get or compile a regex pattern with caching.

    Use this for dynamic patterns that may be reused.

    Args:
        pattern: Regex pattern string
        flags: Regex flags (re.IGNORECASE, etc.)

    Returns:
        Compiled regex pattern

    Example:
        # Good for dynamic patterns built at runtime
        user_pattern = compile_pattern(rf'\\b{username}\\b', re.IGNORECASE)
    """
    return re.compile(pattern, flags)
