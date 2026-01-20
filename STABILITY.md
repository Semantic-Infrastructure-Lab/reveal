---
title: Reveal Stability Policy
type: documentation
category: policy
date: 2026-01-17
---

# Stability Policy

**Last updated:** 2026-01-19
**Version:** v0.40.0

---

## Purpose

This document defines what users and AI agents can safely depend on in reveal. It provides clear stability guarantees for features, adapters, and APIs.

---

## Stability Levels

### 🟢 Stable

**Guarantee:** API stability guaranteed. Breaking changes require major version bump (v1.0 → v2.0).

**What's Stable:**
- **Core modes:** directory → file → element pattern
- **Output format:** `filename:line` format for all text output
- **CLI interface:** Basic flags (`--format`, `--check`, `--outline`, `--stdin`)
- **Adapters:**
  - `help://` - Self-documenting help system
  - `env://` - Environment variable inspection
  - `ast://` - Code queries and structure analysis
  - `python://` - Python runtime inspection
- **Quality rules (core):** B001-B005 (bugs), S701 (security), C901 (complexity), E501 (line length)
- **Languages (full support):** Python, JavaScript, TypeScript, Rust, Go, Java, C, C++

**Backward compatibility:** Guaranteed within major versions (v0.x → v0.y is safe for stable features).

---

### 🟡 Beta

**Guarantee:** Feature-complete but API may evolve. Changes announced in CHANGELOG with migration guidance.

**What's Beta:**
- **Adapters:**
  - `diff://` - Semantic structural comparison
  - `imports://` - Import graph analysis
  - `sqlite://` - SQLite database inspection
  - `mysql://` - MySQL database inspection
  - `stats://` - Code quality metrics
  - `json://` - JSON navigation
  - `markdown://` - Frontmatter queries
  - `git://` - Git repository inspection
- **Quality rules (extended):** B001-B006 (bugs), D001-D002 (duplicates), I001-I004 (imports), L001-L005 (links), M101-M103 (maintainability), N001-N003 (nginx), R913 (refactoring), U501-U502 (URLs), F001-F005 (frontmatter), V001-V022 (validation)
- **Languages (full support):** C#, Scala, PHP, Ruby, Lua, Kotlin, Swift, Dart, HCL/Terraform, GraphQL, Protobuf, Zig, GDScript, Bash, SQL
- **Features:**
  - Schema validation (`--validate-schema`)
  - Configuration system (`.reveal.yaml`)
  - Link validation (L-series rules)
  - Import analysis (I-series rules)

**Expectations:** May receive breaking changes in minor versions (v0.36 → v0.37) but with clear migration path in CHANGELOG.

---

### 🔴 Experimental

**Guarantee:** No stability guarantees. May change significantly or be removed without notice.

**What's Experimental:**
- Features not yet documented in README.md
- Internal V-series rules (V016-V022) used for reveal's self-validation
- Undocumented query parameters on adapters
- Features marked "experimental" in help text
- Languages with only tree-sitter extraction (165+ languages, basic structure only)

**Expectations:** Use at your own risk. Test thoroughly before depending on experimental features.

---

## Version Policy

### Current Version: v0.40.0 (Beta)

**Semver interpretation for pre-v1.0:**
- **Patch (v0.36.0 → v0.36.1):** Bug fixes only, no breaking changes
- **Minor (v0.36 → v0.37):** New features, may include breaking changes in Beta features
- **Major (v0 → v1):** Stability commitment - Stable features frozen, breaking changes announced 3+ months in advance

### Path to v1.0

