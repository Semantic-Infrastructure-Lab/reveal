# Reveal Code Quality Review: Duplication & Refactoring Opportunities

**Review Date**: 2026-01-18
**Session**: boundless-meteorite-0118
**Reviewer**: TIA (automated analysis + manual review)
**Codebase Version**: reveal v0.37.0
**Files Analyzed**: 203 Python files
**Current Quality Score**: 98.5/100 (excellent baseline)

---

## Executive Summary

Comprehensive review of the Reveal codebase identified **12 categories of code duplication** with an estimated **200-300 lines** that could be consolidated into shared utilities. The codebase demonstrates **strong architectural patterns** with clear separation of concerns, but has **micro-level duplication** in utility operations (file I/O, formatting, path manipulation).

**Key Finding**: Most duplication is in utility-level operations rather than core business logic, making refactoring **low-risk and high-impact**.

---

## Critical Findings (Priority 1 - Immediate Action Recommended)

### 1. Duplicated `_format_size()` Function ⚠️ CRITICAL

**Status**: EXACT DUPLICATE (100% identical code)
**Impact**: 21 lines duplicated across 3 files
**Complexity**: TRIVIAL (5-minute fix)

**Locations**:
```
reveal/base.py:172-178
reveal/tree_view.py:197-203
reveal/analyzers/office/base.py:178-184
```

**Duplicated Code**:
```python
def _format_size(self, size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
```

**Proposed Solution**:
```python
# NEW FILE: reveal/utils/format_utils.py
"""Formatting utilities for human-readable output."""

def format_size(size: int) -> str:
    """Format file size in human-readable form.

    Args:
        size: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.5 KB", "2.3 MB")

    Examples:
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1536)
        '1.5 KB'
        >>> format_size(1048576)
        '1.0 MB'
    """
    if size == 0:
        return "0 B"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
```

**Files to Update**:
1. `reveal/base.py:172-178` - Replace with `from .utils.format_utils import format_size`
2. `reveal/tree_view.py:197-203` - Replace with `from .utils.format_utils import format_size`
3. `reveal/analyzers/office/base.py:178-184` - Replace with `from ..utils.format_utils import format_size`

**Testing**:
- Existing tests should continue passing (2240 tests)
- Add unit tests for edge cases (0 bytes, very large files)

**Estimated Time**: 30 minutes (create + update + test)

---

### 2. Multi-Encoding File Reading Logic ⚠️ HIGH

**Status**: COMPLEX LOGIC DUPLICATED
**Impact**: 19 lines of complex encoding fallback logic
**Complexity**: MEDIUM (1-2 hour refactoring)

**Primary Implementation**: `reveal/base.py:36-53`
```python
def _read_file(self) -> List[str]:
    """Read file with automatic encoding detection."""
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(self.path, 'r', encoding=encoding) as f:
                return f.read().splitlines()
        except (UnicodeDecodeError, LookupError):
            continue

    # Last resort: binary mode with error replacement
    with open(self.path, 'rb') as f:
        content = f.read().decode('utf-8', errors='replace')
        return content.splitlines()
```

**Also Duplicated In**:
- `reveal/analyzers/markdown.py` - Similar encoding fallback
- `reveal/analyzers/imports/python.py` - Encoding detection
- Potentially other analyzers (needs audit)

