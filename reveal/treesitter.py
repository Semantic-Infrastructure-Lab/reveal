"""Tree-sitter based analyzer for multi-language support."""

import hashlib
import logging
import os
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Set, Tuple
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

from tree_sitter_language_pack import get_parser, downloaded_languages  # noqa: E402

logger = logging.getLogger(__name__)

# BACK-979: dedup state for the two grammar-availability warnings below, kept
# module-level (not per-instance) so a directory scan touching hundreds of
# files in an uncached/offline language only warns once per language, not
# once per file.
_warned_uncached_languages: Set[str] = set()
_warned_failed_languages: Set[str] = set()

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
# BACK-814: FUNCTION_NODE_TYPES/CLASS_NODE_TYPES/STRUCT_NODE_TYPES/
# IMPORT_NODE_TYPES/ELEMENT_TYPE_MAP are defined at the BOTTOM of this file
# (after TreeSitterAnalyzer), derived from node_taxonomy.py's DEF_NODES/
# CLASS_NODES/STRUCT_NODES/IMPORT_NODES — the actual single source of truth
# for "which tree-sitter node kinds mean X across every supported grammar"
# (see that module's docstring for the BACK-427/430/431/478 history this
# consolidates). Per-node-kind provenance/corpus comments now live there too.
#
# Placed at module end, not here, because a module-level import of
# node_taxonomy.py (which lives under reveal.adapters.ast) triggers that
# package's __init__ chain, which transitively imports analyzers/python.py,
# which does `from ..treesitter import TreeSitterAnalyzer` — a genuine
# circular import if TreeSitterAnalyzer isn't bound yet (confirmed live: this
# was tried at the top of the file first and failed with exactly that
# ImportError). By the time Python re-enters this partially-initialized
# module via that cycle, TreeSitterAnalyzer is already defined, so the import
# succeeds. Same shape nav_exits.py/nav_calls.py already solve for
# CALL_NODE_TYPES via a function-local deferred import — this can't use that
# exact form because ELEMENT_TYPE_MAP is consumed at true module scope
# elsewhere in this file's history; module-end placement covers that too
# since nothing calls into TreeSitterAnalyzer before this module finishes
# importing.
#
# MAINTENANCE: to add new language support, edit node_taxonomy.py's families,
# not tuples here.
# =============================================================================

