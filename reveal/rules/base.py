"""Base classes for reveal's pattern detector system.

Industry-aligned pattern detection following Ruff, ESLint, and Semgrep patterns.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import re
import logging

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Issue severity levels (Ruff-compatible)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RulePrefix(Enum):
    """
    Industry-standard rule prefixes (Ruff-compatible).

    Format: PREFIX + NUMBER (e.g., E501, S102, C901)
    """

    # Code Errors (E) - pycodestyle errors
    E = "E"  # Syntax, structure, language-level errors
    # E1xx: Indentation
    # E2xx: Whitespace
    # E3xx: Blank lines
    # E4xx: Imports
    # E5xx: Line length
    # E7xx: Statements
    # E9xx: Runtime errors

    # Security (S) - bandit rules
    S = "S"  # Security vulnerabilities
    # S1xx: Shell injection, command execution
    # S2xx: Insecure functions (eval, exec, pickle)
    # S3xx: Hardcoded passwords, secrets
    # S4xx: Cryptography issues
    # S5xx: Network/protocol issues
    # S6xx: File permissions
    # S7xx: Docker/container security

    # Complexity (C) - mccabe complexity
    C = "C"  # Code complexity metrics
    # C901: Function too complex (cyclomatic)
    # C902: Function too long
    # C903: Too many arguments
    # C904: Too many local variables
    # C905: Nested depth too high

    # Bugs (B) - bugbear rules
    B = "B"  # Likely bugs and design issues
    # B0xx: Exception handling
    # B1xx: Function definitions
    # B2xx: Context managers
    # B3xx: Loops
    # B9xx: Misuse of builtins

    # Performance (PERF)
    PERF = "PERF"  # Performance anti-patterns
    # PERF1xx: Inefficient operations
    # PERF2xx: Memory issues
    # PERF3xx: Algorithm choice

    # Maintainability (M) - custom
    M = "M"  # Code maintainability
    # M1xx: Documentation
    # M2xx: Naming conventions
    # M3xx: Code organization
    # M4xx: Dead code
    # M5xx: TODO/FIXME comments

    # Infrastructure (I) - custom
    I = "I"  # Infrastructure/config files  # noqa: E741
    # I1xx: Dockerfile
    # I2xx: Docker Compose
    # I3xx: Kubernetes
    # I4xx: Terraform
    # I5xx: CI/CD (GitHub Actions, etc.)
    # I6xx: Nginx/Apache
    # I7xx: Database configs

    # URLs (U) - custom
    U = "U"  # URI/URL pattern detection
    # U1xx: Docker Hub URIs
    # U2xx: GitHub/GitLab URIs
    # U3xx: Package registry URIs (PyPI, npm)
    # U4xx: API endpoints
    # U5xx: Insecure protocols (http://, ftp://)

    # Refactoring (R) - pylint refactoring rules
    R = "R"  # Code smells and refactoring opportunities
    # R1xx: Class design
    # R2xx: Method/function design
    # R9xx: General code smells (too many args, too many locals, etc.)

    # Duplicates (D) - copy-paste detection
    D = "D"  # Duplicate code detection
    # D001: Exact duplicate functions (normalized)
    # D002: Similar functions (fuzzy match)
    # D003: Duplicate code blocks

    # Links (L) - link validation
    L = "L"  # Link and reference validation
    # L001: Broken internal links (filesystem)
    # L002: Broken external links (HTTP)
    # L003: Framework routing mismatches

    # Frontmatter (F) - markdown metadata validation
    F = "F"  # Markdown front matter validation
    # F001: Missing front matter
    # F002: Empty front matter
    # F003: Required field missing
    # F004: Type mismatch
    # F005: Custom validation failed

    # Nginx (N) - nginx configuration
    N = "N"  # Nginx/web server configuration
    # N001: Duplicate backend servers
    # N002: Missing SSL configuration
    # N003: Missing proxy headers

    # Validation (V) - reveal self-validation
    V = "V"  # Reveal internal validation rules
    # V001-V011: Completeness and consistency checks

    # Type annotations (T) - type hint enforcement
    T = "T"  # Type annotation rules (PEP 484, mypy compliance)
    # T001: Missing return type annotations
    # T002: Missing parameter type annotations
    # T003: Overuse of Any type
    # T004: Implicit Optional (PEP 484 violation)


@dataclass
class Detection:
    """
    Single detection result (industry-standard format).

    Mirrors Ruff's violation format and ESLint's message format.
    """
    file_path: str
    line: int
    rule_code: str        # e.g., "B001", "S701"
    message: str          # Human-readable description
    column: int = 1
    suggestion: Optional[str] = None  # Auto-fix or recommendation
    context: Optional[str] = None     # Code snippet
    severity: Severity = Severity.MEDIUM
    category: Optional[RulePrefix] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON output."""
        data = asdict(self)
        # Convert enums to strings
        if self.severity:
            data['severity'] = self.severity.value
        if self.category:
            data['category'] = self.category.value
        return data

    def __str__(self) -> str:
        """Format for terminal output (Ruff-style)."""
        loc = f"{self.file_path}:{self.line}:{self.column}"
        severity_marker = {
            Severity.LOW: "ℹ️ ",
            Severity.MEDIUM: "⚠️ ",
            Severity.HIGH: "❌",
            Severity.CRITICAL: "🚨"
        }.get(self.severity, "")

        result = f"{loc} {severity_marker} {self.rule_code} {self.message}"
        if self.suggestion:
            result += f"\n  💡 {self.suggestion}"
        if self.context:
            result += f"\n  📝 {self.context}"
        return result