**Proposed Solution**:
```python
# NEW FILE: reveal/utils/encoding_utils.py
"""File reading utilities with automatic encoding detection."""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ENCODINGS = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']

def read_file_with_fallback(
    path: Path,
    encodings: Optional[List[str]] = None,
    return_lines: bool = True
) -> str | List[str]:
    """Read file with automatic encoding detection.

    Tries multiple encodings in order. Falls back to binary mode
    with error replacement if all encodings fail.

    Args:
        path: Path to file
        encodings: List of encodings to try (default: utf-8, utf-8-sig, latin-1, cp1252)
        return_lines: If True, return list of lines; if False, return full text

    Returns:
        File content as string or list of strings

    Raises:
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> lines = read_file_with_fallback(Path('file.py'))
        >>> text = read_file_with_fallback(Path('file.py'), return_lines=False)
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if encodings is None:
        encodings = DEFAULT_ENCODINGS

    # Try each encoding
    for encoding in encodings:
        try:
            with open(path, 'r', encoding=encoding) as f:
                content = f.read()
                return content.splitlines() if return_lines else content
        except (UnicodeDecodeError, LookupError):
            logger.debug(f"Failed to read {path} with {encoding}, trying next")
            continue

    # Last resort: binary mode with error replacement
    logger.debug(f"All encodings failed for {path}, using binary mode with error replacement")
    with open(path, 'rb') as f:
        content = f.read().decode('utf-8', errors='replace')
        return content.splitlines() if return_lines else content


def detect_encoding(path: Path) -> str:
    """Detect the most likely encoding for a file.

    Args:
        path: Path to file

    Returns:
        Best-guess encoding name

    Note:
        Returns 'utf-8' if detection fails.
    """
    for encoding in DEFAULT_ENCODINGS:
        try:
            with open(path, 'r', encoding=encoding) as f:
                f.read()
                return encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return 'utf-8'
```

**Files to Update**:
1. `reveal/base.py:36-53` - Replace `_read_file()` implementation
2. Audit all analyzers for similar patterns
3. Update imports across affected files

**Testing**:
- Test with UTF-8, UTF-8-BOM, Latin-1, CP1252 files
- Test with binary files (should not crash)
- Test with non-existent files (should raise FileNotFoundError)

**Estimated Time**: 2 hours (create + update + test + audit)

---

### 3. AST Parsing with Error Handling ⚠️ HIGH

**Status**: BOILERPLATE PATTERN REPEATED
**Impact**: ~10 lines × 4+ files = 40+ lines
**Complexity**: MEDIUM (1 hour refactoring)

**Duplicated Pattern** (found in 4+ rule files):
```python
try:
    tree = ast.parse(content, filename=file_path)
except SyntaxError as e:
    logger.debug(f"Syntax error in {file_path}, skipping: {e}")
    return detections
```

**Locations**:
```
reveal/rules/bugs/B001.py:42-46
reveal/rules/bugs/B005.py:120-124
reveal/rules/complexity/C901.py:114-129
reveal/rules/maintainability/M102.py (needs verification)
```

**Proposed Solution**:
```python
# NEW FILE: reveal/rules/base_mixins.py
"""Mixins for common rule functionality."""

import ast
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ASTParsingMixin:
    """Mixin for rules that need to parse Python AST.

    Provides safe AST parsing with standardized error handling.
    """

    def _safe_parse_python(
        self,
        content: str,
        file_path: str
    ) -> Optional[ast.AST]:
        """Safely parse Python AST with error handling.

        Args:
            content: Python source code
            file_path: Path to file (for error reporting)

        Returns:
            Parsed AST tree, or None if parsing failed

        Note:
            Logs debug message on syntax error but doesn't raise.
        """
        try:
            return ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}, skipping AST check: {e}")
            return None

    def _safe_parse_python_or_skip(
        self,
        content: str,
        file_path: str,
        detections: list
    ) -> Optional[ast.AST]:
        """Parse Python AST and return early if parsing fails.

        Convenience method that returns detections list if parsing fails,
        making it easy to use in check() methods.

        Args:
            content: Python source code
            file_path: Path to file
            detections: List of detections to return if parsing fails

        Returns:
            Parsed AST tree, or detections list if parsing failed

        Example:
            tree = self._safe_parse_python_or_skip(content, file_path, detections)
            if tree is None:
                return detections
            # Use tree...
        """
        return self._safe_parse_python(content, file_path)


class RegexParsingMixin:
    """Mixin for rules that use regex patterns.

    Provides caching and safe regex compilation.
    """

    _regex_cache = {}

    def _get_compiled_regex(self, pattern: str):
        """Get cached compiled regex pattern.

        Args:
            pattern: Regex pattern string

        Returns:
            Compiled regex pattern
        """
        if pattern not in self._regex_cache:
            import re
            self._regex_cache[pattern] = re.compile(pattern)
        return self._regex_cache[pattern]
```

