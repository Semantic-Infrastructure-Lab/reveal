# Reveal Planning Documentation

Internal planning documents for future features.

---

## Active Plans

### 🔍 Duplicate Detection (D001, D002 Rules)

**Status:** Foundation complete, needs feature improvement
**Target:** v0.20.0+
**Session:** infernal-throne-1212 (2025-12-12)
**Priority:** Medium

Universal duplicate detection system across all file types.

**Documents:**
- **[PENDING_WORK.md](./PENDING_WORK.md)** - 📌 Master index of ALL pending work
- [DUPLICATE_DETECTION_DESIGN.md](./DUPLICATE_DETECTION_DESIGN.md) - System architecture (20KB)
- [DUPLICATE_DETECTION_GUIDE.md](./DUPLICATE_DETECTION_GUIDE.md) - User guide (15KB)
- [DUPLICATE_DETECTION_OPTIMIZATION.md](./DUPLICATE_DETECTION_OPTIMIZATION.md) - Mathematical framework (14KB)
- [DUPLICATE_DETECTION_OVERVIEW.md](./DUPLICATE_DETECTION_OVERVIEW.md) - Visual overview (19KB)

**Tools:**
- `scripts/analyze_duplicate_detection.py` - Statistical analysis toolkit

```bash
reveal app.py --check --select D       # Detect duplicates
reveal app.py --check --select D --show-stats  # With statistics
```

**Next Steps:** Improve D002 feature discrimination (mean similarity 0.935→0.5)

---

### 🎯 Code Quality Refactoring

**Status:** Phase 1 complete (246→40 lines), Phases 2-3 designed
**Target:** v0.20.0+
**Session:** wise-goddess-1212 (2025-12-12)
**Priority:** Medium

Systematic cleanup of large functions (target: 75/100 quality score).

**Documents:**
- **[PENDING_WORK.md](./PENDING_WORK.md)** - 📌 Master index of ALL pending work
- [CODE_QUALITY_ARCHITECTURE.md](./CODE_QUALITY_ARCHITECTURE.md) - Pattern discovery (12KB)
- [CODE_QUALITY_REFACTORING.md](./CODE_QUALITY_REFACTORING.md) - Phase-by-phase plan (9.6KB)
- `../../docs/REVEAL_ENGINEERING_REVIEW_2025-12-12.md` - Engineering audit (16KB)

**Git Branch:** `refactor/code-quality-wise-goddess`

**Next Steps:** Phase 2 (rendering dispatchers, 4 hours)

---

### MySQL Adapter

**Status:** Planned (spec not yet written)
**Target:** v0.23.0+

Database exploration with progressive disclosure.

```bash
reveal mysql://prod/users            # Table structure
reveal mysql://prod/users id         # Column details
```

### Nginx Adapter Enhancements

**Status:** Design complete
**Target:** v0.19.0+

Config validation and conflict detection.

**Document:** [NGINX_ADAPTER_ENHANCEMENTS.md](./NGINX_ADAPTER_ENHANCEMENTS.md)

```bash
reveal /etc/nginx/conf.d/upstreams.conf --check
```

### 🏗️ Type-First Architecture

**Status:** Design complete
**Target:** v0.23.0+
**Session:** hidden-grove-1213 (2025-12-13)
**Priority:** Medium

Elevate `types.py` to be first-class: drive extension→adapter mapping, containment rules, and Pythonic navigation.

**Document:** [CONTAINMENT_MODEL_DESIGN.md](./CONTAINMENT_MODEL_DESIGN.md)

**Key insight**: TypeRegistry becomes source of truth. Enables:
- Auto-upgrade `.py` → `py://` for rich analysis
- Computed containment from EntityDef rules + line ranges
- Pythonic navigation: `structure / 'MyClass' / 'method'`
- `walk()`, `find()`, `.parent`, `.children` on elements

```bash
reveal app.py                     # PythonType → structure adapter
reveal py://app.py                # PythonType → deep adapter
reveal app.py --rich              # Explicit upgrade

# Python API
structure = reveal('app.py')
for method in structure / 'MyClass':
    print(method.path, method.depth)
```

**Phases:**
1. TypeRegistry, RevealType, EntityDef classes
2. TypedElement with navigation (`__contains__`, `walk()`)
3. TypedStructure container (`__truediv__`, `find()`)
4. Wire up PythonType + TreeSitter
5. Extension → scheme magic (`--rich` flag)
6. Additional types (Markdown, JSON, YAML)
7. Rules integration

---

## Shipped

### Architecture Refactoring (v0.22.0)

**Status:** Complete
**Sessions:** bright-panther-1213, fidajosa-1213, wireju-1213
**Branch:** `refactor/architecture-v1`

Systematic modularization of core reveal codebase.

**Results:**
- `main.py`: 2,446 → 287 lines (**-88%**)
- `base.py`: 520 → 302 lines (**-42%**)
- `python.py`: 1,140 lines → 7 focused modules

**New Packages:**
- `reveal/cli/` - Argument parsing, routing, handlers (4 files)
- `reveal/rendering/` - Output formatting (4 files)
- `reveal/display/` - Terminal display (5 files)
- `reveal/adapters/python/` - Python adapter modules (7 files)
- `reveal/registry.py` - Analyzer registration system

**Phases:**
1. Extract rendering system ✅
2. Extract display system ✅
3. Extract CLI system ✅
4. Split Python adapter ✅
5. Extract registry ✅
6. Consolidation ✅

**Git Tags:** phase-1 through phase-6

---

### Python Adapter (v0.17.0-v0.18.0)

**Status:** Shipped

**Documents:**
- [PYTHON_ADAPTER_SPEC.md](./PYTHON_ADAPTER_SPEC.md) - Specification
- [PYTHON_ADAPTER_ROADMAP.md](./PYTHON_ADAPTER_ROADMAP.md) - Implementation plan

```bash
reveal python://                     # Environment overview
reveal python://debug/bytecode       # Stale .pyc detection
reveal python://packages             # Package listing
```

---

## Archive

Historical documents moved to `../archive/`:
- `IMPROVEMENT_PLAN.md` - Codebase analysis (2025-11-30)
- `REVEAL_ENHANCEMENT_PROPOSALS.md` - Feature proposals (2025-12-09)
- Version-specific checklists and validation reports

---

## Document Template

```markdown
# Feature Name

**Status:** Planning | In Progress | Complete
**Version:** vX.Y.Z
**Priority:** High | Medium | Low

## Overview
Brief description.

## Design
How it works.

## Implementation
Key decisions.
```

---

**Last Updated:** 2025-12-13 (wireju-1213 - architecture refactoring complete)
