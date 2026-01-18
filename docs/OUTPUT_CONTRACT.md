# Output Contract Specification v1.0

**Version**: 1.0.0
**Status**: Draft
**Date**: 2026-01-17
**Stability**: Beta 🟡

---

## Purpose

This document defines the **Output Contract** for all Reveal adapters and analyzers. It establishes:
- Required fields that MUST be present in all outputs
- Optional recommended fields for common patterns
- Versioning strategy for backwards compatibility
- Validation rules for compliance

**Why this matters:**
- **AI agents** need stable, predictable JSON schemas
- **Contributors** need clear contracts for new adapters
- **Users** can depend on consistent output structure
- **Tool builders** can parse Reveal output reliably

---

## Contract v1.0 Schema

### Required Fields (4)

Every adapter/analyzer output MUST include these fields:

```python
{
    'contract_version': '1.0',     # String: Contract version (semver)
    'type': str,                   # String: Output type (snake_case)
    'source': str,                 # String: Data source identifier
    'source_type': str,            # String: Source category
}
```

#### Field Definitions

**`contract_version`** (required)
- **Type**: String (semantic version)
- **Format**: `"MAJOR.MINOR"` (e.g., `"1.0"`, `"2.1"`)
- **Purpose**: Identifies which contract version the output conforms to
- **Example**: `"1.0"`

**`type`** (required)
- **Type**: String
- **Format**: `snake_case` (lowercase with underscores)
- **Purpose**: Identifies the output schema variant
- **Examples**: `"ast_query"`, `"mysql_server"`, `"environment"`, `"python_structure"`
- **Rules**:
  - Must start with lowercase letter
  - Only lowercase letters, numbers, underscores
  - No leading/trailing underscores
  - Regex: `^[a-z][a-z0-9_]*$`

**`source`** (required)
- **Type**: String
- **Purpose**: Identifies where the data came from
- **Examples**:
  - File: `"src/main.py"`
  - Directory: `"src/"`
  - Database: `"localhost:3306/mydb"`
  - Runtime: `"env://"`
  - URL: `"https://api.example.com"`

**`source_type`** (required)
- **Type**: String (enum)
- **Values**: `"file"` | `"directory"` | `"database"` | `"runtime"` | `"network"`
- **Purpose**: Categorizes the source for filtering/processing
- **Examples**:
  - `"file"` - Single file path
  - `"directory"` - Directory path
  - `"database"` - Database connection
  - `"runtime"` - Runtime/environment state
  - `"network"` - Remote resource

---

### Recommended Optional Fields (5)

These fields are OPTIONAL but recommended for common patterns:

**`metadata`** (optional, dict)
- **Purpose**: Generic counts, timestamps, metrics
- **Examples**:
  ```python
  'metadata': {
      'total_files': 42,
      'total_results': 156,
      'timestamp': '2026-01-17T14:30:00Z',
      'duration_ms': 234
  }
  ```

**`query`** (optional, dict)
- **Purpose**: Applied filters or search parameters
- **Examples**:
  ```python
  'query': {
      'complexity': {'op': '>', 'value': 10},
      'language': 'python'
  }
  ```

**`next_steps`** (optional, list of strings)
- **Purpose**: Progressive disclosure - what to explore next
- **Examples**:
  ```python
  'next_steps': [
      'reveal ast://src/main.py:MainClass',
      'reveal stats://src/ --hotspots'
  ]
  ```

**`status`** (optional, dict)
- **Purpose**: Health/state assessment
- **Examples**:
  ```python
  'status': {
      'health': 'healthy',  # 'healthy' | 'warning' | 'error'
      'warnings': ['Table has no primary key'],
      'errors': []
  }
  ```

**`issues`** (optional, list of dicts)
- **Purpose**: Problems/warnings found during analysis
- **Examples**:
  ```python
  'issues': [
      {
          'code': 'F401',
          'message': 'Unused import',
          'file': 'src/main.py',
          'line': 42
      }
  ]
  ```

---

### Adapter-Specific Fields

Adapters MAY include additional fields beyond the contract. These fields:
- MUST NOT conflict with reserved field names
- SHOULD be documented in adapter help (`reveal help://<adapter>`)
- SHOULD follow naming conventions (snake_case for dicts, lowercase for simple types)

