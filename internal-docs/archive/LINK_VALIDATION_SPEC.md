# Link Validation Specification for Reveal

**Date**: 2025-12-16
**Status**: Planning / Track 4 in PENDING_WORK.md
**Context**: Link validation workflow exposed gaps in Reveal's directory handling (savage-siege-1216)
**Target Release**: v0.24

This document specifies link validation features for Reveal, addressing documentation workflows and CI/CD integration.

---

## Current Limitations

### Problem 1: No Native Recursive Processing

**Current workaround**:
```bash
find docs/ -name "*.md" | reveal --stdin --links --link-type internal
```

**What we want**:
```bash
reveal docs/ --recursive --links --link-type internal
```

**Issue**: `reveal docs/` only shows tree structure, doesn't process files recursively.

---

### Problem 2: No Aggregated Link Validation Mode

**Current**: Must parse grep output manually
```bash
find docs/ -name "*.md" | reveal --stdin --links | grep "BROKEN" | wc -l
```

**What we want**:
```bash
reveal docs/ --validate-links
```

**Output**:
```
🔍 Link Validation Report
========================

Checked: 64 files
Total links: 1,245
  ✅ External: 634 (valid)
  ✅ Internal: 315 (valid)
  ❌ Broken: 296
  
Files with issues:
  ❌ docs/systems/reveal.md (12 broken)
  ❌ docs/meta/FAQ.md (22 broken)
  ...

Exit code: 1 (failures detected)
```

---

### Problem 3: No Context-Aware Link Validation

**Issue**: Reveal checks filesystem paths, but FastHTML uses web routing:

```markdown
[Link](/foundations/FOUNDERS_LETTER)
```

- **Filesystem**: `docs/foundations/FOUNDERS_LETTER` ❌ doesn't exist
- **Web route**: `/foundations/FOUNDERS_LETTER` ✅ works (served from FOUNDERS_LETTER.md)

**What we want**:
```bash
reveal docs/ --validate-links --mode fasthtml
```

Understands:
- `/foundations/LETTER` → checks for `docs/foundations/LETTER.md`
- Uppercase web routes work (FastHTML case-insensitive)
- Anchor links `#section` are valid

---

### Problem 4: No Link Fixing Mode

**Current**: Manual sed commands
```bash
find docs/ -name "*.md" -exec sed -i 's|../canonical/|/foundations/|g' {} \;
```

**What we want**:
```bash
# Dry run
reveal docs/ --fix-links --dry-run

# Show proposed fixes:
docs/systems/reveal.md:88
  - [SIL Principles](../canonical/SIL_PRINCIPLES.md)
  + [SIL Principles](/foundations/SIL_PRINCIPLES)
  
# Apply fixes  
reveal docs/ --fix-links --apply
```

---

## Proposed Enhancements

### 1. Recursive Processing Flag ⭐ HIGH PRIORITY

```bash
reveal docs/ --recursive --links
reveal docs/ -r --links  # short form
```

**Behavior**:
- Process all supported files in directory tree
- Respect `.gitignore` patterns
- Optional: `--ignore "*/test/*"` for custom exclusions
- Output aggregated results

---

### 2. Link Validation Mode ⭐ HIGH PRIORITY

```bash
reveal docs/ --validate-links [OPTIONS]

Options:
  --mode [static|fasthtml|jekyll|hugo]  # Framework-aware validation
  --exclude-anchors                      # Ignore #anchor links
  --external                             # Check external URLs (HTTP HEAD)
  --summary                              # Summary only (no details)
  --json                                 # JSON output for CI/CD
```

**Output Modes**:

**Text (default)**:
```
❌ docs/systems/reveal.md
  Line 88   [SIL Principles](/foundations/SIL_PRINCIPLES) [BROKEN]
  Line 177  [Agent Help](/research/AGENT_HELP_STANDARD) [BROKEN]

✅ docs/pages/index.md (all links valid)

Summary: 296 broken links in 42 files
```

**JSON (CI/CD)**:
```json
{
  "summary": {
    "files_checked": 64,
    "total_links": 1245,
    "broken": 296,
    "valid": 949
  },
  "broken_links": [
    {
      "file": "docs/systems/reveal.md",
      "line": 88,
      "link": "/foundations/SIL_PRINCIPLES",
      "reason": "file_not_found"
    }
  ],
  "exit_code": 1
}
```

**Exit codes**:
- 0: All links valid
- 1: Broken links found
- 2: Validation error

---

### 3. Link Fixing Mode ⭐ MEDIUM PRIORITY

```bash
reveal docs/ --fix-links [OPTIONS]

Options:
  --dry-run              # Show proposed fixes without applying
  --interactive          # Confirm each fix
  --pattern old=new      # Custom replacement pattern
  --apply                # Apply all fixes
```

