---
date: 2026-02-07
session: zibeta-0207
type: current-priorities
status: active
---

# Reveal Current Priorities - February 2026

**Last Updated**: 2026-02-07 (Session: zibeta-0207)
**Project Version**: v0.47.0
**Overall Status**: Strong foundation, focused quality improvements

---

## Current State Summary

### ✅ Recently Completed

**Phases 1, 2, 6, 7 - UX Consistency** (v0.47.0)
- ✅ Phase 1: Format consistency (all 16 adapters support --format json|text)
- ✅ Phase 2: Batch processing (universal --batch flag with aggregation)
- ✅ Phase 6: Help introspection (all 15 adapters have machine-readable schemas)
- ✅ Phase 7: Output Contract v1.1 (trust metadata for AI agents)

**Verification Sessions**:
- sapphire-spark-0207: Phase 1 format consistency + test expansion (domain, claude, imports)
- zibeta-0207: Phase 2 batch processing + Phase 6/7 verification + quality audit

**Test Suite**:
- 2912 tests passing ✅
- 73% overall coverage
- Test runtime: 110 seconds

### 🔄 In Progress

**UX Consistency Phases 3-5**:
- Phase 3: Query operator standardization (~20 hours remaining)
- Phase 4: Field selection + budget awareness (~12 hours)
- Phase 5: Element discovery (~6 hours)

---

## Priority 1: Test Coverage Expansion (HIGH)

**Current Status**: 73% coverage, critical gaps in database adapters

### Critical Gaps (< 20% coverage)

| Adapter | Coverage | Lines Missing | Impact |
|---------|----------|---------------|--------|
| MySQL adapter | 19.5% | 264 | Production database adapter |
| SQLite adapter | 18.2% | 99 | Production database adapter |
| MySQL renderer | 11.4% | 78 | Output rendering |
| SQLite renderer | 12.5% | 63 | Output rendering |
| Domain DNS | 14.5% | 65 | DNS functionality |

**Why Priority 1**:
- MySQL and SQLite are production features with <20% coverage
- Quality risk for user-facing database adapters
- Established test pattern makes implementation straightforward
- Previous sessions show 40 min per adapter with pattern

### Action Plan

**Week 1** (8 hours):
1. MySQL adapter tests (3 hours)
   - Schema tests (6): validate AI agent documentation
   - Renderer tests (4): validate output formatting
   - Target: 70%+ coverage

2. SQLite adapter tests (2 hours)
   - Apply same pattern
   - Target: 70%+ coverage

3. MySQL renderer tests (1.5 hours)
4. SQLite renderer tests (1.5 hours)

**Expected Outcome**: Eliminate critical quality risk, raise coverage to ~76%

---

## Priority 2: Documentation Currency (COMPLETE ✅)

**Status**: Completed in zibeta-0207 session

**Changes Made**:
1. ✅ Updated ADAPTER_UX_CONSISTENCY.md (Phase 6 checkboxes, verification dates)
2. ✅ Updated ROADMAP.md (added v0.46.0, v0.47.0 entries, updated current focus)
3. ✅ Updated CHANGELOG.md (added Phase 1, 2, 7 completion notes)
4. ✅ Created CURRENT_PRIORITIES_2026-02.md (this file)

**Result**: All documentation reflects current project status

---

## Priority 3: Phase 3 - Query Operator Standardization (MEDIUM)

**Status**: Infrastructure complete, operators need standardization

**Completed** (Phase 3a - Query Infrastructure Unification):
- Unified query parser across 5 adapters
- -299 duplicate lines removed
- ast, stats, markdown, git, json adapters unified

**Remaining** (Phase 3b - Operator Standardization):
- Standardize operators across all query-capable adapters
- Add sort/limit/offset query parameters
- Document operator reference for all adapters

**Effort Estimate**: 20 hours
**Impact**: High consistency value, enables predictable queries

**When**: After test coverage expansion (Priority 1)

---

## Priority 4: Code Quality Improvements (LOW)

**Status**: Well-managed, minor improvements available

### TODOs Found (9 total)

**High Priority**:
1. Domain WHOIS integration (2 TODOs) - Feature incomplete
2. SSL nginx validation (1 TODO) - Flag incomplete

**Low Priority**: 6 minor TODOs in various modules

### Deprecated Code (19 references)

