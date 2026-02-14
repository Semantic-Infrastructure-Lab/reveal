# Production TODOs - Issue Tracking

> **Generated**: 2026-02-14
> **Purpose**: Track production TODOs for conversion to GitHub issues
> **Status**: Ready for issue creation

This document captures production-level TODOs found in the Reveal codebase, excluding template files. Each TODO should be converted to a GitHub issue with appropriate labels.

---

## 🔴 Priority: High (Core Functionality)

### TODO-001: Implement cross-sheet search in XLSX adapter
**File**: `reveal/adapters/xlsx.py:663`
**Context**: `get_element()` method
**Description**: Add support for searching across multiple sheets in Excel files
**Current**: Placeholder comment
**Impact**: High - Missing feature for xlsx:// adapter
**Effort**: Medium (2-3 days)
**Labels**: `enhancement`, `adapters`, `xlsx`

```python
# TODO: Implement cross-sheet search
```

**Suggested Issue**:
```markdown
Title: Implement cross-sheet search for xlsx:// adapter
Body: The xlsx adapter currently lacks cross-sheet search functionality.
Users should be able to search for values across all sheets in a workbook.

Example: `reveal xlsx:///file.xlsx?search=revenue`

Implementation should:
- Search cell values across all sheets
- Return sheet name + cell reference for matches
- Support case-insensitive matching
- Respect result limits
```

---

## 🟡 Priority: Medium (Integration/Enhancement)

### TODO-002: Implement WHOIS integration for domain adapter
**File**: `reveal/adapters/domain/adapter.py:204, 484` + `domain/renderer.py:145`
**Context**: Domain registration data
**Description**: Add WHOIS lookup support using python-whois library
**Current**: Placeholder methods, documented but not implemented
**Impact**: Medium - Nice-to-have feature for domain:// adapter
**Effort**: Medium (1-2 days)
**Labels**: `enhancement`, `adapters`, `domain`, `external-api`
**Blocker**: Requires `python-whois` dependency

```python
whois: WHOIS registration data (TODO: requires python-whois)

def get_whois(self) -> Dict[str, Any]:
    """Get WHOIS information (TODO: requires python-whois)."""
    # TODO: Implement when python-whois is integrated
```

**Suggested Issue**:
```markdown
Title: Add WHOIS integration to domain:// adapter
Body: Implement WHOIS lookup functionality for domain adapter.

Requirements:
- Add python-whois as optional dependency
- Implement get_whois() method
- Parse registrar, expiry date, nameservers
- Add WHOIS element to domain:// structure
- Handle rate limits and API errors gracefully

Depends on: Evaluating python-whois library stability
```

---

### TODO-003: Parse nginx config for SSL certificate validation
**File**: `reveal/adapters/ssl/adapter.py:731`
**Context**: `_extract_cert_from_config()` method
**Description**: Parse nginx configuration files to extract certificate paths
**Current**: Placeholder comment
**Impact**: Medium - Would enable nginx-specific SSL validation
**Effort**: High (3-4 days)
**Labels**: `enhancement`, `adapters`, `ssl`, `nginx`

```python
# TODO: Parse nginx config to get cert path and validate
```

**Suggested Issue**:
```markdown
Title: Parse nginx config for SSL certificate validation
Body: Enable ssl:// adapter to read certificate paths from nginx configuration.

Example: `reveal ssl://nginx --config /etc/nginx/sites-enabled/example.conf`

Implementation:
- Parse nginx config syntax (server blocks, ssl_certificate directives)
- Extract certificate and key paths
- Validate certificates found in config
- Handle includes and multi-file configs
- Consider using pyparsing or nginx-config-parser library
```

---

## 🟢 Priority: Low (Code Quality/Technical Debt)

### TODO-004: Track import level explicitly in ImportStatement
**File**: `reveal/analyzers/imports/resolver.py:49`
**Context**: Import resolution logic
**Description**: Add explicit level tracking for relative imports
**Current**: Implicit level calculation
**Impact**: Low - Code clarity improvement
**Effort**: Low (30 minutes)
**Labels**: `refactor`, `analyzers`, `imports`

```python
# TODO: Track level explicitly in ImportStatement
```

**Suggested Issue**:
```markdown
Title: Add explicit level tracking to ImportStatement
Body: Currently import level (for relative imports like `from .. import`)
is calculated implicitly. Add an explicit `level` field to ImportStatement
for clarity.

