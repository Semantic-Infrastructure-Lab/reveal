---
title: Query Parameter Reference
description: Complete reference for query parameters across all Reveal adapters
date: 2026-02-07
---

# Query Parameter Reference

Query parameters allow filtering, formatting, and modifying adapter behavior using URI syntax: `adapter://resource?param=value&param2=value2`

## Quick Reference

| Adapter | Query Params | Example |
|---------|--------------|---------|
| **imports://** | `unused`, `circular`, `violations` | `imports://.?unused` |
| **git://** | `type`, `detail`, `element`, `author`, `email`, `message`, `hash`, `ref` | `git://file.py?type=history` |
| **json://** | `schema`, `flatten`, `gron`, `type`, `keys`, `length`, field filters, `sort`, `limit`, `offset` | `json://data.json?type=object` |
| **markdown://** | field filters (frontmatter), `aggregate`, `body-contains`, `sort`, `limit`, `offset` | `markdown://docs/?status=draft` |
| **stats://** | `hotspots`, `code_only`, `min_lines`, `max_lines`, `min_complexity`, `max_complexity`, `min_functions` | `stats://.?hotspots` |
| **ast://** | `type`, `name`, `complexity`, `lines`, `depth`, `decorator`, `calls`, `callee_of`, `show`, `rank` | `ast://src?complexity>10` |
| **calls://** | `target`, `callees`, `rank`, `top`, `depth`, `format`, `builtins` | `calls://src?target=fn` |
| **claude://** | `summary`, `errors`, `tools`, `contains`, `role`, `search`, `tail`, `last`, `tokens` | `claude://session?summary` |
| **depends://** | `top`, `format` | `depends://src?top=10` |
| **xlsx://** | `sheet`, `range`, `search`, `format`, `limit`, `formulas`, `powerpivot`, `powerquery`, `names`, `connections` | `xlsx://model.xlsx?sheet=Sales` |
| **cpanel://** | `domain_type`, `dns-verified`, `check-live` | `cpanel://USER/ssl?domain_type=addon` |
| **ssl://** | `expiring-within`, `summary` | `ssl://host?expiring-within=30` |
| **diff://** | none | N/A |
| **env://** | none | N/A |
| **sqlite://** | none | N/A |
| **mysql://** | none | N/A |
| **autossl://** | `only-failures`, `summary`, `user=NAME` | `autossl://latest?only-failures` |
| **letsencrypt://** | `check-orphans`, `check-duplicates` | `letsencrypt://?check-orphans` |
| **nginx://** | none (CLI flags only; unrecognized `?params` stripped with warning) | N/A |
| **python://** | none | N/A |
| **domain://** | none | N/A |
| **reveal://** | none | N/A |

## Detailed Documentation

### imports:// - Import Analysis

**Purpose**: Detect import-related code quality issues

**Query Parameters**:

- **`unused`** (flag) - Find unused imports
  ```bash
  reveal 'imports://src?unused'
  ```
  Shows all imports that are declared but never referenced in the code.

- **`circular`** (flag) - Detect circular dependencies
  ```bash
  reveal 'imports://src?circular'
  ```
  Identifies circular import chains that can cause runtime errors.

- **`violations`** (flag) - Check layer violations
  ```bash
  reveal 'imports://src?violations'
  ```
  Detects imports that violate architectural layer boundaries (if configured).

**Combining Parameters**:
```bash
reveal 'imports://src?unused&circular'
```

---

### git:// - Git Repository Inspection

**Purpose**: Query git history, blame, and file tracking

**Query Parameters**:

- **`type`** - Query type for file operations
  - **Values**: `history`, `blame`
  - **Examples**:
    ```bash
    reveal 'git://app.py?type=history'   # File commit history
    reveal 'git://app.py?type=blame'     # Git blame for file
    ```

- **`detail`** - Detail level for blame
  - **Values**: `full`, `summary`
  - **Example**:
    ```bash
    reveal 'git://app.py?type=blame&detail=summary'
    ```

- **`element`** - Semantic element for blame (function/class name)
  - **Example**:
    ```bash
    reveal 'git://app.py?type=blame&element=load_config'
    ```
  - Blames only the specified function or class

- **`author`** - Filter commits by author name (case-insensitive)
  - **Operators**: `=` (exact), `~=` (contains)
  - **Examples**:
    ```bash
    reveal 'git://app.py?type=history&author=John'
    reveal 'git://app.py?type=history&author~=john'
    ```

- **`email`** - Filter commits by author email
  - **Operators**: `=` (exact), `~=` (contains)
  - **Example**:
    ```bash
    reveal 'git://app.py?type=history&email~=@example.com'
    ```

