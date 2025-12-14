# Root Cause Analysis: Three Markdown Support Bugs

**Date**: 2025-12-11
**Session**: magenta-glow-1211
**Analysis By**: TIA (Chief Semantic Agent)

---

## Executive Summary

Three bugs in reveal's markdown support shared a common pattern: **feature implementation without considering user intent and lacking comprehensive integration testing**. All three issues existed at different layers (data extraction, UI rendering, documentation) but stemmed from the same underlying problem: insufficient consideration of the complete user experience.

---

## Issue #1: `--links` Text Output Showed Headings

### What Happened

When users ran `reveal README.md --links`, they got headings AND links instead of JUST links.

**Expected Behavior**: Show only what was explicitly requested (links)
**Actual Behavior**: Show headings plus links
**Severity**: HIGH - Breaks principle of least surprise

### Root Cause Analysis

#### Layer 1: Design Flaw (Core Issue)

The `MarkdownAnalyzer.get_structure()` method had this logic:

```python
result = {}
# Always extract headings
result['headings'] = self._extract_headings()

if extract_links:
    result['links'] = self._extract_links(...)
```

**Design Assumption**: "Headings are always useful baseline information, like a table of contents."

**Why This is Wrong**:
- Violates **separation of concerns**: Default behavior vs. feature flags
- Contradicts **user intent**: `--links` means "show me links", not "show me links AND headings"
- Inconsistent with **mental model**: Other tools (grep, find, jq) filter to what you ask for

#### Layer 2: Missing Specification

No specification document existed defining:
- What should `reveal doc.md` show? (Answer: headings only)
- What should `reveal doc.md --links` show? (Answer: links only)
- What should `reveal doc.md --links --code` show? (Answer: links + code)

**Developer Context**: The original developer likely thought "users always want to see headings for context" without testing the actual UX.

#### Layer 3: Test Gap

The existing tests verified:
- ✅ `get_structure(extract_links=True)` returns links in structure
- ❌ `get_structure(extract_links=True)` ONLY returns links (no headings)

**Test That Would Have Caught This**:
```python
def test_links_only_when_requested(self):
    """When extract_links=True, headings should NOT be in structure."""
    structure = analyzer.get_structure(extract_links=True)
    self.assertNotIn('headings', structure)  # MISSING TEST
    self.assertIn('links', structure)
```

### Why It Persisted

1. **JSON format masked the problem**: JSON output shows raw structure, so both headings and links appeared. Users could filter with jq, so less noticeable.
2. **Text format exposed it**: Text renderer iterates ALL keys in structure dict, making the bug obvious.
3. **Feature testing, not behavior testing**: Tests checked "does it extract links?" not "does it extract ONLY links when requested?"

### Lessons Learned

1. **Design Principle**: Feature flags should be additive to a minimal default, not subtractive from a maximal default
2. **Test Principle**: Test the ABSENCE of things, not just presence
3. **UX Principle**: Tools should filter to what users explicitly request

---

## Issue #3: No `--outline` Support for Markdown

### What Happened

`reveal code.py --outline` worked beautifully with hierarchical tree rendering, but `reveal README.md --outline` wasn't implemented.

**Expected Behavior**: Hierarchical tree view of markdown headings
**Actual Behavior**: Feature not implemented / not tested
**Severity**: MEDIUM - Missing feature, not broken behavior

### Root Cause Analysis

#### Layer 1: Implementation Gap

The `build_hierarchy()` function in `main.py` assumed **line-range-based nesting**:

```python
def build_hierarchy(structure):
    # Assumes items have 'line' and 'line_end' for range detection
    if candidate_start < item_start and candidate_end >= item_end:
        parent = candidate  # Parent contains child
```

**Works For**: Code (functions, classes have start/end lines)
**Doesn't Work For**: Markdown (headings only have single line + level field)

**Why The Gap Existed**:
- Outline feature was built for **code analysis use case**
- Markdown support was added **later** without extending outline mode
- No cross-feature testing (outline + markdown)

#### Layer 2: Generalization Failure

The hierarchy building logic was **tightly coupled** to the code analysis domain:
- Used line ranges to detect parent/child relationships
- Assumed hierarchical nesting means "one thing contains another"
- Didn't consider **level-based hierarchy** (H1 → H2 → H3)

**Better Design**: Abstract hierarchy builder that accepts different nesting strategies:
- Line-range strategy (for code)
- Level strategy (for markdown)
- Depth strategy (for nested data structures)

#### Layer 3: Feature Discoverability

Even if markdown had outline support, how would users discover it?
- No examples in `--help` showing markdown + outline
- No mention in documentation
- No integration tests covering this combination

