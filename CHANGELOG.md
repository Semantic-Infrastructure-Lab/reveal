---
title: Reveal Changelog
type: documentation
category: changelog
date: 2026-02-20
---

# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - v0.60.x (sessions toxic-onslaught-0310, ethereal-leviathan-0310, psychic-frenzy-0310, mystical-sword-0311, kilonova-throne-0311, eternal-launch-0311, turbo-ultimatum-0311, pattering-wind-0311)

### Added
- **BACK-014: `nginx://` adapter `get_schema()` — completes 21/21 adapter schema coverage** — `reveal help://schemas/nginx` now works. Schema covers all 8 output types (`nginx_sites_overview`, `nginx_vhost_summary`, `nginx_vhost_not_found`, `nginx_vhost_ports`, `nginx_vhost_upstream`, `nginx_vhost_auth`, `nginx_vhost_locations`, `nginx_vhost_config`), 5 elements, 7 example queries. `AGENT_HELP.md` updated from "20 of 21" to "all 21 adapters"; nginx and cpanel added to schemas listing. (session kilonova-throne-0311)
- **BACK-015: Comprehensive `nginx://` URI adapter tests** — 56 new tests in `tests/adapters/test_nginx_uri_adapter.py` covering: init/URI parsing, `get_schema()` completeness, overview mode, vhost-not-found handling, full vhost summary, all 5 element endpoints (ports/upstream/auth/locations/config), `get_available_elements()`, and 7 helper unit test classes (`_extract_ports`, `_extract_upstreams_referenced`, `_find_upstream_definitions`, `_extract_auth_directives`, `_extract_location_blocks`, `_detect_warnings`, `_resolve_symlink_info`). Tests: 4,696 → 4,752. (session kilonova-throne-0311)
- **BACK-009: `markdown://` body text search via `?body-contains=`** — `reveal 'markdown://docs/?body-contains=nginx'` searches file body content (text after frontmatter) rather than frontmatter fields. Case-insensitive substring match. Multiple `body-contains=` params are AND'd (all terms must appear). Combines cleanly with frontmatter filters (`type=guide&body-contains=nginx`) and result control (`limit=`, `sort=`). Files without frontmatter are also matched. Implemented in `files.read_body_text()`, `filtering.matches_body_contains()`, extracted from query string before legacy/new filter parsing. 9 new tests.
- **BACK-007: Local SSL cert file validation from nginx config** — `reveal ssl://nginx:///path/to/config --check --local-certs` parses `ssl_certificate` directives from nginx config files and validates each referenced cert file directly on disk — no network connection required. Reports expiry status (pass/warning/failure) per cert file with domain names, CN, issuer, and days until expiry. Deduplicates by cert path (one report per unique file even across multiple server blocks). Complements the existing domain-check mode (`--check` without `--local-certs`, which connects to live servers). `NginxAnalyzer` now also exposes `extract_ssl_cert_paths()` and `_parse_server_block` now captures `cert_path`/`key_path` from `ssl_certificate`/`ssl_certificate_key` directives. 15 new tests.
- **BACK-003: XLSX cross-sheet search** — `reveal xlsx://file.xlsx?search=pattern` scans every sheet in the workbook and returns matching rows (case-insensitive) with sheet name, row number, and cell content grouped by sheet. `?search=X&limit=N` caps total results. Result type `xlsx_search`; JSON output supported. Also fixes a silent bug in `XlsxAnalyzer._get_cell_value`: inline-string cells (`t="inlineStr"`, used by openpyxl and similar) returned empty string — now resolved correctly. 18 new tests.
- **BACK-006: WHOIS integration for `domain://`** — `reveal domain://example.com/whois` now returns full WHOIS data (registrar, creation/expiry dates, nameservers, status, DNSSEC). Domain overview (`reveal domain://example.com`) now includes a Registration section showing registrar + dates. `/registrar` element also enriched with WHOIS fields. `python-whois` is an optional dep (`pip install reveal[whois]`); if absent, all three outputs degrade gracefully with an install hint. 11 new tests.

### Fixed
- **BACK-016: `json://` error message now shows plain path** — `reveal json:///path/to/file.py` previously showed `"JSON file not found: json:/path/to/file.py"` (with spurious `json:` scheme prefix). Root cause: `_try_full_uri_init` passes full URI `json:///path` to `JsonAdapter`, and `Path('json:///path')` normalizes to `PosixPath('json:/path')`. Fix: `parse_path()` now strips `json://` prefix when present. Error message is now `"Error: file.py is not valid JSON."` with a suggestion. 3 new regression tests. (session kilonova-throne-0311)
- **`stats://` path always showed `.`** — renderer used `result.get('path', '.')` but the Output Contract stores the path under `source`. `"Codebase Statistics: ."` now shows the actual directory. Regression test added.
- **`imports://` path always showed `.`** — `_render_import_summary` defaulted to `resource='.'`. Now reads `result.get('source', resource)` for display. Verified absolute and relative paths both show correctly.
- **BACK-001: bare integer / `:N` line nav now consistent** — `reveal file.py 73` and `reveal file.py :73` previously errored with "No element found" when the target line was outside any named element (imports, module-level code). Now falls back to a ±10-line context window so every line reference returns something useful. `_extract_line_range` also now clamps `end_line` to file length instead of failing.
- **BACK-005: `ast://` unknown filter key now hints** — `reveal 'ast://src/?badkey=foo'` previously returned silent 0 results. Now emits "not a recognized filter key — valid keys: complexity, decorator, lines, name, size, type". Known-shorthand hints (`?functions → ?type=function`) unchanged.
- **BACK-008: `git://dir/` error message** — terse error when a directory path is given now explains expected repo-root form with absolute path example.
- **BACK-012: L003 false positives on Django/Flask projects** — `_detect_framework()` now recognises Django (`manage.py` + django import) and Flask (`from flask import` / `Flask(__name__)`). Routes in those projects are dynamic and can't be validated against the filesystem; L003 now skips them entirely instead of flagging every route as broken. Default framework fallback changed from `'fasthtml'` to `'static'` (safer for projects with no detectable framework). 6 new tests.
- **BACK-010: explicit `level` field in `ImportStatement`** — relative import levels now tracked explicitly rather than inferred, improving code clarity in the resolver.
- **BACK-011: `analyzer` passed directly to `_handle_outline_mode`** — removed redundant re-resolution that previously used `None`.

### Added (session kilonova-throne-0311 continued)
- **`autossl://` and `cpanel://` schemas enriched with `example_queries` + `notes`** — both schemas were missing `example_queries` entirely, an AI-agent discoverability gap. autossl gets 4 examples + 5 notes; cpanel gets 6 examples + 4 notes. (session kilonova-throne-0311)
- **Adapter contract tests expanded from 14 → 20 adapters** — `tests/test_adapter_contracts.py` now tracks all non-demo adapters: autossl, cpanel, domain, nginx, ssl, xlsx added. New `test_all_adapters_have_get_schema` verifies that all 20 adapters return a valid schema dict with `adapter` and `output_types` keys. Tests: 4,755 → 4,756. (session kilonova-throne-0311)
- **Schema `example_queries` enrichment sweep** — all 19 adapters (excluding meta `help://`) now have complete example coverage: `domain://` added `/whois` + `/registrar` (was missing 2 of 4 elements); `python://` added `imports` + `debug/bytecode` (listed in elements but absent from examples); `env://` expanded from 3 → 5 (json format + jq pipeline); `xlsx://` added `?search=` cross-sheet examples (BACK-003 feature); `imports://` added single-file scan example. (session kilonova-throne-0311)

### Added (session kilonova-throne-0311, continued)
- **All 19 non-demo/help adapter schemas now have `notes` arrays** — 8 schemas were missing notes: ast, ssl, stats, json, markdown, xlsx, env, reveal. Notes surface adapter-specific behavior, gotchas, and usage patterns to AI agents consuming `help://schemas/<adapter>`. Each adapter now has 4–7 notes. (session kilonova-throne-0311)
- **Schema contract tests enforce `notes`, `example_queries`, and `uri` key** — `test_all_adapters_have_get_schema` now asserts: `notes` is a non-empty list; `example_queries` exists; each example uses `uri` key (not `query`). Prevents regressions on new adapters shipping with incomplete schemas. (session kilonova-throne-0311)
- **Element coverage audit: all static elements now have example queries** — ssl (/subject, /issuer, /dates, /full), mysql (/performance, /variables), claude (/timeline, /context), python (/env) were all listed in `elements{}` but absent from `example_queries`. Added 8 missing examples across 4 adapters. AI agents can now discover all element endpoints from the schema alone. (session kilonova-throne-0311)
- **AGENT_HELP.md schema example updated** — example schema in "Machine-Readable Schemas" section now shows the `notes` field and the "What you get" list explicitly includes notes as a discoverable field. (session kilonova-throne-0311)
- **`output_types` schema completeness audit — 19 missing types added** — 7 adapter schemas had example_queries referencing output types not listed in `output_types`. Fixed: ssl (+4: ssl_subject, ssl_issuer, ssl_dates, ssl_full), xlsx (+1: xlsx_search), mysql (+2: mysql_performance, mysql_variables), python (+1: python_bytecode), domain (+3: domain_whois, domain_registrar, domain_health), reveal (+1: code_element), claude (+7: claude_user_messages, claude_assistant_messages, claude_thinking, claude_message, claude_timeline, claude_context, claude_search_results). Total: 77 output types across 19 adapters. (session kilonova-throne-0311)
- **Contract tests enforce output_type reference consistency** — `test_all_adapters_have_get_schema` now verifies each `example_queries[n].output_type` resolves to a defined entry in `output_types`. Cross-adapter references (e.g., `domain/ssl` returning `ssl_certificate`) are explicitly whitelisted. (session kilonova-throne-0311)

