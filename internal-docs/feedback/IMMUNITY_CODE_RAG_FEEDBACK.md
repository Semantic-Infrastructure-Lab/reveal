# Reveal Feedback: Immunity Code RAG Project

> Bugs, UX issues, and wishlist items discovered while using reveal to aid RAG pipeline development.

**Project:** immunity-code (RAG system for health knowledge base)
**Session:** clearing-ice-0120
**Date:** 2026-01-20
**Reveal Version:** 0.32.0

---

## Context

Used reveal to analyze a knowledge base (68 markdown docs, 1373 chunks) for RAG retrieval optimization. Key tasks:
- Document structure analysis
- Frontmatter metadata extraction
- Section heading pattern discovery
- Evaluation dataset (JSON) exploration

---

## Bugs

### B1: Shell Loops with Reveal Produce No Output

**Severity:** Medium
**Reproducible:** Yes

```bash
# This produces no output (expected: list of types)
for f in knowledge_base/domains/*/*.md; do
  reveal "$f" --frontmatter --format json 2>/dev/null | jq -r '.structure.frontmatter.data.type // "untyped"'
done | sort | uniq -c | sort -rn

# Workaround: use grep instead
grep -h "^type:" knowledge_base/domains/*/*.md | sort | uniq -c
```

**Expected:** Each file processed, output aggregated.
**Actual:** Silent failure, no output.
**Notes:** May be related to working directory or subshell behavior. Works fine for single files.

---

## UX Issues

### U1: No Batch Frontmatter Extraction

**Pain Point:** Analyzing frontmatter across many files requires shell loops.

**Current Workflow:**
```bash
for f in docs/*.md; do
  reveal "$f" --frontmatter --format json
done
```

**Desired:**
```bash
reveal docs/*.md --frontmatter --format json
# Or: reveal markdown://docs?frontmatter
```

**Use Case:** Aggregate metadata analysis across documentation sets (tag frequency, type distribution, missing fields).

### U2: json:// Flatten Output Hard to Parse with jq

**Pain Point:** `?flatten` output includes metadata that breaks jq piping.

```bash
reveal json://file.json?flatten | grep "type"
# Returns: "type": "json_flatten" (metadata, not data)
```

**Suggestion:** Flatten should output only the flattened key-value pairs, or have a `--data-only` flag.

### U3: No markdown:// URI Adapter for Querying

**Current:** `reveal doc.md --frontmatter` works for single files.
**Missing:** `markdown://` URI adapter for structured queries.

**Desired:**
```bash
reveal markdown://knowledge_base/domains?type=protocol
reveal markdown://docs?has_frontmatter=false
reveal markdown://docs?tag=gut-microbiome
```

**Use Case:** Query documentation by metadata attributes without shell loops.

---

## Wishlist

### W1: Frontmatter Aggregation Command

```bash
reveal docs/*.md --frontmatter --aggregate
# Output:
# type: mechanism (40), protocol (16), framework (10)
# domain: gut_microbiome (15), interventions (12), ...
# tags: [tag cloud or frequency list]
```

**Benefit:** One command to understand metadata distribution across a documentation set.

### W2: Section Heading Extraction

```bash
reveal doc.md --sections
# Output:
# ## Overview (line 23)
# ## Core Mechanisms (line 31)
# ## Action Items (line 215)
```

Currently possible via `reveal doc.md` (shows headings), but a dedicated `--sections` flag could:
- Show only H2+ (skip H1 title)
- Include line ranges for each section
- Support `--format json` for programmatic use

**Use Case:** RAG chunking analysis - understanding section boundaries before chunking.

### W3: Markdown Schema Validation for Frontmatter

```bash
reveal doc.md --validate-schema immunity-code
# Validates: required fields (type, domain, topics), valid enum values, etc.
```

**Benefit:** Ensure knowledge base consistency before ingestion.

### W4: Cross-File Link Graph

```bash
reveal docs/*.md --link-graph
# Output:
# akkermansia.md -> bifidobacteria.md, gut_reboot_protocol.md, ...
# gut_reboot_protocol.md -> akkermansia.md, order_of_operations.md, ...
```

**Use Case:** Understanding document relationships for RAG - which docs should be retrieved together.

### W5: stdin Support for Markdown Features

```bash
find docs -name "*.md" | reveal --stdin --frontmatter --format json
```

**Current:** `--stdin` works for code files but unclear if markdown features (--frontmatter, --links) work in batch mode.

---

## Positive Feedback

### What Worked Well

1. **`--outline` is excellent** - Hierarchical view of document structure is exactly what's needed for understanding chunking boundaries.

2. **`--frontmatter` extraction** - Clean YAML parsing, JSON output works perfectly for single files.

3. **`json://?schema`** - Instant understanding of unknown JSON structure. Used for evaluation dataset exploration.

4. **Progressive disclosure philosophy** - The "orient → navigate → focus" pattern maps perfectly to RAG development workflow.

5. **Help system** - `reveal help://markdown` provided comprehensive guidance.

---

## Summary

| Category | Count | Priority Items |
|----------|-------|----------------|
| Bugs | 1 | B1: Shell loop silent failure |
| UX Issues | 3 | U1: Batch frontmatter, U3: markdown:// adapter |
| Wishlist | 5 | W1: Frontmatter aggregation, W4: Link graph |

**Most Valuable Enhancement:** A `markdown://` URI adapter that supports querying by frontmatter fields would transform reveal into a documentation database query tool.
