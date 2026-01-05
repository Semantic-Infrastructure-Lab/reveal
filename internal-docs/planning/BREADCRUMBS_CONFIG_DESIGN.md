# Breadcrumbs Configuration Design

**Date:** 2026-01-05
**Session:** infernal-omega-0105
**Status:** Design phase
**Priority:** HIGH (user-requested feature)

---

## Problem Statement

Currently, breadcrumbs (navigation hints) are always printed and cannot be disabled. Users need the ability to:
1. Disable breadcrumbs globally (for automation/scripting)
2. Enable/disable per-project
3. Override via CLI or environment variables

**Current behavior**: Breadcrumbs always print unconditionally

**Desired behavior**: Breadcrumbs respect config layers with proper defaults

---

## Design

### 1. Config Structure

Add a `display` section to reveal configuration:

```yaml
# .reveal.yaml or ~/.config/reveal/config.yaml
display:
  breadcrumbs: true  # Default: true (preserve existing behavior)
```

**Rationale**:
- Groups display-related settings for future expansion
- Clear, self-documenting config structure
- Follows common config patterns

### 2. Config Layer Support

Breadcrumbs config should respect all config layers:

| Layer | Priority | Example |
|-------|----------|---------|
| CLI | 1 (highest) | `--no-breadcrumbs` flag |
| Environment | 2 | `REVEAL_BREADCRUMBS=0` |
| Project config | 3 | `.reveal.yaml` in project |
| User config | 4 | `~/.config/reveal/config.yaml` |
| System config | 5 | `/etc/reveal/config.yaml` |
| Built-in default | 6 (lowest) | `true` |

### 3. Implementation Changes

#### 3.1 Config Module (`reveal/config.py`)

Add method to RevealConfig class:

```python
def is_breadcrumbs_enabled(self) -> bool:
    """Check if breadcrumbs are enabled.

    Returns:
        True if breadcrumbs should be displayed (default: True)
    """
    display_config = self._config.get('display', {})
    return display_config.get('breadcrumbs', True)  # Default: True
```

#### 3.2 Environment Variable Support

Add to `_load_from_env()` method:

```python
# In _load_from_env() method
if 'REVEAL_BREADCRUMBS' in os.environ:
    value = os.getenv('REVEAL_BREADCRUMBS')
    if 'display' not in config:
        config['display'] = {}
    config['display']['breadcrumbs'] = value not in ('0', 'false', 'False', 'no', 'No')
```

#### 3.3 CLI Argument

Add to argument parser (`reveal/cli/parser.py`):

```python
parser.add_argument(
    '--no-breadcrumbs',
    action='store_true',
    help='Disable breadcrumb navigation hints'
)
```

Handle in CLI overrides:

```python
if args.no_breadcrumbs:
    cli_overrides['display'] = {'breadcrumbs': False}
```

#### 3.4 Breadcrumbs Module (`reveal/utils/breadcrumbs.py`)

Modify `print_breadcrumbs()` signature:

```python
def print_breadcrumbs(context, path, file_type=None, config=None, **kwargs):
    """Print navigation breadcrumbs with reveal command suggestions.

    Args:
        context: 'structure', 'element', 'metadata', 'typed'
        path: File or directory path
        file_type: Optional file type for context-specific suggestions
        config: Optional RevealConfig instance (if None, loads default)
        **kwargs: Additional context (element_name, line_count, etc.)
    """
    # Check if breadcrumbs are enabled
    if config is None:
        from reveal.config import RevealConfig
        config = RevealConfig.get()

    if not config.is_breadcrumbs_enabled():
        return  # Exit early if disabled

    # ... existing breadcrumb printing logic
```

#### 3.5 Display Modules

Update all call sites to pass config:

**reveal/display/metadata.py:**
```python
def show_metadata(analyzer: FileAnalyzer, output_format: str, config=None):
    # ... existing code
    if config is None:
        from reveal.config import RevealConfig
        config = RevealConfig.get(start_path=Path(meta['path']).parent)

    print_breadcrumbs('metadata', meta['path'], config=config)
```

**reveal/display/element.py:**
```python
def extract_element(analyzer: FileAnalyzer, element: str, output_format: str, config=None):
    # ... existing code
    if config is None:
        from reveal.config import RevealConfig
        config = RevealConfig.get(start_path=Path(path).parent)

    print_breadcrumbs('element', path, file_type=file_type, config=config,
                     element_name=name, line_count=line_count, line_start=line_start)
```

**reveal/display/structure.py:**
```python
def show_structure(analyzer: FileAnalyzer, output_format: str, args=None):
    # Load config at top of function
    config = RevealConfig.get(start_path=Path(analyzer.file_path).parent)

    # ... existing code

    # Pass config to breadcrumbs calls
    print_breadcrumbs("typed", file_path, file_type=file_type, config=config)
    # ...
    print_breadcrumbs('structure', path, file_type=file_type, config=config)
```

