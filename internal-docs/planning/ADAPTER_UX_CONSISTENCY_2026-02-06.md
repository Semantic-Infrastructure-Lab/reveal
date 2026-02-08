# Adapter UX Consistency: Long-term Roadmap

**Date**: 2026-02-06
**Session**: neon-undertaker-0206 (TIA)
**Scope**: Consistency patterns across 16 adapters + extensibility recommendations
**Status**: Planning document (not yet implemented)

---

## Executive Summary

**Finding**: Reveal's 16 adapters demonstrate excellent progressive disclosure but inconsistent filtering, batching, and operation patterns.

**Impact**: Users switching between adapters must learn different syntaxes, reducing reveal's composability promise.

**Proposal**: Adopt a **3-tier UX model** (Resource Identity, Operations, Filters) with backward-compatible improvements over 3-6 months.

**Estimated Effort**: 40-60 hours total across 5 phases
**Risk**: Low (additive changes, backward compatible)
**Value**: High (consistency across all current and future adapters)

---

## Problem Statement

### Current State: Inconsistent Patterns

**16 Adapters Analyzed**:
- ast://, claude://, diff://, domain://, env://, git://, help://
- imports://, json://, markdown://, mysql://, python://, reveal://
- sqlite://, ssl://, stats://

**Inconsistencies Found**:

| Aspect | Problem | Example |
|--------|---------|---------|
| **Query operators** | ast:// uses `>`, `<`; json:// none; markdown:// uses `=`, `!` | Users must learn 3+ syntaxes |
| **Wildcards** | ast:// uses glob `*`; json:// none | Pattern mismatch |
| **Flags** | `--check` vs `--check-advanced` vs `--expiring-within` | Naming inconsistency |
| **Batch** | No adapter explicitly documents stdin batch | Missing composability |
| **Negation** | markdown:// has `!field`; no value negation | Limited filtering |
| **OR logic** | Only ast:// supports `type=a\|b` | No boolean queries |
| **Element syntax** | `env://VAR` vs `sqlite:///db/table` | Slash count varies |

---

## Proposed Solution: Three-Tier UX Model

### Tier 1: Resource Identity (URI)
**What resource are you inspecting?**

```bash
ssl://example.com:443           # Host + port
domain://example.com/dns        # Domain + element
ast://./src                     # Path
env://PATH                      # Element name
```

**Principle**: URIs identify resources, not operations.

---

### Tier 2: Operations (CLI Flags)
**What do you want to do with the resource?**

```bash
--check              # Validate/health check (universal)
--validate           # Cross-system validation
--format json        # Output format (universal)
--select=fields      # Field selection (universal)
--advanced           # Advanced mode (operation modifier)
```

**Principle**: Flags are verbs (check, validate, analyze). Operations don't change resource identity.

---

### Tier 3: Filters (Query Params OR Display Flags)
**How do you filter results?**

```bash
# URI query params (changes resource variant)
ast://src?lines>50&complexity>10

# Display flags (filters view)
--only-failures      # Display filter
--limit=10           # Result limiting
```

**Principle**:
- Query params = Different resource variant (different results)
- Display flags = Same resource, different view

---

## Phase 1: Universal Operation Flags (Immediate - 4 hours)

### Goal
Standardize common operations across all adapters.

### Implementation

#### Add Universal Flags Module
```python
# reveal/cli/parser.py

def _add_universal_operation_flags(parser: argparse.ArgumentParser) -> None:
    """Universal operations that work across all adapters."""
    parser.add_argument('--check', action='store_true',
                        help='Run health/validation checks')
    parser.add_argument('--advanced', action='store_true',
                        help='Enable advanced checks (requires --check)')
    parser.add_argument('--only-failures', action='store_true',
                        help='Only show failed checks (requires --check)')

def _add_universal_filter_flags(parser: argparse.ArgumentParser) -> None:
    """Universal filters for result limiting."""
    parser.add_argument('--select', type=str, metavar='FIELDS',
                        help='Select specific fields (comma-separated)')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit results to first N items')
    parser.add_argument('--offset', type=int, metavar='M',
                        help='Skip first M items (use with --limit)')
```

#### Update Adapter Support

**ssl:// and domain://**:
- Add `--advanced` parameter handling
- Document `--only-failures` works with stdin batch

**mysql://**:
- Standardize `--only-failures` (currently inconsistent)

**git://**:
- Add `--check` for repository health

**claude://**:
- Add `--check` for conversation validation

### Expected Behavior
```bash
# Universal across adapters
reveal ssl://example.com --check --advanced
reveal domain://example.com --check --advanced
reveal mysql://localhost --check --advanced
reveal git://. --check

# Field selection (token efficiency)
reveal ssl://example.com --select=domain,expiry
reveal stats://src --select=path,quality_score
```

### Files to Modify
- `reveal/cli/parser.py` - Add universal flag functions
- `reveal/adapters/*/adapter.py` - Add parameter handling
- `reveal/adapters/help_data/*.yaml` - Update documentation

