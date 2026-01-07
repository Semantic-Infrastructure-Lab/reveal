---
title: "Building Knowledge Graphs with Reveal"
date: 2026-01-01
session_id: prairie-snow-0101
project: reveal
type: user-guide
beth_topics:
  - reveal
  - knowledge-graphs
  - documentation
  - front-matter
  - hugo
  - obsidian
  - beth
related_docs:
  - ./KNOWLEDGE_GRAPH_PROPOSAL.md
  - ./KNOWLEDGE_GRAPH_ARCHITECTURE.md
  - ../../ROADMAP.md
status: ready-for-implementation
ships_as: "reveal help://knowledge-graph"
---

<!-- Source: KNOWLEDGE_GRAPH_GUIDE.md | Type: User Guide | Access: reveal help://knowledge-graph -->

# Building Knowledge Graphs with Reveal

## Overview

Reveal helps you build and maintain **personal knowledge graphs** using YAML front matter in markdown files. Whether you're building a digital garden, documenting a codebase, or organizing research notes, Reveal provides tools for:

- **Metadata validation** - Ensure front matter follows your schema
- **Link discovery** - Find and validate document relationships
- **Quality checks** - Maintain knowledge graph health
- **Progressive exploration** - Navigate relationships without getting lost

**Philosophy**: Reveal extracts and validates structure. You (or dedicated tools like Beth, Obsidian, etc.) provide the semantics and scoring.

---

## Quick Start

### Basic Front Matter Extraction

```bash
# Extract front matter from any markdown file
reveal README.md --frontmatter

# Output:
Frontmatter (5):
  Lines 1-8:
    title: Project Overview
    tags: [python, cli, documentation]
    related: [./ARCHITECTURE.md, ./API.md]
```

### JSON for Programmatic Use

```bash
reveal README.md --frontmatter --format=json | jq '.structure.frontmatter.data'

# Output:
{
  "title": "Project Overview",
  "tags": ["python", "cli", "documentation"],
  "related": ["./ARCHITECTURE.md", "./API.md"]
}
```

---

## Use Case: Static Site Generation (Hugo, Jekyll)

### Validate Front Matter Schema

**Problem**: Hugo requires `title` and `date`, but easy to forget.

**Solution**: Validate before building:

```bash
# Validate against Hugo schema
reveal content/posts/my-post.md --validate-schema hugo

# Output:
✅ Front matter present
❌ Missing required field: date
⚠️  Unknown field: publish_date (did you mean 'date'?)
```

### Aggregate Quality Checks

```bash
# Check all posts
reveal content/**/*.md --check-metadata --summary

# Output:
Checked 150 files:
  ✅ 145 have front matter (96.7%)
  ❌ 5 missing front matter
  ✅ 140 have required fields (93.3%)
  ❌ 10 missing 'date' field
```

### CI/CD Integration

```yaml
# .github/workflows/validate-content.yml
- name: Validate Hugo front matter
  run: |
    for file in content/**/*.md; do
      reveal "$file" --validate-schema hugo || exit 1
    done
```

---

## Use Case: Personal Knowledge Management (Obsidian-style)

### Document Relationships

**Pattern**: Use `related` field in front matter to create bidirectional links.

```markdown
---
title: Progressive Disclosure Pattern
tags: [ux, design-patterns]
related:
  - ./Information-Architecture.md
  - ./Cognitive-Load.md
  - ../research/Progressive-Enhancement.md
---

# Progressive Disclosure Pattern
...
```

### Explore Relationship Graph

```bash
# Show immediate relationships
reveal Progressive-Disclosure.md --related

# Output:
File: Progressive-Disclosure.md
Related docs (3):

  1. ./Information-Architecture.md
     Headings (12):
       - Overview
       - Navigation Patterns
       - Progressive Disclosure

  2. ./Cognitive-Load.md
     Headings (8):
       - Working Memory
       - Progressive Disclosure

  3. ../research/Progressive-Enhancement.md
     Headings (15):
       - History
       - Modern Applications
```

### Two-Hop Exploration

```bash
# Follow links recursively (max depth 2)
reveal Progressive-Disclosure.md --related --depth 2

# Shows:
# Progressive-Disclosure.md
#   → Information-Architecture.md
#       → Navigation-Patterns.md
#       → Hierarchical-Information.md
#   → Cognitive-Load.md
#       → Working-Memory.md
```

