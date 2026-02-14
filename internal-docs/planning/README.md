# Planning Documentation

**Last Updated**: 2026-02-14

This directory contains active planning documents for the Reveal project. For completed/historical planning docs, see [../archived/planning/](../archived/planning/).

---

## Quick Start

**Looking for current priorities?** → [CURRENT_PRIORITIES_2026-02.md](CURRENT_PRIORITIES_2026-02.md)

**Planning architecture improvements?** → [ARCHITECTURE_IMPROVEMENTS_2026-02.md](ARCHITECTURE_IMPROVEMENTS_2026-02.md)

**Understanding the UX roadmap?** → [ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md) (✅ COMPLETE)

---

## Active Planning Documents

### 1. Current Priorities & Status

**[CURRENT_PRIORITIES_2026-02.md](CURRENT_PRIORITIES_2026-02.md)** - **START HERE**

**Purpose**: Single source of truth for current sprint/project status

**Contains**:
- Current project version and test count
- Recently completed work (last 1-2 weeks)
- Active priorities ranked
- Success metrics
- Next action recommendations

**When to read**: Starting any new work session

**When to update**: After completing major features, weekly at minimum

**Last updated**: 2026-02-14

---

### 2. Architecture Improvements Roadmap

**[ARCHITECTURE_IMPROVEMENTS_2026-02.md](ARCHITECTURE_IMPROVEMENTS_2026-02.md)**

**Purpose**: Medium-term developer experience improvements

**Contains**:
- Config introspection tools (Priority 1)
- Scaffolding commands (Priority 2)
- Type hints completion (Priority 3)
- Detection strategies (Priority 4)
- Rule mixins/templates (Priority 5-6)

**When to read**: Planning DX/architecture improvements

**When to update**: After completing architecture priorities

**Last updated**: 2026-02-10

---

## Completed Roadmaps (Reference Only)

### 3. Adapter UX Consistency

**[ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md)** - ✅ **COMPLETE**

**Purpose**: Long-term UX consistency roadmap (8 phases)

**Status**:
- ✅ **All 8 phases complete** (v0.45.0 - v0.48.0)
- Phase 1: Universal operation flags
- Phase 2: Stdin batch processing
- Phase 3: Query operator standardization
- Phase 4: Field selection + budget awareness
- Phase 5: Element discovery
- Phase 6: Help introspection
- Phase 7: Output Contract v1.1
- Phase 8: Convenience flags

**When to read**: Understanding UX design decisions, authoring new adapters

**Historical value**: Documents the design thinking behind adapter consistency

**Last updated**: 2026-02-06

---

### 4. Technical Debt Resolution

**[TECHNICAL_DEBT_RESOLUTION.md](TECHNICAL_DEBT_RESOLUTION.md)**

**Purpose**: TreeSitter architecture audit response

**Status**: ~90% complete

**When to read**: Working on TreeSitter-related improvements

**Last updated**: 2026-01-13

---

## Archived Planning Documents

**Location**: [../archived/planning/](../archived/planning/)

**Contains**:
- Completed strategic analyses (STRATEGIC_PRIORITIES_ANALYSIS_2026-02-07.md)
- Historical decision-making records
- Past planning sessions

**When to archive**: After planning doc served its purpose (features shipped, recommendations completed)

---

## Document Lifecycle

Planning documents follow the lifecycle defined in [../LIFECYCLE.md](../LIFECYCLE.md):

**Active** (this directory):
- Currently relevant planning
- Reference for active development
- Updated as work progresses

**Archived** ([../archived/planning/](../archived/planning/)):
- Completed plans (features shipped)
- Historical decision records
- Kept for reference, not updated

**Removed** (deleted from repo):
- Obsolete or incorrect planning
- No longer relevant

---

## When to Create New Planning Docs

**Create new planning doc when**:
- Starting multi-week effort (like UX consistency roadmap)
- Major architectural changes proposed
- Strategic direction needs documentation

**Naming convention**: `TOPIC_YYYY-MM-DD.md` (use date of creation)

**Don't create planning doc for**:
- One-off tasks (use issues/PRs instead)
- Quick fixes (document in commit message)
- Short-term work (<1 week effort)

---

## Integration with Other Docs

### vs Public Docs

**Planning docs** (this directory):
- Internal decision-making
- Work prioritization
- Architecture proposals

**Public docs** ([../../reveal/docs/](../../reveal/docs/)):
- User-facing guides
- Feature documentation
- Quick starts and recipes

**Public roadmap** ([../../ROADMAP.md](../../ROADMAP.md)):
- Public-facing feature timeline
- Version history
- Upcoming features

### vs Other Internal Docs

**Planning** (this directory):
- Future work
- Strategic direction
- Priorities

**Refactoring** ([../refactoring/](../refactoring/)):
- Code quality improvements
- Technical debt
- Architecture reviews

**Research** ([../research/](../research/)):
- Dogfooding reports
- Experiments
- Validation studies

**Case Studies** ([../case-studies/](../case-studies/)):
- Bug analyses
- Incident post-mortems
- Pattern discovery

---

## Quick Reference

| Question | Document |
|----------|----------|
| What should I work on next? | [CURRENT_PRIORITIES_2026-02.md](CURRENT_PRIORITIES_2026-02.md) |
| What's the current project status? | [CURRENT_PRIORITIES_2026-02.md](CURRENT_PRIORITIES_2026-02.md) |
| How many tests? What version? | [CURRENT_PRIORITIES_2026-02.md](CURRENT_PRIORITIES_2026-02.md) |
| What architecture improvements are planned? | [ARCHITECTURE_IMPROVEMENTS_2026-02.md](ARCHITECTURE_IMPROVEMENTS_2026-02.md) |
| Why is adapter UX designed this way? | [ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md) |
| What phases are complete? | [ADAPTER_UX_CONSISTENCY_2026-02-06.md](ADAPTER_UX_CONSISTENCY_2026-02-06.md) |
| What was the strategic thinking? | [../archived/planning/STRATEGIC_PRIORITIES_ANALYSIS_2026-02-07.md](../archived/planning/STRATEGIC_PRIORITIES_ANALYSIS_2026-02-07.md) |

---

## Maintenance Guidelines

### Weekly Review

**Every Friday** (or end of sprint):
1. Update CURRENT_PRIORITIES with completed work
2. Update test count and version
3. Add new priorities based on blockers
4. Archive completed planning docs

### Monthly Review

**First Monday of month**:
1. Review all active planning docs
2. Archive completed roadmaps
3. Update architecture improvement priorities
4. Check alignment with public ROADMAP.md

### Before Major Releases

1. Update CURRENT_PRIORITIES with release highlights
2. Check that planning docs reflect shipped features
3. Archive completed phase roadmaps
4. Update public ROADMAP.md

---

## Contributing

When updating planning docs:
- ✅ Update dates and version numbers
- ✅ Mark completed items with ✅
- ✅ Add session IDs for traceability
- ✅ Keep current priorities < 1 page
- ✅ Archive docs when their purpose is served

---

**Questions?** See [../LIFECYCLE.md](../LIFECYCLE.md) for document lifecycle policy.

**Need help?** Check [../README.md](../README.md) for full internal docs structure.