**Status**: All well-managed with documented replacements
- Import extractors: Deprecated functions, replacements exist
- Config loading: Warning issued, backward compatible
- Markdown traversal: Replaced with tracker object

**Action**: Document as technical debt, address opportunistically

---

## Priority 5: Phase 4 & 5 Implementation (MEDIUM)

### Phase 4: Field Selection + Budget Awareness (~12 hours)

**Goal**: Token reduction for AI agents
**Features**:
- `--select=fields` for specific field output
- `--max-items`, `--max-bytes`, `--max-depth` budget flags
- Truncation metadata in output contract

**When**: After Phase 3 completion

### Phase 5: Element Discovery (~6 hours)

**Goal**: Auto-show available elements
**Features**:
- Adapters display available elements in overview
- JSON output includes element list
- Breadcrumbs reference elements

**When**: After Phase 4 completion

---

## Next Actions

### This Week (8 hours)

1. **MySQL adapter test expansion** (3 hours)
   - Start Monday
   - Apply established pattern (6 schema + 4 renderer tests)
   - Target: 70%+ coverage

2. **SQLite adapter test expansion** (2 hours)
   - Continue Tuesday
   - Same pattern
   - Target: 70%+ coverage

3. **Renderer tests** (3 hours)
   - MySQL and SQLite renderers
   - Complete by Wednesday

**Expected Outcome**: 76% coverage, critical gaps eliminated

### Next Week (20 hours)

**Phase 3b: Query Operator Standardization**
1. Audit current operator support across adapters
2. Design universal operator set
3. Implement across all query-capable adapters
4. Document operator reference
5. Add tests for operator consistency

---

## Success Metrics

### Coverage Targets

| Metric | Current | Target (Week 1) | Target (Month) |
|--------|---------|-----------------|----------------|
| Overall coverage | 73% | 76% | 80% |
| MySQL adapter | 19.5% | 70%+ | 75%+ |
| SQLite adapter | 18.2% | 70%+ | 75%+ |
| Critical gaps (< 20%) | 4 adapters | 0 adapters | 0 adapters |

### Phase Completion

| Phase | Current | Target (Month) |
|-------|---------|----------------|
| Phase 1-2, 6-7 | ✅ Complete | Maintain |
| Phase 3 | 50% (infra done) | 100% Complete |
| Phase 4 | Not started | Started |
| Phase 5 | Not started | Planned |

---

## Long-Term Strategy (Post-v1.0)

**From ROADMAP.md**:
- Relationship queries (call graphs)
- Intent-based commands
- Cross-language refactoring
- AI-assisted code generation

**Current Focus**: Finish UX consistency phases, achieve 80%+ coverage, then evaluate v1.0 readiness.

---

## Notes for Future Sessions

### Established Patterns

**Test Expansion Pattern** (40 min per adapter):
- 6 schema tests: Validate AI agent documentation
- 4 renderer tests: Validate output formatting
- Proven in: git, stats, domain, claude, imports adapters

**Verification Pattern** (15-20 min per phase):
1. Live testing of claimed features
2. Code review of implementation
3. Update planning docs with verification dates
4. Document in session README

### Session Continuity

**Previous Sessions**:
- razor-zeppelin-0207: Query infrastructure unification
- onyx-gleam-0207: Test expansion (git, stats) + UX analysis
- sapphire-spark-0207: Format verification + test expansion (domain, claude, imports)
- zibeta-0207: Phase 2 verification + Phase 6/7 verification + quality audit

**Next Session Should**:
1. Read this file for current priorities
2. Check REVEAL_QUALITY_REPORT.md for detailed coverage analysis
3. Start with MySQL adapter test expansion

---

## References

**Key Documents**:
- [ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md) - Phase details and status
- [TECHNICAL_DEBT_RESOLUTION.md](TECHNICAL_DEBT_RESOLUTION.md) - Technical debt tracking
- [REVEAL_QUALITY_REPORT.md](/home/scottsen/src/tia/sessions/zibeta-0207/REVEAL_QUALITY_REPORT.md) - Detailed coverage analysis

**User Documentation**:
- [reveal/docs/AGENT_HELP.md](../../reveal/docs/AGENT_HELP.md) - AI agent reference
- [reveal/docs/RECIPES.md](../../reveal/docs/RECIPES.md) - Task workflows

---

**Status**: ✅ Documentation current, clear priorities, test expansion ready to start
**Next Action**: MySQL adapter test expansion (3 hours)
**Session**: zibeta-0207
