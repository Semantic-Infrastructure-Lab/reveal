# Code Review: Proposed Improvements

## Overview
Systematic improvements to reduce duplication, improve performance, and follow Python best practices.

## 1. Rendering Functions (reveal.py)

### Issue: Print Coupling & Duplication
**Current:** Functions print directly, making them untestable and hard to reuse.

**Fix:** Introduce output builder pattern:
```python
class OutputBuilder:
    """Builder for formatted text output."""

    def __init__(self):
        self.lines = []

    def add_header(self, text: str, level: int = 1):
        """Add a header with appropriate spacing."""
        if level == 1:
            self.lines.append(f"\n{text}\n")
        else:
            self.lines.append(f"{text}:")
        return self

    def add_item(self, label: str, value: Any, indent: int = 1):
        """Add a labeled item."""
        prefix = "  " * indent
        self.lines.append(f"{prefix}* {label}: {value}")
        return self

    def add_section(self, title: str, items: List[str], indent: int = 1):
        """Add a titled section with items."""
        if not items:
            return self
        prefix = "  " * indent
        self.lines.append(f"{prefix}{title}:")
        for item in items:
            self.lines.append(f"{prefix}  * {item}")
        self.lines.append("")
        return self

    def build(self) -> str:
        """Return the built output."""
        return "\n".join(self.lines)
```

### Issue: Duplication in _render_config_sources
**Fix:** Extract common pattern:
```python
def _render_optional_section(title: str, items: Union[str, List, Dict],
                             builder: OutputBuilder, indent: int = 1):
    """Render an optional section if items exist."""
    if not items:
        return

    builder.add_header(title, level=2)

    if isinstance(items, str):
        builder.add_item(items, "", indent=indent)
    elif isinstance(items, dict):
        for key, value in items.items():
            builder.add_item(f"{key} = {value}", "", indent=indent)
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                # Handle project configs with root marker
                path = item['path']
                marker = " (root)" if item.get('root') else ""
                builder.add_item(f"{path}{marker}", "", indent=indent)
            else:
                builder.add_item(item, "", indent=indent)
```

## 2. Sys.Path Analysis (modules.py)

### Issue: os.getenv() called twice
**Fix:**
```python
# Before (line 205)
elif os.getenv("PYTHONPATH") and path in os.getenv("PYTHONPATH", "").split(":"):

# After
pythonpath = os.getenv("PYTHONPATH", "")
# ... later in classification
elif pythonpath and path in pythonpath.split(":"):
```

### Issue: Inefficient summary building (5 iterations)
**Fix:** Use Counter + single pass:
```python
from collections import Counter

def _build_syspath_summary(paths: List[Dict[str, Any]]) -> Dict[str, int]:
    """Build summary statistics for sys.path in one pass."""
    # Count by type
    type_counts = Counter(p["type"] for p in paths)

    # Count is_cwd separately (different key)
    cwd_count = sum(1 for p in paths if p["is_cwd"])

    return {
        "cwd_entries": cwd_count,
        "site_packages": type_counts.get("site-packages", 0),
        "stdlib": type_counts.get("python_stdlib", 0),
        "pythonpath": type_counts.get("pythonpath", 0),
        "other": type_counts.get("other", 0),
    }
```

### Issue: Magic strings for path types
**Fix:** Use Enum:
```python
from enum import Enum

class PathType(str, Enum):
    """Sys.path entry types."""
    CWD = "cwd"
    SITE_PACKAGES = "site-packages"
    PYTHON_STDLIB = "python_stdlib"
    PYTHONPATH = "pythonpath"
    OTHER = "other"

class PathPriority(str, Enum):
    """Path priority levels."""
    HIGHEST = "highest"
    HIGH = "high"
    NORMAL = "normal"

# Usage:
path_info["type"] = PathType.CWD
path_info["priority"] = PathPriority.HIGHEST
```

### Issue: Duplicate condition check
**Fix:** Compute once, reuse:
```python
def _classify_syspath_entry(path: str, index: int, cwd: Path) -> Dict[str, Any]:
    """Classify a single sys.path entry."""
    is_cwd = not path or path == "."

    path_info = {
        "index": index,
        "path": path if path else f"(CWD: {cwd})",
        "is_cwd": is_cwd,  # Use computed value
        "exists": Path(path).exists() if path else True,
    }

    # Classify using pre-computed is_cwd
    if is_cwd:
        path_info["type"] = PathType.CWD
        path_info["priority"] = PathPriority.HIGHEST
    # ... rest of logic
```

