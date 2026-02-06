# Adapter Consistency Guide

**Audience**: Users and adapter authors
**Last Updated**: 2026-02-06
**See Also**: [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)

---

## Overview

Reveal has 16 URI adapters that follow a **3-tier UX model** for consistency:

1. **Resource Identity** (URI) - What to inspect
2. **Operations** (Flags) - What to do with it
3. **Filters** (Query params or flags) - What to show

This guide explains the patterns and how to use them effectively.

---

## Tier 1: Resource Identity (URI)

URIs identify **what resource** you're inspecting.

### Patterns

**Host-based resources**:
```bash
ssl://example.com:443           # SSL certificate on specific port
domain://example.com            # Domain information
mysql://localhost:3306/db       # MySQL database
```

**Path-based resources**:
```bash
ast://./src                     # Code analysis of directory
git://./repo                    # Git repository
stats://./src                   # Code metrics
```

**Element-based resources**:
```bash
env://PATH                      # Specific environment variable
python://packages               # Python packages info
help://ast                      # Help topic
```

**Hybrid (path + element)**:
```bash
domain://example.com/dns        # DNS records for domain
ssl://example.com/san           # Subject Alternative Names
json://config.json/database     # Specific JSON key
```

---

## Tier 2: Operations (CLI Flags)

Operations are **what you do** with the resource.

### Universal Operations

These work across all adapters (where applicable):

```bash
--check              # Health/validation check
--advanced           # Advanced mode (requires --check)
--format json        # Output format (json, text, compact, grep)
--select=fields      # Select specific fields
--only-failures      # Show only failures (requires --check)
```

### Examples

**SSL Certificate Health Check**:
```bash
reveal ssl://example.com --check
reveal ssl://example.com --check --advanced
reveal ssl://example.com --check --only-failures
```

**Domain Validation**:
```bash
reveal domain://example.com --check
reveal domain://example.com --check --advanced
```

**MySQL Database Health**:
```bash
reveal mysql://localhost/mydb --check
```

**Git Repository Health**:
```bash
reveal git://. --check
```

---

## Tier 3: Filters

Filters determine **what to show** from the results.

### Query Parameters (URI-based filtering)

Query params change **which resource variant** you see:

```bash
# Code complexity filtering
ast://src?complexity>10&lines>50

# JSON structure queries
json://config.json?keys&flatten

# Markdown frontmatter filtering
markdown://docs/?status=active&tags=python

# Stats filtering
stats://src?lines=50..200&hotspots=true
```

### Display Flags (Output filtering)

Display flags filter **the view** of the same resource:

```bash
--only-failures      # Hide successful checks
--limit=10           # Show first 10 items
--offset=20          # Skip first 20 items
--select=fields      # Show specific fields only
```

---

## Query Operator Reference

### Comparison Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `>` | Greater than | `lines>50` |
| `<` | Less than | `lines<200` |
| `>=` | Greater or equal | `complexity>=10` |
| `<=` | Less or equal | `complexity<=5` |
| `==` | Equals | `type==function` |
| `!=` | Not equals | `decorator!=property` |
| `~=` | Regex match | `name~=^test_` |
| `..` | Range | `lines=50..200` |

### Wildcards

| Pattern | Meaning | Example |
|---------|---------|---------|
| `*` | Glob wildcard (any chars) | `name=test_*` |
| `?` | Single character | `name=test_?` |

### Boolean Logic

| Operator | Meaning | Example |
|----------|---------|---------|
| `&` | AND (implicit) | `lines>50&complexity>10` |
| `\|` | OR (explicit) | `type=function\|method` |
| `()` | Grouping | `(lines>50\|complexity>10)&decorator=cached` |
| `!` | NOT prefix | `!deprecated&status=active` |

---

## Batch Processing

Process multiple resources with stdin:

