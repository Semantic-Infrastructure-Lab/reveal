# Practical Code Analysis Adapters - Production-Validated Design

**Version:** 1.1 (Updated for v0.31+)
**Date:** 2026-01-06 (originally 2025-12-22)
**Status:** Partially Shipped - See ROADMAP.md for current timeline
**Source:** Real-world architectural audits of large-scale production codebases

> **Note (2026-01-06):** `imports://` shipped in v0.28. Remaining features planned for v0.32-v0.34. See `external-git/ROADMAP.md` for authoritative timeline.

---

## 🎯 Executive Summary

This document consolidates **production-validated adapter proposals** with Reveal's existing roadmap. Based on analyzing large-scale production codebases (60K+ lines), we identified that Reveal handles **~80% of code analysis tasks** out of the box, but **20% of critical analysis** required custom scripts for cross-file relationships.

**Key Finding**: The missing 20% consists of **cross-file relational analysis** (imports, calls, architecture, duplicates) - not single-file structure analysis (which Reveal already excels at).

**Impact**: Adding these 4 adapters eliminates the need for most custom audit scripts in real-world codebases.

---

## 📊 Gap Analysis: What Reveal Has vs What's Needed

### ✅ What Reveal Already Does Well

| Feature | Adapter | Shipped |
|---------|---------|---------|
| File structure analysis | `file://` | ✅ v0.1+ |
| Code quality metrics | `stats://` | ✅ v0.24.0 |
| AST-based pattern detection | Built-in | ✅ v0.13+ |
| Runtime environment inspection | `python://` | ✅ v0.17.0 |
| JSON/data structure navigation | `json://` | ✅ v0.20.0 |

### ❌ What's Missing (20% Gap)

| Need | Current Workaround | Impact |
|------|-------------------|--------|
| **Import graph analysis** | Custom Python AST scripts | Hundreds of unused imports found manually in audits |
| **Architecture validation** | Manual grep patterns | Layer violations undetected, found during code review |
| **Dead code detection** | Custom call graph builders | High false positive rates, unreliable results |
| **Duplicate detection** | Basic D002 rule (names only) | Can't measure code similarity, only name duplicates |

**Common Thread**: All missing features are **cross-file relational analysis**.

---

## 🆕 Proposed Adapters (Priority Order)

### Priority 1: ✅ SHIPPED (v0.28)

#### 1. `imports://` - Import Graph Analysis

**Status**: ✅ **Shipped in v0.28.0** (Jan 2026)

**Problem Solved**:
- Unused imports accumulate over time (often hundreds in large codebases)
- Circular dependencies cause maintenance issues and are hard to detect manually
- Layer violations (e.g., routes importing repositories) break architectural patterns
- No visibility into cross-file import relationships and dependency graphs

**URI Design**:
```bash
# Show all imports in a directory
reveal imports://app/routes

# Find unused imports
reveal 'imports://app?unused'

# Find circular dependencies
reveal 'imports://app?circular'

# Find layer violations
reveal 'imports://app/routes?from=repositories'  # Should be empty

# Show import graph
reveal imports://app --graph
```

**Language Support**: Generic (Python, JavaScript, Go, Rust, Java)
- Uses tree-sitter AST parsing (already in Reveal)
- Language-agnostic import pattern matching

**Implementation Notes**:
- Build on existing tree-sitter infrastructure
- Parse all files to build directed import graph
- Detect unused via AST symbol usage analysis
- Detect cycles via topological sort
- Cache graph, invalidate on file changes

**Effort**: Medium (3-4 weeks)

**Expected Output**:
```
Import Graph: app/routes

Unused Imports (8):
  ❌ app/routes/ui_routes.py:5
     render_gallery - Not used in this file

  ❌ app/routes/api.py:12
     old_validator - Not used in this file

Circular Dependencies: 0 ✅

Layer Violations (2):
  ❌ app/routes/api.py:15
     Routes layer importing from repositories layer
     Fix: Import from services/ instead

Summary:
  Total imports: 247
  Unused: 8 (3.2%)
  Circular: 0
  Layer violations: 2
```

