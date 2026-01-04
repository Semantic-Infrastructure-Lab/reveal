# AST Migration Roadmap

**Created:** 2026-01-03
**Status:** Active Planning
**Target:** Continuous improvement (v0.29.0+)
**Priority:** MEDIUM (quality/maintainability improvement)

---

## Executive Summary

Progressive migration from regex-based analyzers to AST-based parsing where quality parsers exist. Improves accuracy, enables precise error location tracking, and reduces edge case bugs.

**Completed:** Phase 1-4 (Markdown migration + research)
**Next:** Crossplane nginx enhancement (optional dependency)
**Future:** Monitor GDScript, evaluate other analyzers

---

## Why AST Migration?

### Benefits

✅ **Accuracy:** AST handles edge cases better than regex
✅ **Column tracking:** Free precise position from AST nodes
✅ **Maintainability:** Parser updated by language community
✅ **Edge cases:** Correctly ignores links in code blocks, etc.
✅ **Simpler logic:** No state machines or complex lookaheads

### Anti-Benefits (When NOT to migrate)

❌ **Parser doesn't exist:** Don't build custom parsers
❌ **Regex works fine:** Don't migrate working, simple patterns
❌ **Performance cost:** Only if AST is measurably slower
❌ **Heavy dependency:** Avoid hard dependencies on unmaintained parsers

---

## Completed Migrations

### ✅ Phase 1: Foundation (aerial-sphinx-0103, 2026-01-03)

**Goal:** Fix pattern compilation bugs, document patterns

**Work:**
- Fixed regex compilation issues across analyzers
- Created ANALYZER_PATTERNS.md with 8 patterns
- Established migration best practices

**Status:** Complete, 1517/1517 tests passing

---

### ✅ Phase 2: Rules Refactoring (nexus-nemesis-0103, 2026-01-03)

**Goal:** Eliminate duplicate parsing in rules

**Work:**
- Refactored L001, L002, L003 to use analyzer structure
- Single source of truth: analyzers own parsing
- Rules consume analyzer output

**Status:** Complete, 1320/1320 tests passing

---

### ✅ Phase 3: Markdown AST Migration (swift-abyss-0103, 2026-01-03)

**Goal:** Replace regex with tree-sitter AST for Markdown

**Work:**
- Migrated link extraction to AST
- Migrated code block extraction to AST
- Added column position tracking
- Implemented fallback mechanisms

**Benefits:**
- Correctly ignores links in code blocks
- Column tracking for precise error location
- Handles edge cases (nested brackets, escapes)

**Status:** Complete, 1517/1517 tests passing

**Implementation:**
```python
def _extract_links(self, ...):
    if not self.tree:
        return self._extract_links_regex(...)  # Fallback
    # AST-based extraction with column tracking
    line = node.start_point[0] + 1
    column = node.start_point[1] + 1
    ...
```

**Documentation:** PHASES_3_4_AST_MIGRATION.md (external-git/internal-docs/)

---

### ✅ Phase 4: Parser Research (swift-abyss-0103, 2026-01-03)

**Goal:** Evaluate GDScript and nginx parser options

**Findings:**

**GDScript:**
- ❌ NOT in tree-sitter-languages (would need manual build)
- ✅ EXISTS as standalone (PrestonKnopp/tree-sitter-gdscript)
- ⚠️ Current regex works adequately
- **Decision:** DEFER until in tree-sitter-languages

**Nginx (crossplane):**
- ✅ Maintained by nginx team
- ✅ On PyPI (crossplane 0.5.8)
- ✅ Production-ready, handles all nginx syntax
- ✅ Extracts complete directive tree
- **Decision:** RECOMMENDED as optional dependency

**Status:** Research complete, recommendations documented

**Documentation:** NGINX_SUPPORT_DOCUMENTATION.md (external-git/internal-docs/)

---

## Planned Migrations

### 🎯 Phase 5: Nginx Crossplane Enhancement (OPTIONAL)

**Priority:** MEDIUM (nice-to-have for infrastructure visibility)
**Effort:** 1 day (6-8 hours)
**Target:** v0.29.0 or v0.30.0 (alongside Knowledge Graph features)
**Dependencies:** None (optional dependency pattern)

#### What is Crossplane?

**crossplane** - Official nginx config parser maintained by nginx team
- PyPI: https://pypi.org/project/crossplane/ (v0.5.8)
- Converts nginx configs to JSON and back
- Handles ALL nginx syntax (includes, variables, etc.)

