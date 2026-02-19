---
title: Element Discovery Guide
category: guide
---
# Element Discovery Guide

**Phase 5: UX Consistency - Element Discovery**
**Version**: 1.0
**Date**: 2026-02-08

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [What Are Elements?](#what-are-elements)
3. [Element Discovery](#element-discovery)
4. [Element Access](#element-access)
5. [Adapter Examples](#adapter-examples)
6. [JSON Output](#json-output)
7. [Common Patterns](#common-patterns)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

**See available elements**:
```bash
reveal ssl://google.com
```

Output shows:
```
📍 Available elements:
  /san          Subject Alternative Names (138 domains)
  /chain        Certificate chain (1 certificates)
  /issuer       Certificate issuer details
  /subject      Certificate subject details
  /dates        Validity dates (expires in 56 days)
  /full         Full certificate details

💡 Try: reveal ssl://google.com/san
```

**Access specific element**:
```bash
reveal ssl://google.com/san
```

**Get elements programmatically** (JSON):
```bash
reveal ssl://google.com --format=json | jq '.available_elements'
```

---

## What Are Elements?

**Elements** are sub-resources within a Reveal adapter that provide focused, detailed views of specific aspects of the main resource.

### Progressive Disclosure Pattern

Reveal uses **progressive disclosure** - start with overview, drill down to details:

1. **Overview**: `reveal ssl://google.com` - High-level status
2. **Element**: `reveal ssl://google.com/san` - Detailed SAN list
3. **Element**: `reveal ssl://google.com/chain` - Certificate chain analysis

### Why Elements?

**Without elements** (everything in overview):
- 🔴 Overwhelming output (500+ lines)
- 🔴 Slow for simple checks
- 🔴 Hard to find specific info

**With elements** (progressive disclosure):
- ✅ Fast overview (30 lines)
- ✅ Drill down when needed
- ✅ Focused, relevant output

---

## Element Discovery

### Text Output (Human-Readable)

Elements are automatically shown in overview output:

```bash
reveal ssl://google.com
```

Output includes:
```
📍 Available elements:
  /san          Subject Alternative Names (138 domains)
  /chain        Certificate chain (1 certificates)
  💡 Try: reveal ssl://google.com/san
```

### JSON Output (Programmatic)

Elements are included in `available_elements` field:

```bash
reveal ssl://google.com --format=json
```

```json
{
  "type": "ssl_certificate",
  "host": "google.com",
  "available_elements": [
    {
      "name": "san",
      "description": "Subject Alternative Names (138 domains)",
      "example": "reveal ssl://google.com/san"
    },
    {
      "name": "chain",
      "description": "Certificate chain (1 certificates)",
      "example": "reveal ssl://google.com/chain"
    }
  ]
}
```

### Dynamic Elements

Some adapters have **runtime-discovered** elements:

- **env://**: Any environment variable name
- **json://**: Any JSON key path
- **git://**: Any commit hash, file path, branch
- **sqlite://**: Any table name

These adapters return **empty** `available_elements` since elements can't be known statically.

---

## Element Access

### Basic Syntax

```
reveal <scheme>://<resource>/<element>
```

### Examples

**SSL certificate elements**:
```bash
reveal ssl://google.com/san       # Subject Alternative Names
reveal ssl://google.com/chain     # Certificate chain
reveal ssl://google.com/issuer    # Issuer details
reveal ssl://google.com/dates     # Validity dates
```

**Domain elements**:
```bash
reveal domain://google.com/dns       # DNS records
reveal domain://google.com/whois     # WHOIS data
reveal domain://google.com/ssl       # SSL status
```

**MySQL elements**:
```bash
reveal mysql://localhost/connections    # Active connections
reveal mysql://localhost/performance    # Query performance
reveal mysql://localhost/innodb         # InnoDB status
reveal mysql://localhost/slow-queries   # Slow query log
```

**Python runtime elements**:
```bash
reveal python://version     # Python version details
reveal python://venv        # Virtual environment status
reveal python://packages    # Installed packages
reveal python://doctor      # Environment diagnostics
```

### Element with Filters

Combine elements with query operators:

```bash
# Get DNS records, filter by type
reveal domain://google.com/dns?type=A

# Get slow queries, limit to top 10
reveal mysql://localhost/slow-queries?limit=10

# Get packages starting with 'django'
reveal python://packages | grep django
```

---

## Adapter Examples

### SSL Adapter

**Elements**: san, chain, issuer, subject, dates, full

**Overview**:
```bash
reveal ssl://google.com
```

**Element access**:
```bash
reveal ssl://google.com/san         # All domain names
reveal ssl://google.com/chain       # Certificate chain details
reveal ssl://google.com/issuer      # Issuer information
```

**JSON with elements**:
```bash
reveal ssl://google.com --format=json | jq '.available_elements[].name'
# Output: san, chain, issuer, subject, dates, full
```

---

### Domain Adapter

**Elements**: dns, whois, ssl, registrar

**Overview**:
```bash
reveal domain://example.com
```

**Element access**:
```bash
reveal domain://example.com/dns        # All DNS records
reveal domain://example.com/whois      # WHOIS registration
reveal domain://example.com/ssl        # SSL certificate status
reveal domain://example.com/registrar  # Registrar info
```

**Use case**: Check DNS propagation
```bash
# Quick overview
reveal domain://example.com

# Detailed DNS analysis
reveal domain://example.com/dns
```

---

### MySQL Adapter

**Elements**: connections, performance, innodb, replication, storage, errors, variables, health, databases, indexes, slow-queries

**Overview**:
```bash
reveal mysql://localhost
```

**Element access**:
```bash
reveal mysql://localhost/connections    # Processlist
reveal mysql://localhost/performance    # QPS, slow queries
reveal mysql://localhost/innodb         # Buffer pool, locks
reveal mysql://localhost/replication    # Master/slave status
reveal mysql://localhost/storage        # Database sizes
```

**Use case**: Debug slow queries
```bash
# Check if slow queries exist (overview)
reveal mysql://localhost

# Analyze slow queries (element)
reveal mysql://localhost/slow-queries
```

---

### Python Adapter

**Elements**: version, env, venv, packages, imports, syspath, doctor

**Overview**:
```bash
reveal python://
```

**Element access**:
```bash
reveal python://version     # Python version, build details
reveal python://venv        # Virtual environment status
reveal python://packages    # All installed packages
reveal python://doctor      # Environment health check
```

**Use case**: Debug import issues
```bash
# Check environment overview
reveal python://

# Check sys.path conflicts
reveal python://syspath

# Run diagnostics
reveal python://doctor
```

---

### Dynamic Adapters

**Env Adapter** - Element = any variable name:
```bash
reveal env://              # Overview (all variables)
reveal env://PATH          # Specific variable
reveal env://HOME          # Specific variable
```

**Git Adapter** - Element = commit/file/branch:
```bash
reveal git://repo/         # Overview (recent commits)
reveal git://repo/abc123   # Specific commit
reveal git://repo/main.py  # Specific file
```

**SQLite Adapter** - Element = table name:
```bash
reveal sqlite://db.sqlite3        # Overview (all tables)
reveal sqlite://db.sqlite3/users  # Specific table
```

---

## JSON Output

### Structure

When adapter supports elements, JSON includes `available_elements`:

```json
{
  "type": "ssl_certificate",
  "host": "google.com",
  "available_elements": [
    {
      "name": "san",
      "description": "Subject Alternative Names (138 domains)",
      "example": "reveal ssl://google.com/san"
    }
  ]
}
```

### Accessing Elements

**Check if elements available**:
```bash
reveal ssl://google.com --format=json | jq 'has("available_elements")'
```

**List element names**:
```bash
reveal ssl://google.com --format=json | jq '.available_elements[].name'
```

**Get element descriptions**:
```bash
reveal ssl://google.com --format=json | \
  jq '.available_elements[] | "\(.name): \(.description)"'
```

### AI Agent Usage

```python
import subprocess
import json

# Get resource overview
result = subprocess.run(
    ['reveal', 'ssl://google.com', '--format=json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

# Discover available elements
if 'available_elements' in data:
    for elem in data['available_elements']:
        print(f"Element: {elem['name']}")
        print(f"  Description: {elem['description']}")
        print(f"  Example: {elem['example']}")

        # Optionally fetch element details
        elem_result = subprocess.run(
            ['reveal', f"ssl://google.com/{elem['name']}", '--format=json'],
            capture_output=True, text=True
        )
        elem_data = json.loads(elem_result.stdout)
        # Process element data...
```

---

## Common Patterns

### Pattern 1: Progressive Exploration

Start broad, narrow down:

```bash
# 1. Overview - see what's available
reveal ssl://google.com
# Shows: 138 SANs, certificate expires in 56 days

# 2. Drill down - investigate specific aspect
reveal ssl://google.com/san
# Shows: All 138 domain names

# 3. Further analysis - check chain
reveal ssl://google.com/chain
# Shows: Certificate chain validation
```

### Pattern 2: Element Discovery Loop

Programmatically explore resources:

```bash
#!/bin/bash
# Get all SSL elements and fetch each

reveal ssl://google.com --format=json | \
  jq -r '.available_elements[].name' | \
  while read element; do
    echo "=== $element ==="
    reveal "ssl://google.com/$element"
    echo
  done
```

### Pattern 3: Conditional Element Access

Check if element exists before accessing:

```python
import subprocess
import json

def get_element_if_available(uri, element_name):
    # Get overview
    result = subprocess.run(
        ['reveal', uri, '--format=json'],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)

    # Check if element exists
    if 'available_elements' in data:
        available = [e['name'] for e in data['available_elements']]
        if element_name in available:
            # Element exists, fetch it
            elem_result = subprocess.run(
                ['reveal', f"{uri}/{element_name}", '--format=json'],
                capture_output=True, text=True
            )
            return json.loads(elem_result.stdout)

    return None
```

### Pattern 4: Multi-Element Analysis

Fetch multiple elements for comprehensive view:

```bash
# Analyze domain health - fetch all elements
for elem in dns whois ssl registrar; do
  echo "=== $elem ==="
  reveal "domain://example.com/$elem"
done
```

### Pattern 5: Element-Based Monitoring

Monitor specific aspects:

```bash
# Check SSL expiry across multiple hosts
for host in google.com github.com reddit.com; do
  echo -n "$host: "
  reveal "ssl://$host/dates" --format=json | \
    jq -r '.days_until_expiry'
done
```

---

## Best Practices

### 1. Start with Overview

Always check overview first:

**❌ Don't**:
```bash
# Directly access element without context
reveal ssl://google.com/san
```

**✅ Do**:
```bash
# Check overview first to see available elements
reveal ssl://google.com
# Then drill down
reveal ssl://google.com/san
```

### 2. Use Elements for Focused Output

**❌ Don't** (parse large overview):
```bash
# Get overview and grep for specific info
reveal ssl://google.com | grep "Alternative Names"
```

**✅ Do** (use dedicated element):
```bash
# Use element for focused output
reveal ssl://google.com/san
```

### 3. Check available_elements in Code

**❌ Don't** (assume element exists):
```python
# Blindly access element
data = get_reveal_output(f"{uri}/dates")
```

**✅ Do** (check if element exists):
```python
# Check available_elements first
overview = get_reveal_output(uri)
if 'dates' in [e['name'] for e in overview.get('available_elements', [])]:
    data = get_reveal_output(f"{uri}/dates")
```

### 4. Combine Elements with Query Operators

**❌ Don't** (get all data then filter):
```bash
# Get all packages, filter in shell
reveal python://packages | grep django
```

**✅ Do** (filter at adapter level when possible):
```bash
# Use query operators for efficiency
reveal python://packages?filter=django
```

### 5. Document Expected Elements

When building on Reveal, document which elements you use:

```python
# SSL Monitoring Script
# Required elements: dates, chain
# Adapters: ssl://

def check_ssl_health(host):
    # Check expiry via /dates element
    dates = get_element(f"ssl://{host}/dates")

    # Check chain validity via /chain element
    chain = get_element(f"ssl://{host}/chain")
```

---

## Troubleshooting

### Element Not Found

**Problem**: `reveal ssl://google.com/invalid` returns error

**Solution**: Check `available_elements` in overview:
```bash
reveal ssl://google.com --format=json | jq '.available_elements[].name'
```

### Empty available_elements

**Problem**: `available_elements` is empty or missing

**Reason**: Adapter has **dynamic elements** (env, git, json, sqlite)

**Solution**: Consult adapter documentation for element syntax:
```bash
reveal help://env      # See env:// element syntax
reveal help://git      # See git:// element syntax
```

### Element Syntax Confusion

**Problem**: Not sure if `/element` or `?element=` syntax

**Rule of thumb**:
- `/element` - Sub-resource access (SSL SAN, domain DNS)
- `?param=value` - Query filter (stats filter, ast type filter)

**Examples**:
```bash
# Sub-resource (element)
reveal ssl://google.com/san

# Query filter (parameter)
reveal stats://src?min_complexity=10
```

### No Element Hints in Output

**Problem**: Text output doesn't show "📍 Available elements"

**Reason**: Adapter doesn't override `get_available_elements()` OR is showing element view (not overview)

**Check**:
```bash
# JSON always includes available_elements if present
reveal ssl://google.com --format=json | jq 'has("available_elements")'
```

---

## Adapter Element Reference

| Adapter | Elements | Notes |
|---------|----------|-------|
| **ssl** | san, chain, issuer, subject, dates, full | Fixed list |
| **domain** | dns, whois, ssl, registrar | Fixed list |
| **mysql** | connections, performance, innodb, replication, storage, errors, variables, health, databases, indexes, slow-queries | Fixed list |
| **python** | version, env, venv, packages, imports, syspath, doctor | Fixed list |
| **env** | (any variable name) | Dynamic |
| **git** | (any commit/file/branch) | Dynamic |
| **json** | (any JSON key) | Dynamic |
| **sqlite** | (any table name) | Dynamic |
| **help** | (any topic/adapter) | Dynamic |
| **imports** | (any file name) | Dynamic |
| **reveal** | (any resource path) | Dynamic |
| **diff** | (any element name) | Dynamic |

---

## Related Documentation

- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) - Query operators (filter, sort, limit)
- [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) - Field selection (`--fields`)
- [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) - JSON output structure
- [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) - Creating adapters with elements

---

## Implementation Details

### For Adapter Authors

**Adding element support to your adapter**:

1. Override `get_available_elements()`:
```python
def get_available_elements(self) -> List[Dict[str, str]]:
    return [
        {
            'name': 'my-element',
            'description': 'Element description',
            'example': f'reveal myscheme://{self.resource}/my-element'
        }
    ]
```

2. Implement `get_element()`:
```python
def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
    if element_name == 'my-element':
        return self._get_my_element()
    return None
```

3. Element hints appear automatically in text output (no renderer changes needed for basic display)

See [ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md) for details.

---

**Phase 5 Complete**: Element discovery implemented across all adapters with element support.
**Session**: scarlet-shade-0208
**Date**: 2026-02-08
