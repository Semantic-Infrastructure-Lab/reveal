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

## [Unreleased] - (session majevebo-0417)

### Maintenance
- **`reveal_structure` and `reveal_query` MCP tools off `_capture()`** — `reveal_structure` directory case now calls `show_directory_tree()` directly (returns a string; no stdout capture at all). File case and `reveal_query` use `_run_and_capture()`, a lock-free replacement for `_capture()`. Global `_capture_lock` and `threading` import removed. All 5 MCP tools no longer use the global-lock capture helper. (BACK-193)

---

## [0.80.0] - 2026-04-17 (sessions fractal-zealot-0417, jade-beam-0417, vobage-0417, kotowiro-0417, butajiko-0417)

### Fixed
- **`help://schemas --format=json` now returns structured listing** — bare `help://schemas` with `--format=json` previously returned `{"error": "No adapter specified"}`. Now returns `{"type":"adapter_schema","available_adapters":[...],"usage":"..."}`. Text rendering unchanged. (BACK-188)
- **`claude://` help text shows all URI forms** — `help://claude` and `help://adapters` previously showed only `claude://session/{name}`. Now documents all 10 forms: bare listing, `?search=`, session-scoped, `info`, `config`, `history`, `plans`, `memory`, `agents`, `hooks`. (BACK-190)
- **`depends://` missing from `help://relationships` cluster** — adapter was registered but absent from all clusters, causing the dynamic count to read 22 instead of 23. Added to Code Analysis cluster with `imports↔depends` pair. (BACK-189)
- **Hardcoded "22 adapters" in `mcp_server.py` and `MCP_SETUP.md`** — updated to 23. (BACK-189)
- **`review.py` subprocess calls replaced with direct internal API** — `_run_check`, `_run_hotspots`, `_run_complexity`, `_run_diff` previously shelled out to `reveal` via subprocess. Now call `_check_files_json`, `StatsAdapter`, `AstAdapter`, `DiffAdapter` directly. Also fixed latent bug: `_run_check` was calling `data.get('violations', [])` but `reveal check --format=json` emits `{files, summary}`, so checks always returned `[]`. (BACK-181)
- **`reveal_check()` MCP tool no longer uses `_capture()`** — replaced `_capture(run_check, args)` with direct `_check_files_json` call. Violations serialized to human-readable text at the MCP boundary. No global lock, no stdout redirection, no `SystemExit` catching. Proof-of-concept for BACK-182; remaining 4 MCP tools need display-layer structured returns before the same refactor applies. (BACK-182 partial)
- **`reveal_pack()` MCP tool no longer uses `_capture()`** — calls `_parse_budget`, `_get_changed_files`, `_collect_candidates`, `_apply_budget`, `_collect_file_contents` directly. Content and file listing rendered as text at the MCP boundary. No global lock, no stdout capture. (BACK-193 partial)
- **`reveal_element()` MCP tool no longer uses `_capture()`** — calls `get_analyzer` + `_parse_element_syntax` + `_extract_by_syntax` directly; formats result dict at the MCP boundary. No global lock, no stdout redirection. 3 of 5 MCP tools now use direct APIs; only `reveal_structure` and `reveal_query` remain on `_capture()`. (BACK-182 partial)