Changes:
- Add `level: int` field to ImportStatement dataclass
- Populate during import parsing
- Update tests

Benefit: Makes relative import handling more explicit and testable
```

---

### TODO-005: Pass analyzer to get_file_type_from_analyzer()
**File**: `reveal/display/structure.py:586`
**Context**: File type detection
**Description**: Fix None parameter by passing actual analyzer instance
**Current**: Passing None as workaround
**Impact**: Low - Potential bug/inconsistency
**Effort**: Low (30 minutes)
**Labels**: `bug`, `display`, `tech-debt`

```python
file_type = get_file_type_from_analyzer(None)  # TODO: pass analyzer if needed
```

**Suggested Issue**:
```markdown
Title: Fix analyzer parameter in get_file_type_from_analyzer call
Body: The call to get_file_type_from_analyzer() in display/structure.py:586
currently passes None. Investigate if this is intentional or if we should
pass the actual analyzer instance.

Steps:
1. Review get_file_type_from_analyzer() signature and usage
2. Determine if analyzer parameter is actually needed
3. Either pass correct analyzer or update function to not require it
4. Add tests to prevent regression
```

---

### TODO-006: Handle framework routing in L003 rule
**File**: `reveal/rules/links/L001.py:227`
**Context**: Link validation
**Description**: Delegate framework-specific routing to L003 rule
**Current**: Skipped in L001
**Impact**: Low - Architecture decision
**Effort**: Low (1 hour)
**Labels**: `refactor`, `rules`, `link-validation`

```python
# TODO: Handle in L003 with framework routing
```

**Suggested Issue**:
```markdown
Title: Move framework routing detection to L003 rule
Body: Currently L001 skips framework routing patterns. Move this logic
to L003 (Framework-Aware Link Validation) for better separation of concerns.

Affected:
- L001: Remove framework routing TODOs
- L003: Implement framework-specific link validation
- Ensure both rules work together

Frameworks to support: FastHTML, Flask, Django, etc.
```

---

## 📋 Summary Statistics

- **Total Production TODOs**: 6 (excluding template generators)
- **Priority Breakdown**:
  - 🔴 High: 1 (cross-sheet search)
  - 🟡 Medium: 2 (WHOIS, nginx parsing)
  - 🟢 Low: 3 (code quality improvements)
- **Estimated Total Effort**: 8-11 days
- **External Dependencies**: 1 (python-whois)

---

## 📝 Next Steps

1. **Create GitHub Issues**: Convert each TODO to a tracked issue
2. **Add Labels**: Apply priority, component, and type labels
3. **Link Issues**: Reference issue numbers in code comments
4. **Remove TODOs**: Replace with issue references (e.g., `# See issue #123`)
5. **Update CHANGELOG**: Document issue creation

---

## 🔧 Conversion Script

Once issues are created, update code comments:

```bash
# Replace TODO with issue reference
# Before: # TODO: Implement cross-sheet search
# After:  # See issue #123: Implement cross-sheet search
```

---

## ❌ Excluded TODOs

**Template Files** (intentional placeholders):
- `reveal/cli/scaffold/adapter.py:84` - Generates TODO in scaffolded code
- `reveal/templates/*.py` - Example code with instructional TODOs
- `reveal/adapters/test.py` - Test adapter template
- `reveal/adapters/demo.py` - Demo adapter with TODOs

These are **not bugs** - they're intentional placeholders in generated/example code.

---

**Document Status**: ✅ Ready for GitHub Issue Creation
**Last Updated**: 2026-02-14
**Maintainer**: See CONTRIBUTING.md
