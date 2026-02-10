---
date: 2026-02-10
session: bright-slayer-0210
type: planning
source: nebular-droid-0209 architecture review
status: active
---

# Architecture Improvements Roadmap

**Source**: Comprehensive architecture review from nebular-droid-0209 (2026-02-09)
**Context**: After "pit of success" improvements (Result type, enhanced errors, type hints)
**Current State**: Architecture grade A- (4.5/5), aiming for A+

---

## Overview

This document captures architecture improvement recommendations from the comprehensive review conducted in session nebular-droid-0209. The review analyzed 25+ files across 8 design patterns and identified specific opportunities to improve developer experience.

**What's Already Done** ✅:
- Result type for type-safe error handling (`reveal/result.py`)
- Enhanced error classes with actionable suggestions (`reveal/errors.py`)
- Improved CLI error messages with context
- Type hints added to core modules (treesitter.py, etc.)
- All 3,090 tests passing with zero regressions

**Architecture Assessment**:
- Grade: **A- (4.5/5)**
- Strengths: World-class adapter pattern, perfect modularity, progressive disclosure
- Opportunities: Developer experience improvements (scaffolding, config introspection, type safety)

---

## Priority 1: Config Introspection Tools (1-2 days)

### Problem
Configuration system is powerful but opaque:
- 5-layer config system (CLI → user → project → adapter → defaults)
- Users struggle with "where did this value come from?"
- Debugging config issues is trial-and-error

### Solution: Config Introspection Commands

**Implementation**:
```bash
reveal config explain file.py
# Output:
# effective_config:
#   max_depth: 3 (from: user config ~/.reveal.yaml)
#   show_imports: true (from: CLI flag --show-imports)
#   complexity_threshold: 10 (from: default)
#
# config_layers:
#   1. CLI flags: --show-imports
#   2. User config: max_depth=3, theme=dark
#   3. Project config: (none)
#   4. Adapter defaults: complexity_threshold=10
#   5. System defaults: format=text

reveal config layers
# Show all config files being loaded

reveal config validate
# Check for config errors, deprecated options
```

**Files to modify**:
- `reveal/config.py` - Add introspection methods
- `reveal/cli/handlers.py` - Add config command handler
- `reveal/docs/CONFIGURATION_GUIDE.md` - Document new commands

**Benefits**:
- Users can debug config issues themselves
- Transparent config resolution
- Better onboarding for new users

**Effort**: 1-2 days
**Impact**: High - Makes complex system transparent

---

## Priority 2: Scaffolding Commands (3-4 days)

### Problem
Creating custom adapters takes 2-4 hours:
- Need to understand adapter contract
- Boilerplate setup (imports, registration, methods)
- Test setup from scratch
- Documentation patterns unclear

### Solution: Scaffolding Commands

**Implementation**:
```bash
reveal scaffold adapter --name github --uri "github://"
# Creates:
# - reveal/adapters/github.py (with template)
# - tests/test_github_adapter.py (with basic tests)
# - reveal/docs/GITHUB_ADAPTER_GUIDE.md (template)

reveal scaffold analyzer --name xyz --extension .xyz
# Creates:
# - reveal/analyzers/xyz.py (with template)
# - tests/test_xyz_analyzer.py (with basic tests)

reveal scaffold rule --code C999 --name custom_complexity
# Creates:
# - reveal/rules/complexity/C999.py (with template)
# - tests/test_C999.py (with test cases)
```

**Templates to create**:
- Adapter template (with registration, structure, query support)
- Analyzer template (with tree-sitter setup, extraction methods)
- Rule template (with detection logic, error messages)

**Files to create**:
- `reveal/cli/scaffold.py` - Scaffolding command handlers
- `reveal/templates/` - Template directory
  - `adapter_template.py.tmpl`
  - `analyzer_template.py.tmpl`
  - `rule_template.py.tmpl`
  - `test_adapter_template.py.tmpl`
  - etc.

