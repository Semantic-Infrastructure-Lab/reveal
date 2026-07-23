"""Tree-sitter based analyzer for multi-language support."""

import hashlib
import logging
import os
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Tuple
from .base import FileAnalyzer
from .complexity import (
    calculate_complexity_and_depth,
    _DECISION_TYPES,
    _NESTING_TYPES,
    _KEYWORD_PAIRS,
)
from .core import disk_cache
from .core import suppress_treesitter_warnings
from .core import node_children as _children
from .core import node_next_sibling as _next_sibling
from .core import iter_tree as _iter_tree
from .core.treesitter_compat import _zero_arg
from .core import tree_root
from .core import ts_parse

# Suppress tree-sitter deprecation warnings (centralized in core module)
suppress_treesitter_warnings()

from tree_sitter_language_pack import get_parser  # noqa: E402

logger = logging.getLogger(__name__)

# Module-level cache: (path_str, mtime_ns) -> {'tree': ..., 'node_cache': ...}
# Eliminates redundant parses when multiple rules/callers analyze the same
# unchanged file (e.g. extract_imports + extract_symbols + extract_exports
# for the same .py file during `reveal --check`).
#
# Bounded LRU: directory scans (stats://, overview) visit each file once so
# the cache provides no hit benefit while growing to hold every file's parse
# tree and node cache in memory indefinitely.  128 entries covers all
# realistic single-file multi-adapter patterns without unbounded growth.
_MAX_PARSE_CACHE = 128
_parse_cache: OrderedDict[Tuple[str, int], Dict[str, Any]] = OrderedDict()

# Cross-invocation disk cache (BACK-535) for the built structure dict
# (imports/functions/classes/structs, pre-slicing). `_parse_cache` above only
# saves the tree-sitter parse within one process; the structure walk itself
# (extraction + complexity + callers-index) is redone from cold every CLI
# invocation. Keyed per-file on (path, mtime_ns, size, language) so one edited
# file invalidates one entry, unlike I002's whole-tree import-graph cache.
_STRUCTURE_CACHE_NAMESPACE = "structure"

# One entry per source file (unlike I002's one-entry-per-project-root), so
# disk_cache's default 64-entry-per-namespace prune cap would thrash on any
# real repo — every file evicted before it's ever reused. Override with
# REVEAL_STRUCTURE_CACHE_MAX_FILES for monorepos past this ceiling.
_DEFAULT_STRUCTURE_CACHE_MAX_FILES = 100_000


def _structure_cache_max_files() -> int:
    """Read the structure-cache entry cap, honoring REVEAL_STRUCTURE_CACHE_MAX_FILES."""
    raw = os.environ.get('REVEAL_STRUCTURE_CACHE_MAX_FILES')
    if raw is None:
        return _DEFAULT_STRUCTURE_CACHE_MAX_FILES
    try:
        return int(raw)
    except ValueError:
        logger.debug("Invalid REVEAL_STRUCTURE_CACHE_MAX_FILES=%r, using default", raw)
        return _DEFAULT_STRUCTURE_CACHE_MAX_FILES


# =============================================================================
# TREE-SITTER NODE TYPE CONSTANTS
# =============================================================================
# Single source of truth for tree-sitter node types across languages.
# Used by treesitter.py and display/element.py for consistent extraction.
#
# MAINTENANCE: When adding new language support, update these lists.
# Run `reveal file.ext --show-ast` to discover node types for new languages.
# =============================================================================

# Node types for function extraction
FUNCTION_NODE_TYPES = (
    'function_definition',   # Python
    'function_declaration',  # Go, C, JavaScript, Kotlin, Swift
    'function_item',         # Rust
    'function_signature',    # Dart
    'method_declaration',    # Java, C#
    'method_definition',     # Ruby
    'function',              # Generic
    'method',                # Ruby
    'Decl',                   # Zig (wraps FnProto + body; see ZigAnalyzer._get_node_name)
    # BACK-638: Java/C# constructors parse to a DISTINCT node kind from
    # method_declaration, not a same-name variant of it. Without this, a
    # constructor's name lookup (--boundary/--effects/--scope/element
    # extraction) fell through _find_element_node's 'function' pass entirely
    # and matched the enclosing class_declaration instead (same string name),
    # silently returning the WHOLE CLASS BODY as the constructor's range —
    # sibling methods' effects leaked into constructor --sideeffects results.
    # Found via the Java sideeffects-recall-oracle loop (BACK-547 third
    # language): reveal RecoveryMetricsCollector.java RecoveryMetricsCollector
    # --boundary showed effects from an unrelated method ~70 lines later.
    'constructor_declaration',  # Java, C#
    # BACK-643: `async function* name() {}` parses to a DISTINCT node kind,
    # 'generator_function_declaration', not a same-name variant of
    # 'function_declaration' — same shape of gap as constructor_declaration
    # above. Verified via direct tree-sitter-typescript parse: a generator
    # declared inside another function's body was entirely absent from
    # get_structure()['functions'] / --outline, and bare-name lookup
    # ('reveal file.ts genName') errored "could not find function or
    # method" even though the enclosing function's --sideeffects correctly
    # included its effects. The whole-tree walk in _find_nodes_by_type
    # already covers any nesting depth once the kind is listed here, so
    # this one addition fixes both outline and name-lookup for the shape.
    'generator_function_declaration',  # JS/TS/TSX generator function statement
    # BACK-478: 'function_definition_statement'/'local_function_definition_statement'
    # used to be listed here as Lua's global/local function kinds. Verified via
    # direct tree-sitter inspection: both `function foo() end` and
    # `local function foo() end` parse to the same 'function_declaration' kind
    # (already covered above) — these two names never matched any real Lua
    # grammar node. Dead entries, removed rather than fixed.
    # Ruby sideeffects-recall-oracle loop (BACK-547 sixth language): `def
    # self.foo` / `def Class.foo` parses to a DISTINCT node kind,
    # 'singleton_method', not a same-name variant of 'method' (`def foo`).
    # BACK-451/477 already added 'singleton_method' to CHILD_NODE_TYPES (so
    # dotted hierarchical lookup like `Class.method_name` worked), but never
    # to FUNCTION_NODE_TYPES/ALL_ELEMENT_NODE_TYPES — the exact same
    # cross-taxonomy fragmentation BACK-638 (Java/C# constructors) and
    # BACK-519 (JS class-field arrows) hit. Without this, every `def self.x`
    # method — the dominant Ruby/Rails idiom for module-level utility, job,
    # and service-object entry points — was entirely invisible to
    # `--outline`/`get_structure()`, and a bare (non-dotted) name lookup for
    # one failed outright ("could not find function or method"), even when
    # the name was unique in the file. Verified live: Discourse's
    # `lib/discourse.rb` (107 `def self.` methods) showed only 6 functions in
    # `--outline`; `reveal discourse.rb allow_dev_populate?` (unique name)
    # errored not-found despite the method existing at line 1321.
    'singleton_method',       # Ruby class method (`def self.foo`/`def Class.foo`)
    # BACK-547 C# sideeffects-recall-oracle pre-flight check (JAVA.md's "notes
    # for the next language" flagged operator overloads specifically as a
    # name-collision-prone node kind worth checking): C# operator overloads
    # (`public static bool operator ==(...)`) parse to their own distinct node
    # kind, `operator_declaration`, not a variant of `method_declaration`.
    # Without this, they were entirely absent from --outline/--boundary/
    # --sideeffects and any name lookup failed outright ("could not find
    # function or method"), unlike BACK-638's constructor gap (which at least
    # fell through to the enclosing class). See _operator_declaration_name for
    # the paired name-extraction fix — the node has no identifier child at
    # all, so the node-type fix alone isn't sufficient.
    'operator_declaration',   # C#
    # BACK-718/BACK-724 (GDScript sideeffects-recall-oracle pre-flight check,
    # seventeenth language): GDScript's `func _init(...)` constructor parses
    # to its OWN distinct node kind, `constructor_definition`, not a variant
    # of `function_definition` (ordinary `func` methods) — the same shape as
    # BACK-638 (Java/C#) and BACK-651 (C# operators), except here the gap is
    # even more total: without this, `_init` was ENTIRELY absent from
    # --outline/get_structure() (not even folded into the enclosing class —
    # GDScript has no wrapping class_declaration node for a top-level script
    # file at all) and a direct name lookup errored outright ("could not
    # find function or method '_init'"), unlike BACK-638's constructor gap
    # (which at least fell through to the enclosing class body). Verified
    # live: samples/gdscript_pixelorama/src/Classes/SteamManager.gd's
    # `_init` (sets `OS.set_environment(...)`, a real corpus `env` oracle
    # positive) was invisible to both --outline and `reveal file.gd _init`.
    # See _constructor_definition_name for the paired name-extraction fix —
    # the identifier "child" is a fixed keyword-shaped leaf whose node KIND
    # literally IS the text `_init` (not a `name`/`identifier` kind any
    # `_name_via_*` strategy recognizes), one node-shape deeper than
    # operator_declaration's gap.
    'constructor_definition',  # GDScript `func _init(...)`
    # Swift `init(...) { ... }` / `deinit { ... }` parse to their OWN
    # distinct node kinds, `init_declaration`/`deinit_declaration`, not a
    # variant of `function_declaration` (plain `func` methods) — same bug
    # class as BACK-638 (Java/C# constructors) and BACK-724 (GDScript
    # `constructor_definition`), found via a pre-flight check before the
    # Swift calls-recall-oracle measurement (BACK-730, tenth language).
    # Without this, every Swift initializer/deinitializer — arguably THE
    # most common lifecycle method in any Swift OOP codebase, since nearly
    # every class/struct declares at least one `init` — was entirely
    # invisible to --outline/get_structure(), and every call made from
    # inside one had no caller scope to attribute to at all (worse than a
    # misattribution: a total edge loss, same shape as BACK-731's
    # decorator-argument gap). Neither node has an identifier child (like
    # GDScript's `_init`, the node KIND itself carries the fixed lifecycle
    # name) — see `_get_node_name`'s special-case branch for the paired
    # name-extraction fix.
    'init_declaration',    # Swift `init(...) { ... }`
    'deinit_declaration',  # Swift `deinit { ... }`
)

# Node types for class extraction
CLASS_NODE_TYPES = (
    'class_definition',           # Python
    'class_declaration',          # Java, C#, JavaScript, PHP
    'abstract_class_declaration', # TypeScript: abstract class Foo { ... }
    'class_specifier',            # C++
    'class',                      # Ruby
    'anonymous_class',            # PHP: new class(...) extends Foo { ... }
    # BACK-478: 'struct_item' (Rust) used to be listed here too ("treated as
    # class"), so every Rust struct was double-counted under both Classes
    # and Structs in get_structure()/--outline (confirmed live). It's a
    # struct, and STRUCT_NODE_TYPES below already extracts it correctly —
    # removed here rather than adding it to keep the label honest.
)

# Node types for struct extraction
STRUCT_NODE_TYPES = (
    'struct_item',           # Rust
    'struct_specifier',      # C/C++
    # BACK-478: this entry was labeled "Go" but is actually C#'s real struct
    # node kind (verified via direct tree-sitter inspection: `struct Foo { }`
    # in C# parses to `struct_declaration`; Go has no node of this kind at
    # all). Go's real struct kind is `struct_type` below — it was entirely
    # absent, so Go structs were invisible to --structs/--outline/--scope
    # regardless of this mislabel.
    'struct_declaration',    # C#
    # Go `type Foo struct { ... }` — the struct body parses as `struct_type`
    # nested inside `type_declaration -> type_spec -> [type_identifier,
    # struct_type]`. Unlike every other member here, struct_type carries no
    # name of its own; see TreeSitterAnalyzer._get_node_name's struct_type
    # branch, which reaches into the parent type_spec for the sibling
    # type_identifier.
    'struct_type',            # Go
)

# Node types for import extraction
IMPORT_NODE_TYPES = (
    'import_statement',      # Python, JavaScript
    'import_declaration',    # Go, Java
    'use_declaration',       # Rust
    'using_directive',       # C#
    'import_from_statement',  # Python
    'preproc_include',       # C/C++
    'namespace_use_declaration',  # PHP: use App\Models\User;
    'import_header',         # Kotlin
)

# Mapping from element type to node types (for element extraction)
ELEMENT_TYPE_MAP = {
    'function': FUNCTION_NODE_TYPES,
    'class': CLASS_NODE_TYPES,
    'struct': STRUCT_NODE_TYPES,
}

