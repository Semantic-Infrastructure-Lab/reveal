# Reveal Markdown Support - Issues & Improvement Opportunities

**Date**: 2025-12-11
**Session**: visible-pulsar-1211
**Version Tested**: v0.21.0
**Status**: ✅ ALL ISSUES FIXED in v0.22.0-v0.23.1

**Update (2025-12-14)**: All issues identified below have been resolved:
- Issue #1 (--links): Fixed in v0.22.0
- Issue #2 (help://markdown): Added in v0.23.0
- Issue #3 (--outline hierarchy): Fixed in v0.22.0
- Issues #4-5: Design decisions, documented in help://markdown

---

## Executive Summary

Comprehensive testing of reveal's markdown support uncovered significant gaps between **documented features** and **actual behavior**, plus missing discoverability through the help:// system. While core functionality works well, several features either don't work as documented or lack proper documentation.

**Impact**: Users struggle to discover markdown capabilities and encounter broken workflows when following documentation examples.

---

## Key Findings

### ✅ What Works Well

1. **Heading extraction** (default behavior) - Excellent
2. **Section extraction by name**: `reveal README.md "Executive Summary"` - Works perfectly
3. **Progressive disclosure**: `--head`, `--tail`, `--range` - Works as expected
4. **Code block extraction**: `--code --language python` - Works well
5. **JSON output** with full metadata - Complete and useful
6. **--stdin pipeline** support - Excellent for aggregate analysis
7. **Heading levels in JSON** - Properly structured

### ❌ Critical Issues

1. **--links text output broken** (HIGH priority)
2. **Missing help://markdown topic** (MEDIUM priority)
3. **--outline lacks hierarchy** (MEDIUM priority)
4. **Bare URLs not extracted** (LOW priority - design decision)

---

## Issue #1: --links Text Output Broken

### Problem

`reveal README.md --links` shows headings instead of links in text format, contradicting documentation.

### Evidence

```bash
# What help://tricks says:
reveal README.md --links                      # Extract all links

# What actually happens:
$ reveal README.md --links
File: README.md
Headings (27):
  README.md:15    Title
  README.md:24    Executive Summary
  # ... (shows headings, NOT links!)

# Workaround (what actually works):
$ reveal README.md --links --format=json | jq '.structure.links'
[
  {
    "line": 596,
    "text": "Claude Code",
    "url": "https://claude.com/claude-code",
    "type": "external",
    "protocol": "https",
    "domain": "claude.com"
  }
]
```

### Current Behavior

- Text format: Ignores `--links` flag, shows headings
- JSON format: Works correctly, extracts links with full metadata

### Expected Behavior

Text format should show links similar to how `--code` shows code blocks:

```
File: README.md

Links (5):

  External (3 links):
    Line 26: Claude Code
      → https://claude.com/claude-code
    Line 29: SIL Website
      → https://semanticinfrastructurelab.org

  Internal (2 links):
    Line 40: Architecture Docs
      → docs/ARCHITECTURE.md
```

### Affected Documentation

- `reveal --help` examples show text output
- `reveal help://tricks` "Markdown Surgery" section
- All examples assume text format works

### Priority

**HIGH** - Breaks documented workflows, confusing for users

---

## Issue #2: Missing help://markdown Topic

### Problem

Markdown is fully supported but has no help:// documentation, making it undiscoverable through reveal's primary help system.

### Evidence

```bash
$ reveal --list-supported
# Shows: Markdown .md (built-in analyzer) ✓

$ reveal help://
# Available topics: ast, env, help, json, python
# Missing: markdown ❌

$ reveal help://markdown
Error: Help topic 'markdown' not found
```

### Comparison with Other File Types

| Feature | URI Adapter | help:// Topic | --list-supported |
|---------|-------------|---------------|------------------|
| Python  | python://   | ✓ help://python | ✓ .py |
| JSON    | json://     | ✓ help://json   | ✓ .json |
| AST     | ast://      | ✓ help://ast    | ✓ (via tree-sitter) |
| **Markdown** | ❌ None | **❌ Missing** | ✓ .md |

### Impact

- Users rely on `help://` for progressive discovery
- Markdown features hidden unless user reads `--help` output
- Inconsistent with other well-documented analyzers

### Proposed Solution

Add `reveal help://markdown` covering:

```markdown
# markdown - Extract structure, links, and code from Markdown files

**What it does:** Parse .md/.markdown files to extract headings, links,
and code blocks with progressive disclosure support.

## Basic Usage

  reveal README.md                     # Show heading structure
  reveal README.md "Section Name"      # Extract specific section
  reveal README.md --head 5            # First 5 headings

## Extract Links

  reveal README.md --links                      # All links (JSON only)
  reveal README.md --links --format=json        # Full metadata
  reveal README.md --links --link-type=external # GitHub, APIs
  reveal README.md --links --domain=github.com  # Filter by domain

## Extract Code Blocks

  reveal README.md --code                  # All code blocks
  reveal README.md --code --language=python # Python examples only
  reveal README.md --code --inline         # Include inline code

## Progressive Disclosure

  reveal README.md --head 10          # First 10 headings
  reveal README.md --tail 5           # Last 5 headings
  reveal README.md --range 15-20      # Headings 15-20

## JSON Output

  reveal README.md --format=json | jq '.structure'
  # Returns:
  {
    "headings": [{"line": 15, "level": 1, "name": "Title"}],
    "links": [...],      # Requires --links flag
    "code_blocks": [...]  # Requires --code flag
  }

## Notes

  • Links: Only markdown-formatted [text](url), not bare URLs
  • --links: Currently requires --format=json (text output pending)
  • Heading levels: 1-6 (H1-H6) included in JSON metadata
```

### Priority