#### Current Limitations

**Current implementation (regex-based):**
- ✅ Server blocks (name, port)
- ✅ Location blocks (path, proxy_pass/root)
- ✅ Upstream names
- ❌ Upstream backend servers
- ❌ SSL certificate details
- ❌ Headers (proxy_set_header, etc.)
- ❌ Include directive following
- ❌ Variable resolution

**Example gap:**
```nginx
upstream backend {
    server 192.168.1.10:8080;  # NOT extracted currently
    server 192.168.1.11:8080;  # NOT extracted currently
}
```

#### Implementation Plan

**Approach:** Optional dependency with fallback

```toml
# pyproject.toml
[project.optional-dependencies]
nginx = ["crossplane>=0.5.8"]
```

**Installation:**
```bash
pip install reveal[nginx]  # Enhanced parsing
pip install reveal         # Basic parsing (current)
```

**Code structure:**
```python
class NginxAnalyzer:
    def get_structure(self, **kwargs):
        if self._has_crossplane():
            return self._parse_crossplane(**kwargs)
        else:
            return self._parse_regex(**kwargs)  # Current fallback
```

**Benefits:**
- ✅ No breaking changes
- ✅ Users choose level of detail
- ✅ Lightweight by default
- ✅ Clear upgrade path
- ✅ Complete infrastructure visibility (with crossplane)

#### Success Criteria

- [ ] crossplane added as optional dependency
- [ ] Dual-mode parser (crossplane + regex fallback)
- [ ] Extract upstream backend servers
- [ ] Extract SSL configuration details
- [ ] Extract ALL directives (not just proxy_pass/root)
- [ ] Test with real-world nginx configs
- [ ] Document benefits in user guide
- [ ] All tests passing (no regressions)

#### Why Optional Priority?

**TIA infrastructure benefits:**
- See actual backend servers (not just upstream names)
- Certificate expiration tracking
- Complete request routing visibility
- Include file following

**But:**
- Current implementation works for basic cases
- No user requests for enhanced nginx support
- Knowledge Graph features are higher priority

**Recommendation:** Implement alongside v0.29.0/v0.30.0 if time permits, or defer to v0.31.0

---

### 📋 Phase 6: GDScript Migration (DEFERRED)

**Priority:** LOW (wait for ecosystem)
**Effort:** Unknown (depends on tree-sitter-languages inclusion)
**Status:** MONITOR

#### Why Deferred?

- tree-sitter-gdscript NOT in tree-sitter-languages package
- NOT on PyPI (requires manual compilation)
- Current regex implementation adequate for basic GDScript

#### Monitoring Criteria

**Check every 3 months:**
- Is tree-sitter-gdscript in tree-sitter-languages?
- Is tree-sitter-gdscript on PyPI?
- Are we seeing GDScript edge case bugs?

**Trigger for implementation:**
- ✅ tree-sitter-gdscript in tree-sitter-languages, OR
- ✅ User reports of GDScript parsing issues, OR
- ✅ GDScript becomes critical for TIA workflows

---

## Future Analyzer Evaluation

### Candidates for AST Migration

| Analyzer | Current | Parser Available? | Priority | Notes |
|----------|---------|-------------------|----------|-------|
| **nginx** | Regex | ✅ crossplane | MEDIUM | Phase 5 planned |
| **GDScript** | Regex | ⚠️ Standalone | LOW | Phase 6 deferred |
| **bash** | None | ✅ tree-sitter-bash | LOW | Minimal bash analysis currently |
| **Dockerfile** | Regex | ✅ dockerfile-parse | LOW | Current regex adequate |
| **TOML** | tomli | ✅ Already using parser | ✅ Done | - |
| **YAML** | PyYAML | ✅ Already using parser | ✅ Done | - |
| **JSON** | json stdlib | ✅ Already using parser | ✅ Done | - |

### Evaluation Criteria

Before proposing AST migration for any analyzer:

1. **Parser exists?** (tree-sitter-languages, PyPI, or stdlib)
2. **Current implementation problems?** (edge cases, bugs)
3. **User benefit?** (what new capabilities unlocked?)
4. **Maintenance burden?** (dependency weight vs benefit)
5. **Performance impact?** (measure before/after)

**Default stance:** Regex is fine for simple cases. Only migrate when clear benefit.