**Why Not `python://imports`?**
- `python://` is for **runtime** inspection (currently loaded modules)
- `imports://` is for **source code** analysis (import statements in files)
- Import analysis is **language-agnostic** (applies to Python, JS, Go, Rust, etc.)
- Keeps runtime inspection separate from static analysis

**Decision**: Create `imports://` as language-agnostic adapter, NOT extend `python://`

---

#### 2. `architecture://` - Architecture Rule Validation

**Status**: Not in existing roadmap - **Genuinely New**

**Problem Solved**:
- Layer violations (e.g., presentation layer importing data layer directly)
- No automated enforcement of architectural rules and patterns
- Architecture degrades over time without continuous validation
- Manual validation is error-prone and doesn't scale to large teams

**URI Design**:
```bash
# Check all architecture rules
reveal architecture://app

# Check specific layer
reveal architecture://app/routes

# List violations only
reveal 'architecture://app?violations'
```

**Configuration** (`.reveal.yaml` - New Standard):
```yaml
architecture:
  layers:
    - name: routes
      path: app/routes/**
      can_import:
        - services/**
        - components/**
        - models/**
      cannot_import:
        - repositories/**  # Must go through services

    - name: services
      path: app/services/**
      can_import:
        - repositories/**
        - models/**
      cannot_import:
        - routes/**

  rules:
    - name: no-god-functions
      check: function_lines <= 100
      severity: error

    - name: no-deep-nesting
      check: nesting_depth <= 4
      severity: warning
```

**Implementation Notes**:
- Parse `.reveal.yaml` for layer definitions
- Use `imports://` graph to check layer boundaries
- Check code quality rules (function size, nesting)
- Report violations with file:line references

**Effort**: Medium (3-4 weeks)

**Expected Output**:
```
Architecture Validation: app

Layers: 5 defined
  ✅ routes (15 files)
  ✅ services (7 files)
  ✅ repositories (4 files)

Layer Violations (2):
  ❌ app/routes/api.py:15
     Layer violation: routes → repositories
     Fix: Import from services/ instead

  ❌ app/components/pack_builder.py:23
     Layer violation: components → repositories
     Fix: Import from services/ instead

Rule Violations (3):
  ⚠️  app/routes/ui_routes.py:17
      Function 'register_ui_routes' has 2446 lines (max: 100)

Status: ❌ FAILED (2 layer violations)
```

**CI/CD Integration**:
```bash
# Pre-commit hook
reveal architecture://app --format=json > arch.json
if [ $(jq '.layer_violations | length' arch.json) -gt 0 ]; then
  echo "❌ Architecture violations detected"
  exit 1
fi
```

---

### Priority 2: High Value (Post v1.0) 🟡

#### 3. Enhanced `ast://` with Dead Code Detection

**Status**: `ast://` planned Phase 1, dead code detection is **New Enhancement**

**Problem Solved**:
- Unused functions accumulate over time (hundreds in large codebases)
- Many false positives (route handlers, framework callbacks, entry points)
- Difficult to find truly dead code without entry point configuration

**URI Design** (enhance planned `ast://`):
```bash
# Find dead code
reveal 'ast://app?unused'

# Find functions called once (inlining candidates)
reveal 'ast://app?called=1'

# Find functions called many times
reveal 'ast://app?called>10'

# Show call chain
reveal ast://app/auth.py#authenticate --callers
```

**Configuration** (`.reveal.yaml`):
```yaml
ast:
  entry_points:
    - pattern: "@app\\.(route|get|post|put|delete)"
      description: "FastHTML route handlers"
    - pattern: "def test_"
      description: "Pytest test functions"
    - pattern: "def __.*__"
      description: "Magic methods"

  exclude_from_unused:
    - "**/routes/**"  # All route handlers
    - "tests/**"      # All test functions
```

**Implementation Notes**:
- Build on planned `ast://` adapter
- Add call graph generation (static analysis)
- Configurable entry points to reduce false positives
- Conservative analysis for dynamic calls

**Effort**: Medium-High (4-5 weeks, integrated with `ast://`)