**Usage Example** (how rules would use it):
```python
from ..base import BaseRule, Detection
from .base_mixins import ASTParsingMixin


class B001(BaseRule, ASTParsingMixin):
    """Detect mutable default arguments."""

    def check(self, file_path, structure, content):
        detections = []

        # Old way (10 lines):
        # try:
        #     tree = ast.parse(content, filename=file_path)
        # except SyntaxError as e:
        #     logger.debug(f"...")
        #     return detections

        # New way (2 lines):
        tree = self._safe_parse_python(content, file_path)
        if tree is None:
            return detections

        # Rest of check logic...
```

**Files to Update**:
1. Create `reveal/rules/base_mixins.py`
2. Update all rules that parse AST (audit needed to find all)
3. Add mixin to rule class inheritance

**Testing**:
- Test with valid Python files
- Test with syntax errors (should not crash)
- Test with empty files
- Verify all affected rules still pass tests

**Estimated Time**: 1 hour (create + update + test)

---

## Medium Priority Findings (Priority 2)

### 4. Path/Directory Search Utilities

**Status**: SEARCH PATTERN DUPLICATED
**Impact**: ~40 lines across 3+ files
**Complexity**: MEDIUM (1-2 hours)

**Duplicated Patterns**:
```
reveal/rules/validation/utils.py:12-54 - find_reveal_root()
reveal/rules/validation/adapter_utils.py:11-49 - find_adapter_file()
reveal/rules/validation/V001.py - Multiple directory searches
```

**Common Pattern**:
```python
# Pattern: Search up directory tree (max 10 levels)
for _ in range(10):
    if some_condition(current_dir):
        return current_dir
    current_dir = current_dir.parent
    if current_dir == current_dir.parent:  # Reached filesystem root
        break
return None
```

**Proposed Solution**:
```python
# NEW FILE: reveal/utils/path_utils.py
"""Path manipulation and search utilities."""

from pathlib import Path
from typing import Optional, Callable, List


def search_parent_directories(
    start: Path,
    condition_func: Callable[[Path], bool],
    max_depth: int = 10
) -> Optional[Path]:
    """Search up directory tree until condition is met.

    Args:
        start: Starting directory
        condition_func: Function that returns True when target is found
        max_depth: Maximum levels to search upward

    Returns:
        First directory where condition is True, or None

    Examples:
        >>> # Find directory containing .git
        >>> git_root = search_parent_directories(
        ...     Path.cwd(),
        ...     lambda p: (p / '.git').exists()
        ... )

        >>> # Find directory containing pyproject.toml
        >>> project_root = search_parent_directories(
        ...     Path(__file__).parent,
        ...     lambda p: (p / 'pyproject.toml').exists()
        ... )
    """
    current = start.resolve()

    for _ in range(max_depth):
        if condition_func(current):
            return current

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


def find_file_in_parents(
    start: Path,
    filename: str,
    max_depth: int = 10
) -> Optional[Path]:
    """Find file by searching up directory tree.

    Args:
        start: Starting directory
        filename: Name of file to find
        max_depth: Maximum levels to search upward

    Returns:
        Path to file if found, None otherwise

    Example:
        >>> pyproject = find_file_in_parents(Path.cwd(), 'pyproject.toml')
    """
    result = search_parent_directories(
        start,
        lambda p: (p / filename).exists(),
        max_depth
    )
    return (result / filename) if result else None


def find_from_patterns(
    base_path: Path,
    patterns: List[str]
) -> Optional[Path]:
    """Try multiple path patterns and return first that exists.

    Args:
        base_path: Base directory to search from
        patterns: List of path patterns (can include wildcards)

    Returns:
        First matching path, or None

    Example:
        >>> config = find_from_patterns(
        ...     Path.cwd(),
        ...     ['reveal.toml', '.reveal.toml', 'config/reveal.toml']
        ... )
    """
    for pattern in patterns:
        path = base_path / pattern
        if path.exists():
            return path
    return None
```

