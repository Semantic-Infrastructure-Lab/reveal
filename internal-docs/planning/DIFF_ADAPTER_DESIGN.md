# diff:// Adapter Design Document

**Date**: 2026-01-04
**Session**: glowing-aurora-0104
**Status**: Design Phase
**Target Version**: v0.30.0

---

## Overview

The `diff://` adapter enables **comparative exploration** across any two reveal-compatible resources. It composes with all existing adapters to provide structural diffs for files, databases, environments, and more.

**Core Value**: Instead of comparing text (like traditional `diff`), compare **semantic structures** - functions added/removed/modified, schema changes, configuration drift, etc.

---

## Architecture

### URI Syntax

```
diff://<left-uri>:<right-uri>[/element]
```

**Examples**:
```bash
# File comparison
reveal diff://app.py:backup/app.py
reveal diff://file:app.py:file:backup/app.py  # Explicit

# Git revision comparison
reveal diff://app.py:git:HEAD~1:app.py
reveal diff://file:@main:app.py:file:@develop:app.py

# Cross-environment
reveal diff://env://:env://production
reveal diff://python://venv:python://system

# Database schema drift
reveal diff://mysql://localhost/users:mysql://staging/users

# AST query comparison
reveal diff://ast:v1:./src:ast:v2:./src

# Element-specific diff
reveal diff://app.py:old_app.py/handle_request  # Compare specific function
```

### Design Principles

1. **Composition Over Custom Logic**: Leverage existing adapters - don't reimplement parsing
2. **Universal Compatibility**: Works with ANY adapter that returns structure
3. **Semantic Diff**: Compare structure/meaning, not text
4. **Progressive Disclosure**: Summary → details → specific elements
5. **Actionable Output**: Clear added/removed/modified markers

---

## Implementation Plan

### Phase 1: Core Diff Engine (Week 1)

**Files to Create**:
```
reveal/adapters/diff.py                  # DiffAdapter class
reveal/cli/scheme_handlers/diff.py      # handle_diff() function
reveal/rendering/diff.py                 # Diff-specific rendering
reveal/diff/                             # Diff algorithm module
  ├── __init__.py
  ├── structure_diff.py                  # Core diff logic
  ├── function_diff.py                   # Function-specific diffs
  ├── class_diff.py                      # Class-specific diffs
  └── import_diff.py                     # Import-specific diffs
```

**Core Classes**:

#### 1. `DiffAdapter` (reveal/adapters/diff.py)

