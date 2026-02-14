# SQLite Adapter Guide

**Version**: 1.0 (reveal 0.49.2+)
**Status**: 🟢 Stable - Production Ready
**Adapter**: `sqlite://`

---

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [Features](#features)
- [URI Syntax](#uri-syntax)
- [Database Overview](#database-overview)
- [Table Inspection](#table-inspection)
- [Output Formats](#output-formats)
- [Common Workflows](#common-workflows)
- [Performance](#performance)
- [Limitations](#limitations)
- [Error Messages](#error-messages)
- [Tips & Best Practices](#tips-best-practices)
- [Integration with Other Tools](#integration-with-other-tools)
- [Related Documentation](#related-documentation)
- [Version History](#version-history)

---

## Quick Start

The SQLite adapter provides zero-dependency database exploration and schema inspection.

**Common examples:**

```bash
# 1. Database overview (all tables, indices, size)
reveal sqlite:///path/to/app.db

# 2. Table structure (columns, types, constraints, indices)
reveal sqlite:///path/to/app.db/users

# 3. Relative paths
reveal sqlite://./local.db
reveal sqlite://./data/test.db

# 4. Multiple tables
reveal sqlite:///app.db/users
reveal sqlite:///app.db/posts
reveal sqlite:///app.db/comments

# 5. JSON output for scripting
reveal sqlite:///app.db --format=json
reveal sqlite:///app.db/users --format=json

# 6. Health check (planned feature)
reveal sqlite:///app.db --check
```

---

## Overview

### What is the SQLite Adapter?

The `sqlite://` adapter provides **structured database inspection** - explore schemas, tables, columns, indices, and relationships without writing SQL or using external tools.

**Why use sqlite:// instead of sqlite3 CLI?**

| Task | sqlite3 CLI | sqlite:// |
|------|-------------|-----------|
| Schema overview | ❌ `.schema` (unstructured) | ✅ Structured with stats |
| Table inspection | ✅ `PRAGMA table_info` | ✅ Human-readable format |
| External dependency | ❌ Requires sqlite3 binary | ✅ Built-in to reveal |
| JSON output | ❌ Manual scripting | ✅ `--format=json` flag |
| Progressive disclosure | ❌ All or nothing | ✅ Database → table → details |
| Foreign keys | ❌ Separate PRAGMA | ✅ Shown with table |
| Read-only mode | ❌ Manual flag | ✅ Automatic safety |

**Key capabilities:**

- 🔍 **Schema exploration**: Tables, columns, indices, foreign keys
- 📊 **Statistics**: Row counts, table sizes, database metrics
- 🔐 **Read-only mode**: Safe for production database inspection
- 📈 **Progressive disclosure**: Start broad (database), drill down (table)
- 🎯 **Zero dependencies**: Uses Python built-in sqlite3 module
- 🤖 **AI-friendly**: JSON schema for agent integration

---

## Features

### 1. **Database Overview**

Get high-level view of entire database:

```bash
reveal sqlite:///path/to/app.db
```

**Information provided:**
- **Tables**: All user tables (excluding sqlite_* internal tables)
- **Indices**: All indices with associated tables
- **Statistics**: Database size, SQLite version, page size
- **Configuration**: Journal mode, encoding, foreign key enforcement
- **Row counts**: Total rows per table

**Example output:**
```
Database: app.db
Size: 524 KB
SQLite Version: 3.35.5
Tables: 5
  users (150 rows)
  posts (1,234 rows)
  comments (5,678 rows)
  tags (45 rows)
  post_tags (2,567 rows)

Indices: 8
  idx_users_email on users
  idx_posts_author on posts
  idx_posts_created on posts
  idx_comments_post on comments
  ...

Configuration:
  Page Size: 4096 bytes
  Journal Mode: WAL
  Encoding: UTF-8
  Foreign Keys: ON
```

### 2. **Table Structure Inspection**

Detailed view of individual tables:

```bash
reveal sqlite:///path/to/app.db/users
```

**Information provided:**
- **Columns**: Name, type, nullable, default value, primary key
- **Indices**: All indices on this table
- **Foreign keys**: Relationships to other tables
- **Constraints**: Primary keys, unique constraints
- **Statistics**: Row count, estimated size

**Example output:**
```
Table: users
Rows: 150

Columns:
  id              INTEGER   PRIMARY KEY  AUTOINCREMENT
  email           TEXT      NOT NULL     UNIQUE
  username        VARCHAR   NOT NULL
  password_hash   TEXT      NOT NULL
  created_at      TIMESTAMP NOT NULL     DEFAULT CURRENT_TIMESTAMP
  updated_at      TIMESTAMP
  is_active       BOOLEAN   NOT NULL     DEFAULT 1
  role            TEXT                   DEFAULT 'user'

Indices:
  PRIMARY KEY (id)
  UNIQUE (email)
  idx_users_email on (email)
  idx_users_username on (username)

Foreign Keys:
  None

Constraints:
  PRIMARY KEY (id)
  UNIQUE (email)
```

### 3. **Foreign Key Relationships**

Automatically detect and display table relationships:

```bash
reveal sqlite:///app.db/posts
```

**Example output:**
```
Table: posts
Rows: 1,234

Columns:
  id          INTEGER   PRIMARY KEY  AUTOINCREMENT
  title       TEXT      NOT NULL
  content     TEXT      NOT NULL
  author_id   INTEGER   NOT NULL
  created_at  TIMESTAMP NOT NULL

Foreign Keys:
  author_id → users(id) ON DELETE CASCADE
```

### 4. **Index Information**

View all indices with detailed information:

```bash
# Database-level (all indices)
reveal sqlite:///app.db

# Table-level (table indices)
reveal sqlite:///app.db/users
```

**Index details shown:**
- Index name
- Indexed columns
- Associated table
- Unique constraint (if applicable)

### 5. **Database Statistics**

Comprehensive metrics at database and table levels:

**Database-level:**
- Total size in bytes/KB/MB
- Number of tables
- Number of indices
- Total row count
- SQLite version
- Page size
- Journal mode
- Encoding

**Table-level:**
- Row count (via `COUNT(*)`)
- Column count
- Index count
- Foreign key count

### 6. **Configuration Information**

SQLite-specific configuration details:

```bash
reveal sqlite:///app.db
```

**Configuration shown:**
- Page size (e.g., 4096 bytes)
- Journal mode (DELETE, TRUNCATE, PERSIST, MEMORY, WAL, OFF)
- Encoding (UTF-8, UTF-16le, UTF-16be)
- Foreign key enforcement (ON/OFF)
- Auto-vacuum mode
- Synchronous mode

---

## URI Syntax

### Path Format

```
sqlite:///<path/to/database.db>[/table]
```

**Components:**

| Part | Description | Example |
|------|-------------|---------|
| `sqlite://` | Protocol | Required prefix |
| `//` or `///` | Path type | `//` = relative, `///` = absolute |
| `path/to/db.db` | Database path | Must end in `.db`, `.sqlite`, or `.sqlite3` |
| `/table` | Optional table | Table name for detailed inspection |

### Absolute Paths

Use **three slashes** (`///`) for absolute paths:

```bash
# Linux/macOS absolute paths
reveal sqlite:///var/lib/app/data.db
reveal sqlite:///home/user/project/app.db
reveal sqlite:///Users/name/Documents/test.db

# Windows absolute paths
reveal sqlite:///C:/Users/name/data.db
reveal sqlite:///D:/Projects/app/database.sqlite
```

### Relative Paths

Use **two slashes** (`//`) for relative paths:

```bash
# Current directory
reveal sqlite://./local.db
reveal sqlite://./data.db

# Subdirectory
reveal sqlite://./data/app.db
reveal sqlite://./databases/test.sqlite

# Parent directory
reveal sqlite://./../shared.db
```

### File Extensions

Supported database file extensions:

- `.db` - Most common
- `.sqlite` - Explicit SQLite format
- `.sqlite3` - Version-specific naming

**All three are treated identically** by the adapter.

---

## Database Overview

### View All Tables

```bash
reveal sqlite:///path/to/app.db
```

**Output includes:**

1. **Database metadata**: Path, size, version
2. **Table list**: All user tables with row counts
3. **Index list**: All indices with associated tables
4. **Configuration**: Page size, journal mode, encoding

**Use cases:**
- Understand database structure
- Find table names
- Check database health
- Generate documentation

### JSON Output

For programmatic access:

```bash
reveal sqlite:///app.db --format=json
```

**JSON structure:**
```json
{
  "contract_version": "1.1",
  "type": "sqlite_database",
  "source": "/path/to/app.db",
  "source_type": "database",
  "db_path": "/path/to/app.db",
  "size_bytes": 524288,
  "tables": [
    {
      "name": "users",
      "row_count": 150
    },
    {
      "name": "posts",
      "row_count": 1234
    }
  ],
  "indices": [
    {
      "name": "idx_users_email",
      "table": "users",
      "columns": ["email"]
    }
  ],
  "version": "3.35.5",
  "config": {
    "page_size": 4096,
    "journal_mode": "WAL",
    "encoding": "UTF-8",
    "foreign_keys": true
  }
}
```

---

## Table Inspection

### View Table Structure

```bash
reveal sqlite:///path/to/app.db/table_name
```

**Output includes:**

1. **Table name** and row count
2. **Column definitions**: Name, type, nullable, default, constraints
3. **Primary keys**: Single or composite
4. **Unique constraints**: Unique columns
5. **Indices**: All indices on table
6. **Foreign keys**: Relationships to other tables

### Column Information

Each column shows:

- **Name**: Column name
- **Type**: SQLite type (INTEGER, TEXT, REAL, BLOB, NULL)
- **Nullable**: NOT NULL constraint
- **Default**: Default value (if any)
- **Constraints**: PRIMARY KEY, UNIQUE, etc.

**Example:**
```
id              INTEGER   PRIMARY KEY  AUTOINCREMENT
email           TEXT      NOT NULL     UNIQUE
username        VARCHAR   NOT NULL
created_at      TIMESTAMP NOT NULL     DEFAULT CURRENT_TIMESTAMP
is_active       BOOLEAN   NOT NULL     DEFAULT 1
```

### Index Information

Table-specific indices with details:

**Example:**
```
Indices:
  PRIMARY KEY (id)
  UNIQUE (email)
  idx_users_email on (email)
  idx_users_username on (username)
  idx_users_created on (created_at DESC)
```

### Foreign Key Relationships

Shows all foreign key constraints:

**Example:**
```
Foreign Keys:
  author_id → users(id) ON DELETE CASCADE
  category_id → categories(id) ON DELETE SET NULL
```

**Foreign key details:**
- Source column
- Target table and column
- ON DELETE action
- ON UPDATE action

### JSON Output

For programmatic access:

```bash
reveal sqlite:///app.db/users --format=json
```

**JSON structure:**
```json
{
  "contract_version": "1.1",
  "type": "sqlite_table",
  "source": "/path/to/app.db",
  "source_type": "table",
  "table_name": "users",
  "row_count": 150,
  "columns": [
    {
      "name": "id",
      "type": "INTEGER",
      "nullable": false,
      "primary_key": true,
      "auto_increment": true
    },
    {
      "name": "email",
      "type": "TEXT",
      "nullable": false,
      "unique": true
    }
  ],
  "indices": [
    {
      "name": "PRIMARY",
      "columns": ["id"],
      "unique": true
    },
    {
      "name": "idx_users_email",
      "columns": ["email"],
      "unique": false
    }
  ],
  "foreign_keys": [
    {
      "column": "author_id",
      "references_table": "users",
      "references_column": "id",
      "on_delete": "CASCADE"
    }
  ]
}
```

---

## Output Formats

The SQLite adapter supports two output formats:

### 1. Text Format (Default)

Human-readable, formatted output:

```bash
reveal sqlite:///app.db
reveal sqlite:///app.db/users
```

**Features:**
- Color coding (if terminal supports)
- Table formatting
- Clear section headers
- Human-readable sizes (KB/MB)

### 2. JSON Format

Machine-readable with metadata:

```bash
reveal sqlite:///app.db --format=json
reveal sqlite:///app.db/users --format=json
```

**Output types:**

- `sqlite_database` - Database overview
- `sqlite_table` - Table structure
- `sqlite_health` - Health check results (planned)

---

## Common Workflows

### Workflow 1: Explore Unknown Database

**Scenario**: Received a SQLite database file, need to understand its structure.

```bash
# Step 1: Database overview
reveal sqlite:///unknown.db

# Step 2: Identify key tables (look for user/auth tables)
reveal sqlite:///unknown.db | grep -i user
reveal sqlite:///unknown.db | grep -i auth

# Step 3: Inspect primary table
reveal sqlite:///unknown.db/users

# Step 4: Check relationships
reveal sqlite:///unknown.db/posts  # Look for foreign keys

# Step 5: Understand data model
reveal sqlite:///unknown.db/orders
reveal sqlite:///unknown.db/order_items
```

**Expected outcome**: Complete understanding of database schema and relationships.

### Workflow 2: Schema Documentation

**Scenario**: Generate documentation for database schema.

```bash
# Step 1: Generate markdown header
echo "# Database Schema Documentation" > SCHEMA.md
echo "" >> SCHEMA.md

# Step 2: Database overview
echo "## Overview" >> SCHEMA.md
reveal sqlite:///app.db >> SCHEMA.md

# Step 3: Document each table
for table in users posts comments tags; do
  echo "" >> SCHEMA.md
  echo "## Table: $table" >> SCHEMA.md
  reveal sqlite:///app.db/$table >> SCHEMA.md
done

# Result: Complete schema documentation in SCHEMA.md
```

**Expected outcome**: Auto-generated documentation for entire database.

### Workflow 3: Schema Comparison (Migration Planning)

**Scenario**: Compare two database versions before migration.

```bash
# Step 1: Export old schema to JSON
reveal sqlite:///old_version.db --format=json > old_schema.json

# Step 2: Export new schema to JSON
reveal sqlite:///new_version.db --format=json > new_schema.json

# Step 3: Compare schemas
diff old_schema.json new_schema.json

# Or use jq for specific comparisons
jq '.tables[].name' old_schema.json | sort > old_tables.txt
jq '.tables[].name' new_schema.json | sort > new_tables.txt
diff old_tables.txt new_tables.txt

# Step 4: Compare specific table
reveal sqlite:///old_version.db/users > old_users.txt
reveal sqlite:///new_version.db/users > new_users.txt
diff old_users.txt new_users.txt
```

**Expected outcome**: List of schema changes for migration planning.

### Workflow 4: Health Check

**Scenario**: Verify database integrity before backup or migration.

```bash
# Step 1: Check database can be opened
reveal sqlite:///app.db > /dev/null && echo "✓ Database readable"

# Step 2: Verify all tables accessible
for table in $(reveal sqlite:///app.db --format=json | jq -r '.tables[].name'); do
  reveal sqlite:///app.db/$table > /dev/null && echo "✓ Table $table OK"
done

# Step 3: Check row counts
reveal sqlite:///app.db --format=json | \
  jq -r '.tables[] | "\(.name): \(.row_count) rows"'

# Step 4: Verify foreign key integrity (manual SQL check)
sqlite3 app.db "PRAGMA foreign_key_check"
```

**Expected outcome**: Confirmation of database integrity.

### Workflow 5: Find Large Tables

**Scenario**: Identify tables consuming most space for optimization.

```bash
# Export to JSON and analyze with jq
reveal sqlite:///app.db --format=json | \
  jq -r '.tables[] | [.name, .row_count] | @tsv' | \
  sort -k2 -rn | \
  head -10

# Example output:
# posts       1234567
# comments    987654
# logs        456789
# ...
```

**Expected outcome**: Prioritized list of large tables for optimization.

### Workflow 6: Development Database Validation

**Scenario**: Verify development database matches expected schema.

```bash
# Step 1: Export expected schema
reveal sqlite:///production.db --format=json > expected_schema.json

# Step 2: Export development schema
reveal sqlite:///dev.db --format=json > dev_schema.json

# Step 3: Automated comparison
if diff -q expected_schema.json dev_schema.json > /dev/null; then
  echo "✓ Schema matches production"
else
  echo "✗ Schema mismatch detected"
  diff expected_schema.json dev_schema.json
fi
```

**Expected outcome**: Automated schema validation in development.

---

## Performance

### Query Speed

SQLite adapter operations are fast:

| Operation | Typical Speed | Notes |
|-----------|---------------|-------|
| Database overview | 10-100ms | Scans table list |
| Table inspection | 10-50ms | PRAGMA queries |
| Row count | 10-500ms | `COUNT(*)` query |
| Large databases (100+ tables) | 100ms-1s | Parallel table scanning |
| Very large tables (1M+ rows) | 500ms-5s | `COUNT(*)` on large tables |

### Large Database Strategies

For databases with 100+ tables or very large tables:

**Strategy 1: Skip row counts for overview**
```bash
# Faster overview (no row counts)
reveal sqlite:///large.db --format=json | jq 'del(.tables[].row_count)'
```

**Strategy 2: Inspect specific tables only**
```bash
# Don't scan entire database
reveal sqlite:///large.db/specific_table
```

**Strategy 3: Use JSON and filter**
```bash
# Get schema only, skip stats
reveal sqlite:///large.db --format=json | \
  jq '.tables[] | {name, columns: (.columns | length)}'
```

### Memory Considerations

**Current implementation**: Lightweight - only metadata loaded.

**Memory usage:**
- Database overview: ~1-5 MB (metadata only)
- Table inspection: ~100KB-1MB (schema only)
- Large databases: ~10-50 MB (100+ tables)

**No data loaded**: Only schema and statistics, never table contents.

---

## Limitations

### What SQLite Adapter CAN'T Do

**1. Query table data**

Adapter only shows schema, not data:

❌ "Show all users"
❌ "SELECT * FROM users WHERE active=1"
✅ Use `sqlite3` CLI or Python script for data queries

**2. Modify database**

Read-only mode for safety:

❌ "Create new table"
❌ "Alter table schema"
❌ "Drop index"
✅ Use `sqlite3` CLI or migrations for modifications

**3. Performance analysis**

No query performance metrics:

❌ "Which queries are slow?"
❌ "Analyze query plan"
✅ Use `EXPLAIN QUERY PLAN` in sqlite3 CLI

**4. Trigger and view definitions**

Shows triggers and views exist, but not definitions:

❌ "Show trigger SQL"
❌ "Show view definition"
✅ Use `sqlite3` CLI: `.schema trigger_name`

**5. Attached databases**

Only inspects main database:

❌ "Show attached databases"
✅ Use `PRAGMA database_list` in sqlite3 CLI

**6. Write-Ahead Log (WAL) details**

Shows WAL mode, but not WAL file details:

❌ "WAL file size"
❌ "Checkpoint info"
✅ Use `PRAGMA wal_checkpoint` in sqlite3 CLI

### Current Implementation Limitations

**Row count performance**: `COUNT(*)` queries can be slow on large tables (millions of rows). Consider skipping row counts for very large databases.

**Foreign key runtime**: Foreign keys may be disabled at runtime even if defined in schema. Check database configuration.

**Virtual tables**: Limited support for virtual table details (FTS, R-Tree).

---

## Error Messages

### Common errors and solutions:

**1. Database file not found**

```
Error: Database file not found: /path/to/app.db
```

**Cause**: File doesn't exist at specified path.
**Solution**:
- Verify file path
- Use absolute path: `sqlite:///full/path`
- Check current directory for relative paths

**2. Not a valid SQLite database**

```
Error: file is not a database
```

**Cause**: File exists but isn't a SQLite database.
**Solution**:
- Verify file type: `file app.db`
- Check file isn't corrupted
- Ensure correct file extension

**3. Database is locked**

```
Error: database is locked
```

**Cause**: Another process has write lock on database.
**Solution**:
- Close other connections
- Wait for write operations to complete
- Use read-only mode (automatic in adapter)

**4. Table not found**

```
Error: Table 'nonexistent' not found
```

**Cause**: Specified table doesn't exist.
**Solution**:
- List tables: `reveal sqlite:///app.db`
- Check table name spelling
- Case sensitivity may vary

**5. Permission denied**

```
Error: unable to open database file: Permission denied
```

**Cause**: Insufficient file permissions.
**Solution**:
- Check file permissions: `ls -l app.db`
- Ensure read access
- Check directory permissions

---

## Tips & Best Practices

### Progressive Exploration

Start broad, then narrow:

```bash
# 1. Database overview
reveal sqlite:///app.db

# 2. Identify key tables
reveal sqlite:///app.db | grep -i user

# 3. Inspect specific table
reveal sqlite:///app.db/users

# 4. Check relationships
reveal sqlite:///app.db/posts  # Look for foreign keys to users
```

### Use Relative Paths in Projects

For portability:

```bash
# ✅ GOOD: Relative path
reveal sqlite://./data/app.db

# ❌ BAD: Absolute path
reveal sqlite:///Users/yourname/project/data/app.db
```

### JSON for Scripting

Use JSON output for automation:

```bash
# Get all table names
reveal sqlite:///app.db --format=json | jq -r '.tables[].name'

# Count total rows across all tables
reveal sqlite:///app.db --format=json | \
  jq '[.tables[].row_count] | add'

# Find tables with >1000 rows
reveal sqlite:///app.db --format=json | \
  jq -r '.tables[] | select(.row_count > 1000) | .name'
```

### Document Schema Changes

Before migrations:

```bash
# Backup current schema
reveal sqlite:///app.db --format=json > schema_backup_$(date +%Y%m%d).json

# After migration, compare
diff schema_backup_20261201.json schema_backup_20261215.json
```

### Verify Foreign Key Enforcement

Check if foreign keys are enforced:

```bash
# Method 1: Check database config
reveal sqlite:///app.db | grep "Foreign Keys"

# Method 2: JSON output
reveal sqlite:///app.db --format=json | jq '.config.foreign_keys'

# If disabled, foreign key relationships may not be enforced at runtime
```

### Use Wildcards for Multiple Tables

Document multiple related tables:

```bash
# All auth-related tables
for table in users roles permissions; do
  echo "=== $table ==="
  reveal sqlite:///app.db/$table
done

# Or use grep
reveal sqlite:///app.db | grep -E "(users|roles|permissions)"
```

---

## Integration with Other Tools

### With jq (JSON Processing)

```bash
# Extract all table names
reveal sqlite:///app.db --format=json | jq -r '.tables[].name'

# Get column names for specific table
reveal sqlite:///app.db/users --format=json | \
  jq -r '.columns[].name'

# Find tables with foreign keys
reveal sqlite:///app.db --format=json | jq -r '
  .tables[] |
  select(.foreign_keys | length > 0) |
  .name'

# Generate CSV of table statistics
reveal sqlite:///app.db --format=json | \
  jq -r '.tables[] | [.name, .row_count] | @csv'
```

### With diff (Schema Comparison)

```bash
# Compare two databases
diff <(reveal sqlite:///db1.db) \
     <(reveal sqlite:///db2.db)

# JSON comparison
diff <(reveal sqlite:///db1.db --format=json | jq -S .) \
     <(reveal sqlite:///db2.db --format=json | jq -S .)

# Compare specific table
diff <(reveal sqlite:///db1.db/users) \
     <(reveal sqlite:///db2.db/users)
```

### With sqlite3 CLI (Data Queries)

```bash
# Schema with reveal, data with sqlite3
reveal sqlite:///app.db/users           # Structure
sqlite3 app.db "SELECT * FROM users LIMIT 10"  # Data

# Combined workflow
echo "=== Schema ===" && reveal sqlite:///app.db/users
echo "=== Sample Data ===" && sqlite3 app.db "SELECT * FROM users LIMIT 5"
```

### With Python (Scripting)

```python
import subprocess
import json

# Get database schema
result = subprocess.run(
    ["reveal", "sqlite:///app.db", "--format=json"],
    capture_output=True,
    text=True
)

schema = json.loads(result.stdout)

# Process schema
for table in schema["tables"]:
    print(f"{table['name']}: {table['row_count']} rows")

# Get table details
result = subprocess.run(
    ["reveal", "sqlite:///app.db/users", "--format=json"],
    capture_output=True,
    text=True
)

table_schema = json.loads(result.stdout)
columns = [col["name"] for col in table_schema["columns"]]
print(f"Columns in users: {', '.join(columns)}")
```

### With Markdown (Documentation)

```bash
# Generate markdown documentation
{
  echo "# Database Schema"
  echo ""
  echo "## Tables"
  echo ""
  for table in $(reveal sqlite:///app.db --format=json | jq -r '.tables[].name'); do
    echo "### $table"
    echo ""
    echo '```'
    reveal sqlite:///app.db/$table
    echo '```'
    echo ""
  done
} > SCHEMA.md
```

---

## Related Documentation

**Core reveal documentation:**
- [QUICK_START.md](QUICK_START.md) - Getting started with reveal
- [AGENT_HELP.md](AGENT_HELP.md) - Complete agent help

**Related adapters:**
- [JSON_ADAPTER_GUIDE.md](JSON_ADAPTER_GUIDE.md) - JSON file navigation
- [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) - Query code as AST
- MySQL adapter (help://mysql) - Similar adapter for MySQL databases

**Workflow guides:**
- [RECIPES.md](RECIPES.md) - Reveal recipes and patterns

**External resources:**
- [SQLite Official Documentation](https://www.sqlite.org/docs.html)
- [SQLite CLI Reference](https://www.sqlite.org/cli.html)
- [SQLite PRAGMA Reference](https://www.sqlite.org/pragma.html)

---

## Version History

### v1.0 (reveal 0.49.0+)

**Features:**
- ✅ Database overview (tables, indices, statistics)
- ✅ Table structure inspection (columns, types, constraints)
- ✅ Foreign key relationships
- ✅ Index information
- ✅ Row counts and statistics
- ✅ SQLite configuration (page size, journal mode, encoding)
- ✅ Read-only mode (safe for production)
- ✅ JSON output format
- ✅ Progressive disclosure (database → table)

**Supported SQLite features:**
- Tables, columns, types
- Primary keys, unique constraints
- Foreign keys (if enforced)
- Indices (excluding auto-generated)
- AUTOINCREMENT
- DEFAULT values
- NOT NULL constraints

**Known limitations:**
- No data querying (schema only)
- No write operations (read-only)
- Limited trigger/view definitions
- Row counts can be slow on large tables
- No attached database support

---

## FAQ

**Q: Can I query table data with sqlite://?**

A: No, sqlite:// only shows schema (structure). Use `sqlite3` CLI or Python for data queries.

**Q: Is it safe to use on production databases?**

A: Yes! The adapter opens databases in read-only mode automatically. No writes possible.

**Q: Why are row counts slow?**

A: SQLite requires `COUNT(*)` query for exact counts, which scans entire table. For very large tables (millions of rows), this can take seconds.

**Q: Can I modify the database schema?**

A: No, sqlite:// is read-only. Use `sqlite3` CLI or migration tools for schema changes.

**Q: What about triggers and views?**

A: The adapter shows they exist but not their definitions. Use `sqlite3` CLI: `.schema trigger_name`

**Q: Does it work with encrypted SQLite databases?**

A: No, encrypted databases (SQLCipher) require special libraries not included in Python's built-in sqlite3.

**Q: Can I inspect WAL file details?**

A: No, the adapter only shows journal mode (WAL/DELETE/etc.). Use `PRAGMA wal_checkpoint` for WAL details.

**Q: How do I check multiple databases?**

A: Run reveal on each database separately. Attached databases are not supported.

---

**End of SQLite Adapter Guide**

*This guide covers reveal v0.49.2+. For updates, see CHANGELOG.md.*
