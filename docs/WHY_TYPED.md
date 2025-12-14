# Why Type-First Architecture?

**TL;DR**: Reveal's `--typed` output gives LLM agents semantic understanding of code structure, not just syntax. This enables smarter navigation, targeted queries, and behavior inference from decorators.

## The Problem: Flat Structure Loses Context

Traditional code analysis returns flat lists:

```
functions: [__init__, process, helper, validate, _internal]
classes: [Config, Handler]
```

An LLM seeing this can't answer:
- "Which methods belong to which class?"
- "Is `helper` a utility function or a method?"
- "Is `process` a property or a regular method?"
- "What does `@lru_cache` on `validate` tell us about its behavior?"

## The Solution: Hierarchical Typed Structure

With `--typed`, reveal returns containment relationships and semantic categories:

```
@dataclass Config (class) [1-8]
  name (attribute) [3]
  value (attribute) [4]

Handler (class) [10-85]
  __init__(self, config) (method) [12-18]
  @property name() (property) [20-23]
  @lru_cache process(data) → Result (method) [25-60]
    _helper() (function) [40-50]      # Nested, private
  @staticmethod validate(x) → bool (staticmethod) [62-70]

standalone_util(a, b) → int (function) [75-85]
```

Now an LLM can immediately see:
- `_helper` is nested inside `process`, not a class method
- `name` is a property (getter), not a method to call
- `process` is memoized (`@lru_cache`) - calling it twice with same args is cheap
- `validate` is static - doesn't need instance state
- `Config` is a dataclass - has auto-generated `__init__`, `__repr__`, etc.

## How This Helps LLM Agents

### 1. Targeted Navigation

Instead of reading entire files, agents can navigate to specific elements:

```python
structure = TypedStructure.from_analyzer_output(raw, 'handler.py')

# Navigate directly to what you need
handler = structure / 'Handler'
process_method = handler / 'process'

# Only read the 35 lines of process(), not the 85-line file
print(process_method.source)
```

**Token savings**: 10-50x reduction when you only need specific methods.

### 2. Semantic Queries

Find elements by meaning, not just name:

```python
# Find all properties in the codebase
properties = list(structure.find(lambda el: el.is_property))

# Find all cached functions (memoized)
cached = [el for el in structure.walk() if '@lru_cache' in el.decorators]

# Find all abstract methods (must be implemented)
abstract = [el for el in structure.walk() if '@abstractmethod' in el.decorators]
```

### 3. Behavior Inference from Decorators

Decorators encode behavior that LLMs can reason about:

| Decorator | Inference |
|-----------|-----------|
| `@property` | Read-only access, no arguments, likely cheap |
| `@staticmethod` | No instance state needed, pure function |
| `@classmethod` | Factory pattern, returns new instance |
| `@lru_cache` | Memoized - safe to call repeatedly |
| `@abstractmethod` | Must be overridden in subclasses |
| `@dataclass` | Auto-generated `__init__`, `__eq__`, `__repr__` |
| `@cached_property` | Computed once, then cached on instance |

An LLM seeing `@lru_cache` knows:
- "I can call this function multiple times without performance concern"
- "Results are cached, so same inputs always give same output"
- "This function is likely pure (no side effects)"

### 4. Understanding Code Organization

The containment hierarchy reveals design patterns:

```
# Nested function = implementation detail, not part of public API
Handler (class)
  process (method)
    _helper (function)    # Internal to process()

# Module-level function = utility, potentially public
standalone_util (function)  # At root level
```

### 5. Smarter Refactoring Suggestions

With typed structure, an LLM can make informed suggestions:

- "This `@property` is 50 lines - properties should be simple getters"
- "This `@staticmethod` doesn't use any class context - could be a module function"
- "This class has 15 methods but no `@property` - consider encapsulating attributes"

## Comparison: With vs Without Types

| Task | Without Types | With Types |
|------|---------------|------------|
| "Find the validate method" | Search all functions named `validate` | `structure / 'Handler' / 'validate'` |
| "Is this a property?" | Parse source for `@property` | `element.is_property` |
| "What's inside this class?" | Read entire file, parse manually | `handler.children` |
| "Find all cached functions" | grep for `@lru_cache` | `find(lambda el: '@lru_cache' in el.decorators)` |
| "What category is this?" | Infer from context | `element.display_category` → "staticmethod" |

## Usage

```bash
# CLI: See typed structure
reveal app.py --typed

# CLI: Get JSON for programmatic use
reveal app.py --typed --format=json

# Python: Navigate programmatically
from reveal.structure import TypedStructure
typed = TypedStructure.from_analyzer_output(raw_dict, 'app.py')
```

## Summary

Type-first architecture transforms reveal from "show me the code" to "help me understand the code." For LLM agents operating under token constraints, this semantic understanding is the difference between intelligent navigation and brute-force reading.

**Key benefits:**
1. **Hierarchical context** - Know what contains what
2. **Semantic categories** - property vs method vs staticmethod
3. **Behavior hints** - Decorators reveal intent and constraints
4. **Efficient navigation** - Query and traverse, don't read everything
5. **Informed reasoning** - Make smarter suggestions with richer context
