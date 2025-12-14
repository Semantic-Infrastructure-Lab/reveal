# Type-First Architecture: Elevating Reveal's Type System

**Status:** Phases 1-5 Complete ✅
**Priority:** Medium
**Sessions:** hidden-grove-1213, slate-gem-1213, binary-empire-1213, heating-squall-1213 (2025-12-13)
**Target:** v0.23.0+

**Implementation Status:**
- ✅ Phase 1: TypeRegistry, RevealType, EntityDef
- ✅ Phase 2: TypedElement with navigation
- ✅ Phase 3: TypedStructure container
- ✅ Phase 4: PythonType wired up, factory method
- ✅ Phase 5: `--typed` flag in CLI
- ⏳ Phase 6: Additional types (Markdown, JSON, YAML)
- ⏳ Phase 7: Rules integration

## The Vision

Make `types.py` the source of truth that drives everything:
- Extension → adapter mapping (`.py` → `py://`)
- Containment rules (class contains method)
- Element navigation (Pythonic `.parent`, `.children`, `.walk()`)
- Adapter upgrades (simple → rich analysis)

```
reveal file.py              # Auto-selects PythonType → structure adapter
reveal py://file.py         # Explicit rich adapter for Python files
reveal file.py --rich       # Upgrade to type-specific deep analysis

structure = reveal('app.py')
for method in structure / 'MyClass':  # Pythonic navigation
    print(method.complexity)
```

---

## Current State: Orphaned Scaffolding

`types.py` has 617 lines of unused infrastructure:

```python
# Already exists but not wired in!
'function': Entity(
    properties={'name': str, 'line': int, 'signature': str},
    contains=['variable'],        # ← Containment rules defined
)
'method': Entity(
    inherits='function',          # ← Type inheritance defined
    properties={'parent_class': str}
)

relationships = {
    'calls': relationship(...)    # ← Cross-references defined
}
```

**The gap**: Analyzers emit raw dicts. Types exist but nothing uses them.

```python
# Current: raw dicts, no type awareness
{'name': 'process', 'line': 42, 'signature': '(self, data)'}

# Proposed: typed elements with computed navigation
PythonMethod(name='process', line=42, parent=MyClass@10, children=[...])
```

---

## ✅ Verification (slate-gem-1213)

Design assumptions verified against actual codebase state:

### TreeSitter Already Emits `line_end`

**Original assumption**: Need to update TreeSitter to emit `line_end`.
**Reality**: It already does! (`treesitter.py:132-137`)

```python
# Already in treesitter.py _extract_functions():
functions.append({
    'line': line_start,
    'line_end': line_end,  # ← Already present!
    'name': name,
    'signature': self._get_signature(node),
    'line_count': line_count,
    'depth': self._get_nesting_depth(node),
})
```

Both `_extract_functions()` and `_extract_classes()` emit `line_end`.
**Impact**: Phase 4 is simpler than estimated.

### types.py Confirmed Orphaned

Verified that **zero analyzers** define `self.types` or `self.relationships`:
- `FileAnalyzer._init_type_system()` exists and is ready
- But no subclass provides the type definitions
- Validation code in `display/structure.py` references `_type_registry` but it's always `None`

**Impact**: Can safely replace current types.py without breaking anything.

### Architecture Refactoring Complete

The codebase was refactored (Phases 1-5, branch `refactor/architecture-v1`):
- `main.py`: 2,446 → 287 lines (-88%)
- New packages: `cli/`, `display/`, `rendering/`, `utils/`, `adapters/python/`
- All files under 400 lines

**Impact**: New modular structure makes integration cleaner:
- Type routing logic → `cli/routing.py`
- Structure display → `display/structure.py`
- Element extraction → `display/element.py`

---

## Proposed Architecture

### Layer 1: Type Registry (Source of Truth)

