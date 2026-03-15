# Reveal Roadmap
> **Last updated**: 2026-03-15 (kumewu-0315 — v0.63.0)

This document outlines reveal's development priorities and future direction. For contribution opportunities, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What We've Shipped

### v0.63.0
- ✅ **`calls://` `?rank=callers`** — coupling metrics via in-degree ranking; ranks functions by unique caller count. `?top=N`, `?builtins=true`.
- ✅ **`ast://` builtin filtering** — `show=calls` + element-level `calls:` field now filter Python builtins by default (consistent with `calls://?callees=`). `?builtins=true` restores raw output.
- ✅ **`reveal hotspots <path>`** — new subcommand: file-level hotspots (quality score, issues) + high-complexity functions in one view. `--top N`, `--min-complexity N`, `--functions-only`, `--files-only`, `--format json`. Exit 1 on critical findings for CI use.
- ✅ **I006 rule** — detects imports inside function/method bodies that should be at module top. Python-only. Skips `__future__`, `TYPE_CHECKING` blocks, `# noqa`, and functions with `lazy`/`import` in their name (intentional lazy-load pattern).
- ✅ **I005 bug fix** — `_normalize_import()` was checking `statement`/`source` keys but Python structure dicts use `content`; rule silently returned zero detections for all Python files. Fixed.
- ✅ **`claude://` session recovery + search** (BACK-028/029/040) — `?tail=N`/`?last`/`message/-1` for fast re-entry; cross-session file tracking; cross-session content search.
- ✅ **`claude://` overview improvements** (BACK-031/032) — richer session index, collapsed workflow run output.
- ✅ **`markdown://` cross-file link graph** (BACK-039) — outbound link tracking across a doc collection.
- ✅ **`markdown://` `?aggregate=<field>`** (BACK-033) — frontmatter frequency table for any field.
- ✅ **Query parser unification** (BACK-024) — replaced 4 hand-rolled parse loops with `parse_query_params()`; net -45 lines.
- ✅ **6,009 tests** — up from 4,949; new test_I005.py, test_I006.py, test_cli_hotspots.py; scaffold 100%, analysis/tools 100%, adapter 94%

### v0.62.0
- ✅ **`calls://` adapter** — new URI scheme for project-level cross-file call graph analysis. `?target=fn` (reverse: who calls fn?), `?callees=fn` (forward: what does fn call?), `?depth=N` (transitive BFS up to 5 levels), `?format=dot` (Graphviz output). Cross-file resolution: `resolved_calls` field links each outgoing call to its definition file. Builds inverted callers index cached by mtime fingerprint.
- ✅ **`calls://` builtin filtering** — Python builtins (`len`, `str`, `sorted`, `ValueError`, etc.) hidden by default in `?callees` output; `?builtins=true` restores full list. Footer shows `(N builtin(s) hidden)`. `PYTHON_BUILTINS` frozenset derived from `dir(builtins)` — stays correct across Python versions.
- ✅ **`calls://` bug fixes** — renderer crash fixed (static-method pattern); `?format=dot` in query string now works; `show=calls` no longer includes imports in output.
- ✅ **38 new tests** — 4,924 → 4,962; covers callers index, callees, builtin filtering, renderer, schema contracts, dot format, relative paths.

### v0.61.0
- ✅ **`cpanel://user/full-audit`** — composite ssl+acl-check+nginx ACME audit in one pass; exits 2 on any failure; `has_failures` flag in JSON output
- ✅ **`cpanel://user/ssl?domain_type=`** — query filter by domain type (`main_domain|addon|subdomain|parked`); composable with `--only-failures` and `--dns-verified`
- ✅ **`--only-failures` for `cpanel://user/ssl` and `cpanel://user/acl-check`** — was wired only for nginx; now complete across all three cpanel views
- ✅ **`--dns-verified` IP-match verification** — extends DNS mode to detect "resolves but to different server"; `dns_points_here` field; `[→ elsewhere]` renderer tag; elsewhere domains excluded from summary counts
- ✅ **`--validate-nginx-acme --format=json`** — machine-readable ACME audit; `{type, has_failures, only_failures, domains: [...]}` shape; exit 2 on failures preserved
- ✅ **`cpanel://user/ssl` `domain_type` field** — each cert entry now carries its domain type; renderer shows subdomain/parked breakdown in expired count
- ✅ **CLI no-path crash fix** — `--capabilities`, `--explain-file`, `--show-ast` no longer raise `TypeError` when called without a file path; clean `Usage:` message + exit 1
- ✅ **Rule false positive fixes** — `imports://` `__init__.py` re-exports; M102 `importlib.import_module()` dispatch tables + rule plugin naming convention; B006 try-then-try fallback pattern
- ✅ **B006 real violations fixed** — 11 `except Exception: pass` antipatterns corrected across 8 files; `return` moved into except body, specific exception types where appropriate
- ✅ **`TreeViewOptions` dataclass** — `show_directory_tree` refactored from 11-param signature to options object; fully backwards-compatible
- ✅ **9 unused imports removed** — autossl, markdown, jsonl, toml, review, routing, treesitter (discovered via `imports://` self-scan)
- ✅ **49 new tests** — 4,816 → 4,865; cpanel full-audit/dns/query-params/only-failures; CLI no-path guards; rule false positive regression guards
- ✅ **Quality: 99.8/100** — nesting depth hotspots eliminated across 40+ functions; all depth>4 reduced to ≤4

