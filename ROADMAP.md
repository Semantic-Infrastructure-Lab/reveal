# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.31.0
**Last updated:** 2026-01-05

---

## What We've Shipped

### v0.29.0 - Schema Validation (Jan 2026)

**Markdown Front Matter Validation:**
- `--validate-schema` flag for markdown front matter validation
- **Built-in schemas:** beth (TIA sessions), hugo (static sites), jekyll (GitHub Pages), mkdocs (Python docs), obsidian (knowledge bases)
- **F-series rules:** F001-F005 for front matter quality checks
  - F001: Missing front matter detection
  - F002: Empty front matter detection
  - F003: Required field validation
  - F004: Type checking (string, list, dict, integer, boolean, date)
  - F005: Custom validation rules with safe Python expression evaluation
- **SchemaLoader:** Loads schemas by name or path with caching
- **Custom schema support:** Create project-specific YAML schemas
- **Multiple output formats:** text (human), json (CI/CD), grep (pipeable)
- **Exit codes:** 0 = pass, 1 = fail (CI/CD integration ready)
- **Date type handling:** Supports YAML auto-parsed dates (datetime.date objects)
- **103 comprehensive tests:** 27 loader + 44 rules + 33 CLI + 43 schemas (100% passing)
- **Documentation:** 808-line [Schema Validation Guide](docs/SCHEMA_VALIDATION_GUIDE.md)
- **Implementation:** 5 phases across 4 sessions, 75% code coverage
- **Test suite:** 1,292/1,292 tests passing (100% pass rate)

### v0.28.0 - Import Intelligence (Jan 2026)

**Import Graph Analysis:**
- `imports://` adapter for multi-language import analysis (Python, JS, TS, Go, Rust)
- I001: Unused import detection with symbol usage analysis
- I002: Circular dependency detection via topological sort
- I003: Layer violation detection (requires `.reveal.yaml` config)
- Plugin-based architecture using ABC + registry pattern
- Query parameters: `?unused`, `?circular`, `?violations`
- 1,086/1,086 tests passing, 94% coverage on imports adapter

**Configuration Transparency:**
- `reveal://config` for debugging active configuration
- Source tracking: environment variables, config files, CLI overrides
- 7-level precedence visualization (CLI → env → config files → defaults)
- Text and JSON output formats for scripting
- Test coverage: 9 tests, 82% coverage on reveal.py adapter

### v0.27.1 - Code Quality Refactoring (Dec 2025)

**Internal Improvements:**
- Extensive refactoring for better maintainability (no functional changes)
- Broke down large functions (100-300 lines) into focused helpers (10-50 lines)
- Improved Single Responsibility Principle adherence across 5 files
- Reduced cyclomatic complexity for better testability
- Files refactored: `help.py`, `parser.py`, `formatting.py`, `main.py`, `L003.py`
- 988/988 tests passing (100% pass rate maintained)
- 74% code coverage maintained

### v0.27.0 - Element Extraction (Dec 2025)

**reveal:// Element Extraction:**
- Extract specific code elements from reveal's own source
- `reveal reveal://rules/links/L001.py _extract_anchors_from_markdown` extracts function
- `reveal reveal://analyzers/markdown.py MarkdownAnalyzer` extracts class
- Self-referential: Can extract reveal's own code using reveal
- Works with any file type in reveal's codebase
- 988 tests passing (up from 773 in v0.26.0), 74% coverage (up from 67%)

### v0.26.0 - Link Validation Complete (Dec 2025)

**L001 Anchor Validation:**
- Full support for `#heading` links in markdown files
- Extract headings using GitHub Flavored Markdown slug algorithm
- Validate anchor-only links (`[text](#heading)`)
- Validate file+anchor links (`[text](file.md#heading)`)
- Detects broken anchors and suggests valid alternatives

**reveal:// Enhancements:**
- Component filtering now works (`reveal reveal://analyzers` shows only analyzers)
- Smart root detection (prefer git checkouts over installed packages)
- Support `REVEAL_DEV_ROOT` environment variable for explicit override

**Quality Improvements:**
- Added debug logging to 9 bare exception handlers
- Improved pymysql missing dependency errors
- Updated outdated version references in help text
- Comprehensive test coverage for L001, L002, L003 rules (28 tests)
- 773 tests passing, 67% coverage

### v0.25.0 - HTML Analyzer & Link Validation (Dec 2025)

**HTML Analyzer:**
- Full HTML analysis with template support (Jinja2, Go, Handlebars, ERB, PHP)
- `--metadata` flag: Extract SEO, OpenGraph, Twitter cards
- `--semantic TYPE` flag: Extract navigation, content, forms, media elements
- `--scripts` and `--styles` flags: Extract inline/external scripts and stylesheets
- Comprehensive guide via `reveal help://html`
- 35 tests with 100% pass rate