```python
@register_adapter('diff')
class DiffAdapter(ResourceAdapter):
    """Compare two reveal-compatible resources."""

    def __init__(self, left_uri: str, right_uri: str):
        """Initialize with two URIs to compare.

        Args:
            left_uri: Source URI (e.g., 'file:app.py', 'env://')
            right_uri: Target URI (e.g., 'file:backup/app.py', 'env://prod')
        """
        self.left_uri = left_uri
        self.right_uri = right_uri
        self.left_structure = None
        self.right_structure = None

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get diff summary between two resources.

        Returns:
            {
                'type': 'diff',
                'left': {'uri': ..., 'type': ...},
                'right': {'uri': ..., 'type': ...},
                'summary': {
                    'functions': {'added': 2, 'removed': 1, 'modified': 3},
                    'classes': {'added': 0, 'removed': 0, 'modified': 1},
                    'imports': {'added': 5, 'removed': 2},
                },
                'diff': {
                    'functions': [...],  # Detailed function diffs
                    'classes': [...],    # Detailed class diffs
                    'imports': [...]     # Import changes
                }
            }
        """
        # Resolve both URIs using existing adapter infrastructure
        left_struct = self._resolve_uri(self.left_uri, **kwargs)
        right_struct = self._resolve_uri(self.right_uri, **kwargs)

        # Compute semantic diff
        diff_result = compute_structure_diff(left_struct, right_struct)

        return {
            'type': 'diff',
            'left': self._extract_metadata(left_struct, self.left_uri),
            'right': self._extract_metadata(right_struct, self.right_uri),
            'summary': diff_result['summary'],
            'diff': diff_result['details']
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get diff for a specific element (function, class, etc.).

        Args:
            element_name: Name of element to compare (e.g., 'handle_request')

        Returns:
            Detailed diff for that specific element
        """
        left_struct = self._resolve_uri(self.left_uri, **kwargs)
        right_struct = self._resolve_uri(self.right_uri, **kwargs)

        left_elem = self._find_element(left_struct, element_name)
        right_elem = self._find_element(right_struct, element_name)

        return compute_element_diff(left_elem, right_elem, element_name)

    def _resolve_uri(self, uri: str, **kwargs) -> Dict[str, Any]:
        """Resolve a URI to its structure using existing adapters.

        This is the key composition point - we delegate to existing
        adapters instead of reimplementing parsing logic.
        """
        # If it's a plain path, treat as file://
        if '://' not in uri:
            uri = f'file:{uri}'

        scheme, resource = uri.split('://', 1)

        # Get registered adapter
        adapter_class = get_adapter_class(scheme)
        if not adapter_class:
            raise ValueError(f"Unsupported URI scheme: {scheme}://")

        # Instantiate and get structure
        # Different adapters have different constructors, handle gracefully
        adapter = self._instantiate_adapter(adapter_class, resource)
        return adapter.get_structure(**kwargs)

    def _instantiate_adapter(self, adapter_class: type, resource: str):
        """Instantiate adapter with appropriate arguments."""
        # This handles different adapter constructor signatures
        # Some take no args (EnvAdapter), some take paths (FileAnalyzer), etc.
        # Implementation omitted for brevity - see full code
        pass
```

#### 2. Diff Algorithm (reveal/diff/structure_diff.py)

```python
def compute_structure_diff(left: Dict[str, Any],
                          right: Dict[str, Any]) -> Dict[str, Any]:
    """Compute semantic diff between two structures.

    Args:
        left: Structure from left URI
        right: Structure from right URI

    Returns:
        {
            'summary': {
                'functions': {'added': N, 'removed': M, 'modified': K},
                'classes': {...},
                'imports': {...}
            },
            'details': {
                'functions': [
                    {'type': 'added', 'name': 'foo', 'line': 42, ...},
                    {'type': 'removed', 'name': 'bar', ...},
                    {'type': 'modified', 'name': 'baz', 'changes': {...}}
                ],
                ...
            }
        }
    """
    return {
        'summary': {
            'functions': diff_functions(left.get('structure', {}).get('functions', []),
                                      right.get('structure', {}).get('functions', [])),
            'classes': diff_classes(left.get('structure', {}).get('classes', []),
                                  right.get('structure', {}).get('classes', [])),
            'imports': diff_imports(left.get('structure', {}).get('imports', []),
                                  right.get('structure', {}).get('imports', []))
        },
        'details': {
            'functions': diff_functions_detailed(left, right),
            'classes': diff_classes_detailed(left, right),
            'imports': diff_imports_detailed(left, right)
        }
    }


def diff_functions(left_funcs: List[Dict],
                   right_funcs: List[Dict]) -> Dict[str, int]:
    """Compare function lists and return summary counts."""
    left_names = {f['name']: f for f in left_funcs}
    right_names = {f['name']: f for f in right_funcs}

    added = len(right_names.keys() - left_names.keys())
    removed = len(left_names.keys() - right_names.keys())

    # Count modified (same name, different signature/complexity/lines)
    modified = 0
    for name in left_names.keys() & right_names.keys():
        if function_changed(left_names[name], right_names[name]):
            modified += 1

    return {'added': added, 'removed': removed, 'modified': modified}


def function_changed(left: Dict, right: Dict) -> bool:
    """Determine if a function has meaningfully changed."""
    # Compare signature
    if left.get('signature') != right.get('signature'):
        return True

    # Compare complexity (significant change = ±2 or more)
    left_cx = left.get('complexity', 0)
    right_cx = right.get('complexity', 0)
    if abs(left_cx - right_cx) >= 2:
        return True

    # Compare line count (significant change = ±10% or more)
    left_lines = left.get('line_count', 0)
    right_lines = right.get('line_count', 0)
    if left_lines > 0:
        change_pct = abs(right_lines - left_lines) / left_lines
        if change_pct >= 0.10:
            return True

    return False
```