**MEDIUM** - Discoverability issue, but workaround exists (--help, help://tricks)

---

## Issue #3: --outline Lacks Hierarchy Visualization

### Problem

`--outline` shows flat list of headings instead of hierarchical tree structure, despite JSON including heading levels.

### Evidence

```bash
# Current --outline output (flat):
$ reveal README.md --outline
Executive Summary
Key Accomplishments
1. Production Deployment
2. Validation
Technical Details

# JSON has levels:
$ reveal README.md --format=json | jq '.structure.headings[0:3]'
[
  {"line": 15, "level": 1, "name": "Executive Summary"},
  {"line": 24, "level": 2, "name": "Key Accomplishments"},
  {"line": 53, "level": 3, "name": "1. Production Deployment"}
]
```

### Expected Behavior

```
Executive Summary
  Key Accomplishments
    1. Production Deployment ✅
    2. Validation ✅
  Technical Details
    Container Architecture
    Application Stack
```

### Use Case

Understanding document structure at a glance, especially for long READMEs with deep nesting.

### Workaround

```bash
# Use jq to create hierarchy
reveal README.md --format=json | jq -r '
  .structure.headings[] |
  (("  " * (.level - 1)) + .name)
'
```

### Priority

**MEDIUM** - Nice-to-have for UX, workaround available

---

## Issue #4: Bare URLs Not Extracted

### Problem

Only markdown-formatted links `[text](url)` are extracted, not bare URLs like `https://example.com`.

### Evidence

```bash
$ cat README.md
Line 26: Check out https://example.com for details
Line 30: Visit [our site](https://example.com)

$ reveal README.md --links --format=json | jq '.structure.links | length'
1  # Only extracts line 30
```

### Impact

Many TIA session READMEs use bare URLs (especially generated docs):
- 3,377 total README files analyzed
- ~40% contain bare URLs in plain text
- Aggregate link analysis workflows incomplete

### Design Question

Is this intentional (markdown-only) or a limitation?

**Arguments for bare URL support:**
- More complete link extraction
- Useful for validation/checking
- Common in auto-generated docs

**Arguments against:**
- Noise (version numbers, example URLs)
- Not "semantic" markdown
- Performance impact on large files

### Priority

**LOW** - May be design decision, needs product discussion

---

## Issue #5: Help System Architecture Gap

### Problem

`help://adapters` only lists URI adapters (5 total), doesn't mention file analyzers (25 total including markdown).

### Impact

Users don't know reveal supports markdown unless they:
1. Run `--list-supported` (hidden command)
2. Try `reveal README.md` and it works (discovery by accident)
3. Read full `--help` output (overwhelming)

### Proposed Solution

Add `help://file-types` or expand `help://adapters`:

```bash
$ reveal help://adapters

# URI Adapters (5 total)
ast://    - Query code as AST database
env://    - Environment variables
json://   - JSON navigation
python:// - Python runtime inspection
help://   - Help system

# File Analyzers (25 total)
Python (.py), JavaScript (.js), TypeScript (.ts), Rust (.rs),
Go (.go), Markdown (.md), JSON (.json), YAML (.yaml), ...

Full list: reveal --list-supported
File-specific help: reveal help://markdown, reveal help://python
```

### Priority

**LOW** - Discoverability enhancement

---

## Testing Methodology

### Test Environment

- **Session**: visible-pulsar-1211 (2025-12-11)
- **Version**: reveal v0.21.0
- **Dataset**: 3,377 README files from TIA sessions
- **Sample**: 33 December 2025 session READMEs

### Test Cases

```bash
# 1. Basic structure (PASS)
reveal README.md

# 2. Section extraction (PASS)
reveal README.md "Executive Summary"

# 3. Progressive disclosure (PASS)
reveal README.md --head 5
reveal README.md --tail 3
reveal README.md --range 10-15

# 4. Code extraction (PASS)
reveal README.md --code
reveal README.md --code --language python

# 5. Link extraction - TEXT FORMAT (FAIL)
reveal README.md --links
# Expected: Links
# Actual: Headings only

# 6. Link extraction - JSON FORMAT (PASS)
reveal README.md --links --format=json

# 7. Outline hierarchy (PARTIAL)
reveal README.md --outline
# Works: Shows all headings
# Missing: No indentation for levels

# 8. Help discovery (FAIL)
reveal help://markdown
# Error: Topic not found

# 9. Bare URL extraction (EXPECTED LIMITATION)
# Only markdown-formatted links extracted
```

### Files Tested

- `/home/scottsen/src/tia/sessions/valley-twilight-1211/README_2025-12-11_14-06.md`
- `/home/scottsen/src/tia/sessions/bronze-flash-1119/README_2025-11-19_00-52.md`
- 31 additional December 2025 session READMEs

---

## Aggregate Analysis Use Cases

### Current Workflow (Working)

```bash
# Analyze README structure across sessions
find sessions/ -name "README*.md" -path "*-1211/*" | reveal --stdin

# Extract all executive summaries
find sessions/ -name "README*.md" | while read f; do
  reveal "$f" "Executive Summary"
done

# Find most common sections
find sessions/ -name "README*.md" | reveal --stdin --format=json | \
  jq -r '.structure.headings[] | .name' | sort | uniq -c | sort -rn
```

### Broken Workflow (Due to --links Issue)

```bash
# ❌ Extract all external links from December sessions
find sessions/ -name "README*.md" -path "*-1211/*" | \
  reveal --stdin --links --link-type=external
# Doesn't work - shows headings instead

# ✓ Workaround (verbose)
find sessions/ -name "README*.md" -path "*-1211/*" | \
  xargs -I{} reveal {} --links --format=json | \
  jq -r '.structure.links[]? | select(.type=="external") | .url'
```

---

## Recommendations

### Immediate (v0.22.0)

1. **Fix --links text output** or update documentation to specify JSON-only
2. **Add help://markdown topic** with basic examples
3. **Document bare URL limitation** in help text

### Short-term (v0.23.0)

4. **Add hierarchy to --outline** (indentation based on heading level)
5. **Improve help://adapters** to mention file analyzers

### Long-term (Post v1.0)

6. **Consider markdown:// URI adapter** for advanced queries:
   - `markdown://docs/?level=2` (all H2 headings)
   - `markdown://README.md?section=Installation`
   - `markdown://docs/?has-code-blocks`

7. **Add --bare-urls flag** (optional) for complete link extraction

---

## Related Documents

- Internal docs: `internal-docs/planning/ADVANCED_URI_SCHEMES.md`
- Help system: `reveal help://tricks` (Markdown Surgery section)
- Test data: `/home/scottsen/src/tia/sessions/*-12*/README*.md`

---

## Next Steps

1. **Create GitHub issues** for items #1-2 (high/medium priority)
2. **Update documentation** as interim fix for --links
3. **Product discussion** on bare URL extraction (design decision)
4. **Community feedback** on markdown:// URI adapter interest

---

## Appendix: Statistics

**TIA Session README Corpus:**
- Total READMEs: 3,377
- December 2025: 539 (538 sessions, 1 session with 2 versions)
- Average words per README: 1,750
- Total documentation: 5.8M words

**Common Sections (from analyze-readmes):**
1. Executive Summary: 1,172 READMEs (35.3%)
2. Next Steps: 863 READMEs (26.0%)
3. Technical Decisions: 705 READMEs (21.2%)
4. Key Accomplishments: varies
5. Files Modified: varies

**Link Distribution (sampled):**
- Markdown-formatted: ~15% of READMEs
- Bare URLs: ~40% of READMEs
- Internal links: ~5% of READMEs

---

**Research Complete**: 2025-12-11
**Session**: visible-pulsar-1211
**Lead**: TIA (Chief Semantic Agent)