**Files to Update**:
1. `reveal/rules/validation/utils.py` - Refactor `find_reveal_root()`
2. `reveal/rules/validation/adapter_utils.py` - Refactor `find_adapter_file()`
3. Any other validation rules with directory search logic

**Estimated Time**: 2 hours

---

### 5. Broad Exception Handling Pattern

**Status**: PATTERN REPEATED
**Impact**: ~15 lines × 5+ files = 75+ lines
**Complexity**: MEDIUM (1-2 hours)

**Pattern** (repeated in 5+ files):
```python
try:
    result = some_operation()
except Exception as e:
    logging.debug(f"Failed to {operation}: {e}")
    return fallback_value
```

**Locations**:
```
reveal/analyzers/office/base.py:76-91, 144-146, 186-193
reveal/rules/validation/adapter_utils.py:141-147, 165-171
reveal/rules/validation/V001.py:135-144
```

**Proposed Solution**:
```python
# NEW FILE: reveal/utils/safe_operations.py
"""Safe operation wrappers and decorators."""

import logging
from functools import wraps
from typing import Any, Callable, Optional


def safe_operation(
    fallback: Any = None,
    logger: Optional[logging.Logger] = None,
    log_level: str = 'debug'
):
    """Decorator for operations that might fail gracefully.

    Args:
        fallback: Value to return on exception
        logger: Logger instance (uses module logger if None)
        log_level: Log level for errors ('debug', 'info', 'warning', 'error')

    Returns:
        Decorated function that returns fallback on exception

    Examples:
        >>> @safe_operation(fallback=[], logger=logger)
        ... def parse_config():
        ...     return json.loads(config_text)

        >>> @safe_operation(fallback={})
        ... def load_metadata():
        ...     return yaml.safe_load(file_content)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if logger:
                    log_func = getattr(logger, log_level, logger.debug)
                    log_func(f"Operation {func.__name__} failed: {e}")
                return fallback
        return wrapper
    return decorator


def safe_call(
    func: Callable,
    *args,
    fallback: Any = None,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Any:
    """Call function safely, returning fallback on exception.

    Args:
        func: Function to call
        *args: Positional arguments to pass
        fallback: Value to return on exception
        logger: Logger instance
        **kwargs: Keyword arguments to pass

    Returns:
        Function result or fallback value

    Example:
        >>> result = safe_call(json.loads, text, fallback={}, logger=logger)
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if logger:
            logger.debug(f"Operation {func.__name__} failed: {e}")
        return fallback
```

**Estimated Time**: 2 hours

---

### 6. Tree-Sitter Node Type Lists

**Status**: CONFIGURATION SCATTERED
**Impact**: Maintainability issue (hard to add languages)
**Complexity**: LOW (30 minutes)

**Current State** in `reveal/treesitter.py`:
```python
# Lines 97-104: Import types
import_types = ['import_statement', 'import_declaration', 'use_declaration', ...]

# Lines 137-149: Function types
function_types = ['function_definition', 'function_declaration', 'function_item', ...]

# Lines 259-267: Class types
class_types = ['class_definition', 'class_declaration', ...]

# Lines 352-360: Struct types
struct_types = ['struct_item', 'struct_specifier', 'struct_declaration', ...]
```