### v0.60.0
- ✅ **`nginx://` URI adapter** — domain-centric nginx vhost inspection (21st adapter). `reveal nginx://domain` shows config file + symlink status, ports (80/443, SSL, redirect), upstream servers + TCP reachability, auth directives, location blocks. Sub-paths: `/ports`, `/upstream`, `/auth`, `/locations`, `/config`. `reveal nginx://` lists all enabled sites. Searched against `/etc/nginx/sites-enabled/` and `/etc/nginx/conf.d/` automatically. Zero extra dependencies. Validated against 44 real vhosts on tia-proxy — 0 errors.
- ✅ **`domain://` HTTP response check** — `--check` now makes actual HTTP/HTTPS requests and reports status codes + redirect chains (e.g. `HTTP (80): 301 → https://... (200)`). On failure, suggests `reveal nginx://domain` as next diagnostic step.

### v0.59.0
- ✅ **`--help` argument groups** — replaced the flat 70+ flag wall with 12 named sections (Output, Discovery, Navigation, Display, Type-aware output, Quality checks, Universal adapter options, Markdown, HTML, Schema validation, SSL adapter, Nginx/cPanel adapter); taxonomy documented in ADAPTER_CONSISTENCY.md is now visible in the tool itself
- ✅ **`CpanelAdapter.get_schema()`** — all 20 URI adapters now fully support `help://schemas/<adapter>`; covers all 4 cpanel output types
- ✅ **CLI flag taxonomy docs** — ADAPTER_CONSISTENCY.md documents global/universal/adapter-specific tiers and the architectural principle: URI adapter options → query params, file target options → CLI flags

### v0.58.0
- ✅ **`autossl://` adapter** — inspect cPanel AutoSSL run logs at `/var/cpanel/logs/autossl/`. Lists runs, parses latest or specific run, shows per-user/per-domain TLS outcomes with defect codes and DCV impediment codes. 20th URI adapter.

### v0.57.0
- ✅ **`reveal check <path>`** — canonical quality check subcommand replacing `--check` flag; own `--help`, `--rules`, `--explain`
- ✅ **`reveal review <path>`** — PR review workflow orchestrating diff + check + hotspots + complexity; `--format json` for CI/CD
- ✅ **`reveal health <target>`** — unified health check with exit codes 0/1/2; `--all` auto-detects targets from `.reveal.yaml` or common source dirs
- ✅ **`reveal pack <path>`** — token-budgeted context snapshot for LLM consumption; `--budget`, `--focus`, `--verbose`
- ✅ **`reveal dev <subcommand>`** — developer tooling: `new-adapter`, `new-analyzer`, `new-rule`, `inspect-config`
- ✅ **Parser inheritance** — all 4 subcommand parsers inherit global flags via `parents=` pattern
- ✅ **`--sort -field` syntax** — `reveal 'markdown://path/' --sort -modified` now works via argv preprocessing
- ✅ **`--sort modified` alias** — accepted as alias for `mtime` in `--files` mode and directory trees
- ✅ **`claude:// --base-path DIR`** — runtime override for `CONVERSATION_BASE` (WSL, remote machines, mounted volumes)
- ✅ **Per-adapter CLI flags in `help://`** — `help://ssl`, `help://nginx`, `help://markdown`, `help://html` each show adapter-specific flag reference
- ✅ **Mypy: 0 errors** across 313 source files