### Success Criteria
- [ ] All adapters support `--check` (where validation makes sense)
- [ ] All adapters support `--advanced` modifier
- [x] All adapters support `--format` consistently ✅ (Verified 2026-02-07 - all 16 adapters via BaseRenderer)
- [ ] Documentation updated for universal flags

---

## Phase 2: Stdin Batch Processing (High Priority - 8 hours)

### Goal
Explicit stdin batch support with aggregation.

### Current State
Stdin works but isn't documented:
```bash
# This works now but undocumented:
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --stdin --check
```

### Proposed Enhancement
```bash
# Explicit batch flag
reveal --batch < uris.txt

# Works with any adapter
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --batch --check
cat paths.txt | sed 's/^/ast://' | reveal --batch --format=json

# Mixed adapters in one batch
cat mixed-uris.txt | reveal --batch --check
# mixed-uris.txt:
#   ssl://example.com
#   domain://example.com
#   mysql://localhost/db
```

### Implementation

#### 1. Add --batch Flag
```python
def _add_universal_operation_flags(parser: argparse.ArgumentParser) -> None:
    # ...existing flags...
    parser.add_argument('--batch', action='store_true',
                        help='Batch mode: read URIs from stdin, aggregate results')
```

#### 2. Routing Layer Enhancement
```python
# reveal/cli/routing.py

def handle_batch_mode(args):
    """Process batch URIs from stdin."""
    uris = sys.stdin.read().strip().split('\n')
    results = []

    for uri in uris:
        try:
            result = route_uri(uri, args)
            results.append({'uri': uri, 'status': 'success', 'data': result})
        except Exception as e:
            results.append({'uri': uri, 'status': 'error', 'error': str(e)})

    # Aggregate results
    return aggregate_batch_results(results, args)
```

#### 3. Aggregation Logic
```python
def aggregate_batch_results(results, args):
    """Aggregate batch results with summary."""
    success_count = sum(1 for r in results if r['status'] == 'success')
    failure_count = len(results) - success_count

    output = {
        'batch': True,
        'total': len(results),
        'success': success_count,
        'failures': failure_count,
        'results': results if not args.only_failures else [r for r in results if r['status'] == 'error']
    }

    return output
```

### Expected Behavior
```bash
# SSL batch check
cat domains.txt | sed 's/^/ssl:\/\//' | reveal --batch --check

# Output:
Batch Check: 100 URIs processed
✅ Success: 95
❌ Failures: 5

Failures:
  ssl://expired-domain.com: Certificate expired (3 days ago)
  ssl://invalid-cert.com: Hostname mismatch
  ...

Exit code: 5 (number of failures)
```

### Files to Modify
- `reveal/cli/parser.py` - Add `--batch` flag
- `reveal/cli/routing.py` - Add batch processing logic
- `reveal/cli/handlers.py` - Add aggregation functions
- All adapter help files - Document batch usage

### Success Criteria
- [ ] `--batch` works with all 16 adapters
- [ ] Results aggregated with summary
- [ ] Exit code = failure count
- [ ] `--only-failures` filters batch results
- [ ] Documentation includes batch examples

---

## Phase 3: Query Operator Standardization ✅ COMPLETE

**Updated**: 2026-02-08 - Session hosuki-0208 (Completed)
**Effort**: 3 hours actual vs 20 hours estimated
**Commits**: a36d6b5 (markdown fix), 3610488 (git result control)

### Goal
Unified query syntax across all adapters, including sorting and pagination.

### Current Operator Support

| Adapter | Operators | Wildcards | Boolean | Missing |
|---------|-----------|-----------|---------|---------|
| **ast://** | `>`, `<`, `>=`, `<=`, `==` | `*`, `?` (glob) | `\|` (OR only) | `!=`, `~=`, `()`, `!` |
| **json://** | None | None | None | All |
| **markdown://** | `=` | `*` (glob) | AND only | `!=`, `~=`, `\|`, `()` |
| **stats://** | `=` | None | AND only | All |
| **git://** | None | None | None | All |

### Proposed Universal Operator Set

#### Comparison Operators
```
>    Greater than           ast://src?lines>50
<    Less than              ast://src?lines<200
>=   Greater or equal       ast://src?complexity>=10
<=   Less or equal          ast://src?complexity<=5
==   Equals                 ast://src?type==function
!=   Not equals             ast://src?decorator!=property
~=   Regex match            ast://src?name~=^test_
..   Range                  stats://src?lines=50..200
```

#### Wildcards
```
*    Glob wildcard          ast://src?name=test_*
?    Single char            ast://src?name=test_?
```

#### Boolean Logic
```
&    AND (implicit)         ast://src?lines>50&complexity>10
|    OR (explicit)          ast://src?type=function|method
()   Grouping               ast://src?(lines>50|complexity>10)&decorator=cached
!    NOT prefix             markdown://docs/?!deprecated&status=active
```

#### Result Control (NEW - from agentic AI feedback)
```
sort=field       Sort ascending       ast://src?lines>50&sort=complexity
sort=-field      Sort descending      ast://src?lines>50&sort=-complexity
limit=N          Limit results        ast://src?lines>50&limit=20
offset=M         Skip first M         ast://src?lines>50&offset=10&limit=10
```

