---
title: Review Validation & Improvement Recommendations
category: strategic
date: 2026-03-17
---

# Review Validation & Improvement Recommendations

**Purpose**: Validate the external review of Reveal, confirm what it got right, and provide actionable improvement recommendations across architecture, adapters, documentation, testing, UX, and strategic positioning.

**Audience**: Reveal core team and contributors

---

## Part 1: Review Validation

### Confirmed Accurate

The following review observations were validated against the codebase:

#### 1. Multi-domain adapter architecture

**Claim**: Reveal is an "adapter-based inspection framework" spanning code, data, infrastructure, and documents.

**Verified**: 19 adapter directories under `reveal/adapters/` plus 3 standalone adapter files (`env.py`, `imports.py`, `xlsx.py`). The URI scheme routing in `base.py` confirms a deliberate abstraction layer, not accidental sprawl.

| Domain | Adapters |
|--------|----------|
| Code semantics | `ast://`, `calls://`, `imports://`, `python://`, `diff://` |
| Data systems | `mysql://`, `sqlite://`, `json://`, `xlsx://` |
| Infrastructure | `ssl://`, `nginx://`, `domain://`, `cpanel://`, `autossl://`, `env://` |
| Documents | `markdown://`, `stats://`, `git://` |
| Meta/self-referential | `help://`, `reveal://`, `claude://` |

#### 2. Progressive disclosure as architectural principle

**Claim**: Structure -> Element -> Detail is the design center.

**Verified**: The `BaseAdapter` class enforces this via `get_structure()` and `get_element()` methods. The Output Contract (v1.1) codifies required fields (`contract_version`, `type`, `source`, `source_type`) and the three-tier help system (`--help`, `--agent-help`, `help://`) mirrors this same pattern. Token efficiency is structural, not accidental.

#### 3. Unified but not formal query language

**Claim**: Coherent query params, but no strongly typed query language.

**Verified**: `utils/query.py` provides `parse_query_params()` used across adapters (unified in v0.63.0, replacing 4 hand-rolled loops). Universal operators (`=`, `!=`, `>`, `<`, `>=`, `<=`, `~=`, `..`) exist. But there is no formal grammar, no query planner, no type system for query expressions. The QUERY_SYNTAX_GUIDE.md documents conventions, not a spec.

#### 4. Analysis depth positioning

**Claim**: Between grep/AST tools and CodeQL/research-grade analyzers.

**Verified**: `calls://` provides cross-file call graphs with BFS traversal (`?depth=N`, max 5), callers index, and Graphviz output. `ast://` handles complexity, filtering, and element queries. Rules cover bugs (B-series), maintainability (M-series), imports (I-series), validation (V-series), links (L-series), and nginx (N-series). However: no dataflow analysis, no taint tracking, no formal verification. The `calls://` adapter is ~722 LOC — functional but not CodeQL-scale.

#### 5. Workflow layer

**Claim**: Reveal is inspection + operational workflows.

**Verified**: Six subcommands shipped: `check`, `review`, `health`, `pack`, `hotspots`, `dev`. These are orchestration commands — `review` composes diff + check + hotspots + complexity. `health` provides exit codes (0/1/2) for CI. `pack` does token-budgeted snapshots. This is genuinely a category shift from pure inspection.

#### 6. README claims

**Claim**: "22 adapters" and "80+ languages" should be treated as repo-claimed.

**Verified**: README says "22 built-in adapters" but ROADMAP lists 21 implemented. The `calls://` adapter appears shipped (v0.62.0+) but ROADMAP's adapter table still lists it as "Planned". Language count: 31 built-in analyzers + 165+ via tree-sitter fallback. The "80+" claim in README understates actual capability. **Recommendation**: Update README to say "22 adapters" (counting calls://) and "190+ languages" to match reality.

---

### Review Gaps Confirmed

The review correctly identified these as underdeveloped in its own analysis:

#### 1. Schema/self-describing infrastructure is strategically important

