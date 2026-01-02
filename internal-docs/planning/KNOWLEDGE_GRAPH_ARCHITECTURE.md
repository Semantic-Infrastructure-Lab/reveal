---
title: "Reveal Knowledge Graph Architecture"
date: 2026-01-01
session_id: prairie-snow-0101
project: reveal
type: technical-architecture
beth_topics:
  - reveal
  - knowledge-graphs
  - architecture
  - schema-validation
  - progressive-disclosure
  - metadata
related_docs:
  - ./KNOWLEDGE_GRAPH_PROPOSAL.md
  - ./KNOWLEDGE_GRAPH_GUIDE.md
  - ../../ROADMAP.md
status: active-planning
---

# Reveal as a Generic Knowledge Graph Tool

**Strategic Design Document**
**Version**: 1.0
**Date**: 2026-01-01
**Purpose**: Position Reveal as a generic progressive disclosure tool with knowledge graph capabilities

---

## Table of Contents

1. [Vision](#vision)
2. [Generic Patterns Analysis](#generic-patterns-analysis)
3. [Architectural Principles](#architectural-principles)
4. [Feature Design](#feature-design)
5. [Reference Implementations](#reference-implementations)
6. [Implementation Roadmap](#implementation-roadmap)

---

## Vision

**Current State**: Reveal is a progressive disclosure tool that extracts front matter from markdown files.

**Target State**: Reveal is a **generic knowledge management enabler** that:
- Supports ANY metadata schema (not just Beth)
- Enables knowledge graph patterns (linking, validation, traversal)
- Ships with reference implementations (Beth, Obsidian-style, Hugo-style)
- Maintains architectural purity (stateless, file-focused)

**Key Insight**: Front matter + document linking is a **universal pattern** across:
- Static site generators (Hugo, Jekyll, VuePress)
- Note-taking tools (Obsidian, Roam, Logseq)
- Documentation systems (Docusaurus, MkDocs)
- Knowledge bases (Notion, Confluence)
- Research tools (Zotero, Beth)

Reveal should support these patterns **generically**, not as Beth-specific features.

---

## Generic Patterns Analysis

### Pattern 1: Metadata Schemas (Universal)

**Tools doing this**:
- **Hugo**: Front matter with taxonomies (`tags`, `categories`, `series`)
- **Jekyll**: YAML front matter with custom fields
- **Obsidian**: Properties (tags, aliases, date)
- **Beth**: Weighted fields (`beth_topics`, `related_docs`, `session_id`)

**Generic abstraction**:
```yaml
# Schema definition (user-provided or built-in)
schemas:
  hugo:
    required: [title, date]
    optional: [tags, categories, series]
    list_fields: [tags, categories]

  obsidian:
    required: [title]
    optional: [tags, aliases, cssclass]
    list_fields: [tags, aliases]

  beth:
    required: [session_id, beth_topics]
    optional: [related_docs, tags, summary]
    list_fields: [beth_topics, tags, related_docs]

    # Beth-specific: field weights (for validation, not scoring)
    field_priorities:
      session_id: tier1  # 3.0x in Beth
      beth_topics: tier2  # 2.5x in Beth
      tags: tier3         # 2.0x in Beth
```

**Reveal's role**:
- Extract front matter (✅ already does this)
- Validate against schema (❌ new feature)
- Document schema patterns (❌ new guide)

---

### Pattern 2: Document Linking (Universal)

**Tools doing this**:
- **Obsidian**: `[[wiki-links]]` and front matter `related: [doc1, doc2]`
- **Roam**: Block references `((ref))` and page links
- **Beth**: `related_docs: [path1, path2]` in front matter
- **Hugo**: `related: [/posts/foo]` or taxonomy linking

**Generic abstraction**:
```yaml
# Link field config (user-provided or auto-detected)
link_fields:
  - related_docs      # Beth-style
  - related           # Hugo-style
  - aliases           # Obsidian-style
  - see_also          # Generic
  - references        # Academic

# Auto-detect: any field ending in _docs, _links, _files, _refs
auto_detect_patterns:
  - "*_docs"
  - "*_links"
  - "*_files"
  - "*_refs"
```

**Reveal's role**:
- Extract link fields from front matter (✅ already does this)
- Follow links to show structure (❌ new feature)
- Validate link targets exist (❌ new feature)
- Limit traversal depth (stateless constraint)

---

### Pattern 3: Knowledge Graph Scoring (Tool-Specific)

**Tools doing this**:
- **Beth**: PageRank with relationship count + keyword weighting
- **Obsidian**: Graph view with link density
- **Roam**: Backlink count
- **Google**: PageRank

**Generic abstraction**:
**Reveal DOES NOT do this** - it's corpus-level analysis requiring stateful indexing.

**Why**:
- Violates stateless architecture
- Requires full corpus scan
- Tool-specific algorithms (PageRank vs other metrics)

**Instead**: Reveal provides the **raw material** (metadata, links) that scoring systems consume.

---

### Pattern 4: Progressive Disclosure (Universal)

**This is Reveal's core competency**:
- Orient: `reveal file.md` (structure only)
- Navigate: `reveal file.md --outline` (hierarchical view)
- Focus: `reveal file.md "Section"` (specific content)

**Extension for knowledge graphs**:
- Orient: `reveal file.md --related` (show related docs structure)
- Navigate: `reveal file.md --related --depth 2` (follow links)
- Focus: `reveal file.md --validate` (check metadata quality)

---

## Architectural Principles

### 1. **Stateless by Design**

Reveal operates on **explicit inputs** (files, globs, URIs), never maintains an index.

**Implications**:
- ✅ Can show structure of `related_docs` (read paths, show structure)
- ✅ Can validate front matter against schema (file-local check)
- ❌ Cannot compute PageRank (requires corpus index)
- ❌ Cannot find all backlinks (requires reverse index)

**Boundary**: Reveal stops where indexing begins. That's where Beth/Obsidian/etc take over.

---

### 2. **Schema-Agnostic Core, Schema-Aware Extensions**

Core extraction is schema-agnostic (parses any YAML), extensions provide schema awareness.

**Implementation**:
```python
# Core (already exists)
reveal file.md --frontmatter  # Extract any front matter

# Extension (new)
reveal file.md --validate-schema hugo      # Validate against Hugo schema
reveal file.md --validate-schema beth      # Validate against Beth schema
reveal file.md --validate-schema custom.yaml  # User-provided schema
```

**Ships with schemas**: `beth.yaml`, `hugo.yaml`, `obsidian.yaml`, `jekyll.yaml`

---

### 3. **Link Following with Depth Limits**

Reveal can follow `related_docs` links, but with strict depth limits to avoid becoming a graph crawler.

**Constraint**: Max depth = 2 (current file + one hop + one more hop)

**Rationale**:
- Depth 1: Show immediate neighbors (useful)
- Depth 2: Show neighborhood (still useful)
- Depth 3+: Becomes graph traversal (use Beth/dedicated tool)

**Implementation**:
```bash
reveal file.md --related           # Depth 1 (immediate links)
reveal file.md --related --depth 2 # Depth 2 (links of links)
reveal file.md --related --depth 3 # ERROR: Max depth is 2
```

---

### 4. **Examples Over Specificity**

Don't build "Beth mode" or "Obsidian mode" - build **generic features** and document **patterns**.

**Anti-pattern**:
```bash
reveal file.md --beth-validate    # Too specific
reveal file.md --obsidian-graph   # Too specific
```

**Better**:
```bash
reveal file.md --validate-schema beth      # Generic schema validation
reveal file.md --related --depth 2         # Generic link following
```

**Documentation**: Show how to use generic features for specific tools:
- `KNOWLEDGE_GRAPH_GUIDE.md`: Generic patterns
- `BETH_INTEGRATION.md`: Beth-specific examples
- `OBSIDIAN_INTEGRATION.md`: Obsidian-specific examples

---

## Feature Design

### Feature 1: Schema-Based Validation

**User Experience**:
```bash
# Use built-in schema
reveal README.md --validate-schema beth

# Output:
✅ Front matter present (lines 1-12)
✅ Required fields: session_id, beth_topics
✅ Field types correct
⚠️  F003: Using 'topics:' instead of 'beth_topics:'
❌ F004: 'beth_topics' is not a list (expected: list, got: string)

# Use custom schema
reveal README.md --validate-schema .reveal-schema.yaml

# No schema validation (just extract)
reveal README.md --frontmatter
```

**Schema File Format** (`.reveal-schema.yaml`):
```yaml
name: "Beth Front Matter Schema"
version: "1.0"

required_fields:
  - session_id
  - beth_topics

optional_fields:
  - related_docs
  - tags
  - summary
  - title
  - project

field_types:
  session_id: string
  beth_topics: list
  related_docs: list
  tags: list
  summary: string
  title: string
  project: string

validation_rules:
  # Custom validation rules
  - code: F001
    description: "Front matter must start at line 1"
    check: frontmatter_position == 1

  - code: F003
    description: "Use 'beth_topics' not 'topics'"
    check: not ("topics" in fields and "beth_topics" not in fields)

  - code: F004
    description: "beth_topics must be a list"
    check: isinstance(beth_topics, list)
```

**Built-in Schemas** (ship with reveal):
- `beth`: Beth/TIA schema (as above)
- `hugo`: Hugo front matter
- `jekyll`: Jekyll front matter
- `obsidian`: Obsidian properties
- `minimal`: Just title + date (generic)

---

### Feature 2: Related Documents Viewer

**User Experience**:
```bash
# Show immediate related docs
reveal README.md --related

# Output:
File: README.md
Related docs (3):

  1. ../session-1210/README.md
     Headings (8):
       - Session Summary
       - Implementation Details
       - Files Modified
     Frontmatter:
       beth_topics: [reveal, markdown, testing]
       session_id: session-1210

  2. /docs/BETH_GUIDE.md
     Headings (39):
       - Quick Reference
       - Field Names Beth Recognizes

  3. /docs/REVEAL_ARCHITECTURE.md
     Headings (15):
       - Two-System Architecture
       - Progressive Disclosure

# Follow links recursively (max depth 2)
reveal README.md --related --depth 2

# Output includes:
File: README.md
  → ../session-1210/README.md
      → ../session-1209/README.md  (referenced by session-1210)
      → /docs/SESSION_GUIDE.md
  → /docs/BETH_GUIDE.md
      → /docs/FRONT_MATTER_SPEC.md
```

**Configuration** (optional `.revealrc`):
```yaml
# Configure which front matter fields contain links
related_fields:
  - related_docs   # Default
  - see_also
  - references

# Auto-detect patterns
auto_detect_link_fields: true  # Finds *_docs, *_links, *_refs

# Max depth for --related (default: 2)
max_related_depth: 2
```

---

### Feature 3: Markdown URI Adapter (Metadata Querying)

**User Experience**:
```bash
# Find all markdown files with specific front matter
reveal markdown://sessions/?beth_topics=reveal

# Output:
Found 23 markdown files matching: beth_topics=reveal

  1. sessions/stormy-gust-1213/README.md
     beth_topics: [reveal, front-matter, markdown]
     session_id: stormy-gust-1213

  2. sessions/emerald-crystal-1210/README.md
     beth_topics: [reveal, semantic, integration]

# Multiple criteria
reveal markdown://sessions/?beth_topics=reveal&type=production

# Missing field check
reveal markdown://?!beth_topics  # Files missing beth_topics

# Combine with other features
reveal markdown://?session_id=*-1213 --related
```

**Implementation**: New adapter `reveal/adapters/markdown.py`

**Scope**: Local directory tree (not corpus-wide index like Beth)

---

### Feature 4: Knowledge Graph Quality Checks

**User Experience**:
```bash
# Check front matter quality
reveal README.md --check-metadata

# Output:
✅ Front matter present
✅ Required fields complete (if schema provided)
⚠️  Low graph connectivity: 0 related_docs (consider adding 2-5)
⚠️  No beth_topics (document won't be discoverable)
✅ Well-formed YAML

# Aggregate quality report
reveal sessions/**/*.md --check-metadata --summary

# Output:
Checked 3,377 files:
  ✅ 3,200 have front matter (94.8%)
  ⚠️  177 missing front matter
  ✅ 2,950 have beth_topics (87.4%)
  ⚠️  427 missing beth_topics
  ⚠️  1,200 have 0 related_docs (35.5% - low connectivity)
```

**Quality Metrics** (configurable):
- Front matter presence
- Required fields (schema-based)
- Link density (related_docs count)
- Topic coverage (beth_topics or equivalent)

---

## Reference Implementations

### Beth Integration (TIA/SIL)

**Schema**: `beth.yaml` (ships with reveal)
```yaml
name: "Beth Knowledge Graph Schema"
version: "1.0"

required_fields:
  - session_id
  - beth_topics

field_priorities:
  session_id: 3.0    # Tier 1
  beth_topics: 2.5   # Tier 2
  tags: 2.0          # Tier 3
  title: 1.5
  summary: 1.0

validation_rules:
  - code: F001
    description: "Front matter must start at line 1"
  - code: F002
    description: "Malformed YAML syntax"
  - code: F003
    description: "Use 'beth_topics' not 'topics'"
  - code: F004
    description: "beth_topics must be a list"
  - code: F005
    description: "Missing required field: session_id or beth_topics"
```

**Workflows**:
```bash
# Create session README with validation
reveal README.md --validate-schema beth

# Check link graph
reveal README.md --related --depth 2

# Find all sessions about reveal
reveal markdown://sessions/?beth_topics=reveal

# Aggregate quality
reveal sessions/**/*.md --check-metadata --summary
```

---

### Obsidian Integration (Generic Note-Taking)

**Schema**: `obsidian.yaml` (ships with reveal)
```yaml
name: "Obsidian Properties Schema"
version: "1.0"

optional_fields:
  - tags
  - aliases
  - cssclass
  - created
  - modified

field_types:
  tags: list
  aliases: list
  cssclass: string
  created: date
  modified: date
```

**Workflows**:
```bash
# Validate Obsidian note
reveal note.md --validate-schema obsidian

# Find notes by tag
reveal markdown://vault/?tags=project

# Show note graph
reveal note.md --related
```

---

### Hugo Integration (Static Sites)

**Schema**: `hugo.yaml` (ships with reveal)
```yaml
name: "Hugo Front Matter Schema"
version: "1.0"

required_fields:
  - title
  - date

optional_fields:
  - draft
  - tags
  - categories
  - series
  - description

field_types:
  title: string
  date: date
  draft: boolean
  tags: list
  categories: list
  series: list
```

**Workflows**:
```bash
# Validate Hugo post
reveal content/posts/my-post.md --validate-schema hugo

# Find all posts in series
reveal markdown://content/?series=tutorial

# Check taxonomy usage
reveal content/**/*.md --check-metadata --summary
```

---

## Implementation Roadmap

### Phase 1: Foundation (v0.29.0)
**Target**: Jan 2025
**Goal**: Schema validation framework

- [ ] Schema file format design (`reveal/schemas/*.yaml`)
- [ ] Built-in schemas: `beth.yaml`, `hugo.yaml`, `obsidian.yaml`
- [ ] `--validate-schema <name|path>` CLI flag
- [ ] Validation rule engine (F001-F005 for Beth)
- [ ] Error reporting format
- [ ] Tests (50+ covering all built-in schemas)
- [ ] Docs: `SCHEMA_VALIDATION_GUIDE.md`

**Deliverable**: `reveal file.md --validate-schema beth`

---

### Phase 2: Link Following (v0.30.0)
**Target**: Feb 2025
**Goal**: Related docs viewer

- [ ] `--related` CLI flag
- [ ] `--depth N` parameter (max 2)
- [ ] Link field detection (config + auto-detect)
- [ ] Recursive structure extraction
- [ ] Output formatting (tree view)
- [ ] `.revealrc` config file support
- [ ] Tests (30+ covering depth limits, cycles, missing files)
- [ ] Docs: Update `MARKDOWN_GUIDE.md` with `--related`

**Deliverable**: `reveal file.md --related --depth 2`

---

### Phase 3: Metadata Querying (v0.31.0)
**Target**: Mar 2025
**Goal**: Markdown URI adapter

- [ ] New adapter: `reveal/adapters/markdown.py`
- [ ] Query parser (`?field=value&field2=value2`)
- [ ] Glob + filter implementation
- [ ] Missing field checks (`!field`)
- [ ] Wildcard support (`session_id=*-1213`)
- [ ] Integration with `--related`, `--validate`
- [ ] Tests (40+ covering query combinations)
- [ ] Docs: `MARKDOWN_ADAPTER_GUIDE.md`

**Deliverable**: `reveal markdown://?beth_topics=reveal`

---

### Phase 4: Quality Checks (v0.32.0)
**Target**: Apr 2025
**Goal**: Knowledge graph quality metrics

- [ ] `--check-metadata` CLI flag
- [ ] Quality metrics framework
- [ ] Aggregate reporting (`--summary`)
- [ ] Configurable thresholds
- [ ] Integration with schemas
- [ ] Link density analysis
- [ ] Tests (20+ covering metrics)
- [ ] Docs: `KNOWLEDGE_GRAPH_QUALITY_GUIDE.md`

**Deliverable**: `reveal sessions/**/*.md --check-metadata --summary`

---

### Phase 5: Documentation & Integration (v0.33.0)
**Target**: May 2025
**Goal**: Complete knowledge graph story

- [ ] **New Guide**: `KNOWLEDGE_GRAPH_GUIDE.md` (this document, refined)
- [ ] **Beth Integration**: `BETH_INTEGRATION_GUIDE.md`
- [ ] **Obsidian Integration**: `OBSIDIAN_INTEGRATION_GUIDE.md`
- [ ] **Hugo Integration**: `HUGO_INTEGRATION_GUIDE.md`
- [ ] Update `AGENT_HELP.md` with knowledge graph patterns
- [ ] Update `README.md` with use cases
- [ ] Video tutorial (5-10 min)

**Deliverable**: Complete knowledge graph documentation suite

---

## Success Metrics

### Adoption Metrics
- [ ] 3+ different schema types in use (Beth, Hugo, Obsidian)
- [ ] 10+ custom schemas created by users
- [ ] 5+ blog posts about using Reveal for knowledge graphs

### Technical Metrics
- [ ] Schema validation: <50ms for typical file
- [ ] `--related --depth 2`: <500ms for 10 files
- [ ] `markdown://` queries: <2s for 1000 files
- [ ] Zero breaking changes to existing API

### Quality Metrics
- [ ] 200+ tests covering new features
- [ ] 100% test coverage on validation logic
- [ ] Documentation examples for each use case
- [ ] Zero security issues (YAML parsing, path traversal)

---

## FAQ

### Q: Why not build full graph traversal into Reveal?

**A**: Architectural purity. Reveal is **stateless** - it operates on explicit inputs without maintaining an index. Graph traversal requires:
- Full corpus scanning
- Reverse index (backlinks)
- Ranking algorithms

These belong in **stateful tools** like Beth, Obsidian's graph view, or dedicated knowledge graph systems.

**Reveal's role**: Provide the **raw material** (metadata extraction, link validation) that graph systems consume.

---

### Q: How is this different from just using Beth?

**A**: Beth is **corpus-specific** (TIA ecosystem) and **stateful** (maintains index). Reveal is:
- **Generic**: Works with any front matter schema
- **Stateless**: No index, operates on explicit file inputs
- **Portable**: Works without TIA/Beth infrastructure

**Relationship**: Reveal → extracts metadata → Beth indexes it → Beth provides discovery

---

### Q: What about Obsidian Graph View?

**A**: Obsidian's graph is **visual + interactive**. Reveal is **CLI + scriptable**. Different use cases:
- **Obsidian**: Interactive exploration, note-taking UX
- **Reveal**: CI/CD validation, CLI workflows, AI agent tooling

**Complement**: Use both - Obsidian for authoring, Reveal for automation.

---

### Q: Will this bloat Reveal?

**A**: No. Features are **opt-in** and follow existing patterns:
- `--frontmatter`: Already exists (v0.23.0)
- `--validate-schema`: New, opt-in
- `--related`: New, opt-in
- `markdown://`: New URI adapter (same pattern as `ast://`, `json://`, etc.)

**Core remains unchanged**: `reveal file.py` still shows structure, no knowledge graph features involved.

---

## Conclusion

**Vision**: Reveal becomes the **CLI tool for knowledge graph construction** - generic, portable, composable.

**Strategy**:
1. Build **generic features** (schema validation, link following, metadata queries)
2. Ship **reference implementations** (Beth, Hugo, Obsidian schemas)
3. Document **patterns** (guides for each ecosystem)

**Architecture**: Maintain stateless design - Reveal **extracts and validates**, doesn't **index and score**.

**Timeline**: 5 releases over 5 months (Jan-May 2025)

**Success**: When users say "I use Reveal to validate my Hugo front matter" or "Reveal caught my broken Obsidian links in CI" - **not just** "Reveal is for Beth/TIA".

---

**Next Steps**: Review this design doc, then implement Phase 1 (Schema Validation).
