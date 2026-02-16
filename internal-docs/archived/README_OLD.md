# Internal Documentation Index

**Purpose**: Private planning, research, and maintainer documentation (not in public git repo)

**Quick Navigation**:
- **Strategic direction?** → planning/POSITIONING_STRATEGY.md
- **What to build?** → planning/PRIORITIES.md
- **Deep analysis?** → research/ directory
- **Quality gates?** → VALIDATION_ROADMAP.md
- **Dev standards?** → ARCHITECTURAL_DILIGENCE.md
- **Lost/new here?** → DOC_NAVIGATION.md (detailed guide)
- **Documentation overview?** → DOCS_SUMMARY.md (meta-doc)

---

## Core Standards & Process

- **ARCHITECTURAL_DILIGENCE.md** - Development quality standards and gates
- **RUFF_ALIGNMENT.md** - Linting/style alignment status with Ruff
- **REGEX_TO_TREESITTER_MIGRATION.md** - Tree-sitter migration tracking
- **PRACTICAL_UTILITY_ANALYSIS.md** - Utility analysis for features

## Validation System

- **VALIDATION_ROADMAP.md** - V-rules gaps, improvement plan, and implementation status
  - Complete V001-V015 reference
  - Identified gaps and fixes
  - Success metrics: 0% → 100% catch rate

## Documentation Meta

- **DOC_NAVIGATION.md** - Navigation guide for internal docs
- **DOCS_SUMMARY.md** - Meta-documentation overview
- **DOCUMENTATION_HEALTH_REPORT.md** - Audit results (historical)

## Active Planning

- **planning/POSITIONING_STRATEGY.md** - Product positioning, value prop, strategic direction
- **planning/PRIORITIES.md** - Authoritative roadmap
- **planning/GIT_ADAPTER_DESIGN.md** - Git adapter specification (comprehensive)
- **planning/CLAUDE_ADAPTER_DESIGN.md** - Claude adapter design spec
- **planning/CLAUDE_ADAPTER_INTEGRATION_ANALYSIS.md** - Integration analysis
- **planning/AST_QUERY_PATTERNS.md** - AST query cookbook and patterns
- **planning/EXTRACTION_IMPROVEMENTS.md** - Extraction feature improvements

## Research & Investigation