**Expected Output**:
```
Dead Code Analysis: app
(Excluding entry points: routes, tests, magic methods)

Unused Functions (5):

app/utils/helpers.py:
  old_format_date [45 lines] - Not called anywhere
  Recommendation: Remove or add to deprecated module

app/services/analytics.py:
  track_legacy_event [23 lines] - Not called anywhere
  Recommendation: Remove if no longer needed

Summary:
  Total functions: 312
  Called: 307
  Unused: 5 (1.6%)
  Entry points excluded: 78
```

**Design Decision**: Enhance `ast://` rather than create separate `callgraph://`
- `ast://` already planned for AST queries
- Call graph is AST-based analysis
- Avoids adapter proliferation

---

#### 4. Enhanced `stats://` with Duplicate Detection

**Status**: `stats://` shipped v0.24.0, has basic D002 rule - **Enhancement Needed**

**Current State**: D002 detects duplicate names only
**Needed**: AST-based similarity scoring for duplicate implementations

**URI Design** (enhance existing `stats://`):
```bash
# Find duplicates with similarity scoring
reveal 'stats://app?duplicates&similarity>85'

# Find exact duplicates
reveal 'stats://app?duplicates&type=exact'
```

**Implementation Notes**:
- Enhance existing D002 rule
- Add AST structure comparison
- Compute similarity score (0-100%)
- Group similar functions, identify canonical implementation

**Effort**: Medium (3-4 weeks, enhancement to existing)

**Expected Output**:
```
Duplicate Code Analysis: app

Duplicate Set 1: health_check() - 5 implementations, 92% similar
  app/app.py:708               [15 lines, 100% match]
  app/admin_hub.py:346         [31 lines, 45% match]
  app/database/config_db.py:90 [26 lines, 82% match]

  Canonical: app/app.py:708
  Recommendation: Consolidate to utils/health.py

Summary:
  Duplicate sets: 23
  Functions with duplicates: 67
  Lines deduplicable: 1,247
```

**Design Decision**: Enhance `stats://` rather than create separate `duplicates://`
- `stats://` already has quality metrics
- D002 rule is foundation for enhancement
- Keeps quality analysis unified

---

### Priority 3: Advanced (Phase 3) 🟢

#### 5. Enhanced `semantic://` with Behavior Patterns

**Status**: `semantic://` planned Phase 3 - **Merge Proposals**

**Existing Plan**: Embeddings-based semantic search
**Enhancement**: Add built-in behavior patterns for practical use cases

**URI Design** (enhance planned `semantic://`):
```bash
# Built-in patterns (NEW)
reveal 'semantic://app?opens_file'
reveal 'semantic://app?makes_http_call'
reveal 'semantic://app?executes_sql'
reveal 'semantic://app?uses_subprocess'

# Embeddings-based (EXISTING)
reveal 'semantic://"user authentication" --in ast://app'
```

**Configuration** (`.reveal.yaml`):
```yaml
semantic:
  # Built-in patterns (AST-based, fast)
  patterns:
    - name: opens_file
      detect: ["open(", "Path().read_text(", "Path().write_bytes("]

    - name: executes_sql
      detect: ["execute(", "executemany(", "cursor.execute"]

  # Custom patterns (project-specific)
  custom_patterns:
    - name: uses_stripe_api
      description: "Functions that call Stripe API"
      patterns:
        - "stripe\\..*\\("
        - "Stripe.*"
```

**Implementation Notes**:
- Phase 1: Built-in AST-based patterns (fast, no ML)
- Phase 2: Embeddings-based similarity (requires sentence-transformers)
- Optional dependency: `reveal-cli[semantic]` for embeddings

**Effort**: Medium (Phase 1: 3-4 weeks), High (Phase 2: 6+ weeks)

**Design Decision**: Merge behavior patterns (audit-driven) with embeddings (research-oriented)
- Behavior patterns are practical, immediate value
- Embeddings are advanced, require ML dependencies
- Progressive enhancement: patterns first, embeddings later

---

## 🔧 Cross-Cutting: `.reveal.yaml` Configuration Standard

