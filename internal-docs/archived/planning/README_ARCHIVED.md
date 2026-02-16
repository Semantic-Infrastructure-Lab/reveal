# Archived Planning Documents

**Archive Date:** 2026-01-10
**Reason:** Historical planning docs superseded by PRIORITIES.md

---

## Why Archived?

These planning documents represented earlier strategic thinking (Dec 2025 - Jan 2026) but have been superseded by:

1. **PRIORITIES.md** (in `external-git/internal-docs/planning/`) - The current authoritative roadmap
2. **Reality** - Many planned features either shipped or were explicitly deprioritized

---

## Documents in This Archive

### ADVANCED_URI_SCHEMES.md
**Status:** Mostly obsolete
- `diff://` adapter - ✅ **Shipped** (v0.30.0)
- `query://`, `semantic://`, `trace://`, `live://`, `merge://` - ❌ **Killed** (unclear value, marked in PRIORITIES.md)
- `time://` (git history) - Partial via `diff://git://` support
- Original date: Dec-Jan 2025

### PRACTICAL_CODE_ANALYSIS_ADAPTERS.md
**Status:** Obsolete (planned features deprioritized)
- `architecture://` adapter - **Deprioritized** (complex, unclear ROI, use `imports://` + `stats://` instead)
- `calls://` adapter (dead code) - **Deferred** post-v1.0 (requires full call graph analysis)
- Original plan: v0.32-v0.34 timeframe
- Reality: v0.32.2 shipped without these, they're not blocking v1.0

### GITHUB_ISSUES_FROM_TESTING.md
**Status:** Historical test results
- Test results from popular repos (Django, Flask, FastAPI, Requests)
- Original date: Jan 4, 2026
- **Action needed:** Re-test on v0.32.2 and file actual GitHub issues for confirmed bugs

---

## Still-Active Planning Docs

These documents remain in the parent directory (`../`) because they're still relevant:

- **AST_QUERY_PATTERNS.md** - Living cookbook of ast:// query patterns (gold standard)
- **AST_MIGRATION_ROADMAP.md** - Active migration plan (Phase 5 pending: nginx crossplane decision)
- **URI_ADAPTER_COMPOSABILITY.md** - Architectural foundation (still canonical)
- **PLANNING_DOCS_ASSESSMENT.md** - The assessment that led to this archive (2026-01-10)

---

## Current Roadmap

**See:** `external-git/internal-docs/planning/PRIORITIES.md`

**Summary:**
- **Tier 1 (ship soon):** Kotlin/Swift/Dart, sqlite://, Terraform, auto-fix for rules
- **Tier 2 (next quarter):** git:// (history/blame), GraphQL, Protobuf, K8s YAML
- **Tier 3:** PostgreSQL, Docker, image metadata, --watch, LSP
- **Explicitly Killed:** query://, semantic://, trace://, live://, merge://, --check-metadata

---

**These documents are preserved for historical reference and learning. Do not update them.**