#### 3. Scheme Handler (reveal/cli/scheme_handlers/diff.py)

```python
def handle_diff(adapter_class: type, resource: str,
                element: Optional[str], args: Namespace) -> None:
    """Handle diff:// URIs.

    Args:
        adapter_class: DiffAdapter class
        resource: Contains "left_uri:right_uri"
        element: Optional element to diff
        args: CLI arguments
    """
    # Parse left:right from resource
    if ':' not in resource:
        print("Error: diff:// requires format: diff://left:right", file=sys.stderr)
        sys.exit(1)

    # Handle complex URIs (may contain multiple colons)
    left_uri, right_uri = parse_diff_uris(resource)

    # Instantiate diff adapter
    adapter = adapter_class(left_uri, right_uri)

    # Get diff (full or element-specific)
    if element:
        result = adapter.get_element(element)
        if result is None:
            print(f"Error: Element '{element}' not found in either resource",
                  file=sys.stderr)
            sys.exit(1)
    else:
        result = adapter.get_structure()

    # Render diff
    from ...rendering.diff import render_diff
    render_diff(result, args.format)


def parse_diff_uris(resource: str) -> Tuple[str, str]:
    """Parse left:right from diff resource string.

    Handles complex URIs that may contain colons:
    - Simple: "app.py:backup/app.py" → ("app.py", "backup/app.py")
    - Complex: "mysql://prod/db:mysql://staging/db" → ("mysql://prod/db", "mysql://staging/db")

    Strategy: Look for :// as delimiter between URIs
    """
    # If both sides have ://, split on the : between them
    parts = resource.split('://')
    if len(parts) == 3:  # Format: "scheme://resource:scheme://resource"
        left = f"{parts[0]}://{parts[1].rsplit(':', 1)[0]}"
        right = f"{parts[1].rsplit(':', 1)[1]}://{parts[2]}"
        return left, right

    # Otherwise simple split on first :
    left, right = resource.split(':', 1)
    return left, right
```

### Phase 2: Rendering (Week 2)

**File**: `reveal/rendering/diff.py`

```python
def render_diff(diff_result: Dict[str, Any], format: str = 'text') -> None:
    """Render diff result in specified format.

    Args:
        diff_result: Output from DiffAdapter.get_structure()
        format: 'text', 'json', or 'markdown'
    """
    if format == 'json':
        render_diff_json(diff_result)
    elif format == 'markdown':
        render_diff_markdown(diff_result)
    else:
        render_diff_text(diff_result)


def render_diff_text(diff_result: Dict[str, Any]) -> None:
    """Render diff in human-readable text format."""
    left = diff_result['left']
    right = diff_result['right']
    summary = diff_result['summary']
    details = diff_result['diff']

    # Header
    print(f"\n{'=' * 70}")
    print(f"Structure Diff: {left['uri']} → {right['uri']}")
    print(f"{'=' * 70}\n")

    # Summary
    print("📊 Summary:\n")
    if summary.get('functions'):
        f = summary['functions']
        print(f"  Functions:  +{f['added']} -{f['removed']} ~{f['modified']}")

    if summary.get('classes'):
        c = summary['classes']
        print(f"  Classes:    +{c['added']} -{c['removed']} ~{c['modified']}")

    if summary.get('imports'):
        i = summary['imports']
        print(f"  Imports:    +{i['added']} -{i['removed']}")

    print()

    # Detailed changes
    if details.get('functions'):
        print("🔧 Functions:\n")
        for func in details['functions']:
            if func['type'] == 'added':
                print(f"  + {func['name']}")
                print(f"      [NEW - {func.get('line_count', '?')} lines, "
                      f"complexity {func.get('complexity', '?')}]")
            elif func['type'] == 'removed':
                print(f"  - {func['name']}")
                print(f"      [REMOVED]")
            elif func['type'] == 'modified':
                print(f"  ~ {func['name']}")
                changes = func.get('changes', {})
                if 'signature' in changes:
                    print(f"      Signature: {changes['signature']['old']}")
                    print(f"              → {changes['signature']['new']}")
                if 'complexity' in changes:
                    print(f"      Complexity: {changes['complexity']['old']} "
                          f"→ {changes['complexity']['new']}")
                if 'line_count' in changes:
                    print(f"      Lines: {changes['line_count']['old']} "
                          f"→ {changes['line_count']['new']}")
        print()

    # Classes, imports, etc. - similar pattern
```