### v0.56.0
- ✅ **`reveal check` parser foundation** — `_build_global_options_parser()` shared parent; `reveal check --help` subcommand-specific help
- ✅ **Error-with-hint guards** — nginx/cPanel batch flags and markdown `--related` fail with helpful redirect errors on wrong input types
- ✅ **`--check` deprecation hint** — `reveal ./src --check` still works but prints migration hint

### v0.55.0
- ✅ **`--files` mode** — flat time-sorted file list with timestamps; replaces `find dir/ | sort -rn`
- ✅ **`--ext <ext>`** — filetype filter for directory trees and `--files` mode
- ✅ **`--sort`, `--desc`, `--asc`** — sort control for directory listings and file lists
- ✅ **`--meta`** — show file metadata (size, lines, extension) in directory listings

### v0.54.8
- ✅ **`claude://` Bash commands in tools summary** — `reveal claude://session` shows Bash tool invocations in tool-use summary view

### v0.54.7
- ✅ **Issue 3 — `claude://sessions` alias** — `sessions` was parsed as a session name and errored. Now an early-exit alias for `_list_sessions()`, mirroring the `search` guard.
- ✅ **Issue 4 — Session title from first user message** — overview now includes a `title` field (first line of first user message, max 100 chars). Handles both string and list-of-items content. Renderer shows it beneath the session name.
- ✅ **Issue 5 — Cross-platform `help://claude` examples** — `try_now` no longer uses `$(basename $PWD)` bash substitution. Static example session name used instead; notes added for bash/zsh and PowerShell equivalents.

### v0.54.6
- ✅ **B6 — subagent files excluded from `claude://` listing** — `agent-*.jsonl` files were counted as duplicate sessions (2841 phantom entries on TIA, 45 on Frono). Now skipped in both `_list_sessions()` and `_find_conversation()`.
- ✅ **B7 — `_find_conversation()` agent-file filter** — explicit filter replaces accidental alphabetic ordering; main session JSONL reliably returned.
- ✅ **B2 — `claude://search` returns helpful error** — structured `claude_error` with `tia search sessions` hint instead of "session not found".

### v0.54.5
- ✅ **N003 false positive fix — `include` snippets not resolved** — `_find_proxy_headers()` now follows `include` directives in proxy location blocks and checks included files for the required headers. Eliminated 17 false positives across 4 vhost configs on tia-proxy.
- ✅ **N001 annotation — `# reveal:allow-shared-backend`** — upstreams containing this comment are excluded from duplicate-backend detection. Allows intentional aliasing (e.g. staging alias for a dev node) without noise. Suggestion text updated to tell users about the annotation.
- ✅ **nginx:// URI scheme removed from help docs** — scheme is not implemented; removed 5 unimplemented `nginx://` examples from `help://nginx` and `ssl.yaml`. Replaced with working file-path equivalents.
- ✅ **N007: ssl_stapling without OCSP URL** (LOW) — new rule detects `ssl_stapling on;` on certs that lack an OCSP responder URL. nginx silently ignores stapling in this case; TLS performance degrades without warning. Reads cert via `cryptography` lib with DER byte-scan fallback; suppresses gracefully when cert is unreadable.

### v0.54.4
- ✅ **V023 false positives eliminated** — two new skip conditions: `ResultBuilder.create()` pattern (kwargs, not dict literals); module-level delegation pattern (all returns via `module.func(...)` with no direct `{}`).
- ✅ **Batch checker warning** — `file_checker.py` now logs `WARNING` when skipping a file due to analyzer exception (was silent).
- ✅ **Type annotation coverage** — `xml_analyzer.py`, `graphql.py`, `hcl.py`, `protobuf.py` helper methods now fully annotated.
- ✅ **INDEX.md anchor fix** — stale `#adapter-guides-16-files` links corrected; was causing test failure.

### v0.54.3
- ✅ **B3 — N004 quoted path messages** — `.strip('"\'')` on ACME root in N004 messages; cPanel configs quote root directives, causing `'"/home/..."'` double-wrapped display and false-positive path mismatches. Messages now show bare paths; quoted and unquoted forms treated as equal.
- ✅ **U6 — `cpanel://USERNAME/ssl --dns-verified`** — DNS-verified mode for cpanel ssl: NXDOMAIN domains shown with `[nxdomain]` tag but excluded from critical/expiring summary counts. Eliminates false alarms from former-customer domains whose DNS has moved away. NXDOMAIN-only scope via `socket.getaddrinfo` (stdlib, no subprocess).
- ✅ **Dogfood false positive elimination** — three rules fixed via `reveal reveal/ --check`: I001 skips `__init__.py` (imports are always public API/registration); B006 checks enclosing function docstring for error-tolerance keywords before flagging intentional broad catches; V023 skips dispatcher methods (`return self._` delegation pattern).
- ✅ **CPANEL_ADAPTER_GUIDE.md** — new comprehensive guide for the cpanel:// adapter.
- ✅ **NGINX_ANALYZER_GUIDE.md** — new comprehensive guide for nginx analysis: all flags, N001–N006 rules, operator workflows.

