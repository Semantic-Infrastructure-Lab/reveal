---
title: Reveal Stability Policy
type: documentation
category: policy
date: 2026-08-01
---

# Stability Policy

**Last updated:** 2026-08-01 (see `reveal --version` for the current release; this
policy doc is checked for adapter/language count drift by V012/V013, but its
prose — version numbers, dates, blocker status — is not machine-verified and
can still go stale between refreshes)

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
- **Quality rules (core):** B001-B005 (bugs), S701 (security), C901 (complexity), E501 (line length) — run `reveal --rules` for the full current set (55 rules as of v0.112.0, growing)
- **Languages (full support):** Python, JavaScript, TypeScript, Rust, Go, Java, C, C++ — see [Language Support Stability](#language-support-stability) below; conformance is now tracked per-language via `reveal --language-info <lang>` (BACK-444), not a hand-maintained tier list

**Backward compatibility:** Guaranteed within major versions (v0.x → v0.y is safe for stable features).

---

### 🟡 Beta

**Guarantee:** Feature-complete but API may evolve. Changes announced in CHANGELOG with migration guidance.

**What's Beta:**
- **Code/data-navigation adapters:**
  - `diff://` - Semantic structural comparison
  - `imports://` - Import graph analysis
  - `calls://` - Cross-file call graph queries
  - `depends://` - Inverse module dependency graph
  - `sqlite://` - SQLite database inspection
  - `mysql://` - MySQL database inspection
  - `stats://` - Code quality metrics
  - `json://` - JSON navigation
  - `markdown://` - Frontmatter queries
  - `git://` - Git repository inspection
  - `xlsx://` - Excel spreadsheet inspection
- **Infra/ops adapters** (production-quality, domain-scoped — cPanel/hosting stack): `nginx://`, `ssl://`, `letsencrypt://`, `autossl://`, `cpanel://`, `domain://`
- **Session-analysis adapters:** `claude://` (Claude Code sessions), `codex://` (OpenAI Codex CLI sessions)
- **Test-hygiene adapters:** `patches://` (mock/patch pressure scanning)
- **Quality rules (extended):** the majority of the current 55-rule set (D, I, L, M, N, R, T, U, F, V series) — run `reveal --rules` for the live list; only the core set above is Stable
- **Languages (full support):** C#, Scala, PHP, Ruby, Lua, Kotlin, Swift, Dart, HCL/Terraform, GraphQL, Protobuf, Zig, GDScript, Bash, SQL — see `reveal --languages` for the current full roster (87 languages total across explicit analyzers + tree-sitter fallback, growing)
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
- Internal V-series rules (self-validation only, hidden by default — pass `--all` to `reveal --rules` to see them; the set has grown well past the original V016-V022 range, now up to V030+)
- Undocumented query parameters on adapters
- Features marked "experimental" in help text
- Languages with only tree-sitter extraction (basic structure only, no dedicated analyzer — run `reveal --languages` for the live "Tree-sitter Fallback" list)

**Expectations:** Use at your own risk. Test thoroughly before depending on experimental features.

---

## Version Policy

### Current Status: Beta (Pre-v1.0)

**Semver interpretation for pre-v1.0:**
- **Patch (v0.36.0 → v0.36.1):** Bug fixes only, no breaking changes
- **Minor (v0.36 → v0.37):** New features, may include breaking changes in Beta features
- **Major (v0 → v1):** Stability commitment - Stable features frozen, breaking changes announced 3+ months in advance

### Path to v1.0

**Blockers for v1.0:**
1. ✅ Output contract specification (structured return values) - **COMPLETE** (2026-01-17)
2. ✅ JSON schema versioning - **COMPLETE** (2026-01-17, via Output Contract v1.0)
3. 🟡 Comprehensive integration test suite - **IN PROGRESS** (11,600+ tests passing as of v0.112.0, expanding coverage; Output Contract v1.1 rollout to remaining analyzers still open, see ROADMAP.md)
4. 🟡 Documentation completeness (all adapters have help:// guides) - **IN PROGRESS** (V024 now lints this — `reveal reveal:// --check --select V024` is clean as of this writing, i.e. every registered adapter has a guide)
5. ❌ 6 months without breaking changes to Stable features - **NOT MET, window reset**: the original 2026-01-17 start was invalidated by a Stable-tier breaking change on 2026-05-22 (v0.95.0, tree-sitter-language-pack 1.x migration — dropped Alpine/musl and Ubuntu 20.04/Debian 11 support for all Tier-1 languages). No further breaking changes to Stable features have landed since; the clean window is running from 2026-05-22, not from January. Verify via `grep -A2 "^### Breaking Changes" CHANGELOG.md` before trusting this without a re-check.

**Current progress:** 2/5 complete outright (Output Contract, JSON versioning), 2/5 in progress (tests, docs), 1/5 blocked on a clean 6-month window that has not yet elapsed.

**Estimated timeline:** not before 2026-11-22 (earliest the reset 6-month window closes), and only if no further Stable-tier breaking change lands before then. Treat any specific quarter estimate in older docs/sessions as stale.

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

| Adapter | Stability | Notes |
|---------|-----------|-------|
| `diff://` | 🟡 Beta | Output format may change, git:// integration stable |
| `imports://` | 🟡 Beta | Query syntax stable, multi-language support growing |
| `calls://` | 🟡 Beta | Query syntax stable; multi-language coverage still expanding |
| `depends://` | 🟡 Beta | Inverse of imports:// — same maturity profile |
| `stats://` | 🟡 Beta | Metrics may be added/renamed |
| `git://` | 🟡 Beta | Core features stable (blame, history, diff), new query params may be added |
| `sqlite://` | 🟡 Beta | Format stabilizing |
| `mysql://` | 🟡 Beta | Requires `[database]` extra, tuning ratios may change |
| `json://` | 🟡 Beta | Path syntax stable, query features may expand |
| `markdown://` | 🟡 Beta | Frontmatter queries stable, may add new filters |
| `xlsx://` | 🟡 Beta | Spreadsheet/PowerPivot/PowerQuery support, format-dependent edge cases |

Run `reveal --adapters` for the authoritative, current list — this table is
illustrative, not exhaustive.

### Infra & Project Adapters (Extensibility Examples)

**What these are:** Production-quality adapters built for specific projects/tools/domains. They demonstrate how to extend reveal to inspect YOUR project's unique resources, and several (the cPanel/hosting-stack group) are genuinely domain-specific rather than universal.

| Adapter | Purpose | Domain | Status |
|---------|---------|--------|--------|
| `reveal://` | Self-inspection (dogfooding) | Reveal codebase validation | ✅ Production-ready |
| `claude://` | AI conversation analysis | Claude Code session logs | ✅ Production-ready |
| `codex://` | AI conversation analysis | OpenAI Codex CLI session logs | ✅ Production-ready |
| `nginx://` | Vhost config inspection | nginx | ✅ Production-ready |
| `ssl://` | Certificate health/chain | TLS certs | ✅ Production-ready |
| `letsencrypt://` | Cert inventory, orphan/duplicate SAN detection | Let's Encrypt | ✅ Production-ready |
| `autossl://` | AutoSSL run log inspection | cPanel | ✅ Production-ready |
| `cpanel://` | User environment inspection | cPanel | ✅ Production-ready |
| `domain://` | DNS/registration/health | Domain names | ✅ Production-ready |
| `patches://` | Mock/patch pressure scanning | Test hygiene (Python/JS/TS) | ✅ Production-ready |

**Stability commitment:**
- ✅ Production-ready code (tested, documented, works for intended use case) — enforced by `V024` (every registered adapter needs a guide) and `V025` (must appear in `help://relationships`)
- ✅ Stable within their domain (reveal devs rely on `reveal://`, Claude users rely on `claude://`, ops workflows rely on the cPanel-stack adapters)
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

All other rules (B006+, C902/C905, D, I, L, M, N, R, T, U, F, V series) are Beta. Thresholds may be adjusted, detection may improve, new rules may be added. Run `reveal --rules` for the current full set (55 rules as of v0.112.0, 2 opt-in) with per-rule language verification status (BACK-432); pass `--all` to also see the internal V-series self-check rules, which are Experimental (below), not Beta.

### Configuration Stability

**Stable:** `.reveal.yaml` structure, environment variable names
**Beta:** Specific config keys may be added/renamed with migration guidance

---

## Language Support Stability

The three broad bands below (Tier 1/2/3) still describe the *policy* — how much
you can rely on each group — but the authoritative per-language conformance
data now comes from `reveal --language-info <lang>` (BACK-444), which reports
one of four verified levels: `tier1-verified` > `smoke-tested` >
`structure-only` > `untested`. Treat any language list below as illustrative;
the live command is the source of truth and can only grow more precise over
time, not this doc.

### Tier 1 (Stable)

Full support, tested on production codebases, extraction quality guaranteed:
- Python, JavaScript, TypeScript, Rust, Go, Java, C, C++

### Tier 2 (Beta)

Full support, extraction quality improving, may have edge cases (several have
known tree-sitter grammar bugs tracked as open `tt` tickets, e.g. Kotlin
`BACK-738`, C# `BACK-703`, Swift `BACK-742` — these are honest-declined
grammar limitations, not reveal bugs):
- C#, Scala, PHP, Ruby, Lua, Kotlin, Swift, Dart, HCL/Terraform, GraphQL, Protobuf, Zig, GDScript, Bash, SQL

### Tier 3 (Experimental)

Tree-sitter extraction only, basic structure, no custom analyzers — run
`reveal --languages` for the live "Tree-sitter Fallback" list (count varies as
languages get promoted to Tier 2 with a dedicated analyzer).

---

## JSON Output Stability

**Current status:** 🟢 Stable (Output Contract v1.0)

**What shipped (2026-01-17):**
- Output Contract v1.0 defines consistent JSON structure across all adapters
- All adapters follow predictable schemas
- `meta.extractable` field for agent discoverability
- Versioned output format

**Guarantees:**
- Core JSON structure is stable (`file`, `type`, `analyzer`, `meta` fields)
- `meta.extractable` includes `types`, `elements`, `examples`
- All adapters return consistent error formats
- Breaking changes require major version bump

**Known gap (in progress, not yet uniform):** Output Contract v1.1
(`meta.parse_mode`/`meta.confidence`) is rolling out per-analyzer via
`ResultBuilder.create(..., contract_version='1.1')`, but a majority of
analyzers are still hardcoded at `contract_version: '1.0'` with no `meta`
block — tracked as `BACK-885` (large effort, open). Don't assume every
adapter carries v1.1 fields yet; check the specific adapter's output or
`grep contract_version` in its source.

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
- `--agent-help` (AI agent guide)
- `--validate-schema` (schema validation)
- `--rules`, `--explain`, `--select` (quality rules)
- `--provenance` (attach execution metadata to JSON output — added v0.111.0)
- `--capabilities`, `--show-ast`, `--language-info`, `--discover` (agent-facing introspection)
- `--format typed` (typed JSON with types/relationships — newer than plain `json`, may still evolve)

Run `reveal --help-all` for the complete current flag surface — this list
covers the ones worth calling out, not every flag.

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

**Recommendation:** Pin reveal version in CI (`pip install reveal-cli==<current version>` — see `reveal --version` or [PyPI](https://pypi.org/project/reveal-cli/)) and upgrade explicitly after testing.

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
# This policy doc is not (yet) exposed through help:// — read it directly,
# or from an agent session: reveal STABILITY.md

# Check what's currently registered/live (adapter help pages do not carry
# a "Stability:" field today — use the live registry commands instead)
reveal --adapters              # registered adapters
reveal --rules                 # registered quality rules, with per-language verification tags
reveal --languages             # language support, explicit analyzers vs tree-sitter fallback
reveal --language-info <lang>  # per-language conformance tier (tier1-verified/smoke-tested/structure-only/untested)

# Check CLI flag surface
reveal --help-all

# Output contract details
reveal help://output            # OUTPUT_CONTRACT.md
reveal help://contract-versions # CONTRACT_VERSIONS.md
```

---

## Questions?

- **General stability questions:** See [CONTRIBUTING.md](CONTRIBUTING.md)
- **Feature requests:** [GitHub Issues](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)
- **Breaking change reports:** Tag issue with `breaking-change`

---

**Next review:** opportunistically, or whenever a v1.0 blocker status changes (see Path to v1.0 above) — this doc drifted ~4 months and ~70 releases undetected last time (`BACK-886`); don't let it go that long again
**Owner:** Semantic Infrastructure Lab
