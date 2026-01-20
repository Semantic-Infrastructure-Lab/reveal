# Reveal Architecture Improvements: Meta-Level Refactoring Opportunities

**Review Date**: 2026-01-20
**Session**: prairie-storm-0120
**Reviewer**: TIA (Opus 4.5)
**Complements**: `CODE_QUALITY_REVIEW_2026-01-18.md` (micro-level duplication)

---

## Executive Summary

This document focuses on **meta-level architectural concerns** rather than function-level code duplication (covered in the companion review). The key areas are:

1. **Monolithic Files** - 12 files over 500 lines need splitting
2. **Renderer Pattern Sprawl** - 15+ near-identical render_structure implementations
3. **Static Value Scatter** - Hardcoded thresholds and limits across 30+ files
4. **Regex Pattern Duplication** - Same patterns compiled multiple times
5. **Query Parser Inconsistency** - 4 different `_parse_query` implementations

**Estimated Total Impact**: ~4,000 lines that could be consolidated/refactored

---

## 1. Monolithic File Refactoring (Priority: HIGH)

### Files Requiring Decomposition

| File | Lines | Recommended Split |
|------|-------|-------------------|
| `adapters/claude/adapter.py` | 1,203 | See detailed plan below |
| `analyzers/markdown.py` | 1,029 | 4 modules |
| `config.py` | 957 | 3 modules |
| `adapters/mysql/adapter.py` | 950 | Already has submodules, just need to move more |
| `adapters/git/adapter.py` | 923 | 3 modules |
| `analyzers/html.py` | 866 | 3 modules |
| `adapters/diff.py` | 744 | 2 modules |
| `adapters/stats.py` | 713 | 2 modules |
| `treesitter.py` | 692 | OK but consider splitting extraction |
| `adapters/reveal.py` | 690 | 2 modules |
| `display/formatting.py` | 676 | 2-3 modules |
| `display/structure.py` | 626 | 2 modules |

### Detailed Refactoring Plans

#### 1.1 `adapters/claude/adapter.py` (1,203 lines → 5 modules)

**Current Problems:**
- Renderer, adapter, and analysis all in one file
- Duplicate regex patterns (lines 601 and 1057)
- Session parsing mixed with analysis

**Proposed Structure:**
```
adapters/claude/
├── __init__.py           # Exports (16 lines)
├── adapter.py            # Core adapter logic (~300 lines)
├── renderer.py           # ClaudeRenderer class (~100 lines)
├── parser.py             # Session/query parsing (~150 lines)
├── analysis/
│   ├── __init__.py
│   ├── overview.py       # _get_overview, _get_summary (~150 lines)
│   ├── timeline.py       # _get_timeline (~150 lines)
│   ├── errors.py         # _get_errors, _get_error_context (~200 lines)
│   └── tools.py          # Tool extraction, success rates (~200 lines)
└── patterns.py           # Shared regex patterns (~50 lines)
```

**Impact**:
- Eliminates duplicate regex (lines 601 + 1057)
- Single Responsibility per module
- Easier testing of individual components

#### 1.2 `config.py` (957 lines → 3 modules)

**Current Problems:**
- Config loading, merging, file config, rule config, and utilities all mixed
- Complex environment variable parsing (60+ lines)
- Breadcrumb logic mixed with config

**Proposed Structure:**
```
config/
├── __init__.py           # Re-exports RevealConfig
├── core.py               # RevealConfig class (~350 lines)
├── loader.py             # _load_file, _discover_project_configs (~150 lines)
├── env.py                # _load_from_env, environment parsing (~100 lines)
├── rules.py              # Rule enable/disable logic (~100 lines)
├── paths.py              # Path utilities, cache/data paths (~100 lines)
└── breadcrumbs.py        # Breadcrumb hint system (~80 lines)
```

#### 1.3 `analyzers/markdown.py` (1,029 lines → 4 modules)

**Current Problems:**
- Heading, link, code, frontmatter extraction all mixed
- RelatedTracker class at top but only used by one method
- Regex-based fallbacks mixed with tree-sitter code