**Benefits**:
- Adapter authoring: 2-4 hours → 30 minutes
- Consistent patterns across codebase
- Lower barrier to contribution
- Better documentation by default

**Effort**: 3-4 days
**Impact**: Very high - Dramatically improves extensibility

---

## Priority 3: Complete Type Hints (3-5 days)

### Problem
Type hint coverage is inconsistent:
- Core modules: ~70% coverage
- Some files: 100%, others: 0%
- Many `**kwargs` without TypedDict
- No mypy enforcement in CI

### Solution: Comprehensive Type Coverage

**Implementation Plan**:

**Phase 1: Complete Core Modules** (2 days)
```python
# Files to complete:
- reveal/main.py
- reveal/base.py
- reveal/registry.py
- reveal/config.py
- reveal/elements.py

# Pattern: Add return types, parameter types, remove Any
def get_analyzer(path: str, **kwargs) -> Optional[BaseAnalyzer]:  # Before
def get_analyzer(path: str, config: Config) -> Optional[BaseAnalyzer]:  # After
```

**Phase 2: TypedDict for kwargs** (1-2 days)
```python
# Before
def render_element(element: Element, **options) -> str:

# After
from typing import TypedDict

class RenderOptions(TypedDict, total=False):
    show_source: bool
    max_depth: int
    format: Literal['text', 'json']

def render_element(element: Element, options: RenderOptions) -> str:
```

**Phase 3: Add mypy to CI** (1 day)
```bash
# Add to CI pipeline:
mypy reveal/ --strict --show-error-codes

# Fix any issues found
# Enforce for all new code
```

**Benefits**:
- Better IDE autocomplete
- Catch bugs at compile time
- Self-documenting code
- Easier onboarding

**Effort**: 3-5 days
**Impact**: High - Better developer experience, fewer bugs

---

## Priority 4: Extract Detection Strategies (2-3 days)

### Problem
Analyzer detection logic is mixed with adapter logic:
- Hard to test analyzer detection separately
- Can't easily add new detection methods
- Logic duplicated across adapters

### Solution: Strategy Pattern for Detection

**Current (mixed concerns)**:
```python
def get_analyzer(path: str):
    # Extension detection
    if path.endswith('.py'):
        return PythonAnalyzer()
    # Content detection
    if 'SELECT' in content:
        return SQLAnalyzer()
    # Tree-sitter detection
    # ...
```

**Proposed (strategy pattern)**:
```python
class AnalyzerDetectionStrategy(ABC):
    @abstractmethod
    def detect(self, path: str, content: Optional[str]) -> Optional[str]:
        """Return analyzer name if detected, None otherwise."""

class ExtensionStrategy(AnalyzerDetectionStrategy):
    def detect(self, path: str, content: Optional[str]) -> Optional[str]:
        ext = Path(path).suffix
        return EXTENSION_MAP.get(ext)

class ContentStrategy(AnalyzerDetectionStrategy):
    def detect(self, path: str, content: Optional[str]) -> Optional[str]:
        if content and 'SELECT' in content:
            return 'sql'

class TreeSitterStrategy(AnalyzerDetectionStrategy):
    def detect(self, path: str, content: Optional[str]) -> Optional[str]:
        # Try parsing with tree-sitter

def get_analyzer(path: str) -> Optional[BaseAnalyzer]:
    strategies = [
        ExtensionStrategy(),
        ContentStrategy(),
        TreeSitterStrategy(),
    ]

    for strategy in strategies:
        analyzer_name = strategy.detect(path, content)
        if analyzer_name:
            return REGISTRY.get(analyzer_name)
```

**Benefits**:
- Testable detection logic
- Easy to add new detection methods
- Configurable strategy ordering
- Better separation of concerns

**Effort**: 2-3 days
**Impact**: Medium - Better architecture, easier testing

---

## Priority 5: Rule Mixins/Templates (3-4 days)

### Problem
Writing new rules involves boilerplate:
- Walking AST tree (repeated code)
- Complexity counting (similar patterns)
- Error message formatting
- Test setup

### Solution: Reusable Rule Components