### Why It Persisted

1. **Code-centric development**: Reveal started as a code analysis tool, markdown was secondary
2. **Lack of "feature matrix" thinking**: No systematic testing of feature combinations
3. **No user feedback loop**: Users didn't know to ask for it because they didn't know it was missing

### Lessons Learned

1. **Design Principle**: Build abstractions that generalize across domains, not implementations tied to specific use cases
2. **Feature Matrix Principle**: Test combinations (every feature × every file type)
3. **Documentation Principle**: Feature parity should be explicit ("outline works with: Python, JS, Markdown")

---

## Issue #2: Missing `help://markdown` Topic

### What Happened

Markdown was fully supported but completely undiscoverable via the `help://` system.

**Expected Behavior**: `reveal help://` lists markdown, `reveal help://markdown` shows guide
**Actual Behavior**: No markdown topic existed
**Severity**: MEDIUM - Discoverability issue, feature worked but hidden

### Root Cause Analysis

#### Layer 1: Integration Gap

The markdown analyzer was implemented without updating the help system:

```python
# adapters/help.py - STATIC_HELP dict
STATIC_HELP = {
    'agent': 'AGENT_HELP.md',
    'python-guide': 'PYTHON_ADAPTER_GUIDE.md',
    # 'markdown': 'MARKDOWN_GUIDE.md'  # MISSING!
}
```

**Why This Happened**:
- Markdown analyzer added to `analyzers/` directory
- Help system lives in `adapters/` directory
- No automated discovery or registration requirement
- No "definition of done" checklist including documentation

#### Layer 2: Documentation Debt

Markdown features were implemented incrementally:
1. Basic heading extraction (initial implementation)
2. Link extraction with filtering (feature addition)
3. Code block extraction (feature addition)
4. Broken link detection (feature addition)

Each addition focused on **functionality** but not **discoverability**. Documentation was never prioritized.

#### Layer 3: Help System Architecture

