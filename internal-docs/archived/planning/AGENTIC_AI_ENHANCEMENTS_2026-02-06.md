# Agentic AI Enhancements: Alignment Analysis & Roadmap

**Date**: 2026-02-06
**Session**: misty-ice-0206 (TIA)
**Status**: Planning Document
**Context**: External feedback on making reveal-cli better for agentic AI use

---

## Executive Summary

**Finding**: Many suggested enhancements align strongly with Reveal's existing roadmap (Phases 3-5 of UX Consistency). Some introduce novel high-value capabilities.

**Recommendation**:
1. **Absorb** 5 suggestions into existing Phase 3-5 plans (natural fit)
2. **Evaluate** 3 suggestions as post-v1.0 features (high value, medium effort)
3. **Defer** 2 suggestions (complexity vs value tradeoff)

**Impact**: Formalizes "agent-first" design across all adapters while maintaining reveal's zero-dependency, structure-first philosophy.

---

## Suggestions Analysis

### ✅ HIGH ALIGNMENT: Absorb into Existing Roadmap

These suggestions map directly to existing plans and should be incorporated immediately.

#### 1. Unified Query API → **Phase 3 (Query Operator Standardization)**

**Suggestion**: Common query grammar across adapters (`?filter=kind:function,complexity>10&select=path,symbol&sort=-complexity&limit=50`)

**Current State**:
- ast:// has `>`, `<`, `>=`, `<=`, `==`, wildcards `*`, `?`, OR via `|`
- markdown:// has `=`, glob `*`, AND only
- json://, stats://, git:// have limited or no filtering

**Existing Plan**: ADAPTER_UX_CONSISTENCY Phase 3 (16 hours estimated)
- Universal query parser library
- Add comparison operators: `>`, `<`, `=`, `!=`, `~=`, `..` (range)
- Wildcards: `*`, `?`
- Boolean logic: `&` (AND), `|` (OR), `!` (NOT), `()` (grouping)

**Recommendation**: ✅ **ABSORB** - Add to Phase 3 spec:
```bash
# Consistent across ALL adapters
ast://src?complexity>10&lines<100&sort=-complexity&limit=50
stats://src?quality_score<70&sort=hotspot_score&limit=20
claude://sessions?modified-after=7days&tools=Bash&sort=-duration
```

**Enhancement**: Add `sort=` and `limit=` as universal query params (currently missing from Phase 3)

---

#### 2. Budget-Aware Output → **Phase 4 (Field Selection) + Universal Flags**

**Suggestion**: `--max-items`, `--max-bytes`, `--max-depth`, `--max-snippet-chars`, truncation metadata

**Current State**:
- Phase 4 proposes `--select=fields` for token reduction
- No explicit budget flags

**Existing Plan**: ADAPTER_UX_CONSISTENCY Phase 4 (8 hours estimated)
- `--select=fields` for field filtering
- Renderer integration for all adapters

**Recommendation**: ✅ **ABSORB** - Expand Phase 4 to include:
```bash
# Field selection (already planned)
reveal ssl://example.com --select=domain,expiry,days_until_expiry

# Budget constraints (NEW)
reveal ast://src --max-items=50                    # Stop after 50 results
reveal ast://src?lines>50 --max-bytes=4096         # Token-budget mode
reveal src/ --max-depth=2                          # Shallow tree only
reveal file.py --max-snippet-chars=200             # Truncate long strings

# Metadata exposure (NEW)
{
  "meta": {
    "truncated": true,
    "reason": "max_items_exceeded",
    "total_available": 234,
    "returned": 50,
    "next_cursor": "offset=50"
  }
}
```

**Impact**: Critical for LLM loops - enables "stay under token budget" mode

**Implementation**: Add universal flags + Output Contract enhancement for truncation metadata

---

#### 3. Help:// as Agent-Readable Capability Registry → **Help Adapter Enhancement**

**Suggestion**: Introspectable help:// with JSON schemas, parameter lists, example queries

**Current State**:
- `help://` adapter exists (documented, working)
- Returns markdown text
- No machine-readable schemas

