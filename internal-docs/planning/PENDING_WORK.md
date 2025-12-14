# Reveal - Pending Work Index

**Last Updated:** 2025-12-14
**Sessions:** infernal-throne-1212, wise-goddess-1212, cyber-phoenix-1212, emerald-hue-1214

---

## Recent Completions (v0.23.0)

**Released:** 2025-12-14
**Session:** emerald-hue-1214

### ✅ Type-First Architecture (COMPLETE)

The Type-First Architecture is now fully implemented and released in v0.23.0:

- ✅ `--typed` flag for hierarchical code structure with containment
- ✅ Decorator extraction (`@property`, `@staticmethod`, `@classmethod`, `@dataclass`)
- ✅ `TypedStructure` and `TypedElement` classes for programmatic navigation
- ✅ `PythonElement` with decorator-aware properties
- ✅ AST decorator query (`ast://.?decorator=property`)
- ✅ Category filtering (`--filter=property`)
- ✅ Decorator statistics (`--decorator-stats`)
- ✅ New bug rules: B002, B003, B004 (decorator-related)
- ✅ 401 tests passing

**Design docs:** `internal-docs/planning/CONTAINMENT_MODEL_DESIGN.md`

### ✅ Architecture Refactoring (COMPLETE)

- ✅ main.py reduced 64% (2,446 → 804 lines)
- ✅ 7-phase systematic extraction (CLI, display, rendering, adapters)
- ✅ Clean separation of concerns

---

## Overview

This document indexes all pending work for Reveal, organized by project track. Each track has comprehensive documentation in this directory or in `docs/`.