The help system requires **manual registration**:
- URI adapters (python://, ast://) auto-register via `@register_adapter` decorator
- Static guides must be manually added to `STATIC_HELP` dict
- No validation that all file types have corresponding help topics

**Brittle Process**: Easy to forget, no guardrails

### Why It Persisted

1. **Manual registration**: No automated "you added markdown support, did you document it?" check
2. **Separate directories**: Analyzer code and help system code live in different places
3. **No completion criteria**: Feature was "done" when tests passed, not when documented

### Lessons Learned

1. **Definition of Done**: Feature complete = code + tests + documentation + help integration
2. **Architecture Principle**: Manual registration is a code smell - prefer auto-discovery
3. **Testing Principle**: Integration tests should verify help system reflects all features

---

## Common Patterns Across All Three Issues

### Pattern 1: Feature-Centric vs. User-Centric Development

All three bugs happened because development focused on **"does the feature work?"** instead of **"is the user experience complete?"**

**Feature-Centric**:
- ✅ Markdown analyzer extracts headings
- ✅ Markdown analyzer extracts links
- ✅ Code outline works

**User-Centric**:
- ❓ When I ask for links, do I get ONLY links?
- ❓ Can I view markdown structure hierarchically?
- ❓ How do I discover markdown features?

### Pattern 2: Integration Testing Gap

All three bugs would have been caught by **cross-cutting integration tests**:

```python
# Missing integration test for Issue #1
def test_cli_links_flag_shows_only_links():
    """CLI: reveal file.md --links should show ONLY links"""
    output = run_cli(['reveal', 'test.md', '--links'])
    assert 'Headings' not in output  # WOULD HAVE CAUGHT BUG
    assert 'Links' in output

# Missing integration test for Issue #3
def test_cli_outline_supports_markdown():
    """CLI: reveal file.md --outline should show hierarchy"""
    output = run_cli(['reveal', 'test.md', '--outline'])
    assert '├─' in output  # Tree characters
    assert '└─' in output

# Missing integration test for Issue #2
def test_help_system_covers_all_analyzers():
    """Help system should document all supported file types"""
    supported = list_supported_file_types()  # ['.md', '.py', '.js', ...]
    help_topics = list_help_topics()

    for file_type in supported:
        assert has_help_topic(file_type), f"No help for {file_type}"
```

### Pattern 3: Lack of Behavior Specification

No document existed specifying:
- What should each CLI flag combination produce?
- What is the expected output format for each file type?
- What help topics should exist?

**Result**: Developers made implicit assumptions that diverged from user expectations.

---

## Systemic Issues

### 1. No Feature Matrix Testing

Reveal has:
- **File types**: Python, JavaScript, Markdown, JSON, etc.
- **Features**: --outline, --links, --code, --format json, etc.

**Missing**: Systematic testing of **file type × feature combinations**

Current testing approach:
- ✅ Test each feature independently
- ❌ Test every feature with every applicable file type

### 2. Manual Registration Anti-Pattern

Multiple places require manual registration:
- File analyzers: Auto-registered via `@register` decorator ✅
- Help topics: Manual registration in `STATIC_HELP` dict ❌
- URI adapters: Auto-registered via `@register_adapter` ✅

**Inconsistency**: Some registration is automated, some is manual. The manual ones get forgotten.

### 3. No "Definition of Done" Checklist

When is a feature complete? Current practice:
- ✅ Code written
- ✅ Unit tests pass

**Missing from checklist**:
- ❌ Integration tests added
- ❌ Documentation written
- ❌ Help system updated
- ❌ Examples added to guides
- ❌ Cross-feature compatibility verified

### 4. Output Format Testing Gap

Tests verified **data extraction** (analyzer layer) but not **output rendering** (presentation layer):

```python
# What was tested ✅
structure = analyzer.get_structure(extract_links=True)
assert 'links' in structure

# What wasn't tested ❌
output = render_text(structure)
assert 'Headings' not in output
```

**Gap**: No tests for `main.py` output functions (`_render_text_categories`, `render_outline`)

---

## Recommendations

### Immediate Actions

1. **Add missing integration tests** (included in this PR)
2. **Create feature matrix test suite**
3. **Add output format regression tests**

### Process Improvements

1. **Feature Completion Checklist**:
   ```
   □ Unit tests (analyzer/adapter layer)
   □ Integration tests (CLI layer)
   □ Output format tests (rendering layer)
   □ Help system updated
   □ Documentation written
   □ Examples added
   □ Cross-feature testing
   ```

2. **Automated Help System Validation**:
   ```python
   def test_all_file_types_have_help():
       """Enforce that every supported file type has help documentation."""
       supported = get_supported_file_types()
       for file_type in supported:
           assert has_help_or_guide(file_type)
   ```

3. **Feature Matrix CI Check**:
   - Generate matrix of file types × features
   - Test each applicable combination
   - Fail CI if coverage < 80%

### Architectural Improvements

1. **Unify Registration Pattern**:
   - Move to decorator-based registration for help topics
   - Auto-discover markdown guides in specific directory
   - Remove manual `STATIC_HELP` dict

2. **Separate Output Testing**:
   - Create `tests/test_output_formats.py`
   - Test text, JSON, and grep output for each analyzer
   - Verify format contracts (e.g., "links flag hides headings")

3. **Behavior Specification Documents**:
   - Create `docs/BEHAVIOR_SPEC.md` defining expected outputs
   - Use spec as source of truth for test generation
   - Include examples for every flag combination

---

## Timeline: How These Bugs Were Introduced

### Phase 1: Initial Markdown Support (Unknown Date)
- MarkdownAnalyzer created with basic heading extraction
- Design decision: "always include headings" seemed reasonable
- No text output testing (only data extraction tests)

### Phase 2: Link Extraction Added (Unknown Date)
- `extract_links` flag added
- Feature worked: links were extracted
- Bug introduced: headings still included (but not noticed in JSON output)
- No integration test for "links only" behavior

### Phase 3: Code Outline Feature Added (Unknown Date)
- `--outline` implemented for code files
- Beautiful hierarchical rendering with tree characters
- Markdown not considered (different hierarchy model)
- No feature matrix test covering "outline × markdown"

### Phase 4: Markdown Features Matured (Unknown Date)
- Code block extraction added
- Link filtering added
- Broken link detection added
- Help documentation never prioritized

### Phase 5: Discovery (2025-12-11)
- User (Scott) tested markdown extensively
- Research session `visible-pulsar-1211` documented issues
- Root causes analyzed (this document)
- Fixes implemented in `magenta-glow-1211`

**Time to Discovery**: Unknown, possibly months/years
**Time to Fix**: ~2 hours once root causes understood

---

## Key Takeaway

**These weren't coding bugs - they were process and testing gaps.**

The code worked as written. The issue was that no one specified what "correct" behavior looked like for:
- CLI flag combinations
- Output format filtering
- Feature discoverability

**Solution**: Better specifications, integration testing, and feature completion checklists would have caught all three issues before release.

---

## References

- Research session: `sessions/visible-pulsar-1211/`
- Implementation session: `sessions/magenta-glow-1211/`
- Test file: `tests/test_markdown_analyzer.py`
- Markdown analyzer: `reveal/analyzers/markdown.py`
- Output rendering: `reveal/main.py`
