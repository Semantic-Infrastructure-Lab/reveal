# Reveal Internal Documentation

Internal development documentation for the reveal project. These docs capture architectural decisions, research findings, historical records, and development planning that aren't appropriate for user-facing documentation.

## Directory Structure

```
internal-docs/
├── README.md                    # This file
├── LIFECYCLE.md                 # Document lifecycle policy
├── UNIFIED_OPERATOR_REFERENCE.md # Query operator reference (Phase 3)
├── archived/                    # Completed work (not tracked in git)
│   ├── case-studies/
│   ├── planning/
│   ├── refactoring/
│   └── research/
├── case-studies/                # Bug analysis, real-world usage
│   └── BUG_PREVENTION.md
├── marketing/                   # Marketing intelligence and voice development
│   └── MARKETING_INTELLIGENCE_2026-01-20.md
├── planning/                    # Feature planning and design
│   ├── CURRENT_PRIORITIES_2026-02.md  # Active priorities
│   ├── ADAPTER_UX_CONSISTENCY_2026-02-06.md  # UX roadmap (5 phases)
│   └── TECHNICAL_DEBT_RESOLUTION.md
├── refactoring/                 # Code quality reviews
│   ├── REFACTORING_ACTION_PLAN.md
│   ├── CODE_QUALITY_REVIEW_2026-01-18.md
│   └── ARCHITECTURE_IMPROVEMENTS_2026-01-20.md
└── research/                    # Dogfooding, experiments
    ├── DOGFOODING_REPORT_2026-01-19.md
    ├── UX_ISSUES_2026-01-20.md
    ├── VALIDATION_REPORT.md
    └── MYSQL_VALIDATION_REPORT.md
```

## Document Inventory

### Case Studies

| Document | Description | Date |
|----------|-------------|------|
| [BUG_PREVENTION.md](case-studies/BUG_PREVENTION.md) | git:// routing bug analysis and prevention strategies | 2026-01-16 |

### Marketing

| Document | Description | Date |
|----------|-------------|------|
| [MARKETING_INTELLIGENCE_2026-01-20.md](marketing/MARKETING_INTELLIGENCE_2026-01-20.md) | Comprehensive audit: positioning, features, messaging angles, gaps, voice materials | 2026-01-20 |

### Planning

| Document | Description | Date |
|----------|-------------|------|
| [CURRENT_PRIORITIES_2026-02.md](planning/CURRENT_PRIORITIES_2026-02.md) | **Active** - Current project priorities and status (Phases 1-8 complete, xlsx adapter, Windows CI) | 2026-02-14 |
| [ARCHITECTURE_IMPROVEMENTS_2026-02.md](planning/ARCHITECTURE_IMPROVEMENTS_2026-02.md) | **Active** - Developer experience improvements roadmap (config introspection, scaffolding) | 2026-02-10 |
| [ADAPTER_UX_CONSISTENCY_2026-02-06.md](planning/ADAPTER_UX_CONSISTENCY_2026-02-06.md) | Long-term roadmap for adapter consistency (3-tier model, 8 phases) - ✅ **COMPLETE** | 2026-02-06 |
| [TECHNICAL_DEBT_RESOLUTION.md](planning/TECHNICAL_DEBT_RESOLUTION.md) | TreeSitter architecture audit response (~90% complete) | 2026-01-13 |

**Archived**: See [archived/planning/](archived/planning/) for completed strategic analyses

### Refactoring

| Document | Description | Date |
|----------|-------------|------|
| [REFACTORING_ACTION_PLAN.md](refactoring/REFACTORING_ACTION_PLAN.md) | **Active** - Consolidated action plan (start here) | 2026-01-20 |
| [CODE_QUALITY_REVIEW_2026-01-18.md](refactoring/CODE_QUALITY_REVIEW_2026-01-18.md) | Micro-level duplication analysis (~200-300 lines) | 2026-01-18 |
| [ARCHITECTURE_IMPROVEMENTS_2026-01-20.md](refactoring/ARCHITECTURE_IMPROVEMENTS_2026-01-20.md) | Meta-level refactoring (monolithic files, renderer consolidation, ~4000 lines) | 2026-01-20 |

### Research

| Document | Description | Date |
|----------|-------------|------|
| [DOGFOODING_REPORT_2026-01-19.md](research/DOGFOODING_REPORT_2026-01-19.md) | Adapter validation via dogfooding | 2026-01-19 |
| [UX_ISSUES_2026-01-20.md](research/UX_ISSUES_2026-01-20.md) | UX issues identified during dogfooding | 2026-01-20 |
| [VALIDATION_REPORT.md](research/VALIDATION_REPORT.md) | Claude adapter validation (all tests passed) | 2026-01-22 |
| [MYSQL_VALIDATION_REPORT.md](research/MYSQL_VALIDATION_REPORT.md) | MySQL adapter production validation (56 tests + live db) | 2026-01-22 |

### Reference Documentation

| Document | Description | Date |
|----------|-------------|------|
| [UNIFIED_OPERATOR_REFERENCE.md](UNIFIED_OPERATOR_REFERENCE.md) | Authoritative reference for query operators across all adapters (Phase 3) | 2026-02-07 |

## Related Documentation

### User-Facing Docs (`reveal/docs/`)
- **AGENT_HELP.md** - Complete AI agent reference
- **RECIPES.md** - Task-based workflows
- **QUICK_START.md** - Getting started guide
- **CODEBASE_REVIEW.md** - Complete review workflows
- 10 additional guides covering adapters, analyzers, and features

### Root-Level Docs
- **CHANGELOG.md** - Version history
- **CONTRIBUTING.md** - Contribution guidelines
- **RELEASING.md** - Release process
- **STABILITY.md** - API stability guarantees

## Document Lifecycle

See [LIFECYCLE.md](LIFECYCLE.md) for the complete policy on when documents are active, archived, or removed.

**Quick reference**:
- **Active** - `internal-docs/{category}/` - Currently relevant
- **Archived** - `internal-docs/archived/{category}/` - Completed work, kept for reference
- **Removed** - Deleted from repo - Obsolete or incorrect

**Archive trigger**: Planning (after shipped), Research (6 months or implemented), Refactoring (after completed)

## Adding New Documents

| Type | Location |
|------|----------|
| Bug analysis | `case-studies/` |
| Marketing/voice | `marketing/` |
| Feature design | `planning/` |
| Code quality | `refactoring/` |
| Experiments | `research/` |

**Naming convention:** `TOPIC_YYYY-MM-DD.md` for dated documents.