**Link Validation:**
- L-series quality rules (L001, L002, L003) for documentation workflows
- **L001:** Broken internal links (filesystem validation, case sensitivity)
- **L002:** Broken external links (HTTP validation with 404/403 detection)
- **L003:** Framework routing mismatches (FastHTML, Jekyll, Hugo auto-detection)
- Performance optimized: L001+L003 fast (~50ms/file), L002 slow (network I/O)
- Comprehensive guide: [LINK_VALIDATION_GUIDE.md](docs/LINK_VALIDATION_GUIDE.md)

**Dependencies Added:**
- `beautifulsoup4>=4.12.0` and `lxml>=4.9.0` for HTML parsing

### v0.24.0 - Code Quality Metrics (Dec 2025)

**Stats Adapter & Hotspot Detection:**
- `stats://` adapter: Automated code quality analysis and metrics
- `--hotspots` flag: Identify worst quality files (technical debt detection)
- Quality scoring: 0-100 rating based on complexity, nesting, and function length
- CI/CD integration: JSON output for quality gates
- Dogfooding validation: Used on reveal itself to improve code quality

**Documentation Improvements:**
- Generic workflow patterns (removed tool-specific references)
- Enhanced adapter documentation

### v0.23.0-v0.23.1 - Type-First Architecture (Dec 2025)

**Type System & Containment:**
- `--typed` flag: Hierarchical code structure with containment relationships
- Decorator extraction: `@property`, `@staticmethod`, `@classmethod`, `@dataclass`
- `TypedStructure` and `TypedElement` classes for programmatic navigation
- AST decorator queries: `ast://.?decorator=property`
- New bug rules: B002, B003, B004, B005 (decorator-related)

**Adapters & Features:**
- `reveal://` self-inspection adapter with V-series validation rules
- `json://` adapter for JSON navigation with path access and schema discovery
- `--copy` / `-c` flag: Cross-platform clipboard integration
- `ast://` query system with multiline pattern matching
- Enhanced help system with `help://` progressive discovery

### v0.22.0 - Self-Inspection (Dec 2025)

- `reveal://` adapter: Inspect reveal's own codebase
- V-series validation rules for completeness checks
- Modular package refactoring (cli/, display/, rendering/, rules/)

### v0.20.0-v0.21.0 - JSON & Quality Rules (Dec 2025)

- `json://` adapter: Navigate JSON files with path access, schema, gron-style output
- Enhanced quality rules: M101-M103 (maintainability), D001-D002 (duplicate detection)
- `--frontmatter` flag for markdown YAML extraction

### v0.19.0 - Clipboard & Nginx Rules (Dec 2025)

- `--copy` / `-c` flag: Copy output to clipboard (cross-platform)
- Nginx configuration rules: N001-N003

### v0.17.0-v0.18.0 - Python Runtime (Dec 2025)

- `python://` adapter: Environment inspection, bytecode debugging, module conflicts
- Enhanced help system with progressive discovery

### v0.13.0-v0.16.0 - Pattern Detection & Help (Nov-Dec 2025)

- `--check` flag for code quality analysis
- Pluggable rule system (B/S/C/E categories)
- `--select` and `--ignore` for rule filtering
- Per-file and per-project rules

### v0.12.0 - Semantic Navigation (Nov 2025)

- `--head N`, `--tail N`, `--range START-END`
- JSONL record navigation
- Progressive function listing

### v0.11.0 - URI Adapter Foundation (Nov 2025)

- `env://` adapter for environment variables
- URI routing and adapter protocol
- Optional dependency system

### Earlier Releases

- v0.9.0: `--outline` mode (hierarchical structure)
- v0.8.0: Tree-sitter integration (50+ languages)
- v0.7.0: Cross-platform support
- v0.1.0-v0.6.0: Core file analysis

---

## What's Next

### v0.29.0 ✅ SHIPPED (Jan 2026): Schema Validation for Knowledge Graphs

**Front Matter Schema Validation** - Validate markdown metadata against schemas:
```bash
reveal file.md --validate-schema beth       # TIA sessions
reveal file.md --validate-schema hugo       # Static sites
reveal file.md --validate-schema jekyll     # GitHub Pages
reveal file.md --validate-schema mkdocs     # Python docs
reveal file.md --validate-schema obsidian   # Knowledge bases
reveal file.md --validate-schema custom.yaml # Custom schema
```