**Mixins**:
```python
class StructureWalkerMixin:
    """Provides tree walking utilities."""
    def walk_nodes(self, node, node_type: str):
        # Reusable tree walking logic

class ComplexityRuleMixin:
    """Provides complexity calculation utilities."""
    def count_decisions(self, node):
        # Standard complexity counting

class RuleMessageMixin:
    """Provides consistent error message formatting."""
    def format_error(self, location, message, suggestions):
        # Consistent error messages
```

**Usage**:
```python
class C999_CustomRule(ComplexityRuleMixin, RuleMessageMixin, BaseRule):
    def check(self, element: Element):
        complexity = self.count_decisions(element.node)
        if complexity > self.threshold:
            return self.format_error(
                location=element.location,
                message=f"Complexity {complexity} exceeds {self.threshold}",
                suggestions=["Break into smaller functions"]
            )
```

**Templates**:
- Complexity rule template
- Structure rule template
- Pattern matching rule template
- Test template for rules

**Benefits**:
- Faster rule authoring
- Consistent error messages
- Less boilerplate
- Easier to maintain

**Effort**: 3-4 days
**Impact**: Medium - Makes rule authoring easier

---

## Priority 6: Dependency Injection (4-5 days)

### Problem
Many classes hardcode dependencies:
```python
class MyAdapter:
    def __init__(self):
        self.analyzer = get_analyzer()  # Hardcoded
        self.config = load_config()      # Hardcoded
```