- **`message`** - Filter commits by message (supports regex with `~=`)
  - **Examples**:
    ```bash
    reveal 'git://app.py?type=history&message~=bug'
    reveal 'git://app.py?type=history&message=Initial commit'
    ```

- **`hash`** - Filter commits by hash prefix
  - **Example**:
    ```bash
    reveal 'git://app.py?type=history&hash=a1b2c3d'
    ```

- **`ref`** - Override the starting ref (alias for `@ref` in the URI)
  - **Example**:
    ```bash
    reveal 'git://src/app.py?type=history&ref=v0.63.0'
    reveal 'git://.?ref=main'          # same as git://.@main
    ```

**Combining Parameters**:
```bash
reveal 'git://.?type=history&author~=john&message~=fix'
```

---

### json:// - JSON Structure Inspection

**Purpose**: Query and filter JSON data

**Query Parameters**:

- **`schema`** (flag) - Show JSON schema instead of data
  ```bash
  reveal 'json://data.json?schema'
  ```

- **Field Filters** - Filter by JSON field values
  - **Syntax**: `field=value`, `field~=pattern`, `field>N`, `field<N`
  - **Examples**:
    ```bash
    reveal 'json://data.json?type=user'           # Exact match
    reveal 'json://data.json?name~=john'          # Contains pattern
    reveal 'json://data.json?age>25'              # Numeric comparison
    reveal 'json://data.json?status=active&role=admin'  # Multiple filters
    ```

**Supported Operators**:
- `=` - Exact match
- `~=` - Contains (case-insensitive substring match)
- `>`, `<`, `>=`, `<=` - Numeric/lexical comparison
- `..` - Range (e.g., `age=25..35`)
- `!` - Field does not exist (e.g., `!draft`)
- `*` - Wildcard (e.g., `name=*john*`)

---

### markdown:// - Markdown Document Query

**Purpose**: Search and filter markdown documents by frontmatter

**Query Parameters**:

Same as **json://** - markdown adapter supports filtering by frontmatter fields using the unified query syntax.

**Examples**:
```bash
reveal 'markdown://docs/?status=draft'              # Find drafts
reveal 'markdown://docs/?tags~=python'               # Documents tagged with python
reveal 'markdown://docs/?!published'                 # Unpublished documents
reveal 'markdown://docs/?created>2026-01-01'         # Documents created after date
reveal 'markdown://docs/?priority=high&status=draft' # High-priority drafts
```

**Wildcard Search**:
```bash
reveal 'markdown://docs/?title=*api*'    # Titles containing "api"
```

**Body Text Search** (markdown-specific, not frontmatter):
```bash
reveal 'markdown://docs/?body-contains=nginx'                    # Body mentions "nginx"
reveal 'markdown://docs/?body-contains=nginx&body-contains=ssl'  # Both terms (AND)
```
`body-contains=` is case-insensitive substring match. Multiple values are AND'd. Combines with frontmatter filters and result control (`sort=`, `limit=`).

**Extra columns** (markdown-specific):
```bash
reveal 'markdown://primitives/?type=framework&fields=book,cohort'  # Append book= cohort= inline per result
```
`fields=f1,f2` appends comma-separated frontmatter values as `field=value` on each result row. Fields absent from a file are silently omitted.

---

### stats:// - Code Statistics

**Purpose**: Codebase metrics and quality analysis

**Query Parameters**:

- **`hotspots`** (flag) - Identify quality hotspots (worst 10 files)
  ```bash
  reveal 'stats://.?hotspots'
  ```
  Shows files with lowest quality scores (most in need of refactoring).

- **`code_only`** (flag) - Exclude data/config files from analysis
  ```bash
  reveal 'stats://.?code_only'
  ```
  Filters out `.json` > 10KB, `.yaml`, `.xml`, `.csv`, `.toml` files.

**Combining Parameters**:
```bash
reveal 'stats://.?hotspots&code_only'
```

---

### ast:// - Abstract Syntax Tree Inspection

**Purpose**: Query code structure — find functions by complexity, size, name, type, and call relationships.

**Query Parameters**:

- **`type`** - Filter by element type (`function`, `class`, `method`)
  ```bash
  reveal 'ast://src?type=function'
  reveal 'ast://src?type=class'
  ```

- **`name`** / **`name~=`** - Filter by element name (exact or substring)
  ```bash
  reveal 'ast://src?name=validate_item'
  reveal 'ast://src?name~=auth'          # name contains "auth"
  reveal 'ast://src?name=*handler*'      # wildcard match
  ```