**Blockers for v1.0:**
1. ✅ Output contract specification (structured return values) - **COMPLETE** (2026-01-17)
2. ✅ JSON schema versioning - **COMPLETE** (2026-01-17, via Output Contract v1.0)
3. 🟡 Comprehensive integration test suite - **IN PROGRESS** (2,500+ tests passing, expanding coverage)
4. 🟡 Documentation completeness (all adapters have help:// guides) - **IN PROGRESS** (most adapters documented)
5. ⏳ 6 months without breaking changes to Stable features - **STARTED** (2026-01-17, target: 2026-07-17)

**Current progress:** 4/5 complete (Output Contract ✅, JSON versioning ✅, integration tests 🟡, docs 🟡, 6-month stability ⏳)

**Estimated timeline:** Q2-Q3 2026 (July 2026 earliest, after 6-month stability period)

---

## Breaking Change Policy

### For Stable Features

**Before v1.0:**
- Breaking changes allowed in minor versions but:
  - Must be announced in CHANGELOG with "BREAKING CHANGE" label
  - Must include migration guide
  - Must preserve backward compatibility for at least one minor version (deprecation warnings)

**After v1.0:**
- Breaking changes require major version bump (v1 → v2)
- Deprecated features get 6 months notice minimum
- Migration tooling provided when possible

### For Beta Features

**Before v1.0:**
- Breaking changes allowed in minor versions
- Announced in CHANGELOG with "BREAKING CHANGE" label
- Migration guidance provided but not guaranteed

**After v1.0:**
- Beta features promoted to Stable or removed
- Same guarantees as Stable features apply

### For Experimental Features

- May change or be removed at any time
- No CHANGELOG requirement
- No migration guidance guaranteed

---

## Deprecation Process

1. **Announce:** Add deprecation warning to help text and CHANGELOG
2. **Grace period:** Minimum 1 minor version (2-4 weeks typical)
3. **Remove:** Delete in next minor version, document in CHANGELOG

**Example:**
```
v0.36.0: Feature X deprecated (warning added)
v0.37.0: Feature X removed (documented in CHANGELOG)
```

---

## Adapter-Specific Stability

### Stable Adapters (Universal Tools)

| Adapter | Stability | Notes |
|---------|-----------|-------|
| `help://` | 🟢 Stable | Help system format frozen |
| `env://` | 🟢 Stable | Environment variable inspection, cross-platform |
| `ast://` | 🟢 Stable | Query syntax stable, new filters may be added |
| `python://` | 🟢 Stable | Core commands stable, new diagnostics may be added |

### Beta Adapters (Development & Domain Tools)

| Adapter | Stability | Maturity | Notes |
|---------|-----------|----------|-------|
| `diff://` | 🟡 Beta | High | Output format may change, git:// integration stable |
| `imports://` | 🟡 Beta | High | Query syntax stable, multi-language support growing |
| `stats://` | 🟡 Beta | Medium | Metrics may be added/renamed |
| `git://` | 🟡 Beta | High | Core features stable (blame, history, diff), new query params may be added |
| `sqlite://` | 🟡 Beta | Medium | Recently added (v0.35.0), format stabilizing |
| `mysql://` | 🟡 Beta | Medium | Requires `[database]` extra, tuning ratios may change |
| `json://` | 🟡 Beta | High | Path syntax stable, query features may expand |
| `markdown://` | 🟡 Beta | Medium | Frontmatter queries stable, may add new filters |

### Project Adapters (Extensibility Examples)

**What these are:** Production-quality adapters built for specific projects/tools. They demonstrate how to extend reveal to inspect YOUR project's unique resources.

| Adapter | Purpose | Domain | Status |
|---------|---------|--------|--------|
| `reveal://` | Self-inspection (dogfooding) | Reveal codebase validation | ✅ Production-ready |
| `claude://` | AI conversation analysis | Claude Code session logs | ✅ Production-ready |

**Stability commitment:**
- ✅ Production-ready code (tested, documented, works for intended use case)
- ✅ Stable within their domain (reveal devs rely on `reveal://`, Claude users rely on `claude://`)
- ⚠️ No cross-project API guarantees (these are examples - adapt patterns to your needs)
- 💡 Study these to build adapters for YOUR project (k8s://, logs://, config://, etc.)

**Why this category?**
These adapters are **teaching implementations** that solve real problems for specific projects. They're production-quality code you can study and adapt, but they exist primarily to show extensibility patterns rather than serve universal needs.

---

## Quality Rule Stability

### Stable Rules (Won't Change)

- **B001-B005:** Bug detection (assert False, bare except, etc.)
- **S701:** Security (hardcoded passwords)
- **C901:** Cyclomatic complexity (McCabe's algorithm)
- **E501:** Line length

### Beta Rules (May Evolve)

All other rules (D, I, L, M, N, R, U, F, V series) are Beta. Thresholds may be adjusted, detection may improve, new rules may be added.

### Configuration Stability

**Stable:** `.reveal.yaml` structure, environment variable names
**Beta:** Specific config keys may be added/renamed with migration guidance

---

## Language Support Stability

### Tier 1 (Stable)

Full support, tested on production codebases, extraction quality guaranteed:
- Python, JavaScript, TypeScript, Rust, Go, Java, C, C++

### Tier 2 (Beta)

Full support, extraction quality improving, may have edge cases:
- C#, Scala, PHP, Ruby, Lua, Kotlin, Swift, Dart, HCL/Terraform, GraphQL, Protobuf, Zig, GDScript, Bash, SQL

### Tier 3 (Experimental)

Tree-sitter extraction only, basic structure, no custom analyzers:
- 165+ languages via tree-sitter-language-pack

---

## JSON Output Stability

**Current status:** 🟢 Stable (Output Contract v1.0)

**What shipped (2026-01-17):**
- Output Contract v1.0 defines consistent JSON structure across all adapters
- All 14 adapters follow predictable schemas
- `meta.extractable` field for agent discoverability
- Versioned output format

**Guarantees:**
- Core JSON structure is stable (`file`, `type`, `analyzer`, `meta` fields)
- `meta.extractable` includes `types`, `elements`, `examples`
- All adapters return consistent error formats
- Breaking changes require major version bump

---

## CLI Stability

**Stable flags:**
- `--format` (text, json, grep)
- `--check` (quality analysis)
- `--outline` (hierarchical view)
- `--stdin` (read file paths from stdin)
- `--help`, `--version`

**Beta flags:**
- `--copy` / `-c` (clipboard)
- `--frontmatter`, `--metadata`, `--semantic`, `--scripts`, `--styles` (HTML/Markdown)
- `--agent-help`, `--agent-help-full` (AI agent guides)
- `--validate-schema` (schema validation)
- `--rules`, `--explain`, `--select` (quality rules)

**Experimental flags:**
- Flags not documented in README or help text

---

## Guarantees by Use Case

### For AI Agents

**Stable:**
- `reveal <path>` → structure output format (filename:line)
- `reveal help://` → adapter discovery
- `reveal --agent-help` → usage patterns
- `reveal --format json` → JSON output (Output Contract v1.0)

**Beta:**
- Adapter query parameters (may evolve)

**Recommendation:** Both text output (`filename:line` format) and JSON output (`--format json`) are production-ready. Output Contract v1.0 shipped 2026-01-17.

### For CI/CD Pipelines

**Stable:**
- `reveal --check` exit codes (0 = pass, 1 = violations found)
- `--format=grep` output format
- `--format=json` schema (Output Contract v1.0)
- Rule selection (`--select B,S`)

**Beta:**
- Specific rule IDs (may be renamed/renumbered)

**Recommendation:** Pin reveal version in CI (`pip install reveal-cli==0.39.0`) and upgrade explicitly after testing.

### For Human Users

**Stable:**
- Basic exploration workflow (directory → file → element)
- Text output format
- Help system navigation

**Beta:**
- Advanced adapter features
- Quality rule behavior
- Configuration options

**Recommendation:** Use freely, expect minor changes in Beta features between versions.

---

## How to Check Stability

```bash
# Check what's stable in current version
reveal help://stability

# Check adapter stability
reveal help://<adapter>  # Look for "Stability: Stable/Beta/Experimental"

# Check CLI flag stability
reveal --help  # Flags marked with stability levels

# Verify output contract
reveal reveal://schema  # (Coming in Output Contract Specification)
```

---

## Questions?

- **General stability questions:** See [CONTRIBUTING.md](CONTRIBUTING.md)
- **Feature requests:** [GitHub Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)
- **Breaking change reports:** Tag issue with `breaking-change`

---

**Next review:** Q2 2026 (before v1.0 release)
**Owner:** Scott (with TIA)