**Status**: **New Standard** - Proposed across all adapters

**Purpose**: Project-specific configuration for all adapters

**Location**: `.reveal.yaml` in project root (checked into version control)

**Benefits**:
- Reduces false positives (entry point configuration)
- Enables team-specific rules (layer boundaries)
- Shareable configuration (committed to repo)
- Consistent across adapters

**Proposed Structure**:
```yaml
# .reveal.yaml - Project-specific Reveal configuration

# Import analysis
imports:
  ignore_unused:
    - "**/tests/fixtures/**"  # Test fixtures import without using

# Architecture validation
architecture:
  layers: [...]
  rules: [...]

# AST/call graph analysis
ast:
  entry_points: [...]
  exclude_from_unused: [...]

# Semantic patterns
semantic:
  custom_patterns: [...]

# Quality thresholds
quality:
  min_score: 70
  max_function_lines: 100
  max_complexity: 10
```

**Implementation Priority**: Phase 1 (foundational)

---

## 🗺️ Integrated Roadmap

> **See `external-git/ROADMAP.md` for authoritative timeline.**

### ✅ Shipped (as of v0.31.0)

- ✅ `stats://` - Quality metrics, hotspot detection (v0.24)
- ✅ `json://` - JSON navigation (v0.20)
- ✅ `reveal://` - Self-inspection (v0.22)
- ✅ `env://` - Environment variables
- ✅ `python://` - Runtime inspection (v0.17)
- ✅ `imports://` - Import graph, unused imports, circular deps (v0.28)
- ✅ `diff://` - Semantic diff (v0.30)
- ✅ Schema validation framework (v0.29)

### v0.32-v0.33 (Q2-Q3 2026)

1. **`--related`** - Knowledge graph link following (v0.32)
2. **`markdown://`** - Query markdown by frontmatter (v0.33)
3. **`architecture://`** - Layer validation, rule enforcement
4. **`.reveal.yaml`** - Project-specific configuration

### v0.34-v1.0 (Q4 2026 - Q1 2027)

1. **Documentation & Polish** - Pre-v1.0 stability
2. **Enhanced `ast://`** - Dead code detection with configurable entry points
3. **Enhanced `stats://`** - Duplicate detection with similarity scoring

### Post v1.0

- `query://` - Cross-resource queries
- `graph://` - Relationship visualization
- `time://` - Temporal exploration (Git history)
- `semantic://` - Behavior patterns (Phase 1) + embeddings (Phase 2)
- `trace://` - Execution trace exploration

---

## 📐 Design Decisions & Rationale

### 1. `imports://` is Generic, Not Python-Specific

**Decision**: Create `imports://` adapter, NOT extend `python://`

**Rationale**:
- `python://` is for **runtime** inspection (currently loaded modules, sys.path, environment)
- `imports://` is for **source code** analysis (import statements across files)
- Import analysis is **language-agnostic** (Python, JS, Go, Rust, Java all have imports)
- Keeps runtime inspection separate from static code analysis

**Conflict Resolved**: Future plan for `python://imports/graph` should be reconsidered in favor of generic `imports://`

---

### 2. Enhance Existing Adapters Rather Than Proliferate

**Decision**: Enhance `ast://` and `stats://` rather than create new adapters

**Rationale**:
- `callgraph://` → Enhance `ast://` with call graph queries
- `duplicates://` → Enhance `stats:// D002` rule with similarity scoring
- Avoids adapter proliferation
- Maintains coherent API surface

---

### 3. Practical (Audit-Driven) Before Conceptual (Research)

**Decision**: Prioritize `imports://` and `architecture://` over `time://` and `trace://`

**Rationale**:
- Production-validated adapters solve **real pain points** (unused imports, layer violations)
- Research adapters are **visionary** but unvalidated (time-travel, distributed tracing)
- Front-load validated, high-ROI features
- Build foundation for advanced features later

**Impact**: Ship practical value faster, validate with real production codebases

---

### 4. `.reveal.yaml` as Configuration Standard

**Decision**: Introduce project-specific configuration file

