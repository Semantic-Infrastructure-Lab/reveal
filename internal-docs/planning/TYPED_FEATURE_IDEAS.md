# Typed Architecture: Feature Ideas

Potential features enabled by reveal's type-first architecture with decorator extraction.

## Status Legend
- **[EASY]** - Small change, hours of work
- **[MEDIUM]** - Moderate complexity, day of work
- **[HARD]** - Significant effort, multiple days

---

## 1. New `--check` Rules for Decorator Patterns

**[MEDIUM]** Detect common decorator-related bugs and anti-patterns.

### Proposed Rules

| Rule | Description | Example |
|------|-------------|---------|
| D001 | `@property` with no return statement | Likely bug - property returns None |
| D002 | `@staticmethod` with `self` parameter | Wrong decorator - should be regular method |
| D003 | `@classmethod` without `cls` parameter | Missing required first parameter |
| D004 | `@property` body too complex (>10 lines) | Properties should be simple getters |
| D005 | Conflicting decorators | `@property` + `@staticmethod` on same method |
| D006 | `@abstractmethod` in non-ABC class | Abstract method in concrete class |

### Implementation
```python
# In reveal/rules/decorators/D002.py
class StaticmethodWithSelf(BaseRule):
    code = "D002"
    message = "@staticmethod should not have 'self' parameter"

    def check(self, element: PythonElement) -> List[Issue]:
        if '@staticmethod' in element.decorators:
            if element.signature.startswith('(self'):
                return [Issue(self.code, self.message, element.line)]
        return []
```

---

## 2. AST Query by Decorator

**[MEDIUM]** Extend `ast://` adapter to query by decorator.

### Proposed Syntax
```bash
# Find all properties
reveal 'ast://src/?decorator=property'

# Find all cached functions (wildcard)
reveal 'ast://src/?decorator=*cache*'

# Find all abstract methods
reveal 'ast://src/?decorator=abstractmethod'

# Combine with existing queries
reveal 'ast://src/?decorator=property&lines>10'  # Complex properties
```

### Implementation
Add decorator filtering to `ASTQueryAdapter._matches_query()`:

```python
def _matches_query(self, element: TypedElement, query: dict) -> bool:
    # Existing: type, name, complexity, lines

    # New: decorator matching
    if 'decorator' in query:
        pattern = query['decorator']
        if not any(fnmatch(d, f'@{pattern}') for d in element.decorators):
            return False

    return True
```

---

## 3. Category Filtering in `--typed` Output

**[EASY]** Filter `--typed` output by element category.

### Proposed Syntax
```bash
reveal app.py --typed --filter=property       # Show only properties
reveal app.py --typed --filter=staticmethod   # Show only staticmethods
reveal app.py --typed --filter=class          # Show only classes
reveal app.py --typed --filter=method         # Show only methods (exclude nested functions)
```

### Implementation
Add `--filter` flag to CLI, filter in `render_typed_structure()`.

---

## 4. API Surface Detection

**[MEDIUM]** Automatically identify the public API of a module.

### Proposed Command
```bash
reveal app.py --api

# Output:
Public API for app.py:

Classes:
  Config (dataclass)
    - name: str (attribute)
    - value: int (attribute)

  Handler
    - name (property, read-only)
    - process(data) → Result
    - validate(x) → bool (static)

Functions:
  - create_handler(config) → Handler
```

### Logic
- Exclude `_private` and `__dunder__` (except `__init__`)
- Include `@property` (as attributes)
- Mark `@staticmethod`, `@classmethod`
- Include public module-level functions
- Respect `__all__` if defined

---

## 5. Decorator Statistics

**[EASY]** Show decorator usage statistics for a codebase.

### Proposed Command
```bash
reveal src/ --decorator-stats

# Output:
Decorator Usage in src/ (42 files):

@property          23 occurrences (12 files)
@staticmethod      15 occurrences (8 files)
@dataclass         11 occurrences (6 files)
@lru_cache          8 occurrences (4 files)
@classmethod        7 occurrences (5 files)
@abstractmethod     4 occurrences (2 files)
@cached_property    3 occurrences (2 files)
@pytest.fixture     3 occurrences (1 file)

Custom decorators:
@retry              5 occurrences (3 files)
@validate_input     4 occurrences (2 files)
```

---

## 6. Inheritance-Aware Structure

**[HARD]** Show inherited methods and overrides.

### Proposed Output
```bash
reveal models.py --typed --inheritance

User (class) [10-50] extends BaseModel
  id (attribute) - inherited from BaseModel
  name (attribute) [12]
  @property email() (property) [15-18]
  save() (method) [20-30] - overrides BaseModel.save()
  validate() (method) [32-40] - inherited from BaseModel
```

### Requirements
- Parse class bases from AST
- Track which methods are overrides vs inherited
- Handle multiple inheritance

---

## 7. Semantic Diff

**[HARD]** Diff at the semantic level, not line level.

### Proposed Command
```bash
reveal diff HEAD~1 --typed

# Output:
Semantic changes in src/handler.py:

Modified:
  Handler.process()
    - Added @lru_cache decorator
    - Changed return type: Optional[Result] → Result
    - +12 lines, -3 lines

Added:
  Handler.validate() (staticmethod)

Removed:
  Handler._old_helper() (was nested in process())

Moved:
  standalone_util() → utils.py
```

---

## 8. Type Stub Generation

**[MEDIUM]** Generate `.pyi` type stubs from typed structure.

### Proposed Command
```bash
reveal app.py --stub > app.pyi
```

### Output
```python
# app.pyi - generated by reveal
from typing import Optional

class Config:
    name: str
    value: int

class Handler:
    def __init__(self, config: Config) -> None: ...
    @property
    def name(self) -> str: ...
    def process(self, data: dict) -> Result: ...
    @staticmethod
    def validate(x: Any) -> bool: ...
```

---

## 9. Decorator-Aware Complexity Metrics

**[EASY]** Adjust complexity scoring based on decorators.

### Proposal
- `@property` with high complexity is worse than regular method (properties should be simple)
- `@lru_cache` functions should be pure (flag side effects)
- `@abstractmethod` with implementation is suspicious

### Example Rule
```
C906: @property 'user_data' has complexity 8 (max recommended: 3)
      Properties should be simple getters. Consider refactoring to a method.
```

---

## 10. Cross-Reference Index

**[HARD]** Build index of decorator usage across codebase.

### Proposed Command
```bash
reveal src/ --index decorators

# Creates .reveal/decorator-index.json
{
  "@property": ["src/models.py:User.name", "src/models.py:User.email", ...],
  "@lru_cache": ["src/cache.py:fetch_data", "src/api.py:get_user", ...],
  "@dataclass": ["src/models.py:Config", "src/dto.py:Request", ...]
}
```

### Use Case
LLM agents can quickly find all usages of a decorator pattern without scanning files.

---

## Priority Recommendation

### ✅ Implemented in v0.23.0
1. **Category filtering** (#3) - `--filter` flag ✅
2. **Decorator statistics** (#5) - `--decorator-stats` ✅
3. **Decorator bug rules** (#1) - B002, B003, B004 ✅
4. **AST decorator query** (#2) - `decorator=*pattern*` ✅

### Next Up
5. **API surface detection** (#4) - [MEDIUM], documentation use case

### Future Exploration
6. **Inheritance-aware structure** (#6) - [HARD], OOP codebases
7. **Semantic diff** (#7) - [HARD], code review game-changer