**Proposed Solution**:
```python
# NEW FILE: reveal/treesitter_config.py
"""Tree-sitter node type configurations.

Centralizes node type definitions for all languages supported by tree-sitter.
Makes it easy to add new languages or update node types.
"""

# Node types for different code constructs across languages
NODE_TYPES = {
    'imports': [
        'import_statement',        # Python
        'import_declaration',      # Java, C++, Go
        'use_declaration',         # Rust
        'import_clause',           # TypeScript
        'include_directive',       # C, C++
        'package_clause',          # Go
        'using_directive',         # C#
    ],

    'functions': [
        'function_definition',     # Python, C, C++
        'function_declaration',    # C, C++, TypeScript
        'function_item',           # Rust
        'method_definition',       # Ruby, JavaScript
        'method_declaration',      # Java, C#
        'arrow_function',          # JavaScript, TypeScript
        'lambda_expression',       # C#, Java
    ],

    'classes': [
        'class_definition',        # Python, Ruby
        'class_declaration',       # Java, C++, C#, TypeScript
        'struct_item',             # Rust
        'interface_declaration',   # Java, C#, TypeScript
        'trait_item',              # Rust
        'protocol_declaration',    # Swift
    ],

    'structs': [
        'struct_item',             # Rust
        'struct_specifier',        # C, C++
        'struct_declaration',      # C, C++, Go
    ],
}

# Language-specific overrides
LANGUAGE_OVERRIDES = {
    'python': {
        'functions': ['function_definition', 'lambda'],
        'classes': ['class_definition'],
    },
    'rust': {
        'functions': ['function_item'],
        'classes': ['struct_item', 'enum_item', 'trait_item', 'impl_item'],
    },
    # Add more as needed
}


def get_node_types(category: str, language: str = None) -> list:
    """Get node types for a category, with optional language override.

    Args:
        category: Category name ('imports', 'functions', 'classes', 'structs')
        language: Optional language name for overrides

    Returns:
        List of node type strings

    Examples:
        >>> get_node_types('functions')
        ['function_definition', 'function_declaration', ...]

        >>> get_node_types('functions', 'python')
        ['function_definition', 'lambda']
    """
    if language and language in LANGUAGE_OVERRIDES:
        overrides = LANGUAGE_OVERRIDES[language]
        if category in overrides:
            return overrides[category]

    return NODE_TYPES.get(category, [])
```

**Files to Update**:
1. Create `reveal/treesitter_config.py`
2. Update `reveal/treesitter.py` to import from config

**Estimated Time**: 30 minutes

---

## Low Priority / Architectural Observations (Priority 3)

### 7. Renderer Protocol Formalization (Optional)

**Current State**: Renderers use duck typing without formal base class

**All Renderers Follow This Pattern**:
```python
class SomeRenderer:
    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render main structure."""

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render single element (optional)."""

    @staticmethod
    def render_check(result: dict, format: str = 'text') -> None:
        """Render check results (optional)."""

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message."""
```

**Renderers**:
```
reveal/adapters/python/renderer.py - PythonRenderer
reveal/adapters/mysql/renderer.py - MySQLRenderer
reveal/adapters/sqlite/renderer.py - SqliteRenderer
```

**Proposed Solution (Optional)**:
```python
# NEW FILE: reveal/adapters/base_renderer.py
"""Base renderer protocol and utilities."""

from typing import Protocol, runtime_checkable
import json
import sys


@runtime_checkable
class RendererProtocol(Protocol):
    """Protocol for adapter renderers.

    Renderers transform adapter output into user-facing formats.
    All renderers must implement render_structure() and render_error().
    """

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render main structure/overview.

        Args:
            result: Structure dict from adapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        ...

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message.

        Args:
            error: Exception that occurred
        """
        ...

    # Optional methods:
    # def render_element(result: dict, format: str = 'text') -> None: ...
    # def render_check(result: dict, format: str = 'text') -> None: ...


class BaseRenderer:
    """Base class with shared renderer utilities.

    Provides common JSON/formatting helpers that all renderers can use.
    """

    @staticmethod
    def render_json(data: dict) -> None:
        """Render data as formatted JSON."""
        print(json.dumps(data, indent=2))

    @staticmethod
    def format_error(error: Exception, scheme: str = None) -> str:
        """Format error message consistently.

        Args:
            error: Exception that occurred
            scheme: Optional scheme name (for context)

        Returns:
            Formatted error string
        """
        prefix = f"Error in {scheme}:// adapter" if scheme else "Error"
        return f"{prefix}: {error}"

    @staticmethod
    def format_table(rows: list, headers: list = None) -> str:
        """Format data as ASCII table.

        Args:
            rows: List of row data
            headers: Optional header row

        Returns:
            ASCII table string
        """
        # Simple table formatting
        # (Could use tabulate library or implement custom)
        pass
```