**Example**: MySQL adapter with custom fields
```python
{
    'contract_version': '1.0',
    'type': 'mysql_server',
    'source': 'localhost:3306',
    'source_type': 'database',
    'metadata': {
        'total_tables': 45,
        'total_databases': 3
    },

    # MySQL-specific fields (not in contract)
    'connection_health': {...},
    'innodb_health': {...},
    'replication': {...},
    'tables': [...]
}
```

---

## Reserved Field Names

The following field names are reserved and MUST NOT be used for adapter-specific data:

- `contract_version`
- `type`
- `source`
- `source_type`
- `metadata`
- `query`
- `next_steps`
- `status`
- `issues`
- `error` (use `status.errors` instead)
- `version` (use `contract_version` instead)

---

## Naming Conventions

### Type Field Values

**Format**: `snake_case` (lowercase with underscores)

```python
# ✅ Correct
"ast_query"
"mysql_server"
"environment"
"python_structure"

# ❌ Incorrect
"ast-query"        # No hyphens
"AstQuery"         # No camelCase
"AST_QUERY"        # No uppercase
```

### Line Number Fields

For elements with source locations, use:
- `line_start` (int) - First line (1-indexed)
- `line_end` (int) - Last line (1-indexed, inclusive)

```python
# ✅ Correct
{
    'name': 'my_function',
    'line_start': 42,
    'line_end': 56
}

# ❌ Incorrect
{
    'name': 'my_function',
    'line': 42,         # Ambiguous
    'end': 56           # Not namespaced
}
```

---

## Validation Rules

### V016: Output Contract Compliance

Adapters MUST comply with the Output Contract specification.

**Checks**:
1. ✅ Required fields present (`contract_version`, `type`, `source`, `source_type`)
2. ✅ Type field uses snake_case format
3. ✅ Line fields use `line_start`/`line_end` (not `line`)
4. ✅ No conflicts with reserved field names

**Command**:
```bash
reveal --check reveal/adapters/myadapter.py
```

**Implementation**: See `reveal/rules/validation/V016.py`

---

## Versioning Strategy

### Contract Version Evolution

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Add optional field | Patch (1.0 → 1.1) | Add `metadata.timestamp` |
| Change optional field | Minor (1.0 → 1.5) | Rename recommended field |
| Change required field | Major (1.0 → 2.0) | Rename `source` to `origin` |
| Remove required field | Major (1.0 → 2.0) | Remove `type` field |

### Backwards Compatibility

#### Phase 1: Additive (v1.0 - Current)
- **Add** contract fields to all adapters
- **Keep** legacy fields for compatibility
- **Emit** deprecation warnings via V016

Example output (transitional):
```python
{
    'contract_version': '1.0',
    'type': 'ast_query',
    'source': 'src/main.py',
    'source_type': 'file',
    'path': 'src/main.py',      # DEPRECATED: Use 'source' instead
    'results': [...]
}
```

#### Phase 2: Hard Migration (v2.0 - Future)
- **Remove** deprecated fields
- **Enforce** contract compliance strictly
- **Break** compatibility with pre-v1.0 consumers

---

## Migration Checklist

For adapter/analyzer authors migrating to v1.0:

### Step 1: Add Required Fields
```python
def get_structure(self, **kwargs):
    return {
        'contract_version': '1.0',           # ← Add this
        'type': 'my_adapter_type',           # ← Add/update this
        'source': self.source_path,          # ← Add this
        'source_type': 'file',               # ← Add this
        # ... rest of output
    }
```

### Step 2: Standardize Type Naming
```python
# Before
'type': 'my-adapter'

# After
'type': 'my_adapter'
```

### Step 3: Migrate Line Fields
```python
# Before
{
    'name': 'foo',
    'line': 42,
    'line_count': 10
}

# After
{
    'name': 'foo',
    'line_start': 42,
    'line_end': 51      # 42 + 10 - 1
}
```

### Step 4: Add Validation Tests
```python
def test_output_contract_compliance(self):
    """Verify adapter output conforms to v1.0 contract."""
    adapter = MyAdapter('test.py')
    result = adapter.get_structure()

    # Required fields
    assert 'contract_version' in result
    assert 'type' in result
    assert 'source' in result
    assert 'source_type' in result

    # Type naming
    assert re.match(r'^[a-z][a-z0-9_]*$', result['type'])

    # Source type
    assert result['source_type'] in ['file', 'directory', 'database', 'runtime', 'network']
```

---

## Schema Command

Check contract compliance:

```bash
# Show contract schema
reveal schema

# Validate adapter output
reveal ast://src/main.py --validate-contract

# Check adapter implementation
reveal --check reveal/adapters/myadapter.py --select V016
```

