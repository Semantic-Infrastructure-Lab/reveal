# Breadcrumb System Improvements Design Document

**Date:** 2026-01-04
**Version:** 1.0
**Status:** Design approved, implementation planned
**Authors:** TIA (based on codebase analysis and usage patterns)
**Session:** tetoni-0104 (design), kucinuga-0104 (integration)

---

## Release Integration

**This design is integrated into the Reveal roadmap:**
- **v0.30.1 (Feb 2026):** Phase 1 - Critical fixes (1-2 hours)
- **v0.31.0 (Q2 2026):** Phase 2 - Adapter awareness (3-4 weeks)
- **v0.32.0 (Q3 2026):** Phase 3 - Workflow guidance (2-3 weeks)
- **Future:** Phase 4-5 - Advanced features (post v1.0)

**See also:**
- `../../ROADMAP.md` - Overall project roadmap
- `./README.md` - Planning documentation index

---

## Executive Summary

The breadcrumb system was implemented in v0.13.1 (Dec 1, 2025) to provide agent-friendly navigation hints. Since then, Reveal has evolved significantly with 217+ commits adding major features:
- 11 URI adapters (help://, ast://, diff://, imports://, stats://, json://, etc.)
- Advanced query capabilities
- Workflow-oriented features (diff, imports, validation)
- Extensive help system

**Current state:** Breadcrumbs work well for basic file exploration but don't leverage Reveal's advanced capabilities.

**Critical bug discovered:** The "typed" context is not handled (structure.py:257), causing blank breadcrumb output.

**This document proposes:** Breadcrumb enhancements to guide users through Reveal's full feature set, with emphasis on progressive disclosure, workflow guidance, and adapter discovery.

**Impact:**
- Phase 1: Fix broken functionality (HIGH priority)
- Phase 2: 50-200 token savings per session through better feature discovery
- Phase 3: Complete workflow guidance (pre-commit, code review, refactoring)

---

## Current Implementation Analysis

### What Works Well

**Location:** `reveal/utils/breadcrumbs.py` (106 lines)

**Contexts Supported:**
- `metadata` - After `--meta` output
- `structure` - After file structure display
- `element` - After element extraction

**File-Type Awareness:**
- 15+ file types mapped (Python, JS, Markdown, YAML, etc.)
- Context-specific suggestions (--check for code, --links for Markdown)
- Progressive disclosure pattern established

**Design Principles:**
- Agent-first (no vim suggestions)
- Token-efficient
- Actionable next steps

### Issues Identified

#### 1. **BUG: Missing "typed" Context Handler**

**Location:** `reveal/display/structure.py:257`

```python
print_breadcrumbs("typed", file_path, file_type=file_type)
```

**Problem:** `breadcrumbs.py` only handles `metadata`, `structure`, `element`. The `typed` context silently fails (prints blank line).

**Impact:** Users lose guidance when viewing typed structure output.

**Fix Priority:** HIGH (broken functionality)

#### 2. **No Adapter Awareness**

Breadcrumbs don't suggest URI adapters even when they're the best tool:

```bash
# After: reveal large_module.py
# Current: Next: reveal large_module.py <function>
# Should suggest: reveal 'ast://large_module.py?complexity>10'  # Find hotspots
```

**Impact:** Users don't discover powerful adapter features.

#### 3. **No Workflow Guidance**

Missing context about common workflows:
- Pre-commit validation
- Code review patterns
- Refactoring workflows
- Quality improvement cycles

#### 4. **No Quality-Check Follow-up**

After `--check` finds issues, breadcrumbs don't suggest:
- How to fix specific rule violations
- Deeper analysis with other rules
- Stats analysis to find patterns

#### 5. **No Cross-File Suggestions**

When viewing imports, don't suggest:
- Using `imports://` adapter for dependency analysis
- Viewing imported files
- Finding circular dependencies

#### 6. **No HTML Analyzer Mapping**

`get_file_type_from_analyzer()` doesn't map `HtmlAnalyzer` to `'html'`, yet HTML analyzer exists.

---

## Design Principles (Established)

From codebase analysis and documentation:

1. **Progressive Disclosure** - Reveal structure before content (10-150x token savings)
2. **Agent-First Design** - Optimize for AI agents, not humans
3. **Token Awareness** - Every suggestion must reduce token consumption
4. **Self-Documenting** - Point to help:// when features need explanation
5. **Workflow-Oriented** - Guide through complete tasks, not just single commands
6. **Context-Sensitive** - Different suggestions based on what user just did

---

## Proposed Improvements

### Priority 1: Fix Critical Issues (1-2 hours)

#### 1.1 Fix "typed" Context Bug

**Change:** `reveal/utils/breadcrumbs.py`

```python
# Line 79: Add "typed" to structure handling
elif context in ['structure', 'typed']:
    element_placeholder = get_element_placeholder(file_type)
    print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")
    # ... rest of structure logic
```

**Testing:** Verify typed output now shows breadcrumbs.

#### 1.2 Add HTML Analyzer Mapping

**Change:** `reveal/utils/breadcrumbs.py`, line 44

```python
mapping = {
    # ... existing mappings
    'HtmlAnalyzer': 'html',
}
```

**Add HTML breadcrumbs:** (line 92)

```python
elif file_type == 'html':
    print(f"      reveal {path} --check      # Validate HTML")
    print(f"      reveal {path} --links      # Extract all links")
```

---

### Priority 2: Adapter Discovery (4-6 hours)

#### 2.1 Large File Detection → AST Adapter

**Trigger:** File has >500 lines or >20 functions

**Current:**
```
Next: reveal large_module.py <function>
```

**Proposed:**
```
Next: reveal large_module.py <function>   # Extract specific element
      reveal 'ast://large_module.py?complexity>10'  # Find complex functions
      reveal 'ast://large_module.py?lines>100'      # Find large functions
```

**Implementation:**

```python
def print_breadcrumbs(context, path, file_type=None, **kwargs):
    # ... existing code

    if context == 'structure':
        element_placeholder = get_element_placeholder(file_type)
        print(f"Next: reveal {path} {element_placeholder}   # Extract specific element")

        # Check if structure has many elements (large file)
        structure = kwargs.get('structure', {})
        total_elements = sum(len(items) for items in structure.values())

        if total_elements > 20:
            # Suggest AST queries for large files
            print(f"      reveal 'ast://{path}?complexity>10'   # Find complex code")
            print(f"      reveal 'ast://{path}?lines>100'       # Find large elements")
            return  # Skip standard suggestions for large files

        # ... rest of standard suggestions
```

#### 2.2 Post-Check Guidance

**After:** `reveal file.py --check` finds issues

**Current:** No breadcrumbs after check output

**Proposed:**

```
Found 3 issues:
  - B001: Invalid escape sequence
  - E501: Line too long (3 violations)
  - C901: Function too complex (handle_request)

Next: reveal file.py handle_request        # View complex function
      reveal help://rules                  # Learn about all rules
      reveal stats://file.py               # See complexity trends
```

**Implementation:** Add new context `quality-check`

```python
def print_breadcrumbs(context, path, file_type=None, **kwargs):
    # ... existing contexts

    elif context == 'quality-check':
        issues = kwargs.get('issues', [])
        if not issues:
            print("✅ No issues found - code quality is excellent!")
            print(f"Next: reveal {path} --outline    # Explore structure")
            return

        # Group by rule
        rules = set(issue['rule'] for issue in issues)

        print()
        if 'C901' in rules or 'C902' in rules:
            # Found complexity issues
            complex_funcs = [i['element'] for i in issues if i['rule'] in ['C901', 'C902']]
            if complex_funcs:
                print(f"Next: reveal {path} {complex_funcs[0]}   # View complex function")

        print(f"      reveal stats://{path}         # Analyze complexity trends")
        print(f"      reveal help://configuration  # Adjust rule thresholds")
```

**Callsite:** `reveal/main.py` in `run_pattern_detection()`

#### 2.3 Import Analysis Breadcrumbs

**After:** Viewing file with imports

**Current:**
```
Imports (15):
  /path/to/file.py:1    import os
  /path/to/file.py:2    import sys
  ...
```

**Proposed:**
```
Imports (15):
  /path/to/file.py:1    import os
  ...

Next: reveal imports://file.py             # Analyze dependencies
      reveal imports://. --circular        # Find circular imports
      reveal imports://. --unused          # Find unused imports
```

**Implementation:** Detect when import section is large

```python
# In print_breadcrumbs(), after structure output
structure = kwargs.get('structure', {})
if 'imports' in structure and len(structure['imports']) > 5:
    print()
    print("💡 Tip: Use imports:// adapter for dependency analysis")
    print(f"      reveal imports://{path}           # Analyze imports")
    print(f"      reveal imports://. --circular     # Find circular deps")
```

#### 2.4 diff:// Workflow Guidance

**After:** `reveal help://diff`

**Custom breadcrumbs in help adapter already exist** - extend them:

```python
# In reveal/rendering/adapters/help.py, _render_help_breadcrumbs()

related = {
    'diff': ['stats', 'ast'],  # ADD THIS
    # ... existing
}

# Also add workflow hints for diff
if scheme == 'diff':
    print("## Try It Now")
    print("  # Compare uncommitted changes:")
    print("  reveal diff://git://HEAD/.:.")
    print()
    print("  # Before/after refactoring:")
    print("  reveal diff://old.py:new.py")
    print()
```

---

### Priority 3: Workflow Context (6-8 hours)

#### 3.1 Workflow Detection

Detect common workflows and provide end-to-end guidance:

**Pre-Commit Workflow:**

```bash
# User runs: reveal src/ --check
# System detects: checking entire directory before commit

✅ 47 files checked, 3 issues found

Next Steps - Pre-Commit Workflow:
  1. reveal src/api.py handle_user  # Fix complex function
  2. reveal diff://git://HEAD/src/:src/  # Review all changes
  3. reveal stats://src/            # Verify no complexity regression
```

**Code Review Workflow:**

```bash
# User runs: reveal diff://git://main/.:git://feature/.

# After showing diff, suggest:

Next Steps - Code Review Workflow:
  1. reveal diff://git://main/app.py:git://feature/app.py/process  # Deep dive
  2. reveal 'ast://app.py?complexity>15'  # Check new hotspots
  3. reveal imports://. --circular         # Verify no new cycles
```

**Implementation:**

```python
def detect_workflow_context(command_history, current_context):
    """Detect if user is in a workflow."""
    # Check if they just ran directory check
    if current_context == 'directory-check':
        return 'pre-commit'

    # Check if they're using diff with git refs
    if current_context == 'diff' and 'git://' in kwargs.get('left_uri', ''):
        return 'code-review'

    return None

def print_workflow_breadcrumbs(workflow, **kwargs):
    """Print workflow-specific guidance."""
    workflows = {
        'pre-commit': [
            "Pre-Commit Workflow:",
            "  1. Fix issues found above",
            "  2. reveal diff://git://HEAD/.:.  # Review changes",
            "  3. git add . && git commit       # Commit if clean",
        ],
        'code-review': [
            "Code Review Workflow:",
            "  1. Review structural changes above",
            "  2. reveal stats://file.py         # Check complexity trends",
            "  3. reveal imports://. --circular  # Verify dependencies",
        ],
    }

    for line in workflows.get(workflow, []):
        print(line)
```

#### 3.2 Help System Integration

**After:** `reveal help://`

**Currently:** Shows index, no breadcrumbs

**Proposed:**
```
# ... help index output ...

Next: reveal help://ast              # Query code as database
      reveal help://diff             # Semantic code comparison
      reveal --agent-help            # Quick start guide
```

**Implementation:** Already has custom breadcrumbs in help adapter - just need to call it for index view.

---

### Priority 4: Context Awareness (8-12 hours)

#### 4.1 Content-Based Suggestions

Go beyond file type to content analysis:

**Example 1: Detect TODO comments**
```python
# After: reveal file.py --check
# If file contains TODO/FIXME comments

💡 Found 5 TODO items in this file
Next: grep "TODO" file.py             # Review all TODOs
      reveal 'ast://.?name=*test*'    # Find related tests
```

**Example 2: Detect test files**
```python
# After: reveal test_module.py
# Detect it's a test file (has test_ prefix or test functions)

💡 This is a test file
Next: reveal test_module.py test_handle_request  # View specific test
      reveal src/module.py                        # View tested code
      reveal --check test_module.py               # Check test quality
```

**Example 3: Detect config files**
```python
# After: reveal config.yaml
# Detect it's a configuration file

💡 Configuration file
Next: reveal env://                   # View environment vars
      reveal config.yaml --check      # Validate syntax
```

#### 4.2 Recently Modified Files

Suggest checking files that changed recently:

```python
# If in git repo
recent_files = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD~5..HEAD'])

print("💡 Recently modified files:")
print("  reveal diff://git://HEAD~5/.:.")
```

#### 4.3 Cross-Reference Suggestions

When viewing a file, suggest related files:

```python
# After viewing file with imports
imports = structure.get('imports', [])
if imports:
    # Extract imported files
    local_imports = [imp for imp in imports if imp.startswith('.') or '/' in imp]
    if local_imports:
        print()
        print("📎 Related files:")
        for imp in local_imports[:3]:
            print(f"      reveal {imp}  # View imported module")
```

---

### Priority 5: Advanced Features (Future)

#### 5.1 Session Memory

Track what user has done in this session:

```python
class BreadcrumbSession:
    """Track user's exploration path."""

    def __init__(self):
        self.history = []
        self.viewed_files = set()
        self.current_focus = None

    def suggest_next(self):
        """Suggest based on session context."""
        # If they've viewed multiple files, suggest aggregation
        if len(self.viewed_files) > 5:
            return "reveal stats://.  # Analyze all files together"

        # If they keep viewing structure, suggest AST
        if self.history[-3:] == ['structure', 'structure', 'structure']:
            return "reveal 'ast://.?complexity>10'  # Query across files"
```

#### 5.2 Smart Element Suggestions

Instead of generic `<function>`, show actual available elements:

```python
# Current:
Next: reveal file.py <function>

# Proposed:
Next: reveal file.py <function>      # e.g., handle_request, process_data
      reveal file.py --outline        # See all 15 functions
```

**Implementation:** Requires caching structure from last output.

#### 5.3 URI Template Suggestions

Show copyable URI templates:

```python
After: reveal file.py SomeClass

📋 Copy for later:
  reveal://file.py#SomeClass        # URI for this element
  diff://file.py:backup/file.py/SomeClass  # Compare versions
```

---

## Implementation Plan

### Phase 1: Critical Fixes (Week 1) ✅ COMPLETE
- [x] Fix "typed" context bug (already fixed in codebase)
- [x] Add HTML analyzer mapping (already had HtmlAnalyzer→html, added to element placeholder)
- [x] Test all existing contexts still work (69 tests passing)
- [ ] Bundle with v0.31.0 release

### Phase 2: Adapter Awareness (Week 2-3) ✅ COMPLETE
- [x] Large file detection → AST suggestions (already in v0.30.x)
- [x] Post-check quality guidance (quality-check context)
- [x] Import analysis breadcrumbs (already in v0.30.x)
- [x] diff:// workflow hints (help://diff + diff output)
- [x] `--quiet` / `-q` mode for scripting
- [x] Bundle with v0.31.0 release ✅ SHIPPED

### Phase 3: Workflow Guidance (Week 4-6) ✅ COMPLETE
- [x] Pre-commit workflow detection (directory-check context)
- [x] Code review workflow detection (code-review context, git:// URI detection)
- [ ] Refactoring workflow detection (future)
- [ ] Help system breadcrumbs enhancement (future)
- [x] Integrated into v0.32.0 (unreleased)

### Phase 4: Context Awareness (Future)
- [ ] Content-based suggestions (TODO detection, test files, etc.)
- [ ] Cross-file suggestions
- [ ] Recently modified files
- [ ] Release as minor version (v0.33.0)

### Phase 5: Advanced (Post v1.0)
- [ ] Session memory
- [ ] Smart element suggestions
- [ ] URI template suggestions

---

## Testing Strategy

### Unit Tests

```python
# tests/test_breadcrumbs.py

def test_typed_context():
    """Verify typed context produces output."""
    output = capture_breadcrumbs('typed', 'file.py', file_type='python')
    assert 'reveal file.py <function>' in output
    assert len(output) > 0  # Not blank!

def test_large_file_suggestions():
    """Large files should suggest AST adapter."""
    structure = {'functions': [f'func{i}' for i in range(25)]}
    output = capture_breadcrumbs('structure', 'big.py',
                                   file_type='python',
                                   structure=structure)
    assert 'ast://big.py?complexity>10' in output

def test_post_check_guidance():
    """After check, suggest next steps."""
    issues = [
        {'rule': 'C901', 'element': 'handle_request'},
        {'rule': 'E501', 'element': None},
    ]
    output = capture_breadcrumbs('quality-check', 'file.py',
                                   issues=issues)
    assert 'handle_request' in output
    assert 'stats://' in output
```

### Integration Tests

```bash
# Test full workflow
reveal test_file.py --check
# Verify breadcrumbs appear

reveal large_module.py
# Verify AST suggestions for large files

reveal diff://old.py:new.py
# Verify workflow suggestions
```

### Dogfooding

Use reveal on reveal itself and verify:
- Breadcrumbs are helpful
- Don't suggest irrelevant operations
- Actually save tokens
- Lead to productive workflows

---

## Success Metrics

### Token Efficiency
- **Current:** Breadcrumbs save ~10-50 tokens by preventing documentation reads
- **Target:** Save 50-200 tokens by directing to optimal tools (AST vs grep, etc.)

### Feature Discovery
- **Current:** Users discover adapters through `reveal help://`
- **Target:** 50% of adapter usage comes from breadcrumb suggestions

### Workflow Completion
- **Current:** Users perform single operations
- **Target:** 30% of sessions involve multi-step workflows guided by breadcrumbs

### User Feedback
- **Current:** "Breadcrumbs are helpful for basic navigation"
- **Target:** "Breadcrumbs teach me Reveal's advanced features"

---

## Risks and Mitigations

### Risk 1: Breadcrumb Overload
**Problem:** Too many suggestions overwhelm users
**Mitigation:**
- Max 3 suggestions per breadcrumb
- Prioritize most relevant suggestion first
- Use progressive disclosure (suggest help:// for complex topics)

### Risk 2: Context Detection Failures
**Problem:** Wrong suggestions for user's intent
**Mitigation:**
- Keep existing simple suggestions as fallback
- Add `--no-breadcrumbs` flag for users who don't want them
- Collect feedback on suggestion relevance

### Risk 3: Maintenance Burden
**Problem:** Breadcrumbs become stale as features evolve
**Mitigation:**
- Keep adapter-specific breadcrumbs in adapter code
- Use help:// system as single source of truth
- Test breadcrumbs in CI

### Risk 4: Performance Impact
**Problem:** Context detection slows down output
**Mitigation:**
- Keep detection logic simple (no expensive analysis)
- Cache structure data from display pass
- Make breadcrumb generation optional via env var

---

## Open Questions

1. **Should breadcrumbs be stateful?**
   - Track session history to suggest next steps?
   - Or stay stateless for simplicity?

2. **Verbosity levels?**
   - BREADCRUMB_LEVEL=minimal|standard|verbose?
   - Or always show standard?

3. **Adapter ownership?**
   - Should each adapter define its own breadcrumbs?
   - Or centralize in breadcrumbs.py?

4. **Help:// integration?**
   - Every breadcrumb links to help:// topic?
   - Or keep concise?

5. **Output format sensitivity?**
   - Skip breadcrumbs in JSON mode?
   - Or include in separate field?

---

## Related Work

- Original breadcrumb implementation: v0.13.1 (Dec 1, 2025)
- Help adapter custom breadcrumbs: `reveal/rendering/adapters/help.py:9`
- Progressive disclosure patterns: `COOL_TRICKS.md:376`
- Anti-patterns guidance: `ANTI_PATTERNS.md:343`

---

## Appendix A: Current Breadcrumb Coverage

| Context | Handled | File-Type Aware | Notes |
|---------|---------|-----------------|-------|
| metadata | ✅ | ❌ | Generic suggestions |
| structure | ✅ | ✅ | 15+ file types |
| typed | ❌ | ❌ | **BUG: Not handled** |
| element | ✅ | ✅ | Shows extraction context |
| quality-check | ❌ | - | **Proposed** |
| adapter-result | Partial | - | Only help:// has custom |
| workflow | ❌ | - | **Proposed** |

---

## Appendix B: Adapter Breadcrumb Opportunities

| Adapter | Current | Proposed Breadcrumb |
|---------|---------|---------------------|
| ast:// | None | `reveal stats://<path>` for trends |
| diff:// | None | Element-specific diffs, stats comparison |
| env:// | None | `reveal python://` for python-specific env |
| help:// | ✅ Custom | Enhance with try-now examples |
| imports:// | None | Circular detection, unused imports |
| json:// | None | Schema validation, ast:// for JSON files |
| mysql:// | None | Performance analysis, replication status |
| python:// | None | Doctor mode, package inspection |
| reveal:// | None | Configuration fixes, completeness checks |
| stats:// | None | AST queries for hotspots, diff for trends |

---

## Appendix C: Example Session with Enhanced Breadcrumbs

```bash
# User wants to review code before committing
$ reveal src/

src/
├── api.py (15 functions)
├── utils.py (8 functions)
└── models.py (12 classes)

💡 Pre-Commit Workflow Detected
Next: reveal src/ --check           # Check all files for issues
      reveal diff://git://HEAD/src/:src/  # See what changed

$ reveal src/ --check

Checking 3 files...
✅ src/utils.py - No issues
✅ src/models.py - No issues
❌ src/api.py - 2 issues found:
  - C901: handle_request (complexity: 18, limit: 15)
  - E501: Line 47 (length: 125, limit: 100)

Next: reveal src/api.py handle_request   # View complex function
      reveal stats://src/api.py          # See complexity trends
      reveal help://configuration        # Adjust thresholds

$ reveal src/api.py handle_request

def handle_request(req):
    # ... 45 lines of code ...

Extracted handle_request (45 lines, complexity: 18)
💡 High complexity detected - consider refactoring

Next: reveal 'ast://src/api.py?type=function'  # See all functions
      reveal help://tricks                      # Learn refactoring patterns
      reveal diff://git://HEAD/src/api.py:src/api.py  # What changed

$ # User is now guided through full quality improvement workflow!
```

---

**End of Design Document**