### Phase 3: Testing (Week 3)

**File**: `tests/test_diff_adapter.py`

```python
class TestDiffAdapter(unittest.TestCase):
    """Test diff:// adapter."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def test_simple_file_diff(self):
        """Test diffing two Python files."""
        # Create two versions of a file
        v1 = """
def foo():
    return 42

def bar():
    return "hello"
"""
        v2 = """
def foo():
    return 42

def baz():  # bar renamed to baz, different implementation
    return "world"

def new_function():
    return True
"""
        path1 = self.create_file(v1, "v1.py")
        path2 = self.create_file(v2, "v2.py")

        adapter = DiffAdapter(path1, path2)
        result = adapter.get_structure()

        # Verify summary
        self.assertEqual(result['summary']['functions']['added'], 1)  # new_function
        self.assertEqual(result['summary']['functions']['removed'], 1)  # bar
        self.assertGreaterEqual(result['summary']['functions']['modified'], 1)  # baz

    def test_cross_adapter_diff(self):
        """Test diffing different adapter types (file vs ast)."""
        # This tests composition with existing adapters
        pass

    # ... more tests
```

---

## Key Design Decisions

### 1. Composition Over Reimplementation ✅

**Decision**: Use existing adapters to resolve URIs, don't reparse files.

**Rationale**:
- DRY: Existing adapters already parse Python, MySQL, etc.
- Maintainability: Bug fixes in adapters automatically benefit diff
- Extensibility: New adapters (future markdown://, postgres://) work immediately with diff
- Consistency: Same structure format everywhere

**Implementation**: `DiffAdapter._resolve_uri()` calls `get_adapter_class()` and delegates

### 2. Semantic Diff, Not Text Diff ✅

**Decision**: Compare structure (functions, classes, complexity), not line-by-line text.

**Rationale**:
- More meaningful: "Function complexity increased from 3 to 7" vs "line 42 changed"
- Language-agnostic: Works with Python, JavaScript, MySQL schemas, env vars
- Actionable: Developers care about structural changes
- Complements text diff: For line-level changes, use `git diff`

### 3. Two-Level Output (Summary + Details) ✅

**Decision**: Provide both high-level summary and detailed diff.

**Rationale**:
- Progressive disclosure: Quick overview first, drill down if needed
- Terminal-friendly: Summary fits in one screen
- Scriptable: JSON output has both levels for automation

**Example**:
```
Summary: +2 -1 ~3 functions
Details: [List of specific changes with line numbers, signatures, etc.]
```

### 4. Element-Specific Diff Support ✅

**Decision**: Allow diffing individual functions/classes via `/element` syntax.

**Rationale**:
- Focused reviews: "How did handle_request change?"
- Faster: Don't diff entire file if you care about one function
- Consistent with reveal's element extraction pattern

**Example**: `reveal diff://app.py:old.py/handle_request`

---

## Open Questions

### Q1: How to handle different structure schemas?

**Problem**: `env://` returns different structure than `file://` (no functions/classes).

**Options**:
1. **Adapter-specific diff logic**: Check adapter type and use custom diff
2. **Generic dict diff**: Diff any two dicts, report all changes
3. **Hybrid**: Generic for unknown types, specialized for known types

**Recommendation**: **Option 3 (Hybrid)**
- Known types (file structures): Use semantic diff (functions, classes, etc.)
- Unknown types: Fall back to generic dict diff
- Provides best experience without limiting compatibility

### Q2: How to diff directories?

**Syntax**: `reveal diff://./src:./backup/src`

**Options**:
1. **Aggregate**: Diff all files, combine results
2. **File-by-file**: Show which files added/removed/modified, then diff each
3. **Recursive tree diff**: Show tree structure changes

**Recommendation**: **Option 2 (File-by-file)**
```
Directory Diff: ./src → ./backup/src

Files:
  + models/user.py        [NEW]
  - deprecated/old.py     [REMOVED]
  ~ handlers/api.py       [MODIFIED - 3 functions changed]

Use: reveal diff://./src/handlers/api.py:./backup/src/handlers/api.py
```

### Q3: Git integration depth?

**Options**:
1. **Minimal**: Support `diff://file:git:HEAD:file` by shelling out to `git show`
2. **Deep**: Parse git refs, handle branches, commits, etc. directly
3. **Delegated**: Create separate `git://` adapter

**Recommendation**: **Option 1 (Minimal for v0.30.0, Option 3 for v0.31.0)**
- v0.30.0: Basic git support via shell commands (MVP)
- v0.31.0: Full `git://` adapter with time-travel (`git://HEAD~5:file.py`)

---

## Success Metrics

**Must Have (v0.30.0)**:
- ✅ Diff two local files: `diff://app.py:backup/app.py`
- ✅ Diff environment vars: `diff://env://:env://production`
- ✅ Show summary (added/removed/modified counts)
- ✅ Show detailed function/class changes
- ✅ JSON output for scripting
- ✅ Element-specific diff: `diff://a.py:b.py/function_name`
- ✅ 80%+ test coverage

**Nice to Have (v0.30.0)**:
- Directory diff support
- Basic git revision support
- Markdown output format

**Future (v0.31.0+)**:
- Time-travel: `diff://time:file:@2025-01:file:@2025-12`
- Cross-repository: `diff://git://repo1:git://repo2`
- Schema migration reports: `diff://mysql://v1:mysql://v2`

---

## Timeline

**Week 1 (Jan 6-10)**: Core engine
- DiffAdapter class
- Structure diff algorithm
- URI parsing and resolution
- Basic function/class/import diffing

**Week 2 (Jan 13-17)**: Rendering & UX
- Text rendering with colors
- JSON output
- Markdown output
- Error handling

**Week 3 (Jan 20-24)**: Testing & Polish
- Comprehensive test suite (80%+ coverage)
- Documentation updates
- Examples and use cases
- Performance optimization

**Week 4 (Jan 27-31)**: Integration & Release
- Integration with existing CLI
- Cross-adapter testing
- Release notes
- v0.30.0 launch

---

## Related Work

**Existing Tools**:
- `diff` / `git diff`: Line-by-line text comparison (complementary, not competitive)
- `diffoscope`: Deep binary/package comparison (different domain)
- `jsondiff`: JSON-specific diffing (similar concept, narrower scope)

**Differentiation**: Reveal's `diff://` is **semantic** and **composable**:
- Understands code structure (not just text)
- Works with any adapter (files, DBs, envs, etc.)
- Foundation for powerful composition (`diff://time:markdown://...`)

---

## Next Steps

1. **Review this design** with Scott
2. **Prototype** core `DiffAdapter` class
3. **Implement** function diff algorithm
4. **Test** with real-world examples
5. **Iterate** based on usage

---

**End of Design Document**