---

## Migration Pattern (Established)

Based on Phase 3 completion:

### Step 1: Research (30 min - 1 hour)

Create test script to explore AST structure:

```python
# test_ast_exploration.py
import tree_sitter_<language>
from tree_sitter import Parser

parser = Parser()
parser.set_language(tree_sitter_<language>.language())
tree = parser.parse(b"sample code")

def explore_nodes(node, depth=0):
    print("  " * depth + f"{node.type}: {node.text[:50]}")
    for child in node.children:
        explore_nodes(child, depth + 1)

explore_nodes(tree.root_node)
```

**Lesson:** 30 minutes exploration saves hours of debugging.

### Step 2: Implement AST Extraction

```python
def _extract_<element>_ast(self):
    """Extract using AST (preferred)."""
    if not self.tree:
        return self._extract_<element>_regex()  # Fallback

    results = []
    nodes = self._find_nodes_by_type('<node_type>')

    for node in nodes:
        line = node.start_point[0] + 1     # Row (1-indexed)
        column = node.start_point[1] + 1   # Column (1-indexed)
        # Extract data from node children
        results.append({
            'line': line,
            'column': column,
            # ... more data
        })

    return results
```

### Step 3: Keep Regex Fallback

```python
def _extract_<element>_regex(self):
    """Fallback regex implementation (current)."""
    # Keep existing implementation
    ...
```

**Why fallback?**
- Graceful degradation if tree-sitter fails
- Zero downtime during migration
- Handles custom/invalid syntax
- Proven pattern from Phase 3

### Step 4: Test Edge Cases

Create comprehensive tests:
- Nested structures
- Comments with special chars
- Quotes and escapes
- Language-specific edge cases

**Lesson:** Don't assume AST handles edge cases - verify with tests.

### Step 5: Document in ANALYZER_PATTERNS.md

Add concrete examples showing:
- What changed
- Benefits gained
- Edge cases handled
- Migration date (for archaeology)

---

## Dependencies

### Current (Required)

- tree-sitter (core library)
- tree-sitter-languages (20 languages including Python, JS, etc.)

### Optional (Proposed)

- crossplane (nginx enhancement, Phase 5)

### Future (Monitoring)

- tree-sitter-gdscript (if added to tree-sitter-languages)

---

## Success Metrics

### Code Quality

- ✅ Zero regressions (all tests passing)
- ✅ Column tracking enabled where possible
- ✅ Simpler analyzer logic (no complex state machines)
- ✅ Edge cases handled correctly

### Documentation

- ✅ ANALYZER_PATTERNS.md updated with each migration
- ✅ Migration rationale documented
- ✅ Fallback patterns explained

### Architecture

- ✅ Fallback mechanisms proven
- ✅ Optional dependency pattern established
- ✅ Parser evaluation criteria documented

---

## Related Documents

### Completion Reports

- `external-git/internal-docs/PHASES_3_4_AST_MIGRATION.md` - Phase 3/4 completion
- `external-git/internal-docs/NGINX_SUPPORT_DOCUMENTATION.md` - Crossplane spec

### User-Facing Docs

- `external-git/reveal/ANALYZER_PATTERNS.md` - Development patterns
- `external-git/reveal/ANTI_PATTERNS.md` - What to avoid

### Planning Docs

- `planning/KNOWLEDGE_GRAPH_PROPOSAL.md` - v0.29.0-v0.32.0 roadmap (higher priority)
- `README.md` (this directory) - Planning overview

---

## Timeline

### Completed (Jan 2026)

- ✅ Phase 1-4 complete (3 sessions, ~12 hours total)

### Q1 2026 (Optional)

- Phase 5: Nginx crossplane enhancement (1 day, if time permits)

### Q2 2026+

- Phase 6+: Monitor GDScript, evaluate other analyzers quarterly

**Note:** AST migrations are **opportunistic quality improvements**, not critical path features. They happen:
- During foundation work (between major features)
- When debugging edge cases reveals need
- When user requests enhanced language support

---

## Search Keywords

ast-migration, tree-sitter, crossplane, nginx, gdscript, parser-evaluation, optional-dependencies, fallback-patterns, analyzer-quality, column-tracking, edge-case-handling

---

**Last Updated:** 2026-01-03
**Next Review:** Q2 2026 (re-evaluate GDScript, bash, Dockerfile)