---

## Use Case: Research Knowledge Base (Beth-style)

### Semantic Metadata

**Pattern**: Use weighted topics for semantic search integration.

```markdown
---
session_id: stormy-gust-1213
beth_topics:
  - reveal
  - front-matter
  - knowledge-graphs
related_docs:
  - ../visible-pulsar-1211/README.md
  - /docs/BETH_FRONT_MATTER_GUIDE.md
type: production-execution
---

# Session Summary
...
```

### Validate Against Custom Schema

```bash
# Create .reveal-schema.yaml
cat > .reveal-schema.yaml <<EOF
name: "Research Session Schema"
required_fields:
  - session_id
  - beth_topics
field_types:
  session_id: string
  beth_topics: list
  related_docs: list
EOF

# Validate
reveal README.md --validate-schema .reveal-schema.yaml

# Output:
✅ Front matter present
✅ Required fields: session_id, beth_topics
⚠️  F004: 'beth_topics' should be a list, got string
```

### Find Related Sessions

```bash
# Find all sessions about 'reveal'
reveal markdown://sessions/?beth_topics=reveal

# Output:
Found 23 files:
  1. sessions/stormy-gust-1213/README.md
  2. sessions/emerald-crystal-1210/README.md
  ...
```

---

## Knowledge Graph Patterns

### Pattern 1: Hub-and-Spoke (Index Documents)

**Use Case**: Create high-level index documents that link to many related docs.

```markdown
---
title: Authentication System Overview
type: index
related_docs:
  - ./oauth2-implementation.md
  - ./jwt-tokens.md
  - ./session-management.md
  - ./password-policies.md
  - ../api/auth-endpoints.md
---

# Authentication System
This document provides an overview of our authentication architecture.
...
```

**Exploration**:
```bash
reveal auth-overview.md --related
# Shows structure of all 5 related documents

reveal auth-overview.md --related --depth 2
# Shows related docs + their relationships
```

---

### Pattern 2: Chronological Chains (Session Logs)

**Use Case**: Link related work sessions chronologically.

```markdown
---
session_id: session-1213
date: 2025-12-13
previous: ../session-1212/README.md
next: ../session-1214/README.md
related_topics:
  - reveal
  - front-matter
---
```

**Navigation**:
```bash
# Find all sessions in December 2025
reveal markdown://sessions/*-12[0-9][0-9]/?

# Trace session chain
reveal sessions/session-1213/README.md --related
```

---

### Pattern 3: Bidirectional References (Research Papers)

**Use Case**: Create citation networks.

```markdown
---
title: Progressive Disclosure in Web UX
authors: [Smith, J., Doe, A.]
cites:
  - ../papers/cognitive-load-theory.md
  - ../papers/information-architecture.md
cited_by:
  - ../papers/modern-web-patterns.md
---
```

---

## Built-in Schemas

Reveal ships with schemas for popular tools:

### Beth Schema (`beth.yaml`)

For Beth session documentation:

```yaml
required_fields:
  - session_id
  - beth_topics
field_priorities:
  session_id: 3.0     # Tier 1
  beth_topics: 2.5    # Tier 2
  tags: 2.0           # Tier 3
```

**Usage**:
```bash
reveal README.md --validate-schema beth
```

### Hugo Schema (`hugo.yaml`)

For Hugo static sites:

```yaml
required_fields:
  - title
  - date
optional_fields:
  - draft
  - tags
  - categories
  - series
```

**Usage**:
```bash
reveal content/posts/my-post.md --validate-schema hugo
```

### Obsidian Schema (`obsidian.yaml`)

For Obsidian vaults:

```yaml
optional_fields:
  - tags
  - aliases
  - cssclass
field_types:
  tags: list
  aliases: list
```

**Usage**:
```bash
reveal vault/note.md --validate-schema obsidian
```

---

## Custom Schemas

### Creating a Schema File

