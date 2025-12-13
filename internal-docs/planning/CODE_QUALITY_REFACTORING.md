# Reveal Code Quality Refactoring Plan

**Date**: 2025-12-12
**Session**: wise-goddess-1212
**Goal**: Reduce huge/long/complex functions to improve maintainability

---

## Current State

**Quality Score**: 22/100
- 🚨 6 huge functions (>100 lines)
- 📏 6 long functions (>50 lines)
- 🧠 6 complex functions (>10 complexity)

**Target**: 75/100 (eliminate all huge functions)

---

## Functions to Refactor

### main.py

1. **`_main_impl`** - 246 lines, depth 5
   - Lines 1183-1428
   - Purpose: CLI argument parsing and dispatch
   - **Refactoring Strategy**: Extract argument groups into builder functions

2. **`render_help`** - 212 lines, depth 5
   - Lines 663-874
   - Purpose: Render help:// adapter output
   - **Refactoring Strategy**: Extract rendering sections into helper functions

3. **`render_python_element`** - 173 lines, depth 6
   - Lines 911-1083
   - Purpose: Render python:// element details
   - **Refactoring Strategy**: Extract rendering logic per element type

### adapters/python.py

4. **`_get_module_analysis`** - 118 lines, depth 5
   - Purpose: Analyze Python module details
   - **Refactoring Strategy**: Extract analysis sections (imports, functions, classes, etc.)

5. **`_run_doctor`** - 149 lines, depth 5
   - Purpose: Python environment diagnostics
   - **Refactoring Strategy**: Extract diagnostic checks into separate functions

