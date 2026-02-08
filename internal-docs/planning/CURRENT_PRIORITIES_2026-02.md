---
date: 2026-02-08
session: vilalo-0208
type: current-priorities
status: active
updated_from: cooling-frost-0208
---

# Reveal Current Priorities - February 2026

**Last Updated**: 2026-02-08 (Session: vilalo-0208)
**Previous Update**: 2026-02-08 (Session: cooling-frost-0208)
**Project Version**: v0.47.2 (Phases 3-5 complete)
**Overall Status**: Core UX consistency complete (Phases 1-5), documentation consolidation in progress

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

### ✅ Recently Completed (February 2026)

**UX Consistency Phases 3-5**:
- ✅ Phase 3: Query operator standardization (Complete 2026-02-08)
- ✅ Phase 4: Field selection + budget awareness (Complete 2026-02-08)
- ✅ Phase 5: Element discovery (Complete 2026-02-08)

**Result**: Core UX consistency effort (Phases 1-5) complete. Reveal now provides universal format consistency, batch processing, query operators, field selection, and element discovery.

---

## Priority 1: Test Coverage Status - UPDATED 2026-02-08

**Current Status**: 75% overall coverage (updated from 73%)

**IMPORTANT UPDATE**: Previous coverage numbers were severely outdated. Actual current state measured 2026-02-08:

### Database Adapter Coverage (Actual)

| Adapter | Actual Coverage | Lines Missing | Status |
|---------|-----------------|---------------|--------|
| **SQLite adapter** | **96%** | 8/193 | ✅ **COMPLETE** |
| **SQLite renderer** | **90%** | 7/72 | ✅ **COMPLETE** |
| **MySQL adapter** | **54%** | 293/641 | 🟡 Moderate |
| **MySQL connection** | **81%** | 20/105 | ✅ Good |
| **MySQL renderer** | **83%** | 15/88 | ✅ Good |
| **MySQL health** | **17%** | 43/52 | 🔴 Low |
| **MySQL performance** | **16%** | 37/44 | 🔴 Low |

### Key Findings

**SQLite**: Essentially complete at 96% coverage (was incorrectly reported as 18.2%)
- adapter.py: 99% coverage (1 line missing)
- renderer.py: 90% coverage (7 lines missing)
- **Recommendation**: Mark as COMPLETE ✅

**MySQL**: Reasonable at 54% overall (was incorrectly reported as 19.5%)
- Core adapter: 54% (decent for database adapter)
- Main gaps: health.py (17%), performance.py (16%)
- Note: `pyproject.toml` excludes MySQL/SQLite with comment "Database adapters require external connections for meaningful testing"

### Coverage Report Issue

**Root Cause**: Quality report from zibeta-0207 used stale data. Test commits were made Feb 7 but not reflected in report.

**Resolution**: Ran fresh coverage analysis 2026-02-08, bypassing pyproject.toml exclusions.

### Revised Priority Assessment

**Priority Downgraded**: LOW → MEDIUM

**Rationale**:
- SQLite is done (96% coverage)
- MySQL at 54% is reasonable for database adapter requiring live connections
- Project explicitly excludes DB adapters from coverage (architectural decision)
- Main gaps are health/performance modules that need live DB

### Optional Action Plan

**If pursuing MySQL improvement** (~4 hours):
1. MySQL health.py tests (2 hours) - 17% → 60%+
2. MySQL performance.py tests (2 hours) - 16% → 60%+

**Alternative**: Accept 54% MySQL coverage as adequate architectural boundary, remove from critical priorities

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

## Priority 3: Phase 3 - Query Operator Standardization ✅ COMPLETE

**Status**: ✅ Complete (2026-02-08, Session: hosuki-0208)

**Completed** (Phase 3a - Query Infrastructure Unification):
- Unified query parser across 5 adapters
- -299 duplicate lines removed
- ast, stats, markdown, git, json adapters unified