- **research/TLDR_FEEDBACK_ANALYSIS.md** - External feedback analysis (tldr-pages comparison)
- **research/MARKDOWN_SUPPORT_ISSUES.md** - Markdown analyzer issues and improvements
- **research/JAVA_ANALYZER_COMPARISON.md** - Tree-sitter vs custom parser evaluation
- **research/POPULAR_REPOS_TESTING.md** - Real-world validation on popular repos
- **research/POPULAR_REPOS_TESTING_ISSUES.md** - Bugs discovered during testing
- **research/OUTPUT_CONTRACT_ANALYSIS.md** - Output contract design analysis
- **research/GIT_ADAPTER_ANALYSIS.md** - Git adapter research
- **research/CLAUDE_ADAPTER_POSTMORTEM.md** - Claude adapter lessons learned
- **research/ADAPTER_CONSISTENCY_AUDIT_2026-01-19.md** - Adapter consistency audit
- **research/DOGFOODING_REPORT_2026-01-15.md** - Prior dogfooding session
- **research/DOGFOODING_REPORT_2026-01-19.md** - Latest dogfooding (found claude:// bug)

## Case Studies

- **case-studies/VEINBORN_CASE_STUDY.md** - Real-world usage analysis
- **case-studies/VEINBORN_FEEDBACK.md** - User feedback documentation

## Release Management

- **releasing/PROCESS_NOTES.md** - Release procedure notes

## Archived Planning

- **planning/archived/** - Deprioritized/obsolete planning docs
  - ADVANCED_URI_SCHEMES.md (post-v1.0 concepts)
  - PRACTICAL_CODE_ANALYSIS_ADAPTERS.md (deprioritized adapters)
  - GITHUB_ISSUES_FROM_TESTING.md (test results)

## Historical Archive

**Moved to ~/Archive/reveal-docs-2026-01-14/** (obsolete docs from v0.7 era)

---

## Directory Structure

```
internal-docs/  (maintainer workspace - outside public git)
├── README.md (this file)
├── ARCHITECTURAL_DILIGENCE.md
├── DOC_NAVIGATION.md
├── DOCS_SUMMARY.md
├── DOCUMENTATION_HEALTH_REPORT.md
├── PRACTICAL_UTILITY_ANALYSIS.md
├── REGEX_TO_TREESITTER_MIGRATION.md
├── RUFF_ALIGNMENT.md
├── VALIDATION_ROADMAP.md
├── case-studies/
│   ├── VEINBORN_CASE_STUDY.md
│   └── VEINBORN_FEEDBACK.md
├── planning/
│   ├── AST_QUERY_PATTERNS.md
│   ├── CLAUDE_ADAPTER_DESIGN.md
│   ├── CLAUDE_ADAPTER_INTEGRATION_ANALYSIS.md
│   ├── EXTRACTION_IMPROVEMENTS.md
│   ├── GIT_ADAPTER_DESIGN.md
│   ├── POSITIONING_STRATEGY.md
│   ├── PRIORITIES.md
│   └── archived/
├── research/
│   ├── ADAPTER_CONSISTENCY_AUDIT_2026-01-19.md
│   ├── CLAUDE_ADAPTER_POSTMORTEM.md
│   ├── DOGFOODING_REPORT_2026-01-15.md
│   ├── DOGFOODING_REPORT_2026-01-19.md
│   ├── GIT_ADAPTER_ANALYSIS.md
│   ├── JAVA_ANALYZER_COMPARISON.md
│   ├── MARKDOWN_SUPPORT_ISSUES.md
│   ├── OUTPUT_CONTRACT_ANALYSIS.md
│   ├── POPULAR_REPOS_TESTING.md
│   ├── POPULAR_REPOS_TESTING_ISSUES.md
│   └── TLDR_FEEDBACK_ANALYSIS.md
└── releasing/
    └── PROCESS_NOTES.md

external-git/  (public OSS boundary - GitHub/PyPI)
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
└── reveal/  (source code)
```

---

## Doc Lifecycle

1. **Plan** in `planning/` - Design specs, architecture proposals
2. **Research** in `research/` - Comparisons, experiments, investigations
3. **Ship** - Extract user-facing content to `external-git/`
4. **Archive** - Move obsolete docs to `planning/archived/` or `~/Archive/reveal-docs-YYYY-MM-DD/`

---

## Quick Reference

| Need | Document |
|------|----------|
| **Product strategy** | **planning/POSITIONING_STRATEGY.md** |
| Quality standards | ARCHITECTURAL_DILIGENCE.md |
| Validation roadmap | VALIDATION_ROADMAP.md |
| Project roadmap | planning/PRIORITIES.md |
| Git adapter design | planning/GIT_ADAPTER_DESIGN.md |
| Claude adapter design | planning/CLAUDE_ADAPTER_DESIGN.md |
| AST patterns | planning/AST_QUERY_PATTERNS.md |
| Ecosystem patterns | research/TLDR_FEEDBACK_ANALYSIS.md |
| Markdown issues | research/MARKDOWN_SUPPORT_ISSUES.md |
| Release process | releasing/PROCESS_NOTES.md |
| Dogfooding results | research/DOGFOODING_REPORT_2026-01-19.md |

---

**Last updated:** 2026-01-19 (comprehensive inventory update)

**Recent changes** (2026-01-19):
- **Inventory**: Updated to reflect actual 34 files (was documenting only 20)
- **Dogfooding**: Found and fixed claude:// adapter bug (missing import in routing.py)
- **Architecture**: Simplified adapter registration (single source of truth in adapters/__init__.py)
- **Testing**: Added test_all_adapters_have_renderers to prevent future regressions
- **Documentation**: Updated AGENT_HELP.md with extraction syntaxes (:LINE, @N, Class.method)
