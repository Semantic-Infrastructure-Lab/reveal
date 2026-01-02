# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.28.0
**Last updated:** 2026-01-01

---

## What We've Shipped

### v0.28.0 - Import Intelligence (Jan 2026)

**Import Graph Analysis:**
- `imports://` adapter for multi-language import analysis (Python, JS, TS, Go, Rust)
- I001: Unused import detection with symbol usage analysis
- I002: Circular dependency detection via topological sort
- I003: Layer violation detection (requires `.reveal.yaml` config)
- Plugin-based architecture using ABC + registry pattern
- Query parameters: `?unused`, `?circular`, `?violations`
- 1,086/1,086 tests passing, 94% coverage on imports adapter

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

### v0.28.0 (Q1 2026): Import Intelligence

**`imports://` adapter** - Import graph analysis (Python-first):
```bash
reveal imports://src                     # All imports in directory
reveal 'imports://src?unused'            # Find unused imports
reveal 'imports://src?circular'          # Detect circular dependencies
```

**Initial scope (v0.28.0):**
- Python import analysis (via tree-sitter)
- Unused import detection with symbol usage analysis
- Circular dependency detection via topological sort
- `.reveal.yaml` configuration (imports section)

**Language expansion (v0.28.1-v0.28.5):**
- v0.28.1: JavaScript support
- v0.28.2: TypeScript support
- v0.28.3: Go support
- v0.28.4: Rust support
- v0.28.5: Layer violation detection (multi-language)

**See:** `internal-docs/planning/IMPORTS_IMPLEMENTATION_PLAN.md` for detailed implementation plan

**Strategy:** Ship Python-first, validate approach, then add languages incrementally (one per release).

---

### v0.29.0 (Q2 2026): Architecture Validation

**`architecture://` adapter** - Architecture rule validation:
```bash
reveal architecture://src               # Check all architecture rules
reveal 'architecture://src?violations'   # List violations only
reveal architecture://src/routes         # Check specific layer
```

**Features:**
- Layer boundary enforcement (presentation → service → data)
- Custom dependency rules via `.reveal.yaml` (architecture section)
- Pattern compliance validation
- CI/CD integration for architecture governance
- Expand .reveal.yaml schema (add architecture configuration)

**Prerequisites:**
- Create `ARCHITECTURE_ADAPTER_PLAN.md` (detailed implementation spec)
- Validate design with users

**See:** (Planning document to be created)

---

### v0.29.5 (Q2 2026): Optional Enhancements

**If time permits:**

**`diff://` adapter** - Comparative exploration:
```bash
reveal diff://app.py:backup/app.py       # Compare two files
reveal diff://app.py:HEAD~1              # Compare with git revision
reveal diff://python://venv:python://    # Compare environments
```

### v0.30.0 (Q3 2026): Polish for v1.0

**UX Improvements:**
- `--watch` mode: Live feedback for file changes
- Color themes (light/dark/high-contrast)
- Global config support (`~/.config/reveal/config.yaml`)
- `--quiet` mode for scripting
- Interactive mode exploration

**Documentation:**
- Complete adapter authoring guide
- CI/CD integration examples
- Performance benchmarking suite

### v1.0 (Q4 2026): Stable Foundation

**Stability commitment:**
- API freeze (CLI flags, output formats, adapter protocol)
- 60%+ test coverage
- All 18 built-in languages tested
- Comprehensive documentation
- Performance guarantees

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
