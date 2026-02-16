# Internal Documentation Index

**Last Updated**: 2026-02-15
**Session**: receding-journey-0215

---

## 📖 Current / Living Documents

These documents are actively maintained and represent current state.

### Design & Architecture

- **CLAUDE_ADAPTER_DESIGN.md** - Claude adapter architecture and design decisions (1539 lines)
- **GIT_ADAPTER_DESIGN.md** - Git adapter architecture and design decisions (1380 lines)
- **CLAUDE_ADAPTER_INTEGRATION_ANALYSIS.md** - Claude adapter integration analysis (925 lines)

### Planning & Roadmaps

- **PRIORITIES.md** - Current project priorities and roadmap (920 lines)
- **VALIDATION_ROADMAP.md** - Validation rules roadmap (613 lines)
- **MYPY_CLEANUP_STRATEGY.md** - Type checking cleanup strategy (394 lines)
- **REGEX_TO_TREESITTER_MIGRATION.md** - Migration strategy and status (322 lines)
- **RUFF_ALIGNMENT.md** - Ruff linter alignment (79 lines)
- **README.md** - Planning directory overview (250 lines)

### Research & Analysis

- **ARCHITECTURAL_DILIGENCE.md** - Architectural analysis and decisions (974 lines)
- **OUTPUT_CONTRACT_ANALYSIS.md** - Output contract consistency analysis (972 lines)
- **MYSQL_VALIDATION_REPORT.md** - MySQL adapter validation (699 lines)
- **PRACTICAL_UTILITY_ANALYSIS.md** - Practical utility and value analysis (629 lines)
- **POSITIONING_STRATEGY.md** - Product positioning and market strategy (534 lines)
- **TLDR_FEEDBACK_ANALYSIS.md** - TLDR integration feedback (513 lines)
- **MARKDOWN_SUPPORT_ISSUES.md** - Markdown support issues and gaps (507 lines)
- **POPULAR_REPOS_TESTING_ISSUES.md** - Issues found in popular repos (478 lines)
- **GIT_ADAPTER_ANALYSIS.md** - Git adapter research and findings (471 lines)
- **V_SERIES_TEST_PLAN_2026-02-07.md** - V-series test plan (467 lines)
- **EXCEL_UX_ANALYSIS.md** - Excel/XLSX UX analysis (387 lines)
- **AST_QUERY_PATTERNS.md** - AST query patterns and best practices (299 lines)
- **VALIDATION_REPORT.md** - General validation report (283 lines)
- **POPULAR_REPOS_TESTING.md** - Testing on popular repositories (219 lines)
- **JAVA_ANALYZER_COMPARISON.md** - Java analyzer comparison (212 lines)

### Case Studies

- **VEINBORN_CASE_STUDY.md** - Veinborn integration case study (439 lines)
- **VEINBORN_FEEDBACK.md** - Feedback from Veinborn (380 lines)
- **XLSX_DEMO.md** - Excel/XLSX demo and usage (366 lines)
- **BUG_PREVENTION.md** - Bug prevention strategies (310 lines)
- **CLAUDE_ADAPTER_POSTMORTEM.md** - Claude adapter postmortem (169 lines)

### Guides & References

- **FILING_GUIDE.md** - How to file and organize internal docs (226 lines)
- **LIFECYCLE.md** - Document lifecycle management (363 lines)
- **UNIFIED_OPERATOR_REFERENCE.md** - Operator reference guide (670 lines)
- **MYSQL_TIMESTAMP_IMPROVEMENTS.md** - MySQL timestamp handling (558 lines)

### Refactoring & Technical Debt

- **TECHNICAL_DEBT_RESOLUTION.md** - Ongoing technical debt tracking (688 lines)
- **REFACTORING_ACTION_PLAN.md** - Current refactoring action plan (295 lines)
- **TODO_TRACKING.md** - Internal task tracking (248 lines)

### Releasing

- **PROCESS_NOTES.md** - Release process notes and checklists (125 lines)

### Feedback

- **IMMUNITY_CODE_RAG_FEEDBACK.md** - Immunity Code RAG integration feedback (178 lines)

---

## 📦 Archived Documents

Historical documents and dated snapshots are in `archived/` subdirectories:

