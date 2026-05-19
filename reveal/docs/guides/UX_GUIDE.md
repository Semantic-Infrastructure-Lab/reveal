---
title: "Reveal UX Guide: CLI Flags vs URI Query Parameters"
type: guide
category: best-practices
---

# Reveal UX Guide: CLI Flags vs URI Query Parameters

**Access**: `reveal help://ux`

Understanding when to use flags vs query params is the key mental model for reveal. Get it right and everything clicks.

---

## The 3-Tier Model

| Tier | Question | Mechanism | Example |
|------|----------|-----------|---------|
| **1. Resource Identity** | *What are we inspecting?* | URI | `ssl://host`, `ast://./src`, `file.py` |
| **2. Operations** | *What to do with it?* | Universal CLI flags | `--check`, `--format`, `--fields` |
| **3. Filters / Options** | *What to show?* | URI query params (for URIs); CLI flags (for files) | `?summary`, `--name` |

The key rule:
> **URI adapters** (`ssl://`, `cpanel://`, `ast://`, etc.) — adapter-specific options go in the URI query string.
> **File targets** (`file.py`, `nginx.conf`) — adapter-specific options stay as CLI flags.

---

## When to Use a File Path vs a URI

**Use a file path** when you want to inspect a local file:
```bash
reveal file.py                     # Structure of a Python file
reveal /etc/nginx/nginx.conf       # nginx file analysis
reveal docs/guide.md               # Markdown with --links, --outline
```

**Use a URI** when you're querying a system resource or need filtering:
```bash
reveal ssl://example.com           # Live cert check — not a local file
reveal 'ast://./src?complexity>10' # Code as a queryable database
reveal 'git://.?author=Alice'      # Git log filtered by author
reveal 'cpanel://USERNAME/ssl'     # cPanel filesystem introspection
```

**Rule of thumb**: If you'd need a URL or connection string in other tools, you need a URI in reveal.

---

## When to Use CLI Flags vs URI Query Parameters

### Use CLI flags for:

**Universal operations** — work everywhere:
```bash
reveal ssl://host --check          # Health check
reveal ast://src --format json     # JSON output
reveal file.py --fields name,lines # Select output fields
reveal file.py --head 10           # First 10 results
```

**File-target-specific options** — only meaningful on the right file type:
```bash
reveal file.py --name auth         # Search file structure
reveal file.py --type function     # Filter by element type
reveal nginx.conf --diagnose       # nginx-specific analysis
reveal doc.md --links              # markdown-specific
```

### Use URI query parameters for:

**URI adapter filtering** — options that belong with the resource:
```bash
reveal 'ast://src?complexity>10'             # Filter by complexity
reveal 'ssl://host?expiring-within=30'      # Cert expiry filter
reveal 'cpanel://USER/ssl?dns-verified'     # Exclude NXDOMAIN domains
reveal 'git://.?author=Alice&since=2024-01-01'  # Multi-condition git query
```

**Batch/pipeline mode** — when options must travel with each URI:
```bash
# Bad: global flag applies to ALL URIs — can't mix options per-URI
cat domains.txt | reveal --stdin --check --expiring-within 30

# Good: each URI carries its own options
echo -e "ssl://a.com?expiring-within=30\nssl://b.com" | reveal --stdin --check
```

---

## The Flag-to-Param Translation Table

For file targets, convenience flags translate to URI params when you switch to URI form. The names are not always identical — this is intentional:

| Concept | File path (CLI flag) | URI (query param) | Note |
|---------|---------------------|-------------------|------|
| Name search | `--name pattern` | `?name~=pattern` | Different names — `--name` is ergonomic; `name~=` is the formal filter (`--search` is a deprecated alias for `--name`) |
| Text search | `--grep pattern` | *(no URI equivalent)* | Text content search; results grouped by enclosing element |
| Type filter | `--type function` | `?type=function` | Same ✓ |
| Sort ascending | `--sort field` | `?sort=field` | Same ✓ |
| Sort descending | `--sort field --desc` | `?sort=-field` | CLI needs two flags; URI uses `-` prefix |
| Limit results | `--head N` / `--max-items N` | `?limit=N` | See below — they're not equivalent |
| SSL expiry filter | `--expiring-within N` | `?expiring-within=N` | Both work; URI form preferred in pipelines |
| SSL summary | `--summary` | `?summary` | Both work; URI form preferred in pipelines |
| cPanel dns filter | `--dns-verified` | `?dns-verified` | Both work |
| cPanel live check | `--check-live` | `?check-live` | Both work |

---

## `--name` vs `?name~=` — The Most Confusing Rename

When escalating from a file-path command to a URI command, `--name` becomes `?name~=`:

```bash
# Step 1: Start simple
reveal file.py --name authenticate

# Step 2: Add filters
reveal file.py --name authenticate --type function --sort=-complexity

# Step 3: Need complex conditions? Switch to URI — NOTE the rename
reveal 'ast://file.py?name~=authenticate&type=function&complexity>10&sort=-complexity'
#                       ^^^^^^^^^^^                               ← --name becomes name~=
```