### 4. Backward Compatibility

**Preserved**:
- ✅ Default behavior unchanged (breadcrumbs enabled)
- ✅ No breaking changes to existing configs
- ✅ Optional `config` parameter (defaults to loading if not provided)

**New capabilities**:
- ✅ Disable via config file
- ✅ Disable via environment variable
- ✅ Disable via CLI flag

---

## Usage Examples

### Example 1: Disable Globally for User

```bash
# ~/.config/reveal/config.yaml
display:
  breadcrumbs: false
```

### Example 2: Enable for Specific Project

```yaml
# /project/.reveal.yaml
display:
  breadcrumbs: true  # Override user config
```

### Example 3: Disable via CLI

```bash
reveal main.py --no-breadcrumbs
```

### Example 4: Disable via Environment

```bash
export REVEAL_BREADCRUMBS=0
reveal main.py
```

### Example 5: Check Current Config

```bash
# View resolved config (includes display settings)
reveal config  # (would require adding config dump command)
```

---

## Testing Strategy

### Unit Tests

1. **Config loading** (`tests/test_config.py`):
   - Test default breadcrumbs=true
   - Test user config override
   - Test project config override
   - Test environment variable
   - Test CLI override
   - Test config layer precedence

2. **Breadcrumbs behavior** (`tests/test_breadcrumbs.py`):
   - Test breadcrumbs print when enabled
   - Test breadcrumbs skip when disabled
   - Test config=None fallback behavior

3. **Display integration** (`tests/test_display_*.py`):
   - Test show_metadata with breadcrumbs enabled/disabled
   - Test extract_element with breadcrumbs enabled/disabled
   - Test show_structure with breadcrumbs enabled/disabled

### Integration Tests

```bash
# Test CLI flag
reveal main.py > output.txt
grep "Next:" output.txt  # Should find breadcrumbs

reveal main.py --no-breadcrumbs > output.txt
grep "Next:" output.txt  # Should NOT find breadcrumbs

# Test environment variable
REVEAL_BREADCRUMBS=0 reveal main.py > output.txt
grep "Next:" output.txt  # Should NOT find breadcrumbs

# Test config file
echo "display:\n  breadcrumbs: false" > .reveal.yaml
reveal main.py > output.txt
grep "Next:" output.txt  # Should NOT find breadcrumbs
```

---

## Implementation Plan

### Phase 1: Config Infrastructure (30 min)
- [ ] Add `is_breadcrumbs_enabled()` to RevealConfig
- [ ] Add environment variable support in `_load_from_env()`
- [ ] Add CLI argument `--no-breadcrumbs`
- [ ] Add unit tests for config behavior

### Phase 2: Breadcrumbs Module (15 min)
- [ ] Update `print_breadcrumbs()` signature
- [ ] Add config check and early return
- [ ] Add unit tests for enabled/disabled behavior

### Phase 3: Display Integration (30 min)
- [ ] Update `show_metadata()` to pass config
- [ ] Update `extract_element()` to pass config
- [ ] Update `show_structure()` to pass config
- [ ] Update all breadcrumbs call sites

### Phase 4: Testing (30 min)
- [ ] Run full test suite
- [ ] Add integration tests
- [ ] Manual testing of all config layers
- [ ] Verify backward compatibility

### Phase 5: Documentation (15 min)
- [ ] Update README with breadcrumbs config
- [ ] Update CHANGELOG
- [ ] Add example configs

**Total Estimated Time**: 2 hours

---

## Future Enhancements

Once basic enable/disable is working, consider:

1. **Granular control**:
   ```yaml
   display:
     breadcrumbs:
       structure: true
       element: true
       metadata: false
       typed: true
   ```

2. **Custom breadcrumb templates**:
   ```yaml
   display:
     breadcrumbs:
       enabled: true
       template: "minimal"  # or "full", "custom"
   ```

3. **Context-specific control**:
   ```yaml
   display:
     breadcrumbs:
       enabled: true
       python: true   # Show for Python files
       markdown: false  # Hide for Markdown
   ```

---

## Open Questions

1. **CLI flag naming**: `--no-breadcrumbs` vs `--hide-breadcrumbs` vs `--quiet`?
   - **Decision**: `--no-breadcrumbs` (matches config naming)

2. **Config section naming**: `display` vs `output` vs `breadcrumbs`?
   - **Decision**: `display` (future-proof for other display settings)

3. **Default behavior**: Keep enabled or change to disabled?
   - **Decision**: Keep enabled (preserve existing behavior, non-breaking)

4. **Scope**: Should this also control other output like file headers?
   - **Decision**: No, start with just breadcrumbs (focused scope)

---

## Related Documents

- `BREADCRUMB_IMPROVEMENTS_2026.md` - Feature enhancements roadmap
- `../../ROADMAP.md` - Project roadmap
- `reveal/config.py` - Config implementation
- `reveal/utils/breadcrumbs.py` - Breadcrumbs implementation
