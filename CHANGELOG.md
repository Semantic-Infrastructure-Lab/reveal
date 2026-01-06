# Changelog

All notable changes to reveal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.31.0] - 2026-01-05

### Breaking Changes
- **Minimum Python version raised to 3.10** (was 3.8)
  - Python 3.8 reached EOL in October 2024
  - Python 3.9 reaches EOL in October 2025
  - Code uses walrus operators (`:=`) and modern type hints compatible with 3.10+
  - CI now tests Python 3.10 and 3.12 on Ubuntu only (simplified from 3.8/3.12 on 3 platforms)
  - Users on Python 3.8/3.9 should use reveal-cli <0.30.0

### Fixed
- **I001 now detects partial unused imports** (aligned with Ruff F401)
  - Previously only flagged imports when ALL names were unused
  - Now correctly flags each unused name individually
  - Example: `from typing import Dict, List` with only `List` used now flags `Dict`
- **Breadcrumbs: Added HTML to element placeholder mapping**
  - HTML files now correctly show `<element>` placeholder in breadcrumb hints
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
- **Enhanced breadcrumb system with smart suggestions** (Phase 2 complete)
  - **Configurable breadcrumbs**: Multi-layer config support (global, project, env vars)
  - **File-type specific suggestions**: Markdown (--links), HTML (--check, --links), YAML/JSON/TOML (--check), Dockerfile/Nginx (--check)
  - **Large file detection**: Files with >20 elements suggest AST queries (`ast://file.py?complexity>10`)
  - **Import analysis hints**: Files with >5 imports suggest `imports://file.py` for dependency analysis
  - **Post-check quality guidance**: After `--check`, suggests viewing complex functions, stats analysis
    - Detects complexity issues (C901, C902) and suggests viewing the specific function
    - Links to `stats://` and `help://rules` for further analysis
  - **diff:// workflow hints**: After `reveal help://diff`, shows practical try-it-now examples
    - Added related adapters mapping (diff→stats, ast; stats→ast, diff; imports→ast, stats)
    - Breadcrumbs after diff output suggest element-specific diffs, stats, and quality checks
  - **`--quiet` / `-q` scripting mode**: Alias for `--no-breadcrumbs` for scripting pipelines
  - **Supports**: Python, JavaScript, TypeScript, Rust, Go
  - **Test coverage**: 74 breadcrumb tests (100% coverage on breadcrumbs.py)
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
  - **Usage**: `reveal README.md --validate-schema beth`
  - **Implementation**: 5 phases complete across 4 sessions (garnet-ember-0102, amber-rainbow-0102, dark-constellation-0102, pearl-spark-0102)
  - **Test coverage**: 103 comprehensive tests (27 loader + 44 rules + 33 CLI + 43 schemas), 100% passing, 75% coverage overall
  - **Documentation**: 800+ line [Schema Validation Guide](docs/SCHEMA_VALIDATION_GUIDE.md)

- **Beth Schema (`beth.yaml`)** - TIA session README validation
  - Required fields: `session_id` (pattern: word-word-MMDD), `beth_topics` (min 1 topic)
  - Optional fields: date, badge, type, project, files_modified, files_created, commits
  - Custom validation: session_id format checking, topic count validation

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

## Older Releases

For changelog entries prior to v0.25.0, see [CHANGELOG.archive.md](CHANGELOG.archive.md).

## Links

- **GitHub**: https://github.com/Semantic-Infrastructure-Lab/reveal
- **PyPI**: https://pypi.org/project/reveal-cli/
- **Issues**: https://github.com/Semantic-Infrastructure-Lab/reveal/issues