**Proposed Structure:**
```
analyzers/markdown/
├── __init__.py           # MarkdownAnalyzer export
├── analyzer.py           # Core analyzer, get_structure (~200 lines)
├── headings.py           # _extract_headings, _heading_to_slug (~100 lines)
├── links.py              # _extract_links, _is_broken_link (~200 lines)
├── code_blocks.py        # _extract_code_blocks, inline code (~200 lines)
├── frontmatter.py        # Frontmatter + related extraction (~250 lines)
└── tracker.py            # RelatedTracker class (~50 lines)
```

---

## 2. Renderer Pattern Consolidation (Priority: HIGH)

### The Problem

**15+ identical render_structure implementations** scattered across adapters:

```
adapters/sqlite/renderer.py:11
adapters/stats.py:40
adapters/mysql/renderer.py:12
adapters/imports.py:113
adapters/json_adapter.py:15
adapters/env.py:13
adapters/markdown.py:17
adapters/reveal.py:13
adapters/git/adapter.py:29
adapters/help.py:13
adapters/ssl/renderer.py:12
adapters/diff.py:18
adapters/ast.py:19
adapters/claude/adapter.py:20
adapters/python/renderer.py:10
```

Most follow this pattern:
```python
@staticmethod
def render_structure(result: dict, format: str = 'text') -> None:
    if format == 'json':
        print(safe_json_dumps(result, indent=2))
    else:
        # Custom text rendering...
```

### Proposed Solution

Create a base renderer with format handling:

```python
# NEW: rendering/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..utils.json_utils import safe_json_dumps

class BaseRenderer(ABC):
    """Base class for all renderers with common format handling."""

    @classmethod
    def render_structure(cls, result: dict, format: str = 'text') -> None:
        """Dispatch to appropriate format renderer."""
        if format == 'json':
            cls._render_json(result)
        elif format == 'grep':
            cls._render_grep(result)
        else:
            cls._render_text(result)

    @staticmethod
    def _render_json(result: dict) -> None:
        """Standard JSON output."""
        print(safe_json_dumps(result, indent=2))

    @classmethod
    def _render_grep(cls, result: dict) -> None:
        """Grep-compatible output (override if needed)."""
        # Default: same as JSON
        cls._render_json(result)

    @classmethod
    @abstractmethod
    def _render_text(cls, result: dict) -> None:
        """Human-readable text output - subclasses must implement."""
        pass

    @classmethod
    def render_element(cls, result: dict, format: str = 'text') -> None:
        """Render a single element (default: same as structure)."""
        cls.render_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Standard error rendering."""
        print(f"Error: {error}")
```

**Impact**:
- ~200 lines of boilerplate eliminated
- Consistent format handling
- Single point for format extension (e.g., adding YAML output)

---

## 3. Static Value Centralization (Priority: MEDIUM)

### Current State: Values Scattered Across 30+ Files

```python
# rules/complexity/C901.py
DEFAULT_THRESHOLD = 10

# rules/complexity/C905.py
MAX_DEPTH = 4

# rules/duplicates/D002.py
MAX_CANDIDATES = 5

# rules/maintainability/M101.py
THRESHOLD_WARN = 500
THRESHOLD_ERROR = 1000

# rules/complexity/C902.py
THRESHOLD_WARN = 50
THRESHOLD_ERROR = 100

# rules/bugs/B003.py
MAX_PROPERTY_LINES = 8

# rules/refactoring/R913.py
MAX_ARGS = 5

# rules/errors/E501.py
DEFAULT_MAX_LENGTH = 100

# analyzers/jsonl.py
DEFAULT_LIMIT = 10
```

### Proposed Solution: Central Defaults Module