```yaml
# .reveal-schema.yaml
name: "My Custom Schema"
version: "1.0"

required_fields:
  - title
  - author

optional_fields:
  - tags
  - related
  - status

field_types:
  title: string
  author: string
  tags: list
  related: list
  status: string  # enum: draft, review, published

validation_rules:
  - code: CUSTOM001
    description: "Title must be at least 3 words"
    check: len(title.split()) >= 3

  - code: CUSTOM002
    description: "Status must be valid"
    check: status in ['draft', 'review', 'published']
```

### Using Custom Schemas

```bash
# Validate against custom schema
reveal README.md --validate-schema .reveal-schema.yaml

# Validate all docs in directory
reveal docs/**/*.md --validate-schema .reveal-schema.yaml --summary
```

---

## Configuration

### Project-Level Config (`.revealrc`)

```yaml
# .revealrc
schemas:
  default: hugo  # Default schema for validation

related_fields:
  - related_docs
  - see_also
  - references

auto_detect_link_fields: true  # Auto-find *_docs, *_links, *_refs

max_related_depth: 2  # Limit for --related --depth

quality_thresholds:
  min_related_docs: 2      # Warn if fewer than 2 links
  require_topics: true     # Warn if no topic/tag field
```

### Usage

```bash
# Uses settings from .revealrc
reveal README.md --validate  # Uses default schema
reveal README.md --related   # Uses related_fields config
```

---

## Advanced Workflows

### Workflow 1: Find Orphan Documents

Find documents with no relationships:

```bash
# Check for documents with no related_docs
for file in docs/**/*.md; do
  count=$(reveal "$file" --frontmatter --format=json | \
          jq '.structure.frontmatter.data.related_docs | length')
  if [ "$count" -eq 0 ]; then
    echo "Orphan: $file"
  fi
done
```

### Workflow 2: Visualize Topic Distribution

Aggregate topics across corpus:

```bash
# Extract all topics
find docs/ -name "*.md" | while read f; do
  reveal "$f" --frontmatter --format=json | \
    jq -r '.structure.frontmatter.data.tags[]?' 2>/dev/null
done | sort | uniq -c | sort -rn

# Output:
#  45 python
#  32 documentation
#  28 cli
#  15 knowledge-graph
```

### Workflow 3: Validate Link Integrity

Check that all `related_docs` paths exist:

```bash
# Validate all links
for file in docs/**/*.md; do
  reveal "$file" --frontmatter --format=json | \
    jq -r '.structure.frontmatter.data.related_docs[]?' | \
    while read link; do
      if [ ! -f "$link" ]; then
        echo "Broken link in $file: $link"
      fi
    done
done
```

### Workflow 4: Generate Navigation Index

Create index of all documents by topic:

```bash
# Generate topics.md index
echo "# Documentation Index" > topics.md
echo "" >> topics.md

for topic in $(find docs/ -name "*.md" | while read f; do
  reveal "$f" --frontmatter --format=json | \
    jq -r '.structure.frontmatter.data.tags[]?'
done | sort -u); do
  echo "## $topic" >> topics.md
  find docs/ -name "*.md" | while read f; do
    if reveal "$f" --frontmatter --format=json | \
       jq -e ".structure.frontmatter.data.tags[]? | select(. == \"$topic\")" >/dev/null; then
      title=$(reveal "$f" --frontmatter --format=json | \
              jq -r '.structure.frontmatter.data.title // empty')
      echo "- [$title]($f)" >> topics.md
    fi
  done
  echo "" >> topics.md
done
```

---

## Integration with Knowledge Graph Tools

### Beth (Session Documentation)

**Reveal's role**: Extract and validate metadata
**Beth's role**: Index, search, score (PageRank)

**Workflow**:
```bash
# 1. Create session README with reveal validation
reveal README.md --validate-schema beth

# 2. External tooling indexes the file (if using beth)
# beth rebuild

# 3. Drill down with reveal
reveal README.md --frontmatter --related
```

### Obsidian

**Reveal's role**: CLI validation, CI/CD checks
**Obsidian's role**: Visual graph, note-taking UX

**Workflow**:
```bash
# Validate vault before commit
reveal vault/**/*.md --validate-schema obsidian --summary

# Find broken links
reveal vault/my-note.md --related  # Check paths exist
```

### Hugo

**Reveal's role**: Pre-build validation
**Hugo's role**: Site generation, taxonomy

**Workflow**:
```bash
# Pre-commit hook
git diff --cached --name-only | grep "content/.*\.md$" | \
  xargs -I {} reveal {} --validate-schema hugo
```

