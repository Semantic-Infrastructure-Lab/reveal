---
title: Reveal Changelog
type: documentation
category: changelog
date: 2026-02-13
---

# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.49.2] - 2026-02-14

### Added
- **Test coverage** - Added comprehensive tests for core utilities (45% → 46% overall)
  - `reveal/result.py`: 0% → 100% (51 tests, 67 lines) - Success/Failure monads, chaining, error handling
  - `reveal/utils/uri.py`: 0% → 97.7% (76 tests, 86 lines) - URI parsing (all schemes), auth, IPv4/IPv6
  - `reveal/utils/validation.py`: 28.2% → 100% (65 tests, 56 lines) - Path, type, range, port validators
  - `reveal/errors.py`: 55.6% → 100% (57 tests, 36 lines) - Custom exceptions, suggestions, context
  - Total: 249 tests added, 245 lines covered, 3440 tests passing (was 3191)
  - Session: yoxumema-0214

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