```python
# NEW: reveal/defaults.py
"""Central configuration defaults for Reveal.

All magic numbers and thresholds should be defined here.
These can be overridden by config files and environment variables.
"""

class RuleDefaults:
    """Default thresholds for quality rules."""

    # Complexity
    CYCLOMATIC_COMPLEXITY_THRESHOLD = 10  # C901
    NESTING_DEPTH_MAX = 4                  # C905
    FUNCTION_LENGTH_WARN = 50              # C902
    FUNCTION_LENGTH_ERROR = 100            # C902

    # File Quality
    FILE_LENGTH_WARN = 500                 # M101
    FILE_LENGTH_ERROR = 1000               # M101
    MAX_LINE_LENGTH = 100                  # E501

    # Duplicates
    MAX_DUPLICATE_CANDIDATES = 5           # D002

    # Code Smells
    MAX_PROPERTY_LINES = 8                 # B003
    MAX_FUNCTION_ARGUMENTS = 5             # R913


class AnalyzerDefaults:
    """Default limits for analyzers."""

    JSONL_PREVIEW_LIMIT = 10
    DIRECTORY_MAX_ENTRIES = 50
    RELATED_DOCS_LIMIT = 100


class AdapterDefaults:
    """Default limits for adapters."""

    STATS_MAX_FILES = 1000
    CLAUDE_SESSION_SCAN_LIMIT = 50
    GIT_COMMIT_HISTORY_LIMIT = 20


# Environment variable overrides
ENV_OVERRIDES = {
    'REVEAL_C901_THRESHOLD': ('RuleDefaults', 'CYCLOMATIC_COMPLEXITY_THRESHOLD'),
    'REVEAL_E501_MAX_LENGTH': ('RuleDefaults', 'MAX_LINE_LENGTH'),
    # ... etc
}
```

**Impact**:
- Single source of truth for all defaults
- Easy to find and modify limits
- Self-documenting configuration

---

## 4. Regex Pattern Sharing (Priority: MEDIUM)

### The Problem

Same or similar patterns compiled multiple times:

```python
# adapters/claude/adapter.py:601
strong_patterns = re.compile(
    r'(error|failed|exception|traceback|cannot|unable|denied)',
    re.IGNORECASE
)

# adapters/claude/adapter.py:1057 (DUPLICATE!)
strong_patterns = re.compile(
    r'(error|failed|exception|traceback|cannot|unable|denied)',
    re.IGNORECASE
)

# rules/infrastructure/N002.py:88 and N004.py:135
listen_pattern = re.compile(r'listen\s+[^;]*(?:ssl|443)[^;]*;', re.IGNORECASE)
```

### Proposed Solution: Pattern Registry

```python
# NEW: utils/patterns.py
"""Centralized regex patterns for Reveal.

Compiling patterns once and reusing them improves performance
and ensures consistency across the codebase.
"""

import re
from functools import lru_cache

class Patterns:
    """Pre-compiled patterns for common matches."""

    # Error detection
    ERROR_KEYWORDS = re.compile(
        r'(error|failed|exception|traceback|cannot|unable|denied)',
        re.IGNORECASE
    )
    EXIT_CODE = re.compile(r'exit code (\d+)', re.IGNORECASE)

    # Nginx patterns
    NGINX_LISTEN_SSL = re.compile(
        r'listen\s+[^;]*(?:ssl|443)[^;]*;',
        re.IGNORECASE
    )
    NGINX_SERVER_BLOCK = re.compile(
        r'server\s*\{',
        re.MULTILINE
    )

    # Code patterns
    PYTHON_CLASS = re.compile(r'^\s*class\s+(\w+)\s*:', re.MULTILINE)
    PYTHON_FUNCTION = re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE)

    # Version patterns
    SEMVER = re.compile(r'(\d+)\.(\d+)\.(\d+)(?:-(\w+))?')

    # GitHub patterns
    GITHUB_HTTP = re.compile(
        r'http://github\.com/([^/]+/[^/]+)',
        re.IGNORECASE
    )


@lru_cache(maxsize=128)
def compile_pattern(pattern: str, flags: int = 0) -> re.Pattern:
    """Get or compile a regex pattern with caching.

    Use this for dynamic patterns that may be reused.
    """
    return re.compile(pattern, flags)
```

**Impact**:
- Eliminates duplicate compilation
- Improved startup performance
- Single source for pattern maintenance

---

## 5. Query Parser Unification (Priority: LOW)

### Current State: 4 Different Implementations

