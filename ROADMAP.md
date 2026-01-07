# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.32.0
**Last updated:** 2026-01-06

---

## What We've Shipped

### v0.32.0 - Knowledge Graph Navigation (Jan 2026)

**`--related` Flag - Follow Knowledge Graph Links:**
- `reveal file.md --related` shows immediate related documents
- Extracts links from frontmatter fields: `related_docs`, `see_also`, `references`
- Works with Beth, Hugo, Obsidian, and custom link patterns
- Tree view of document relationships
- First step toward full knowledge graph construction

**Language Support:**
- C#, Scala, SQL language support via tree-sitter
- 29 built-in languages now supported

**Fixes:**
- MySQL `MYSQL_HOST` environment variable now respected
- Documentation: rule count, GitHub URLs, related_docs paths corrected
- AGENT_HELP updated with `--related` examples

### v0.31.0 - UX Polish & Workflow Hints (Jan 2026)

**Enhanced Breadcrumbs & Scripting:**
- **Post-check quality guidance** with function name extraction for complex functions
- **diff:// workflow hints** with "Try It Now" examples and related adapters
- **`-q`/`--quiet` mode** for scripting pipelines (alias for `--no-breadcrumbs`)
- **I001 aligned with Ruff F401** - partial unused import detection
- **Workflow-aware breadcrumbs** (Phase 3): Pre-commit and code review workflows
- **Breaking:** Python 3.10+ required (black/ruff target-version updated)
- Test coverage: 1,611 tests passing, 100% coverage on breadcrumbs.py

### v0.30.0 - Semantic Diff & Smart Breadcrumbs (Jan 2026)

**diff:// Adapter - Structural Comparison:**
- `diff://app.py:backup.py` - Compare files (functions, classes, imports)
- `diff://src/:backup/src/` - Compare directories (aggregated changes)
- `diff://git://HEAD~1/:git://HEAD/:` - Compare commits
- `diff://git://main/.:git://feature/.:` - Compare branches
- `diff://app.py:new.py/handle_request` - Element-specific diff
- Cross-adapter composition (env://, mysql://, etc.)

**Smart Breadcrumbs:**
- Large file detection (>20 elements → suggest AST queries)
- Import analysis hints (>5 imports → suggest imports://)
- File-type specific suggestions (Markdown, HTML, YAML, Dockerfile, Nginx)
- Configurable via global, project, and environment variables

**Breaking:** Python 3.10+ required (Python 3.8 EOL Oct 2024, Python 3.9 EOL Oct 2025)
- Ruby 💎 and Lua 🌙 language support added
- lxml moved to optional `[html]` extras
- Test coverage: 1,600+ tests, 77% overall

### v0.29.0 - Schema Validation (Jan 2026)

**Markdown Front Matter Validation:**
- `--validate-schema` flag for markdown front matter validation
- **Built-in schemas:** beth (session READMEs), hugo (static sites), jekyll (GitHub Pages), mkdocs (Python docs), obsidian (knowledge bases)
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

### v0.33.0 (Q1 2026): Deep Knowledge Graph & Metadata Queries ✅ IMPLEMENTED

> **Status:** Implemented on master, pending release

**Recursive Related Documents:** ✅
```bash
reveal file.md --related-depth 3         # Follow links to depth 3
reveal file.md --related-all             # All connected documents (unlimited)
reveal file.md --related-flat            # Flat path list (grep-friendly)
reveal file.md --related-limit 50        # Cap traversal at 50 files
```

**`markdown://` URI Adapter:** ✅
```bash
reveal markdown://sessions/?beth_topics=reveal  # Find by topic
reveal markdown://docs/?tags=python             # Find by tag
reveal 'markdown://?!beth_topics'               # Find missing fields
reveal 'markdown://?type=*guide*'               # Wildcard matching
```

**Features Implemented:**
- Deep traversal with configurable depth (0=unlimited)
- Flat output for piping to other tools
- File count limits prevent runaway traversal
- Dict-format frontmatter support (uri/path/href fields)
- Local directory tree queries (recursive)
- Field filtering with wildcards and missing-field checks
- Multiple criteria support (AND logic)
- JSON and grep output formats

---

### v0.34.0 (Q3 2026): Quality Checks & Documentation

**Metadata Quality Checks:**
```bash
reveal file.md --check-metadata                 # Single file check
reveal docs/**/*.md --check-metadata --summary  # Aggregate report
```

**Metrics:**
- Front matter presence
- Required fields (schema-based)
- Link density (connectivity)
- Topic coverage

**Knowledge Graph Documentation:**
- Complete knowledge graph guide (ships as `reveal help://knowledge-graph`)
- Integration guides: Beth, Hugo, Obsidian
- Best practices and workflow examples

**Implementation:** 3-4 weeks

---

### v0.35.0 (Q4 2026): Final Polish for v1.0

**Documentation:**
- Complete adapter authoring guide
- CI/CD integration examples
- Performance benchmarking suite
- Comprehensive troubleshooting guide
- Update `AGENT_HELP.md` with KG workflow patterns

**Optional Features:**
- `--watch` mode: Live feedback for file changes (if time permits)
- Color themes (light/dark/high-contrast) (if time permits)

---

### v1.0 (Q1 2027): Stable Foundation

**Stability commitment:**
- API freeze (CLI flags, output formats, adapter protocol)
- 75%+ test coverage (currently at 76%)
- All 31 built-in formats tested
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

**Image & Asset Adapters:**
```bash
reveal image://photo.png                 # Dimensions, color depth, EXIF
reveal svg://icon.svg                    # viewBox, paths, groups, embedded text
reveal image://a.png --hash              # MD5, SHA256, perceptual hash (pHash)
reveal "diff://image://a.png?image://b.png"  # Visual similarity score
```

*Use case:* Asset management pipelines (e.g., mapping source SVGs to rendered PNGs via perceptual hashing when direct provenance is lost).

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
