# Reveal Code Architecture Analysis

**Date**: 2025-12-12
**Session**: wise-goddess-1212
**Purpose**: Understand large function architecture before refactoring

---

## Large Function Patterns Discovered

### Pattern 1: Dispatcher Functions (Rendering)

**Examples**:
- `render_help` (212 lines)
- `render_python_element` (173 lines)

**Structure**:
```python
def render_X(data, output_format):
    # Early return for JSON
    if output_format == 'json':
        print(json.dumps(data))
        return

    # Detect data type and dispatch
    if 'type_a_marker' in data:
        # Render type A (20-50 lines)
        ...
        return
    elif 'type_b_marker' in data:
        # Render type B (20-50 lines)
        ...
        return
    elif 'type_c_marker' in data:
        # Render type C (20-50 lines)
        ...
        return
    # ... more branches
```

**Why It's Long**: Multiple rendering modes in one function (5-10 branches, each 20-50 lines)

**Best Refactoring Pattern**: **Strategy Pattern**
```python
# Rendering strategies
def _render_help_list_mode(data):
    """Render help:// topic list."""
    ...

def _render_help_static_guide(data):
    """Render static markdown guide."""
    ...

def _render_help_adapter_summary(data):
    """Render adapter summary."""
    ...

def _render_help_section(data):
    """Render help section extraction."""
    ...

def _render_help_adapter_specific(data):
    """Render adapter-specific help."""
    ...

# Main dispatcher
def render_help(data, output_format, list_mode=False):
    """Render help content."""
    if output_format == 'json':
        import json
        print(json.dumps(data, indent=2))
        return

    if list_mode:
        _render_help_list_mode(data)
    elif data.get('type') == 'static_guide':
        _render_help_static_guide(data)
    elif data.get('type') == 'adapter_summary':
        _render_help_adapter_summary(data)
    elif data.get('type') == 'help_section':
        _render_help_section(data)
    else:
        _render_help_adapter_specific(data)
```

**Impact**: 212 → ~40 lines for main function, 5 focused helper functions (~30 lines each)

---

### Pattern 2: Sequential Analyzer Functions

**Examples**:
- `_get_module_analysis` (118 lines)
- `_run_doctor` (226 lines)

**Structure**:
```python
def _analyze_thing(input):
    """Analyze something complex."""
    result = {}

    # Analysis section 1 (20-40 lines)
    result['section1'] = ...

    # Analysis section 2 (20-40 lines)
    result['section2'] = ...

    # Analysis section 3 (20-40 lines)
    result['section3'] = ...

    # Analysis section 4 (20-40 lines)
    result['section4'] = ...

    return result
```

**Why It's Long**: Sequential data gathering (4-6 sections, each 20-40 lines)

**Best Refactoring Pattern**: **Extract Sequential Steps**
```python
def _analyze_imports(module):
    """Extract import information."""
    ...

def _analyze_functions(module):
    """Extract function information."""
    ...

def _analyze_classes(module):
    """Extract class information."""
    ...

def _analyze_attributes(module):
    """Extract module attributes."""
    ...

def _get_module_analysis(module_name):
    """Analyze Python module."""
    module = importlib.import_module(module_name)

    return {
        'name': module_name,
        'imports': _analyze_imports(module),
        'functions': _analyze_functions(module),
        'classes': _analyze_classes(module),
        'attributes': _analyze_attributes(module),
        'metadata': _get_module_metadata(module),
    }
```

**Impact**: 118 → ~20 lines for main function, 5 focused helper functions (~20-30 lines each)

---

### Pattern 3: CLI Argument Parser (Already Refactored ✅)

**Example**: `_main_impl` (was 246 lines, now 40 lines)

**Original Structure**:
```python
def _main_impl():
    # Argument parser setup (70 lines)
    parser = argparse.ArgumentParser(...)
    parser.add_argument(...)  # x50

    # Argument validation (30 lines)
    args = parser.parse_args()
    # validation logic

    # Dispatch logic (146 lines)
    if args.special_mode_1:
        # handler 1 (20 lines)
    if args.special_mode_2:
        # handler 2 (30 lines)
    if args.stdin:
        # handler 3 (40 lines)
    # ... etc
```