**Rationale**:
- Reduces false positives (entry points, framework-specific patterns)
- Enables team-specific rules (layer boundaries, quality thresholds)
- Shareable via version control
- Consistent across all adapters

**Implementation**: Phase 1 infrastructure work

---

## 🎯 Success Metrics

### Quantitative

**Coverage Goals**:
- Reveal handles ~80% of code analysis → Target: 95%+
- Unused imports found manually → Target: Automated detection
- Layer violations found manually → Target: Automated in CI/CD
- Dead code candidates with high false positives → Target: <5% false positive rate

**Performance**:
- Structure queries: <100ms (maintain existing performance)
- Import graph build: <2s for 100 files
- Architecture validation: <1s for medium codebase

### Qualitative

**Developer Experience**:
- "I don't need custom scripts anymore" - audit workflow
- "Architecture stays clean over time" - CI/CD integration
- "Onboarding is faster" - `.reveal.yaml` documents rules

**Adoption**:
- `imports://` and `architecture://` in 20%+ of projects
- `.reveal.yaml` files committed to repos
- Community contributions of layer patterns

---

## 🔄 Validation Strategy

### Dogfooding

**Primary Testbeds**: Production codebases (10K-100K+ lines)
- Test `imports://` on large-scale production code
- Test `architecture://` for layer violation detection
- Measure false positive rate for dead code detection
- Validate `.reveal.yaml` configuration effectiveness

**Additional Testbeds**:
- Reveal itself (~10K lines)
- Community open-source projects
- Various language ecosystems (Python, JS, Go, Rust)

### Metrics

Track for each adapter:
- True positives vs false positives
- Time saved vs manual scripts
- Configuration complexity
- Performance at scale

---

## 📚 Documentation Updates Needed

### Internal Docs (this directory)

- ✅ This document (PRACTICAL_CODE_ANALYSIS_ADAPTERS.md)
- 🔄 Update ADVANCED_URI_SCHEMES.md (merge semantic proposals)
- 🔄 Update URI_ADAPTERS_MASTER_SPEC.md (add .reveal.yaml standard)

### Public Docs

- ✅ Update ROADMAP.md (revise v0.26-v0.27 priorities) - DONE
- 🆕 Create CONFIGURATION.md (document .reveal.yaml format)
- 🆕 Create ARCHITECTURE_VALIDATION_GUIDE.md (architecture:// usage)

### Examples

- 🆕 Create examples/architecture-validation/ (layer configs)
- 🆕 Create examples/import-analysis/ (common patterns)

---

## 🚀 Next Steps

### Immediate (This Week)

1. ✅ Consolidate proposals (this document)
2. ⏭️ Review with Reveal maintainers
3. ✅ Update public ROADMAP.md with revised priorities - DONE (2025-12-22)
4. ⏭️ Create GitHub issues for each adapter

### Short Term (Next Month)

1. ⏭️ Design .reveal.yaml schema and parser
2. ⏭️ Prototype `imports://` on production codebase
3. ⏭️ Validate performance and false positive rate
4. ⏭️ Draft adapter developer guide

### Medium Term (v0.26-v0.27 Implementation)

1. ⏭️ Implement `imports://` (3-4 weeks)
2. ⏭️ Implement `architecture://` (3-4 weeks)
3. ⏭️ Add `.reveal.yaml` support to core (1-2 weeks)
4. ⏭️ Ship and gather feedback

---

## 📝 Appendix: Original Proposal Source

**Source**: Production codebase architectural audits (2025-12-22)
**Context**: Large-scale production codebases (10K-100K+ lines)
**Session**: prism-flash-1222

**Key Insights from Audits**:
- Reveal excellent for single-file analysis
- Gap in cross-file relational analysis (imports, calls, architecture)
- Need for configurable rules (reduce false positives)
- Practical patterns more valuable than conceptual features

**Validation**: Real-world production codebase audit, measured impact

---

**Status**: Ready for review and integration
**Maintainer**: TIA (consolidation), Reveal team (implementation)
**Last Updated**: 2025-12-22
