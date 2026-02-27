---
title: Reveal Recipes
category: reference
---
# Reveal Recipes

**Task-based patterns for getting work done**

Find your task, get the commands. This guide organizes reveal by workflow, not by feature.

---

## Table of Contents

- [Code Review](#code-review)
- [Onboarding & Exploration](#onboarding-exploration)
- [Debugging & Troubleshooting](#debugging-troubleshooting)
- [Refactoring & Quality](#refactoring-quality)
- [Documentation Maintenance](#documentation-maintenance)
- [JSON Navigation](#json-navigation)
- [Database Operations](#database-operations)
  - [SSL certificate inspection](#ssl-certificate-inspection)
  - [On-disk certificate inspection](#on-disk-certificate-inspection)
  - [SSL expiry monitoring](#ssl-expiry-monitoring)
  - [Nginx SSL audit](#nginx-ssl-audit)
  - [Nginx ACL, routing, and ACME audit](#nginx-acl-routing-and-acme-audit)
  - [cPanel user environment](#cpanel-user-environment)
  - [Batch SSL checking with @file](#batch-ssl-checking-with-file)
- [Pipeline Integration](#pipeline-integration)
- [AI Agent Patterns](#ai-agent-patterns)
- [Multi-Language Support](#multi-language-support)
- [Quick Reference](#quick-reference)

---

## Code Review

### See what changed structurally

```bash
# Compare branches
reveal diff://git://main/.:git://feature/.

# Pre-commit check (what did I actually change?)
reveal diff://git://HEAD/src/:src/

# Compare specific files
reveal diff://app.py:backup/app.py

# See commit impact
reveal diff://git://HEAD~1/src/:git://HEAD/src/
```

**What you get:** Functions/classes added, removed, modified. Complexity changes. Import changes.

### Check quality before merge

```bash
# Run all checks
reveal src/ --check

# Security + bugs only (fast)
reveal src/ --check --select B,S

# Specific file
reveal src/auth.py --check --select B,S
```

### Review specific changes

```bash
# See what's in a file
reveal src/app.py

# Extract specific function
reveal src/app.py handle_request

# Check complexity of changed functions
reveal 'ast://src/?complexity>10'
```

### PR Review Workflow

```bash
# 1. See what changed
git diff --name-only origin/main | reveal --stdin

# 2. Check quality issues
git diff --name-only origin/main | grep '\.py$' | reveal --stdin --check

# 3. Find new complex functions
git diff --name-only origin/main | grep '\.py$' | \
  xargs -I{} reveal 'ast://{}?complexity>10'
```

---

## Onboarding & Exploration

### Map a new codebase

```bash
# 1. See high-level structure
reveal .

# 2. Explore main directories
reveal src/
reveal tests/

# 3. Find entry points
reveal src/main.py
reveal src/__init__.py

# 4. Drill into key functions
reveal src/main.py main
reveal src/app.py create_app
```

### Find patterns

```bash
# Find all authentication-related code
reveal 'ast://./src?name=*auth*'

# Find complex functions (likely important or buggy)
reveal 'ast://./src?complexity>10'

# Find long functions (refactor candidates)
reveal 'ast://./src?lines>50'

# Combine filters (complex AND long)
reveal 'ast://./src?complexity>10&lines>50'
```

### Understand architecture

```bash
# See all imports
reveal imports://src/

# Find circular dependencies
reveal 'imports://src?circular'

# Check layer violations
reveal 'imports://src?violations'

# Get statistics
reveal stats://./src
```

### Cross-codebase analysis

```bash
# Find all get_* methods across entire project
reveal 'ast://.?name=get_*' --format=json | \
  jq -r '.results[] | "\(.file):\(.line) \(.name)"'

# Count functions per file
reveal 'ast://./src?type=function' --format=json | \
  jq -r '.results[].file' | sort | uniq -c | sort -rn

# Find largest classes (potential god objects)
reveal 'ast://./src?type=class' --format=json | \
  jq -r '[.results[] | {name, file, lines: .line_count}] |
         sort_by(.lines) | reverse | .[0:10][] |
         "\(.file) - \(.name) (\(.lines) lines)"'
```

---

## Debugging & Troubleshooting

### Python environment issues

```bash
# Full health check
reveal python://doctor

# Check specific module (import shadowing?)
reveal python://module/requests

# Analyze sys.path conflicts
reveal python://syspath

# Find stale bytecode
reveal python://debug/bytecode

# See virtual environment status
reveal python://venv

# Check installed packages
reveal python://packages
```

### Detect import shadowing

```bash
# Is your local module hiding a pip package?
reveal python://module/requests

# Output shows:
# - import_location: Where Python actually imports from
# - pip_package: Where pip thinks it is
# - conflicts: [] or [{ type: "cwd_shadowing", ... }]
# - recommendations: Exact fix if there's a problem
```

### Find the code behind the error

```bash
# Locate error handling
reveal 'ast://src?name=*error*'
reveal 'ast://src?name=*exception*'

# Find specific handler
reveal src/handlers.py error_handler

# Check environment configuration
reveal env://
reveal env://DATABASE_URL
```

### Self-referential diagnosis

```bash
# Use reveal to extract reveal's own implementation
reveal reveal://rules/links/L001.py _extract_anchors_from_markdown

# Extract a class definition
reveal reveal://analyzers/markdown.py MarkdownAnalyzer

# Learn adapter patterns by extracting adapter code
reveal reveal://adapters/reveal.py get_element
```

---

## Refactoring & Quality

### Find technical debt

```bash
# Quality hotspots (worst files first)
reveal stats://./src --hotspots

# Complex functions across codebase
reveal 'ast://./src?complexity>10'

# Long functions
reveal 'ast://./src?lines>100'

# Code golf (complex but short - suspicious)
reveal 'ast://./src?complexity>10&lines<50'
```

### Complexity analysis

```bash
# Find complex functions (industry standard: >10 needs refactoring)
reveal 'ast://./src?complexity>10'

# The danger zone - extremely complex functions
reveal 'ast://./src?complexity>20'

# Find functions that are BOTH complex AND long (prime refactoring targets)
reveal 'ast://./src?complexity>15&lines>100'

# Top 10 most complex functions in your codebase
reveal 'ast://./src?type=function' --format=json | \
  jq -r '[.results[] | {name, file, complexity, lines: .line_count}] |
         sort_by(.complexity) | reverse | .[0:10][] |
         "\(.file) - \(.name) (complexity: \(.complexity), lines: \(.lines))"'

# Find god functions (both metrics high)
reveal 'ast://./src?complexity>30|lines>150'

# Simple but long - candidate for splitting or inlining
reveal 'ast://./src?complexity<5&lines>50'
```

### Decorator intelligence

```bash
# Find all @property methods
reveal 'ast://.?decorator=property'

# Find all cached functions (wildcards work!)
reveal 'ast://.?decorator=*cache*'

# Find abstract interface methods
reveal 'ast://.?decorator=abstractmethod'

# Find complex properties (code smell - properties should be simple)
reveal 'ast://.?decorator=property&lines>10'

# Find all @dataclass classes
reveal 'ast://.?decorator=dataclass&type=class'

# Analyze decorator usage across your codebase
reveal src/ --decorator-stats
```

### Before/after refactoring

```bash
# Before: Capture current state
reveal src/module.py function_name
reveal src/module.py --check --select C
reveal src/module.py --outline

# After: Verify improvements
reveal diff://git://HEAD/src/module.py:src/module.py
reveal src/module.py --check
reveal 'imports://src?circular'
```

### Find duplication

```bash
# Check for duplicate code
reveal src/ --check --select D

# Specific duplication check
reveal src/module.py --check --select D001,D002
```

---

## Documentation Maintenance

### Validate markdown frontmatter

```bash
# Session READMEs
reveal sessions/*/README.md --validate-schema session

# Hugo blog posts
reveal content/posts/*.md --validate-schema hugo

# Jekyll/GitHub Pages
reveal _posts/*.md --validate-schema jekyll

# MkDocs
reveal docs/**/*.md --validate-schema mkdocs
```

### Find docs by metadata

```bash
# Find all docs on a topic
reveal 'markdown://docs/?topics=authentication'

# Find incomplete docs
reveal 'markdown://docs/?status=draft'

# Find docs with specific tag
reveal 'markdown://?tags=python'

# Find docs missing metadata
reveal 'markdown://?!topics'
```

### Validate links

```bash
# Check all link rules
reveal docs/ --check --select L

# Fast check (internal links + routing only)
reveal docs/ --check --select L001,L003

# Extract all links
reveal README.md --links

# Filter by type
reveal README.md --links --link-type=external
reveal README.md --links --link-type=internal

# Find broken links
reveal docs/*.md --links 2>/dev/null | grep BROKEN
```

### Extract content

```bash
# See frontmatter structure
reveal docs/page.md --frontmatter

# Get as JSON for scripting
reveal docs/page.md --frontmatter --format=json

# All code blocks
reveal README.md --code

# Only Python examples
reveal README.md --code --language=python
```

---

## JSON Navigation

The `json://` adapter turns reveal into a JSON explorer - no jq required for basic operations.

### Explore unknown JSON structure

```bash
# What's in this JSON file?
reveal json://config.json?schema

# Output:
# Schema:
# {
#   "database": {
#     "host": "str",
#     "port": "int",
#     "credentials": {
#       "username": "str",
#       "password": "str"
#     }
#   },
#   "features": "Array[str]"
# }
```

**Why this matters:** AI agents constantly work with `package.json`, `tsconfig.json`, API responses. Schema inference shows structure without reading the whole file.

### Navigate to specific keys

```bash
# Get nested value
reveal json://package.json/scripts
reveal json://config.json/database/host

# Array access
reveal json://data.json/users/0           # First user
reveal json://data.json/users[0:3]        # First 3 users (slice)
```

### Search inside JSON (gron-style)

```bash
# Flatten to grep-able format
reveal json://config.json?flatten

# Output:
# json = {}
# json.database = {}
# json.database.host = "localhost"
# json.database.port = 5432
# json.database.credentials = {}
# json.database.credentials.username = "admin"

# Now search!
reveal json://config.json?flatten | grep -i password
reveal json://large-config.json?flatten | grep 'api.*key'
```

### Real-world patterns

```bash
# Explore package.json
reveal json://package.json?schema           # See structure
reveal json://package.json/dependencies     # List deps
reveal json://package.json/scripts          # See npm scripts

# Explore tsconfig.json
reveal json://tsconfig.json/compilerOptions
reveal json://tsconfig.json?flatten | grep strict

# Debug API response (saved to file)
reveal json://api-response.json?schema      # Understand structure
reveal json://api-response.json/data/0      # First result
```

**Token savings:** For AI agents, `json://?schema` gives structure understanding in ~100 tokens vs ~5000 tokens for the full file.

---

## Database Operations

### SQLite inspection

```bash
# Database overview
reveal sqlite:///path/to/app.db

# Table structure
reveal sqlite:///path/to/app.db/users

# Get as JSON
reveal sqlite:///app.db --format=json
```

### MySQL inspection (requires [database] extra)

```bash
# Database health
reveal mysql://localhost

# Performance metrics
reveal mysql://localhost/performance

# Index analysis
reveal mysql://localhost/indexes

# Slow queries
reveal mysql://localhost/slow-queries

# InnoDB status
reveal mysql://localhost/innodb
```

### Schema drift detection

```bash
# Compare database schemas
reveal diff://mysql://localhost/users:mysql://staging/users

# Compare SQLite schemas
reveal diff://sqlite://./dev.db:sqlite://./prod.db
```

### SSL certificate inspection

```bash
# Certificate overview
reveal ssl://example.com

# Non-standard port
reveal ssl://example.com:8443

# View all domains covered by certificate (SANs)
reveal ssl://example.com/san

# Certificate chain details
reveal ssl://example.com/chain

# Health check (expiry, chain verification, hostname match)
reveal ssl://example.com --check

# JSON output for CI/CD
reveal ssl://example.com --check --format=json
```

### On-disk certificate inspection

```bash
# Inspect a PEM/DER cert file directly (no network connection needed)
reveal ssl://file:///var/cpanel/ssl/apache_tls/example.com/combined
reveal ssl://file:///etc/letsencrypt/live/example.com/fullchain.pem

# Same output as live cert: health, expiry, SANs, chain count
# Combined PEM files (leaf + chain) are split automatically
```

### SSL expiry monitoring

```bash
# Check if certificate expires within 30 days
reveal ssl://example.com --check
# Exit code 0 = healthy, 1 = warning (<30 days), 2 = critical (<7 days)

# Combine with nginx config analysis
reveal /etc/nginx/nginx.conf --check  # N004 detects ACME path issues, N006 detects timeout mismatches

# Batch output shows failure reason and expiry dates inline:
# example.com    EXPIRED  3 days ago  (Jan 25, 2026)
# api.example.com    DNS FAILURE (NXDOMAIN)
# staging.example.com    WARNING  expires in 12 days  (Mar 11, 2026)
# www.example.com    OK  182 days  (Aug 27, 2026)
```

### Nginx SSL audit

```bash
# See nginx config with SSL status indicators
reveal /etc/nginx/nginx.conf

# Extract all SSL-enabled domains as ssl:// URIs
reveal /etc/nginx/nginx.conf --extract domains

# Check SSL certificates for all nginx domains (composable pipeline)
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check

# Show only problems (failures and warnings)
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --only-failures

# Quick summary (counts only)
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --summary

# Find certs expiring within 30 days
reveal /etc/nginx/nginx.conf --extract domains | reveal --stdin --check --expiring-within=30
```

### Nginx ACL, routing, and ACME audit

```bash
# Check nobody-user ACL access on all docroots (required for nginx ACME renewal)
reveal /etc/nginx/conf.d/users/USERNAME.conf --check-acl

# Find all ACME challenge root paths + ACL status in one table
reveal /etc/nginx/conf.d/users/USERNAME.conf --extract acme-roots

# Detect location block routing surprises (prefix overlap, regex shadowing prefix)
reveal /etc/nginx/conf.d/users/USERNAME.conf --check-conflicts

# Filter output to a single domain (essential for 1,500-line cPanel user configs)
reveal /etc/nginx/conf.d/users/USERNAME.conf --domain example.com

# Full composed audit: ACME paths + ACL status + live SSL cert per domain
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme

# On large configs (500+ domains), show only failures
reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme --only-failures

# Disk cert vs live cert comparison (detect "AutoSSL renewed but nginx not reloaded")
reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs
# ⚠️ STALE (reload nginx) when serial numbers differ; exit 2 on stale or expired

# Scan nginx error log for ACME/SSL failure patterns (retroactive diagnosis)
reveal /etc/nginx/conf.d/users/USERNAME.conf --diagnose
# Groups by domain: permission_denied (exit 2), ssl_error (exit 2), not_found (info)
```

### cPanel user environment

```bash
# Overview: domain count, SSL summary, nginx config path
reveal cpanel://USERNAME

# All domains with docroots and type (addon/subdomain/main)
reveal cpanel://USERNAME/domains

# Disk cert health per domain
reveal cpanel://USERNAME/ssl

# Nobody ACL check on every domain docroot
reveal cpanel://USERNAME/acl-check

# JSON output for scripting
reveal cpanel://USERNAME/ssl --format=json
```

### Batch SSL checking with @file

```bash
# Create a domain list file (one per line, comments with #)
cat > domains.txt << 'EOF'
# Production domains
ssl://api.example.com
ssl://www.example.com
ssl://app.example.com

# Staging
ssl://staging.example.com
EOF

# Check all domains from file
reveal @domains.txt --check

# Show only failures
reveal @domains.txt --check --only-failures

# Filter to expiring soon
reveal @domains.txt --check --expiring-within=14
```

---

## Pipeline Integration

### Unix pipelines

```bash
# Process changed files
git diff --name-only | reveal --stdin --outline

# Find complex functions in changed files
git diff --name-only origin/main | grep "\.py$" | reveal --stdin --format=json

# CI/CD quality gate
git diff --name-only origin/main | reveal --stdin --check --format=grep
```

### JSON processing

```bash
# Extract function info
reveal src/app.py --format=json | jq '.functions'

# Find large functions
reveal src/ --format=json | jq '.functions[] | select(.line_count > 100)'

# Get complexity metrics
reveal stats://src/ --format=json | jq '.quality_score'
```

### Batch operations

```bash
# Check multiple files
find src/ -name "*.py" -print0 | xargs -0 -I {} reveal {} --check

# Process all markdown
fd -e md | reveal --stdin --validate-schema hugo

# Get structure of all files
fd -e py | reveal --stdin --format=json > structure.json
```

### URI batch processing

```bash
# Check multiple SSL certificates
echo -e "ssl://example.com\nssl://api.example.com\nssl://staging.example.com" | reveal --stdin

# Mix files and URIs in same batch
echo -e "config.yaml\nssl://prod.example.com\nenv://PATH" | reveal --stdin

# Scan all domains from nginx config
grep -h "server_name" /etc/nginx/sites-enabled/* | awk '{print $2}' | \
  sed 's/;$//' | sed 's/^/ssl:\/\//' | reveal --stdin --check

# Batch SSL health checks with JSON output
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --stdin --format=json | \
  jq 'select(.status.health != "healthy")'
```

### Clipboard integration

```bash
# Copy function to clipboard
reveal src/app.py handle_request --copy

# Copy structure as JSON
reveal src/app.py --format=json --copy
```

### Format transformations

```bash
# Structure as JSON
reveal app.py --format=json

# Query with jq
reveal app.py --format=json | jq '.structure.functions | length'
reveal app.py --format=json | jq '.structure.imports[].content'

# Typed JSON (with relationships)
reveal app.py --format=typed

# Grep-compatible output
reveal app.py --format=grep
# Output: file:line:content
# Perfect for: reveal ... | grep pattern | cut -d: -f1-2
```

---

## AI Agent Patterns

### Progressive disclosure pattern

```bash
# Level 1: Structure (~100 tokens)
reveal app.py

# Level 2: Hierarchy (~150 tokens)
reveal app.py --outline

# Level 3: Specific extraction (~50 tokens)
reveal app.py process_data

# Compare: cat app.py (~7,500 tokens for 300 lines)
# Savings: 50-150x
```

### Token efficiency

```bash
# Python environment
reveal python://              # Overview (~20 tokens)
reveal python://packages      # Package list (~200 tokens)
reveal python://packages/numpy  # Specific package (~50 tokens)

# AST queries
reveal ast://./src            # All structure (~500 tokens)
reveal 'ast://./src?complexity>10'  # Just complex ones (~100 tokens)
```

### Semantic slicing

```bash
# First 5 functions only
reveal large_module.py --head 5

# Last 3 functions (bugs cluster at the bottom!)
reveal large_module.py --tail 3

# Specific range
reveal conversation.jsonl --range 48-52
```

### Query before reading

```bash
# Find relevant code without reading everything
reveal 'ast://./src?name=*config*'

# Filter by complexity
reveal 'ast://./src?complexity>5'

# Get structured output for parsing
reveal 'ast://./src?name=*auth*' --format=json
```

---

## Multi-Language Support

### Built-in analyzers (full support)

```bash
# Python, JS, TS, Rust, Go, Dockerfile, YAML, JSON, TOML, Markdown
reveal app.py            # Python
reveal config.yaml       # YAML
reveal Dockerfile        # Dockerfile with quality checks
reveal package.json      # JSON structure
reveal main.go           # Go
reveal lib.rs            # Rust
```

### Tree-sitter fallback (37+ languages)

```bash
# C, C++, Java, Ruby, PHP, Scala, Haskell, OCaml, Lua...
reveal Main.java         # Works!
reveal app.rb            # Works!
reveal script.lua        # Works!

# Check what's supported
reveal --list-supported
```

### Nginx configuration

```bash
# See all server blocks
reveal nginx.conf

# Filter output to a single domain (essential for large cPanel user configs)
reveal /etc/nginx/conf.d/users/USERNAME.conf --domain example.com

# Extract specific server block by name
reveal nginx.conf server_myapp

# Find all upstreams
reveal nginx.conf --format=json | jq '.structure.upstreams'

# Check for common issues
reveal /etc/nginx/nginx.conf --check
# N001: Duplicate backends
# N002: SSL servers missing certificate directives
# N003: Proxy locations missing X-Real-IP, X-Forwarded-For
# N004: ACME challenge path inconsistency (cert renewal failures)
# N005: Timeout/buffer values outside safe ranges
# N006: send_timeout too short for client_max_body_size (HIGH — silent uploads)

# Large generated configs collapse repeated rules by default
reveal ea-nginx.conf --check          # N003 x2,685 shown as one summary line
reveal ea-nginx.conf --check --no-group  # expand all occurrences

# Check nobody-user ACL access (cPanel ACME requirement)
reveal /path/user.conf --check-acl

# Find ACME challenge root paths + ACL status
reveal /path/user.conf --extract acme-roots

# Detect location routing surprises (regex shadowing prefix, prefix overlap)
reveal /path/user.conf --check-conflicts

# Full audit: ACME paths + ACL + live SSL cert status per domain
reveal /path/user.conf --validate-nginx-acme
reveal /path/user.conf --validate-nginx-acme --only-failures  # filter to failures on large configs

# Disk cert vs live cert comparison
reveal /path/user.conf --cpanel-certs

# Scan nginx error log for ACME/SSL failures
reveal /path/user.conf --diagnose
```

### Jupyter notebooks

```bash
# See notebook structure
reveal analysis.ipynb

# All cells with outputs
reveal analysis.ipynb --format=json
```

---

## Quick Reference

### Discovery commands

```bash
reveal .                                 # Map directory structure
reveal src/                              # Explore subdirectory
reveal 'ast://./src?name=*pattern*'      # Find by name
reveal 'ast://./src?complexity>10'       # Find by complexity
reveal 'imports://src?circular'          # Find circular imports
reveal stats://./src --hotspots          # Find technical debt
```

### Inspection commands

```bash
reveal file.py                           # File structure
reveal file.py --outline                 # Hierarchical view
reveal file.py function_name             # Extract specific code
reveal file.py --format=json             # Structured output
```

### Validation commands

```bash
reveal file.py --check                   # All rules
reveal file.py --check --select B,S      # Specific categories
reveal --rules                           # List all rules
reveal --explain B001                    # Explain specific rule
```

### Comparison commands

```bash
reveal diff://file1.py:file2.py          # Compare files
reveal diff://git://HEAD/.:src/          # Pre-commit check
reveal diff://git://main/.:git://feat/.  # Branch comparison
```

### Configuration commands

```bash
reveal reveal://config                   # Show active config
reveal env://                            # Environment variables
reveal python://doctor                   # Python health check
```

### AST query operators

| Operator | Example | Description |
|----------|---------|-------------|
| `name=` | `name=test_*` | Wildcard matching |
| `complexity>` | `complexity>10` | Cyclomatic complexity |
| `lines>` | `lines>50` | Function line count |
| `type=` | `type=class` | Element type |
| `depth>` | `depth>4` | Nesting depth |
| `decorator=` | `decorator=property` | Decorator filter |
| `&` | `complexity>10&lines>50` | AND logic |

### Rule categories

| Category | Description |
|----------|-------------|
| **B** | Bugs and anti-patterns |
| **S** | Security vulnerabilities |
| **C** | Complexity metrics |
| **D** | Duplicate code detection |
| **E** | Errors and syntax issues |
| **F** | Frontmatter validation |
| **I** | Import analysis |
| **L** | Link validation |
| **M** | Maintainability issues |
| **N** | Nginx configuration |
| **V** | Validation rules |

### Performance tips

```bash
# Fast mode (skip line counting, ~6x faster)
reveal src/ --fast

# Per-directory limit (stops node_modules from dominating)
reveal project/ --dir-limit 20

# Global entry limit (hard cap on total output)
reveal huge_dir/ --max-entries 100

# Control tree depth
reveal . --depth 2
```

---

## Getting Help

```bash
# List all adapters
reveal help://

# Adapter-specific help
reveal help://ast
reveal help://python
reveal help://diff

# Agent documentation
reveal --agent-help
```

---

**See also:**
- [AGENT_HELP.md](AGENT_HELP.md) - AI agent reference
- [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) - Configuration options
- [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md) - Complete review workflows