**Completed** (Phase 3b - Operator Standardization):
- ✅ All 5 adapters support unified operator syntax
- ✅ Result control (sort/limit/offset) in all adapters
- ✅ Fixed markdown routing bug (query parsing)
- ✅ Added result control to git adapter

**Effort**: 3 hours actual vs 20 hours estimated
**Commits**: a36d6b5 (markdown), 3610488 (git)
**Impact**: All query-capable adapters now consistent

**Documentation**: ✅ COMPLETE (2026-02-08)
- Created QUERY_SYNTAX_GUIDE.md - Comprehensive operator reference
- Updated ROADMAP.md, CHANGELOG.md, ADAPTER_UX_CONSISTENCY
- Session: gentle-cyclone-0208

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

### Phase 4: Field Selection + Budget Awareness - ✅ **COMPLETE** (2026-02-08)

**Goal**: Token reduction for AI agents ✅
**Features**:
- ✅ `--fields=field1,field2` for specific field output (changed from --select to avoid conflict)
- ✅ `--max-items`, `--max-bytes`, `--max-depth`, `--max-snippet-chars` budget flags
- ✅ Truncation metadata in output contract
- ✅ Nested field support with dot notation
- ✅ Universal routing layer integration (works with all adapters)

**Delivered**:
- Field filtering utility (`reveal/display/formatting.py`)
- Budget constraint utilities (`reveal/utils/query.py`)
- Universal filter flags in parser
- Routing layer integration
- Comprehensive documentation (FIELD_SELECTION_GUIDE.md, 644 lines)
- Tested across SSL, AST, Stats, Git adapters

**Session**: luminous-twilight-0208 (~4 hours)
**Token Reduction**: 5-40x depending on adapter and field selection

### Phase 5: Element Discovery - ✅ **COMPLETE** (2026-02-08)

**Goal**: Auto-show available elements ✅

**Delivered**:
- ✅ Added `get_available_elements()` to ResourceAdapter base class
- ✅ Implemented in 4 fixed-element adapters (SSL, Domain, MySQL, Python)
- ✅ Text output shows "📍 Available elements" hints with descriptions
- ✅ JSON output includes `available_elements` array
- ✅ Dynamic adapters (10) use default empty list
- ✅ Comprehensive documentation (ELEMENT_DISCOVERY_GUIDE.md, 698 lines)
- ✅ Full testing across adapters (text + JSON output)

**Session**: scarlet-shade-0208 (~4 hours)

**Impact**: Users can now discover available elements without consulting documentation. AI agents can programmatically explore adapter capabilities via `available_elements` JSON field.

---

## Next Actions

### Immediate (This Week)

1. **Phase 3 Documentation** - ✅ **COMPLETE** (2026-02-08)
   - ✅ Update CURRENT_PRIORITIES with actual coverage
   - ✅ Update CHANGELOG.md with Phase 3 documentation completion
   - ✅ Update ROADMAP.md (mark Phase 3 complete with docs)
   - ✅ Create QUERY_SYNTAX_GUIDE.md (comprehensive operator reference)
   - ✅ Update ADAPTER_UX_CONSISTENCY checkboxes
   - Session: gentle-cyclone-0208

2. **Documentation Consolidation** (3 hours) - OPTIONAL
   - Audit complete (cooling-frost-0208)
   - Create navigation/index for internal-docs/
   - Review and archive stale docs

### Next Priority Options

**Option A: Phase 4 & 5 Implementation** (18 hours)
- Phase 4: Field selection + budget awareness (~12 hours)
- Phase 5: Element discovery (~6 hours)
- Builds on completed Phase 3

**Option B: MySQL Coverage Improvement** (4 hours)
- health.py tests (17% → 60%)
- performance.py tests (16% → 60%)
- Would raise MySQL from 54% → ~70%

**Option C: Documentation & User Experience**
- Complete QUERY_SYNTAX_GUIDE.md
- Review public docs for accuracy
- Update examples with Phase 3 query syntax

**Recommendation**: Option A (Phase 4/5) - Continue UX consistency momentum

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