### Implementation

#### 1. Create Query Parser Library
```python
# reveal/utils/query_parser.py

class QueryParser:
    """Universal query parser for adapter filtering."""

    OPERATORS = {
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
        '!=': operator.ne,
        '~=': 're.match',  # Regex
        '..': 'range',     # Range operator
    }

    def parse(self, query_string: str) -> Dict[str, Any]:
        """Parse query string into structured filters."""
        # Parse operators, wildcards, boolean logic
        # Return AST of filter conditions
        pass

    def apply(self, items: List[Any], filters: Dict[str, Any]) -> List[Any]:
        """Apply parsed filters to items."""
        # Evaluate filter AST against items
        pass
```

#### 2. Migrate Adapters

**ast://** (add `!=`, `~=`, `()`, `!`):
```bash
# Before (works)
reveal 'ast://src?lines>50&complexity>10'

# After (also works)
reveal 'ast://src?lines>50&decorator!=property'
reveal 'ast://src?(type=function|type=method)&lines>100'
reveal 'ast://src?name~=^test_.*&!decorator=skip'
```

**stats://** (add range, comparison):
```bash
# Before
reveal stats://src?min_lines=50&max_lines=200

# After (both work)
reveal stats://src?lines=50..200
reveal stats://src?complexity>10&lines<100
```

**markdown://** (add regex, OR, negation):
```bash
# Before
reveal 'markdown://docs/?status=active&!deprecated'

# After (also works)
reveal 'markdown://docs/?status=active|draft&!deprecated'
reveal 'markdown://docs/?tags~=python.*'
```

**json://** (add filtering):
```bash
# Before (no filtering)
reveal json://config.json

# After
reveal 'json://config.json?type==object&length>5'
reveal 'json://data.json/users?age>18&status==active'
```

#### 3. Backward Compatibility
- Keep existing syntax working
- Add new operators as alternatives
- Deprecation path for conflicts (if any)

### Files to Modify
- `reveal/utils/query_parser.py` (NEW)
- `reveal/adapters/ast.py` - Use unified parser
- `reveal/adapters/stats.py` - Use unified parser
- `reveal/adapters/markdown.py` - Use unified parser
- `reveal/adapters/json_adapter.py` - Add filtering
- `reveal/adapters/git/adapter.py` - Add filtering
- All adapter help files - Document operators

### Success Criteria
- [x] All adapters use same operator syntax ✅ (2026-02-08)
- [x] Backward compatible with existing queries ✅ (2026-02-08)
- [x] Documentation includes operator reference ✅ (2026-02-08 - QUERY_SYNTAX_GUIDE.md created)
- [ ] Error messages suggest correct syntax (TODO: verify)

---

## Phase 4: Field Selection + Budget Awareness (Medium Priority - 12 hours)

**Updated**: 2026-02-06 - Added budget-aware flags (+4 hours from agentic AI feedback)

### Goal
Reduce token usage by selecting specific fields in output AND enable explicit token budget constraints for LLM loops.

### Current State
Full structure returned (100-500 lines):
```bash
reveal ssl://example.com --format=json
# Returns: ~400 lines of JSON
```

### Proposed Enhancement
```bash
# Field selection (original)
reveal ssl://example.com --select=domain,expiry,days_until_expiry --format=json
# Returns: ~10 lines of JSON (40x reduction)

# Budget constraints (NEW)
reveal ast://src --max-items=50                    # Stop after 50 results
reveal ast://src?lines>50 --max-bytes=4096         # Stay under token budget
reveal src/ --max-depth=2                          # Shallow tree only
reveal file.py --max-snippet-chars=200             # Truncate long strings
```

### Implementation

#### 1. Add --select Flag
Already proposed in Phase 1 universal flags.

#### 2. Renderer Field Filtering
```python
# reveal/display/formatting.py

def filter_fields(structure: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    """Filter structure to only include selected fields."""
    if not fields:
        return structure

    filtered = {}
    for field in fields:
        if '.' in field:  # Nested field: "certificate.expiry"
            parts = field.split('.')
            value = structure
            for part in parts:
                value = value.get(part)
                if value is None:
                    break
            if value is not None:
                set_nested(filtered, parts, value)
        else:
            if field in structure:
                filtered[field] = structure[field]

    return filtered
```

#### 3. Adapter Integration
Each adapter's renderer checks for `--select` flag:
```python
class SSLRenderer:
    def render(self, structure, args):
        if args.select:
            structure = filter_fields(structure, args.select.split(','))

        # Continue with normal rendering
        ...
```

#### 4. Budget-Aware Flags (NEW)

**Add to universal flags:**
```python
def _add_universal_filter_flags(parser: argparse.ArgumentParser) -> None:
    """Universal filters for result limiting."""
    # Field selection (already planned)
    parser.add_argument('--select', type=str, metavar='FIELDS',
                        help='Select specific fields (comma-separated)')

    # Budget constraints (NEW)
    parser.add_argument('--max-items', type=int, metavar='N',
                        help='Stop after N results')
    parser.add_argument('--max-bytes', type=int, metavar='N',
                        help='Stop after N bytes (token budget mode)')
    parser.add_argument('--max-depth', type=int, metavar='N',
                        help='Limit tree depth to N levels')
    parser.add_argument('--max-snippet-chars', type=int, metavar='N',
                        help='Truncate long strings to N characters')
```

