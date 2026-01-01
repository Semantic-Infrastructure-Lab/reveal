# Reveal Planning Documentation

**Last Updated:** 2025-12-31
**Current Release:** v0.27.1
**Next Release:** v0.28.0 (imports://)

Internal planning documents for future and in-progress features.

---

## Active Plans

### 🎯 imports:// Adapter (v0.28.0)

**Status:** Planning complete, ready for implementation
**Target:** v0.28.0 (Q1 2026)
**Priority:** HIGH
**Effort:** 30-40 hours (5 weeks)

Import graph analysis: unused imports, circular dependencies, layer violations.

**Primary Document:**
- **[IMPORTS_IMPLEMENTATION_PLAN.md](./IMPORTS_IMPLEMENTATION_PLAN.md)** - Complete implementation spec

**Features:**
- Unused import detection (I001 rule)
- Circular dependency detection (I002 rule)
- Layer violation detection (I003 rule)
- Multi-language support: Python, JavaScript, TypeScript, Go, Rust
- .reveal.yaml configuration

**Next Steps:** Begin Phase 1 (Foundation) - Core data structures and Python import extraction

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
