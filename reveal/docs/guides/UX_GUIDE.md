---
title: "Reveal UX Guide: Paths, Nouns, Flags and Resource URIs"
type: guide
category: best-practices
help_topic: ux
help_description: "Paths, nouns, flags and resource URIs: when to use each, progressive escalation, old query keys and their flags"
help_category: best_practices
---

# Reveal UX Guide: Paths, Nouns, Flags and Resource URIs

**Access**: `reveal help://ux`

Options are flags on every noun: `reveal NOUN TARGET --option value`, and a resource URI takes the same flags. This guide
used to teach URI query strings (`?option=value`) for options; that spelling is retiring: it still answers until 1.0 with a
note naming its flag form, then exits 2, and the [old keys and their flags](#old-query-keys-and-their-flags) are listed
below.

---

## The 3-Tier Model

| Tier | Question | Mechanism | Example |
|------|----------|-----------|---------|
| **1. Target** | *What are we inspecting?* | A path, a noun and its target, or a resource URI | `file.py`, `reveal ast ./src`, `ssl://host` |
| **2. Operations** | *What to do with it?* | Universal CLI flags | `--format`, `--fields`, `--output` |
| **3. Filters / Options** | *What to show?* | The noun's flags | `--where 'complexity>10'`, `--name`, `--view history` |

The key rule:
> **Every option is a flag**, on a path (`file.py --name auth`), on a noun (`reveal ast src --where 'complexity>10'`) and
> after a resource URI (`reveal git://app.py@main --view history`), with the same answer and exit code on each.
> The hosting-ops adapters (`ssl://`, `cpanel://`, `letsencrypt://`, `autossl://`, ...) are outside this rule: they are
> moving to a separate package and keep their query options.

---

## When to Use a File Path, a Noun or a URI

**Use a file path** when you want to inspect a local file:
```bash
reveal file.py                     # Structure of a Python file
reveal /etc/nginx/nginx.conf       # nginx file analysis
reveal docs/guide.md               # Markdown with --links, --outline
```

**Use a noun** when you ask a question about code or data under a path:
```bash
reveal ast ./src --where 'complexity>10'   # Code as a queryable database
reveal git . --where author=Alice          # Git log filtered by author
```

**Use a URI** when the target is an address a plain path cannot name: a host, a ref, a session, a key:
```bash
reveal ssl://example.com           # Live cert check — not a local file
reveal 'cpanel://USERNAME/ssl'     # cPanel filesystem introspection
```

**Rule of thumb**: If you'd need a URL or connection string in other tools, you need a URI in reveal. A path with a
question about it is a noun.

---

## Which Flags Go Where

### Universal operations — work everywhere:
```bash
reveal ssl://host --check                          # Health check
reveal ast src --format json                       # JSON output
reveal ast src --format json --fields name,line    # Select output fields
reveal file.py --head 10                           # First 10 results
```

### File-target options — only meaningful on the right file type:
```bash
reveal file.py --name auth         # Search file structure
reveal file.py --type function     # Filter by element type
reveal nginx.conf --diagnose       # nginx-specific analysis
reveal doc.md --links              # markdown-specific
```

### Noun options — the noun's own flags, given after its target:
```bash
reveal ast src --where 'complexity>10'                # Filter by complexity
reveal git . --where author=Alice --since 2024-01-01  # Multi-condition git query
reveal 'ssl://host?expiring-within=30'                # Ops adapter: its own query option (implies --check)
reveal 'cpanel://USER/ssl?dns-verified'               # Ops adapter: exclude NXDOMAIN domains
```

### Batch/pipeline mode — each line is a whole request:
```bash
# A --stdin line answers as `reveal LINE` would, flags included
printf '%s\n' "ast src --where 'complexity>10'" "metrics src --view hotspots" | reveal --stdin

# Ops adapters keep their per-URI query options
echo -e "ssl://a.com?expiring-within=30\nssl://b.com" | reveal --stdin --check
```

---

## Old Query Keys and Their Flags

A query key names the same control as its flag, so the old spelling is a one-word change. The names are not always
identical — this is intentional:

| Concept | Flag | Old query key (retiring) | Note |
|---------|------|--------------------------|------|
| Name search (file) | `--name pattern` | — | On a file read; on `reveal ast` it is the filter `--where 'name~=pattern'` (`--search` is a deprecated alias for `--name`) |
| Name filter (noun) | `--where 'name~=pattern'` | `?name~=pattern` | A filter on the `name` field |
| Text search | `--grep pattern` | *(no query key)* | Text content search; results grouped by enclosing element |
| Type filter | `--type function` (file), `--kind function` (`reveal ast`) | `?type=function`, `?kind=function` | `type` is ast's legacy word for `kind` |
| Field filter | `--where 'FIELD OP VALUE'`, repeatable | `?FIELD OP VALUE`, `?where=...` | One `--where` per condition; all must match |
| Sort ascending | `--sort field` | `?sort=field` | Same name |
| Sort descending | `--sort=-field` (or `--sort field --desc` on a file read) | `?sort=-field` | `-` prefix |
| Limit results | `--limit N` (nouns), `--head N` (file reads) | `?limit=N` | See below — they're not equivalent |
| SSL expiry filter (ops) | `--expiring-within N` | `?expiring-within=N` | Ops: both spellings stay; either runs the check by itself |
| SSL summary (ops) | `--summary` | `?summary` | Ops; batch and nginx views only; a single `ssl://host` ignores it with a note |
| cPanel dns filter (ops) | `--dns-verified` | `?dns-verified` | Ops: both spellings stay |
| cPanel live check (ops) | `--check-live` | `?check-live` | Ops: both spellings stay |

Each noun's full list of keys and flags is in `reveal help://query-params`.

---

## `--name` vs `--where 'name~='` — The Most Confusing Rename

When escalating from a file-path command to the `ast` noun, `--name` becomes the filter `--where 'name~=PATTERN'`:

```bash
# Step 1: Start simple
reveal file.py --name authenticate

# Step 2: Add filters
reveal file.py --name authenticate --type function --sort=-complexity

# Step 3: Need complex conditions? Switch to the ast noun — NOTE the rename
reveal ast file.py --where 'name~=authenticate' --where 'complexity>10' --kind function --sort=-complexity
#                          ^^^^^^^^^^^^^^^^^^^^ ← --name becomes --where 'name~=...'
```

**Why the rename?** `--name` is an ergonomic shorthand; `name~=` is a formal predicate: "name matches regex". They mean the same thing but belong to different layers. (`--search` was the old name for `--name` and remains a backwards-compat alias.)

**Scope:** both `--name` and `--where 'name~=...'` match named code elements only — functions, classes, structs, imports. They do **not** search text content. Use `--grep` for that:

```bash
reveal file.py --name CONFIG                      # ← finds nothing (CONFIG is a variable, not a named element)
reveal ast file.py --reveal-type CONFIG           # ← variables/constants
reveal file.py --grep CONFIG                      # ← every line containing the text "CONFIG"
reveal doc.md --grep 'BACK-308'                   # ← text in table cells, body, anywhere
```

**`--name` vs `--grep` at a glance:**

| | `--name` | `--grep` |
|---|---|---|
| Finds | Named elements by name | Any line by text content |
| Markdown | Headings whose title matches | Lines in any section (body, tables, code) |
| Output | Element list (line, complexity, signature) | Hits grouped by enclosing element |
| Noun form | `reveal ast PATH --where 'name~=pattern'` | No noun equivalent |

---

## `--head`/`--tail` vs `--limit`/`--offset` — Intentionally Different

These look similar but are **not interchangeable**:

| Mechanism | What it does | When to use |
|-----------|-------------|-------------|
| `--head N` | Output-stream slicing on a path read — shows first N semantic units | Quick "show me the top N" of a file or directory |
| `--tail N` | Output-stream slicing on a path read — shows last N units | The end of a file's structure |
| `--max-items N` | Budget cap — stops processing after N items | Protecting against runaway output |
| `--limit N` | Result control on a noun — constrains what the noun *returns*, like SQL LIMIT (`0` = no cap) | Nouns with filtering (ast, json, markdown, git, metrics, ...) |
| `--offset M` | Skip first M results before returning | Pagination on a noun |

```bash
# --head: quick slice of a file's structure
reveal file.py --head 5            # First 5 functions/sections

# --limit: filter before output (more precise)
reveal ast src --where 'complexity>10' --limit 5  # Top 5 complex functions (filtered first)
```

On a noun, `--head` and `--tail` still answer until 1.0 with a note naming the replacement (`--limit N`; for `--tail`, a
descending `--sort` with `--limit N`); use `--sort=-FIELD --limit N` for "top N by metric."

---

## A Setting Given Twice

A setting takes one value. The same value twice is one request; two different values are an invalid request (exit 2)
naming both, on every noun and for every setting (`--limit`, `--sort`, `--format`, ...):

```bash
# Different values: exit 2, nothing is guessed
reveal ast src --sort name --sort complexity
# Error (exit 2): argument --sort: given twice with different values: --sort name and --sort complexity; give it once

# One value is one request
reveal ast src --where 'complexity>10' --sort=-lines
```

The retiring query key and its flag are one setting too: `reveal 'ast://src?sort=name' --sort complexity` exits 2 the same
way. Filters such as `--where` and `--match` are not settings: they repeat and combine.

---

## Progressive Escalation Pattern

The recommended workflow — start simple, escalate to a noun only when needed:

```bash
# Step 1: See file structure
reveal file.py

# Step 2: Filter with file flags (80% of queries)
reveal file.py --name auth --type function

# Step 3: Add sort
reveal file.py --name auth --type function --sort=-complexity

# Step 4: Complex multi-condition query → switch to the ast noun
# (--name becomes --where 'name~=...', the rest maps cleanly)
reveal ast file.py --where 'name~=auth' --where 'complexity>10' --where 'lines>20' --kind function --sort=-complexity

# Step 5: Combine with cross-adapter patterns
# (--stdin reads one path per line, so hand it file paths, not the text listing)
reveal ast file.py --where 'name~=auth' --format json | jq -r '.results[].file' | sort -u | reveal --stdin --check
```

---

## Which Nouns Take Which Options?

| Noun or adapter | Options (flags) | Example |
|-----------------|-----------------|---------|
| `ast` | Rich filtering: `--where`, `--kind`, `--sort`, `--limit` | `reveal ast src --kind function --where 'lines>50'` |
| `json` | Field filters, `--view schema\|flatten\|keys\|...` | `reveal json data.json --view schema` |
| `markdown` | Frontmatter filtering, body text | `reveal markdown docs --where status=draft --match X` |
| `metrics` | Metric filtering, hotspots | `reveal metrics src --view hotspots`, `--where 'avg_complexity>=10'` (`stats://` is a deprecated alias: it still answers, with a note) |
| `git` | Commit filtering, views | `reveal git . --where author=Alice --since 2024-01-01`, `reveal git app.py --view history` |
| `calls` | Call graph | `reveal calls src --callers fn`, `reveal calls src --sort=-callers --limit 10` |
| `patches` | Test patch pressure | `reveal patches src --view target --min 3 --limit 20` |
| `imports` | Import graph | `--unused`, `--circular`, `--importers` (`depends://` is deprecated: it still answers, with a note; use `reveal imports PATH --importers`) |
| `claude://` | Session filtering (a session is an address, so the URI stays) | `reveal claude://session/NAME --errors`, `--detail summary`, `--match TEXT` |
| `xlsx` | Sheet/cells | `reveal xlsx model.xlsx --sheet Sales --cells A1:D10` |
| `ssl://` (ops) | Expiry/summary query options | `?expiring-within=30` (implies `--check`), `?summary` (batch and nginx views) |
| `cpanel://` (ops) | Domain/SSL filters | `?domain_type=addon`, `?dns-verified` |
| `letsencrypt://` (ops) | Cert audit | `?check-orphans`, `?check-duplicates` |
| `autossl://` (ops) | Run filtering | `?only-failures`, `?summary`, `?user=NAME` |
| `nginx://`, `domain://` (ops) | ❌ None | Use element paths; unrecognized `?params` are ignored with a warning |
| `env://` | ❌ None | Use element paths; a `?query` is read as a variable name and fails |
| `mysql://`, `sqlite://` | Element paths | `sqlite://db.sqlite/users`; `reveal sqlite://db.sqlite --view health` |

---

## See Also

- `reveal help://tricks` — Task-based workflow recipes
- `reveal help://query-syntax` — Filter operator reference (=, !=, >, ~=, ..)
- `reveal help://query-params` — Each noun's options and their old query keys
- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) — Full filter operator reference