**Why the rename?** `--name` is an ergonomic shorthand; `name~=` is a formal predicate: "name matches regex". They mean the same thing but belong to different layers. (`--search` was the old name for `--name` and remains a backwards-compat alias.)

**Scope:** both `--name` and `?name~=` match named code elements only — functions, classes, structs, imports. They do **not** search text content. Use `--grep` for that:

```bash
reveal file.py --name CONFIG                      # ← finds nothing (CONFIG is a variable, not a named element)
reveal 'ast://file.py?reveal_type=CONFIG'         # ← variables/constants
reveal file.py --grep CONFIG                      # ← every line containing the text "CONFIG"
reveal doc.md --grep 'BACK-308'                   # ← text in table cells, body, anywhere
```

**`--name` vs `--grep` at a glance:**

| | `--name` | `--grep` |
|---|---|---|
| Finds | Named elements by name | Any line by text content |
| Markdown | Headings whose title matches | Lines in any section (body, tables, code) |
| Output | Element list (line, complexity, signature) | Hits grouped by enclosing element |
| URI form | `?name~=pattern` | No URI equivalent |

---

## `--head`/`--tail` vs `?limit=`/`?offset=` — Intentionally Different

These look similar but are **not interchangeable**:

| Mechanism | What it does | When to use |
|-----------|-------------|-------------|
| `--head N` | Output-stream slicing — shows first N semantic units after the adapter runs | Quick "show me the top N" on any target |
| `--tail N` | Output-stream slicing — shows last N results | No URI equivalent |
| `--max-items N` | Budget cap — stops processing after N items | Protecting against runaway output |
| `?limit=N` | Query result control — constrains what the adapter *returns*, like SQL LIMIT | URI adapters with filtering (ast, json, markdown, git) |
| `?offset=M` | Skip first M query results before returning | Pagination in URI queries |

```bash
# --head: quick slice of any output
reveal file.py --head 5            # First 5 functions/sections

# ?limit=: filter before output (more precise)
reveal 'ast://src?complexity>10&limit=5'  # Top 5 complex functions (filtered first)
```

`--tail` has no URI equivalent — use `?sort=-field&limit=N` to approximate "top N by metric."

---

## `--sort` and `?sort=` Precedence

If you use both `--sort` and `?sort=` in the URI, the URI wins:

```bash
# URI ?sort= takes precedence — --sort is ignored
reveal 'ast://src?sort=name' --sort complexity
# → sorts by name (URI wins)

# --sort injects only when URI has no sort=
reveal 'ast://src?complexity>10' --sort=-lines
# → ?sort=-lines appended to URI
```

---

## Progressive Escalation Pattern

The recommended workflow — start simple, escalate to URI only when needed:

```bash
# Step 1: See file structure
reveal file.py

# Step 2: Filter with convenience flags (80% of queries)
reveal file.py --name auth --type function

# Step 3: Add sort
reveal file.py --name auth --type function --sort=-complexity

# Step 4: Complex multi-condition query → switch to URI
# (--search becomes ?name~=, rest maps cleanly)
reveal 'ast://file.py?name~=auth&type=function&complexity>10&lines>20&sort=-complexity'

# Step 5: Combine with cross-adapter patterns
reveal 'ast://file.py?name~=auth' | reveal --stdin --check
```

---

## Which Adapters Support Query Params?

| Adapter | Query params | Notes |
|---------|-------------|-------|
| `ast://` | ✅ Rich filtering | Reference implementation |
| `json://` | ✅ Rich filtering | Field filters, flatten, schema |
| `markdown://` | ✅ Frontmatter filtering | `?status=draft`, `?body-contains=X` |
| `stats://` | ✅ Metric filtering | `?hotspots`, `?min_complexity=10` |
| `git://` | ✅ Commit filtering | `?author=`, `?since=`, `?type=` |
| `calls://` | ✅ Call graph | `?target=fn`, `?top=10` |
| `claude://` | ✅ Session filtering | `?summary`, `?errors`, `?contains=` |
| `xlsx://` | ✅ Sheet/range | `?sheet=Sales`, `?range=A1:D10` |
| `ssl://` | ✅ Expiry/summary | `?expiring-within=30`, `?summary` |
| `cpanel://` | ✅ Domain/SSL filters | `?domain_type=addon`, `?dns-verified` |
| `letsencrypt://` | ✅ Cert audit | `?check-orphans`, `?check-duplicates` |
| `autossl://` | ✅ Run filtering | `?only-failures`, `?summary`, `?user=NAME` |
| `depends://` | Partial | `?top=10`, `?format=` |
| `imports://` | Partial | `?unused`, `?circular` |
| `nginx://`, `domain://`, `env://` | ❌ None | Use element paths; unrecognized `?params` stripped with warning |
| `mysql://`, `sqlite://`, `python://` | ❌ None | Use element paths |

---

## See Also

- `reveal help://tricks` — Task-based workflow recipes
- `reveal help://query-syntax` — Query operator reference (=, !=, >, ~=, ..)
- `reveal help://query-parameter-reference` — Per-adapter query param documentation
- [ADAPTER_CONSISTENCY.md](../development/ADAPTER_CONSISTENCY.md) — Architectural rationale
- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) — Full query operator reference
