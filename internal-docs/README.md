# Reveal Internal Documentation

Internal development documentation for the reveal project. These docs capture architectural decisions, research findings, and development planning that aren't appropriate for user-facing documentation.

## Directory Structure

```
internal-docs/
├── README.md                    # This file - inventory and navigation
├── case-studies/                # Real-world usage analysis
├── planning/                    # Feature planning and design docs
├── refactoring/                 # Code quality reviews and refactoring plans
│   └── CODE_QUALITY_REVIEW_2026-01-18.md
└── research/                    # Dogfooding, experiments, findings
    └── DOGFOODING_REPORT_2026-01-19.md
```

## Document Inventory

### Refactoring

| Document | Description | Status |
|----------|-------------|--------|
| [CODE_QUALITY_REVIEW_2026-01-18.md](refactoring/CODE_QUALITY_REVIEW_2026-01-18.md) | Comprehensive duplication analysis and refactoring opportunities | Active |

### Research

| Document | Description | Status |
|----------|-------------|--------|
| [DOGFOODING_REPORT_2026-01-19.md](research/DOGFOODING_REPORT_2026-01-19.md) | Adapter validation via dogfooding starting from `reveal://help` | Complete |

## Related Documentation

### User-Facing Docs (`reveal/docs/`)
- **AGENT_HELP.md** - Quick reference for AI agents
- **QUICK_START.md** - Getting started guide
- **CONFIGURATION_GUIDE.md** - Config file reference
- 14 additional guides covering adapters, analyzers, and features

### Developer Docs (`docs/`)
- **OUTPUT_CONTRACT.md** - Stable output format specification
- **BUG_PREVENTION.md** - Quality rules and their rationale
- **REVEAL_CODEBASE_REVIEW_GUIDE.md** - How to review reveal's own code

### Root-Level Docs
- **CHANGELOG.md** - Version history and release notes
- **CONTRIBUTING.md** - Contribution guidelines
- **RELEASING.md** - Release process documentation
- **STABILITY.md** - API stability guarantees
- **TECHNICAL_DEBT_RESOLUTION.md** - Debt tracking and resolution

## Adding New Documents

1. **Research/experiments** → `research/`
2. **Code quality/refactoring** → `refactoring/`
3. **Feature design/planning** → `planning/`
4. **Real-world usage analysis** → `case-studies/`

Use the naming convention: `TOPIC_YYYY-MM-DD.md` for dated documents.