```python
# reveal/types.py - The central registry

from dataclasses import dataclass, field
from typing import List, Dict, Type, Optional
from functools import cached_property

@dataclass
class EntityDef:
    """Defines what an element type can contain."""
    contains: List[str] = field(default_factory=list)
    properties: Dict[str, type] = field(default_factory=dict)
    inherits: Optional[str] = None

@dataclass
class RevealType:
    """Complete type definition for a file format."""
    name: str
    extensions: List[str]
    scheme: str  # URI scheme for rich adapter

    # What elements exist and their containment rules
    entities: Dict[str, EntityDef] = field(default_factory=dict)

    # Adapter chain: mode → adapter class
    adapters: Dict[str, type] = field(default_factory=dict)

    # Element class for typed navigation
    element_class: type = None


class TypeRegistry:
    """Central registry mapping extensions/schemes to types."""
    _types: Dict[str, RevealType] = {}
    _by_extension: Dict[str, RevealType] = {}
    _by_scheme: Dict[str, RevealType] = {}

    @classmethod
    def register(cls, reveal_type: RevealType):
        cls._types[reveal_type.name] = reveal_type
        for ext in reveal_type.extensions:
            cls._by_extension[ext] = reveal_type
        cls._by_scheme[reveal_type.scheme] = reveal_type

    @classmethod
    def from_extension(cls, ext: str) -> Optional[RevealType]:
        return cls._by_extension.get(ext)

    @classmethod
    def from_scheme(cls, scheme: str) -> Optional[RevealType]:
        return cls._by_scheme.get(scheme)
```

### Layer 2: Type Definitions

```python
# reveal/types/python.py

PythonType = RevealType(
    name='python',
    extensions=['.py', '.pyw', '.pyi'],
    scheme='py',

    entities={
        'module': EntityDef(
            contains=['class', 'function', 'import'],
        ),
        'class': EntityDef(
            contains=['method', 'attribute', 'class'],  # nested classes
            properties={'name': str, 'line': int, 'bases': list},
        ),
        'function': EntityDef(
            contains=['function', 'variable'],  # nested functions
            properties={'name': str, 'line': int, 'signature': str, 'depth': int},
        ),
        'method': EntityDef(
            inherits='function',
            properties={'decorators': list},
        ),
    },

    adapters={
        'structure': 'TreeSitterAnalyzer',   # reveal file.py
        'deep': 'PythonDeepAdapter',         # py://file.py
        'ast': 'ASTQueryAdapter',            # ast://file.py
        'runtime': 'PythonRuntimeAdapter',   # python://
    },

    element_class=PythonElement,
)

TypeRegistry.register(PythonType)
```

```python
# reveal/types/markdown.py

MarkdownType = RevealType(
    name='markdown',
    extensions=['.md', '.markdown', '.mdx'],
    scheme='md',

    entities={
        'document': EntityDef(
            contains=['section', 'code_block', 'link'],
        ),
        'section': EntityDef(
            contains=['section', 'code_block', 'link'],  # nested sections
            properties={'name': str, 'line': int, 'level': int},
        ),
        'code_block': EntityDef(
            properties={'language': str, 'line': int, 'content': str},
        ),
    },

    adapters={
        'structure': 'MarkdownAnalyzer',
        'deep': 'MarkdownDeepAdapter',  # md://file.md
    },

    element_class=MarkdownElement,
)
```

```python
# reveal/types/data.py

JsonType = RevealType(
    name='json',
    extensions=['.json'],
    scheme='json',

    entities={
        'object': EntityDef(contains=['key', 'object', 'array']),
        'array': EntityDef(contains=['object', 'array']),
        'key': EntityDef(
            contains=['object', 'array', 'key'],  # nested keys
            properties={'name': str, 'line': int, 'path': str},
        ),
    },

    adapters={
        'structure': 'JsonAnalyzer',
        'deep': 'JsonAdapter',  # Already exists! json://
    },
)

YamlType = RevealType(
    name='yaml',
    extensions=['.yaml', '.yml'],
    scheme='yaml',
    entities=JsonType.entities,  # Same structure model
    adapters={
        'structure': 'YamlAnalyzer',
        'deep': 'YamlDeepAdapter',
    },
)
```

### Layer 3: Typed Elements (Pythonic Navigation)

