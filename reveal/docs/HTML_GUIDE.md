---
title: HTML Analysis with Reveal
category: guide
---
# HTML Analysis with Reveal

First-class HTML support for reveal with progressive disclosure, template awareness, and semantic structure extraction.

## Quick Start

### View HTML Structure

```bash
# Default view - semantic elements and template blocks
reveal page.html

# Extract all links
reveal page.html --links

# Get metadata (SEO, OpenGraph, Twitter cards)
reveal page.html --metadata

# Extract specific element by ID, class, or CSS selector
reveal page.html "#search-form"
reveal page.html ".hero-section"
reveal page.html "nav ul li"
```

## Features

### 1. Template Detection

Automatically detects and handles template engines:

- **Jinja2** (FastHTML, Flask, Django)
- **Go templates** (Hugo)
- **Handlebars**
- **ERB** (Ruby)
- **PHP**

**Example:**
```bash
$ reveal base.html
File: base.html (6.8KB, 170 lines)

Elements (18):
  base.html:6   <title>: {% block title %}Site{% endblock %}
  base.html:16  <nav> .sidebar
  base.html:81  <main> #main-content
  ...

Template_blocks (8):
  base.html:6   title
  base.html:9   description
  base.html:83  content
```

### 2. Semantic Element Extraction

Extracts HTML5 semantic elements with progressive disclosure:

```bash
# Default view shows semantic structure
reveal page.html

# Extract specific semantic elements
reveal page.html --semantic navigation  # nav, header
reveal page.html --semantic content     # main, article, section
reveal page.html --semantic forms       # All forms
reveal page.html --semantic media       # img, video, audio
```

**Output shows:**
- Semantic HTML elements (nav, header, main, article, section, footer)
- Element IDs and classes
- Line numbers for quick navigation

### 3. Link Extraction and Validation

```bash
# Extract all links
reveal page.html --links

# Filter by link type
reveal page.html --links --link-type internal
reveal page.html --links --link-type external

# Filter by domain
reveal page.html --links --domain example.com

# Check for broken links (local files only)
reveal page.html --links --broken
```

**Link types detected:**
- `internal` - `/path` links
- `external` - `https://` links
- `anchor` - `#section` links
- `mailto` - Email links
- `tel` - Phone number links
- `relative` - `./page.html` links

### 4. Metadata Extraction

Extract SEO and social media metadata:

```bash
# Get all metadata
reveal page.html --metadata

# JSON format for processing
reveal page.html --metadata --format json
```

**Extracts:**
- Page title
- Meta tags (description, keywords, author)
- OpenGraph tags (og:title, og:description, og:image)
- Twitter Card tags
- Canonical URL
- Stylesheets and scripts

### 5. Element Extraction

Extract specific HTML elements by selector:

```bash
# By ID
reveal page.html "#main-content"
reveal page.html "search-form"  # ID without #

# By class
reveal page.html ".hero-section"

# By tag
reveal page.html "form"
reveal page.html "table"

# By CSS selector
reveal page.html "nav ul li"
reveal page.html "div.content > p"
```

### 6. Script and Style Analysis

```bash
# Extract all scripts
reveal page.html --scripts all

# Only inline scripts
reveal page.html --scripts inline

# Only external scripts
reveal page.html --scripts external

# Extract all stylesheets
reveal page.html --styles all

# Only inline styles
reveal page.html --styles inline

# Only external stylesheets
reveal page.html --styles external
```

## Common Workflows

### Template Auditing

See what blocks and variables a template uses:

```bash
# View template structure
reveal templates/base.html

# Find all templates using specific block
reveal templates/*.html | grep "block content"

# Check template variable usage
reveal template.html --format json | jq '.template.variables'
```

### Web Scraping Preparation

Understand page structure before writing scraping code:

```bash
# See overall structure
reveal scraped_page.html

# Find specific data containers
reveal scraped_page.html ".product-list"

# Get all links for crawling
reveal scraped_page.html --links --format json

# Extract data tables
reveal scraped_page.html "table.data"
```

### SEO/Social Media Optimization

```bash
# Check metadata completeness
reveal index.html --metadata

# Verify OpenGraph tags
reveal page.html --metadata --format json | jq '.meta | select(has("og:title"))'

# Find pages missing descriptions
for f in site/**/*.html; do
  reveal "$f" --metadata | grep -q "description" || echo "$f: missing description"
done
```

### Link Validation

