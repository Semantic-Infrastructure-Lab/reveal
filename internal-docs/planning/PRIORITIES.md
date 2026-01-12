# Reveal Priorities

> **Mission:** Make AI coding assistants (Claude Code, TIA, Copilot) more effective by providing maximum understanding per token across popular tech stacks.

**Last Updated:** 2026-01-11
**Current Version:** v0.34.0 (+ unreleased: sqlite://)

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

### v0.35.0 (Unreleased)
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

## Priority Framework

**Score each feature on:**
1. **Token efficiency** - Does it reduce tokens needed to understand code?
2. **Ecosystem reach** - How many developers/projects use this?
3. **Implementation effort** - Can we ship it quickly?
4. **AI-agent fit** - Does it help automated coding workflows?

---

## Tier 1: High Value, Ship Soon

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

**Status:** ✅ **SHIPPED** (v0.35.0 unreleased)
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

### Auto-Fix for Rules

```bash
reveal src/ --check --fix                  # Fix what can be fixed
reveal src/ --check --fix --select I001    # Fix unused imports only
```

**Why:** Currently Reveal is diagnostic-only. Auto-fix makes it actionable. Start with safe fixes:
- I001: Remove unused imports
- E501: Line wrapping (with formatter integration)

---

## Tier 2: Medium Value, Next Quarter

### git:// Adapter (History/Blame)

```bash
reveal git://HEAD~5/src/auth.py            # File 5 commits ago
reveal git://main..feature/               # What changed in branch
reveal git://blame/src/auth.py:42          # Who wrote line 42, why
```

**Why:** Understanding code evolution is crucial for debugging and refactoring. Every project uses git.

**Complexity:** Medium - need to handle git object model, refs, ranges.

### GraphQL Schema Support

```bash
reveal schema.graphql                      # Types, queries, mutations
reveal schema.graphql User                 # Specific type
reveal schema.graphql --check              # Schema best practices
```

**Why:** GraphQL is standard for APIs. AI agents encounter it constantly in web projects.

### Protobuf Support

```bash
reveal api.proto                           # Messages, services, enums
reveal api.proto UserService               # Specific service
```

**Why:** gRPC is dominant for microservices. Proto files define contracts.

### Kubernetes YAML Intelligence

```bash
reveal k8s/deployment.yaml                 # Resources, containers, volumes
reveal k8s/ --check                        # K8s best practices, common mistakes
```

**Why:** K8s is standard for deployment. YAML support exists but K8s-specific intelligence adds value.

---

## Tier 3: Lower Priority / Speculative

| Feature | Why Lower |
|---------|-----------|
| PostgreSQL adapter | mysql:// proves pattern, diminishing returns |
| Docker adapter | `docker inspect` already exists |
| Image metadata | Niche use case (asset pipelines) |
| --watch mode | Nice UX but not core to AI workflows |
| LSP integration | Big effort, IDEs have good tools |

---

## Explicitly Killed

These were in the old roadmap but provide unclear value:

| Feature | Why Killed |
|---------|------------|
| `query://` "SQL-like cross-resource queries" | Vague, undefined problem |
| `semantic://` embedding search | Requires ML infrastructure, over-engineered |
| `trace://` execution traces | Wrong domain (debugging tools) |
| `live://` real-time monitoring | Wrong domain (observability tools) |
| `merge://` composite views | Unclear use case |
| `--check-metadata` | Duplicates schema validation |
| Knowledge graph docs | TIA-specific, not general value |

---

## Language Support Status

### Fully Supported (16)
Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Scala, PHP, Ruby, Lua, GDScript, Bash, SQL

### Supported via tree-sitter (not exposed)
Kotlin, Swift, Dart, Elixir, Haskell, OCaml, Zig

### Config/Data Formats
Nginx, Dockerfile, TOML, YAML, JSON, JSONL, Markdown, HTML

### Office Formats
Excel, Word, PowerPoint, LibreOffice (ODF)

---

## Adapter Status

### Implemented (11)
| Adapter | Purpose |
|---------|---------|
| `help://` | Documentation discovery |
| `env://` | Environment variables |
| `ast://` | Semantic code queries |
| `json://` | JSON navigation |
| `python://` | Python runtime inspection |
| `reveal://` | Self-inspection |
| `stats://` | Code quality metrics |
| `mysql://` | MySQL schema exploration |
| `imports://` | Dependency analysis |
| `diff://` | Structural comparison |
| `markdown://` | Frontmatter queries |

### Planned
| Adapter | Priority | Status |
|---------|----------|--------|
| `sqlite://` | Tier 1 | Not started |
| `git://` | Tier 2 | Partial (git refs work via `diff://git://HEAD/...`) |

### Explicitly Deprioritized
| Adapter | Why Deprioritized |
|---------|-------------------|
| `architecture://` | Complex, unclear ROI vs effort. Use `imports://` + `stats://` instead |
| `calls://` | Dead code detection requires full call graph analysis. Deferred post-v1.0 |

---

## Quality Rules Status

**42 rules** across categories: B (bugs), S (security), C (complexity), E (style), L (links), I (imports), M (maintainability), D (duplicates), N (nginx), V (validation), F (frontmatter), U (urls), R (refactoring)

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