```python
# reveal/elements.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Iterator, TYPE_CHECKING
from functools import cached_property

if TYPE_CHECKING:
    from .types import RevealType, EntityDef

@dataclass
class TypedElement:
    """Base class for navigable, typed elements."""
    name: str
    line: int
    line_end: int
    category: str  # 'function', 'class', 'section', etc.

    # Internal references (not serialized)
    _type: RevealType = field(repr=False, default=None)
    _siblings: List[TypedElement] = field(repr=False, default_factory=list)

    # === Containment (computed from EntityDef.contains + line ranges) ===

    @cached_property
    def children(self) -> List[TypedElement]:
        """Elements contained within this one."""
        if not self._type:
            return []

        # What categories can this element contain?
        entity_def = self._type.entities.get(self.category)
        if not entity_def:
            return []
        allowed = set(entity_def.contains)

        # Find siblings that are inside our line range and allowed type
        return [
            el for el in self._siblings
            if el.category in allowed and el in self
        ]

    @cached_property
    def parent(self) -> Optional[TypedElement]:
        """The element that contains this one."""
        candidates = [
            el for el in self._siblings
            if self in el and el is not self
        ]
        # Return innermost container (smallest line range)
        if candidates:
            return min(candidates, key=lambda e: e.line_end - e.line)
        return None

    @property
    def depth(self) -> int:
        """Nesting depth (0 = top-level)."""
        return 0 if self.parent is None else self.parent.depth + 1

    # === Python Magic Methods ===

    def __contains__(self, other: TypedElement) -> bool:
        """Support 'child in parent' syntax."""
        if other is self:
            return False
        return self.line <= other.line and other.line_end <= self.line_end

    def __iter__(self) -> Iterator[TypedElement]:
        """Iterate over direct children."""
        return iter(self.children)

    def __truediv__(self, name: str) -> Optional[TypedElement]:
        """Navigate via '/': element / 'child_name'"""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def __getitem__(self, key: str) -> Optional[TypedElement]:
        """Navigate via []: element['child_name']"""
        return self / key

    # === Traversal ===

    def walk(self) -> Iterator[TypedElement]:
        """Depth-first traversal of this element and all descendants."""
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self) -> Iterator[TypedElement]:
        """Walk up the containment chain."""
        current = self.parent
        while current:
            yield current
            current = current.parent

    def find(self, predicate) -> Iterator[TypedElement]:
        """Find descendants matching predicate."""
        for el in self.walk():
            if predicate(el):
                yield el

    # === Path ===

    @cached_property
    def path(self) -> str:
        """Full path: 'MyClass.process.helper'"""
        if self.parent:
            return f"{self.parent.path}.{self.name}"
        return self.name


@dataclass
class PythonElement(TypedElement):
    """Python-specific element with extra properties."""
    signature: str = ''
    decorators: List[str] = field(default_factory=list)

    @property
    def is_method(self) -> bool:
        return self.parent and self.parent.category == 'class'

    @property
    def is_nested_function(self) -> bool:
        return self.parent and self.parent.category == 'function'


@dataclass
class MarkdownElement(TypedElement):
    """Markdown-specific element."""
    level: int = 1

    @property
    def subsections(self) -> List[MarkdownElement]:
        """Direct child sections."""
        return [c for c in self.children if c.category == 'section']
```

### Layer 4: Structure Container

```python
# reveal/structure.py

@dataclass
class TypedStructure:
    """Container for typed elements with navigation."""
    path: str
    reveal_type: RevealType
    elements: List[TypedElement]

    def __post_init__(self):
        # Wire up sibling references for containment computation
        for el in self.elements:
            el._type = self.reveal_type
            el._siblings = self.elements

    # === Category Accessors ===

    @cached_property
    def functions(self) -> List[TypedElement]:
        return [e for e in self.elements if e.category == 'function']

    @cached_property
    def classes(self) -> List[TypedElement]:
        return [e for e in self.elements if e.category == 'class']

    @cached_property
    def imports(self) -> List[TypedElement]:
        return [e for e in self.elements if e.category == 'import']

    # === Top-level (no parent) ===

    @cached_property
    def roots(self) -> List[TypedElement]:
        """Top-level elements only."""
        return [e for e in self.elements if e.parent is None]

    # === Navigation ===

    def __truediv__(self, name: str) -> Optional[TypedElement]:
        """Navigate from root: structure / 'MyClass' / 'method'"""
        for el in self.roots:
            if el.name == name:
                return el
        return None

    def __getitem__(self, path: str) -> Optional[TypedElement]:
        """Path access: structure['MyClass.process']"""
        parts = path.split('.')
        current = self / parts[0]
        for part in parts[1:]:
            if current is None:
                return None
            current = current / part
        return current

    def walk(self) -> Iterator[TypedElement]:
        """All elements, depth-first."""
        for root in self.roots:
            yield from root.walk()

    # === Queries ===

    def find(self, **kwargs) -> Iterator[TypedElement]:
        """Find elements by properties.

        structure.find(category='function', depth=2)
        """
        for el in self.elements:
            if all(getattr(el, k, None) == v for k, v in kwargs.items()):
                yield el
```

### Layer 5: Extension → Adapter Magic