#### 5. Truncation Metadata (NEW)

**Enhance Output Contract to expose truncation:**
```python
def apply_budget_limits(items, args):
    """Apply budget constraints and track truncation."""
    truncated = False
    total_available = len(items)

    # Apply max-items
    if args.max_items and len(items) > args.max_items:
        items = items[:args.max_items]
        truncated = True

    # Add metadata
    return {
        'items': items,
        'meta': {
            'truncated': truncated,
            'reason': 'max_items_exceeded' if truncated else None,
            'total_available': total_available,
            'returned': len(items),
            'next_cursor': f'offset={len(items)}' if truncated else None
        }
    }
```

### Expected Behavior

**SSL Certificate**:
```bash
# Full output (400 lines)
reveal ssl://example.com --format=json

# Selected fields (10 lines)
reveal ssl://example.com --select=domain,expiry,days_until_expiry --format=json
```

**Stats Analysis**:
```bash
# Full output (500 lines)
reveal stats://src --format=json

# Selected fields (50 lines)
reveal stats://src --select=path,quality_score,hotspot_score --format=json
```

**Git History**:
```bash
# Full commits (1000 lines)
reveal git://repo/file.py --format=json

# Selected fields (100 lines)
reveal git://repo/file.py --select=hash,author,date,message --format=json
```

### Files to Modify
- `reveal/display/formatting.py` - Add field filtering
- All adapter renderers - Integrate filtering
- All adapter help files - Document available fields

### Success Criteria
- [x] `--fields` works with all adapters (note: renamed from --select to avoid conflict with --check rules)
- [x] 5-10x token reduction measured (40x for SSL, 10x for AST/Stats, 7x for Git)
- [x] Works with `--format=json` (primary use case)
- [x] Nested field support with dot notation
- [x] Budget constraints implemented (`--max-items`, `--max-bytes`, `--max-depth`, `--max-snippet-chars`)
- [x] Truncation metadata in output contract
- [x] Comprehensive documentation (FIELD_SELECTION_GUIDE.md)

**Status**: ✅ COMPLETE (2026-02-08, Session: luminous-twilight-0208)

---

## Phase 5: Element Discovery Hints (Low Priority - 4 hours)

### Goal
Show available elements in overview for better discoverability.

### Current State
Users don't know what elements exist:
```bash
reveal ssl://example.com/???  # What elements are available?
```

### Proposed Enhancement
```bash
reveal ssl://example.com

# Output includes:
SSL Certificate: example.com
Common Name: example.com
Expires: 2026-04-15 (58 days)

📍 Available elements:
  /san      Subject Alternative Names (3 domains)
  /chain    Certificate chain (3 certs)
  /issuer   Issuer details
  /subject  Subject details
  /dates    Validity dates

💡 Try: reveal ssl://example.com/san
```

### Implementation

#### 1. Add Method to ResourceAdapter
```python
# reveal/adapters/base.py

class ResourceAdapter(ABC):
    def get_available_elements(self) -> List[Dict[str, str]]:
        """Return list of available elements for this resource.

        Returns:
            List of dicts with 'name', 'description', 'example' keys
        """
        return []
```

#### 2. Implement in Adapters
```python
# reveal/adapters/ssl/adapter.py

class SSLAdapter(ResourceAdapter):
    def get_available_elements(self):
        return [
            {
                'name': 'san',
                'description': f'Subject Alternative Names ({len(self._certificate.san)} domains)',
                'example': f'reveal ssl://{self.host}/san'
            },
            {
                'name': 'chain',
                'description': f'Certificate chain ({len(self._chain)} certs)',
                'example': f'reveal ssl://{self.host}/chain'
            },
            # ...
        ]
```

#### 3. Renderer Integration
```python
# reveal/adapters/ssl/renderer.py

class SSLRenderer:
    def _render_overview(self, structure, adapter):
        # ...existing overview rendering...

        # Add element discovery
        elements = adapter.get_available_elements()
        if elements:
            output.append("\n📍 Available elements:")
            for elem in elements:
                output.append(f"  /{elem['name']:<12} {elem['description']}")

            output.append(f"\n💡 Try: {elements[0]['example']}")
```

### Expected Behavior
All adapters with elements show hints:
- ssl:// → /san, /chain, /issuer, /subject, /dates
- domain:// → /dns, /ssl, /whois, /registrar
- mysql:// → /connections, /innodb, /replication, /tables
- json:// → /path/to/key

### Files to Modify
- `reveal/adapters/base.py` - Add `get_available_elements()` method
- All adapter classes - Implement method
- All adapter renderers - Show elements in overview

### Success Criteria
- [ ] All adapters with elements show hints
- [ ] JSON output includes available elements
- [ ] Breadcrumbs reference available elements

