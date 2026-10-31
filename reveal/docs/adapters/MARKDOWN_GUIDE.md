---
title: Markdown Support - Complete Guide
category: guide
help_topic: markdown
help_description: Markdown feature guide
help_category: feature_guides
---
# Markdown Support - Complete Guide

## Overview

Reveal treats Markdown files as structured documents with queryable entities: headings, links, and code blocks. Using tree-sitter for accurate parsing, reveal can extract document structure, validate links, analyze code examples, and support documentation workflows.

**Core Philosophy**: Progressive disclosure of markdown structure - start with headings, drill down to specific elements.

## Quick Start

```bash
# View document structure (headings)
reveal README.md

# Extract specific section
reveal README.md "Installation"

# Extract all links
reveal README.md --links

# Extract code blocks
reveal README.md --code

# Hierarchical outline view
reveal README.md --outline

# JSON output for programmatic use
reveal README.md --links --format json
```

## Features at a Glance

| Feature | Command | Use Case |
|---------|---------|----------|
| Document Structure | `reveal doc.md` | See all headings |
| Hierarchical Outline | `reveal doc.md --outline` | **Tree view of document** |
| Section Extraction | `reveal doc.md "Section"` or `--section` | Extract specific content |
| Link Extraction | `reveal doc.md --links` | Find all hyperlinks |
| Link Filtering | `reveal doc.md --links --link-type external` | External links only |
| Domain Filtering | `reveal doc.md --links --domain github.com` | Links to specific domain |
| Code Block Extraction | `reveal doc.md --code` | Extract code examples |
| Language Filtering | `reveal doc.md --code --language python` | Python code only |
| **Front Matter Extraction** | `reveal doc.md --frontmatter --format json` | **Extract YAML metadata (requires JSON)** |
| Broken Link Detection | `reveal doc.md --links` | **Find broken internal links** |
| Progressive Disclosure | `reveal doc.md --head 5` | First 5 headings |
| Cross-File Link Graph | `reveal 'markdown://docs/?link-graph'` | Whole-tree forward links, backlinks, orphans |
| Single-Doc Backlinks | `reveal 'markdown://docs/?backlinks=file.md'` | Who links to this doc, before you rename it |
| Ranked Body Search | `reveal 'markdown://docs/?body-contains=x&explain'` | Multi-doc search, best match first, with a score breakdown |
| Frontmatter Lint Queue | `reveal 'markdown://docs/?lint'` | Malformed YAML / missing frontmatter across a tree |

## The Problem This Solves

### Classic Scenario

```
Developer: "I need to audit all external links in our documentation"
```

**Before Reveal**:
```bash
grep -r "https://" docs/  # Misses [text](url) format
# Manual parsing of markdown link syntax
# False positives from code blocks
# ... 30 minutes later ...
```

**With Reveal**:
```bash
ls docs/*.md | reveal --stdin --links --link-type external
```

Output shows:
- ✅ All markdown-formatted links
- ✅ Grouped by type (external, internal, email)
- ✅ Line numbers for easy navigation
- ⚠️ **BROKEN** markers for dead internal links

## Document Structure

### Viewing Headings (Default)

The default behavior shows all headings in a document:

```bash
$ reveal README.md

File: README.md (651B, 52 lines)

Headings (8):
  :11     Project Title
    :15     Installation
      :17     Prerequisites
      :21     Quick Install
    :28     Usage
    :42     Bug 11 Analysis
      :46     Bug 11 Details
    :50     Background


Next: reveal README.md --section 'Project Title'  # Extract this section
```

Each row is `:LINE  Heading`, indented two spaces per heading level.

### Hierarchical Outline View (NEW in v0.22.0)

See document structure as a tree:

```bash
$ reveal README.md --outline

File: README.md

Project Title (README.md:1, 50 lines)
  ├─ Installation (line 5, 10 lines)
  │  ├─ Prerequisites (line 7, 3 lines)
  │  └─ Quick Install (line 12, 3 lines)
  ├─ Usage (line 15, 10 lines)
  │  ├─ Basic Example (line 17, 3 lines)
  │  └─ Advanced Usage (line 21, 4 lines)
  ├─ Configuration (line 25, 10 lines)
  └─ API Reference (line 35, 16 lines)
     ├─ Core Functions (line 37, 7 lines)
     └─ Utilities (line 45, 6 lines)
```