### Fixed (session kilonova-throne-0311, continued)
- **6 invalid `ast://` filter params in `help://examples` recipes** — `kind=function` (not a real ast:// filter) replaced with `type=function` in 5 recipes. `visibility=public` recipe replaced with `type=class&sort=name`. `has_docstring=false` recipe replaced with `type=function&lines>50&sort=-lines`. (session kilonova-throne-0311)
- **Invalid `git://src?since=7days` in debugging recipe** — `since` is not a `git://` query param; replaced with `git://.?type=history`. (session kilonova-throne-0311)

### Fixed (session kilonova-throne-0311 continued)
- **3 unused imports removed via `imports://` self-scan** — `import sys` (dev.py), `import subprocess` (pack.py), `import socket` (N007.py) were genuinely unused. Discovered by running `reveal 'imports://reveal/?unused'` on the reveal codebase itself. (session kilonova-throne-0311)
- **`help://examples` (no slash) now shows task list** — previously "Element not found"; now "Specify a task. Available: ...". `help://examples/` improved from "Unknown task ''" to "Specify a task". (session kilonova-throne-0311)
- **`help://schemas/` now lists available adapters** — previously "No adapter named ''"; now "Specify an adapter. Available: ...". (session kilonova-throne-0311)
- **`help://schemas/help` now gives explicit error** — "HelpAdapter does not provide a machine-readable schema. This is expected for meta-adapters like help://". Previously returned None → "Element not found". (session kilonova-throne-0311)
- **`help://schemas/badname` error includes adapter list** — "No adapter named 'xlxs'. Available: ast, autossl, ..." with `available_adapters` array in JSON output. AI agents can now programmatically discover valid adapter names from any schema error. (session kilonova-throne-0311)

### Fixed (session eternal-launch-0311)
- **`help://examples/*` and `help://schemas/*` rendered as stubs** — `query_recipes` and `adapter_schema` result types were not registered in `render_help()`'s dispatch table, so both fell through to `_render_help_adapter_specific` which produced only a header stub (no content). Added `_render_query_recipes` (shows task + recipe list with goal/query/description/output_type) and `_render_adapter_schema` (shows uri_syntax, query_params, elements, output_types, example_queries, cli_flags, notes). Both registered. (session eternal-launch-0311)
- **`help://schemas` (no trailing slash) routed to wrong static guide** — bare `schemas` matched `SCHEMA_VALIDATION_HELP.md` before hitting the schemas listing route. Added `topic == 'schemas'` check alongside existing `topic == 'schemas/'`. (session eternal-launch-0311)
- **`help://schemas` bare and `help://examples` bare showed stderr errors, not listings** — both routes returned an error dict with `available_adapters`/`available_tasks`. Renderers now treat these as listing mode (no adapter/task name supplied); unknown adapter/task names still exit(1). (session eternal-launch-0311)
- **`help://schemas/unknown_adapter` showed listing, not error** — renderer's `if available_adapters:` check didn't distinguish "bare listing" from "unknown name listing". Fixed: only show listing when `adapter == ''`; unknown names show error + exit(1). (session eternal-launch-0311)
- **5 recipe output_type names didn't match schema definitions** — `ast_query_results` → `ast_query` (12 occurrences), `git_log` → `git_ref`, `stats_results` → `stats_summary`, `links` → `markdown_query`, `outline` → `markdown_query`. The contract test `test_recipe_output_types_resolve_to_schema_types` now enforces alignment. (session eternal-launch-0311)
- **`_render_adapter_schema` crashed on markdown/cpanel query_params** — those adapters use flat string values in `query_params` (e.g. `'body-contains=term': 'description...'`). Renderer now handles both dict and string param values. (session eternal-launch-0311)

### Fixed (session turbo-ultimatum-0311)
- **`stats://src --only-failures` in quality recipe was silently a no-op** — `--only-failures` is not implemented in the stats adapter (check/batch mode only); it was listed as a CLI flag and cited in schema notes without effect. Quality recipe replaced with `stats://src?hotspots=true` which actually shows files with issues. stats schema `--only-failures` flag removed; replaced with `--hotspots` and `--format=json` which work. (session turbo-ultimatum-0311)
- **ast schema claimed complexity "heuristic-based (line count proxy)"** — outdated since tree-sitter was added. Proper McCabe cyclomatic complexity is calculated for all 50+ tree-sitter languages; line-count heuristic is only the fallback for unsupported languages. Schema note updated to reflect reality. (session turbo-ultimatum-0311)
- **ast text output groups by file, making `sort=` invisible** — text renderer always groups results by filename (alphabetical). Sort IS applied to the underlying data (verifiable via `--format=json` or `--format=grep`). Added schema note: "text output groups results by file; use --format=json or --format=grep for globally sorted output". (session turbo-ultimatum-0311)
- **Cross-field OR syntax broken in RECIPES.md** — `reveal 'ast://./src?complexity>30|lines>150'` returns 0 results because `|` is for same-field OR only (e.g., `type=function|class`). "Find god functions" recipe fixed to use `&` (AND). (session turbo-ultimatum-0311)
- **AGENT_HELP.md jq pipeline used wrong field names** — `file_path` → `file`, `line_number` → `line`, `select(.depth > 10)` → `select(.complexity > 10)` (depth is nesting depth, not cyclomatic complexity). (session turbo-ultimatum-0311)
- **`imports://` schema missing false positive warning** — decorator-based registration imports (e.g., `from . import adapter` in `__init__.py`) are flagged as unused but are intentional side-effect imports. Added schema note. (session turbo-ultimatum-0311)
- **`reveal://rules` listed utility modules as rules** — `get_rules()` discovered all `.py` files in rule category directories, including `validation/utils.py` and `validation/adapter_utils.py`. Fix: skip files not starting with uppercase (rule codes are always uppercase-first: V001, B001, etc.). Validation category: 23 → 21 actual rules. (session turbo-ultimatum-0311)

### Tests (session turbo-ultimatum-0311)
- **`test_rules_exclude_utility_modules`** — asserts `utils` and `adapter_utils` not present in rules list; also asserts all rule codes start with uppercase. Prevents recurrence of the utility-as-rule bug. Tests: 4,770 → 4,771. (session turbo-ultimatum-0311)

### Tests (session eternal-launch-0311)
- **16 new `TestHelpAdapter` tests** — cover all new/fixed routes: `help://schemas` listing, `help://schemas/ast` data and rendering, `help://schemas/unknown_adapter` error + stderr, `help://examples` listing, `help://examples/quality` data and rendering, all 6 task categories validation. Tests: 4,768 → 4,770. (session eternal-launch-0311)
- **`TestHelpSystemContracts` — 3 new contract tests** — `test_recipe_output_types_resolve_to_schema_types` prevents recipe/schema drift; `test_all_example_tasks_have_recipes` guards empty categories; `test_all_adapter_schemas_render_without_error` catches renderer regressions across all adapters. (session eternal-launch-0311)

### Documentation
- **AGENT_HELP.md** — bare integer line nav (`reveal file.py 73`) added to line-number section and quick-reference table.
- **AGENT_HELP.md — 'Inspect nginx vhost configuration' task section (16th)** — Covers all 7 `nginx://` views, "when to use" table, and cross-adapter workflow (nginx + ssl, nginx + domain). (session kilonova-throne-0311)
- **`help://examples/` — `infrastructure` and `documentation` recipe categories** — `reveal help://examples/infrastructure` returns 6 recipes for nginx vhost inspection, nginx overview, upstream health, SSL cert check, nginx SSL from config path, and domain health. `reveal help://examples/documentation` returns 5 recipes for markdown body-contains search, frontmatter filter, body+sort combo, link validation, and outline view. Error listing for unknown tasks now includes all 6 categories. (session kilonova-throne-0311)

### Refactored (session pattering-wind-0311)
- **9 high-complexity functions decomposed across 8 files** — functions with complexity>15 dropped from 30 → 3. All 4771 tests pass. Quality: 97.3 → 97.4/100. Functions: 2280 → 2327.
  - `autossl/parser.py`: `parse_run` (complexity 49) → `_process_indent0/1/2/3`, `_parse_log_lines`, `_build_user_list`
  - `adapters/domain/adapter.py`: `_check_http_response` (40) → `_NoRedirect`, `_follow_redirect_chain`, `_classify_http_check`, `_aggregate_http_checks`
  - `rendering/adapters/help.py`: `_render_adapter_schema` (40) → 9 `_render_schema_*` section helpers
  - `cli/routing.py`: `_apply_claude_display_hints` (38) → `_apply_slice`, `_apply_workflow_filters`, `_apply_session_list_filters`, `_apply_messages_slice`; `handle_file_or_directory` (28) → 4 guard functions + 2 routing helpers; eliminates duplicate head/tail/range slice logic
  - `file_handler.py`: `_handle_cpanel_certs` (40) → `_load_disk_cert`, `_load_live_cert`, `_cert_match_label`, `_format_disk/live/match_col`; `_handle_validate_nginx_acme` (23) → `_format_acl_col`, `_format_acme_ssl_col`, `_fetch_acme_ssl_data`
  - `adapters/ssl/renderer.py`: `_render_ssl_cert_file_validation` (28) → `_render_cert_file_failures/warnings/passes` static methods
  - `cli/commands/review.py`: `_render_report` (26) → 5 section renderers
  - `tree_view.py`: `show_file_list` (27) → `_collect_matching_files`, `_sort_files`

---

## [0.60.0] - 2026-03-10

### Added (session earthly-phoenix-0310)
- **`nginx://` URI adapter** — domain-centric nginx vhost inspection (21st adapter). Closes the documented-but-unimplemented gap (Issue 3 in REVEAL_ISSUES_REPORT.md, v0.54.4). `reveal nginx://domain` finds the config file by `server_name`, parses it, and shows a structured summary: config file + symlink status, ports (80/443, SSL, redirect), upstream servers + TCP reachability, auth directives, location blocks with targets. Sub-paths: `/ports`, `/upstream`, `/auth`, `/locations`, `/config`. `reveal nginx://` lists all enabled sites. Searches `/etc/nginx/sites-enabled/` and `/etc/nginx/conf.d/` automatically. Zero extra dependencies.
- **`domain://` HTTP response check** — `--check` now makes actual HTTP/HTTPS requests and reports status codes + redirect chains, closing the gap where `--check` validated DNS and SSL cert but never hit the endpoint. Shows `HTTP (80): 301 → https://... (200)` style output. On failure or wrong-service redirect, suggests `reveal nginx://domain` as next step. Sourced from `docs/tools/reveal/REVEAL_NGINX_RUNTIME_FEEDBACK.md` (session zayiyu-0310).

### Fixed (session spinning-asteroid-0310)
- **`nginx://` glob pattern** — `_find_config_for_domain` and overview mode used `*.conf` glob, missing all extension-less files in `sites-enabled/` (42 of 44 vhosts on tia-proxy). Now uses `_iter_nginx_configs()` which mirrors nginx's own include logic: `sites-enabled/` takes all files; `conf.d/` takes `*.conf` only; backup/temp files (`.bak`, `.backup-*`, `.old`) are excluded everywhere. Found during tia-proxy validation.
- **`nginx://` nested location parsing** — `_parse_server_block_for_domain` regex handled only 1 level of brace nesting, causing the SSL server block to be missed when config used nested `location ~*` inside `location /`. Extended to 3 levels of nesting. Symptom: adapter reported "No HTTPS listener" for configs that had `listen 443 ssl`. Found during tia-proxy validation (frono.mytia.net).
- **`nginx://` stability promoted to Beta** — adapter validated against 44 real vhosts on tia-proxy; 0 errors, all domains resolved correctly. Stability updated from Experimental → Beta.

## [0.59.0] - 2026-03-03

### Added (sessions jeruya-0303, amethyst-prism-0303)
- **`CpanelAdapter.get_schema()`** — all 20 URI adapters now support `help://schemas/<adapter>`. Covers all 4 cpanel output types (`cpanel_user`, `cpanel_domains`, `cpanel_ssl`, `cpanel_acl`) with triggered_by, description, and full JSON Schema properties. `reveal help://schemas/cpanel --format=json` now works.
- **`--help` argument groups** — replaced the flat 70+ flag wall with 12 named sections surfacing the flag taxonomy documented in ADAPTER_CONSISTENCY.md: Output [global], Discovery, Navigation, Display, Type-aware output, Quality checks, Universal adapter options, Markdown, HTML, Schema validation, SSL adapter, Nginx/cPanel adapter. No behavior change; extracted `_add_global_options()` helper so subcommand parsers still inherit globals via `parents=`.

### Documentation (session jeruya-0303)
- **CLI flag taxonomy** — ADAPTER_CONSISTENCY.md updated with explicit three-tier breakdown: global / universal / adapter-specific flags, plus new "Adapter-Specific Flags vs Query Parameters" section with architectural principle, current-vs-target migration table, and guidance for adapter authors.
- **QUERY_PARAMETER_REFERENCE.md** — fixed stale "Adapters Without Query Parameters" section: split into adapters using element paths (correct) vs adapters with flags-as-workaround (migration candidates: cpanel://, ssl://, claude://). Named `ast://` as the reference implementation.
- **QUERY_SYNTAX_GUIDE.md** — added architectural note in "when to use flags" section cross-linking to ADAPTER_CONSISTENCY.md.

## [0.58.0] - 2026-03-03

### Added (session opal-tint-0303)
- **`autossl://` adapter** — inspect cPanel AutoSSL run logs at `/var/cpanel/logs/autossl/`. `reveal autossl://` lists available runs; `reveal autossl://latest` parses the most recent run, showing per-user/per-domain TLS outcomes (ok/incomplete/defective), defect codes (CERT_HAS_EXPIRED, DEPTH_ZERO_SELF_SIGNED_CERT), and DCV impediment codes (TOTAL_DCV_FAILURE, NO_UNSECURED_DOMAIN_PASSED_DCV). `reveal autossl://TIMESTAMP` parses a specific run. `--format=json` for scripting. 20th URI adapter.

## [0.57.0] - 2026-03-03

### Added (session zaheye-0303)
- **`reveal health --all`** — auto-detects health check targets from context: first checks `.reveal.yaml` `health.targets`, then falls back to common source dirs (`src/`, `lib/`, `app/`, or top-level Python package), then `.`. No more slow `reveal health .` on large repos.
- **`health.targets` config support** — `.reveal.yaml` can declare `health: targets: [src/, ssl://api.example.com]` for `--all` to use.
- **`claude:// --base-path DIR`** — override `CONVERSATION_BASE` at runtime: `reveal claude:// --base-path /mnt/wsl/.claude/projects`. Enables use with WSL, mounted volumes, Zack/Mark Windows machines, or any non-default Claude session directory. Works for session listing and individual session lookup.

### Fixed (session zaheye-0303)
- **`reveal pack` key-directory scoring** — `'main'` substring was falsely matching `maintainability`, causing all rules in that directory to score +2.0 as "key modules". Now uses whole-path-component matching (`Path.parts` set intersection), fixing `reveal/rules/maintainability/*.py` files from being over-scored.
- **Mypy cleanup — 121 → 0 errors**: Phase 1 (121→33): `get_structure` return type, treesitter class-level attrs, adapter signature fixes. Phase 2 (33→0): str()/cast() for no-any-return, typed variables for StructureOptions returns, `parse_host_port` return type fix, unused `type: ignore` removal across 19 files.

### Fixed (session prism-tone-0303)
- **`--sort modified` alias for `'mtime'`** — `reveal dir/ --files --sort modified` and `reveal dir/ --sort modified` were silently ignored because `'modified'` wasn't a recognized sort key in `tree_view.py`. Now accepted as an alias for `'mtime'` in both `show_file_list` and `_get_sorted_entries`.

### Added (session techno-thrasher-0303)
- **Parser inheritance consistency** — `review`, `health`, `pack` parsers now use `parents=[_build_global_options_parser()]`, matching `check`. All 4 subcommand parsers now inherit `--format`, `--copy`, `--verbose`, `--no-breadcrumbs` uniformly.
- **`--check` one-implementation rule** — routing.py `--check` path now calls `run_check(args)` from `commands/check.py` directly, eliminating dead code duplication. `handle_recursive_check` import removed.

### Added (session ultra-warmonger-0303)
- **`reveal dev` subcommand** — developer tooling: `reveal dev new-adapter`, `new-analyzer`, `new-rule` (wraps scaffold), `reveal dev inspect-config` (shows effective `.reveal.yaml`).
- **`reveal review` subcommand** — PR review workflow. Orchestrates diff + check + hotspots + complexity into a unified report. Supports git range syntax (`reveal review main..feature`) and path syntax (`reveal review ./src`). `--format json` for CI/CD gating.
- **`reveal health` subcommand** — unified health check across code, SSL, databases, DNS. Routes by target type. Exit codes: 0=pass, 1=warn, 2=fail. Composable: `reveal health ./src ssl://example.com`.
- **`reveal pack` subcommand** — token-budgeted context snapshot for LLM consumption. `--budget N` (tokens) or `--budget N-lines`. `--focus TOPIC` weights matching files. Prioritizes entry points → key modules → recency. `--verbose` shows per-file token/line counts.
- **`--sort -field` syntax** — `reveal 'markdown:///path/' --sort -modified` now works. argv preprocessing converts space-form to `=` form before argparse.
- **CLI flags sections in `help://` topics** — `help://ssl`, `help://nginx`, `help://markdown`, `help://html` each show a "CLI Flags" section listing adapter-specific flags with descriptions. `_render_help_cli_flags()` added to help renderer.

### Fixed
- **SSL batch flags error-with-hint** — `--expiring-within`, `--summary`, `--validate-nginx` now fail with a helpful error and `ssl://` URI hint when used on local paths.
- **Markdown `--related` error-with-hint** — `--related`, `--related-all` now fail with helpful error when used on non-markdown files.

## [0.56.0] - 2026-03-03

### Added (session celestial-mage-0303)
- **`reveal check` subcommand** — canonical entry point for quality checks. `reveal check ./src` replaces `reveal ./src --check`. Clean namespace, own `--help`, own `--rules`/`--explain`. 8 flags removed from global `--help` (`--check`, `--select`, `--ignore`, `--only-failures`, `--recursive`, `--config`, `--no-group`, `--advanced`).
- **`_build_global_options_parser()`** — shared parent parser. Subcommands inherit `--format`, `--copy`, `--verbose`, `--no-breadcrumbs`, `--disable-breadcrumbs` via `parents=` without re-declaration. Foundation for all future subcommands.
- **`reveal check --help`** — subcommand-specific help with examples and rule category reference.
- **`--check` deprecation hint** — `reveal ./src --check` still works, but prints `hint: --check is deprecated; use reveal check <path>` to stderr. Non-breaking transition.
- **Nginx/cPanel error-with-hint guards** — `--diagnose`, `--check-acl`, `--validate-nginx-acme`, `--check-conflicts`, `--cpanel-certs` now fail with a helpful error message when used on non-nginx files (e.g., `.py`, `.js`, `.md`). Follows the `--hotspots` pattern. Flags still work on `.conf` files.
- **Subcommands in `reveal --help`** — epilog now shows `reveal check <path>` as the modern form.

## [0.55.0] - 2026-03-03

### Added (sessions enigmatic-wave-0303, solar-observatory-0303)
- **`--files` — flat file listing replacing `find dir/ | sort -rn`** — shows all files sorted by mtime (newest first) with timestamps. Combines with `--ext`, `--sort`, `--asc`/`--desc`. Respects `.gitignore` and `--exclude` patterns. Replaces the most common shell one-liner in TIA workflow.
- **`--ext EXTS` — extension filter** — comma-separated extensions (e.g., `--ext md` or `--ext py,md`). Works on directory trees and `--stdin` pipelines. Case-insensitive, leading-dot-tolerant.
- **`--sort FIELD` extended** — now works with `--files` (sort by `mtime`, `size`, `name`) in addition to existing code element sorting. `--sort name --files` gives alphabetical listing.
- **`--desc` / `--asc` flags** — explicit sort direction. `--files` defaults newest-first; `--asc` reverses to oldest-first. `--sort modified --desc` in element views sorts descending.
- **`--sort` injects into URI query string** — `reveal stats://. --sort complexity --desc` now passes `sort=-complexity` to adapter automatically; no need to embed sort in the URI manually.
- **`--meta` on directories** — shows summary: file count, total size, modification range, breakdown by extension. Outputs JSON with `--format json`.

## [0.54.8] - 2026-03-02

### Fixed (session distant-voyage-0302)
- **B8 — `claude://tools` showed counts only, no commands** — `get_all_tools()` now captures `detail` via `_extract_tool_detail()` for every tool call (preferred: Claude's description; fallback: `command[:80]`). Renderer shows up to 8 details per tool with "...and N more" for longer lists. Previously "Bash: 58 calls" told you nothing; now you see the actual commands run.
- **Bash command truncation 60→80** — `_extract_tool_detail()` raw command fallback extended to 80 chars so full reveal URIs and common compound commands fit without mid-argument truncation.

## [0.54.7] - 2026-03-02

### Fixed (session obsidian-kaiju-0302)
- **Issue 3 — `claude://sessions` errored with "Conversation not found for session: sessions"** — `sessions` was parsed as a session name and fell through to `_load_messages()`. Added `sessions` and `sessions/` to the early-exit guards in `get_structure()`, routing to `_list_sessions()` (mirrors the existing `search` guard).
- **Issue 4 — Session overview showed raw UUID, no title** — `get_overview()` now derives a `title` from the first user message: first line, max 100 chars, handles both string content and list-of-items content. Renderer prints it below the session name. `None` when no user text is found (overview still works).
- **Issue 5 — `help://claude` try_now used `$(basename $PWD)` bash substitution** — replaced with static example session name (`infernal-earth-0118`) plus a `reveal claude://` listing entry. Added two notes explaining how to get the current session name on bash/zsh (`basename $PWD`) and PowerShell (`Split-Path -Leaf $PWD`).

## [0.54.6] - 2026-03-02

### Fixed (session jewaha-0302)
- **B6 — `claude://` listing inflated by subagent files** — `_list_sessions()` was including `agent-*.jsonl` subagent files as duplicate session entries (2841 phantom sessions on a typical TIA machine; 45 on Frono). Now skips any JSONL file whose stem starts with `agent-`.
- **B7 — `_find_conversation()` fragile agent-file ordering** — strategy 1 was relying on alphabetic ordering (`0` < `a`) to accidentally return the main JSONL over agent files. Now explicitly filters agent files from the candidate list before picking `[0]`.
- **B2 — `claude://search?query=` returned "session not found"** — `search` was parsed as a session name, causing a confusing error. Now caught before `_load_messages()` and returns a structured `claude_error` with a hint pointing to `tia search sessions "<term>"`.

## [0.54.5] - 2026-03-01

### Fixed (session charcoal-glow-0301)
- **N003 false positives — `include` snippets not resolved** — `_find_proxy_headers()` now follows `include` directives in proxy location blocks. Resolves paths relative to the config file's directory then the nginx root (e.g. `/etc/nginx/snippets/tia-proxy-headers.conf`). If the included file contains the required headers, N003 is suppressed. If the include exists but can't be read, N003 is also suppressed (can't verify → no false positive). Bare locations with no include and no headers still fire. Eliminated 17 false positives across 4 vhost configs on tia-proxy.
- **N001 false positives — no way to mark intentional shared backends** — Added `# reveal:allow-shared-backend` annotation. Any upstream block containing this comment is excluded from the duplicate-backend map entirely. N001's suggestion text now tells users about the annotation. Allows intentional aliasing (e.g. staging alias for a dev node) without noise.
- **`nginx://` URI scheme in `help://nginx` and `ssl.yaml`** — The scheme is not implemented; `reveal nginx://...` returns "Unsupported URI scheme". Removed unimplemented `nginx://` examples from `HelpAdapter` and one stray reference in `ssl.yaml`. Replaced with working file-path equivalents.

### Added (session charcoal-glow-0301)
- **N007: ssl_stapling without OCSP responder URL** (LOW) — Detects server blocks with `ssl_stapling on;` whose certificate has no Authority Information Access / OCSP extension. When present, nginx silently ignores stapling and logs a warning; TLS handshakes degrade because clients must fetch OCSP directly. Rule reads the `ssl_certificate` file and checks for an OCSP URL (via `cryptography` library if available, DER byte-scan fallback). Gracefully suppresses when the cert is unreadable (cert may live on a remote host). Fires with suggestion to remove `ssl_stapling` or replace the cert.

## [0.54.4] - 2026-02-27

### Fixed (session aqua-shade-0227)
- **V023 false positive — `ResultBuilder.create()` pattern** — V023 was flagging `get_structure()` in `ast/adapter.py` as non-compliant because it checks for `'contract_version':` dict literal syntax; `ResultBuilder.create(contract_version='1.1', ...)` uses kwargs. V023 now skips when `ResultBuilder.create(` appears in the method body.
- **V023 false positive — delegating adapters** — `git/adapter.py` `get_structure()` delegates all paths to module-level helpers (`return files.get_file_history(...)`, `return refs.get_ref_structure()`, etc.) with no direct dict return. V023 now skips when all returns are `module.func(...)` calls with no literal `return {`.
- **Broken anchor links in INDEX.md** — two stale `#adapter-guides-16-files` links (updated heading is now 18 files). Was causing `test_all_docs_have_valid_internal_links` to fail.

### Added (session aqua-shade-0227)
- **Batch checker warning on skipped files** — `file_checker.py` now logs `WARNING: check: skipped <path> — ExceptionType: message` when a file is skipped due to an analyzer exception during `--check` runs. Previously silent; analyzer crashes now surface for debugging.

### Changed (session aqua-shade-0227)
- **Type annotations** — added full type annotations to `xml_analyzer.py` (`_filter_xml_children`), `graphql.py` (7 tree-sitter helper methods), `hcl.py` (3 methods), `protobuf.py` (11 methods; `_get_rpc_types` and `_get_rpc_streaming` now have precise `Tuple` return types).
- **CSV sniffer logging** — `csv_analyzer.py` now logs at DEBUG level when `csv.Sniffer` fails and the extension-based fallback is used.

## [0.54.3] - 2026-02-27

### Fixed (sessions infernal-lightning-0227, ninja-force-0227)
- **B3 — N004 quoted ACME root paths** — `.strip('"\'')` applied to ACME root in N004 messages; cPanel nginx configs quote all `root` directives, causing `'"/home/..."'` double-wrapped display and false-positive path mismatches. Messages now show bare paths; quoted and unquoted forms treated as equal.
- **I001 false positive — `__init__.py` broad catches** — B006 rule incorrectly flagged `except Exception` in `__init__.py` registration functions. `__init__.py` imports are always public API; broad catches there are intentional. B006 now skips `__init__.py` files.
- **V023 false positive — dispatcher delegation** — V023 fired on `return self._delegate_method(...)` patterns where the method is a dispatcher, not a dead branch. V023 now skips `return self._` patterns (delegation by convention).

### Added (sessions infernal-lightning-0227, ninja-force-0227)
- **U6 — `cpanel://USERNAME/ssl --dns-verified`** — DNS-verified mode for cpanel ssl element: domains with no DNS record (NXDOMAIN) are shown with a `[nxdomain]` tag but excluded from critical/expiring summary counts. Eliminates false alarms from former-customer domains whose DNS has moved away. Detection uses `socket.getaddrinfo` (stdlib only, no subprocess).

### Documentation (session ninja-force-0227)
- **CPANEL_ADAPTER_GUIDE.md** — new comprehensive guide for the `cpanel://` adapter: all four elements, `--dns-verified` with annotated example output, JSON scripting patterns, 6-step SSL audit workflow, and filesystem paths reference.
- **NGINX_ANALYZER_GUIDE.md** — new comprehensive guide for nginx file analysis: all 6 rules (N001–N006) with real-world context, all operator flags, domain extraction pipeline, 7-step SSL failure diagnosis workflow.

## [0.54.2] - 2026-02-27

### Fixed (session peaceful-aurora-0227)
- **B1 — `--validate-nginx-acme` ACL always `not_found` on cPanel configs** — `_parse_location_root` and `_parse_server_root` returned `m.group(1)` raw; cPanel nginx configs quote all root directives (`root "/home/user/public_html";`), so `Path('"..."')` never existed → every domain reported `not_found`. Fixed with `.strip('"\'')` in both methods. Feature is now functional on production cPanel gateways.
- **U1 — `nginx:///` four-slash URIs in cpanel next_steps** — `cpanel://` overview and `get_help()` suggested `reveal nginx:///path` which fails in subprocesses (only works in shell where one slash is consumed). Replaced all instances with plain file paths (`reveal /path/to/nginx.conf`), consistent with `reveal help://nginx` guidance.

### Added (session peaceful-aurora-0227)
- **U3 — `--validate-nginx-acme --only-failures`** — `--only-failures` flag now respected by `--validate-nginx-acme`. On 500+ domain configs the full output is 89KB; filter suppresses passing rows and prints `✅ No failures found.` when everything passes.
- **U4 — doc note: cpanel ACL vs nginx ACME audit** — added note to `reveal help://cpanel`: "cpanel ACL check is filesystem-based (authoritative); nginx ACME audit also verifies config routing — use both". Clarifies which to trust and why results can differ.
- **U5 — cpanel graduated 🔴 Experimental → 🟡 Beta** — adapter produced accurate results in production (found 3 denied domains in 2s, correct next steps). B1 was in the nginx analyzer, not cpanel. Updated renderer and `get_help()` stability field.

## [0.54.1] - 2026-02-27

### Fixed (session serene-current-0227)
- **`reveal help://cpanel` — "Element not found"** — `CpanelAdapter` inherited `get_help()` from base (returns `None`); added full `get_help()` implementation with examples, elements, and operator workflow.
- **`reveal help://nginx` — "Element not found"** — nginx is a file-based analyzer (not a URI adapter); added `_get_file_analyzer_help()` to `HelpAdapter` returning focused usage help for known file analyzers.
- **V016 not firing via `reveal reveal:// --check`** — added `_check_reveal_adapters()` so V016 scans adapter files when called with `file_path.startswith('reveal://')`.

## [0.54.0] - 2026-02-27

### Added (session magnetic-regiment-0227)
- **nginx: S4 — `--cpanel-certs`** — `reveal nginx:///etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs` compares cPanel on-disk certs (`/var/cpanel/ssl/apache_tls/DOMAIN/combined`) against live certs per SSL domain. Serial number comparison detects "AutoSSL renewed but nginx hasn't reloaded" (shows `⚠️ STALE (reload nginx)`). Table: domain | disk cert expiry | live cert expiry | match status. Exit 2 on stale or expired certs.
- **nginx: S3 — `--diagnose`** — `reveal nginx:///path/user.conf --diagnose` scans the nginx error log for ACME/SSL failure patterns (Permission Denied on `/.well-known/`, ENOENT, SSL cert load errors) grouped by SSL domain with count and last-seen timestamp. Auto-detects error_log path from config directive or cPanel defaults; `--log-path PATH` overrides. Exit 2 on permission_denied or ssl_error hits. Retroactively diagnoses incidents already in the log.
- **cpanel:// adapter** — First-class cPanel user environment adapter. `reveal cpanel://USERNAME` shows domain count and SSL summary. `reveal cpanel://USERNAME/domains` lists all addon/subdomain domains with docroots and type. `reveal cpanel://USERNAME/ssl` shows S2 disk cert health for every domain (`/var/cpanel/ssl/apache_tls/DOMAIN/combined`). `reveal cpanel://USERNAME/acl-check` runs N1 nobody ACL check on every domain docroot. All filesystem-based; no WHM API or credentials needed. Composes S2/S3/S4/N1 into a single `cpanel://` namespace for cPanel operator workflows.

### Added (session meteoric-armada-0227)
- **nginx: N3 — `--domain` filter** — `reveal nginx:///path/user.conf --domain DOMAIN` filters output to only the server block(s) matching DOMAIN, including all server_name aliases. Essential for navigating 1,500-line cPanel user configs with one block per domain. Passes as `get_structure(domain=...)` kwarg; no extra request.
- **nginx: N2 — `--check-conflicts`** — detects location block routing surprises: `prefix_overlap` (one non-regex location is a strict prefix of another) and `regex_shadows_prefix` (a regex location pattern can match a prefix location's path). Groups by server block, includes line numbers and human-readable explanations. Exit 2 on regex conflicts; info-only for prefix overlaps.
- **ssl: S2 — cert file inspection** — `reveal ssl://file:///var/cpanel/ssl/apache_tls/DOMAIN/combined` loads and inspects an on-disk PEM or DER certificate without a live connection. PEM combined files (leaf + chain) are split; chain count surfaced. Same health/expiry/SAN display as live cert. Next steps suggest `reveal ssl://DOMAIN --check` for disk-vs-live comparison.
- **nginx: `--validate-nginx-acme`** — composed audit command: per-domain table of ACME root path + nobody ACL status + live SSL certificate status in one invocation. Chains `extract_acme_roots()` (N4) with `check_ssl_health()` per domain. Exit 2 on any ACL failure or SSL expiry. The single command that would have caught and explained the Feb 2026 Sociamonials incident.

### Added (session tropical-sleet-0227)
- **ssl: S1 — batch failure detail** — `--batch --check` now shows failure reason inline: expired certs show `EXPIRED N days ago (Mon DD, YYYY)`, connection errors classified as `DNS FAILURE (NXDOMAIN)`, `CONNECTION REFUSED`, `TIMEOUT`, `NETWORK UNREACHABLE`, `CERT VERIFY FAILED`. All rows column-aligned to max hostname width. Eliminates follow-up loop per domain.
- **ssl: S5 — expiry dates in batch output** — warnings show `expires in N days  (Mon DD, YYYY)`, healthy domains show `N days  (Mon DD, YYYY)`. Date derived from `not_after` field, no extra request needed.
- **nginx: N1 — `--check-acl`** — checks that the `nobody` user has read+execute access to every `root` directive in the config. Checks standard Unix `other` permission bits on each path component; falls back to `getfacl` for ACL entries. Deduplicates paths; exits 2 on any failure.
- **nginx: N4 — `--extract acme-roots`** — finds `/.well-known/acme-challenge` location blocks, resolves the root path (location-level or server-level fallback), runs nobody ACL check on each. Outputs aligned table: `domain → acme root path → ACL status`. The "SSL audit for cPanel nginx" command — would have identified the Feb 2026 Sociamonials incident in one command.

### Fixed (session tropical-sleet-0227)
- **release script: CHANGELOG extractor** — awk range pattern had two bugs: unescaped dots in version number matched any character, causing the range end to collide with the start line (empty output). New approach: `found=1; next` skips header, prints body, exits on next `## [`.

## [0.53.0] - 2026-02-27

### Added (session revodoku-0227)
- **`--check` grouped output** — when a rule fires ≥ 10 times in a single file, results collapse to one summary line + "+N more occurrences hidden" note. Keeps 2,685 N003s from burying 6 actionable N004s in cPanel-managed configs. Applies to both single-file and recursive check.
- **`--no-group` flag** — disables result collapsing; expands every occurrence individually (for scripts that parse full output).
- **Auto-generated file skip** — files containing `# reveal: generated`, `# Generated by ...`, `# @generated`, or `# This file is automatically generated` in the first 15 lines are silently skipped in recursive `--check` sweeps. Single-file check still runs but prints a notice. Use `# reveal: generated` in cPanel-managed configs to remove them from directory-wide reports.
- **nginx: N006 rule** (HIGH severity) — flags dangerous `send_timeout`/`proxy_read_timeout`/`proxy_send_timeout` < 60s when `client_max_body_size` > 10m. This exact combination caused the Sociamonials Feb 2026 media upload incident (30s timeout + 200m body size = silent upload failures). Includes estimated max transfer size at current timeout and minimum recommended value.

## [0.52.0] - 2026-02-27

### Added (session clever-zenith-0227)
- **nginx: main context directives** — `_parse_main_directives()` extracts depth-0 directives (`user`, `worker_processes`, `worker_rlimit_nofile`, `error_log`, `pid`, `include`) from `nginx.conf`, and `ssl_protocols`, `ssl_ciphers`, `client_max_body_size`, `server_names_hash_*` from vhost include files. Surfaced as `main_directives` key.
- **nginx: multi-line directive support** — `_parse_block_directives()` now accumulates continuation lines until the terminating `;`. Fixes `log_format` spanning 9 lines in prod — previously silently dropped.
- **nginx: upstream backend detail** — `_parse_upstream_servers()` reads each upstream block body, extracting `server` entries (address + params like `max_fails`, `fail_timeout`) and settings (`keepalive`, `keepalive_timeout`, `keepalive_requests`). Upstream items now carry a `signature` with backend hostname for display.
- **nginx: map{} block detection** — detects `map $src $target { }` blocks. Surfaced as `maps` list with `source_var`/`target_var`. Captures the 5 `$host`-routing maps in `ea-nginx.conf` (cPanel/WHM pattern).
- **display: Main directives label** — `_render_single_category()` extended to handle `main_directives` dict; long values (ssl_ciphers etc.) truncated at 80 chars for display.

### Added (session valley-flood-0227)
- **nginx: http{} and events{} directives** — `get_structure()` now surfaces all direct-child key-value directives from the `http {}` and `events {}` blocks as `directives` and `events_directives` dict keys. Previously, a main `nginx.conf` containing only global timeout/buffer/proxy settings (no `server {}` blocks) returned only a file header — all directives were invisible.
- **nginx: N005 rule** — new check flags timeout and buffer directives outside safe operational ranges (e.g. `send_timeout < 10s`, `proxy_read_timeout > 300s`, `client_body_buffer_size > 64m`). Covers: `send_timeout`, `proxy_read_timeout`, `proxy_send_timeout`, `proxy_connect_timeout`, `keepalive_timeout`, `client_body_timeout`, `client_header_timeout`, `client_body_buffer_size`, `proxy_buffer_size`, `client_max_body_size`.
- **display: dict-type category rendering** — `_render_single_category()` handles `directives` and `events_directives` as key-value tables rather than silently dropping them.

## [0.51.1] - 2026-02-20

### Fixed
- **Cross-platform CI** — all 6 matrix jobs (Python 3.10/3.12 × Ubuntu/macOS/Windows) now pass
- **Claude adapter conversation search** — split `_find_conversation` into two sequential passes so TIA-style directory names (Strategy 1) are always checked before UUID filename matches (Strategy 2), preventing filesystem-order-dependent failures
- **DNS adapter** — added missing `dnspython>=2.0.0` dev dependency; tests patched `HAS_DNSPYTHON=True` but the module was never imported
- **V009 symlink resolution** — replaced `Path.resolve()` (which follows symlinks, causing `/var` → `/private/var` on macOS) with `os.path.normpath()` plus an explicit null-byte guard
- **V003 / stats adapter** — used `.as_posix()` for relative paths to ensure forward-slash separators on Windows
- **Diff adapter** — parse Windows drive-letter paths (e.g. `C:\...`) via `parse_diff_uris()` wrapped in try/except instead of short-circuiting on the `:` character
- **Scaffold `rule.py`** — added `encoding='utf-8'` to all `write_text()` / `read_text()` calls to avoid `charmap` errors on Windows
- **V002/V007/V011/V015/validation chmod tests** — skipped on Windows (`pytest.mark.skipif`) since `chmod(0o000)` is a no-op on that platform

## [0.51.0] - 2026-02-20

### Performance
- **I002 shared graph across parallel workers** — `ProcessPoolExecutor` previously triggered up to 4 independent import-graph builds (one per worker). The main process now pre-builds the graph once, pickles it, and seeds each worker's `_graph_cache` via the pool `initializer`. Workers get a cache hit on the first file they check; CPU cost drops from 4× to 1× with no change in wall-clock time. Graceful degradation: if the pre-build fails, workers fall back to building their own graph as before.
- **I002 import-graph cache fix** — `_build_import_graph` was keyed on each file's parent directory, so a project with N subdirectories triggered N full tree-sitter scans instead of 1. Cache is now keyed on the project root (resolved via `.git` → `pyproject.toml` → `__init__.py` boundary). Serial I002 cost on a 73-subdir project: 13 min → 33s. Also fixes a correctness gap: the old per-subdir scan missed cycles that cross package boundaries.
- **`--check` parallelism** — `reveal --check dir/` now uses `ProcessPoolExecutor` (4 workers) to check files in parallel. Wall-clock time on a 3,500-file project: 48s → 21.5s (2.2×). Worker count capped at 4 after empirical benchmark sweep showed 74% of max speedup at 4 workers vs marginal gains beyond that (commits 1298515, 891f9bd)
- **O(n²) rule scan eliminated** — `RuleRegistry.check_file` was iterating all rules for every file even after an early-exit condition; fixed to short-circuit correctly. Large projects went from many minutes → ~30s before parallelism (commit faa09d4)
- **Per-file micro-optimizations** — 8 targeted fixes: cache `Path.resolve()`, pre-compile glob patterns once, reuse `RuleRegistry` instance across files, avoid re-parsing markdown for link rules. Net: 8.3s → ~5.6s user time on reveal's own codebase (commits 25c42f9, 5d52a0a)

### Security
- **Zip bomb protection** — `.docx`/`.xlsx`/`.pptx` files are now checked before extraction: decompressed size capped at 50 MB and compression ratio capped at 1000×. Crafted archives that would cause OOM are rejected with a clear error (commit 8569c47)
- **File size guard** — `_read_file()` now rejects files larger than 100 MB before reading, preventing OOM from `/dev/zero` or similar (commit 8569c47)
- **MySQL URL parsing** — replaced custom `@`-split parser with `urlparse`+`unquote`; passwords containing `@` or `:` were previously silently misparsed and caused connection failures (commit 8569c47)
- **Frontmatter eval hardening** — `safe_builtins` can no longer be shadowed by frontmatter field values (e.g., `len: evil`); expression length capped at 200 chars (commit 8569c47)
- **SSL timeout propagation** — user-configured timeout now threads through `_run_advanced_checks()` instead of being hardcoded to 10s (commit 8569c47)

### Added
- **claude:// content views** - `/user`, `/assistant`, `/thinking`, `/message/<n>` routes now render actual content instead of falling through to the fallback `[list with N items]` renderer (commit 78505b2)
  - `/user` — first message as full prompt text (1200 char limit), subsequent turns as `[N tool result(s)]`
  - `/assistant` — text blocks only with `[thinking]`/`[tools: Bash]` metadata per message; truncates at 600 chars with `/message/<n>` pointer
  - `/thinking` — all thinking blocks with content preview (800 chars), char count, token estimate
  - `/message/<n>` — single message by index, full text with block-level fallback for non-text content
- **claude:// ?search=** - `reveal "claude://session/name?search=term"` searches all content: text blocks, thinking blocks, tool inputs; returns matches with role/block_type/timestamp/excerpt context windows (commit 78505b2)
- **String content normalization** - fixed char-iteration bug where initial user prompt stored as bare `str` would produce one output block per character in `/user`, `/assistant`, and `?search=` routes; content is now normalized to `[{type:text, text:...}]` before iteration (commit 78505b2)
- **claude:// adapter guides** - Quick Start, Elements Reference, and Query Params sections updated in `CLAUDE_ADAPTER_GUIDE.md`; inline `_get_help_examples` and `_get_help_workflows` updated with new examples (commit f9ae167)

### Tests
- Added 3 regression tests for I002 cache-key fix: project-root resolution via `.git`, shared cache across sibling subdirectories, and no false-positive for unresolved cross-package imports (`TestI002ProjectRootCache` in `tests/test_rules.py`)
- Added 67 unit tests for `analysis/messages.py` covering `_extract_text`, `_content_to_blocks`, `_find_excerpt`, `search_messages`, `filter_by_role` str-content fix, `get_thinking_blocks`, `get_message` (new file: `tests/adapters/test_claude_analysis.py`)
- Added 27 renderer tests for 5 new renderers: `_render_claude_thinking`, `_render_claude_user_messages`, `_render_claude_assistant_messages`, `_render_claude_message`, `_render_claude_search_results`

### Fixed
- **ast:// OR logic** - `name=*run*|*process*` now returns the union of matches for all fields (was only `type=` field) (commit 0f861b2)
- **ast:// import noise** - `name=*X*` glob no longer returns import declarations; use explicit `type=import` to find imports (commit 0f861b2)
- **--check recursive** - `reveal dir/ --check` now runs recursively like ruff/mypy instead of exiting with an error (commit 0f861b2)
- **M102 false positive** - `_find_package_root` two-pass walk now climbs to `pyproject.toml` before falling back to `__init__.py` boundary, fixing wrong module name resolution in nested packages (commit 0f861b2)
- **I004 false positive** - Shadowing rule no longer fires for files nested ≥2 levels deep in subpackages (commit 0f861b2)
- **--check paths** - File paths in `--check` output are now relative to CWD, not to the scan target (commit 0f861b2)
- **claude:// UUID sessions** - Sessions with UUID IDs are now found via JSONL filename lookup, not just project dir name matching (commit 0f861b2)
- **claude:// session list** — `reveal claude://` now renders sessions as a table (id, date, title) instead of a collapsed dict (commit 77407b3)
- **--agent-help-full** — flag was broken after AGENT_HELP consolidation; restored correct file lookup (commit 1000fca)
- **D001 false positives** — duplicate function detection now scopes to the containing class; `setUp`/`tearDown` in different test classes no longer flagged as duplicates (commit 086d98b)
- **`--check` build artifact noise** — `build/` and `dist/` directories are now excluded from recursive checks alongside `.git`, `__pycache__`, `node_modules` (commit 086d98b)

### Changed
- **B003 threshold** - Raised from 8→15 lines; 8 was flagging legitimate computed properties in real-world code (commit 0f861b2)
- **T004 severity** - Downgraded HIGH→MEDIUM; missing `Optional[]` annotations are a style/compat issue, not a runtime bug (commit 0f861b2)

### Added
- **--explain thresholds** - `reveal --explain B003` now shows threshold values, `.reveal.yaml` config guidance, and a compliant code example (commit 0f861b2)
- **--select T category** - T (Types) rules now listed in applicable categories for Python files and in `--select` help text (commit 0f861b2)

- **Element extraction** - `[0.50.0]` and `v1.2.3` in element position no longer trigger confusing "Looking for '0]' within '[0.50'" hierarchical error. Regex now requires both sides of `.` to start with `[A-Za-z_]` (commit d3c2307)
- **diff:// errors** - Error messages now include expected format and examples when separator colon is missing (commit 2d9b7b8)
- **--stdin patch detection** - Piping `git diff` (not `--name-only`) to `reveal --stdin` now emits a single clear error with the correct command, instead of N "not found, skipping" warnings (commit 2d9b7b8)
- **markdown:// single-file** - Passing a file path to `markdown://` now shows a helpful error directing to `reveal <path>` instead of a garbled "Directory not found" message (commit 2d9b7b8)
- **Bare integer line reference** - `reveal file.py 200` now jumps to line 200, matching editor/grep convention; the `:` prefix is no longer required (commit 309ecab)
- **--check dir/ false negative** - `reveal --check dir/` previously exited 0 and showed the tree, masking a no-op. Now exits 1 with guidance to use `--recursive` or `find | --stdin --check` (commit 309ecab)
- **imports:// single-file cycles** - `imports://single-file.py` now shows "N/A (single-file scan)" for Cycles Found instead of a misleading "✅ No" (commit 309ecab)
- **ast:// unknown shorthand filter** - `?functions`, `?classes`, etc. now print a hint suggesting the correct syntax (`?type=function`) instead of silently returning 0 results (commit 309ecab)
- **git:// directory path** - `reveal git://dir/` now includes guidance ("For repo overview use: reveal git://") in the error message (commit 309ecab)

### Removed
- Deleted 6 stale `.old` adapter files (`ast.py.old`, `diff.py.old`, `json_adapter.py.old`, `markdown.py.old`, `reveal.py.old`, `stats.py.old`) — pre-refactor monoliths, ~5400 lines of dead weight (commit 309ecab)

### Tests
- Added 4 regression tests for element syntax parsing covering `[0.50.0]`, `v1.2.3`, `1.2.3.4` (not hierarchical) and `FileAnalyzer._read_file` (still hierarchical) (commit a72dc25)
- Added 3 regression tests for bare integer line reference parsing (`200`, `1`, `9999`) (commit 309ecab)

## [0.50.0] - 2026-02-16

### Added
- **MySQL Adapter** - Added `mysql:///tables` endpoint for table I/O statistics and hotspot detection
  - Reveals table-level read/write counts, timing, and read:write ratios
  - Automatic alerts: extreme_read_ratio (>10K:1), high_read_volume (>1B reads), long_running (>1 hour)
  - Progressive disclosure pattern: `/tables` overview → `/tables/{name}` detail (future)
  - Token-efficient (~300-500 tokens vs 2000+ for raw SQL)
  - Real production impact: Detected 28.5 hour table hotspot with 490K:1 read ratio
  - Follows existing patterns: snapshot context, performance_schema reset detection
  - Comprehensive test coverage: 5 new tests covering routing, alerts, and data processing

### Fixed
- **Windows CI** - Resolved 19 of 22 Windows test failures (86% success rate)
  - PermissionError (14 tests): Improved file cleanup with GC, retries, readonly handling
  - UnicodeDecodeError (4 tests): Added explicit UTF-8 encoding to all file operations
  - Platform-specific tests: Skip chmod tests on Windows where behavior differs
- **Encoding** - Added `encoding='utf-8'` to 10+ files across codebase for cross-platform compatibility

## [0.49.3] - 2026-02-15

### Added
- **Documentation** - Added 12 comprehensive adapter guides with real-world examples
  - `AST_ADAPTER_GUIDE.md` - Abstract Syntax Tree introspection and structure analysis
  - `CLAUDE_ADAPTER_GUIDE.md` - AI session analysis (messages, tools, workflows, files touched)
  - `DIFF_ADAPTER_GUIDE.md` - Git diff analysis and structural change comparison
  - `DOMAIN_ADAPTER_GUIDE.md` - Domain infrastructure validation (SSL, DNS, WHOIS)
  - `ENV_ADAPTER_GUIDE.md` - Environment variable analysis and tracking
  - `GIT_ADAPTER_GUIDE.md` - Git repository introspection and history analysis
  - `IMPORTS_ADAPTER_GUIDE.md` - Import dependency analysis and visualization
  - `JSON_ADAPTER_GUIDE.md` - JSON data structure exploration with querying
  - `MYSQL_ADAPTER_GUIDE.md` - MySQL schema and query analysis
  - `SQLITE_ADAPTER_GUIDE.md` - SQLite schema and data exploration
  - `SSL_ADAPTER_GUIDE.md` - SSL/TLS certificate validation and server configuration
  - `STATS_ADAPTER_GUIDE.md` - Codebase statistics and project metrics
- **Validation** - Added M105 rule for detecting orphaned CLI handlers (CLI_INTEGRATION_GUIDE.md)
- **Help System** - Implemented hybrid auto-discovery for guide files (improved help output)

### Fixed
- **Documentation Accuracy** - Fixed 33 broken internal links across adapter guides
  - Corrected markdown anchor formatting for GitHub compatibility
  - Replaced references to moved/reorganized files
  - Updated cross-references in ADAPTER_CONSISTENCY.md
- **Type Safety** - Fixed 15 mypy type errors (improved static analysis)
- **Test Suite** - Fixed failing documentation validation test (ADAPTER_CONSISTENCY.md links)

### Changed
- **Documentation Organization** - Improved structure and navigation
  - Moved internal-docs outside public git repo (cleaner separation)
  - Reorganized planning and design documents by function
  - Enhanced frontmatter documentation (clarified JSON format support)
- **Code Quality** - Internal improvements for maintainability
  - Reduced complexity in Claude adapter analysis tools
  - Converted wildcard imports to explicit imports
  - Documented production TODOs for tracking

### Internal
- **Test Coverage** - Continued expansion of test suite (Phase 10 completion)
  - `reveal/utils/query.py`: 77% → 95% (+37 tests) - Query parsing, filtering, budgets
  - `reveal/adapters/stats/adapter.py`: 95% → 100% (+3 tests) - Perfect coverage
  - `reveal/rules/validation/V002.py`: 80% → 100% (+10 tests) - Analyzer registration
  - Sessions: ascending-observatory-0215, expanding-station-0215, valley-whirlwind-0215, rofuvoke-0215, and 6 more (10 phases total)

## [0.49.2] - 2026-02-14

### Added
- **Test coverage** - Added comprehensive tests for utility modules (45% → 46%+ overall)
  - **Phase 1** (session yoxumema-0214):
    - `reveal/result.py`: 0% → 100% (51 tests, 67 lines) - Success/Failure monads, chaining, error handling
    - `reveal/utils/uri.py`: 0% → 97.7% (76 tests, 86 lines) - URI parsing (all schemes), auth, IPv4/IPv6
    - `reveal/utils/validation.py`: 28.2% → 100% (65 tests, 56 lines) - Path, type, range, port validators
    - `reveal/errors.py`: 55.6% → 100% (57 tests, 36 lines) - Custom exceptions, suggestions, context
    - Subtotal: 249 tests, 245 lines, 3440 tests passing (was 3191)

  - **Phase 2** (session viral-zenith-0214):
    - `reveal/utils/results.py`: 0% → 100% (41 tests, 59 lines) - Output Contract v1.x result builders
    - `reveal/utils/formatting.py`: 14% → 100% (10 tests, 7 lines) - Human-readable file sizes
    - `reveal/utils/clipboard.py`: 21% → 100% (13 tests, 14 lines) - Cross-platform clipboard (xclip/xsel/pbcopy/clip)
    - `reveal/utils/json_utils.py`: 45% → 100% (15 tests, 11 lines) - DateTime JSON serialization
    - `reveal/utils/path_utils.py`: 17% → 100% (32 tests, 36 lines) - Directory traversal, project root detection
    - `reveal/utils/safe_operations.py`: 25% → 100% (43 tests, 52 lines) - Graceful failure decorators/context managers
    - `reveal/utils/updates.py`: 9% → 100% (14 tests, 35 lines) - PyPI update checking with caching
    - Subtotal: 168 tests, 214 lines, 7 modules at 100%

  - **Phase 3** (session cunning-wizard-0214):
    - `reveal/cli/handlers.py`: 11% → 73% (20 tests, 254 lines) - CLI handlers for special modes
      - Simple handlers: list_supported, adapters, explain_file, capabilities, show_ast, language_info
      - Agent help: agent_help, agent_help_full (success and missing file cases)
      - Schema: handle_schema, _get_schema_v1 (default, explicit, unknown versions)
      - Batch helpers: aggregate_stats, group_by_scheme, filter_display, status_indicator, exit_code
      - Stdin processing: process_stdin_file (not found, directory, success)
    - `reveal/adapters/diff/renderer.py`: 67% → 100% (1 test, 7 lines) - Diff adapter error rendering
      - ValueError error handling with usage examples
    - Subtotal: 21 tests, 261 lines, 2 modules improved

  - **Phase 4** (session obsidian-jammer-0214):
    - `reveal/adapters/help_data/__init__.py`: 68% → 100% (8 tests, 12 lines) - Help data loader
      - Error paths: missing file, empty file, YAML parse errors, general exceptions
      - Cache functionality and clear_cache() method
      - Convenience function load_help_data()
    - `reveal/adapters/stats/analysis.py`: 67% → 98% (9 tests, 14 lines) - Stats analysis helpers
      - find_analyzable_files() with code_only filter (excludes data/config files, large JSON)
      - analyze_file() error handling (no analyzer, exceptions)
      - get_file_display_path() variants (single file, relative, absolute)
    - `reveal/structure_options.py`: 82% → 100% (10 tests, 7 lines) - StructureOptions dataclass
      - Initialization with defaults and custom values
      - from_kwargs() with known/unknown fields (extra dict)
      - to_dict() conversion, filtering, and roundtrip
    - Subtotal: 27 tests, 33 lines, 3 modules improved (2 to 100%, 1 to 98%)

  - **Phase 5** (session howling-ice-0214):
    - `reveal/rules/infrastructure/N004.py`: 88% → 100% (5 tests, 7 lines) - ACME path consistency
      - SSL server without ACME location tracking
      - _get_server_name edge cases (no directive, empty value)
      - _find_listen_line with/without listen directive
    - `reveal/rules/validation/V004.py`: 85% → 100% (5 tests, 6 lines) - Test coverage gaps
      - find_reveal_root returning None, non-dev checkout detection
      - Missing tests/ and analyzers/ directory handling
      - Analyzer without test file detection
    - `reveal/rules/links/L005.py`: 86% → 100% (3 tests, 9 lines) - Cross-reference density
      - Suggestions included when related docs exist
      - Current file excluded from suggestions, duplicate removal
    - `reveal/rules/validation/V001.py`: 88% → 100% (7 tests, 9 lines) - Help documentation completeness
      - find_reveal_root None, analyzer missing expected help
      - Referenced help file doesn't exist, no analyzers/help.py
      - STATIC_HELP dict not found, exception handling
    - `reveal/rules/validation/V008.py`: 89% → 100% (5 tests, 9 lines) - Analyzer signatures
      - find_reveal_root None, parse error handling
      - Missing **kwargs and base params detection
    - Subtotal: 25 tests, 40 lines, 5 modules at 100%

  - **Phase 6** (sessions defixo-0215, crackling-thunder-0215):
    - `reveal/display/element.py`: 48% → 100% (43 tests, 133 lines) - Element extraction display
      - Syntax parsing: ordinal (@N, type:N), line (:N, :N-M), hierarchical (Class.method)
      - Extraction routing: ordinal, line range, single line, hierarchical, name-based
      - Grep fallback when TreeSitter unavailable
      - Error handling: typed ordinal, line, hierarchical, name-based extraction failures
      - Hierarchical extraction: parent/child not found, multi-level rejection, successful extraction
      - Line-based extraction: non-TreeSitter analyzers, no match, invalid ranges, exception handling
      - Markdown section extraction: no headings, target before first heading, section middle, end calculation
      - Ordinal edge cases: structure exception, category no match, invalid items, non-TreeSitter source
      - Output formats: JSON, grep, human (with line numbers)
    - `reveal/display/formatting.py`: 35% → 71% (81 tests, 220 lines) - Formatting output & utilities
      - **Utility functions** (23 tests, 45 lines): set_nested, _find_list_field, _extract_nested_value, _filter_single_item_fields, _preserve_metadata, filter_fields
      - **Frontmatter formatting** (6 tests): None/empty, scalar/list/dict values display
      - **Link formatting** (5 tests): Normal/broken/domain links, grep format, grouping by type
      - **Code block formatting** (8 tests): Fenced blocks, inline code, grep format, grouping by language
      - **Related document formatting** (12 tests): Exists/error states, nested docs (recursive), stats counting, flat paths, various output modes
      - **CSV schema formatting** (3 tests): Basic info, sample values, truncation
      - **XML children formatting** (7 tests): Tags, attributes, text/children, nesting (recursive), truncation
      - **Kwargs builders** (17 tests): Navigation, markdown links/code, HTML extraction args
    - `reveal/cli/scaffold/adapter.py`: 14% → 100% (11 tests, 42 lines) - Adapter scaffolding commands
      - Basic scaffolding (adapter, test, doc files), name/class/scheme normalization
      - Existing files handling (error without force, overwrite with force)
      - Directory creation, reveal root finding (found/not found)
    - `reveal/cli/scaffold/analyzer.py`: 12% → 98% (11 tests, 48 lines) - Analyzer scaffolding commands
      - Basic scaffolding (analyzer, test, doc files), extension/name/class normalization
      - Helper functions (_to_class_name, _to_module_name)
      - Existing files handling, reveal root finding via __init__.py
    - `reveal/cli/scaffold/rule.py`: 9% → 98% (11 tests, 52 lines) - Rule scaffolding commands
      - Basic scaffolding (rule, test, doc files), code/category normalization
      - Prefix/severity mapping (B=HIGH, E=LOW, F/C/D/M/V=MEDIUM, S=HIGH, N=LOW, unknown=MEDIUM)
      - __init__.py creation/preservation, RulePrefix enum for known prefixes
    - `reveal/adapters/domain/dns.py`: 14% → 97% (22 tests, 74 lines) - DNS resolution and validation
      - get_dns_records (all record types: A, AAAA, MX, TXT, NS, CNAME, SOA), exception handling
      - get_dns_summary (nameservers, a_records, has_mx, error handling)
      - check_dns_resolution (IP resolution via socket, pass/failure status)
      - check_nameserver_response (authoritative NS queries, status/severity)
      - check_dns_propagation (consistency across NSs, partial/complete/failed)
      - Comprehensive mocking (dnspython, socket.getaddrinfo)
    - `reveal/adapters/claude/renderer.py`: 27% → 100% (33 tests, 222 lines) - Claude output rendering
      - Session overview (messages, tools, duration), tool calls (Bash, Read, Edit, Write, Grep, Glob, generic)
      - Tool summary (counts, success rates), errors (context, truncation, "N more")
      - Files touched (Read/Write/Edit operations, truncation), workflow (steps, detail)
      - Context changes (cwd, branch), filtered results (query, filters, error indicators)
      - Rendering dispatch (_render_text routes to _render_{type}), fallback (unknown types)
      - Element rendering (content field, key-value, JSON format), error rendering (stderr)
    - Subtotal: 212 tests, 795 lines, 7 modules improved (3 to 100%, 2 to 98%, 1 to 97%, 1 to 71%)

  - **Phase 6 Total**: 702 tests added, 1588 lines covered, 28 modules with major coverage improvements

  - **Phase 7** (session rofuvoke-0215):
    - `reveal/rules/validation/adapter_utils.py`: 38% → 100% (35 tests, 52 lines) - Adapter utility functions
      - find_adapter_file (4 patterns: scheme.py, scheme_adapter.py, scheme/adapter.py, scheme/__init__.py)
      - get_adapter_schemes, get_adapter_class, get_renderer_class, get_adapter_and_renderer
      - Line finding utilities: find_class_definition_line, find_method_definition_line, find_init_definition_line
      - Pattern precedence testing, exception handling, edge cases
    - `reveal/rules/validation/utils.py`: 57% → 100% (15 tests, 28 lines) - Reveal root finding utilities
      - find_reveal_root: REVEAL_DEV_ROOT env var, git checkout discovery, installed package fallback
      - dev_only flag behavior (excludes installed, allows dev checkout)
      - is_dev_checkout: pyproject.toml detection in parent directory
      - Search depth limit (10 levels), nested directory handling
    - `reveal/rules/validation/V009.py`: 65% → 99% (22 tests, 84 lines) - Documentation cross-reference validation
      - Link extraction (markdown, filters for external/anchor/mailto)
      - External link detection (http/https), anchor fragment removal
      - Link validation (broken/valid detection with line numbers)
      - URI to path conversion (reveal:// → file path, project root vs reveal root precedence)
      - Link resolution (absolute, relative, parent relative, outside project rejection)
      - Exception handling for invalid paths
    - `reveal/rules/validation/V020.py`: 65% → 96% (20 tests, 89 lines) - Adapter element/structure contract validation
      - Contract validation (missing get_element/get_structure detection)
      - Adapter instantiation testing (no args, TypeError handling)
      - get_element error handling (crashes vs returns None)
      - Helper methods: find_class_line, find_method_line, find_adapter_file
      - Edge cases: no reveal root, missing adapter/renderer class, missing adapter file
    - Subtotal: 92 tests, 253 lines, 4 modules improved (2 to 100%, 1 to 99%, 1 to 96%)

  - **Phase 8** (session valley-whirlwind-0215):
    - `reveal/rules/validation/V005.py`: 69% → 97% (18 tests, bug fix, 114 lines) - Static help file synchronization
      - No reveal root detection (returns empty)
      - STATIC_HELP parsing: detection when not parseable, help.py missing, pattern not found, exception handling
      - Missing help files: detection when referenced files don't exist, no detection when files exist
      - _find_line_in_static_help: help.py missing, topic found/not found, exception handling
      - Unregistered guides: docs_dir missing, unregistered guide detected, registered guide not detected, test files skipped
      - _find_reveal_root: find from rule location, alternative parent search, not found returns None
      - Bug fixed: Line 154 incomplete condition `or '/.':` → `or '/.' in relative_path:` (unregistered guide detection non-functional)
    - `reveal/rules/validation/V018.py`: 70% → 96% (13 tests, 86 lines) - Adapter renderer registration completeness
      - No reveal root detection (returns empty)
      - Import failure handling (exceptions during adapter/renderer imports)
      - Missing renderer: detects adapters without renderers, no crash when adapter file not found
      - Orphaned renderer: detects renderers without adapters (LOW severity)
      - _find_adapter_file: adapters_dir missing, 4 patterns (scheme.py, scheme_adapter.py, scheme/adapter.py, scheme/__init__.py), not found, pattern precedence
      - get_description: returns meaningful description
    - `reveal/rules/validation/V021.py`: 71% → 100% (15 tests, 112 lines) - Detect inappropriate regex when tree-sitter available
      - No reveal root detection (returns empty)
      - No analyzers directory (returns empty)
      - File reading error handling (exceptions during read)
      - _imports_re_module: detects `import re`, `from re import`, no import, syntax error fallback
      - _uses_treesitter_analyzer: detects TreeSitterAnalyzer usage vs non-usage
      - Regex detection: regex-based analyzer when tree-sitter available, ignores TreeSitterAnalyzer with supplemental regex, ignores languages without tree-sitter, ignores whitelisted files
      - _create_violation: effort estimation (small/medium/large based on regex count)
    - `reveal/rules/validation/V003.py`: 73% → 96% (22 tests, 106 lines) - Feature matrix coverage
      - AnalyzerContext.relative_path property calculation
      - No reveal root detection (returns empty)
      - No analyzers directory (returns empty dict)
      - Missing get_structure: detects analyzers without get_structure(), no detection when present
      - Missing outline: detects structured analyzers without outline, no detection when outline keywords present, non-structured not checked
      - _check_hierarchy_support: detects hierarchy/outline/tree/nested/parent/children keywords, false when no keywords
      - _find_class_line: finds class definition, returns 1 when not found
      - _find_reveal_root: find from location, alternative search, not found returns None
      - Detection creation: _create_missing_structure_detection, _create_missing_outline_detection
    - Subtotal: 68 tests, 418 lines, 4 modules improved (1 to 100%, 3 to 96-97%)

  - **Phase 9** (session expanding-station-0215):
    - `reveal/rules/validation/V006.py`: 74% → 98% (14 tests, 62 lines) - Output format support validation
      - No reveal root detection (returns empty)
      - No analyzers directory (returns empty)
      - Missing get_structure: detects analyzers with @register but no get_structure(), no detection when present/inherited
      - Missing return type hint: detects local get_structure without Dict return type, no detection with proper types
      - File handling: skips underscore files, skips base.py, handles read exceptions gracefully
      - _find_reveal_root: finds from rule location, returns None when not found
    - `reveal/rules/validation/V007.py`: 76% → 98% (21 tests, 103 lines) - Version consistency validation
      - No reveal root detection (returns empty)
      - Not dev checkout (returns empty for installed packages)
      - Pyproject handling: missing file creates detection, invalid version creates detection, exception handling
      - Changelog validation: missing file = no detection, missing dated entry creates detection, exception handling
      - README validation: missing file = no detection, version badge mismatch creates detection, PyPI badge extraction
      - Agent help validation: version mismatch creates detection, exception handling
      - Version extraction helpers: pyproject.toml (double/single quotes), changelog detection, markdown extraction, README badges
    - `reveal/rules/validation/V019.py`: 76% → 97% (18 tests, 71 lines) - Adapter initialization pattern compliance
      - No reveal root detection (returns empty)
      - Import exception handling (graceful failure)
      - Adapter not found: skips when adapter class None, skips when adapter file None
      - No-arg init violations: ValueError instead of TypeError creates detection, crashes create detection, TypeError = expected, success = no detection
      - Resource init violations: ImportError = no detection (optional deps), ValueError with format keywords = acceptable, unexpected ValueError creates MEDIUM severity detection, AttributeError creates detection
      - Initialization contract validation: ensures TypeError (not ValueError) for signature mismatches
    - `reveal/rules/validation/V011.py`: 78% → 99% (17 tests, 87 lines) - Release readiness validation
      - No reveal root detection (returns empty)
      - Not dev checkout (returns empty)
      - Pyproject handling: missing file = no detections, no version = no detections, exception handling
      - Changelog validation: missing file = no detection, missing dated entry creates detection, section without date = false, exception handling
      - Roadmap validation: missing file = no detection, missing shipped section creates detection, no "What We've Shipped" = false, exception handling
      - Version extraction helpers: pyproject.toml extraction, changelog dated entry detection, roadmap shipped section detection
    - `reveal/rules/validation/V015.py`: 79% → 99% (10 tests, 68 lines) - Rules count accuracy validation
      - No reveal root detection (returns empty)
      - Missing files: missing README = no detection, no rules directory = no detection
      - Count mismatches: minimum claim below actual creates detection, exact claim mismatch creates detection, minimum at actual = no detection
      - Counting logic: skips utils.py/__init__.py/_private.py/*_utils.py files, exception handling
      - README extraction: multiple claims (minimum "50+" and exact "50"), exception handling
    - `reveal/rules/validation/V002.py`: 80% → 100% (10 tests, 45 lines) - Analyzer registration validation [PERFECT 100%]
      - No reveal root detection (returns empty)
      - No analyzers directory (returns empty)
      - Analyzer registration: with @register = no detection, without @register creates detection, no classes = no detection, exception handling, skips underscore files
      - Has register decorator: detects @register decorator, detects register import, no register = false
    - Subtotal: 90 tests, 436 lines, 6 modules improved (1 to 100%, 2 to 99%, 3 to 97-98%)

  - **Phase 10** (session ascending-observatory-0215):
    - `reveal/utils/query.py`: 77% → 95% (37 tests, 63 lines) - Query parsing and filtering utilities
      - CoerceValueEdgeCases: non-string input handling (returns unchanged)
      - QueryFilterNormalization: operator normalization (== → =)
      - ParseQueryFiltersEdgeCases: empty part skipping in filter parsing
      - ComparisonExceptionHandling: range operator invalid format, wildcard operator edge cases, equality operator range special case, numeric operator string fallback, dispatch comparison default return
      - NoneComparison: None equals 'null' string (case insensitive)
      - ResultControlInvalidInput: empty parts skipped, invalid limit/offset values ignored
      - SortingMixedTypes: _safe_numeric with None/numbers/strings, mixed-type sorting, None value handling, TypeError fallback
      - BudgetLimits: max_items truncation, max_bytes truncation, truncate_strings, next_cursor metadata, within limits
      - StringTruncation: basic truncation, nested dicts, lists, list of dicts, recursive truncation (_truncate_dict_strings)
    - `reveal/adapters/stats/adapter.py`: 95% → 100% (3 tests, 4 lines) - Stats adapter [PERFECT 100%]
      - query_filter_parsing_exception_fallback: parse_query_filters exception handling (falls back to empty filters)
      - sorting_type_error_fallback: TypeError exception in sorting (returns unsorted list)
      - sorting_key_error_fallback: KeyError exception in sorting (returns unsorted list)
    - Subtotal: 40 tests, 67 lines, 2 modules improved (1 to 100%, 1 to 95%)

  - **Total**: 992 tests added, 2762 lines covered, 44 modules with major coverage improvements

### Fixed
- **Documentation link validation** - Fixed 33 broken internal links in adapter guides
  - Corrected double-dash anchor formatting (GitHub slug compatibility)
  - Replaced references to non-existent files with actual documentation
  - Updated AGENT_HELP.md anchor references
  - Result: All documentation validation tests passing
  - Session: boundless-cosmos-0214
- **Windows CI compatibility** - Fixed all remaining Windows test failures (100% pass rate)
  - Path separators: Use `.as_posix()` for MANIFEST.in paths (V022 rule)
  - Permission tests: Skip chmod-based tests on Windows (not supported)
  - Test directory detection: Use `Path.parts` for platform-independent path matching (I004 rule)
  - Error messages: Normalize diff adapter error messages for Windows drive letter handling
  - Result: 3177/3177 tests passing on Windows (previously 3170/3177)
  - Sessions: celestial-galaxy-0213 (48→7 failures), flooding-thunder-0213 (7→0 failures)

## [0.49.1] - 2026-02-13

### Fixed
- **Help system badges** - Mark xlsx, ssl, and domain adapters as 🟡 Beta instead of 🔴 Experimental
  - These adapters are production-ready with comprehensive tests
  - xlsx: 40 tests, complete CSV/JSON export
  - ssl: 52 tests, certificate inspection
  - domain: Full DNS/health status checks

## [0.49.0] - 2026-02-13

### Added
- **xlsx:// adapter** - Complete Excel spreadsheet inspection and data extraction
  - Workbook overview with sheet list and dimensions
  - Sheet extraction by name (case-insensitive) or 0-based index
  - Cell range extraction using A1 notation (A1:Z100, supports AA-ZZ columns)
  - Row limiting for large sheet preview (?limit=N)
  - CSV export via ?format=csv query parameter
  - JSON and text output formats
  - Performance validated up to 20K+ rows
  - 40 comprehensive tests (100% passing)
  - Complete help documentation and examples
  - Example: `reveal xlsx:///data/sales.xlsx?sheet=Q1&range=A1:D10&format=csv`
  - Session: distant-nebula-0213, timeless-energy-0213

### Fixed
- **xlsx adapter error messages** - Enhanced ValueError messages with examples
- **elixir analyzer** - Added return type hint to example override method

## [0.48.0] - 2026-02-08

### Added
- **Phase 1 & 2 UX Consistency verified complete** (v0.47.0)
  - **Phase 1: Format Consistency** - All 16 adapters support `--format json|text`
  - **Phase 2: Batch Processing** - Universal `--batch` flag works with all adapters
  - Batch mode supports mixed adapters, aggregated results, exit codes
  - Verified sessions: sapphire-spark-0207 (Phase 1), zibeta-0207 (Phase 2)
- **Phase 3: Query Operator Standardization** (v0.47.1) - COMPLETE ✅
  - **Universal query operators** across all 5 query-capable adapters (ast, json, markdown, stats, git)
  - **Comparison operators**: `=`, `!=`, `>`, `<`, `>=`, `<=`, `~=` (regex), `..` (range)
  - **Result control**: `sort=field`, `sort=-field`, `limit=N`, `offset=M` work consistently
  - **Query infrastructure**: Unified `compare_values()` and `parse_result_control()` utilities
  - Session: hosuki-0208 (3 hours, 85% efficiency through discovery)
- **Phase 4: Field Selection + Budget Constraints** (v0.47.2) - COMPLETE ✅
  - **Field selection**: `--fields=field1,field2` for dramatic token reduction (5-10x)
  - **Budget constraints**: `--max-items=N`, `--max-bytes=N`, `--max-depth=N`, `--max-snippet-chars=N`
  - **Truncation metadata**: Output includes `meta.truncated`, `meta.reason`, `meta.next_cursor`
  - **Nested field support**: Access nested fields with dot notation (`certificate.expiry`)
  - **Works with all adapters**: Universal routing layer integration
  - **Combines with Phase 3**: Query operators + field selection = powerful precision
  - Session: luminous-twilight-0208 (~4 hours, full implementation + testing + documentation)
- **Phase 5: Element Discovery** (v0.47.3) - COMPLETE ✅
  - **Auto-discovery**: Adapters show available elements in overview with descriptions
  - **Text hints**: "📍 Available elements" section shows element names, descriptions, example usage
  - **JSON output**: `available_elements` array enables programmatic element discovery
  - **4 adapters with fixed elements**: SSL (6), Domain (4), MySQL (11), Python (7)
  - **10 adapters with dynamic elements**: Git, JSON, Env, Stats, Markdown, SQLite, Help, Imports, Reveal, Diff
  - **Progressive disclosure**: Start with overview, drill down to specific elements
  - Session: scarlet-shade-0208 (~4 hours, implementation + testing + documentation)
- **Phase 8: Convenience Flags** (v0.47.3) - COMPLETE ✅
  - **Ergonomic within-file operations**: Simple flags for 80% of within-file queries
  - **Three convenience flags**: `--search PATTERN`, `--sort FIELD`, `--type TYPE`
  - **Grep replacement workflow**: `reveal file.py --search pattern` replaces `grep -n pattern file.py` with richer output
  - **Progressive escalation**: Start with simple flags, graduate to URI syntax for complex queries
  - **Auto-conversion**: Flags transparently convert to AST query URIs at routing layer
  - **Full compatibility**: Works with all existing flags (`--head`, `--format json`, etc.)
  - **Shell-safe sorting**: `--sort=-field` syntax avoids shell interpretation issues
  - **Comprehensive tests**: 12 new tests covering all flag combinations and edge cases
  - Session: ferocious-apocalypse-0208 (~4 hours, validation + implementation + documentation)
  - Commit: d9b873d
- **Phase 7: Output Contract v1.1** - Trust metadata for AI agents (v0.47.0)
  - Added optional `meta` field with parse_mode, confidence, warnings, errors
  - Enables AI agents to assess result trustworthiness
  - Implemented in AST adapter, available to all adapters via base class
- **Claude adapter session analysis elements**
  - `/workflow` - Chronological sequence of tool operations
  - `/files` - All files read, written, or edited during session
  - `/context` - Track directory and branch changes
  - Updated usage examples and help documentation

### Fixed
- **Markdown adapter routing bug** (Phase 3 completion)
  - Query parameters were completely ignored due to default parameter in `__init__`
  - Removed default parameter to fix routing layer's Try 1 initialization
  - Now correctly applies `sort`, `limit`, `offset`, and filter operators
  - Commit: a36d6b5 (Session: hosuki-0208)
- **Git adapter missing result control** (Phase 3 completion)
  - Added `sort`, `limit`, `offset` support across commit/file history queries
  - Applied in `_get_file_history`, `_get_recent_commits`, `_get_commit_history`
  - Keeps legacy limit parameter for backward compatibility
  - Commit: 3610488 (Session: hosuki-0208)
- **MySQL adapter bugs** (3 issues fixed)
  - `--check` no longer crashes with TypeError (only_failures kwarg)
  - Progressive disclosure now returns correct element (not overview)
  - Server display shows actual host/port when using ~/.my.cnf (was "None:None")
  - Lag display no longer appends "s" to "Unknown" values
- **I005 rule signature mismatch** (Phase 8 preparation)
  - Added missing `content` parameter to match BaseRule interface
  - Fixes TypeError when running `--check` on files with I005 rule enabled
  - Session: cakiyawu-0208

### Documentation
- **Phase 3 Documentation Complete** (2026-02-08)
  - Created `QUERY_SYNTAX_GUIDE.md` - Complete reference for unified query operators
  - Documents all 8 universal operators (`=`, `!=`, `>`, `<`, `>=`, `<=`, `~=`, `..`)
  - Result control reference (sort/limit/offset)
  - Adapter-by-adapter examples with common patterns
  - Progressive filtering, pagination, and top-N query patterns
  - Session: gentle-cyclone-0208
- **Phase 4 Documentation Complete** (2026-02-08)
  - Created `FIELD_SELECTION_GUIDE.md` - Comprehensive guide for token reduction (644 lines)
  - Field selection syntax and examples across all adapters
  - Budget constraint flags and truncation metadata reference
  - Token reduction metrics (5-40x depending on adapter)
  - Common patterns: AI agent loops, monitoring, pagination, progressive loading
  - Advanced patterns: Multi-source aggregation, budget-aware search, incremental fetching
  - Session: luminous-twilight-0208
- **Phase 5 Documentation Complete** (2026-02-08)
  - Created `ELEMENT_DISCOVERY_GUIDE.md` - Complete reference for element discovery (698 lines)
  - What elements are and why progressive disclosure matters
  - Element discovery in text and JSON output
  - Element access syntax and examples for all adapters
  - Common patterns: Progressive exploration, element loops, conditional access
  - Best practices: When to use elements vs query parameters
  - Adapter element reference table (fixed vs dynamic elements)
  - Session: scarlet-shade-0208
- **Phase 8 Documentation Complete** (2026-02-08)
  - Updated `AGENT_HELP.md` - New "Task: Search within a single file" section
  - Updated `QUERY_SYNTAX_GUIDE.md` - Added "Convenience Flags vs URI Syntax" comparison
  - Convenience flag examples with grep replacement workflows
  - Progressive escalation guidance (when to use flags vs URI syntax)
  - Real-world examples showing 80/20 split in action
  - Session: ferocious-apocalypse-0208
- **MySQL adapter production validation** - Updated help_data/mysql.yaml
  - Added `mysql://` example (simplest form using ~/.my.cnf)
  - Added "Production Database Monitoring" workflow
  - Noted production validation against 189GB Digital Ocean MySQL 8.0.35

## [0.47.0] - 2026-02-06

### Added
- **Phase 6 Complete: AI Agent Introspection - 100% Adapter Coverage**
  - All 15 adapters now have machine-readable `get_schema()` methods
  - Complete schema coverage enables AI agents to auto-discover capabilities
  - Added schemas to 12 remaining adapters:
    - **Simple adapters**: env, json, markdown, reveal
    - **Analysis adapters**: diff, imports
    - **Data adapters**: mysql, sqlite, python
    - **Complex adapters**: git, domain, claude
  - Each schema includes:
    - URI syntax patterns
    - Query parameters with types and operators
    - Available elements and CLI flags
    - Output types with JSON Schema definitions
    - Example queries with expected outputs
  - Updated AGENT_HELP.md with complete adapter list organized by category
  - Session: xtreme-shockwave-0206 (4 hours implementation)

### Changed
- **AGENT_HELP.md updated to v0.47.0**
  - Now lists all 15 adapters organized by category (File & Analysis, Environment & Data, Infrastructure, Meta)
  - Clear examples for each adapter schema query

### Documentation
- **Phase 6 marked as FULLY COMPLETE in planning documents**
  - Updated ADAPTER_UX_CONSISTENCY_2026-02-06.md with 100% coverage status
  - Added adapter coverage matrix showing all 15 adapters with schemas

## [0.44.2] - 2026-01-21

### Fixed
- **SSL certificate parsing for TLS 1.3 connections** - Certificates were falsely reported as expired
  - When Python's `getpeercert()` returns None (common with TLS 1.3 + CERT_NONE), the binary DER cert is now properly parsed using cryptography library
  - Previously, empty dates caused fallback to `datetime.now()`, making valid certs appear to expire "today"
  - Affects: batch SSL checks on servers with certain TLS configurations

### Added
- **cryptography** dependency for robust SSL certificate parsing

## [0.44.1] - 2026-01-21

### Fixed
- **Batch SSL filter flags with `--stdin --check`** (Issue #19)
  - `--summary`, `--only-failures`, `--expiring-within` now work with composable pipeline
  - `reveal nginx.conf --extract domains | reveal --stdin --check --summary` now aggregates results
  - Both `ssl://nginx:///` and composable `--stdin --check` pipeline support all batch flags

### Changed
- **Removed premature deprecation of `ssl://nginx:///` syntax**
  - Both approaches are now first-class citizens with different strengths
  - `ssl://nginx:///path --check --summary` - Best for simple batch audits
  - `--extract domains | --stdin --check` - Best when filtering between steps

### Documentation
- Updated ssl.yaml help with clear guidance on when to use each approach
- Added workflow examples for both simple and composable batch audits

## [0.44.0] - 2026-01-21

### Added
- **`--extract` flag for composable pipelines** - Extract structured data from files
  - `reveal nginx.conf --extract domains` - outputs SSL domains as `ssl://` URIs
  - Enables composable workflows: `reveal nginx.conf --extract domains | reveal --stdin --check`
  - More flexible than `ssl://nginx:///` - can filter, transform, or redirect between steps

### Deprecated (REVERTED in 0.44.1)
- ~~`ssl://nginx:///` syntax~~ - Deprecation removed; both syntaxes are now recommended for their specific use cases

### Documentation
- Updated AGENT_HELP.md, RECIPES.md, QUICK_START.md to use composable pipeline
- Clarified deprecation status in ssl.yaml help data

## [0.43.0] - 2026-01-21

### Added
- **`@file` syntax for batch URIs** - Read targets from a file
  - `reveal @domains.txt --check` reads URIs/paths from file
  - Supports comments (`#`) and blank lines
  - Works with any URI scheme: `ssl://`, `env://`, file paths
  - Example: `reveal @certs.txt --check --only-failures`

- **`ssl://nginx:///` integration** - Extract and check SSL domains from nginx config
  - `reveal ssl://nginx:///etc/nginx/conf.d/*.conf` - list SSL domains
  - `reveal ssl://nginx:///etc/nginx/*.conf --check` - check all certs
  - Automatically extracts domains from `server_name` in SSL-enabled blocks
  - Filters out localhost, wildcards, IPs, and non-FQDNs

- **Batch SSL filter flags** - Filter large certificate audits
  - `--only-failures` - Show only failed/warning checks (hide healthy)
  - `--summary` - Aggregated counts instead of full details
  - `--expiring-within N` - Show certs expiring within N days
  - Example: `reveal ssl://nginx:///etc/nginx/*.conf --check --only-failures --expiring-within=30`

### Performance
- **5x faster AST parsing** - Tree-sitter node queries now use single-pass caching
  - Full test suite: 123s → 88s (28% faster)
  - AST adapter: 4.1s → 0.76s on reveal codebase

### Fixed
- **Batch processing warnings** - `--stdin` and `@file` no longer print spurious "failed, skipping" warnings for successful operations
- **Validation rules for installed package** - V004/V007/V011 no longer report false positives when reveal is pip-installed (checks only run in dev checkout)

## [0.42.0] - 2026-01-20

### Added
- **Universal `--stdin` URI support** - Batch processing now works with any URI scheme
  - Process multiple SSL certs: `echo -e "ssl://a.com\nssl://b.com" | reveal --stdin`
  - Mix files and URIs: `echo -e "config.py\nssl://example.com\nenv://PATH" | reveal --stdin`
  - Graceful error handling: failed URIs warn and continue (match file behavior)

- **Query parsing utilities** - New `reveal/utils/query.py` for adapter authors
  - `parse_query_params(query)`: Simple key=value parsing
  - `parse_query_filters(query)`: Operator-aware filters (>, <, >=, <=, !, ?)
  - `QueryFilter` dataclass and `apply_filters()` for structured filtering
  - `coerce_value()`: Smart type coercion (bool/int/float/str)

### Changed
- **Claude adapter** - Migrated to centralized `parse_query_params()`
- **Stats adapter** - Migrated to centralized `parse_query_params(coerce=True)`
- Internal code deduplication: 4 separate `_parse_query` implementations → 2 categories

## [0.41.0] - 2026-01-20

### Added
- **`ssl://` adapter** - SSL/TLS certificate inspection (zero dependencies)
  - Certificate overview: `reveal ssl://example.com`
  - Non-standard ports: `reveal ssl://example.com:8443`
  - Subject Alternative Names: `reveal ssl://example.com/san`
  - Certificate chain: `reveal ssl://example.com/chain`
  - Health checks: `reveal ssl://example.com --check`
  - Checks: expiry (30/7 day thresholds), chain verification, hostname match
  - Batch mode: `batch_check_from_nginx()` for checking all SSL domains in nginx config

- **N004: ACME challenge path inconsistency** - Nginx quality rule
  - Detects when server blocks have different root paths for `/.well-known/acme-challenge/`
  - Identifies the pattern that caused the 209-cert sociamonials outage
  - HIGH severity - path inconsistencies cause cert renewal failures
  - Example: `reveal /etc/nginx/nginx.conf --check --select N004`

- **Content-based nginx detection** - Improved `.conf` file handling
  - Files with nginx patterns (`server {`, `location /`, etc.) now use NginxAnalyzer
  - Works regardless of file path (not just `/etc/nginx/`)
  - Detects nginx content in first 4KB of file

- **Enhanced nginx display** - Better structure output
  - Server blocks show ports: `social.weffix.com [443 (SSL)]`
  - Location blocks show targets: `/.well-known/acme-challenge/ -> static: /path`

- **Path utilities** - New `reveal/utils/path_utils.py`
  - `find_file_in_parents()`: Search up directory tree for config files
  - `search_parents()`: Generic parent directory search with conditions
  - `find_project_root()`: Locate project root by common markers

- **Safe operation utilities** - New `reveal/utils/safe_operations.py`
  - `safe_operation()`: Decorator for graceful failure with fallbacks
  - `safe_read_file()`, `safe_json_loads()`, `safe_yaml_loads()`
  - `SafeContext`: Context manager for safe operations

### Changed
- **Rule infrastructure refactoring** - Technical debt reduction
  - New `ASTParsingMixin` for consistent AST parsing across rules
  - Extended `create_detection()` to support severity overrides
  - Updated B001, B005, B006, R913, M104 to use mixin

- **Renderer consolidation** - New `reveal/rendering/base.py`
  - `RendererMixin`: Shared utilities (JSON rendering, status output)
  - `TypeDispatchRenderer`: Auto-routes to `_render_{type}()` methods
  - SSLRenderer migrated to use new base classes

- **Centralized defaults** - New `reveal/defaults.py` consolidates threshold constants
  - `RuleDefaults`: Complexity, file quality, code smell thresholds
  - `AdapterDefaults`: SSL expiry thresholds, scan limits
  - `DisplayDefaults`: Tree view limits
  - Supports future environment variable overrides

- **Centralized patterns** - New `reveal/utils/patterns.py` consolidates regex patterns
  - Error detection patterns (was duplicated in claude adapter)
  - Nginx patterns (server blocks, SSL listen, ACME locations)
  - Code patterns (Python class/function, semver)
  - Includes `compile_pattern()` with LRU caching for dynamic patterns

### Fixed
- **SSLAdapter TypeError** - No-arg initialization now raises `TypeError` (was `ValueError`)
  - Consistent with git adapter behavior
  - Allows generic handler to try next initialization pattern

## [0.40.0] - 2026-01-20

### Added
- **`--dir-limit` flag** - Per-directory entry limit for tree view (default: 50)
  - Caps entries shown per directory, then shows `[snipped N more entries]`
  - Continues with sibling directories (unlike global `--max-entries` which stops)
  - Breadcrumb hint: `(--dir-limit 0 to show all)` when snipping
  - Example: `reveal myproject/ --dir-limit 10` - shows 10 entries per dir
  - Solves: `node_modules/` consuming entire entry budget, hiding other directories

- **`--adapters` flag** - List all available URI adapters with descriptions
  - Shows scheme, name, stability tier, and purpose for each adapter
  - Example: `reveal --adapters` lists all URI adapters
  - Complements `--languages` for file type analyzers

- **M104: Hardcoded list detection** - Quality rule for maintainability
  - Detects large lookup tables (dicts with 5+ list values)
  - Flags high-risk patterns (file extensions, node types) that may become stale
  - Example: `reveal src/ --check --select M104`

- **ROADMAP.md** - Public-facing roadmap for contributors
  - Shows shipped features, current focus, and post-v1.0 plans
  - Linked from CONTRIBUTING.md for discoverability

- **Breadcrumb improvements** - Expanded file type coverage
  - Added extraction hints for 25+ file types
  - Documents all extraction syntaxes (by name, ordinal, line, hierarchical)

### Changed
- **Tree-sitter constants consolidated** - Centralized node type definitions
  - `FUNCTION_NODE_TYPES`, `CLASS_NODE_TYPES`, `STRUCT_NODE_TYPES` in treesitter.py
  - Reduces duplication and staleness risk across codebase

- **Nginx rules use shared constant** - `NGINX_FILE_PATTERNS` extracted
  - N001, N002, N003 now share single source of truth

- **Documentation restructured** - Consolidated and reorganized
  - Clearer hierarchy between internal and public docs
  - Fixed stale "most wanted" list in CONTRIBUTING.md (all shipped!)

### Fixed
- **SQLite adapter** - Clean error message instead of traceback for missing database
  - Before: `FileNotFoundError: [Errno 2] No such file or directory`
  - After: `Error (sqlite://): Database file not found: /path/to/file.db`

- **MySQL adapter** - Clean connection error with hints
  - Before: Long pymysql traceback
  - After: `Error: Failed to connect to MySQL at localhost:3306` with config hints

- **Imports adapter query params** - `?circular`, `?unused`, `?violations` now work
  - Root cause: URI not passed to adapters that expected query params

- **Validation rule cleanup** - Removed dead code from validation rules
  - Removed V014 (checked for "**Current version:**" pattern no longer used)
  - Removed dead roadmap version checks from V007 and V011
  - Removed unused version_utils.py

- **Display fixes** - HTML metadata, CSV schema, XML children, PowerShell signatures

## [0.39.0] - 2026-01-19

### Added
- **Windows Batch analyzer** - Windows automation script analysis (.bat, .cmd)
  - Label extraction (subroutines/jump targets as functions)
  - Variable assignments (SET commands)
  - Internal calls (CALL :label) and external calls (CALL script.bat)
  - Script statistics (echo off, setlocal, code lines)
  - Element extraction by label name
  - Head/tail/range filtering
  - Examples:
    - `reveal build.bat` - Show script structure
    - `reveal deploy.cmd setup` - Extract :setup subroutine
    - `reveal script.bat --head 3` - First 3 labels
  - Tests: 14 tests, 95% coverage
  - Fills Windows platform gap (CI/CD, build automation, enterprise scripts)
  - Session: shimmering-spark-0119

- **QUICK_START.md** - New 5-minute quick start guide for new users
  - Progressive disclosure workflow examples (directory → file → element)
  - Real-world tasks: code review, onboarding, finding complexity
  - Token efficiency demonstrations (10-150x reduction)
  - Comparison with traditional tools (grep, find, cat)
  - Clear navigation to other documentation
  - Integrated into help system: `reveal help://quick-start`
  - Target: New users, onboarding
  - Session: blazing-hail-0119

- **CSV/TSV analyzer** - Tabular data file analysis
  - Schema inference (column types: integer, float, boolean, list, string)
  - Data quality metrics (missing values, unique counts, sample values)
  - Row filtering (head, tail, range)
  - Delimiter detection (comma/tab)
  - Examples:
    - `reveal data.csv` - Show schema and sample rows
    - `reveal data.csv --head 10` - First 10 rows
    - `reveal data.csv:42` - Get row 42
  - Tests: 16 tests, 92% coverage
  - Fills major gap: CSV is universal data format (data pipelines, ML, exports)
  - Session: aqua-sunset-0118

- **INI/Properties analyzer** - Configuration file analysis
  - Supports Windows INI, Java properties, Python configs
  - Section and key extraction
  - Type inference (integer, float, boolean, list, string)
  - Section filtering (head, tail, range)
  - Examples:
    - `reveal config.ini` - Show all sections and keys
    - `reveal app.properties` - Java properties (no sections)
    - `reveal config.ini:database` - Get database section
    - `reveal config.ini:database.host` - Get specific key
  - Tests: 18 tests, 94% coverage
  - Fills major gap: INI/Properties files common in Windows, Java, Python ecosystems
  - Session: aqua-sunset-0118

- **XML analyzer** - XML document analysis
  - Supports Maven pom.xml, Spring configs, Android manifests, SOAP APIs, SVG
  - Document statistics (element count, max depth, namespace detection)
  - Element tree structure with attributes and text content
  - Type inference for text content (integer, float, boolean, string)
  - Child element filtering (head, tail, range)
  - Element extraction by tag name (finds all matches with paths)
  - Examples:
    - `reveal pom.xml` - Show Maven project structure
    - `reveal config.xml --head 5` - First 5 child elements
    - `reveal manifest.xml:application` - Find all application elements
    - `reveal spring-config.xml:bean` - Find all bean definitions
  - Tests: 20 tests, 92% coverage
  - Fills major gap: XML is enterprise-standard (Maven, Gradle, Spring, Android)
  - Session: sapphire-rainbow-0119

- **PowerShell analyzer** - PowerShell script analysis (.ps1, .psm1, .psd1)
  - Function extraction (function, filter, workflow statements)
  - Parameter block detection (CmdletBinding, advanced functions)
  - Cross-platform PowerShell Core support
  - Head/tail/range filtering for large scripts
  - Examples:
    - `reveal deploy.ps1` - Show Azure deployment script structure
    - `reveal module.psm1` - Show PowerShell module functions
    - `reveal script.ps1 --head 5` - First 5 functions
  - Tests: 14 tests, 93% coverage
  - Fills major gap: Modern Windows automation (Azure DevOps, cloud infrastructure)
  - Session: sapphire-rainbow-0119

- **B006: Silent broad exception handler detector** - Detects `except Exception: pass` with no comment/logging
  - Catches broad exception handlers that silently swallow errors
  - Prevents bugs from being hidden (like the tree-sitter parsing failure in v0.38.0)
  - Allows intentional cases with explanatory comments
  - Medium severity (can hide serious bugs)
  - Examples:
    - `reveal src/ --check --select B006` - Find silent exception handlers
    - Suggests: use specific exceptions, add logging, add comments, or re-raise
  - Session: aqua-sunset-0118

- **`--section` flag for markdown** - Extract sections by heading name with explicit flag
  - Alternative to positional syntax: `reveal doc.md --section "Installation"` same as `reveal doc.md "Installation"`
  - Clearer for scripts and automation
  - Error message guides users when used on non-markdown files
  - Session: legendary-sea-0119

- **`meta.extractable` in JSON output** - Agent discoverability for element extraction
  - JSON output now includes `meta.extractable` with available element types and names
  - Enables agents to discover what can be extracted without trial-and-error
  - Fields: `types` (available element types), `elements` (names by type), `examples` (ready-to-use commands)
  - Maps structure categories to extraction types: functions→function, classes→class, headings→section, etc.
  - Example output:
    ```json
    "meta": {
      "extractable": {
        "types": ["function", "class"],
        "elements": {"function": ["foo", "bar"], "class": ["MyClass"]},
        "examples": ["reveal file.py foo"]
      }
    }
    ```
  - Design principle: Every JSON response should tell agents what they can do next
  - Session: heroic-giant-0119

- **`--capabilities` endpoint** - Pre-analysis introspection for agents
  - Shows what reveal CAN do with a file before analyzing it
  - Returns JSON with analyzer info, extractable types, quality rules, supported flags
  - Enables agents to plan their approach without trial-and-error
  - Example: `reveal --capabilities app.py`
    ```json
    {
      "analyzer": {"name": "Python", "type": "explicit"},
      "extractable": {"types": ["function", "class", "method"]},
      "quality": {"available": true, "rule_categories": ["B", "C", "I", "M", "R", "S"]},
      "flags": {"supported": ["--check", "--outline", "--head", "--tail"]}
    }
    ```
  - Complements `meta.extractable` (post-analysis): capabilities = before, meta = after
  - Session: eternal-god-0119

- **Hierarchical element extraction** - Extract methods within classes using `Class.method` syntax
  - New syntax: `reveal file.py MyClass.my_method` extracts method within class
  - Works for: Python classes, Rust impl blocks, Ruby modules, Go structs
  - Falls back gracefully if parent or child not found
  - Example: `reveal app.py DatabaseHandler.connect` extracts just the connect method
  - Session: eternal-god-0119

- **claude:// composite queries** - Filter tool results with multiple criteria
  - Syntax: `?tools=X&errors&contains=Y` combines filters
  - Examples:
    - `reveal claude://session/name?tools=Bash&errors` - Bash commands that failed
    - `reveal claude://session/name?tools=Read&contains=config` - Read calls with 'config'
    - `reveal claude://session/name?errors&contains=traceback` - Errors with tracebacks
  - Session: kabawose-0119

- **claude:// error context** - Show what led to each error
  - Each error now includes context: `tool_name`, `tool_input_preview`, `thinking_preview`
  - Helps debug why errors occurred without manual investigation
  - Example output: `context: {tool_name: 'Bash', tool_input_preview: 'cd /path && reveal ...'}`
  - Session: kabawose-0119

- **claude:// session listing** - Bare `reveal claude://` now lists sessions
  - Shows 20 most recent sessions with metadata (modified date, size)
  - Includes usage examples for all query types
  - 3600+ sessions indexed automatically
  - Session: kabawose-0119

- **`:LINE` extraction syntax** - Extract element at/containing line number
  - New syntax: `reveal file.py :73` extracts function/class containing line 73
  - Range syntax: `reveal file.py :73-91` extracts exact line range
  - Complements existing extraction methods (by name, hierarchical)
  - Matches output format where `:73` is shown as line prefix
  - Session: glowing-gleam-0119

- **`@N` ordinal extraction syntax** - Extract Nth element by position
  - New syntax: `reveal file.py @3` extracts 3rd function (dominant category)
  - Typed syntax: `reveal file.py function:2` extracts 2nd function explicitly
  - Typed syntax: `reveal file.py class:1` extracts 1st class
  - 1-indexed to match JSONL and markdown `--section` behavior
  - Dominant category auto-detection: functions for code, headings for markdown
  - Supports all element types: function, class, section, query, message, etc.
  - 20 new tests in `test_ordinal_extraction.py`
  - Session: yevaxi-0119

- **Expanded `meta.extractable` mappings** - 25+ new category mappings
  - GraphQL: queries, mutations, types, interfaces, enums
  - Protobuf/gRPC: messages, services, rpcs
  - Terraform/HCL: resources, variables, outputs, modules
  - Zig/Rust: tests, unions
  - Jupyter: cells
  - JSONL: records
  - Core: imports, tests
  - Session: glowing-gleam-0119

- **Configurable `stats://` quality thresholds** - Follow mysql adapter config pattern
  - Quality score thresholds now configurable via `.reveal/stats-quality.yaml`
  - Config search: project → user → defaults
  - Configurable: complexity_target, function_length_target, penalty multipliers
  - Allows per-project quality standards (enterprise vs startup codebases)
  - Session: glowing-gleam-0119

- **`imports://` adapter breadcrumbs** - Complete 100% breadcrumb coverage
  - Added `see_also` to imports.py adapter (was the only adapter missing it)
  - Links to: ast, stats, configuration, --check flag
  - Session: glowing-gleam-0119

- **`git://` adapter documentation** - Clarified limit behavior
  - Added notes: "Overview shows 10 most recent items per category"
  - Added notes: "Use ?limit=N on history/element queries for more results"
  - Session: glowing-gleam-0119

- **Integration tests for imports://, diff://, reveal:// adapters** - CLI integration test coverage
  - 8 new tests in `test_adapter_integration.py`
  - Covers: import graph analysis, semantic diff, self-inspection
  - Test count: 2525 → 2533 tests
  - Session: burning-trajectory-0119

- **AGENT_HELP.md adapter reference** - Complete adapter table for AI agents
  - Added table with all URI adapters (purpose + example)
  - Highlights most useful for agents: ast://, stats://, python://, imports://
  - Session: burning-trajectory-0119

- **Internal documentation structure** - Created `internal-docs/` organization
  - `internal-docs/README.md` - Document inventory and navigation
  - `internal-docs/research/DOGFOODING_REPORT_2026-01-19.md` - Adapter validation findings
  - Session: burning-trajectory-0119

### Changed
- **Claude adapter refactoring** - Reduced complexity of `_calculate_tool_success_rate`
  - Extracted 4 helper methods for single responsibility
  - Complexity: 37 → 1 (97% reduction)
  - Lines: 65 → 20 (69% reduction)
  - Improved readability and maintainability
  - All tests passing (50/50)
  - Session: blazing-hail-0119

- **Help system** - Added quick-start to help:// index
  - New "Getting Started" section (appears first in help listing)
  - Navigation tip: `reveal help://quick-start` for new users
  - Integrated with existing static guides system
  - Session: blazing-hail-0119

- **README accuracy** - Updated language and test counts
  - Language count: Corrected to 42 built-in analyzers (CSV, INI, XML, PowerShell, Batch added in v0.39.0)
  - Test count: 2,230+ → 2,475 tests (measured)
  - Coverage: 74% → 76% (measured)
  - All counts verifiable via `--list-supported` and test suite
  - Session: blazing-hail-0119, mumuxi-0119, shimmering-spark-0119

- **`--capabilities` accuracy** - Fixed claims to match actual extraction support
  - Removed `method` from extractable types (use `Class.method` hierarchical syntax instead)
  - Removed `heading` from markdown (redundant with `section`)
  - Removed `code_block` from markdown (requires `--code` flag)
  - Added missing types: Terraform, GraphQL, Protobuf, JSONL, Jupyter
  - Added examples for new types (resource, query, message, row, element, record)
  - Improved docstring explaining extraction methods: by name, by ordinal, hierarchical
  - Session: shimmering-spark-0119

- **Adapter categorization** - Reclassified `reveal://` and `claude://` as "Project Adapters"
  - New category: 🎓 Project Adapters (production-quality extensibility examples)
  - `reveal://` moved from 🟢 Stable to 🎓 Project Adapters
  - `claude://` moved from 🔴 Experimental to 🎓 Project Adapters
  - Rationale: Both are production-ready for their domains (reveal devs, Claude users) but exist primarily to demonstrate how to build project-specific adapters
  - Impact: Clarifies that reveal is an extensibility framework, not just a file analyzer
  - Updated: STABILITY.md, help system, README with categorized adapter listing
  - No functional changes - only improved messaging and positioning
  - Session: mumuxi-0119

- **Code quality cleanup** - Consolidated duplicate utilities
  - Created `reveal/utils/formatting.py` with shared `format_size()` function
  - Removed 3 duplicate implementations from `base.py`, `tree_view.py`, `analyzers/office/base.py`
  - Updated documentation version references (v0.37.0 → v0.39.0)
  - Fixed rule count in README (59 → 57 to match actual count)
  - Updated test count in STABILITY.md (2239 → 2456)
  - Session: garnet-fire-0119

### Fixed
- **Adapter routing** - Fixed "No renderer registered" error for claude://, git://, stats:// adapters
  - Root cause: `routing.py` had manual import list that fell out of sync with `adapters/__init__.py`
  - Fix: Simplified to single source of truth (`from .. import adapters`)
  - Added regression test `test_all_adapters_have_renderers` to prevent recurrence
  - Added input validation to claude adapter (raises `TypeError` for invalid input)
  - Session: psychic-shark-0119, burning-trajectory-0119

- **claude:// error detection** - Fixed broken `?errors` query that returned 0 errors
  - Root cause: `_get_errors()` checked `type == 'assistant'` but tool results are in `type == 'user'` messages
  - Also fixed `_track_tool_results()` and `_is_tool_error()` which had the same bug
  - Enhanced detection now uses: `is_error` flag, exit codes > 0, traceback/exception patterns
  - Previously: 0 errors detected. Now: proper error detection with categorization
  - Session: kabawose-0119

- **claude:// test fixtures** - Fixed incorrect message format in test data
  - Test fixtures had tool_results in `type: "assistant"` messages
  - Real Claude Code conversations have tool_results in `type: "user"` messages
  - Updated `_get_timeline()` to also extract tool_results from user messages
  - 50/50 tests now passing (was 45/50)
  - Session: glowing-gleam-0119

- **B006 comment detection** - Fixed false positives for comments between except and pass lines
  - Previously only checked except line and pass line for comments
  - Now checks all lines in exception handler body
  - Impact: Eliminated all 41 false positives in reveal codebase (100% were intentional patterns with comments)
  - Test added: `test_allow_exception_with_comment_between_except_and_pass`

### Removed
- **M104: Hardcoded configuration detection** - Removed due to high false positive rate
  - Rationale: Rule could not reliably distinguish between code structure (workflow definitions, output contracts, package metadata) and actual configuration
  - Impact: Eliminates 300+ false positives across typical Python codebases
  - Rule count: 58 → 57 (M104 removed, B006 added: net -1)
  - Dogfooding revealed that even with context awareness improvements, semantic analysis was insufficient
  - Conclusion: Better to have fewer, more accurate rules than noisy ones that obscure real issues

## [0.38.0] - 2026-01-18

### Added
- **claude:// adapter** - Claude Code conversation analysis (Tier 2 priority, Phase 1 + Phase 2)
  - Session overview: message counts, tool usage, duration (`reveal claude://session/name`)
  - Progressive disclosure: overview → analytics → filtered → specific messages
  - Tool usage analytics and filtering (`reveal claude://session/name/tools`, `reveal claude://session/name?tools=Bash`)
  - Tool success rate calculation: tracks success/failure per tool type (`reveal claude://session/name?summary`)
  - Timeline view: chronological event flow with 5 event types (user_message, assistant_message, tool_call, tool_result, thinking) (`reveal claude://session/name?timeline`)
  - Error detection with context (`reveal claude://session/name?errors`)
  - Thinking block extraction and token estimates (`reveal claude://session/name/thinking`)
  - File operation tracking (Read, Write, Edit operations)
  - Message filtering by role (`reveal claude://session/name/user`, `reveal claude://session/name/assistant`)
  - Output Contract v1.0 compliant (10 output types: added claude_analytics, claude_timeline)
  - 267 lines implementation (+67 from Phase 1), 795 lines tests (+345 from Phase 1), 50 tests passing (+17), 100% coverage
  - Session discovery from `~/.claude/projects/` directories
  - Help documentation with workflows and examples (`reveal help://claude`)
  - Sessions: infernal-earth-0118 (design), blazing-cyclone-0118 (integration), fluorescent-prism-0118 (doc updates), infernal-grove-0118 (Phase 1 implementation), drizzling-lightning-0118 (Phase 2 implementation)

- **git:// adapter** - Complete git repository inspection (Tier 1 priority)
  - Repository overview: branches, tags, recent commits (`reveal git://.`)
  - Ref exploration: commit history for branches/tags (`reveal git://.@main`)
  - Time-travel: file at any commit (`reveal git://file.py@HEAD~5`, `reveal git://file.py@v1.0.0`)
  - File history: commits that touched a file (`reveal git://file.py?type=history`)
  - File blame: progressive disclosure (summary/detailed/semantic) (`reveal git://file.py?type=blame`)
  - Output Contract v1.0 compliant (5 output types)
  - 904 lines implementation, 446 lines tests, 23 tests passing
  - Sessions: hyper-asteroid-0117 (Output Contract compliance)

- **Output Contract Specification v1.0** - Standardized adapter output schemas (Tier 1 priority)
  - New OUTPUT_CONTRACT.md document (523 lines, v1.0 specification)
  - All 13 adapters migrated to v1.0 contract (100% coverage)
  - Required fields: contract_version, type (snake_case), source, source_type
  - Enables predictable JSON parsing for AI agents and tool builders
  - Unblocks plugin ecosystem (contributors have clear contract)
  - Versioning strategy for backwards compatibility
  - Session: astral-pulsar-0117 (11 adapters), hyper-asteroid-0117 (git adapter)

### Changed
- **Language count standardization** - Corrected built-in language count
  - Updated documentation: 38 languages built-in (was incorrectly listed as "31 analyzers")
  - Accurate count includes Office formats (Excel, Word, PowerPoint, Calc, Writer, Impress)
  - Tree-sitter fallback: 165+ additional languages (structure-only extraction)
  - Impact: Clear, verifiable language support claims matching registry reality

## [0.37.0] - 2026-01-17

### Added
- **Stability Taxonomy** - Clear stability guarantees for adapters and features (Tier 1 priority)
  - New STABILITY.md document with comprehensive policy and v1.0 roadmap
  - Stability labels in README.md: 🟢 Stable, 🟡 Beta, 🔴 Experimental
  - Stability badges in `reveal help://` output (legend shows at adapter list)
  - Stability field in individual adapter help pages (`reveal help://<adapter>`)
  - Classification: 5 stable adapters (help, env, ast, python, reveal), 8 beta adapters (diff, imports, sqlite, mysql, stats, json, markdown, git)
  - Purpose: Users and AI agents know what's safe to depend on
  - Breaking change policy defined: stable features won't break in minor versions
  - Path to v1.0 documented: Q2 2026 after Output Contract Specification ships
  - Session: mysterious-rocket-0117

## [0.36.1] - 2026-01-16

### Fixed
- **CLI --agent-help flags** - Fixed file path lookup for agent help documentation
  - Issue: `reveal --agent-help` and `reveal --agent-help-full` failed with "file not found"
  - Root cause: CLI handlers looked for AGENT_HELP*.md in wrong directory (reveal/ instead of reveal/docs/)
  - Solution: Updated path construction to include docs/ subdirectory
  - Impact: Agent help flags now work correctly
  - Files: reveal/cli/handlers.py (lines 69, 82)
  - Session: wise-helm-0116

- **git:// adapter help documentation** - Removed unimplemented query parameters
  - Issue: Help text documented 3 parameters that don't exist in code (since, until, author)
  - Impact: Users would try features that don't work, breaking trust
  - Solution: Removed broken example and unimplemented parameters from help text
  - Documentation accuracy: 57% → 100%
  - Files: reveal/adapters/git/adapter.py
  - Session: obsidian-canvas-0116

- **Package manifest** - Updated MANIFEST.in for docs/ subdirectory
  - Issue: MANIFEST.in referenced old paths (reveal/AGENT_HELP*.md)
  - Impact: Built packages would exclude help docs, breaking --agent-help flags
  - Solution: Changed to recursive-include reveal/docs *.md
  - Verified: Built wheel includes all docs/ files correctly
  - Files: MANIFEST.in
  - Session: wise-helm-0116

## [0.36.0] - 2026-01-15

### Fixed
- **stats:// adapter routing** - Fixed "Element not found" error when using stats://
  - Issue: Routing logic treated resource path as element name for adapters with render_element
  - Root cause: Line 193 in routing.py used `(element or resource)` check, causing stats://reveal to look for element 'reveal' instead of analyzing reveal/ directory
  - Solution: Added ELEMENT_NAMESPACE_ADAPTERS whitelist (env, python, help) to distinguish adapters where resource IS the element name vs adapters where resource is the analysis target
  - Impact: stats:// now works correctly for all path patterns (stats://., stats://dir, stats://?hotspots=true)
  - Verified: env://, python://, help://, ast://, json://, stats:// all working correctly
  - Session: wild-drought-0115

- **git:// adapter help references** - Removed broken help:// links
  - Removed: `help://git-guide` reference (doesn't exist, was Phase 5 from prior session)
  - Removed: `diff://git:file@v1 vs git:file@v2` example (broken - diff uses different git format)
  - Added: Valid cross-references to help://diff, help://ast, help://stats
  - Impact: Users following git:// help won't hit dead ends
  - Session: wild-drought-0115

- **diff:// adapter documentation** - Clarified git URI format
  - Updated features: Changed "Works with ANY adapter" to "Works with file paths, directories, and some adapters"
  - Added note: "diff git:// format differs from git:// adapter (uses git CLI directly)"
  - Clarification: diff:// uses `git://REF/path` format (e.g., git://HEAD/file.py) vs git:// adapter uses `git://path@REF` format
  - Impact: Users understand diff's git support is separate from GitAdapter
  - Session: wild-drought-0115

- **markdown:// query parameters routing** - Fixed by stats:// routing fix
  - Issue: Query parameters like `markdown://path?field=value` treated entire string as element name
  - Root cause: Same routing bug as stats:// (ELEMENT_NAMESPACE_ADAPTERS whitelist)
  - Solution: markdown not in whitelist, so resource goes to get_structure() not get_element()
  - Impact: Query filtering now works (e.g., `markdown://.?status=completed`)
  - Session: wild-drought-0115

- **Semantic blame element-not-found feedback** - Added user-visible note
  - Issue: When element not found in semantic blame query, silently fell back to full file blame
  - Solution: Added stderr note: "Element 'X' not found in path, showing full file blame"
  - Impact: Users get explicit feedback when element lookup fails
  - Verified: Warning shows for nonexistent elements, doesn't show for valid elements
  - Session: wild-drought-0115

### Added
- **diff:// git:// adapter integration** - Full support for git:// adapter URIs
  - **NEW**: diff:// now supports git:// adapter format: `diff://git://file@REF:git://file@REF`
  - Uses GitAdapter (pygit2) for semantic diffs between git refs
  - Backwards compatible: Legacy format `git://REF/path` still works (uses git CLI)
  - Auto-detects format: `@` symbol → adapter format, `/` symbol → CLI format
  - Example: `reveal diff://git://main.py@HEAD~5:git://main.py@HEAD`
  - Impact: Unified git:// syntax across adapters, semantic diff between any git refs
  - Session: wild-drought-0115


- **Dogfooding report** - Comprehensive real-world usage testing (internal-docs/research/DOGFOODING_REPORT_2026-01-15.md)
  - Tested: git:// semantic blame, structure exploration, help://, stats://, diff://, ast://, multiple adapters
  - Found: 6 issues (2 high priority, 2 medium, 2 low) - all high priority issues fixed this session
  - Validated: Core features work excellently, token efficiency proven (17-25x reduction in practice)
  - Session: wild-drought-0115

- **git:// adapter polish** - Production-ready git repository inspection (Phase 1-3)
  - **Phase 1**: Fixed CLI routing for git:// URIs (was broken - treated queries as element names)
  - **Phase 2**: Progressive disclosure for blame (summary view by default, detail mode with `&detail=full`)
    - Summary shows contributors, key hunks (94% token reduction: 216 hunks → ~15 lines)
    - Detail mode shows line-by-line blame (original behavior)
  - **Phase 3**: Semantic blame queries (KILLER FEATURE - unique to reveal)
    - Query blame by function/class: `git://file.py?type=blame&element=main`
    - Example: "Who wrote function X?" → direct answer without line number math
    - Filters hunks to element's line range automatically
    - Works with any language reveal analyzes (Python, JS, Rust, Go, etc.)
  - Updated help://git with all new features and query parameters
  - Token efficiency: <500 tokens for any git:// query (was 4800+ for blame)
  - Session: spinning-wormhole-0115

### Changed
- **README.md reverted to utility-first messaging** - Removed marketing fluff
  - Old title (from kiyuda-0115): "Trust and Legibility for AI-Assisted Development"
  - New title: "Progressive Code Exploration"
  - New lead: "Structure before content. Understand code by navigating it, not reading it."
  - Removed "Why Reveal?" AI trust gap section (aspirational, not validated)
  - Removed "🛡️ AI Safety Net" branding (overselling)
  - Removed "When to Use Reveal" personas (unvalidated use cases)
  - Added simple "Common Workflows" section with real, tested examples
  - **Impact**: External docs now match actual usage patterns, not aspirational positioning
  - **Rationale**: kiyuda-0115 leaked internal planning language (POSITIONING_STRATEGY.md) into external docs as if it were proven reality
  - Session: pulsing-horizon-0115
- **pyproject.toml description updated** - Utility-first language
  - Old (from kiyuda-0115): "Trust and legibility for AI-assisted development - verify code changes structurally"
  - New: "Progressive code exploration with semantic queries and structural diffs - understand code by navigating structure, not reading text"
  - Keywords updated: Removed "verification", "trust", "ai-safety" → Added "code-exploration", "ast", "tree-sitter"
  - **Impact**: PyPI listing focuses on actual capabilities, not aspirational use cases
  - Session: pulsing-horizon-0115
- **POSITIONING_STRATEGY.md marked as internal only** - Prevent future leakage
  - Added warning header: "INTERNAL PLANNING DOCUMENT"
  - Documented why warning exists (kiyuda-0115 leakage into external docs)
  - Clear guidance: Use for strategic discussions, NOT for external documentation
  - Session: pulsing-horizon-0115

### Added
- **WORKFLOW_RECIPES.md** - Task-based practical documentation
  - 8 workflows: code review, onboarding, debugging, refactoring, documentation, AI agents, databases, pipelines
  - Consolidates proven patterns from COOL_TRICKS.md and AGENT_HELP.md
  - Organized by task (what you want to do), not by feature (what reveal has)
  - Real commands for real use cases
  - No aspirational fluff, only tested workflows
  - **Impact**: Contributors and users get practical, task-oriented guidance
  - Session: pulsing-horizon-0115
- **PRACTICAL_UTILITY_ANALYSIS.md** - Internal analysis document
  - Comprehensive analysis separating real utility from marketing fluff
  - Identified 9 production-grade features with evidence (tests, docs, real usage)
  - Documented critical gaps (output schema, stability taxonomy, workflow recipes)
  - 5-phase consolidation plan (Phase 1-2 completed in pulsing-horizon-0115)
  - Session: pulsing-horizon-0115
- **Multi-language circular dependency detection (I002)** - Extended to JavaScript, Rust
  - I002 now uses dynamic extractor selection instead of Python-specific functions
  - Automatically supports all languages with import resolution (Python, JS, Rust)
  - File patterns auto-populated from extractor registry
  - Language-agnostic import graph building across entire project
  - Version bump to 2.0.0 (breaking: multi-language support)
  - Examples:
    - `reveal app.js --check --select I002` - Detect JS circular imports
    - `reveal src/lib.rs --check --select I002` - Detect Rust circular imports
    - Works with Python (existing), JavaScript, and Rust projects
  - Phase 5.4 complete: Multi-language import analysis (I001 + I002) production-ready
  - Session: sleeping-earth-0115

### Changed
- **I002 rule architecture** - Language-agnostic circular dependency detection
  - Replaced `extract_python_imports()` with `extractor.extract_imports()`
  - Replaced `resolve_python_import()` with `extractor.resolve_import()`
  - Dynamic file discovery for all supported extensions (not just .py)
  - Graph building works across multiple languages in same project
- **FileAnalyzer is now an Abstract Base Class (ABC)** - Enforces implementation contract
  - Added ABC inheritance and @abstractmethod decorator to get_structure()
  - Provides type safety and catches missing implementations at import time
  - No code changes needed - all 33 existing analyzers already compliant
  - Improves consistency with adapter and rule architectures (which are also ABCs)
  - Architecture validated against SOLID principles (Grade: A-)
  - Session: desert-squall-0115 validation, cursed-wizard-0115 implementation

### Fixed
- **GitAdapter backward compatibility** - Accept both `resource=` and `path=` parameters
  - Fixes 22 failing git adapter tests (TypeError on path= usage)
  - Maintains full backward compatibility with both calling styles
  - Improves git adapter test coverage from 15% to 64% (+234 lines covered)
  - All 23 git adapter tests now passing
  - Root cause: GitAdapter expected resource= but tests used path=
  - Solution: Parameter aliasing with sensible precedence and defaults
  - Session: desert-squall-0115, committed by cursed-wizard-0115

## [0.36.0] - 2026-01-14

### Added
- **Git repository inspection adapter (git://)** - Progressive disclosure for Git history
  - Repository overview with branches, tags, and recent commits
  - Branch/commit/tag exploration with full history
  - File inspection at any ref (commit, branch, tag)
  - File history tracking (commits that modified a file)
  - File blame functionality (who/when/why for each line)
  - Query parameters: `type=history|blame`, `since`, `until`, `author`, `limit`
  - Optional dependency: `pip install reveal-cli[git]`
  - Uses pygit2 (libgit2 bindings) for high performance
  - Comprehensive help: `reveal help://git`
  - Examples:
    - `reveal git://.` - Repository overview
    - `reveal git://.@main` - Branch history
    - `reveal git://src/app.py@v1.0` - File at specific tag
    - `reveal git://README.md?type=history` - File commit history
    - `reveal git://src/app.py?type=blame` - File blame annotations
  - 23 comprehensive tests with 82% code coverage
  - Enables temporal code exploration and archaeology

- **Introspection commands** - New commands for understanding how reveal analyzes files
  - `--explain-file` - Shows which analyzer will be used for a file, whether it's a fallback, and capabilities
  - `--show-ast` - Displays tree-sitter AST for files (tree-sitter analyzers only)
  - `--language-info <lang>` - Shows detailed information about a language's capabilities
  - Examples:
    - `reveal app.py --explain-file` - See which analyzer handles Python files
    - `reveal code.swift --explain-file` - Check if Swift uses fallback mode
    - `reveal app.py --show-ast` - View the tree-sitter AST structure
    - `reveal --language-info python` - Get Python analyzer capabilities
    - `reveal --language-info .rs` - Look up by extension

- **Tree-sitter fallback transparency** - Better visibility into fallback analyzer usage
  - Logging when fallback analyzers are created (INFO level with `--verbose`)
  - Fallback quality metadata (`basic` - functions, classes, imports only)
  - Metadata accessible via introspection API
  - Clear distinction between explicit analyzers (full featured) and fallbacks (basic)

- **Smart directory filtering** - Cleaner directory trees by default
  - Automatic `.gitignore` pattern support (respects project conventions)
  - 50+ default noise patterns (build artifacts, caches, dependencies)
  - New flags: `--respect-gitignore` (default: on), `--no-gitignore`, `--exclude PATTERN`
  - ~20-50% fewer entries shown in typical projects
  - Examples:
    - `reveal src/` - Automatically filters __pycache__, node_modules, etc.
    - `reveal . --exclude "*.log"` - Custom exclusion patterns
    - `reveal . --no-gitignore` - Disable gitignore filtering

- **Code quality validation rules** - Two new rules to catch issues proactively
  - **V016: Adapter help completeness** - Ensures all adapters provide `get_help()` documentation
  - **V017: Tree-sitter node type coverage** - Verifies TreeSitterAnalyzer has node types for all languages
  - Examples:
    - `reveal reveal/adapters/ --check --select V016` - Check adapter documentation
    - `reveal reveal/treesitter.py --check --select V017` - Verify node type coverage

### Changed
- **Centralized tree-sitter warning suppression** - DRY improvement
  - Created `reveal/core/` package with `treesitter_compat.py` module
  - Eliminated duplication across 3 files (registry.py, treesitter.py, ast.py)
  - Single source of truth for tree-sitter compatibility handling
  - Clear documentation of rationale and future migration path

### Fixed
- **Tree-sitter parsing completely broken** - `warnings` module not imported in `treesitter.py`
  - Affected: All tree-sitter based analyzers (Python, JavaScript, Rust, etc.)
  - Symptom: `--show-ast` failed silently, tree attribute always None
  - Root cause: Phase 1 centralized warning suppression but left unused `warnings.catch_warnings()` context manager
  - Fix: Removed redundant context manager (warnings already suppressed at module level)
  - Impact: Restores AST parsing for 50+ tree-sitter analyzers
- **Test failures in test_tree_view.py** - Updated tests to use new PathFilter parameter
  - Affected: TestCountEntries test class (3 tests failing)
  - Root cause: `_count_entries()` signature changed to require PathFilter but tests not updated
  - Fix: Added PathFilter instantiation in all test methods
  - Impact: All tree view tests now passing
- **Documentation drift in README** - Rules count updated from 47 to 49
  - Detected by V015 self-validation rule (working as designed)
  - Added V016-V017 (validation) to documentation

### Technical Notes
- All changes maintain backward compatibility
- No breaking API changes
- Test suite passes: 2,118 passing tests, 75% coverage

## [0.35.0] - 2026-01-13

### Added
- **SQLite database adapter (sqlite://)** - Zero-dependency database exploration
  - Database overview with schema summary, statistics, and configuration
  - Table structure inspection with columns, indexes, and foreign keys
  - Progressive disclosure pattern (database → table → details)
  - Uses Python's built-in sqlite3 module (no external dependencies)
  - Human-readable CLI output with table/view icons and relationship display
  - Comprehensive help system: `reveal help://sqlite`
  - Examples:
    - `reveal sqlite:///path/to/app.db` - Database overview
    - `reveal sqlite:///path/to/app.db/users` - Table structure
    - `reveal sqlite://./relative.db` - Relative paths supported
    - `reveal sqlite:///data/prod.db --format=json` - JSON output
  - Perfect for mobile, embedded, and development databases
  - 22 comprehensive tests with 98% code coverage

## [0.34.0] - 2026-01-10

### Added
- **Infrastructure-as-Code and API language support** - Expands reveal to infrastructure and API definition ecosystems
  - **HCL/Terraform** (.tf, .tfvars, .hcl files) - Infrastructure-as-Code (95% of cloud infra uses Terraform)
  - **GraphQL** (.graphql, .gql files) - API schema and query language (90% of modern APIs)
  - **Protocol Buffers** (.proto files) - gRPC and cross-language serialization (Google/FAANG standard)
  - **Zig** (.zig files) - Modern systems programming language (Rust alternative)
  - Tree-sitter parsing support for all 4 languages
  - Brings total language support from 34 to 38 languages

### Technical Notes
- New languages use base TreeSitterAnalyzer functionality
- Custom extraction logic (resources, types, messages) can be added in future releases
- All 2008 tests pass (100% pass rate maintained)

## [0.33.0] - 2026-01-10

### Added
- **Mobile platform language support** - Full support for mobile development ecosystems
  - **Kotlin** (.kt, .kts files) - Android and JVM development (8M+ developers)
  - **Swift** (.swift files) - iOS, macOS, iPadOS native development (5M+ developers)
  - **Dart** (.dart files) - Flutter cross-platform development (2M+ developers)
  - Automatic extraction of classes, functions, imports via tree-sitter
  - Brings total language support from 31 to 34 languages

### Changed
- **BREAKING: Migrated to tree-sitter-language-pack** - Modern, actively maintained parser library
  - Previous `tree-sitter-languages` package is officially unmaintained (last update Feb 2024)
  - New package supports 165+ languages (vs 50), includes mobile platforms
  - Upgraded tree-sitter core from 0.21.3 to 0.25.2 (latest)
  - API-compatible drop-in replacement - no user-facing changes
  - Pre-built wheels for all platforms (no compilation required)
  - Enhanced security: signed attestations via Sigstore, permissive licenses only
- **C# language name updated** - Internal parser reference changed from `c_sharp` to `csharp`
  (tree-sitter grammar convention)

### Known Issues
- **Test suite: 48 markdown/link tests need updates** - New tree-sitter grammars have improved
  AST structures requiring test adjustments. Core functionality unaffected (1960/2008 tests pass).
  Will be addressed in v0.33.1.

### Migration Notes
For developers extending Reveal: if you use tree-sitter directly, update imports:
- `from tree_sitter_languages import get_parser` → `from tree_sitter_language_pack import get_parser`

## [0.32.2] - 2026-01-08

### Fixed
- **MySQL adapter `.my.cnf` support completely broken** - Adapter always set explicit `host` and
  `port` values, causing pymysql to ignore `read_default_file` parameter
  - `reveal mysql://` now properly reads credentials from `~/.my.cnf` (600 permissions)
  - Enables proper Unix-style credential management (no passwords in env vars or process lists)
  - Fixed credential resolution order: URI params → env vars → `~/.my.cnf` → pymysql defaults
  - Added `MYSQL_PORT` environment variable support (was missing)
  - Verified on production with 187GB managed MySQL database
- **Rule categorization bug in `--rules` output** - F, N, and V rules displayed under wrong categories
  - F001-F005 (frontmatter validation) now correctly show under "F Rules" (was "M Rules")
  - N001-N003 (nginx configuration) now correctly show under "N Rules" (was "I Rules")
  - V001-V011 (reveal self-validation) now correctly show under "V Rules" (was "M Rules")
  - Root cause: `RulePrefix` enum was missing F, N, V entries
  - Total: 42 enabled rules properly organized into 12 categories

### Changed
- **.gitignore** - Added `.coverage.*` pattern to exclude pytest-xdist parallel coverage artifacts

## [0.32.1] - 2026-01-07

### Added
- **I004: Standard library shadowing detection** - New rule detects when local Python files
  shadow stdlib modules (e.g., `logging.py`, `json.py`, `types.py`)
  - Warns about potential import confusion and subtle bugs
  - Allows test files (`test_*.py`, `*_test.py`) and files in `tests/` directories
  - Supports `# noqa: I004` to suppress warnings
  - Provides rename suggestions (e.g., "consider `utils_logging.py` or `logger.py`")

### Fixed
- **Circular import false positive** - Files that shadow stdlib modules (like `logging.py`
  importing stdlib `logging`) no longer create false `A → A` self-dependency cycles
  - Fixed in both `imports://` adapter and I002 rule

### Changed
- **STDLIB_MODULES refactored to shared location** - Moved from B005 class attribute to
  `reveal.rules.imports` module for reuse by I004 and future rules

## [0.32.0] - 2026-01-07

### Added
- **`--related` flag for knowledge graph navigation** - Show related documents from front matter
  - Extracts links from `related`, `related_docs`, `see_also`, and `references` fields
  - Shows headings from each related document for quick context
  - Detects missing files, skips URLs and non-markdown files
  - Cycle detection prevents infinite loops
  - JSON output includes full resolved paths for tooling integration
- **Deep knowledge graph traversal** - Extended `--related` with unlimited depth support
  - `--related-depth N` - Now supports any depth (was limited to 1-2)
  - `--related-depth 0` - Unlimited traversal until graph exhausted
  - `--related-all` - Shorthand for `--related --related-depth 0`
  - `--related-flat` - Output flat list of paths (grep-friendly, pipeable)
  - `--related-limit N` - Safeguard to stop at N files (default: 100)
  - Summary header shows "N docs across M levels" for multi-level traversals
- **`markdown://` URI adapter** - Query markdown files by front matter
  - `reveal markdown://docs/` - List all markdown files in directory
  - `reveal 'markdown://?topics=reveal'` - Filter by field value
  - `reveal 'markdown://?!status'` - Find files missing a field
  - `reveal 'markdown://?type=*guide*'` - Wildcard matching
  - Multiple filters with AND logic: `field1=val1&field2=val2`
  - Recursive directory traversal
  - JSON and grep output formats for tooling
- **C# language support** (.cs files) - classes, interfaces, methods via tree-sitter
- **Scala language support** (.scala files) - classes, objects, traits, functions via tree-sitter
- **SQL language support** (.sql files) - tables, views, functions/procedures via tree-sitter
- **Workflow-aware breadcrumbs** (Phase 3)
  - Pre-commit workflow: After directory checks, suggests fix → review → commit flow
  - Code review workflow: After git-based diffs, suggests stats → circular imports → quality check flow
  - Context-sensitive numbered steps for guided workflows

### Fixed
- **`--related` crashes on dict-format frontmatter entries** - Related fields with structured
  entries like `{uri: "doc://path", title: "Title"}` now correctly extract the path from
  `uri`, `path`, `href`, `url`, or `file` fields. Also strips `doc://` prefix automatically.
- **MySQL adapter ignores MYSQL_HOST env var** - `reveal mysql://` now correctly uses
  MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE environment variables when
  URI doesn't specify these values
- **Validation rules (V001, V005, V007)** - Fixed path detection after docs reorganization
  - Rules now correctly find help files in `reveal/docs/` subdirectory
  - V007 AGENT_HELP path detection updated for new structure
- **AGENT_HELP.md** claimed Swift support (not available in tree_sitter_languages)
- **I003 rule missing category** - rule now correctly shows under "I Rules" instead of "UNKNOWN Rules" in `--rules` output
- **AGENT_HELP.md File Type Support** - Added missing JSONL, HTML, and LibreOffice formats to match README
- **README rule count** - Architecture section now correctly states 41 quality rules (was 24)
- **GitHub Stars badge URL** - Now correctly points to Semantic-Infrastructure-Lab/reveal
- **Test suite consolidation** - Recovered 197 orphaned tests (1793 → 1990 tests, 77% coverage)

### Changed
- **Project structure reorganized** for Python packaging best practices
  - Documentation moved to `reveal/docs/` (now ships with pip package)
  - Three-tier docs: user guides (packaged), internal docs (dev only), archived (historical)
  - Tests consolidated under `tests/` directory
- **Schema renamed: `beth` → `session`** for generic open source use
  - `session.yaml` schema for workflow/session README validation
  - `topics` field replaces `beth_topics`
  - Backward compatible: `load_schema('beth')` still works via alias
  - Generic `session_id` pattern (was TIA-specific `word-word-MMDD`)
- **MySQL credential resolution simplified** - Removed TIA-specific integration,
  now uses standard 3-tier resolution: URI > environment variables > ~/.my.cnf
- **Documentation cleaned for open source** - Removed internal references,
  updated examples to use generic paths and field names

## [0.31.0] - 2026-01-05

### Fixed
- **I001 now detects partial unused imports** (aligned with Ruff F401)
  - Previously only flagged imports when ALL names were unused
  - Now correctly flags each unused name individually
  - Example: `from typing import Dict, List` with only `List` used now flags `Dict`
- **Breadcrumbs: Added HTML to element placeholder mapping**
  - HTML files now correctly show `<element>` placeholder in breadcrumb hints

### Added
- **Enhanced breadcrumb system Phase 2 additions**:
  - **Post-check quality guidance**: After `--check`, suggests viewing complex functions, stats analysis
    - Detects complexity issues (C901, C902) and suggests viewing the specific function
    - Links to `stats://` and `help://rules` for further analysis
  - **diff:// workflow hints**: After `reveal help://diff`, shows practical try-it-now examples
    - Added related adapters mapping (diff→stats, ast; stats→ast, diff; imports→ast, stats)
    - Breadcrumbs after diff output suggest element-specific diffs, stats, and quality checks
  - **`--quiet` / `-q` scripting mode**: Alias for `--no-breadcrumbs` for scripting pipelines
  - **Test coverage**: 68 → 74 breadcrumb tests (100% coverage on breadcrumbs.py)

## [0.30.0] - 2026-01-05

### Breaking Changes
- **Minimum Python version raised to 3.10** (was 3.8)
  - Python 3.8 reached EOL in October 2024
  - Python 3.9 reaches EOL in October 2025
  - Code uses walrus operators (`:=`) and modern type hints compatible with 3.10+
  - CI now tests Python 3.10 and 3.12 on Ubuntu only (simplified from 3.8/3.12 on 3 platforms)
  - Users on Python 3.8/3.9 should use reveal-cli <0.30.0

### Fixed
- **Cross-platform CI test failures** (40 unique test failures across Ubuntu/Windows/macOS)
  - Added `pymysql` to dev dependencies (was only in `[database]` extras, tests failed on all platforms)
  - Fixed macOS symlink path resolution (`/var` vs `/private/var` mismatch)
  - Fixed config override path matching on macOS (symlink-aware `relative_to()`)
  - Fixed ignore pattern path matching on macOS (symlink-aware `relative_to()`)
  - Fixed L001 case sensitivity detection on case-insensitive filesystems (macOS HFS+)
  - **Fixed Windows Unicode encoding errors in test subprocess calls** (20 test failures on Windows)
    - Added `encoding='utf-8'` to all `subprocess.run()` calls in test files
    - Prevents `UnicodeDecodeError` when Windows cp1252 codepage can't decode UTF-8 output
    - Ensures consistent UTF-8 handling across all platforms (Linux, macOS, Windows)
    - Fixed in: test_builtin_schemas.py, test_schema_validation_cli.py, test_main_cli.py, test_cli_flags_integration.py, test_decorator_features.py, test_clipboard.py
  - **Fixed Windows Unicode file writing errors in tests** (2 additional test failures)
    - Added `encoding='utf-8'` to all `tempfile.NamedTemporaryFile()` and `Path.write_text()` calls
    - Prevents `UnicodeEncodeError` when writing Unicode content (Chinese, Russian, Japanese, emoji) to test files
    - Fixed in: test_builtin_schemas.py (21 instances), test_schema_validation_cli.py (1 instance)
  - All 1,339 tests now pass on Linux and macOS; Windows CI expected to be fully green with encoding fixes

### Changed
- **lxml is now optional** (moved to `[html]` extras for HTML analyzer performance)
  - HTML analyzer uses stdlib `html.parser` by default (no C dependencies required)
  - Install `pip install reveal-cli[html]` for faster lxml-based parsing (requires system libs: libxml2-dev, libxslt1-dev)
  - Graceful fallback ensures HTML analysis works on all platforms without build tools
  - Fixes CI failures since v0.17.0 (Dec 2025) caused by lxml C extension build issues
- **Refactored 3 high-complexity hotspots** using Extract Method pattern
  - `analyzers/markdown.py`: Extracted `_extract_links` into 4 focused helpers (64→18 lines, quality 84.6→85.3/100)
  - `adapters/mysql/adapter.py`: Extracted `get_structure` into 4 subsystem builders (135→66 lines, removed from top 10 hotspots)
  - `adapters/python/help.py`: Extracted `get_help` into 2 data builders (152→94 lines, quality 55→passing, removed from top 10 hotspots)
  - Overall quality improved from 97.2/100 to 97.4/100
  - Established refactoring patterns: Nested Traversal→Extract Navigation, Monolithic Orchestration→Extract Builders

### Added
- **Ruby 💎 and Lua 🌙 language support** (3-line tree-sitter pattern)
  - Ruby: Extracts classes, methods, modules via tree-sitter
  - Lua: Extracts global and local functions (game development, embedded scripting)
  - Added node type support: `method` (Ruby), `function_definition_statement` and `local_function_definition_statement` (Lua)
  - Total built-in languages: 28 → 30
- **`diff://` Adapter - Semantic Structural Diff**
  - **Semantic comparison**: Compare functions, classes, and imports - not just text lines
  - **File diffing**: `diff://app.py:backup/app.py` shows structural changes (signature, complexity, line count)
  - **Directory diffing**: `diff://src/:backup/src/` aggregates changes across all analyzable files
  - **Git integration**: Compare commits, branches, and working tree
    - `diff://git://HEAD~1/file.py:git://HEAD/file.py` - Compare across commits
    - `diff://git://HEAD/src/:src/` - Pre-commit validation (uncommitted changes)
    - `diff://git://main/.:git://feature/.:` - Branch comparison (merge impact assessment)
  - **Element-specific diffs**: `diff://app.py:new.py/handle_request` compares specific function
  - **Cross-adapter composition**: Works with ANY adapter (env://, mysql://, etc.)
  - **Progressive disclosure**: Summary (counts) → Details (changes) → Context (file paths)
  - **Two-level output**: Aggregate summary + per-element details with old→new values
  - **Usage**: `reveal diff://app.py:backup.py`, `reveal diff://git://HEAD/src/:src/ --format=json`
  - **Test coverage**: 34 tests (100% pass rate), 77% coverage on diff.py
  - **Documentation**: README examples, enhanced help text (`reveal help://diff`), docs/DIFF_ADAPTER_GUIDE.md guide
  - **Git URI format**: `git://REF/path` (REF = HEAD, HEAD~1, main, branch-name, commit-sha)
  - **Directory handling**: Skips common ignore dirs (.git, node_modules, __pycache__, etc.)
  - **Composition pattern**: Delegates to existing adapters (file analyzers, env://, mysql://, etc.)
- **Smart breadcrumb system with contextual suggestions** (Phase 1)
  - **Configurable breadcrumbs**: Multi-layer config support (global, project, env vars)
  - **File-type specific suggestions**: Markdown (--links), HTML (--check, --links), YAML/JSON/TOML (--check), Dockerfile/Nginx (--check)
  - **Large file detection**: Files with >20 elements suggest AST queries (`ast://file.py?complexity>10`)
  - **Import analysis hints**: Files with >5 imports suggest `imports://file.py` for dependency analysis
  - **Supports**: Python, JavaScript, TypeScript, Rust, Go
  - **Test coverage**: 68 breadcrumb tests (100% coverage on breadcrumbs.py)
- **19 comprehensive integration tests** covering critical gaps
  - 10 URI query parameter tests for `stats://` adapter (validates `?hotspots=true&min_complexity=10` syntax)
  - 9 tests for refactored markdown.py link helpers (validates extraction, filtering, edge cases)
  - Test coverage improved from 75% to 77%
  - stats.py coverage improved from 84% to 92% (+8%)

### Removed
- **Kotlin language support** removed before release
  - Tree-sitter grammar had upstream limitations preventing reliable function extraction
  - Class extraction worked, but partial support deemed insufficient
  - Removed Kotlin analyzer, file extensions (.kt, .kts), and `object_declaration` node type
  - Focus on languages with reliable tree-sitter grammars (Ruby, Lua working well)
  - Can be re-added when upstream grammar improves

## [0.29.0] - 2026-01-03

### Added
- **Schema Validation for Markdown Front Matter (`--validate-schema`)**
  - **Built-in schemas**: beth (TIA sessions), hugo (static sites), jekyll (GitHub Pages), mkdocs (Python docs), obsidian (knowledge bases)
  - **F-series quality rules**: F001-F005 for front matter validation
    - F001: Detect missing front matter
    - F002: Detect empty front matter
    - F003: Check for required fields
    - F004: Validate field types (string, list, dict, integer, boolean, date)
    - F005: Run custom validation rules
  - **SchemaLoader**: Loads schemas by name or file path with caching
  - **Custom schema support**: Create project-specific validation with YAML schemas
  - **Multiple output formats**: text (human-readable), json (CI/CD), grep (pipeable)
  - **Exit codes**: 0 for pass, 1 for failure (CI/CD integration ready)
  - **CLI flag**: `--validate-schema <name-or-path>`
  - **Usage**: `reveal README.md --validate-schema session`
  - **Implementation**: 5 phases complete across 4 sessions (garnet-ember-0102, amber-rainbow-0102, dark-constellation-0102, pearl-spark-0102)
  - **Test coverage**: 103 comprehensive tests (27 loader + 44 rules + 33 CLI + 43 schemas), 100% passing, 75% coverage overall
  - **Documentation**: 800+ line [Schema Validation Guide](reveal/docs/SCHEMA_VALIDATION_HELP.md)

- **Session Schema (`session.yaml`)** - Workflow/session README validation (renamed from `beth` in v0.32.0)
  - Required fields: `session_id`, `topics` (min 1 topic)
  - Optional fields: date, badge, type, project, files_modified, files_created, commits
  - Custom validation: session_id format checking, topic count validation
  - Backward compatible: `--validate-schema beth` still works via alias

- **Hugo Schema (`hugo.yaml`)** - Static site front matter validation
  - Required fields: `title` (non-empty)
  - Optional fields: date, draft, tags, categories, description, author, slug, weight, etc.
  - Custom validation: title length, date format checking
  - **Dogfooded:** Fixed on SIF website (date moved to optional after real-world validation)

- **Jekyll Schema (`jekyll.yaml`)** - GitHub Pages front matter validation
  - Required fields: `layout` (best practice enforcement)
  - Optional fields: title, date, categories, tags, author, permalink, excerpt, published, etc.
  - Custom validation: layout non-empty, permalink format, date validation, published boolean
  - **Community reach:** 1M+ GitHub Pages users

- **MkDocs Schema (`mkdocs.yaml`)** - Python documentation front matter validation
  - No required fields (all optional, following MkDocs philosophy)
  - Optional fields: title, description, template, icon, status, tags, hide, authors, date, etc.
  - Material theme support: hide (navigation/toc/footer), status (new/deprecated/beta/experimental)
  - Custom validation: hide options, status values, date format, tags minimum count
  - **Community reach:** Large Python ecosystem (FastAPI, NumPy, Pydantic patterns)
  - **Enhanced safe eval:** Added `all` and `any` builtins for list validation

- **Obsidian Schema (`obsidian.yaml`)** - Knowledge base note validation
  - No required fields (fully optional front matter)
  - Optional fields: tags, aliases, cssclass, publish, created, modified, rating, priority, etc.
  - Custom validation: tag count (if specified), rating range (1-5), priority range (1-5)

- **Validation Engine** - Schema-aware rule infrastructure
  - Safe Python expression evaluation for custom rules (restricted builtins)
  - Global schema context management (set/get/clear)
  - Type validation with YAML auto-parsing support (datetime.date objects)
  - Available functions: len(), re.match(), isinstance(), str(), int(), bool()
  - Security: No file I/O, no network, no command execution

- **`--list-schemas` Flag** - Discover available schemas
  - Lists all built-in schemas with descriptions and required fields
  - Professional formatted output for easy reference
  - Usage: `reveal --list-schemas`
  - Improves discoverability (previously had to trigger error to see schemas)

- **Comprehensive Duplicate Detection Guide** (DUPLICATE_DETECTION_GUIDE.md)
  - 488 lines covering D001 (exact duplicates) and D002 (similar code)
  - Clear status indicators: ✅ works, ⚠️ experimental, 🚧 planned
  - Documented D002 false positive rate (~90%) with examples
  - Practical workarounds for cross-file detection using `ast://` queries
  - Workflows, limitations, best practices, FAQ, roadmap
  - Integrated into help system: `reveal help://duplicates`

- **URI Parameter Support for stats://** - Query parameters as alternative to global flags
  - Three-tier parameter model: global flags → URI params → element paths
  - **Parameters**: `?hotspots=true`, `?min_lines=N`, `?min_complexity=N`
  - **Usage**: `reveal stats://reveal?hotspots=true&min_complexity=10`
  - **Migration hints**: Helpful error messages guide users from old flag syntax
  - **Implementation**: Query parameter parsing, validation, documentation
  - Files: stats.py (+56 lines), routing.py (+11 lines), scheme_handlers/stats.py (+20 lines)
  - Documentation: AGENT_HELP.md (+37 lines), AGENT_HELP_FULL.md (+29 lines)

### Changed
- **Date Type Handling**: Enhanced to support YAML auto-parsed dates
  - `validate_type()` now accepts both `datetime.date` objects AND strings for "date" type
  - Handles PyYAML's automatic date parsing (`2026-01-02` → `datetime.date` object)
  - Backward compatible with string dates
  - Added `isinstance` to safe eval builtins for custom validation rules

- **Schema Validation Exit Codes**: Proper CI/CD integration
  - Returns exit code 1 when validation detects issues
  - Returns exit code 0 when validation passes
  - Enables use in pre-commit hooks and GitHub Actions

- **F-Series Rule Defaults**: Focused validation output
  - `--validate-schema` defaults to F-series rules only (not all rules)
  - User can override with `--select` to include other rule categories
  - Cleaner, more focused output for schema validation

### Fixed
- **Schema Validation UX Improvements** (from dogfooding reveal on itself)
  - **Confusing error messages**: Changed validation exception logging from error to debug level
    - Previously: "object of type 'int' has no len()" confused users
    - Now: Clean type mismatch errors only (F004 reports the actual issue)
  - **Non-markdown file warning**: Added warning when validating non-.md files
    - Schema validation designed for markdown front matter
    - Non-breaking (continues with warning to stderr)
  - Impact: Better first-time user experience, clearer error messages

- **Misleading Duplicate Detection Documentation**
  - Removed cross-file detection examples from AGENT_HELP_FULL.md (feature not implemented)
  - Added explicit warning: "Cross-file duplicate detection is not yet implemented"
  - Updated examples to reflect actual single-file behavior
  - Enhanced AGENT_HELP.md with status indicators and workarounds

- **Test Suite Quality**: Fixed pre-existing test data issues
  - Corrected invalid session_id patterns in edge case tests
  - Updated test data to match Beth schema requirements
  - All 1,320 tests now passing (100%)

- **Version Metadata Consistency** (from comprehensive validation)
  - Updated version footers in AGENT_HELP.md (0.24.2 → 0.29.0)
  - Updated version footers in AGENT_HELP_FULL.md (0.26.0 → 0.29.0)
  - Updated version in HELP_SYSTEM_GUIDE.md (0.23.1 → 0.29.0, 2 occurrences)
  - Updated metadata version in adapters/imports.py (0.28.0 → 0.29.0)
  - Impact: Consistent version reporting across all documentation

- **Configuration Guide Documentation** (from validation testing)
  - Fixed override `files` pattern syntax (array → string, 7 occurrences)
  - **Before**: `files: ["tests/**/*.py"]` (caused validation errors)
  - **After**: `files: "tests/**/*.py"` (matches schema)
  - Impact: Users copying examples no longer get validation errors

### Dogfooding
- **Reveal on itself:** Comprehensive validation (25+ scenarios, v0.29.0 production readiness)
  - Tested: basic analysis, element extraction, quality checks, schema validation, custom schemas, all output formats, help system, URI adapters, URI parameters, edge cases
  - Code quality analysis: 191 files, 42,161 lines, 1,177 functions, 173 classes
  - Quality score: **97.2/100** (from `reveal stats://reveal?hotspots=true`)
  - Hotspots identified: 10 files with quality issues (config.py: 91.7/100, markdown.py: 84.6/100)
  - Most complex function: `analyzers/markdown.py:_extract_links` (complexity 38)
  - URI parameter validation: `reveal stats://reveal?hotspots=true&min_complexity=10` works perfectly
  - Issues found: 3 UX issues (confusing errors, missing --list-schemas, no non-markdown warning)
  - All issues fixed in this release
  - Result: v0.29.0 validated through real-world use

- **Hugo schema validation:** Tested on SIF website (5 pages)
  - Found issue: `date` field required but static pages don't need dates
  - Fixed: Moved `date` from required → optional
  - Result: All 5 SIF pages now validate correctly

- **Beth schema validation:** Tested on 24 TIA session READMEs
  - Pass rate: 66% (16/24)
  - Issues found: 6 missing front matter, 2 wrong field names
  - Proves schema validation catches real quality issues

- **Web research validation:** All schemas validated against official documentation
  - Hugo: https://gohugo.io/content-management/front-matter/
  - Jekyll: https://jekyllrb.com/docs/front-matter/
  - MkDocs: https://squidfunk.github.io/mkdocs-material/reference/

### Documentation
- **docs/SCHEMA_VALIDATION_GUIDE.md** (808 lines)
  - Complete reference for all five built-in schemas
  - Custom schema creation guide with examples
  - CI/CD integration examples (GitHub Actions, GitLab CI, pre-commit hooks)
  - Output format documentation (text, json, grep)
  - Troubleshooting guide and FAQ
  - Command-line reference
  - Common workflows and batch validation patterns

- **reveal/DUPLICATE_DETECTION_GUIDE.md** (488 lines)
  - Comprehensive guide for D001 (exact duplicates) and D002 (similar code)
  - Clear documentation of implemented vs planned features
  - Practical workarounds for cross-file detection using AST queries
  - Workflows, limitations, best practices, FAQ, roadmap
  - Accessible via `reveal help://duplicates`

- **reveal/AGENT_HELP.md**: Enhanced duplicate detection and schema validation
  - Expanded duplicate detection from 4 to 28 lines with status indicators
  - Added cross-file workaround patterns using `ast://` queries
  - Added schema validation section with practical examples
  - Built-in schemas reference, F-series rules overview, exit codes
  - Updated version to 0.29.0

- **reveal/AGENT_HELP_FULL.md**: Fixed misleading duplicate detection examples
  - Removed cross-file detection example (feature not implemented)
  - Added explicit warnings about limitations
  - Updated output examples to reflect actual single-file behavior
  - Added 3-step AST query workaround

- **README.md**: Added Schema Validation feature section
  - Quick start examples for all five built-in schemas
  - Custom schema usage
  - CI/CD integration example
  - Added F001-F005 to rule categories list
  - Link to comprehensive guide

- **reveal/CONFIGURATION_GUIDE.md**: Updated to v0.29.0

### Performance
- **Zero Performance Impact**: Schema validation only runs with `--validate-schema` flag
- **Instant Validation**: F001-F005 rules execute in milliseconds
- **Efficient Caching**: Schemas cached after first load

### Security
- **Safe Expression Evaluation**: Custom validation rules use restricted eval
  - Whitelisted functions only (len, re, isinstance, type conversions)
  - No `__builtins__`, `__import__`, exec, eval, compile
  - No file I/O or network operations
  - No system command execution

## [0.28.0] - 2026-01-02

### Added
- **`imports://` Adapter - Import Graph Analysis**
  - **Multi-language support**: Python, JavaScript, TypeScript, Go, Rust
  - **Unused import detection (I001)**: Find imports that are never used in code
  - **Circular dependency detection (I002)**: Identify import cycles via topological sort
  - **Layer violation detection (I003)**: Enforce architectural boundaries (requires `.reveal.yaml`)
  - **Plugin-based architecture**: Elegant ABC + registry pattern for language extractors
    - `@register_extractor` decorator for zero-touch language additions
    - Type-first dispatch (file extension → extractor)
    - Mirrors Reveal's adapter registry pattern exactly
  - **Query parameters**: `?unused`, `?circular`, `?violations` for focused analysis
  - **Element extraction**: Get specific file imports via `imports://path file.py`
  - **Usage**: `reveal imports://src`, `reveal 'imports://src?unused'`, `reveal imports://src --check`
  - **Implementation**: Phases 1-5 complete (foundation, unused detection, circular deps, layer violations, multi-language)
  - **Test coverage**: 94% on adapter, 63 dedicated tests, zero regressions
  - **Documentation**: `internal-docs/planning/IMPORTS_IMPLEMENTATION_PLAN.md` (1,134 lines)
- **V-series Validation Enhancements**: Improved release process automation
  - **V007 (extended)**: Now checks ROADMAP.md and README.md version consistency
  - **V009 (new)**: Documentation cross-reference validation - detects broken markdown links
  - **V011 (new)**: Release readiness checklist - validates CHANGELOG dates and ROADMAP completeness
  - Total validation rules: V001-V011 (10 rules for reveal's self-checks)
- **Architectural Diligence Documentation**: Comprehensive development standards
  - `internal-docs/ARCHITECTURAL_DILIGENCE.md` - 970+ line living document
  - Defines separation of concerns (public/self-validation/dev layers)
  - Documents quality standards by layer
  - Includes pre-release validation checklist
  - Provides decision trees for code placement
  - Establishes long-term architectural vision (3-year roadmap)
- **Strategic Documentation Review**: Complete documentation audit
  - `internal-docs/STRATEGIC_DOCUMENTATION_REVIEW.md` - 430+ lines
  - Validates coherence across all planning documents
  - Identifies scope overlaps and timeline conflicts
  - Provides practical 6-month roadmap with feasibility analysis
  - Recommends phased language rollout strategy (Python-first)
- **Intent Lenses Design**: Community-curated relevance system
  - `internal-docs/planning/INTENT_LENSES_DESIGN.md` - 577 lines
  - SIL-aligned approach to progressive disclosure
  - Typed metadata (not prose) for agent-friendly navigation
  - Deferred to v0.30.0+ for proper strategic sequencing
- **Pre-Release Validation Script**: Automated quality gate
  - `scripts/pre-release-check.sh` - Comprehensive 8-step validation
  - Blocks releases with quality issues (V-series, tests, coverage, docs)
  - Provides clear next-steps output when all checks pass
  - Integrates with existing release workflow
- **Shared Validation Utilities**: Eliminated code duplication
  - `reveal/rules/validation/utils.py` - Shared helper functions
  - `find_reveal_root()` extracted from V007, V009, V011
  - Reduces duplication, improves maintainability
- **`reveal://config` - Configuration Transparency**
  - **Self-inspection**: Show active configuration with full transparency
  - **Sources tracking**: Display environment variables, config files (project/user/system), and CLI overrides
  - **Precedence visualization**: Clear 7-level hierarchy from CLI flags to built-in defaults
  - **Metadata display**: Project root, working directory, file counts, no-config mode status
  - **Multiple formats**: Text output for humans, JSON for scripting (`--format json`)
  - **Debugging aid**: Troubleshoot configuration issues by seeing exactly what's loaded and from where
  - **Usage**: `reveal reveal://config` for text, `reveal reveal://config --format json` for scripting
  - **Documentation**: Integrated into `help://reveal` and `help://configuration`
  - **Test coverage**: 9 comprehensive tests, 100% pass rate, increases reveal.py coverage 45% → 82%

### Changed
- **V007 Code Quality**: Refactored for clarity and maintainability
  - Reduced check() method from 105 lines to 29 lines (73% reduction)
  - Extracted helper methods: `_get_canonical_version()`, `_check_project_files()`
  - Eliminated duplicate `_find_reveal_root()` code
  - Fixed blocking C902 error (function too long)
  - Improved from 10 quality issues down to 3
- **V009 Code Quality**: Refactored for zero complexity violations
  - Extracted helper methods: `_get_file_path_context()`, `_process_link()`, `_is_external_link()`
  - Reduced complexity: check() from 14 to <10, _extract_markdown_links() from 13 to <10
  - Improved from 2 issues to 0 issues (✅ completely clean)
  - Better separation of concerns: context setup, link extraction, link processing, validation
  - Uses `find_reveal_root()` from shared utils module
- **V011 Code Quality**: Refactored for clarity and maintainability
  - Extracted validation methods: `_validate_changelog()`, `_validate_roadmap_shipped()`, `_validate_roadmap_version()`
  - Added `_get_canonical_version()` helper method
  - Reduced complexity: check() from 27 to below threshold
  - Fixed all line length issues (E501)
  - Improved from 10 quality issues down to 0 (✅ completely clean)
  - Uses `find_reveal_root()` from shared utils module
- **V-Series Quality Summary**: 100% elimination of quality issues
  - Session 1 (magenta-paint-0101): V009 (5→2), V011 (10→0)
  - Session 2 (continuation): V009 (2→0) ✅
  - Final: V009 (0 issues), V011 (0 issues) = 0 total issues
  - All V-series rules now meet their own quality standards
  - All tests passing (1010/1010)
  - 74% code coverage maintained
- **ROADMAP.md**: Aligned with implementation reality
  - Moved `.reveal.yaml` config to v0.28.0 (where it's actually planned)
  - Clarified Python-first strategy with phased language rollout
  - Added v0.28.1-v0.28.5 incremental releases (one language each)
  - Documented architecture:// adapter for v0.29.0
  - Deferred Intent Lenses to v0.30.0 for strategic focus
- **Test Suite**: Updated for shared utilities
  - All validation tests now use `find_reveal_root()` from utils
  - New test: `test_find_reveal_root_utility()` validates shared function
  - Removed obsolete `test_all_rules_have_find_reveal_root()`
- **Planning Documentation**: Reorganized and indexed
  - Updated `internal-docs/planning/README.md` with Intent Lenses reference
  - Added "Future Ideas (Exploration)" section
  - Clear separation of active vs. reference documents
- **README**: Updated with imports:// adapter and examples
  - Added imports:// to URI adapters section with usage examples
  - Updated adapter count from 8 to 9 built-in adapters
  - Updated rule count from 31 to 33 rules (V009, V011 added)
- **Import Extractors - Tree-Sitter Architectural Refactor**: Achieved full consistency
  - **JavaScript/TypeScript extractor**: Replaced regex parsing with tree-sitter nodes (`import_statement`, `call_expression`)
    - Handles ES6 imports, CommonJS require(), dynamic import()
    - Coverage: 88%, all 11 tests passing
  - **Go extractor**: Replaced regex parsing with tree-sitter nodes (`import_spec`)
    - Unified handling for single/grouped/aliased/dot/blank imports
    - Coverage: 90%, all 7 tests passing
  - **Rust extractor**: Replaced regex parsing with tree-sitter nodes (`use_declaration`)
    - Cleaner handling of nested/glob/aliased use statements
    - Coverage: 91%, all 10 tests passing
  - **Python extractor**: Already using tree-sitter (completed in prior session)
    - Coverage: 76%, all 23 tests passing
  - **Architectural consistency achieved**: All import extractors now use TreeSitterAnalyzer
  - **Improved fault tolerance**: Tree-sitter creates partial trees for broken code (better than ast.parse())
  - **Documentation**: Added "Architectural Evolution" section to IMPORTS_IMPLEMENTATION_PLAN.md
  - **Total test coverage**: 51/51 import tests passing (100%), 1086/1086 overall tests passing

### Fixed
- **imports:// Relative Path Resolution**: Fixed URL parsing to support both relative and absolute paths
  - `imports://relative/path` now correctly interprets as relative path (not absolute `/relative/path`)
  - URL netloc component is now combined with path for proper resolution
  - Both `imports:///absolute/path` (triple slash) and `imports://relative/path` (double slash) work correctly
- **Test Expectations**: Updated test_syntax_error_handling for improved tree-sitter behavior
  - Old behavior (ast.parse): Crash on syntax errors, return 0 detections
  - New behavior (tree-sitter): Extract valid imports from broken code, return detections
  - Test now validates improved fault tolerance instead of crash-and-give-up behavior

### Documentation
- Established architectural boundaries and quality standards
- Defined diligent path for reveal development and maintenance
- Created comprehensive contributor guidelines
- Validated documentation coherence across all planning docs
- Reconciled roadmap with implementation plans
- Created 6-month practical strategy (v0.28-v0.30)

## [0.27.1] - 2025-12-31

### Changed
- **Code Quality Improvements**: Extensive refactoring for better maintainability
  - Broke down large functions (100-300 lines) into focused helpers (10-50 lines)
  - Improved Single Responsibility Principle adherence
  - Reduced cyclomatic complexity for better testability
  - Files refactored: help.py, parser.py, formatting.py, main.py, L003.py
  - 754 insertions, 366 deletions (function extraction, no logic changes)

### Technical
- 988/988 tests passing (100% pass rate maintained)
- 74% code coverage maintained
- Zero functional changes - pure internal improvements
- Session: ancient-satellite-1231

## [0.27.0] - 2025-12-31

### Added
- **reveal:// Element Extraction**: Extract specific code elements from reveal's own source
  - `reveal reveal://rules/links/L001.py _extract_anchors_from_markdown` extracts function
  - `reveal reveal://analyzers/markdown.py MarkdownAnalyzer` extracts class
  - Works with any file type in reveal's codebase (Python, Markdown, etc.)
  - Self-referential: Can extract reveal's own code using reveal
  - Added 8 new tests for element extraction and component filtering

### Documentation
- Updated `reveal help://reveal` with element extraction examples and workflow
- Added element extraction section to COOL_TRICKS.md
- Added README examples for reveal:// element extraction

### Technical
- 988/988 tests passing (up from 773 in v0.26.0)
- 74% code coverage (up from 67%)
- Sessions: wrathful-eclipse-1223, cloudy-flood-1231, ancient-satellite-1231

## [0.26.0] - 2025-12-23

### ✨ NEW: Link Validation Complete

**Anchor validation, improved root detection, and reveal:// enhancements!**

This release completes the link validation feature with anchor support, fixes dogfooding issues discovered while using reveal on itself, and improves development workflows.

### Added
- **L001 Anchor Validation**: Full support for heading anchor links in markdown
  - Extract headings from markdown files using GitHub Flavored Markdown slug algorithm
  - Validate anchor-only links (like `#heading` references)
  - Validate file+anchor links (like `file.md#heading` references)
  - Detects broken anchors and suggests valid alternatives
- **reveal:// Component Filtering**: Path-based filtering now works
  - `reveal reveal://analyzers` shows only analyzers (15 items)
  - `reveal reveal://adapters` shows only adapters (8 items)
  - `reveal reveal://rules` shows only rules (32 items)
- **Smart Root Detection**: Prefer git checkouts over installed packages
  - Search from CWD upward for reveal/ directory with pyproject.toml
  - Support `REVEAL_DEV_ROOT` environment variable for explicit override
  - Fixes confusing behavior where `reveal:// --check` found wrong root

### Fixed
- **Logging**: Added debug logging to 9 bare exception handlers (main.py, html.py, markdown.py, office/base.py)
- **MySQL Errors**: Improved pymysql missing dependency errors (fail-fast in `__init__`)
- **Version References**: Updated outdated v0.18.0 → v0.27 references in help text
- **reveal:// Rendering**: Renderer now handles partial structure dicts correctly

### Changed
- **Link Validation Tests**: Comprehensive test coverage for L001, L002, L003 rules (594 lines, 28 tests)
- **Documentation**: Updated README with link validation section and correct rule count (32 rules)
- **Roadmap**: Updated to reflect v0.25.0 shipped, v0.26 planning

### Technical
- 773/773 tests passing (100% pass rate)
- 67% code coverage maintained
- Zero regressions introduced
- Sessions: charcoal-dye-1223, garnet-dye-1223


---

## Links

- **GitHub**: https://github.com/Semantic-Infrastructure-Lab/reveal
- **PyPI**: https://pypi.org/project/reveal-cli/
- **Issues**: https://github.com/Semantic-Infrastructure-Lab/reveal/issues