**Example**:
```bash
# Fix common patterns
reveal docs/ --fix-links \
  --pattern "../canonical/=/foundations/" \
  --pattern ".md)=)" \
  --dry-run
```

---

### 4. Framework-Aware Validation ⭐ HIGH PRIORITY

**FastHTML Mode**:
```bash
reveal docs/ --validate-links --framework fasthtml --docs-root docs/
```

**Rules**:
- `/path/FILE` → checks `docs/path/FILE.md`
- Case-insensitive matching
- Anchor links treated as valid
- Respects FastHTML routing conventions

**Jekyll Mode**:
```bash
reveal docs/ --validate-links --framework jekyll
```

**Rules**:
- Understands `{% link ... %}` tags
- Checks `_includes`, `_layouts` directories
- Validates permalink mappings

---

### 5. Link Statistics & Reports 🔵 LOW PRIORITY

```bash
reveal docs/ --link-stats

Link Statistics
===============
Total files: 64
Total links: 1,245

By Type:
  External: 634 (50.9%)
    ├─ github.com: 425
    ├─ docs.python.org: 87
    └─ other: 122
  Internal: 611 (49.1%)
    ├─ valid: 315
    └─ broken: 296

By Domain (external):
  1. github.com/Semantic-Infrastructure-Lab  425 links
  2. docs.python.org                          87 links
  3. wikipedia.org                            45 links
  
Most linked files:
  1. /foundations/SIL_GLOSSARY (89 references)
  2. /systems/reveal (67 references)
  3. /architecture/UNIFIED_ARCHITECTURE_GUIDE (54 references)
```

---

### 6. Watch Mode 🔵 LOW PRIORITY

```bash
reveal docs/ --watch --validate-links
```

- Monitor file changes
- Re-validate on save
- Live feedback for documentation editing

---

### 7. Export Formats 🔵 LOW PRIORITY

```bash
reveal docs/ --validate-links --format [markdown|html|junit]

# Markdown report
reveal docs/ --validate-links --format markdown > LINK_REPORT.md

# JUnit XML (CI integration)
reveal docs/ --validate-links --format junit > link-validation.xml

# HTML report
reveal docs/ --validate-links --format html > report.html
```

---

## Implementation Priority

### Phase 1: Core Functionality ⭐
1. **Recursive processing** (`--recursive`)
2. **Link validation mode** (`--validate-links`)
3. **Framework-aware validation** (`--framework`)
4. **JSON output** for CI/CD integration

### Phase 2: Quality of Life 🟡
5. **Link fixing mode** (`--fix-links`)
6. **Better error messages** and suggestions
7. **Exclude patterns** (`--ignore`)

### Phase 3: Advanced Features 🔵
8. **Link statistics** (`--link-stats`)
9. **Watch mode** (`--watch`)
10. **Export formats** (HTML, JUnit)

---

## Real-World Use Cases

### Use Case 1: CI/CD Link Validation
```yaml
# .github/workflows/validate-docs.yml
- name: Validate documentation links
  run: |
    reveal docs/ --validate-links --framework fasthtml --json > results.json
    
- name: Comment on PR
  if: failure()
  uses: actions/github-script@v6
  with:
    script: |
      const results = require('./results.json')
      // Post broken links as PR comment
```

### Use Case 2: Documentation Refactoring
```bash
# Before: Manual find/sed
find docs/ -name "*.md" -exec sed -i 's|../old/|/new/|g' {} \;

# After: Reveal link fixer
reveal docs/ --fix-links --pattern "../old/=/new/" --apply
```

### Use Case 3: Link Quality Dashboard
```bash
# Generate daily report
reveal docs/ --link-stats --format html > dashboard.html

# Track link health over time
reveal docs/ --validate-links --json | jq '.summary' >> metrics.jsonl
```

---

## Alternative: Reveal Adapters

Instead of built-in features, create **adapters**:

```bash
# markdown:// adapter already exists
reveal help://markdown

# Proposed: links:// adapter
reveal links://docs/
reveal links://docs/?type=internal&broken=true
reveal links://docs/?framework=fasthtml

# Proposed: fix:// adapter  
reveal fix://docs/?pattern=../canonical/=/foundations/
```

**Benefits**:
- Keeps core reveal clean
- Extensible by community
- Follows reveal's URI philosophy

---

## Questions for SIL Team

1. **Recursive processing**: Built-in `--recursive` or rely on `find | --stdin`?
2. **Link validation**: Core feature or separate adapter?
3. **Framework awareness**: Generic or FastHTML-specific?
4. **Link fixing**: In reveal or separate tool?
5. **Priority**: Which features would have most impact?

---

## Next Steps

1. **Create GitHub issues** for high-priority enhancements
2. **Prototype** `links://` adapter for validation
3. **Gather feedback** from reveal users
4. **Implement** Phase 1 features

---

**Session**: savage-siege-1216  
**Related**: Link validation work exposed these gaps
