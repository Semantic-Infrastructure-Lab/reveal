# Schema Validation Guide

**Reveal v0.29+** includes production-ready schema validation for Markdown front matter through F-series quality rules and the `--validate-schema` flag.

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

## Built-in Schemas

| Schema | Purpose | Required Fields | Use Case |
|--------|---------|----------------|----------|
| **beth** | Beth session READMEs | `session_id`, `beth_topics` | Workflow session documentation |
| **hugo** | Hugo static sites | `title` | Blog posts, static pages |
| **jekyll** | Jekyll sites (GitHub Pages) | `layout` | GitHub Pages blogs |
| **mkdocs** | MkDocs documentation | _(none)_ | Python project docs (FastAPI, NumPy) |
| **obsidian** | Obsidian vaults | _(none)_ | Personal knowledge management |

---

## Validation Rules

| Rule | Description | Severity |
|------|-------------|----------|
| **F001** | Missing front matter | Medium |
| **F002** | Empty front matter | Medium |
| **F003** | Required field missing | Medium |
| **F004** | Field type mismatch | Medium |
| **F005** | Custom validation failed | Medium |

---

## F001: Missing Front Matter

**Detects:**
- Markdown files with no YAML front matter block
- Files missing opening `---` delimiter

**Example output:**
```
/path/to/file.md:1:1 ⚠️  F001 No front matter found in markdown file
  💡 Add front matter block at top of file
  📝 Schema: Beth Session Schema
```

**How to fix:**
```markdown
---
session_id: my-session-0102
beth_topics: [testing]
---

# Your Content
```

---

## F002: Empty Front Matter

**Detects:**
- Front matter block exists but contains no data
- Only whitespace between `---` delimiters

**Example output:**
```
/path/to/file.md:1:1 ⚠️  F002 Front matter is empty
  💡 Add required fields to front matter
  📝 Schema: Hugo Static Site Schema
```

**How to fix:**
```markdown
---
title: "My Post"
date: 2026-01-02
---

# Content
```

---

## F003: Required Field Missing

**Detects:**
- Schema requires field but it's not present in front matter
- Checks all fields listed in schema's `required_fields`

**Example output:**
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
date: 2026-01-02
---
```

---

## F004: Field Type Mismatch

**Detects:**
- Field has wrong data type (string vs list vs integer, etc.)
- Violates schema's `field_types` constraints

**Example output:**
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

**Supported types:**
- `string` - Text value (`"hello"`)
- `list` - Array (`[item1, item2]`)
- `dict` - Object (`{key: value}`)
- `integer` - Whole number (`42`)
- `boolean` - True/false (`true`)
- `date` - Date value (`2026-01-02` or YAML date object)

---

## F005: Custom Validation Failed

**Detects:**
- Field value doesn't meet custom validation rules
- Examples: format patterns, value ranges, length constraints

**Example output:**
```
/path/to/file.md:1:1 ⚠️  F005 session_id format must be: word-word-MMDD (e.g., 'garnet-ember-0102')
  💡 Fix value of 'session_id' field
  📝 Schema: Beth Session Schema | Check: re.match(r'^[a-z]+-[a-z]+-\d{4}$', value)
```

**How to fix:**
```markdown
# Wrong:
session_id: mysession-0102

# Correct (matches pattern):
session_id: my-session-0102
```

---

## Beth Schema

**Purpose:** Validate Beth session README files

**Required fields:**
- `session_id` - Session identifier (format: `word-word-MMDD`)
- `beth_topics` - List of topics (at least 1)

**Optional fields:**
- `date` - Session date (YYYY-MM-DD)
- `badge` - Session badge/description
- `type` - Session type
- `project` - Related project
- `files_modified`, `files_created`, `commits` - Metadata counts

**Custom validations:**
- `session_id` must match pattern: `^[a-z]+-[a-z]+-\d{4}$`
- `beth_topics` must have at least 1 topic

**Example:**
```yaml
---
session_id: garnet-ember-0102
date: 2026-01-02
badge: "Schema Validation Phase 1"
beth_topics: [reveal, schema-validation, yaml]
type: development
project: reveal
files_modified: 3
files_created: 2
commits: 1
---

