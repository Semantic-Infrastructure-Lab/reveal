# Reveal Planning Documentation

**Last Updated:** 2026-01-04
**Current Release:** v0.29.0
**Next Release:** v0.30.0 (Semantic Diff Adapter)

Internal planning documents for future and in-progress features.

---

## Active Plans

### 🚧 diff:// Adapter (v0.30.0)

**Status:** 🚧 In progress (90% complete)
**Target:** v0.30.0 (Jan 2026)
**Priority:** HIGH
**Effort:** 2-3 weeks

Semantic structural comparison for code review and impact assessment.

**Features:**
- File and directory comparison
- Git integration (commits, branches, working tree)
- Element-level diff for deep dives
- JSON output for CI/CD
- AI agent optimized usage guide

**Breaking Change:** Python 3.10+ minimum (was 3.8+)

**Documents:**
- `AI_DIFF_USAGE.md` - AI agent integration guide
- See ROADMAP.md for feature details

---

### 🎯 Breadcrumb Navigation Enhancements (v0.30.1-v0.32.0)

**Status:** Design complete, implementation pending
**Target:** v0.30.1 (Feb 2026), v0.31.0 (Q2 2026), v0.32.0 (Q3 2026)
**Priority:** HIGH (Phase 1), MEDIUM (Phase 2-3)
**Effort:** 1-2 hours (Phase 1), 3-4 weeks (Phase 2), 2-3 weeks (Phase 3)

Enhanced breadcrumb system to guide users through Reveal's full feature set.

**Primary Document:**
- **[BREADCRUMB_IMPROVEMENTS_2026.md](./BREADCRUMB_IMPROVEMENTS_2026.md)** - Complete design with 5-phase implementation plan

**Roadmap:**
- **Phase 1 (v0.30.1):** Critical fixes (1-2 hours)
  - Fix "typed" context bug (broken functionality)
  - Add HTML analyzer mapping
  - Test coverage for all contexts
- **Phase 2 (v0.31.0):** Adapter awareness (3-4 weeks)
  - Large file detection → AST suggestions
  - Post-check quality guidance
  - Import analysis breadcrumbs
  - diff:// workflow hints
  - Token savings: 50-200 per session
- **Phase 3 (v0.32.0):** Workflow guidance (2-3 weeks)
  - Pre-commit workflow detection
  - Code review workflow hints
  - Refactoring workflow support
  - Help system integration
- **Phase 4-5 (Future):** Context awareness and advanced features

**Key Principles:**
- Agent-first design (token efficiency)
- Progressive disclosure (guide to advanced features)
- Workflow-oriented (complete tasks, not just commands)
- Opportunistic (leverage existing infrastructure)

**Next Steps:**
- Phase 1: Fix critical bug in v0.30.1 (1-2 hours)
- Phase 2: Design adapter-specific breadcrumbs for v0.31.0

---

### 🎯 Knowledge Graph Features (v0.29.0-v0.33.0)

**Status:** Phase 1 complete ✅, remaining phases planned
**Target:** v0.29.0 ✅ (Schema validation), v0.32.0 (Link following), v0.33.0 (Queries + checks)
**Priority:** MEDIUM
**Effort:** 10-12 weeks over 4 releases

Knowledge graph construction: schema validation, link following, metadata queries, quality checks.

**Primary Documents:**
- **[KNOWLEDGE_GRAPH_PROPOSAL.md](./KNOWLEDGE_GRAPH_PROPOSAL.md)** - Executive decision document (Option A approved)
- **[KNOWLEDGE_GRAPH_ARCHITECTURE.md](./KNOWLEDGE_GRAPH_ARCHITECTURE.md)** - Technical architecture & implementation specs
- **[KNOWLEDGE_GRAPH_GUIDE.md](./KNOWLEDGE_GRAPH_GUIDE.md)** - User-facing guide (ships as `reveal help://knowledge-graph`)

**Roadmap (Updated):**
- ✅ v0.29.0 (Jan 2026): Schema validation framework - SHIPPED
- v0.32.0 (Q3 2026): Link following with --related flag (2-3 weeks)
- v0.33.0 (Q3 2026): markdown:// adapter + quality checks (5-6 weeks)
- v0.34.0 (Q4 2026): Complete documentation suite (1-2 weeks)

**Key Principles:**
- Generic features (not Beth-specific) - works with Hugo, Obsidian, Jekyll, custom schemas
- Stateless architecture (max depth 2 for link following)
- Ships with reference schemas: beth.yaml, hugo.yaml, jekyll.yaml, mkdocs.yaml, obsidian.yaml

**Completed:**
- ✅ v0.29.0: Schema validation with 5 built-in schemas, F001-F005 rules, comprehensive guide

---

### 🔧 AST Migration & Analyzer Quality (v0.29.0+)

**Status:** Phase 1-4 complete, Phase 5 planned
**Priority:** MEDIUM (quality/maintainability, fits between major features)
**Effort:** Opportunistic (1 day per phase)

Progressive migration from regex-based analyzers to AST parsing for better accuracy and maintainability.

**Primary Document:**
- **[AST_MIGRATION_ROADMAP.md](./AST_MIGRATION_ROADMAP.md)** - Complete roadmap and pattern guide

**Completed (Jan 2026):**
- ✅ Phase 1-4: Markdown AST migration with column tracking (3 sessions)
- ✅ Pattern established: Optional dependencies + fallback mechanisms
- ✅ Research: GDScript (defer), nginx/crossplane (viable)

