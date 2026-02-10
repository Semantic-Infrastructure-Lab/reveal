# V-Series Validation Rules Test Plan

**Session**: mighty-crown-0207
**Date**: 2026-02-07
**Status**: Design Phase

## Overview

This document outlines the test plan for 11 untested V-series validation rules (V012-V023). These rules currently have 0% test coverage despite being production code.

**Target Coverage**: 70%+ for each rule (happy path + key edge cases)

---

## Rules Summary

| Rule | Lines | Severity | Purpose | Complexity |
|------|-------|----------|---------|------------|
| V012 | 135 | MEDIUM | Language count accuracy in README | Low |
| V013 | 120 | MEDIUM | Adapter count accuracy in README | Low |
| V015 | 147 | MEDIUM | Rules count accuracy in README | Medium |
| V016 | 156 | MEDIUM | Adapter help completeness | Medium |
| V017 | 206 | HIGH | Tree-sitter node type coverage | High |
| V018 | 139 | HIGH | Adapter renderer registration | Medium |
| V019 | 227 | HIGH | Adapter initialization patterns | High |
| V020 | 291 | MEDIUM | Adapter element/structure contract | High |
| V021 | 255 | HIGH | Regex vs tree-sitter usage | High |
| V022 | 175 | HIGH | Package manifest inclusion | High |
| V023 | 278 | HIGH | Output contract compliance | High |

**Total**: 2,133 lines of untested code

---

## Test Design Pattern

Following the established pattern from test_validation_rules.py:

```python
class TestV0XX(unittest.TestCase):
    def setUp(self):
        self.rule = V0XX()

    def test_metadata(self):
        """Test rule metadata is correct"""
        self.assertEqual(self.rule.code, "V0XX")
        self.assertIsNotNone(self.rule.message)
        # ...

    def test_non_reveal_uri_ignored(self):
        """Test rule ignores non-reveal:// URIs"""
        detections = self.rule.check("regular_file.py", None, "")
        self.assertEqual(len(detections), 0)

    def test_reveal_uri_processed(self):
        """Test rule processes reveal:// URIs"""
        detections = self.rule.check("reveal://.", None, "")
        # Assertions depend on rule logic

    # Rule-specific tests
```

---

## V012: Language Count Accuracy

**Purpose**: Validates README.md language count matches registered analyzers

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_language_count_matches** - No detection when counts match
5. **test_language_count_mismatch** - Detection when count differs
6. **test_multiple_claims_checked** - All README claims validated
7. **test_pattern_detection** - All 3 patterns detected ("N languages built-in", "Built-in (N):", "Zero config. N languages")
8. **test_missing_readme** - Handles missing README gracefully

**Fixtures Needed**:
- Mock README with correct count
- Mock README with incorrect count
- Mock README with multiple claims
- Mock registry with known language count

**Complexity**: Low
**Estimated Time**: 1 hour

---

## V013: Adapter Count Accuracy

**Purpose**: Validates README.md adapter count matches registered adapters

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_adapter_count_matches** - No detection when counts match
5. **test_adapter_count_mismatch** - Detection when count differs
6. **test_pattern_detection** - Both patterns detected ("N adapters", "**N Built-in Adapters**")
7. **test_missing_readme** - Handles missing README gracefully

**Fixtures Needed**:
- Mock README with correct adapter count
- Mock README with incorrect adapter count
- Mock adapter registry

**Complexity**: Low
**Estimated Time**: 1 hour

---

## V015: Rules Count Accuracy

**Purpose**: Validates README.md rules count matches actual rules

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_exact_count_matches** - No detection when exact count matches
5. **test_exact_count_mismatch** - Detection when exact count differs
6. **test_minimum_claim_valid** - "50+ rules" passes when actual >= 50
7. **test_minimum_claim_invalid** - "50+ rules" fails when actual < 50
8. **test_rule_counting_excludes_utils** - utils.py, __init__.py excluded
9. **test_missing_readme** - Handles missing README gracefully

**Fixtures Needed**:
- Mock README with exact count
- Mock README with minimum count ("50+")
- Mock rules directory structure
- Mock reveal root

**Complexity**: Medium (minimum vs exact logic)
**Estimated Time**: 1.5 hours

---

## V016: Adapter Help Completeness

**Purpose**: Validates adapters implement get_help() for discoverability

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_adapter_file_ignored** - Non-adapter files skipped
3. **test_init_and_base_skipped** - __init__.py and base.py skipped
4. **test_adapter_with_get_help** - No detection when get_help() exists
5. **test_adapter_missing_get_help** - Detection when get_help() missing
6. **test_adapter_with_trivial_get_help** - Detection when get_help() returns None only
7. **test_detect_adapter_class** - Correctly identifies adapter files

**Fixtures Needed**:
- Sample adapter with get_help()
- Sample adapter without get_help()
- Sample adapter with trivial get_help()
- Non-adapter file for negative test

**Complexity**: Medium
**Estimated Time**: 1 hour

---