## 3. GDScript Parser (gdscript.py)

### Issue: Regex recompilation
**Fix:** Compile patterns at class level:
```python
@register('.gd', name='GDScript', icon='')
class GDScriptAnalyzer(FileAnalyzer):
    """GDScript file analyzer for Godot Engine."""

    # Compile regex patterns once at class level
    CLASS_PATTERN = re.compile(r'^\s*class\s+(\w+)\s*:')
    FUNC_PATTERN = re.compile(r'^\s*func\s+(\w+)\s*\((.*?)\)\s*(?:->\s*(.+?))?\s*:')
    SIGNAL_PATTERN = re.compile(r'^\s*signal\s+(\w+)(?:\((.*?)\))?\s*$')
    VAR_PATTERN = re.compile(r'^\s*(?:(export|onready)\s+)?(?:(var|const)\s+)?(\w+)(?:\s*:\s*(\w+))?(?:\s*=\s*(.+?))?\s*(?:#.*)?$')

    def _parse_class_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse a class definition line."""
        if match := self.CLASS_PATTERN.match(line):
            return {'line': line_num, 'name': match.group(1)}
        return None
```

### Issue: Duplication in parse functions
**Fix:** Generic parser factory:
```python
def _parse_with_pattern(
    self,
    line: str,
    line_num: int,
    pattern: re.Pattern,
    builder: Callable
) -> Optional[Dict[str, Any]]:
    """Generic parser using pattern and builder."""
    if match := pattern.match(line):
        return builder(match, line_num)
    return None

# Usage:
def _parse_class_line(self, line: str, line_num: int):
    return self._parse_with_pattern(
        line, line_num,
        self.CLASS_PATTERN,
        lambda m, ln: {'line': ln, 'name': m.group(1)}
    )
```

### Issue: Inefficient _build_result
**Fix:** Dict comprehension:
```python
def _build_result(self, **element_groups) -> Dict[str, List[Dict[str, Any]]]:
    """Build result dictionary from parsed elements."""
    return {
        name: elements
        for name, elements in element_groups.items()
        if elements
    }

# Usage in get_structure:
return self._build_result(
    classes=classes,
    functions=functions,
    signals=signals,
    variables=variables
)
```

## 4. General Improvements

### Use dataclasses for structured data
```python
from dataclasses import dataclass, asdict

@dataclass
class SysPathEntry:
    """A sys.path entry with metadata."""
    index: int
    path: str
    is_cwd: bool
    exists: bool
    type: PathType
    priority: PathPriority

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return asdict(self)
```

### Use contextlib for output capture (testing)
```python
from contextlib import redirect_stdout
from io import StringIO

def test_render_function():
    """Test rendering without mocking print."""
    output = StringIO()
    with redirect_stdout(output):
        render_function(data)
    assert "Expected text" in output.getvalue()
```

## Priority

**High Priority (Performance):**
1. ✅ Fix os.getenv() double call (modules.py:205)
2. ✅ Fix 5-iteration summary (modules.py:244-259)
3. ✅ Compile regex patterns (gdscript.py)

**Medium Priority (Maintainability):**
4. ✅ Extract duplication in _render_config_sources
5. ✅ Use Enum for magic strings
6. ✅ Dict comprehension for _build_result

**Low Priority (Architecture):**
7. ⚠️  Introduce OutputBuilder (requires broader refactoring)
8. ⚠️  Dataclasses for structured data (nice-to-have)

## Implementation Strategy

**Phase 1:** Quick wins (no behavior change)
- Fix double os.getenv call
- Use Counter for summary
- Compile regex patterns
- Dict comprehension for _build_result

**Phase 2:** Code quality (minor refactoring)
- Introduce PathType/PathPriority enums
- Extract duplication in rendering
- Generic parse pattern helper

**Phase 3:** Architecture (if time permits)
- OutputBuilder pattern
- Dataclasses for data structures
- Full separation of concerns