- **`complexity>`** - Filter by cyclomatic complexity
  ```bash
  reveal 'ast://src?complexity>10'       # complexity over 10
  reveal 'ast://src?complexity>5&type=function'
  ```

- **`lines`** / **`lines>`** - Filter by element length in lines
  ```bash
  reveal 'ast://src?lines>50'            # functions longer than 50 lines
  reveal 'ast://src?lines=20..50'        # functions that are 20–50 lines long
  ```

- **`depth>`** - Filter by nesting depth
  ```bash
  reveal 'ast://src?depth>3'             # deeply nested code
  ```

- **`decorator`** - Filter by decorator name
  ```bash
  reveal 'ast://src?decorator=property'
  reveal 'ast://src?decorator=staticmethod'
  ```

- **`calls`** - Find functions that call a given function (within-file)
  ```bash
  reveal 'ast://src?calls=validate_item'
  reveal 'ast://src?calls=*send*'        # wildcard: calls anything with "send"
  ```

- **`callee_of`** - Find functions called by a given function (within-file)
  ```bash
  reveal 'ast://src?callee_of=main'
  ```

- **`show=calls`** - Show call graph for all functions in the file
  ```bash
  reveal 'ast://src/file.py?show=calls'
  ```

- **`rank`** - Sort by a field descending (e.g., `rank=-complexity`)
  ```bash
  reveal 'ast://src?rank=-complexity'    # most complex first
  reveal 'ast://src?rank=-lines'         # longest first
  ```

> For cross-file call graph queries, use `calls://` (see below). `ast://` call filters (`calls=`, `callee_of=`) are within-file only.

---

### calls:// - Cross-File Call Graph

**Purpose**: Find who calls a function, what a function calls, or rank functions by coupling — across the entire project.

**Query Parameters**:

- **`target`** - Find all callers of a function (reverse lookup)
  ```bash
  reveal 'calls://src?target=validate_item'
  # Shorthand: calls://src/file.py:validate_item
  ```

- **`callees`** - Find everything a function calls (forward lookup)
  ```bash
  reveal 'calls://src?callees=validate_item'
  reveal 'calls://src?callees=validate_item&builtins=true'  # include len, str, etc.
  ```

- **`rank=callers`** - Rank all functions by number of unique callers (coupling metrics)
  ```bash
  reveal 'calls://src?rank=callers'          # top 10 most-called
  reveal 'calls://src?rank=callers&top=20'   # top 20
  ```

- **`depth`** - Transitive caller levels for `?target` (default 1, max 5)
  ```bash
  reveal 'calls://src?target=validate_item&depth=2'  # callers-of-callers
  ```

- **`format`** - Output format: `text` (default), `json`, `dot` (Graphviz)
  ```bash
  reveal 'calls://src?target=main&format=dot' | dot -Tsvg > graph.svg
  ```

- **`builtins`** - Include Python builtins in `?callees` and `?rank` output (default: false)
  ```bash
  reveal 'calls://src?callees=fn&builtins=true'
  ```

---

### claude:// - Claude Conversation Analysis

**Purpose**: Analyze Claude Code session logs (JSONL conversation files)

**Query Parameters**:

- **`summary`** (flag) - Session summary (overview + key events)
  ```bash
  reveal 'claude://my-session?summary'
  ```

- **`errors`** (flag) - Filter for messages containing errors
  ```bash
  reveal 'claude://my-session?errors'
  ```

- **`tools=<name>`** (string) - Filter for specific tool usage
  ```bash
  reveal 'claude://my-session?tools=Bash'
  reveal 'claude://my-session?tools=Edit'
  ```

- **`contains=<text>`** (string) - Filter messages containing text
  ```bash
  reveal 'claude://my-session?contains=reveal'
  ```

- **`role=<role>`** (string) - Filter by message role (`user` or `assistant`)
  ```bash
  reveal 'claude://my-session?role=user'
  ```

- **`search=<term>`** (string) - Search all message content (text, thinking, tool inputs), case-insensitive
  ```bash
  reveal 'claude://my-session?search=FileNotFoundError'
  ```

- **`tail=N`** (integer) - Show last N assistant turns — fast session recovery
  ```bash
  reveal 'claude://my-session?tail=3'
  reveal 'claude://my-session?tail=1'
  ```

- **`last`** (flag) - Show last assistant turn (shorthand for `?tail=1`)
  ```bash
  reveal 'claude://my-session?last'
  ```

- **`tokens`** (flag) - Token usage breakdown by message role (input/output/cache)
  ```bash
  reveal 'claude://my-session?tokens'
  ```

---

### depends:// - Inverse Dependency Graph

**Purpose**: Find all files that import a given module ("what depends on this?")

