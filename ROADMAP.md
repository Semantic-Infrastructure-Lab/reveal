# Reveal Roadmap
> **Last updated**: 2026-02-08 (Phase 3 complete, coverage data corrected)

This document outlines reveal's development priorities and future direction. For contribution opportunities, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What We've Shipped

### v0.46.0
- ✅ **Phase 6: Help Introspection** — Machine-readable adapter schemas for all 15 adapters
- ✅ **Phase 7: Output Contract v1.1** — Trust metadata (parse_mode, confidence, warnings, errors)
- ✅ **help://schemas/<adapter>** — JSON schemas for AI agent auto-discovery
- ✅ **help://examples/<task>** — Canonical query recipes for common tasks

### v0.45.0
- ✅ **Phase 1: Universal Operation Flags** — `--advanced`, `--only-failures` across all adapters
- ✅ **Phase 2: Stdin Batch Processing** — Universal `--batch` flag with result aggregation
- ✅ **Batch mode** — Works with any adapter, mixed adapter batches supported
- ✅ **Format consistency** — All 16 adapters support `--format json|text`

### v0.44.2
- ✅ **SSL certificate parsing fix** — TLS 1.3 connections properly handled (cryptography dependency)
- ✅ **52 SSL tests passing** — Comprehensive test coverage

### v0.44.1
- ✅ **Batch SSL filter flags** — `--only-failures`, `--summary`, `--expiring-within` work with `--stdin --check`
- ✅ **Issue #19 resolved** — Composable SSL batch checks fully functional

### v0.44.0
- ✅ **`--extract` flag** — Extract structured data for composable pipelines
- ✅ **domain:// adapter** — Domain registration, DNS records, health status inspection

### v0.43.0
- ✅ **`@file` batch syntax** — Read targets from a file (`reveal @domains.txt --check`)
- ✅ **`ssl://nginx:///` integration** — Extract and check SSL domains from nginx configs
- ✅ **Batch SSL filters** — `--only-failures`, `--summary`, `--expiring-within N`
- ✅ **Validation rule fixes** — V004/V007/V011 skip non-dev installs (no false positives)