---

## Phase 6: Help Introspection ✅ FULLY COMPLETE (8 hours total)

**Added**: 2026-02-06 - From agentic AI feedback
**Phase 1 Complete**: 2026-02-06 - Session jinipoke-0206 (infrastructure + 3 adapters)
**Phase 2 Complete**: 2026-02-06 - Session xtreme-shockwave-0206 (remaining 12 adapters)
**Total Effort**: 8 hours (4 hours infrastructure + 4 hours coverage)

### Goal
Make help:// adapter machine-readable for AI agents to auto-discover capabilities and generate valid queries.

### Implementation Summary
- ✅ Added `get_schema()` method to base adapter
- ✅ Implemented `help://schemas/<adapter>` route
- ✅ Implemented `help://examples/<task>` route with 4 task categories (security, codebase, debugging, quality)
- ✅ **ALL 15 adapters now have schemas** (100% coverage):
  - **Simple**: env, json, markdown, reveal (4/4)
  - **Analysis**: diff, imports (2/2)
  - **Data**: mysql, sqlite, python (3/3)
  - **Complex**: git, domain, claude (3/3)
  - **Original**: ssl, ast, stats (3/3)
- ✅ All routes tested and working
- ✅ JSON schemas include query params, operators, output types, examples
- ✅ Updated AGENT_HELP.md with complete adapter list (v0.47.0)

### Proposed Enhancement

```bash
# Current (human-readable)
reveal help://ssl                # Markdown guide

# NEW: Machine-readable introspection
reveal help://adapters           # List all adapters with metadata
reveal help://schemas/ssl        # JSON schema for ssl:// output
reveal help://adapters/ssl       # SSL adapter metadata + schema
reveal help://examples/task      # Canonical query recipes
```

### Implementation

#### 1. Extend help:// Adapter

**Add routes:**
```python
# reveal/adapters/help_adapter.py

class HelpAdapter(ResourceAdapter):
    def get_structure(self, **kwargs):
        if self.resource == 'adapters':
            return self._list_adapters()
        elif self.resource.startswith('schemas/'):
            adapter_name = self.resource.split('/')[1]
            return self._get_adapter_schema(adapter_name)
        elif self.resource.startswith('adapters/'):
            adapter_name = self.resource.split('/')[1]
            return self._get_adapter_metadata(adapter_name)
        elif self.resource.startswith('examples/'):
            task = self.resource.split('/')[1]
            return self._get_task_examples(task)
        # ...existing help logic
```

#### 2. Schema Generation

**Leverage Output Contract v1.0:**
```python
def _get_adapter_schema(self, adapter_name: str) -> Dict:
    """Generate JSON schema from adapter's Output Contract."""
    adapter_class = get_adapter_class(adapter_name)

    return {
        'contract_version': '1.0',
        'type': 'adapter_schema',
        'adapter': adapter_name,
        'description': adapter_class.get_description(),
        'uri_syntax': adapter_class.get_uri_syntax(),
        'query_params': adapter_class.get_query_params(),
        'elements': adapter_class.get_available_elements(),
        'output_types': adapter_class.get_output_types(),
        'cli_flags': adapter_class.get_cli_flags(),
        'example_queries': adapter_class.get_example_queries()
    }
```

#### 3. Example Recipes

**Add task-based query recipes:**
```python
def _get_task_examples(self, task: str) -> Dict:
    """Get canonical query recipes for common tasks."""
    recipes = {
        'code-review': [
            {
                'description': 'Find complex functions',
                'query': 'ast://src?complexity>10&sort=-complexity&limit=20',
                'adapter': 'ast'
            },
            {
                'description': 'Check code quality',
                'query': 'reveal src/ --check',
                'adapter': 'file'
            }
        ],
        'onboarding': [
            {
                'description': 'See project structure',
                'query': 'reveal src/ --max-depth=2',
                'adapter': 'file'
            }
        ],
        # ... more recipes
    }
    return recipes.get(task, [])
```

### Expected Output

**List adapters:**
```bash
$ reveal help://adapters --format=json
{
  "contract_version": "1.0",
  "type": "adapter_list",
  "adapters": [
    {
      "name": "ssl",
      "description": "SSL/TLS certificate inspection",
      "uri_pattern": "ssl://<host>[:<port>]",
      "stability": "beta",
      "query_capable": true,
      "batch_capable": true
    },
    ...
  ]
}
```

**Get adapter schema:**
```bash
$ reveal help://schemas/ssl --format=json
{
  "adapter": "ssl",
  "uri_syntax": "ssl://<host>[:<port>][/<element>]",
  "query_params": {
    "check": {"type": "boolean", "description": "Run health checks"},
    "advanced": {"type": "boolean", "description": "Enable advanced checks"}
  },
  "output_types": [
    {
      "type": "ssl_certificate",
      "fields": {
        "domain": {"type": "string"},
        "expiry": {"type": "datetime"},
        "days_until_expiry": {"type": "integer"}
      }
    }
  ],
  "example_queries": [
    {
      "uri": "ssl://example.com",
      "description": "Certificate overview"
    }
  ]
}
```