**Query Parameters**:

- **`top=N`** (integer) - Limit to the N most-imported files (directory mode)
  ```bash
  reveal 'depends://src?top=10'
  ```

- **`format=dot`** (string) - Output GraphViz DOT format for visualization
  ```bash
  reveal 'depends://src/core.py?format=dot'
  ```

---

### xlsx:// - Excel/XLSX Workbook

**Purpose**: Extract data, structure, and embedded models from Excel files

**Query Parameters**:

- **`sheet=<name|index>`** (string|integer) - Sheet to extract (name or 0-based index)
  ```bash
  reveal 'xlsx://model.xlsx?sheet=Sales'
  reveal 'xlsx://model.xlsx?sheet=0'
  ```

- **`range=<A1:C10>`** (string) - Cell range in A1 notation
  ```bash
  reveal 'xlsx://model.xlsx?sheet=Sales&range=A1:C10'
  ```

- **`search=<text>`** (string) - Search for text across all sheets
  ```bash
  reveal 'xlsx://model.xlsx?search=revenue'
  ```

- **`format=<format>`** (string) - Output format (`text`, `json`, `csv`)
  ```bash
  reveal 'xlsx://model.xlsx?sheet=Sales&format=csv'
  ```

- **`limit=N`** (integer) - Maximum number of rows to return
  ```bash
  reveal 'xlsx://model.xlsx?sheet=Sales&limit=100'
  ```

- **`formulas=true`** (boolean) - Show formulas instead of computed values
  ```bash
  reveal 'xlsx://model.xlsx?sheet=Budget&formulas=true'
  ```

- **`powerpivot=<mode>`** (string) - Extract Power Pivot data model (`tables`, `schema`, `measures`, `dax`)
  ```bash
  reveal 'xlsx://model.xlsx?powerpivot=schema'
  reveal 'xlsx://model.xlsx?powerpivot=dax'
  ```

- **`powerquery=<mode>`** (string) - Extract Power Query M code (`list`, `show`, or query name)
  ```bash
  reveal 'xlsx://model.xlsx?powerquery=list'
  reveal 'xlsx://model.xlsx?powerquery=SalesData'
  ```

- **`names`** (flag) - List named ranges defined in the workbook
  ```bash
  reveal 'xlsx://model.xlsx?names'
  ```

- **`connections`** (string/flag) - List external data connections
  ```bash
  reveal 'xlsx://model.xlsx?connections=list'
  ```

---

### cpanel:// - cPanel User Environment

**Purpose**: Inspect cPanel user environments — domains, SSL certs, ACL health

**Query Parameters**:

- **`domain_type=<type>`** (string, on `ssl` element) - Filter SSL certs by domain type
  - Values: `main_domain`, `addon`, `subdomain`, `parked`
  ```bash
  reveal 'cpanel://USERNAME/ssl?domain_type=addon'
  reveal 'cpanel://USERNAME/ssl?domain_type=main_domain'
  ```

- **`dns-verified`** (flag) - Exclude domains with no DNS record (NXDOMAIN) from SSL counts
  ```bash
  reveal 'cpanel://USERNAME/ssl?dns-verified'
  reveal 'cpanel://USERNAME/full-audit?dns-verified'
  ```
  Equivalent to `--dns-verified` CLI flag; URI form preferred when options need to travel with the resource.

- **`check-live`** (flag) - Cross-check disk certs against live TLS (network call)
  ```bash
  reveal 'cpanel://USERNAME/ssl?check-live'
  reveal 'cpanel://USERNAME/full-audit?check-live'
  ```
  Equivalent to `--check-live` CLI flag; URI form preferred in batch/pipeline workflows.

---

## Adapters Without Query Parameters (Current State)

The following adapters use **element paths** for navigation — query params are not needed because the element path covers the use case:

- **env://** - `env://VAR_NAME` (element = variable name)
- **sqlite://** - `sqlite://db.sqlite/table_name` (element = table)
- **mysql://** - `mysql://host/element` (element = connections, innodb, errors, databases, etc.)
- **python://** - `python://packages` (element = topic)
- **reveal://** - `reveal://adapters` (element = topic)
- **diff://** - Element path selects comparison side

The following adapters use CLI flags that switch routing mode (not URI filters) — they are documented in `--discover` under `cli_only_flags` but do not support query params:

- **nginx://**, **domain://**, **mysql://**, **sqlite://** — `--check`, `--only-failures` are check-mode switches; migrating to query params would require routing-layer changes

The following adapters still have adapter-specific options expressed as CLI flags rather than query params. These are known migration targets — the direction is to move them to URI query params so options travel with the resource:

| Adapter | Current (CLI flag) | Target (query param) |
|---------|-------------------|----------------------|
| `claude://` | `reveal claude:// --base-path /path` | `reveal 'claude://?base-path=/path'` |

**Already migrated** — both CLI flag and URI query param now work:

| Adapter | CLI flag | URI query param |
|---------|---------|-----------------|
| `ssl://` | `reveal ssl://host --expiring-within 30` | `reveal 'ssl://host?expiring-within=30'` ✅ |
| `ssl://` | `reveal ssl://nginx:///etc/nginx/*.conf --summary` | `reveal 'ssl://nginx:///etc/nginx/*.conf?summary'` ✅ |
| `cpanel://` | `reveal cpanel://USER/ssl --dns-verified` | `reveal 'cpanel://USER/ssl?dns-verified'` ✅ |
| `cpanel://` | `reveal cpanel://USER/ssl --check-live` | `reveal 'cpanel://USER/ssl?check-live'` ✅ |
| `letsencrypt://` | `reveal letsencrypt:// --check-orphans` | `reveal 'letsencrypt://?check-orphans'` ✅ |
| `letsencrypt://` | `reveal letsencrypt:// --check-duplicates` | `reveal 'letsencrypt://?check-duplicates'` ✅ |
| `autossl://` | `reveal autossl://latest --only-failures` | `reveal 'autossl://latest?only-failures'` ✅ |
| `autossl://` | `reveal autossl://latest --summary` | `reveal 'autossl://latest?summary'` ✅ |
| `autossl://` | `reveal autossl://latest --user=NAME` | `reveal 'autossl://latest?user=NAME'` ✅ |

The `ast://` adapter is the **reference implementation** — all filtering options are query parameters. New URI adapters should follow this pattern. See [ADAPTER_CONSISTENCY.md](../development/ADAPTER_CONSISTENCY.md#adapter-specific-flags-vs-query-parameters) for the full rationale.

---

## Universal Query Operators

The following operators work across adapters that support field filtering (json://, markdown://):

| Operator | Description | Example |
|----------|-------------|---------|
| `=` | Exact match | `status=published` |
| `~=` | Contains (substring) | `title~=python` |
| `>`, `<` | Comparison | `count>100` |
| `>=`, `<=` | Comparison (inclusive) | `age>=18` |
| `..` | Range (inclusive) | `lines=50..200` |
| `!` | Field absence | `!draft` (no draft field) |
| `*` | Wildcard | `name=*john*` |

---

## Combining Query Parameters

Multiple query parameters are combined with `&`:

```bash
reveal 'git://.?type=history&author~=john&message~=fix'
reveal 'markdown://docs/?status=draft&priority=high'
reveal 'imports://.?unused&circular'
```

**Behavior**:
- Parameters are **AND**ed together (all must match)
- For adapters supporting field filters, multiple filters narrow results

---

## Query Parameter vs Element Path

**When to use query parameters**:
- Filtering multiple results (imports, markdown documents, git commits)
- Modifying adapter behavior (show schema, enable hotspots)
- Applying conditions across data

**When to use element paths**:
- Accessing a specific named resource (table, variable, function)
- Examples:
  - `sqlite://db.sqlite/users` (table name)
  - `env://PATH` (variable name)
  - `ssl://example.com/san` (certificate element)

---

## Testing Query Parameters

To see what query parameters an adapter supports:

```bash
reveal 'adapter://?help'           # Show adapter help
reveal --agent-help                # Full query reference
```

Or programmatically:

```bash
reveal 'adapter://' --format json | jq '.query_params'
```

---

## Best Practices

1. **Use quotes** around URIs with query parameters (shell may interpret `?` and `&`)
   ```bash
   reveal 'imports://.?unused'    # ✅ Correct
   reveal imports://.?unused       # ❌ Shell may break this
   ```

2. **Start broad, then filter** - Run without params first to see data structure
   ```bash
   reveal 'git://app.py?type=history'                    # All commits
   reveal 'git://app.py?type=history&author~=john'       # Then filter
   ```

3. **Combine complementary filters** - Use multiple params for precision
   ```bash
   reveal 'markdown://docs/?status=draft&tags~=python&!published'
   ```

4. **Check adapter schema** for available params
   ```bash
   reveal 'adapter://' --format json | jq '.query_params'
   ```

---

## See Also

- [Adapter Authoring Guide](../development/ADAPTER_AUTHORING_GUIDE.md) - How to add query params to custom adapters
- [Agent Help](../AGENT_HELP.md) - AI agent integration guide
- [Output Contract](../development/OUTPUT_CONTRACT.md) - Adapter output format specification