# Node types for call expression extraction (call graph)
# Scala type-node kinds that can appear as the constructed type in an
# `instance_expression` (`new X(...)`) — used by _scala_simple_type_name /
# nav_calls._extract_scala_instance_callee to peel qualified/generic types
# down to the simple class name (BACK-747).
_SCALA_TYPE_KINDS = frozenset({
    'type_identifier', 'generic_type', 'stable_type_identifier', 'field_expression',
})

CALL_NODE_TYPES = {
    'call',                    # Python
    'call_expression',         # JS, TS, Go, Rust, C, C++, Kotlin
    'function_call_expression', # PHP
    'member_call_expression',  # PHP $obj->method()
    'object_creation_expression', # PHP new ClassName()
    # PHP `self::method()` / `parent::method()` / `static::method()` /
    # `ClassName::method()` (static/scoped calls) parse to a DISTINCT node
    # kind, 'scoped_call_expression', not a variant of member_call_expression
    # or function_call_expression — entirely absent from CALL_NODE_TYPES
    # meant calls:// silently returned zero callers/callees for the whole
    # class of PHP static-method calls (BACK-736, found via a pre-flight
    # grammar dump before building the calls-recall-oracle PHP measurement,
    # same discovery method as BACK-734/BACK-735). Real-world impact is
    # large: self::/parent::/static:: calls are the dominant idiom for
    # calling sibling static helpers, parent-class overrides, and late
    # static binding in any PHP OOP codebase (WordPress, Laravel, etc).
    # See _callee_name_php_scoped_call for the paired extraction.
    'scoped_call_expression',  # PHP self::/parent::/static::/Class::method()
    'method_call',             # Ruby, Rust (method syntax)
    'method_call_expression',  # Rust
    'invocation_expression',   # C#
    'function_call',           # Lua, Bash
    'method_invocation',       # Java
    # Rust macro invocations (`tracing::debug!(...)`, `println!(...)`,
    # `vec![...]`) are a distinct grammar node, NOT call_expression --
    # entirely invisible to --calls/--sideeffects/--boundary without this
    # (BACK-547 ninth loop, Rust sideeffects-recall-oracle: this was the
    # single dominant recall gap, since Rust logging is done almost
    # exclusively via macros, not calls). child(0) is the macro name
    # (identifier or scoped_identifier, e.g. "tracing::debug") followed by
    # a literal `!` token and a `token_tree` holding the args -- the
    # existing generic callee-extraction fallback (child(0) text) already
    # produces the right callee string with no further special-casing.
    'macro_invocation',         # Rust
    # Scala `new Foo(args)`/`new Foo[T](args)` is a DISTINCT grammar node,
    # 'instance_expression' -- NOT the same node kind as PHP/C#'s
    # 'object_creation_expression' above despite the identical source shape
    # (`new <Name>(...)`). Without this, every Scala constructor call was
    # entirely invisible to --calls/--sideeffects/--boundary (BACK-718/
    # BACK-720, Scala sideeffects-recall-oracle, fifteenth language): real
    # misses included `new File(...)`/`new FileOutputStream(...)`/
    # `new FileInputStream(...)` (java.io interop, GitBucket's dominant
    # non-JGit file-I/O idiom, 100+ corpus call sites) and `new HttpPost(...)`
    # (Apache HttpClient webhook delivery). See
    # nav_calls.py:_extract_scala_instance_callee for the paired callee-text
    # extraction (mirrors _extract_object_creation_callee's "new <Name>"
    # convention already established for PHP/C#, so the same taxonomy
    # pattern shape works unchanged).
    'instance_expression',      # Scala
    # Scala infix method calls: `a :: b`, `list map doubler`, `xs filterNot q`
    # — Scala lets any single-arg method be called without a dot/parens, and
    # operators ARE methods (`a + b` == `a.+(b)`). tree-sitter parses all of
    # these to 'infix_expression', a node kind absent from CALL_NODE_TYPES, so
    # every infix call was silently invisible to calls:// (BACK-746, twelfth
    # calls-recall language). Found via pre-flight grammar dump + a scalameta
    # oracle on GitBucket (96.64% -> 100% recall). See
    # _callee_name_scala_infix (the `operator` field is the method name) and
    # nav_calls.py:_extract_scala_infix_callee for the paired ast:// nav path.
    'infix_expression',         # Scala
    # Swift: any call with an explicit generic type argument — both a
    # generic function call (`identity<Int>(5)`) AND a generic type
    # initializer (`Array<Int>()`, `Dictionary<K, V>()`) — parses to a
    # DISTINCT node kind, 'constructor_expression', not call_expression
    # (found via pre-flight grammar dump before the Swift calls-recall-oracle
    # measurement, tenth language, BACK-730). Entirely absent from
    # CALL_NODE_TYPES meant calls:// silently returned zero callers/callees
    # for every generic call/initializer in a Swift file — a common shape in
    # any Swift codebase using generics (collections, generic helpers). See
    # nav_calls.py:_extract_swift_constructor_callee for the paired
    # callee-text extraction — unlike Scala/PHP's "new <Name>" convention,
    # this node covers plain generic *function* calls too (not always
    # construction), so it emits the bare callee name with no "new" prefix.
    'constructor_expression',   # Swift
    # C++ `new ClassName(args)` / `new NS::ClassName(args)` is a DISTINCT
    # node kind, 'new_expression', not PHP/C#'s 'object_creation_expression'
    # despite the identical source shape — found via a pre-flight grammar
    # dump for the 11th calls-recall-oracle candidate language, C++
    # (BACK-730). Entirely absent from CALL_NODE_TYPES meant calls://
    # silently returned zero callers/callees for every heap-allocated C++
    # constructor call. See nav_calls.py:_extract_cpp_new_callee for the
    # paired callee-text extraction (same "new <Name>" convention as
    # PHP/C#/Scala). NOTE: this does NOT cover C++'s OTHER constructor-call
    # syntax, direct-initialization (`ClassName obj(args);`) — that parses
    # to a `declaration`/`init_declarator` shape with no call-expression-
    # family node at all, a distinct gap needing its own extraction
    # approach, tracked separately (not fixed here).
    'new_expression',           # C++
}

# Callee node types for attribute/member access (self.foo, obj.method, pkg.Func)
CALLEE_ATTRIBUTE_TYPES = {
    'attribute',             # Python: self.bar
    'member_expression',     # JS/TS: obj.method
    'field_expression',      # C/C++: obj.field
    'selector_expression',   # Go: pkg.Func
}

# Parent node types for hierarchical extraction (Class.method)
PARENT_NODE_TYPES = (
    'class_definition', 'class_declaration',
    'class_specifier',        # C++ class (BACK-451)
    'struct_item', 'struct_specifier', 'struct_declaration',
    'impl_item',              # Rust impl blocks
    'interface_declaration',
    'module',                 # Ruby module
    'class',                  # Ruby class (BACK-451/477: was missing entirely,
                               # so Class.method always failed for Ruby classes
                               # regardless of CHILD_NODE_TYPES — verified via
                               # direct tree-sitter inspection, `class Batch`
                               # parses to kind 'class', already used elsewhere
                               # in CLASS_NODE_TYPES but never added here)
    'anonymous_class',        # PHP anonymous class
)

# Child node types for hierarchical extraction (methods within classes)
CHILD_NODE_TYPES = (
    'function_definition', 'function_declaration',
    'method_declaration', 'method_definition',
    'function_item',         # Rust
    'function_signature',    # Dart methods (wrapped in method_signature)
    'method',                # Ruby instance method (`def foo`)
    'singleton_method',      # Ruby class method (`def self.foo`) — BACK-451/477
)

# All element types for line-based extraction
ALL_ELEMENT_NODE_TYPES = (
    'function_definition', 'function_declaration', 'function_item',
    'method_declaration', 'method_definition',
    'class_definition', 'class_declaration',
    'struct_item', 'struct_specifier', 'struct_declaration',
    'anonymous_class',        # PHP anonymous class
)