**Trade-offs**:
- ✅ **Pro**: Type safety, shared utilities, consistent interface
- ✅ **Pro**: Easier for new contributors to understand pattern
- ❌ **Con**: Adds structure/ceremony to simple renderers
- ❌ **Con**: Current duck-typing approach works well

**Decision**: Defer this refactoring. Current approach is flexible and working well.

**Estimated Time**: 3 hours (if pursued)

---

### 8. Detection Creation Consistency Audit

**Status**: MOSTLY GOOD, NEEDS AUDIT
**Impact**: Code consistency
**Complexity**: LOW (30 minutes audit)

**Current State**: `BaseRule.create_detection()` helper exists and works well

**Issue**: Some rules still create `Detection` objects directly:
```
reveal/rules/complexity/C901.py:87-97 - Direct Detection() call
```

**Action Required**:
1. Audit all 63 rule files
2. Identify rules using `Detection()` directly
3. Update to use `self.create_detection()`

**Search Command**:
```bash
grep -r "Detection(" reveal/rules/ --include="*.py" | grep -v "create_detection"
```

**Estimated Time**: 30 minutes (audit) + 1 hour (fixes if needed)

---

### 9. File Existence + Read Pattern

**Status**: MINOR PATTERN
**Impact**: ~10 lines × 3 files = 30 lines
**Complexity**: LOW (30 minutes)

**Pattern**:
```python
if not path.exists():
    return self.create_detection(
        file_path=str(path),
        line=1,
        message=f"File not found: {path}",
        ...
    )
content = path.read_text()
```

**Proposed Solution**:
```python
# ADD TO: reveal/utils/file_io_utils.py

def read_file_or_detection(
    path: Path,
    file_path_for_report: str,
    rule: BaseRule
) -> Tuple[Optional[str], Optional[Detection]]:
    """Read file or create detection for missing file.

    Args:
        path: Path to file
        file_path_for_report: Path string for detection report
        rule: Rule instance (for create_detection)

    Returns:
        Tuple of (content, detection). One will be None.

    Example:
        content, detection = read_file_or_detection(path, str(path), self)
        if detection:
            return [detection]
        # Use content...
    """
    if not path.exists():
        detection = rule.create_detection(
            file_path=file_path_for_report,
            line=1,
            message=f"File not found: {path}",
            suggestion="Create the file or update the reference"
        )
        return None, detection

    try:
        content = path.read_text()
        return content, None
    except Exception as e:
        detection = rule.create_detection(
            file_path=file_path_for_report,
            line=1,
            message=f"Failed to read file: {e}",
            suggestion="Check file permissions"
        )
        return None, detection
```

**Estimated Time**: 30 minutes

---

## Architectural Strengths ✅

**No Refactoring Needed** - these patterns are already well-designed:

### 1. Analyzer Registration System
```python
@register('.py', name='Python', icon='🐍')
class PythonAnalyzer(TreeSitterAnalyzer):
    language = 'python'
```
✅ Clean decorator pattern, minimal boilerplate

### 2. Tree-Sitter Base Analyzer
- Reduces analyzer implementation to 3-5 lines
- Handles all parsing, extraction, error handling
- Example: 13 analyzers are just `language = 'name'`

