---
title: Markdown Support - Complete Guide
category: guide
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
reveal docs/*.md --links --link-type external
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

File: README.md

Headings (8):
  README.md:1      Project Title
  README.md:5      Installation
  README.md:15     Usage
  README.md:25     Configuration
  README.md:30     Advanced Topics
  README.md:35     API Reference
  README.md:50     Contributing
  README.md:60     License
```

### Hierarchical Outline View (NEW in v0.22.0)

See document structure as a tree:

```bash
$ reveal README.md --outline

File: README.md

Project Title (README.md:1)
  ├─ Installation (line 5)
  │  ├─ Prerequisites (line 7)
  │  └─ Quick Install (line 12)
  ├─ Usage (line 15)
  │  ├─ Basic Example (line 17)
  │  └─ Advanced Usage (line 21)
  ├─ Configuration (line 25)
  └─ API Reference (line 35)
     ├─ Core Functions (line 37)
     └─ Utilities (line 45)
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

## Link Extraction

### Basic Link Extraction

```bash
$ reveal docs/README.md --links

File: README.md

Links (5):

  External (3):
    Line 10   [Project Website](https://example.com)
             → example.com
    Line 15   [Documentation](https://docs.example.com)
             → docs.example.com
    Line 20   [GitHub](https://github.com/user/repo)
             → github.com

  Internal (2):
    Line 25   [API Guide](./api.md)
    ❌ Line 30   [Tutorial](./docs/tutorial.md) [BROKEN]
```

**Key Features**:
- **Grouped by type**: External, Internal, Email
- **Domain display**: Quick domain identification
- **Broken link detection**: ❌ markers for missing internal files
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

File: README.md

Links (3):

  Internal (3):
    Line 10   [Installation](./docs/install.md)
    Line 15   [Usage Guide](./docs/usage.md)
    ❌ Line 20   [API Reference](./docs/api.md) [BROKEN]
```

**Use Cases**:
- Validate documentation after restructuring
- Find broken links before publishing
- Audit internal documentation consistency

### JSON Output for Programmatic Use

```bash
$ reveal README.md --links --format json

{
  "file": "README.md",
  "structure": {
    "links": [
      {
        "line": 10,
        "text": "GitHub",
        "url": "https://github.com/user/repo",
        "type": "external",
        "protocol": "https",
        "domain": "github.com",
        "broken": false
      },
      {
        "line": 25,
        "text": "API Guide",
        "url": "./api.md",
        "type": "internal",
        "protocol": "file",
        "broken": true
      }
    ]
  }
}
```

## Code Block Extraction

### Extract All Code Blocks

```bash
$ reveal README.md --code

File: README.md

Code Blocks (3):

  Python (2):
    Lines 15-18 (4 lines)
      import myproject
      result = myproject.run()
      print(result)

    Lines 30-35 (6 lines)
      def example():
          return "Hello"

  Bash (1):
    Lines 50-52 (3 lines)
      pip install myproject
      myproject --version
```

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

File: README.md

Code Blocks (5):

  Python (2):
    [... fenced blocks ...]

  Inline (3):
    Line 10: `import sys`
    Line 25: `pip install`
    Line 40: `myproject.run()`
```

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

Extract and analyze tags from all documentation:

```bash
# Count tag frequency across all docs
find docs/ -name "*.md" | while read f; do
  reveal "$f" --frontmatter --format=json 2>/dev/null | \
    jq -r '.structure.frontmatter.data.tags[]?' 2>/dev/null
done | sort | uniq -c | sort -rn

# Find all unique authors
find docs/ -name "*.md" | while read f; do
  reveal "$f" --frontmatter --format=json 2>/dev/null | \
    jq -r '.structure.frontmatter.data.author?' 2>/dev/null
done | sort -u

# Validate required fields are present
reveal README.md --frontmatter --format=json | \
  jq '.structure.frontmatter.data | keys'
```

#### Find Documents by Metadata

Search for documents matching specific criteria:

```bash
# Find all tutorial documents
find docs/ -name "*.md" | while read f; do
  if reveal "$f" --frontmatter --format=json | \
     jq -e '.structure.frontmatter.data.tags[]? | select(. == "tutorial")' >/dev/null 2>&1; then
    echo "$f"
  fi
done

# Find documents by category
find docs/ -name "*.md" | while read f; do
  if reveal "$f" --frontmatter --format=json | \
     jq -e '.structure.frontmatter.data.category == "api"' >/dev/null 2>&1; then
    echo "$f"
  fi
done
```

#### Real-World Integration Example

Use reveal for metadata extraction in documentation pipelines:

```bash
# Extract tags/topics for indexing
reveal docs/**/*.md --frontmatter --format=json | \
  jq -r '.structure.frontmatter.data.tags[]?' | \
  sort | uniq -c | sort -rn
```

This pattern works well for building topic indexes, documentation search, and content categorization.

### Combined with Other Features

Front matter extraction combines with headings by default:

```bash
reveal README.md --frontmatter
# Shows both front matter AND document structure
```

Combine with other features:

```bash
# Front matter + links
reveal README.md --frontmatter --links --format=json

# Front matter + code blocks
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
# Output: Frontmatter (0):
#           (No front matter found)
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
File: example.md

Headings (4):
  example.md:1     Main Title
  example.md:4     Section One
  example.md:7     Subsection 1.1
  example.md:10    Section Two
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

See the [configuration guide](CONFIGURATION_GUIDE.md) for usage.

Contact us at [support@example.com](mailto:support@example.com).
```

**Output**:
```
File: example.md

Links (3):

  External (1):
    Line 3    [website](https://example.com)
             → example.com

  Internal (1):
    Line 5    [configuration guide](CONFIGURATION_GUIDE.md)

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
File: example.md

Guide (example.md:1)
  ├─ Installation (line 2)
  │  ├─ Linux (line 3)
  │  └─ macOS (line 4)
  └─ Usage (line 5)
     ├─ Basic (line 6)
     └─ Advanced (line 7)
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

Section extraction is case-sensitive and exact match:

```bash
reveal doc.md "installation"   # Won't match "Installation"
reveal doc.md "Installation"   # ✅ Matches "## Installation"
```

## Output Formats

### Text Format (Default)

Human-readable output with grouping and formatting:

```bash
$ reveal README.md --links

File: README.md

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
  "file": "README.md",
  "type": "markdown",
  "structure": {
    "links": [
      {"line": 10, "text": "GitHub", "url": "https://github.com/user/repo", ...}
    ]
  }
}
```

### Grep Format

Pipeable format for integration:

```bash
$ reveal README.md --links --format grep

README.md:10:https://github.com/user/repo
README.md:15:https://docs.example.com
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

## Notes

- **Accurate Parsing**: Tree-sitter ensures `#` in code fences aren't treated as headings
- **Link Validation**: Internal links checked against filesystem
- **Language Detection**: Uses code fence language tags (```python, ```bash, etc.)
- **Performance**: Efficient for large markdown files (progressive disclosure recommended)

## See Also

- **help://tricks** - Cool tricks and hidden features
- **help://python-guide** - Python adapter guide
- **reveal --help** - CLI reference
