# JSON Adapter Guide

**Version**: 1.0 (reveal 0.49.2+)
**Status**: 🟢 Stable - Production Ready
**Adapter**: `json://`

---

## Table of Contents

- [Quick Start](#quick-start)
- [Overview](#overview)
- [Features](#features)
- [Path Navigation](#path-navigation)
- [Query Parameters](#query-parameters)
- [Array Filtering](#array-filtering)
- [Operators](#operators)
- [Output Formats](#output-formats)
- [Common Workflows](#common-workflows)
- [Result Control](#result-control)
- [Performance](#performance)
- [Limitations](#limitations)
- [Error Messages](#error-messages)
- [Tips & Best Practices](#tips--best-practices)
- [Integration with Other Tools](#integration-with-other-tools)
- [Related Documentation](#related-documentation)
- [Version History](#version-history)

---

## Quick Start

The JSON adapter provides powerful JSON file navigation without requiring jq or other external tools.

**Common examples:**

```bash
# 1. View entire JSON file (pretty-printed)
reveal json://config.json

# 2. Get nested value
reveal json://package.json/name
reveal json://config.json/database/host

# 3. Array access
reveal json://data.json/users/0          # First user
reveal json://data.json/users[0:3]       # First 3 users (slice)
reveal json://data.json/users[-1]        # Last user

# 4. Understand structure (schema inference)
reveal json://config.json?schema

# 5. Flatten for grep workflow
reveal json://config.json?flatten

# 6. List keys
reveal json://package.json/dependencies?keys

# 7. Filter arrays
reveal json://data.json/users?age>25
reveal json://data.json/products?price=10..50

# 8. Sort and limit
reveal json://data.json/users?sort=-age&limit=10
```

---

## Overview

### What is the JSON Adapter?

The `json://` adapter provides **structured JSON navigation and querying** - access nested values, infer schemas, filter arrays, and flatten for grep workflows, all without external dependencies.

**Why use json:// instead of jq?**

| Task | jq | json:// |
|------|-----|---------|
| Simple path access | ✅ `jq .database.host` | ✅ `json://.../database/host` |
| External dependency | ❌ Requires jq installed | ✅ Built-in to reveal |
| Schema inference | ❌ Manual inspection | ✅ `?schema` flag |
| Flatten for grep | ❌ Complex expression | ✅ `?flatten` flag |
| Array filtering | ✅ Full power | ✅ Built-in operators |
| Consistent syntax | ❌ Different from reveal | ✅ Same URI pattern |
| Error handling | ❌ Cryptic errors | ✅ Clear error messages |

**Note**: For complex queries, jq is still more powerful. json:// is optimized for **common operations** with **zero dependencies**.

**Key capabilities:**

- 🔍 **Path navigation**: Access nested values with `/` separator
- 📊 **Schema inference**: Understand structure without reading entire file
- 📝 **Flatten mode**: Gron-style output for grep workflows
- 🔢 **Array operations**: Indexing, slicing, filtering
- 🎯 **Query filtering**: 8 operators for array filtering
- 📈 **Result control**: Sort, limit, offset for large arrays
- 🤖 **AI-friendly**: JSON schema for agent integration

---

## Features

### 1. **Direct Value Access**

Get any value from JSON structure:

```bash
# Top-level key
reveal json://package.json/name

# Nested object
reveal json://config.json/database/host
reveal json://config.json/database/port

# Deep nesting
reveal json://data.json/api/endpoints/users/url
```

**Output**: Raw value (no quotes for strings, pretty-printed for objects/arrays)

### 2. **Array Access and Slicing**

Python-style array operations:

```bash
# Index access (0-based)
reveal json://data.json/users/0          # First element
reveal json://data.json/users/1          # Second element

# Negative indices (from end)
reveal json://data.json/users[-1]        # Last element
reveal json://data.json/users[-2]        # Second to last

# Slicing [start:end] (end exclusive)
reveal json://data.json/users[0:3]       # First 3 elements (indices 0,1,2)
reveal json://data.json/users[5:10]      # Elements 5-9
reveal json://data.json/users[10:]       # From index 10 to end
reveal json://data.json/users[:5]        # First 5 elements
```

**Slice behavior**: Same as Python - `[start:end]` where `end` is exclusive.

### 3. **Schema Inference**

Understand JSON structure without reading entire file:

```bash
# Schema of entire file
reveal json://config.json?schema

# Schema of nested path
reveal json://data.json/users?schema
```

**Example output:**
```
{
  "users": Array[Object] (150 items)
    {
      "id": Integer
      "name": String
      "email": String
      "age": Integer
      "active": Boolean
      "metadata": Object
        {
          "created": String (ISO date)
          "updated": String (ISO date)
        }
    }
}
```

**Use cases:**
- Explore unknown JSON files
- Validate data structure
- Generate documentation
- Understand API responses

### 4. **Flatten Mode (Gron-Style)**

Convert JSON to grep-able lines:

```bash
# Flatten entire file
reveal json://config.json?flatten

# Also accepts ?gron (named after github.com/tomnomnom/gron)
reveal json://config.json?gron
```

**Example output:**
```
config = {}
config.database = {}
config.database.host = "localhost"
config.database.port = 5432
config.database.name = "mydb"
config.api = {}
config.api.base_url = "https://api.example.com"
config.api.timeout = 30
```

**Workflow with grep:**
```bash
# Find all database-related config
reveal json://config.json?flatten | grep -i database

# Find all URLs
reveal json://config.json?flatten | grep url

# Find specific value
reveal json://config.json?flatten | grep "5432"
```

### 5. **Type Introspection**

Get type information at any path:

```bash
# Type of entire file
reveal json://data.json?type
# Output: Object

# Type of nested path
reveal json://data.json/users?type
# Output: Array[Object] (150 items)

# Type of value
reveal json://config.json/database/port?type
# Output: Integer
```

### 6. **Key Listing**

List object keys or array indices:

```bash
# List object keys
reveal json://package.json?keys
# Output: name, version, description, dependencies, devDependencies, scripts

# List nested keys
reveal json://package.json/dependencies?keys
# Output: express, lodash, axios, ...

# For arrays, shows length
reveal json://data.json/users?keys
# Output: 150 items
```

### 7. **Length Information**

Get counts and lengths:

```bash
# Array length
reveal json://data.json/users?length
# Output: 150

# Object key count
reveal json://package.json/dependencies?length
# Output: 45

# String length
reveal json://data.json/users/0/name?length
# Output: 12
```

### 8. **Array Filtering**

Filter arrays of objects using query parameters:

```bash
# Exact match
reveal json://data.json/users?status=active

# Numeric comparisons
reveal json://data.json/users?age>25
reveal json://data.json/users?age>=18
reveal json://data.json/users?score<50

# Range queries
reveal json://data.json/products?price=10..50
reveal json://data.json/users?age=18..65

# Regex matching
reveal json://data.json/users?name~=^John
reveal json://data.json/products?category~=electronics

# Negation
reveal json://data.json/users?status!=inactive
reveal json://data.json/products?stock!=0

# Combined filters (AND logic)
reveal json://data.json/users?age>25&status=active
reveal json://data.json/products?price<100&stock>0
```

---

## Path Navigation

### Path Syntax

Paths use `/` separator (like URLs):

| Syntax | Meaning | Example |
|--------|---------|---------|
| `/key` | Object key | `/database/host` |
| `/0` | Array index | `/users/0` |
| `/key/subkey` | Nested path | `/api/endpoints/users` |
| `[0:3]` | Array slice | `/users[0:3]` |
| `[-1]` | Negative index | `/users[-1]` |

### Path Examples

**Object navigation:**
```bash
# Single level
reveal json://config.json/database

# Multiple levels
reveal json://config.json/database/host
reveal json://config.json/api/endpoints/users/url
```

**Array navigation:**
```bash
# Index
reveal json://data.json/users/0
reveal json://data.json/users/42

# Negative index
reveal json://data.json/users/-1        # Last
reveal json://data.json/users/-2        # Second to last

# Slice
reveal json://data.json/users[0:10]     # First 10
reveal json://data.json/users[10:20]    # Next 10
reveal json://data.json/users[100:]     # From 100 to end
reveal json://data.json/users[:5]       # First 5
```

**Mixed navigation:**
```bash
# Object → Array → Object
reveal json://data.json/users/0/name
reveal json://data.json/teams/3/members/0/email

# Array slice → Object key
reveal json://data.json/users[0:10]/name  # NOT SUPPORTED
# Instead: filter and extract
reveal json://data.json/users[0:10] --format=json | jq '.[].name'
```

### Dot Notation in Field Names

For filtering, field names support dot notation:

```bash
# Filter by nested field
reveal json://data.json/users?metadata.verified=true
reveal json://data.json/orders?customer.tier=premium
```

---

## Query Parameters

Complete reference of all query modes:

### Introspection Modes

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `schema` | flag | Show type structure of data | `?schema` |
| `flatten` | flag | Flatten to grep-able lines (gron-style) | `?flatten` |
| `gron` | flag | Alias for `flatten` | `?gron` |
| `type` | flag | Show type at current path | `?type` |
| `keys` | flag | List keys (objects) or length (arrays) | `?keys` |
| `length` | flag | Get array/string length or object key count | `?length` |

**Note**: These are **mutually exclusive** - use one at a time.

### Filtering Parameters

Used with arrays of objects:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `field=value` | filter | Exact match (case-insensitive for strings) | `status=active` |
| `field>value` | filter | Greater than (numeric) | `age>25` |
| `field<value` | filter | Less than (numeric) | `price<100` |
| `field>=value` | filter | Greater than or equal | `score>=80` |
| `field<=value` | filter | Less than or equal | `age<=65` |
| `field!=value` | filter | Not equal | `status!=inactive` |
| `field~=pattern` | filter | Regex match | `name~=^John` |
| `field=min..max` | filter | Range (inclusive) | `price=10..50` |

**Field names** can use dot notation: `metadata.verified=true`

### Result Control Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `sort=field` | control | Sort by field (ascending) | `sort=age` |
| `sort=-field` | control | Sort by field (descending) | `sort=-age` |
| `limit=N` | control | Limit results to N items | `limit=10` |
| `offset=M` | control | Skip first M items | `offset=20` |

---

## Array Filtering

### Filter Operators

**Comparison operators** (numeric values):

```bash
# Greater than
reveal json://data.json/users?age>25

# Less than
reveal json://data.json/products?price<100

# Greater than or equal
reveal json://data.json/scores?value>=80

# Less than or equal
reveal json://data.json/users?age<=65
```

**Equality operators** (any value type):

```bash
# Exact match (case-insensitive for strings)
reveal json://data.json/users?status=active
reveal json://data.json/products?category=electronics

# Not equal
reveal json://data.json/users?status!=inactive
reveal json://data.json/products?stock!=0
```

**Pattern operators** (string values):

```bash
# Regex match
reveal json://data.json/users?name~=^John       # Starts with "John"
reveal json://data.json/users?email~=@gmail     # Contains "@gmail"
reveal json://data.json/products?sku~=^ABC      # SKU starts with "ABC"
```

**Range operator** (numeric or string):

```bash
# Numeric range
reveal json://data.json/products?price=10..50
reveal json://data.json/users?age=18..65

# String range (alphabetical)
reveal json://data.json/users?name=A..M        # Names starting A-M
```

### Combined Filters

Multiple filters use AND logic:

```bash
# Age AND status
reveal json://data.json/users?age>25&status=active

# Price AND stock
reveal json://data.json/products?price<100&stock>0

# Three filters
reveal json://data.json/users?age>18&age<65&status=active
```

### Nested Field Filtering

Use dot notation for nested fields:

```bash
# Filter by nested field
reveal json://data.json/users?metadata.verified=true
reveal json://data.json/orders?customer.tier=premium
reveal json://data.json/products?details.weight>10
```

---

## Operators

### Filter Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Equal to (exact match) | `status=active` |
| `>` | Greater than | `age>25` |
| `<` | Less than | `price<100` |
| `>=` | Greater than or equal | `score>=80` |
| `<=` | Less than or equal | `age<=65` |
| `!=` | Not equal to | `status!=inactive` |
| `~=` | Regex match | `name~=^John` |
| `..` | Range (inclusive) | `price=10..50` |

### Logic Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `&` | AND - all filters must match | `age>25&status=active` |

**Note**: OR logic not currently supported. Use multiple queries or jq for OR operations.

---

## Output Formats

The JSON adapter supports two output formats:

### 1. Text Format (Default)

Human-readable, pretty-printed JSON:

```bash
reveal json://config.json
```

**Output:**
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "mydb"
  },
  "api": {
    "base_url": "https://api.example.com",
    "timeout": 30
  }
}
```

**Features:**
- Syntax highlighting (if terminal supports colors)
- 2-space indentation
- Sorted keys (for consistent diffing)

### 2. JSON Format

Machine-readable with metadata:

```bash
reveal json://config.json/database --format=json
```

**Output structure:**
```json
{
  "contract_version": "1.1",
  "type": "json_value",
  "source": "config.json",
  "source_type": "file",
  "file": "/absolute/path/config.json",
  "path": "/database",
  "value_type": "Object",
  "value": {
    "host": "localhost",
    "port": 5432,
    "name": "mydb"
  },
  "meta": {
    "parse_mode": "json_standard",
    "confidence": 1.0
  }
}
```

**Output types:**

- `json_value` - Raw value at path
- `json_schema` - Schema inference result (`?schema`)
- `json_flatten` - Flattened output (`?flatten`)
- `json_keys` - Key listing (`?keys`)

---

## Common Workflows

### Workflow 1: Explore Unknown JSON Structure

**Scenario**: Large JSON file, need to understand contents without reading everything.

```bash
# Step 1: Get high-level schema
reveal json://data.json?schema

# Step 2: List top-level keys
reveal json://data.json?keys

# Step 3: Drill into nested structure
reveal json://data.json/users?schema

# Step 4: Sample first element
reveal json://data.json/users/0

# Step 5: Get type of specific field
reveal json://data.json/users/0/metadata?type
```

**Expected outcome**: Complete understanding of JSON structure without reading entire file.

### Workflow 2: Search JSON Content

**Scenario**: Find specific values in a large JSON configuration file.

```bash
# Step 1: Flatten entire file
reveal json://config.json?flatten > flat_config.txt

# Step 2: Search for database config
reveal json://config.json?flatten | grep -i database

# Step 3: Find all URLs
reveal json://config.json?flatten | grep url

# Step 4: Find specific port number
reveal json://config.json?flatten | grep "5432"

# Step 5: Navigate directly to found path
reveal json://config.json/database/host
```

**Expected outcome**: Located configuration values without manual JSON navigation.

### Workflow 3: Extract API Response Data

**Scenario**: Parse API response and extract specific records.

```bash
# Step 1: Save API response
curl https://api.example.com/users > users.json

# Step 2: Understand structure
reveal json://users.json?schema

# Step 3: Filter active users
reveal json://users.json/data/users?status=active

# Step 4: Sort by age descending
reveal json://users.json/data/users?status=active&sort=-age

# Step 5: Get top 10
reveal json://users.json/data/users?status=active&sort=-age&limit=10

# Step 6: Export to CSV with jq
reveal json://users.json/data/users?status=active --format=json | \
  jq -r '.value[] | [.id, .name, .email, .age] | @csv'
```

**Expected outcome**: Filtered, sorted data ready for analysis.

### Workflow 4: Compare Configuration Files

**Scenario**: Compare two JSON config files to find differences.

```bash
# Step 1: Flatten both files
reveal json://config.prod.json?flatten > prod_flat.txt
reveal json://config.dev.json?flatten > dev_flat.txt

# Step 2: Diff flattened output
diff prod_flat.txt dev_flat.txt

# Or use reveal directly
diff <(reveal json://config.prod.json?flatten) \
     <(reveal json://config.dev.json?flatten)

# Step 3: Navigate to specific difference
reveal json://config.prod.json/database/host
reveal json://config.dev.json/database/host
```

**Expected outcome**: Clear diff of configuration differences.

### Workflow 5: Validate API Contract

**Scenario**: Ensure API response matches expected schema.

```bash
# Step 1: Get response schema
reveal json://response.json?schema > actual_schema.txt

# Step 2: Compare with expected schema
# (Manual inspection or diff against documented schema)

# Step 3: Check required fields exist
reveal json://response.json/data/users/0?keys

# Step 4: Validate field types
reveal json://response.json/data/users/0/id?type      # Should be Integer
reveal json://response.json/data/users/0/email?type   # Should be String

# Step 5: Check array lengths
reveal json://response.json/data/users?length
```

**Expected outcome**: Verified API contract compliance.

### Workflow 6: Generate Documentation from JSON Schema

**Scenario**: Document JSON API structure for team.

```bash
# Step 1: Generate schema
reveal json://api_response.json?schema > API_SCHEMA.md

# Step 2: List all endpoints
reveal json://swagger.json/paths?keys

# Step 3: Document each endpoint
for endpoint in $(reveal json://swagger.json/paths?keys); do
  echo "## $endpoint"
  reveal json://swagger.json/paths/$endpoint?schema
  echo ""
done > API_DOCS.md
```

**Expected outcome**: Auto-generated API documentation.

---

## Result Control

**NEW in v0.49.0**: Result control parameters for array queries.

### Sort Results

Sort arrays by any field:

```bash
# Sort by age (ascending)
reveal json://data.json/users?sort=age

# Sort by age (descending - oldest first)
reveal json://data.json/users?sort=-age

# Sort by name (alphabetical)
reveal json://data.json/users?sort=name

# Sort by nested field
reveal json://data.json/orders?sort=customer.name
```

**Note**: Sorting works on arrays of objects. The field must exist in all objects.

### Limit Results

Restrict output to first N items:

```bash
# Top 10 results
reveal json://data.json/users?limit=10

# Top 5 oldest users
reveal json://data.json/users?sort=-age&limit=5

# Top 20 cheapest products
reveal json://data.json/products?sort=price&limit=20
```

### Offset Results

Skip first N items (pagination):

```bash
# Skip first 10 items
reveal json://data.json/users?offset=10

# Pagination: items 11-20
reveal json://data.json/users?offset=10&limit=10

# Next page: items 21-30
reveal json://data.json/users?offset=20&limit=10
```

### Combined Result Control

All three can be combined:

```bash
# Top 10 oldest active users
reveal json://data.json/users?status=active&sort=-age&limit=10

# Products paginated, cheapest first
reveal json://data.json/products?sort=price&limit=20&offset=40

# Complex query: active users over 25, sorted by name, page 2
reveal json://data.json/users?status=active&age>25&sort=name&offset=10&limit=10
```

---

## Performance

### Query Speed

JSON operations are generally fast:

| Operation | Typical Speed | Notes |
|-----------|---------------|-------|
| Direct path access | <10ms | Immediate navigation |
| Schema inference | 10-100ms | Scans entire structure |
| Flatten mode | 50-500ms | Converts all paths |
| Array filtering | 10-100ms | Linear scan of array |
| Large files (>10MB) | 100ms-2s | Depends on operation |

### Large File Strategies

For JSON files >10MB:

**Strategy 1: Use direct paths**
```bash
# ❌ Slow: load and display entire file
reveal json://large_data.json

# ✅ Fast: direct path access
reveal json://large_data.json/users/0
```

**Strategy 2: Use slicing**
```bash
# ❌ Slow: entire array (10,000 items)
reveal json://large_data.json/users

# ✅ Fast: just first 10 items
reveal json://large_data.json/users[0:10]
```

**Strategy 3: Filter at query time**
```bash
# ✅ Fast: filter during load
reveal json://large_data.json/users?status=active&limit=100

# ❌ Slower: load all then filter with jq
reveal json://large_data.json/users --format=json | jq '.value[] | select(.status == "active") | .[0:100]'
```

**Strategy 4: Use schema first**
```bash
# Understand structure before deep dive
reveal json://large_data.json?schema
reveal json://large_data.json/users?schema
# Then: targeted queries
reveal json://large_data.json/users[0:100]
```

### Memory Considerations

**Current implementation**: Entire JSON file loaded into memory.

**Memory usage**:
- Small files (<1MB): Negligible
- Medium files (1-10MB): ~2-5x file size
- Large files (>10MB): Consider streaming tools (jq, jless)

**When to use alternatives**:
- Files >50MB: Consider `jq` (streaming parser)
- Files >100MB: Consider `jless` (interactive JSON viewer)
- Extremely large files: Consider specialized tools (BigQuery, DuckDB)

---

## Limitations

### What JSON Adapter CAN'T Do

**1. Modify JSON files**

JSON adapter is read-only:

❌ "Update value in JSON file"
❌ "Delete key from JSON"
✅ Use `jq` with `-w` flag or Python for modifications

**2. Validate against JSON Schema**

No schema validation:

❌ "Validate JSON against schema.json"
✅ Use `ajv` or `jsonschema` CLI tools

**3. Pretty-print/minify JSON files**

Use dedicated formatters:

❌ "Minify this JSON file"
✅ Use `jq -c` for minifying or `jq .` for pretty-printing

**4. JSON5 or JSONC support**

Only standard JSON:

❌ Comments in JSON
❌ Trailing commas
❌ Unquoted keys
✅ Only RFC 8259 JSON

**5. Stream processing**

Entire file loaded into memory:

❌ Process 1GB JSON file
✅ Use `jq --stream` for large files

**6. Cross-file queries**

No multi-file operations:

❌ "Find users in both file1.json and file2.json"
✅ Use shell scripting with multiple reveal calls

### Current Implementation Limitations

**OR logic**: Not supported for filtering. Use multiple queries or jq.

**Complex queries**: For advanced queries (nested filters, aggregations), use `jq`.

**JSONPath expressions**: Use simple paths only. For JSONPath spec, use dedicated tools.

---

## Error Messages

### Common errors and solutions:

**1. Path not found**

```
Error: Key 'nonexistent' not found at path /database
```

**Cause**: Specified key doesn't exist in JSON.
**Solution**:
- Check key spelling
- Use `?keys` to list available keys
- Use `?schema` to understand structure

**2. Invalid array index**

```
Error: Array index 999 out of range (length: 10)
```

**Cause**: Array index beyond array length.
**Solution**:
- Use `?length` to check array size
- Use negative indices for end access: `[-1]`
- Use slicing: `[0:10]`

**3. Type mismatch**

```
Error: Cannot index into Integer (expected Array or Object)
```

**Cause**: Tried to navigate into primitive value.
**Solution**:
- Use `?type` to check value type
- Stop path at correct level

**4. Invalid JSON syntax**

```
Error: JSON parsing failed: Expecting ',' delimiter at line 42
```

**Cause**: Malformed JSON file.
**Solution**:
- Validate JSON with `jq .` or online validator
- Check for trailing commas, missing quotes
- Ensure proper encoding (UTF-8)

**5. Filter field not found**

```
Warning: Filter field 'nonexistent' not found in 15 objects
```

**Cause**: Filter field doesn't exist in objects.
**Solution**:
- Check field name spelling
- Use `?schema` to see available fields
- Use dot notation for nested fields: `metadata.verified`

---

## Tips & Best Practices

### Progressive Exploration

Start broad, then narrow:

```bash
# 1. Understand structure
reveal json://data.json?schema

# 2. List top-level keys
reveal json://data.json?keys

# 3. Explore specific section
reveal json://data.json/users?schema

# 4. Sample first element
reveal json://data.json/users/0

# 5. Filter and extract
reveal json://data.json/users?status=active&sort=-age&limit=10
```

### When to Use Schema

**Use `?schema` when:**
- Exploring unfamiliar JSON
- Documenting API responses
- Validating data structure
- Understanding nested complexity

**Skip `?schema` when:**
- You know the structure
- File is very large (>10MB)
- You only need one value

### Flatten for Search

**Flatten workflow:**

```bash
# 1. Flatten entire file
reveal json://config.json?flatten > flat.txt

# 2. Search with grep
grep -i "database" flat.txt

# 3. Find all database config
grep "config.database" flat.txt

# 4. Navigate directly to found path
reveal json://config.json/database/host
```

**When to flatten:**
- Searching across entire JSON
- Don't know exact path to value
- Need to see all paths with specific substring
- Creating searchable index

### Quote URIs Consistently

**Always quote URIs** to prevent shell interpretation:

```bash
# ✅ GOOD: Quoted
reveal 'json://data.json/users?age>25'

# ❌ BAD: Unquoted (shell redirects > to file)
reveal json://data.json/users?age>25

# ✅ GOOD: Quoted with regex
reveal 'json://data.json/users?name~=^John'

# ❌ BAD: Unquoted (shell interprets ~)
reveal json://data.json/users?name~=^John
```

### Prefer Direct Paths Over Filtering

**When you know the path:**

```bash
# ❌ Slow: filter then extract
reveal json://data.json/users?id=42 --format=json | jq '.value[0]'

# ✅ Fast: direct array index (if you know it)
reveal json://data.json/users/5
```

**When you don't know the path:**

```bash
# ✅ Filter to find it
reveal json://data.json/users?id=42
```

### Use Result Control for Large Arrays

**Don't load entire array:**

```bash
# ❌ Bad: load all 10,000 users
reveal json://data.json/users

# ✅ Good: limit to 100
reveal json://data.json/users?limit=100

# ✅ Good: slice syntax
reveal json://data.json/users[0:100]
```

### Combine with jq for Advanced Queries

**json:// for navigation, jq for processing:**

```bash
# Extract array, then process with jq
reveal json://data.json/users --format=json | \
  jq '.value[] | select(.age > 25 and .status == "active") | .email'

# Get value, then transform with jq
reveal json://config.json/endpoints --format=json | \
  jq -r '.value | to_entries[] | "\(.key): \(.value.url)"'
```

---

## Integration with Other Tools

### With jq (Advanced Queries)

```bash
# Extract users, then complex jq query
reveal json://data.json/users --format=json | \
  jq '.value | group_by(.department) |
      map({department: .[0].department, count: length})'

# Nested filtering with jq
reveal json://data.json/orders --format=json | \
  jq '.value[] | select(.total > 100) |
      .items[] | select(.quantity > 5)'

# Generate CSV with jq
reveal json://data.json/users?status=active --format=json | \
  jq -r '.value[] | [.id, .name, .email, .age] | @csv'
```

### With grep (Search Workflow)

```bash
# Find all database config
reveal json://config.json?flatten | grep -i database

# Find specific values
reveal json://config.json?flatten | grep "localhost"

# Case-insensitive search
reveal json://config.json?flatten | grep -i "api"

# Count occurrences
reveal json://config.json?flatten | grep -c "endpoint"
```

### With diff (Configuration Comparison)

```bash
# Compare two JSON configs
diff <(reveal json://prod.json?flatten) \
     <(reveal json://dev.json?flatten)

# Colorized diff
diff -u <(reveal json://prod.json?flatten) \
        <(reveal json://dev.json?flatten) | colordiff

# Just show differences
diff --suppress-common-lines \
     <(reveal json://prod.json?flatten) \
     <(reveal json://dev.json?flatten)
```

### With curl (API Workflow)

```bash
# Fetch API, explore structure
curl -s https://api.example.com/users | \
  reveal json://- ?schema  # stdin support coming soon

# For now: save then explore
curl -s https://api.example.com/users > response.json
reveal json://response.json?schema

# Filter API response
curl -s https://api.example.com/users > users.json
reveal json://users.json/data/users?status=active
```

### With Python (Scripting)

```python
import subprocess
import json

# Get JSON value
result = subprocess.run(
    ["reveal", "json://data.json/users?status=active", "--format=json"],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
users = data["value"]

# Process in Python
for user in users:
    print(f"{user['name']}: {user['email']}")
```

### With shell loops (Batch Processing)

```bash
# Process multiple JSON files
for file in *.json; do
  echo "=== $file ==="
  reveal json://$file?schema
done

# Extract specific value from multiple files
for file in config/*.json; do
  host=$(reveal json://$file/database/host)
  echo "$file: $host"
done
```

---

## Related Documentation

**Core reveal documentation:**
- [QUICK_START.md](QUICK_START.md) - Getting started with reveal
- [QUERY_SYNTAX_GUIDE.md](QUERY_SYNTAX_GUIDE.md) - Query parameter reference
- [AGENT_HELP.md](AGENT_HELP.md) - Complete agent help

**Related adapters:**
- [AST_ADAPTER_GUIDE.md](AST_ADAPTER_GUIDE.md) - Query code as AST
- [XLSX_ADAPTER_GUIDE.md](XLSX_ADAPTER_GUIDE.md) - Excel/spreadsheet navigation

**Workflow guides:**
- [RECIPES.md](RECIPES.md) - Reveal recipes and patterns
- [FIELD_SELECTION_GUIDE.md](FIELD_SELECTION_GUIDE.md) - Field selection patterns

**External tools:**
- [jq](https://stedolan.github.io/jq/) - Powerful JSON processor
- [gron](https://github.com/tomnomnom/gron) - Flatten JSON for grep
- [jless](https://jless.io/) - Interactive JSON viewer

---

## Version History

### v1.0 (reveal 0.49.0+)

**Features:**
- ✅ Path navigation with `/` separator
- ✅ Array indexing and slicing (Python-style)
- ✅ Schema inference (`?schema`)
- ✅ Flatten mode (`?flatten` / `?gron`)
- ✅ Type introspection (`?type`)
- ✅ Key listing (`?keys`)
- ✅ Length information (`?length`)
- ✅ Array filtering (8 operators)
- ✅ Result control (sort, limit, offset)
- ✅ Nested field filtering (dot notation)

**Operators supported:**
- `=`, `>`, `<`, `>=`, `<=`, `!=`, `~=`, `..`

**Known limitations:**
- Entire file loaded into memory (no streaming)
- OR logic not supported for filtering
- JSON5/JSONC not supported
- Read-only (no modifications)

---

## FAQ

**Q: What's the difference between `?flatten` and `?gron`?**

A: They're identical. `?gron` is an alias named after the popular [gron tool](https://github.com/tomnomnom/gron).

**Q: Can I modify JSON files with json://?**

A: No, json:// is read-only. Use `jq` with write mode or Python for modifications.

**Q: Why not just use jq?**

A: json:// is built-in (no external dependency), uses consistent reveal URI syntax, and has better error messages for common operations. For complex queries, jq is still more powerful.

**Q: How do I handle large JSON files (>50MB)?**

A: Use direct paths or slicing to avoid loading entire file. For very large files, consider streaming tools like `jq --stream`.

**Q: Can I use JSONPath expressions?**

A: No, json:// uses simple slash-based paths. For JSONPath spec, use dedicated tools like `jp` or `jq`.

**Q: How do I do OR logic in filters?**

A: Not currently supported. Use multiple reveal calls or pipe to jq:
```bash
reveal json://data.json/users --format=json | \
  jq '.value[] | select(.age > 25 or .status == "active")'
```

**Q: Can I read from stdin?**

A: Not yet, but planned for future releases. For now: `cat file.json > /tmp/temp.json && reveal json:///tmp/temp.json`

---

**End of JSON Adapter Guide**

*This guide covers reveal v0.49.2+. For updates, see CHANGELOG.md.*