```bash
# SSL batch check
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --stdin --check

# Code analysis batch
find . -name "*.py" | sed 's|^|ast://|' | reveal --stdin --format=json

# Mixed adapters
cat uris.txt | reveal --stdin --check
# uris.txt contains:
#   ssl://example.com
#   domain://example.com
#   mysql://localhost/db
```

**Coming Soon**: `--batch` flag for explicit batch mode with aggregation.

---

## Field Selection (Token Efficiency)

Select specific fields to reduce output size:

```bash
# SSL - only show domain and expiry
reveal ssl://example.com --select=domain,expiry,days_until_expiry

# Stats - only show path and quality score
reveal stats://src --select=path,quality_score,hotspot_score

# Git - only show commit info
reveal git://repo/file.py --select=hash,author,date,message
```

**Benefit**: 5-10x token reduction for AI agents and scripting.

---

## Adapter Comparison

### Query-Heavy Adapters
**ast://, json://, markdown://, stats://** - Rich filtering via query params

```bash
ast://src?lines>50&complexity>10&decorator=property
json://config.json?schema&flatten&keys
markdown://docs/?status=active&!deprecated
stats://src?lines=50..200&hotspots=true
```

### Progressive Disclosure Adapters
**ssl://, domain://, mysql://, git://** - Overview → detail → validation

```bash
ssl://example.com              # Overview
ssl://example.com/san          # Element detail
ssl://example.com --check      # Validation
```

### Element-Based Adapters
**env://, python://, help://** - Navigate via element names

```bash
env://PATH                     # Specific variable
python://packages              # Python packages
help://ast                     # Help topic
```

---

## Best Practices

### 1. Start with Overview
```bash
# Get overview first
reveal ssl://example.com

# Then drill down
reveal ssl://example.com/san
```

### 2. Use --check for Validation
```bash
# Always check health when relevant
reveal ssl://example.com --check
reveal domain://example.com --check
reveal mysql://localhost/db --check
```

### 3. Use --format=json for Scripting
```bash
# JSON for composability
reveal ssl://example.com --format=json | jq '.expiry'
reveal stats://src --format=json | jq '.files[] | select(.quality_score < 7)'
```

### 4. Use --select for Efficiency
```bash
# Reduce tokens when you know what you need
reveal ssl://example.com --select=domain,expiry
reveal stats://src --select=path,quality_score
```

### 5. Batch Process with stdin
```bash
# Bulk operations
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --stdin --check
```

---

## Adapter-Specific Features

Some adapters have unique flags:

**ssl://**:
```bash
--expiring-within=30        # Show certs expiring within 30 days
--validate-nginx            # Cross-validate with nginx config
```

**mysql://**:
```bash
--select=connections,replication  # Specific health checks
```

**stats://**:
```bash
--hotspots                  # Identify quality hotspots
--code-only                 # Exclude data/config files
```

**git://**:
```bash
git://repo@branch           # Specific branch/ref
git://repo?type=history     # Query by type
```

---

## Future Enhancements

Planned improvements (see [ADAPTER_UX_CONSISTENCY_2026-02-06.md](../../internal-docs/planning/ADAPTER_UX_CONSISTENCY_2026-02-06.md)):

1. **Universal --batch flag** - Explicit batch mode with aggregation
2. **Standardized query operators** - Same syntax across all adapters
3. **Element discovery hints** - Show available elements in overview
4. **Field selection everywhere** - All adapters support --select

---

## Getting Help

```bash
# List all adapters
reveal --adapters

# Adapter-specific help
reveal help://ssl
reveal help://domain
reveal help://ast

# Query syntax help
reveal help://tricks
```

---

## Related Guides

- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Create custom adapters
- [REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md) - Reference implementation
- [RECIPES.md](RECIPES.md) - Task-based workflows
- [QUICK_START.md](QUICK_START.md) - Getting started

---

**For Maintainers**: See internal planning doc for implementation details:
`internal-docs/planning/ADAPTER_UX_CONSISTENCY_2026-02-06.md`