# Session README
```

---

## Hugo Schema

**Purpose:** Validate Hugo static site front matter

**Required fields:**
- `title` - Post title (non-empty string)

**Optional fields:**
- `date` - Publication date (YYYY-MM-DD format, typically required for blog posts)
- `draft` - Draft status (boolean)
- `tags` - Post tags (list)
- `categories` - Post categories (list)
- `description` - Post description
- `author` - Post author
- `slug` - URL slug
- `weight` - Ordering weight (integer)
- `featured_image` - Image path
- `summary` - Post summary
- `toc` - Table of contents (boolean)
- `type` - Content type
- `layout` - Layout template

**Custom validations:**
- `title` cannot be empty
- `date` must be YYYY-MM-DD format (or valid YAML date)

**Example:**
```yaml
---
title: "Getting Started with Reveal"
date: 2026-01-02
draft: false
tags: [python, cli, tools]
categories: [development, tutorial]
description: "A comprehensive guide to using Reveal"
author: "Scott"
slug: "getting-started-reveal"
toc: true
---

# Post Content
```

---

## Jekyll Schema

**Purpose:** Validate Jekyll static site front matter (GitHub Pages compatible)

**Required fields:**
- `layout` - Page layout (e.g., `post`, `page`, `default`, `home`)

**Optional fields:**
- `title` - Post/page title
- `date` - Publication date (YYYY-MM-DD format, typically required for posts)
- `categories` - Post categories (list or string)
- `tags` - Post tags (list or string)
- `author` - Post author
- `permalink` - Custom URL (must start with `/`)
- `excerpt` - Post excerpt/summary
- `published` - Publication status (boolean)
- `description` - Meta description
- `image` - Featured image path
- `comments` - Enable comments (boolean)
- `sitemap` - Include in sitemap (boolean)
- `lang` - Content language
- `redirect_from` - Redirect sources (list)
- `redirect_to` - Redirect destination

**Custom validations:**
- `layout` must be non-empty (common values: default, post, page, home)
- `title` cannot be empty if specified
- `date` must be YYYY-MM-DD format (or valid YAML date)
- `permalink` must start with `/` (e.g., `/posts/my-post/`)
- `published` must be boolean (true/false)

**Example:**
```yaml
---
layout: post
title: "Building with Jekyll on GitHub Pages"
date: 2026-01-03
categories: [tutorial, github]
tags: [jekyll, github-pages, static-sites]
author: "Developer"
excerpt: "Learn how to build and deploy Jekyll sites on GitHub Pages"
permalink: /posts/jekyll-github-pages/
published: true
---

# Post Content
```

---

## MkDocs Schema

**Purpose:** Validate MkDocs documentation front matter (including Material theme)

**Required fields:** _(none - all optional)_

**Optional fields:**
- `title` - Page title (overrides h1)
- `description` - Page description for meta tags and social cards
- `template` - Custom template to use (default: main.html)
- `icon` - Icon for navigation sidebar (Material theme)
- `status` - Page status (new, deprecated, beta, experimental)
- `tags` - Page tags (Material theme with tags plugin)
- `hide` - Hide elements: navigation, toc, footer (Material theme)
- `authors` - Document authors (list)
- `date` - Document date (YYYY-MM-DD)
- `summary` - Brief summary/excerpt
- `comments` - Enable comments (boolean, Material theme)
- `feedback` - Enable feedback widget (boolean, Material theme)

**Custom validations:**
- `title` cannot be empty if specified
- `hide` options must be 'navigation', 'toc', or 'footer'
- `date` must be YYYY-MM-DD format (or valid YAML date)
- `tags` must have at least one tag if specified
- `status` should be one of: new, deprecated, beta, experimental

**Example:**
```yaml
---
title: "API Reference"
description: "Complete API documentation for the project"
icon: material/api
status: new
tags:
  - api
  - reference
  - python
