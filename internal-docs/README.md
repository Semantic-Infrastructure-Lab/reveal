# Internal Documentation

**Last Updated**: 2026-02-15
**Session**: onyx-brush-0215

This directory contains internal documentation for Reveal maintainers, including architecture decisions, research findings, planning documents, case studies, and technical debt tracking.

---

## 🚀 Quick Start

**New to internal docs?** Start here:

1. **[INDEX.md](INDEX.md)** - Complete list of all documents with descriptions
2. **[FILING_GUIDE.md](FILING_GUIDE.md)** - How to add and organize new docs
3. **[LIFECYCLE.md](LIFECYCLE.md)** - Document lifecycle and archiving rules

**Looking for something specific?**
- **Current priorities** → [planning/PRIORITIES.md](planning/PRIORITIES.md)
- **Architecture decisions** → [research/ARCHITECTURAL_DILIGENCE.md](research/ARCHITECTURAL_DILIGENCE.md)
- **Recent research** → [research/](research/) directory
- **Historical docs** → [archived/](archived/) subdirectories

---

## 📂 Directory Structure

| Directory | Purpose | File Count | Examples |
|-----------|---------|------------|----------|
| **planning/** | Current roadmaps, strategies, designs | ~12 | PRIORITIES.md, CLAUDE_ADAPTER_DESIGN.md |
| **research/** | Analysis, investigations, findings | ~15 | ARCHITECTURAL_DILIGENCE.md, OUTPUT_CONTRACT_ANALYSIS.md |
| **case-studies/** | Real-world usage and integration studies | ~4 | VEINBORN_CASE_STUDY.md, BUG_PREVENTION.md |
| **refactoring/** | Refactoring plans and technical debt | ~1 | REFACTORING_ACTION_PLAN.md |
| **feedback/** | User and integration feedback | ~1 | IMMUNITY_CODE_RAG_FEEDBACK.md |
| **releasing/** | Release process and checklists | ~1 | PROCESS_NOTES.md |
| **archived/** | Historical docs and dated snapshots | ~20 | archived/research/, archived/planning/ |

---

## 📖 Key Documents by Category

### 🏗️ Architecture & Design
| Document | Lines | Description |
|----------|-------|-------------|
| [CLAUDE_ADAPTER_DESIGN.md](planning/CLAUDE_ADAPTER_DESIGN.md) | 1539 | Claude adapter architecture, patterns, implementation details |
| [GIT_ADAPTER_DESIGN.md](planning/GIT_ADAPTER_DESIGN.md) | 1380 | Git adapter architecture, query system, performance |
| [ARCHITECTURAL_DILIGENCE.md](research/ARCHITECTURAL_DILIGENCE.md) | 974 | Overall architectural analysis and decisions |
| [AST_QUERY_PATTERNS.md](planning/AST_QUERY_PATTERNS.md) | 299 | AST query patterns and best practices |

### 📋 Planning & Strategy
| Document | Lines | Description |
|----------|-------|-------------|
| [PRIORITIES.md](planning/PRIORITIES.md) | 920 | **Current project priorities and roadmap** ⭐ |
| [POSITIONING_STRATEGY.md](planning/POSITIONING_STRATEGY.md) | 534 | Product positioning and market strategy |
| [VALIDATION_ROADMAP.md](planning/VALIDATION_ROADMAP.md) | 613 | Validation rules roadmap and plans |
| [TECHNICAL_DEBT_RESOLUTION.md](planning/TECHNICAL_DEBT_RESOLUTION.md) | 688 | Ongoing technical debt tracking |

### 🔬 Research & Analysis
| Document | Lines | Description |
|----------|-------|-------------|
| [OUTPUT_CONTRACT_ANALYSIS.md](research/OUTPUT_CONTRACT_ANALYSIS.md) | 972 | Output consistency analysis across adapters |
| [PRACTICAL_UTILITY_ANALYSIS.md](research/PRACTICAL_UTILITY_ANALYSIS.md) | 629 | Value and utility analysis |
| [MARKDOWN_SUPPORT_ISSUES.md](research/MARKDOWN_SUPPORT_ISSUES.md) | 507 | Markdown support issues and gaps |
| [MYSQL_VALIDATION_REPORT.md](research/MYSQL_VALIDATION_REPORT.md) | 699 | MySQL adapter comprehensive validation |

### 📚 Guides & References
| Document | Lines | Description |
|----------|-------|-------------|
| [UNIFIED_OPERATOR_REFERENCE.md](UNIFIED_OPERATOR_REFERENCE.md) | 670 | Complete query operator reference |
| [MYSQL_TIMESTAMP_IMPROVEMENTS.md](MYSQL_TIMESTAMP_IMPROVEMENTS.md) | 558 | MySQL timestamp handling improvements |
| [FILING_GUIDE.md](FILING_GUIDE.md) | 226 | How to file and organize docs |
| [LIFECYCLE.md](LIFECYCLE.md) | 363 | Document lifecycle management |

### 🎯 Case Studies
| Document | Lines | Description |
|----------|-------|-------------|
| [VEINBORN_CASE_STUDY.md](case-studies/VEINBORN_CASE_STUDY.md) | 439 | Veinborn integration case study and lessons |
| [VEINBORN_FEEDBACK.md](case-studies/VEINBORN_FEEDBACK.md) | 380 | Detailed feedback from Veinborn integration |
| [BUG_PREVENTION.md](case-studies/BUG_PREVENTION.md) | 310 | Bug prevention strategies and patterns |

---

## 🗂️ Document Lifecycle

### Living Documents (No Date in Filename)
**Actively maintained, represent current state**

Examples:
- `PRIORITIES.md` - Always shows current priorities
- `CLAUDE_ADAPTER_DESIGN.md` - Updated as design evolves
- `ARCHITECTURAL_DILIGENCE.md` - Ongoing analysis

**Location**: Main subdirectories (planning/, research/, etc.)

### Dated Snapshots (Date in Filename)
**Point-in-time reports, automatically archived**

Examples:
- `DOGFOODING_REPORT_2026-02-07.md` - Snapshot from Feb 7
- `CURRENT_PRIORITIES_2026-02.md` - Priorities as of Feb 2026
- `COMPLEXITY_FIX_2026-02-09.md` - Specific fix documentation

**Location**: `archived/` subdirectories

See [LIFECYCLE.md](LIFECYCLE.md) for complete lifecycle rules.

---

## ✍️ Contributing

### Adding New Documentation

1. **Choose Location** (see [FILING_GUIDE.md](FILING_GUIDE.md)):
   - Planning/roadmap → `planning/`
   - Research/analysis → `research/`
   - Case study → `case-studies/`
   - User feedback → `feedback/`
   - Release notes → `releasing/`

2. **Naming Convention**:
   - Living docs: `DESCRIPTIVE_NAME.md` (no date)
   - Snapshots: `DESCRIPTIVE_NAME_YYYY-MM-DD.md` (with date)
   - Use UPPERCASE, underscores, be descriptive

3. **Update Index**:
   - Add entry to [INDEX.md](INDEX.md) with line count and description

4. **Commit with Context**:
   - Include session ID if applicable
   - Describe purpose and key findings

### Archiving Documents

**When to Archive**:
- Document has date in filename (automatic rule)
- Document is superseded by newer version
- Document is historical snapshot, not living

**How to Archive**:
```bash
mv planning/OLD_DOC_2026-01.md archived/planning/
mv research/HISTORICAL_REPORT.md archived/research/
```

Update INDEX.md to move entry to archived section.

---

## 🔍 Finding Information

### By Topic
- **Architecture** → planning/ (CLAUDE_ADAPTER_DESIGN, GIT_ADAPTER_DESIGN)
- **Priorities** → planning/PRIORITIES.md
- **Research** → research/ (OUTPUT_CONTRACT_ANALYSIS, ARCHITECTURAL_DILIGENCE)
- **Integration** → case-studies/ (VEINBORN_CASE_STUDY)
- **History** → archived/

### By Date
- **Recent (2026-02)** → Main directories (planning/, research/)
- **Historical (2026-01)** → archived/research/, archived/planning/

### By Size
- **Large (>1000 lines)** → CLAUDE_ADAPTER_DESIGN (1539), GIT_ADAPTER_DESIGN (1380)
- **Medium (500-1000)** → PRIORITIES (920), OUTPUT_CONTRACT_ANALYSIS (972)
- **Quick reads (<300)** → AST_QUERY_PATTERNS (299), FILING_GUIDE (226)

---

## 📊 Documentation Stats

**Current (Living) Documents**:
- Total files: ~45
- Total lines: ~25,000
- Categories: Planning (12), Research (15), Case Studies (4), Guides (4)

**Archived Documents**:
- Total files: ~20
- Categories: Planning (15), Research (10), Case Studies (1), Marketing (1), Refactoring (2)

**Last Consolidation**: 2026-02-15 (Session: onyx-brush-0215)
- Consolidated from dual internal-docs locations
- Archived 15 dated documents
- Created INDEX.md navigation
- Cleaned root directory (removed 7 internal docs)

---

## 🎯 Common Tasks

### "I need to understand the current architecture"
1. Start with [research/ARCHITECTURAL_DILIGENCE.md](research/ARCHITECTURAL_DILIGENCE.md)
2. Deep dive: [planning/CLAUDE_ADAPTER_DESIGN.md](planning/CLAUDE_ADAPTER_DESIGN.md)
3. See patterns: [planning/AST_QUERY_PATTERNS.md](planning/AST_QUERY_PATTERNS.md)

### "What are we working on now?"
1. Read [planning/PRIORITIES.md](planning/PRIORITIES.md) - Current roadmap
2. Check [planning/TECHNICAL_DEBT_RESOLUTION.md](planning/TECHNICAL_DEBT_RESOLUTION.md) - Active debt tracking
3. Review [planning/](planning/) - Other current plans

### "How did we solve X in the past?"
1. Search [archived/research/](archived/research/) - Historical research
2. Check [case-studies/](case-studies/) - Real-world examples
3. Review [archived/planning/](archived/planning/) - Old strategies

### "I want to add a new feature"
1. Check [planning/PRIORITIES.md](planning/PRIORITIES.md) - Is it planned?
2. Review [planning/VALIDATION_ROADMAP.md](planning/VALIDATION_ROADMAP.md) - Related validation
3. See [research/OUTPUT_CONTRACT_ANALYSIS.md](research/OUTPUT_CONTRACT_ANALYSIS.md) - Consistency patterns

---

## Related Documentation

### User-Facing Docs (`reveal/docs/`)
- **AGENT_HELP.md** - Complete AI agent reference
- **RECIPES.md** - Task-based workflows
- **QUICK_START.md** - Getting started guide
- **CODEBASE_REVIEW.md** - Complete review workflows
- 29 guides covering adapters, analyzers, and features

### Root-Level Docs
- **CHANGELOG.md** - Version history
- **CONTRIBUTING.md** - Contribution guidelines
- **INSTALL.md** - Installation instructions
- **RELEASING.md** - Release process
- **ROADMAP.md** - Public roadmap
- **SECURITY.md** - Security policy
- **STABILITY.md** - API stability guarantees

---

## 📧 Questions?

- **Where should this doc go?** → See [FILING_GUIDE.md](FILING_GUIDE.md)
- **Is this document current?** → Check filename (no date = living, date = archived)
- **Who maintains this?** → Reveal core maintainers (see CONTRIBUTING.md in root)

---

**Navigation**: [INDEX.md](INDEX.md) | [FILING_GUIDE.md](FILING_GUIDE.md) | [LIFECYCLE.md](LIFECYCLE.md)
