# Intent Lenses: Community-Curated Relevance for Reveal

**Status:** Design / Exploration (Post-v0.28.0)
**Target:** v0.29.0+ (Q2 2026 or later)
**Priority:** MEDIUM
**Complexity:** HIGH (requires careful SIL alignment)

**Last Updated:** 2025-12-31

---

## Executive Summary

**Problem:** Reveal excels at showing "what exists" (structure, facts, metadata), but doesn't help users discover "what matters for a given intent" (onboarding, debugging, entry points).

**Solution:** **Intent Lenses** — community-curated, typed overlays that reorder, filter, and emphasize existing Reveal output **without adding new facts or summaries**.

**Key Principle:** Borrow from `tldr`'s social abstraction (community curation), but encode it as **typed, inspectable intent metadata** — not prose.

**SIL Alignment:**
- ✅ Provenance-safe (lenses reference artifacts, never rewrite)
- ✅ Inspectable (every emphasis is explicit and reviewable)
- ✅ Grounded (all pointers map to Reveal outputs)
- ✅ Token-efficient (adds guidance, not verbosity)
- ✅ L6 Reflection layer (exposes "what matters", not "what to do")

---

## Table of Contents

1. [Design Rationale](#design-rationale)
2. [What Intent Lenses Are (and Are Not)](#what-intent-lenses-are-and-are-not)
3. [Architectural Integration](#architectural-integration)
4. [Schema Design](#schema-design)
5. [CLI Interface](#cli-interface)
6. [Implementation Strategy](#implementation-strategy)
7. [Community Model](#community-model)
8. [Success Criteria](#success-criteria)
9. [Related Work](#related-work)
10. [References](#references)

---

## Design Rationale

### The Gap: Structure vs. Relevance

**Reveal v0.27.1 (Current State):**
```bash
reveal src/
# Returns: 42 files, 15 directories, 200 functions
# Tokens: ~5,000 (complete structure)
```

**Agent's Challenge:** "Where do I start?"
- All facts are true, but no guidance on priority
- Equal emphasis on entry points, utilities, tests, config
- Agent must guess what matters for their intent

**Traditional Solution (tldr-style):**
```markdown
# Getting Started with FastAPI
1. Look at main.py (defines routes)
2. Check api/ directory (business logic)
3. See models.py (data schemas)
```

**Problem:** Prose is fragile, non-inspectable, breaks grounding.

---

### The Intent Lens Solution

**Lens-Enhanced Output:**
```bash
reveal src/ --lens=onboarding
# Returns: Same 42 files, but reordered + emphasized
# Tokens: ~5,000 (structure unchanged)
# + ~200 tokens (lens metadata)
```

**Key Insight:** Lenses don't add facts — they add **typed navigation hints**.

```json
{
  "lens": "onboarding",
  "priority": [
    {"path": "main.py", "role": "entry_point", "importance": "high"},
    {"path": "api/", "role": "core_logic", "importance": "high"},
    {"path": "tests/", "role": "validation", "importance": "medium"}
  ],
  "suppress": ["migrations/", "generated/", "__pycache__/"]
}
```

**Benefits:**
- ✅ **Typed** (not prose) - machine-readable, inspectable
- ✅ **Grounded** (references existing paths) - provenance-safe
- ✅ **Cheap** (metadata, not duplication) - token-efficient
- ✅ **Explicit** (every emphasis is visible) - transparent
- ✅ **Community-curated** (like tldr) - scales with usage

---

## What Intent Lenses Are (and Are Not)

### ✅ Intent Lenses ARE:

1. **Selection** - Which files/functions matter most for this intent?
2. **Prioritization** - What order should an agent explore?
3. **Canonicalization** - What's the typical path (not exhaustive)?
4. **Typed metadata** - Structured, inspectable, version-controlled
5. **Community knowledge** - Accumulated wisdom from users

### ❌ Intent Lenses are NOT:

1. ❌ **Summaries** - No prose explanations (that's what docs are for)
2. ❌ **New facts** - Only reorder/filter existing Reveal output
3. ❌ **AI-generated** - Human-curated, reviewed, deliberate
4. ❌ **Heuristics** - No guessing, only explicit rules
5. ❌ **Executable** - L6 reflection only (not L7 execution)
6. ❌ **Framework-specific** - Language/framework patterns, not individual projects

---

## Architectural Integration

### Layer 1: Public Core (Lens Engine)

**Location:** `reveal/lenses/`

```
reveal/
└── lenses/
    ├── __init__.py           # Lens loader + registry
    ├── engine.py             # Apply lens to Reveal output
    ├── schema.py             # Lens validation schema
    └── builtin/
        ├── onboarding.yaml   # Built-in lens: project exploration
        └── entry_points.yaml # Built-in lens: find main()
```

**Responsibilities:**
- Load lens YAML files
- Validate schema compliance
- Apply transformations (reorder, filter, emphasize)
- Return augmented JSON output

---

### Layer 2: Community Lenses (Separate Repo)

**Repository:** `reveal-lenses` (similar to `tldr-pages`)

```
reveal-lenses/
├── lenses/
│   ├── python/
│   │   ├── fastapi-onboarding.yaml
│   │   ├── django-onboarding.yaml
│   │   └── flask-debugging.yaml
│   ├── javascript/
│   │   ├── react-entry-points.yaml
│   │   └── nodejs-api-structure.yaml
│   └── rust/
│       └── cargo-project-layout.yaml
├── schemas/
│   └── lens.schema.v1.json
└── CONTRIBUTING.md
```

**Curation Model:**
- Pull requests reviewed for correctness
- No prose allowed (typed metadata only)
- Versioned schemas (breaking changes = new schema version)
- Community voting on quality

---

### Integration with Reveal's Architecture

**From ARCHITECTURAL_DILIGENCE.md:**

| Lens Component | Layer | Shipped? | Quality Standard |
|----------------|-------|----------|------------------|
| Lens engine | Layer 1 (Public Core) | ✅ Yes | Production-grade, tested |
| Built-in lenses | Layer 1 (Public Core) | ✅ Yes | High-quality, dogfooded |
| Community lenses | External repo | ❌ No | Community-curated, reviewed |
| Lens validation (V014?) | Layer 2 (Self-Validation) | ✅ Yes | Validates Reveal's own lenses |

---

## Schema Design

### Lens Schema v1.0 (Draft)

```yaml
# File: python/fastapi-onboarding.yaml
schema_version: "1.0"
lens:
  name: "fastapi-onboarding"
  description: "Explore a FastAPI project for the first time"
  applies_to:
    language: python
    framework: fastapi  # Detected via imports or pyproject.toml

  # Priority: What to explore first
  prioritize:
    - path: "main.py"
      role: "entry_point"
      importance: "critical"
      reason: "Defines application routes and startup logic"

    - path: "api/"
      role: "core_logic"
      importance: "high"
      reason: "Business logic and route handlers"

    - path: "models/"
      role: "data_schemas"
      importance: "high"
      reason: "Pydantic models define API contracts"

    - path: "tests/"
      role: "validation"
      importance: "medium"
      reason: "Shows expected behavior and usage examples"

  # Suppress: What to ignore for this intent
  suppress:
    - "migrations/"     # Database changes (not relevant to structure)
    - "alembic/"        # Migration tool (not core logic)
    - "__pycache__/"    # Generated files
    - "*.pyc"           # Compiled Python

  # Recommended exploration order (progressive disclosure)
  next_steps:
    - query: "reveal main.py"
      reason: "See application entry point and route definitions"
    - query: "reveal api/ --outline"
      reason: "Understand API structure without reading all code"
    - query: "reveal models/ --typed"
      reason: "Inspect data schemas and validation logic"
```

**Schema Properties:**

1. **`applies_to`** - When to suggest this lens (language, framework, file patterns)
2. **`prioritize`** - What to show first (paths + metadata)
3. **`suppress`** - What to hide (irrelevant for this intent)
4. **`next_steps`** - Progressive disclosure hints

---

### JSON Output Schema (Applied Lens)

When a lens is applied, Reveal's JSON output gains metadata:

```json
{
  "uri": "src/",
  "lens_applied": "fastapi-onboarding",
  "lens_version": "1.0",
  "structure": {
    "files": [
      {
        "path": "main.py",
        "size": 1234,
        "lens_metadata": {
          "role": "entry_point",
          "importance": "critical",
          "priority": 1,
          "reason": "Defines application routes and startup logic"
        }
      },
      {
        "path": "api/routes.py",
        "size": 5678,
        "lens_metadata": {
          "role": "core_logic",
          "importance": "high",
          "priority": 2
        }
      }
    ]
  },
  "next_steps": [
    {
      "query": "reveal main.py",
      "reason": "See application entry point and route definitions"
    }
  ],
  "suppressed_count": 12
}
```

**Benefits:**
- Agent can prioritize exploration (sort by `priority`)
- User can inspect reasoning (`reason` field)
- Lens is transparent (all metadata visible)
- Provenance is clear (`lens_applied` field)

---

## CLI Interface

### Minimal CLI (v0.29.0)

```bash
# Apply a lens to output
reveal src/ --lens=onboarding
reveal main.py --lens=entry_points

# List available lenses
reveal --lenses

# Show lens definition
reveal --lens-show=fastapi-onboarding

# Validate a lens file
reveal --lens-validate=my-lens.yaml
```

**Output Behavior:**

1. **Without lens:** Normal Reveal output (current behavior)
2. **With lens:** Same structure, but:
   - Files reordered by `priority`
   - Suppressed paths hidden (count shown)
   - `lens_metadata` added to JSON
   - `next_steps` appended to output

---

### Advanced CLI (v0.30.0+)

```bash
# Auto-detect best lens for project
reveal src/ --lens=auto
# Detects: FastAPI project → applies fastapi-onboarding lens

# Combine lenses (union of priorities)
reveal src/ --lens=onboarding,security

# Create a lens from usage patterns
reveal src/ --record-lens=my-workflow.yaml
# Records which files you explore → generates lens

# Community lens repository
reveal --lens-update  # Fetch latest community lenses
reveal --lens-search="django debugging"
```

---

## Implementation Strategy

### Phase 1: Core Engine (v0.29.0, ~10-15 hours)

**Goal:** Proof of concept with 2 built-in lenses

**Tasks:**
1. **Lens schema** (2 hours)
   - Define `lens.schema.v1.json`
   - YAML parser + validator

2. **Lens engine** (4 hours)
   - `LensEngine.apply(reveal_output, lens)` → augmented output
   - Priority sorting, suppression, metadata injection

3. **CLI integration** (3 hours)
   - `--lens=<name>` flag
   - `--lenses` (list available)
   - `--lens-show=<name>` (inspect lens)

4. **Built-in lenses** (4 hours)
   - `onboarding.yaml` (generic project exploration)
   - `entry_points.yaml` (find main() / startup code)

5. **Tests + docs** (3 hours)
   - Unit tests for lens engine
   - Integration tests (apply lens to test projects)
   - Update README.md with lens examples

**Deliverable:** `reveal src/ --lens=onboarding` works for any project

---

### Phase 2: Community Infrastructure (v0.30.0, ~8-12 hours)

**Goal:** Enable community-curated lenses

**Tasks:**
1. **Lens repository** (3 hours)
   - Create `reveal-lenses` repo
   - Add schema validation CI
   - Write CONTRIBUTING.md

2. **Lens discovery** (3 hours)
   - `reveal --lens-update` (fetch from repo)
   - Local cache (~/.reveal/lenses/)
   - Auto-update check (weekly)

3. **Framework detection** (4 hours)
   - Detect Python frameworks (FastAPI, Django, Flask)
   - Detect JS frameworks (React, Vue, Express)
   - Auto-suggest lenses: "Detected FastAPI, try: --lens=fastapi-onboarding"

4. **Quality gates** (2 hours)
   - V014: Validate Reveal's built-in lenses
   - CI: Validate all community lenses on PR

**Deliverable:** Community can contribute lenses via PRs

---

### Phase 3: Advanced Features (v0.31.0+, Future)

**Ideas (not committed):**

1. **Lens composition**
   - `--lens=onboarding,security` (union of both)

2. **Lens recording**
   - `--record-lens=workflow.yaml` (learn from user's exploration)

3. **Lens ranking**
   - Community upvotes/downvotes
   - Usage analytics (privacy-preserving)

4. **Project-specific lenses**
   - `.reveal/lenses/my-team-workflow.yaml` (internal use)

5. **Lens inheritance**
   - `extends: python/generic-onboarding.yaml`
   - Override specific paths

---

## Community Model

### Governance (Like tldr-pages)

**Repository:** `github.com/reveal-cli/reveal-lenses`

**Contribution Workflow:**
1. Fork repo, add lens YAML to `lenses/<language>/<name>.yaml`
2. Run `reveal --lens-validate=<file>` (schema check)
3. Submit PR with:
   - Example project it applies to
   - Reasoning for priorities
4. Maintainers review for:
   - Schema compliance
   - Scope discipline (no prose, only metadata)
   - Non-overreach (applies to pattern, not specific project)
5. Merge → available via `reveal --lens-update`

**Quality Standards:**
- ✅ **Typed metadata only** (no free-form prose)
- ✅ **Generality** (applies to framework/pattern, not one repo)
- ✅ **Inspectability** (every field has clear semantics)
- ✅ **Versioning** (lenses are versioned, schema is versioned)

**Rejected:**
- ❌ AI-generated lenses (too fragile, no grounding)
- ❌ Company-specific lenses (use private `.reveal/lenses/` instead)
- ❌ Prose summaries (breaks inspectability)

---

## Success Criteria

### Functional Requirements

**v0.29.0 (Core Engine):**
- ✅ `reveal src/ --lens=onboarding` reorders output by priority
- ✅ `reveal src/ --lens=entry_points` highlights main() functions
- ✅ `--lenses` lists available built-in lenses
- ✅ `--lens-show=onboarding` shows lens definition
- ✅ Lens metadata appears in JSON output
- ✅ Suppressed paths are hidden (count shown)

**v0.30.0 (Community):**
- ✅ `reveal --lens-update` fetches community lenses
- ✅ Framework detection suggests relevant lenses
- ✅ Community can submit lenses via PR
- ✅ V014 rule validates built-in lenses

### Quality Requirements

- ✅ 80%+ test coverage for lens engine
- ✅ Lens schema documented with examples
- ✅ Dogfooding: Reveal's own lens for contributors
- ✅ Performance: Lens application <10ms overhead
- ✅ Zero false positives in lens validation

### SIL Alignment Requirements

- ✅ **Provenance:** Every lens reference maps to real path
- ✅ **Inspectability:** Full lens definition visible via `--lens-show`
- ✅ **Grounding:** No AI-generated content, only curated metadata
- ✅ **Transparency:** User knows when lens is applied (metadata field)
- ✅ **Explicit contracts:** Lens schema is versioned, breaking changes = new version

---

## Related Work

### Comparison: Intent Lenses vs. Similar Systems

| System | Approach | Strengths | Why Lenses are Different |
|--------|----------|-----------|--------------------------|
| **tldr** | Community prose summaries | High-quality curation | Lenses: typed, inspectable, agent-friendly |
| **Starship prompts** | Context-aware UI hints | Fast, minimal | Lenses: richer metadata, framework-aware |
| **EditorConfig** | Project-local settings | Simple, universal | Lenses: community-shared, intent-driven |
| **LSP inlay hints** | IDE type annotations | Real-time, grounded | Lenses: broader scope, not just types |
| **GitHub Topics** | Repo categorization | Discoverable, social | Lenses: actionable, not just labels |

**Key Differentiator:** Lenses are **typed, versioned, community-curated metadata** that **augment (not replace) Reveal's output**.

---

## References

### Internal Documents

- **[docs/WHY_TYPED.md](../../docs/WHY_TYPED.md)** - Rationale for type-first architecture
- **[internal-docs/ARCHITECTURAL_DILIGENCE.md](../ARCHITECTURAL_DILIGENCE.md)** - Quality standards, layer definitions
- **[internal-docs/planning/TYPED_FEATURE_IDEAS.md](./TYPED_FEATURE_IDEAS.md)** - Related typed features
- **[ROADMAP.md](../../ROADMAP.md)** - Release timeline and priorities

### External Inspiration

- **tldr-pages:** Community-curated command examples (https://tldr.sh/)
- **Semantic Infrastructure Lab (SIL):** L6 Reflection layer principles
- **EditorConfig:** Community-shared project config (https://editorconfig.org/)
- **tree-sitter:** Typed AST parsing (https://tree-sitter.github.io/)

---

## Open Questions

1. **Lens conflicts:** What if two lenses prioritize different files? (Answer: Union, show both)
2. **Lens versioning:** How to handle breaking schema changes? (Answer: Semantic versioning, old lenses keep working)
3. **Private lenses:** Should companies host internal lens repos? (Answer: Yes, via `.reveal/lenses/` local dir)
4. **Auto-detection accuracy:** What if framework detection is wrong? (Answer: User can override with explicit `--lens=`)
5. **Lens performance:** Does applying 10 lenses slow down Reveal? (Answer: Benchmark required, but metadata-only should be fast)

---

## Conclusion

**Intent Lenses** bring **tldr-style community curation** to Reveal, but encode it as **typed, inspectable metadata** instead of prose.

**Alignment with SIL:**
- ✅ Provenance-safe (references, not rewrites)
- ✅ Grounded (maps to real artifacts)
- ✅ Token-efficient (metadata, not duplication)
- ✅ Transparent (every decision is visible)
- ✅ L6 Reflection (exposes relevance, not execution)

**Next Steps:**
1. Review this design with Reveal maintainers
2. Validate alignment with ARCHITECTURAL_DILIGENCE.md principles
3. Prototype lens engine (Phase 1, ~10-15 hours)
4. Dogfooding: Create `reveal-onboarding.yaml` lens for Reveal itself
5. If successful, launch community repo (Phase 2)

**One-Sentence Summary:**
> Borrow from tldr its social abstraction (community-curated relevance), but encode it as typed, inspectable intent lenses — not prose.

---

**Document Status:** ✅ Design complete, ready for review
**Next Milestone:** Post-v0.28.0 (after imports:// ships)
**Estimated Effort:** 10-15 hours (Phase 1), 8-12 hours (Phase 2)
**Strategic Value:** HIGH - Unlocks community knowledge, improves agent UX, preserves SIL principles
