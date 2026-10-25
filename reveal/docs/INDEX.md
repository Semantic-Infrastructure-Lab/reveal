---
title: Reveal Documentation Index
category: reference
---
# Reveal Documentation Index

Every user-facing doc, one line each. The same material is browsable from the CLI:
`reveal help://` lists every help topic and adapter live, and
`reveal 'markdown://reveal/docs/?link-graph'` shows how these files link to each other.
Line counts and file totals are deliberately not listed here; they drift.

## Start here

- **New users** → [QUICK_START.md](QUICK_START.md) → [RECIPES.md](guides/RECIPES.md)
- **AI agents** → [AGENT_HELP.md](AGENT_HELP.md) (or `reveal --agent-help`, `reveal help://quick`)
- **nginx / cPanel operators** → [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md), [CPANEL_ADAPTER_GUIDE.md](adapters/CPANEL_ADAPTER_GUIDE.md)
- **Contributors** → [ARCHITECTURE.md](../../ARCHITECTURE.md), then [Development Guides](#development-guides)

## User guides

| File | Description |
|------|-------------|
| [README.md](README.md) | Documentation overview and navigation |
| [QUICK_START.md](QUICK_START.md) | 5-minute introduction |
| [WHY_REVEAL.md](WHY_REVEAL.md) | What makes Reveal powerful, with examples |
| [WHAT_IS_REVEAL_GOOD_FOR.md](guides/WHAT_IS_REVEAL_GOOD_FOR.md) | Jobs-to-be-done guide: where Reveal is strongest |
| [BENCHMARKS.md](BENCHMARKS.md) | Measured token reduction on real scenarios |
| [INSTALL_GUIDE.md](guides/INSTALL_GUIDE.md) | Optional extras and network requirements (`reveal help://install`) |
| [MCP_SETUP.md](guides/MCP_SETUP.md) | MCP server setup for Claude Code, Cursor, Windsurf |
| [CI_RECIPES.md](guides/CI_RECIPES.md) | GitHub Actions and GitLab CI YAML: PR review, complexity gate, hotspot tracking, SSL checks |
| [RECIPES.md](guides/RECIPES.md) | Task-based workflows and multi-adapter patterns |
| [NAV_GUIDE.md](guides/NAV_GUIDE.md) | Deep-dive code navigation flags: `--boundary`, `--varflow`, `--sideeffects` |
| [UX_GUIDE.md](guides/UX_GUIDE.md) | CLI flags vs URI query parameters: when to use each |
| [SUBCOMMANDS_GUIDE.md](guides/SUBCOMMANDS_GUIDE.md) | Reference for the subcommands (`check`, `health`, `pack`, `dev`, and the retired names that map to new ones) |
| [TESTABILITY_GUIDE.md](guides/TESTABILITY_GUIDE.md) | Test patch pressure joined with production boundary fan-out (`reveal patches --view pressure`) |

## Adapter guides

One guide per URI adapter, named `<ADAPTER>_ADAPTER_GUIDE.md` and served as `reveal 'help://<adapter>'`.
They live in the `adapters/` directory.

| File | Description |
|------|-------------|
| [ARCHITECTURE_ADAPTER_GUIDE.md](adapters/ARCHITECTURE_ADAPTER_GUIDE.md) | Entry points, core abstractions, risks |
| [AST_ADAPTER_GUIDE.md](adapters/AST_ADAPTER_GUIDE.md) | Code analysis with complexity and size filtering |
| [AUTOSSL_ADAPTER_GUIDE.md](adapters/AUTOSSL_ADAPTER_GUIDE.md) | cPanel AutoSSL run logs: per-domain TLS outcomes, DCV failures |
| [CALLS_ADAPTER_GUIDE.md](adapters/CALLS_ADAPTER_GUIDE.md) | Cross-file call graph: callers, callees, coupling |
| [CLAUDE_ADAPTER_GUIDE.md](adapters/CLAUDE_ADAPTER_GUIDE.md) | Claude Code session analysis and tool usage |
| [CODEX_ADAPTER_GUIDE.md](adapters/CODEX_ADAPTER_GUIDE.md) | OpenAI Codex CLI session analysis |
| [CONTRACTS_ADAPTER_GUIDE.md](adapters/CONTRACTS_ADAPTER_GUIDE.md) | Contracts and architectural seams |
| [CPANEL_ADAPTER_GUIDE.md](adapters/CPANEL_ADAPTER_GUIDE.md) | cPanel user environment: domains, SSL, ACL health |
| [DEPENDS_ADAPTER_GUIDE.md](adapters/DEPENDS_ADAPTER_GUIDE.md) | Reverse module dependency graph: who imports this module |
| [DEPS_ADAPTER_GUIDE.md](adapters/DEPS_ADAPTER_GUIDE.md) | Dependency health: third-party packages, circular and unused imports |
| [DIFF_ADAPTER_GUIDE.md](adapters/DIFF_ADAPTER_GUIDE.md) | Git diff analysis and structural comparison |
| [DOMAIN_ADAPTER_GUIDE.md](adapters/DOMAIN_ADAPTER_GUIDE.md) | Domain, DNS and WHOIS analysis |
| [ENV_ADAPTER_GUIDE.md](adapters/ENV_ADAPTER_GUIDE.md) | Environment variable analysis and validation |
| [GIT_ADAPTER_GUIDE.md](adapters/GIT_ADAPTER_GUIDE.md) | Commits, branches, tags, blame |
| [HOTSPOTS_ADAPTER_GUIDE.md](adapters/HOTSPOTS_ADAPTER_GUIDE.md) | Files and functions most likely to need attention (complexity and churn) |
| [IMPORTS_ADAPTER_GUIDE.md](adapters/IMPORTS_ADAPTER_GUIDE.md) | Import dependency analysis across languages |
| [JSON_ADAPTER_GUIDE.md](adapters/JSON_ADAPTER_GUIDE.md) | JSON/JSONL analysis with JMESPath |
| [LETSENCRYPT_ADAPTER_GUIDE.md](adapters/LETSENCRYPT_ADAPTER_GUIDE.md) | Let's Encrypt certificate inventory: orphan and duplicate detection |
| [METRICS_ADAPTER_GUIDE.md](adapters/METRICS_ADAPTER_GUIDE.md) | Codebase metrics, file hotspots and provenance (replaces `stats://` and `classify://`) |
| [MYSQL_ADAPTER_GUIDE.md](adapters/MYSQL_ADAPTER_GUIDE.md) | MySQL introspection and schema analysis |
| [OVERVIEW_ADAPTER_GUIDE.md](adapters/OVERVIEW_ADAPTER_GUIDE.md) | One-glance dashboard: languages, quality, git |
| [PATCHES_ADAPTER_GUIDE.md](adapters/PATCHES_ADAPTER_GUIDE.md) | Test patch pressure: repeated mocks, private patches |
| [PYTHON_ADAPTER_GUIDE.md](adapters/PYTHON_ADAPTER_GUIDE.md) | Python runtime introspection |
| [REVEAL_ADAPTER_GUIDE.md](adapters/REVEAL_ADAPTER_GUIDE.md) | Reveal introspection (analyzers, adapters, config); reference implementation |
| [SQLITE_ADAPTER_GUIDE.md](adapters/SQLITE_ADAPTER_GUIDE.md) | SQLite introspection and schema analysis |
| [SSL_ADAPTER_GUIDE.md](adapters/SSL_ADAPTER_GUIDE.md) | SSL/TLS certificate analysis and validation |
| [SURFACE_ADAPTER_GUIDE.md](adapters/SURFACE_ADAPTER_GUIDE.md) | External boundary map: CLI args, HTTP routes, env vars, exported symbols |
| [XLSX_ADAPTER_GUIDE.md](adapters/XLSX_ADAPTER_GUIDE.md) | Excel file analysis and data extraction |

**Pointer stubs** (kept because rule V024 requires a guide file for every registered adapter):
[CLASSIFY](adapters/CLASSIFY_ADAPTER_GUIDE.md) and [STATS](adapters/STATS_ADAPTER_GUIDE.md) are retired into `metrics://`;
[TRACE](adapters/TRACE_ADAPTER_GUIDE.md) into `calls://?callees=&depth=&detail`;
[TESTABILITY](adapters/TESTABILITY_ADAPTER_GUIDE.md) into `patches://`;
[PACK](adapters/PACK_ADAPTER_GUIDE.md) points at the `pack` section of the Subcommands guide.

**Adapters without a dedicated guide:** `markdown://` ([MARKDOWN_GUIDE.md](adapters/MARKDOWN_GUIDE.md)),
`nginx://` ([NGINX_GUIDE.md](adapters/NGINX_GUIDE.md)), `help://` (use `reveal help://`), and
`demo://` (scaffolding template only, not registered by default; see [SCAFFOLDING_GUIDE.md](development/SCAFFOLDING_GUIDE.md)).

## Analyzer guides

| File | Description |
|------|-------------|
| [ANALYZER_PATTERNS.md](development/ANALYZER_PATTERNS.md) | Code analysis patterns and best practices |
| [ELIXIR_ANALYZER_GUIDE.md](development/ELIXIR_ANALYZER_GUIDE.md) | Elixir analyzer |
| [HTML_GUIDE.md](adapters/HTML_GUIDE.md) | HTML analysis and template extraction |
| [MARKDOWN_GUIDE.md](adapters/MARKDOWN_GUIDE.md) | Markdown analysis, headings, frontmatter |
| [NGINX_GUIDE.md](adapters/NGINX_GUIDE.md) | `nginx://` adapter and config analyzer (N001–N012 rules, ACME/SSL audits) |

## Reference

| File | Description |
|------|-------------|
| [QUERY_SYNTAX_GUIDE.md](guides/QUERY_SYNTAX_GUIDE.md) | Universal query operators and result control |
| [QUERY_PARAMETER_REFERENCE.md](guides/QUERY_PARAMETER_REFERENCE.md) | Query parameters for every adapter |
| [FIELD_SELECTION_GUIDE.md](guides/FIELD_SELECTION_GUIDE.md) | Token reduction with `--fields` and budgets |
| [ELEMENT_DISCOVERY_GUIDE.md](guides/ELEMENT_DISCOVERY_GUIDE.md) | Progressive disclosure with `available_elements` |
| [OUTPUT_CONTRACT.md](development/OUTPUT_CONTRACT.md) | JSON output specification (adapter-author-facing) |
| [CONTRACT_VERSIONS.md](development/CONTRACT_VERSIONS.md) | Output contract version policy |
| [OUTPUT_DIAGNOSTICS_GUIDE.md](OUTPUT_DIAGNOSTICS_GUIDE.md) | `--format`, the meta trust envelope, `--provenance`, `--perf`: which one do I need |
| [CONFIGURATION_GUIDE.md](guides/CONFIGURATION_GUIDE.md) | `.reveal.yaml`, configuration options, custom analyzer plugins |
| [DUPLICATE_DETECTION_GUIDE.md](guides/DUPLICATE_DETECTION_GUIDE.md) | Duplicate detection algorithms |
| [SCHEMA_VALIDATION_HELP.md](guides/SCHEMA_VALIDATION_HELP.md) | Frontmatter schema validation |
| `rules/V026.md`, `rules/V036.md` to `rules/V042.md` | Per-rule pages for the validation rules of the same codes |

## Development guides

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](../../ARCHITECTURE.md) | **Start here**: URI routing, adapter lifecycle, output contract, query pipeline, help tiers |
| [ADAPTER_AUTHORING_GUIDE.md](development/ADAPTER_AUTHORING_GUIDE.md) | Create custom adapters |
| [ADAPTER_CONSISTENCY.md](development/ADAPTER_CONSISTENCY.md) | Adapter UX patterns and consistency |
| [RULE_AUTHORING_GUIDE.md](development/RULE_AUTHORING_GUIDE.md) | Write your own quality rules (user-global and project-local) |
| [CLI_INTEGRATION_GUIDE.md](development/CLI_INTEGRATION_GUIDE.md) | Add a top-level subcommand |
| [SCAFFOLDING_GUIDE.md](development/SCAFFOLDING_GUIDE.md) | `reveal dev new-*` scaffolding |
| [HELP_SYSTEM_GUIDE.md](development/HELP_SYSTEM_GUIDE.md) | Help system internals (`help://` adapter) |
| [WINDOWS_SIGNING.md](development/WINDOWS_SIGNING.md) | Windows Application Control problem, SignPath Foundation plan, PyInstaller signing pipeline |

## AI agent reference

| File | Description |
|------|-------------|
| [AGENT_HELP.md](AGENT_HELP.md) | Complete AI agent reference (`reveal help://agent/full`; `reveal --agent-help` prints the orientation section) |

---

**Navigation**: [README](README.md) | [Project Root](../../README.md)