class BaseRule(ABC):
    """
    Minimal rule interface - ONE rule per class.

    Prevents god objects by enforcing single responsibility.
    Each rule file implements exactly ONE check.

    Example:
        # reveal/rules/bugs/B001.py
        class B001(BaseRule):
            code = "B001"
            message = "Bare except clause"
            category = RulePrefix.B
            severity = Severity.HIGH
            file_patterns = ['.py']

            def check(self, file_path, structure, content):
                # Check ONLY bare except - nothing else!
                detections: List[Detection] = []
                # ... analyze bare except only
                return detections

    Auto-discovered by code: B001.py → rule B001
    """

    # Metadata (override in subclass)
    code: str = "R000"              # e.g., "B001", "S701"
    message: str = ""               # Short description
    category: Optional[RulePrefix] = None     # E, S, C, B, etc.
    severity: Severity = Severity.MEDIUM
    file_patterns: List[str] = ["*"]  # ['.py'] or ['*'] for universal
    uri_patterns: List[str] = []    # Optional URI regex patterns
    version: str = "1.0.0"
    enabled: bool = True
    # Optional: thresholds exposed via --explain (key → default value)
    # e.g. {"max_lines": 15, "threshold": 10}
    thresholds: Dict[str, Any] = {}
    # Optional: brief compliant code example shown via --explain
    compliant_example: str = ""

    # For tracking current file during check (set by registry)
    _current_file: Optional[str] = None
    _config: Optional[Any] = None  # Lazy-loaded config instance

    def get_config(self):
        """Get configuration instance (lazy-loaded).

        Returns:
            RevealConfig instance
        """
        if self._config is None:
            try:
                from reveal.config import RevealConfig
                self._config = RevealConfig.get()
            except Exception as e:
                logger.debug(f"Failed to load config: {e}")
                # Return a mock config that always uses defaults
                class MockConfig:
                    def get_rule_config(self, code, key, default=None):
                        return default
                    def is_rule_enabled(self, code, path=None):
                        return True
                self._config = MockConfig()
        return self._config

    def get_threshold(self, key: str, default: Any) -> Any:
        """Get a configuration threshold for this rule.

        This method allows rules to read their configuration from .reveal.yaml:

        Example .reveal.yaml:
            rules:
              C901:
                threshold: 15
              E501:
                max_length: 120

        Args:
            key: Configuration key (e.g., "threshold", "max_length")
            default: Default value if not configured

        Returns:
            Configured value or default

        Example:
            class C901(BaseRule):
                code = "C901"
                DEFAULT_THRESHOLD = 10

                def check(self, file_path, structure, content):
                    threshold = self.get_threshold('threshold', self.DEFAULT_THRESHOLD)
                    # Use threshold...
        """
        config = self.get_config()
        return config.get_rule_config(self.code, key, default)

    @abstractmethod
    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for ONE specific pattern - that's it!

        Args:
            file_path: Path to file OR URI being checked
            structure: Parsed structure (for files) or None (for URIs)
            content: File content OR HTTP response body

        Returns:
            List of Detection instances (0+ findings)
        """
        pass

    def create_detection(self,
                        file_path: str,
                        line: int,
                        message: Optional[str] = None,
                        column: int = 1,
                        suggestion: Optional[str] = None,
                        context: Optional[str] = None,
                        severity: Optional[Severity] = None) -> Detection:
        """
        Helper to create Detection with rule defaults.

        Reduces boilerplate - auto-fills rule_code, severity, category from self.

        Args:
            file_path: Path to file (or URI)
            line: Line number of issue
            message: Custom message (defaults to self.message)
            column: Column number (default: 1)
            suggestion: Fix suggestion
            context: Code snippet showing issue
            severity: Override severity (defaults to self.severity)

        Returns:
            Detection instance with rule metadata auto-filled

        Example:
            # Before (9 parameters):
            Detection(
                file_path=file_path,
                line=node.lineno,
                rule_code=self.code,
                message=self.message,
                column=node.col_offset + 1,
                suggestion="Use specific exception",
                context=context,
                severity=self.severity,
                category=self.category
            )

            # After (6 parameters, 3 auto-filled):
            self.create_detection(
                file_path=file_path,
                line=node.lineno,
                column=node.col_offset + 1,
                suggestion="Use specific exception",
                context=context
            )
        """
        return Detection(
            file_path=file_path,
            line=line,
            rule_code=self.code,
            message=message or self.message,
            column=column,
            suggestion=suggestion,
            context=context,
            severity=severity or self.severity,
            category=self.category
        )

    def matches_target(self, target: str) -> bool:
        """
        Check if this rule applies to target (file or URI).

        Args:
            target: File path OR URI

        Returns:
            True if rule should check this target
        """
        # Check URI patterns first
        if self.uri_patterns:
            for pattern in self.uri_patterns:
                if re.match(pattern, target):
                    return True

        # Check file patterns
        if self.file_patterns == ['*']:
            return True

        # Handle both string paths and Path objects
        if isinstance(target, str):
            target_path = Path(target)
        else:
            target_path = target

        # Check if file extension matches
        suffix = target_path.suffix.lower()

        # Also check for files like 'Dockerfile' with no extension
        name = target_path.name

        for pattern in self.file_patterns:
            if pattern == suffix:
                return True
            # Support patterns like 'Dockerfile' (exact name match)
            if pattern == name:
                return True

        return False

    def get_description(self) -> str:
        """Get full rule description."""
        return f"{self.code}: {self.message}"

    @property
    def current_file(self) -> Optional[str]:
        """Get the current file being checked (for use in check methods)."""
        return self._current_file

    def set_current_file(self, file_path: str):
        """Set the current file being checked (called by registry)."""
        self._current_file = file_path
T = 'T'