# Node types for call expression extraction (call graph)
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
    # PHP/C#/Scala).
    'new_expression',           # C++
    # C++'S OTHER constructor-call syntax, direct-initialization
    # (`ClassName obj(args);`, `std::vector<int> v(10);`) has no
    # call-expression-family node at all — it parses to a `declaration`
    # holding an `init_declarator` whose 'value' field is a bare
    # `argument_list` (no wrapping call node), a DISTINCT shape from
    # copy-init (`Foo obj2 = Foo(3, 4);`, whose 'value' field is a real
    # `call_expression` and is already covered by the generic dispatch
    # above). Confirmed via a live grammar dump (BACK-744): the type name
    # lives on the *parent* `declaration` node's 'type' field, not on
    # `init_declarator` itself, so this entry alone doesn't visit a
    # meaningful callee node — `init_declarator` must ALSO be excluded
    # from every OTHER language's plain-assignment case
    # (`int y = 5;` / `int x;`), which the 'value'-is-argument_list check
    # in _callee_name_cpp_direct_init/_extract_cpp_direct_init_callee
    # handles by returning None for non-direct-init shapes. See
    # nav_calls.py:_extract_cpp_direct_init_callee for the paired ast://
    # nav extraction.
    'init_declarator',          # C++ direct-init: ClassName obj(args);
    # GDScript: any dotted method call -- `self.foo()`, `obj.method()`,
    # `Class.static()`/`Class.new()`, and every segment of a chained call
    # (`a.b().c()`) -- parses to a DISTINCT node kind, 'attribute_call', NOT
    # a variant of 'function_call' (GDScript's plain `foo()` node kind,
    # already covered above). Found via a pre-flight grammar dump before the
    # GDScript calls-recall-oracle measurement (BACK-730, seventeenth
    # language): entirely absent from CALL_NODE_TYPES meant calls:// silently
    # returned zero callers/callees for the single most common GDScript call
    # idiom -- `self.`-qualified calls and Godot's constructor convention
    # (`ClassName.new()`, since GDScript has no `new` keyword) are both this
    # shape. See _callee_name_gdscript_attribute_call for the paired callee-
    # text extraction; unlike every other dotted-call node in this table
    # (Java's method_invocation, Ruby's call, PHP's member_call_expression),
    # the receiver here is NOT a child/field of this node at all -- it's a
    # preceding SIBLING in the flat 'attribute' parent node, since
    # tree-sitter-gdscript models `a.b().c()` as one flat
    # (receiver, '.', segment, '.', segment, ...) list rather than nested
    # call-of-a-member-access the way Python/JS do.
    'attribute_call',           # GDScript `self.foo()` / `obj.method()` / `Class.new()`
    # Dart: tree-sitter-dart has NO dedicated call-expression node kind at
    # all -- a plain call, a receiver-qualified call, a cascade call, and a
    # null-safe (`?.`) call are all built from a flat sequence of SIBLINGS
    # (primary expression + zero or more 'selector' nodes), not a single
    # nested node the way every other language in this program is shaped.
    # `foo()` parses to identifier('foo') + selector(argument_part); a
    # qualified `obj.method()` parses to identifier('obj') +
    # selector(unconditional_assignable_selector: '.' identifier('method'))
    # + selector(argument_part) -- three siblings, no receiver/name FIELD
    # to read the way Java/Ruby's fix shape works. Found via a pre-flight
    # grammar dump before the Dart calls-recall-oracle measurement
    # (BACK-730, eighteenth and final language): entirely absent from
    # CALL_NODE_TYPES meant calls:// returned ZERO callers/callees for
    # EVERY Dart call site, not just a subset -- the single largest total
    # blind spot in this whole program (GDScript's attribute_call gap was
    # "only" the dominant idiom; Dart had no working call detection at
    # all). See _callee_name_dart_argument_part for the paired sibling-walk
    # extraction (BACK-760).
    'argument_part',            # Dart: the `(args)` selector marking ANY call
    # Dart's OTHER call shape: a generic-typed constructor call with an
    # explicit or named constructor segment (`List<int>.from(...)`,
    # `Map<String, int>()`) parses to a DISTINCT node, 'constructor_invocation'
    # (child of 'postfix_expression'), where 'arguments' IS a direct child
    # -- structurally closer to every other language's call node than the
    # 'argument_part'-selector shape above. See
    # _callee_name_dart_flat_type_call.
    'constructor_invocation',   # Dart `List<int>.from(...)` / `Map<K, V>()`
    # Dart's THIRD flat-constructor-call shape: an explicitly `const`-
    # evaluated constructor call (`const Duration(milliseconds: 300)`,
    # `const EdgeInsets.all(8)`, `const Color(0xFFFFFFFF)`) -- ubiquitous
    # in Flutter code (compile-time-constant widget/value construction is
    # the recommended default whenever every argument is itself constant).
    # Parses to a DISTINCT node kind, 'const_object_expression', NOT a
    # variant of 'constructor_invocation' above despite the near-identical
    # flat shape (const_builtin, type_identifier, type_arguments?, '.',
    # identifier?, arguments) -- entirely absent from CALL_NODE_TYPES meant
    # every `const`-constructed value's constructor call was invisible to
    # calls://. Found via the Dart calls-recall-oracle measurement
    # (BACK-730, eighteenth and final language): AppFlowy's real corpus
    # dominant residual miss (`Duration`, `BoxShadow`, `CircleBorder`,
    # `Positioned` — every one of them a `const Foo(...)` construction).
    # See _callee_name_dart_flat_type_call (shared with
    # constructor_invocation above, same flat shape modulo the leading
    # 'const' token, which the extractor simply ignores).
    'const_object_expression',  # Dart `const Duration(milliseconds: 300)`
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