## V017: Tree-sitter Node Type Coverage

**Purpose**: Validates TreeSitterAnalyzer has node types for supported languages

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_treesitter_file_ignored** - Non-treesitter.py files skipped
3. **test_sufficient_function_types** - No detection when >= 5 function types
4. **test_insufficient_function_types** - Detection when < 5 function types
5. **test_sufficient_class_types** - No detection when >= 3 class types
6. **test_insufficient_class_types** - Detection when < 3 class types
7. **test_missing_simple_identifier** - Detection when simple_identifier missing (Kotlin/Swift)
8. **test_node_type_extraction** - _extract_function_types() works correctly

**Fixtures Needed**:
- Mock treesitter.py with sufficient node types
- Mock treesitter.py with insufficient function types
- Mock treesitter.py with insufficient class types
- Mock treesitter.py missing simple_identifier

**Complexity**: High (parsing method bodies, counting types)
**Estimated Time**: 2 hours

---

## V018: Adapter Renderer Registration

**Purpose**: Validates all adapters have corresponding renderers

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_adapter_with_renderer** - No detection when renderer exists
5. **test_adapter_without_renderer** - HIGH detection for missing renderer
6. **test_renderer_without_adapter** - LOW detection for orphaned renderer
7. **test_find_adapter_file** - All 4 patterns work (scheme.py, scheme_adapter.py, scheme/adapter.py, scheme/__init__.py)

**Fixtures Needed**:
- Mock adapter/renderer registries
- Mock adapter directory structure
- Mock reveal root

**Complexity**: Medium
**Estimated Time**: 1.5 hours

---

## V019: Adapter Initialization Patterns

**Purpose**: Validates adapters follow initialization contract

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_no_arg_init_success** - No detection when no-arg init works
5. **test_no_arg_init_typeerror** - No detection when no-arg init raises TypeError
6. **test_no_arg_init_valueerror** - Detection when no-arg init raises ValueError
7. **test_no_arg_init_crash** - Detection when no-arg init crashes
8. **test_resource_init_success** - No detection when resource init works
9. **test_resource_init_typeerror** - No detection when resource init raises TypeError
10. **test_resource_init_valueerror** - Context-dependent (validation is OK)
11. **test_resource_init_attributeerror** - Detection when crashes with AttributeError

**Fixtures Needed**:
- Mock adapter classes with different init behaviors
- Mock adapter files for error reporting
- Mock adapter registry

**Complexity**: High (multiple initialization patterns)
**Estimated Time**: 2.5 hours

---

## V020: Adapter Element/Structure Contract

**Purpose**: Validates adapters implement element/structure methods correctly

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_element_based_adapter_complete** - No detection when get_element() exists
5. **test_element_based_adapter_missing_get_element** - HIGH detection when renderer has render_element() but adapter lacks get_element()
6. **test_structure_only_adapter** - No detection when renderer lacks render_element()
7. **test_adapter_missing_get_structure** - HIGH detection when get_structure() missing
8. **test_get_element_error_handling** - Detection when get_element() crashes instead of returning None
9. **test_get_element_returns_none** - No detection when get_element() correctly returns None

**Fixtures Needed**:
- Mock adapter/renderer pairs with various capabilities
- Mock adapter classes with different method implementations
- Mock adapter files

**Complexity**: High (element vs structure logic)
**Estimated Time**: 2.5 hours

---

## V021: Regex vs Tree-sitter Usage

**Purpose**: Validates analyzers use tree-sitter instead of regex for parsing

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_treesitter_analyzer_no_detection** - No detection when using TreeSitterAnalyzer
5. **test_regex_analyzer_with_treesitter_available** - Detection when using regex and tree-sitter available
6. **test_regex_analyzer_no_treesitter** - No detection when using regex but tree-sitter unavailable
7. **test_whitelisted_files_ignored** - markdown.py, html.py, imports/base.py ignored
8. **test_imports_re_module_detection** - Correctly detects 're' module imports
9. **test_language_inference** - Correctly infers language from filename
10. **test_effort_estimation** - Correctly estimates migration effort based on regex count

**Fixtures Needed**:
- Mock analyzer using regex (GDScript example)
- Mock analyzer using TreeSitterAnalyzer
- Mock analyzer using regex for unsupported language
- Mock analyzers directory

**Complexity**: High (AST parsing, language mapping)
**Estimated Time**: 2.5 hours

---

## V022: Package Manifest Inclusion

**Purpose**: Validates MANIFEST.in includes critical files

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_reveal_uri_ignored** - Non-reveal URIs skipped
3. **test_reveal_uri_processed** - reveal:// URIs processed
4. **test_cli_handler_paths_exist** - No detection when CLI handler paths valid
5. **test_cli_handler_paths_missing** - Detection when CLI handler references non-existent path
6. **test_manifest_paths_exist** - No detection when MANIFEST.in paths valid
7. **test_manifest_paths_missing** - Detection when MANIFEST.in references non-existent file
8. **test_critical_files_included** - No detection when critical docs in manifest
9. **test_critical_files_missing** - Detection when critical docs not in manifest
10. **test_wildcard_paths_skipped** - Wildcard patterns not validated