### v0.54.2
- ✅ **B1 fix — `--validate-nginx-acme` ACL column** — `_parse_location_root`/`_parse_server_root` now strip quotes from root paths; cPanel configs quote all `root` directives, causing every domain to report `not_found`. Feature fully functional on production gateways.
- ✅ **`--validate-nginx-acme --only-failures`** — filter flag respected; passing rows suppressed; "✅ No failures found." when all pass.
- ✅ **cpanel graduated 🔴 Experimental → 🟡 Beta** — accurate production results (3 denied domains found in 2s); B1 was in nginx analyzer, not cpanel.
- ✅ **U1 — plain file paths in cpanel next_steps** — replaced `nginx:///path` (fragile, subprocess-incompatible) with `reveal /path/file.conf`.
- ✅ **U4 — ACL method guidance** — added note to `help://cpanel`: filesystem ACL (authoritative) vs nginx ACME audit (routing) — explains when to use each.

### v0.54.0
- ✅ **cpanel:// adapter** — first-class cPanel user environment adapter: `reveal cpanel://USERNAME` (overview), `/domains` (all docroots), `/ssl` (disk cert health), `/acl-check` (nobody ACL). All filesystem-based; no WHM API needed.
- ✅ **nginx: S4 — `--cpanel-certs`** — disk cert vs live cert comparison per SSL domain; detects "AutoSSL renewed but nginx not reloaded" (`⚠️ STALE (reload nginx)`). Exit 2 on stale or expired.
- ✅ **nginx: S3 — `--diagnose`** — scans last 5,000 lines of nginx error log for ACME/SSL failures by domain; groups `permission_denied`, `ssl_error`, `not_found`; exit 2 on first two.
- ✅ **nginx: N1 — `--check-acl`** — checks nobody-user has read+execute on every `root` directive; exits 2 on any failure.
- ✅ **nginx: N4 — `--extract acme-roots`** — ACME root paths + nobody ACL status table across all SSL domains.
- ✅ **nginx: N2 — `--check-conflicts`** — detects prefix overlap and regex-shadows-prefix location routing issues; exit 2 on regex conflicts.
- ✅ **nginx: N3 — `--domain` filter** — filter any nginx output to a single domain's server block(s).
- ✅ **nginx: `--validate-nginx-acme`** — composed audit: ACME root path + ACL + live SSL per domain in one table.
- ✅ **ssl: S2 — `ssl://file:///path`** — inspect on-disk PEM/DER certs without a network connection.
- ✅ **ssl: S1 — batch failure detail** — `--batch --check` shows failure reason inline: EXPIRED, DNS FAILURE (NXDOMAIN), CONNECTION REFUSED, TIMEOUT.
- ✅ **ssl: S5 — expiry dates in batch output** — warnings show "expires in N days (Mon DD, YYYY)"; healthy shows "N days (Mon DD, YYYY)".

### v0.53.0
- ✅ **`--check` grouped output** — rules firing ≥ 10× per file collapse to summary + "+N more" note; `--no-group` expands all
- ✅ **Auto-generated file skip** — `# reveal: generated` (and common patterns like `# Generated by`) skips files in recursive `--check`
- ✅ **nginx: N006 rule** (HIGH) — `send_timeout`/`proxy_read_timeout` < 60s + `client_max_body_size` > 10m; caught real Sociamonials incident

### v0.52.0
- ✅ **nginx: main context directives** — `user`, `worker_processes`, `worker_rlimit_nofile`, `error_log`, `pid` now visible in `nginx.conf`; `ssl_protocols`, `ssl_ciphers`, `client_max_body_size` visible in vhost includes
- ✅ **nginx: multi-line directives** — `log_format` and other continuation-line directives no longer silently dropped
- ✅ **nginx: upstream backend detail** — server entries, `max_fails`, `fail_timeout`, `keepalive` now surfaced per upstream
- ✅ **nginx: map{} block detection** — `map $src $target {}` blocks detected and listed (cPanel/WHM pattern)
- ✅ **nginx: N005 rule** — flags timeout/buffer directives outside safe operational bounds