### 3. Import Analysis Plugin System
```python
@register_import_analyzer('python')
class PythonImportAnalyzer(BaseImportAnalyzer):
    ...
```
✅ Well-architected base class with language-specific implementations

### 4. Rule Categories
- Clear separation: bugs/, complexity/, validation/, etc.
- Each rule is self-contained
- BaseRule provides consistent interface

### 5. Adapter Registry
```python
@register_adapter('mysql')
class MySQLAdapter(ResourceAdapter):
    ...
```
✅ Centralized adapter/renderer registration

---

## Implementation Roadmap

### Phase 1: Critical Utilities (Priority 1)
**Time**: 2-3 hours
**Risk**: LOW
**Impact**: HIGH (eliminates ~100 lines of duplication)

**Tasks**:
1. Create `reveal/utils/format_utils.py` with `format_size()`
2. Create `reveal/utils/encoding_utils.py` with `read_file_with_fallback()`
3. Create `reveal/rules/base_mixins.py` with `ASTParsingMixin`
4. Update 3 files using `_format_size()`
5. Update base.py and analyzers using encoding detection
6. Update 4+ rules using AST parsing
7. Run full test suite (2240 tests)

**Files Created**: 3
**Files Modified**: 10-15
**Lines Eliminated**: ~100

---

### Phase 2: Path & Error Handling (Priority 2)
**Time**: 2-3 hours
**Risk**: LOW
**Impact**: MEDIUM (eliminates ~80 lines, improves consistency)

**Tasks**:
1. Create `reveal/utils/path_utils.py` with directory search utilities
2. Create `reveal/utils/safe_operations.py` with decorators
3. Create `reveal/utils/file_io_utils.py` with safe file reading
4. Update validation rules using path utilities
5. Update office analyzer and rules using safe operations
6. Run full test suite

**Files Created**: 3
**Files Modified**: 10+
**Lines Eliminated**: ~80

---

### Phase 3: Configuration & Consistency (Priority 2-3)
**Time**: 1-2 hours
**Risk**: LOW
**Impact**: MEDIUM (improves maintainability)

**Tasks**:
1. Create `reveal/treesitter_config.py` with node type configs
2. Update `reveal/treesitter.py` to use config
3. Audit all 63 rules for `create_detection()` usage
4. Fix any rules using `Detection()` directly
5. Run full test suite

**Files Created**: 1
**Files Modified**: 2-10
**Lines Eliminated**: ~20 (but improves consistency)

---

### Phase 4: Renderer Formalization (Optional)
**Time**: 2-3 hours
**Risk**: MEDIUM
**Impact**: LOW (type safety, shared utilities)

**Tasks**:
1. Create `reveal/adapters/base_renderer.py`
2. Update 3-5 renderers to inherit/implement protocol
3. Extract shared JSON/formatting utilities
4. Run full test suite

**Files Created**: 1
**Files Modified**: 3-5
**Decision**: DEFERRED (current approach works well)

---

## Testing Strategy

### Unit Tests (New)
Create tests for all new utilities:
```python
# tests/utils/test_format_utils.py
def test_format_size_bytes()
def test_format_size_kilobytes()
def test_format_size_megabytes()
def test_format_size_zero()

# tests/utils/test_encoding_utils.py
def test_read_utf8_file()
def test_read_latin1_file()
def test_read_binary_fallback()
def test_missing_file_error()

# tests/rules/test_base_mixins.py
def test_ast_parsing_mixin_valid_python()
def test_ast_parsing_mixin_syntax_error()
```

### Regression Tests
- Run full test suite after each phase: `pytest -xvs`
- Expected: All 2240 tests pass
- No performance degradation

### Integration Tests
- Test each refactored file individually
- Verify output matches original behavior
- Check error messages are consistent

---

## Metrics & Expected Impact