**Refactored Structure**:
```python
def _create_argument_parser():
    """Create and configure argument parser."""
    ...

def _validate_navigation_args(args):
    """Validate navigation arguments."""
    ...

def _handle_special_mode_X():
    """Handle special mode X."""
    ...

def _main_impl():
    """Main CLI entry point."""
    parser = _create_argument_parser()
    args = parser.parse_args()
    _validate_navigation_args(args)

    # Dispatch to handlers
    if args.list_supported:
        _handle_list_supported()
    # ... etc
```

**Impact**: ✅ 246 → 40 lines DONE

---

## Architectural Insights

### Common Anti-Pattern: "Kitchen Sink Functions"

**Characteristics**:
- 100-250 lines
- Multiple responsibilities
- Low cohesion (many unrelated things)
- High coupling (hard to test)

**Root Causes**:
1. **Feature creep**: New modes/options added inline instead of extracted
2. **Copy-paste**: Similar rendering logic duplicated across branches
3. **Convenience**: "It's easier to add it here than refactor"

**Example - `render_help`**:
- Started as simple help renderer (~50 lines)
- Added list mode (+30 lines)
- Added static guides (+20 lines)
- Added adapter summary (+25 lines)
- Added help sections (+40 lines)
- Added workflows, anti-patterns, try-now sections (+50 lines)
- **Total**: 212 lines of accidental complexity

### Recommended Architecture: **Composition Over Nesting**

**Instead of**:
```python
def do_everything(data, options):
    if mode_a:
        if submode_1:
            # 20 lines
        elif submode_2:
            # 20 lines
    elif mode_b:
        if submode_3:
            # 20 lines
        # ... 10 more branches
```

**Do this**:
```python
def do_thing_a1(data):
    # 20 lines

def do_thing_a2(data):
    # 20 lines

def do_everything(data, options):
    handlers = {
        ('mode_a', 'submode_1'): do_thing_a1,
        ('mode_a', 'submode_2'): do_thing_a2,
        # ... etc
    }

    handler = handlers.get((data.mode, data.submode))
    if handler:
        handler(data)
```

---

## Refactoring Priority Matrix

| Function | Lines | Depth | Priority | Effort | Impact |
|----------|-------|-------|----------|--------|--------|
| `_main_impl` | ~~246~~ 40 | ~~5~~ 2 | ✅ DONE | - | HIGH |
| `_run_doctor` | 226 | 5 | **HIGH** | 3h | HIGH |
| `render_help` | 212 | 5 | **HIGH** | 2h | HIGH |
| `render_python_element` | 173 | 6 | **MEDIUM** | 2h | MEDIUM |
| `_get_module_analysis` | 118 | 5 | **MEDIUM** | 1h | MEDIUM |
| `get_help` (various) | 158 | 0 | LOW | 1h | LOW |

**Rationale**:
- **Depth > 5**: Hard to understand, high cyclomatic complexity
- **Lines > 200**: Hard to maintain, likely multiple responsibilities
- **get_help depth 0**: Mostly static text, low priority

---

## Recommended Refactoring Strategy

### Phase 1: CLI Entry Point ✅ DONE
- [x] Refactor `_main_impl` (246 → 40 lines)
- [x] Extract argument parser creation
- [x] Extract special mode handlers
- [x] Extract dispatch logic

**Result**: 206 lines saved, depth reduced from 5 to 2

### Phase 2: Rendering Dispatchers (4 hours)
- [ ] Refactor `render_help` (212 → ~40 lines)
  - Extract `_render_help_list_mode`
  - Extract `_render_help_static_guide`
  - Extract `_render_help_adapter_summary`
  - Extract `_render_help_section`
  - Extract `_render_help_adapter_specific`