### Files to Modify
- `reveal/adapters/help_adapter.py` - Add schema routes
- `reveal/adapters/base.py` - Add schema metadata methods
- All adapter classes - Implement metadata methods
- `reveal/adapters/help_data/` - Add schema generation

### Success Criteria
- [x] `help://adapters` lists all adapters with metadata ✅ (Verified 2026-02-07)
- [x] `help://schemas/<adapter>` returns JSON schema for ALL 15 adapters ✅ (Verified 2026-02-07)
- [x] Schema includes all URI patterns, query params, output types ✅ (Verified 2026-02-07)
- [x] `help://examples/<task>` returns canonical recipes ✅ (Verified 2026-02-07)
- [x] AI agents can auto-discover capabilities ✅ (Verified 2026-02-07)

### Adapter Coverage (15/15 = 100%)
```
✅ ast          - Code structure analysis
✅ claude       - Claude conversation analysis
✅ diff         - Resource comparison
✅ domain       - Domain DNS/WHOIS
✅ env          - Environment variables
✅ git          - Git repositories
✅ imports      - Import graph analysis
✅ json         - JSON file navigation
✅ markdown     - Markdown frontmatter queries
✅ mysql        - MySQL databases
✅ python       - Python runtime
✅ reveal       - Self-inspection
✅ sqlite       - SQLite databases
✅ ssl          - SSL certificates
✅ stats        - Code statistics
```

---

## Phase 7: Output Contract v1.1 - Trust Metadata ✅ COMPLETE (2 hours actual)

**Added**: 2026-02-06 - From agentic AI feedback
**Completed**: 2026-02-06 - Session jinipoke-0206
**Effort**: 2 hours (vs 2-4 estimated) - 50% efficiency

### Goal
Expose parsing confidence, warnings, and errors in-band so AI agents know when to trust results.

### Implementation Summary
- ✅ Added optional `meta` field to Output Contract
- ✅ Defined trust metadata structure (parse_mode, confidence, warnings, errors)
- ✅ Added `create_meta()` helper to base adapter
- ✅ Updated AST adapter with v1.1 contract
- ✅ Full backward compatibility (v1.0 clients work)
- ✅ Documentation updated (OUTPUT_CONTRACT.md)
- ✅ All tests passing

### Proposed Enhancement: Output Contract v1.1

**Add meta section with trust indicators:**
```json
{
  "contract_version": "1.1",
  "type": "ast_query_results",
  "source": "src/",
  "source_type": "directory",

  // NEW: Quality metadata
  "meta": {
    "parse_mode": "tree_sitter_full",      // or "fallback", "regex", "heuristic"
    "confidence": 0.95,                     // 0.0-1.0 overall parse confidence
    "warnings": [
      {
        "code": "W001",
        "message": "File encoding uncertain, assumed UTF-8",
        "file": "legacy.py",
        "severity": "low"
      }
    ],
    "errors": [
      {
        "code": "E002",
        "message": "Parse failed for malformed.py",
        "file": "malformed.py",
        "fallback": "Used regex fallback",
        "severity": "medium"
      }
    ]
  },

  // Optional: Per-item confidence
  "items": [
    {
      "symbol": "authenticate",
      "confidence": 0.98,            // Per-item confidence
      "parse_warnings": []           // Per-item warnings
    }
  ]
}
```

### Implementation

#### 1. Update Output Contract Spec

**Add to `docs/OUTPUT_CONTRACT.md`:**
- Define v1.1 fields
- Document confidence scoring (0.0-1.0)
- Define parse_mode values: `tree_sitter_full`, `tree_sitter_partial`, `fallback`, `regex`, `heuristic`
- Define warning/error structure

#### 2. Enhance Base Adapter

```python
# reveal/adapters/base.py

class ResourceAdapter(ABC):
    def get_structure(self, **kwargs) -> Dict[str, Any]:
        # Existing implementation...

        # NEW: Add meta section with trust indicators
        result = {
            'contract_version': '1.1',
            'type': self._get_output_type(),
            'source': self._get_source(),
            'source_type': self._get_source_type(),
            'meta': {
                'parse_mode': self._get_parse_mode(),      # NEW
                'confidence': self._calculate_confidence(),  # NEW
                'warnings': self._collect_warnings(),        # NEW
                'errors': self._collect_errors()             # NEW
            },
            # ...adapter-specific fields
        }
        return result
```

#### 3. Confidence Scoring

**Parse mode determines baseline confidence:**
```python
def _calculate_confidence(self) -> float:
    """Calculate overall parsing confidence."""
    base_confidence = {
        'tree_sitter_full': 0.95,
        'tree_sitter_partial': 0.80,
        'fallback': 0.60,
        'regex': 0.50,
        'heuristic': 0.40
    }[self.parse_mode]

    # Adjust for warnings/errors
    if self.warnings:
        base_confidence -= 0.05 * len(self.warnings)
    if self.errors:
        base_confidence -= 0.10 * len(self.errors)

    return max(0.0, min(1.0, base_confidence))
```

### Migration Strategy

