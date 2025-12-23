# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.25.0
**Last updated:** 2025-12-23

---

## What We've Shipped

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

### v0.26 (Q1 2026): Quality & Usability

**Link Validation Enhancements:**
- Test coverage for L001, L002, L003 (target: 80%+)
- `--recursive` flag for batch processing
- Anchor validation (#heading links)
- `.reveal.yaml` config for ignoring URLs

**Quality Improvements:**
- D002 duplicate detection refinement (better discrimination)
- Overall test coverage improvements (target: 60%+)
- Code quality refactoring based on dogfooding results

**See:** `internal-docs/planning/PENDING_WORK.md` for active tracks

### v0.27-v0.28 (Q2 2026): Code Analysis & Architecture

**`imports://` adapter** - Import graph analysis:
```bash
reveal imports://src                     # All imports in directory
reveal 'imports://src?unused'            # Find unused imports
reveal 'imports://src?circular'          # Detect circular dependencies
reveal imports://src --graph             # Visualize import relationships
```
- Language-agnostic (Python, JavaScript, Go, Rust, Java, TypeScript)
- Unused import detection with symbol usage analysis
- Circular dependency detection via topological sort
- Layer violation detection (routes importing repositories, etc.)
- Multi-language support via tree-sitter

**`architecture://` adapter** - Architecture rule validation:
```bash
reveal architecture://src               # Check all architecture rules
reveal 'architecture://src?violations'   # List violations only
reveal architecture://src/routes         # Check specific layer
```
- Layer boundary enforcement (presentation → service → data)
- Custom dependency rules via `.reveal.yaml`
- Pattern compliance validation
- CI/CD integration for architecture governance

**`.reveal.yaml` config** - Project-specific configuration:
```yaml
# .reveal.yaml - shareable project configuration
imports:
  entry_points: [app/main.py, tests/]
  ignore_unused: [__init__.py]

architecture:
  layers:
    - name: routes
      allow_imports: [services, models, utils]
      deny_imports: [repositories, database]
```
- Reduces false positives (entry points, framework patterns)
- Team-shared rules (commit to version control)
- Adapter-specific configuration sections
- JSON Schema validation

**`diff://` adapter** - Comparative exploration:
```bash
reveal diff://app.py:backup/app.py       # Compare two files
reveal diff://app.py:HEAD~1              # Compare with git revision
reveal diff://python://venv:python://    # Compare environments
```

**See:** `internal-docs/planning/PRACTICAL_CODE_ANALYSIS_ADAPTERS.md` for implementation details

### v0.29-v0.30 (Q3 2026): Polish for v1.0

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