- [ ] Refactor `render_python_element` (173 → ~40 lines)
  - Extract `_render_package_list`
  - Extract `_render_imports_list`
  - Extract `_render_doctor_results`
  - Extract `_render_bytecode_check`
  - Extract `_render_env_details`

**Expected Impact**: ~300 lines reduced, 10 new focused functions

### Phase 3: Python Adapter Analysis (4 hours)
- [ ] Refactor `_run_doctor` (226 → ~40 lines)
  - Extract `_check_bytecode_issues`
  - Extract `_check_import_shadowing`
  - Extract `_check_path_conflicts`
  - Extract `_check_package_conflicts`
  - Extract `_check_venv_issues`

- [ ] Refactor `_get_module_analysis` (118 → ~30 lines)
  - Extract `_analyze_imports`
  - Extract `_analyze_functions`
  - Extract `_analyze_classes`
  - Extract `_analyze_attributes`

**Expected Impact**: ~270 lines reduced, 9 new focused functions

### Phase 4: Polish (deferred)
- [ ] Refactor various `get_help` functions (low priority - mostly text)

---

## Quality Score Projection

**Before** (baseline):
- Quality Score: 22/100
- Huge functions (>100 lines): 6 (in main analysis scope)
- Total lines in huge functions: ~1,150

**After Phase 1** (completed):
- Huge functions reduced: 6 → 5
- Lines saved: 206
- Quality Score: ~30/100 (estimated)

**After Phase 2** (rendering dispatchers):
- Huge functions reduced: 5 → 3
- Lines saved: 506 total
- Quality Score: ~50/100 (estimated)

**After Phase 3** (Python adapter):
- Huge functions reduced: 3 → 1
- Lines saved: 776 total
- Quality Score: ~75/100 (estimated)

**Final Target**:
- Quality Score: ≥75/100
- Huge functions: ≤1 (only get_help text content)
- All functions <100 lines (except static content)
- Average function length: <30 lines

---

## Testing Strategy

### Per-Phase Testing
After each refactoring:
1. **Unit tests**: `pytest tests/ -v`
2. **Smoke tests**:
   ```bash
   reveal --help
   reveal help://
   reveal python://
   reveal reveal/main.py --outline
   reveal 'ast://reveal/?complexity>5'
   ```
3. **Dogfooding**: Use reveal to analyze itself
   ```bash
   reveal reveal/main.py --check
   tia quality scan reveal/
   ```

### Regression Prevention
- Compare output before/after:
  ```bash
  reveal reveal/main.py > /tmp/before.txt
  # ... refactor ...
  reveal reveal/main.py > /tmp/after.txt
  diff /tmp/before.txt /tmp/after.txt  # Should be empty
  ```

---

## Next Steps

1. **Complete Phase 2**: Refactor rendering dispatchers
   - Start with `render_help` (clearest pattern)
   - Apply same pattern to `render_python_element`
   - Test thoroughly

2. **Complete Phase 3**: Refactor Python adapter analysis
   - Start with `_get_module_analysis` (simpler)
   - Then tackle `_run_doctor` (most complex)
   - Test with `reveal python://` commands

3. **Measure Impact**: Run final quality scan
   - `tia quality scan reveal/ --save`
   - Compare before/after metrics
   - Document improvements

4. **Create PR**: Submit for review
   - Clear commit messages
   - Before/after metrics
   - Testing evidence

---

## Conclusion

**Pattern Recognition**: The huge functions fall into 3 clear patterns:
1. ✅ **CLI Dispatchers** (argument parsing + routing) - DONE
2. **Rendering Dispatchers** (format detection + rendering branches)
3. **Sequential Analyzers** (data gathering steps)

**Best Practice**: Extract functions following **Single Responsibility Principle**
- Each function does ONE thing
- Functions are <50 lines
- Clear, descriptive names
- Easy to test in isolation

**Current Progress**: 1 of 3 patterns complete (246 lines saved, depth 5→2 reduced)

**Remaining Work**: 2 patterns, ~8 hours estimated, ~570 lines to save

**Projected Quality Improvement**: 22/100 → 75/100 (3.4x improvement)