**Backward Compatible:**
- v1.0 clients ignore `meta` field
- v1.1 clients get enhanced metadata
- Both versions supported simultaneously

**Deprecation:**
- v1.0 remains supported indefinitely (no breaking changes)
- v1.1 becomes default in reveal v0.46+

### Files to Modify
- `docs/OUTPUT_CONTRACT.md` - Add v1.1 spec
- `reveal/adapters/base.py` - Add meta section methods
- All adapter classes - Implement confidence/warnings/errors
- Tests for each adapter - Validate v1.1 compliance

### Success Criteria
- [ ] All adapters emit v1.1 meta section
- [ ] Confidence scores accurate (validated against test fixtures)
- [ ] Warnings collected programmatically
- [ ] Errors don't crash, return in `meta.errors`
- [ ] AI agents can check `meta.confidence` before trusting results

---

## Backward Compatibility Strategy

### Principles

1. **Additive Only**: Add new features, don't break existing
2. **Dual Support**: Support old and new syntax simultaneously
3. **Deprecation Path**: 3-version deprecation cycle (announce → warn → remove)

### Breaking Change Avoidance

**Example: Query Operators**
```bash
# Old (still works)
stats://src?min_lines=50&max_lines=200

# New (also works)
stats://src?lines=50..200
```

**Example: Flags**
```bash
# Old (deprecated but works in v0.45-v0.50)
reveal ssl://example.com --check-advanced

# New (preferred, works immediately)
reveal ssl://example.com --check --advanced
```

### Deprecation Timeline

**Phase 1 (v0.45)**: Add new, keep old
- Introduce universal flags
- Add deprecation warnings to old syntax
- Update docs to show new approach

**Phase 2 (v0.46-v0.50)**: Both work
- Old syntax still works
- Warnings logged
- New syntax documented everywhere

**Phase 3 (v0.51+)**: Remove old
- Old syntax removed
- Tests updated
- Migration guide published

---

## Documentation Updates Needed

### User-Facing Docs (`reveal/docs/`)

#### 1. Update ADAPTER_AUTHORING_GUIDE.md
Add section:
- "Universal Operation Flags"
- "Query Operator Standard"
- "Field Selection Support"

#### 2. Update AGENT_HELP.md
Add sections:
- Universal flags reference
- Query operator syntax
- Batch processing patterns

#### 3. Create QUERY_SYNTAX_GUIDE.md (NEW)
Comprehensive operator reference:
- Comparison operators
- Wildcards
- Boolean logic
- Examples per adapter

### Internal Docs (`internal-docs/`)

#### 1. Update planning/README
Reference this document

#### 2. Create IMPLEMENTATION_STATUS.md (NEW)
Track progress:
- [x] Phase 1: Universal flags (v0.45.0)
- [x] Phase 2: Batch processing (v0.45.0)
- [ ] Phase 3: Query operators + sort/limit
- [ ] Phase 4: Field selection + budget awareness
- [ ] Phase 5: Element discovery
- [x] Phase 6: Help introspection (v0.46.0) ✅ 2026-02-06
- [x] Phase 7: Output Contract v1.1 (v0.46.0) ✅ 2026-02-06

---

## Success Metrics

### Consistency
- [ ] All adapters support `--check` (where validation makes sense)
- [x] All adapters support `--format=json|text` ✅ (Verified 2026-02-07)
- [ ] All adapters support `--format=compact` (Not yet implemented)
- [x] All adapters support `--batch` for stdin input ✅ (Verified 2026-02-07)
- [ ] All query-based adapters use same operator syntax
- [ ] All adapters support `--select` for field selection

### Token Efficiency
- [ ] `--select` reduces output by 5-10x (measured)
- [ ] `--format=compact` reduces output by 2-3x (measured)
- [x] `--batch` aggregates results (no repeated headers) ✅ (Verified 2026-02-07)

### Discoverability
- [ ] Overview shows available elements
- [ ] Help docs include query operator reference
- [ ] Error messages suggest correct syntax
- [ ] `--adapters` shows all with consistent descriptions

### Test Coverage
- [ ] Universal flags tested across all adapters
- [ ] Query parser has 90%+ coverage
- [ ] Batch mode integration tests
- [ ] Field selection tests per adapter

---

## Implementation Priority

**Updated**: 2026-02-06 - Phases 1+2 complete, added Phases 6+7

### ✅ COMPLETE (v0.45.0)
1. **Phase 1**: Universal operation flags (4 hours) ✅
   - `--advanced`, `--only-failures` work across all adapters
   - Completed: pulsing-supernova-0206

2. **Phase 2**: Stdin batch processing (8 hours) ✅
   - Universal `--batch` flag with aggregation
   - Completed: pulsing-supernova-0206

### High Priority (Next 2-4 weeks) - 38 hours total
3. **Phase 3**: Query operator standardization + sort/limit (20 hours, was 16)
   - Universal operators: `>`, `<`, `=`, `!=`, `~=`, `..`, `&`, `|`, `!`, `()`
   - **NEW**: `sort=`, `limit=`, `offset=` query params
   - Significant effort but high consistency value

