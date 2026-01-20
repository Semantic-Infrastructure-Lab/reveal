# Reveal Internal Documentation

Internal development documentation for the reveal project. These docs capture architectural decisions, research findings, historical records, and development planning that aren't appropriate for user-facing documentation.

## Directory Structure

```
internal-docs/
├── README.md                    # This file
├── case-studies/                # Bug analysis, real-world usage
│   └── BUG_PREVENTION.md        # git:// routing bug analysis
├── planning/                    # Feature planning and design
│   └── TECHNICAL_DEBT_RESOLUTION.md  # Tech debt audit response
├── refactoring/                 # Code quality reviews
│   └── CODE_QUALITY_REVIEW_2026-01-18.md
└── research/                    # Dogfooding, experiments
    └── DOGFOODING_REPORT_2026-01-19.md
```

## Document Inventory

### Case Studies

| Document | Description | Date |
|----------|-------------|------|
| [BUG_PREVENTION.md](case-studies/BUG_PREVENTION.md) | git:// routing bug analysis and prevention strategies | 2026-01-16 |

### Planning

| Document | Description | Date |
|----------|-------------|------|
| [TECHNICAL_DEBT_RESOLUTION.md](planning/TECHNICAL_DEBT_RESOLUTION.md) | TreeSitter architecture audit response (~90% complete) | 2026-01-13 |

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

## Adding New Documents

| Type | Location |
|------|----------|
| Bug analysis | `case-studies/` |
| Feature design | `planning/` |
| Code quality | `refactoring/` |
| Experiments | `research/` |

**Naming convention:** `TOPIC_YYYY-MM-DD.md` for dated documents.