**Features:** ✅ All delivered
- ✅ Schema-based validation framework
- ✅ Built-in schemas: `beth.yaml`, `hugo.yaml`, `jekyll.yaml`, `mkdocs.yaml`, `obsidian.yaml`
- ✅ Custom validation rules (YAML-based, safe eval)
- ✅ CI/CD integration for documentation quality gates
- ✅ Validation rules: F001-F005 (front matter quality)
- ✅ 103 comprehensive tests (100% passing)
- ✅ 808-line documentation guide
- ✅ Dogfooded on real data (SIF website, TIA sessions)
- ✅ Web-validated against official docs

**Implementation:** Completed in 5 sessions (5 phases + dogfooding + Jekyll/MkDocs addition)
**See:** `docs/SCHEMA_VALIDATION_GUIDE.md` for complete guide

**Community Reach:**
- Jekyll schema: 1M+ GitHub Pages users
- MkDocs schema: Large Python documentation ecosystem (FastAPI, NumPy, Pydantic)
- Hugo/Obsidian/Beth: Static sites, knowledge bases, TIA sessions

**Rationale:** Lightweight feature (builds on existing `--frontmatter` from v0.23.0), foundational for knowledge graph construction. Extended with Jekyll/MkDocs for broader community impact.

---

### v0.30.0 ✅ SHIPPED (Jan 2026): Semantic Diff & Smart Breadcrumbs

**diff:// Adapter** - Semantic structural comparison for code review:
```bash
reveal diff://app.py:backup/app.py         # Compare files (functions/classes)
reveal diff://src/:backup/src/              # Compare directories (aggregated)
reveal diff://git://HEAD~1/:git://HEAD/:    # Compare commits
reveal diff://git://HEAD/.:src/             # Compare git vs working tree
reveal diff://git://main/.:git://feature/:  # Compare branches
reveal diff://app.py:new.py/handle_request # Element-specific diff
```

**Smart Breadcrumbs** - Context-aware navigation hints:
```bash
# After viewing large file (>20 elements):
reveal large_module.py
# Breadcrumbs suggest: reveal 'ast://large_module.py?complexity>10'

# After viewing file with many imports (>5):
reveal utils.py
# Breadcrumbs suggest: reveal imports://utils.py  # Dependency analysis

# File-type specific suggestions:
reveal docs/guide.md    # Suggests: --links
reveal app.html         # Suggests: --check, --links
reveal config.yaml      # Suggests: --check
```

**Features:** ✅ All delivered
- ✅ diff:// adapter with file, directory, and git comparison
- ✅ Git integration (commits, branches, working tree)
- ✅ Structural diff (functions, classes, imports, decorators)
- ✅ Element-level diff for deep dives
- ✅ JSON output for CI/CD integration
- ✅ Smart breadcrumbs with large file detection
- ✅ Import analysis hints (Python, JS, TS, Rust, Go)
- ✅ File-type specific suggestions (Markdown, HTML, YAML, Dockerfile, Nginx)
- ✅ Configurable breadcrumbs (global, project, env vars)

**Breaking Changes:**
- **Python 3.10+ required** (was 3.8+)
  - Python 3.8 EOL: October 2024
  - Python 3.9 EOL: October 2025

**Test Coverage:** 1,600+ tests, 77% coverage (100% on breadcrumbs.py, diff.py)
**Documentation:** README, help text, docs/DIFF_ADAPTER_GUIDE.md, CHANGELOG
**Sessions:** cooling-hurricane-0104, sacred-sphinx-0104, fallen-leviathan-0104, infernal-omega-0105, yutazu-0105
**See:** `docs/DIFF_ADAPTER_GUIDE.md` for AI agent guide

---

### v0.31.0 ✅ SHIPPED (Jan 2026): UX Polish & Workflow Hints

**Post-Check Guidance** - After --check finds issues, suggest fixes:
```bash
reveal app.py --check
# Breadcrumbs suggest: reveal app.py handle_request  # View complex function
# Breadcrumbs suggest: reveal stats://app.py         # Analyze trends
```

**Features:** ✅ All delivered
- ✅ Post-check quality guidance with function name extraction
- ✅ diff:// workflow hints ("Try It Now" examples)
- ✅ `-q`/`--quiet` mode for scripting pipelines
- ✅ I001 aligned with Ruff F401 (partial unused import detection)
- ✅ black/ruff target-version updated to py310

**Test Coverage:** 1,606 tests, 100% coverage on breadcrumbs.py
**Sessions:** risen-god-0105, risen-armor-0105
**See:** `internal-docs/planning/BREADCRUMB_IMPROVEMENTS_2026.md` Phase 2 complete

---

### v0.32.0 (Q3 2026): Knowledge Graph Navigation