---

## Best Practices

### 1. **Use Consistent Field Names**

Pick a convention and stick to it:
- `related` vs `related_docs` vs `see_also`
- `topics` vs `tags` vs `keywords`

**Tip**: Configure `.revealrc` to recognize all variants.

### 2. **Limit Related Docs to 2-10 Links**

Too few: Document is isolated
Too many: Dilutes relationship meaning

**Guideline**: 2-5 strong relationships, 5-10 if hub document.

### 3. **Validate in CI/CD**

Catch metadata issues before they reach production:
```yaml
# GitHub Actions
- name: Validate front matter
  run: reveal docs/**/*.md --validate-schema custom --summary
```

### 4. **Create Index/Hub Documents**

High-level documents that link to many related docs help navigation:
- `AUTH_OVERVIEW.md` → links to all auth-related docs
- `SESSION_INDEX.md` → links to all sessions in a sprint

### 5. **Document Your Schema**

Include `.reveal-schema.yaml` in your repo and document it:
```markdown
# Front Matter Schema

We use the following front matter fields:
- `title`: Document title (required)
- `tags`: Topics (list, required)
- `related`: Related documents (list, 2-5 recommended)

Validate with: `reveal README.md --validate-schema .reveal-schema.yaml`
```

---

## Troubleshooting

### Front Matter Not Detected

**Problem**: `reveal file.md --frontmatter` shows "No front matter found"

**Solutions**:
1. Check front matter starts at line 1 (not line 2)
2. Ensure opening/closing `---` are on their own lines
3. Validate YAML syntax: `cat file.md | head -20 | yq eval -`

### Validation Always Fails

**Problem**: `--validate-schema` shows errors even though front matter looks correct

**Debug**:
```bash
# Check what reveal extracted
reveal file.md --frontmatter --format=json | jq '.structure.frontmatter.data'

# Compare with schema requirements
cat .reveal-schema.yaml
```

### Related Docs Not Showing

**Problem**: `--related` shows no related documents

**Solutions**:
1. Check field name: default is `related_docs` (configure in `.revealrc`)
2. Verify paths are correct (relative to file location)
3. Check files actually exist

---

## See Also

- **help://markdown** - Markdown features guide (includes front matter)
- **help://tricks** - Cool tricks and advanced patterns
- **BETH_FRONT_MATTER_GUIDE.md** - Beth-specific schema reference
- **SCHEMA_VALIDATION_GUIDE.md** - Deep dive on validation rules

---

## Examples

### Example 1: Research Paper Network

```markdown
---
title: "Progressive Disclosure in Modern Web Design"
authors: ["Smith, J.", "Doe, A."]
year: 2024
venue: CHI 2024
tags: [ux, progressive-disclosure, web-design]
related_papers:
  - ./cognitive-load-theory.md
  - ./information-architecture.md
cited_by:
  - ./modern-patterns-2025.md
---
```

**Exploration**:
```bash
reveal paper.md --related --depth 2
# Shows citation network 2 hops deep
```

### Example 2: Code Documentation

```markdown
---
title: Authentication Manager
module: auth.manager
related_modules:
  - auth.tokens
  - auth.session
  - database.users
api_endpoints:
  - /api/auth/login
  - /api/auth/logout
tags: [authentication, security, api]
---
```

**Validation**:
```bash
reveal auth-manager.md --validate-schema code-docs.yaml
```

### Example 3: Session Log

```markdown
---
session_id: prairie-snow-0101
date: 2026-01-01
project: reveal
beth_topics:
  - knowledge-graphs
  - front-matter
  - reveal
related_docs:
  - ../stormy-gust-1213/README.md
  - /docs/REVEAL_BETH_PROGRESSIVE_KNOWLEDGE_SYSTEM.md
type: planning
---
```

**Workflow**:
```bash
# Validate
reveal README.md --validate-schema beth

# Find related sessions
reveal markdown://sessions/?beth_topics=reveal

# Explore graph
reveal README.md --related --depth 2
```

---

**Remember**: Reveal provides the tools to build and maintain your knowledge graph. The semantics, scoring, and discovery are up to you (or your chosen tool like Beth, Obsidian, etc.).