6. **`get_help`** - 158 lines, depth 0
   - Purpose: Generate help text for python:// adapter
   - **Refactoring Strategy**: Keep as-is (it's mostly text content, depth 0)

---

## Refactoring Approach

### Principle: Extract Without Changing Behavior

**Rules**:
1. No functional changes - pure refactoring
2. Extract functions with clear, descriptive names
3. Keep extracted functions in same file (for now)
4. Maintain all existing tests
5. Run tests after each major extraction

### Pattern: Bottom-Up Extraction

1. Identify logical sections within huge function
2. Extract smallest coherent units first
3. Build up to larger extractions
4. Reduce nesting depth

---

## Implementation Plan

### Phase 1: main.py - `_main_impl` (246 → <100 lines)

**Current Structure**:
- Lines 1185-1230: Argument parser setup (~45 lines)
- Lines 1231-1280: More argument setup (~50 lines)
- Lines 1281-1350: Dispatch logic (~70 lines)
- Lines 1351-1428: More dispatch (~80 lines)

**Extractions**:

```python
def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(...)
    _add_basic_arguments(parser)
    _add_output_arguments(parser)
    _add_pattern_detection_arguments(parser)
    _add_display_arguments(parser)
    return parser

def _add_basic_arguments(parser):
    """Add basic positional and informational arguments."""
    # --version, --list-supported, --agent-help, etc.

def _add_output_arguments(parser):
    """Add output formatting arguments."""
    # --format, --copy, --stdin, etc.

def _add_pattern_detection_arguments(parser):
    """Add pattern detection (linting) arguments."""
    # --check, --select, --ignore, --rules, --explain

def _add_display_arguments(parser):
    """Add display control arguments."""
    # --outline, --head, --tail, --range, --depth, etc.

def _handle_special_modes(args) -> bool:
    """Handle special modes that exit early. Returns True if handled."""
    # --agent-help, --list-supported, --rules, --explain

def _handle_uri_mode(args):
    """Handle URI scheme mode (help://, python://, ast://, etc.)"""

def _handle_file_mode(args):
    """Handle file/directory mode."""

def _main_impl():
    """Main CLI entry point."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    if _handle_special_modes(args):
        return

    if args.path and '://' in args.path:
        _handle_uri_mode(args)
    elif args.stdin:
        _handle_stdin_mode(args)
    else:
        _handle_file_mode(args)
```

**Expected Reduction**: 246 → 40 lines

---

### Phase 2: main.py - `render_help` (212 → <100 lines)

**Current Structure**:
- Adapter listing
- Topic listing
- Element details
- Examples
- Guide text

**Extractions**:

```python
def _render_adapter_list(adapters: List[str], output_format: str):
    """Render list of available adapters."""

def _render_topic_list(topics: List[str], output_format: str):
    """Render list of available topics."""

def _render_guide_text(guide_data: Dict, output_format: str):
    """Render guide text content."""

def render_help(data: Dict[str, Any], output_format: str, list_mode: bool = False):
    """Render help:// adapter output."""
    if list_mode:
        _render_adapter_list(data['adapters'], output_format)
    elif 'topics' in data:
        _render_topic_list(data['topics'], output_format)
    elif 'guide' in data:
        _render_guide_text(data['guide'], output_format)
    else:
        _render_element_help(data, output_format)
```

**Expected Reduction**: 212 → 60 lines

---

### Phase 3: main.py - `render_python_element` (173 → <100 lines)

**Current Structure**:
- Overview rendering
- Packages rendering
- Package details
- Environment details
- Imports rendering
- Venv rendering
- Debug/bytecode rendering

**Extractions**:

```python
def _render_python_overview(data: Dict, output_format: str):
    """Render Python environment overview."""

def _render_python_packages(data: Dict, output_format: str):
    """Render package list or details."""

def _render_python_env(data: Dict, output_format: str):
    """Render Python environment details."""

def _render_python_debug(data: Dict, output_format: str):
    """Render debug information (bytecode, etc.)."""

def render_python_element(data: Dict[str, Any], output_format: str):
    """Render python:// element details."""
    element_type = data.get('element_type')

    renderers = {
        'overview': _render_python_overview,
        'packages': _render_python_packages,
        'env': _render_python_env,
        'debug': _render_python_debug,
        # etc.
    }

    renderer = renderers.get(element_type)
    if renderer:
        renderer(data, output_format)
    else:
        # fallback
```

**Expected Reduction**: 173 → 40 lines

---

### Phase 4: adapters/python.py - `_get_module_analysis` (118 → <100 lines)

**Extractions**:

```python
def _analyze_imports(module) -> Dict:
    """Extract import information from module."""

def _analyze_functions(module) -> List[Dict]:
    """Extract function information from module."""

def _analyze_classes(module) -> List[Dict]:
    """Extract class information from module."""

def _get_module_analysis(module_name: str) -> Dict:
    """Analyze a Python module."""
    module = importlib.import_module(module_name)

    return {
        'name': module_name,
        'imports': _analyze_imports(module),
        'functions': _analyze_functions(module),
        'classes': _analyze_classes(module),
        # etc.
    }
```

**Expected Reduction**: 118 → 30 lines

---

### Phase 5: adapters/python.py - `_run_doctor` (149 → <100 lines)

**Extractions**:

```python
def _check_bytecode_issues() -> List[Dict]:
    """Check for stale .pyc files."""

def _check_import_shadowing() -> List[Dict]:
    """Check for import shadowing issues."""

def _check_path_conflicts() -> List[Dict]:
    """Check for sys.path conflicts."""

def _run_doctor() -> Dict:
    """Run Python environment diagnostics."""
    issues = []
    issues.extend(_check_bytecode_issues())
    issues.extend(_check_import_shadowing())
    issues.extend(_check_path_conflicts())

    return {
        'status': 'healthy' if not issues else 'issues_found',
        'issues': issues
    }
```

**Expected Reduction**: 149 → 40 lines

---

## Testing Strategy

### Before Each Refactoring

1. Run existing tests: `pytest tests/`
2. Capture baseline output: `reveal reveal/main.py > /tmp/before.txt`

### After Each Refactoring

1. Run tests again: `pytest tests/`
2. Compare output: `reveal reveal/main.py > /tmp/after.txt && diff /tmp/before.txt /tmp/after.txt`
3. Test specific functionality:
   ```bash
   reveal --help
   reveal help://
   reveal python://
   reveal ast://reveal/?complexity>5
   reveal reveal/main.py --check
   ```

### Full Validation

After all refactorings:
```bash
# Run full test suite
pytest tests/ -v

# Quality scan
tia quality scan /home/scottsen/src/projects/reveal/external-git/reveal

# Self-dogfooding
reveal reveal/ --check
reveal reveal/main.py --outline
reveal 'ast://reveal/?lines>100'
```

---

## Success Criteria

**Before**:
- Quality Score: 22/100
- Huge functions: 6
- Long functions: 6
- Complex functions: 6

**After** (Target):
- Quality Score: ≥75/100
- Huge functions: 0
- Long functions: ≤3 (only if unavoidable)
- Complex functions: ≤3

**Additional Goals**:
- All tests pass
- No behavior changes
- Improved readability
- Easier to test individual components

---

## Risk Mitigation

1. **Work in a branch**: Create `refactor/code-quality` branch
2. **Commit after each phase**: Allows easy rollback
3. **Keep original functions**: Comment out, don't delete (first pass)
4. **Test incrementally**: Don't wait until end
5. **Use reveal to validate**: Dogfood the tool during refactoring

---

## Execution Timeline

**Phase 1**: _main_impl refactoring (2 hours)
**Phase 2**: render_help refactoring (1 hour)
**Phase 3**: render_python_element refactoring (1 hour)
**Phase 4**: _get_module_analysis refactoring (30 min)
**Phase 5**: _run_doctor refactoring (30 min)
**Testing & Validation**: 1 hour

**Total**: ~6 hours

---

## Next Steps

1. Create git branch: `git checkout -b refactor/code-quality`
2. Start with Phase 1 (_main_impl)
3. Test after each extraction
4. Commit after each phase
5. Run full quality scan at end
6. Create PR for review