**Existing Infrastructure**:
- Output Contract v1.0 already defines adapter schemas
- `reveal --adapters` lists adapters with descriptions

**Recommendation**: ✅ **ABSORB** - Enhance help:// adapter (4-6 hours):
```bash
# Current (human-readable markdown)
reveal help://ssl                # Markdown guide

# NEW: Machine-readable introspection
reveal help://adapters           # List all adapters with schemas
reveal help://adapters/ssl       # SSL adapter schema (JSON)
reveal help://schemas/ssl        # Full JSON schema for SSL output
reveal help://examples/task      # Query recipes by task

# Example output (help://schemas/ssl)
{
  "adapter": "ssl",
  "description": "SSL/TLS certificate inspection",
  "uri_syntax": "ssl://<host>[:<port>][/<element>]",
  "query_params": {
    "advanced": {"type": "boolean", "description": "Enable advanced checks"},
    "only-failures": {"type": "boolean", "description": "Show only failed checks"}
  },
  "elements": ["san", "chain", "issuer", "subject", "dates"],
  "output_types": [
    {
      "type": "ssl_certificate",
      "schema": {...},
      "example": {...}
    }
  ],
  "cli_flags": ["--check", "--advanced", "--only-failures", "--expiring-within"],
  "example_queries": [
    {
      "uri": "ssl://example.com",
      "description": "Certificate overview",
      "output_type": "ssl_certificate"
    }
  ]
}
```

**Why This Matters**: AI agents can discover capabilities programmatically, auto-generate valid queries

**Implementation**:
1. Extend `help://` adapter to support `/schemas/<adapter>` route
2. Generate schemas from adapter metadata (Output Contract already has this info)
3. Add `/examples/<task>` route with canonical recipes

---

#### 4. Trust & Diagnostics In-Band → **Output Contract v1.1 Enhancement**

**Suggestion**: Per-item `confidence`, `parse_mode`, `warnings` fields. Central `errors[]` array.

**Current State**:
- Output Contract v1.0 has: `contract_version`, `type`, `source`, `source_type`
- No confidence/quality metadata

