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
| **git://** | `type`, `detail`, `element`, `author`, `email`, `message`, `hash` | `git://file.py?type=history` |
| **json://** | `schema`, field filters | `json://data.json?type=object` |
| **markdown://** | field filters (frontmatter) | `markdown://docs/?status=draft` |
| **stats://** | `hotspots`, `code_only` | `stats://.?hotspots` |
| **ast://** | `lines` | `ast://file.py?lines=50..200` |
| **claude://** | `summary`, `tools`, `errors` | `claude://conv.json?summary` |
| **diff://** | none | N/A |
| **env://** | none | N/A |
| **sqlite://** | none | N/A |
| **mysql://** | none | N/A |
| **ssl://** | none | N/A |
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

**Purpose**: Explore Python AST nodes

**Query Parameters**:

- **`lines`** - Filter AST nodes by line range
  - **Syntax**: `lines=START..END`
  - **Example**:
    ```bash
    reveal 'ast://file.py?lines=50..200'
    ```
  - Shows only AST nodes within the specified line range.

---

### claude:// - Claude Conversation Analysis

**Purpose**: Analyze Claude API conversation logs

**Query Parameters**:

- **`summary`** (flag) - Show conversation summary instead of full details
  ```bash
  reveal 'claude://conversation.json?summary'
  ```

- **`tools`** (flag) - Show tool usage statistics
  ```bash
  reveal 'claude://conversation.json?tools'
  ```

- **`errors`** (flag) - Show only error messages
  ```bash
  reveal 'claude://conversation.json?errors'
  ```

**Combining Parameters**:
```bash
reveal 'claude://conversation.json?summary&tools'
```

---

## Adapters Without Query Parameters

The following adapters do not currently support query parameters:

- **diff://** - Comparison adapter (uses element path for filtering)
- **env://** - Environment variables (use element name: `env://VAR_NAME`)
- **sqlite://** - SQLite inspection (use element name: `sqlite://db.sqlite/table_name`)
- **mysql://** - MySQL inspection (use element name: `mysql://host/database/table`)
- **ssl://** - SSL certificate inspection (use element name: `ssl://domain.com/san`)
- **python://** - Python environment (use element name: `python://packages`)
- **domain://** - Domain inspection (use element name: `domain://example.com/dns`)
- **reveal://** - Reveal introspection (use element name: `reveal://adapters`)

These adapters use **element paths** instead of query parameters for filtering.

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

- [Adapter Authoring Guide](ADAPTER_AUTHORING_GUIDE.md) - How to add query params to custom adapters
- [Agent Help](AGENT_HELP.md) - AI agent integration guide
- [Output Contract](OUTPUT_CONTRACT.md) - Adapter output format specification