**Issues**:
- Hard to test (can't mock dependencies)
- Inflexible (can't swap implementations)
- Tight coupling

### Solution: Constructor Injection

**Before**:
```python
class MySQLAdapter:
    def __init__(self, uri: str):
        self.connection = create_connection(uri)  # Hardcoded
```

**After**:
```python
class MySQLAdapter:
    def __init__(self, uri: str, connection_factory: ConnectionFactory):
        self.connection = connection_factory.create(uri)  # Injected
```

**Testing becomes easy**:
```python
def test_mysql_adapter():
    mock_factory = MockConnectionFactory()
    adapter = MySQLAdapter("mysql://test", mock_factory)
    # Now we can control connection behavior in tests
```

**Implementation**:
- Identify classes with hardcoded dependencies
- Add constructor parameters
- Create factory classes where needed
- Update tests to use injection

**Benefits**:
- Easier testing
- More flexible
- Better testability
- Cleaner architecture

**Effort**: 4-5 days
**Impact**: Medium - Better long-term maintainability

---

## Lower Priority (Nice to Have)

### Priority 7: Interactive Documentation (`reveal learn`)

**Concept**:
```bash
reveal learn adapters
# Interactive tutorial on adapter system

reveal learn queries
# Interactive query syntax tutorial

reveal learn rules
# Interactive rule development tutorial
```

**Effort**: 5-6 days
**Impact**: Low - Nice UX improvement but docs already good

---

### Priority 8: Configuration GUI (`reveal config ui`)

**Concept**:
```bash
reveal config ui
# Opens browser with config builder
# Visual config editor
# Live validation
```

**Effort**: 8-10 days
**Impact**: Low - CLI is fine for target audience

---

### Priority 9: Plugin Marketplace

**Concept**:
- Central registry of community adapters
- `reveal plugin install github-adapter`
- Versioning and compatibility

**Effort**: 15-20 days
**Impact**: Low - Not needed until larger community

---

## Recommended Implementation Order

### Next 2 Weeks (High ROI)

1. **Config Introspection** (1-2 days)
   - Immediate user benefit
   - Solves real pain point
   - Small, focused scope

2. **Scaffolding Commands** (3-4 days)
   - Dramatically improves extensibility
   - Encourages contributions
   - High impact on adoption

**Total**: 4-6 days of high-impact work

### Next 4 Weeks (Foundation)

3. **Complete Type Hints** (3-5 days)
   - Better developer experience
   - Fewer bugs
   - Gradual improvement

4. **Extract Detection Strategies** (2-3 days)
   - Better architecture
   - Easier testing
   - Sets pattern for future

**Total**: 5-8 days of foundational work

### Next 8 Weeks (Polish)

5. **Rule Mixins/Templates** (3-4 days)
6. **Dependency Injection** (4-5 days)

---

## Success Metrics

**Config Introspection**:
- ✅ Users can debug config without asking for help
- ✅ Config-related support requests drop 50%+
- ✅ Config validation catches errors proactively

**Scaffolding**:
- ✅ New adapter creation time: 2-4 hours → 30 minutes
- ✅ At least 2 community adapters created using scaffolds
- ✅ Contribution guide references scaffolding

**Type Hints**:
- ✅ Core modules at 90%+ type coverage
- ✅ mypy --strict passes in CI
- ✅ No new code without type hints

**Detection Strategies**:
- ✅ Analyzer detection logic fully tested
- ✅ Can add new detection method in <1 hour
- ✅ Tests cover all detection paths

---

## Trade-offs & Decisions

### Why Config Introspection First?

**Decision**: Prioritize config introspection over other features

**Rationale**:
- ✅ Solves real user pain point (config debugging is hard)
- ✅ Small scope (1-2 days)
- ✅ No breaking changes
- ✅ Builds on existing infrastructure

**Alternative**: Start with scaffolding (more impactful but longer)

---

### Why Not Interactive Docs?

**Decision**: Defer interactive documentation

**Rationale**:
- ❌ Current docs are already excellent
- ❌ High effort (5-6 days) for marginal benefit
- ❌ Target audience comfortable with written docs
- ✅ Would be nice-to-have but not essential

---

### Why Type Hints Before DI?

**Decision**: Complete type hints before dependency injection

**Rationale**:
- ✅ Type hints make DI refactoring safer
- ✅ Incremental improvement (can do module by module)
- ✅ Immediate IDE benefits
- ✅ DI refactoring benefits from better types

---

## Integration with Existing Plans

This roadmap complements existing planning documents:

**vs ROADMAP.md**:
- ROADMAP focuses on user-facing features (adapters, queries, rules)
- This focuses on developer experience and internal architecture
- Both are important, this fills the DX gap

**vs CURRENT_PRIORITIES_2026-02.md**:
- Current priorities focus on immediate work (tests, coverage, bugs)
- This provides medium-term architectural improvements
- Sequential: Do current priorities first, then this

**vs STRATEGIC_PRIORITIES_ANALYSIS_2026-02-07.md**:
- Strategic analysis focuses on feature priorities
- This focuses on architecture and developer experience
- Complementary: Features depend on good architecture

---

## Context for Future Sessions

### When to Reference This Document

**Use this document when**:
- Planning developer experience improvements
- Deciding on architectural refactorings
- Onboarding contributors (show them scaffolding exists)
- Someone asks "how do I make Reveal easier to extend?"

**Don't use this document when**:
- Planning user-facing features (use ROADMAP.md)
- Fixing bugs (use CURRENT_PRIORITIES)
- Making strategic decisions (use STRATEGIC_PRIORITIES)

### Key Principles from Architecture Review

1. **Progressive Disclosure** - Start cheap, get more expensive
2. **Adapter Pattern** - Consistent interface, diverse backends
3. **Type Safety** - Catch errors at compile time
4. **Developer Experience** - Make the right thing easy
5. **Pit of Success** - Users naturally fall into good patterns

---

## Related Sessions

- **nebular-droid-0209** - Architecture review + initial improvements
- **turbo-bastion-0209** - Complexity accuracy fixes
- **bright-slayer-0210** - Documentation audit (this session)

---

## Status

- **Created**: 2026-02-10 (session: bright-slayer-0210)
- **Status**: Active planning document
- **Next Review**: After Priority 1-2 completion (config introspection + scaffolding)
- **Owner**: Reveal project maintainers

---

**Summary**: Focus on developer experience improvements that make Reveal easier to extend, debug, and contribute to. Start with config introspection and scaffolding for maximum impact.
