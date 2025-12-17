# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.24.0
**Last updated:** 2025-12-16

---

## What We've Shipped

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

### v0.24 (Q1 2026): Link Validation & Quality

**Link Validation** - Documentation workflow support:
- L-series quality rules (L001: broken internal, L002: broken external, L003: routing mismatches)
- `--recursive` modifier for batch processing
- Framework profiles (FastHTML, Jekyll, Hugo routing awareness)
- CI/CD integration (exit codes, JSON output)

**Quality Improvements:**
- D002 duplicate detection refinement (better discrimination)
- Test coverage improvements (target: 50%+)
- Code quality refactoring (Phases 2-3)

**See:** `internal-docs/planning/PENDING_WORK.md` for active tracks

### v0.25-v0.26 (Q2 2026): Core Features

**`diff://` adapter** - Comparative exploration:
```bash
reveal diff://app.py:backup/app.py       # Compare two files
reveal diff://app.py:HEAD~1              # Compare with git revision
reveal diff://python://venv:python://    # Compare environments
```

**`stats://` adapter** - Codebase health metrics:
```bash
reveal stats://./src                     # Overview: lines, functions, complexity
reveal stats://./src --hotspots          # Largest/most complex files
reveal stats://./src --format=json       # For CI/CD dashboards
```

**`--watch` mode** - Live feedback:
```bash
reveal app.py --watch --check            # Monitor file for changes
reveal src/ --watch --typed              # Watch directory
```

### v0.27-v0.29 (Q3 2026): Polish for v1.0

**UX Improvements:**
- Color themes (light/dark/high-contrast)
- Config file support (`~/.config/reveal/config.yaml`)
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