# _get_callee_name's node-kind -> hook-method dispatch table (BACK-915 slice
# 4). Every value is a method that exists on every TreeSitterAnalyzer (a
# no-op stub by default, overridden per language in analyzers/*.py) — see
# each hook's docstring for which analyzer overrides it and why the kind
# isn't handled generically. `call_expression`/`call` are deliberately absent
# — see _get_callee_name's docstring for why they can't be table-driven.
_CALLEE_NAME_DISPATCH = {
    'member_call_expression': '_callee_name_php_method',
    'object_creation_expression': '_callee_name_php_new',
    'scoped_call_expression': '_callee_name_php_scoped_call',
    'new_expression': '_callee_name_new_expression',
    'init_declarator': '_callee_name_cpp_direct_init',
    'instance_expression': '_callee_name_scala_instance',
    'infix_expression': '_callee_name_scala_infix',
    'method_invocation': '_callee_name_java_method',
    'attribute_call': '_callee_name_gdscript_attribute_call',
    'constructor_invocation': '_callee_name_dart_flat_type_call',
    'const_object_expression': '_callee_name_dart_flat_type_call',
    'argument_part': '_callee_name_dart_argument_part',
}


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
        self.parse_error: Optional[str] = None  # BACK-979: set when _parse_tree()'s except branch fires

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

        # Proactive check (BACK-979): downloaded_languages() is a local
        # cache-directory read with no network attempt, unlike get_parser()
        # below which downloads the grammar bundle on first use of a
        # language. Warn before that fetch, not after it silently fails.
        if self.language not in downloaded_languages() and self.language not in _warned_uncached_languages:
            _warned_uncached_languages.add(self.language)
            logger.warning(
                "tree-sitter grammar for %r not yet downloaded — first parse "
                "will attempt to fetch it from the network (see "
                "INSTALL.md#network-requirements for offline setups)",
                self.language,
            )

        try:
            parser = get_parser(self.language)  # type: ignore[arg-type]  # language is validated at runtime
            self.tree = ts_parse(parser, self.content)
        except Exception as e:
            self.parse_error = str(e)
            if self.language not in _warned_failed_languages:
                _warned_failed_languages.add(self.language)
                logger.warning(
                    "tree-sitter parse failed for %s (language=%r): %s — "
                    "structure extraction degrades to empty for this "
                    "language until resolved (see "
                    "INSTALL.md#network-requirements)",
                    self.path, self.language, e,
                )
            else:
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
        result = {k: v for k, v in structure.items() if v}

        # BACK-1084: tree-sitter's error-tolerant parser still fabricates
        # plausible-looking structure from a plain syntax error (e.g. a
        # function with a garbled signature) rather than signaling failure,
        # so a caller has no way to tell confident structure from a guess
        # recovered around an ERROR node. Additive, `_`-prefixed key --
        # TypedStructure.from_analyzer_output already skips `_`-prefixed
        # keys (reveal/structure.py), so this can't be mistaken for a real
        # element category by anything already consuming this dict.
        if self._has_recovery_artifacts():
            result['_has_errors'] = True

        return result

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
        # BACK-1003: interfaces used to be extracted outside this cached dict
        # (C#/Java/PHP each re-walked the tree for 'interface_declaration' on
        # every get_structure() call, uncached, even on a disk-cache hit for
        # everything else here). Folding it in means it's built once and
        # cached like every other category — languages with no distinct
        # interface node kind just cache an empty list from the cheap walk.
        interfaces = self._extract_interface_declarations()
        if interfaces:
            structure['interfaces'] = interfaces

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
        functions.extend(self._extract_language_specific_functions())

        return functions

    def _extract_language_specific_functions(self) -> List[Dict[str, Any]]:
        """Hook for a language whose functions-as-values aren't covered by
        the shared arrow/class-field extractors above (e.g. Lua's
        `name = function(...) ... end`, BACK-758). No-op by default —
        overridden in analyzers/lua.py (BACK-915).
        """
        return []

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

        # 3. Language-specific fallback (e.g. Lua's `name = function(...) ... end`
        # / table-field function value, BACK-758) — no-op by default.
        return self._find_named_language_specific_function(name)

    def _find_named_language_specific_function(self, name: str):
        """Hook paired with `_extract_language_specific_functions` above:
        resolve a bare name to a language-specific function-as-value node.
        No-op by default — overridden in analyzers/lua.py (BACK-915).
        """
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
        # Dart signature-adjacent call sites -- a constructor's initializer
        # list (`Foo(...) : super(compute()), x = y, assert(cond) { ... }`)
        # and ANY signature's parameter DEFAULT VALUES (`{int x =
        # paramDefault()}`) -- live entirely OUTSIDE body_node (they're
        # part of the disjoint signature node / a THIRD sibling, see
        # _function_end_node), so the walk above never sees calls made
        # there. Same "call in a signature-adjacent expression, not the
        # body proper" shape as Python's BACK-731 decorator-argument gap.
        # Found real corpus impact via the Dart calls-recall-oracle
        # measurement (BACK-730): `super(...)` calls (Flutter/BLoC's
        # dominant constructor idiom) and `const`-constructed default
        # parameter values (Flutter's dominant const-constructor-argument
        # idiom, e.g. `this.duration = const Duration(seconds: 1)`) were
        # both silently absent from every affected signature's own calls
        # list even after the _function_end_node fix above. (BACK-760)
        calls = self._dart_merge_signature_extra_calls(node, calls)
        calls = self._decorator_extra_calls(decorated_node, calls)
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': self._get_signature(node),
            'line_count': line_end - line_start + 1,
            'code_line_count': self._code_line_count(body_node, line_start, line_end),
            'depth': depth,
            'complexity': complexity,
            'decorators': decorators,
            'calls': calls,
        }

    def _mark_non_code_rows(self, node, non_code_rows: Set[int]) -> None:
        """Add a comment/docstring node's fully-self-contained rows to
        `non_code_rows` (0-indexed). A row is only added when nothing but
        the node itself occupies it -- a trailing `x = 1  # why` comment
        leaves its line counted as code; a comment/docstring on its own
        line(s) does not.
        """
        sp = _zero_arg(node, 'start_position')
        ep = _zero_arg(node, 'end_position')
        start_row, start_col = sp.row, sp.column
        end_row, end_col = ep.row, ep.column

        if start_row == end_row:
            line = self.lines[start_row] if start_row < len(self.lines) else ''
            if not line[:start_col].strip() and not line[end_col:].strip():
                non_code_rows.add(start_row)
            return

        # Multi-row (block comment / triple-quoted docstring): interior
        # rows are always fully consumed by the node; the two boundary
        # rows are only blanked if no other content shares them.
        for row in range(start_row + 1, end_row):
            non_code_rows.add(row)
        first_line = self.lines[start_row] if start_row < len(self.lines) else ''
        if not first_line[:start_col].strip():
            non_code_rows.add(start_row)
        last_line = self.lines[end_row] if end_row < len(self.lines) else ''
        if not last_line[end_col:].strip():
            non_code_rows.add(end_row)

    def _leading_docstring_node(self, body_node):
        """The function's first statement, if it's a bare string literal
        used as a docstring (Python convention only -- other supported
        languages don't use a leading string expression this way).

        `body_node` may be the outer `function_definition` (its 'block'
        child holds the actual statements) or already the block itself
        (Dart's disjoint-sibling body) -- look one level in either shape.
        """
        if self.language != 'python' or body_node is None:
            return None
        block = body_node
        if _zero_arg(block, 'kind') != 'block':
            block = next(
                (c for c in _children(body_node) if _zero_arg(c, 'kind') == 'block'),
                None,
            )
        if block is None:
            return None
        for child in _children(block):
            kind = _zero_arg(child, 'kind')
            return child if kind == 'string' else None
        return None

    def _code_line_count(self, body_node, line_start: int, line_end: int) -> int:
        """Lines that carry real code, excluding blank lines and lines
        consumed entirely by a comment or a leading docstring.

        `line_count` (the raw start-to-end span) stays as-is for LLM-cost
        estimates -- comments still cost real tokens to read -- but using
        it alone for C902's *length* threshold conflates documentation
        with logic: a function with a large explanatory docstring (e.g.
        recording *why* a non-obvious branch exists, a specific
        corpus-verified bug fix) reads as equally "too long" as one with
        the same line count of dense branching. This under-counts the
        threshold-relevant length instead.
        """
        lo, hi = line_start - 1, line_end - 1  # 0-indexed, inclusive
        non_code_rows: Set[int] = {
            row for row in range(lo, min(hi, len(self.lines) - 1) + 1)
            if not self.lines[row].strip()
        }

        self._find_nodes_by_type('comment')  # ensure the node-kind cache is built
        for kind, nodes in (self._node_cache or {}).items():
            if 'comment' not in kind:
                continue
            for comment_node in nodes:
                row = _zero_arg(comment_node, 'start_position').row
                if lo <= row <= hi:
                    self._mark_non_code_rows(comment_node, non_code_rows)

        docstring = self._leading_docstring_node(body_node)
        if docstring is not None:
            self._mark_non_code_rows(docstring, non_code_rows)

        return (hi - lo + 1) - len(non_code_rows)

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

        Base default: no bases. Real per-language logic lives in the
        analyzer subclasses — Python's in analyzers/python.py, the shared
        JS/TS class_heritage-based logic (plain JavaScript and TypeScript
        share the same class_declaration/class_heritage grammar shapes) in
        analyzers/_js_class_bases.py's JSClassBasesMixin, and most other
        languages override this directly (kotlin.py/scala.py/dart.py/etc.),
        falling back to super() for node kinds they don't handle.
        """
        return []

    def _extract_generic_type_base(self, generic_type) -> Optional[str]:
        # Shared by JSClassBasesMixin._extract_ts_implements_names and
        # analyzers/scala.py's _extract_class_bases — kept here rather than
        # behind the JS-only mixin since scala.py calls it directly.
        for gchild in _children(generic_type):
            if gchild.kind() == 'type_identifier':
                return self._get_node_text(gchild).strip() or None
        return None

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

    def has_parse_errors(self) -> bool:
        """True if the parsed tree contains any ERROR node.

        Tree-sitter is error-tolerant: a file with a plain syntax error still
        produces a non-empty, non-None tree (recovered with ERROR nodes)
        rather than failing outright. Callers that only check `not
        self.tree` (e.g. imports/base.py's parse_failed guard) miss this —
        the tree exists, so the check passes, but structure derived from it
        (imports, symbols, usages) is incomplete or wrong for the
        ERROR-recovered region (BACK-1082). Uses the cached
        _find_nodes_by_type lookup, so this is near-zero marginal cost after
        the first call on a given tree.

        Deliberately narrower than `_has_recovery_artifacts()` below: an
        ERROR node means the parser genuinely lost its place, which is what
        makes derived imports/symbols unreliable enough to skip outright.
        """
        return bool(self._find_nodes_by_type('ERROR'))

    def _has_recovery_artifacts(self) -> bool:
        """True if the parse was not fully clean: an ERROR node OR a
        MISSING token inserted during error recovery.

        Wider than `has_parse_errors()` above -- tree-sitter's own
        recursive `has_error()` also catches a recovery shape ERROR-node
        checking misses entirely: an unclosed construct like `def foo(:`
        recovers as a well-typed subtree with a MISSING token spliced in
        (`(parameters (MISSING ")"))`) and no ERROR node anywhere in the
        tree — confirmed live investigating BACK-1084, where that exact
        input silently produced a plausible-looking `foo` function with no
        error signal.

        NOT used for `has_parse_errors()` itself: `has_error()` also fires
        on at least one confirmed-benign grammar quirk (a C/C++
        translation unit consisting only of #include lines with nothing
        after the last one trips a trailing MISSING token in
        tree-sitter-c, with no actual problem for import extraction --
        caught live as a regression across tests/test_imports_generic.py
        when this was first wired into has_parse_errors() directly). That
        makes it too trigger-happy for imports/base.py's parse_failed
        guard, where a false positive silently drops real results. It's
        fine as an advisory-only signal for get_structure()'s additive
        `_has_errors` flag, where a false positive just means an
        occasional unnecessary "the structure might be incomplete" note
        on an actually-fine file -- a strictly better failure mode than
        BACK-1084's original bug (fabricated structure, no signal at all).
        """
        if not self.tree:
            return False
        return bool(_zero_arg(tree_root(self.tree), 'has_error'))

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
        if _zero_arg(node, 'kind') in (
            'function_signature', 'constructor_signature', 'factory_constructor_signature',
            'getter_signature', 'setter_signature', 'constant_constructor_signature',
        ):
            sibling = _next_sibling(node)
            # A constructor WITH an initializer list (`SpaceBloc(...) :
            # super(...) { ... }` / `: x = y, assert(...)`) has an
            # 'initializers' node wedged in as ANOTHER sibling of
            # constructor_signature, inside the SAME method_signature
            # wrapper, BEFORE the real function_body (which is still one
            # level up, next to method_signature -- initializers is never
            # itself the body). Without this check, `sibling` here is
            # 'initializers' (not None), so the "sibling is None" fallback
            # below never fired, and the final `sibling.kind() ==
            # 'function_body'` check failed -- silently returning `node`
            # itself (bounds truncated to the bare signature, calls list
            # empty) for EVERY constructor with an initializer list, a
            # common, high-impact Dart/Flutter idiom (BLoC constructors
            # almost universally use `: super(...)`). Found via the Dart
            # calls-recall-oracle measurement (BACK-730, eighteenth and
            # final language): AppFlowy's `SpaceBloc` constructor -- real
            # calls to `super(...)`, `on<SpaceEvent>(...)`, and everything
            # inside that handler -- reported ZERO calls before this fix.
            if sibling is not None and _zero_arg(sibling, 'kind') == 'initializers':
                sibling = None
            if sibling is None:
                # Methods wrap function_signature in a method_signature node
                # (`class_body: method_signature(function_signature), function_body`)
                # — function_signature is method_signature's only child, so its
                # own next-sibling is None; the real function_body sibling is
                # one level up, next to method_signature (dogfood audit against
                # AppFlowy: every class method showed "[1 lines]" in --outline
                # even after the top-level-function fix above). Constructors
                # (BACK-760) wrap the same way: `method_signature(constructor_
                # signature)` / `method_signature(factory_constructor_signature)`,
                # optionally followed by `initializers` (handled above).
                parent = node.parent()
                # 'constant_constructor_signature' wraps in 'declaration',
                # not 'method_signature' -- checked defensively even though
                # a real `const` constructor can't carry an imperative body
                # under Dart's own language rules (so this branch is not
                # expected to ever actually find a function_body sibling
                # for it in practice).
                if parent is not None and _zero_arg(parent, 'kind') in ('method_signature', 'declaration'):
                    sibling = _next_sibling(parent)
            if sibling is not None and sibling.kind() == 'function_body':
                return sibling
        return node

    def _dart_merge_signature_extra_calls(self, node, calls: List[str]) -> List[str]:
        """Hook: merge calls found in a language's signature-adjacent
        children (e.g. Dart's constructor initializer list / parameter
        default values, BACK-760/BACK-764) into a function's calls list.
        No-op by default — overridden in analyzers/dart.py (BACK-915).

        Safe to call unconditionally, including for any non-Dart language.
        """
        return calls

    def _decorator_extra_calls(self, decorated_node, calls: List[str]) -> List[str]:
        """Merge calls made in a Python decorator's own arguments into the
        decorated function's calls list.

        `@validator(vol.Schema(...))` / `@singleton(DATA_RESOLVER)` /
        `@lru_cache(maxsize=512)` parse decorator expressions as SIBLINGS of
        the function node under `decorated_definition`, not part of
        `body_node` -- the walk in `_complexity_depth_and_calls` never sees
        them (BACK-731, same "call in a signature-adjacent expression, not
        the body proper" shape as Dart's `_dart_merge_signature_extra_calls`
        above). Confirmed via Home Assistant's helpers/data_entry_flow.py:
        two `post` methods decorated `@RequestDataValidator(vol.Schema(...))`
        -- calls://...?target=Schema reported zero callers in that file at
        all, in both the reverse (?target=) and forward (?callees=)
        directions.

        Safe to call unconditionally (including with `decorated_node=None`
        for an undecorated function, or any non-Python language with no
        `decorated_definition` wrapper): both are no-ops.
        """
        if decorated_node is None:
            return calls
        extra: List[str] = []
        seen_extra: set = set()
        for child in _children(decorated_node):
            if _zero_arg(child, 'kind') != 'decorator':
                continue
            stack = _children(child)
            while stack:
                dec_node = stack.pop()
                if _zero_arg(dec_node, 'kind') in CALL_NODE_TYPES:
                    name = self._get_callee_name(dec_node)
                    if name and name not in seen_extra:
                        extra.append(name)
                        seen_extra.add(name)
                stack.extend(reversed(_children(dec_node)))
        if not extra:
            return calls
        seen = set(calls)
        merged = list(calls)
        for name in extra:
            if name not in seen:
                merged.append(name)
                seen.add(name)
        return merged

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

    def _dart_constructor_name(self, node) -> Optional[str]:
        """Hook: name a Dart constructor-signature node ('constructor_signature'/
        'factory_constructor_signature'/'constant_constructor_signature',
        BACK-760). No-op by default — overridden in analyzers/dart.py
        (BACK-915). Only ever invoked for those Dart-only node kinds (see
        the dispatch a few lines below `_dart_constructor_name` is called
        from), so an unimplemented base default is unreachable elsewhere.
        """
        return None

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
        """Hook: Lua `function table.name(...)` naming (`dot_index_expression`).
        No-op by default — overridden in analyzers/lua.py (BACK-918).
        """
        return None

    def _name_via_method_index(self, kids) -> Optional[str]:
        """Hook: Lua `function table:name(...)` naming (`method_index_expression`).
        No-op by default — overridden in analyzers/lua.py (BACK-918).
        """
        return None

    def _name_via_ruby_special_name(self, kids) -> Optional[str]:
        """Hook: Ruby `setter`/`operator`-kind method naming (`def x=`, `def []`).
        No-op by default — overridden in analyzers/ruby.py (BACK-918).
        """
        return None

    def _name_via_swift_operator_function(self, kids) -> Optional[str]:
        """Hook: Swift operator-overload naming (`static func -(...)`).
        No-op by default — overridden in analyzers/swift.py (BACK-918).
        """
        return None

    def _name_via_scala_operator_function(self, kids) -> Optional[str]:
        """Hook: Scala symbolic-name def naming (`def +(o)`, `def ::(x)`).
        No-op by default — overridden in analyzers/scala.py (BACK-918).
        """
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
        if _zero_arg(node, 'kind') in (
            'constructor_signature', 'factory_constructor_signature', 'constant_constructor_signature',
        ):
            return self._dart_constructor_name(node)

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

    def _callee_name_php_new(self, call_node) -> Optional[str]:
        # PHP: new ClassName() — object_creation_expression. NOT PHP-exclusive
        # despite the name: Java's `new Baz(1, 2)` AND C#'s `new Baz(1, 2)`
        # (no dedicated C# analyzer — reaches this via the tree-sitter
        # fallback path) parse to the SAME 'object_creation_expression' node
        # kind with the identical (new, type, arguments) flat-sibling shape
        # (verified via `reveal file.java --show-ast` and a direct
        # tree-sitter-language-pack grammar probe, BACK-915 slice 4). Stays
        # here as genuinely shared infra rather than moving to php.py —
        # moving it would silently break Java/C# `new` extraction.
        for child in _children(call_node):
            if child.kind() not in ('new', 'arguments'):
                return f"new {self._get_node_text(child)}"
        return None

    def _callee_name_php_method(self, call_node) -> Optional[str]:
        """Hook: name a PHP `$obj->method()` call ('member_call_expression').
        No-op by default — overridden in analyzers/php.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_php_scoped_call(self, call_node) -> Optional[str]:
        """Hook: name a PHP `self::method()`/`parent::method()`/
        `Class::method()` call ('scoped_call_expression'). No-op by
        default — overridden in analyzers/php.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_scala_instance(self, call_node) -> Optional[str]:
        """Hook: name a Scala `new ClassName(args)` call
        ('instance_expression'). No-op by default — overridden in
        analyzers/scala.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_scala_infix(self, call_node) -> Optional[str]:
        """Hook: name a Scala infix method call (`a :: b`, `xs filterNot q`,
        'infix_expression'). No-op by default — overridden in
        analyzers/scala.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_js_new(self, call_node) -> Optional[str]:
        """Hook: name a JS/TS/TSX `new Foo(args)`-shaped 'new_expression'
        call (the 'constructor'-field branch below). No-op by default —
        overridden in analyzers/_js_callee_names.py::JSCalleeNameMixin
        (BACK-915 slice 4).
        """
        return None

    def _callee_name_new_expression(self, call_node) -> Optional[str]:
        # 'new_expression' is shared by C++, JS/TS/TSX, AND Dart with THREE
        # mutually exclusive shapes — dispatch on which shape is actually
        # present rather than self.language, so this stays correct for
        # tree-sitter fallback languages too. C++/JS-TS-TSX both carry
        # explicit 'constructor'/'type' FIELDS; Dart's grammar has no field
        # names at all here (like the rest of its grammar — flat siblings),
        # so both field lookups return None for it. Dart's explicit `new
        # Foo(...)` / `new List<int>.from(...)` (the pre-Dart-2 constructor
        # syntax, still valid and used in real corpora even though modern
        # style omits `new`) was found entirely invisible to calls:// via
        # the calls-recall-oracle Dart measurement (BACK-730, eighteenth
        # and final language) — `new_expression` was already a
        # CALL_NODE_TYPES member (added for C++), so the node WAS visited,
        # but both existing field-based extractors returned None for
        # Dart's flat shape, silently dropping the call rather than
        # misnaming it. See _callee_name_dart_new_expression. (BACK-760)
        if call_node.child_by_field_name('constructor') is not None:
            return self._callee_name_js_new(call_node)
        if call_node.child_by_field_name('type') is not None:
            return self._callee_name_cpp_new(call_node)
        return self._callee_name_dart_new_expression(call_node)

    def _callee_name_dart_new_expression(self, call_node) -> Optional[str]:
        """Hook: name a Dart `new Foo(...)`-shaped 'new_expression' call
        (the fallback branch above, once JS/C++'s field-based shapes are
        ruled out — BACK-760). No-op by default — overridden in
        analyzers/dart.py (BACK-915).
        """
        return None

    def _callee_name_cpp_new(self, call_node) -> Optional[str]:
        """Hook: name a C++ `new ClassName(args)`-shaped 'new_expression'
        call (the 'type'-field branch above, once JS's 'constructor' field
        is ruled out). No-op by default — overridden in analyzers/cpp.py
        (BACK-915 slice 4).
        """
        return None

    def _callee_name_cpp_direct_init(self, call_node) -> Optional[str]:
        """Hook: name a C++ direct-initialization call
        (`ClassName obj(args);`, `init_declarator` with an 'argument_list'
        'value' field). No-op by default.

        `init_declarator` is in CALL_NODE_TYPES and walked for EVERY
        language that uses it (not just C++ — plain C and Objective-C share
        the same node kind for `int x = 5;`), so this default MUST stay a
        real no-op rather than falling through to the generic callee-name
        resolver: `_callee_name_generic` would read `init_declarator`'s
        child(0) — the identifier being declared — and misreport it as a
        callee name for every ordinary variable declaration in those
        languages. Overridden in analyzers/cpp.py, which re-applies the
        'value'-is-'argument_list' shape check before returning a name
        (BACK-915 slice 4).
        """
        return None

    def _callee_name_java_method(self, call_node) -> Optional[str]:
        """Hook: name a Java `obj.method()`/`Class.staticMethod()` call
        ('method_invocation'). No-op by default — overridden in
        analyzers/java.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_gdscript_attribute_call(self, call_node) -> Optional[str]:
        """Hook: name a GDScript `self.foo()`/`obj.method()`/`Class.new()`
        call ('attribute_call'). No-op by default — overridden in
        analyzers/gdscript.py (BACK-915 slice 4).
        """
        return None

    def _callee_name_dart_flat_type_call(self, call_node) -> Optional[str]:
        """Hook: name Dart's flat type-then-arguments call shapes
        ('constructor_invocation'/'const_object_expression', BACK-760).
        No-op by default — overridden in analyzers/dart.py (BACK-915).
        """
        return None

    def _callee_name_dart_argument_part(self, call_node) -> Optional[str]:
        """Hook: name a Dart 'argument_part' call site — the '(args)'
        selector that marks a call in Dart's flat, wrapper-less call
        grammar (BACK-760). No-op by default — overridden in
        analyzers/dart.py (BACK-915).
        """
        return None

    def _callee_name_generic(self, call_node) -> Optional[str]:
        return self._callee_name_from_node(call_node.child(0))

    def _callee_name_from_node(self, callee_node) -> Optional[str]:
        # Chained/IIFE calls (`f(...)()`) parse as call(call(...), args) --
        # the outer call's callee is itself a call node. The inner call
        # already gets its own top-level entry from the tree walk (it's a
        # CALL_NODE_TYPES node in its own right), so falling through to the
        # raw-text branch below would emit a SECOND, un-normalized entry for
        # the same call site (BACK-732: confirmed on Home Assistant's
        # helpers/temperature.py display_temp(), which calls
        # TemperatureConverter.converter_factory(...)(temperature) --
        # produced both the correct "TemperatureConverter.converter_factory"
        # and the raw "TemperatureConverter.converter_factory(temperature_unit, ha_unit)").
        # The outer call has no nameable callee of its own -- its target is
        # a call result, not an identifier/attribute -- so return None.
        if callee_node.kind() in CALL_NODE_TYPES:
            return None
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

        Dispatch by node kind is table-driven via `_CALLEE_NAME_DISPATCH`
        (BACK-915 slice 4) — every entry is a hook method that exists on
        every TreeSitterAnalyzer (no-op by default, overridden per language),
        so the lookup never needs a missing-attribute fallback. Two kinds
        can't be table-driven because they're not decided by kind() alone:
        `call_expression` collides between a real call and a C++
        member-function-pointer misparse (BACK-745, disambiguated by
        `self.language`), and `call` collides between Python and Ruby
        (BACK-734, same disambiguation).
        """
        if not call_node.child_count():
            return None
        kind = _zero_arg(call_node, 'kind')
        if (
            kind == 'call_expression'
            and self.language == 'cpp'
            and self._is_cpp_member_function_pointer_misparse(call_node)
        ):
            return None
        if kind == 'call' and self.language == 'ruby':
            return self._callee_name_ruby_call(call_node)
        handler_name = _CALLEE_NAME_DISPATCH.get(kind)
        if handler_name is not None:
            return getattr(self, handler_name)(call_node)
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

            children = _children(node)
            # BACK-760 (Dart): a nested named local function
            # (`local_function_declaration > lambda_expression >
            # function_signature, function_body`) is the ONE shape in this
            # program where the FUNCTION_NODE_TYPES stop-condition above
            # doesn't actually stop the walk from seeing the nested
            # function's body — Dart's function_signature/function_body
            # pair are disjoint SIBLINGS (see `_function_end_node`'s
            # docstring), so `continue`-ing at the signature leaves its
            # paired body as an ordinary, unguarded sibling of `node`'s
            # OTHER children, which the walk below would otherwise descend
            # into and double-count: every call inside the nested function
            # would be credited to BOTH its own scope (via its own
            # top-level entry) AND every enclosing scope on the path
            # (unbounded cascading, unlike any other language measured in
            # this program — confirmed via a direct repro, `nested()`
            # containing `void inner() { innerCall(); }` originally
            # reported `innerCall` in both `nested`'s and `inner`'s own
            # calls list). `_function_end_node` is a no-op (returns the
            # same node) for every other language's FUNCTION_NODE_TYPES
            # shape, so this exclusion costs nothing and changes nothing
            # for them.
            occluded_bodies = None
            for sibling in children:
                if _zero_arg(sibling, 'kind') in FUNCTION_NODE_TYPES:
                    paired_body = self._function_end_node(sibling)
                    if paired_body is not sibling:
                        if occluded_bodies is None:
                            occluded_bodies = set()
                        occluded_bodies.add(_zero_arg(paired_body, 'start_byte'))

            for child in reversed(children):
                if occluded_bodies is not None and _zero_arg(child, 'start_byte') in occluded_bodies:
                    continue
                child_kind = child.kind()
                child_depth = depth + 1 if child_kind in _NESTING_TYPES else depth
                stack.append((child, kind, child_depth))

        return decision_count + 1, max_depth, calls



# =============================================================================
# Deferred derivation of the node-type constants declared near the top of
# this file (BACK-814) — see the comment there for why this must live here,
# at module end, rather than at the top: a module-level import of
# node_taxonomy.py at this file's top would trigger a circular import
# (adapters.ast's package __init__ chain reaches back into this module
# before TreeSitterAnalyzer is bound). By this point in the file,
# TreeSitterAnalyzer is fully defined, so the same import here is safe.
# =============================================================================
from .adapters.ast.node_taxonomy import (  # noqa: E402
    DEF_NODES as _DEF_NODES,
    CLASS_NODES as _CLASS_NODES,
    STRUCT_NODES as _STRUCT_NODES,
    IMPORT_NODES as _IMPORT_NODES,
)

# arrow_function is deliberately excluded: JS-family arrow functions are
# extracted via a dedicated path (_extract_arrow_functions/file_handler.py),
# not this generic node-kind scan, to avoid double-extracting every nested
# callback arrow expression as a false top-level function.
FUNCTION_NODE_TYPES = tuple(_DEF_NODES - {'arrow_function'})
CLASS_NODE_TYPES = tuple(_CLASS_NODES)
STRUCT_NODE_TYPES = tuple(_STRUCT_NODES)
IMPORT_NODE_TYPES = tuple(_IMPORT_NODES)

# Mapping from element type to node types (for element extraction)
ELEMENT_TYPE_MAP = {
    'function': FUNCTION_NODE_TYPES,
    'class': CLASS_NODE_TYPES,
    'struct': STRUCT_NODE_TYPES,
}