hide:
  - navigation
  - toc
authors:
  - Development Team
date: 2026-01-03
comments: false
---

# API Reference

Documentation content here.
```

---

## Obsidian Schema

**Purpose:** Validate Obsidian vault note front matter

**Required fields:** _(none - all optional)_

**Optional fields:**
- `tags` - Note tags (list, at least 1 if specified)
- `aliases` - Alternative note names (list)
- `cssclass` - Single CSS class (string)
- `cssclasses` - Multiple CSS classes (list)
- `publish` - Publish status (boolean)
- `permalink` - Custom URL slug
- `created` - Creation date (YYYY-MM-DD)
- `modified` - Modification date (YYYY-MM-DD)
- `rating` - Note rating (1-5)
- `status` - Note status (string)
- `due` - Due date (YYYY-MM-DD)
- `completed` - Completion status (boolean)
- `priority` - Priority level (1-5)
- `author` - Note author

**Custom validations:**
- `tags` must have at least 1 tag if specified
- `rating` must be between 1-5
- `priority` must be between 1-5

**Example:**
```yaml
---
tags: [productivity, notes, gtd]
aliases: [productivity-guide, getting-things-done]
cssclass: clean
publish: true
created: 2026-01-01
modified: 2026-01-02
rating: 5
status: active
priority: 1
author: "Scott"
---

# Productivity Tips
```

---

## Custom Schemas

Create your own validation schemas for project-specific front matter.

### Schema Format

```yaml
name: "My Custom Schema"
description: "Optional description"
version: "1.0"

# Required fields (must be present)
required_fields:
  - title
  - author

# Optional fields (commonly used but not required)
optional_fields:
  - tags
  - date

# Field type constraints
field_types:
  title: string
  author: string
  tags: list
  date: date
  published: boolean
  priority: integer

# Custom validation rules
validation_rules:
  - code: F005
    field: title
    check: "len(value) >= 5"
    message: "Title must be at least 5 characters"

  - code: F005
    field: priority
    check: "1 <= value <= 10"
    message: "Priority must be between 1 and 10"
```

### Field Types

| Type | Python Type | Example YAML |
|------|-------------|--------------|
| `string` | `str` | `title: "Hello"` |
| `list` | `list` | `tags: [a, b, c]` |
| `dict` | `dict` | `meta: {key: value}` |
| `integer` | `int` | `count: 42` |
| `boolean` | `bool` | `draft: true` |
| `date` | `str` or `datetime.date` | `date: 2026-01-02` |

### Validation Rules

Custom validation rules use Python expressions evaluated safely:

**Available functions:**
- `len(value)` - Length of string/list
- `re.match(pattern, value)` - Regex matching
- `isinstance(value, type)` - Type checking
- `str(value)`, `int(value)`, `bool(value)` - Type conversions

**Examples:**
```yaml
# Length check
check: "len(value) >= 1"

# Regex pattern
check: "re.match(r'^[A-Z]', value)"

# Range validation
check: "1 <= value <= 100"

# Conditional check
check: "isinstance(value, list) and len(value) >= 1"
```

### Using Custom Schemas

```bash
# Create schema file
cat > blog-schema.yaml << 'EOF'
name: "Blog Post Schema"
required_fields:
  - title
  - author
  - publish_date
field_types:
  title: string
  author: string
  publish_date: date
  tags: list
validation_rules:
  - code: F005
    field: title
    check: "len(value) >= 10"
    message: "Title must be at least 10 characters"
EOF

# Validate with custom schema
reveal my-post.md --validate-schema blog-schema.yaml
```

---

## Output Formats

### Text Format (Default)

Human-readable output with colors and formatting:

```bash
reveal README.md --validate-schema beth
```

```
/path/to/README.md: Found 2 issues