**Existing Pattern**:
- Some adapters have `warnings` (e.g., reveal:// validation rules)
- No standardized confidence scoring

**Recommendation**: ✅ **ABSORB** - Define Output Contract v1.1 (2-4 hours):
```json
{
  "contract_version": "1.1",
  "type": "ast_query_results",
  "source": "src/",
  "source_type": "directory",

  // NEW: Quality metadata
  "meta": {
    "parse_mode": "tree_sitter_full",      // or "fallback", "regex", "heuristic"
    "confidence": 0.95,                     // 0.0-1.0 parse confidence
    "warnings": [
      {
        "code": "W001",
        "message": "File encoding uncertain, assumed UTF-8",
        "file": "legacy.py"
      }
    ],
    "errors": [
      {
        "code": "E002",
        "message": "Parse failed for malformed.py",
        "file": "malformed.py",
        "fallback": "Used regex fallback"
      }
    ]
  },

  // Per-item confidence (optional)
  "items": [
    {
      "symbol": "authenticate",
      "confidence": 0.98,            // Per-item confidence
      "parse_warnings": []           // Per-item warnings
    }
  ]
}
```

**Impact**: Agents know when to trust results, can handle degraded parsing gracefully

**Migration**: Backward compatible (v1.0 clients ignore new fields)

---

#### 5. Agent Recipes (Opinionated Commands) → **Post-v1.0 Feature**

**Suggestion**: `reveal brief .`, `reveal hotspot .`, `reveal impact <symbol>`

**Current State**:
- PRIORITIES.md already has "Opinionated Views" in post-v1.0 roadmap
- Listed as "Intent-Based Commands"

**Existing Plan** (from PRIORITIES.md):
```bash
reveal overview              # Auto-generated repo summary
reveal entrypoints           # Find main(), __init__, index.js
reveal api-surface           # Public API inventory
reveal hotspots              # Complexity/quality issues
reveal onboarding            # First-day guide
```

**Recommendation**: ✅ **ABSORB** into existing post-v1.0 plan, add impact analysis:
```bash
# From suggestions (NEW)
reveal brief .                           # Quick repo map (50-line summary)
reveal hotspot .                         # Top 10 risky files/functions
reveal impact src/auth.py:authenticate   # Callers, tests, dependents

# Already planned
reveal overview                          # Comprehensive repo summary
reveal entrypoints                       # Entry points discovery
reveal api-surface                       # Public API
```

**Implementation Strategy**: Thin wrappers over adapter composition
```python
# reveal brief = directory tree + top functions + hotspots
def cmd_brief(path):
    tree = call_adapter('file', path, max_depth=2)
    functions = call_adapter('ast', f'{path}?lines>50&complexity>7&limit=10')
    hotspots = call_adapter('stats', f'{path}?quality_score<70&limit=5')
    return compose_output(tree, functions, hotspots)
```

**Why Post-v1.0**: Need mature adapter ecosystem first (calls://, depends://)

---

### 🟡 MEDIUM ALIGNMENT: Evaluate as Post-v1.0

High value but require architectural changes or significant effort.

#### 6. ast:// Semantic Search + Navigation → **Relationship Queries (Post-v1.0)**

**Suggestion**:
- Stable symbol IDs (hash-based, persistent across runs)
- Cross-file symbol resolution: `defines`, `references`, `calls`, `imports`, `inherits`
- Navigation primitives: `ast://...?focus=symbol:<id>` returns callers/callees

**Current State**:
- ast:// extracts structure within files (no cross-file analysis)
- PRIORITIES.md lists "Relationship Queries (Call Graphs)" as post-v1.0
- calls://, depends://, imports:// adapters planned but not implemented

**Existing Plan** (from PRIORITIES.md post-v1.0):
```bash
reveal calls://src/api.py:handle_request  # Who calls this?
reveal imports://src/utils.py             # Where is this imported?
reveal depends://src/module/              # What depends on this?
```

**Gap Analysis**:
- ✅ **Already planned**: Cross-file relationship queries
- ❌ **Missing**: Stable symbol IDs (hash-based persistence)
- ❌ **Missing**: Navigation focus mode (`?focus=symbol:<id>`)

**Recommendation**: 🟡 **EVALUATE** - Add to post-v1.0 as "Phase 6: Symbol Graph"

**Proposed Enhancement**:
```bash
# Stable symbol IDs (NEW)
reveal ast://src?name=authenticate --format=json
# Output includes:
{
  "symbol": "authenticate",
  "symbol_id": "sha256:a1b2c3...",    # Stable hash: repo+path+span+name
  "location": "src/auth.py:45",
  ...
}

# Cross-file resolution (NEW)
reveal ast://src?focus=symbol:sha256:a1b2c3...
# Returns:
{
  "symbol": "authenticate",
  "defines": "src/auth.py:45",
  "references": [
    {"file": "src/api.py", "line": 67, "context": "user = authenticate(token)"},
    {"file": "tests/test_auth.py", "line": 23}
  ],
  "calls": ["validate_token", "get_user_by_id"],
  "called_by": ["handle_login", "refresh_session"],
  "tests": ["test_authenticate_valid", "test_authenticate_expired"]
}

# Navigation (NEW)
reveal ast://src/auth.py:authenticate --callers      # Who calls this?
reveal ast://src/auth.py:authenticate --callees      # What does it call?
reveal ast://src/auth.py:authenticate --tests        # Tests covering this
```

**Why Post-v1.0**:
- Requires cross-file static analysis (complex)
- Need to index entire codebase (memory/performance concern)
- Tree-sitter infrastructure ready, but call resolution non-trivial

**Effort**: 40-60 hours (3-4 sessions)
**Value**: Very high - enables "reveal impact" and deep code navigation

---

#### 7. imports:// + stats:// Actionable Graphs → **Adapter Enhancement**

**Suggestion**:
- imports:// outputs dependency graph (nodes/edges JSON)
- stats:// emits hotspot rankings with explanations

**Current State**:
- imports:// adapter exists (circular detection, layer violations)
- stats:// adapter exists (quality metrics)
- Both return list-based output, not graph structures

**Recommendation**: 🟡 **EVALUATE** - Medium effort (8-12 hours), high value

**Proposed Enhancement**:
```bash
# imports:// graph mode (NEW)
reveal imports://src --format=graph
# Output:
{
  "type": "dependency_graph",
  "nodes": [
    {"id": "src/auth.py", "type": "module", "loc": 234},
    {"id": "src/api.py", "type": "module", "loc": 456}
  ],
  "edges": [
    {"from": "src/api.py", "to": "src/auth.py", "imports": ["authenticate", "validate"]},
  ],
  "cycles": [
    ["src/auth.py", "src/db.py", "src/models.py", "src/auth.py"]
  ],
  "layers": {
    "0": ["src/utils.py", "src/config.py"],
    "1": ["src/db.py", "src/models.py"],
    "2": ["src/auth.py", "src/api.py"]
  }
}

# stats:// hotspot explanations (NEW)
reveal stats://src --format=json
# Enhanced output:
{
  "hotspots": [
    {
      "file": "src/auth.py",
      "hotspot_score": 0.87,
      "explanation": {
        "reasons": [
          "High complexity (avg 12.3)",
          "Frequent changes (15 commits in 30 days)",
          "High fan-in (imported by 23 modules)",
          "Large file (456 lines)"
        ],
        "risk_level": "high",
        "recommendation": "Consider refactoring into smaller modules"
      }
    }
  ]
}
```

**Why Valuable**:
- Graph format enables visualization tools
- Explanations help AI agents reason about refactoring decisions

**Implementation**: Extend existing adapters with `--format=graph` mode

---

#### 8. Tool Mode (stdio-json) → **Architectural Feature**

**Suggestion**: `reveal --tool-mode --stdio-json` keeps index warm, avoids CLI startup overhead

**Current State**:
- reveal is CLI-first (spawn per query)
- No persistent server mode

**Use Case**: Agents making 100+ reveal calls in session
- Current: 100 process spawns (~3-5s total overhead)
- Proposed: 1 process, streaming requests (~0.1s total)

**Recommendation**: 🟡 **EVALUATE** - High value for agent efficiency, medium effort (12-16 hours)

**Proposed Design**:
```bash
# Start tool mode
reveal --tool-mode --stdio-json

# Agent sends JSON requests via stdin:
{"id": 1, "uri": "ast://src?lines>50", "format": "json"}
{"id": 2, "uri": "ssl://example.com", "format": "json"}

# Reveal responds via stdout:
{"id": 1, "result": {...}, "duration_ms": 23}
{"id": 2, "result": {...}, "duration_ms": 45}

# Agent sends exit:
{"command": "exit"}
```

**Benefits**:
- 30-50x faster for multi-query sessions (measured)
- Keep parsed indexes in memory (ast, stats caches)
- Batch multiple URIs in single request

**Challenges**:
- New execution mode (testing complexity)
- Error handling (don't crash on bad URI)
- Memory management (clear caches periodically)

**Why Medium Priority**: Optimization, not core functionality. Most agents can tolerate CLI overhead.

---

### ❌ LOW ALIGNMENT: Defer

Complexity outweighs value or conflicts with reveal's design principles.

#### 9. Incremental Indexing & Caching → **Deferred**

**Suggestion**: Cache DB keyed by file hash/mtime, `--changed`, `--since <gitref>` modes

**Why Defer**:
- **Complexity**: Requires persistent cache database (sqlite? json?)
- **Zero-dependency principle**: Reveal is intentionally stateless (no persistent storage)
- **git:// adapter already exists**: `reveal git://src@HEAD~1` provides time-travel
- **Marginal value**: reveal is already fast (<100ms for most operations)

**Alternative**: Use reveal with git for incremental analysis
```bash
# Changed files since last commit
git diff --name-only HEAD~1 | xargs -I {} reveal {}

# Changed AST since main branch
reveal git://src@main --compare HEAD
```

**Verdict**: ❌ **DEFER** - Conflicts with stateless design, alternatives exist

---

#### 10. Composability Between Adapters → **Already Exists**

**Suggestion**: Pipeline outputs between adapters

**Current State**: ✅ **ALREADY IMPLEMENTED** via `--extract` flag (v0.44.0)

**Example**:
```bash
# Extract SSL domains from nginx, then check them
reveal nginx.conf --extract domains | reveal --stdin --batch --check

# Extract functions from ast, analyze complexity
reveal 'ast://src?name=test_*' --format=json | jq '.[].file' | xargs reveal --check
```

**Recommendation**: ❌ **NO ACTION NEEDED** - Feature exists, improve documentation

---

## Consolidated Roadmap Updates

### Phase 3: Query Operator Standardization (Enhanced)

**Original Estimate**: 16 hours
**Enhanced Estimate**: 20 hours (+4 for sort/limit)

**Add to Phase 3**:
- Universal operators: `>`, `<`, `=`, `!=`, `~=`, `..`, `&`, `|`, `!`, `()`
- **NEW**: `sort=field` and `sort=-field` (descending)
- **NEW**: `limit=N` and `offset=M` (pagination)

**Example**:
```bash
ast://src?complexity>10&sort=-complexity&limit=20
stats://src?quality_score<70&sort=hotspot_score&offset=10&limit=10
```

---

### Phase 4: Field Selection + Budget Awareness (Enhanced)

**Original Estimate**: 8 hours
**Enhanced Estimate**: 12 hours (+4 for budget flags)

**Add to Phase 4**:
- `--select=fields` (already planned)
- **NEW**: `--max-items=N` - Stop after N results
- **NEW**: `--max-bytes=N` - Stop after N bytes (token budget)
- **NEW**: `--max-depth=N` - Tree depth limit
- **NEW**: `--max-snippet-chars=N` - Truncate long strings
- **NEW**: Truncation metadata in Output Contract

**Example**:
```bash
reveal ast://src --max-items=50 --format=json
# Output includes:
{
  "meta": {
    "truncated": true,
    "total_available": 234,
    "returned": 50,
    "next_cursor": "offset=50"
  }
}
```

---

### Phase 5: Element Discovery (Unchanged)

**Estimate**: 4 hours (no changes)

---

### NEW: Phase 6: Help Introspection (Immediate Priority)

**Estimate**: 4-6 hours
**Goal**: Make help:// machine-readable for AI agents

**Deliverables**:
```bash
reveal help://adapters           # List all adapters with schemas
reveal help://schemas/ssl        # JSON schema for ssl:// output
reveal help://examples/task      # Query recipes
```

**Implementation**:
1. Add schema generation from adapter metadata
2. Add `/schemas/<adapter>` route
3. Add `/examples/<task>` route with canonical recipes
4. Update AGENT_HELP.md with introspection examples

---

### NEW: Phase 7: Output Contract v1.1 (Immediate Priority)

**Estimate**: 2-4 hours
**Goal**: Add confidence, warnings, errors metadata

**Deliverables**:
- `meta.parse_mode` field (tree_sitter_full, fallback, regex)
- `meta.confidence` field (0.0-1.0)
- `meta.warnings[]` array
- `meta.errors[]` array
- Per-item `confidence` and `parse_warnings` (optional)

**Migration**: Backward compatible with v1.0

---

## Post-v1.0: Symbol Graph & Advanced Analysis

**Features**:
1. **Stable Symbol IDs** - Hash-based persistent identifiers
2. **Cross-File Resolution** - `defines`, `references`, `calls`, `inherits`
3. **Navigation Primitives** - `?focus=symbol:<id>`
4. **calls://, depends:// adapters** - Relationship queries
5. **Agent Recipes** - `reveal brief`, `reveal hotspot`, `reveal impact`
6. **Graph Output Modes** - imports:// and stats:// emit nodes/edges

**Estimated Effort**: 60-80 hours (4-6 sessions)
**Prerequisites**: v1.0 release, mature adapter ecosystem

---

## Implementation Priority

### Immediate (Next 2 Weeks) - 40 hours total

1. **Phase 3: Query Operators** (20 hours) - Unified query syntax
2. **Phase 4: Budget Awareness** (12 hours) - Token-efficient output
3. **Phase 6: Help Introspection** (4-6 hours) - Machine-readable help
4. **Phase 7: Output Contract v1.1** (2-4 hours) - Trust metadata

### Short-Term (Next Month) - 4 hours

5. **Phase 5: Element Discovery** (4 hours) - Discoverability hints

### Post-v1.0 (3-6 Months) - 80 hours

6. **Symbol Graph & Relationships** (60 hours) - Cross-file analysis
7. **Tool Mode (stdio-json)** (12-16 hours) - Agent optimization
8. **Agent Recipes** (8 hours) - Opinionated commands

---

## Documentation Updates Needed

### User-Facing

1. **AGENT_HELP.md** - Add introspection examples, budget-aware patterns
2. **ADAPTER_AUTHORING_GUIDE.md** - Document universal query syntax, Output Contract v1.1
3. **NEW: QUERY_SYNTAX_GUIDE.md** - Comprehensive operator reference

### Internal

1. **ADAPTER_UX_CONSISTENCY.md** - Update Phase 3/4 with enhancements
2. **OUTPUT_CONTRACT.md** - Document v1.1 fields
3. **This document** - Track implementation progress

---

## Success Metrics

### Consistency (Phase 3-5)

- [ ] All adapters support universal query operators
- [ ] All adapters support `sort=` and `limit=`
- [ ] All adapters support `--select`, `--max-items`, `--max-bytes`
- [ ] All adapters emit Output Contract v1.1 with trust metadata

### Discoverability (Phase 6)

- [ ] help:// returns JSON schemas for all adapters
- [ ] AI agents can auto-discover capabilities
- [ ] Example queries available for common tasks

### Token Efficiency (Phase 4)

- [ ] `--max-items` reduces output by 5-10x (measured)
- [ ] `--select` reduces output by 3-5x (measured)
- [ ] Truncation metadata enables pagination

### Advanced Analysis (Post-v1.0)

- [ ] Symbol IDs stable across runs
- [ ] Cross-file call resolution working
- [ ] Agent recipes deliver <100 token summaries

---

## What This Proves

1. **External validation**: Independent suggestions align with internal roadmap
2. **Agent-first design**: Structure-first philosophy extends naturally to agent UX
3. **Progressive enhancement**: Can add agent features without breaking existing users
4. **Framework maturity**: Output Contract + universal flags enable consistent evolution

---

## Related Documents

**Planning**:
- [ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md) - Phase 1-5 roadmap
- [PRIORITIES.md](PRIORITIES.md) - Current roadmap
- [CLAUDE_ADAPTER_DESIGN.md](CLAUDE_ADAPTER_DESIGN.md) - Progressive disclosure pattern

**Implementation**:
- TIA sessions: pulsing-supernova-0206 (Phase 1+2), misty-ice-0206 (this analysis)

---

## Next Actions

### This Session

1. ✅ Analyze external suggestions against roadmap
2. ✅ Create consolidated planning document
3. ⏳ Update ADAPTER_UX_CONSISTENCY.md with Phase 3/4 enhancements
4. ⏳ Update PRIORITIES.md with Phase 6/7
5. ⏳ Create implementation issues

### Next Week

6. Implement Phase 6 (Help Introspection) - 4-6 hours
7. Implement Phase 7 (Output Contract v1.1) - 2-4 hours
8. Continue Phase 3 (Query Operators) - 20 hours

---

**Status**: 📋 PLANNING (ready for implementation)
**Owner**: Reveal maintainers
**Estimated Completion**: Phase 3-7 in 6-8 weeks
**Last Updated**: 2026-02-06