---

## Examples

### Minimal Compliant Output

```python
{
    'contract_version': '1.0',
    'type': 'file_structure',
    'source': 'src/main.py',
    'source_type': 'file'
}
```

### Full-Featured Output

```python
{
    'contract_version': '1.0',
    'type': 'ast_query',
    'source': 'src/api/',
    'source_type': 'directory',
    'metadata': {
        'total_files': 12,
        'total_results': 47,
        'timestamp': '2026-01-17T14:30:00Z',
        'duration_ms': 123
    },
    'query': {
        'complexity': {'op': '>', 'value': 5},
        'type': 'function'
    },
    'results': [
        {
            'file': 'src/api/auth.py',
            'name': 'authenticate',
            'type': 'function',
            'line_start': 42,
            'line_end': 67,
            'complexity': 8,
            'signature': 'def authenticate(username, password)'
        }
    ],
    'next_steps': [
        'reveal ast://src/api/auth.py:authenticate',
        'reveal stats://src/api/ --hotspots'
    ],
    'status': {
        'health': 'warning',
        'warnings': ['High complexity function found'],
        'errors': []
    }
}
```

---

## Implementation Status

### Adapters

| Adapter | Status | Notes |
|---------|--------|-------|
| help:// | ✅ Compliant | v1.0 ready |
| env:// | ⚠️ In Progress | Missing `source_type` |
| ast:// | ⚠️ In Progress | Uses `ast-query` (should be `ast_query`) |
| python:// | ⚠️ In Progress | Missing `contract_version` |
| reveal:// | ⚠️ In Progress | Missing `contract_version` |
| diff:// | ⚠️ In Progress | Missing `contract_version` |
| imports:// | ⚠️ In Progress | Missing `contract_version` |
| sqlite:// | ⚠️ In Progress | Missing `contract_version` |
| mysql:// | ⚠️ In Progress | Missing `contract_version` |
| stats:// | ❌ Non-Compliant | Missing `type` field entirely |
| json:// | ⚠️ In Progress | Uses `json-value` (should be `json_value`) |
| markdown:// | ⚠️ In Progress | Missing `contract_version` |
| git:// | ⚠️ In Progress | Missing `contract_version` |

### Analyzers

| Analyzer | Status | Notes |
|----------|--------|-------|
| TreeSitter | ⚠️ In Progress | Uses `line` (should be `line_start`) |
| Python | ⚠️ In Progress | Implicit type |
| HTML | ⚠️ In Progress | Uses `line` (should be `line_start`) |
| YAML | ❌ Non-Compliant | Missing `type` field |
| Markdown | ⚠️ In Progress | Partial compliance |
| GraphQL | ⚠️ In Progress | Partial compliance |

---

## FAQ

**Q: Why 4 required fields? Isn't that too rigid?**

A: 4 fields is the minimum needed for:
- Version tracking (`contract_version`)
- Schema identification (`type`)
- Data provenance (`source`)
- Source categorization (`source_type`)

Everything else is optional, allowing flexibility.

**Q: Can I add my own fields?**

A: Yes! Add any fields you need, just avoid reserved names. Put domain-specific data at the top level, generic metadata in `metadata`.

**Q: What if my adapter doesn't have a "source"?**

A: Every adapter has a source:
- Files: path
- Databases: connection string
- Runtime: `"env://"`, `"python://runtime"`
- Network: URL

**Q: Do I need to migrate immediately?**

A: No. V016 will emit warnings but not fail builds. You have until v2.0 (12+ months) to migrate.

**Q: How do I test contract compliance?**

A: Use the validation utilities:
```python
from reveal.contracts import validate_output
validate_output(result, version='1.0')
```

Or run V016 validation:
```bash
reveal --check reveal/adapters/myadapter.py --select V016
```

---

## References

- **Analysis**: `internal-docs/research/OUTPUT_CONTRACT_ANALYSIS.md` - Research findings
- **Validation**: `reveal/rules/validation/V016.py` - Contract enforcement
- **Adapter Guide**: `docs/ADAPTER_AUTHORING.md` - Creating adapters
- **Stability**: `STABILITY.md` - Feature stability taxonomy

---

**Status**: This is a living document. Feedback welcome via GitHub issues.

**Next Steps**:
1. Implement V016 validation rule
2. Migrate 3-5 core adapters to v1.0
3. Add `reveal schema` command
4. Update adapter authoring guide
5. Release v0.38.0 with Output Contract support