**Use Cases**:
- Understand document organization at a glance
- Navigate complex nested documentation
- Verify heading hierarchy (H1 → H2 → H3)

### Section Extraction

Extract specific sections by heading name:

```bash
# Positional argument (same pattern as extracting code elements)
$ reveal README.md "Installation"

# Explicit flag (clearer for scripts/automation)
$ reveal README.md --section "Installation"

# Installation

## Prerequisites

- Python 3.8+
- pip

## Quick Install

```bash
pip install myproject
```
```

**Workflow**: Use default view to see all headings, then extract specific sections by name.

### OR-Pattern Section Extraction

Use `|` to extract multiple sections in a single call — all matching sections are
returned concatenated in document order:

```bash
# Two specific sections
$ reveal CHANGELOG.md "Breaking Changes|Migration Guide"

# Three sections
$ reveal doc.md "Open Issues|Action Items|Known Gaps"

# grep-style \| escaping also works (useful when calling from shell scripts)
$ reveal doc.md "Bug 11\|social_repost_log\|Action Items"

# Spaces around | are trimmed
$ reveal doc.md "Open Issues | Action Items"
```

Each `|`-separated term follows the same matching rules as single-term extraction:
exact match first (case-insensitive), falling back to substring match.  A term that
matches multiple headings via substring includes all of them, but a section inside
another returned section is not repeated.

```bash
# 'Bug 11' is in '# Bug 11 Analysis' and in its own '## Bug 11 Details':
# the Analysis section is returned once, with Details inside it
$ reveal doc.md "Background|Bug 11"
```

**Why this matters for agents**: eliminates the need for multiple sequential `reveal`
calls when you know which sections you want, reducing round-trips by N−1.

## Link Extraction

### Basic Link Extraction

```bash
$ reveal docs/README.md --links

File: README.md (651B, 52 lines)

Links (5):

  External (3):
    Line 10   [Project Website](https://example.com)
             -> example.com
    Line 15   [Documentation](https://docs.example.com)
             -> docs.example.com
    Line 20   [GitHub](https://github.com/user/repo)
             -> github.com

  Internal (2):
    Line 25   [API Guide](./api.md)
    X Line 30   [Tutorial](./docs/tutorial.md) [BROKEN]
```

**Key Features**:
- **Grouped by type**: External, Internal, Email
- **Domain display**: Quick domain identification
- **Broken link detection**: an `X` marker and `[BROKEN]` for missing internal files
- **Line numbers**: Easy navigation to source

### Link Types

Reveal classifies links into three categories:

1. **External**: Full URLs (http://, https://)
   ```markdown
   [GitHub](https://github.com)
   ```

2. **Internal**: Relative paths (./file.md, ../doc.md)
   ```markdown
   [API Reference](./api.md)
   ```

3. **Email**: mailto: links
   ```markdown
   [Contact](mailto:support@example.com)
   ```

### Filtering Links

#### Filter by Link Type

```bash
# External links only
reveal README.md --links --link-type external

# Internal links only (useful for validation)
reveal README.md --links --link-type internal

# Email addresses
reveal README.md --links --link-type email
```

#### Filter by Domain

Find all links to a specific domain:

```bash
# All GitHub links
reveal README.md --links --domain github.com

# All documentation site links
reveal README.md --links --domain docs.python.org
```

### Broken Link Detection

Reveal automatically validates internal links:

```bash
$ reveal README.md --links --link-type internal

File: README.md (651B, 52 lines)

Links (3):

  Internal (3):
    Line 10   [Installation](./docs/install.md)
    Line 15   [Usage Guide](./docs/usage.md)
    X Line 20   [API Reference](./docs/api.md) [BROKEN]
```

**Use Cases**:
- Validate documentation after restructuring
- Find broken links before publishing
- Audit internal documentation consistency

### JSON Output for Programmatic Use

```bash
$ reveal README.md --links --format json

{
  "analyzer": "...",
  "file": "README.md",
  "meta": {...},
  "structure": {
    "links": [
      {
        "line": 30,
        "text": "GitHub",
        "url": "https://github.com/user/repo",
        "type": "external",
        "protocol": "https",
        "domain": "github.com",
        "column": 5,
        "file": "README.md"
      },
      {
        "line": 32,
        "text": "Tutorial",
        "url": "./docs/tutorial.md",
        "type": "internal",
        "target": "./docs/tutorial.md",
        "broken": true,
        "column": 37,
        "file": "README.md"
      }
    ],
    ...
  },
  "type": "..."
}
```

Internal links carry `target` and `broken`; external links have `protocol` and `domain` and no
`broken` (they are not checked); email links carry `email`.

## Code Block Extraction

### Extract All Code Blocks

```bash
$ reveal README.md --code

File: README.md (651B, 52 lines)

Code_blocks (2):

  Bash (1 blocks):
    Lines 23-26 (2 lines)
      pip install myproject
      myproject --version

  Python (1 blocks):
    Lines 34-40 (5 lines)
      import myproject
      result = myproject.run()
      print(result)
      ... (2 more lines)
```

`Lines` spans the opening and closing fence; the count is the code inside.

**Features**:
- **Grouped by language**: Easy navigation
- **Line ranges**: Jump to source location
- **Preview**: First 3 lines of each block
- **Accurate parsing**: Tree-sitter ignores # in code fences

### Filter by Language

```bash
# Python code blocks only
reveal README.md --code --language python

# Bash/shell examples
reveal README.md --code --language bash

# JSON examples
reveal README.md --code --language json
```

### Include Inline Code

By default, only fenced code blocks (```) are extracted. Include inline code:

```bash
$ reveal README.md --code --inline

File: README.md (651B, 52 lines)

Code_blocks (3):

  Bash (1 blocks):
    [... fenced blocks ...]

  Inline code (1 snippets):
    Line 13   `import sys`
```

Inline spans inside fenced blocks are not reported again.

## Front Matter Extraction

Extract YAML front matter metadata from markdown files. Front matter is metadata at the beginning of a file, delimited by `---`:

```markdown
---
title: Document Title
author: Author Name
date: 2025-12-13
topics:
  - topic1
  - topic2
tags: [tag1, tag2]
---

# Document Content
```

### Basic Front Matter Extraction

**Important**: Frontmatter extraction requires `--format json` to display the parsed YAML data. Text format shows document structure only.

```bash
# Get frontmatter data (requires JSON format)
reveal README.md --frontmatter --format json
```

**Output**:
```json
{
  "structure": {
    "frontmatter": {
      "data": {
        "title": "Document Title",
        "author": "Author Name",
        "date": "2025-12-13",
        "topics": ["topic1", "topic2"],
        "tags": ["tag1", "tag2"]
      },
      "line_start": 1,
      "line_end": 8,
      "raw": "title: Document Title\nauthor: Author Name\n..."
    }
  }
}
```

**Text format behavior**:
```bash
# Text format shows document structure, not frontmatter data
reveal README.md --frontmatter

# Output:
# Headings (4):
#   :7      Main Title
#   ...
```

**Querying frontmatter across many files?** Stop here and use `markdown://` instead of
`--frontmatter --format json` in a loop — it's the native, purpose-built adapter for exactly
this, not a fallback:

```bash
reveal 'markdown://docs/?aggregate=tags'          # frequency table of tag values across all docs
reveal 'markdown://docs/?tags=tutorial'           # find docs by tag/category/any field
reveal 'markdown://docs/?fields=author,date'      # extra columns per matched file
```

See the "CLI Flags" section below (`?body-contains=`, `?fields=`) or
`reveal help://schemas/markdown` for the full query syntax. The "Advanced Examples" below cover
the rare case where you need per-file JSON (e.g. `.raw` frontmatter text) that `markdown://`
doesn't expose.

### JSON Output (Required for Frontmatter Data)

**Note**: JSON format is required to access parsed frontmatter data programmatically.

```bash
reveal README.md --frontmatter --format json
```

**Output**:
```json
{
  "structure": {
    "frontmatter": {
      "data": {
        "title": "Document Title",
        "author": "Author Name",
        "date": "2025-12-13",
        "topics": ["topic1", "topic2"],
        "tags": ["tag1", "tag2"]
      },
      "line_start": 1,
      "line_end": 8,
      "raw": "title: Document Title\nauthor: Author Name\n..."
    }
  }
}
```

### Advanced Examples

#### Aggregate Metadata Across Documents

Use `markdown://` — a single query, no shell loop, no `jq`:

```bash
# Count tag frequency across all docs
reveal 'markdown://docs/?aggregate=tags'

# Find all unique authors
reveal 'markdown://docs/?aggregate=author'

# Validate required fields are present (per file, via missing-field filter)
reveal 'markdown://docs/?!title'    # docs missing a title field
```

#### Find Documents by Metadata

```bash
# Find all tutorial documents
reveal 'markdown://docs/?tags=tutorial'

# Find documents by category
reveal 'markdown://docs/?category=api'
```

#### Real-World Integration Example

```bash
# Extract tags/topics for indexing — topic index in one call
reveal 'markdown://docs/?aggregate=tags'
```

This pattern works well for building topic indexes, documentation search, and content categorization.

#### Per-File JSON Fallback (rare)

`markdown://` covers frontmatter *field* queries. If you need something it doesn't expose —
the raw frontmatter text (`.raw`), line offsets, or programmatic access to a single file's
parsed YAML — fall back to per-file JSON:

```bash
find docs/ -name "*.md" | while read f; do
  reveal "$f" --frontmatter --format=json 2>/dev/null | \
    jq -r '.structure.frontmatter.data.tags[]?' 2>/dev/null
done | sort | uniq -c | sort -rn
```

### Combined with Other Features

In text mode `--frontmatter` prints a note and the headings; the parsed data needs `--format json`:

```bash
reveal README.md --frontmatter
# Note: --frontmatter needs --format json to show parsed YAML data (text mode shows structure only). ...
# then the headings
```

Combine with other features:

```bash
# Front matter + links
reveal README.md --frontmatter --links --format=json

# Front matter + code blocks (text shows the code blocks; front matter needs --format json)
reveal README.md --frontmatter --code
```

### Error Handling

Reveal handles malformed front matter gracefully:

- **Missing closing delimiter**: Returns `null`
- **Invalid YAML syntax**: Returns `null` (does not crash)
- **Not at file start**: Front matter must begin at line 1
- **Non-dict content**: Only dict-style YAML is recognized

```bash
# File without front matter
reveal no-frontmatter.md --frontmatter
# Output: the headings (text); `structure.frontmatter` is `null` in JSON.
```

### Use Cases

1. **Metadata Validation**: Audit front matter consistency across documentation
2. **Topic Analysis**: Extract and analyze `tags` distribution across files
3. **Bibliography Generation**: Collect author/date metadata for citations
4. **Documentation Indexes**: Build metadata-driven navigation
5. **Quality Checks**: Ensure required fields present in all docs

## Progressive Disclosure

Limit output to specific ranges of headings/links/code blocks:

```bash
# First 5 headings
reveal README.md --head 5

# Last 3 headings
reveal README.md --tail 3

# Headings 10-15
reveal README.md --range 10-15

# Works with all features
reveal README.md --links --head 10
reveal README.md --code --tail 5
```

On an extracted section the flags count its lines instead:
`reveal README.md "Installation" --head 20` prints the section's first 20 lines and
says how many it left out (`⚠ Truncated source: showing 20 of 85`).

A long section that has subsections (150+ lines, typically an H1 that is the whole
document) is shown as the text under its own heading plus a `Subsections` outline with
line numbers, so one call can't dump the document. A heading with no text of its own
shows the outline alone. The truncation note gives the `:N-M` line range that returns
the whole section; `--head`, `--tail`, `--range` and `:N-M` requests are never collapsed.

**Note**: Slicing applies to each category independently. With `--head 5`:
- Shows first 5 headings
- AND first 5 links (if --links specified)
- AND first 5 code blocks (if --code specified)

## Workflows

### Workflow 1: Documentation Quality Audit

```bash
# 1. Check structure
reveal README.md --outline

# 2. Validate all links
reveal README.md --links --link-type internal

# 3. Verify code examples
reveal README.md --code --language python

# 4. Find all external references
reveal README.md --links --link-type external
```

### Workflow 2: Extract Code Examples for Testing

```bash
# Extract all Python code blocks
reveal README.md --code --language python --format json | \
  jq -r '.structure.code_blocks[] | .source' > examples.py

# Test the examples
python examples.py
```

### Workflow 3: Link Validation Across Multiple Files

```bash
# Find all broken links in documentation
for file in docs/*.md; do
  echo "Checking $file..."
  reveal "$file" --links --link-type internal | grep "BROKEN"
done
```

### Workflow 4: Aggregate Link Analysis

```bash
# Find all external links in project
find . -name "*.md" | while read f; do
  reveal "$f" --links --link-type external --format json
done | jq -r '.structure.links[]? | "\(.domain)\t\(.url)"' | sort | uniq -c | sort -rn
```

## Multi-Shot Examples for LLM Context

These examples provide concrete input/output patterns for AI agents:

### Example 1: Basic Structure Inspection

**Input**:
```bash
reveal example.md
```

**File Content** (example.md):
```markdown
# Main Title
Introduction text.

## Section One
Content here.

### Subsection 1.1
More content.

## Section Two
Final content.
```

**Output**:
```
File: example.md (127B, 11 lines)

Headings (4):
  :1      Main Title
    :4      Section One
      :7      Subsection 1.1
    :10     Section Two


Next: reveal example.md --section 'Main Title'  # Extract this section
```

### Example 2: Link Extraction with Mixed Types

**Input**:
```bash
reveal example.md --links
```

**File Content** (example.md):
```markdown
# Project

Visit our [website](https://example.com) for details.

See the [configuration guide](../guides/CONFIGURATION_GUIDE.md) for usage.

Contact us at [support@example.com](mailto:support@example.com).
```

**Output**:
```
File: example.md (127B, 11 lines)

Links (3):

  External (1):
    Line 3    [website](https://example.com)
             -> example.com

  Internal (1):
    Line 5    [configuration guide](../guides/CONFIGURATION_GUIDE.md)

  Email (1):
    Line 7    [support@example.com](mailto:support@example.com)
```

### Example 3: Hierarchical Outline

**Input**:
```bash
reveal example.md --outline
```

**File Content** (example.md):
```markdown
# Guide
## Installation
### Linux
### macOS
## Usage
### Basic
### Advanced
```

**Output**:
```
File: example.md (76B, 7 lines)

Guide (example.md:1, 7 lines)
  ├─ Installation (line 2, 3 lines)
  │  ├─ Linux (line 3, 1 line)
  │  └─ macOS (line 4, 1 line)
  └─ Usage (line 5, 3 lines)
     ├─ Basic (line 6, 1 line)
     └─ Advanced (line 7, 1 line)
```

## Edge Cases & Limitations

### Bare URLs Not Extracted

Reveal only extracts markdown-formatted links `[text](url)`, not bare URLs:

```markdown
Check out https://example.com for details.  ❌ Not extracted
Visit [our site](https://example.com).      ✅ Extracted
```

**Rationale**: Bare URLs create noise (version numbers, examples) and aren't semantic markdown.

### Code Fences vs Inline Code

- **Fenced code blocks** (```) are always extracted with `--code`
- **Inline code** (`) requires `--inline` flag
- Headings inside code fences are correctly ignored (tree-sitter parsing)

### Heading Levels

- Reveal extracts H1-H6 (levels 1-6)
- Level information included in JSON output
- Outline view uses levels for indentation

### Section Name Matching

Section extraction is **case-insensitive**.  Matching applies the following
priority rules, in order:

1. **Exact match** (case-insensitive) — returns that section.  A heading that
   occurs more than once (every release's `### Fixed` in a changelog) returns
   its first copy, and a note on stderr gives a `:N-M` address for each copy.
2. **Substring match** — if the query appears inside exactly one heading,
   that section is returned.  If it appears in multiple headings, all are
   returned, each with its own line numbers; a section nested inside another
   matched section is not repeated.

Headings are compared on their visible text: inline formatting (`` ` `` `*` `_`),
link syntax (`[text](url)` matches as `text`), HTML entities, a trailing `{#id}`
and a closing `##` are ignored.  A leading `#` marker in the query is dropped, so
`reveal doc.md "## Install"` works.  A heading that looks like a line number or
an ordinal (`## 2026`, `## Phase:1`) is found by name; an explicit `:N` is always
a line.

```bash
reveal doc.md "installation"   # ✅ Matches "## Installation" (case-insensitive)
reveal doc.md "Install"        # ✅ Substring match → "## Installation"
reveal doc.md "Bug"            # ✅ Substring match → every "## Bug *" section
```

When multiple sections match, a count prefix is shown, and each block is labelled
with the heading it matched:

```
# 3 sections matched "Bug" — showing all

doc.md:45-80 | Bug 9: retries
...
```

A name that matches nothing exits 1 with a "Did you mean" from the file's
headings and the first few heading names.

**Survey a section before reading it**: `--outline` with a section name lists the
headings inside that section instead of its text (`--depth N` collapses deeper
levels, `--format json` gives the heading list):

```bash
reveal CURRENT_FOCUS.md "Current Focus" --outline   # its table of contents
reveal CURRENT_FOCUS.md "Current Focus"             # then the full text, or a subsection
```

**OR-alternation with `|`**: use pipe-separated terms to pull multiple named
sections in one call:

```bash
reveal doc.md "Open Issues|Action Items"           # exact or substring per term
reveal doc.md "Bug 11\|social_repost_log\|Action"  # grep-style \| also accepted
```

Each term is resolved independently; results are deduplicated and returned in
document order.

**Label-only hint**: when a section has no body of its own (its heading is
followed directly by the next heading at its level), reveal says so on stderr and
names the next section.

## Output Formats

### Text Format (Default)

Human-readable output with grouping and formatting:

```bash
$ reveal README.md --links

File: README.md (651B, 52 lines)

Links (3):
  External (2):
    Line 10   [GitHub](https://github.com/user/repo)
    ...
```

### JSON Format

Structured output for programmatic use:

```bash
$ reveal README.md --links --format json

{
  "analyzer": "...",
  "file": "README.md",
  "meta": {...},
  "structure": {
    "links": [
      {"line": 30, "text": "GitHub", "url": "https://github.com/user/repo", "type": "external", ...}
    ],
    ...
  },
  "type": "..."
}
```

### Grep Format

Pipeable format for integration:

```bash
$ reveal README.md --links --format grep

File: README.md (651B, 52 lines)

Links (5):

  External (2):
README.md:30:https://github.com/user/repo
README.md:30:https://docs.example.com/x

  Internal (2):
README.md:32:./docs/api.md
README.md:32:./docs/tutorial.md
...
```

The `file:line:url` rows are interleaved with the text-mode `File:`, `Links (N):` and group
headings. Keep only the rows before piping them on:

```bash
reveal README.md --links --format grep | grep -E '^[^ ]+:[0-9]+:'
```

## Integration with Documentation Workflows

Progressive disclosure pattern for documentation exploration:

```bash
# Orient: Discover structure
reveal docs/README.md                       # See all headings

# Navigate: Explore specific sections
reveal docs/README.md --outline             # Hierarchical view
reveal docs/README.md "API Reference"       # Extract section

# Focus: Extract specific elements
reveal docs/README.md --links --domain github.com   # GitHub links
reveal docs/README.md --code --language python      # Python examples
```

## Advanced Use Cases

### Documentation Consistency Checks

```bash
# Ensure all docs have "Installation" section
for f in docs/*.md; do
  reveal "$f" | grep -q "Installation" || echo "Missing: $f"
done
```

### Extract Table of Contents

```bash
# Generate TOC from headings
reveal README.md --format json | \
  jq -r '.structure.headings[] | "\("#" * .level) \(.name)"'
```

### Find Undocumented APIs

```bash
# Compare code examples with actual API
reveal README.md --code --language python --format json | \
  jq -r '.structure.code_blocks[] | .source' | \
  grep -o 'api\.\w\+' | sort | uniq > documented.txt

# Compare with actual API
python -c "import api; print(dir(api))" > actual.txt
diff documented.txt actual.txt
```

## CLI Flags

These flags apply specifically to markdown files:

| Flag | Description |
|------|-------------|
| `--links` | Extract all hyperlinks |
| `--link-type internal\|external\|email` | Filter links by type |
| `--domain DOMAIN` | Filter links by domain (e.g., `--domain github.com`) |
| `--code` | Extract code blocks |
| `--language LANG` | Filter code blocks by language (requires `--code`) |
| `--inline` | Include inline code snippets (requires `--code`) |
| `--frontmatter` | Extract YAML front matter |
| `--related` | Show related documents from front matter |
| `--related-depth N` | Traversal depth for `--related` (default: 1, 0=unlimited) |
| `--related-all` | Follow all related links (equivalent to `--related --related-depth 0`) |
| `--related-flat` | Output related docs as flat path list (grep-friendly) |
| `--related-limit N` | Max files to traverse for `--related` (default: 100) |
| `--section NAME` | Extract section by heading name |

For adapter-specific flags via URI params: `reveal 'markdown:///path/?type=guide'`

### Body Text Search (`?body-contains=`)

Search file body content (text after frontmatter) rather than frontmatter fields:

```bash
# Find docs mentioning "nginx" in the body
reveal 'markdown://docs/?body-contains=nginx'

# AND — both terms must appear
reveal 'markdown://docs/?body-contains=nginx&body-contains=ssl'

# Combine with frontmatter filter + limit
reveal 'markdown://docs/?type=guide&body-contains=nginx&limit=10'
```

- Case-insensitive substring match
- Multiple `body-contains=` params are AND'd (all must appear)
- Unicode lowercase matching is supported (for example, `CAFÉ` matches `café`).
  This does not normalize composed/decomposed accents or equate `Straße` with `STRASSE`.
- Files without frontmatter are also matched
- Combines with all frontmatter filters and result control (`sort=`, `limit=`, `offset=`)
- `sort=FIELD` puts a file whose field is `null` or missing last, ascending or descending (`sort=-status`
  lists the files with no status at the end, in path order); a list field sorts by its first element

Direct ordinary body searches exit `0` when complete, `2` for an invalid resource
or control, and `3` when required source or requested output is lost. Missing or
unreadable files retain diagnostics and surviving matches. A healthy search with
no matches still succeeds. Registered MCP preserves partial answers and marks
fully failed searches as errors.

JSON `analysis` counts discovered candidates, completed source decisions, failed
files and directory-enumeration failure events before selection or pagination.
A successfully searched file counts as completed even when it does not match.
Body matching, frontmatter filtering and relevance scoring reuse one decoded
content read; the earlier whole-file prefilter is separate, so this is not a filesystem
snapshot. See the [output contract](../development/OUTPUT_CONTRACT.md#declared-execution-policy)
for the exact counts and Python API behavior.

Active `aggregate=FIELD` queries also use this execution policy, with or without
body filters, and include the same `analysis` counts. Unreadable sources never
count as matched files or missing fields. Readable files with absent, malformed
or non-mapping frontmatter retain their existing missing-field meaning. List
values count each item, including duplicates; frequency totals can therefore
exceed matched file totals. Partial frequencies remain available with diagnostics.

Backlinks, link-graph and lint operations take precedence and keep their existing
policy, along with bare/empty body terms in ordinary listings, element/check
operations, stdin and batches.

### Extra Frontmatter Columns (`?fields=`)

Add arbitrary frontmatter fields as inline columns in listing output:

```bash
# Show book and cohort for each matched primitive
reveal 'markdown://primitives/?type=framework&fields=book,cohort'

# Output:
# Matched: 3 of 47 files
#
#   primitives/gsbs-kernel.md [framework] - The Kernel of Good Strategy book=good-strategy-bad-strategy cohort=strategy
#   primitives/kahneman-system2.md [framework] - System 2 Thinking book=thinking-fast-and-slow cohort=decision-making
```

- Fields missing from a file's frontmatter are silently omitted
- List-valued fields are rendered as `field=v1,v2`
- Combines with all filters and result control

### Cross-File Link Graph (`?link-graph`, `?backlinks=`)

Two related but distinct queries over the tree's `[text](path)` link structure:

```bash
# Whole-tree bidirectional graph: forward links, backlinks, orphans
reveal 'markdown://docs/?link-graph'

# Single doc: who links to it, before you rename/restructure it
reveal 'markdown://docs/?backlinks=auth.md'
```

- `?link-graph` builds and returns the full graph for every markdown file
  under the queried directory — use it to survey overall doc connectivity or
  find orphaned files (`isolated` in the output).
- `?backlinks=path` returns just the one node you asked about — cheaper when
  you only need "who references this doc" as a pre-edit staleness check.
  Accepts either a path relative to the queried directory or a bare filename
  (resolved by basename if unambiguous; flagged as `ambiguous` with
  `candidates` listed otherwise).
- Both are a live regex parse of `[text](path)` link syntax — no persisted
  index, so results always reflect the current filesystem state.

### Ranked Body Search (`?body-contains=`, `?explain`)

`?body-contains=` results sort best-first by relevance, not file order:

```bash
# Multi-term AND search, ranked best-first
reveal 'markdown://docs/?body-contains=auth&body-contains=token'

# Same, with a per-term score breakdown
reveal 'markdown://docs/?body-contains=auth&body-contains=token&explain'
```

- `relevance_score` combines term frequency with a heading-proximity boost
  (a term appearing in a heading counts extra) — simpler than Beth's full
  phrase/authority ranking model, but enough to stop common terms from
  flooding results in file-listing order.
- `?explain` adds `relevance_explain` (`term_counts`, `heading_hits`) to each
  result so you can see why one doc outranked another.
- An explicit `sort=` still overrides ranking when you want plain
  alphabetical/recency order instead.

### Frontmatter Maintenance Queue (`?lint`, `?lint-fields=`)

A corpus-wide frontmatter health check, one list instead of one-file-at-a-time:

```bash
# Malformed YAML and files with no frontmatter at all
reveal 'markdown://docs/?lint'

# Same, also flagging files missing required fields
reveal 'markdown://docs/?lint&lint-fields=title,type'
```

- Three issue types: `no_frontmatter` (file has none), `malformed_yaml`
  (a `---` block that fails to parse), and — only when `lint-fields=` is
  given — `missing_fields` (frontmatter parses fine but lacks a named field).
- A clean corpus reports zero issues rather than an empty ambiguous list.
- Mirrors the maintenance-queue shape of Beth's `quality frontmatter-lint`,
  scoped to what a live per-call scan can check (no fake-metric or
  oversized-frontmatter heuristics — those stay Beth-side).

## Notes

- **Accurate Parsing**: Tree-sitter ensures `#` in code fences aren't treated as headings
- **Link Validation**: Internal links checked against filesystem
- **Language Detection**: Uses code fence language tags (```python, ```bash, etc.)
- **Performance**: Efficient for large markdown files (progressive disclosure recommended)

## See Also

- **help://tricks** - Cool tricks and hidden features
- **help://python-guide** - Python adapter guide
- **reveal --help** - CLI reference