### v0.42.0
- ✅ **Universal `--stdin` URI support** — Batch processing works with any URI scheme (ssl://, claude://, env://)
- ✅ **Query parsing utilities** — New `reveal/utils/query.py` for adapter authors
- ✅ **SSL batch workflows** — Check multiple certificates via stdin pipeline
- ✅ **Nginx+SSL integration docs** — Comprehensive AGENT_HELP.md coverage

### v0.41.0
- ✅ **`ssl://` adapter** — SSL/TLS certificate inspection (zero dependencies)
- ✅ **N004 rule** — ACME challenge path inconsistency detection
- ✅ **Content-based nginx detection** — `.conf` files detected by content, not path
- ✅ **Enhanced nginx display** — Server ports `[443 (SSL)]`, location targets

### v0.40.0
- ✅ **`--dir-limit` flag** — Per-directory entry limit (solves node_modules problem)
- ✅ **`--adapters` flag** — List all URI adapters with descriptions
- ✅ **M104 rule** — Hardcoded list detection for maintainability
- ✅ **ROADMAP.md** — Public roadmap for contributors
- ✅ **Breadcrumb improvements** — Extraction hints for 25+ file types

### v0.33 - v0.39

#### Language Support
- ✅ **Kotlin, Swift, Dart** — Mobile development platforms
- ✅ **Zig** — Systems programming
- ✅ **Terraform/HCL** — Infrastructure-as-code
- ✅ **GraphQL** — API schemas
- ✅ **Protocol Buffers** — gRPC serialization
- ✅ **CSV/Excel** — Tabular data analysis

#### Adapters
- ✅ **sqlite://** — SQLite database inspection
- ✅ **git://** — Repository history and blame analysis
- ✅ **imports://** — Dependency analysis with circular detection

#### Quality & Developer Experience
- ✅ **Output Contract** — Stable, documented output formats
- ✅ **Stability Taxonomy** — Clear API stability guarantees
- ✅ **Workflow Recipes** — Common usage patterns documented

---

## Current Focus: Path to v1.0

### Test Coverage & Quality
- Overall coverage: 75% (2911 tests passing)
- Database adapter status: MySQL 54%, SQLite 96% ✅
- Target: 80%+ coverage for core adapters

### UX Consistency (Phases 3-5)
- **Phase 3**: Query operator standardization ✅ **COMPLETE**
  - Universal operators across all 5 query-capable adapters
  - Sort/limit/offset result control unified
  - Documentation: QUERY_SYNTAX_GUIDE.md created
  - Completed: 2026-02-08 (Sessions: hosuki-0208, gentle-cyclone-0208)
- **Phase 4**: Field selection + budget awareness (next)
  - `--select=fields` for token reduction
  - Budget-aware flags for AI agent loops
  - Estimated: ~12 hours
- **Phase 5**: Element discovery
  - Auto-show available elements in adapter output
  - Estimated: ~6 hours

### Stability & Polish
- Output contract v1.1 enforcement
- Performance optimization for large codebases

---

## Post-v1.0 Features

> **Status**: Strategic backlog. Not prioritized for implementation yet.

### Relationship Queries (Call Graphs)
```bash
reveal calls://src/api.py:handle_request  # Who calls this?
reveal depends://src/module/              # What depends on this?
```
**Why valuable**: Structure tells you what exists; relationships tell you what *matters*.

**Current limitation**: Requires cross-file static analysis. Tree-sitter infrastructure is ready, but call resolution is non-trivial.

### Intent-Based Commands
```bash
reveal overview              # Auto-generated repo summary
reveal entrypoints           # Find main(), __init__, index.js
reveal hotspots              # Complexity/quality issues
reveal onboarding            # First-day guide
```
**Why valuable**: Strong tools encode *questions*, not mechanics.

### Context Packs (Budgeted Context)
```bash
reveal pack ./src --budget 500-lines     # Curated context
reveal pack ./api --budget 2000-tokens   # For LLM consumption
```
**Why valuable**: Formalizes "give me enough context but not too much."

### Git-Aware Defaults
```bash
reveal .                    # Defaults to changed files on branch
reveal --since HEAD~3       # Changes since commit
reveal --pr                 # PR context auto-detection
```
**Why valuable**: Makes tool instantly relevant to daily workflows.

---

## Lower Priority / Speculative

| Feature | Notes |
|---------|-------|
| PostgreSQL adapter | mysql:// proves pattern; diminishing returns |
| Docker adapter | `docker inspect` already exists |
| LSP integration | Big effort; IDEs have good tools |
| --watch mode | Nice UX but not core; use `watch reveal file.py` |

---

## Explicitly Not Planned

These violate reveal's mission ("reveal reveals, doesn't modify") or have unclear value:

| Feature | Why Not |
|---------|---------|
| `--fix` auto-fix | Mission violation. Use Ruff/Black for formatting/fixes. |
| `semantic://` embedding search | Requires ML infrastructure; over-engineered |
| `trace://` execution traces | Wrong domain (debugging tools) |
| `live://` real-time monitoring | Wrong domain (observability tools) |
| Parquet/Arrow | Binary formats, not human-readable. Use pandas. |

---

## Language Support Status

**Current**: 31 built-in analyzers + 165+ via tree-sitter fallback

### Production-Ready
Python, JavaScript, TypeScript, Rust, Go, Java, C, C++, C#, Ruby, PHP, Kotlin, Swift, Dart, Zig, Scala, Lua, GDScript, Bash, SQL

### Config & Data
Nginx, Dockerfile, TOML, YAML, JSON, JSONL, Markdown, HTML, CSV, XML, INI, HCL/Terraform, GraphQL, Protobuf

### Office Formats
Excel (.xlsx), Word (.docx), PowerPoint (.pptx), LibreOffice (ODF)

### Tree-Sitter Fallback
165+ additional languages with basic structure extraction: Perl, R, Haskell, Elixir, OCaml, and more.

---

## Adapter Status

### Implemented (16)
| Adapter | Description |
|---------|-------------|
| `ast://` | Query code as database (complexity, size, type filters) |
| `claude://` | Claude conversation analysis |
| `diff://` | Compare files or git revisions |
| `domain://` | Domain registration, DNS records, health status |
| `env://` | Environment variable inspection |
| `git://` | Repository history, blame, commits |
| `help://` | Built-in documentation |
| `imports://` | Dependency analysis, circular detection |
| `json://` | JSON/JSONL deep inspection |
| `mysql://` | MySQL database schema inspection |
| `python://` | Python runtime inspection |
| `reveal://` | Reveal's own codebase |
| `sqlite://` | SQLite database inspection |
| `ssl://` | SSL/TLS certificate inspection |
| `stats://` | Codebase statistics |

### Planned
| Adapter | Notes |
|---------|-------|
| `nginx://` | Nginx config structured querying (Tier 3) |
| `calls://` | Call graph analysis (post-v1.0) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules.

**Good first contributions:**
- Language analyzer improvements
- Pattern detection rules
- Documentation and examples