/path/to/README.md:1:1 ⚠️  F003 Required field 'session_id' missing from front matter
  💡 Add 'session_id' to front matter
  📝 Schema: Beth Session Schema

/path/to/README.md:1:1 ⚠️  F004 Field 'date' has wrong type (expected date, got string)
  💡 Change 'date' to date
  📝 Schema: Beth Session Schema
```

### JSON Format

Machine-readable output for CI/CD pipelines:

```bash
reveal README.md --validate-schema beth --format json
```

```json
[
  {
    "file_path": "/path/to/README.md",
    "line": 1,
    "column": 1,
    "rule": "F003",
    "message": "Required field 'session_id' missing from front matter",
    "severity": "medium",
    "suggestion": "Add 'session_id' to front matter"
  }
]
```

### Grep Format

Pipeable output for filtering:

```bash
reveal README.md --validate-schema beth --format grep
```

```
/path/to/README.md:1:1: F003: Required field 'session_id' missing from front matter
```

---

## CI/CD Integration

### Pre-commit Hook

Validate before committing:

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Find all modified markdown files
modified_md=$(git diff --cached --name-only --diff-filter=ACM | grep '\.md$')

if [ -n "$modified_md" ]; then
  echo "Validating markdown front matter..."
  for file in $modified_md; do
    if [[ $file == *"README.md" ]]; then
      reveal "$file" --validate-schema beth || exit 1
    fi
  done
fi
```

### GitHub Actions

```yaml
name: Validate Front Matter

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install Reveal
        run: pip install reveal-tool

      - name: Validate Beth READMEs
        run: |
          find . -name "README.md" -type f | while read file; do
            reveal "$file" --validate-schema beth --format json
          done

      - name: Validate Hugo posts
        run: |
          find content/posts -name "*.md" | while read file; do
            reveal "$file" --validate-schema hugo
          done
```

### GitLab CI

```yaml
validate_frontmatter:
  stage: test
  script:
    - pip install reveal-tool
    - find docs -name "*.md" | xargs -I {} reveal {} --validate-schema hugo
  only:
    - merge_requests
```

---

## Command-Line Reference

### Basic Usage

```bash
# Validate with built-in schema
reveal <file> --validate-schema <schema-name>

# Validate with custom schema
reveal <file> --validate-schema <path-to-schema.yaml>
```

### Options

```bash
# Select specific rules
reveal file.md --validate-schema beth --select F003,F004

# Ignore specific rules
reveal file.md --validate-schema beth --ignore F001,F002

# Change output format
reveal file.md --validate-schema beth --format json
reveal file.md --validate-schema beth --format grep
reveal file.md --validate-schema beth --format text  # default

# Combine with other flags
reveal file.md --validate-schema beth --format json | jq '.[] | select(.rule == "F003")'
```

### Exit Codes

- **0** - Validation passed (no issues found)
- **1** - Validation failed (issues detected)
- **1** - Schema not found or invalid

### List Available Schemas

```bash
# Try to use nonexistent schema to see list
reveal file.md --validate-schema invalid-schema-name
```

Output:
```
Error: Schema 'invalid-schema-name' not found

Available built-in schemas:
  - beth
  - hugo
  - obsidian

Or provide a path to a custom schema file
```

---

## Common Workflows

### Batch Validation

Validate all files in a directory:

```bash
# Find and validate all READMEs
find . -name "README.md" -type f -exec reveal {} --validate-schema beth \;

# Validate Hugo content
find content -name "*.md" -exec reveal {} --validate-schema hugo \;

# Parallel validation (faster)
find . -name "*.md" | parallel reveal {} --validate-schema obsidian
```

### Filter by Rule

Focus on specific validation rules:

```bash
# Only check required fields
reveal README.md --validate-schema beth --select F003

# Only check types
reveal post.md --validate-schema hugo --select F004

# Check everything except empty front matter
reveal note.md --validate-schema obsidian --ignore F002
```