**Fixtures Needed**:
- Mock CLI handlers.py
- Mock MANIFEST.in (valid and invalid)
- Mock critical files (AGENT_HELP.md, etc.)
- Mock project structure

**Complexity**: High (file system mocking)
**Estimated Time**: 2.5 hours

---

## V023: Output Contract Compliance

**Purpose**: Validates adapter/analyzer outputs conform to v1.0 contract

**Test Cases**:

1. **test_metadata** - Verify rule code, message, severity
2. **test_non_adapter_file_ignored** - Non-adapter/analyzer files skipped
3. **test_init_and_base_skipped** - __init__.py, base.py, utils.py skipped
4. **test_output_with_all_fields** - No detection when all required fields present
5. **test_output_missing_contract_version** - Detection for missing contract_version
6. **test_output_missing_type** - Detection for missing type
7. **test_output_missing_source** - Detection for missing source
8. **test_output_missing_source_type** - Detection for missing source_type
9. **test_deprecated_line_field** - Detection when using 'line' instead of 'line_start'
10. **test_hyphenated_type_field** - Detection when type uses hyphens ('ast-query')
11. **test_snake_case_type_field** - No detection when type is snake_case ('ast_query')
12. **test_scheme_extraction** - Correctly extracts scheme from file path

**Fixtures Needed**:
- Mock adapter with compliant output
- Mock adapter with missing fields
- Mock adapter with deprecated 'line' field
- Mock adapter with hyphenated type
- Mock get_structure() method bodies

**Complexity**: High (code parsing, pattern matching)
**Estimated Time**: 2.5 hours

---

## Test Infrastructure

### Shared Utilities

```python
# tests/test_validation_rules.py

def create_temp_readme(content: str) -> Path:
    """Create temporary README.md for testing"""

def create_temp_manifest(content: str) -> Path:
    """Create temporary MANIFEST.in for testing"""

def create_mock_reveal_root() -> Path:
    """Create mock reveal directory structure"""

def create_mock_adapter_file(scheme: str, content: str) -> Path:
    """Create mock adapter file"""
```

### Mocking Strategy

1. **File System**: Use tempfile for temporary structures
2. **Registry**: Mock reveal.registry functions
3. **Adapter Base**: Mock list_supported_schemes(), get_adapter_class()
4. **reveal_root**: Mock find_reveal_root() utility

### Test Execution

```bash
# Run all validation tests
pytest tests/test_validation_rules.py -v

# Run specific rule tests
pytest tests/test_validation_rules.py::TestV012 -v

# Run with coverage
pytest tests/test_validation_rules.py --cov=reveal/rules/validation --cov-report=term-missing
```

---

## Implementation Strategy

### Phase 1: Simple Rules (4 hours)
- V012, V013, V015 (documentation count checks)
- V016 (adapter help)
- **Deliverable**: 4 test classes, ~50 tests

### Phase 2: Adapter Rules (6 hours)
- V018 (renderer registration)
- V019 (initialization patterns)
- V020 (element/structure contract)
- **Deliverable**: 3 test classes, ~40 tests

### Phase 3: Complex Rules (6 hours)
- V017 (tree-sitter coverage)
- V021 (regex vs tree-sitter)
- V022 (manifest inclusion)
- V023 (output contract)
- **Deliverable**: 4 test classes, ~50 tests

### Total Estimated Time: 16 hours

---

## Success Criteria

1. **Coverage Target**: 70%+ for each V-series rule
2. **Test Count**: ~140 new tests added
3. **Test Pass Rate**: 100% (all tests passing)
4. **Code Quality**: Follow existing test patterns
5. **Documentation**: Clear test descriptions and docstrings

---

## Risk Assessment

### Low Risk
- V012, V013, V015: Simple pattern matching, straightforward logic
- V016: Class detection is well-established pattern

### Medium Risk
- V018: Registry mocking might be complex
- V017: Parsing method bodies requires careful regex

### High Risk
- V019, V020: Adapter instantiation might fail due to dependencies
  - **Mitigation**: Mock adapter classes instead of instantiating
- V021: AST parsing and language inference
  - **Mitigation**: Focus on string patterns for language detection
- V022: File system state dependencies
  - **Mitigation**: Use tempfile extensively
- V023: Code pattern detection is brittle
  - **Mitigation**: Use flexible patterns, accept false negatives

---

## Next Steps

1. ✅ **Analysis Complete** - All 11 rules documented
2. ⏭️ **Design Test Cases** - Create detailed test specs (this document)
3. ⏭️ **Implement Tests** - Write test code in test_validation_rules.py
4. ⏭️ **Run and Verify** - Execute tests, measure coverage
5. ⏭️ **Document Results** - Update session README with results

---

**Document Status**: COMPLETE
**Next Action**: Begin test implementation (Phase 1)
