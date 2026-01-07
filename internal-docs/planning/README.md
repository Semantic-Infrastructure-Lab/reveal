# Reveal Planning Documentation

**Last Updated:** 2026-01-06
**Current Release:** v0.31.0
**Next Release:** v0.32.0 (Link Following with --related)

Internal planning documents for future and in-progress features.

---

## Active Plans

### 🎯 Knowledge Graph Features (v0.32.0-v0.34.0)

**Status:** Schema validation ✅ SHIPPED, link following planned
**Target:** v0.32.0 (Link following), v0.33.0 (markdown:// adapter), v0.34.0 (Documentation)
**Priority:** HIGH
**Effort:** 8-10 weeks remaining

Knowledge graph construction: link following, metadata queries, quality checks.

**Primary Documents:**
- **[KNOWLEDGE_GRAPH_PROPOSAL.md](./KNOWLEDGE_GRAPH_PROPOSAL.md)** - Executive decision document (Option A approved)
- **[KNOWLEDGE_GRAPH_ARCHITECTURE.md](./KNOWLEDGE_GRAPH_ARCHITECTURE.md)** - Technical architecture & implementation specs
- **[KNOWLEDGE_GRAPH_GUIDE.md](./KNOWLEDGE_GRAPH_GUIDE.md)** - User-facing guide

**Roadmap:**
- ✅ v0.29.0: Schema validation framework - SHIPPED
- 🎯 v0.32.0 (Q2 2026): `--related` flag for link following (2-3 weeks)
- 🎯 v0.33.0 (Q3 2026): `markdown://` adapter + quality checks (5-6 weeks)
- 🎯 v0.34.0 (Q4 2026): Complete documentation suite (1-2 weeks)

**Key Principles:**
- Generic features (not Beth-specific) - works with Hugo, Obsidian, Jekyll, custom schemas
- Stateless architecture (max depth 2 for link following)
- Ships with reference schemas: beth.yaml, hugo.yaml, jekyll.yaml, mkdocs.yaml, obsidian.yaml

---

### 🔧 AST Migration - Nginx Phase (v0.32.0, optional)

**Status:** Pattern established ✅, nginx enhancement planned
**Priority:** LOW (quality/maintainability)
**Effort:** 1 day (opportunistic)

**Primary Document:** [AST_MIGRATION_ROADMAP.md](./AST_MIGRATION_ROADMAP.md)

**Planned:**
- Nginx crossplane enhancement: `pip install reveal[nginx]`
- Complete directive extraction (upstream servers, SSL config)
- Fallback to current regex parser

---

## Shipped Plans

### ✅ diff:// Adapter (v0.30.0)

**Status:** ✅ SHIPPED (Jan 2026)
**Features:** File/directory comparison, Git integration (commits, branches), element-level diff, JSON output
**Document:** [../../docs/DIFF_ADAPTER_GUIDE.md](../../docs/DIFF_ADAPTER_GUIDE.md)

### ✅ Smart Breadcrumbs (v0.30.0-v0.31.0)

**Status:** ✅ SHIPPED (Jan 2026)
**Features:**
- v0.30.0: Large file detection, import analysis hints, file-type suggestions
- v0.31.0: Post-check quality guidance, diff:// workflow hints, -q/--quiet mode, pre-commit/code review workflows
**Document:** [BREADCRUMB_IMPROVEMENTS_2026.md](./BREADCRUMB_IMPROVEMENTS_2026.md) (phases 1-3 complete)

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

## Archive

Historical planning documents for completed features have been moved to `../archive/`:

**Completed Feature Docs:**
- Duplicate detection (4 docs) - v0.20.0-v0.26.0
- Code quality (2 docs) - v0.27.1
- Type system containment model - v0.23.0
- Nginx/link validation adapters (2 docs) - v0.26.0
- Documentation audits (3 docs) - Dec 2025-Jan 2026

**Reference:**
- **`../archive/PENDING_WORK_ARCHIVED_2025-12-31.md`** - Pre-v0.27.0 pending work index
- **`../archive/`** - Full archive directory

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