### CI/CD Pipeline

```bash
# Validate and capture exit code
if reveal README.md --validate-schema beth --format json > validation.json; then
  echo "✅ Validation passed"
else
  echo "❌ Validation failed"
  cat validation.json | jq '.[] | "\(.rule): \(.message)"'
  exit 1
fi
```

### Documentation Generation

Validate before building documentation site:

```bash
#!/bin/bash
# pre-build.sh

echo "Validating documentation front matter..."

# Validate all Hugo posts
find content/posts -name "*.md" | while read file; do
  if ! reveal "$file" --validate-schema hugo; then
    echo "❌ Failed: $file"
    exit 1
  fi
done

echo "✅ All documentation validated"
hugo build
```

---

## Troubleshooting

### Schema Not Found

**Error:**
```
Error: Schema 'myschema' not found
```

**Solutions:**
1. Check spelling: `beth`, `hugo`, `obsidian` (lowercase)
2. For custom schemas, provide full path: `/path/to/schema.yaml`
3. Verify custom schema file exists and is readable

### Invalid Schema Format

**Error:**
```
Error: Failed to parse YAML in /path/to/schema.yaml
```

**Solutions:**
1. Validate YAML syntax (use `yamllint` or online validator)
2. Ensure schema has required `name` field
3. Check for typos in field names

### Date Type Errors

**Issue:** Date fields showing type mismatch errors

**Explanation:** YAML automatically parses unquoted dates (`2026-01-02`) as date objects, not strings. Reveal v0.29+ handles this automatically for schemas with `date` type fields.

**Solutions:**
1. Use schemas with proper `date` type (beth, hugo, obsidian all support this)
2. Or quote dates in YAML: `date: "2026-01-02"`

### Empty Front Matter vs No Front Matter

**F001:** File has no front matter block at all
- **Fix:** Add `---` delimiters and content

**F002:** Front matter block exists but is empty
- **Fix:** Add fields to existing front matter block

### Custom Validation Not Working

**Issue:** F005 rules not triggering

**Debug:**
1. Verify field exists in front matter
2. Check validation `check` expression syntax
3. Test expression in Python REPL: `eval("len('test') >= 1")`
4. Ensure field name matches exactly (case-sensitive)

---

## Performance

### Speed

- **F001-F003:** Instant (schema lookup only)
- **F004:** Very fast (type checking)
- **F005:** Fast (simple Python expression evaluation)

### Optimization Tips

1. **Skip rules:** Use `--ignore` to skip unnecessary rules
2. **Parallel processing:** Use `parallel` or `xargs -P` for batch validation
3. **CI caching:** Cache Reveal installation in CI pipelines

---

## Security

### Safe Evaluation

Custom validation rules (`F005`) use **restricted eval**:

**Allowed:**
- `len()`, `str()`, `int()`, `bool()`, `list()`, `dict()`
- `re.match()` and regex functions
- `isinstance()` for type checking
- Basic operators: `+`, `-`, `*`, `/`, `<`, `>`, `==`, `and`, `or`

**Blocked:**
- `__import__`, `exec`, `eval`, `compile`
- File I/O operations
- Network access
- System commands

### Best Practices

1. **Review custom schemas** before using in CI/CD
2. **Use built-in schemas** when possible (pre-audited)
3. **Validate schema files** themselves (check YAML syntax)
4. **Limit permissions** for schema files in repositories

---

## Examples

### Blog Deployment Pipeline

```bash
#!/bin/bash
# deploy.sh

echo "📝 Validating blog posts..."

# Validate all posts
FAILED=0
for post in content/posts/*.md; do
  if ! reveal "$post" --validate-schema hugo --format grep; then
    FAILED=1
  fi
done

if [ $FAILED -eq 1 ]; then
  echo "❌ Validation failed - fix errors before deploying"
  exit 1
fi

echo "✅ All posts validated"
echo "🚀 Deploying..."
hugo deploy
```

