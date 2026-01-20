"""Central configuration defaults for Reveal.

All magic numbers and thresholds should be defined here.
These can be overridden by config files and environment variables.

Usage:
    from reveal.defaults import RuleDefaults

    threshold = self.get_threshold('threshold', RuleDefaults.CYCLOMATIC_COMPLEXITY)
"""


class RuleDefaults:
    """Default thresholds for quality rules.

    Organized by rule category. Each constant documents the rule(s) that use it.
    """

    # Complexity Rules
    CYCLOMATIC_COMPLEXITY = 10           # C901: Cyclomatic complexity threshold
    NESTING_DEPTH_MAX = 4                # C905: Maximum nesting depth
    FUNCTION_LENGTH_WARN = 50            # C902: Function length warning
    FUNCTION_LENGTH_ERROR = 100          # C902: Function length error (god function)

    # File Quality Rules
    FILE_LENGTH_WARN = 500               # M101: File length warning
    FILE_LENGTH_ERROR = 1000             # M101: File length error (too large)
    MAX_LINE_LENGTH = 100                # E501: Maximum line length

    # Code Smell Rules
    MAX_FUNCTION_ARGUMENTS = 5           # R913: Maximum function arguments
    MAX_PROPERTY_LINES = 8               # B003: Maximum property/getter lines

    # Duplication Rules
    MIN_FUNCTION_SIZE = 8                # D002: Minimum function size for comparison
    MIN_SIMILARITY = 0.50                # D002: Minimum similarity score
    MAX_DUPLICATE_CANDIDATES = 5         # D002: Maximum candidates to report

    # Maintainability Rules
    MIN_LIST_SIZE = 5                    # M104: Minimum list size for detection
    MIN_DICT_VALUE_SIZE = 3              # M104: Minimum dict value size

    # Link Rules
    LINK_TIMEOUT = 5                     # L002: HTTP request timeout (seconds)
    MIN_CROSS_REFS = 2                   # L005: Minimum cross-references


class AnalyzerDefaults:
    """Default limits for analyzers."""

    JSONL_PREVIEW_LIMIT = 10             # Lines to preview in JSONL files
    DIRECTORY_MAX_ENTRIES = 50           # Max entries per directory
    RELATED_DOCS_LIMIT = 100             # Max related documents to return


class AdapterDefaults:
    """Default limits for adapters."""

    STATS_MAX_FILES = 1000               # Maximum files for stats analysis
    CLAUDE_SESSION_SCAN_LIMIT = 50       # Sessions to scan for claude://
    GIT_COMMIT_HISTORY_LIMIT = 20        # Default commit history depth
    SSL_EXPIRY_WARNING_DAYS = 30         # SSL certificate expiry warning
    SSL_EXPIRY_CRITICAL_DAYS = 7         # SSL certificate expiry critical


class DisplayDefaults:
    """Default limits for display/output."""

    TREE_DIR_LIMIT = 50                  # --dir-limit default
    TREE_MAX_ENTRIES = 200               # --max-entries default
    SNIPPET_CONTEXT_LINES = 3            # Lines of context around matches


# Environment variable overrides
# Maps env var names to (class_name, attribute_name)
ENV_OVERRIDES = {
    'REVEAL_C901_THRESHOLD': ('RuleDefaults', 'CYCLOMATIC_COMPLEXITY'),
    'REVEAL_C905_MAX_DEPTH': ('RuleDefaults', 'NESTING_DEPTH_MAX'),
    'REVEAL_E501_MAX_LENGTH': ('RuleDefaults', 'MAX_LINE_LENGTH'),
    'REVEAL_M101_WARN': ('RuleDefaults', 'FILE_LENGTH_WARN'),
    'REVEAL_M101_ERROR': ('RuleDefaults', 'FILE_LENGTH_ERROR'),
    'REVEAL_DIR_LIMIT': ('DisplayDefaults', 'TREE_DIR_LIMIT'),
}
