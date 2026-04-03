# Reveal Roadmap
> **Last updated**: 2026-04-03 (sleeping-goddess-0403 — v0.70.1 released)

This document outlines reveal's development priorities and future direction. For contribution opportunities, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What We've Shipped

### v0.70.1
- ✅ **`--base-path` quote stripping on Windows** — `cmd.exe` passes single quotes literally; `'C:/Users/...'` resolved to a nonexistent path, causing `claude://` to return 0 sessions. Added `_strip_path_quotes()` as the `type=` converter for `--base-path` (and `--log-path`) in argparse. UUID-named sessions returning 0 results was purely downstream of this bug.

### v0.70.0
- ✅ **Full Claude adapter telemetry (Phases A–E)** — `?tokens` route, `toolUseResult` error detection, `filePath`/patches in `/files`, Glob/Grep tracking, `/agents` sub-route with per-agent duration/token/tool-count telemetry, `result` blocks on `?tools=` calls, `caller_type: "direct"` on all tool entries.
- ✅ **`reveal file.md --search` crash fix** — `analyze_file()` now skips non-list/non-dict items when iterating markdown structure; heading search now works correctly.

### v0.69.1
- ✅ **`git://` pygit2 path separator fix (Windows)** — `os.path.relpath()` returns backslashes on Windows; pygit2 requires POSIX slashes. `.replace(os.sep, '/')` fix in `adapter.py:402`. `reveal git://./file.py?type=blame` from a subdirectory was broken on Windows in 0.69.0.
- ✅ **`_dir_cache_key` uses `os.scandir`** — replaced `iterdir()+is_dir()` with `os.scandir()+entry.is_dir()` to avoid routing through `os.stat` singleton; fixes test reliability on Linux and Windows.
- ✅ **Windows CI green** — 5 test antipattern fixes + `scripts/check_windows_compat.py` checker wired into CI.

### v0.69.0
- ✅ **`REVEAL_CLAUDE_JSON` env var** (BACK-119) — explicit override for `~/.claude.json`; auto-derives from `REVEAL_CLAUDE_HOME` when set.
- ✅ **`CONVERSATION_BASE` derives from `REVEAL_CLAUDE_HOME`** (BACK-121) — single env var covers the whole Claude install in SSH multi-user scenarios.
- ✅ **`--base-path` covers the full Claude install** (BACK-120) — derives `CLAUDE_HOME`, `CLAUDE_JSON`, `PLANS_DIR`, `AGENTS_DIR`, `HOOKS_DIR` from one flag.
- ✅ **`calls://` .venv hang fix** — `collect_structures()` replaced `rglob` with `os.walk` pruning `_SKIP_DIRS`; 90s → 0.8s on virtualenv projects.
- ✅ **`calls://` starred-callee fix** — `*foo(args)` and `*self.method(args)` callers now correctly indexed.
- ✅ **`calls://` stale cache fix** — `_dir_cache_key` stats root + immediate subdirectories, not just root.
- ✅ **`_extract_project_from_dir` hardcoded username removed** — `_SKIP` contains only generic path words.
- ✅ **TIA session boilerplate + badge regex generalized** — removed TIA-specific prefixes from title extraction; badge regex matches any CLI prefix.

### v0.68.0
- ✅ **`claude://` install introspection (8 new resources)** — `history`, `settings`, `plans`, `info`, `config`, `memory`, `agents`, `hooks`. Browse prompt history, inspect user settings, read saved plans, surface feature flags, MCP server registrations, memory files, agent definitions, and hook scripts without specifying a session name.
- ✅ **`CLAUDE_HOME` / `CLAUDE_JSON` / `PLANS_DIR` / `AGENTS_DIR` / `HOOKS_DIR` class attrs** — centralised path resolution with `REVEAL_CLAUDE_HOME` env override and Windows `%APPDATA%\Claude` fallback.
- ✅ **`CLAUDE_ADAPTER_GUIDE.md` — Install Introspection section** (BACK-101) — new section documents all 8 resources with query param tables, sub-resource paths, and return value descriptions.
- ✅ **Test count: 7,035 → 7,169** — 42 new tests across `TestClaudeHistory`, `TestClaudeInfo`, `TestClaudeSettings`, `TestClasuePlans`, `TestClaudeConfig`, `TestClaudeMemory`, `TestClaudeAgents`, `TestClaudeHooks`.