### Knowledge Base Quality Check

```bash
#!/bin/bash
# check-vault.sh

# Count notes
TOTAL=$(find vault -name "*.md" | wc -l)
echo "📊 Checking $TOTAL Obsidian notes..."

# Validate with detailed output
PASSED=0
for note in vault/**/*.md; do
  if reveal "$note" --validate-schema obsidian 2>&1 | grep -q "Found 0 issues"; then
    ((PASSED++))
  fi
done

echo "✅ Passed: $PASSED/$TOTAL ($(( PASSED * 100 / TOTAL ))%)"
```

### Session Documentation Audit

```bash
#!/bin/bash
# audit-sessions.sh

# Find all session READMEs
SESSIONS=$(find sessions -name "README.md")

echo "📋 Auditing Beth session documentation..."

# Validate and generate report
echo "Session,Status,Issues" > audit-report.csv

for session in $SESSIONS; do
  result=$(reveal "$session" --validate-schema beth --format json 2>&1)

  if [ $? -eq 0 ]; then
    echo "$session,PASS,0" >> audit-report.csv
  else
    issues=$(echo "$result" | jq 'length')
    echo "$session,FAIL,$issues" >> audit-report.csv
  fi
done

echo "✅ Audit complete - see audit-report.csv"
```

---

## Migration Guide

### From Manual Validation

**Before:**
```python
# Custom validation script
import yaml

with open('README.md') as f:
    content = f.read()
    if content.startswith('---'):
        fm = yaml.safe_load(content.split('---')[1])
        assert 'session_id' in fm
        assert 'beth_topics' in fm
```

**After:**
```bash
reveal README.md --validate-schema beth
```

### From yamllint

**Before:**
```bash
yamllint README.md
```

**After (more specific):**
```bash
# Validates both YAML syntax AND schema
reveal README.md --validate-schema beth
```

### Adding to Existing Project

1. **Choose schema:** Pick beth/hugo/obsidian or create custom
2. **Test locally:** Run on sample files
3. **Add to pre-commit:** Validate before commits
4. **Add to CI:** Validate in pipeline
5. **Document:** Add usage to project README

---

## FAQ

**Q: Can I validate multiple files at once?**
A: Use shell loops or `parallel` command for batch validation.

**Q: Does this validate YAML syntax?**
A: Yes! Invalid YAML will be caught during parsing.

**Q: Can I create schema for non-Markdown files?**
A: Not yet - v0.29 only supports Markdown front matter. JSON/YAML validation coming in future releases.

**Q: What's the difference between F-series and other rules?**
A: F-series rules are schema-aware and only run with `--validate-schema`. Other rules (B, C, D, E, L, etc.) run with `--check`.

**Q: Can schemas inherit from each other?**
A: Not in v0.29 - each schema is independent. Schema composition coming in future releases.

**Q: How do I validate frontmatter with nested objects?**
A: Use `dict` type for nested objects. Nested validation coming in v0.30.

**Q: Can I use this in pre-commit framework?**
A: Yes! Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: validate-frontmatter
      name: Validate Front Matter
      entry: reveal
      args: [--validate-schema, beth]
      language: system
      files: README\.md$
```

---

## Changelog

**v0.29.0** (2026-01-02)
- Initial schema validation release
- Built-in schemas: beth, hugo, obsidian
- F001-F005 validation rules
- `--validate-schema` CLI flag
- Custom schema support
- JSON/grep/text output formats

---

## See Also

- [Link Validation Guide](LINK_VALIDATION_GUIDE.md) - L-series rules
- [reveal --help](../reveal/docs/AGENT_HELP.md) - Full CLI reference
- [ROADMAP.md](../ROADMAP.md) - Feature roadmap

---

**Questions or issues?** File a bug report or feature request on GitHub.