**Quick Navigation:**
- [Track 1: Duplicate Detection](#track-1-duplicate-detection-d001-d002-rules) - Universal duplicate detection system
- [Track 2: Code Quality Refactoring](#track-2-code-quality-refactoring) - Systematic codebase cleanup
- [Track 3: Testing & Infrastructure](#track-3-testing--infrastructure) - Coverage and reliability
- [Quick Start Commands](#quick-start-commands)

---

## Track 1: Duplicate Detection (D001, D002 Rules)

**Status:** ✅ Foundation complete, needs feature improvement
**Session:** infernal-throne-1212
**Priority:** Medium
**Effort:** 2-3 hours to improve D002

### What's Done ✅

- ✅ D001: Exact duplicate detection (hash-based, ~90ms/file)
- ✅ D002: Structural similarity detection (vector-based)
- ✅ Universal framework (works for Python, extensible to all languages)
- ✅ Statistical analysis toolkit
- ✅ Self-reflection system (quality metrics, suggestions)
- ✅ Configuration system (YAML + CLI overrides)

### What's Pending

**Immediate (Improve D002 discrimination)**:
- [ ] Add AST structural features (node sequences, depth histograms)
- [ ] Implement TF-IDF weighting for token features
- [ ] Create ground truth test set (100+ labeled duplicate pairs)
- [ ] Compute precision/recall curves
- [ ] Find optimal threshold via cross-validation

**Current Issue:** Mean similarity too high (0.935 instead of 0.5-0.6)
**Root Cause:** Token-based features dominated by common patterns (if, for, return)
**Solution:** AST structural features or TF-IDF weighting

**Short-term (Extend coverage)**:
- [ ] Rust extractor (functions, impls, traits)
- [ ] Markdown extractor (sections by headers)
- [ ] JavaScript/TypeScript extractor
- [ ] Nginx config extractor (server blocks)
- [ ] JSON extractor (top-level objects)

**Medium-term (Enhanced features)**:
- [ ] Interactive calibration mode (`--calibrate`)
- [ ] Explain mode (`--explain` shows why each detection)
- [ ] Cross-file duplicate detection (batch mode)
- [ ] Web UI for threshold tuning

**Long-term (Advanced)**:
- [ ] D003: Semantic duplicates with CodeBERT embeddings
- [ ] Cross-language duplicate detection (Python ↔ Rust)
- [ ] Automatic feature weight learning

### Documentation

**Comprehensive Guides** (moved to `internal-docs/planning/`):
- `DUPLICATE_DETECTION_DESIGN.md` (20KB) - System architecture
- `DUPLICATE_DETECTION_GUIDE.md` (15KB) - User guide
- `DUPLICATE_DETECTION_OPTIMIZATION.md` (14KB) - Mathematical framework
- `DUPLICATE_DETECTION_OVERVIEW.md` (19KB) - Visual overview

**Session Context:**
- `/home/scottsen/src/tia/sessions/infernal-throne-1212/README_2025-12-12_16-09.md`

### Quick Start

```bash
# Test current implementation
cd /home/scottsen/src/projects/reveal/external-git
reveal reveal/main.py --check --select D

# Run statistical analysis
python /tmp/analyze_duplicate_detection.py

# See all duplicate rules
reveal --rules | grep D0

# Benchmark performance
time reveal reveal/ --check --select D --show-stats
```

---

## Track 2: Code Quality Refactoring

**Status:** ✅ COMPLETE - All phases shipped in v0.23.0
**Session:** wise-goddess-1212, emerald-hue-1214
**Priority:** ~~Medium~~ Done
**Effort:** ~~8 hours for Phases 2-3~~ Shipped

### What's Done ✅

**Phase 1: CLI Entry Point** ✅
- Refactored `_main_impl` (246→40 lines, depth 5→2)
- Extracted 9 focused helper functions
- All 363 tests passing
- Git branch: `refactor/code-quality-wise-goddess`
- Commit: `b50357e`

**Analysis Complete** ✅
- Comprehensive engineering review (22/100 quality score)
- Architecture pattern discovery (3 distinct patterns)
- Refactoring roadmap for 75/100 target

### What's Pending

**Phase 2: Rendering Dispatchers** (4 hours estimated)
- [ ] Refactor `render_help` (212→40 lines)
- [ ] Refactor `render_python_element` (173→40 lines)
- [ ] Extract rendering mode functions
- [ ] Test each extraction
- **Impact:** +300 lines saved, quality 30→50/100

**Phase 3: Sequential Analyzers** (4 hours estimated)
- [ ] Refactor `_get_module_analysis` (118→30 lines)
- [ ] Refactor `_run_doctor` (226→40 lines)
- [ ] Extract analysis sections
- [ ] Test each extraction
- **Impact:** +270 lines saved, quality 50→75/100

**Testing & Infrastructure**
- [ ] Increase test coverage (current: <20%, target: >50%)
- [ ] Fix `types.py` naming conflict (rename to `models.py`)
- [ ] Add M001 rule to Reveal (dogfooding sample)

### Architecture Patterns Identified

**Pattern 1: CLI Dispatchers** (✅ REFACTORED)
- Argument parsing + dispatch logic combined
- Solution: Extract parser, validators, handlers

**Pattern 2: Rendering Dispatchers** (PENDING)
- Multiple rendering modes in one function (6-7 branches)
- Solution: Extract each mode into focused function

**Pattern 3: Sequential Analyzers** (PENDING)
- Sequential data gathering in one function
- Solution: Extract each analysis section

### Quality Metrics

| Metric | Before | Phase 1 | Target (Phase 3) |
|--------|--------|---------|------------------|
| Quality Score | 22/100 | ~30/100 | ≥75/100 |
| Huge Functions (>100 lines) | 6 | 5 | 0 |
| Lines Saved | 0 | 206 | ~776 |
| Max Complexity Depth | 5 | 2 (in refactored) | ≤3 everywhere |

### Documentation

**Comprehensive Guides** (in session directory, to be moved):
- `REVEAL_ENGINEERING_REVIEW.md` (16KB) - Engineering assessment
- `ARCHITECTURE_ANALYSIS.md` (12KB) - Pattern discovery
- `REFACTORING_PLAN.md` (9.6KB) - Phase-by-phase plan

**Session Context:**
- `/home/scottsen/src/tia/sessions/wise-goddess-1212/README_2025-12-12_16-18.md`

### Quick Start

```bash
# Check current quality score
cd /home/scottsen/src/tia
tia quality scan /home/scottsen/src/projects/reveal/external-git --format=brief

# Switch to refactoring branch
cd /home/scottsen/src/projects/reveal/external-git
git checkout refactor/code-quality-wise-goddess

# View Phase 1 changes
git show b50357e

# Continue with Phase 2 (render_help)
reveal reveal/formatting.py --outline
reveal reveal/formatting.py render_help
# ... refactor based on REFACTORING_PLAN.md

# Run tests after each change
pytest tests/ -v
```

---

## Track 3: Testing & Infrastructure

**Status:** 🔴 Needs Work
**Priority:** High (blocks large refactorings)
**Effort:** 12-20 hours

### What's Pending

**Test Coverage Improvements**
- [ ] Add tests for rules engine (priority)
- [ ] Add tests for AST query system
- [ ] Add tests for URI adapters (python://, ast://, json://)
- [ ] Add tests for duplicate detection (D001, D002)
- [ ] Target: 50%+ coverage (current: <20%)

**Naming & Organization**
- [ ] Fix `types.py` naming conflict (blocks development inside reveal/)
  - Rename to `models.py` or `reveal_types.py`
  - Update all imports
- [ ] Organize internal docs (this document is a start!)

**Quality Tooling Integration**
- [ ] Add M001 rule to Reveal (maintainability scoring)
- [ ] Set up quality gates in CI/CD
- [ ] Dogfood TIA quality tools regularly

### Quick Start

```bash
# Run existing tests
cd /home/scottsen/src/projects/reveal/external-git
pytest tests/ -v --cov=reveal

# Check coverage report
pytest tests/ --cov=reveal --cov-report=html
# Open htmlcov/index.html

# Fix types.py conflict
# 1. Rename reveal/types.py to reveal/models.py
# 2. Update all imports
# 3. Test with: pytest tests/ -v
```

---

## Decision Points

### For Scott to Decide

**1. Which track to pursue next?**
- **Option A:** Track 1 (Improve D002 duplicate detection)
  - Effort: 2-3 hours
  - Impact: Better feature discrimination, validated statistical framework
  - Status: Foundation solid, needs tuning

- **Option B:** Track 2 (Continue quality refactoring, Phases 2-3)
  - Effort: 8 hours
  - Impact: 75/100 quality score, -776 lines, clean architecture
  - Status: Phase 1 proven successful, clear roadmap

- **Option C:** Track 3 (Testing infrastructure first)
  - Effort: 12-20 hours
  - Impact: Safe foundation for other work
  - Status: Blocks large refactorings, but Track 2 Phase 1 succeeded without it

- **Option D:** Ship what we have, move to other priorities
  - Merge Phase 1 refactoring
  - Document D001/D002 as experimental
  - Defer improvements to future sessions

**2. Documentation organization**
- Where should comprehensive guides live?
  - `internal-docs/planning/` - Planning docs (specs, roadmaps)
  - `docs/` - Audits, investigations, reference material
  - Keep in session directories (current)

**3. Release strategy**
- Ship Track 1 (duplicate detection) in next release?
- Merge Track 2 Phase 1 before or after other phases?
- What version should these target? (v0.20.0? v0.21.0?)

---

## Quick Start Commands

### Check Current Status

```bash
# Quality score
tia quality scan /home/scottsen/src/projects/reveal/external-git --format=brief

# Git branches
cd /home/scottsen/src/projects/reveal/external-git
git branch -a

# Test suite
pytest tests/ -v

# Duplicate detection
reveal reveal/ --check --select D
```

### Session Context

```bash
# View previous session summaries
cat /home/scottsen/src/tia/sessions/infernal-throne-1212/README_2025-12-12_16-09.md
cat /home/scottsen/src/tia/sessions/wise-goddess-1212/README_2025-12-12_16-18.md

# Load comprehensive guides (still in /tmp/ and session dirs)
ls -lh /tmp/REVEAL*.md /tmp/DUPLICATE*.md /tmp/UNIVERSAL*.md
ls -lh ~/src/tia/sessions/wise-goddess-1212/*.md
```

### Work Continuation

```bash
# Continue Track 1 (Duplicate Detection)
cd /home/scottsen/src/projects/reveal/external-git
python /tmp/analyze_duplicate_detection.py  # See current stats
# Then: Implement AST features or TF-IDF weighting in reveal/rules/duplicates/D002.py

# Continue Track 2 (Quality Refactoring)
cd /home/scottsen/src/projects/reveal/external-git
git checkout refactor/code-quality-wise-goddess
reveal reveal/formatting.py render_help  # Next target
# Follow: ~/src/tia/sessions/wise-goddess-1212/REFACTORING_PLAN.md

# Start Track 3 (Testing)
cd /home/scottsen/src/projects/reveal/external-git
pytest tests/ --cov=reveal --cov-report=term-missing
# Identify gaps, write tests
```

---

## Related Documentation

### In This Repository

- `ROADMAP.md` - Overall Reveal roadmap
- `CONTRIBUTING.md` - Contribution guidelines
- `docs/REVEAL_SELF_AUDIT_2025-12-11.md` - Previous audit
- `internal-docs/planning/README.md` - Planning index

### Session Artifacts (To Be Organized)

**Duplicate Detection:**
- `internal-docs/planning/DUPLICATE_DETECTION_DESIGN.md` (20KB)
- `internal-docs/planning/DUPLICATE_DETECTION_GUIDE.md` (15KB)
- `internal-docs/planning/DUPLICATE_DETECTION_OPTIMIZATION.md` (14KB)
- `internal-docs/planning/DUPLICATE_DETECTION_OVERVIEW.md` (19KB)
- `scripts/analyze_duplicate_detection.py` (analysis tool)

**Quality Refactoring:**
- `~/src/tia/sessions/wise-goddess-1212/REVEAL_ENGINEERING_REVIEW.md` (16KB)
- `~/src/tia/sessions/wise-goddess-1212/ARCHITECTURE_ANALYSIS.md` (12KB)
- `~/src/tia/sessions/wise-goddess-1212/REFACTORING_PLAN.md` (9.6KB)

### TIA Project Context

```bash
# Explore Reveal project in TIA
tia project show reveal
tia beth explore "reveal duplicate detection"
tia beth explore "reveal code quality"

# Session continuity
tia session context infernal-throne-1212
tia session context wise-goddess-1212
```

---

## Next Session Quick Start

When resuming work on Reveal:

1. **Boot TIA:** `boot.`
2. **Read this file:** You're here! ✅
3. **Choose a track:** See [Decision Points](#decision-points)
4. **Check status:** Run commands in [Quick Start Commands](#quick-start-commands)
5. **Load context:** Review session READMEs for detailed history
6. **Continue work:** Follow track-specific quick start guides

---

**This document is the single source of truth for Reveal pending work.**

**Created:** 2025-12-12 (cyber-phoenix-1212)
**Tracks:** 3 active (Duplicate Detection, Quality Refactoring, Testing)
**Total Pending Effort:** ~22-31 hours across all tracks
**Documentation:** 7 comprehensive guides (68KB total)
