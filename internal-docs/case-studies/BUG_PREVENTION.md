# Bug Prevention Analysis: git:// Routing Bug

**Bug:** CLI routing failed to catch `ValueError` during adapter initialization, only catching `TypeError`. This prevented fallback initialization patterns from being tried.

**Impact:** git:// adapter crashed instead of working correctly.

**Date:** 2026-01-16

---

## Could We Have Caught This Earlier?

### 1. ✅ Integration Tests (We DID catch it!)

**Status:** The bug WAS documented in skipped tests, and integration tests caught it when we ran them.

**What worked:**
- Subprocess-based integration tests revealed real CLI behavior
- Tests were properly skipped with clear documentation of the bug
- Bug was visible and actionable

**Improvement opportunity:**
- Run integration tests more frequently during development
- CI should fail if number of skipped tests increases

---

### 2. ❌ Unit Tests for routing.py (MISSING)

**Current state:**
- `reveal/cli/routing.py` has 67% coverage
- **NO dedicated unit test file** (`tests/test_routing.py` doesn't exist!)
- Most coverage comes from indirect integration tests

**What we should have:**
```python
# tests/test_routing.py

def test_generic_adapter_handler_catches_value_error():
    """Verify ValueError is caught during adapter initialization."""

    class FailsWithValueError:
        def __init__(self):
            raise ValueError("Missing required parameter")

    # Should not raise - should try other initialization patterns
    result = generic_adapter_handler(
        FailsWithValueError,
        MockRenderer,
        "test",
        "resource",
        None,
        args
    )
    # Should handle gracefully, not crash

def test_all_initialization_patterns_tried():
    """Verify all 5 Try blocks are attempted on failures."""
    attempts = []

    class TracksAttempts:
        def __init__(self, *args, **kwargs):
            attempts.append((args, kwargs))
            raise TypeError("Not this pattern")

    generic_adapter_handler(TracksAttempts, ...)
    assert len(attempts) == 5  # All patterns tried

def test_consistent_exception_handling():
    """Verify all Try blocks catch same exception types."""
    # Parse routing.py, extract all try/except blocks
    # Verify they all catch (TypeError, ValueError) consistently
```

**Gap identified:** ❌ No unit tests for routing logic

---

### 3. ⚠️ Static Analysis / Linting (PARTIAL)

**Could pylint/mypy catch this?**
- **No** - This is a logic bug, not a type error
- Static analysis can't know that adapters might raise `ValueError`
- Would need custom linting rule

**Could a custom rule catch it?**
- **Maybe** - A rule could detect inconsistent exception handling patterns
- Example: "Multiple try/except blocks in same function catching different exception types"

---

### 4. ❌ Adapter Contract Tests (MISSING)

**What we should have:**
```python
# tests/test_adapter_contracts.py

@pytest.mark.parametrize("adapter_class", [
    GitAdapter, HelpAdapter, EnvAdapter, AstAdapter, ...
])
def test_adapter_handles_missing_parameters(adapter_class):
    """All adapters should raise TypeError or ValueError for invalid init."""

    # Try initialization with no args
    with pytest.raises((TypeError, ValueError)):
        adapter_class()

    # Try with invalid args
    with pytest.raises((TypeError, ValueError)):
        adapter_class(None)

def test_adapter_error_types_documented():
    """Verify adapter docstrings document what exceptions they raise."""
    for adapter in get_all_adapters():
        init_doc = adapter.__init__.__doc__
        assert "Raises:" in init_doc
        # Check that ValueError/TypeError are documented
```

**Gap identified:** ❌ No contract tests ensuring consistent adapter behavior

---

### 5. 🆕 Reveal Rule: B006 - Inconsistent Exception Handling

**Proposal:** Create a new rule to detect this pattern.

```python
"""B006: Inconsistent exception handling in retry patterns.

Detects functions with multiple try/except blocks that catch different
exception types for similar operations (initialization, retry logic, etc.).
"""

class B006(BaseRule):
    """Detect inconsistent exception handling in similar try/except blocks."""

    code = "B006"
    message = "Inconsistent exception handling in retry pattern"
    category = RulePrefix.B
    severity = Severity.MEDIUM

    def check(self, file_path: str, structure: dict) -> List[Detection]:
        """Find functions with >3 try/except blocks catching different types."""

        # Pattern to detect:
        # 1. Function has multiple try/except blocks (3+)
        # 2. Blocks are doing similar things (variable assignment to same var)
        # 3. Exception types differ between blocks

        # Example:
        # Try 1: except TypeError -> ❌
        # Try 2: except (TypeError, ValueError) -> ✅
        # Try 3: except TypeError -> ❌
        #
        # Should all catch the same exception types
```

**Usefulness:** Medium
- This is a relatively rare pattern
- Most code doesn't have complex retry logic like routing.py
- But when it exists, this bug pattern is subtle and dangerous

---

## Recommended Improvements

### Priority 1: Add Unit Tests for routing.py ⭐⭐⭐

**Effort:** 2-3 hours
**Impact:** HIGH
**Why:** Direct protection, catches bugs early, fast feedback

**Action items:**
1. Create `tests/test_routing.py`
2. Test each initialization pattern (Try 1-5)
3. Test exception handling consistency
4. Test edge cases (None, empty string, special chars)
5. Target: 90%+ coverage of routing.py

**Benefits:**
- Fast (runs in milliseconds vs seconds for integration tests)
- Precise (pinpoints exact failure location)
- Enables TDD for routing changes

---

### Priority 2: Add Adapter Contract Tests ⭐⭐

**Effort:** 1-2 hours
**Impact:** MEDIUM
**Why:** Prevents future adapters from having inconsistent behavior

**Action items:**
1. Create `tests/test_adapter_contracts.py`
2. Test that all adapters handle missing/invalid parameters consistently
3. Test that error messages are helpful
4. Run against all adapters

**Benefits:**
- Ensures new adapters follow conventions
- Documents expected adapter behavior
- Prevents regression

---

### Priority 3: Create B006 Rule ⭐

**Effort:** 3-4 hours
**Impact:** LOW-MEDIUM
**Why:** Detects this pattern proactively, but it's rare

**Action items:**
1. Create `reveal/rules/bugs/B006.py`
2. Implement AST-based detection of inconsistent exception handling
3. Test on routing.py (should have caught this bug)
4. Document in rules README

**Benefits:**
- Catches this class of bugs automatically
- Educates developers about best practices
- Works across any codebase reveal checks

---

### Priority 4: CI Improvements ⭐

**Effort:** 30 minutes
**Impact:** MEDIUM
**Why:** Prevents skipped tests from being ignored

**Action items:**
1. Add CI check: "Fail if skipped tests count increases"
2. Add pre-commit hook: Run integration tests for changed adapters
3. Add coverage gates: Fail if routing.py coverage drops below 80%

**Benefits:**
- Catches regressions immediately
- Makes skipped tests visible
- Forces addressing test failures

---

## Architectural Improvements

### Consider: Adapter Base Class with Validated __init__

**Current:** Each adapter implements its own initialization with different patterns

**Proposed:** Base class with clear initialization contract

```python
class ResourceAdapter(ABC):
    """Base class for all adapters."""

    @classmethod
    @abstractmethod
    def init_patterns(cls) -> List[InitPattern]:
        """Return initialization patterns this adapter supports.

        Returns:
            List of InitPattern enums:
            - NO_ARG: AdapterClass()
            - RESOURCE: AdapterClass(resource)
            - QUERY_PARSE: AdapterClass(path, query)
            - KEYWORD: AdapterClass(base_path=..., query=...)
            - FULL_URI: AdapterClass("scheme://resource")
        """
        pass

    @classmethod
    def validate_init_args(cls, *args, **kwargs) -> None:
        """Validate initialization arguments.

        Raises:
            AdapterInitError: If arguments are invalid (not TypeError/ValueError)
        """
        pass
```

**Benefits:**
- Centralized initialization logic
- Consistent error handling
- Self-documenting adapter capabilities
- Routing.py becomes much simpler

**Drawbacks:**
- Requires refactoring all adapters
- Breaking change
- More complex base class

---

## Summary

| Prevention Method | Exists? | Priority | Effort | Impact |
|------------------|---------|----------|--------|--------|
| Integration tests | ✅ Yes | - | - | HIGH |
| Unit tests (routing) | ❌ No | P1 | 2-3h | HIGH |
| Adapter contracts | ❌ No | P2 | 1-2h | MEDIUM |
| B006 rule | ❌ No | P3 | 3-4h | LOW-MED |
| CI improvements | ⚠️ Partial | P4 | 30m | MEDIUM |
| Adapter base refactor | ❌ No | Future | 8-12h | MEDIUM |

**Immediate actions:**
1. ✅ Create `tests/test_routing.py` with comprehensive unit tests
2. ✅ Create `tests/test_adapter_contracts.py` for all adapters
3. 🤔 Consider B006 rule (if this pattern appears elsewhere)

**This bug was preventable with better test coverage of routing.py.**
