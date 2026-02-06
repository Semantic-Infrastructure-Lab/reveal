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
- [ ] All adapters support `--format` consistently
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

## Phase 3: Query Operator Standardization (Medium Priority - 16 hours)

### Goal
Unified query syntax across all adapters.

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
- [ ] All adapters use same operator syntax
- [ ] Backward compatible with existing queries
- [ ] Documentation includes operator reference
- [ ] Error messages suggest correct syntax

---

## Phase 4: Field Selection for Token Efficiency (Medium Priority - 8 hours)

### Goal
Reduce token usage by selecting specific fields in output.

### Current State
Full structure returned (100-500 lines):
```bash
reveal ssl://example.com --format=json
# Returns: ~400 lines of JSON
```

### Proposed Enhancement
```bash
reveal ssl://example.com --select=domain,expiry,days_until_expiry --format=json
# Returns: ~10 lines of JSON (40x reduction)
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
- [ ] `--select` works with all adapters
- [ ] 5-10x token reduction measured
- [ ] Works with `--format=json` and `--format=text`
- [ ] Error if field doesn't exist

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
- [ ] Phase 1: Universal flags
- [ ] Phase 2: Batch processing
- [ ] Phase 3: Query operators
- [ ] Phase 4: Field selection
- [ ] Phase 5: Element discovery

---

## Success Metrics

### Consistency
- [ ] All adapters support `--check` (where validation makes sense)
- [ ] All adapters support `--format=json|text|compact`
- [ ] All adapters support `--batch` for stdin input
- [ ] All query-based adapters use same operator syntax
- [ ] All adapters support `--select` for field selection

### Token Efficiency
- [ ] `--select` reduces output by 5-10x (measured)
- [ ] `--format=compact` reduces output by 2-3x (measured)
- [ ] `--batch` aggregates results (no repeated headers)

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

### High Priority (Next 2 weeks)
1. **Phase 1**: Universal operation flags (4 hours)
   - Immediate value for ssl://, domain://, mysql://
   - Foundation for other phases

2. **Phase 2**: Stdin batch processing (8 hours)
   - High user value
   - Enables bulk operations

### Medium Priority (Next 1-2 months)
3. **Phase 3**: Query operator standardization (16 hours)
   - Significant effort but high consistency value
   - Can be done incrementally per adapter

4. **Phase 4**: Field selection (8 hours)
   - Token efficiency critical for AI agents
   - Relatively straightforward implementation

### Low Priority (Next 3-6 months)
5. **Phase 5**: Element discovery hints (4 hours)
   - Nice-to-have for UX
   - Can be added incrementally

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
- [ ] Supports `--format=json|text|compact`
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