```python
# Different return types!
adapters/markdown.py:151  → List[Tuple[str, str, str]]
adapters/stats.py:184     → Dict[str, Any]
adapters/claude/adapter.py:102 → Dict[str, Any]
adapters/ast.py:267       → Dict[str, Any]
```

Each re-implements URL query parsing with slight variations.

### Proposed Solution: Base Query Parser

```python
# NEW: adapters/query.py
"""Unified query parsing for adapters."""

from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, List, Tuple, Optional


class QueryParser:
    """Base query parser with common utilities."""

    def __init__(self, query_string: str):
        self.raw = query_string or ''
        self.params = parse_qs(self.raw)

    def get_single(self, key: str, default: Any = None) -> Any:
        """Get single value for key (first if multiple)."""
        values = self.params.get(key, [])
        return values[0] if values else default

    def get_list(self, key: str) -> List[str]:
        """Get all values for key as list."""
        return self.params.get(key, [])

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get boolean value (handles 'true', '1', 'yes')."""
        value = self.get_single(key)
        if value is None:
            return default
        return value.lower() in ('true', '1', 'yes', '')

    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer value."""
        value = self.get_single(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert to flat dictionary (single values)."""
        return {k: self.get_single(k) for k in self.params}


# Subclass example for specific adapter
class ClaudeQueryParser(QueryParser):
    """Claude adapter query parser with specific fields."""

    @property
    def mode(self) -> str:
        return self.get_single('mode', 'overview')

    @property
    def tool_name(self) -> Optional[str]:
        return self.get_single('tool')

    @property
    def message_id(self) -> Optional[int]:
        val = self.get_single('msg')
        return int(val) if val else None
```

**Impact**:
- Consistent query handling
- Reduced boilerplate
- Type-safe accessors

---

## 6. Better Tools for Regex Usage (Priority: LOW)

### Current Issues

1. **No pattern validation** - Invalid patterns silently fail or crash
2. **No pattern reuse** - Same patterns compiled repeatedly
3. **Mixed paradigms** - Some use tree-sitter, some regex, some both

### Recommendation: Lint Rule + Migration Guide

Create a new rule `V030: Regex Pattern Hygiene`:
- Warn on inline `re.compile()` that could use `Patterns` class
- Warn on patterns without `re.IGNORECASE` for case-insensitive searches
- Warn on patterns that could be tree-sitter queries instead

Create migration guide: `docs/REGEX_TO_TREESITTER_GUIDE.md`:
- When to use regex vs tree-sitter
- Performance characteristics
- Common migration patterns

---

## Implementation Roadmap

### Phase 1: Quick Wins (1-2 days)

1. Create `reveal/defaults.py` with all hardcoded values
2. Create `utils/patterns.py` with shared patterns
3. Fix duplicate regex in claude adapter (lines 601, 1057)

### Phase 2: Renderer Consolidation (2-3 days)

1. Create `rendering/base.py` with BaseRenderer
2. Migrate all renderers to inherit from base
3. Update tests

### Phase 3: Large File Splits (1-2 weeks)

1. Split `config.py` → `config/` package
2. Split `adapters/claude/adapter.py` → `adapters/claude/` package
3. Split `analyzers/markdown.py` → `analyzers/markdown/` package
4. (Remaining files as time permits)

### Phase 4: Query Parser Unification (1 week)

1. Create `adapters/query.py`
2. Migrate adapters to use base parser
3. Update tests

---

## Metrics to Track

| Metric | Current | Target |
|--------|---------|--------|
| Files > 500 lines | 12 | 4 |
| Duplicate render_structure | 15+ | 0 |
| Hardcoded thresholds | 30+ | 0 (all in defaults.py) |
| Duplicate regex patterns | ~10 | 0 |

---

## Related Documents

- `CODE_QUALITY_REVIEW_2026-01-18.md` - Micro-level duplication
- `ARCHITECTURAL_DILIGENCE.md` - Layer boundaries and standards
- `DOGFOODING_REPORT_2026-01-19.md` - Functional issues

---

**Document Status**: Draft
**Next Review**: After Phase 1 completion