### v0.51.1
- ✅ **Cross-platform CI** — All 6 matrix jobs pass (Python 3.10/3.12 × Ubuntu/macOS/Windows)
- ✅ **Claude adapter two-pass search** — TIA-style directory names always checked before UUID filename matches
- ✅ **V009 symlink fix** — `normpath` instead of `resolve()` prevents macOS `/var` → `/private/var` expansion
- ✅ **Windows path separators** — `.as_posix()` in V003 and stats adapter; robust drive-letter parsing in diff adapter
- ✅ **Windows encoding** — `encoding='utf-8'` in scaffold write/read; `charmap` errors eliminated
- ✅ **DNS dev dep** — `dnspython>=2.0.0` added to dev extras so DNS adapter tests load correctly
- ✅ **chmod tests skipped on Windows** — V002/V007/V011/V015/validation tests skip where `chmod(0o000)` is a no-op

### v0.51.0
- ✅ **I002 cache fix** — Import graph cache keyed on project root (not file parent); 73-subdir project: 13 min → 33s
- ✅ **I002 shared graph across workers** — Pre-build once in main process, seed workers via pool initializer; CPU cost 4× → 1×
- ✅ **`--check` parallelism** — ProcessPoolExecutor (4 workers); 3,500-file project: 48s → 21.5s (2.2×)
- ✅ **O(n²) scan eliminated** — Rule registry short-circuits correctly; large projects: minutes → ~30s
- ✅ **Security hardening** — Zip bomb protection, 100 MB file guard, MySQL URL parsing fix, frontmatter eval hardening
- ✅ **claude:// content views** — `/user`, `/assistant`, `/thinking`, `/message/<n>` render real content
- ✅ **claude:// search** — `?search=term` searches all content including thinking blocks and tool inputs
- ✅ **Bug fixes** — ast:// OR logic, `--check` recursive mode, M102/I004 false positives, D001 scoping

### v0.50.0
- ✅ **MySQL table I/O statistics** — `mysql:///tables` endpoint for table hotspot detection
- ✅ **Automatic alerts** — Extreme read ratios (>10K:1), high volume (>1B reads), long-running (>1h)
- ✅ **Token efficiency** — 300-500 tokens vs 2000+ for raw SQL queries
- ✅ **Windows CI fixes** — 19 of 22 test failures resolved (86% success rate)
- ✅ **UTF-8 encoding** — Cross-platform file handling with explicit encoding

### v0.49.2
- ✅ **Windows CI compatibility** — 100% test pass rate on Windows (3177/3177 tests)
- ✅ **Path separator normalization** — Cross-platform MANIFEST.in validation
- ✅ **Platform-independent test detection** — Use Path.parts for Windows compatibility
- ✅ **Permission test handling** — Skip chmod-based tests on Windows

### v0.49.1
- ✅ **Help system badges** — Mark xlsx, ssl, and domain as 🟡 Beta (production-ready)

### v0.49.0
- ✅ **xlsx:// adapter** — Complete Excel spreadsheet inspection and data extraction
- ✅ **Sheet extraction** — By name (case-insensitive) or 0-based index
- ✅ **Cell range extraction** — A1 notation support (A1:Z100, supports AA-ZZ columns)
- ✅ **CSV export** — `?format=csv` query parameter for data extraction
- ✅ **40 comprehensive tests** — 100% passing, performance tested up to 20K+ rows
- ✅ **Complete documentation** — Help system, demo docs, examples

### v0.48.0
- ✅ **Phase 3: Query Operator Standardization** — Universal query operators (`=`, `!=`, `>`, `<`, `>=`, `<=`, `~=`, `..`) across all adapters
- ✅ **Phase 4: Field Selection** — Token reduction with `--fields`, budget constraints (`--max-items`, `--max-bytes`)
- ✅ **Phase 5: Element Discovery** — Auto-discovery of available elements in text and JSON output
- ✅ **Phase 8: Convenience Flags** — Ergonomic `--search`, `--sort`, `--type` flags for 80% of within-file queries
- ✅ **Result control** — `sort`, `limit`, `offset` work consistently across ast://, json://, markdown://, stats://, git://
- ✅ **Progressive disclosure** — `available_elements` enables programmatic element discovery