4. **Phase 4**: Field selection + budget awareness (12 hours, was 8)
   - `--select=fields` for token reduction
   - **NEW**: `--max-items`, `--max-bytes`, `--max-depth`, `--max-snippet-chars`
   - **NEW**: Truncation metadata in Output Contract
   - Critical for AI agent token budgets

5. **Phase 6**: Help introspection (4-6 hours) **NEW**
   - Machine-readable `help://adapters`, `help://schemas/<adapter>`
   - JSON schemas for all adapters
   - Canonical query recipes
   - Enables AI agent auto-discovery

### Medium Priority (Next 1-2 months) - 6 hours total
6. **Phase 7**: Output Contract v1.1 (2-4 hours) **NEW**
   - Add `meta.parse_mode`, `meta.confidence`, `meta.warnings`, `meta.errors`
   - Trust metadata for AI agents
   - Backward compatible with v1.0

7. **Phase 5**: Element discovery hints (4 hours)
   - Nice-to-have for UX
   - Can be added incrementally

**Total Effort**: 44-50 hours (5-7 weeks)

---

## Risk Assessment

### Low Risk
- **Additive changes**: Won't break existing code
- **Backward compatible**: Old syntax continues working
- **Incremental**: Can implement phase by phase
- **Well-tested**: Each phase can be tested independently

### Medium Risk
- **Query parser complexity**: Need robust parsing logic
- **Documentation debt**: 16 adapters × 5 help files = 80 docs to update
- **Testing burden**: Universal flags need testing across all adapters

### Mitigation
- Start with pilot adapter (ssl://) before rolling out
- Automated testing for universal flag support
- Documentation templates for consistency
- Deprecation warnings before breaking changes

---

## Maintenance Considerations

### Adding New Adapters
All future adapters should:
1. Inherit universal operation flags
2. Use unified query parser (if filtering needed)
3. Support `--select` for field filtering
4. Implement `get_available_elements()` if element-based
5. Support `--batch` mode

### Adapter Checklist
```markdown
- [ ] Supports `--check` (if validation makes sense)
- [ ] Supports `--advanced` modifier
- [x] Supports `--format=json|text` (inherited from BaseRenderer)
- [ ] Supports `--format=compact` (not yet implemented)
- [ ] Supports `--select=fields`
- [ ] Supports `--batch` mode
- [ ] Uses unified query parser (if filtering needed)
- [ ] Implements `get_available_elements()` (if element-based)
- [ ] Help file documents all universal flags
- [ ] Tests cover universal flag behavior
```

---

## Related Documents

**User-Facing**:
- `reveal/docs/ADAPTER_AUTHORING_GUIDE.md` - Creating adapters
- `reveal/docs/REVEAL_ADAPTER_GUIDE.md` - Reference implementation
- `reveal/docs/RECIPES.md` - Usage patterns

**Internal**:
- `internal-docs/refactoring/ARCHITECTURE_IMPROVEMENTS_2026-01-20.md` - Meta-level refactoring
- `internal-docs/research/UX_ISSUES_2026-01-20.md` - UX issues from dogfooding
- `internal-docs/research/DOGFOODING_REPORT_2026-01-19.md` - Adapter validation

**Session Docs** (TIA):
- `tia/sessions/neon-undertaker-0206/ADAPTER_UX_CONSISTENCY_RECOMMENDATIONS.md` - Detailed analysis
- `tia/sessions/neon-undertaker-0206/URI_PARAMS_VS_CLI_FLAGS_ANALYSIS.md` - Architecture decision
- `tia/sessions/neon-undertaker-0206/REVEAL_ARCHITECTURE_VALIDATION.md` - SSL/domain implementation review

---

## See Also

**User-Facing Docs**:
- [ADAPTER_CONSISTENCY.md](../../reveal/docs/ADAPTER_CONSISTENCY.md) - User guide for adapter consistency patterns
- [ADAPTER_AUTHORING_GUIDE.md](../../reveal/docs/ADAPTER_AUTHORING_GUIDE.md) - How to create custom adapters

**Related Planning**:
- [TECHNICAL_DEBT_RESOLUTION.md](TECHNICAL_DEBT_RESOLUTION.md) - TreeSitter architecture improvements

**Implementation**:
- TIA sessions: jade-jewel-0205 (domain adapter), neon-undertaker-0206 (analysis), blessed-witch-0206 (CLI flags)

---

## Next Actions

### Immediate (This Week)
1. Review this document with maintainers
2. Prioritize phases based on roadmap
3. Start Phase 1 implementation (universal flags)

### Short-term (Next Month)
4. Implement Phase 2 (batch processing)
5. Create pilot for Phase 3 (query parser) with ast://

### Medium-term (Next Quarter)
6. Roll out Phase 3 to all adapters
7. Implement Phase 4 (field selection)
8. Implement Phase 5 (element discovery)

---

**Status**: 📋 PLANNING (not yet implemented)
**Owner**: TBD
**Est. Completion**: 3-6 months (40-60 hours total)
**Last Updated**: 2026-02-06
