# Reveal Roadmap

> **Vision:** Universal resource exploration with progressive disclosure

**Current version:** v0.19.0
**Last updated:** 2025-12-09

---

## What We've Shipped

### v0.19.0 - Clipboard & Nginx Rules (Dec 2025)

- `--copy` / `-c` flag: Copy output to clipboard (cross-platform)
- Nginx configuration rules: N001 (duplicate backends), N002 (missing SSL certs), N003 (missing proxy headers)
- `help://tricks`: Cool tricks and hidden features guide

### v0.18.0 - Agent-First Improvements (Dec 2025)

- Enhanced help system with progressive discovery
- Python adapter improvements (bytecode debugging, module inspection)
- AST adapter enhancements (wildcard patterns, combined queries)

### v0.17.0 - Python Runtime Inspection (Dec 2025)

- `python://` adapter: Inspect Python environment
- `python://debug/bytecode`: Detect stale .pyc files
- `python://packages`: Package information
- `python://module/<name>`: Module conflict detection

### v0.16.0 - Enhanced Help System (Dec 2025)

- Self-documenting `help://` URIs
- Static guides: `help://agent`, `help://anti-patterns`, `help://python-guide`
- Adapter authoring guide

### v0.13.0 - Pattern Detection (Nov 2025)

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

### Near-term: CLI Polish

**Completed in v0.19.0:**
- [x] `--copy` clipboard integration
- [x] `help://tricks` documentation
- [x] Nginx configuration rules (N001-N003)

**Ready to implement:**
- [ ] `--watch` mode: Live updates on file changes
- [ ] Color themes: Light/dark/16-color
- [ ] `--quiet` mode: Suppress breadcrumbs

### Short-term: Structural Analysis

**`diff://` adapter** - Compare files, environments, or time:
```bash
reveal diff://app.py:backup/app.py       # Compare two files
reveal diff://app.py:HEAD~1              # Compare with git revision
reveal diff://env://:env://prod          # Compare environments
```

**`stats://` adapter** - Codebase health metrics:
```bash
reveal stats://./src                     # Lines, functions, complexity
reveal stats://./src --hotspots          # Largest/most complex files
```

### Medium-term: Database Adapters

**Goal:** Explore database schemas with the same ease as code files

```bash
pip install reveal-cli[database]

reveal postgres://prod                   # All tables
reveal postgres://prod users             # Table structure
reveal mysql://staging orders            # MySQL support
reveal sqlite:///path/to/db.sqlite       # SQLite files
```

**Design:** MySQL adapter spec complete in `internal-docs/planning/MYSQL_ADAPTER_SPEC.md`

### Long-term: Ecosystem

**API Adapters:**
```bash
reveal https://api.github.com            # REST API exploration
reveal openapi://petstore.swagger.io     # OpenAPI spec parsing
reveal graphql://api.github.com/graphql  # GraphQL introspection
```

**Container Adapters:**
```bash
reveal docker://my-app-prod              # Container inspection
reveal docker-compose://web              # Compose service details
```

**Plugin Ecosystem:**
```bash
pip install reveal-adapter-mongodb       # Third-party adapters
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

**Share ideas:** [GitHub Discussions](https://github.com/scottsen/reveal/discussions)