### v0.47.0
- ✅ **Phase 6: Help Introspection** — Machine-readable adapter schemas for all 15 adapters
- ✅ **Phase 7: Output Contract v1.1** — Trust metadata (parse_mode, confidence, warnings, errors)
- ✅ **help://schemas/<adapter>** — JSON schemas for AI agent auto-discovery
- ✅ **help://examples/<task>** — Canonical query recipes for common tasks

### v0.45.0
- ✅ **Phase 1: Universal Operation Flags** — `--advanced`, `--only-failures` across all adapters
- ✅ **Phase 2: Stdin Batch Processing** — Universal `--batch` flag with result aggregation
- ✅ **Batch mode** — Works with any adapter, mixed adapter batches supported
- ✅ **Format consistency** — All 18 adapters support `--format json|text`

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
- Test count: **5,904 passing** (v0.64.0)
- UX Phases 3/4/5: ✅ **ALL COMPLETE** (query operators, field selection, element discovery)
- Target: 80%+ coverage for core adapters — scaffold 100%, tools 100%, adapter 94%

### Stability & Polish
- Output contract v1.1 enforcement
- Performance optimization for large codebases
- `autossl://` adapter — ✅ shipped in v0.58.0
- `nginx://` adapter — ✅ shipped in v0.60.0 (21st adapter; validated on 44 real vhosts)
- `domain://` HTTP response check — ✅ shipped in v0.60.0
- `cpanel://USERNAME/full-audit` — ✅ shipped (platinum-gleam-0313): ssl + acl-check + nginx ACME in one pass; exits 2 on any failure
- U6 follow-on — ✅ shipped (platinum-gleam-0313): `dns_points_here` annotation on `--dns-verified`; elsewhere domains excluded from summary counts; `[→ elsewhere]` renderer tag; `dns_elsewhere` result dict key for jq consumers

---

## Post-v1.0 Features

> **Status**: Strategic backlog. Not prioritized for implementation yet.

### Additional Subcommands

Six subcommands (`check`, `review`, `pack`, `health`, `dev`, `hotspots`) shipped. Remaining subcommand ideas:

```bash
reveal overview              # Auto-generated repo summary
reveal onboarding            # First-day guide for unfamiliar codebases
reveal audit                 # Security/compliance focus (S, B, N rules)
reveal deps                  # Full dependency analysis (wraps imports://)
```

### Relationship Queries (Call Graphs)
```bash
reveal calls://src/api.py:handle_request  # Who calls this?
reveal depends://src/module/              # What depends on this?
```
**Why valuable**: Structure tells you what exists; relationships tell you what *matters*.

**Current limitation**: Requires cross-file static analysis. Tree-sitter infrastructure is ready, but call resolution is non-trivial.

### Git-Aware Defaults
```bash
reveal .                    # Defaults to changed files on branch
reveal --since HEAD~3       # Changes since commit
reveal --pr                 # PR context auto-detection
```
**Why valuable**: Makes tool instantly relevant to daily workflows.

---

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
| `--no-fail` / `--exit-zero` | `\|\| true` is the Unix idiom. The flag conflates "checking" with "what to do about findings" — callers decide that, not the tool. Documented in AGENT_HELP under "Exit code 2 is breaking my pipeline." |
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

### Implemented (21)
| Adapter | Description |
|---------|-------------|
| `ast://` | Query code as database (complexity, size, type filters) |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `claude://` | Claude conversation analysis |
| `cpanel://` | cPanel user environments — domains, SSL certs, ACL health |
| `diff://` | Compare files or git revisions |
| `domain://` | Domain registration, DNS records, health status + HTTP response check |
| `env://` | Environment variable inspection |
| `git://` | Repository history, blame, commits |
| `help://` | Built-in documentation |
| `imports://` | Dependency analysis, circular detection |
| `json://` | JSON/JSONL deep inspection |
| `markdown://` | Markdown document inspection and related-file discovery |
| `mysql://` | MySQL database schema inspection |
| `nginx://` | Nginx vhost inspection — config file, ports, upstreams, auth, locations |
| `python://` | Python runtime inspection |
| `reveal://` | Reveal's own codebase |
| `sqlite://` | SQLite database inspection |
| `ssl://` | SSL/TLS certificate inspection |
| `stats://` | Codebase statistics |
| `xlsx://` | Excel spreadsheet inspection and data extraction |

### Planned
| Adapter | Notes |
|---------|-------|
| `calls://` | Call graph analysis — who calls what (post-v1.0) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules.

**Good first contributions:**
- Language analyzer improvements
- Pattern detection rules
- Documentation and examples
