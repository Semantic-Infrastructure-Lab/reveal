# Reveal Priorities

> **Mission:** Make AI coding assistants (Claude Code, TIA, Copilot) more effective by providing maximum understanding per token across popular tech stacks.

**Last Updated:** 2026-02-06
**Current Version:** v0.44.2
**Document Type**: Authoritative Roadmap (Single Source of Truth)

**Recent Updates:**
- 2026-02-06: **Doc validation** - Updated to v0.44.2, verified 16 adapters, validated all planning docs
- 2026-01-21: ✅ **ssl:// COMPLETE** - Shipped v0.44.2 with TLS 1.3 cert parsing, domain:// adapter, composable pipelines
- 2026-01-20: Added Infrastructure Adapters category (ssl://, nginx://) from real-world ops debugging feedback
- 2026-01-20: Updated to v0.40.0, added v0.38-v0.40 releases, cleaned up stale content
- 2026-01-17: ✅ **TIER 1 COMPLETE** - All three Tier 1 priorities shipped (Output Contract, Stability Taxonomy, git:// adapter)
- 2026-01-17: Documentation consolidation - Fixed stale PRIORITIES.md, standardized language counts (31 analyzers), updated CHANGELOG
- 2026-01-15: Added Tier 0 strategic positioning, restructured roadmap, added "Developer Experience & Ecosystem" category

---

## Document Scope

**This document is the SINGLE SOURCE OF TRUTH for**:
- What features to build
- Priority tiers and sequencing
- Effort estimates and status
- Implementation approach

**Related documents**:
- **Public roadmap** → external-git/ROADMAP.md (contributor-facing, no internal detail)
- **WHY these features?** → planning/POSITIONING_STRATEGY.md (strategic rationale)
- **Deep analysis?** → research/TLDR_FEEDBACK_ANALYSIS.md (research archive)
- **Quality gates?** → VALIDATION_ROADMAP.md (V-rules strategy)

---

## Core Value Proposition

AI agents reading code face a fundamental problem: **context windows cost tokens, tokens cost time and money.**

Reveal solves this by providing:
- **Structure over content** - 50 tokens vs 5000 to understand a file
- **Semantic queries** - Find what matters without grep noise
- **Progressive disclosure** - Overview → Details → Specifics

**Measured impact:** 10-25x token reduction on real codebases (tested on Django, FastAPI, Flask, Requests).

---

## Recent Releases

### v0.44.2 (2026-01-21)
- **SSL certificate parsing fix** - TLS 1.3 connections now properly handled
- **cryptography dependency** - Robust binary cert parsing eliminates false expiry reports
- **52 SSL tests passing** - Comprehensive test coverage

### v0.44.1 (2026-01-21)
- **Batch SSL filters with `--stdin --check`** - All filter flags work in composable pipelines (Issue #19)
- **Both syntaxes first-class** - `ssl://nginx:///` and `--extract | --stdin` both fully supported
- **51 SSL tests passing**

### v0.44.0 (2026-01-21)
- **`--extract` flag** - Composable pipeline support for structured data extraction
- **domain:// adapter** - Domain registration, DNS records, and health status inspection
- **nginx domain extraction** - `reveal nginx.conf --extract domains` outputs SSL URIs

### v0.43.0 (2026-01-21)
- **`@file` syntax** - Read targets from file (`reveal @domains.txt --check`)
- **`ssl://nginx:///` integration** - Extract SSL domains from nginx config
- **Batch SSL filters** - `--only-failures`, `--summary`, `--expiring-within`
- **Bug fix** - Spurious warnings in `--stdin` and `@file` processing

### v0.42.0 (2026-01-20)
- **Universal `--stdin` URI support** - Batch processing works with any URI scheme
- **Query parsing utilities** - `reveal/utils/query.py` for adapter authors

### v0.41.0 (2026-01-20)
- **`ssl://` adapter** - SSL certificate inspection (zero dependencies)
- **N004 rule** - ACME challenge path inconsistency detection
- **Content-based nginx detection** - `.conf` files auto-detect nginx patterns

### v0.40.0 (2026-01-20)
- **`--dir-limit` flag** - Per-directory entry cap, continues with siblings (solves node_modules problem)
- **Dead code cleanup** - Removed ~490 lines of dead code (V014, version_utils.py)
- **Release process** - Simplified to 2 files (pyproject.toml, CHANGELOG.md)
- **Dependency cleanup** - Removed unused optional deps (openpyxl, pygments)

### v0.39.0 (2026-01-19)
- **Breadcrumb improvements** - Extraction hints for 25+ file types
- **M104 rule** - Hardcoded list detection for maintainability
- **--adapters flag** - List all URI adapters with descriptions

### v0.38.0 (2026-01-18)
- **claude:// adapter Phase 1+2** - Session overview, tool analytics, thinking extraction
  - Progressive disclosure (overview → analytics → filtered → specific)
  - Tool success rate calculation, timeline view
  - 50 tests, 100% coverage

### v0.37.0 (2026-01-17)
- **git:// adapter** - Repository history, blame, time-travel
- **Output Contract v1.0** - All 13 adapters migrated
- **Stability Taxonomy** - Clear API stability guarantees (STABILITY.md)

### v0.36.0 (2026-01-15)
- **Workflow Recipes** - Task-based documentation (8 workflows)
- **Documentation consolidation** - Stripped marketing fluff from README

### v0.35.0 (2026-01-13)
- **sqlite:// adapter** - Zero-dependency SQLite database exploration
  - Database overview with schema, statistics, configuration
  - Table structure with columns, indexes, foreign keys
  - 22 tests, 98% code coverage
  - Examples: `reveal sqlite:///app.db`, `reveal sqlite:///app.db/users`

### v0.34.0 (2026-01-10)
- **HCL/Terraform** support (.tf, .tfvars, .hcl files)
- **GraphQL** support (.graphql, .gql files)
- **Protocol Buffers** support (.proto files)
- **Zig** support (.zig files)
- Migrated to tree-sitter-language-pack (165+ languages)
- Total language count: 34 → 38

### v0.33.0 (2026-01-10)
- **Kotlin, Swift, Dart** language support (mobile platforms)
- Language count: 31 → 34

### v0.32.2 (2026-01-08)
- Fixed MySQL adapter `.my.cnf` support (proper credential resolution)
- Fixed rule categorization bug (F, N, V rules now show under correct categories)

### v0.32.1 (2026-01-07)
- **I004 rule:** Standard library shadowing detection

### v0.32.0 (2026-01-07)
- **markdown:// adapter** - Query markdown files by front matter (`reveal 'markdown://?topics=reveal'`)
- **--related flags** - Knowledge graph navigation with unlimited depth support
- **C#, Scala, SQL language support** via tree-sitter
- **Workflow-aware breadcrumbs** (Phase 3) - Pre-commit and code review workflows

### v0.30.0-v0.31.0 Highlights
- **diff:// adapter** (v0.30.0) - Semantic structural comparison (files, directories, git refs)
- **Enhanced breadcrumbs** (v0.30.0-v0.31.0) - Context-aware workflow suggestions
- **I001 partial imports** (v0.31.0) - Detects each unused name individually (Ruff F401 alignment)

### Notable Older Features
- **imports://** adapter (v0.28.0) - Dependency analysis, circular import detection, layer violations
- **.reveal.yaml config** (v0.28.0) - Project-level rule configuration with environment variable overrides
- **mysql://** adapter (v0.17.0+) - Database schema exploration with DBA tuning ratios
- **python://** adapter (v0.17.0+) - Runtime inspection, package conflicts, bytecode debugging
- **ast://** queries (v0.15.0+) - Query code as a database (`ast://src?complexity>10`)
- **stats://** adapter - Code quality metrics and hotspot detection

---

## Mission Test

**Every feature must pass this test:**

✅ **Does it REVEAL something?** (not modify, not fix)
✅ **Does it reduce tokens?** (efficiency for AI agents)
✅ **Does it help understand code?** (structure, history, relationships)
✅ **Is it universally useful?** (ecosystem reach)

**Anti-patterns (auto-reject):**
❌ Modifies code (that's a linter/formatter)
❌ Adds observability (that's a monitoring tool)
❌ Requires external services (keep it local/offline)
❌ Only works for specific frameworks (generalize or skip)

---

## Priority Framework

**Score each feature on:**
1. **Token efficiency** - Does it reduce tokens needed to understand code?
2. **Ecosystem reach** - How many developers/projects use this?
3. **Implementation effort** - Can we ship it quickly?
4. **AI-agent fit** - Does it help automated coding workflows?

---

## Active Roadmap

### Tier 0: Documentation Consolidation (Zero Code, High Clarity) 🔥

**Why Tier 0**: External docs had marketing fluff (from kiyuda-0115) that didn't match actual usage patterns. Need honest, practical documentation.

**Impact**: Clear utility-first messaging, task-based workflows, contributor-friendly
**Effort**: 3-4 hours total (zero code changes)
**Status**: ✅ **COMPLETE** (4/4 tasks done)
**Session**: pulsing-horizon-0115 (2026-01-15)

#### What Changed

**Problem identified**: The kiyuda-0115 session leaked aspirational positioning language (POSITIONING_STRATEGY.md) into external docs as if it were proven reality. Created marketing fluff ("Trust and Legibility", "🛡️ AI Safety Net", unvalidated personas) that didn't match real usage.

**Solution**: Strip fluff, consolidate proven patterns, create workflow-based docs.

#### Tasks

1. **✅ Strip marketing fluff from README.md** (COMPLETED 2026-01-15)
   - Removed "Trust and Legibility for AI-Assisted Development" positioning
   - Removed "Why Reveal?" AI trust gap section
   - Removed "🛡️ AI Safety Net" branding
   - Removed aspirational personas (unvalidated use cases)
   - Replaced with utility-first framing: "Progressive Code Exploration"
   - New lead: "Structure before content. Understand code by navigating it, not reading it."
   - Kept all technical features (they're real and tested)
   - Added simple "Common Workflows" section with real examples

2. **✅ Update pyproject.toml description** (COMPLETED 2026-01-15)
   - Old: "Trust and legibility for AI-assisted development - verify code changes structurally"
   - New: "Progressive code exploration with semantic queries and structural diffs - understand code by navigating structure, not reading text"
   - Updated keywords: Removed "verification", "trust", "ai-safety" → Added "code-exploration", "ast", "tree-sitter"

3. **✅ Mark POSITIONING_STRATEGY.md as internal only** (COMPLETED 2026-01-15)
   - Added warning header: "INTERNAL PLANNING DOCUMENT"
   - Documented why the warning exists (kiyuda-0115 leakage)
   - Clear guidance: Use for strategic discussions, NOT for external docs

4. **✅ Create WORKFLOW_RECIPES.md** (COMPLETED 2026-01-15)
   - Task-based documentation (8 workflows: code review, onboarding, debugging, refactoring, docs, AI agents, databases, pipelines)
   - Consolidates proven patterns from COOL_TRICKS.md and AGENT_HELP.md
   - Real commands for real tasks
   - No aspirational fluff, only tested workflows

---

## Recently Shipped (v0.33.0 - v0.35.0)

### ✅ Language Support Gaps (COMPLETED v0.33.0 + v0.34.0)

**Mobile Platforms (v0.33.0):**
- ✅ **Kotlin** - Android, backend (8M+ developers)
- ✅ **Swift** - iOS/macOS (Apple ecosystem)
- ✅ **Dart** - Flutter (cross-platform mobile)

**Infrastructure + API (v0.34.0):**
- ✅ **HCL/Terraform** - Infrastructure-as-code (95% of cloud infra)
- ✅ **GraphQL** - API schema and queries (90% of modern APIs)
- ✅ **Protocol Buffers** - gRPC serialization (Google/FAANG standard)
- ✅ **Zig** - Modern systems programming

**Status:** ✅ **SHIPPED** (v0.33.0 + v0.34.0)
- Successfully migrated to tree-sitter-language-pack
- 165+ languages now available
- Language count: 31 → 34 (v0.33.0) → 38 (v0.34.0)
- Mobile development fully covered
- Infrastructure-as-code fully covered

**Impact:** Reveal now covers mobile development (Android, iOS, Flutter), infrastructure-as-code (Terraform), and modern API definitions (GraphQL, Protobuf).

### ✅ sqlite:// Adapter (COMPLETED v0.35.0)

```bash
reveal sqlite:///app.db                    # Database overview
reveal sqlite:///app.db/users              # Table structure
reveal sqlite://./relative.db              # Relative paths
```

**Status:** ✅ **SHIPPED** (v0.35.0)
- Zero dependencies (uses Python's built-in sqlite3)
- Database overview with schema, stats, config
- Table structure with columns, indexes, foreign keys
- Progressive disclosure pattern
- 22 tests, 98% coverage
- Comprehensive help: `reveal help://sqlite`

**Why:** SQLite is everywhere - mobile apps (iOS/Android), desktop apps, embedded systems, development databases, browser storage. Low effort (mysql:// template exists).

### ✅ Terraform/HCL Support (COMPLETED v0.34.0)

```bash
reveal infra/main.tf                       # Resources, variables, outputs
reveal infra/main.tf aws_instance.web      # Specific resource
reveal infra/ --check                      # Best practices
```

**Status:** ✅ **SHIPPED** (v0.34.0)
- Full HCL/Terraform file support (.tf, .tfvars, .hcl)
- Tree-sitter parsing for infrastructure-as-code
- Part of infrastructure + API language expansion

**Why:** Infrastructure-as-code is standard practice. Terraform is dominant (95% of cloud infra). AI agents helping with infra need this.


---

### Tier 1: High Value, Core Mission - ✅ **ALL COMPLETE** (2026-01-17)

**Status**: ✅ **100% COMPLETE** - All three Tier 1 priorities shipped
- Output Contract Specification v1.0
- Stability Taxonomy
- git:// Adapter

---

#### ✅ git:// Adapter (History/Blame) - **COMPLETE** (2026-01-17)

```bash
reveal git://.                              # Repository overview
reveal git://.@main                         # Branch/commit history
reveal git://src/auth.py@HEAD~5             # File 5 commits ago
reveal git://README.md@v0.30.0              # File at tag
reveal git://src/auth.py?type=history       # File commit history
reveal git://src/auth.py?type=blame         # Blame summary (contributors + key hunks)
reveal git://src/auth.py?type=blame&detail=full  # Line-by-line blame
reveal git://src/auth.py?type=blame&element=load_config  # Semantic blame
```

**Status**: ✅ **COMPLETE** - All core features implemented
- **Implementation**: 904 lines (adapter.py), 446 lines (tests), 23 tests passing
- **Features complete**:
  - Repository overview (branches, tags, commits)
  - Ref exploration (branches, tags, commits)
  - File at ref (time-travel)
  - File history (commits that touched a file)
  - File blame (progressive disclosure: summary → detailed → semantic)
  - Output Contract v1.0 compliant (5 output types)
- **Session**: hyper-asteroid-0117 (2026-01-17)

**Why Tier 1**:
- **Code history is fundamental to understanding** (when/who/why)
- Every project uses git
- AI agents asking "why does this code exist?" need this
- Foundation already existed (`diff://git://HEAD/...` works)

**Mission alignment**: ✅ **STRONGLY ALIGNED**
- Reveals code evolution (pure inspection)
- Token-efficient (structure at different points in time)
- Helps understand "why" not just "what"

**Complexity:** Medium - git object model, refs, blame integration (Successfully implemented)

---

## Platform Vision (Future Directions)

> **Note**: These are longer-term strategic directions, not near-term roadmap items

### Editor Integrations (Without Becoming an IDE)
- Quick "Reveal Outline" command in editors
- Jump-to-symbol based on reveal output
- Mini "map" panel (terminal/editor)
- **Philosophy**: Reveal as engine, editors as UI

### PR Bots / Review Assistants
- Comment on PRs: summary of changed symbols, new API surface, risky changes
- **Sweet spot**: Lightweight structure-aware automation

### Onboarding Generators
- Auto-generate "first day guide": entry points, key modules, APIs, data models
- **No AI required**: Just rules + repo heuristics

### Repository Health Dashboards
- Complexity distribution, largest modules, dependency tangles
- **Audience**: Tech leads, maintainers

**Status**: Not on roadmap, documented for strategic context

---

## High-Leverage Future Features (Post-v1.0)

> **Note**: Not prioritized yet, documented for strategic evaluation

### Relationship Queries (Call Graphs)
```bash
reveal calls://src/api.py:handle_request  # Who calls this?
reveal imports://src/utils.py             # Where is this imported?
reveal depends://src/module/              # What depends on this?
```
**Why high-leverage**: Structure tells you what exists; relationships tell you what matters.

### Opinionated Views (Intent-Based Commands)
```bash
reveal overview              # Auto-generated repo summary
reveal entrypoints           # Find main(), __init__, index.js
reveal api-surface           # Public API inventory
reveal hotspots             # Complexity/quality issues
reveal onboarding           # First-day guide
```
**Why high-leverage**: Strong tools encode *questions*, not mechanics.

### Context Packs (Budgeted Context)
```bash
reveal pack ./src --budget 500-lines     # Curated context: tree + outlines + key symbols
reveal pack ./api --budget 2000-tokens   # For LLM consumption
```
**Why high-leverage**: Formalizes "give me enough context but not too much."

### Git-Aware Defaults
```bash
reveal .                    # In repo: defaults to changed files on current branch
reveal --since HEAD~3       # Changes since commit
reveal --pr                 # PR context auto-detection
```
**Why high-leverage**: Makes tool instantly relevant to daily workflows.

**Status**: Strategic backlog, evaluate after v1.0 and ecosystem features ship.

---

## Developer Experience & Ecosystem - **NEW CATEGORY (2026-01-15)**

> **Source**: External feedback analysis (research/TLDR_FEEDBACK_ANALYSIS.md)
> **Theme**: Consistency, contributor experience, and ecosystem enablement

### Output Contract Specification - **TIER 1** ✅ **COMPLETE**

**Status**: ✅ **COMPLETE** (2026-01-17)
- **Documentation**: docs/OUTPUT_CONTRACT.md (523 lines, v1.0 specification)
- **Implementation**: All 13 adapters migrated to v1.0 contract
- **Required fields**: contract_version, type, source, source_type
- **Session**: astral-pulsar-0117 (11 adapters), hyper-asteroid-0117 (git:// adapter)

**What was implemented**:
```python
# Output Contract v1.0 - ALL adapters now return:
{
  "contract_version": "1.0",  # Semantic version
  "type": "snake_case",       # Output type (e.g., "ast_query", "mysql_server")
  "source": str,              # Data source identifier
  "source_type": str,         # Category: file|directory|database|runtime|network
  # ... adapter-specific fields
}
```

**Migrated adapters (13/13 = 100%)**:
- env://, python://, reveal://, ast://, diff://, imports://, markdown://, json://, sqlite://, mysql://, stats://, help://, git://

**Impact**:
- ✅ All adapters have predictable JSON schemas
- ✅ AI agents can parse output reliably
- ✅ Plugin ecosystem unblocked (contributors have clear contract)
- ✅ Versioning enables future evolution without breaking changes

**Why Tier 1**:
- **Blocked plugin ecosystem** - Contributors need predictable contracts
- **Agent-critical** - AI tools depend on stable JSON
- **Prevents drift** - 44 plugins need shared standard

---

### Stability Taxonomy - **TIER 1** ✅ **COMPLETE**

**Status**: ✅ **COMPLETE** (2026-01-17)
- **Documentation**: STABILITY.md (246 lines, comprehensive policy)
- **Session**: mysterious-rocket-0117

**What was implemented**:
- 🟢 **Stable**: Core modes (directory/file/element), basic CLI, 5 core adapters (help://, env://, ast://, python://, reveal://)
- 🟡 **Beta**: 8 adapters (diff://, imports://, sqlite://, mysql://, stats://, json://, markdown://, git://), extended rules, config system
- 🔴 **Experimental**: Undocumented features, internal V-rules, tree-sitter-only languages

**Stability commitments**:
- Stable features: API frozen, breaking changes require major version bump (v1.0 → v2.0)
- Beta features: Feature-complete, API may evolve with migration guidance in CHANGELOG
- Experimental: No guarantees, may change or be removed without notice

**Path to v1.0** (Q2 2026):
1. ✅ Output contract specification (COMPLETE)
2. ✅ JSON schema versioning (COMPLETE via Output Contract)
3. 🟡 Comprehensive integration test suite (in progress)
4. 🟡 Documentation completeness (most adapters have help:// guides)
5. ⏳ 6 months without breaking changes to Stable features (started 2026-01-17)

**Impact**:
- ✅ Users know what's safe to depend on
- ✅ AI agents can trust Stable features won't break
- ✅ Clear upgrade path to v1.0
- ✅ Reduces support burden (expectations are explicit)

**Why Tier 1**:
- **Trust signal** - Users know what's safe
- **Low effort** - Just labeling, no code
- **High impact** - Reduces support burden, enables confidence

---

### Workflow Recipes - **TIER 0 → COMPLETE** ✅

**Status:** ✅ **SHIPPED** (pulsing-horizon-0115)
**Location:** `external-git/WORKFLOW_RECIPES.md`

**What was built**:
- 8 workflows (574 lines): code review, onboarding, debugging, refactoring, documentation, AI agents, databases, pipelines
- Task-based organization (users find by "what I want to do")
- Consolidates proven patterns from COOL_TRICKS.md and AGENT_HELP.md
- Real commands for real use cases
- Quick reference section for discovery

**Why this succeeded**:
- Content already existed (just needed reorganization)
- Task-based organization is natural for users and LLMs
- No code changes required
- Immediate value to contributors and users

**Completed as part of**: Tier 0 documentation consolidation (pulsing-horizon-0115)

---

### File Filtering (--exclude flag) - ✅ **ALREADY EXISTS**

**Status**: ✅ **FEATURE ALREADY IMPLEMENTED AND WORKING**

**Discovered**: astral-pulsar-0117 - User requested this thinking it didn't exist, but it's fully implemented!

**Current usage**:
```bash
reveal ~/.peyton --exclude "*.exe" --exclude "*.db" --exclude "__pycache__"
reveal src/ --exclude "node_modules" --exclude "dist" --exclude "*.pyc"
```

**Implementation details**:
- CLI argument: `parser.py` line 190-191 (`action='append'` for multiple patterns)
- Routing: `routing.py` line 334 passes `args.exclude` to tree view
- Filtering: `display/filtering.py` PathFilter class handles pattern matching
- Supports wildcards (`*.exe`) and exact matches (`__pycache__`)
- Already documented in `reveal --help`

**Next steps (documentation/discoverability)**:
1. **Update WORKFLOW_RECIPES.md** - Add filtering examples to exploration workflows
2. **Update README.md** - Mention --exclude in "Real-world usage" section
3. **Future enhancement**: .revealignore file (like .gitignore, auto-loaded from project root)

**Why users miss this**:
- Feature exists but may not be prominent enough in docs
- User had older version (v0.32.0), may predate this feature
- Grep workaround is common Unix pattern, users default to it

**Mission alignment**: ✅ **STRONGLY ALIGNED** (already shipped)
- Improves token efficiency (reduces noise in output)
- Makes Reveal usable on production directories
- Fits progressive disclosure pattern (filter → explore → detail)

**Action item**: Improve documentation and discoverability (Tier 1 documentation task)

**Source**: User feedback (astral-pulsar-0117) - discovered existing feature through investigation

---

### Plugin Linter + Scaffolding - **TIER 2**

**Problem**: No automated validation or scaffolding for contributors. Creating an analyzer requires understanding boilerplate.

**Proposed tools**:
```bash
# Scaffolding
reveal dev new-analyzer --name kotlin --icon 🔷
# Creates: analyzer, tests, fixtures, boilerplate

# Linting
reveal --lint-plugin reveal/analyzers/kotlin.py
# Checks:
#   ✅ Schema compliance (output contract)
#   ✅ Deterministic output
#   ✅ Performance budget (<100ms)
#   ✅ Help documentation exists
#   ✅ 3+ test fixtures present
```

**Why Tier 2** (not Tier 1):
- **Depends on**: Output contract must exist first
- **Higher effort**: 3-4 sessions implementation
- **But high impact**: 10x contributor experience

**Implementation**:
1. Create `reveal dev` command namespace
2. Implement scaffolding generator
3. Create V017-V020: Plugin validation rules
4. Add linter to CONTRIBUTING.md
5. Enforce in CI

**Complexity**: Medium-High (3-4 sessions)
**Impact**: High (ecosystem)
**Status**: Ready to start (unblocked 2026-01-17)
**Was blocked by**: Output contract specification ✅ (now complete)

---

## Tier 2: Medium Value, Next Quarter

### claude:// Adapter (Conversation Analysis) - **TIER 2**

```bash
reveal claude://session/infernal-earth-0118           # Session overview
reveal claude://session/current/thinking               # Extract thinking
reveal claude://session/current?tools=Bash             # Tool filtering
reveal claude://session/current --check                # Quality checks
```

**Why Tier 2:**
- **Ecosystem reach**: ⭐⭐⭐⭐ All Claude Code users, TIA users
- **Token efficiency**: ⭐⭐⭐⭐⭐ Progressive disclosure vs reading full JSONL
- **AI-agent fit**: ⭐⭐⭐⭐⭐ Meta-circular: AI inspecting AI work
- **Implementation effort**: 32-48 hours (5-7 days) - Medium-High

**Mission alignment:** ✅ **STRONGLY ALIGNED**
- Reveals conversation structure (pure inspection)
- Token-efficient (overview → details → specifics)
- Helps understand "what did my AI agent do?"

**Features:**
- Progressive disclosure (overview → analytics → filtered → specific messages)
- Tool usage analytics and filtering
- Token usage estimates and optimization insights
- Error detection with context
- Thinking block extraction and analysis
- File operation tracking
- Quality rules (CQ001-CQ007): Excessive retries, token bloat, file churn

**Implementation phases:**
- ✅ Phase 1 (v0.38): Core adapter, session overview (8-12 hours) - COMPLETE
- ✅ Phase 2 (v0.38): Analytics & queries (6-10 hours) - COMPLETE
  - Tool success rate calculation
  - Timeline view (5 event types)
  - 50 tests, 100% coverage
- Phase 3 (v0.39): Quality rules (8-12 hours) - PENDING
- Phase 4 (v0.40): Cross-session analysis (6-8 hours) - PENDING
- Phase 5 (v0.41): Polish & launch (4-6 hours) - PENDING

**Complexity:** Medium-High (5 phases, new rule category)
**Status:** Phase 1 + Phase 2 complete (v0.38.0), ready for Phase 3
**Sessions:** infernal-earth-0118 (design), blazing-cyclone-0118 (integration), fluorescent-prism-0118 (doc updates), infernal-grove-0118 (Phase 1), drizzling-lightning-0118 (Phase 2)

---

### ✅ File Format Coverage Gaps - **COMPLETE**

**Status**: ✅ **ALL COMPLETE** - All 5 formats implemented and working

#### Implemented Formats

**1. ✅ CSV/TSV (Tabular Data)**
```bash
reveal data.csv
# Output: Schema with column types, unique counts, sample values
```
- Schema shows column names, inferred types (string/integer/float/boolean)
- Shows missing value percentages and unique counts
- Sample values for quick data preview

**2. ✅ XML (Config + API)**
```bash
reveal config.xml
# Output: Tree structure with elements, attributes, namespaces
```
- Shows root element and child hierarchy
- Displays attributes and text content
- Namespace awareness

**3. ✅ INI/Properties (Config Files)**
```bash
reveal app.ini
# Output: Sections with key counts
```
- Shows section names
- Works with standard INI format

**4. ✅ Windows Batch (.bat, .cmd)**
```bash
reveal build.bat
# Output: Labels (:setup, :build) as functions
```
- Extracts labels as function-like elements
- Shows line counts

**5. ✅ PowerShell (.ps1)**
```bash
reveal deploy.ps1
# Output: Functions with parameters
```
- Extracts function definitions
- Shows function structure

**Validated**: 2026-01-19 (lingering-tide-0119 session)

---

### ✅ GraphQL + Protobuf Support (COMPLETED v0.34.0)

**Status:** ✅ **BASIC SUPPORT SHIPPED**
- GraphQL (.graphql, .gql) via tree-sitter
- Protobuf (.proto) via tree-sitter
- Structure extraction works
- Future: Custom analyzers for type→resolver and message→service mapping

**Why:** GraphQL is standard for APIs. Protobuf is standard for gRPC. Tree-sitter extraction provides basic support.

### Kubernetes YAML Intelligence

```bash
reveal k8s/deployment.yaml                 # Resources, containers, volumes
reveal k8s/ --check                        # K8s best practices, common mistakes
```

**Why:** K8s is standard for deployment. YAML support exists but K8s-specific intelligence adds value.

---

### Infrastructure Adapters (SSL/Nginx) - **TIER 2/3**

> **Source**: Real-world ops debugging on sociamonials gateway (2026-01-20)
> **Document**: sociamonials-ops/docs/REVEAL_NGINX_SSL_OPPORTUNITIES.md

**Context**: Diagnosing white-label SSL failures required manual openssl commands and nginx grep patterns. Would have saved 30+ minutes with proper adapters.

#### ssl:// Adapter - ✅ **COMPLETE** (v0.41.0 + v0.43.0)

**Status**: ✅ **SHIPPED**
- v0.41.0: Core adapter (cert inspection, health checks)
- v0.43.0: Nginx integration, @file batch, filter flags

```bash
reveal ssl://example.com                 # Certificate overview
reveal ssl://example.com --check         # Health check (expiry, chain, hostname)
reveal ssl://example.com/san             # Subject Alternative Names
reveal ssl://nginx:///etc/nginx/*.conf   # Extract SSL domains from nginx
reveal ssl://nginx:///etc/nginx/*.conf --check --only-failures  # Audit with filters
reveal @domains.txt --check              # Batch from file
```

**Features implemented**:
- Certificate inspection (issuer, expiry, SANs, chain)
- Health checks with exit codes (0=pass, 1=warning, 2=critical)
- `ssl://nginx:///` - Extract domains from nginx config
- `@file` syntax - Read URIs from file
- `--only-failures`, `--summary`, `--expiring-within` filters
- 35 tests, comprehensive documentation

**Sessions**: kojaye-0120 (impl), nebular-expedition-0120 (tests/docs), foggy-cloud-0121 (release)

#### nginx:// Adapter - **TIER 3** (Medium Value, Medium Effort)

```bash
reveal nginx:///etc/nginx/conf.d/users/file.conf  # Server block overview
reveal nginx:// --query "location=acme-challenge" # Query specific location types
reveal nginx:// --domain social.weffix.com        # Show specific server block
reveal nginx:// --health                          # Scan for path mismatches
```

**Mission alignment**: ✅ ALIGNED (but specialized)
- Reveals nginx config structure (pure inspection)
- Token-efficient (structured view vs grep noise)
- Helps understand "how is nginx configured?"

**Implementation**: Regex-based parser (tree-sitter has nginx grammar but complex)
**Effort**: Medium (16-24 hours) - nginx syntax is well-defined but complex
**Ecosystem reach**: Medium (ops teams, nginx debugging)
**Note**: Reveal already has nginx *analyzer* - adapter would add structured querying

#### cpanel:// Adapter - **EXPLICITLY DEPRIORITIZED**

**Why deprioritized**:
- Very niche (cPanel-specific hosting environments)
- Low ecosystem reach
- YAML parsing exists, users can read files directly

---

## Tier 3: Lower Priority / Speculative

| Feature | Why Lower |
|---------|-----------|
| PostgreSQL adapter | mysql:// proves pattern, diminishing returns |
| Docker adapter | `docker inspect` already exists |
| Image metadata | Niche use case (asset pipelines) |
| --watch mode | Nice UX but not core to AI workflows |
| LSP integration | Big effort, IDEs have good tools |
| **Makefile analyzer** | Complex syntax (many variants), CMake more common now, declining ecosystem |
| **reStructuredText (.rst)** | Niche (Python/Sphinx docs only), Markdown dominates |
| **AsciiDoc (.adoc)** | Niche (technical docs), less common than Markdown |
| **LaTeX (.tex)** | Very specialized (academia), high complexity (8+ hours), low general reach |

---

## Explicitly Killed

These were in the old roadmap but provide unclear value or violate mission:

| Feature | Why Killed |
|---------|------------|
| `--fix` auto-fix | **Mission violation** - Reveal reveals, doesn't modify. Use Ruff/Black. |
| `query://` "SQL-like cross-resource queries" | Vague, undefined problem |
| `semantic://` embedding search | Requires ML infrastructure, over-engineered |
| `trace://` execution traces | Wrong domain (debugging tools) |
| `live://` real-time monitoring | Wrong domain (observability tools) |
| `merge://` composite views | Unclear use case |
| `--check-metadata` | Duplicates schema validation |
| `--watch` mode | Convenience feature, not core. Use Unix `watch reveal file.py` |
| Knowledge graph docs | TIA-specific, not general value |
| **Parquet/Arrow analyzers** | **Mission violation** - Binary formats, not human-readable. Use pandas/pyarrow. |
| **Windows Registry (.reg)** | Too specialized, registry editing tools handle this |
| **.env file analyzer** | Redundant - env:// adapter inspects environment. .env is just key=value (INI covers this). |
| `cpanel://` adapter | Too niche (cPanel-specific hosting). YAML parsing exists, users can read files directly. |

---

## Language Support Status

**Current**: 31 built-in analyzers + 165+ via tree-sitter fallback
**Planned (Tier 2)**: +5 analyzers (CSV, XML, INI/Properties, .bat, .ps1) → 36 total

### Programming Languages (20)

**Tier 1 (production-ready custom analyzers)**:
- Python, JavaScript, TypeScript, Rust, Go, Java, C, C++

**Tier 2 (tree-sitter with custom extraction)**:
- C#, Scala, PHP, Ruby, Lua, GDScript, Bash, SQL
- Kotlin, Swift, Dart (mobile platforms - v0.33.0)
- Zig (systems programming - v0.34.0)

### Infrastructure & API (3)
- **HCL/Terraform** - Infrastructure-as-code (.tf, .tfvars, .hcl)
- **GraphQL** - API schema and queries (.graphql, .gql)
- **Protocol Buffers** - gRPC serialization (.proto)

### Config/Data Formats (8 → 13 planned)

**Current**:
- Nginx, Dockerfile, TOML, YAML, JSON, JSONL, Markdown, HTML
- ✅ **CSV/TSV** - Tabular data (data pipelines, ML, exports)
- ✅ **XML** - Enterprise configs (Maven, Gradle, Spring, Android)
- ✅ **INI/Properties** - Config files (Windows, Java, Python)
- ✅ **Windows Batch (.bat, .cmd)** - Windows CI/CD, game engines
- ✅ **PowerShell (.ps1)** - Modern Windows automation, Azure DevOps

### Office Formats (4)
- Excel (.xlsx), Word (.docx), PowerPoint (.pptx), LibreOffice (ODF)

### Tree-Sitter Fallback (165+)
Additional languages get basic structure extraction via tree-sitter-language-pack:
Perl, R, Haskell, Elixir, OCaml, and 160+ more. Structure-only (no custom logic).

---

## Adapter Status

### Implemented (16)

All adapters are Output Contract v1.0 compliant (100% coverage).

| Adapter | Purpose | Stability |
|---------|---------|-----------|
| `help://` | Documentation discovery | 🟢 Stable |
| `env://` | Environment variables | 🟢 Stable |
| `ast://` | Semantic code queries | 🟢 Stable |
| `python://` | Python runtime inspection | 🟢 Stable |
| `reveal://` | Self-inspection | 🟢 Stable |
| `json://` | JSON navigation | 🟡 Beta |
| `stats://` | Code quality metrics | 🟡 Beta |
| `mysql://` | MySQL schema exploration | 🟡 Beta |
| `sqlite://` | SQLite database exploration | 🟡 Beta |
| `imports://` | Dependency analysis | 🟡 Beta |
| `diff://` | Structural comparison | 🟡 Beta |
| `markdown://` | Frontmatter queries | 🟡 Beta |
| `git://` | Git repository inspection (history, blame, time-travel) | 🟡 Beta |
| `claude://` | Claude Code session analysis (tools, thinking, timeline) | 🟡 Beta |
| `ssl://` | SSL certificate inspection (nginx integration, batch) | 🟡 Beta |
| `domain://` | Domain registration, DNS records, health status | 🟡 Beta |

**Recent additions**:
- `domain://` (2026-01-21) - Domain registration, DNS inspection, health checks
- `ssl://` (2026-01-21) - Certificate inspection, nginx integration, batch filters
- `claude://` (2026-01-18) - Session overview, tool analytics, thinking extraction
- `git://` (2026-01-17) - Repository overview, history, blame with progressive disclosure

### Planned
| Adapter | Priority | Status |
|---------|----------|--------|
| `nginx://` | Tier 3 | Structured nginx config querying (medium effort) |

### Explicitly Deprioritized
| Adapter | Why Deprioritized |
|---------|-------------------|
| `architecture://` | Complex, unclear ROI vs effort. Use `imports://` + `stats://` instead |
| `calls://` | Dead code detection requires full call graph analysis. Deferred post-v1.0 |
| `cpanel://` | Too niche (cPanel-specific). YAML parsing exists, users can read files directly |

---

## Quality Rules Status

**42 rules** across 12 categories: B (bugs), S (security), C (complexity), E (style), L (links), I (imports), M (maintainability), D (duplicates), N (nginx), V (validation), F (frontmatter), U (urls), R (refactoring)

**After claude:// adapter implementation:** 49 rules across 13 categories (adds CQ - conversation quality: CQ001-CQ007)

**Recent additions:**
- **I004** (v0.32.1) - Detects Python files shadowing stdlib modules (e.g., `logging.py`, `json.py`)

### Ruff Alignment
Reveal complements Ruff, doesn't replace it. Aligned rules: E501, C901, I001 (F401), R913.

### Reveal-Unique Value
Rules Ruff doesn't have: I002 (circular deps), L001-L003 (link validation), M101-M103 (file size limits for AI), D001-D002 (duplicates).

---

## Success Metrics

**How we know Reveal is working:**

1. **Token efficiency** - Measured reduction vs reading raw files
2. **Coverage** - % of popular repos where reveal works out-of-box
3. **Adoption** - Usage in Claude Code, TIA, other AI tools
4. **Rule quality** - Real bugs found in production code (tested on Django, Flask, FastAPI, Requests)

---

## What We Don't Do

Reveal is not:
- A linter (use Ruff, ESLint)
- A formatter (use Black, Prettier)
- A type checker (use mypy, tsc)
- An IDE (use VS Code, JetBrains)
- A debugger (use pdb, lldb)

Reveal is: **A structure-first exploration tool optimized for AI agents.**