```bash
# Check for broken internal links
reveal site/**/*.html --links --broken

# Find all external links
reveal page.html --links --link-type external

# Verify all links to specific domain
reveal page.html --links --domain example.com
```

### Documentation Review

```bash
# See documentation structure
reveal docs/api.html

# Extract specific section
reveal docs/api.html "#authentication"

# Find all code examples
reveal docs/*.html --scripts inline
```

## Progressive Disclosure

The HTML analyzer follows reveal's progressive disclosure philosophy:

**Structure first** (default view):
- Shows high-level organization (50-200 tokens)
- Semantic elements, meta tags, template blocks
- Quick overview before deep dive

**Selective extraction**:
- `--links` - Extract all links
- `--metadata` - Get SEO/social metadata
- `--semantic TYPE` - Specific semantic elements
- `"#selector"` - Extract specific element

**Full details when needed**:
- Element extraction shows complete HTML
- `--format json` for machine processing
- `--head`/`--tail`/`--range` for line-based navigation

## Template Support

### Jinja2 (FastHTML, Flask, Django)

```html
{% block title %}Page Title{% endblock %}
{{ variable.name }}
{% if condition %}...{% endif %}
```

**Detection:** `{% %}` and `{{ }}` syntax
**Extracts:** Blocks, variables, template directives

### Go Templates (Hugo)

```html
{{ .Title }}
{{ range .Pages }}...{{ end }}
{{- with .Params.author -}}...{{- end -}}
```

**Detection:** `{{ . }}` syntax
**Extracts:** Field references, variables

### Handlebars

```html
{{#if user}}
  <p>Hello {{user.name}}</p>
{{/if}}
{{#each items}}...{{/each}}
```

**Detection:** `{{#if}}`, `{{#each}}` helpers
**Extracts:** Helpers, variables

## Integration with Reveal Features

Works with all standard reveal features:

```bash
# Line navigation
reveal page.html --head 50        # First 50 lines
reveal page.html --tail 30        # Last 30 lines
reveal page.html --range 10-50    # Lines 10-50

# Output formats
reveal page.html --format json    # JSON output
reveal page.html --format grep    # Grep-compatible

# Element extraction
reveal page.html form             # First form
reveal page.html "#search"        # Element by ID
```

## Token Efficiency

HTML analyzer provides massive token savings through progressive disclosure:

- **Structure view**: 50-200 tokens (semantic elements, meta tags)
- **Full HTML**: 5,000+ tokens (raw HTML content)
- **Savings**: **25-100x fewer tokens**

Perfect for AI workflows where you need to understand HTML structure before processing.

## Examples

### FastHTML Project

```bash
# Analyze FastHTML route template
reveal app/templates/index.html

# Check all templates for required blocks
reveal app/templates/*.html | grep "block content"

# Find templates missing navigation
reveal app/templates/*.html | grep -v "nav"
```

### Hugo Site

```bash
# Analyze theme layout
reveal themes/mytheme/layouts/_default/single.html

# Find all partial templates
find layouts/partials -name "*.html" -exec reveal {} \;

# Check for missing OpenGraph tags
reveal layouts/_default/baseof.html --metadata
```

### Static Website

```bash
# Validate all internal links
reveal public/**/*.html --links --broken

# Extract all images for optimization
reveal public/**/*.html --semantic media

# Check SEO metadata across site
for f in public/**/*.html; do
  reveal "$f" --metadata --format json >> seo-audit.jsonl
done
```

## Tips

1. **Use progressive disclosure**: Start with default view, then drill down
2. **Check templates first**: Template blocks show page structure quickly
3. **Validate links early**: Catch broken links before deployment
4. **Extract before scraping**: Use reveal to find selectors
5. **Automate SEO checks**: Script metadata extraction for audits

## Limitations

- **Broken link checking**: Only works for local files (not external URLs)
- **Line numbers**: Approximate for dynamically generated content
- **JavaScript**: Analyzes static HTML only (no JS rendering)

## Dependencies

The HTML analyzer requires:

- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=4.9.0` - Fast XML/HTML parser backend

Both are included in reveal's default dependencies.

## See Also

- [MARKDOWN_GUIDE.md](./MARKDOWN_GUIDE.md) - Similar progressive disclosure for Markdown
- [AGENT_HELP.md](./AGENT_HELP.md) - Full reveal agent guide
- [RECIPES.md](./RECIPES.md) - Advanced reveal patterns

---

**Feedback**: Found a bug or have a feature request? [Open an issue](https://github.com/Semantic-Infrastructure-Lab/reveal/issues)
