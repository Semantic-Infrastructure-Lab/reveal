# Reveal Roadmap

> **Last updated**: 2026-01-20
> **Current version**: v0.35.x

This document outlines reveal's development priorities and future direction. For contribution opportunities, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Recently Shipped (v0.33 - v0.35)

### Language Support
- ✅ **Kotlin, Swift, Dart** — Mobile development platforms
- ✅ **Zig** — Systems programming
- ✅ **Terraform/HCL** — Infrastructure-as-code
- ✅ **GraphQL** — API schemas
- ✅ **Protocol Buffers** — gRPC serialization
- ✅ **CSV/Excel** — Tabular data analysis

### Adapters
- ✅ **sqlite://** — SQLite database inspection
- ✅ **git://** — Repository history and blame analysis
- ✅ **imports://** — Dependency analysis with circular detection

### Quality & Developer Experience
- ✅ **Output Contract** — Stable, documented output formats
- ✅ **Stability Taxonomy** — Clear API stability guarantees
- ✅ **Workflow Recipes** — Common usage patterns documented

---

## Current Focus: Path to v1.0

### Documentation Consolidation
- Unified help system across all adapters
- Consistent examples and workflows
- Agent-optimized documentation (`--agent-help`)

### Stability & Polish
- Output contract enforcement
- Test coverage improvements
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

### Implemented (14)
| Adapter | Description |
|---------|-------------|
| `ast://` | Query code as database (complexity, size, type filters) |
| `diff://` | Compare files or git revisions |
| `env://` | Environment variable inspection |
| `git://` | Repository history, blame, commits |
| `help://` | Built-in documentation |
| `imports://` | Dependency analysis, circular detection |
| `json://` | JSON/JSONL deep inspection |
| `mysql://` | MySQL database schema inspection |
| `python://` | Python runtime inspection |
| `reveal://` | Reveal's own codebase |
| `sqlite://` | SQLite database inspection |
| `stats://` | Codebase statistics |

### Planned
| Adapter | Notes |
|---------|-------|
| `claude://` | Claude conversation analysis (Tier 2) |
| `calls://` | Call graph analysis (post-v1.0) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules.

**Good first contributions:**
- Language analyzer improvements
- Pattern detection rules
- Documentation and examples