```python
# reveal/cli/routing.py - Updated routing (post-refactoring location)

def get_reveal_type(path_or_uri: str) -> Tuple[RevealType, str, str]:
    """Determine type and adapter mode from path or URI.

    Returns: (reveal_type, mode, resource_path)
    """
    # Check for URI scheme first
    if '://' in path_or_uri:
        scheme, resource = path_or_uri.split('://', 1)
        reveal_type = TypeRegistry.from_scheme(scheme)
        if reveal_type:
            return reveal_type, 'deep', resource

    # Fall back to extension lookup
    ext = Path(path_or_uri).suffix.lower()
    reveal_type = TypeRegistry.from_extension(ext)
    if reveal_type:
        return reveal_type, 'structure', path_or_uri

    return None, None, path_or_uri


def reveal(path_or_uri: str, mode: str = None) -> TypedStructure:
    """Main entry point with type-aware routing.

    reveal('app.py')           → PythonType, structure mode
    reveal('py://app.py')      → PythonType, deep mode
    reveal('app.py', 'deep')   → PythonType, deep mode (explicit)
    """
    reveal_type, detected_mode, resource = get_reveal_type(path_or_uri)
    mode = mode or detected_mode

    if not reveal_type:
        # Fallback to generic TreeSitter
        return _fallback_analyze(resource)

    # Get adapter for mode
    adapter_name = reveal_type.adapters.get(mode, 'structure')
    adapter_class = _resolve_adapter(adapter_name)

    # Run analysis
    raw_structure = adapter_class(resource).get_structure()

    # Upgrade to typed elements
    element_class = reveal_type.element_class or TypedElement
    elements = [
        element_class(**{**item, 'category': category})
        for category, items in raw_structure.items()
        if not category.startswith('_')
        for item in items
    ]

    return TypedStructure(
        path=resource,
        reveal_type=reveal_type,
        elements=elements,
    )
```

---

## Usage Examples

### Basic Navigation

```python
from reveal import reveal

# Analyze Python file
structure = reveal('app.py')

# Pythonic iteration
for cls in structure.classes:
    print(f"Class: {cls.name}")
    for method in cls.children:
        print(f"  Method: {method.name} (depth={method.depth})")

# Path navigation
helper = structure / 'MyClass' / 'process' / 'inner_helper'
print(helper.path)  # "MyClass.process.inner_helper"

# Or string path
helper = structure['MyClass.process.inner_helper']

# Walk all elements
for el in structure.walk():
    if el.depth > 2:
        print(f"Deeply nested: {el.path}")
```

### Queries

```python
# Find all nested functions
nested = list(structure.find(category='function', depth=2))

# Custom predicate
complex_methods = [
    el for el in structure.walk()
    if el.category == 'method' and el.line_end - el.line > 50
]

# Ancestors
method = structure['MyClass.process']
for ancestor in method.ancestors():
    print(f"Inside: {ancestor.name}")
```

### Adapter Upgrade

```python
# Simple analysis (default)
structure = reveal('app.py')

# Rich analysis (type-specific adapter)
structure = reveal('py://app.py')
# or
structure = reveal('app.py', mode='deep')

# AST queries
results = reveal('ast://app.py?complexity>10')
```

### Rules Integration

```python
# reveal/rules/base.py

class BaseRule(ABC):
    def check(
        self,
        file_path: str,
        structure: TypedStructure,  # Now typed!
        content: str,
    ) -> List[Detection]:
        ...


# Example rule using typed navigation
class NestedComplexity(BaseRule):
    """Flag complex nested functions."""

    code = 'C902'

    def check(self, file_path, structure, content):
        detections = []

        for func in structure.find(category='function'):
            if func.depth >= 2:  # Nested
                complexity = self._calculate_complexity(func)
                if complexity > 5:  # Lower threshold for nested
                    detections.append(Detection(
                        file_path=file_path,
                        line=func.line,
                        rule_code=self.code,
                        message=f"Nested function '{func.path}' too complex ({complexity})",
                        context=f"Parent: {func.parent.name if func.parent else 'none'}",
                    ))

        return detections
```

---

## Implementation Phases

### Phase 1: Type Registry Foundation

**Scope**: Create TypeRegistry, RevealType, EntityDef classes

**Files**:
- Replace `reveal/types.py` with new model (safe - current code is unused)
- No backward compatibility needed (verified: zero consumers)

**Effort**: ~3 hours (reduced - no compatibility layer needed)
**Risk**: Low (orphaned code can be replaced freely)

### Phase 2: TypedElement Base Class

**Scope**: Create TypedElement with navigation

**Files**:
- New `reveal/elements.py`
- Implement `__contains__`, `children`, `parent`, `walk()`

**Effort**: ~3 hours
**Risk**: Low (new code, nothing depends on it yet)

### Phase 3: TypedStructure Container

**Scope**: Create structure container with path navigation