**Evidence**: `help://schemas/<adapter>` provides machine-readable JSON schemas for all adapters. `get_schema()` is implemented across 29 files. The help system has three tiers designed for different consumers (humans, AI agents, programmatic discovery). `available_elements` enables autonomous exploration.

This makes Reveal **self-describing infrastructure** — a property that enables:
- AI agents to safely explore without external documentation
- Programmatic adapter discovery and capability detection
- Reduced documentation maintenance burden

#### 2. Adapter quality variance is a real risk

**Evidence from LOC and test analysis**:

| Adapter | Lines of Code | Unit Tests | Error Handling (except blocks) | Maturity |
|---------|--------------|------------|-------------------------------|----------|
| claude:// | 3,478 | 5 test files | Moderate | Deep, complex |
| ssl:// | 2,651 | 0 unit tests | 17 except blocks (highest) | Production-hardened via incidents |
| mysql:// | 2,118 | 0 unit tests | 8 except blocks | Deep, modular |
| python:// | 1,529 | 0 unit tests | Unknown | Moderate depth |
| domain:// | 1,456 | 0 unit tests | 18 except blocks | Feature-rich |
| ast:// | 1,335 | 38 unit tests | 5 except blocks | Mature, well-tested |
| markdown:// | 1,304 | 0 unit tests | 9 except blocks | Active development |
| nginx:// | 1,042 | 109 combined tests | 6 except blocks | Battle-tested |
| calls:// | 722 | 68 unit tests (highest ratio) | 3 except blocks | Newest, most active |
| sqlite:// | 634 | 0 unit tests | **0 except blocks** | Minimal error handling |
| autossl:// | 754 | 0 unit tests | Unknown | Domain-specific |

The variance is multi-dimensional:

1. **Size**: `claude://` (3,478 LOC) is 5.5x larger than `calls://` (722 LOC)
2. **Test coverage inversion**: `calls://` has 68 unit tests for 722 LOC (best ratio), while `ssl://` has 0 unit tests for 2,651 LOC — relying on production hardening instead
3. **Error handling gap**: `sqlite://` has zero `except` blocks despite being a database adapter. Compare to `ssl://` (17) and `domain://` (18)
4. **Documentation depth**: `ast://` has 429-line help.py; `sqlite://` has 87-line YAML — a 5x difference
5. **Development velocity**: `calls://` had 7 commits in 2 weeks; most others had 1

Some adapters (ssl, mysql, nginx) have been hardened through production incidents (B1, B3, N003 fixes documented in CHANGELOG). Newer adapters haven't had this exposure yet. The `sqlite://` adapter's zero error handling is the most concrete risk.

#### 3. Operational scope is read-only by design

**Evidence**: ROADMAP explicitly states under "Not Planned": `--fix` auto-fix is a "mission violation" — "reveal reveals, doesn't modify." The tool is deliberately read-heavy with light evaluation and packaging. No mutation, no write operations, no automation orchestration. This is a principled constraint, not an oversight.

---

## Part 2: Improvement Recommendations

### A. Architecture & Core

#### A1. Formalize the query language

**Current state**: Conventions documented in QUERY_SYNTAX_GUIDE.md, universal operators implemented, but no formal grammar.

**Recommendation**: Define a minimal grammar spec (even informal BNF) that adapter authors must support. This prevents drift as adapters multiply. Priority: medium.

```
query      := param ("&" param)*
param      := key "=" value | key operator value
operator   := "!=" | ">=" | "<=" | ">" | "<" | "~=" | ".."
value      := string | number | boolean
```

**Why**: Without this, each new adapter will subtly reinvent query parsing, even with `parse_query_params()` available. The unification in v0.63.0 was the right move — now lock it down.

#### A2. Adapter capability matrix

**Current state**: Each adapter self-reports capabilities via `get_schema()`, but there's no aggregated view.

**Recommendation**: Generate a machine-readable capability matrix (`reveal help://capabilities` or similar) that shows which adapters support which features: `batch`, `advanced`, `format=json`, `format=dot`, progressive disclosure depth, query operators supported.

**Why**: Users and agents currently must probe each adapter individually. A single matrix enables informed adapter selection and exposes quality variance transparently.