def build_callers_index(functions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Invert the callees map to produce a within-file callers index.

    Args:
        functions: List of function dicts with 'name' and 'calls' fields.

    Returns:
        Dict mapping function name → sorted list of names that call it (within this file).

    Example:
        [{'name': 'main', 'calls': ['parse', 'run']},
         {'name': 'run',  'calls': ['parse']}]
        → {'parse': ['main', 'run'], 'run': ['main']}
    """
    callers: Dict[str, List[str]] = {}
    for func in functions:
        for callee in func.get('calls', []):
            # Strip attribute prefix for local matching: "self.bar" → "bar"
            local_name = callee.split('.')[-1]
            callers.setdefault(local_name, [])
            if func['name'] not in callers[local_name]:
                callers[local_name].append(func['name'])
    return callers


# Node kinds used to pair a function/method's real name with its argument
# list (BACK-413) — shared between _get_node_name and _get_signature so both
# agree on which parameter_list is the actual signature vs. a receiver
# (Go) or which identifier is the name vs. a bare return type (C#).
#
# 'method_parameters' (Ruby) was missing entirely until the calls-recall-
# oracle Ruby measurement (BACK-730, sixth language): without it,
# `_name_via_param_adjacent` never matched any Ruby method, so naming fell
# through to `_name_via_identifier_kind`'s first-identifier-or-constant-kind
# scan — correct by coincidence for `def foo(x)`/`def self.foo(x)` (the
# method identifier is the only such child), but wrong for `def
# Class.method(x)` singleton methods qualified by a class CONSTANT rather
# than `self` (e.g. `def Report.add_report(...)`): the constant `Report`
# came first positionally and won, so the method was named "Report", not
# "add_report" — every call made from inside one had its caller
# misattributed to the bare class name (real corpus example: Report.rb's
# `add_report`/`remove_report`, both `def Report.xxx` singleton methods).
_NAME_KINDS = ('identifier', 'name', 'constant', 'simple_identifier', 'property_identifier', 'field_identifier')
_PARAM_LIST_KINDS = ('parameters', 'parameter_list', 'formal_parameters', 'method_parameters')


class TreeSitterAnalyzer(FileAnalyzer):
    """Base class for tree-sitter based analyzers.

    Provides automatic extraction for ANY tree-sitter language!

    Subclass just needs to set:
        language (str): tree-sitter language name (e.g., 'python', 'rust', 'go')

    Everything else is automatic:
    - Structure extraction (imports, functions, classes, structs)
    - Element extraction (get specific function/class)
    - Line number tracking

    Usage:
        @register('.go', name='Go', icon='🔷')
        class GoAnalyzer(TreeSitterAnalyzer):
            language = 'go'
            # Done! Full support in 3 lines.
    """

    language: Optional[str] = None  # Set in subclass

    def __init__(self, path: str):
        super().__init__(path)
        self._tree: Optional[Any] = None
        self._tree_parsed: bool = False  # tree is parsed lazily, see `tree` property
        self._node_cache: Optional[Dict[str, List[Any]]] = None  # None = unbuilt; {} = built but empty
        self._content_bytes: Optional[bytes] = None

        # Cache key is cheap (one stat) and computed eagerly — some subclasses
        # (e.g. MarkdownAnalyzer's inline-tree cache) read it right after
        # construction. The expensive part, the actual parse, stays lazy.
        path_str = os.path.abspath(str(self.path))
        try:
            mtime_ns = os.stat(path_str).st_mtime_ns
        except OSError:
            mtime_ns = 0
        self._cache_key: Tuple[str, int] = (path_str, mtime_ns)

    @property
    def tree(self) -> Optional[Any]:
        """Tree-sitter parse tree, parsed on first access.

        Deferred so that a `get_structure()` disk-cache hit (BACK-535) never
        pays the tree-sitter parse cost — the whole point of that cache.
        Anything needing the raw tree directly (import extractors, nav
        adapters, `extract_element`, etc.) still triggers a real parse
        transparently on first touch.
        """
        if not self._tree_parsed:
            self._tree_parsed = True
            if self.language:
                self._parse_tree()
        return self._tree

    @tree.setter
    def tree(self, value: Optional[Any]) -> None:
        self._tree = value
        self._tree_parsed = True

    def _parse_tree(self) -> None:
        """Parse file with tree-sitter.

        Uses a module-level cache keyed by (path, mtime_ns) to avoid
        re-parsing the same unchanged file across multiple analyzer
        instances (e.g. extract_imports, extract_symbols, extract_exports
        all called on the same .py file during --check).

        Note: Tree-sitter warnings are suppressed at module level via
        suppress_treesitter_warnings() call at top of file.
        """
        cached = _parse_cache.get(self._cache_key)
        if cached is not None:
            # Move to end (most-recently-used) on hit
            _parse_cache.move_to_end(self._cache_key)
            self.tree = cached['tree']
            if 'node_cache' in cached:
                self._node_cache = cached['node_cache']
            return

        try:
            parser = get_parser(self.language)  # type: ignore[arg-type]  # language is validated at runtime
            self.tree = ts_parse(parser, self.content)
        except Exception as e:
            logger.debug("tree-sitter parse failed for %s: %s", self.path, e)
            self.tree = None

        if self.tree is not None:
            _parse_cache[self._cache_key] = {'tree': self.tree}
            if len(_parse_cache) > _MAX_PARSE_CACHE:
                _parse_cache.popitem(last=False)  # evict least-recently-used

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract structure using tree-sitter.

        Args:
            head: Show first N semantic units (per category)
            tail: Show last N semantic units (per category)
            range: Show semantic units in range (start, end) - 1-indexed (per category)
            **kwargs: Additional parameters (unused)

        Returns imports, functions, classes, structs, etc.
        Works for ANY tree-sitter language!

        Note: Slicing applies to each category independently
        (e.g., --head 5 shows first 5 functions AND first 5 classes)
        """
        structure = self._get_or_build_structure()
        if not structure:
            return {}

        # Apply semantic slicing to each category. `_apply_semantic_slice`
        # returns new lists (never mutates in place), so slicing a
        # disk-cache hit is safe even though it's shared with future hits.
        if head or tail or range:
            structure = {
                category: self._apply_semantic_slice(items, head, tail, range)
                for category, items in structure.items()
            }

        # Remove empty categories
        return {k: v for k, v in structure.items() if v}

    def _structure_fingerprint(self) -> Optional[str]:
        """Disk-cache key for this file's built structure, or None to skip caching.

        Bound to (path, mtime_ns, size, language) — any edit changes mtime_ns
        (and usually size), and language guards against reusing an entry if a
        path were ever analyzed under a different grammar. Returns None (skip
        cache) on any stat error, so a vanished/unreadable file falls through
        to the uncached (correct) path rather than caching a wrong key.
        """
        try:
            path_str = os.path.abspath(str(self.path))
            st = os.stat(path_str)
        except OSError:
            return None
        hasher = hashlib.sha256()
        hasher.update(path_str.encode("utf-8", "replace"))
        hasher.update(b"\x00")
        hasher.update(str(st.st_mtime_ns).encode("ascii"))
        hasher.update(b"\x00")
        hasher.update(str(st.st_size).encode("ascii"))
        hasher.update(b"\x00")
        hasher.update(str(self.language).encode("utf-8", "replace"))
        return hasher.hexdigest()

    def _get_or_build_structure(self) -> Dict[str, Any]:
        """Return the unsliced structure dict, from disk cache when possible.

        The fingerprint/cache lookup happens before `self.tree` is touched
        anywhere below — `tree` parses lazily on first access, so a cache hit
        here means the file is never even parsed, not just not re-extracted.
        """
        fingerprint = self._structure_fingerprint()
        if fingerprint is not None:
            cached = disk_cache.get(_STRUCTURE_CACHE_NAMESPACE, fingerprint)
            if cached is not None:
                return cached

        if not self.tree:  # first access here triggers the actual parse
            return {}

        structure = {}
        structure['imports'] = self._extract_imports()
        functions = self._extract_functions()
        callers_index = build_callers_index(functions)
        for func in functions:
            func['called_by'] = callers_index.get(func['name'], [])
        structure['functions'] = functions
        structure['classes'] = self._extract_classes()
        structure['structs'] = self._extract_structs()

        if fingerprint is not None:
            disk_cache.put(_STRUCTURE_CACHE_NAMESPACE, fingerprint, structure,
                           max_entries=_structure_cache_max_files())
        return structure

    def _extract_relationships(self, structure: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """Extract intra-file call graph edges from structure.

        Flattens the per-function ``calls`` lists into a flat edge list suitable
        for graph consumers.  Only edges where both endpoints are named are emitted;
        callee names are included as-is (may include attribute access like
        ``self.validate`` or cross-module calls like ``json.dumps``).

        Returns:
            ``{'calls': [{'from': caller_name, 'from_line': line, 'to': callee}, ...]}``
            or ``{}`` if no call data is present.
        """
        edges = []
        for category in ('functions', 'methods'):
            for func in structure.get(category, []):
                caller_name = func.get('name', '')
                caller_line = func.get('line', 0)
                if not caller_name:
                    continue
                for callee in func.get('calls', []):
                    if callee:
                        edges.append({
                            'from': caller_name,
                            'from_line': caller_line,
                            'to': callee,
                        })
        return {'calls': edges} if edges else {}

    def _extract_imports(self) -> List[Dict[str, Any]]:
        """Extract import statements."""
        imports = []

        for import_type in IMPORT_NODE_TYPES:
            nodes = self._find_nodes_by_type(import_type)
            for node in nodes:
                imports.append({
                    'line': node.start_position().row + 1,
                    'content': self._get_node_text(node),
                })

        # Dart wraps both `import` and `export` under one node kind
        # (`import_or_export` -> `library_import` | `library_export`), so
        # a plain node-kind-set entry would also capture exports as imports.
        for node in self._find_nodes_by_type('import_or_export'):
            if any(child.kind() == 'library_import' for child in _children(node)):
                imports.append({
                    'line': node.start_position().row + 1,
                    'content': self._get_node_text(node),
                })

        return imports

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions with complexity metrics and decorators.

        Handles both decorated and undecorated functions across multiple languages.
        """
        functions = []
        processed_funcs = set()  # Track (func_node_line, name) to avoid duplicates

        function_types = self._get_function_node_types()

        # Extract decorated functions first (Python-specific)
        decorated_funcs, decorated_lines = self._extract_decorated_functions(function_types)
        functions.extend(decorated_funcs)
        processed_funcs.update(decorated_lines)

        # Extract undecorated functions
        undecorated_funcs = self._extract_undecorated_functions(function_types, processed_funcs)
        functions.extend(undecorated_funcs)

        functions.extend(self._extract_arrow_functions())
        functions.extend(self._extract_class_field_functions())
        functions.extend(self._extract_lua_function_expressions())

        return functions

    # ── Lua function-expression-as-value (`name = function(...) ... end`) ───
    # BACK-758 (Lua calls-recall-oracle pre-flight, BACK-730 sixteenth
    # language): a bare `function_definition` (Lua's node kind for an
    # anonymous function literal -- coincidentally the same string Python's
    # own `def` uses, but a structurally distinct grammar in this language)
    # carries no name of its own; the name lives on the enclosing
    # assignment/field, exactly the shape `_arrow_or_fn_value` already
    # handles for JS/TS `const f = () => {}`. Without an equivalent here,
    # `local NOOP = function() ... end`, `M.setter = function(x) ... end`
    # (module-table method idiom), bare `setter = function(x) ... end`
    # (no `local`), and table-constructor fields (`{ __call = function()
    # ... end }`, Lua's metatable/dispatch-table idiom) were ALL entirely
    # invisible to get_structure()/--outline -- not just their calls, the
    # whole scope -- found via a real Kong corpus grep (643 occurrences of
    # `= function(` across 176 files). `local function name() ... end` /
    # `function name() ... end` (both `function_declaration`, already
    # extracted above) are unaffected; this only covers the
    # value-is-a-bare-function_definition shape.
    _LUA_ASSIGN_TARGET_KINDS = ('identifier', 'dot_index_expression')

    def _lua_function_expr_name(self, target_node) -> Optional[str]:
        """Return the bare name for a Lua assignment/field target node.

        `identifier` -> its own text; `dot_index_expression` (`M.setter`)
        -> just the final segment, matching `_name_via_dot_index`'s
        existing convention for `function M.setter(...)` declarations.
        """
        kind = _zero_arg(target_node, 'kind')
        if kind == 'identifier':
            return self._get_node_text(target_node)
        if kind == 'dot_index_expression':
            return self._get_node_text(target_node).rsplit('.', 1)[-1]
        return None

    def _lua_table_field_name_value(self, field_node) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a Lua table-constructor `field`
        whose key is a LITERAL identifier (`{ key = function() end }`), or
        (None, None) for a computed key (`{ [expr] = function() end }`) or a
        positional value (no key at all).

        A computed key's bracketed expression (`[CONTENT_TYPE_POST] =
        function...`) also parses its inner expression as a bare
        `identifier` child of the same `field` node -- found via a real
        Kong corpus false positive (`pdk/service/request.lua`'s
        `[CONTENT_TYPE_POST] = function(...)`/`[CONTENT_TYPE_FORM_DATA] =
        function(...)` dynamic dispatch table): naively taking "the first
        identifier child" misattributed the value function's calls to the
        KEY EXPRESSION's name, not a real function name at all. A literal
        string-key field's identifier is always the field's structural
        FIRST child; a computed key's is preceded by a `[` token — that
        ordering is the only reliable distinguishing signal.
        """
        kids = _children(field_node)
        if not kids or _zero_arg(kids[0], 'kind') != 'identifier':
            return None, None
        name_node = kids[0]
        value_node = next(
            (c for c in kids if _zero_arg(c, 'kind') == 'function_definition'), None
        )
        return (name_node, value_node) if value_node else (None, None)

    def _extract_lua_function_expressions(self) -> List[Dict[str, Any]]:
        """Extract `name = function(...) ... end` at assignment or table-field sites.

        `assignment_statement` is Lua-only among reveal's supported grammars
        (a no-op scan everywhere else), so this needs no language gate.
        """
        funcs = []

        # `local NAME = function...` / `NAME = function...` / `M.k = function...`
        for stmt in self._find_nodes_by_type('assignment_statement'):
            kids = _children(stmt)
            try:
                eq_idx = next(i for i, c in enumerate(kids) if _zero_arg(c, 'kind') == '=')
            except StopIteration:
                continue
            targets = [c for c in kids[:eq_idx] if _zero_arg(c, 'kind') == 'variable_list']
            values = [c for c in kids[eq_idx + 1:] if _zero_arg(c, 'kind') == 'expression_list']
            if not targets or not values:
                continue
            target_nodes = [c for c in _children(targets[0]) if _zero_arg(c, 'kind') in self._LUA_ASSIGN_TARGET_KINDS]
            value_nodes = [c for c in _children(values[0]) if _zero_arg(c, 'kind') == 'function_definition']
            for target_node, value_node in zip(target_nodes, value_nodes):
                name = self._lua_function_expr_name(target_node)
                if name:
                    funcs.append(self._build_function_dict(value_node, name, []))

        # Table-constructor field: `{ key = function(...) ... end }`
        for field in self._find_nodes_by_type('field'):
            name_node, value_node = self._lua_table_field_name_value(field)
            if name_node and value_node:
                funcs.append(self._build_function_dict(
                    value_node, self._get_node_text(name_node), []
                ))

        return funcs

    # ── JS-family class-field arrow method (`foo = (...) => {}`) ────────────
    # BACK-519: `public_field_definition` (TS/TSX) / `field_definition` (JS)
    # class members were entirely absent from FUNCTION_NODE_TYPES, so every
    # class method written as an arrow-function field (a common pattern for
    # binding `this`, e.g. React class components) was invisible to
    # get_structure()/calls://check/hotspots/testability/element-nav with no
    # warning. Verified on a real 426KB TSX file (excalidraw's App.tsx): 113
    # such fields class-wide, 0 extracted pre-fix. Only node kinds unique to
    # JS-family grammars, so this is a no-op for every other language.

    _CLASS_FIELD_NODE_TYPES = ('public_field_definition', 'field_definition')

    def _extract_class_field_functions(self) -> List[Dict[str, Any]]:
        """Extract class-field arrow/function-expression methods (`foo = () => {}`)."""
        funcs = []
        for field_type in self._CLASS_FIELD_NODE_TYPES:
            for field_node in self._find_nodes_by_type(field_type):
                name_node = value_node = None
                for ch in _children(field_node):
                    if ch.kind() in ('property_identifier', 'private_property_identifier') and name_node is None:
                        name_node = ch
                    elif ch.kind() in ('arrow_function', 'function_expression'):
                        value_node = ch
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    # ── JS-family arrow-function-as-const (`const f = (...) => {}`) ─────────
    # BACK-431 Issue G tier B dogfood audit (mysterious-probe-0703, real
    # excalidraw source): this pattern was TypeScript/TSX-only special-case
    # logic that get_structure()/--outline used, but plain JavaScript had no
    # equivalent at all (`const f = () => {}` was invisible even to
    # --outline) — and neither language's nav-flag lookup
    # (file_handler._find_element_node) called it, so `reveal file.ts f
    # --varflow x` failed with "could not find function" for a function
    # --outline listed a moment earlier. Promoted here so every JS-family
    # grammar (lexical_declaration is JS/TS/TSX/JSX-specific — a no-op for
    # every other language) gets both get_structure() coverage and nav-flag
    # resolution from one shared implementation.

    def _arrow_or_fn_value(self, variable_declarator_node) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a variable_declarator, or (None, None).

        BACK-726 (sideeffects-recall-oracle/tsx, eighteenth language, pre-flight
        check on a synthetic HOC-wrapped component): `const Name =
        React.forwardRef((props, ref) => {...})` / `React.memo(...)` — the
        dominant "named component wrapped in a higher-order function" shape in
        modern React/TSX (47 corpus occurrences of forwardRef/memo alone in
        samples/tsx/excalidraw) — was entirely invisible to both
        get_structure()/--outline and bare-name lookup. The declarator's value
        child is a `call_expression` (the HOC call), not a bare
        `arrow_function`/`function_expression`/`generator_function` directly,
        so the original direct-child-kind check never matched at all — same
        "wrapped one level deeper than the direct-child check expects" shape as
        prior loops' constructor/instance_expression findings, just one call
        deeper. Fixed by falling through to the call's own direct argument
        list when the value is a call_expression, looking for the single
        function-literal argument (the render/component callback every real
        corpus site — forwardRef, memo, styled-component render props — passes
        as exactly one argument; a curried second call like
        `connect(...)(Component)` has no function literal at this level and is
        correctly left unmatched, not mis-attributed).
        """
        name_node = value_node = None
        for ch in _children(variable_declarator_node):
            if ch.kind() == 'identifier' and name_node is None:
                name_node = ch
            elif ch.kind() in ('arrow_function', 'function_expression', 'generator_function'):
                value_node = ch
            elif _zero_arg(ch, 'kind') == 'call_expression' and value_node is None:
                value_node = self._call_wrapped_function_literal(ch)
        return name_node, value_node

    @staticmethod
    def _call_wrapped_function_literal(call_expression_node) -> Optional[Any]:
        """Return the sole function-literal argument of a call, or None.

        BACK-726: supports the `HOC(...)((...) => {...})` shape — looks only
        at the call's own direct `arguments` list (not nested calls), so a
        curried `outer(...)(inner)` HOC only matches at the level that
        actually carries the function literal.
        """
        for ch in _children(call_expression_node):
            if _zero_arg(ch, 'kind') != 'arguments':
                continue
            candidates = [
                arg for arg in _children(ch)
                if _zero_arg(arg, 'kind') in ('arrow_function', 'function_expression', 'generator_function')
            ]
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _extract_arrow_functions(self) -> List[Dict[str, Any]]:
        """Extract named arrow/function-expression declarations (const X = () => {}),
        at module scope or nested inside another function's body.

        BACK-643: this used to gate on `_is_module_scope_decl`, so a local
        `const name = (...) => {}` declared inside another function's body
        was invisible to both get_structure()/--outline and bare-name
        lookup (`_find_named_arrow_function` below) — even though a plain
        `function name() {}` in the exact same nested position was already
        found at any depth via `_extract_undecorated_functions`'s unscoped
        tree walk. `_arrow_or_fn_value` only matches a variable_declarator
        whose value is an actual function literal, so dropping the scope
        gate only brings named function-valued consts to parity with
        function declarations — it does not start flagging arbitrary local
        variables. As with declaration lookup, an ambiguous name reused at
        multiple nesting depths resolves to the first tree-walk match; a
        qualifier syntax to disambiguate is a separate, larger change.
        """
        funcs = []
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            for child in _children(decl_node):
                if child.kind() != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    def _find_named_arrow_function(self, name: str):
        """Resolve a named arrow/function-expression value to its function
        node, for bare-name lookup by both the plain element extractor
        (display.element._try_treesitter_extraction) and nav-flag lookup
        (file_handler._find_element_node).

        Covers two JS-family shapes that carry their name on a parent node
        rather than the (anonymous) arrow node itself:
          1. `const name = (...) => {}` (lexical_declaration) at module
             scope or nested inside another function's body — BACK-643:
             previously module-scope-only, so a local named arrow-const was
             listed nowhere and this lookup always missed it, and
          2. class-field methods `name = (...) => {}` (public_field_definition
             / field_definition) — BACK-527: previously only get_structure()
             saw these (via _extract_class_field_functions), so they listed in
             --outline but `reveal file.tsx name` returned "not found".
        """
        # 1. `const name = (...) => {}`, module scope or nested
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            for child in _children(decl_node):
                if child.kind() != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node and self._get_node_text(name_node) == name:
                    return value_node

        # 2. class-field arrow method `name = (...) => {}`
        for field_type in self._CLASS_FIELD_NODE_TYPES:
            for field_node in self._find_nodes_by_type(field_type):
                name_node = value_node = None
                for ch in _children(field_node):
                    if ch.kind() in ('property_identifier', 'private_property_identifier') and name_node is None:
                        name_node = ch
                    elif ch.kind() in ('arrow_function', 'function_expression'):
                        value_node = ch
                if name_node and value_node and self._get_node_text(name_node) == name:
                    return value_node

        # 3. Lua `name = function(...) ... end` / `M.k = function(...) ... end`
        # (BACK-758) — assignment_statement is Lua-only, a no-op scan for
        # every other language.
        for stmt in self._find_nodes_by_type('assignment_statement'):
            kids = _children(stmt)
            try:
                eq_idx = next(i for i, c in enumerate(kids) if _zero_arg(c, 'kind') == '=')
            except StopIteration:
                continue
            targets = [c for c in kids[:eq_idx] if _zero_arg(c, 'kind') == 'variable_list']
            values = [c for c in kids[eq_idx + 1:] if _zero_arg(c, 'kind') == 'expression_list']
            if not targets or not values:
                continue
            target_nodes = [c for c in _children(targets[0]) if _zero_arg(c, 'kind') in self._LUA_ASSIGN_TARGET_KINDS]
            value_nodes = [c for c in _children(values[0]) if _zero_arg(c, 'kind') == 'function_definition']
            for target_node, value_node in zip(target_nodes, value_nodes):
                if self._lua_function_expr_name(target_node) == name:
                    return value_node

        # 4. Lua table-constructor field `{ key = function(...) ... end }`
        for field in self._find_nodes_by_type('field'):
            name_node, value_node = self._lua_table_field_name_value(field)
            if name_node and value_node and self._get_node_text(name_node) == name:
                return value_node
        return None

    def _get_function_node_types(self) -> List[str]:
        """Get common function node types across languages."""
        return list(FUNCTION_NODE_TYPES)

    def _extract_decorated_functions(self, function_types: List[str]) -> tuple[List[Dict[str, Any]], set]:
        """Extract decorated functions (Python-specific).

        decorated_definition contains decorator(s) + function/class.
        Returns tuple: (functions_list, tracking_set)
        tracking_set contains (func_node_line, name) for deduplication.
        """
        functions = []
        tracking_lines = set()
        decorated_nodes = self._find_nodes_by_type('decorated_definition')

        for decorated_node in decorated_nodes:
            func_node, decorators = None, []

            # Find function child and collect decorators
            for child in _children(decorated_node):
                if child.kind() in function_types:
                    func_node = child
                elif child.kind() == 'decorator':
                    decorators.append(self._get_node_text(child))

            if func_node:
                name = self._get_node_name(func_node)
                if name:
                    func_dict = self._build_function_dict(
                        node=func_node,
                        decorated_node=decorated_node,
                        name=name,
                        decorators=decorators
                    )
                    functions.append(func_dict)
                    # Track by func_node line (not decorated_node line) for matching
                    func_line = func_node.start_position().row + 1
                    tracking_lines.add((func_line, name))

        return functions, tracking_lines

    def _extract_undecorated_functions(self, function_types: List[str],
                                      processed_funcs: set) -> List[Dict[str, Any]]:
        """Extract undecorated functions across all supported languages."""
        functions = []

        for func_type in function_types:
            nodes = self._find_nodes_by_type(func_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    continue

                line_start = node.start_position().row + 1
                if (line_start, name) in processed_funcs:
                    continue  # Already processed as decorated

                functions.append(self._build_function_dict(
                    node=node,
                    name=name,
                    decorators=[]
                ))

        return functions

    def _build_function_dict(self, node, name: str, decorators: List[str],
                            decorated_node=None) -> Dict[str, Any]:
        """Build function dictionary with metrics.

        Args:
            node: Function node
            name: Function name
            decorators: List of decorator strings
            decorated_node: Optional parent decorated_definition node
        """
        # Use decorated_node bounds if available (includes decorators)
        bounds_node = decorated_node if decorated_node else node
        line_start = bounds_node.start_position().row + 1
        end_node = self._function_end_node(bounds_node)
        line_end = end_node.end_position().row + 1
        # For Dart, end_node is the sibling function_body — walk that for
        # complexity/calls too, or both metrics silently see an empty body
        # (same blindness _function_end_node's docstring describes).
        body_node = end_node if end_node is not bounds_node else node

        complexity, depth, calls = self._complexity_depth_and_calls(body_node)
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': self._get_signature(node),
            'line_count': line_end - line_start + 1,
            'depth': depth,
            'complexity': complexity,
            'decorators': decorators,
            'calls': calls,
        }

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract class definitions with decorators.

        Handles both decorated and undecorated classes across multiple languages.
        """
        classes = []
        processed_classes = set()  # Track (class_node_line, name) to avoid duplicates

        class_types = self._get_class_node_types()

        # Extract decorated classes first (Python-specific)
        decorated_classes, decorated_lines = self._extract_decorated_classes(class_types)
        classes.extend(decorated_classes)
        processed_classes.update(decorated_lines)

        # Extract undecorated classes
        undecorated_classes = self._extract_undecorated_classes(class_types, processed_classes)
        classes.extend(undecorated_classes)

        return classes

    def _get_class_node_types(self) -> List[str]:
        """Get common class node types across languages."""
        return list(CLASS_NODE_TYPES)

    def _extract_decorated_classes(self, class_types: List[str]) -> tuple[List[Dict[str, Any]], set]:
        """Extract decorated classes (Python-specific).

        decorated_definition contains decorator(s) + class.
        Returns tuple: (classes_list, tracking_set)
        tracking_set contains (class_node_line, name) for deduplication.
        """
        classes = []
        tracking_lines = set()
        decorated_nodes = self._find_nodes_by_type('decorated_definition')

        for decorated_node in decorated_nodes:
            class_node, decorators = None, []

            # Find class child and collect decorators
            for child in _children(decorated_node):
                if child.kind() in class_types:
                    class_node = child
                elif child.kind() == 'decorator':
                    decorators.append(self._get_node_text(child))

            if class_node:
                name = self._get_node_name(class_node)
                if name:
                    class_dict = self._build_class_dict(
                        node=class_node,
                        decorated_node=decorated_node,
                        name=name,
                        decorators=decorators
                    )
                    classes.append(class_dict)
                    # Track by class_node line (not decorated_node line) for matching
                    class_line = class_node.start_position().row + 1
                    tracking_lines.add((class_line, name))

        return classes, tracking_lines

    def _get_anonymous_class_name(self, node) -> str:
        """Generate a synthetic name for a PHP anonymous class node.

        Reads the extends/implements clause to produce a descriptive label:
            new class extends NodeVisitorAbstract { ... }
            → 'anonymous(NodeVisitorAbstract)@L144'

        Falls back to 'anonymous@L{line}' when no base class is present.
        """
        line = node.start_position().row + 1
        for child in _children(node):
            if child.kind() == 'base_clause':
                for base_child in _children(child):
                    if base_child.kind() == 'name':
                        base_name = self._get_node_text(base_child)
                        return f'anonymous({base_name})@L{line}'
        return f'anonymous@L{line}'

    def _extract_undecorated_classes(self, class_types: List[str],
                                    processed_classes: set) -> List[Dict[str, Any]]:
        """Extract undecorated classes across all supported languages."""
        classes = []

        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    # PHP anonymous classes have no identifier child — generate a
                    # synthetic name from the extends clause and line number.
                    if node.kind() == 'anonymous_class':
                        name = self._get_anonymous_class_name(node)
                    else:
                        continue

                line_start = node.start_position().row + 1
                if (line_start, name) in processed_classes:
                    continue  # Already processed as decorated

                classes.append(self._build_class_dict(
                    node=node,
                    name=name,
                    decorators=[]
                ))

        return classes

    def _extract_class_bases(self, node) -> List[str]:
        """Extract base class names from a class node.

        Handles:
        - Python: argument_list with identifiers/attributes (ABC, abc.ABC)
        - TypeScript class/abstract_class: class_heritage → extends_clause + implements_clause
        - TypeScript interface: extends_type_clause with type_identifier(s)

        Skips punctuation and keyword arguments (metaclass=...).
        Returns an empty list for classes with no bases.
        """
        node_type = node.kind()
        if node_type in ('class_declaration', 'abstract_class_declaration'):
            return self._extract_ts_class_bases(node)
        if node_type == 'interface_declaration':
            return self._extract_ts_interface_bases(node)
        return self._extract_python_class_bases(node)

    def _extract_ts_class_bases(self, node) -> List[str]:
        # class Foo extends Bar implements IBaz, IQux { ... }
        for child in _children(node):
            if child.kind() == 'class_heritage':
                return self._extract_ts_heritage_bases(child)
        return []

    def _extract_ts_heritage_bases(self, heritage) -> List[str]:
        # BACK-631: the plain-JavaScript grammar has no extends_clause/
        # implements_clause wrapper — `class_heritage` holds the `extends`
        # keyword and the base identifier as flat siblings (TS wraps them in
        # extends_clause). Collect both shapes: nested clause children (TS)
        # and bare identifier/type_identifier children directly under
        # `heritage` (JS) — JS has no `implements`, so only extends applies.
        bases = []
        for heritage_child in _children(heritage):
            if heritage_child.kind() == 'extends_clause':
                bases.extend(self._extract_ts_extends_names(heritage_child))
            elif heritage_child.kind() == 'implements_clause':
                bases.extend(self._extract_ts_implements_names(heritage_child))
            elif _zero_arg(heritage_child, 'kind') in ('identifier', 'type_identifier'):
                text = self._get_node_text(heritage_child).strip()
                if text:
                    bases.append(text)
        return bases

    def _extract_ts_extends_names(self, extends_clause) -> List[str]:
        # extends_clause: "extends <identifier>"
        names = []
        for item in _children(extends_clause):
            if item.kind() in ('identifier', 'type_identifier'):
                text = self._get_node_text(item).strip()
                if text:
                    names.append(text)
        return names

    def _extract_ts_implements_names(self, implements_clause) -> List[str]:
        # implements_clause: "implements TypeA, TypeB, ..."
        names = []
        for item in _children(implements_clause):
            if item.kind() == 'generic_type':
                # e.g. implements IFoo<T> — extract base name
                base = self._extract_generic_type_base(item)
                if base:
                    names.append(base)
            elif item.kind() in ('type_identifier', 'identifier'):
                text = self._get_node_text(item).strip()
                if text:
                    names.append(text)
        return names

    def _extract_generic_type_base(self, generic_type) -> Optional[str]:
        for gchild in _children(generic_type):
            if gchild.kind() == 'type_identifier':
                return self._get_node_text(gchild).strip() or None
        return None

    def _extract_ts_interface_bases(self, node) -> List[str]:
        # interface IFoo extends IBar, IBaz { ... }
        for child in _children(node):
            if child.kind() == 'extends_type_clause':
                bases = []
                for item in _children(child):
                    if item.kind() in ('type_identifier', 'identifier'):
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
                return bases
        return []

    def _extract_python_class_bases(self, node) -> List[str]:
        # class Foo(ABC, abc.Meta, metaclass=ABCMeta): ...
        for child in _children(node):
            if child.kind() != 'argument_list':
                continue
            bases = []
            for item in _children(child):
                if item.kind() in ('identifier', 'attribute'):
                    text = self._get_node_text(item).strip()
                    if text:
                        bases.append(text)
            return bases
        return []

    def _extract_interface_declarations(self, node_kind: str = 'interface_declaration') -> List[Dict[str, Any]]:
        """Extract interface declarations as a standalone list (name, line range, bases).

        Shared by any language whose grammar has a distinct interface node kind
        (Java, C# both use 'interface_declaration', same node name as TS but with
        different heritage-clause shapes — see each analyzer's own
        `_extract_class_bases` override for the real per-language bases logic).
        Mirrors `_TypeScriptBase._extract_ts_types`'s interfaces bucket, generalized
        so BACK-403 pt 2 additions don't each reinvent this walk.
        """
        entries: List[Dict[str, Any]] = []
        for node in self._find_nodes_by_type(node_kind):
            name = self._get_node_name(node)
            if not name:
                continue
            line_start = node.start_position().row + 1
            line_end = node.end_position().row + 1
            entries.append({
                'line': line_start,
                'line_end': line_end,
                'name': name,
                'line_count': line_end - line_start + 1,
                'decorators': [],
                'bases': self._extract_class_bases(node),
            })
        return entries

    def _build_class_dict(self, node, name: str, decorators: List[str],
                         decorated_node=None) -> Dict[str, Any]:
        """Build class dictionary.

        Args:
            node: Class node
            name: Class name
            decorators: List of decorator strings
            decorated_node: Optional parent decorated_definition node
        """
        # Use decorated_node bounds if available (includes decorators)
        bounds_node = decorated_node if decorated_node else node
        line_start = bounds_node.start_position().row + 1
        line_end = bounds_node.end_position().row + 1

        result: Dict[str, Any] = {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'decorators': decorators,
            'bases': self._extract_class_bases(node),
        }
        # TypeScript abstract classes use a distinct node type — flag them so
        # consumers (e.g. contracts command) can distinguish from concrete classes.
        # Other languages (Java, C#) share 'class_declaration' for both and mark
        # abstractness via a modifier keyword instead — see _is_abstract_class_node.
        if node.kind() == 'abstract_class_declaration' or self._is_abstract_class_node(node):
            result['is_abstract'] = True
        return result

    def _is_abstract_class_node(self, node) -> bool:
        """Per-language hook: does this class node carry an 'abstract' modifier?

        Base implementation is a no-op (Python/TS don't need it — Python has no
        abstract-class keyword, TS uses a distinct node kind, handled above).
        Java/C# override this to scan their modifier children.
        """
        return False

    def _extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct definitions (for languages that have them)."""
        structs = []

        for struct_type in STRUCT_NODE_TYPES:
            nodes = self._find_nodes_by_type(struct_type)
            for node in nodes:
                name = self._get_node_name(node)
                if name:
                    line_start = node.start_position().row + 1
                    line_end = node.end_position().row + 1
                    structs.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                    })

        return structs

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific element using tree-sitter.

        Args:
            element_type: 'function', 'class', 'struct', etc.
            name: Name of the element

        Returns:
            Dict with source, line numbers, etc.
        """
        if not self.tree:
            return super().extract_element(element_type, name)

        node_types = ELEMENT_TYPE_MAP.get(element_type, [element_type])

        # Find matching node
        for node_type in node_types:
            nodes = self._find_nodes_by_type(node_type)
            for node in nodes:
                node_name = self._get_node_name(node)
                if node_name == name:
                    end_node = self._function_end_node(node)
                    source = (
                        self._get_node_text(node) if end_node is node
                        else self._get_text_span(node.start_byte(), end_node.end_byte())
                    )
                    return {
                        'name': name,
                        'line_start': node.start_position().row + 1,
                        'line_end': end_node.end_position().row + 1,
                        'source': source,
                    }

        # Fall back to grep
        return super().extract_element(element_type, name)

    def _find_nodes_by_type(self, node_type: str) -> List[Any]:
        """Find all nodes of a given type in the tree.

        Uses single-pass caching: first call walks entire tree once and caches
        ALL node types. Subsequent calls return from cache. This is 5-6x faster
        than walking the tree separately for each node type query.

        Also writes the completed node_cache back into the module-level
        _parse_cache so subsequent analyzer instances for the same unchanged
        file can skip the tree traversal entirely.
        """
        if not self.tree:
            return []

        # Build cache on first access (lazy initialization); None sentinel means unbuilt
        if self._node_cache is None:
            self._node_cache = {}
            cache = self._node_cache
            # BACK-489 P2: a TreeCursor pre-order walk (iter_tree) is ~1.79x
            # faster than the equivalent node_children stack walk and yields
            # the identical node sequence in document order, so each kind's
            # bucket is byte-identical to the old `stack=[root]; pop; push
            # reversed(children)` walk (verified over 557K real nodes).
            for node in _iter_tree(tree_root(self.tree)):
                cache.setdefault(node.kind(), []).append(node)

            # Write completed node_cache back to module-level cache
            if hasattr(self, '_cache_key') and self._cache_key in _parse_cache:
                _parse_cache[self._cache_key]['node_cache'] = self._node_cache
                _parse_cache.move_to_end(self._cache_key)  # refresh LRU position

        return (self._node_cache or {}).get(node_type, [])

    def _get_node_text(self, node) -> str:
        """Get the source text for a node.

        IMPORTANT: Tree-sitter uses byte offsets, not character offsets!
        Must slice the UTF-8 bytes, not the string, to handle multi-byte characters.

        Caches content.encode('utf-8') per instance to avoid re-encoding the
        entire file on every call (hot path: called once per symbol/function/class).
        """
        try:
            if self._content_bytes is None:
                raise AttributeError
            content_bytes = self._content_bytes
        except AttributeError:
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    def _get_text_span(self, start_byte: int, end_byte: int) -> str:
        """Get source text for an arbitrary byte range spanning two nodes
        (e.g. Dart's disjoint function_signature + function_body pair) —
        same byte-not-character slicing rationale as _get_node_text."""
        try:
            if self._content_bytes is None:
                raise AttributeError
            content_bytes = self._content_bytes
        except AttributeError:
            content_bytes = self.content.encode('utf-8')
            self._content_bytes = content_bytes
        return content_bytes[start_byte:end_byte].decode('utf-8')

    def _function_end_node(self, node):
        """Return the node whose end position bounds a function's body.

        Every other FUNCTION_NODE_TYPES member nests its body inside the
        function node itself. Dart's grammar is the odd one out:
        `function_signature` (name + params) and `function_body` are
        SEPARATE sibling nodes, not parent/child. Using the signature node's
        own end position (old behavior) silently truncated every Dart
        function's range to its one-line signature — every nav flag
        (--varflow/--exits/--returns/--ifmap/etc.), plus --outline's
        line_end/line_count, saw an empty range for the entire function body
        (BACK-431 Issue G smoke-tier audit: `--varflow` reported "no
        references found" for a variable declared and read three lines into
        the body).
        """
        if node.kind() == 'function_signature':
            sibling = _next_sibling(node)
            if sibling is None:
                # Methods wrap function_signature in a method_signature node
                # (`class_body: method_signature(function_signature), function_body`)
                # — function_signature is method_signature's only child, so its
                # own next-sibling is None; the real function_body sibling is
                # one level up, next to method_signature (dogfood audit against
                # AppFlowy: every class method showed "[1 lines]" in --outline
                # even after the top-level-function fix above).
                parent = node.parent()
                if parent is not None and parent.kind() == 'method_signature':
                    sibling = _next_sibling(parent)
            if sibling is not None and sibling.kind() == 'function_body':
                return sibling
        return node

    def _struct_type_name(self, node) -> Optional[str]:
        """BACK-478: Go `type Foo struct { ... }` parses the struct body as a
        `struct_type` node with no name-shaped child at all — the name
        (`type_identifier`) is a *sibling* under the shared parent
        `type_spec` (`type_declaration -> type_spec -> [type_identifier,
        struct_type]`), not a descendant. Every other STRUCT_NODE_TYPES
        member carries its own name as a child, so this needs its own
        lookup before the generic child-scanning (which would find nothing
        and return None).
        """
        parent = node.parent()
        if parent is not None:
            for sibling in _children(parent):
                if sibling.kind() == 'type_identifier':
                    return self._get_node_text(sibling)
        return None

    def _operator_declaration_name(self, node) -> Optional[str]:
        """C# `public static bool operator ==(...)` parses to `operator_declaration`,
        whose "name" is the operator symbol itself (`==`, `!=`, `+`, ...) — a
        token whose *node kind literally is* the symbol, not an identifier/name
        kind any `_name_via_*` strategy recognizes. Without this, operator
        overloads carried no name at all: absent from FUNCTION_NODE_TYPES meant
        they were entirely invisible to --outline, and even after adding the
        node kind there, every generic name strategy returned None, silently
        dropping the element (same invisibility class as BACK-638's
        constructor gap, one node deeper). Verified live: samples/csharp
        MediaBrowser.Controller/Library/SearchResult.cs — `operator ==`/
        `operator !=` were entirely absent from --outline before this fix.

        The symbol token is the sibling immediately after the literal
        `operator` keyword child.
        """
        kids = _children(node)
        for i, child in enumerate(kids):
            if _zero_arg(child, 'kind') == 'operator' and i + 1 < len(kids):
                return f'operator {self._get_node_text(kids[i + 1])}'
        return None

    def _constructor_definition_name(self, node) -> Optional[str]:
        """GDScript `func _init(...)` parses to `constructor_definition`,
        whose "name" child is a fixed keyword-shaped leaf whose node KIND
        literally is the text `_init` — not an `identifier`/`name` kind any
        `_name_via_*` strategy recognizes (same invisibility class as
        `_operator_declaration_name`, one node-shape deeper: there the
        symbol was at least reachable via a sibling-of-`operator` lookup;
        here the identifier's kind IS the answer, no text extraction
        needed). Unlike C#/Java constructors (named after the class),
        GDScript's `_init` is a fixed lifecycle-method name — Godot does not
        allow renaming it — so this is a constant return, not a lookup.
        """
        return '_init'

    def _name_via_declarator(self, kids) -> Optional[str]:
        # PRIORITY 1: For C/C++ functions, look inside declarators FIRST —
        # these contain the actual function/variable name, not the type.
        for child in kids:
            if child.kind() in ('function_declarator', 'pointer_declarator', 'declarator'):
                # Recursively search for identifier (may be nested deep)
                name = self._find_identifier_in_tree(child)
                if name:
                    return name
        return None

    def _name_via_param_adjacent(self, kids) -> Optional[str]:
        # PRIORITY 2 (BACK-413): name-kind child immediately preceding a
        # parameter list — the node actually attached to the argument list,
        # not an unrelated identifier-shaped sibling (return type, receiver,
        # etc. — e.g. C# `Task Close()`, Go `func (s *T) Name()`).
        #
        # C# generic methods (`Task Enqueue<T>(...)`, `private T
        # CreateItemByName<T>(...)`) put a `type_parameter_list` node
        # BETWEEN the name and the parameter list, so "immediately
        # preceding" (above) never matches — name-extraction fell through
        # to PRIORITY 2b's first-identifier-child scan, which grabbed the
        # RETURN TYPE instead (it's syntactically first): every generic
        # method's own outline entry, and every call made from inside its
        # body, was misattributed to its return-type name (e.g.
        # `CreateItemByName<T>` -> "T", `Enqueue<T>` -> "Task") — found via
        # the calls-recall-oracle C# measurement (BACK-730, eighth
        # language): real corpus misses on `GetItemById`/
        # `ShouldForceSequentialOperation` traced to callers silently
        # renamed "T"/"Task" in Jellyfin's `LibraryManager.cs`/
        # `LimitedConcurrencyLibraryScheduler.cs`.
        for i, child in enumerate(kids):
            if child.kind() in _PARAM_LIST_KINDS and i > 0:
                prev = kids[i - 1]
                prev_kind = _zero_arg(prev, 'kind')
                if prev_kind in _NAME_KINDS:
                    return self._get_node_text(prev)
                if prev_kind == 'type_parameter_list' and i > 1 and _zero_arg(kids[i - 2], 'kind') in _NAME_KINDS:
                    return self._get_node_text(kids[i - 2])
        return None

    def _name_via_identifier_kind(self, kids) -> Optional[str]:
        # PRIORITY 2b: no adjacent parameter list — first identifier/name child
        # (classes, fields, variables; excludes field_identifier, see PRIORITY 4)
        for child in kids:
            if child.kind() in ('identifier', 'name', 'constant', 'simple_identifier', 'property_identifier'):
                return self._get_node_text(child)
        return None

    def _name_via_dot_index(self, kids) -> Optional[str]:
        # PRIORITY 2c: Lua `function table.name(...)` / `function tbl.a.b(...)`
        # — an extremely common module-method idiom (BACK-431 Issue G tier B
        # dogfood audit: found via real Kong source, `kong/concurrency.lua`'s
        # entire public API is declared this way). The name is a
        # `dot_index_expression` ("concurrency.with_worker_mutex"), a kind
        # absent from every check above; return just the final segment,
        # matching how every other bare-name function lookup in reveal works.
        for child in kids:
            if child.kind() == 'dot_index_expression':
                return self._get_node_text(child).rsplit('.', 1)[-1]
        return None

    def _name_via_method_index(self, kids) -> Optional[str]:
        # PRIORITY 2d (BACK-722 Lua sideeffects-recall-oracle pre-flight):
        # Lua `function table:name(...)` — the colon-method idiom, Lua's
        # closest equivalent to a receiver method (implicitly takes `self`
        # as the first parameter). Verified via real Kong source
        # (kong/db/*.lua, kong/plugins/*/handler.lua) that this is the
        # DOMINANT OOP method-definition idiom in this corpus — more common
        # than the dot form `_name_via_dot_index` already handles. The name
        # is a `method_index_expression` ("connector:query"), a distinct
        # tree-sitter-lua node kind from `dot_index_expression` (same
        # grammar family as Go's `selector_expression` vs Kotlin/Swift's
        # `navigation_expression` split) — absent from every check above,
        # so every `function X:y(...)` was entirely invisible to --outline
        # and errored outright on a direct name lookup before this fix.
        # Return just the final segment, matching every other bare-name
        # function lookup in reveal (and `_name_via_dot_index`'s convention).
        for child in kids:
            if child.kind() == 'method_index_expression':
                return self._get_node_text(child).rsplit(':', 1)[-1]
        return None

    def _name_via_ruby_special_name(self, kids) -> Optional[str]:
        # Ruby `def action_key=(val)` / `def [](k)` / `def ===(other)` — the
        # name is a distinct grammar node kind, not `identifier`: `setter`
        # for assignment-style methods (whose own text is already the full
        # "name=" form) and `operator` for operator-overload-style methods
        # (`[]`, `[]=`, `===`, `<=>`, `+`, ...; whose own text is already the
        # bare symbol). Found via the calls-recall-oracle Ruby measurement
        # (BACK-730, sixth language): setter/operator-named methods were
        # entirely absent from --outline/get_structure(), so every call made
        # FROM inside one had no caller name to attribute to, showing up as
        # residual missed edges in an otherwise ~99% recall run (real corpus
        # examples: WatchedWord#action_key=, TagGroup#parent_tag_name=,
        # Topic#title=, Onebox::Engine#===). Same invisibility class as
        # BACK-651 (C# operator_declaration) and BACK-724 (GDScript
        # constructor_definition) — a name-shaped child whose KIND, not an
        # identifier/name-kind child of it, carries the name.
        for child in kids:
            if _zero_arg(child, 'kind') in ('setter', 'operator'):
                return self._get_node_text(child)
        return None

    def _name_via_swift_operator_function(self, kids) -> Optional[str]:
        # Swift operator overload (`static func -(left: CGPoint, right:
        # CGPoint) -> CGPoint`, `static func *(...)`, `static func *=(...)`)
        # -- the "name" is a literal operator-symbol token whose tree-sitter
        # KIND literally IS the operator text (e.g. kind '-'), not an
        # identifier-family kind any `_name_via_*` strategy above
        # recognizes, and Swift's grammar has no wrapping parameter-list
        # node kind at all (`(`/`parameter`/`)` are direct siblings, not
        # nested under a `parameters`-kind node), so
        # `_name_via_param_adjacent` never even applies to Swift. Found via
        # the calls-recall-oracle Swift measurement (BACK-730, tenth
        # language): every operator overload (CGPoint/CGSize arithmetic --
        # a common idiom in any Swift codebase with custom geometry/value
        # types) was entirely absent from --outline/get_structure(), so
        # every call made from inside one had no caller scope to attribute
        # to at all. Same invisibility class as BACK-651 (C#
        # operator_declaration) and Ruby's `operator` node kind above --
        # here the symbol is a plain sibling token (no wrapping node), so
        # it's found positionally: the sibling immediately after the
        # literal `func` keyword child, only used as a last-resort fallback
        # (i.e. no earlier strategy already found a name).
        for i, child in enumerate(kids):
            if _zero_arg(child, 'kind') == 'func' and i + 1 < len(kids):
                nxt = kids[i + 1]
                nxt_kind = _zero_arg(nxt, 'kind')
                if nxt_kind not in _NAME_KINDS and nxt_kind != '(':
                    return self._get_node_text(nxt)
        return None

    def _name_via_scala_operator_function(self, kids) -> Optional[str]:
        # Scala symbolic-name method definitions: `def +(o)`, `def ::(x)`,
        # `def *` (Slick projection), and any operator overload. The name is
        # an `operator_identifier` node (not an identifier-family kind any
        # earlier strategy recognizes), the sibling right after the `def`
        # keyword. Same invisibility class as Swift's operator overloads
        # (_name_via_swift_operator_function), C#'s operator_declaration, and
        # Ruby's `operator` kind: without this, every symbolic-named def was
        # absent from --outline/get_structure(), so any call inside its body
        # had no caller scope to attribute to. Found via the calls-recall-
        # oracle Scala measurement (BACK-730, twelfth language): the sole
        # residual miss was a `Some(...)` call inside GitBucket's Slick
        # `def *` projection in Repository.scala. Gated on language because
        # Python's function_definition also has a `def` keyword child (always
        # followed by an `identifier`, never an `operator_identifier`).
        if self.language != 'scala':
            return None
        for i, child in enumerate(kids):
            if _zero_arg(child, 'kind') == 'def' and i + 1 < len(kids):
                nxt = kids[i + 1]
                if _zero_arg(nxt, 'kind') == 'operator_identifier':
                    text = self._get_node_text(nxt).strip()
                    if text:
                        return text
        return None

    def _name_via_type_identifier(self, kids) -> Optional[str]:
        # PRIORITY 3: type_identifier (fallback for structs, classes) — only
        # used if no name was found in declarators.
        for child in kids:
            if child.kind() == 'type_identifier':
                return self._get_node_text(child)
        return None

    def _name_via_field_identifier(self, kids) -> Optional[str]:
        # PRIORITY 4: field_identifier (for struct fields)
        for child in kids:
            if child.kind() == 'field_identifier':
                return self._get_node_text(child)
        return None

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a node (function/class/struct name).

        CRITICAL: For functions with return types (C/C++), the tree structure is:
            function_definition:
                type_identifier (return type) - NOT the function name!
                function_declarator (contains actual name)
                    identifier (actual function name!)

        We must search declarators BEFORE looking at type_identifier to avoid
        extracting the return type instead of the function name.

        Tries each `_name_via_*` strategy in priority order (see each
        strategy's own comment for its rationale) and returns the first
        match; `_struct_type_name` is a special case with no name-shaped
        descendant at all, so it's checked before any of them.
        """
        if node.kind() == 'struct_type':
            return self._struct_type_name(node)
        if _zero_arg(node, 'kind') == 'operator_declaration':
            return self._operator_declaration_name(node)
        if _zero_arg(node, 'kind') == 'constructor_definition':
            return self._constructor_definition_name(node)
        if _zero_arg(node, 'kind') == 'init_declaration':
            return 'init'
        if _zero_arg(node, 'kind') == 'deinit_declaration':
            return 'deinit'

        kids = _children(node)
        for strategy in (
            # Scala operator-name defs first: the `operator_identifier` right
            # after `def` is unambiguously the name, but for `def +(o) = o` /
            # `def ::(x) = this` an identifier in the body/params would
            # otherwise be grabbed by _name_via_identifier_kind before this
            # ran (gated on language, so no cost/risk for other languages).
            self._name_via_scala_operator_function,
            self._name_via_declarator,
            self._name_via_param_adjacent,
            self._name_via_identifier_kind,
            self._name_via_dot_index,
            self._name_via_method_index,
            self._name_via_ruby_special_name,
            self._name_via_swift_operator_function,
            self._name_via_type_identifier,
            self._name_via_field_identifier,
        ):
            name = strategy(kids)
            if name:
                return name
        return None

    def _find_identifier_in_tree(self, node) -> Optional[str]:
        """Recursively search for an identifier in a node tree.

        Used to extract names from deeply nested declarators.
        Example: pointer_declarator → function_declarator → identifier

        BACK-451: C++ in-line member functions parse their name as a
        ``field_identifier`` inside the ``function_declarator`` (a free
        function uses a plain ``identifier``). Without it here, every C++
        class method returned no name and was silently dropped from the
        structure entirely — invisible to ``--outline`` and ``Class.method``
        extraction alike.

        BACK-421 part 2: an out-of-line C++ method definition
        (``int Widget::compute(int x) { ... }``) declarator-nests a
        ``qualified_identifier`` (``namespace_identifier`` "Widget", ``::``,
        ``identifier`` "compute"). Plain recursion would find the innermost
        identifier-kind child and return bare "compute", silently dropping
        the class association. Joining every identifier-shaped child of a
        ``qualified_identifier`` with "::" preserves it as "Widget::compute".

        BACK-641: C++ operator overloads and destructors name-node as
        ``operator_name`` (whole-node text e.g. "operator==") and
        ``destructor_name`` (whole-node text e.g. "~Ref") respectively —
        neither is an ``identifier``/``field_identifier``. Without them
        here, an out-of-line ``Vector2::operator==`` collapsed to bare
        "Vector2" (the qualifier only), colliding with the constructor and
        every other operator on the type; an inline ``~Ref() { ... }``
        recursed past ``destructor_name`` into its inner ``identifier``
        child and returned bare "Ref" (dropping the "~"), again colliding
        with the constructor. Found via the C++ sideeffects-recall-oracle
        loop (BACK-547 fourth language) while sanity-checking constructor/
        destructor coverage before trusting any recall numbers.
        """
        if _zero_arg(node, 'kind') in ('operator_name', 'destructor_name'):
            return self._get_node_text(node)

        if _zero_arg(node, 'kind') == 'qualified_identifier':
            parts = [
                self._get_node_text(child)
                for child in _children(node)
                if _zero_arg(child, 'kind') in (
                    'identifier', 'namespace_identifier', 'field_identifier',
                    'type_identifier', 'operator_name', 'destructor_name',
                )
            ]
            if parts:
                return '::'.join(parts)

        # Check current node
        if node.kind() in ('identifier', 'name', 'simple_identifier', 'field_identifier'):
            return self._get_node_text(node)

        # Search children recursively
        for child in _children(node):
            # Skip pointer/reference symbols and parameter lists
            if child.kind() in ('*', '&', 'parameter_list', 'parameters'):
                continue

            name = self._find_identifier_in_tree(child)
            if name:
                return name

        return None

    def _get_signature(self, node) -> str:
        """Get function signature (parameters and return type only).

        CRITICAL (BACK-413): some grammars attach more than one parameter_list
        to a single method node — Go methods carry a receiver parameter_list
        before the name AND, for multi-value returns, a tuple-shaped
        parameter_list after the real params (`func (s *T) F() (int, error)`).
        Blindly taking the last parameter_list child (old behavior) grabs the
        tuple-return list instead of the actual arguments. The real params are
        always the parameter_list immediately after the name (see
        _get_node_name), so that pairing is used here too.
        """
        kids = _children(node)
        params_text = ''
        return_type = ''

        for i, child in enumerate(kids):
            if child.kind() in _PARAM_LIST_KINDS and i > 0 and kids[i - 1].kind() in _NAME_KINDS:
                params_text = self._get_node_text(child)
                break

        if not params_text:
            # No name-adjacent parameter list found (e.g. anonymous
            # functions/lambdas) — fall back to the first one present.
            for child in kids:
                if child.kind() in _PARAM_LIST_KINDS:
                    params_text = self._get_node_text(child)
                    break

        for child in kids:
            if child.kind() in ('return_type', 'type'):
                return_type = ' -> ' + self._get_node_text(child).strip(': ')

        if params_text:
            return params_text + return_type

        # Fallback: try to extract from first line
        text = self._get_node_text(node)
        first_line = text.split('\n')[0].strip()

        # Remove common prefixes (def, func, fn, function, etc.)
        for prefix in ['def ', 'func ', 'fn ', 'function ', 'async def ', 'pub fn ', 'fn ', 'async fn ']:
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix):]
                break

        # Extract just the signature part (name + params + return)
        # Remove the name to leave just params + return type
        if '(' in first_line:
            name_end = first_line.index('(')
            signature = first_line[name_end:].rstrip(':').strip()
            return signature

        # No parens at all — e.g. Ruby's paren-less method defs (`def human?`
        # ... `end`) — there is no parameter signature to show; the
        # remaining text is just the name again, which callers (e.g.
        # display/outline.py's _build_item_display, which concatenates
        # name+signature) would otherwise render as a duplicated name like
        # `human?human?` (BACK-431 tier A real-corpus dogfood audit: found
        # via real Discourse source, app/models/user.rb).
        return ''

    def _get_nesting_depth(self, node) -> int:
        """Return maximum nesting depth within a function node."""
        if not node:
            return 0
        _, depth = calculate_complexity_and_depth(node)
        return int(depth)

    def _calculate_complexity(self, node) -> int:
        """Return cyclomatic complexity for a function node."""
        if not node:
            return 1
        complexity, _ = calculate_complexity_and_depth(node)
        return int(complexity)

    def _calculate_complexity_and_depth(self, node) -> tuple:
        """Compute cyclomatic complexity and max nesting depth."""
        return calculate_complexity_and_depth(node)

    def _callee_name_php_method(self, call_node) -> Optional[str]:
        # PHP: $obj->method() — member_call_expression children are:
        #   receiver (->|?->) name arguments
        receiver_text = None
        method_name = None
        seen_arrow = False
        for child in _children(call_node):
            if child.kind() in ('->', '?->'):
                seen_arrow = True
                continue
            if child.kind() == 'arguments':
                break
            if not seen_arrow:
                receiver_text = self._get_node_text(child)
            else:
                method_name = self._get_node_text(child)
        if method_name:
            return f"{receiver_text}->{method_name}" if receiver_text else method_name
        return None

    def _callee_name_php_scoped_call(self, call_node) -> Optional[str]:
        # PHP: self::method() / parent::method() / static::method() /
        # Class::method() — scoped_call_expression's 'scope' field is
        # either a 'relative_scope' node (self/parent/static keyword) or a
        # plain 'name' node (a class constant), and 'name' is the method
        # being called (BACK-736).
        scope_node = call_node.child_by_field_name('scope')
        name_node = call_node.child_by_field_name('name')
        if name_node is None:
            return None
        name_text = self._get_node_text(name_node)
        if scope_node is None:
            return name_text
        return f"{self._get_node_text(scope_node)}::{name_text}"

    def _callee_name_php_new(self, call_node) -> Optional[str]:
        # PHP: new ClassName() — object_creation_expression
        for child in _children(call_node):
            if child.kind() not in ('new', 'arguments'):
                return f"new {self._get_node_text(child)}"
        return None

    def _callee_name_js_new(self, call_node) -> Optional[str]:
        # JS/TS/TSX: new ClassName(args) / new ns.ClassName(args) —
        # new_expression, the SAME node kind C++ uses (_callee_name_cpp_new
        # below) but a completely different grammar shape: the callee sits
        # in a field named 'constructor' (identifier, or member_expression
        # for a dotted form like `new a.b.ClassName()`), not C++'s 'type'
        # field. child_by_field_name('type') is always None on a JS
        # new_expression, so every `new Foo()` call was silently invisible
        # to calls:// (found via the calls-recall-oracle JS/TSX pre-flight
        # dump, 13th language, BACK-730). Dispatched structurally by
        # _callee_name_new_expression (checks which field is populated)
        # rather than by self.language, so tree-sitter fallback languages
        # with no dedicated analyzer class still resolve correctly.
        ctor_node = call_node.child_by_field_name('constructor')
        if ctor_node is None:
            return None
        kind = _zero_arg(ctor_node, 'kind')
        if kind == 'identifier':
            name = self._get_node_text(ctor_node).strip()
            return f"new {name}" if name else None
        if kind == 'member_expression':
            prop = None
            for child in _children(ctor_node):
                if _zero_arg(child, 'kind') == 'property_identifier':
                    prop = child
            if prop is not None:
                name = self._get_node_text(prop).strip()
                return f"new {name}" if name else None
        return None

    def _callee_name_new_expression(self, call_node) -> Optional[str]:
        # 'new_expression' is shared by C++ and JS/TS/TSX with two mutually
        # exclusive field shapes ('type' vs 'constructor') — dispatch on
        # which field is actually populated rather than self.language, so
        # this stays correct for tree-sitter fallback languages too.
        if call_node.child_by_field_name('constructor') is not None:
            return self._callee_name_js_new(call_node)
        return self._callee_name_cpp_new(call_node)

    def _callee_name_cpp_new(self, call_node) -> Optional[str]:
        # C++: new ClassName(args) / new NS::ClassName(args) — new_expression.
        # A DISTINCT node kind from PHP's object_creation_expression above
        # despite the identical source shape (BACK-730 C++ pre-flight,
        # calls-recall-oracle 11th candidate). child(0) is the literal 'new'
        # token, so the generic _callee_name_generic fallback returned the
        # bare keyword "new" as the callee, not the class name — and unlike
        # Swift's constructor_expression (rescued by _bare_callee_name's
        # generic-suffix stripping since its raw text still carries the real
        # name), "new" has no '<' to strip, so this needed its own dispatch
        # case, same shape as _callee_name_php_new.
        type_node = call_node.child_by_field_name('type')
        if type_node is None:
            return None
        kind = _zero_arg(type_node, 'kind')
        if kind == 'qualified_identifier':
            text = self._get_node_text(type_node).strip()
            if text:
                return f"new {text.split('::')[-1]}"
        text = self._get_node_text(type_node).strip()
        return f"new {text}" if text else None

    def _callee_name_scala_instance(self, call_node) -> Optional[str]:
        # Scala: new ClassName(args) / new ArrayList[String](args) /
        # new java.io.File(args) — instance_expression. A DISTINCT node
        # kind from PHP/C#/C++'s object_creation_expression/new_expression
        # above despite the identical source shape (BACK-730 note #17):
        # child(0) is the literal 'new' token, so the generic
        # _callee_name_generic fallback returned the bare keyword "new" as
        # the callee, not the class name. Mirrors
        # nav_calls.py:_extract_scala_instance_callee (the ast:// nav path,
        # fixed separately under BACK-718/720 — that fix never touched this
        # get_structure()/calls:// path, which is exactly the gap flagged
        # in BACK-730 note #17).
        for child in _children(call_node):
            if _zero_arg(child, 'kind') in _SCALA_TYPE_KINDS:
                name = self._scala_simple_type_name(child)
                if name:
                    return f"new {name}"
        return None

    def _scala_simple_type_name(self, type_node) -> Optional[str]:
        # Simple (last) name of a Scala constructor type, unwrapping every
        # nesting seen in practice:
        #   type_identifier            -> `File`          (new File)
        #   generic_type               -> recurse on base (new Array[Byte])
        #   stable_type_identifier     -> trailing name   (new java.io.File,
        #                                                   BACK-747; also the
        #                                                   base of a qualified
        #                                                   generic new scala.
        #                                                   Array[Byte])
        #   field_expression           -> last dotted seg (older grammar shape)
        kind = _zero_arg(type_node, 'kind')
        if kind == 'type_identifier':
            return self._get_node_text(type_node).strip() or None
        if kind == 'generic_type':
            base = next((c for c in _children(type_node)
                         if _zero_arg(c, 'kind') in _SCALA_TYPE_KINDS), None)
            return self._scala_simple_type_name(base) if base is not None else None
        if kind == 'stable_type_identifier':
            names = [c for c in _children(type_node)
                     if _zero_arg(c, 'kind') == 'type_identifier']
            return (self._get_node_text(names[-1]).strip() or None) if names else None
        if kind == 'field_expression':
            text = self._get_node_text(type_node).strip()
            return text.split('.')[-1] if text else None
        return None

    def _callee_name_scala_infix(self, call_node) -> Optional[str]:
        # Scala infix method calls: `a :: b`, `list map doubler`,
        # `xs filterNot q` — every single-argument method can be called without
        # a dot or parens, and operators ARE methods (`a + b` desugars to
        # `a.+(b)`). tree-sitter parses all of these to `infix_expression`, a
        # node kind that was entirely absent from CALL_NODE_TYPES, so every
        # infix call was silently invisible to calls:// (BACK-746, twelfth
        # calls-recall language). The `operator` field holds the method name —
        # an `identifier` for alphabetic infix (`map`, `filterNot`) or an
        # `operator_identifier` for symbolic operators (`::`, `+`). Emit the
        # bare name (no "new "/qualifier), matching the plain-call convention.
        op = call_node.child_by_field_name('operator')
        if op is not None:
            text = self._get_node_text(op).strip()
            if text:
                return text
        # Fallback: middle child (left, OP, right) if the field is unavailable.
        kids = _children(call_node)
        if len(kids) >= 3:
            text = self._get_node_text(kids[1]).strip()
            if text:
                return text
        return None

    def _callee_name_java_method(self, call_node) -> Optional[str]:
        # Java: obj.method() / Class.staticMethod() / method() —
        # method_invocation's grammar puts an optional `object` field BEFORE
        # the `.` token and the `name` field, so child(0) is the *object*
        # whenever one is present (BACK-734: the generic child(0) fallback
        # returned the qualifier — e.g. "RamUsageEstimator" — as the callee
        # name for every qualified/static call, not the method name at all;
        # confirmed via a calls-recall-oracle measurement that fell to 9.99%
        # recall on Elasticsearch, then traced to this exact node-shape
        # mismatch). Use the named fields directly rather than positional
        # child(0), same fix shape as PHP's member_call_expression handling
        # above.
        name_node = call_node.child_by_field_name('name')
        if name_node is None:
            return None
        name_text = self._get_node_text(name_node)
        object_node = call_node.child_by_field_name('object')
        if object_node is None:
            return name_text
        return f"{self._get_node_text(object_node)}.{name_text}"

    def _callee_name_ruby_call(self, call_node) -> Optional[str]:
        # Ruby: obj.method() / Class.static_call() / self.foo() / foo() —
        # tree-sitter-ruby's 'call' node is the SAME node kind Python's
        # plain call() uses, but a structurally different shape: a flat
        # (receiver?, '.', method, argument_list?) sibling list, not a
        # nested func-expression child. child(0) is therefore the
        # *receiver* whenever one is present (BACK-734-shaped bug,
        # discovered pre-flight for the calls-recall-oracle Ruby measurement
        # via a direct grammar dump: `obj.baz` gave calls=["obj"], dropping
        # the actual method name entirely; `self.instance_call` gave
        # calls=["self"]; `Qux.static_call` gave calls=["Qux"]). Use the
        # named 'receiver'/'method' fields directly, same fix shape as
        # Java's method_invocation (BACK-734).
        #
        # `rs.reason = x` (a pure attribute WRITE) parses its LHS as this
        # SAME 'call' node shape (receiver=rs, method=reason) wrapped in an
        # 'assignment' node — tree-sitter-ruby has no distinct ATTRASGN-like
        # node the way Ruby's own AST does. Left un-guarded, a setter write
        # counted as a "call" to the bare attribute name showed up as
        # false-positive edges against the calls-recall-oracle Ruby
        # measurement (which, matching Ruby's own AST, excludes pure writes)
        # — real corpus examples: ColorScheme#... writing `skip_publish`,
        # UserOption#set_defaults writing `mailing_list_mode_frequency`.
        # `+=`/`||=` (`operator_assignment`) is NOT excluded here: it reads
        # the attribute before writing it, so it's a genuine call, matching
        # real Ruby semantics.
        parent = call_node.parent()
        if parent is not None and _zero_arg(parent, 'kind') == 'assignment':
            left = parent.child_by_field_name('left')
            if left is not None and _zero_arg(left, 'start_byte') == _zero_arg(call_node, 'start_byte'):
                return None
        method_node = call_node.child_by_field_name('method')
        if method_node is None:
            return None
        method_text = self._get_node_text(method_node)
        receiver_node = call_node.child_by_field_name('receiver')
        if receiver_node is None:
            return method_text
        return f"{self._get_node_text(receiver_node)}.{method_text}"

    def _callee_name_generic(self, call_node) -> Optional[str]:
        return self._callee_name_from_node(call_node.child(0))

    def _callee_name_from_node(self, callee_node) -> Optional[str]:
        if callee_node.kind() == 'identifier':
            return self._get_node_text(callee_node)
        if callee_node.kind() in CALLEE_ATTRIBUTE_TYPES:
            return self._get_node_text(callee_node).lstrip('*')
        # tree-sitter parses `*foo(args)` as call(list_splat(*foo), args).
        if callee_node.kind() == 'list_splat':
            for child in _children(callee_node):
                if child.kind() == 'identifier':
                    return self._get_node_text(child)
                if child.kind() in CALLEE_ATTRIBUTE_TYPES:
                    return self._get_node_text(child).lstrip('*')
        # Rust turbofish (`size_of::<u32>()`, `x.remap_types::<T>()`,
        # `E::error::<T>()`) parses as generic_function(path, '::',
        # type_arguments) -- the path is the real callee, type_arguments is
        # not. Taking the whole node's raw text (old behavior) left the
        # turbofish in the string, which defeated _bare_callee_name's
        # last-separator split (BACK-733: the '::' *inside* the generic
        # argument won, e.g. "size_of::<u32>" -> bare "<u32>" not "size_of").
        # Recursing into just the path child sidesteps that entirely.
        if _zero_arg(callee_node, 'kind') == 'generic_function':
            path_node = callee_node.child(0)
            if path_node is not None:
                name = self._callee_name_from_node(path_node)
                if name:
                    return name
        # `(f)(args)` parses callee as parenthesized_expression wrapping the
        # real expression. Raw text would be the literal, unmatchable "(f)"
        # (BACK-733) -- unwrap to the inner expression instead.
        if _zero_arg(callee_node, 'kind') == 'parenthesized_expression':
            for child in _children(callee_node):
                if _zero_arg(child, 'kind') not in ('(', ')'):
                    name = self._callee_name_from_node(child)
                    if name:
                        return name
        # Swift `!isRunning(x)` (logical negation of a call's result --
        # common for boolean-returning predicate functions/methods) parses
        # the whole `!isRunning` as a single call-suffix-adjacent
        # `prefix_expression(bang, simple_identifier)`, not a plain
        # identifier -- taking the whole node's raw text (old behavior)
        # left the leading "!" in the callee string, and
        # `_bare_callee_name` has no separator to act on a bare identifier,
        # so the index key was literally "!isRunning", never matching a
        # bare `?target=isRunning` lookup. Confirmed via the calls-recall-
        # oracle Swift measurement (BACK-730, tenth language): real corpus
        # miss on `BackupAttachmentCoordinator.swift`'s
        # `kickOffNextOperation`, which calls `!isRunning(...)` four times.
        # This same node shape (`prefix_expression`) is ALSO how Swift
        # parses an implicit-member call's leading dot (`.foo(...)` ->
        # `prefix_expression('.', simple_identifier)`) -- recursing into
        # the last child (the operand, always positioned after the
        # operator token for any Swift prefix operator) handles both
        # uniformly and doesn't change the already-correct `.foo` case
        # (its raw-text fallback below produced the same bare name via
        # `_bare_callee_name`'s separate leading-dot handling; this makes
        # it explicit instead of accidental).
        if _zero_arg(callee_node, 'kind') == 'prefix_expression':
            kids = _children(callee_node)
            if kids:
                name = self._callee_name_from_node(kids[-1])
                if name:
                    return name
        text = self._get_node_text(callee_node).strip().lstrip('*')
        return text if text else None

    def _get_callee_name(self, call_node) -> Optional[str]:
        """Extract the callee name from a call expression node.

        Handles five forms:
          - Simple:         foo()             → "foo"
          - Attribute:      self.bar()        → "self.bar"
          - Chained:        a.b.c()           → "a.b.c"
          - Starred:        *foo(bar)         → "foo"
          - PHP method:     $obj->method()    → "$obj->method"
          - PHP new:        new ClassName()   → "new ClassName"
          - Java method:    obj.method()      → "obj.method" (field-based,
                             not child(0) — method_invocation's `object`
                             field precedes `name` positionally, BACK-734)
          - Ruby method:    obj.method()      → "obj.method" (field-based;
                             Ruby's 'call' node is the SAME kind as Python's
                             but a flat receiver/./method/args shape, so
                             child(0) is the receiver, not the method,
                             BACK-734-shaped)
        """
        if not call_node.child_count():
            return None
        if call_node.kind() == 'member_call_expression':
            return self._callee_name_php_method(call_node)
        if call_node.kind() == 'object_creation_expression':
            return self._callee_name_php_new(call_node)
        if call_node.kind() == 'scoped_call_expression':
            return self._callee_name_php_scoped_call(call_node)
        if _zero_arg(call_node, 'kind') == 'new_expression':
            return self._callee_name_new_expression(call_node)
        if _zero_arg(call_node, 'kind') == 'instance_expression':
            return self._callee_name_scala_instance(call_node)
        if _zero_arg(call_node, 'kind') == 'infix_expression':
            return self._callee_name_scala_infix(call_node)
        if call_node.kind() == 'method_invocation':
            return self._callee_name_java_method(call_node)
        if _zero_arg(call_node, 'kind') == 'call' and self.language == 'ruby':
            return self._callee_name_ruby_call(call_node)
        return self._callee_name_generic(call_node)

    def _extract_calls_in_function(self, func_node) -> List[str]:
        """Walk function body subtree and return unique callee name strings.

        Returns best-effort callee names from call expression nodes within the
        function body. Names are not resolved across files (that's Phase 3).

        Examples:
            foo()           → ["foo"]
            self.bar()      → ["self.bar"]
            foo(bar())      → ["foo", "bar"]  (nested calls both captured)
        """
        calls: List[str] = []
        seen: set = set()
        stack = _children(func_node)
        while stack:
            node = stack.pop()
            if node.kind() in CALL_NODE_TYPES:
                name = self._get_callee_name(node)
                if name and name not in seen:
                    calls.append(name)
                    seen.add(name)
            stack.extend(reversed(_children(node)))
        return calls

    def _complexity_depth_and_calls(self, func_node) -> Tuple[int, int, List[str]]:
        """Compute complexity, nesting depth, and callee names in one subtree walk.

        `_build_function_dict` used to call `calculate_complexity_and_depth`
        and `_extract_calls_in_function` back to back — two independent full
        walks of the same function-body subtree via `node_children`. Profiling
        a real 11K-file TypeScript repo (BACK-489) showed this pair dominates
        `reveal architecture`'s cost for large repos even after fixing the
        double-parse-per-file bug: `node_children` alone accounted for 88s of
        self time across 94M calls. Merging into one traversal halves that.

        Traversal order matches `_extract_calls_in_function` exactly (reversed
        children pushed onto a stack, so pop order is document order) so the
        `calls` list is identical to before; complexity/depth are order-
        independent aggregates, computed alongside using the same decision/
        nesting-type rules as `calculate_complexity_and_depth`.

        BACK-490: a nested node whose kind is in `FUNCTION_NODE_TYPES` is a
        leaf for this walk — its own body is not expanded here. Every
        `FUNCTION_NODE_TYPES` node anywhere in the tree already gets its own
        top-level entry (and its own call to this method) via
        `_find_nodes_by_type`'s whole-tree scan, so expanding into it here
        would double-count its decisions/calls into the enclosing function
        too (confirmed live across Python/Ruby/Rust/JS: a wrapper containing
        only a nested named function reported the same complexity as the
        nested function itself). Anonymous closures/lambdas/arrow functions
        that never get their own entry (not in `FUNCTION_NODE_TYPES`) are
        deliberately NOT stopped at — their contribution should keep bleeding
        into the enclosing function, since they have no separate identity in
        the output.
        """
        decision_count = 0
        max_depth = 0
        calls: List[str] = []
        seen_calls: set = set()

        # Stack entries: (node, parent_kind, depth). parent_kind is None only
        # for func_node's direct children — mirrors calculate_complexity_and_depth's
        # (node, None, 0) seed (func_node itself is never itself checked as a
        # decision/call node, only its descendants are). The top-level push is
        # intentionally NOT reversed, matching _extract_calls_in_function's own
        # top-level `stack = _children(func_node)` exactly (only its recursive
        # `stack.extend(reversed(...))` step reverses) — preserved byte-for-byte
        # so this merged walk returns the identical `calls` list order.
        stack = [
            (child, None, 1 if child.kind() in _NESTING_TYPES else 0)
            for child in _children(func_node)
        ]
        while stack:
            node, parent_kind, depth = stack.pop()
            if depth > max_depth:
                max_depth = depth

            kind = node.kind()
            if kind in CALL_NODE_TYPES:
                name = self._get_callee_name(node)
                if name and name not in seen_calls:
                    calls.append(name)
                    seen_calls.add(name)
            if kind in _DECISION_TYPES and (parent_kind is None or (parent_kind, kind) not in _KEYWORD_PAIRS):
                decision_count += 1

            if kind in FUNCTION_NODE_TYPES:
                continue

            for child in reversed(_children(node)):
                child_kind = child.kind()
                child_depth = depth + 1 if child_kind in _NESTING_TYPES else depth
                stack.append((child, kind, child_depth))

        return decision_count + 1, max_depth, calls