**Files**:
- New `reveal/structure.py`
- Implement `__truediv__`, `__getitem__`, `find()`

**Effort**: ~2 hours
**Risk**: Low

### Phase 4: Wire Up Python Type

**Scope**: Define PythonType, integrate with TreeSitterAnalyzer

**Files**:
- New `reveal/types/python.py`
- ~~Update `reveal/treesitter.py` to emit line_end~~ ✅ Already done!
- Test containment computation

**Effort**: ~2 hours (reduced - `line_end` already exists)
**Risk**: Low (no analyzer output changes needed)

### Phase 5: Extension → Scheme Magic

**Scope**: Auto-upgrade `.py` → `py://` when using rich mode

**Files**:
- Update `reveal/cli/routing.py` (refactored location)
- Update `reveal/cli/parser.py` to add `--rich` flag
- Update breadcrumbs to suggest scheme upgrade

**Effort**: ~3 hours
**Risk**: Medium (changes CLI behavior)

### Phase 6: Additional Types

**Scope**: Define MarkdownType, JsonType, YamlType

**Files**:
- New `reveal/types/markdown.py`
- New `reveal/types/data.py`
- Update respective analyzers

**Effort**: ~4 hours per type
**Risk**: Low

### Phase 7: Rules Integration

**Scope**: Update BaseRule to receive TypedStructure

**Files**:
- Update `reveal/rules/base.py`
- Update `reveal/rules/__init__.py` check_file()
- Migrate existing rules

**Effort**: ~4 hours
**Risk**: Medium (changes rule interface)

---

## Migration Strategy

### Backward Compatibility

1. **Raw dict access still works**
   ```python
   # Old way (still works)
   structure = analyzer.get_structure()
   for func in structure.get('functions', []):
       print(func['name'])

   # New way (typed)
   structure = reveal('app.py')
   for func in structure.functions:
       print(func.name)
   ```

2. **Analyzers unchanged initially**
   - Analyzers still emit `Dict[str, List[Dict]]`
   - TypedStructure wraps and upgrades

3. **Gradual rule migration**
   - Rules receive TypedStructure but can access `.raw` for dict

### Version Plan

| Version | Milestone | Estimated Effort |
|---------|-----------|------------------|
| v0.23.0 | TypeRegistry, TypedElement, TypedStructure (Phases 1-3) | ~7 hours |
| v0.24.0 | PythonType wired up, `--rich` flag (Phases 4-5) | ~5 hours |
| v0.25.0 | Additional types, rules migration (Phases 6-7) | ~8+ hours |

**Total revised estimate**: ~20 hours (reduced from ~24 due to `line_end` already present and no backward compatibility needed)

---

## Open Questions

1. **Scheme naming**: `py://` vs `python://`? (python:// is taken for runtime)
   - Proposal: `py://` for files, `python://` for runtime

2. **Deep adapter behavior**: What does `py://file.py` add beyond structure?
   - Type hints extraction
   - Docstring parsing
   - Import resolution
   - Test coverage integration

3. **Performance**: Is `cached_property` enough, or do we need lazy evaluation?
   - Likely fine for files <10K elements
   - Can add `__slots__` if needed

4. **Serialization**: How do TypedElements serialize to JSON?
   - Implement `to_dict()` that strips internal refs
   - Or use dataclasses.asdict with exclude

---

## Benefits Summary

| Before | After |
|--------|-------|
| Raw dicts, no navigation | Pythonic `.parent`, `.children`, `walk()` |
| Manual line-range math | Computed containment from type rules |
| Extension hardcoded in analyzers | TypeRegistry drives everything |
| No upgrade path | `file.py` → `py://file.py` automatic |
| Rules get flat structure | Rules get typed, navigable structure |
| `types.py` unused | Types are first-class citizens |

---

## References

### Current Codebase (post-refactoring)

- `reveal/types.py`: Orphaned scaffolding (617 lines, zero consumers) — safe to replace
- `reveal/treesitter.py`: Extraction with `line_end` already present ✅
- `reveal/cli/routing.py`: URI scheme dispatching (refactored from main.py)
- `reveal/cli/parser.py`: Argument parsing (add `--rich` flag here)
- `reveal/display/structure.py`: Structure display logic
- `reveal/display/element.py`: Element extraction
- `reveal/adapters/json_adapter.py`: Example of "deep" adapter pattern

### External References

- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
- `functools.cached_property`: https://docs.python.org/3/library/functools.html

---

**Last Updated:** 2025-12-13 (slate-gem-1213 — design verification)