**Planned:**
- 🎯 Phase 5: Nginx crossplane enhancement (v0.29.0-v0.31.0, optional)
  - Optional dependency pattern: `pip install reveal[nginx]`
  - Complete directive extraction (upstream servers, SSL config, etc.)
  - Fallback to current regex parser
  - Effort: 1 day
- 📋 Phase 6+: Monitor GDScript, evaluate bash/Dockerfile (quarterly review)

**Integration with Knowledge Graph:**
- AST migrations are opportunistic quality improvements
- Implemented during foundation work between major features
- Phase 5 nginx enhancement could ship alongside v0.29.0-v0.31.0 if time permits

**Completion Reports:**
- **[../PHASES_3_4_AST_MIGRATION.md](../PHASES_3_4_AST_MIGRATION.md)** - Phase 3/4 session work
- **[../NGINX_SUPPORT_DOCUMENTATION.md](../NGINX_SUPPORT_DOCUMENTATION.md)** - Crossplane implementation spec

---

## Shipped Plans

### ✅ imports:// Adapter (v0.28.0)

**Status:** ✅ SHIPPED (Jan 2026)
**Features:** Import graph analysis, unused imports (I001), circular dependencies (I002), layer violations (I003)
**Document:** [IMPORTS_IMPLEMENTATION_PLAN.md](./IMPORTS_IMPLEMENTATION_PLAN.md)

---

## Reference Documents

### Production Testing & Validation

**[../research/POPULAR_REPOS_TESTING.md](../research/POPULAR_REPOS_TESTING.md)** - Real-world validation on popular open-source projects
- ✅ Tested on Requests, Flask, FastAPI, Django (Jan 2026, v0.29.0)
- Performance: Sub-second analysis, up to 2,708x token savings
- Quality: Found real issues in production code (circular deps, god functions)
- User guide: `../../docs/PRODUCTION_TESTING_GUIDE.md`

### Foundation & Quality

**[FOUNDATION_QUALITY_PLAN.md](./FOUNDATION_QUALITY_PLAN.md)** - Historical context for v0.27.0/v0.27.1 foundation work
- ✅ Mission accomplished (988 tests, 74% coverage)
- Provides context for imports:// implementation

### Future Ideas (Exploration)

**[INTENT_LENSES_DESIGN.md](./INTENT_LENSES_DESIGN.md)** - Community-curated relevance system (Post-v0.28.0)
- **Status:** Design/exploration phase
- **Concept:** Typed overlays that prioritize, filter, and emphasize Reveal output for specific intents
- **Inspiration:** tldr-style community curation, but as typed metadata (not prose)
- **Target:** v0.29.0+ (pending imports:// completion)
- **SIL Aligned:** Provenance-safe, grounded, token-efficient

**[TYPED_FEATURE_IDEAS.md](./TYPED_FEATURE_IDEAS.md)** - Additional type-first architecture enhancements
- Decorator-aware queries, API surface detection, semantic diff
- Some ideas implemented in v0.23.0-v0.27.1

### Historical Plans (Reference Only)

These documents reflect work from v0.20.0-v0.26.0 timeframe:

**Duplicate Detection:**
- [DUPLICATE_DETECTION_DESIGN.md](./DUPLICATE_DETECTION_DESIGN.md) - System architecture
- [DUPLICATE_DETECTION_GUIDE.md](./DUPLICATE_DETECTION_GUIDE.md) - User guide
- [DUPLICATE_DETECTION_OPTIMIZATION.md](./DUPLICATE_DETECTION_OPTIMIZATION.md) - Mathematical framework
- [DUPLICATE_DETECTION_OVERVIEW.md](./DUPLICATE_DETECTION_OVERVIEW.md) - Visual overview

**Code Quality:**
- [CODE_QUALITY_ARCHITECTURE.md](./CODE_QUALITY_ARCHITECTURE.md) - Pattern discovery
- [CODE_QUALITY_REFACTORING.md](./CODE_QUALITY_REFACTORING.md) - Refactoring plan
- ✅ Completed in v0.27.1

**Type System:**
- [CONTAINMENT_MODEL_DESIGN.md](./CONTAINMENT_MODEL_DESIGN.md) - Type-first architecture
- ✅ Completed in v0.23.0

**Adapters:**
- [NGINX_ADAPTER_ENHANCEMENTS.md](./NGINX_ADAPTER_ENHANCEMENTS.md) - Nginx enhancements
- [LINK_VALIDATION_SPEC.md](./LINK_VALIDATION_SPEC.md) - Link validation (L-series rules)
- ✅ Link validation completed in v0.26.0

---

## Archive

For historical planning documents, see:
- **`../archive/PENDING_WORK_ARCHIVED_2025-12-31.md`** - Pre-v0.27.0 pending work index
- **`../archive/`** - Version-specific checklists, specs, and validation reports

See **`../../ROADMAP.md`** for the complete release roadmap and feature timeline.

---

## Document Organization

**Planning Workflow:**
1. **Active development** → Documents in this directory
2. **Shipped features** → Update ROADMAP.md, move planning docs to archive/
3. **Historical reference** → Keep in archive/ for future context

**Document Lifecycle:**
- Planning docs start here during feature design
- Move to archive/ after feature ships or is abandoned
- ROADMAP.md is the single source of truth for what's shipped vs planned

---

**Questions?** See `../../CONTRIBUTING.md` for how to propose new features.