**Related Documents Viewer** - Follow knowledge graph links:
```bash
reveal file.md --related                 # Show immediate related docs
reveal file.md --related --depth 2       # Follow links recursively (max depth 2)
```

**Features:**
- Configurable link fields (related_docs, see_also, references)
- Tree view of document relationships
- Max depth 2 (maintains stateless architecture)
- Auto-detect link field patterns
- Works with Beth, Hugo, Obsidian, and custom link patterns

**Breadcrumb Workflow Guidance** (Phase 3):
- Pre-commit workflow detection and guidance
- Code review workflow hints
- Refactoring workflow support
- Help system integration

**Implementation:** 4-6 weeks total
- Link following: 2-3 weeks
- Breadcrumb workflows: 2-3 weeks

---

### v0.33.0 (Q3 2026): Metadata Queries & Quality Checks

**`markdown://` URI Adapter** - Query markdown files by front matter:
```bash
reveal markdown://sessions/?beth_topics=reveal  # Find by topic
reveal markdown://content/?tags=python          # Find by tag
reveal markdown://?!beth_topics                 # Find missing fields
```

**Features:**
- Local directory tree queries (not corpus-wide)
- Field filtering with wildcards
- Multiple criteria support
- Integration with --related, --validate

**Quality Checks** - Knowledge graph health metrics:
```bash
reveal file.md --check-metadata                 # Single file check
reveal docs/**/*.md --check-metadata --summary  # Aggregate report
```

**Metrics:**
- Front matter presence
- Required fields (schema-based)
- Link density (connectivity)
- Topic coverage

**Implementation:**
- markdown://: 3-4 weeks
- --check-metadata: 2 weeks

---

### v0.34.0 (Q4 2026): Documentation & Polish for v1.0

**Knowledge Graph Documentation:**
- Complete knowledge graph guide (ships as `reveal help://knowledge-graph`)
- Integration guides: Beth, Hugo, Obsidian
- Best practices and workflow examples
- Update `AGENT_HELP.md` with KG patterns

**General Documentation:**
- Complete adapter authoring guide
- CI/CD integration examples
- Performance benchmarking suite
- Comprehensive troubleshooting guide

**Optional Features:**
- `--watch` mode: Live feedback for file changes (if time permits)
- Color themes (light/dark/high-contrast) (if time permits)

---

### v1.0 (Q1 2027): Stable Foundation

**Stability commitment:**
- API freeze (CLI flags, output formats, adapter protocol)
- 75%+ test coverage (currently at 76%)
- All 18 built-in languages tested
- Comprehensive documentation
- Performance guarantees

**Included Features:**
- Code structure exploration (core competency)
- **11 URI adapters:** help://, env://, ast://, json://, python://, reveal://, stats://, mysql://, imports://, diff://, markdown://
- **38+ quality rules** across B/S/C/E/L/I/M/D/N/V/F/U categories
- Knowledge graph construction (schema validation, link following, metadata queries, quality checks)
- Progressive disclosure patterns for code and documentation
- Enhanced breadcrumb navigation with workflow guidance
- Cross-platform support (Linux, macOS, Windows)

### Post-v1.0: Advanced URI Schemes

**See:** `internal-docs/planning/ADVANCED_URI_SCHEMES.md` for detailed roadmap

**Phases (v1.1-v1.4):**
- `query://` - SQL-like cross-resource queries
- `graph://` - Dependency and call graph visualization
- `time://` - Temporal exploration (git history, blame)
- `semantic://` - Semantic code search with embeddings
- `trace://` - Execution trace exploration
- `live://` - Real-time monitoring
- `merge://` - Multi-resource composite views

### Long-term: Ecosystem

**Database Adapters:**
```bash
pip install reveal-cli[database]
reveal postgres://prod users             # Database schemas
reveal mysql://staging orders
reveal sqlite:///app.db
```

**API & Container Adapters:**
```bash
reveal https://api.github.com            # REST API exploration
reveal docker://container-name           # Container inspection
```

**Plugin System:**
```bash
pip install reveal-adapter-mongodb       # Community adapters
reveal mongodb://prod                    # Just works
```

---

## Design Principles

1. **Progressive disclosure:** Overview → Details → Specifics
2. **Optional dependencies:** Core is lightweight, extras add features
3. **Consistent output:** Text, JSON, and grep-compatible formats
4. **Secure by default:** No credential leakage, sanitized URIs
5. **Token efficiency:** 10-150x reduction vs reading full files

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add analyzers and adapters.

**Good first issues:**
- Add SQLite adapter (simpler than PostgreSQL)
- Add `--watch` mode
- Improve markdown link extraction

**Share ideas:** [GitHub Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)