### Added
- **Section extraction: match count prefix for multi-section results** — when a substring query matches N sections (e.g., `reveal book.md "CHAPTER"` matches 16 headings), output now begins with `# N sections matched "QUERY" — showing all`. Mirrors the `Matched: N of M files` pattern already used by `markdown://`. (BACK-191b, M1)
- **`--outline` shows section size in lines for markdown headings** — each heading in `reveal file.md --outline` now shows `, N lines` after the line number (e.g., `THE KERNEL (file.md:1347, 153 lines)`). Size is computed via `_section_end` — spans all content including sub-headings. Mirrors the `[N lines, depth:M]` already shown for code elements. (BACK-191c, M2)
- **`markdown://` listing: `?fields=f1,f2` param adds frontmatter columns** — `reveal 'markdown://primitives/?type=framework&fields=book,cohort'` appends `book=X cohort=Y` inline on each result row. Fields missing from a file's frontmatter are silently omitted. Combines with all existing filters. (BACK-191d, M3)
- **Section extraction: short-result warning with next-section hint** — when a single section returns ≤ 5 lines and a next heading follows immediately, stderr shows `⚠ Short result (N lines) — this section may be a label only. Next section: NAME (line L)`. Turns a dead end into a navigable suggestion. (BACK-191e, M4)
- **V024: Adapter guide coverage rule** — `reveal reveal:// --check` now flags any registered public adapter missing a guide file in `docs/adapters/`. Prefix-matched (NGINX_GUIDE.md satisfies nginx://). Exempts help://, demo, test. 7 tests. (BACK-191)
- **`AUTOSSL_ADAPTER_GUIDE.md`** — static guide for `autossl://` adapter. Covers defect codes (SELF_SIGNED_CERT, CERT_HAS_EXPIRED, etc.), DCV impediment codes (TOTAL_DCV_FAILURE, DNS_RESOLVES_TO_ANOTHER_SERVER, etc.), shared-host `--user` workflow, domain history, JSON output, combos with `ssl://`/`nginx://`/`cpanel://`/`letsencrypt://`. `reveal reveal:// --check` now fully clean (0 V024 violations). (BACK-192)

### Maintenance
- **I002 circular dependency ceiling documented** — `reveal check reveal/ --select I002 --format json` baseline is **23 violations**. Added to `RELEASING.md` pre-flight checklist. CI gate was evaluated and removed (12.5 min runtime). (BACK-183)
- **`utils/query.py` (762 lines) split into 3 focused modules** — `query_parser.py` (coerce/parse/QueryFilter), `query_eval.py` (compare_values/apply_filter), `query_control.py` (ResultControl/sort/budget). `query.py` is now a re-export shim; all 24 import sites unchanged. (BACK-184)
- **`treesitter.py` complexity metrics extracted** — `_calculate_complexity_and_depth` (79 lines, pure node function) moved to `reveal/complexity.py` as a standalone function. `_calculate_complexity` and `_get_nesting_depth` on `TreeSitterAnalyzer` become thin wrappers. (BACK-187)
- **`adapters/ast/nav.py` (1068 lines) split into 4 modules** — `nav_outline.py` (element_outline, scope_chain), `nav_varflow.py` (var_flow, _walk_var), `nav_calls.py` (range_calls), `nav_exits.py` (collect_exits, collect_deps, collect_mutations). `nav.py` is now a re-export shim. Cross-module deps explicit: nav_exits imports from nav_calls and nav_varflow. (BACK-185)

### Docs
- **RECIPES.md major expansion** — added "Start Here: Distinctive Capabilities" orientation section, "Large-Function Navigation" (all nav flags: `--outline`, `--around`, `--scope`, `--ifmap`, `--catchmap`, `--exits`, `--flowto`, `--varflow`, `--deps`, `--mutations`), "Spreadsheet & BI Inspection" (xlsx/PowerPivot/PowerQuery), "Inspect Claude Install State" (`claude://info/config/history/plans/memory/agents/hooks`), and "Cross-adapter orientation". All examples validated at runtime.

---

## [0.79.0] - 2026-04-14 (sessions orbital-shuttle-0414, ivory-dawn-0414)

### Breaking Changes
- **`--domain` renamed to `--server-name` for nginx** — `--domain` previously meant two unrelated things: filter markdown/HTML links by domain, and filter nginx server blocks by `server_name`. These are now separate flags. `--domain` unchanged for link filtering; `--server-name DOMAIN` is the new flag for nginx file analysis. (BACK-173)
- **`--quiet` alias removed from `--no-breadcrumbs`** — `--quiet` implied global quiet mode but only suppressed breadcrumbs; removed to avoid confusion. `-q` shorthand retained. (BACK-178)
- **`demo://` removed from public adapter registry** — scaffolding template only; was never intended as a user-facing adapter. `demo://` no longer appears in `--adapters`. File remains as a developer reference. (BACK-177)

### Added
- **URI query param support for `ssl://`, `cpanel://`, `letsencrypt://`, `autossl://`** — adapter-specific options now travel with the URI. `ssl://host?expiring-within=30`, `cpanel://USER/ssl?dns-verified`, `letsencrypt://?check-orphans`, `autossl://latest?only-failures` all work. Enables per-URI option control in batch/pipeline workflows. CLI flags still work. (BACK-164, BACK-165, BACK-170, BACK-175)
- **`help://ux` guide** — new static guide covering the CLI-vs-URI mental model: when to use file paths vs URIs, CLI flags vs query params, the `--search` = `?name~=` rename, `--head`/`--tail` vs `?limit=`/`?offset=` semantic difference, and the progressive escalation pattern. Accessible as `reveal help://ux`. (turbulent-wind-0413)
- **`cli_only_flags` in `--discover` schema** — `mysql://`, `domain://`, and `sqlite://` schemas now expose adapter-specific CLI flags (check-mode flags that can't be URI query params) to AI agents via `--discover`. (BACK-175)

### Fixed
- **`--sort` + `?sort=` duplicate injection** — URI-explicit sort takes precedence; CLI `--sort` only injects when URI has no sort param. (BACK-167)
- **`domain://` and `nginx://` URI query string stripping** — bare query params on adapters that don't support them no longer cause confusing DNS errors; both adapters strip `?...` and warn to stderr. (BACK-171)
- **cpanel `get_schema()` key rename** — `uri_query_params` → `query_params` for consistency with all other adapters. (BACK-167)
- **`--help` group label taxonomy** — all 12 argument groups now show scope tier (`[global — ...]`, `[file-specific — ...]`, `[adapter-specific — ...]`, `[universal — ...]`). Previously 6 of 12 groups had no scope hint.
- **`autossl` and `letsencrypt` `get_help()` migrated to YAML** — consistent with mysql/ssl/sqlite; includes `query_params` section and URI param examples. `reveal help://autossl` and `reveal help://letsencrypt` now show current examples.
- Various doc and schema fixes: `QUERY_PARAMETER_REFERENCE.md`, `LETSENCRYPT_ADAPTER_GUIDE.md`, `AGENT_HELP.md`, `INDEX.md`, `SCAFFOLDING_GUIDE.md`, `ADAPTER_CONSISTENCY.md`.

### Tests (+33 since v0.78.0)
- 8 new tests: `TestAutosslQueryParams`
- 10 new tests: letsencrypt/cpanel/domain URI param coverage (v0.78.3)
- 3 new tests: `--sort` dedup regression (v0.78.2)
- 12 new tests: `TestAutosslGetHelp` + `TestLetsEncryptGetHelp` YAML structure pins

---

## [0.78.7] - 2026-04-14 (session orbital-shuttle-0414)

### Fixed
- **`mysql://`, `domain://`, `sqlite://` schemas now expose adapter-specific CLI flags to `--discover`** — These adapters have check-mode flags (`--check`, `--advanced`, `--only-failures`) that can't be URI query params because they switch routing mode, not filter results. Added `cli_only_flags` dict (flag → description) to each schema; wired into `_get_schema_v1()` so `--discover` surfaces them for AI agents. (BACK-175 completion — the letsencrypt half shipped in v0.78.3; this closes the mysql/domain/sqlite half)
- **`AGENT_HELP.md` version header updated to 0.78.6** — was still showing 0.78.0.
- **`AGENT_HELP.md` `--quiet` reference removed** — comment on `-q` example still said `/ --quiet`; alias was removed in v0.78.6 (BACK-178).
- **`INDEX.md` `demo://` entry corrected** — said "example/testing adapter"; now clarifies it's an unregistered scaffolding template since BACK-177 (v0.78.6).
- **`SCAFFOLDING_GUIDE.md` demo example updated** — `reveal demo://` example replaced with `myapp://`; added note that `demo://` ships unregistered.
- **`QUERY_PARAMETER_REFERENCE.md` corrected for autossl:// and letsencrypt://** — both were listed as "none" in the quick-reference table and in the "Adapters Without Query Parameters" section, despite having query param support since v0.78.3/v0.78.4. Table updated; both added to "Already migrated" table. nginx:// note updated to mention param stripping.
- **`LETSENCRYPT_ADAPTER_GUIDE.md` updated with query param forms** — Quick Start and Flags Reference now show URI query param equivalents (`?check-orphans`, `?check-duplicates`) alongside CLI flags.
- **`autossl` and `letsencrypt` `get_help()` migrated from inline dicts to YAML** — both adapters now load from `help_data/autossl.yaml` and `help_data/letsencrypt.yaml`, consistent with mysql/ssl/sqlite. YAML files include URI query param forms in examples and a `query_params` section. `reveal help://autossl` and `reveal help://letsencrypt` now show up-to-date examples.

### Tests (12 new)
- `TestAutosslGetHelp::test_get_help_returns_dict` — YAML loads as dict
- `TestAutosslGetHelp::test_get_help_required_fields` — name/description/syntax/examples present
- `TestAutosslGetHelp::test_get_help_has_query_params_section` — only-failures/summary/user documented
- `TestAutosslGetHelp::test_get_help_examples_include_uri_param_forms` — ?only-failures/?summary/?user= in examples
- `TestAutosslGetHelp::test_get_help_examples_include_cli_flag_forms` — CLI forms still present
- `TestAutosslGetHelp::test_get_help_documents_tls_status_values` — ok/incomplete/defective documented
- `TestLetsEncryptGetHelp::test_get_help_returns_dict` — YAML loads as dict
- `TestLetsEncryptGetHelp::test_get_help_required_fields` — name/description/syntax/examples present
- `TestLetsEncryptGetHelp::test_get_help_has_query_params_section` — check-orphans/check-duplicates documented
- `TestLetsEncryptGetHelp::test_get_help_examples_include_uri_param_forms` — ?check-orphans/?check-duplicates in examples
- `TestLetsEncryptGetHelp::test_get_help_examples_include_cli_flag_forms` — CLI forms still present
- `TestLetsEncryptGetHelp::test_get_help_has_flags_section` — flags section present

### Files Changed
- `reveal/adapters/mysql/adapter.py` — added `cli_only_flags` to schema
- `reveal/adapters/domain/adapter.py` — added `cli_only_flags` to schema
- `reveal/adapters/sqlite/adapter.py` — added `cli_only_flags` to schema
- `reveal/cli/handlers/introspection.py` — `_get_schema_v1()` now includes `cli_only_flags`
- `reveal/docs/AGENT_HELP.md` — version header 0.78.0 → 0.78.7; removed `/ --quiet` from `-q` comment
- `reveal/docs/INDEX.md` — demo:// entry updated
- `reveal/docs/development/SCAFFOLDING_GUIDE.md` — demo example replaced; note added
- `reveal/docs/guides/QUERY_PARAMETER_REFERENCE.md` — autossl/letsencrypt rows corrected; section restructured
- `reveal/docs/adapters/LETSENCRYPT_ADAPTER_GUIDE.md` — query param forms added to Quick Start and Flags Reference
- `reveal/adapters/autossl/adapter.py` — `get_help()` migrated to `load_help_data('autossl')`
- `reveal/adapters/letsencrypt/adapter.py` — `get_help()` migrated to `load_help_data('letsencrypt')`; `load_help_data` import added
- `reveal/adapters/help_data/autossl.yaml` — new; comprehensive help with query_params section and URI param examples
- `reveal/adapters/help_data/letsencrypt.yaml` — new; comprehensive help with query_params section and URI param examples
- `tests/test_autossl_adapter.py` — `TestAutosslGetHelp` class (6 tests)
- `tests/test_letsencrypt_adapter.py` — `TestLetsEncryptGetHelp` class (6 tests)
- `internal-docs/planning/UX_CONSISTENCY_PLAN.md` — Priority 9/10/11 headings marked ✅ DONE; Priority 11 description updated to reflect two-track implementation

---

## [0.78.6] - 2026-04-14 (session cusiki-0414)

### Fixed
- **`demo://` removed from public adapter registry** — The demo adapter is a scaffolding template for developers and was never intended to be a user-facing adapter. Removed import from `adapters/__init__.py`; file stays as a reference template but `demo://` no longer appears in `--adapters`. (BACK-177)
- **`--quiet` alias removed from `--no-breadcrumbs`** — `--quiet` implied global quiet mode but only suppressed breadcrumbs. Removed the `--quiet` alias; `-q` shorthand retained. (BACK-178)
- **`--base-path` inline Windows note removed** — Stripped `Windows: do not wrap in quotes (...)` from the `--base-path` help text. Cross-platform flag; OS-specific guidance belongs in docs. (BACK-179)
- **`--summary` guard example no longer suggests URI param form** — `cli/routing/file.py` error message for `--summary`-on-plain-path now shows only CLI flag examples, not `?summary` URI param form. (pre-existing BACK-162 test gap)

### Files Changed
- `reveal/adapters/__init__.py` — removed `from .demo import DemoAdapter` and `'DemoAdapter'` from `__all__`
- `reveal/cli/parser.py` — removed `'--quiet'` from `--no-breadcrumbs` aliases; trimmed Windows note from `--base-path` help
- `reveal/cli/routing/file.py` — `summary` guard example: removed `?summary` URI param line

---

## [0.78.5] - 2026-04-14 (session garnet-palette-0414)

### Fixed
- **`--domain` overload resolved: nginx use renamed to `--server-name`** — `--domain` previously meant two unrelated things: filter markdown/HTML links by domain, and filter nginx server blocks by `server_name`. These are now separate flags. `--domain` remains for link filtering (unchanged); `--server-name DOMAIN` is the new flag for nginx file analysis. (BACK-173)

### Files Changed
- `reveal/cli/parser.py` — `--domain` help text cleaned to markdown/HTML-only; new `--server-name` flag added to extraction options group (nginx only)
- `reveal/display/formatting.py` — nginx N3 dispatch reads `args.server_name` instead of `args.domain`
- `reveal/analyzers/nginx.py` — `get_structure` reads `kwargs.get('server_name')` instead of `kwargs.get('domain')`
- `tests/test_nginx_analyzer_pytest.py` — `TestNginxDomainFilter` → `TestNginxServerNameFilter`; all `get_structure(domain=)` calls → `get_structure(server_name=)`; test method names updated
- `reveal/docs/adapters/NGINX_GUIDE.md` — `--domain` → `--server-name` throughout; section heading updated
- `reveal/docs/AGENT_HELP.md` — `--domain` → `--server-name` in nginx examples and quick reference table
- `reveal/docs/guides/RECIPES.md` — `--domain` → `--server-name` in nginx recipes

---

## [0.78.4] - 2026-04-14 (session garnet-palette-0414)

### Fixed
- **`autossl://` query param support** — `?only-failures`, `?summary`, and `?user=NAME` now work in URI form (e.g. `reveal 'autossl://latest?only-failures'`), matching the cpanel/ssl/letsencrypt pattern. CLI flags still work. Schema `query_params` updated from `{}` to documented entries. (BACK-170)

### Tests (8 new — `TestAutosslQueryParams`)
- `test_query_params_empty_by_default` — bare `autossl://latest` has empty query_params dict
- `test_only_failures_via_query_param` — `?only-failures` removes ok domains from run output
- `test_summary_via_query_param` — `?summary` strips per-domain detail (no `users` key)
- `test_user_via_query_param` — `?user=alice` filters to single user
- `test_combined_only_failures_and_summary` — both params compose correctly
- `test_query_param_does_not_corrupt_timestamp_parsing` — `autossl://2026-01-01_03-00-00?only-failures` sets timestamp, not domain
- `test_query_param_does_not_corrupt_latest_parsing` — `autossl://latest?summary` sets timestamp='latest'
- `test_schema_documents_query_params` — schema has `only-failures`, `summary`, `user` keys

### Files Changed
- `reveal/adapters/autossl/adapter.py` — added `parse_query_params` import; `__init__` parses query string into `self.query_params`; `_parse_connection_string` strips `?...` before path parsing; `get_structure()` ORs query params with CLI flags; `get_schema()` `query_params` populated; example queries expanded with 3 URI query param examples
- `tests/test_autossl_adapter.py` — 8 new tests in `TestAutosslQueryParams`

---

## [0.78.3] - 2026-04-14 (session warp-onslaught-0413)

### Fixed
- **cpanel `get_schema()` key rename** — `uri_query_params` → `query_params`. Any tooling iterating schemas (AI agents via `--discover`) previously saw cpanel as having no query params. (BACK-167)
- **LetsEncrypt renderer contract fixes** — `render_error(error: str)` → `render_error(error: Exception)` to match the adapter contract; `render_structure(output_format=)` → `render_structure(format=)` to match the calling convention in `uri.py:407`. Both worked by duck typing; now correct by contract. (BACK-168, BACK-169)
- **`letsencrypt://` query param support** — `?check-orphans` and `?check-duplicates` now work in URI form (e.g. `reveal 'letsencrypt://?check-orphans'`), matching the cpanel/ssl pattern. CLI flags still work. Schema `query_params` updated. (BACK-175)
- **`domain://` and `nginx://` URI stripping** — query params on adapters that don't support them (`domain://example.com?foo=bar`) previously tried to resolve `example.com?foo=bar` as a hostname, causing a confusing DNS error. Both adapters now strip `?...` from the resource and warn to stderr. (BACK-171)
- **`--section` guard error format** — `file.py` guard for `--section` on non-markdown files now uses the standard format: ❌ emoji + examples + "Learn more: reveal help://ux" hint. Previously used a bare `Error:` with no examples. (BACK-172)
- **`domain.yaml` TODO comments** — `"WHOIS data ... - TODO: requires python-whois"` replaced with `"... — not yet available (requires python-whois)"` in examples and elements dict. Raw TODO was visible to users via `reveal help://domain`. (BACK-174)
- **`xlsx.yaml` NOT YET IMPLEMENTED noise** — removed `(NOT YET IMPLEMENTED)` suffix from `search` and `formulas` entries in `query_parameters` section. These entries remain in `future_features`. (BACK-176)
- **`domain.yaml` `query_params:` section added** — aligns with all other help YAML files. (BACK-180)

### Tests (10 new)
- `TestCpanelSchema::test_schema_uses_query_params_key_not_uri_query_params` — BACK-167 schema key contract
- `TestCpanelSchema::test_schema_query_params_includes_expected_params` — domain_type/dns-verified/check-live present
- `TestLetsEncryptRenderer::test_render_error_accepts_exception` — BACK-168 signature contract
- `TestLetsEncryptRenderer::test_render_structure_format_kwarg` — BACK-169 parameter name contract
- `TestLetsEncryptRenderer::test_renders_json` — updated to use `format=` keyword (was `output_format=`)
- `TestLetsEncryptQueryParams::test_check_orphans_via_query_param` — BACK-175 URI param parsed
- `TestLetsEncryptQueryParams::test_check_duplicates_via_query_param` — BACK-175 URI param parsed
- `TestLetsEncryptQueryParams::test_no_query_params_by_default` — bare letsencrypt:// has empty query_params
- `TestLetsEncryptQueryParams::test_schema_documents_query_params` — BACK-175 schema documents both params

### Files Changed
- `reveal/adapters/cpanel/adapter.py` — `uri_query_params` → `query_params` in `get_schema()`
- `reveal/adapters/letsencrypt/renderer.py` — `render_error(str)` → `render_error(Exception)`; `output_format` → `format` in `render_structure`
- `reveal/adapters/letsencrypt/adapter.py` — added `parse_query_params` import + `self.query_params` init; `get_structure()` ORs query params with CLI flags; schema `query_params` populated
- `reveal/adapters/domain/adapter.py` — `_parse_connection_string` strips `?...` with stderr warning
- `reveal/adapters/nginx/adapter.py` — `_parse_connection_string` strips `?...` with stderr warning
- `reveal/cli/routing/file.py` — `--section` guard upgraded to standard format
- `reveal/adapters/help_data/domain.yaml` — TODO → "not yet available"; `query_params: {}` section added
- `reveal/adapters/help_data/xlsx.yaml` — `(NOT YET IMPLEMENTED)` suffix removed from query_parameters
- `tests/test_cpanel_adapter.py` — 2 new schema key tests
- `tests/test_letsencrypt_adapter.py` — existing json test fixed; 8 new tests in 2 classes

---

## [0.78.2] - 2026-04-13 (session turbulent-wind-0413)

### Added
- **`help://ux` guide** — new static guide covering the CLI-vs-URI mental model: when to use file paths vs URIs, CLI flags vs query params, the `--search` = `?name~=` rename, `--head`/`--tail` vs `?limit=`/`?offset=` semantic difference, and the progressive escalation pattern. Accessible as `reveal help://ux`. Added to "Best Practices" category in `reveal help://` index.

### Fixed
- **`ADAPTER_CONSISTENCY.md` "Current state vs target"** — `--dns-verified`, `--check-live`, `--expiring-within`, `--summary` all show ✅ (both CLI and URI form work). Previously showed aspirational "target" state. `claude://` remains 🔲 (CLI only).
- **`ADAPTER_CONSISTENCY.md` "Future Enhancements"** — item 1 updated to reflect ssl/cpanel done, only nginx/claude remain.
- **`ADAPTER_CONSISTENCY.md` head/tail note** — clarified that `--head`/`--tail` are output-stream slicing (post-run) while `?limit=`/`?offset=` are query result control (pre-output); they are not interchangeable.
- **`ADAPTER_CONSISTENCY.md` ssl "Adapter-Specific Features"** — URI query param forms added to the ssl example block.
- **`parser.py` ssl option help text** — `--summary` and `--expiring-within` now mention the URI query param equivalent in their `--help` output.

### Tests (3 new)
- `TestHandleUri::test_sort_injection_skipped_when_uri_has_sort` — URI `?sort=` takes precedence over `--sort` flag (regression test for dedup guard in `handle_uri:34`)
- `TestHandleUri::test_sort_injection_applied_when_uri_has_no_sort` — `--sort` injected when URI has no sort param
- `TestHandleUri::test_sort_desc_prefix_applied` — `--sort` + `--desc` produces `sort=-field` in injected URI

### Files Changed
- `reveal/docs/guides/UX_GUIDE.md` — new file (auto-registered as `help://ux`)
- `reveal/adapters/help.py` — `'ux': 'guides/UX_GUIDE.md'` added to `STATIC_HELP`
- `reveal/rendering/adapters/help.py` — `ux` added to `best_practices` category, token estimate, description
- `reveal/cli/parser.py` — `--summary` and `--expiring-within` help text now mentions URI form
- `reveal/docs/development/ADAPTER_CONSISTENCY.md` — 4 targeted updates (current state table, future enhancements, head/tail note, ssl features)
- `tests/test_routing.py` — 3 new tests in `TestHandleUri`

---

## [0.78.1] - 2026-04-13 (session turbo-zephyr-0413 / turbulent-wind-0413)

### Added
- **`ssl://` URI query params: `?expiring-within=N` and `?summary`** — adapter-specific options now travel with the URI. `ssl://host?expiring-within=30` is equivalent to `--expiring-within 30`; `ssl://nginx://...?summary` is equivalent to `--summary`. Enables per-URI option control in batch/pipeline workflows where a global CLI flag applies to all URIs. CLI flags still work (backward compat). (BACK-164)
- **`cpanel://` URI query params: `?dns-verified` and `?check-live`** — same URI-first architecture. `cpanel://USER/ssl?dns-verified` replaces `--dns-verified`; `cpanel://USER/ssl?check-live` replaces `--check-live`. Infrastructure (`parse_query_params` in `_parse_connection_string`) already existed; only the reading of these two params was added. (BACK-165)

### Fixed
- **`--sort` + `?sort=` duplicate injection** — `handle_uri` now skips `--sort` injection if `sort=` already appears in the URI query string. Previously both would be appended producing `?sort=X&sort=Y` with undefined behavior. URI-explicit sort takes precedence; CLI flag only injects when URI has no sort. (BACK-167 / Priority 4 from UX_CONSISTENCY_PLAN)

### Documentation
- `QUERY_PARAMETER_REFERENCE.md` Quick Reference: ssl now shows `expiring-within`, `summary`; cpanel now shows `dns-verified`, `check-live`. (BACK-166)
- `QUERY_PARAMETER_REFERENCE.md` cpanel section: `?dns-verified` and `?check-live` fully documented with examples.
- `QUERY_PARAMETER_REFERENCE.md` "Adapters Without Query Parameters": `ssl://` removed from CLI-flag table; "Already migrated" section added for ssl + cpanel.
- `ssl.yaml` help data: `query_params` block added; flag descriptions note URI equivalents; URI-form examples added.
- `ssl adapter get_schema()`: `query_params` dict populated (was `{}`).
- `cpanel adapter get_schema()`: `uri_query_params` expanded; `uri_syntax` updated.
- `cpanel adapter get_help()`: three URI query param examples added.

### Tests
- 9 new tests: 5 in `TestSSLAdapterInit` (expiring-within and summary query params, both URI and check() routing), 4 in `TestCpanelUriQueryParams` (dns-verified and check-live)

### Files Changed
- `reveal/adapters/ssl/adapter.py` — `parse_query_params` import, `self.query_params` in `__init__`, `?` split in `_parse_connection_string`, `expiring-within` fallback in `check()`, `get_schema()` query_params dict
- `reveal/cli/routing/uri.py` — `_build_render_opts` query_params kwarg, `_handle_check_mode` passes adapter.query_params; `handle_uri` sort dedup guard
- `reveal/adapters/cpanel/adapter.py` — `get_structure()` OR-merge for dns_verified/check_live; `get_schema()` and `get_help()` updated
- `reveal/docs/guides/QUERY_SYNTAX_GUIDE.md` — Step 4 inline comment: `--search` → `?name~=` rename note
- `reveal/docs/guides/QUERY_PARAMETER_REFERENCE.md` — Quick Reference, cpanel section, Adapters Without section
- `reveal/adapters/help_data/ssl.yaml` — query_params block, flag notes, URI examples
- `tests/test_ssl_adapter.py`, `tests/test_cpanel_adapter.py` — 9 new tests

---

## [0.78.0] - 2026-04-13 (session celestial-hydra-0413)

### Added
- **`--around N`: verbatim context centered on a line** — `reveal file.py :123 --around` prints ±20 lines (default) around the target with a `▶` pointer. `--around 10` adjusts the window. Eliminates the mental arithmetic of manually computing a line range. Requires a `:LINE` element; errors with a clear message otherwise.
- **`--ifmap`: branching skeleton for a line range** — `reveal file.php :878-2130 --ifmap` shows only IF/ELIF/ELSE/SWITCH nodes from `--outline`'s output, filtered by keyword. Works on named functions (`reveal file.py myfunc --ifmap`) and flat procedural files. Optionally scoped with `--range`.
- **`--catchmap`: exception skeleton for a line range** — Same as `--ifmap` but filtered to TRY/CATCH/EXCEPT/FINALLY keywords. Equivalent to `probe catchmap`.
- **`--exits`: exit-node list** — `reveal file.php :657-2200 --exits` collects all return/raise/throw/break/continue nodes in a range, plus `die()`/`exit()` language-construct calls (for PHP). Returns kind, line, and first-line text for each.
- **`--flowto`: exit-node list + reachability verdict** — Same output as `--exits` plus a verdict line: `✓ CLEAR` (no exits), `~ CONDITIONAL` (only break/continue), `⚠ BLOCKED` (hard return/raise/exit). Equivalent to `probe flowto`.
- **`--deps`: refactoring pre-flight — variables flowing in** — `reveal file.php :1136-1463 --deps` identifies variables whose first event in the range is a READ (meaning they were set before the range), making them candidates for function parameters on extraction. Shows first-read line and first-write line (or "never written in range").
- **`--mutations`: refactoring pre-flight — variables written and read after** — `reveal file.php :1136-1463 --mutations` identifies variables written in the range that are read after it — candidates for return values on extraction. Together with `--deps`, this is a complete function-extraction pre-flight.
- **Flat-file support for `--varflow` and `--calls`** — Previously these two flags required a named function element and failed with "Error: could not find function…" on flat procedural files (PHP, shell scripts, etc.). Now: (a) any `:LINE-RANGE` element falls back to `root_node` instead of erroring; (b) omitting the element entirely (e.g., `reveal file.php --varflow errormsg`) synthesizes `:1-N` covering the whole file. The `nav.py` functions already accepted any tree-sitter node — the limitation was purely in the CLI dispatch layer (`file_handler.py`).

### Changed
- **`--calls` is now optional-arg** (`nargs='?'`) — `reveal file.php :477-531 --calls` (no range after the flag) uses the element's line range as the scope. `reveal file.py myfunc --calls 89-120` (explicit range) continues to work unchanged.

### Tests (68 new)
- `TestCollectExits` (13) — return/raise/break/continue detection, range filtering, root-node acceptance, die/exit call detection
- `TestRenderExits` (8) — empty, formatted, verdict variants (CLEAR/CONDITIONAL/BLOCKED)
- `TestRenderBranchmap` (4) — empty, formatted, single-line range, depth indentation
- `TestAllVarFlow` (6) — dict return, known vars, event format, range limits, sorted events, root-node acceptance
- `TestCollectDeps` (8) — required fields, sorted order, param detection, non-param exclusion, write info, no-deps case, range limit
- `TestCollectMutations` (7) — required fields, sorted order, result detection, after-write ordering, no-mutations case, range limit
- `TestRenderDeps` (4) — empty, dep without write, dep with write, multiple deps
- `TestRenderMutations` (3) — empty, single, multiple
- `TestIfmapCatchmapFiltering` (4) — keyword exclusion for ifmap/catchmap, depth preservation, render output
- `TestFlatFileFallback` (7) — all six nav functions accept root_node as scope_node
- `TestCollectIdentifierNames` (4) — identifier discovery, range limiting, frozenset type, empty range

### Files Changed
- `reveal/adapters/ast/nav.py` — 8 new functions: `collect_exits`, `_collect_identifier_names`, `all_var_flow`, `collect_deps`, `collect_mutations`, `render_branchmap`, `render_exits`, `render_deps`, `render_mutations`
- `reveal/cli/parser.py` — 7 new flags: `--around`, `--ifmap`, `--catchmap`, `--exits`, `--flowto`, `--deps`, `--mutations`; `--calls` changed to `nargs='?'`
- `reveal/file_handler.py` — `_has_nav_flag()` extended; `_dispatch_nav()` extended with 6 new branches + Change A (root_node fallback); `handle_file()` Change B (flat-file element synthesis)
- `reveal/docs/AGENT_HELP.md` — nav task section fully rewritten; quick-reference table extended; version history updated
- `tests/adapters/test_ast_nav_probe_features.py` — new test file, 68 tests

---

## [0.77.2] - 2026-04-13 (session slate-shine-0413)

### Added
- **Bash/Shell: top-level variable assignments now extracted as structure** — `BashAnalyzer` previously only extracted function definitions, leaving flat worker scripts (no functions, just config vars + a loop) with "No structure available." Now overrides `get_structure()` to walk direct children of the program root for `variable_assignment` nodes. Values truncated at 60 chars. Only captures top-level vars — assignments inside functions, loops, and `if` blocks are excluded to avoid noise. Validated on 14 real-world `.sh` files across workers and bin/ tools. 3 new tests.
- **Small-file fallback: files ≤50 lines with no structure show full content** — Instead of "No structure available for this file type," files under 50 lines are rendered inline with line numbers using `format_with_lines`. Covers entrypoint scripts, minimal deploy scripts, and other tiny files where a `Read` round-trip would be pure overhead.
- **"No structure available" now includes line count** — For files >50 lines with no extractable structure, the message becomes `"No structure available for this file type (N lines)"` so agents can make an informed decision about whether a `Read` is worth it without a separate metadata call.

### Tests
- `test_extract_variables_no_functions` — flat script, vars extracted, inner-loop var excluded
- `test_extract_variables_with_functions` — both vars and functions present
- `test_variable_value_truncation` — 80-char value truncated to 60 with `...`
- `test_empty_structure_large_file_prints_no_structure_message` — line count in message
- `test_empty_structure_small_file_shows_content` — full content rendered, no "No structure" text

6 new tests. Existing `test_empty_structure_prints_no_structure_message` split into the two above.

---

## [0.77.1] - 2026-04-11 (sessions legendary-mountain-0411, hellfire-xenon-0411)

### Fixed
- **`ssl:// --check --probe-http` was silently ignored** — `probe_http` was missing from `_build_check_kwargs` in `cli/routing/uri.py`, so the flag was parsed by argparse but never forwarded to `SSLAdapter.check()`. The redirect check produced no output and no change in exit code. Fixed by adding `add_if_supported('probe_http')` alongside the other check kwargs (`advanced`, `validate_nginx`, `local_certs`, `expiring_within`). Regression test added: `test_routing_passes_probe_http_to_check`. Resolves BUG-155.

### Tests
- **B002/B003/B004 rule tests were entirely wrong** — test classes in `test_bug_rules.py` had inputs for the wrong violations (flake8 equivalents: None comparison, mutable defaults, unused loop vars) instead of the actual rules (`@staticmethod+self`, oversized `@property`, `@property` without return). All three only asserted `isinstance(list)` so they always passed. Replaced with correct detection and allows tests. B001 vacuous `isinstance` check tightened to assert count.
- **Tautological tests removed across 5 files** — deleted 13 `*_exist`/`*_types` tests in `test_defaults.py`, 4 redundant top-level import tests, 3 wrong initialization tests, 1 mock-only test, 1 no-assertion test; `test_env_overrides_count` tightened from `>= 6` to `== 6`; public API used instead of internal `_ADAPTER_REGISTRY` dict.

Net: -97 lines of test code, 7662 passing.

---

## [0.77.0] - 2026-04-11 (session turquoise-ember-0411)

### Added
- **`ssl:// --check --probe-http`: HTTP→HTTPS redirect is now a first-class check item** — Previously `--probe-http` was silently ignored when combined with `--check` (the routing layer exited early for check mode). Now `SSLAdapter.check()` accepts `probe_http=True` and passes it to `check_ssl_health()`, which runs `_check_http_redirect()` and appends it to the checks list. A failing redirect elevates overall exit code to 2. Redirect check reports full chain, hop count, and final URL. `--probe-http` continues to work standalone (structure mode) with its security header display (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) unchanged.
- **`ssl:// --check --advanced`: cipher suite now reported alongside TLS version** — `_check_tls_version()` already opened a live TLS socket but discarded `ssock.cipher()`. Now captures cipher name and bits; message format: `Using TLSv1.3 / TLS_AES_256_GCM_SHA384 (256-bit) (recommended)`. Fields `cipher_name` and `cipher_bits` added to check result for JSON consumers.

### Documentation
- `ssl.yaml`: `--probe-http` added to flags, cli_flags, examples (standalone + combined with `--check`), new "Full TLS + Redirect Audit" workflow, two new anti-patterns, `--advanced` description updated to mention cipher.
- `AGENT_HELP.md`: new "Live TLS + redirect checks" block with example output for both features.
- `SSL_ADAPTER_GUIDE.md`: Advanced Health Checks section updated for cipher, new "HTTP→HTTPS Redirect Check" section, Version 1.3.0 entry.

9 new tests, 7682 passing.

---

## [0.76.3] - 2026-04-11 (session burning-nebula-0411)

### Fixed
- **BACK-145: `nginx://` bare URI now works** — `NginxUriAdapter.__init__` was raising `TypeError` on empty connection string, blocking the `_default_from_uri` dispatch chain before the overview path was reached. Empty string is now normalized to `"nginx://"`. `reveal nginx://` and `reveal nginx:// --audit` work as documented. 1 test updated (`test_empty_is_overview`). Resolves BACK-145.
- **BACK-146: `autossl://` bare URI now works** — Same root cause as BACK-145. `AutosslAdapter.__init__` now normalizes empty string to `"autossl://"` instead of raising `TypeError`. `reveal autossl://` lists available timestamps as documented. 1 test updated (`test_no_arg_is_list_runs`). Resolves BACK-146.
- **BACK-152: `reveal --check` deprecation hint removed** — The runtime `hint:` print to stderr is gone; `--check` still routes to `run_check`. The hint was already removed from help docs (BACK-142, zogipo-0410); now the runtime matches. Resolves BACK-152.
- **BACK-148: `letsencrypt:// --check-duplicates` clean result no longer shows full cert inventory** — When no duplicates are found and `--check-orphans` is not also requested, the full cert table is suppressed and only `✅ No duplicate-SAN certs found.` is printed. Resolves BACK-148.

### Changed
- **BACK-150: `letsencrypt://` inventory sorted by expiry** — Certs now sorted `days_until_expiry` ascending (imminent expirations first). Error certs (no expiry field) sort to the end. Previously alphabetical, which required scanning the full list to find near-expiry certs. Resolves BACK-150.

### Documentation
- **BACK-147: `letsencrypt://` JSON schema documented in `reveal help://letsencrypt`** — Added note listing cert object fields (`name`, `cert_path`, `common_name`, `san`, `days_until_expiry`, `not_after`, `is_expired`, `issuer`). Field is `days_until_expiry` (int), not `days_remaining` (which does not exist). Resolves BACK-147.
- **BACK-149: `--check-orphans` cPanel limitation documented** — Added note to `reveal help://letsencrypt` explaining that on cPanel servers, nginx `ssl_certificate` directives point to `/var/cpanel/ssl/apache_tls/`, not `/etc/letsencrypt/`. All LE certs appear orphaned even when active. Alternative: `reveal cpanel://USER/ssl`. Resolves BACK-149.
- **BACK-154: `--select`/`--ignore` already implemented** — `reveal check <path> --select N004 --ignore N011,E501` already works (added in prior session). Resolves BACK-154.
- **BACK-151: `cert_expiry_days` null for `incomplete` domains is correct** — `cert_expiry_days` is legitimately null when AutoSSL didn't process the cert (e.g., `incomplete` status — cert still valid, no renewal triggered). Field is `cert_expiry_days`, not `days_remaining`. Already documented as `['number', 'null']` in schema. Resolves BACK-151.

7673 tests passing, 0 new tests (all changes are docs/UX/routing).

---


## [0.76.2] - 2026-04-10 (session fiery-goddess-0410)

### Changed
- **`autossl://DOMAIN` row cap** — output capped at 20 most recent rows by default; `--all` flag bypasses cap. 300-row walls for chronic failures were obscuring the pattern. When truncated, shows "… N older runs not shown  (use --all to see full history)".
- **`autossl://DOMAIN` richer summary line** — always shows `✅ 0 ok` even when zero; the zero-ok count is the key signal for chronic failures. Other buckets shown only when non-zero. Also now counts `dcv_failed` entries (tls_status=None + impediments) in the summary dict.
- **`autossl://DOMAIN` failing-since line** — when ok==0, prints "Failing since: YYYY-MM-DD (oldest available run)" at top of output, derived from the true history floor pre-truncation. Previously required scrolling to the bottom of 300 rows.

6 new tests, 73 autossl tests total, 7,673 total passing.

---

## [0.76.1] - 2026-04-10 (session passing-breeze-0410)

### Fixed
- **`autossl://DOMAIN` renderer crash on `None` tls_status** — `_render_domain_history` now uses the same `tls_status or dcv_failed/unknown` fallback as `_render_domain_table`. Triggered on real gateway data where dcv_failed domains have `tls_status: None`. 1 new test.

---

## [0.76.0] - 2026-04-10 (session passing-breeze-0410)

### Added
- **BACK-144: `autossl://DOMAIN` domain history drill-down** — new URI mode that searches all AutoSSL runs for a specific domain and returns its full TLS history across runs. Answers "is this domain always failing or just this run?" `_parse_connection_string` detects dots to distinguish domain names from timestamps. New `_domain_history_structure` method, `autossl_domain_history` output type, `_render_domain_history` table renderer (run | user | status | expiry | detail). `get_schema` and `get_help` updated with new URI syntax, output type schema, and examples. 13 new tests in `TestAutosslDomainHistory`. 7,666 passing.

---

## [0.75.2] - 2026-04-10

### INF Investigation Feedback — Bug Fixes + UX (zogipo-0410)

#### Fixed
- **BACK-138: `letsencrypt://` bare URI now accepted** — `LetsEncryptAdapter.__init__` no longer raises `TypeError` on empty connection string. Matches `letsencrypt://` examples in all help docs and schema. 1 updated test (`test_empty_string_is_accepted`).
- **BACK-139: `autossl://` JSON `detail` field populated** — `_build_user_list` in `parser.py` now synthesizes `detail` from `defect_codes` + `impediments` (e.g. `"CERT_HAS_EXPIRED, DCV:TOTAL_DCV_FAILURE"`). Previously empty in JSON; text renderer built it on-the-fly. 4 new tests in `TestParseRunDetailField`.
- **BACK-136: `--cpanel-certs` alias noise eliminated** — `_handle_cpanel_certs` now uses `canonical_only=True` by default, skipping www/mail/alias server_name variants that never have individual disk certs. `--all` flag restores full alias output. `--only-failures` suppresses `missing` rows (no disk cert = not a failure). 3 new tests in `TestCpanelCerts`.

#### Documented / Exposed
- **BACK-140/141: `autossl://` `--user` and `--only-failures` surfaced** — both were already implemented in `get_structure`/`_apply_autossl_filters` but absent from `get_schema` cli_flags and `get_help` examples. Added to both, plus new `get_help` examples: `--user=sociamonials`, `--only-failures`, combined form.
- **BACK-143: `cpanel://USERNAME/full-audit` added to `get_help`** — was in `get_schema` and implemented, missing from `get_help` examples and elements dict. Added.

#### Help / Docs
- **BACK-142: nginx help updated to use `reveal check` form** — `nginx_uri.yaml` notes/workflow steps and nginx adapter next-step strings updated from deprecated `--check` to `reveal check <path>` / `reveal check ssl://domain`.


## [0.75.1] - 2026-04-10

### Doc Hygiene + Pre-Release Tooling (gladiator-overlord-0409)

#### Fixed
- **15 broken links** — wrong subdirectory paths from doc reorg (README, ROADMAP, CHANGELOG, HTML_GUIDE, XLSX_ADAPTER_GUIDE, SCAFFOLDING_GUIDE)
- **13 internal-docs references removed** — CONTRIBUTING, ROADMAP, CALLS_ADAPTER_GUIDE, OUTPUT_CONTRACT, DUPLICATE_DETECTION_GUIDE
- **10 TIA/personal leaks anonymized** — company names, CLI commands, hardcoded paths in ROADMAP, AGENT_HELP, CLAUDE_ADAPTER_GUIDE, NGINX_GUIDE
- **INDEX.md stale adapter count** — updated from "17 guides + 1 roadmap" to "22 files"

#### Added
- **`scripts/check_doc_hygiene.py`** — pre-release checker: broken links (via `reveal --links`), internal-docs references, TIA/personal leak patterns. Cross-file anchor validation to avoid false positives. Exits non-zero on issues.
- **Pre-release step 6/9** — `check_doc_hygiene.py` wired into `pre-release-check.sh`

## [0.75.0] - 2026-04-09

### cPanel Domain Types + SSL Mismatch UX + Security Fix (heroic-minotaur-0409, pavako-0409)

#### Added
- **BACK-128: Authoritative domain type detection** — `_parse_main_domain_types()` reads cPanel `main` file (`/var/cpanel/userdata/USER/main`) for `main_domain`, `addon_domains`, `sub_domains`, `parked_domains` lists. Parked domains now correctly detected instead of being invisible. Falls back to filename heuristic when main file absent. 12 new tests.
- **BACK-133: Cert store path + wildcard hint on hostname mismatch** — `_check_hostname_match` results now include `cert_store_path` (`/var/cpanel/ssl/apache_tls/DOMAIN/`), `wildcard_candidate` (`*.parent.tld`), and `wildcard_note` (explains coverage). Renderer shows hints inline. 6 new tests.

#### Fixed
- **RFC 6125 wildcard SAN matching** — `_hostname_matches_san` used `host.endswith(san[1:])` which let `*.example.com` incorrectly match `deep.sub.example.com`. Fixed to enforce single-level matching per RFC 6125 §6.4.3. 7 new tests.
- **BACK-129: Backtick heading match** — `_find_heading_match()` now matches headings containing inline code (backticks).
- **BACK-130: Code fence section truncation** — `_section_end()` tracks fence state; `#` inside code blocks no longer treated as headings.
- **BACK-131: `--domain` not-found message** — clear error when domain filter matches nothing.
- **BACK-132: `cpanel://help/api` reference** — help topic now documented and accessible.

#### Refactored
- Extracted `_find_heading_match()` from `extract_element()` (102→86 lines). Moved inline `import sys` to module top.

#### Tests
- 61 new tests across 4 commits (540 tests in cpanel/ssl/markdown test files; 7480 full suite).

## [0.74.0] - 2026-04-07

### Test Coverage + Doc Quality (revealed-sphinx-0407)
- **BACK-127 test coverage** (`tests/test_claude_adapter_gaps.py`, `tests/test_claude_renderer.py`): 22 new tests covering `get_message_range()` (type, metadata filtering, 1-indexed turns, raw message_index, total count, empty input), `_post_process_message_range` (no-slice, range slice, open-ended range, filtered_from, None guard), and `_render_claude_message_range` (header with/without range, open-ended header, user/assistant text, tool-only turns, truncation, `?full`/`--verbose` equivalence, filtered_from, tool_result count).
- **CLAUDE_ADAPTER_GUIDE.md doc fixes**: duplicate element numbering corrected (`agents` was mislabeled §11, now §12); new `### 13. chain` element added to Elements Reference documenting `/chain` route (syntax, example, output fields, notes on cycle detection and README frontmatter traversal, `--base-path` hint); header updated from "eleven" to "thirteen elements".

### claude:// UX Fixes (hologram-solar-0407)
- **N1 — Word-boundary search** (`?word`): cross-session `?search=ICT` no longer returns 2706 false positives from "picture", "critical", etc. Add `?word` to any `claude://sessions/?search=` query for `\bTERM\b` semantics. Phase 1 grep stays substring (speed); word-boundary filter applied in phase 2. (`analysis/search.py`, `analysis/messages.py`)
- **N2 — `?full` on `/assistant`**: `reveal claude://session/NAME/assistant?full` disables the 600-char per-message truncation. (`adapter.py`, `renderer.py`)
- **N3 — Tool-only turn display**: `/assistant` no longer shows dead-end `(tool calls only, no text)`. Tool-only turns now render one-line summaries: `Agent → research strategies`, `Write → STRATEGIES.md`. (`renderer.py`)
- **N4 — `message/N` tool_use params**: `message/N` now shows key input params for common tools — `file_path` + content size for Write, `file_path` + old→new char counts for Edit, `command` for Bash, `prompt` for Agent, `pattern` for Glob/Grep. (`renderer.py`)
- **N5 — `tool_result` content visible**: `message/N` now renders `tool_result` blocks (content preview, 500 chars). Per-session `?search=` now searches inside tool_result content. (`renderer.py`, `analysis/messages.py`)
- All 477 claude adapter tests pass; full suite 7,325 passed.

### BACK-127 + full/verbose UX consistency (intergalactic-moon-0407)
- **`/message --range` route**: `reveal claude://session/NAME/message --range 10-20` returns interleaved user+assistant turns. Open-ended `--range 300-` also supported. (`adapter.py`, `analysis/messages.py`, `renderer.py`)
- **`?full` and `--verbose` now equivalent** across `/assistant`, `/messages`, and `/message`: previously `/assistant` only respected `?full` and `/messages` only respected `--verbose`. Both flags now check both mechanisms. (`renderer.py`)
- **Parser: open-ended `--range N-`**: `--range 300-` stores `(300, None)`; `_slice_list` naturally handles it via `items[n-1:None]`. (`cli/parser.py`)
- **`test_check_flag` updated**: test was using `handle_file` + `args.check=True` (removed in ethereal-witch-0407 refactor); updated to call `run_check` directly. (`tests/test_routing.py`)
- **`CLAUDE_ADAPTER_GUIDE.md` updated**: §11 documents `/message --range` syntax, examples, range indexing rules, `?full`/`--verbose` equivalence note.

### Documentation (oceanic-sea-0407)
- **9 critical doc errors fixed**: CI_RECIPES exit codes unswapped, SSL pipeline double-prefix removed, NGINX N008–N012 descriptions added, SQLITE "planned feature" label stripped, OUTPUT_CONTRACT ghost commands removed, HELP_SYSTEM_GUIDE decorator API fixed, ANALYZER_PATTERNS import fixed (2 locations), AGENT_HELP token cost corrected (~12K→~26.5K)
- **Batch count/version sweep**: adapter count 22→23, language count "190+"→"80", N rules 7→12 in AGENT_HELP, line counts updated across INDEX/README, deprecated `--check` flag replaced with `reveal check` subcommand in RECIPES/CONFIGURATION_GUIDE, phase/session footers stripped from 3 guides
- **New doc**: `DEPENDS_ADAPTER_GUIDE.md` — first complete guide for `depends://` (Quick Start, URI syntax, 5 workflows, limitations, FAQ, Graphviz output)
- **Archived**: `CODEBASE_REVIEW.md` and `XLSX_POWERBI_EXPANSION.md` moved to `internal-docs/archived/guides/`; unique sections from CODEBASE_REVIEW extracted into RECIPES.md (multi-adapter patterns, token strategies, real-world scenarios)
- `depends://` registered in `help.py` STATIC_HELP
- Commit: `aa4e6f7` — 28 files, +707/-2075 lines; all 7,325 tests pass

### Schema Fixes (fubunu-0407)
- **7 adapter schema gaps closed** (Tier 3 from DOC_REVIEW_2026-04-06): `get_schema()` now matches implemented behavior for agents consuming machine-readable schemas
  - `claude://`: added `?tokens` param (token usage breakdown)
  - `xlsx://`: added `powerquery`, `names`, `connections` params
  - `ssl://`: added `--summary` to `_SCHEMA_CLI_FLAGS`
  - `mysql://`: added 5 missing elements (`errors`, `databases`, `indexes`, `slow-queries`, `health`)
  - `letsencrypt://`: added `common_name`, `issuer` fields to cert items in output type schema
  - `stats://`: added `check_issues` field to `stats_file` quality output schema
  - `json://`: added `sort`, `limit`, `offset` result control params (already documented in notes)
  - `markdown://`: `aggregate=field` confirmed present (pre-existing, DOC_REVIEW false positive)
- **QUERY_PARAMETER_REFERENCE.md expanded**: added `depends://`, `xlsx://`, `cpanel://` sections with full param docs; expanded `claude://` from 3 to 9 params; added `autossl://`, `letsencrypt://`, `nginx://` to no-params section; updated Quick Reference table from 14 to 21 adapters

### Check Exit Code Fix (ethereal-witch-0407)
- **`reveal check file.py` now exits 1 on violations** (`reveal/cli/commands/check.py`, `reveal/checks.py`): Single-file mode was silently bridging through `handle_file` → `_dispatch_special_flags` and ignoring the violation count. Fixed by routing single files directly through `run_pattern_detection` in `run_check`, matching directory-mode behavior. `run_pattern_detection` now returns `len(detections)`.
- **`--stdin --check` and `@file --check` now exit 1 on violations** (`reveal/cli/handlers/batch.py`): `handle_stdin_mode` accumulated no violation count from file paths — `_process_stdin_file` returned `None` and the function always ended with `sys.exit(0)`. Fixed: `_process_stdin_file` takes `is_check_mode` param, calls `run_pattern_detection` directly when set, returns violation count; `handle_stdin_mode` accumulates total and exits `1 if total_violations else 0`. Enables `git diff --name-only | reveal --stdin --check` as a CI gate.
- **Dead code removed**: `args.check` branch in `_dispatch_special_flags` (`file_handler.py`) — unreachable from all normal paths after above fixes. Removed.
- **Docs updated**: `SUBCOMMANDS_GUIDE.md` exit code table corrected (removed single-file always-exits-0 caveat); `CI_RECIPES.md` added "Changed-Files Quality Gate" recipe using `git diff --name-only | reveal --stdin --check`.
- **9 new tests**: `test_check_subcommand_exits_1_with_violations`, `test_check_subcommand_exits_0_no_violations`, `test_stdin_check_exits_1_with_violations`, `test_stdin_check_exits_0_no_violations`, `test_at_file_check_exits_1_with_violations`, `test_at_file_check_exits_0_no_violations` (+ 3 prior from toxic-force). Exit code 1 now consistent across all `reveal check` invocation forms.
- **Note**: The toxic-force-0407 CHANGELOG entry for `SUBCOMMANDS_GUIDE.md` ("exit code 1 is directory-mode only; single-file always exits 0") documented the behavior accurately at the time — it was a documentation-of-a-bug pass. This entry is the code fix.

### Documentation + Code (toxic-force-0407)
- **Doc audit Tier 2 complete**: all remaining 10 open items from DOC_REVIEW_2026-04-06 resolved
  - `AST_ADAPTER_GUIDE.md`: version heading v1.0→v1.1; stale "McCabe coming soon" limitation removed (tree-sitter implementation shipped)
  - `STATS_ADAPTER_GUIDE.md`: example quality score calculation now includes Penalty 5 (check_issues row)
  - `MARKDOWN_GUIDE.md`: removed `broken` from `--link-type` valid values (never a valid type)
  - `REVEAL_ADAPTER_GUIDE.md`: `reveal.py (310 lines)` → package reference; V001–V006 → V001–V023+
  - `IMPORTS_ADAPTER_GUIDE.md`: removed hardcoded `"version": "0.30.0"` from all doc examples
  - `SUBCOMMANDS_GUIDE.md`: exit code section now correctly states that code 1 is directory-mode only; single-file always exits 0
  - `ADAPTER_AUTHORING_GUIDE.md`, `ENV_ADAPTER_GUIDE.md`, `PYTHON_ADAPTER_GUIDE.md`, `ELIXIR_ANALYZER_GUIDE.md`: confirmed already correct (pre-existing fixes or false positives)
- **Code bug fix**: `reveals/adapters/imports.py` — removed hardcoded `'version': '0.30.0'` from metadata dict (was emitting stale release version in structured output)

## [0.73.0] - 2026-04-06 (liquid-carnage-0406)

### Added
- **`depends://` adapter — inverse module dependency graph** (`reveal/adapters/depends.py`): New 23rd adapter answering "what imports this module?" by inverting the same graph built by `imports://`. `depends://file.py` lists all files that import it with file/line/names/type. `depends://dir/` produces a ranked summary of most-imported modules in that directory. `?top=N` limits results. `?format=dot` emits GraphViz DOT for visualization. Scans from project root (via `find_project_root`) so cross-directory importers are visible. Reuses `ImportGraph.reverse_deps` which is already computed as a side effect of forward graph construction — no additional graph-walk cost. Added task section to AGENT_HELP.md and recipe to RECIPES.md.

### Fixed
- **`stats://` quality score now reflects check rule detections** (`reveal/adapters/stats/metrics.py`, `reveal/adapters/stats/queries.py`): Previously `calculate_quality_score` used only code metrics (complexity, function length, nesting), so a file with 30+ check issues would still score 100/100. Now `_count_check_issues` runs `RuleRegistry.check_file` with the already-computed `structure` and `content` (no re-parsing), counts detections by severity, and passes them to `calculate_quality_score` as `check_issue_counts`. Penalty formula: CRITICAL=10 pts, HIGH=5 pts, MEDIUM=2 pts, LOW=0.5 pts, capped at 40 total. The PHP probe file (30 issues) now scores 79 instead of 100.
- **`quality.check_issues` exposed in per-file stats output**: `calculate_file_stats` now includes `check_issues: int` in the `quality` dict, making the issue count visible in `stats://` output alongside the score.
- **`check_penalties` configurable** via `check_issues` section in `.reveal/stats-quality.yaml` or `~/.config/reveal/stats-quality.yaml`.
- **PHP anonymous class detection** (`reveal/treesitter.py`): Added `anonymous_class` to `CLASS_NODE_TYPES`. PHP 8's `new class extends Foo { ... }` syntax was invisible to `_extract_classes` — `stats://` reported `Classes: 0`, `--outline` showed methods without parent context, and class extraction by name failed. Now surfaces as `anonymous(Foo)@L{line}` (or `anonymous@L{line}` when no base class). Also added to `PARENT_NODE_TYPES` and `ALL_ELEMENT_NODE_TYPES`.
- **D001 false positives on same-named PHP class methods** (`reveal/treesitter.py`): Consequence of the anonymous class fix. D001's `class_for` lookup now finds the enclosing anonymous class, so identically-named methods in different anonymous classes are correctly scoped and not flagged as duplicates.
- **PHP function call detection** (`reveal/treesitter.py`): Added `function_call_expression` to `CALL_NODE_TYPES`. PHP uses this node type for bare function calls — previously `calls://` returned empty results for all PHP targets.
- **`stats://` complexity always 1.00 for tree-sitter languages** (`reveal/adapters/stats/metrics.py`): `estimate_complexity` was ignoring the pre-computed `func['complexity']` and re-computing from keyword counting using the wrong key (`end_line` instead of `line_end`). Fix: use `func['complexity']` when present. Fallback corrected to use `line_end`.
- **`--outline` empty for closure-heavy functions** (`adapters/ast/nav.py`): Functions whose body consists entirely of inner closures now emit a `DEF`/`CLASS` item and recurse into the body.
- **`--scope` excluded enclosing `def`/`class` nodes** (`adapters/ast/nav.py`): Function and class definitions now appear as `DEF`/`CLASS` entries in the scope chain, outermost first.
- **`--scope` marker shows actual source line** (`adapters/ast/nav.py`): `▶ L{N}: <line text>` instead of a bare `is here` marker.

### Tests
- **49 new tests total**: 27 for `depends://` adapter (`tests/test_depends_adapter.py`); 7 for stats quality check penalties (`TestStatsQualityCheckPenalty`); 15 for PHP fixes (`TestPhpAnonymousClasses`, `TestPhpCallDetection`, `TestStatsComplexityFix`). **Test count: 7,299 → 7,348**.

## [0.72.3] - 2026-04-06 (magical-shrine-0406)

### Fixed
- **PHP anonymous class detection** (`reveal/treesitter.py`): Added `anonymous_class` to `CLASS_NODE_TYPES`. PHP 8's `new class extends Foo { ... }` syntax was invisible to `_extract_classes` — `stats://` reported `Classes: 0`, `--outline` showed methods without parent context, and class extraction by name failed. Now surfaces as `anonymous(Foo)@L{line}` (or `anonymous@L{line}` when no base class). Also added `anonymous_class` to `PARENT_NODE_TYPES` and `ALL_ELEMENT_NODE_TYPES` for `Class.method` extraction and line-based navigation.
- **PHP anonymous class naming** (`reveal/treesitter.py`): Added `_get_anonymous_class_name` helper that reads the `base_clause` child to generate descriptive names like `anonymous(NodeVisitorAbstract)@L144`. Modified `_extract_undecorated_classes` to invoke this fallback when `_get_node_name` returns `None` for `anonymous_class` nodes instead of silently skipping them.
- **D001 false positives on same-named PHP class methods** (`reveal/treesitter.py`): Consequence of the anonymous class fix. D001's `class_for` lookup now finds the enclosing anonymous class, so identically-named methods in *different* anonymous classes (e.g., `isScope`, `leaveNode`) are correctly scoped and not flagged as duplicates.
- **PHP function call detection** (`reveal/treesitter.py`): Added `function_call_expression` to `CALL_NODE_TYPES`. PHP uses this node type for bare function calls — previously `_extract_calls_in_function` found 0 PHP calls and `calls://` returned empty results for all PHP targets. The existing `_get_callee_name` fallback correctly resolves PHP `name` nodes, so no further change was needed there.
- **`stats://` complexity always 1.00 for tree-sitter languages** (`reveal/adapters/stats/metrics.py`): `estimate_complexity` was ignoring the pre-computed `func['complexity']` from `_build_function_dict` and re-computing from keyword counting using the wrong key (`end_line` instead of `line_end`), so `start_line == end_line`, yielding a single-line body and complexity = 1. Fix: use `func['complexity']` when present (all tree-sitter languages). Fallback keyword path corrected to use `line_end`.

### Tests
- **15 new tests for PHP fixes** (`tests/test_php_analyzer.py`): `TestPhpAnonymousClasses` (7 tests — anonymous class with/without extends detected, multiple classes, correct line bounds, D001 false-positive suppression, D001 still fires for real dups, named+anonymous coexist); `TestPhpCallDetection` (3 tests — function_call_expression captured, multiple calls, `name` node callee resolved); `TestStatsComplexityFix` (5 tests — pre-computed complexity used, zero complexity returned, fallback uses `line_end`, wrong key gives minimal, PHP complexity non-zero end-to-end). **Test count: 7,299 → 7,314**.

## [0.72.2] - 2026-04-06 (infinite-satellite-0406)

### Fixed
- **`--outline` empty for closure-heavy functions** (`adapters/ast/nav.py`): `_collect_outline` and `_collect_scope_interior` previously skipped `FUNCTION_TYPES` entirely via `continue`, producing a blank outline for functions whose body consists entirely of inner closures (e.g. `_walk_var` in nav.py itself). Fixed by emitting a `DEF`/`CLASS` labeled item at the current depth and recursing into the body at the next depth level — same treatment as any other scope node.
- **`--scope` excluded enclosing `def`/`class` nodes** (`adapters/ast/nav.py`): `_find_ancestors` had `node.type not in FUNCTION_TYPES` in its inclusion guard, so calling `reveal file.py :LINE --scope` on a line inside a closure produced a chain with no enclosing function context. Fixed by removing the exclusion — function and class definitions now appear as `DEF`/`CLASS` entries in the scope chain, outermost first.
- **`--scope` marker shows actual source line** (`adapters/ast/nav.py`, `file_handler.py`): The `▶ L{N} is here` marker now shows the stripped source text of the target line (`▶ L{N}: <line text>`), eliminating the need to cross-reference the file. Falls back to `is here` / `top level` when line text is unavailable.

### Documentation
- **`KEYWORD_LABEL` extended with function/class node types** — `function_definition`, `method_definition`, `class_definition`, and related cross-language variants now map to `DEF` / `CLASS` / `LAMBDA`, enabling readable labels in both `--outline` and `--scope` output.

### Tests
- `test_nested_function_skipped` renamed `test_nested_function_shown_as_def` — assertion inverted: `DEF` must appear in outline keywords.
- `test_closure_only_function_not_empty` added — verifies a function composed entirely of closures produces a non-empty outline with `DEF` entries.
- `test_scope_includes_enclosing_def` and `test_scope_closure_chain` added — verify `DEF` appears in scope chains and that nested closure chains surface both outer and inner `def` nodes before control-flow nodes.
- `test_render_scope_chain_empty_with_line_text` and `test_render_scope_chain_with_line_text` added — verify line text rendering in both empty-chain and chained cases.
- `test_outermost_ancestor_first` updated — outermost ancestor is now `DEF` (enclosing function), not `FOR`.

## [0.72.1] - 2026-04-06 (flux-goliath-0406, nadela-0406, slate-gem-0405)

### Added
- **M501: TODO/FIXME/HACK/XXX comment marker detection** (`reveal/rules/maintainability/M501.py`, BACK-103): New rule in the M5xx reserved range. Scans all file types, emits one LOW-severity detection per marker line. Excludes `reveal/templates/` and `reveal/adapters/demo.py` (intentional scaffolds). Supports `ignore_patterns` config key in `.reveal.yaml` to suppress specific marker lines (e.g. `# TODO: remove in v2.0`). 16 new tests. (session flux-goliath-0406)

### Fixed
- **Adapter count corrected to 22** (README, ARCHITECTURE, AGENT_HELP, QUICK_START, ADAPTER_CONSISTENCY, MCP_SETUP): `demo://` is an internal adapter excluded from production counts; the correct number is 22, not 23.
- **`domain/adapter.py` docstring: stale `TODO:` removed** — `whois` element docstring said `TODO: requires python-whois`; updated to `optional: pip install reveal[whois]`
- **`L001.py` stale TODO comment replaced** — `# TODO: Handle in L003 with framework routing` → factual comment. L003 already handles absolute paths.
- **`--pattern` typo removed from AGENT_HELP.md** — `reveal src/ --pattern --severity high` is wrong (`--pattern` doesn't exist); corrected to `--check --severity high`
- **Removed `--max-bytes` and `--max-depth` budget flags** — `--max-bytes` measured JSON bytes (not tokens) and was unpredictable; `--max-depth` was never implemented. Removed from parser, `apply_budget_limits`, URI routing, MCP server, tests, and all docs. `--max-items` and `--max-snippet-chars` remain.
- **Stale `--max-bytes`/`--max-depth` references scrubbed from docs** — `FIELD_SELECTION_GUIDE.md`, `ADAPTER_CONSISTENCY.md`, `ARCHITECTURE.md`

### Removed
- **`test.py` adapter and `test_test_adapter.py` deleted** — unregistered scaffold, never wired to registry, redundant with `demo.py`. Net -377 lines.

### Documentation
- **AGENT_HELP.md: L/M/F/T rule sections added** — Complete Rules Reference was missing all Link (L001–L005), Maintainability (M101–M105, M501), Frontmatter (F001–F005), and Type (T004) rules — 18 rules undocumented for agents.
- **AGENT_HELP.md: nav flags added to Quick Reference Card** — `--outline`, `--scope`, `--varflow`, `--calls` were missing from the table
- **AGENT_HELP.md: undocumented markdown flags documented** — `--broken-only`, `--inline`, `--section NAME`
- **AGENT_HELP.md: budget flags section added** — `--max-items` and `--max-snippet-chars` with correct behavior notes
- **AGENT_HELP.md: `-q`/`--no-breadcrumbs` noted** for scripting/agent use
- **AGENT_HELP.md/RECIPES.md: nav version tag corrected** from `v0.71.0+` to `v0.72.0+`

## [0.72.0] - 2026-04-05 (bright-mech-0405)

### Changed
- **`_walk_var` decomposed into inner functions** (`nav.py`) — complexity 35 / 113 lines reduced by extracting each node-type handler into a named closure: `_walk_assignment`, `_walk_named_expression`, `_walk_for`, `_walk_with`, `_walk_if_while`. The outer function becomes a readable dispatch; each handler is independently comprehensible. Public signature unchanged.
- **`handle_file` special-flag guards extracted** (`file_handler.py`) — 9 early-exit routing guards (`--extract`, `--check-acl`, `--validate-nginx-acme`, `--global-audit`, `--check-conflicts`, `--cpanel-certs`, `--diagnose`, `--validate-schema`, `--check`) moved into `_dispatch_special_flags(analyzer, path, output_format, args, config) → bool`. `handle_file` is now setup + one dispatch call + element/structure routing.

---

## [0.71.3] - 2026-04-05 (bright-mech-0405)

### Fixed
- **`--outline` behavioral fork documented in help text** (`parser.py`) — `--outline` silently produces completely different output with vs. without an element argument. The help string now explicitly states both modes: file-level hierarchical outline (no element) vs. control-flow skeleton of the named function (with element).

### Tests
- **Integration tests for `handle_file` nav dispatch path** (`test_cli_commands_integration.py`) — 3 new integration tests exercising the full `_has_nav_flag → _dispatch_nav → printed output` chain: `:LINE --scope` success path, `--scope` without element exits-1 error path, and element `--outline` produces control-flow keywords.
- **`_parse_line_range` edge cases** (`test_cli_commands_integration.py`) — 7 new unit tests documenting: valid range, single number, negative number falls back to defaults, `START > END` returned as-is, out-of-bounds returned without clamping, invalid string falls back, empty string falls back.

---

## [0.71.2] - 2026-04-05 (coastal-hurricane-0405)

### Fixed
- **`--varflow`: augmented assignment now emits READ + WRITE** (`nav.py`) — `x += 1` previously only emitted WRITE; it now correctly emits READ (current value consumed) then WRITE (new value stored). Deduplication updated to key on `(line, col, kind)` to allow both events at the same position.
- **Pre-existing bug: `id()`-based `processed` sets in `_walk_var`** — tree-sitter returns new Python wrapper objects on each node access, so `id()` comparisons never matched. All three `processed` sets (`assignment`, `for_statement`, `if_statement`) now use `(start_byte, end_byte)` for correct identity.
- **Depth guard inconsistency in outline** (`nav.py`) — `ALTERNATIVE_NODES` used `depth <= max_depth` (off-by-one: recurses into `depth+1 == max_depth+1`); `SCOPE_NODES` correctly used `depth < max_depth`. Unified to `<` throughout.
- **UX: `--scope`/`--varflow`/`--calls` without element now exit with a clear error** (`file_handler.py`) — previously silently fell through to normal file output with no indication the flag was ignored.

### Removed
- Dead `_condition_text` function (`nav.py`) — never called; `_node_label` already inlines the same truncation logic.
- Dead `_find_func` test helper (`test_ast_nav.py`) — never called (all callers used `_find_func_with_text`); body was also broken.

### Changed
- `SCOPE_NODES` frozenset deduplicated (`nav.py`) — `if_statement`/`for_statement`/`while_statement`/`finally_clause` were listed twice; overlap with `ALTERNATIVE_NODES` documented with an explanatory comment.
- **`_find_element_node` now supports `Class.method` syntax** (`file_handler.py`) — `reveal file.py MyClass.my_method --outline` previously failed silently with "could not find function"; now correctly resolves the method within the class using existing `PARENT_NODE_TYPES` + `_find_child_in_subtree` infrastructure. "Not found" error now includes a `Class.method` hint.

---

## [0.71.0] - 2026-04-05 (warming-tempest-0405)

### Added
- **Sub-function progressive disclosure** (`adapters/ast/nav.py`): four new CLI flags that close the gap between "here's the function signature" and "here are all 200 lines":
  - `--outline` on an element — control-flow skeleton of a function (`DEF → FOR → IF → TRY → EXCEPT/ELSE`) at configurable depth (default 3, `--depth N` to go deeper). Alternative branches (else/elif/except/finally) render at the same visual depth as their parent scope node.
  - `--scope` on a line reference — ancestor scope chain for a specific line (`reveal file.py :123 --scope`), outermost first, with `▶ L123 is here` marker.
  - `--varflow VAR` on an element — all reads and writes of a named variable scoped to a function, classified as `WRITE`, `READ/COND`, or `READ` in document order.
  - `--calls START-END` on an element — all call sites within a line range, with callee name and first argument.
- **CLI flags** (`cli/parser.py`): `--scope`, `--varflow VAR`, `--calls RANGE` added to navigation options group. Existing `--outline` reused (unchanged behavior when no element; new skeleton behavior when element is present).
- **45 new tests** (`tests/adapters/test_ast_nav.py`) covering all four nav functions and renderers.

---

## [0.70.2] - 2026-04-05 (hologram-harbinger-0405)

### Fixed
- **`--section` misclassified headings containing `.` as `Class.method` hierarchical extraction** (`display/element.py`): `_parse_element_syntax` used an unanchored regex `^[A-Za-z_]\w*\.[A-Za-z_]` that matched any text starting with `identifier.letter` — including markdown headings like `"rr.php sentinel locking"`. The trailing ` sentinel locking` was silently ignored, causing the extraction to split on the last dot and look for `php sentinel locking` within `rr`, always returning an error. Fixed by anchoring the regex end (`\w*$`), requiring both sides to be complete bare identifiers with no spaces. `Class.method_name` still works; headings with dots followed by spaces now correctly fall through to name-based heading extraction.

### Tests
- Added `test_heading_with_dot_and_spaces_not_hierarchical` and `test_heading_with_dot_and_dash_words_not_hierarchical` to `tests/test_display_element.py`.

---

## [0.70.1] - 2026-04-03 (sleeping-goddess-0403)

### Fixed
- **`--base-path` with surrounding quotes on Windows** (`cli/parser.py`): On Windows `cmd.exe`, single quotes are not shell metacharacters — they pass through literally, making `--base-path 'C:/Users/...'` resolve to a nonexistent path and `claude://` return 0 sessions. Fixed by adding `_strip_path_quotes()` as the `type=` converter for `--base-path` in argparse, stripping surrounding `'` or `"` at the input boundary. Also updated the help string to warn Windows users not to quote the path. UUID-named sessions returning 0 results was purely downstream of this bug — once the path resolves, UUID sessions list correctly (already handled by `_collect_sessions_from_dir` and `_find_conversation`).

---

## [0.70.0] - 2026-03-31 (expanding-mission-0331)

### Added
- **Full Claude adapter telemetry (Phases A–E)** — major upgrade to `claude://` URI adapter:
  - **`?tokens` route** (`claude://session/NAME?tokens`): token usage summary with input/output/cache breakdown and percentage stats
  - **`toolUseResult` error detection** (`get_workflow()`): Bash steps use `returnCodeInterpretation`; Agent steps use `status == "completed"`; all tools fall back to `is_tool_error()`
  - **`filePath` and `patches` in `/files`**: Edit/Write tool calls now surface the file path and patch content
  - **Glob/Grep call tracking**: `get_all_tools()` and `get_tool_calls()` now count and surface Glob/Grep calls with their patterns
  - **`/agents` sub-route** (`claude://session/NAME/agents`): lists all Agent tool calls with per-agent telemetry — `agent_type`, `status`, `duration_ms`, `token_count`, `tool_count`, `usage` (input/output/cache tokens), plus session-level `total_agent_tokens` and `total_agent_duration_ms`
  - **Agent support in `get_workflow()`, `get_all_tools()`, `get_files()`**: Agent steps gain `agent_type`, `duration_ms`, `token_count`, `tool_count` fields from TUR
  - **`result` block on `?tools=ToolName` calls**: Bash (`stdout`, `stderr`, `return_code_interpretation`), Edit/Write (`file_path`, `user_modified`), Glob (`filenames`, `num_files`, `truncated`)
  - **`caller_type: "direct"` on all tool entries**: consistent across `get_all_tools()` details and `get_tool_calls()` call entries

### Fixed
- **`reveal file.md --search "term"` crash** (`adapters/ast/analysis.py`): `analyze_file()` iterated over `structure.items()` without guarding against non-list values. Markdown's `get_structure()` returns metadata strings alongside the `headings` list — iterating over those strings yielded characters, causing `'str' object has no attribute 'get'`. Fix: skip non-list values and non-dict items. Markdown `--search` now correctly searches heading names.

### Docs
- `CLAUDE_ADAPTER_GUIDE.md`: documented `/agents` as element 11, added `?tokens` to Query Parameters, updated Key Capabilities

---

## [0.69.6] - 2026-03-31 (celestial-chimera-0331)

### Fixed
- **`reveal file.md --search "term"` crash** (`adapters/ast/analysis.py`): `analyze_file()` iterated over `structure.items()` without guarding against non-list values. Markdown's `get_structure()` returns metadata strings (`contract_version`, `type`, `source`, `source_type`) alongside the `headings` list — iterating over those strings yielded characters, causing `'str' object has no attribute 'get'` in `create_element_dict()`. Fix: skip non-list values and non-dict items in the iteration loop. Markdown headings (which carry `name` and `line`) now correctly participate in `--search` queries.

---

## [0.69.5] - 2026-03-31 (celestial-chimera-0331)

### Added
- **`caller_type: "direct"` on `?tools=ToolName` call entries** (`analysis/tools.py`): `get_tool_calls()` call entries now include `caller_type: "direct"`, consistent with `get_all_tools()` details. Completes Phase E.

---

## [0.69.4] - 2026-03-31 (quantum-knight-0331)

### Added
- **`claude://session/NAME/agents`** (`analysis/tools.py`, `adapter.py`): New `get_session_agents()` function and route. Returns `claude_agents` type — lists all `Agent` tool calls with per-agent telemetry: `agent_type`, `status`, `duration_ms`, `token_count`, `tool_count`, `usage` (input/output/cache tokens). Aggregates `total_agent_tokens` and `total_agent_duration_ms`. Prompt truncated to 200 chars. `agent_type` defaults to `"unknown"` when absent from TUR.
- **`caller_type` on tool details** (`analysis/tools.py`): `get_all_tools()` details entries now include `caller_type: "direct"` — all tool_use in a session file are from the main assistant thread.
- **`result` block on `?tools=ToolName` calls** (`analysis/tools.py`): `get_tool_calls()` now attaches a `result` field sourced from `toolUseResult` — Bash: `{stdout, stderr, interrupted, return_code_interpretation, backgrounded}`; Edit/Write: `{file_path, user_modified}`; Glob: `{filenames, num_files, truncated}`. Omitted when TUR absent or plain string.
- **Agent handling in `get_all_tools()`**: Agent tool calls were already included via the existing loop; no code change needed — confirmed by test.

### Changed
- **`get_workflow()` — Agent step shape** (`analysis/tools.py`): Agent steps gain `agent_type`, `duration_ms`, `token_count`, `tool_count` fields from TUR. Missing `agentType` emits `"unknown"`.
- **`get_workflow()` — precise `outcome` derivation**: Bash steps use `returnCodeInterpretation` first; Agent steps use `status == "completed"` → `"success"` / else → `"error"`. Falls back to `is_tool_error()` for all other tools.
- **`_extract_tool_detail()` — Agent support**: Returns `description` field (preferred) or first 200 chars of `prompt`. Previously returned `None` for Agent calls.

---


## [0.69.3] - 2026-03-31 (komile-0331)

### Changed
- **`/files` — `filePath` from `toolUseResult`** (`analysis/tools.py`): `_extract_file_operation()` now accepts an optional `tool_use_result` dict and uses `filePath` (Edit/Write) or `file.filePath` (Read) from the structured result when available, falling back to `input.file_path`.
- **`/files` — Glob/Grep matched files** (`analysis/tools.py`): `get_files_touched()` now also tracks files matched by Glob and Grep calls — each matched filename from `toolUseResult.filenames` is added as an operation with `operation: 'Glob'` or `'Grep'`. Renderer updated to display these sections.
- **`/files?patches=true`** (`analysis/tools.py`, `adapter.py`): New query param. When set, each operation entry gains a `patch` field — `structuredPatch` list (hunk objects) for Edit/Write, `null` for Read/Glob/Grep.

---

## [0.69.2] - 2026-03-31 (bayuzeso-0331)

### Added
- **`claude://` adapter — token visibility**: `get_overview()` now includes `token_summary` (input/output/cache tokens + hit rate) and `context` (cwd, git_branch, version) blocks. Overview renderer surfaces these as `Tokens:` and `Context:` lines.
- **`claude://session/NAME?tokens` route** (`analysis/overview.py`): New `get_token_breakdown()` function returns `claude_token_breakdown` — per-turn table of input/output/cache tokens with `cumulative_input` tracking context growth. Renderer formats as aligned table with totals.
- **`toolUseResult` integration** (`analysis/tools.py`): `_build_tool_use_result_map()` extracts the structured `toolUseResult` top-level field from user messages (paired 1:1 when a message has exactly one tool_result). `is_tool_error()` now accepts optional `tool_use_result` dict and checks `returnCodeInterpretation` first (`error`/`success`), falling back to `is_error` flag + regex. All callers (`extract_all_tool_results`, `_track_tool_results`, `calculate_tool_success_rate`) updated.
- **`outcome` and `backgrounded` on workflow steps** (`analysis/tools.py`): Each step in `get_workflow()` now has `outcome: 'success'|'error'` (from tool result lookup) and `backgrounded: True` when `backgroundTaskId` present. Workflow renderer shows `✗` suffix on errors and `[bg]` on backgrounded steps.

---

## [0.69.1] - 2026-03-31 (mighty-chimera-0330, emerald-crystal-0331)

### Fixed
- **`_dir_cache_key` stat mock bug** (`adapters/calls/index.py`): `Path.is_dir()` routes through the global `os.stat` singleton, so a test mock on `os.stat` captured every `is_dir()` check — including on `.py` files. Replaced `iterdir()+is_dir()` with `os.scandir()+entry.is_dir()`, which uses cached directory-entry type info and bypasses `os.stat`. Was failing on Linux and Windows.
- **`git://` pygit2 path separator on Windows** (`adapters/git/adapter.py:402`): `os.path.relpath()` returns backslashes on Windows; pygit2 tree and blame APIs require POSIX forward slashes. Fixed with `.replace(os.sep, '/')` — no-op on Linux/macOS, fixes `KeyError`/`ValueError` on Windows for `reveal git://./file.py?type=blame` from a subdirectory.
- **5 Windows path antipattern test fixes**: Hardcoded `/tmp/`, `/fake/` POSIX literals in assertions and `Path('/...')` mock attribute assignments replaced with platform-neutral equivalents. Covered: `test_display_outline`, `test_display_structure_coverage`, `test_git_adapter`, `test_imports`, `test_claude_adapter`.

### Added
- **`scripts/check_windows_compat.py`**: Grep-based antipattern checker that scans `tests/` for POSIX path literals in assertions and `Path('/...')` mock `.path` assignments. Wired into CI via `.github/workflows/test.yml` (`--warn` mode; flip flag to `--strict` to make violations blocking).

---

## [0.69.0] - 2026-03-30 (pearl-tone-0330, bright-nebula-0330, visible-cosmos-0330)

### Added
- **`REVEAL_CLAUDE_JSON` env var** (BACK-119): Explicit override for `~/.claude.json` path. When `REVEAL_CLAUDE_HOME` is set, `CLAUDE_JSON` now auto-derives from `CLAUDE_HOME.parent / '.claude.json'` — a single env var covers the whole user's Claude install (critical for SSH multi-user scenarios). `REVEAL_CLAUDE_JSON` provides an escape hatch for non-standard layouts. `claude://info` now reports `REVEAL_CLAUDE_JSON` in the environment override block.
- **`CONVERSATION_BASE` derives from `REVEAL_CLAUDE_HOME`** (BACK-121): When `REVEAL_CLAUDE_HOME` is set without `REVEAL_CLAUDE_DIR`, `CONVERSATION_BASE` now resolves to `CLAUDE_HOME / 'projects'` automatically. Previously it fell back to `_resolve_claude_projects_dir()` which ignored the override — in SSH scenarios, sessions were read from the wrong user's directory. `REVEAL_CLAUDE_DIR` still takes explicit precedence.
- **`--base-path` covers the full Claude install** (BACK-120): `reconfigure_base_path` now derives `CLAUDE_HOME`, `CLAUDE_JSON`, `PLANS_DIR`, `AGENTS_DIR`, and `HOOKS_DIR` from `path.parent` — a single `--base-path /path/to/.claude/projects` flag is sufficient to point all `claude://` resources at a different install. Previously only `CONVERSATION_BASE` was updated, leaving history, config, and plans reading from the local machine.

### Fixed
- **`calls://` hangs on projects with `.venv`** (visible-cosmos-0330): `collect_structures()` used `rglob('*')` with no directory exclusions, crawling `.venv/site-packages` and other non-project directories. For a project with a virtualenv this meant 11,500+ Python files analyzed instead of ~60, causing 90+ second hangs. Fixed by replacing `rglob` with `os.walk` that prunes `_SKIP_DIRS` (`.venv`, `venv`, `node_modules`, `site-packages`, `__pycache__`, etc.) at directory-entry time. Result: 0.8s vs 90s on the affected project.
- **`calls://` misses callers using `*foo(args)` starred-unpack syntax** (visible-cosmos-0330): tree-sitter Python parses `*foo(bar)` as `call(list_splat(*foo), bar)` — the list_splat node becomes the callee. `_get_callee_name` fell through to the text fallback and returned `'*foo'`, which never matched a lookup for `'foo'`. Fixed in `_get_callee_name` to unwrap `list_splat` and return the inner identifier. Also handles `*self.method(args)` where tree-sitter embeds `*` inside the attribute node text (fixed with `.lstrip('*')` on attribute callee text). Both cases now correctly tracked by the callers index.
- **`_dir_cache_key` only statted the root directory** (visible-cosmos-0330): On Linux, editing a file in a subdirectory only advances that subdirectory's mtime — not the root's — so the callers index cache served stale results after any nested file edit. Fixed to stat the root plus all immediate non-skipped subdirectories (O(subdirs), not O(files)).
- **`_extract_project_from_dir` hardcoded username**: `'scottsen'` was in the `_SKIP` set used to filter non-meaningful path components from encoded Claude project directory names. Removed — `_SKIP` now contains only generic path segment words (`home`, `src`, `projects`, `external`, `internal`, `git`).
- **TIA-specific boilerplate in session title extraction**: `'# TIA System Instructions'` removed from `_BOILERPLATE_PREFIXES` (both `adapter.py` and `analysis/overview.py`) — only the generic `'# Session Continuation Context'` prefix is now treated as auto-injected boilerplate.
- **`tia session badge` regex generalized**: `_extract_badge_from_messages` now matches `session badge "text"` (any CLI prefix), not just the `tia`-prefixed form.
- **`boot.` removed from session title skip list**: Only bare `boot` is skipped; `boot.` and other forms are returned as-is. `boot` skip applies in both `_extract_session_title` (overview.py) and `_parse_jsonl_line_for_title` (adapter.py).
- **TIA references cleaned from code/docs**: Removed `TIA-style` from `_find_conversation` docstring and `SESSIONS_DIR` class comment; removed `TIA session domain` from `get_help` `see_also`; updated `_extract_project_from_dir` docstring to use generic example paths.

---

## [0.68.0] - 2026-03-30 (pearlescent-paint-0328, icy-spear-0330, serene-storm-0330, expanding-planet-0330, pouring-snow-0330)

### Added
- **`claude://config`**: Reads `~/.claude.json` (per-install config). Shows project count, per-project MCP server names, and key feature flags (`autoUpdates`, `verbose`, etc.). `?key=<dotpath>` extracts a specific value. Secrets masked automatically. (`session: expanding-planet-0330`)
- **`claude://memory`**: Walks `~/.claude/projects/*/memory/` to list all memory files across projects. Shows type, description, and modified date (parsed from YAML frontmatter). `claude://memory/<project>` filters to one project. `?search=term` filters by content. (`session: expanding-planet-0330`)
- **`claude://agents`** / **`claude://agents/<name>`**: Lists or reads agent definitions from `~/.claude/agents/`. Parses frontmatter for name, description, tools, and model. (`session: expanding-planet-0330`)
- **`claude://hooks`** / **`claude://hooks/<event>`**: Lists hook event types from `~/.claude/hooks/`. Handles both file-style events (single script) and directory-style events (multiple scripts). Reads content of specific event scripts. (`session: expanding-planet-0330`)
- **`AGENTS_DIR` / `HOOKS_DIR` class attrs**: `ClaudeAdapter.AGENTS_DIR` = `CLAUDE_HOME / 'agents'`, `ClaudeAdapter.HOOKS_DIR` = `CLAUDE_HOME / 'hooks'`. (`session: expanding-planet-0330`)
- **`_parse_agent_frontmatter()` / `_mask_secrets()` helpers**: Shared by config, memory, and agents resources. (`session: expanding-planet-0330`)
- **21 new tests** across `TestClaudeConfig`, `TestClaudeMemory`, `TestClaudeAgents`, `TestClaudeHooks`. (`session: expanding-planet-0330`)
- **`claude://info`**: Diagnostic resource showing all resolved data paths (`~/.claude/`, projects, history, plans, settings, agents, hooks) plus active env var overrides. (`session: serene-storm-0330`)
- **`claude://settings`**: Reads `~/.claude/settings.json` with structured output. `?key=<dotpath>` extracts a nested value (e.g. `?key=permissions.additionalDirectories`, `?key=model`). (`session: serene-storm-0330`)
- **`claude://plans`** / **`claude://plans/<name>`**: List or read plans from `~/.claude/plans/`. Sorted by recency, shows title from first heading. `?search=term` filters by content. Individual plan reads return full markdown. (`session: serene-storm-0330`)
- **`PLANS_DIR` class attr**: `ClaudeAdapter.PLANS_DIR` = `CLAUDE_HOME / 'plans'`. (`session: serene-storm-0330`)
- **`claude://history`**: New resource exposing `~/.claude/history.jsonl` prompt history. Supports `?search=term`, `?project=path`, `?since=date` filters. Default shows 50 most recent prompts; `--all` for full scan. Output grouped by session for readability. (`session: icy-spear-0330`)
- **`CLAUDE_HOME` class attr**: `ClaudeAdapter.CLAUDE_HOME` resolves `~/.claude/` (with `%APPDATA%\Claude` Windows fallback). Override via `REVEAL_CLAUDE_HOME` env var. (`session: icy-spear-0330`)
- **`CLAUDE_JSON` class attr**: `ClaudeAdapter.CLAUDE_JSON` = `~/.claude.json` (per-install MCP config, separate from `CLAUDE_HOME`). (`session: icy-spear-0330`)
- **`_resolve_claude_home_dir()`**: New resolver function; `_resolve_claude_projects_dir()` now delegates to it for consistent Windows fallback logic. (`session: icy-spear-0330`)
- **`CLAUDE_ADAPTER_GUIDE.md` — Install Introspection section** (BACK-101): New "Install Introspection Resources" section documents all 8 non-session resources (`info`, `history`, `settings`, `plans`, `config`, `memory`, `agents`, `hooks`) with query parameter tables, sub-resource paths, and return value descriptions. Overview updated to introduce both resource families. Quick Start entries added. (`session: pouring-snow-0330`)

### Fixed
- **`CONVERSATION_BASE` env var pattern**: `Path(os.environ.get('REVEAL_CLAUDE_DIR', '')) or ...` was silently broken (`Path('')` is truthy as `PosixPath('.')`). Fixed to use the same conditional pattern as `CLAUDE_HOME`. (`session: serene-storm-0330`)
- **`release.sh --resume`: remote-tag-not-found is non-fatal** (`scripts/release.sh`): `git push --delete origin vX.Y.Z` now warns instead of erroring when the remote tag doesn't exist (common when tag was local-only due to a prior interrupted release). Also adds `--resume` and `--dry-run` flags, PyPI polling at the end, and improved error messages pointing to `--resume` on tag-exists failures.
- **`RELEASING.md`**: New troubleshooting section "Tag pushed, no GitHub release, new commits since"; stale `v0.18.0` example versions replaced with `vX.Y.Z`; `--resume` and `--dry-run` flags documented.
- **`UX_ISSUES.md`**: UX-12 marked resolved (was fixed in pearlescent-aurora-0328 via BACK-118 but status not updated).

---

## [0.67.0] - 2026-03-28 (sessions rose-beam-0327, shining-satellite-0327, pulsing-gravity-0327, hopofo-0328)

### Added
- **OR-alternation (`|`) in markdown section extraction** (`analyzers/markdown.py`): `reveal doc.md "Open Issues|Action Items"` extracts both sections in one call, concatenated in document order. Each `|`-separated term follows exact → substring priority. Backslash-escaped pipes (`\|`, grep-style) normalised automatically. Spaces around `|` trimmed. Deduplication when a section matches multiple terms. Returns `None` only when all terms fail. Extracted `_section_end` to a static method; added `_collect_section_spans` helper. 15 new tests in `TestMarkdownSectionOrPattern` (6,932 → 6,946 +14). (rose-beam-0327)
- **`--broken-only` flag for `reveal doc.md --links`** (`analyzers/markdown.py`, `cli/parser.py`): Filter link output to broken internal links only. `broken_only` param added to `_extract_links` and `_extract_links_regex`; wired through `StructureOptions` and `_add_markdown_link_kwargs`. Also implies `--links` when used alone. 5 new tests in `TestMarkdownLinkBrokenOnly`. (shining-satellite-0327)
- **`--lines` ghost flag targeted error** (`main.py`): `_check_ghost_flags()` intercepts `--lines N-M` before argparse and emits a helpful suggestion: `reveal file:N-M` (line range) or `reveal file --range N-M` (structure range). Exit 2, no usage dump. (shining-satellite-0327)

### Fixed
- **`markdown://` query string in error path** (`adapters/markdown/adapter.py`): `MarkdownQueryAdapter.__init__` now strips `?...` suffix from `clean_path` before `Path.resolve()`. Error from `reveal 'markdown://docs/?link-graph'` now reads `markdown:// directory 'docs' not found: /abs/path/docs` instead of `Directory not found: /abs/path/docs/?link-graph`. (shining-satellite-0327)

### Refactored
- **Nginx handlers relocated** (`adapters/nginx/handlers.py`): All 22 nginx CLI handler functions moved from `reveal/handlers_nginx.py` → `reveal/adapters/nginx/handlers.py`. `file_handler.py` updated to import from new location. `handlers_nginx.py` deleted. Tests unaffected (import via `reveal.file_handler` which still re-exports). (shining-satellite-0327)
- **Consolidate tree-sitter extension map** (`registry.py`, `main.py`): Promoted local `EXTENSION_MAP` dict inside `_guess_treesitter_language` to module-level `TREESITTER_EXTENSION_MAP` constant. `main.py._get_tree_sitter_fallbacks` now imports and derives `fallback_languages` from it (adding display names locally). Single source of truth for adding new tree-sitter language support. Also added 12 previously missing extensions to the probed set: `.hxx`, `.mli`, `.ocaml`, `.r`, `.zig`, `.v`, `.sv`, `.svh`, `.m`, `.mm`, `.erl`, `.hrl`, `.ex`, `.exs`. (pulsing-gravity-0327)
- **Intra-file call graph in JSON output** (`treesitter.py`, `display/structure.py`): `TreeSitterAnalyzer._extract_relationships()` now overrides the base class no-op — flattens per-function `calls` lists into a flat edge list `{'calls': [{'from', 'from_line', 'to'}]}`. Wired into `_render_json_output()`: `reveal file.py --format json` now includes a top-level `relationships` key when call data is present, absent otherwise. Covers `functions` and `methods` categories; attribute calls (`self.validate`, `json.dumps`) preserved as-is. 15 new tests. (pulsing-gravity-0327)

### Docs
- **`MARKDOWN_GUIDE.md`**: New "OR-Pattern Section Extraction" section with examples; rewrote "Section Name Matching" to accurately reflect case-insensitive + substring + OR behavior.
- **`AGENT_HELP.md`**: OR-pattern examples added to markdown task; matching rules + agent tips table; version bumped to 0.66.2 (was stale at 0.66.1).
- **`UX_ISSUES.md`**: UX-08 and UX-09 marked resolved (shining-satellite-0327).
- **`ARCHITECTURE.md`**: Constructor Conventions updated (5 strategies, not 4; two-ordering behavior; per-adapter strategy table); Budget Limits expanded with code example and adopter table; new "Known Design Decisions" section documenting `file_handler.py` re-exports, `_grep_extract()` no-op, `_extract_relationships()` reserved hook, and global parse cache. (pulsing-gravity-0327)
- **`CONTRIBUTING.md`**: URI adapter section rewritten with complete working example; Common Pitfalls expanded with bare-except, manual query parsing, and missing output contract pitfalls; Priority Areas updated to reflect current backlog. (pulsing-gravity-0327)
- **`internal-docs/BACKLOG.md`**: BACK-097, BACK-098, BACK-107, BACK-108, BACK-109 resolved; BACK-110 resolved; BACK-111 closed (not present); BACK-112 added. (pulsing-gravity-0327)

### Fixed (hopofo-0328)
- **BACK-113: False `--analyzer text` suggestion removed** (`errors.py`): `AnalyzerNotFoundError` no longer suggests `--analyzer text` (a flag that doesn't exist). Agents following the old hint got a second exit 2 with the full usage dump. Adjacent `--allow-fallback` hint corrected to "remove `--no-fallback`". Confirmed false in copper-beam-0328, amber-spark-0328.
- **BACK-114: `Element not found` now lists available names** (`display/element.py`): `_print_available_names()` added and called from `_handle_extraction_error()` on name-lookup failures. Prints `Available: foo, bar, baz (and N more)` to stderr (up to 10 names from functions/classes/methods). Structure already parsed — zero extra I/O. Eliminates the full-file roundtrip agents were forced into.
- **BACK-115: OR-pattern failure hints `--search`** (`display/element.py`): `_handle_extraction_error()` detects `|` in element name and emits: `Hint: '|' pattern matches headings only. For table or body content, use: reveal file --search 'term'`. Confirmed issue in shining-satellite-0327, pulsing-gravity-0327.
- **BACK-116: B005 skips `try/except ImportError` optional-dep imports** (`rules/bugs/B005.py`): `_find_optional_import_lines()` walks the AST and collects imports inside `try/except ImportError`, `try/except (ImportError, ModuleNotFoundError)`, and bare `except` blocks. These line numbers are excluded from B005 detection. Bare broken imports outside these guards still fire. Confirmed false positive in 2 user projects (pillow_heif in SMD, vtracer in Cutliner). 15 new tests; 6,967 total passing.

### Docs (hopofo-0328)
- **BACK-117: `AGENT_HELP.md` — "Suppressing false positives" section** (`reveal/docs/AGENT_HELP.md`): Added "Suppressing false positives with `.reveal.yaml`" block after "Review code quality" pipeline section. Includes `.reveal.yaml` override examples for workers/plugins/blueprints (M102), M102 heuristic detail (dynamic dispatch patterns), and a common false-positive rule table (M102, B005, I001). Updated v0.67.0 changelog line.
- **`UX_ISSUES.md`**: UX-10, UX-11, UX-13, FP-01, FP-02 marked resolved (hopofo-0328). Status updated to 1 open issue (UX-12).
- **`internal-docs/BACKLOG.md`**: BACK-113, BACK-114, BACK-115, BACK-116, BACK-117 moved to Resolved. All priority sections now empty. (hopofo-0328)

### Fixed (jiticolo-0328)
- **`help://` root leaked internal adapters** (`adapters/help.py`): `_list_adapters()` iterated all `_ADAPTER_REGISTRY` entries without filtering `_INTERNAL_ADAPTERS`, causing `demo://` to appear in the main index and the count to read "23 registered" instead of 22. Added `if scheme in self._INTERNAL_ADAPTERS: continue` guard.
- **`help://schemas` listing leaked internal adapters** (`adapters/help.py`): Same omission in the `schemas` route — `demo` and `test` appeared in the available adapter list. Applied same filter.
- **`help://quick` stale adapter count** (`adapters/help.py`): Hardcoded "20+" updated to "22".
- **`nginx`, `letsencrypt`, `calls` classified as Experimental** (`rendering/adapters/help.py`): All three were missing from `BETA_ADAPTERS` (added after the set was defined), causing 🔴 display in the index and detail headers. Added all three; `letsencrypt` also declares `'stability': 'beta'` in its own adapter.

### Docs (jiticolo-0328)
- **`HELP_SYSTEM_GUIDE.md`**: Version updated 0.30.0 → 0.67.0; file path references corrected (`reveal/` → `reveal/docs/`); `GUIDE_CATEGORIES` code example updated (was showing a local variable that no longer exists); last-updated date corrected.
- **`AGENT_HELP.md`**: Added `letsencrypt://` to schema discovery examples; added full task sections for `letsencrypt://` (cert inventory, orphan/duplicate detection) and `autossl://` (run log inspection, failure investigation workflow) — both adapters had no coverage in the agent guide.

### Fixed (pearlescent-aurora-0328)
- **BACK-118: Code element not-found hints at `--search`** (`display/element.py`): `_handle_extraction_error()` else branch now emits "Hint: Code extraction matches exact names. For content search, use: reveal {path} --search '{element}'" when the query has no `|`. Closes the exact-match/substring asymmetry gap documented in UX-12.
- **Dead code: `'release'` removed from help rendering** (`rendering/adapters/help.py`): `GUIDE_CATEGORIES['dev_guides']`, `TOKEN_ESTIMATES`, and `_get_guide_description()` all referenced a `'release'` topic that has no backing file and never resolves. Removed all three references.
- **`_get_production_adapters()` now excludes `demo`** (`tests/test_registry_integrity.py`): `demo` is in `_INTERNAL_ADAPTERS` and is not a production adapter; discarding only `test` caused the README count assertion to fail (23 vs 22). Added `adapters.discard('demo')`.

### Tests (pearlescent-aurora-0328)
- **`test_display_filtering.py`** (new, 38 tests): Full coverage for `display/filtering.py` — `GitignoreParser` (parse, match, negate, dir patterns, outside-dir path) and `PathFilter` (defaults, `include_defaults=False`, gitignore integration, custom exclude, no gitignore present) and `should_filter_path` convenience wrapper. Coverage: 18% → 98%.
- **`test_display_outline.py`** (new, 31 tests): Full coverage for `display/outline.py` — `build_hierarchy` (empty, flat, nested, sort, category injection, non-dict skip, immutability), `build_heading_hierarchy` (empty, h1/h2/h3 nesting, siblings, new-h1 reset, immutability), `_build_metrics_display`, `_build_item_display`, `_get_child_indent`, `render_outline` (capsys, tree chars). Coverage: 10% → 99%.
- **`test_display_metadata.py`** (new, 13 tests): Coverage for `display/metadata.py` — `_format_display_key` (count suffix, snake_case, title), `_print_file_header` (existing file, size tiers B/KB, fallback indicator, nonexistent file), `show_metadata` (JSON/human format, optional fields, int comma-formatting). Coverage: 16% → 89%.
- **`test_display_element.py`** (+13 tests): `TestHandleExtractionErrorHints` — UX-12 hint fires for simple names, pipe hint fires for `|` queries, hint uses full element name in `--search`; `TestPrintAvailableNames` — functions/classes listed, capped at 10 with "and N more", no output on empty structure, exception silently swallowed, non-dict items skipped. Coverage: 85% → 91%.

---

## [0.66.2] - 2026-03-22 (sessions sacred-shrine-0321, noble-earth-0322)

### Fixed
- **BUG-03: `CallsRenderer.render_element` removed** (`adapters/calls/adapter.py`): `render_element` was byte-for-byte identical to `render_structure` and caused the routing layer to treat `calls://` as element-capable. The routing layer calls `adapter.get_element()` when `render_element` exists — this returns `None` from the base class, producing a false "Element not found" error instead of the structure response. Removed `render_element`; `render_structure` is the only render path. (session sacred-shrine-0321)
- **BUG-04: `LetsEncryptAdapter.get_structure()` missing `source` / `source_type`** (`adapters/letsencrypt/adapter.py`): Both contract fields absent from result dict, breaking downstream consumers. Added `'source': self.live_dir` and `'source_type': 'letsencrypt_directory'`. (session sacred-shrine-0321)
- **CFG-01: `_ALLOWED_RULE_CONFIG_KEYS` too narrow** (`rules/__init__.py`): `max_length` (E501), `MAX_DEPTH` (C905), `MAX_ARGS` (R913) were not in the allowlist, causing hundreds of "Unknown rule config key … ignored" warnings on every `reveal check` run. Corrected allowlist to include the keys with correct case (`MAX_ARGS` not `max_args`). (session sacred-shrine-0321)
- **PERF-01: `_dir_cache_key` full rglob on every cache miss** (`adapters/calls/index.py`): Replaced O(n-files) rglob walk with a single `os.stat(directory).st_mtime_ns` call. Directory mtime advances on any direct child change — sufficient for cache invalidation. OSError fallback preserves original per-file fingerprint. (session sacred-shrine-0321)
- **MEM-08: `_collect_matching_files` builds full list before sort** (`tree_view.py`): Converted to a generator. `show_file_list` now uses `heapq.nlargest/nsmallest` for the default mtime sort, holding at most 500 tuples in memory regardless of directory size. Non-mtime sorts materialize and cap at 500. (session sacred-shrine-0321)
- **`.reveal.yaml` R913 config key wrong case** (`.reveal.yaml`): Config used `max_args: 5` (lowercase) but R913's class attribute is `MAX_ARGS` (uppercase). The allowlist correctly requires `MAX_ARGS`, so the project's own config was triggering the "Unknown rule config key" warning that CFG-01 was meant to stop. Corrected to `MAX_ARGS: 5`. (session noble-earth-0322)

### Tests
- **Test review pass**: replaced 3 tautological/redundant tests added for BUG-03/04/CFG-01. Discovered CFG-01 fix had wrong case (`max_args` vs `MAX_ARGS`); corrected. Tests now use real rule imports (C905, R913, E501) instead of stub mirrors of the implementation. (session sacred-shrine-0321)
- **30 new tests for `AstAdapter`** (`tests/adapters/test_ast_adapter.py`, TEST-01): `__init__` query parsing, show_mode/builtins extraction, result_control, output contract (source/source_type/contract_version/meta), filtering, sort/limit/offset, 200-entry auto-cap, builtin filtering, edge cases (binary file, empty dir, colon syntax error). (session sacred-shrine-0321)
- **33 new tests for `PythonAdapter`** (`tests/test_python_adapter_extended.py`, TEST-02): all 9 `get_element` routes, unknown element returns None, `_get_env`/`_get_venv` field contracts, packages/module sub-routes, `get_structure` contract, `get_available_elements` completeness, every listed element routes without returning None. (session sacred-shrine-0321)
- **4 tests for PERF-01** (`tests/adapters/test_calls_adapter.py`): fast path returns `('dir_mtime', int)`, same key on unchanged dir, hashable, exactly 1 `os.stat` call (not per-file). (session sacred-shrine-0321)
- **5 tests for MEM-08** (`tests/test_tree_view.py`): generator type, tuple shape, heap cap enforcement, ascending mtime sort, name sort fallback. (session sacred-shrine-0321)
- **Test count: 6,860 → 6,932** (+72). All items in UX_ISSUES.md now resolved.

---

## [0.66.1] - 2026-03-21 (session wicked-grid-0321)

### Fixed
- **False-positive circular deps from `from . import X` in packages** (`analyzers/imports/resolver.py`, `rules/imports/I002.py`): `_resolve_relative` incorrectly resolved `from . import refs` (empty `module_name`) to `__init__.py` instead of `refs.py`. This created spurious cycle edges `__init__.py → adapter.py → __init__.py` for any adapter using the standard `from . import submodule` pattern. Root cause: when `not parts`, the resolver fell through to `__init__.py` without checking whether the imported names were sibling modules. Fix: try each imported name as `name.py` / `name/__init__.py` first; fall back to `__init__.py` only when no sibling module matches. Also handles `from . import query as q` (tree-sitter yields `"query as q"` as the name; strip alias before resolving). `_resolve_graph_dependencies` updated to emit one edge per imported name for multi-name `from . import X, Y, Z` statements, restoring full submodule dependency tracking. Eliminated all 3 false-positive cycles in reveal's own adapter packages (git, markdown, reveal). (session wicked-grid-0321)
- **git adapter: semantic blame broken when CWD is nested inside repo root** (`adapters/git/adapter.py`): `get_structure` now normalises `git_subpath` to repo-root-relative before passing to `pygit2` blame/tree APIs. `_parse_resource_string` also handles `./path/file.py` URI form (strips leading `./`, routes to blame). (session digital-vault-0321)
- **git adapter: element blame percentage used total file lines as denominator** (`adapters/git/renderer.py`): `_render_file_blame_summary` now uses `element['line_end'] - element['line_start'] + 1` as denominator when rendering element-scoped blame, so a sole author of a 100-line function shows 100.0% instead of ~9.5%. (session digital-vault-0321)

### Tests
- **4 regression tests for git adapter bug fixes** (`tests/test_git_adapter.py`): `test_blame_cwd_nested_inside_repo` (CWD is a subdirectory of the repo root), `test_blame_element_percentage_uses_element_span` (element % denominator), `test_dotslash_uri_form_parses_to_subpath` (`./file.py` URI parses to `subpath`), `test_dotslash_root_still_means_repo_overview` (`.` and `./` still route to overview). (session wicked-grid-0321)
- **4 regression tests for import resolver fix** (`tests/test_imports.py`): `test_from_dot_import_resolves_to_submodule`, `test_from_dot_import_aliased_resolves_to_submodule`, `test_from_dot_import_class_falls_back_to_init`, `test_init_re_export_pattern_no_false_cycle`. Test count: 6,863 → 6,871. (session wicked-grid-0321)

## [0.66.0] - 2026-03-20 (sessions storm-eruption-0320, electric-ember-0320, oracular-anvil-0320)

### Refactored
- **BACK-098: Split `handlers.py` and `routing.py` into subpackages** (`reveal/cli/`): `handlers.py` (1,104 lines) split into `handlers/introspection.py` (informational flags), `handlers/batch.py` (stdin/batch processing), `handlers/decorators.py` (--decorator-stats). `routing.py` (744 lines) split into `routing/uri.py` (adapter dispatch pipeline) and `routing/file.py` (file/directory routing and guards). All public names re-exported from `__init__.py`; backward-compat aliases preserved. 12 test mock patch targets updated to correct submodule locations. (session electric-ember-0320)
- **`calls/index.py` complexity reduction** (`adapters/calls/index.py`): `find_uncalled` reduced from 126 → 84 lines (eliminating ❌ C902); `build_callers_index` and `find_callers` depth reduced from 5 → 3/2 (eliminating C905). Extracted 7 focused helpers: `_get_decorator_names`, `_is_method_elem`, `_is_implicit_element`, `_uncalled_entry_mtime`, `_index_callee`, `_bfs_level`, and module-level `_IMPLICIT_DECORATORS` constant. (session oracular-anvil-0320)

### Fixed
- **Markdown ambiguous heading match now concatenates** (`analyzers/markdown.py`): When a partial heading query matched multiple sections (e.g. `"BACK-09"` matching 4 entries), reveal crashed with `ValueError: Ambiguous heading match`. Now returns all matching sections concatenated. Test updated from asserting ValueError to asserting both headings appear in the combined source. (session oracular-anvil-0320)
- **Markdown section extraction substring match** (`analyzers/markdown.py`): Section extraction was exact-match only (case-insensitive). Agents passing partial heading text — especially emoji-prefixed headings like `🆕 Critical Status Corrections Since Last Doc` — received "Element not found" errors. Fix: exact match is tried first; if no exact match, falls back to substring match when exactly one heading contains the query; raises `ValueError` listing all candidates when multiple headings match. 4 new tests in `TestMarkdownSectionSubstringMatch`. (session storm-eruption-0320)

### Tests
- **Fixed tautology in `test_extract_element_at_line_no_match`** (`tests/test_display_element.py`): Assertion was `assert result is None or result is not None` (always passes). Fixed to `assert result is None`. Added `test_route_to_single_line_fallback_context_window` (verifies ±10 window fires for module-level lines) and strengthened `test_route_to_single_line_extraction` to assert function name and source content. (session oracular-anvil-0320)

### Docs
- **`:N` line-number extraction documented** (`cli/parser.py`, `docs/QUICK_START.md`, `docs/RECIPES.md`): The `element` argument help text now lists all syntaxes (`:N`, bare integer, `:N-M`, `@N`, `Class.method`). QUICK_START Example 3 adds line-number extraction examples. RECIPES "Find the code behind the error" now leads with `reveal file.py :166` workflow. (session oracular-anvil-0320)

## [0.65.1] - 2026-03-19 (session yapaxe-0319)

### Fixed
- **Windows `claude://` UUID truncation** (`adapters/claude/renderer.py`): Session listing truncated 36-char UUIDs to 34 chars (`name[-34:]` cut first 2 chars). Column width widened to 36; truncation changed to `name[:33] + '...'` for long display names. (session roaring-wind-0319)
- **Windows `claude://` suffix match** (`adapters/claude/adapter.py`): Added Strategy 3 suffix match in `_find_conversation` so truncated UUIDs from prior installs still resolve. (session roaring-wind-0319)
- **Windows `claude://` projects dir** (`adapters/claude/adapter.py`): `_resolve_claude_projects_dir()` now checks `~/.claude/projects` first (standard on all platforms including Windows), with `%APPDATA%\Claude\projects` as fallback for non-standard installs. (session roaring-wind-0319)
- **CI: `mcp` and `pygit2` missing from dev extras** (`pyproject.toml`): All 6 CI jobs (Linux/Mac/Windows × Python 3.10/3.12) failed because `mcp>=1.0.0` and `pygit2>=1.14.0` were not listed under `[project.optional-dependencies] dev`. (session roaring-wind-0319)
- **Windows letsencrypt path separator** (`adapters/letsencrypt/adapter.py`): `_find_orphans` used `str(Path(cert_path).parent)` which returned `\`-separated paths on Windows; changed to `cert_path.rsplit('/', 1)[0]` since server cert paths are always POSIX. (session roaring-wind-0319)

## [0.65.0] - 2026-03-19 (sessions strong-temple-0318, cooling-current-0318, pulsing-cluster-0318, violet-brush-0318, crystal-laser-0318, universal-journey-0319, xaxegotu-0319, fierce-pegasus-0319, bright-star-0319)

### Added
- **BACK-080: HTTP probe mode** (`adapters/ssl/probe.py`, `--probe-http`, `--probe`): Live HTTP→HTTPS redirect verification and security header check. `reveal ssl://domain --probe-http` follows the redirect chain from port 80, verifies the server redirects to HTTPS, and captures HSTS / X-Content-Type-Options / X-Frame-Options / CSP headers from the final HTTPS endpoint — no second request, headers come from the last redirect hop directly. `reveal nginx://domain --probe` appends the same probe to the normal vhost summary. New `probe.py` module is fully testable via injectable `_opener`. 20 new tests in `test_http_probe.py`. (session bright-star-0319)
- **`_extract_includes` inline include fix** (`adapters/nginx/adapter.py`): Removed `^` anchor from the `include` regex — includes appearing inline (e.g. `http { include *.conf; }`) were silently skipped during fleet audit snippet analysis. (session bright-star-0319)
- **`LETSENCRYPT_ADAPTER_GUIDE.md`** (`docs/`): Full guide for the `letsencrypt://` adapter — inventory, orphan/duplicate detection, JSON schema, three operator workflows, limitations, troubleshooting. INDEX.md referenced this file since xaxegotu-0319 but the file was never written. (session bright-star-0319)

### Fixed
- **Exit code logic corrected** (`handlers.py`): `_calculate_batch_exit_code` returned exit code 1 when both failures and warnings were present, and 2 for failures-only — severity backwards. Correct behavior: failures always → exit code 2; warnings alone → 0. Scripts checking `exit_code >= 2` for hard failure now work correctly. (session crystal-laser-0318)
- **Budget off-by-one** (`query.py`): `apply_budget_limits` returned an empty list when the first item exceeded `max_bytes`. Changed `truncated_at = i` to `truncated_at = max(i, 1)` to always return at least one item. (session crystal-laser-0318)
- **Port 0 treated as falsy** (`uri.py`): `build_connection_string` used `if port:` which skipped port 0 (valid OS-assigned port). Changed to `if port is not None:`. (session crystal-laser-0318)

### Refactored
- **`ImportsAdapter` now conforms to adapter contract** (`adapters/imports.py`): Previously `__init__()` took no arguments and `get_structure(uri)` parsed the URI — the only adapter with this pattern. Now `__init__(path, query)` parses on construction, matching all other adapters. The router no longer needs to reconstruct and re-pass the URI. (session crystal-laser-0318)
- **`RuleRegistry.discover()` is now lazy** (`rules/__init__.py`): Removed module-level `RuleRegistry.discover()` call that ran a filesystem scan on every `import reveal.rules`. All public entry points already had `if not cls._discovered: cls.discover()` guards. (session crystal-laser-0318)
- **`_apply_rule_config` now uses allowlist** (`rules/__init__.py`): Previously used unrestricted `setattr` guarded only by `hasattr`. Now validates keys against `_ALLOWED_RULE_CONFIG_KEYS = {enabled, severity, threshold, message, description}`. Unknown keys log a warning and are ignored. (session crystal-laser-0318)
- **Deleted orphaned `T = 'T'`** (`rules/base.py`): Leftover from a removed TypeVar import. (session crystal-laser-0318)

### Added
- **`reveal nginx:// --audit` fleet consistency matrix** (`adapters/nginx/`, BACK-090): Cross-site analysis of all enabled nginx vhosts. 7 checks per site: `server_tokens off`, `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `http2` on 443 listener, `limit_req` applied, deprecated `X-XSS-Protection`. Global column reads nginx.conf http{} block via `NginxAnalyzer.audit_global_directives`. Consolidation hint: when ≥50% of sites have a directive but it's absent globally, marks it as "Move to nginx.conf http{}" with `↑` indicator. Snippet consistency: detects `include` patterns used by ≥25% of sites and surfaces outlier sites missing them. Supports `--only-failures` and `--format json`. Exits with code 2 on gaps. 43 new tests. (session fierce-pegasus-0319)
- **BACK-084: `_handle_validate_nginx_acme` refactored** (`file_handler.py`): Extracted `_render_acme_json` and `_render_acme_text` from the 77-line mixed-output function; main function is now ~20 lines of setup + dispatch. No behavior change. (session fierce-pegasus-0319)

### Added
- **nginx security rules N008–N012** (`rules/infrastructure/`): Five new nginx rules sourced from the tia-proxy fleet audit (45–46/46 sites affected each). N008 HIGH: HTTPS server missing `Strict-Transport-Security` (follows includes one level deep); N009 MEDIUM: `server_tokens` not disabled (nginx version exposed in headers); N010 LOW: deprecated `X-XSS-Protection` header (surfaces snippet file path when header comes from an include); N011 LOW: SSL listener missing `http2` (Certbot strips it on renewal); N012 LOW/MEDIUM: no rate limiting on server block (escalates to MEDIUM when no `limit_req_zone` defined at all). All support `# reveal:allow-*` suppression comments. 37 new tests. Rule count: 64 → 69. (session universal-journey-0319)
- **`ELEMENT_NAMESPACE_ADAPTER` class attribute** (`adapters/base.py`): Replaces hardcoded `ELEMENT_NAMESPACE_ADAPTERS = {'env', 'python', 'help'}` set in `routing.py`. New adapters where `scheme://RESOURCE` means "get element RESOURCE" (rather than "analyze path RESOURCE") now declare `ELEMENT_NAMESPACE_ADAPTER = True` on their class; routing reads the attribute directly. Attribute set on `EnvAdapter`, `HelpAdapter`, `PythonAdapter`. (session universal-journey-0319)
- **`--global-audit` flag for nginx.conf** (`analyzers/nginx.py`, `file_handler.py`, BACK-091): Audits the `http{}` block and main context of nginx.conf for missing security and operational directives. Checks: `server_tokens off` (MEDIUM), `Strict-Transport-Security` (HIGH), `X-Content-Type-Options` (MEDIUM), `X-Frame-Options` (MEDIUM), `ssl_protocols` (MEDIUM), `resolver` (LOW), `limit_req_zone` (LOW), `client_max_body_size` (LOW), `gzip on` (INFO), `worker_processes` (INFO). Supports `--only-failures` and `--format json`. Scope-isolated: directives in nested `server{}` blocks are not counted. Exits with code 2 when directives are missing. 42 new tests. (session xaxegotu-0319)
- **`letsencrypt://` adapter** (`adapters/letsencrypt/`, BACK-079): Let's Encrypt certificate inventory — walks `/etc/letsencrypt/live/*/cert.pem`, returns cert list with SANs, expiry, and common name. `--check-orphans` cross-references nginx ssl_certificate directives (scans `/etc/nginx/sites-enabled/` and `conf.d/`) to find unreferenced certs. `--check-duplicates` groups certs by identical SAN sets. Flags pass through `get_structure()` via `_build_adapter_kwargs`. Supports `--format json`. 33 new tests. README adapter count: 22 → 23. (session xaxegotu-0319)
- **Three code-review fixes** (sessions xaxegotu-0319, crystal-laser-0318 follow-up): (1) `_is_sensitive()` false positives (`env.py`) — `KEY` now requires `_` or string boundary, preventing matches on `MONKEY`/`DONKEY`/`BUCKET`; (2) ReDoS guard (`utils/query.py`) — user-supplied regex patterns longer than 200 chars are rejected before `re.compile()`; (3) MRO inspection hack removed (`cli/routing.py`, `adapters/base.py`) — `post_process()` no-op added to `ResourceAdapter` base, routing uses `getattr(type(adapter), ...)` which is safe against Mock auto-attrs and non-`ResourceAdapter` test adapters.

### Added
- **`reveal help://relationships` — adapter ecosystem map**: New help topic that renders the 22 adapters as 5 functional clusters (Code Analysis, Infrastructure, Data & Config, Sessions & Docs, Self-Describing) with pairwise relationships and 5 "power pairs" — adapters that are best used together. Available as text or `--format=json` for programmatic use. 8 new tests. (session violet-brush-0318)
- **Related-adapter breadcrumbs expanded to all 22 adapters**: The "Next Steps" section shown after any `reveal help://<adapter>` now points to semantically related adapters for all registered adapters. Previously only 6 adapters had related-adapter hints; now all 22 do — grouped by cluster (e.g. `ssl://` points to `domain://` and `nginx://`; `calls://` points to `ast://` and `diff://`). (session violet-brush-0318)

### Fixed
- **xlsx large sheet guard — silent zero rows/cols**: Individual worksheet XML parts > 50 MB are now detected before parsing and reported as `"too large to parse (N MB)"` in the workbook overview instead of silently showing `0 rows, 0 cols`. Other sheets in the same workbook parse normally. Affected real files: `FactInternetSales` (58.5 MB) in AdventureWorksDW, `Sales_data` (72.3 MB) in AdventureWorks Sales. (session cooling-current-0318)
- **xlsx column count from dimension ref**: Column count in workbook overview was derived from first-row cell count, which undercounts sparse sheets and dynamic array spill zones (e.g., a sheet with `A1:P11` dimension but only 7 header cells in row 1 showed `7 cols` instead of `16`). Now parsed from the `dimension ref` XML attribute; first-row count used only as fallback when no dimension tag is present. (session cooling-current-0318)

### Added
- **xlsx Power Query M extraction** (`?powerquery=`): Reveal now extracts Power Query M code embedded in `customXml/DataMashup` blobs. The DataMashup inner ZIP (a streaming ZIP with empty central directory) is parsed via local file header scanning — no external libraries needed. Supports UTF-8 and UTF-16 encoded DataMashup items. Three modes: `list` (query names + line counts), `show` (all M code), `<name>` (specific query). The workbook overview banner now shows "📦 Power Query detected" when present. 12 new tests. (session pulsing-cluster-0318)
- **xlsx named ranges** (`?names=list`): Extracts `<definedName>` elements from `xl/workbook.xml`. Shows name, scope (global or sheet:N), reference, and hidden flag. Zero new dependencies (stdlib XML parsing). 8 new tests. (session pulsing-cluster-0318)
- **xlsx external connections** (`?connections=list|show`): Extracts `<connection>` elements from `xl/connections.xml`. `list` mode shows name, type, source; `show` mode shows full connection strings, SQL commands, and refresh-on-load flag. Type labels: ODBC, OLE DB, Web, Text File, ADO, Power Query. The workbook overview banner now shows "🔗 N external connections" when present. 8 new tests. (session pulsing-cluster-0318)
- **xlsx Tier 2 Power Pivot via pbixray**: Modern Power BI export xlsx files (embedded VertiPaq model, no XMLA) now use `pbixray` (already installed) as Tier 2 before falling back to pivot cache (Tier 3). Tier 2 provides full columns, DAX measures, and relationships. Relationships normalised to the XMLA `from/to` structure for unified rendering. The "Schema limited" and "DAX not available" messages no longer appear when pbixray succeeds. 5 new tests against `Retail_Analysis.xlsx`. (session pulsing-cluster-0318)
- **xlsx real-world test fixtures**: `tests/fixtures/xlsx/` now has 4 general fixtures (AdventureWorks Sales 121K rows, AdventureWorksDW 6-sheet DW, Financial Sample, dynamic arrays) and `tests/fixtures/xlsx/powerpivot/` has 6 Power Pivot fixtures: Contoso PnL in both Excel 2010 (`xl/customData/`) and Excel 2013 (`xl/model/item.data`) formats (full XMLA: 4 tables, 81 DAX measures, 3 relationships), plus 4 modern Power BI service samples (no XMLA; tables + columns + relationships via pbixray). `download.sh` and `README.md` included. (session cooling-current-0318)
- **xlsx Power Pivot capability matrix documented**: `XLSX_ADAPTER_GUIDE.md` updated with three-tier extraction strategy (XMLA → pbixray → pivot cache), full capability table by format, `pbixray` optional-dependency guidance, `DataMashup`/Power Query non-support note. (session cooling-current-0318)

### Fixed
- **BACK-092: `reveal check` text output OOM on large directory trees** — `_check_files_text` now uses `_run_parallel_streaming` (ProcessPoolExecutor + `as_completed`) instead of `list(pool.map(...))`. Results are emitted as each future completes; at most `max_workers` (4) results are held in memory simultaneously. Prevents the scenario where `reveal check <large-dir>` buffered all worker results before printing any output.
- **BACK-093: `collect_files_to_check` expanded excluded dirs** — added `.pytest_cache`, `.tox`, `.eggs`, `env`, `.benchmarks`, `.deepeval`, `.mypy_cache`, `.ruff_cache`, `.cache`, `.hypothesis` to `excluded_dirs`; `*.egg-info` directories excluded via `endswith` check. Prevents walking virtualenv packages on projects with non-standard venv names.
- **BACK-094: `reveal health` file count guard + timeout** — `_check_code()` now counts supported files before spawning the `reveal check` subprocess. Returns exit 1 with an actionable message if count exceeds `_HEALTH_MAX_FILES` (5000). `timeout=120` added to `subprocess.run` to prevent indefinite hangs. Root cause of the original OOM: `health._check_code` used `capture_output=True` with no size guard, double-buffering all JSON output on large trees. 8 new tests.

---

## [0.64.0] - 2026-03-18 (sessions awakened-pegasus-0315, slate-spectrum-0315, lightning-shield-0315, emerald-shade-0315, wise-temple-0316, heating-blizzard-0316, ascending-journey-0316, spinning-observatory-0316, frost-matrix-0316, obsidian-prism-0316, warming-ice-0316, tempestuous-sunshine-0316, bojififo-0317, serene-mist-0317, galactic-quasar-0317, dowepeva-0317, timeless-launch-0317, zifaxo-0317, topaz-flash-0317, timeless-antimatter-0317, kuzujuwe-0317, rainbow-aurora-0317, copper-tint-0317, foggy-flood-0318)

### Added
- **BACK-083: `# noqa: uncalled` suppression + false-positive docs** — `find_uncalled` now honours `# noqa: uncalled` on a function's definition line (or its decorator line) to exclude known entry points from dead-code results. Checked via a line-window reader that handles decorator-first reporting. `CALLS_ADAPTER_GUIDE.md` gains a "Known False Positives" section documenting three patterns (framework `@tool` decorators, console script entry points, dispatch table functions) and a module-level call sites limitation. Stale FAQ entry about `?uncalled` corrected. 3 new tests. (session rainbow-aurora-0317)

### Fixed
- **`test_updates.py` test isolation** — `mcp_server.py` sets `REVEAL_NO_UPDATE_CHECK=1` at import time; when `test_mcp_server.py` runs first in the full suite it pollutes `os.environ` and causes 6 update tests to fail. Fix: `setup_method`/`teardown_method` in `TestCheckForUpdates` clear and restore the env var so each test runs in a clean state. (session rainbow-aurora-0317)

### Refactored
- **BACK-081/082: `_parse_xmla` (cx:64) and `_render_powerpivot` (cx:34) split** — `_parse_xmla` (111L) broken into `_xmla_decode_root`, `_parse_xmla_tables`, `_parse_xmla_measures`, `_parse_xmla_dim_id_map`, `_parse_xmla_end`, `_parse_xmla_relationships`; orchestrator is now ~15 lines. `_render_powerpivot` (106L) broken into `_render_powerpivot_{tables,schema,measures,dax,relationships}` with a dispatch dict; dispatcher is ~25 lines. No behavior change. Helpers are now directly callable for the planned `?powerpivot=check` mode. (session kuzujuwe-0317)

### Added
- **BACK-078: OCSP URL availability in `--advanced`** — `CertificateInfo` gains `ocsp_url: Optional[str]` extracted from the AIA extension via the `cryptography` library. `_check_ocsp_availability()` added to `_run_advanced_checks`; emits an `info`-level finding when the OCSP URL is present (not a failure). Let's Encrypt ECDSA certs get a specific note that OCSP stapling was removed in 2024 and the field may be absent. 4 new tests. (session topaz-flash-0317)

### Fixed
- **BACK-077: `--validate-nginx` KeyError crash** — `render_check()` had no routing branch for the `ssl_nginx_validation` result type, falling through to the single-host path that expected a `result['host']` key. Added the missing branch. Also removed a duplicate `@staticmethod` decorator. 3 new tests. (session topaz-flash-0317)
- **MCP: update-check stdout injection** — `check_for_updates()` prints to stdout; since `_capture()` redirects `sys.stdout` before invoking reveal functions, update notices were appearing at the top of every tool response. Fix: `os.environ.setdefault('REVEAL_NO_UPDATE_CHECK', '1')` at module import time. 2 new tests. (session topaz-flash-0317)
- **MCP: stderr swallowed on tool errors** — `_capture()` only redirected stdout. Errors written to stderr before `sys.exit(1)` were silently dropped; MCP clients received only `[reveal exited with code 1]` with no context. Now captures stderr and includes it in the response (appended to stdout, or as a `[stderr: …]` prefix when stdout is empty). 6 new tests. (session topaz-flash-0317)

### Added
- **`?powerpivot=relationships`** — new query mode extracts the full relationship graph from the SSAS ASSL model. Parses `Relationship` elements, resolves dimension GUIDs to table names, extracts join columns from `Attributes/Attribute/AttributeID`, shows cardinality (Many/One) per end. Output grouped by from-table. Gracefully reports "not available" when XMLA is absent (pivotCache fallback). 11 new unit tests + 3 integration tests (113 total). (session zifaxo-0317)

### Fixed
- **Power Pivot DAX regex handles tableless `CREATE MEASURE` format** — the original regex required `[Database].'Table'[Name]` syntax (Contoso tutorial era) but real-world files emit `'Table'[Name]` without the database prefix. Made `[Database].` optional with `(?:\[[^\]]+\]\.)?`. (session zifaxo-0317)
- **Power Pivot detection extended to external SSAS/OLAP workbooks** — files connected to an external SSAS cube have no embedded model path but do have `xl/pivotCache/` entries with `cacheHierarchies`. `_detect_powerpivot` now recognises these via a sentinel `'xl/pivotCache/'` return value so the banner and `?powerpivot=` modes fire correctly. (session zifaxo-0317)

### Added
- **Power Pivot model extraction for `xlsx://`** — `reveal xlsx:///file.xlsx` now detects Power Pivot workbooks and shows a banner listing table names. Four new query modes: `?powerpivot=tables` (table names + column counts), `?powerpivot=schema` (full table + column listing + measure names), `?powerpivot=measures` (measure names + owning table), `?powerpivot=dax` (measure names + full DAX expressions). Pure stdlib — no new dependencies. Handles Excel 2010 (`xl/customData/item1.data`), Excel 2013+ (`xl/model/item.data`), and modern Power BI exports (pivotCache fallback when XMLA absent). XMLA items are UTF-16 XML with a `<Gemini><CustomContent><![CDATA[...]]>` wrapper containing full SSAS ASSL — tables extracted from `Dimension`/`Attributes`, DAX from `MdxScript/Command/Text`. 44 new tests. Design doc: `internal-docs/planning/POWERPIVOT_SUPPORT.md`. (sessions diabolic-quake-0317 design, timeless-launch-0317 implementation)

### Added
- **`reveal deps` — dependency health dashboard** — new subcommand wraps `imports://` to surface dependency health in one pass: summary (file count, import count, third-party package count, stdlib package count), health line (✅ no circular deps / ❌ N circular dep(s) · ⚠️ N unused import(s)), top third-party packages by usage count, circular dependency cycles with relative paths and `→` chain notation, unused imports with file:line, top importers (files with most dependencies) with bar chart. Self-imports correctly classified as internal via `_local_package_names()` (scans own dir name + subdirs with `__init__.py`). Flags: `--no-unused`, `--no-circular`, `--top N`, `--format json`. Exits 1 on circular deps or unused imports (CI-friendly). 59 new tests. (session dowepeva-0317)
- **`reveal overview` — one-glance codebase dashboard** — new subcommand synthesises four sources into a single human-readable snapshot: codebase stats (files, lines, functions, classes from `stats://`), language breakdown (file count + % bar from extension analysis), quality pulse (avg score, hotspot count with ✅/⚠️/❌ icon), top quality hotspots with `→ reveal <file>` hints, top complex functions (`ast://` query) with relative paths, and recent git commits with age labels. `--no-git` skips the git section; `--top N` controls item count per section; `--format json` outputs machine-readable dict. 71 new tests. (session dowepeva-0317)

### Added
- **`reveal-mcp` — MCP server with 5 tools** — `reveal.mcp_server` exposes reveal's full capabilities via Model Context Protocol for Claude Code, Cursor, Windsurf, and any MCP-compatible agent. Tools: `reveal_structure` (dir tree or file outline), `reveal_element` (extract one function/class), `reveal_query` (full URI adapter access: ast://, calls://, ssl://, etc.), `reveal_pack` (token-budgeted PR context snapshot), `reveal_check` (quality check). Uses `FastMCP` with `@tool` decorators; routes through reveal's internal APIs (no subprocess). Thread-safe stdout capture with `threading.Lock()`. `reveal-mcp` console script in `pyproject.toml`; `mcp` optional dep in `[mcp]` extra. Claude Code config: `{"mcpServers": {"reveal": {"command": "reveal-mcp"}}}`. Setup guide: `reveal/docs/MCP_SETUP.md`. 27 new tests. (session galactic-quasar-0317)
- **`pack --content` tiered emission** — `--content` now applies three tiers based on file priority and change status: changed files → full raw file content (see exactly what changed); non-changed priority≥2.0 → reveal structure (function signatures, imports); non-changed priority<2.0 → name-only listing (preserves token budget). JSON mode: `content` field replaces `structure`; `content_type` field added (`'full'`/`'structure'`/`'name_only'`). New `_get_file_raw_content(file_path, max_lines=500)` helper with configurable truncation. 11 new tests. (session galactic-quasar-0317)
- **`CI_RECIPES.md`** — ready-to-paste GitHub Actions and GitLab CI YAML: PR quality gate (`reveal review`), complexity delta gate (fails on delta > 5), hotspot tracking, quality metrics artifact, dead code check, SSL certificate health check (weekly scheduled). Includes Makefile targets and exit code table. Linked from README and docs INDEX. (session galactic-quasar-0317)
- **`CLAUDE.md.template`** — drop-in CLAUDE.md addition for any project. Instructs Claude to use reveal instead of cat/grep, enforce progressive disclosure, and use `reveal pack` for PR context. (session galactic-quasar-0317)

### Added
- **`ARCHITECTURE.md`** — single end-to-end architecture document covering: system overview (file vs URI path), URI routing (detection, parsing, adapter registry), adapter lifecycle (constructor conventions, `get_structure`/`get_element`/`get_schema`), Output Contract v1.0/1.1, query parameter pipeline (`parse_query_params`, operators, budget limits), help system tiers (human, agent, schema discovery), subcommand orchestration model (check, review, health, pack, hotspots, dev), renderer layer (dispatch, format flags, field selection), and adapter checklist with quality tier targets. Linked from `docs/INDEX.md`. (session serene-mist-0317)
- **`help://quick` decision tree** — `reveal help://quick` now includes a "What do you want to do?" section with 10 task-oriented entries mapping user intent to the right adapter: code structure → `ast://`, callers/dead code → `calls://`, import health → `imports://`, file comparison → `diff://`, SSL → `ssl://`, full server audit → `cpanel://`, nginx → `nginx://`, DNS/email → `domain://`, database → `sqlite://`/`mysql://`, session history → `claude://`. Each entry includes a ready-to-run example command. `decision_tree` field added to `help_quick` output type; renderer updated to display it. (session serene-mist-0317)
- **`reveal --discover` — full adapter registry as JSON** — new flag dumps all 22 registered adapters in a single JSON document: `reveal_version`, `adapter_count`, and per-adapter `description`, `uri_syntax`, `output_types`, `query_params`, `cli_flags`, `supports_batch`, `supports_advanced`, `example_queries`, `notes`. Designed for programmatic discovery by agents, scripts, and future UIs — replaces per-adapter probing with a single cap-matrix query. Adapters without `get_schema()` emit safe defaults. 6 new tests. (session serene-mist-0317)

### Fixed
- **`sqlite://` error handling** — adapter had zero `try/except` blocks despite being a database adapter. `_get_connection()` now catches `sqlite3.DatabaseError` (corrupt/encrypted file) and `sqlite3.OperationalError` (locked, permissions) and raises descriptive `IOError`/`PermissionError`. Added explicit `os.access()` read check before attempting to open. `_execute_query()` wraps cursor execution with the same two exception classes. `_get_pragma_info()` replaces `assert` with `IOError` on null PRAGMA results. `get_structure()` replaces bare `assert` with explicit `ValueError`. `get_element()` adds missing output contract fields (`contract_version`, `source`, `source_type`) to return dict. 4 new error-handling tests added. (session serene-mist-0317)
- **`claude://` schema missing `claude_chain` output type** — `_SCHEMA_OUTPUT_TYPES` was missing the `claude_chain` type returned by `_get_chain()` (the `/chain` element). Added entry with `session`, `chain`, `chain_length`, and `sessions_dir` fields. (session serene-mist-0317)

### Added
- **Output contract conformance test suite** — `tests/test_output_contract_compliance.py`: 30 tests verifying all locally-testable adapters (14 of 22) satisfy Output Contract v1.0 required fields (`contract_version`, `type`, `source`, `source_type`) and that the output `type` appears in the adapter's declared schema `output_types`. 5 network adapters explicitly skipped with documented skip reason. Also fixed 4 schema/output mismatches found during the scan: `diff://` schema said `'diff'` but adapter returns `'diff_comparison'`; `imports://` schema missing default `'imports'` output type; `nginx://` overview missing contract fields; `claude://` schema missing `claude_session_list` and `claude_file_sessions` types. Total: 6,310 passing, 6 skipped. (session bojififo-0317)
- **`reveal pack --content` — agent-consumable structure output** — new flag emits reveal structure for each selected file after the manifest, replacing the file-list-only output with actual content. Uses reveal's own progressive-disclosure analysis (same as `reveal file.py`): imports, function signatures, class definitions. Changed files (via `--since`) are tagged with `◀ CHANGED`. Works with `--format json` too: adds a `content` list of `{file, changed, structure}` dicts. This closes the gap between "pack tells you which files matter" and "pack gives you the context you need". 14 new tests. (session tempestuous-sunshine-0316)
- **README agent-first rewrite** — tagline updated to "Reveal is how AI agents understand codebases without wasting tokens." Description updated with local-first positioning. `progressive disclosure` and `local-first` added as the first two bullets in What Makes It Different. Added scope table (Reveal does/doesn't). Adapter table: `ast://` updated to 190+ languages, `help://` added. (session tempestuous-sunshine-0316)
- **`BENCHMARKS.md` — measured token reduction evidence** — 5 real scenarios on reveal's own codebase with exact measurements: structure output reduces tokens 3.9–33x vs cat/grep/manual methods. File understanding: 5,883→1,499 tokens (3.9x). Module structure: 4,128→275 tokens (15x). Call graph query: 560→84 tokens (6.7x). Dead code detection: 7,196→220 tokens (33x). Includes reproduction commands. Linked from README and docs INDEX. (session tempestuous-sunshine-0316)
- **`reveal pack --since <ref>` — git-aware context snapshots** — new `--since REF` flag boosts git-changed files to priority tier 0 (score=20, above entry points at 10) in `reveal pack`. Uses `git diff --name-only <ref>...HEAD` (triple-dot = since branch point). Changed files rendered in a dedicated "── Changed files (since REF) ──" section. Renderer header shows changed file count. Graceful degradation on non-git dirs or bad refs (stderr warning, pack continues without boost). `format=json` includes `since`, `changed_files_count` in meta and `changed` flag per file. 20 new tests. (session frost-matrix-0316)
- **BACK-076: Import alias resolution in `build_callers_index`** — `?uncalled` no longer false-positives functions called via an import alias. New `build_alias_map(file_path)` in `call_graph.py` maps each aliased import to its canonical name (`from utils import helper as h` → `{'h': 'helper'}`). `build_callers_index` calls it per file and indexes both the alias (`h`) and the definition name (`helper`) for every aliased call. `find_callers('helper')` now finds callers that use the alias; `find_uncalled` no longer flags `helper` as dead code. Stale "Import aliases produce false positives" limitation in `CALLS_ADAPTER_GUIDE.md` removed. 10 new tests. (session warming-ice-0316)
- **BACK-074: `claude://sessions/?search=term` — cross-session content search** — the core feature (BACK-029's `grep_files` + `_search_sessions`) was already implemented but undocumented, unlimted, and not in the schema. This session closes the loop: (1) `post_process` now applies default 20-result limit to `claude_cross_session_search` results; `--all` skips limit, `--head N` overrides; (2) `claude_cross_session_search` output type added to schema with field docs; (3) cross-session search examples added to `_SCHEMA_EXAMPLE_QUERIES` and `_get_help_examples`; (4) `_SCHEMA_NOTES` gains cross-session note; (5) `CLAUDE_ADAPTER_GUIDE` stale "not implemented" limitation and error section replaced with working documentation and examples. 12 new tests. (session obsidian-prism-0316)
- **BACK-073: `diff://` per-function complexity delta** — every entry in `.diff.functions` now carries top-level `complexity_before`, `complexity_after`, and `complexity_delta` fields. Added functions: `complexity_before=null`, `complexity_delta=complexity_after`. Removed: `complexity_after=null`, `complexity_delta=-complexity_before` (or null if no complexity data). Modified: straight arithmetic delta. Enables `jq '.diff.functions[] | select(.complexity_delta > 5)'` CI gate pattern. `reveal review main..feature` surfaces complexity spikes (delta > 5) as a named section. 21 new tests. (session obsidian-prism-0316)
- **BACK-072: `reveal pack --since <ref>` — git-aware context snapshots** — new `--since REF` flag boosts git-changed files to priority tier 0 (score=20, above entry points at 10) in `reveal pack`. Uses `git diff --name-only <ref>...HEAD` (triple-dot = since branch point). Changed files rendered in a dedicated "── Changed files (since REF) ──" section. Renderer header shows changed file count. Graceful degradation on non-git dirs or bad refs (stderr warning, pack continues without boost). `format=json` includes `since`, `changed_files_count` in meta and `changed` flag per file. 20 new tests. (session frost-matrix-0316)
- **BACK-071: `calls://src/?uncalled` — dead code detection** — new query param surfaces all functions/methods defined but never called (in-degree = 0 in the callers index). Automatically excludes `__dunder__` methods and `@property/@classmethod/@staticmethod` decorated functions (called implicitly). Private functions (`_` prefix) included but flagged. `?type=function` skips class methods (detected via `(self`/`(cls` signature prefix); `?top=N` caps results sorted by file mtime descending. `format=json` works. Method detection normalises both explicit `category='methods'` and Python's common case where everything is `'functions'` but signature reveals class membership. 20 new tests. (session frost-matrix-0316)

### Fixed
- **BACK-070: `calls://path:element` colon shorthand not supported** — `calls://src/file.py:my_fn` was treated as a literal path (including `:my_fn`), target was empty, renderer showed `Callers of: ?` with no error. `CallsAdapter.__init__` now splits on the last `:` when the portion before it is an existing path and the portion after has no slashes; sets `target=` in query_params. Also fixed: when target is missing the renderer now emits the error message to stderr instead of printing `Callers of: ?`. 7 new tests. (session ascending-journey-0316)
- **BACK-069: `reveal check dir/ --severity` ignored filter in recursive mode** — `handle_recursive_check` extracted `select`/`ignore` from `args` but not `severity`. `_apply_severity_filter()` helper added (with `_SEVERITY_ORDER` constant); `_check_files_text` and `_check_files_json` each gain a `severity=None` parameter that gates detections post-collection. `handle_recursive_check` now reads `getattr(args, 'severity', None)` and passes it through. Case-insensitive comparison; unknown level passes all. 10 new tests. (session ascending-journey-0316)
- **BACK-051: `domain://` missing email DNS layer** — `check_mx_records()`, `check_spf_record()`, `check_dmarc_record()`, and `check_email_dns()` aggregator added to `dns.py`. New `/mail` element (`reveal domain://DOMAIN/mail`) shows MX/SPF/DMARC status with record details. `check()` now includes all three email checks. Renderer added. 17 new tests. (session emerald-shade-0315)
- **BACK-053: `domain://` no HTTP redirect chain inspection** — `_check_http_to_https_redirect()` added as a named `http_redirect` check in `check()` output. New `/http` element (`reveal domain://DOMAIN/http`) shows full redirect chains for HTTP and HTTPS with `redirects_to_https` flag. Renderer added. 8 new tests. (session emerald-shade-0315)
- **BACK-042: `reveal check` severity filtering** — `--severity LEVEL` flag added (low, medium, high, critical). Filters detections post-check to only show issues at or above the specified level. Case-insensitive; invalid value emits stderr warning and shows all. 9 new tests. (session emerald-shade-0315)
- **BACK-056: `cpanel://USER/ssl` no disk-vs-live cert cross-reference** — `--check-live` flag added. For each non-ok disk cert, fetches live cert via `check_ssl_health()` and merges `live_status/live_days_until_expiry/live_not_after` into the cert entry. Renderer shows `↳ live: Nd (date)` line below each non-ok row. Surfaces CDN/edge renewals where disk cert is stale. 11 new tests. (session emerald-shade-0315)
- **BACK-057: `autossl://error-codes` error code taxonomy** — `reveal autossl://error-codes` returns a reference for all known AutoSSL error codes. OpenSSL defect codes (DEPTH_ZERO_SELF_SIGNED_CERT, CERT_HAS_EXPIRED, etc.) and DCV impediment codes (TOTAL_DCV_FAILURE, etc.) — each with meaning, cause, and fix steps. `_get_error_code_taxonomy()` + `_render_error_codes()` renderer. 6 new tests. (session emerald-shade-0315)
- **BACK-043: `help://quick` short help entry** — `reveal help://quick` returns a top-10 command cheat-sheet (file analysis, ssl://, domain://, nginx://, cpanel://, batch pipeline). `_get_quick_help()` returns `help_quick` type; `_render_help_quick()` formats aligned command table with next-steps. 6 new tests. (session emerald-shade-0315)
- **BACK-055: `--validate-nginx-acme --verbose` shows matched config lines** — `_handle_validate_nginx_acme()` now respects `args.verbose`. When `--verbose` is set, prints the matched `location` block (the matched line + up to 3 following lines, with line numbers) below each result row. 3 new tests. (session emerald-shade-0315)
- **BACK-054: `nginx://` overview doesn't flag `.bak`/`.tmp` files** — `_find_artifact_files()` scans config dirs (top-level + one subdir level) for files matching backup/temp suffixes that nginx silently ignores. `_get_overview()` includes them as `artifact_files[]`; renderer prints a ⚠️  section; `next_steps` gains a housekeeping hint. 6 new tests. (session emerald-shade-0315)
- **BACK-049: `ssl://` `--advanced` shows "Signature algorithm: Unknown"** — `ssl.getpeercert()` dict never includes `signatureAlgorithm`. `_get_peer_cert()` now also fetches the binary form and extracts the hash algorithm via the `cryptography` library, merging it into the returned dict. `_parse_binary_cert()` also includes `signatureAlgorithm`. 3 new tests. (session emerald-shade-0315)
- **BACK-050: `--check` deprecation hint stdout pollution** — Already fixed pre-session. `routing.py:723` confirmed to write deprecation hint to `sys.stderr`. No code change required; confirmed resolved. (session emerald-shade-0315)

### Added
- **BACK-041: `claude://session/<id>/chain` — session continuation chain traversal** — Traverses the continuation chain by reading `continuing_from:` YAML frontmatter from session README files. Configure with `REVEAL_SESSIONS_DIR` env var pointing to the directory containing per-session subdirs (each with `README*.md`). Returns `chain[]` with session name, date, badge, tests start/end, and commits per step. Renderer displays aligned chain with `[HEAD]`/`[N]` labels, `↓ continues from` arrows, and a hint if `REVEAL_SESSIONS_DIR` is not set. Cycle-safe (50-session limit). 22 new tests. (session wise-temple-0316)
- **BACK-052: `domain://DOMAIN/ns-audit` — NS authority cross-check** — Queries each registered NS server directly for the domain's NS records and compares results. Detects orphaned NS entries (listed by registrar but not in any auth NS response), unreachable servers, and inconsistent cross-server NS sets. Real-world motivation: sociamonials.com had `dns1.web-hosting.com` listed as NS but not authoritative — required 4 manual `dig @nameserver` calls to find. `check_ns_authority()` in `dns.py`; `_render_domain_ns_audit()` renderer with ✅/⚠️/❌ icons, per-server IP and NS-returned, orphaned section. 11 new tests. (session wise-temple-0316)

### Documentation
- **Doc audit (spinning-observatory-0316): 14 discrepancies found and fixed across 9 files** — Systematic audit of all docs vs code. Fixed: `calls://` help and schema missing `?rank=callers`, `?top=N`, and colon shorthand; `AGENT_HELP.md` stale v0.51.0 version and adapter count 21→22 (missing calls:// and xlsx://); `GIT_ADAPTER_GUIDE.md` + git schema missing `?ref=` query param; `AST_ADAPTER_GUIDE.md` stale version; `SUBCOMMANDS_GUIDE.md` wrong default budget (4000→2000), wrong priority algorithm, missing `reveal hotspots` section, missing `--select` for review/health; `RECIPES.md` missing colon shorthand and `?rank=callers` examples; `QUERY_PARAMETER_REFERENCE.md` missing calls:// section and severely incomplete ast:// section (1 of 10+ params); `SSL_ADAPTER_GUIDE.md` documenting non-existent `--warn-days/--critical-days` CLI flags; pack JSON field `.selected`→`.files`. All 6,184 tests pass. (session spinning-observatory-0316)
- **BACK-058: `--extract domains | --stdin --batch` pipeline undocumented** — Added "Extract-then-batch pipeline" recipe section to `RECIPES.md`. Added "Pattern 0: Extract-then-Batch Pipeline" to `AGENT_HELP.md`. Documents `--check-live`, `--only-failures`, `--canonical-only` flags with cPanel + nginx + batch-SSL workflow examples. (session emerald-shade-0315)
- **BACK-048: `autossl://latest` 78KB unfiltered output** — Three new filters: `--only-failures` removes ok domains and users with no failures; `--summary` strips per-user detail and returns run-level counts only; `--user=NAME` filters to a single user. `_apply_autossl_filters()` added; `_build_adapter_kwargs` now maps `summary` and `user` kwargs for adapters that support them. `--user` CLI flag added. 8 new tests. (session lightning-shield-0315)
- **BACK-060: `--stdin --batch --summary` emitted per-URI lines instead of summary only** — `--summary` was wired in the SSL-specific batch path (`_render_ssl_batch_results`) but silently ignored by the generic batch path (`_render_batch_results`). With 800+ URIs, the process emitted 800+ per-URI lines instead of the 6-line summary the user requested. `_render_batch_text_output` now accepts `summary_only=True`; JSON format also drops the `results[]` array to avoid 100MB+ serialization. 5 new tests. (session lightning-shield-0315)
- **BACK-045: `cpanel://` domain count inflated by filesystem artifacts** — `.cache`/`.yaml`/`.json`/`.lock`/`.tmp`/`.db`/`.bak`/`.log` files in `/var/cpanel/userdata/USER/` were counted as domains, inflating SSL "missing" counts 300–400×. `_list_user_domains()` now filters these extensions. 2 new tests. (session lightning-shield-0315)
- **BACK-046: `nginx://` missed `conf.d/users/` on cPanel/WHM servers** — `_iter_nginx_configs()` now recurses one level into subdirectories, finding `conf.d/users/*.conf` configs that cPanel writes there. Backup files in subdirs are also excluded. 3 new tests. (session lightning-shield-0315)
- **BACK-059: `--extract domains` 5× URI expansion** — `extract_ssl_domains()` returned all `server_name` aliases (www/mail/rfr.bz variants), producing ~807 URIs for ~163 real vhosts. New `--canonical-only` flag returns one URI per vhost (the first valid `server_name`). `extract_ssl_domains(canonical_only=True)` added to the analyzer; flag wired through CLI parser and `file_handler`. 5 new tests. (session lightning-shield-0315)
- **BACK-047: `domain://` false NS failures on subdomains** — `check_nameserver_response` and `check_dns_propagation` now return pass/skipped for domains with 3+ labels (e.g. `stg.rfr.bz`). Subdomains have no NS records of their own; querying NS for them produces spurious CRITICAL failures. `_is_subdomain()` helper added to `dns.py`. 10 new tests. (session slate-spectrum-0315)
- **BACK-061: `--expiring-within N` had no effect on exit code** — Flag was render-only; now routed to `warn_days` in `SSLAdapter.check()` via `_build_check_kwargs`. `--expiring-within=60` on a cert with 47d to expiry now correctly exits 1 (WARNING). Accepts `30` or `30d` formats. 4 new tests. (session slate-spectrum-0315)
- **BACK-062: `@file` not batch-equivalent to `--stdin --batch`** — `_handle_at_file` now routes through `handle_stdin_mode` (via `io.StringIO`) when `--batch` or `--check` is active, giving identical aggregation behavior. `@file --batch` now shows `BATCH CHECK RESULTS` header with Total URIs count. 3 new tests. (session slate-spectrum-0315)


- **BACK-068: `reveal check --severity` not recognized** — `--severity LEVEL` flag was added to the main parser (`reveal file.py --check --severity high`) in BACK-042 but never added to the `reveal check` subcommand parser in `commands/check.py`. `add_arguments()` now includes `--severity`. 3 new tests. (session heating-blizzard-0316)
- **BACK-066: `git://` empty history with no hint** — `_render_ref_structure` now shows `(no commits matched filter — use '~=' for substring match)` when history is empty and a filter was applied, or `(no commits)` when no filter was active. `filter_applied: bool(query_filters)` added to `get_ref_structure()` result dict. 4 new tests. (session heating-blizzard-0316)
- **BACK-067: `git://` `?ref=` query param treated as filter** — `?type=history&ref=v0.63.0` previously treated `ref` as a commit-dict filter field (which doesn't exist), producing empty history. `_separate_query_parameters()` now recognizes `ref` as an operational param and sets `self.ref` from it, identical to the `@ref` URI syntax. 2 new tests. (session heating-blizzard-0316)
- **BUG: `git://` `?type=blame&element=` crash** — lambda in `get_structure` passed 1 arg but `_apply_element_blame_filter` called it with 3. Fixed lambda arity; semantic blame now works correctly.
- **BUG: `ast://` multi-file colon syntax silently returns 0 results** — `ast://file1.py:file2.py` now raises a clear `ValueError` with the two separate commands to run. Detection by extension pattern, not just path existence.
- **`imports://` `?violations` misleading "0 violations"** — when `.reveal.yaml` config is missing, output now shows `Layer Violations: NOT CONFIGURED` with explanation instead of `Layer Violations: 0`.
- **`diff://` absolute path `::` separator** — `::` now accepted as explicit separator for absolute paths. Malformed right side emits actionable error with suggested fix.
- **`ast://` auto-cap rendered wrong counts** — renderer printed `total_results` (pre-cap) while iterating `results` (post-cap). Now shows `N of M — add filters or use ?limit=N` when auto-capped; cap warning wired into text renderer (was JSON-only).
- **`markdown://` type filter hint was invisible** — `hints[]` added to response but renderer never read it. Now printed after result list.
- **`markdown://` low match rate hint** — when match rate < 5%, prints front matter explanation.
- **File not found error missing cwd** — `_validate_path_exists` now prints `Running from <cwd>` and the resolved absolute path to try.

### Changed
- **`git://` help docs** — `~=` documented as substring regex with word-boundary tip. `?type=history` syntax noted as correct approach for file-scoped history.

---

## [0.63.0] - 2026-03-15 (sessions casuyi-0314, mint-stone-0315, viral-warmonger-0315, wonipuhi-0315, awakened-anvil-0315, kumewu-0315)

### Added
- **`calls://` `?rank=callers`** — coupling metrics via in-degree ranking. `calls://src/?rank=callers&top=10` ranks all callable symbols by how many unique callers reference them. Zero new infrastructure — uses the already-built callers index. `?top=N` controls result count (default 10, max 100). `?builtins=true` includes builtins in ranking. `rank_by_callers()` added to `calls/index.py`; `_render_ranking_text()` added to renderer; `### rank` section added to `CALLS_ADAPTER_GUIDE.md`. 13 new tests. (session casuyi-0314)
- **`ast://` `?builtins=true/false`** — builtin filtering for call graph output. `ast://?show=calls` and element-level `calls:` field now filter Python builtins by default (consistent with `calls://?callees=X` introduced in chosen-flame-0314). Routes through same `PYTHON_BUILTINS` frozenset and `.split('.')[-1]` pattern from `calls/index.py`. `extract_builtins_param()` in `ast/queries.py` mirrors `extract_show_param()`. `?builtins=true` restores raw output. 12 new tests. (session casuyi-0314)
- **`reveal hotspots <path>`** — new subcommand for file-level quality hotspots + high-complexity functions. `--top N`, `--min-complexity N`, `--functions-only`, `--files-only`, `--format json`. Exit 1 on critical findings (quality < 70 or complexity > 20) for CI use. (session viral-warmonger-0315)
- **I006 rule** — detects imports inside function/method bodies (Python-only). Uses function `line`/`line_end` ranges to classify inline imports. Exceptions: `__future__`, `TYPE_CHECKING` blocks, `# noqa: I006`, and functions with `lazy`/`import` in their name (intentional lazy-load pattern). (session viral-warmonger-0315)
- **`claude://` cross-session file tracking** (BACK-040) — track which files appeared in prior sessions; `?files` view. (session mint-stone-0315)
- **`claude://` cross-session content search** (BACK-029) — `grep_files` utility; search across session transcripts. (session mint-stone-0315)
- **`claude://` session recovery** (BACK-028) — `?tail=N`, `?last`, `message/-1` for fast session re-entry. (session mint-stone-0315)
- **`claude://` richer session overview + workflow run collapse** (BACK-031/032) — grouped session index, collapsed tool output in list view. (session mint-stone-0315)
- **`markdown://` cross-file link graph** (BACK-039) — tracks outbound links across a doc collection; `?links` view. (session mint-stone-0315)
- **`markdown://` `?aggregate=<field>`** (BACK-033) — frontmatter frequency table for any field (e.g. `?aggregate=type`). (session mint-stone-0315)

### Fixed
- **I005 silent bug** — `_normalize_import()` checked `statement`/`source` keys but Python structure dicts use `content`; rule returned zero detections for all Python files. Fixed priority to `content` → `statement` → `source`. (session viral-warmonger-0315)
- **I006 `# noqa` detection** — now reads raw source lines (analyzers strip trailing comments from their parsed `content` field), so `# noqa: I006` suppressions are correctly honoured. (session kumewu-0315)
- **`json://` `?flatten` type mismatch** (BACK-038) — fixed coercion error; added `?flatten&data-only` flag. (session mint-stone-0315)
- **`claude://` title extraction, analytics renderer, duration format** (BACK-027/030/034). (session mint-stone-0315)
- **`ast://` builtin filtering consistent with `calls://`** — `show=calls` and element-level `calls:` field now filter builtins by default, matching the `calls://?callees=X` behaviour introduced in v0.62.0. (session casuyi-0314)

### Refactored
- **Query parser unification** (BACK-024) — replaced 4 hand-rolled `split('&') + split('=', 1)` loops with `parse_query_params()` from `utils/query.py`: `calls/adapter.py`, `git/adapter.py` (2 locations), `imports.py`, `cpanel/adapter.py`. `calls` adapter now uses `coerce=True` so `depth` and `builtins` arrive as native `int`/`bool`. Net -45 lines. (session casuyi-0314)
- **`file_handler.py` import hygiene** — hoisted 5 inline imports to module top; circular-avoidance imports annotated with `# noqa: I006`. (session kumewu-0315)

### Documentation
- **Nginx guides merged** — `NGINX_ADAPTER_GUIDE.md` + `NGINX_ANALYZER_GUIDE.md` → `NGINX_GUIDE.md`. (session awakened-anvil-0315)
- **Subcommand stubs merged** — `DEV_GUIDE.md`, `REVIEW_GUIDE.md`, `PACK_GUIDE.md`, `HEALTH_GUIDE.md` → `SUBCOMMANDS_GUIDE.md`. `help://dev`, `//review`, `//health`, `//pack` all route to new file. (session awakened-anvil-0315)
- **`UNIFIED_OPERATOR_REFERENCE.md` retired** — 670-line dev log with broken `See Also` links; content fully covered by `QUERY_SYNTAX_GUIDE.md`. (session awakened-anvil-0315)
- **Hotspot command references updated** — 10× `reveal stats://./src --hotspots` → `reveal hotspots ./src` across `CODEBASE_REVIEW.md`, `STATS_ADAPTER_GUIDE.md`, `RECIPES.md`. (session awakened-anvil-0315)

### Stats
- 4,949 → 6,009 tests (+1,060); includes new `test_I005.py`, `test_I006.py`, `test_cli_hotspots.py`

---

## [0.62.0] - 2026-03-14 (sessions destined-altar-0313, risen-armor-0314, turbulent-frost-0314, chosen-flame-0314, nurosu-0314)

### Added (session chosen-flame-0314)
- **`calls://` `?callees=X` builtin filtering** — Python builtins (`len`, `str`, `sorted`, `ValueError`, etc.) are now hidden from callees output by default, leaving only project-defined and stdlib calls. Uses `PYTHON_BUILTINS` frozenset derived from `dir(builtins)` at import time (stays in sync across Python versions). `?builtins=true` restores the full raw list. Dotted stdlib calls like `os.path.join` are unaffected (bare name `join` is not a builtin). Footer in text output shows `(N builtin(s) hidden — use ?builtins=true to include)` when any are filtered. `_builtins_hidden` count added to result dict. (session chosen-flame-0314)

### Added (session turbulent-frost-0314)
- **`calls://` `?callees=X` forward lookup** — symmetric to the existing `?target=X` (reverse/callers). `calls://src/?callees=validate_item` scans all definitions of `validate_item` across the project and shows what it calls, with per-file breakdown for functions defined in multiple files. New `find_callees()` in `index.py`; new `_render_callees_text()` in renderer; `?callees=` also supports `?format=json`. If both `callees=` and `target=` are given, `callees=` takes precedence. (session turbulent-frost-0314)

### Fixed (session turbulent-frost-0314)
- **`calls://` text renderer showed basename only** — `_render_text` was using `Path(rec['file']).name` (basename), which is ambiguous when files with the same name exist in different directories. Now uses `rec['file']` directly, which is already project-relative. Regression test added. (session turbulent-frost-0314)
- **`calls` adapter missing from schema contract tests** — `calls` was never added to `expected_schemes` in `test_adapter_contracts.py` after Phase 3 shipped, so the schema contract was never enforced. Fixed: added `calls` to `expected_schemes` and imported `CallsAdapter` for registration. (session turbulent-frost-0314)
- **`calls` schema missing `output_types`, `example_queries`, `notes`** — the adapter contract requires all three. Added `calls_query` and `calls_callees` output types with full JSON schema + example, 5 `example_queries` with `output_type` references, and 5 notes. (session turbulent-frost-0314)

### Documentation (session turbulent-frost-0314)
- **`CALLS_ADAPTER_GUIDE.md`** — added `?callees=X` throughout: Quick Start, URI Syntax table, Query Parameters table + new `### callees` section, callees text output format example, Workflow 6 (forward lookup). Updated `ast://` vs `calls://` comparison table. Updated text output examples to show full relative paths (not basename). (session turbulent-frost-0314)
- **`AGENT_HELP.md`** — updated "Trace function call graph" task: added `?callees=` command + row in the scope comparison table. (session turbulent-frost-0314)
- **`ast/help.py`** — updated Trace Call Graph workflow to include `?callees=` step; updated notes to mention forward lookup. (session turbulent-frost-0314)

### Tests (session turbulent-frost-0314)
- **15 new tests** — `TestFindCallees` (5): callees found, total count, no match, multiple files same name, file+line in match. `TestCallsAdapterCallees` (5): type=calls_callees, matches content, callees takes precedence, missing-both-params error, json format stored. `TestCallsRendererCallees` (5): text shows target, no-match message, empty-calls message, json format, relative path in _render_text. Tests: 4,934 → 4,949. (session turbulent-frost-0314)

### Fixed (session risen-armor-0314)
- **`calls://` renderer crash on every query** — `CallsRenderer` used instance-method signature (`self, data, **kwargs`) but the routing layer calls renderers as class-level functions. This made every `calls://` query crash with `AttributeError: 'str' object has no attribute 'get'`. Converted to static-method pattern (no `self`), matching `ImportsRenderer` and all other adapters. 5 regression tests added. (session risen-armor-0314)
- **`calls://` `format=dot` in query string now works** — previously `?target=fn&format=dot` silently produced text output instead of Graphviz dot. `get_structure()` now stores `_query_format` in the result dict; the renderer applies it with precedence over the CLI `--format` flag. (session risen-armor-0314)
- **`show=calls` included imports in call graph output** — `_render_call_graph` now filters results to only `functions` and `methods` before rendering. Previously, import elements appeared with `(no calls or callers within this file)` which was noise. 5 renderer tests added. (session risen-armor-0314)

### Documentation (session risen-armor-0314)
- **`CALLS_ADAPTER_GUIDE.md`** — new full guide for `calls://` adapter: URI syntax, all 3 output formats (text, JSON, dot), 5 workflows (impact analysis, dead code, execution path tracing, architecture docs, refactoring verification), limitations, caching/performance, FAQ. (session risen-armor-0314)
- **`AST_ADAPTER_GUIDE.md`** — updated: fixed stale FAQ ("call graphs not supported" was wrong since Phase 1/2); added `calls`, `callee_of`, `show` to query params table; added full "Call Graph Analysis" section covering within-file queries, `show=calls` format, cross-file escalation, and JSON field docs; added Workflow 7 (Trace Function Call Graph). (session risen-armor-0314)
- **`AGENT_HELP.md`** — added "Task: Trace function call graph" section with both adapters, scope comparison table, JSON fields reference. (session risen-armor-0314)
- **`ast/help.py`** — added `calls`, `callee_of`, `show` to `_SCHEMA_QUERY_PARAMS`, filters, examples, workflows, notes, and see_also. `reveal help://ast` now surfaces all call graph capabilities. (session risen-armor-0314)

### Added (session destined-altar-0313)
- **Call graph Phase 3: cross-file resolution** — `resolve_callees()` in new `adapters/ast/call_graph.py` joins a function's `calls` list against the file's import symbol map, adding `resolved_file` + `resolved_name` to each entry that can be traced to a file on disk. The existing `calls: List[str]` field is unchanged (backward-compatible); resolved data appears in a new `resolved_calls` field in JSON output. Text renderer shows `db.insert (→ database.py::insert)` inline. (session destined-altar-0313)
- **`calls://` adapter** — new URI scheme for project-level cross-file callers queries. Builds a per-directory inverted callers index (callee → [(file, caller, line)]) cached by mtime fingerprint. Supports `?target=<name>` (direct callers), `?depth=N` (transitive BFS, capped at 5), `?format=dot` (Graphviz output). +25 tests. Tests: 4,899 → 4,924. (session destined-altar-0313)

---

## [0.61.0] - 2026-03-13 (sessions toxic-onslaught-0310, ethereal-leviathan-0310, psychic-frenzy-0310, mystical-sword-0311, kilonova-throne-0311, eternal-launch-0311, turbo-ultimatum-0311, pattering-wind-0311, fluorescent-dawn-0311, astral-observatory-0313, astral-comet-0313, platinum-gleam-0313, mountain-gale-0313, turbulent-hail-0313)

### Fixed (session turbulent-hail-0313)
- **`imports://` false positive: `__init__.py` re-exports flagged as unused** — `_should_skip_import` in `analyzers/imports/types.py` now skips all imports in `__init__.py` files unconditionally. These are re-export patterns (public API surface), never unused code. Regression test added. (session turbulent-hail-0313)
- **M102 false positive: dynamically-dispatched command modules flagged as orphaned** — `_extract_imports_regex` in `rules/maintainability/M102.py` now also scans for dotted string literals (`'pkg.sub.mod'` with 2+ dots) and adds them to the imports set. Catches `importlib.import_module()` calls and dispatch-table string entries. Also: rule plugin files named with the rule code convention (`[A-Z][0-9]+`, e.g. B001.py, E501.py) are now recognized as dynamic entry points and skipped. Regression test added. (session turbulent-hail-0313)
- **B006 false positive: try-then-try fallback pattern flagged as silent exception swallowing** — `_is_intentional_fallback` in `rules/bugs/B006.py` now recognizes when `except Exception: pass` is immediately followed by another `try` block — the multi-attempt fallback pattern. First try fails silently; second try is the alternative approach. Two regression tests added. (session turbulent-hail-0313)
- **B006 real issues fixed in 8 files** — Eliminated `except Exception: pass` + `return default` antipattern by moving the return into the except body (explicit intent): `cli/commands/review.py` (4 cases), `adapters/claude/adapter.py` (1). Used specific exception types where appropriate: `adapters/cpanel/adapter.py` (`OSError` for fcntl/socket), `rules/links/L001.py` (`OSError`), `rules/links/L003.py` (`OSError`). Added explanatory comments where broad catch is genuinely needed: `adapters/git/refs.py`, `adapters/ssl/adapter.py`, `cli/commands/health.py`, `rules/validation/V003.py`, `utils/updates.py`. B006 count: 16 → 0. (session turbulent-hail-0313)
- **`tree_view.py` unused `field` import** — `from dataclasses import dataclass, field` → `from dataclasses import dataclass` after `TreeViewOptions` refactor confirmed `field` was never used. (session turbulent-hail-0313)

### Changed (session turbulent-hail-0313)
- **`show_directory_tree` refactored from 11 params to `TreeViewOptions` dataclass** — `reveal/tree_view.py` now exposes `TreeViewOptions` dataclass collecting all 10 rendering options (depth, show_hidden, max_entries, fast, respect_gitignore, exclude_patterns, dir_limit, sort_by, sort_desc, include_extensions). `show_directory_tree` signature is now `(path, options=None, **kwargs)` — fully backwards-compatible via kwargs fallback. Internal `context` dict now pulls from `options`. (session turbulent-hail-0313)

### Tests (session turbulent-hail-0313)
- **4 new regression tests** — `test_init_py_imports_not_flagged_as_unused` (imports/types.py re-export skip); `test_dynamic_dispatch_string_not_flagged` (M102 string literal scanning); `test_try_then_try_fallback_not_flagged` (B006 multi-attempt pattern); `test_try_then_return_still_flagged` (B006 guard: single-try + return None is still a finding). Tests: 4,861 → 4,865. (session turbulent-hail-0313)

### Fixed (session mountain-gale-0313)
- **Bug: `full-audit` with `--dns-verified` could set `has_failures=True` for excluded domains** — `_get_full_audit_structure` computed `ssl_has_failures` from raw `certs[]`, which includes NXDOMAIN and elsewhere-pointing domains even when they're excluded from `summary`. With `--dns-verified`, a NXDOMAIN domain with an expired cert would trigger `has_failures=True` even though the summary showed no failures. Fix: use `ssl_data['summary']` to compute ssl failures, consistent with how the renderer already computed its icon. Exit code 2 and `.has_failures` in JSON now correctly reflect only domains that point here. (session mountain-gale-0313)

### Added (session mountain-gale-0313)
- **AGENT_HELP: `domain://` task section** — `domain://` (shipped v0.60.0) had no dedicated task entry. Added `Task: "Inspect domain health — DNS, registration, HTTP"` with all sub-views (`/dns`, `/ssl`, `/registrar`, `/whois`), `--check`, `--only-failures`, batch check pattern, and domain:// vs ssl:// decision table. (session mountain-gale-0313)

### Changed (session mountain-gale-0313)
- **`import struct/fcntl/array` moved to module top** in `cpanel/adapter.py` — were lazy-imported inside `_get_local_ips()` body; moved to module-level with other stdlib imports. No behavior change; stdlib modules have no import cost concern. (session mountain-gale-0313)
- **Module docstring updated** in `cpanel/adapter.py` — element list now includes `full-audit` (added platinum-gleam-0313 but not reflected in docstring). Also corrected `S2`/`N1` labels that were present as internal notes, not user-facing text. (session mountain-gale-0313)

### Tests (session mountain-gale-0313)
- **1 new regression test** — `test_full_audit_dns_verified_excluded_failures_do_not_set_has_failures`: two-domain setup (ok.com resolves here, gone.com NXDOMAIN + expired cert); asserts `has_failures=False` and `dns_excluded['expired']==1`. Regression guard for the `ssl_has_failures` bug. Tests: 4,860 → 4,861. (session mountain-gale-0313)

### Added (session platinum-gleam-0313)
- **`cpanel://user/full-audit` element** — composite audit composing ssl + acl-check + nginx ACME in one pass. `reveal cpanel://USERNAME/full-audit` calls `_get_ssl_structure`, `_get_acl_structure`, and (if `/etc/nginx/conf.d/users/USERNAME.conf` exists) the nginx analyzer's ACME chain check. Returns `type: 'cpanel_full_audit'` with `ssl`, `acl`, and `nginx` sub-results plus a top-level `has_failures` flag. Renderer shows per-section summaries and drills into failures; exits 2 on any failure in any component (JSON output also exits 2). Overview `next_steps` updated to surface `full-audit` first. (session platinum-gleam-0313)
- **`cpanel://user/ssl?domain_type=<type>` URI query filtering** — `_parse_connection_string` now handles `?key=value` query params on the element component. `?domain_type=main_domain|addon|subdomain|parked` filters the cert list before sorting/summary. `domain_type_filter` included in result dict. Composable with `--only-failures` and `--dns-verified`. (session platinum-gleam-0313)
- **`--only-failures` for `cpanel://user/acl-check`** — was wired for ssl and nginx, silently ignored for acl. Now flows: `get_structure(only_failures=)` → `_get_acl_structure(only_failures=)` → result dict → `_render_acl`. Renderer hides ok domains; prints `✅ No ACL failures found.` when all pass. `only_failures` stored in result dict for JSON consumers. (session platinum-gleam-0313)
- **U6 follow-on: IP-match verification for `--dns-verified`** — extends existing DNS-verified mode to also detect "resolves but to a different server." New helpers: `_dns_resolve_ips(domain)` (returns list of IPv4s; empty = NXDOMAIN) and `_get_local_ips()` (enumerates non-loopback IPs via `fcntl.ioctl(SIOCGIFCONF)` with hostname fallback; stdlib-only, no new dependency). Per-cert: `dns_points_here: bool|None` (false = resolves but IPs don't overlap local interfaces). Domains with `dns_points_here=False` go into `dns_elsewhere` bucket and are excluded from summary counts, same as NXDOMAIN. Renderer shows `[→ elsewhere]` tag in table and `(N elsewhere-excluded: ...)` in summary line. `dns_elsewhere` in result dict for `| jq '.certs[] | select(.dns_points_here == false)'`. (session platinum-gleam-0313)
- **AGENT_HELP + schema current** — cpanel section fully rewritten: `full-audit` as recommended start, `--only-failures` for acl-check, `?domain_type=` query param, `--dns-verified` with both nxdomain and elsewhere semantics, nginx ACME JSON output. Schema: `_SCHEMA_ELEMENTS`, `_SCHEMA_OUTPUT_TYPES` (new `cpanel_full_audit`, updated `cpanel_ssl`/`cpanel_acl` with all new fields), `_SCHEMA_EXAMPLE_QUERIES` (13 examples including jq patterns), `_SCHEMA_NOTES`. (session platinum-gleam-0313)

### Tests (session platinum-gleam-0313)
- **30 new tests** — `TestCpanelUriQueryParams` (7); `TestCpanelFullAudit` (12); `TestCpanelAclOnlyFailures` (5: flag stored, renderer filters, clean message, shows all without flag); `TestCpanelDnsIpMatch` (6: dns_points_here true/false, elsewhere excluded from summary, nxdomain+elsewhere combined, renderer tags). Tests: 4,830 → 4,860. (session platinum-gleam-0313)

### Added (session astral-comet-0313)
- **`--only-failures` support for `cpanel://user/ssl`** — previously wired only for nginx, never reached cpanel. `only_failures` now flows through `_build_adapter_kwargs` → `get_structure` → `_get_ssl_structure` → result dict → renderer. `_render_ssl` filters to non-ok certs; prints `✅ No failures found.` when all pass. Summary counts remain total (not filtered) so context is preserved. (session astral-comet-0313)
- **`--validate-nginx-acme --format=json`** — previously text-only. Now detects `args.format == 'json'` and outputs `{'type': 'nginx_acme_audit', 'has_failures': bool, 'only_failures': bool, 'domains': [...]}`. Works with `--only-failures`. Exit code 2 still fires on failures. Useful for agents that want to `| jq` or process results programmatically. (session astral-comet-0313)
- **`--no-fail` / `--exit-zero` added to Explicitly Not Planned** in ROADMAP.md with reasoning. `|| true` documented in AGENT_HELP under new "Exit code 2 breaking my pipeline" troubleshooting entry. (session astral-comet-0313)

### Fixed (session astral-comet-0313)
- **`cpanel://user/ssl` cert entries now include `domain_type`** — each cert entry now carries `'domain_type': d['type']` (values: `main_domain`, `addon`, `subdomain`, `parked`). The `_get_ssl_structure` method was discarding the `type` field from `_list_user_domains`. Renderer now shows subdomain/parked breakdown in the expired count: `"53 expired (47 subdomain/parked)"` instead of just `"53 expired"`, making it clear which expired certs are fallback subdomains vs customer-owned domains. (session astral-comet-0313)

### Tests (session astral-comet-0313)
- **11 new tests** — `test_ssl_cert_entries_include_domain_type`, `test_render_ssl_expired_subdomain_breakdown` (domain_type work); `TestCpanelSslOnlyFailures` (5 tests: adapter flag passthrough, renderer filtering, clean-message); `TestValidateNginxAcmeJsonOutput` (4 tests: valid JSON, domain rows, only-failures filter, has_failures false). Tests: 4,819 → 4,830. (session astral-comet-0313)

### Fixed (session astral-observatory-0313)
- **`--capabilities`, `--explain-file`, `--show-ast` crash with `TypeError` when no path given** — `reveal --capabilities` (without a file) raised `TypeError: expected str, bytes or os.PathLike object, not NoneType` deep in `Path()`. All three handlers now guard `if path is None` at entry and print `Usage: reveal <file> --flag` to stderr + exit 1. `--decorator-stats` was already safe (defaults to `.`). (session astral-observatory-0313)
- **9 unused imports removed** — `get_run_metadata` (autossl/adapter.py), `Optional` (autossl/parser.py, cli/commands/review.py), `List` (markdown/operations.py, analyzers/jsonl.py, analyzers/toml.py), `Tuple` (cli/commands/review.py), `Dict` (cli/routing.py), `cast` (treesitter.py). All verified genuinely unused via grep. (session astral-observatory-0313)

### Tests (session astral-observatory-0313)
- **3 new no-path regression tests** — `test_handle_capabilities_no_path`, `test_handle_explain_file_no_path`, `test_handle_show_ast_no_path` in `test_cli_handlers.py`. Each asserts exit 1 + "Usage:" in stderr. Tests: 4,816 → 4,819. (session astral-observatory-0313)

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

### Refactored (session fluorescent-dawn-0311)
- **Help file blobs decomposed; nginx parse functions extracted; renderer tests added** — Quality 97.4 → 97.7/100; tests 4771 → 4816. Three changes:
  - `adapters/reveal/help.py` and `adapters/markdown/help.py` (both 55/100): large data blobs extracted to module-level constants (`_SCHEMA_OUTPUT_TYPES`, `_SCHEMA_EXAMPLE_QUERIES`, `_HELP_EXAMPLES`, `_HELP_WORKFLOWS`, `_SCHEMA_QUERY_PARAMS`). Both files exit the 55/100 hotspot list.
  - `analyzers/nginx.py`: `_parse_server_block` (complexity 19) → `_apply_server_block_line` helper isolates per-line dispatch; `_parse_block_directives` (complexity 16) → `_accumulate_pending` + `_try_capture_direct_directive` helpers.
  - `adapters/nginx/renderer.py`: 45 new tests in `tests/adapters/test_nginx_renderer.py` via `capsys`, covering all 13 render methods (was 14.8% covered).

### Refactored (session fluorescent-dawn-0311, continued)
- **Nesting depth hotspots eliminated — quality 99.5 → 99.8/100** — 40+ depth>4 functions across the codebase reduced to depth≤4. All 4816 tests pass. Functions: 2431 → 2436 (helpers extracted). Key fixes by file:
  - `adapters/python/modules.py`: `_annotate_editable()` extracted (was inline try/with/if at depth 6 inside `get_pip_package_metadata`)
  - `adapters/json/introspection.py`: `_key_to_path()` extracted, eliminating if/else at depth 5 inside `_flatten_recursive`
  - `adapters/json/adapter.py`: `_parse_filters_safe()` extracted, collapsing try/if nesting in `__init__`
  - `adapters/stats/queries.py`: `_apply_yaml_config_file()` extracted, reducing `get_quality_config` from depth 6 → 4
  - `adapters/stats/analysis.py`: `_is_excluded_code_only()` extracted, collapsing triple-if code_only block in `find_analyzable_files`
  - `rendering/adapters/markdown_query.py`: `_print_frontmatter_item()` extracted from `_render_single_file` list-value loop
  - `display/filtering.py`: `GitignoreParser._parse()` refactored using `read_text()` + `splitlines()` (eliminates try/with/for nesting)
  - `display/metadata.py`: `_format_display_key()` extracted, replacing nested key-format if/else
  - `adapters/markdown/adapter.py`: `_extract_body_contains()` extracted from `__init__` body-contains loop

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
  - **Documentation**: 800+ line [Schema Validation Guide](reveal/docs/guides/SCHEMA_VALIDATION_HELP.md)

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

