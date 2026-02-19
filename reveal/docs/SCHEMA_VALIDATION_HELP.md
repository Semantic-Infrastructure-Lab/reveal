---
title: Schema Validation for Markdown Front Matter
category: guide
---
# Schema Validation for Markdown Front Matter

**Purpose:** Validate markdown front matter against built-in or custom schemas
**Version:** v0.29.0+
**Audience:** Documentation maintainers, content creators, CI/CD pipelines

---

## Overview

Reveal validates markdown YAML front matter using **schema-aware quality rules (F001-F005)** and the `--validate-schema` flag. This ensures documentation consistency, catches missing metadata, and enforces content standards across projects.

**Core Philosophy:** Progressive validation - check front matter exists → check it's not empty → verify required fields → validate types → run custom rules.

---

## Quick Start

```bash
# Validate Beth session README
reveal README.md --validate-schema beth

# Validate Hugo blog post or static page
reveal content/posts/article.md --validate-schema hugo

# Validate Jekyll post (GitHub Pages)
reveal _posts/2026-01-03-my-post.md --validate-schema jekyll

# Validate MkDocs documentation
reveal docs/api/reference.md --validate-schema mkdocs

# Validate Obsidian note
reveal vault/notes/project.md --validate-schema obsidian

# Use custom schema
reveal document.md --validate-schema /path/to/custom-schema.yaml

# JSON output for CI/CD
reveal README.md --validate-schema beth --format json

# Select specific validation rules
reveal README.md --validate-schema beth --select F003,F004
```

---

## Built-in Schemas

| Schema | Purpose | Required Fields | Community Reach |
|--------|---------|----------------|----------------|
| **beth** | Beth session READMEs | `session_id`, `beth_topics` | Workflow sessions |
| **hugo** | Hugo static sites | `title` | 500K+ users |
| **jekyll** | Jekyll (GitHub Pages) | `layout` | **1M+ users** |
| **mkdocs** | MkDocs documentation | _(none)_ | Large Python ecosystem |
| **obsidian** | Obsidian vaults | _(none)_ | 500K+ users |

### Beth Schema
**Target:** Session README files
**Required:**
- `session_id` - Pattern: `word-word-MMDD` (e.g., `cloudy-steam-0103`)
- `beth_topics` - List of topics (minimum 1)

**Optional:** date, badge, type, project, files_modified, files_created, commits

**Custom Validation:**
- Session ID format checking
- Topic count validation

**Example:**
```yaml
---
session_id: cloudy-steam-0103
date: 2026-01-03
badge: "Schema validation release prep"
beth_topics: [reveal, schema-validation, release-management]
type: production-execution
---
```

### Hugo Schema
**Target:** Hugo static site content (blogs, documentation)
**Required:**
- `title` - Non-empty string

**Optional:** date, draft, tags, categories, description, author, slug, weight

**Custom Validation:**
- Title length checking
- Date format validation

**Example:**
```yaml
---
title: "Getting Started with Reveal"
date: 2026-01-03
draft: false
tags: [documentation, tutorial]
---
```

### Jekyll Schema
**Target:** Jekyll sites (GitHub Pages)
**Required:**
- `layout` - Best practice enforcement (page, post, default)

**Optional:** title, date, categories, tags, author, permalink, excerpt, published

**Custom Validation:**
- Layout non-empty
- Permalink format validation
- Date format checking
- Published boolean validation

**Example:**
```yaml
---
layout: post
title: "My Blog Post"
date: 2026-01-03
categories: [tech, programming]
tags: [python, cli]
---
```

### MkDocs Schema
**Target:** MkDocs documentation (Material theme support)
**Required:** _(none - all fields optional)_

**Optional:** title, description, template, icon, status, tags, hide, authors, date

**Material Theme Support:**
- `hide`: [navigation, toc, footer]
- `status`: new, deprecated, beta, experimental

**Custom Validation:**
- Hide options validation
- Status value checking
- Date format validation
- Tags minimum count

**Example:**
```yaml
---
title: API Reference
description: Complete API documentation
status: new
hide:
  - navigation
  - toc
tags: [api, reference]
---
```

### Obsidian Schema
**Target:** Obsidian knowledge base notes
**Required:** _(none - fully optional)_

**Optional:** tags, aliases, cssclass, publish, created, modified, rating, priority

**Custom Validation:**
- Tag count validation (if specified)
- Rating range (1-5)
- Priority range (1-5)

**Example:**
```yaml
---
tags: [project, planning]
aliases: [Project Plan, Strategic Plan]
rating: 5
priority: 1
created: 2026-01-03
---
```

---

## Validation Rules (F-Series)

### F001: Missing Front Matter
**Detects:** Markdown files with no YAML front matter block