### v0.67.0
- ✅ **OR-pattern extraction** — `reveal doc.md "Open Issues|Action Items"` extracts both sections in one call. Backslash-escaped pipes normalised, deduplication when multiple terms match same section.
- ✅ **`--broken-only` links flag** — filter `reveal doc.md --links` to broken internal links only.
- ✅ **Call graph JSON output** — `reveal file.py --format json` includes top-level `relationships` key with intra-file call edges.
- ✅ **5 agent friction fixes (BACK-113–117)** — false `--analyzer text` hint removed, element not-found lists available names, OR-pattern failure hints `--search`, B005 skips `try/except ImportError` optional deps, code element not-found hints at `--search`.
- ✅ **`help://` internal adapter filtering** — `demo` and `test` no longer appear in adapter listings or counts.
- ✅ **`letsencrypt://` + `autossl://` agent guide coverage** — full task sections added to `AGENT_HELP.md`.
- ✅ **Test count: 6,871 → 7,035**

### v0.66.1
- ✅ **Circular dep false positives fixed** — `from . import X` (empty module_name) now resolves to `X.py` instead of `__init__.py`. Eliminated all false-positive cycles in standard Python `__init__.py` re-export patterns. Also handles aliased imports (`from . import query as q`). Multi-edge emission for `from . import X, Y, Z`.
- ✅ **git blame: CWD nested inside repo** — `get_structure` normalises subpath to repo-root-relative before passing to pygit2; `./file.py` URI form also fixed.
- ✅ **git blame: element % denominator** — sole author of a 100-line function now shows 100.0%, not 9.5%.
- ✅ **8 regression tests** — 4 for git adapter bugs, 4 for import resolver. Test count: 6,863 → 6,871.

### v0.66.0
- ✅ **Public Python SDK** — `analyze()`, `element()`, `query()`, `check()` — programmatic access without subprocess overhead.
- ✅ **`letsencrypt://` renewal timer detection** (BACK-079) — flags certs expiring within 30 days.
- ✅ **Markdown ambiguous heading match** — partial heading queries matching multiple sections now concatenate results instead of crashing with `ValueError`.
- ✅ **`calls/index.py` complexity reduction** — eliminated only ❌ hotspot; `find_uncalled` 126→84 lines, depth 5→3/2 across build/find functions.
- ✅ **`handlers.py` + `routing.py` split into subpackages** (BACK-097/098) — 1,104/744-line files split into focused modules.
- ✅ **Bug fixes**: Windows CI (6 failures), quality rules N008/N009/N010, config §§ placeholder, health subprocess removal.
- ✅ **6,861 tests** — up from ~6,810.

### v0.65.1
- ✅ **Windows `claude://` UUID fix** — session listing truncated 36-char UUIDs to 34 chars; column widened + suffix match added so truncated IDs from prior installs still resolve.
- ✅ **Windows `claude://` projects dir** — `_resolve_claude_projects_dir()` checks `~/.claude/projects` first (standard on all platforms), `%APPDATA%\Claude\projects` as fallback.
- ✅ **CI fix** — `mcp>=1.0.0` + `pygit2>=1.14.0` added to `[dev]` extras; all 6 CI jobs (Linux/Mac/Windows × Python 3.10/3.12) were failing.
- ✅ **Windows letsencrypt path separator** — `_find_orphans` now uses `rsplit('/', 1)` instead of `Path.parent` to keep server paths as POSIX.

### v0.65.0
- ✅ **`letsencrypt://` adapter** — cert inventory, orphan detection (cross-ref nginx ssl_certificate), duplicate detection (identical SANs). 33 new tests.
- ✅ **`--probe-http` / `--probe`** — live HTTP→HTTPS redirect chain verification + security header check (HSTS, XCTO, XFO, CSP). `ssl://domain --probe-http`, `nginx://domain --probe`. 20 new tests.
- ✅ **`reveal nginx:// --audit`** — fleet consistency matrix: 7 checks per site, consolidation hints, snippet consistency analysis. `--only-failures`, `--format json`, exit 2 on gaps. 43 new tests.
- ✅ **`reveal nginx.conf --global-audit`** — http{} block audit, 10 directives (server_tokens, HSTS, XCTO, XFO, ssl_protocols, resolver, limit_req_zone, client_max_body_size, gzip, worker_processes). 42 new tests.
- ✅ **N008–N012: 5 nginx security rules** — sourced from real tia-proxy fleet audit (45–46/46 sites affected each): missing HSTS (HIGH), server_tokens on (MEDIUM), deprecated X-XSS-Protection (LOW), SSL listener missing http2 (LOW), no rate limiting (LOW/MEDIUM). Rule count: 64 → 69. 37 new tests.
- ✅ **xlsx Power Query M extraction** (`?powerquery=list/show/<name>`), named ranges (`?names=list`), external connections (`?connections=list/show`), pbixray Tier 2 for modern Power BI xlsx. Large sheet guard (>50 MB). Column count from dimension ref. 33+ new tests.
- ✅ **`help://relationships`** — adapter ecosystem map: 5 clusters, pairwise relationships, 5 power pairs. Related-adapter breadcrumbs expanded to all 22 adapters. 8 new tests.
- ✅ **Bug fixes**: exit code severity inverted (failures→2, warnings→0), budget off-by-one (always return ≥1 item), port 0 falsy, `_extract_includes` inline include regex anchor.
- ✅ **Refactors**: `ImportsAdapter` adapter contract, lazy rule discovery, rule config allowlist, `ELEMENT_NAMESPACE_ADAPTER` class attribute.
- ✅ **BACK-092/093/094: OOM fixes** — streaming `reveal check`, expanded excluded dirs, health file count guard + timeout. 8 new tests.
- ✅ **~6,810 tests** — up from ~6,560.