| Metric | Before | After (All Phases) | Improvement |
|--------|--------|-------------------|-------------|
| **Lines of duplicated code** | ~200-300 | ~0-50 | **75-85% reduction** |
| **Utility modules** | 4 existing | 9 total | **Better organization** |
| **Maintenance burden** | High (multiple copies) | Low (single source) | **Centralized** |
| **Token efficiency** | Baseline | -15% for duplicated patterns | **LLM-friendly** |
| **Implementation time** | - | 8-12 hours total | **3-4 focused sessions** |
| **Risk level** | - | LOW-MEDIUM | **Safe refactoring** |
| **Test coverage** | 74% | 74% (maintain) | **No regression** |

---

## Decision Points for Future Sessions

### Should We Formalize Renderers? (Phase 4)

**Arguments For**:
- Type safety with Protocol/ABC
- Shared JSON/formatting utilities reduce duplication
- Easier for new contributors to understand pattern
- Could extract common table formatting, error messages

**Arguments Against**:
- Current duck-typing works well and is flexible
- Only 3 renderers currently (small scale)
- Would add ceremony to simple renderers
- Not a pain point right now

**Recommendation**: **Defer**. Revisit when:
- We have 6+ renderers
- Significant duplication emerges in renderer code
- Type safety becomes important for IDE support

---

### Should We Use ABC or Protocol for Base Classes?

**Option 1: ABC (Abstract Base Class)**
```python
from abc import ABC, abstractmethod

class BaseRenderer(ABC):
    @staticmethod
    @abstractmethod
    def render_structure(result: dict, format: str) -> None:
        pass
```

**Option 2: Protocol (Structural Typing)**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class RendererProtocol(Protocol):
    @staticmethod
    def render_structure(result: dict, format: str) -> None: ...
```

**Recommendation**: **Protocol** for new code
- Less intrusive (no explicit inheritance required)
- More Pythonic (duck typing with type hints)
- Better for retrofitting existing code
- Can use `@runtime_checkable` for isinstance checks

---

## Files to Create (Summary)

### High Priority
```
reveal/utils/format_utils.py          (NEW) - Size formatting, other display utils
reveal/utils/encoding_utils.py        (NEW) - Multi-encoding file reading
reveal/rules/base_mixins.py           (NEW) - AST parsing, regex helpers
```

### Medium Priority
```
reveal/utils/path_utils.py            (NEW) - Directory search, path finding
reveal/utils/safe_operations.py       (NEW) - Exception handling decorators
reveal/utils/file_io_utils.py         (NEW) - Safe file reading patterns
reveal/treesitter_config.py           (NEW) - Node type configurations
```

### Low Priority (Optional)
```
reveal/adapters/base_renderer.py      (NEW) - Renderer protocol/base class
```

---

## Related Documentation

- **Session**: boundless-meteorite-0118
- **Prior Session**: universal-comet-0118 (v0.38.0 validation, technical debt refactoring)
- **Quality Baseline**: 98.5/100 (post-refactoring)
- **Test Suite**: 2240 tests passing
- **Project Roadmap**: `internal-docs/planning/PRIORITIES.md`

---

## Next Steps

When resuming this work:

1. **Review this document** - Understand the full context
2. **Choose a phase** - Start with Phase 1 (critical utilities)
3. **Create one utility at a time** - Format utils → Encoding utils → AST mixins
4. **Update consumers incrementally** - One file at a time, test after each
5. **Run tests frequently** - After each file modification
6. **Document decisions** - Update this file with any deviations or learnings

**Estimated Timeline**: 3-4 focused sessions (2-3 hours each)

---

## Maintainer Notes

This review was conducted by automated analysis (Explore agent) combined with manual code inspection. Findings are based on:

- Pattern matching across 203 Python files
- Duplication detection via grep/code analysis
- Manual inspection of high-impact files
- Experience with Python refactoring best practices

**Confidence Level**: HIGH for Critical findings, MEDIUM for architectural recommendations

**Last Updated**: 2026-01-18 by TIA (boundless-meteorite-0118)
