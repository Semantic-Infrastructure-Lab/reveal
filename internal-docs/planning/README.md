# Reveal Planning Documentation

**Last Updated:** 2026-01-02
**Current Release:** v0.28.0
**Next Release:** v0.29.0 (Schema Validation)

Internal planning documents for future and in-progress features.

---

## Active Plans

### 🎯 Knowledge Graph Features (v0.29.0-v0.32.0)

**Status:** Planning complete, roadmap integrated
**Target:** v0.29.0 (Schema validation), v0.30.0 (Link following), v0.31.0 (Queries + checks), v0.32.0 (Docs)
**Priority:** HIGH
**Effort:** 10-12 weeks over 4 releases

Knowledge graph construction: schema validation, link following, metadata queries, quality checks.

**Primary Documents:**
- **[KNOWLEDGE_GRAPH_PROPOSAL.md](./KNOWLEDGE_GRAPH_PROPOSAL.md)** - Executive decision document (Option A approved)
- **[KNOWLEDGE_GRAPH_ARCHITECTURE.md](./KNOWLEDGE_GRAPH_ARCHITECTURE.md)** - Technical architecture & implementation specs
- **[KNOWLEDGE_GRAPH_GUIDE.md](./KNOWLEDGE_GRAPH_GUIDE.md)** - User-facing guide (ships as `reveal help://knowledge-graph`)

**Roadmap (Hybrid Integration - Option D):**
- v0.29.0 (Q2 2026): Schema validation framework (2-3 weeks)
- v0.30.0 (Q2 2026): Link following with --related flag (2-3 weeks)
- v0.31.0 (Q3 2026): markdown:// adapter + quality checks (5-6 weeks)
- v0.32.0 (Q3 2026): Complete documentation suite (1-2 weeks)

**Key Principles:**
- Generic features (not Beth-specific) - works with Hugo, Obsidian, Jekyll, custom schemas
- Stateless architecture (max depth 2 for link following)
- Ships with reference schemas: beth.yaml, hugo.yaml, obsidian.yaml

**Next Steps:**
- Phase 1 (v0.29.0): Design schema validation framework, define YAML schema format
- Create built-in schemas (beth, hugo, obsidian)
- Implement validation rules engine (F001-F005)

---

## Shipped Plans

### ✅ imports:// Adapter (v0.28.0)

**Status:** ✅ SHIPPED (Jan 2026)
**Features:** Import graph analysis, unused imports (I001), circular dependencies (I002), layer violations (I003)
**Document:** [IMPORTS_IMPLEMENTATION_PLAN.md](./IMPORTS_IMPLEMENTATION_PLAN.md)

---

## Reference Documents

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