### v0.64.0
- ✅ **`reveal deps`** — dependency health dashboard: circular deps, unused imports, top packages, CI exit codes. 59 new tests.
- ✅ **`reveal overview`** — one-glance codebase dashboard: stats, language breakdown, quality pulse, top hotspots, complex functions, recent commits. 71 new tests.
- ✅ **`reveal-mcp`** — MCP server with 5 tools (`reveal_structure`, `reveal_element`, `reveal_query`, `reveal_pack`, `reveal_check`) for Claude Code, Cursor, Windsurf. 27 new tests.
- ✅ **Power Pivot / SSAS support** (`xlsx://` `?powerpivot=tables/schema/measures/dax/relationships`) — pure stdlib; handles Excel 2010/2013+/Power BI exports. 44+ new tests.
- ✅ **`reveal pack --since <ref>`** — git-aware context snapshots; changed files boosted to priority tier 0. 20 new tests.
- ✅ **`reveal pack --content`** — tiered content emission (full/structure/name-only by priority + change status). 11 new tests.
- ✅ **`calls://` `?uncalled`** — dead code detection (zero in-degree); excludes dunders, `@property`, `@classmethod`, `@staticmethod`. 20 new tests.
- ✅ **`# noqa: uncalled` suppression** — entry-point exclusion for framework decorators, console scripts, dispatch tables. 3 new tests.
- ✅ **`claude://session/<id>/chain`** — session continuation chain traversal via README frontmatter. 22 new tests.
- ✅ **`domain://DOMAIN/ns-audit`** — NS authority cross-check; detects orphaned NS entries, unreachable servers, inconsistent sets. 11 new tests.
- ✅ **`help://quick` decision tree** — 10 task-oriented entries mapping user intent to the right adapter/command.
- ✅ **`reveal --discover`** — full adapter registry as JSON (all 22 adapters). 6 new tests.
- ✅ **OCSP URL in `ssl://` `--advanced`** — extracts OCSP URL from AIA extension via `cryptography`. 4 new tests.
- ✅ **`ARCHITECTURE.md`** — end-to-end architecture doc: URI routing, adapter lifecycle, output contract, query pipeline, help system, renderer layer.
- ✅ **`CI_RECIPES.md`** — ready-to-paste GitHub Actions + GitLab CI YAML for PR gate, complexity delta, hotspot tracking, SSL checks.
- ✅ **`BENCHMARKS.md`** — measured token reduction evidence (3.9–33× across 5 real scenarios on reveal's own codebase).
- ✅ **`ARCHITECTURE.md`, `CLAUDE.md.template`** — agent-first README rewrite; `local-first` + `progressive disclosure` positioning.
- ✅ **BACK-081/082: `_parse_xmla` + `_render_powerpivot` split** — both cx:64/cx:34 functions decomposed into named helpers; orchestrators ~15–25 lines.
- ✅ **Doc accuracy audit** (spinning-observatory-0316, foggy-flood-0318) — 14 discrepancies fixed across 9 files; rule categories table expanded from 7 to all 14 (B,C,D,E,F,I,L,M,N,R,S,T,U,V).
- ✅ **~6,560 tests** — up from 6,009.

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
- Test count: **~6,560 passing** (v0.64.x)
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

## Backlog: Awesomeness Gaps

> Identified via gap analysis between WHY_REVEAL.md description and actual behavior (session hovori-0316, 2026-03-16). All five items complete existing capabilities — infrastructure is present, the last piece is missing.

### BACK-071: `calls://src/?uncalled` — dead code detection

**Status**: ✅ Shipped (session frost-matrix-0316)
**Value**: High | **Lift**: Low

`?rank=callers` surfaces the most-coupled functions. The natural counterpart — functions defined but never called — doesn't exist. Dead code candidates are a set-difference between ast:// definitions and calls index entries (in-degree = 0).

```bash
reveal 'calls://src/?uncalled'                # all uncalled functions
reveal 'calls://src/?uncalled&type=function'  # skip methods
reveal 'calls://src/?uncalled&top=20'         # most-recently-added uncalled (by file mtime)
```

Implementation: after building callers index, collect all function names from ast:// scan, subtract those appearing as callees in the index. Flag private functions separately (`_` prefix). Exclude `__dunder__` methods and decorated functions with `@property`, `@classmethod`, `@staticmethod` (called implicitly).

---

### BACK-072: `reveal pack --since <branch>` — git-aware context snapshots

**Status**: ✅ Shipped (session frost-matrix-0316)
**Value**: High | **Lift**: Medium

Pack currently ranks by entry points, complexity, and recency — but it's not git-aware. The most common "PR review context" use case is: *give me the changed files plus their key dependencies, within a token budget.*

```bash
reveal pack src/ --since main --budget 8000
reveal pack src/ --since HEAD~3 --budget 4000
```

Implementation: run `git diff --name-only <ref>...HEAD` to get changed file set. Boost those files to priority tier 0 (above entry points). Remaining budget fills with current priority logic (entry points → complexity → recency). Changed files that exceed the budget alone truncate by complexity rank.

---

### BACK-073: `diff://` per-function complexity delta

**Status**: ✅ Shipped (session obsidian-prism-0316)
**Value**: High | **Lift**: Medium

The diff JSON has a `diff.functions` list of changed functions but no before/after complexity. The natural CI gate — "did this PR make anything meaningfully more complex?" — isn't possible without this field.

```bash
reveal diff://git://main/.:git://HEAD/. --format json | \
  jq '.diff.functions[] | select(.complexity_delta > 5)'
```

Implementation: for each function in `diff.functions.changed`, call the AST analyzer on both left and right sides to get complexity, then add `complexity_before`, `complexity_after`, `complexity_delta` to the entry. `reveal review` should surface functions where `complexity_delta > 5` as a named check.

---

### BACK-074: `claude://sessions/?search=term` — cross-session search

**Status**: ✅ Shipped (session obsidian-prism-0316)
**Value**: Medium | **Lift**: Medium

The CLAUDE_ADAPTER_GUIDE explicitly notes "No cross-session full-text search" as a known limitation, pointing users to `tia search sessions`. The `grep_files` utility from BACK-029 exists — it just isn't wired to a URI query.

```bash
reveal 'claude://sessions/?search=validate_token'   # sessions mentioning this term
reveal 'claude://sessions/?search=auth&since=2026-03-01'  # scoped to recent sessions
```

Implementation: `grep_files` scans all session JSONL files. Wire `?search=` on the sessions listing URI to run grep and return matching session names with a snippet per match. Limit to 20 results by default; `--all` for full scan. Add to schema and help.

---

### BACK-075: Frontmatter adoption in reveal's own docs

**Status**: Skipped — low value (deferred indefinitely)
**Value**: Low | **Lift**: Low (docs-only)

`reveal 'markdown://docs/?aggregate=type'` is in WHY_REVEAL.md as a showcase example. Running it against reveal's own docs returns 2 of 44 files — the feature works but looks weak on its own documentation. The example only demonstrates the feature if the docs themselves are tagged.

Add `type:` frontmatter to the 42 docs that lack it, using the taxonomy already implied by INDEX.md: `guide`, `reference`, `adapter-guide`, `analyzer-guide`, `development`. Verify `?aggregate=type` returns a meaningful distribution.

---

### BACK-076: Wire Phase 3 import resolution into `build_callers_index`

**Status**: ✅ Shipped (session warming-ice-0316)
**Value**: Medium | **Lift**: Medium

`?uncalled` uses bare name matching against the callers index. A function imported under an alias (`from utils import helper as h`) is only called as `h` — the definition name `helper` never appears in the index, so it's incorrectly flagged as dead code.

Phase 3 already built `resolve_callees()` and `build_symbol_map()` which map import aliases to their resolved names. These are wired into the `ast://` adapter's element output but not into `build_callers_index`.

```python
# Current: index maps 'h' → caller record
# Fixed: index also maps 'helper' → same caller record (resolved via import graph)
```

Implementation: in `build_callers_index`, optionally call `build_symbol_map` per file and use `resolve_callees` to expand aliased calls to their canonical names before inserting into the index. Both resolved and bare names should be indexed (aliases could point to third-party names we don't want to falsely exclude).

This benefits `?uncalled` accuracy and also `?target=helper` (currently misses callers using the alias).

---

### BACK-077: `--validate-nginx` KeyError crash

**Status**: ✅ Shipped (session topaz-flash-0317)
**Value**: High | **Lift**: Small

`render_check()` had no routing branch for the `ssl_nginx_validation` result type. Every invocation of `--validate-nginx` crashed with a `KeyError` on `result['host']`. Added the missing branch. Also removed a duplicate `@staticmethod` decorator. 3 tests.

---

### BACK-078: OCSP URL availability in `--advanced`

**Status**: ✅ Shipped (session topaz-flash-0317)
**Value**: Medium | **Lift**: Small

`CertificateInfo` gains `ocsp_url: Optional[str]` extracted from the AIA extension via the `cryptography` library. `_check_ocsp_availability()` added to `_run_advanced_checks`; emits `info`-level finding. Let's Encrypt ECDSA certs (which dropped OCSP stapling in 2024) get a specific explanatory note. 4 tests.

---

### BACK-079: `letsencrypt://` adapter — orphan and duplicate cert detection

**Status**: ✅ Shipped (session xaxegotu-0319)
**Value**: High | **Lift**: Medium

Reveal already reads nginx configs and knows which `ssl_certificate` paths are in active use. A `letsencrypt://` adapter can cross-reference `/etc/letsencrypt/live/` against those paths to surface orphaned certs (present on disk but not referenced by any vhost) and duplicate certs (different paths, identical SANs).

```bash
reveal letsencrypt://                    # list all certs + expiry
reveal letsencrypt:// --check-orphans    # certs not referenced by any nginx ssl_certificate
reveal letsencrypt:// --check-duplicates # certs with identical SANs
```

Implementation: walks `/etc/letsencrypt/live/*/cert.pem`, reads SANs + expiry via the `cryptography` lib, joins against `extract_ssl_domains()` output from the nginx analyzer. No new dependencies. `certbot renew --dry-run` (command execution) is out of scope unless explicitly requested.

---

### BACK-080: Remote nginx HTTP probe mode

**Status**: ✅ Shipped (session bright-star-0319)
**Value**: Medium | **Lift**: Medium

Complement to `--validate-nginx`: instead of parsing config files locally, issue a live HTTP probe to a running nginx instance to verify redirect chains, ACME challenge paths, and header presence. Useful when config files are on a remote server or inside a container.

```bash
reveal ssl://example.com --probe-http     # follow redirect chain, verify HTTPS
reveal nginx://example.com --probe        # live HTTP vs config cross-check
```

---

### BACK-081: Refactor `_parse_xmla` — complexity 64

**Status**: ✅ Shipped (session kuzujuwe-0317, commit `8fa1e31`)
**Value**: Medium | **Lift**: Medium

Split into `_xmla_decode_root`, `_parse_xmla_tables`, `_parse_xmla_measures`,
`_parse_xmla_dim_id_map`, `_parse_xmla_end`, `_parse_xmla_relationships`.
`_parse_xmla` is now a ~15-line orchestrator. No behavior change.

---

### BACK-082: Refactor `_render_powerpivot` — complexity 34

**Status**: ✅ Shipped (session kuzujuwe-0317, commit `8fa1e31`)
**Value**: Low | **Lift**: Small

Split into `_render_powerpivot_tables`, `_render_powerpivot_schema`,
`_render_powerpivot_measures`, `_render_powerpivot_dax`,
`_render_powerpivot_relationships`. `_render_powerpivot` is now a ~25-line dispatcher.

---

### BACK-083: `calls://?uncalled` false positives for runtime-dispatched functions

**Status**: ✅ Shipped (session rainbow-aurora-0317) / revised copper-tint-0317
**Value**: Medium | **Lift**: Small

`# noqa: uncalled` suppression implemented in `find_uncalled` — checks the reported line and up to 3 lines forward (handles decorator-first reporting). Module-level call-site limitation documented. Stale FAQ corrected. 3 new tests. Revised (copper-tint-0317): removed 35+ `# noqa: uncalled` annotations from reveal's own codebase; feature kept but no longer advertised as a primary workflow. `CALLS_ADAPTER_GUIDE.md` false-positives section condensed.

---

### BACK-084: Split `_handle_validate_nginx_acme` text/json render paths — complexity 25

**Status**: ✅ Shipped (session fierce-pegasus-0319)
**Value**: Low | **Lift**: Small
**Location**: `reveal/file_handler.py:212`

77-line function with interleaved json/text output branches plus verbose handling. Complexity 25.

Refactor path: extract `_render_acme_json(results, only_failures)` and `_render_acme_text(results, analyzer, only_failures, verbose)`. `_handle_validate_nginx_acme` becomes ~20 lines of setup + dispatch.

---

### BACK-085: N008 — HTTPS server missing `Strict-Transport-Security`

**Status**: ✅ Shipped (session universal-journey-0319)
**Value**: High | **Lift**: Small
**Source**: Real tia-proxy audit (onyx-crystal-0318) — 46/46 sites affected

A server block listening on port 443 with no `Strict-Transport-Security` header. Browsers never pin to HTTPS; an intercepted first HTTP request can strip TLS for the entire session.

**Detection**: `listen 443` (or `listen [::]:443`) in server block + no `add_header Strict-Transport-Security` in block or any resolved `include`. Follows includes one level deep (reuses N003's snippet-following logic). Suppress with `# reveal:allow-no-hsts`.

**Finding format**:
```
N008  HIGH  'motion.mytia.net' (line 8): HTTPS site missing Strict-Transport-Security header
            Fix: add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

---

### BACK-086: N009 — `server_tokens` not disabled

**Status**: ✅ Shipped (session universal-journey-0319)
**Value**: Medium | **Lift**: Small
**Source**: Real tia-proxy audit (onyx-crystal-0318) — 32/46 sites affected

nginx defaults to `server_tokens on`, advertising `Server: nginx/1.18.0` on every response. Two lines in `nginx.conf` http{} fix all sites at once.

**Detection**: server block has no `server_tokens off` AND the main `nginx.conf` http{} block also lacks it (check global first; don't fire per-vhost if global is set). Requires reading `nginx.conf`.

**Finding format**:
```
N009  MEDIUM  'belize.mytia.net' (line 1): server_tokens not disabled
              Fix: add 'server_tokens off;' to nginx.conf http{} block (applies globally)
```

---

### BACK-087: N010 — Deprecated `X-XSS-Protection` header

**Status**: ✅ Shipped (session universal-journey-0319)
**Value**: Low | **Lift**: Small
**Source**: Real tia-proxy audit (onyx-crystal-0318) — 38/46 sites via shared snippet

`X-XSS-Protection` was removed from the W3C spec and ignored by Chrome since 2019. Its presence signals an outdated config.

**Detection**: `add_header X-XSS-Protection` in server block or any resolved include. When the header comes from a snippet, surface the snippet file path so the fix is obvious (editing one snippet fixes all 38 sites).

**Finding format**:
```
N010  LOW  'belize.mytia.net' via snippets/tia-security-headers.conf (line 6): X-XSS-Protection is deprecated
           Remove and add Content-Security-Policy instead.
```

---

### BACK-088: N011 — SSL listener without `http2`

**Status**: ✅ Shipped (session universal-journey-0319)
**Value**: Low | **Lift**: Small
**Source**: Real tia-proxy audit (onyx-crystal-0318) — 25/46 sites affected

`listen 443 ssl` without `http2` on the same line. Certbot's `--nginx` plugin consistently strips `http2` when it rewrites listen directives, creating a repeat pattern.

**Detection**: `listen 443 ssl` or `listen [::]:443 ssl` without `http2` on the same line. Suppress with `# reveal:allow-no-http2`.

**Finding format**:
```
N011  LOW  'patmatch.mytia.net' (line 9): SSL listener missing http2
           listen 443 ssl;  →  listen 443 ssl http2;
           (Certbot strips http2 when it rewrites listen directives — re-add after certbot runs)
```

---

### BACK-089: N012 — No rate limiting on server block

**Status**: ✅ Shipped (session universal-journey-0319)
**Value**: Low | **Lift**: Small
**Source**: Real tia-proxy audit (onyx-crystal-0318) — 45/46 sites affected

Without `limit_req`, server blocks are open to flood attacks and credential stuffing at full connection speed.

**Detection — two levels**:
- `limit_req_zone` is defined in nginx.conf but this server block has no `limit_req` anywhere (server or location level) → LOW
- No `limit_req_zone` defined anywhere → elevate to MEDIUM

**Finding format**:
```
N012  LOW  'belize.mytia.net': no rate limiting applied
           limit_req_zone is configured (admin_limit) but not used here
```

---

### BACK-090: `reveal nginx:// --audit` — fleet consistency matrix

**Status**: ✅ Shipped (session fierce-pegasus-0319)
**Value**: Medium | **Lift**: Medium
**Source**: tia-proxy fleet audit (onyx-crystal-0318)
**Design**: `internal-docs/planning/NGINX_FLEET_AUDIT_2026-03-18.md`

Fleet-level cross-site analysis: reads all enabled site configs + `nginx.conf`, produces a matrix showing where the fleet diverges from its own majority pattern.

```bash
reveal nginx:// --audit                    # full fleet consistency matrix
reveal nginx:// --audit --only-failures    # directives with gaps only
reveal nginx:// --audit --format json      # machine-readable
```

**Checks**: `server_tokens off`, `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `http2` on 443, `limit_req` applied, deprecated headers, snippet consistency.

**Consolidation hint logic**: if a directive appears in ≥50% of server blocks but NOT in `nginx.conf` http{}, flag as "consolidation opportunity — move to global block".

---

### BACK-091: `reveal nginx.conf --global-audit` — http{} block audit

**Status**: ✅ Shipped (session xaxegotu-0319)
**Value**: Medium | **Lift**: Small
**Source**: tia-proxy fleet audit (onyx-crystal-0318)
**Design**: `internal-docs/planning/NGINX_FLEET_AUDIT_2026-03-18.md`

Audits the global `nginx.conf` http{} block for missing security and operational directives.

```bash
reveal /etc/nginx/nginx.conf --global-audit
```

**Directives audited**: `server_tokens off` (MEDIUM), `Strict-Transport-Security` (HIGH), `X-Content-Type-Options` (MEDIUM), `X-Frame-Options` (MEDIUM), `ssl_protocols` (MEDIUM), `resolver` (LOW), `limit_req_zone` (LOW), `client_max_body_size` (LOW), `gzip on` (INFO), `worker_processes` (INFO).

Natural companion to `--audit` (BACK-090): `--audit` surfaces the fleet pattern, `--global-audit` surfaces what's missing from nginx.conf itself.

---

---

### BACK-092/093/094: OOM perf bugs in `reveal check` / `reveal health`

**Status**: ✅ **Resolved** — v0.64.x (strong-temple-0318)

- **BACK-092**: `_check_files_text` switched to `_run_parallel_streaming` (`as_completed` generator) — results processed as each future completes rather than buffering all. At most 4 results held in memory simultaneously.
- **BACK-093**: `collect_files_to_check` `excluded_dirs` expanded to include `.pytest_cache`, `.tox`, `.eggs`, `env`, `.benchmarks`, `.deepeval`, `.mypy_cache`, `.ruff_cache`, `.cache`, `.hypothesis`; `*.egg-info` dirs filtered by suffix.
- **BACK-094**: `_check_code()` in `health.py` now counts files before spawning subprocess; bails with exit 1 + actionable message if count > `_HEALTH_MAX_FILES` (5000). `timeout=120` added to `subprocess.run`. 8 new tests.

---

> **Status**: Strategic backlog. Not prioritized for implementation yet.

---

### BACK-098: Split `handlers.py` and `routing.py` into focused subpackages

**Status**: ✅ Shipped (session electric-ember-0320, commit `3d57caf`)
**Value**: Medium | **Lift**: Medium

`handlers.py` (1,104 lines) and `routing.py` (744 lines) were monolithic files accumulating unrelated concerns.

- `handlers.py` → `handlers/` package: `introspection.py` (informational flags), `batch.py` (stdin/batch), `decorators.py` (--decorator-stats)
- `routing.py` → `routing/` package: `uri.py` (adapter dispatch), `file.py` (file/dir routing)
- All re-exports preserved via `__init__.py`; 12 test patch targets updated to point at correct submodule.

---

### BACK-099: `reveal file.py :N` — extract the semantic unit at a line number

**Status**: ✅ Already shipped (pre-existing, confirmed working oracular-anvil-0320)
**Value**: Medium | **Lift**: Small

When you have a line number (from a traceback, `grep -n`, a GitHub link, a diff), you want the *enclosing semantic element* — not raw lines. This is distinctly Reveal's territory: grep gives you the line, Reveal gives you the function/class/section that owns it.

```bash
reveal reveal/analyzers/markdown.py :1027   # → extract_element() method
reveal tests/test_markdown_analyzer.py :1486 # → test_substring_match_ambiguous_raises()
reveal docs/ROADMAP.md :610                  # → BACK-090 section
```

**Implementation:**
- Detect `:N` syntax in the element argument (CLI + URI)
- Add `extract_element_at_line(n)` to base analyzer: walk element list, return element where `line_start <= N <= line_end`
- Edge case: line falls in module-level code (between named elements) → return nearest enclosing class, or a short window around the line
- All analyzers that carry line info (Python, JS, Ruby, Markdown, YAML, etc.) get this for free via base class

**Why it fits Reveal's core:** progressive disclosure from a line number — the same semantic-unit output as a named extraction, just addressed differently.

---

### BACK-100: `imports://src/?violations` — architecture layer enforcement

**Status**: ✅ Shipped (session stormy-river-0321, commit `3fe3c21`)
**Value**: High | **Lift**: Medium
**Surfaced**: toxic-xenon-0321 (article accuracy review)

Enforce that code respects defined architectural layers (presentation → application → domain → infrastructure). Any import that crosses a layer boundary in the wrong direction is a violation.

**How it works:**
1. User defines layers in `.reveal.yaml`:
   ```yaml
   layers:
     presentation: [src/api/, src/views/]
     application:  [src/services/]
     domain:       [src/models/]
     infrastructure: [src/db/, src/cache/]
   allowed_deps:
     presentation: [application]
     application:  [domain]
     domain:       []
     infrastructure: []
   ```
2. `reveal 'imports://src/?violations'` walks the import graph, classifies each file's layer, and flags any edge that violates the allowed_deps matrix.

**Expected output:**
```
============================================================
Layer Violations: 3
============================================================
  src/models/user.py:3 - domain importing infrastructure (src.db.session)
  src/api/routes.py:12 - presentation importing infrastructure (src.db.connection)
  src/services/auth.py:15 - application importing presentation (src.api.schemas)
```

**Why it matters:** Layer violations are the hardest structural problem to catch — they're syntactically valid, tests pass, but the codebase silently gains the wrong coupling. Static analysis + CI is the only reliable way to stop them from accumulating.

**Note:** The command already exists and returns a placeholder message. The `.reveal.yaml` config schema and the graph classification logic need to be built.

---

### BACK-101: Fix false positive circular deps from multi-dot inline relative imports

**Status**: ✅ Shipped (session stormy-river-0321, commit `6c57ba4`)
**Value**: Medium | **Lift**: Small
**Surfaced**: toxic-xenon-0321 (article accuracy review)

The Python import extractor misreports `level=0` for inline relative imports with multiple dots (`from ... import X`). The resolver then navigates 0 levels up instead of the correct number, resolving the import to the wrong `__init__.py` and creating a false cycle edge.

**Repro:** `reveal 'imports://reveal/cli/handlers/?circular'` reports:
```
reveal/cli/handlers/introspection.py → reveal/cli/handlers/__init__.py
```
But `introspection.py` has no imports pointing back to `handlers/__init__.py`. The false edge comes from `from ... import __version__ as _ver` (level 3) being extracted as level 0.

**Root cause:** The extractor that calls `extract_imports()` — wherever it handles inline (non-top-level) `from` statements — needs to correctly propagate the `level` attribute from the AST node to the `ImportStatement`. Top-level imports get this right; inline ones don't.

**Fix:** In the Python import extractor, ensure `ImportStatement.level` is set from the AST node's `level` field for all `from` statements, not just top-level ones.

---

### Additional Subcommands

Eight subcommands (`check`, `review`, `pack`, `health`, `dev`, `hotspots`, `overview`, `deps`) shipped. Remaining subcommand ideas:

```bash
reveal onboarding            # First-day guide for unfamiliar codebases
reveal audit                 # Security/compliance focus (S, B, N rules)
```

### Relationship Queries (Call Graphs)
- ✅ **`calls://` shipped v0.62.0** — `?target=fn`, `?callees=fn`, `?depth=N`, `?rank=callers`, `?format=dot`. See [CALLS_ADAPTER_GUIDE.md](reveal/docs/CALLS_ADAPTER_GUIDE.md).
- 🔲 **`depends://src/module/`** — inverse module dependency graph (what depends *on* this module, not just what this module imports). Different from `imports://` which is forward-only.

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

**Current**: 37 built-in analyzers + 165+ via tree-sitter fallback = 190+ languages total

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

### Implemented (23)
| Adapter | Description |
|---------|-------------|
| `ast://` | Query code as database (complexity, size, type filters) |
| `autossl://` | cPanel AutoSSL run logs — per-domain TLS outcomes, DCV failures |
| `calls://` | Cross-file call graph — callers, callees, coupling metrics, Graphviz export |
| `claude://` | Claude conversation analysis |
| `cpanel://` | cPanel user environments — domains, SSL certs, ACL health |
| `demo://` | Demo resources (internal/examples) |
| `diff://` | Compare files or git revisions |
| `domain://` | Domain registration, DNS records, health status + HTTP response check |
| `env://` | Environment variable inspection |
| `git://` | Repository history, blame, commits |
| `help://` | Built-in documentation |
| `imports://` | Dependency analysis, circular detection |
| `json://` | JSON/JSONL deep inspection |
| `letsencrypt://` | Let's Encrypt certificate inventory — orphan detection, duplicate SAN detection |
| `markdown://` | Markdown document inspection and related-file discovery |
| `mysql://` | MySQL database schema inspection |
| `nginx://` | Nginx vhost inspection — config file, ports, upstreams, auth, locations, fleet audit |
| `python://` | Python runtime inspection |
| `reveal://` | Reveal's own codebase |
| `sqlite://` | SQLite database inspection |
| `ssl://` | SSL/TLS certificate inspection |
| `stats://` | Codebase statistics |
| `xlsx://` | Excel spreadsheet inspection and data extraction |

### Planned
| Adapter | Notes |
|---------|-------|
| `depends://` | Inverse module dependency graph — what depends on this module (post-v1.0) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers, adapters, or rules.

**Good first contributions:**
- Language analyzer improvements
- Pattern detection rules
- Documentation and examples