### archived/planning/
- ADAPTER_UX_CONSISTENCY_2026-02-06.md (1311 lines)
- ARCHITECTURE_IMPROVEMENTS_2026-02.md (605 lines)
- CURRENT_PRIORITIES_2026-02.md (408 lines)
- AGENTIC_AI_ENHANCEMENTS_2026-02-06.md (706 lines)
- DOC_CONSOLIDATION_SUMMARY_2026-02-06.md (232 lines)
- DOC_VALIDATION_REPORT_2026-02-06.md (449 lines)
- ADVANCED_URI_SCHEMES.md (1208 lines)
- EXTRACTION_IMPROVEMENTS.md (267 lines)
- GITHUB_ISSUES_FROM_TESTING.md (364 lines)
- PRACTICAL_CODE_ANALYSIS_ADAPTERS.md (668 lines)
- RELEASE_READINESS_2026-02-12.md
- DOCS_SUMMARY.md
- DOCUMENTATION_HEALTH_REPORT.md
- DOC_NAVIGATION.md
- README_ARCHIVED.md

### archived/research/
- DOGFOODING_REPORT_2026-01-15.md (479 lines)
- COMPLEXITY_FIX_2026-02-09.md (483 lines)
- SESSION_SUMMARY_2026-02-15.md (363 lines)
- ADAPTER_CONSISTENCY_AUDIT_2026-01-19.md (362 lines)
- COMPLEXITY_INVESTIGATION_2026-02-09.md (328 lines)
- DOGFOODING_ISSUES_2026-02-07.md (225 lines)
- DOGFOODING_REPORT_2026-02-07.md (211 lines)
- DOGFOODING_REPORT_2026-01-19_SESSION2.md (196 lines)
- DOGFOODING_REPORT_2026-01-19_ALTERNATE.md (186 lines) - Alternate version
- UX_ISSUES_2026-01-20.md (165 lines)
- DOGFOODING_REPORT_2026-01-19.md (149 lines)

### archived/case-studies/
- BUG_FIX_SUMMARY_2026-02-07.md (179 lines)

### archived/marketing/
- MARKETING_INTELLIGENCE_2026-01-20.md (494 lines)

### archived/refactoring/
- ARCHITECTURE_IMPROVEMENTS_2026-01-20.md (548 lines)
- CODE_QUALITY_REVIEW_2026-01-18.md (1235 lines)

**Note**: Archived docs are kept for historical reference but are no longer maintained.

---

## 🗂️ Directory Structure

```
internal-docs/
├── INDEX.md (this file)
├── README.md (overview and navigation)
├── FILING_GUIDE.md (how to file new docs)
├── LIFECYCLE.md (doc lifecycle management)
├── UNIFIED_OPERATOR_REFERENCE.md
├── MYSQL_TIMESTAMP_IMPROVEMENTS.md
├── archived/
│   ├── case-studies/
│   ├── marketing/
│   ├── planning/
│   ├── refactoring/
│   └── research/
├── case-studies/
├── design/          ✨ NEW: Completed architectures
├── feedback/
├── planning/        ✨ CLEANED: Now only roadmaps/plans
├── refactoring/
├── releasing/
└── research/
```

---

## 📝 Filing New Documents

See **FILING_GUIDE.md** for rules on where to place new documents.

**Quick Rules**:
- **Current work** → appropriate subdirectory (planning/, research/, etc.)
- **Dated snapshots** → archived/ with date in filename
- **Cross-cutting analysis** → research/
- **Living roadmaps** → planning/ (no date in filename)
- **Session summaries** → research/ with date suffix

---

## 🔍 Finding Documents

**By Topic**:
- Architecture decisions → design/ (CLAUDE_ADAPTER_DESIGN, GIT_ADAPTER_DESIGN)
- Current priorities → planning/PRIORITIES.md
- Research findings → research/ (OUTPUT_CONTRACT_ANALYSIS, etc.)
- Technical debt → refactoring/ (TECHNICAL_DEBT_RESOLUTION)
- Historical snapshots → archived/

**By Date**:
- Recent work (2026-02) → Most current docs are in main directories
- Historical (2026-01) → archived/research/, archived/planning/

---

## 📊 Stats

- **Total current documents**: ~40 files
- **Total archived documents**: ~32 files
- **Lines of documentation**: ~25,000 lines (current)
- **Last consolidation**: 2026-02-15 (Session: onyx-brush-0215)
- **Last cleanup**: 2026-02-15 (Session: receding-journey-0215)
- **Structure**: Single source of truth, clear categorical organization

---

**Quick Links**:
- [README](README.md) - Documentation overview
- [FILING_GUIDE](FILING_GUIDE.md) - How to add new docs
- [LIFECYCLE](LIFECYCLE.md) - Document lifecycle rules
- [PRIORITIES](planning/PRIORITIES.md) - Current project priorities