**Severity:** Medium

**Example:**
```
/path/to/file.md:1:1 ⚠️  F001 No front matter found in markdown file
  💡 Add front matter block at top of file
  📝 Schema: Beth Session Schema
```

**How to fix:**
```markdown
---
session_id: my-session-0103
beth_topics: [testing]
---

# Your Content
```

### F002: Empty Front Matter
**Detects:** Front matter block exists but contains no data

**Severity:** Medium

**Example:**
```
/path/to/file.md:1:1 ⚠️  F002 Front matter is empty
  💡 Add required fields to front matter
  📝 Schema: Hugo Static Site Schema
```

**How to fix:**
```markdown
---
title: "My Post"
date: 2026-01-03
---
```

### F003: Required Field Missing
**Detects:** Schema requires field but it's not present

**Severity:** Medium

**Example:**
```
/path/to/file.md:1:1 ⚠️  F003 Required field 'title' missing from front matter
  💡 Add 'title' to front matter
  📝 Schema: Hugo Static Site Schema
```

**How to fix:**
```markdown
---
# Add the missing required field
title: "My Blog Post"
date: 2026-01-03
---
```

### F004: Field Type Mismatch
**Detects:** Field has wrong data type (string vs list vs dict vs integer)

**Severity:** Medium

**Example:**
```
/path/to/file.md:1:1 ⚠️  F004 Field 'tags' has wrong type (expected list, got string)
  💡 Change 'tags' to list
  📝 Schema: Hugo Static Site Schema
```

**How to fix:**
```markdown
# Wrong:
tags: single-tag

# Correct:
tags: [single-tag, another-tag]
```

### F005: Custom Validation Failed
**Detects:** Custom schema rule violations (Python expressions)

**Severity:** Medium

**Example:**
```
/path/to/file.md:1:1 ⚠️  F005 Custom validation failed: Session ID format invalid
  💡 Session ID must match pattern: word-word-MMDD
  📝 Schema: Beth Session Schema
```

**How to fix:**
```markdown
# Wrong:
session_id: my_session_01

# Correct:
session_id: cloudy-steam-0103
```

---

## Output Formats

### Text Format (Human-Readable)
Default output for terminal use:

```bash
reveal README.md --validate-schema beth
```

**Output:**
```
/path/to/README.md:1:1 ⚠️  F003 Required field 'session_id' missing from front matter
  💡 Add 'session_id' to front matter
  📝 Schema: Beth Session Schema

1 issue found
```

### JSON Format (CI/CD)
Structured output for automation:

```bash
reveal README.md --validate-schema beth --format json
```

**Output:**
```json
{
  "detections": [
    {
      "file": "/path/to/README.md",
      "line": 1,
      "column": 1,
      "code": "F003",
      "message": "Required field 'session_id' missing from front matter",
      "severity": "medium",
      "suggestion": "Add 'session_id' to front matter",
      "context": "Schema: Beth Session Schema"
    }
  ],
  "summary": {
    "total": 1,
    "high": 0,
    "medium": 1,
    "low": 0
  }
}
```

### Grep Format (Pipeable)
Minimal output for scripting:

```bash
reveal README.md --validate-schema beth --format grep
```

**Output:**
```
/path/to/README.md:1:1:F003:Required field 'session_id' missing
```

---

## CI/CD Integration

### Exit Codes
- **0** - All validation passed
- **1** - Validation failures detected

### GitHub Actions Example

```yaml
name: Validate Documentation
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install reveal
        run: pip install reveal-cli
      - name: Validate session READMEs
        run: |
          for file in sessions/*/README.md; do
            reveal "$file" --validate-schema beth || exit 1
          done
      - name: Validate blog posts
        run: |
          for file in content/posts/*.md; do
            reveal "$file" --validate-schema hugo || exit 1
          done
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Validate staged markdown files
for file in $(git diff --cached --name-only --diff-filter=ACM | grep '\.md$'); do
  if [[ $file == sessions/*/README.md ]]; then
    reveal "$file" --validate-schema beth || exit 1
  elif [[ $file == content/posts/*.md ]]; then
    reveal "$file" --validate-schema hugo || exit 1
  fi
done
```

### GitLab CI Example

```yaml
validate-docs:
  stage: test
  script:
    - pip install reveal-cli
    - find docs -name "*.md" -exec reveal {} --validate-schema mkdocs \; || exit 1
```

---

## Custom Schemas

### Creating a Custom Schema

Create a YAML file defining your schema:

**my-schema.yaml:**
```yaml
name: "My Custom Schema"
description: "Project documentation schema"

required_fields:
  - title
  - author

optional_fields:
  - date
  - version
  - tags

field_types:
  title: string
  author: string
  date: date
  version: string
  tags: list

validation_rules:
  - name: "Title length check"
    expression: "len(title) >= 10"
    message: "Title must be at least 10 characters"
  - name: "Author not empty"
    expression: "len(author) > 0"
    message: "Author cannot be empty"
```

### Using Custom Schema

```bash
reveal document.md --validate-schema /path/to/my-schema.yaml
```

### Custom Validation Expressions

**Available functions:**
- `len()` - Length of string/list
- `re.match(pattern, string)` - Regex matching
- `isinstance(value, type)` - Type checking
- `str()`, `int()`, `bool()` - Type conversions
- `all()`, `any()` - List checks

**Examples:**
```yaml
validation_rules:
  # Check minimum length
  - expression: "len(title) >= 10"
    message: "Title too short"

  # Regex pattern matching
  - expression: "re.match(r'^[A-Z]', title)"
    message: "Title must start with capital letter"

  # List validation
  - expression: "len(tags) >= 1"
    message: "At least one tag required"

  # Range checking
  - expression: "priority >= 1 and priority <= 5"
    message: "Priority must be 1-5"
```

**Security:** Custom validation uses **safe eval** with restricted builtins - no file I/O, network access, or command execution.

---

## Common Workflows

### Batch Validation

```bash
# Validate all session READMEs
find sessions -name "README.md" -exec reveal {} --validate-schema beth \;

# Validate all blog posts
find content/posts -name "*.md" -exec reveal {} --validate-schema hugo \;

# Validate with error counting
find docs -name "*.md" -exec reveal {} --validate-schema mkdocs --format json \; | \
  jq -s 'map(.summary.total) | add'
```

### Selective Rule Checking

```bash
# Only check required fields
reveal README.md --validate-schema beth --select F003

# Check types and custom rules only
reveal post.md --validate-schema hugo --select F004,F005

# Skip empty front matter check
reveal note.md --validate-schema obsidian --ignore F002
```

### Format Conversion Pipeline

```bash
# Find all issues, output as JSON, filter with jq
reveal README.md --validate-schema beth --format json | \
  jq '.detections[] | select(.severity == "high")'

# Count issues by rule code
reveal README.md --validate-schema beth --format json | \
  jq '.detections | group_by(.code) | map({code: .[0].code, count: length})'
```

---

## Troubleshooting

### Schema Not Found

**Error:**
```
Error: Schema 'myschema' not found
```

**Solutions:**
1. Check spelling (case-sensitive)
2. Use full path for custom schemas: `/path/to/schema.yaml`
3. Verify schema file exists and is readable
4. List available built-in schemas: `beth`, `hugo`, `jekyll`, `mkdocs`, `obsidian`

### Invalid YAML Syntax

**Error:**
```
Error: Failed to parse front matter YAML
```

**Solutions:**
1. Check YAML syntax (use YAML linter)
2. Ensure proper indentation (spaces, not tabs)
3. Quote strings with special characters
4. Verify closing `---` delimiter exists

### Custom Validation Fails

**Error:**
```
F005 Custom validation failed: <expression>
```

**Solutions:**
1. Check expression syntax in schema YAML
2. Verify field names match front matter exactly (case-sensitive)
3. Ensure expression returns boolean (true/false)
4. Test expression with simple values first

### No Issues Detected But Expected

**Possible causes:**
1. Wrong schema selected (hugo vs jekyll vs mkdocs)
2. Front matter missing entirely (F001 should catch this)
3. Schema has no required fields (mkdocs, obsidian)
4. Rule ignored with `--ignore F003`

**Debug:**
```bash
# Show all rules being run
reveal README.md --validate-schema beth --verbose

# Check which rules are selected
reveal --rules | grep F00
```

---

## Performance

- **Zero impact** when `--validate-schema` not used
- **Millisecond validation** for F001-F005 rules
- **Schema caching** after first load
- **No additional dependencies** (uses core PyYAML)

---

## See Also

- **F-series rules:** `reveal --explain F001` through `reveal --explain F005`
- **Configuration:** `reveal help://configuration` for `.reveal.yaml` setup
- **Anti-patterns:** `reveal help://anti-patterns` for common mistakes

---

## Version History

- **v0.29.0** - Initial release (Jan 2026)
  - 5 built-in schemas (beth, hugo, jekyll, mkdocs, obsidian)
  - F001-F005 validation rules
  - Custom schema support
  - CI/CD integration (exit codes, JSON output)
  - 103 comprehensive tests

## See Also

- [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - Project-wide configuration options
- [MARKDOWN_GUIDE.md](MARKDOWN_GUIDE.md) - Markdown analysis and front matter reference