#### A3. Adapter conformance test suite

**Current state**: `test_adapter_contracts.py` verifies schema contracts. Some adapters have been added late to this suite (calls:// was missing until v0.62.0).

**Recommendation**: Create a comprehensive adapter conformance harness that automatically tests every registered adapter against:
- Schema completeness (output_types, example_queries, notes)
- Output contract v1.1 compliance
- Progressive disclosure (structure -> element -> detail roundtrip)
- Query parameter handling (at least `format=json`)
- Error handling for invalid inputs

Run this in CI for every adapter on every PR.

**Why**: This prevents the "adapter quality variance" risk mechanically. A new adapter that doesn't pass conformance can't merge.

#### A4. Adapter quality tiers with automated enforcement

**Current state**: Stability badges exist (Experimental, Beta, Stable) but are manually assigned.

**Recommendation**: Define objective criteria for each tier:

| Tier | Requirements |
|------|-------------|
| Experimental | get_schema() + get_structure() + basic tests |
| Beta | + get_element() + output contract compliance + 20+ tests + docs |
| Stable | + conformance suite pass + production incident survival + 50+ tests |

Auto-compute tier from test coverage, conformance results, and LOC metrics.

**Why**: Transparent quality tiers set correct user expectations. "The mental model is unified, but capability depth may not be" — making this visible is better than hiding it.

---

### B. Adapters

#### B1. Strengthen adapters with the largest quality gaps

**Priority targets** (by risk, not recency):

| Adapter | Gap | Action |
|---------|-----|--------|
| `sqlite://` (634 LOC, 0 tests, 0 except blocks) | **Critical**: zero error handling for a database adapter | Add try/except for connection failures, corrupt databases, locked files, permission errors. Add unit tests. |
| `ssl://` (2,651 LOC, 0 unit tests) | High: most complex adapter with no unit tests | Extract testable units from the 104 methods. Production incidents prove it works, but regressions are undetectable. |
| `mysql://` (2,118 LOC, 0 unit tests) | High: 74 methods, 8 classes, zero unit test coverage | Add connection mock tests, health check validation, replication monitoring edge cases. |
| `domain://` (1,456 LOC, 0 unit tests) | Medium: 53 methods with good error handling but no test verification | Add DNS resolution tests, timeout handling, partial propagation scenarios. |
| `autossl://` (754 LOC, 0 unit tests) | Medium: log parsing with no failure mode tests | Add malformed log handling, multi-run edge cases. |

#### B2. Cross-adapter integration tests

**Current state**: Adapters are tested in isolation.

**Recommendation**: Add integration tests for cross-adapter workflows:
- `ssl://` + `nginx://` + `cpanel://` (the full-audit composition)
- `ast://` + `calls://` + `imports://` (code analysis pipeline)
- `reveal review` (which composes diff + check + hotspots)

**Why**: The composition story is Reveal's differentiator. If compositions break silently, users lose trust in the unified model.

#### B3. Standalone adapter files should become packages

**Current state**: `env.py`, `imports.py`, `xlsx.py` are standalone files while other adapters are packages (directories with `__init__.py`).

**Recommendation**: Migrate these to package format when they next need feature additions. This allows adding `help.py`, `renderer.py`, and test fixtures consistently.

**Why**: Consistency reduces contributor confusion and enables the conformance suite to treat all adapters uniformly.

---

### C. Self-Describing Infrastructure

#### C1. Elevate help://schemas/ as a first-class feature

**Current state**: Mentioned in docs but not prominently featured.

**Recommendation**:
- Add `reveal --discover` that outputs the full adapter registry with schemas in a single JSON document
- Ensure every adapter's schema includes `input_types`, `output_types`, `query_params`, and `examples`
- Document the schema format as a stable API (part of Output Contract)

**Why**: This is Reveal's most underappreciated strategic asset. Self-describing tools are composable tools. AI agents, scripts, and future UIs all benefit from machine-readable capability descriptions.

#### C2. Add adapter relationship graph

**Current state**: Some adapters reference others (ssl -> nginx, cpanel -> ssl + nginx), but relationships aren't formalized.

**Recommendation**: Add a `related_adapters` field to schemas (some already have it) and expose it via `reveal help://relationships` as a navigable graph.

**Why**: New users don't know that `cpanel://user/full-audit` composes ssl + acl-check + nginx. Making adapter relationships discoverable enables progressive exploration of the tool itself.

#### C3. Schema versioning

**Current state**: Output Contract is versioned (v1.1). Individual adapter schemas are not.

**Recommendation**: Version adapter schemas. When a schema changes (new output_types, removed query params), bump the version. Consumers can then detect incompatible changes.

**Why**: As Reveal grows, schema stability becomes a contract with downstream tools and agents.

---

### D. Documentation

#### D1. Update stale cross-references

**Current state**: ROADMAP adapter table lists `calls://` as "Planned" but it shipped in v0.62.0. README claims "22 adapters" while ROADMAP says 21.

**Recommendation**: Audit all cross-references between README, ROADMAP, CHANGELOG, and docs/INDEX.md. Consider generating adapter counts and language counts from code.

#### D2. Create an architecture overview document

**Current state**: No single document explains the adapter model, progressive disclosure, output contract, and help system as a coherent architecture.

**Recommendation**: Write `ARCHITECTURE.md` (~500 lines) covering:
- URI scheme routing
- Adapter lifecycle (init -> structure -> element -> render)
- Output contract enforcement
- Help system tiers
- Query parameter pipeline
- Subcommand orchestration model

**Why**: Contributors currently need to read 5+ documents to understand the system. A single architecture document accelerates onboarding.

#### D3. Add "When to use which adapter" decision tree

**Current state**: Adapters are documented individually. No guidance on which adapter to use for a given task.

**Recommendation**: Add a task-oriented decision tree to AGENT_HELP.md and help://quick-start:

```
"I want to understand code structure" → ast://
"I want to know who calls what" → calls://
"I want to check import health" → imports://
"I want SSL certificate status" → ssl://
"I want a full server audit" → cpanel://user/full-audit
```

**Why**: The multi-domain nature is powerful but can overwhelm new users. Progressive disclosure of the tool itself.

---

### E. Testing

#### E1. Close the test gap on newer adapters

**Current state**: 6,009 tests total. Coverage: scaffold 100%, tools 100%, adapter 94%.

**Targets**:
- `calls://`: Needs cross-file resolution edge cases, large-project performance tests
- `autossl://`: Needs malformed input handling, multi-run parsing
- `sqlite://`: Needs schema edge cases, large database handling

#### E2. Property-based testing for query parsing

**Current state**: Unit tests with specific inputs.

**Recommendation**: Add hypothesis-based property tests for `parse_query_params()` to ensure the query parser handles arbitrary input without crashing. This is the shared foundation — it must be bulletproof.

#### E3. Performance benchmarks

**Current state**: Some performance improvements documented (I002 cache: 13min -> 33s, parallelism: 48s -> 21.5s).

**Recommendation**: Add benchmark tests for:
- `ast://` on 10K+ file projects
- `calls://` index building on large codebases
- `reveal check` on 5K+ files
- `reveal pack` token counting accuracy

Track regressions in CI.

---

### F. Strategic Positioning

#### F1. Elevate "local-first" as a core property

**Current state**: Mentioned casually. Not in README features.

**Recommendation**: Add to README and positioning:

> **Local-first**: No backend required. No data leaves your machine. Runs in CI, scripts, and air-gapped environments.

**Why**: In an era of SaaS-heavy developer tools, local-first is a genuine differentiator for:
- Privacy-sensitive environments
- CI/CD pipelines (no API keys needed)
- Composability with Unix tools
- Offline/air-gapped operation

#### F2. Clarify the "semantic operations interface" scope

**Recommendation**: Adopt a precise positioning statement:

> Reveal is a local-first, adapter-driven semantic inspection layer that unifies how engineers and AI systems explore code, infrastructure, data, and documents through progressive disclosure and structured, token-aware output.

And clarify scope boundaries:

| Reveal does | Reveal does not |
|-------------|-----------------|
| Inspect / read | Modify / write |
| Evaluate quality | Auto-fix issues |
| Package for LLMs | Run LLM inference |
| Compose workflows | Orchestrate pipelines |
| Describe itself | Require external config |

#### F3. Competitive positioning clarity

**Recommendation**: Don't compare to any single tool. Instead position as:

> A CLI-native, multi-domain alternative to the idea of a unified developer/ops inspection plane.

Overlaps with but is not a competitor to:
- **CodeQL/Semgrep**: Reveal is broader (multi-domain) but shallower (no dataflow)
- **Sourcegraph**: Reveal is local-first, no indexing server needed
- **AST tools (tree-sitter CLI, ast-grep)**: Reveal adds progressive disclosure and multi-domain context
- **jq/yq**: Reveal adds semantic understanding beyond structural queries

---

### G. Risk Mitigation

#### G1. Surface area management

**Risk**: 22 adapters across 5 domains creates maintenance burden.

**Mitigation**:
- Automated conformance testing (A3) catches regressions
- Quality tiers (A4) set expectations
- Adapter authoring guide + scaffolding (`reveal dev new-adapter`) reduces creation cost
- Consider freezing adapter count until v1.0 — improve existing before adding new

#### G2. Adapter quality variance

**Risk**: Users assume all adapters have equal depth. The `claude://` adapter at 3,478 LOC is a different beast than `sqlite://` at 634 LOC.

**Mitigation**:
- Visible quality tiers in help output
- Conformance suite as a quality floor
- Document "depth" per adapter in help://schemas

#### G3. Query language divergence

**Risk**: Without a formal spec, new contributors may bypass `parse_query_params()`.

**Mitigation**:
- Lint rule or CI check that greps for `split('&')` or `split('=')` in adapter code
- Document `parse_query_params()` as mandatory in ADAPTER_AUTHORING_GUIDE.md
- The v0.63.0 unification set the right precedent — enforce it

#### G4. Output contract compliance

**Risk**: New adapters or features may break the output contract.

**Mitigation**:
- The existing `test_adapter_contracts.py` is the right approach
- Extend it to cover all v1.1 fields including `meta` (trust metadata)
- Add CI enforcement that blocks merges on contract violations

---

## Part 3: Quick Wins (Implementable in 1-2 sessions each)

| # | Improvement | Impact | Effort |
|---|------------|--------|--------|
| 1 | Add error handling to `sqlite://` adapter (0 except blocks) | **Safety** | Low |
| 2 | Fix ROADMAP `calls://` "Planned" -> "Implemented" | Accuracy | Trivial |
| 3 | Update README adapter count and language count | Accuracy | Trivial |
| 4 | Add unit tests for `ssl://` (2,651 LOC, 0 unit tests) | Reliability | Medium |
| 5 | Add adapter conformance smoke test to CI | Quality floor | Medium |
| 6 | Add `reveal --discover` (dump full adapter registry as JSON) | Discoverability | Low |
| 7 | Add "local-first" to README features section | Positioning | Trivial |
| 8 | Create task-oriented decision tree in help://quick-start | UX | Low |
| 9 | Add `related_adapters` to all adapter schemas | Navigation | Low |
| 10 | Lint rule blocking raw query parsing in adapters | Consistency | Low |

---

## Part 4: The One-Sentence Description

> **Reveal is a local-first, adapter-driven semantic inspection layer that unifies how engineers and AI systems explore code, infrastructure, data, and documents through progressive disclosure and structured, token-aware output.**

This captures:
- **Local-first**: No backend, no SaaS dependency
- **Adapter-driven**: Extensible, multi-domain by design
- **Semantic inspection**: Not just structural — understands meaning
- **Unified**: One tool, one mental model across domains
- **Engineers and AI systems**: Dual audience, token-aware
- **Progressive disclosure**: The architectural principle
- **Structured output**: Output contract, JSON, composable

---

*Document generated 2026-03-17 from codebase analysis of Reveal v0.63.0*
