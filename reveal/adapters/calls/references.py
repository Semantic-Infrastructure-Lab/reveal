"""Names a non-Python file uses without calling them directly (BACK-1391).

The callers index only records call expressions inside a function body, so a
function passed as a value (C `qsort(..., cmp)`, C++ `&Class::method`, Go
`wg.Go(l.run)`, Java `X::m`, a JS callback or JSX `<Button/>`), called at
module/class-body level (JS `init();`, a Kotlin `init {}` block, a Scala class
body), or named in a PHP hook string (`add_action('init', 'fn')`) or a Ruby
symbol (`before_action :authenticate`) read as dead to `calls://?uncalled`.
Python has had its own pass for this (`_python_referenced_names`, BACK-1265);
this is the same rule for every tree-sitter language.

The rule is name-based, like the callers index: a candidate is referenced when
its name occurs as an identifier somewhere other than its own definition(s).
It deliberately errs toward "referenced" -- an unrelated variable of the same
name hides one dead function, while the inverse costs a reader a manual check
per false entry (the trade _python_referenced_names documents).
"""

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ...core import get_tree, iter_tree, node_children, _zero_arg
from ...conventions import family_for_path
from ...registry import language_for_extension

logger = logging.getLogger(__name__)

_WORD = re.compile(r'[A-Za-z_$][\w$]*')
# Shorter prefixes (`get_`, `is_`, `add_`) are bare verbs that any word literal completes by accident.
_MIN_COMPUTED_PREFIX = 6
# Java reflection calls that read an annotation type off a method or class (BACK-2176).
_JAVA_ANNOTATION_READS = frozenset({
    'isAnnotationPresent', 'getAnnotation', 'getDeclaredAnnotation', 'getAnnotationsByType',
    'getDeclaredAnnotationsByType',
})
_PHP_STRING_KINDS = frozenset({'string', 'encapsed_string'})
# Families whose string literals name callbacks: PHP `add_action('x', 'fn')`, `[$this, 'm']`.
_STRING_CALLBACK_FAMILIES = frozenset({'php'})
# C/C++ name nodes a declarator can wrap (`Foo::run`, `~Foo`, `get<T>`).
_C_NAME_WRAPPERS = frozenset({
    'qualified_identifier', 'destructor_name', 'template_function', 'operator_name',
})


def _is_name_leaf(kind: str) -> bool:
    return (kind.endswith('identifier') and kind != 'type_identifier') or kind in ('name', 'constant')


def _same_node(a, b) -> bool:
    return (a is not None and b is not None
            and _zero_arg(a, 'start_byte') == _zero_arg(b, 'start_byte')
            and _zero_arg(a, 'end_byte') == _zero_arg(b, 'end_byte'))


def _is_c_declarator_name(node) -> bool:
    """The name a C/C++ function declarator declares -- a definition or a
    prototype (`void run();` in a header), never a use."""
    child, parent = node, _zero_arg(node, 'parent')
    while parent is not None and _zero_arg(parent, 'kind') in _C_NAME_WRAPPERS:
        child, parent = parent, _zero_arg(parent, 'parent')
    return (parent is not None and _zero_arg(parent, 'kind') == 'function_declarator'
            and _same_node(parent.child_by_field_name('declarator'), child))


def _parser_language(file_path: str, family: str) -> str:
    language = language_for_extension(Path(file_path).suffix.lower()) or ''
    # `.h` is registered as C; the C++ grammar also reads C headers.
    return 'cpp' if family == 'c' and language == 'c' and file_path.endswith('.h') else language


# Declarations of a variable, parameter or field (a name being bound, not used):
# the identifier sits in one of these parents' name/declarator/pattern/left field.
_BINDING_PARENT = re.compile(
    r'variable|parameter|param|field_declaration|field_definition|property_declaration'
    r'|property_signature|let_declaration|short_var_declaration|var_spec|const_spec'
    r'|init_declarator|catch_clause|for_in|assignment')
_BINDING_FIELDS = ('name', 'declarator', 'pattern', 'left')
_FUNCTION_VALUE = re.compile(r'function|lambda|closure|arrow')
_MEMBER_BINDING = re.compile(r'parameter|param|field|property')


def _binding_kind(node):
    """How the node binds its name: 'function' for a variable bound to a
    function literal (`const f = () => {}`), 'member' for a parameter, field or
    property, 'variable' for any other variable, None when it is a use."""
    parent = _zero_arg(node, 'parent')
    if parent is None:
        return None
    parent_kind = _zero_arg(parent, 'kind')
    if parent_kind.endswith('_pattern') and parent_kind != 'type_pattern':
        return 'variable'
    if not _BINDING_PARENT.search(parent_kind):
        return None
    if not any(_same_node(parent.child_by_field_name(f), node) for f in _BINDING_FIELDS):
        return None
    if _MEMBER_BINDING.search(parent_kind):
        return 'member'
    value = parent.child_by_field_name('value')
    return 'function' if value is not None and _FUNCTION_VALUE.search(_zero_arg(value, 'kind')) else 'variable'


def _is_function_field(node) -> bool:
    """A JS-family class field whose value is a function literal (`public f = () => {}`), BACK-2180."""
    parent = _zero_arg(node, 'parent')
    if parent is None or _zero_arg(parent, 'kind') not in ('public_field_definition', 'field_definition'):
        return False
    value = parent.child_by_field_name('value')
    return value is not None and bool(_FUNCTION_VALUE.search(_zero_arg(value, 'kind')))


def _name_binding(node, kind: str, family: str, name: str, defined_here: Dict[str, int]):
    """`_binding_kind` for a name leaf. A class-field arrow method this file defines is a function: the element
    list counts it as one definition, so its own name must count as one occurrence (BACK-2180)."""
    binding = _binding_kind(node) if _is_name_leaf(kind) else None
    if binding == 'member' and family == 'js' and name in defined_here and _is_function_field(node):
        return 'function'
    return binding


def _read_reference_text(
    file_path: str, *, on_read_error: Optional[Callable[[str, OSError], None]] = None,
) -> Optional[str]:
    """Read one reference input; None is failure while empty text is valid."""
    try:
        return Path(file_path).read_text(encoding='utf-8', errors='replace')
    except OSError as error:
        if on_read_error is not None:
            on_read_error(file_path, error)
        return None


def _count_occurrences(file_path: str, family: str, names: Set[str], defined_here: Dict[str, int],
                       occurrences: Dict[Tuple[str, str], int], *,
                       on_read_error: Optional[Callable[[str, OSError], None]] = None) -> None:
    text = _read_reference_text(file_path, on_read_error=on_read_error)
    if text is None:
        return
    present = names.intersection(_WORD.findall(text))
    if not present:
        return
    try:
        tree = get_tree(_parser_language(file_path, family), text, filename=file_path)
    except Exception as e:  # noqa: BLE001 - unknown grammar or parse failure: skip the file
        logger.debug("referenced-names: cannot parse %s: %s", file_path, e)
        return
    content = text.encode('utf-8')
    counts: Dict[str, int] = {}
    bound: Set[str] = set()   # names this file declares as a variable/parameter/field
    for node in iter_tree(_zero_arg(tree, 'root_node')):
        if _zero_arg(node, 'child_count'):
            continue
        kind = _zero_arg(node, 'kind')
        if not (_is_name_leaf(kind) or kind == 'simple_symbol'
                or (kind == 'string_content' and family in _STRING_CALLBACK_FAMILIES)):
            continue
        name = content[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode(
            'utf-8', errors='replace').lstrip(':')
        if name not in present:
            continue
        if family == 'c' and _is_c_declarator_name(node):
            continue
        binding = _name_binding(node, kind, family, name, defined_here)
        # A variable of a name this file defines as a function is that definition
        # (`export const f = wrap(...)` listed as f); anything else is a separate
        # variable, parameter or field that shadows the name in this file.
        if binding == 'member' or (binding == 'variable' and name not in defined_here):
            bound.add(name)
            continue
        counts[name] = counts.get(name, 0) + 1 + (family == 'js' and _is_exported(node))
    for name, count in counts.items():
        # A same-named local, parameter or field makes this file's other
        # occurrences that variable's reads (`self.size` next to `fn size`); only
        # the file's own definitions of the name still count, to balance them.
        if name in bound:
            count = min(count, defined_here.get(name, 0))
        if not count:
            continue
        key = (family, name)
        occurrences[key] = occurrences.get(key, 0) + count


def _is_exported(node) -> bool:
    """`export function f` / `export const f = ...` / `export default function f`:
    the export is a use, as `function f; export { f }` already is."""
    parent = _zero_arg(node, 'parent')
    for _ in range(3):
        if parent is None:
            return False
        if _zero_arg(parent, 'kind') == 'export_statement':
            return True
        parent = _zero_arg(parent, 'parent')
    return False


def non_python_referenced_names(
    file_paths,
    candidates: Dict[str, Set[str]],
    definition_counts: Dict[Tuple[str, str], int],
    defined_in_file: Dict[str, Dict[str, int]],
    *, on_read_error: Optional[Callable[[str, OSError], None]] = None,
) -> Dict[str, Set[str]]:
    """Per language family, the candidate names that are used somewhere.

    `candidates` maps family -> bare names still reported uncalled; only those
    are looked for, and a file is parsed only when one appears in its text.
    `definition_counts[(family, name)]` is how many definitions of the name the
    scan found: each contributes one occurrence (its own name), so a name is
    referenced only when it occurs more often than that. In C/C++ the
    declarator names (definitions and prototypes) are skipped instead, since a
    header prototype is a second non-use occurrence the element list lacks.
    """
    occurrences: Dict[Tuple[str, str], int] = {}
    for file_path in file_paths:
        family = family_for_path(file_path)
        names = candidates.get(family)
        if names and family != 'python':
            _count_occurrences(file_path, family, names, defined_in_file.get(file_path, {}),
                               occurrences, on_read_error=on_read_error)
    referenced: Dict[str, Set[str]] = {}
    for (family, name), count in occurrences.items():
        own = 0 if family == 'c' else definition_counts.get((family, name), 0)
        if count > own:
            referenced.setdefault(family, set()).add(name)
    if candidates.get('php'):
        computed = _computed_callback_names(file_paths, candidates['php'], on_read_error)
        if computed:
            referenced.setdefault('php', set()).update(computed)
    return referenced


def _computed_callback_names(file_paths, names: Set[str],
                             on_read_error: Optional[Callable[[str, OSError], None]]) -> Set[str]:
    """Candidates a PHP file reaches by building the callback name at run time (BACK-2175).

    `do_action('wp_ajax_' . str_replace('-', '_', $action))` over a list of action strings
    never spells `wp_ajax_fetch_list`. A file that glues a literal prefix to a computed value
    and also holds a string whose word characters, with every other character read as `_`,
    complete a candidate (`fetch-list`) references `prefix + string`. Only that one file is
    read for the strings: it is where the dispatcher and its action list sit together.
    """
    found: Set[str] = set()
    for file_path in file_paths:
        if family_for_path(file_path) == 'php':
            text = _read_reference_text(file_path, on_read_error=on_read_error)
            if text is not None:
                found.update(_names_built_in(text, names))
    return found


def _tree_of(text: str, language: str):
    try:
        return get_tree(language, text)
    except Exception as e:  # noqa: BLE001 - unknown grammar or parse failure: this file adds no evidence
        logger.debug("computed-callback: cannot parse (%s): %s", language, e)
        return None


def _string_text(node, content: bytes) -> Optional[str]:
    """The text of a PHP string with no interpolation, else None."""
    parts = [c for c in node_children(node) if _zero_arg(c, 'kind') not in ('"', "'")]
    if any(_zero_arg(c, 'kind') != 'string_content' for c in parts) or len(parts) > 1:
        return None
    return b''.join(content[_zero_arg(c, 'start_byte'):_zero_arg(c, 'end_byte')] for c in parts).decode(
        'utf-8', errors='replace')


def _php_prefix_and_literals(text: str) -> Tuple[Set[str], Set[str]]:
    """Code-only facts of a PHP file: literal prefixes concatenated to a computed value
    (`'wp_ajax_' . $x`) and every plain string literal. Comments are not code."""
    tree = _tree_of(text, 'php')
    if tree is None:
        return set(), set()
    content = text.encode('utf-8')
    prefixes: Set[str] = set()
    literals: Set[str] = set()
    for node in iter_tree(_zero_arg(tree, 'root_node')):
        kind = _zero_arg(node, 'kind')
        if kind in _PHP_STRING_KINDS:
            literal = _string_text(node, content)
            if literal is not None:
                literals.add(re.sub(r'\W', '_', literal))
        elif kind == 'binary_expression':
            parts = node_children(node)
            if len(parts) == 3 and _zero_arg(parts[1], 'kind') == '.' \
                    and _zero_arg(parts[0], 'kind') in _PHP_STRING_KINDS \
                    and _zero_arg(parts[2], 'kind') not in _PHP_STRING_KINDS:
                prefix = _string_text(parts[0], content)
                if prefix and prefix.endswith('_') and len(prefix) >= _MIN_COMPUTED_PREFIX:
                    prefixes.add(prefix)
    return prefixes, literals


def _names_built_in(text: str, names: Set[str]) -> Set[str]:
    if "_'" not in text and '_"' not in text:     # no string can end in `_`: skip the parse
        return set()
    prefixes, literals = _php_prefix_and_literals(text)
    prefixes = {p for p in prefixes if any(n.startswith(p) and n != p for n in names)}
    if not prefixes:
        return set()
    return {n for n in names if any(n[:len(p)] == p and n[len(p):] in literals for p in prefixes)}


def _smallest_containing(elements: List[Dict[str, Any]], line: int):
    """The innermost function/method element whose line range holds *line* (what a call
    site in an unnamed callback is credited to: ``it(...)``, ``beforeEach``, ...)."""
    matches = [e for e in elements
               if e.get('category') in ('functions', 'methods')
               and e['line'] <= line < e['line'] + max(e['line_count'], 1)]
    return min(matches, key=lambda e: e['line_count']) if matches else None


_COMPONENT_WRAPPER = re.compile(r'(?:React\.)?(?:memo|forwardRef)')


def _is_binding_name(analyzer, function_node) -> bool:
    """Whether a function value takes the name of the variable it is assigned to.

    BACK-1832: `const keys = list.map((k) => <Key/>)` outlines `keys` as a function, but a
    callback to an ordinary call computes a value and owns nothing, so its JSX belongs to
    the scope above. Only the component wrappers (memo, forwardRef) pass their function's name on.
    """
    arguments = _zero_arg(function_node, 'parent')
    if arguments is None or _zero_arg(arguments, 'kind') != 'arguments':
        return True
    call = _zero_arg(arguments, 'parent')
    callee = call.child_by_field_name('function') if call is not None else None
    return callee is not None and bool(_COMPONENT_WRAPPER.fullmatch(analyzer._get_node_text(callee)))


def _jsx_owner(analyzer, node, by_name, value_names, elements):
    """(owner element or None, line of the innermost deferred scope or None) for one JSX use."""
    from ...core.nav_calls import is_deferred_scope
    parent = _zero_arg(node, 'parent')
    deferred_line = None
    while parent is not None:
        kind = _zero_arg(parent, 'kind')
        if kind in ('class_declaration', 'class', 'abstract_class_declaration'):
            # Class field initializers retain their source owner; they are not module callers.
            return {'name': analyzer._get_node_name(parent) or '<class>',
                    'line': _zero_arg(parent, 'start_position').row + 1}, deferred_line
        if is_deferred_scope(parent):
            name = value_names.get((_zero_arg(parent, 'start_byte'), _zero_arg(parent, 'end_byte'))) \
                if _is_binding_name(analyzer, parent) else None
            name = name or analyzer._get_node_name(parent)
            line = _zero_arg(parent, 'start_position').row + 1
            deferred_line = deferred_line or line
            matches = [e for e in by_name.get(name, []) if e['line'] <= line < e['line'] + max(e['line_count'], 1)]
            if matches:
                return min(matches, key=lambda e: e['line_count']), deferred_line
        parent = _zero_arg(parent, 'parent')
    if deferred_line:
        # BACK-1829: an unnamed callback (test blocks, hooks) has no name to match, so use the
        # rule call sites use: the smallest containing element by line range.
        return _smallest_containing(elements, _zero_arg(node, 'start_position').row + 1), deferred_line
    return None, deferred_line


def _owner_tables(analyzer, elements):
    """(elements by name, function-value names by byte span): what `_jsx_owner` resolves against."""
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for element in elements:
        if element.get('category') in ('functions', 'methods'):
            by_name.setdefault(element['name'], []).append(element)
    values = analyzer._iter_function_values() if hasattr(analyzer, '_iter_function_values') else ()
    value_names = {(_zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte')): name for name, node in values}
    return by_name, value_names


def _owner_fields(owner, deferred_line):
    return {'owner': owner['name'] if owner else '<anonymous>' if deferred_line else '<module>',
            'owner_line': owner['line'] if owner else deferred_line or 1}


def jsx_component_references(analyzer, elements):
    """Typed component uses attributed through the analyzer's existing function owners."""
    from ...core.nav_calls import jsx_reference_hit
    tree = analyzer.tree
    if tree is None:
        return []
    by_name, value_names = _owner_tables(analyzer, elements)
    references = []
    for node in iter_tree(_zero_arg(tree, 'root_node')):
        reference = jsx_reference_hit(node, analyzer._get_node_text)
        if reference is None:
            continue
        owner, deferred_line = _jsx_owner(analyzer, node, by_name, value_names, elements)
        references.append({**reference, **_owner_fields(owner, deferred_line)})
    return references


def jsx_owner_call_sites(analyzer, elements, references):
    """Call lines of the names a scope also renders (BACK-1834 F7).

    A function element lists its callees without lines, so `Btn(); return <Btn/>` could only
    show the JSX line. Each call to a rendered name is attributed through the same owner seam
    as its JSX use; `call_sources` joins the two on (owner, owner_line, callee).
    """
    from ...treesitter import CALL_NODE_TYPES
    tree = analyzer.tree
    rendered = {r['callee'] for r in references}
    if tree is None or not rendered:
        return []
    by_name, value_names = _owner_tables(analyzer, elements)
    sites = []
    for node in iter_tree(_zero_arg(tree, 'root_node')):
        if _zero_arg(node, 'kind') not in CALL_NODE_TYPES:
            continue
        callee = analyzer._get_callee_name(node)
        if callee not in rendered:
            continue
        owner, deferred_line = _jsx_owner(analyzer, node, by_name, value_names, elements)
        sites.append({'callee': callee, 'line': _zero_arg(node, 'start_position').row + 1,
                      **_owner_fields(owner, deferred_line)})
    return sites


def reflected_annotation_types(file_paths, *,
                               on_read_error: Optional[Callable[[str, OSError], None]] = None) -> Set[str]:
    """Annotation types the scan declares and some code reads through reflection (BACK-2176).

    `FreshValueGenerator` keeps the methods where `isAnnotationPresent(Generates.class)` holds
    and invokes them by return type, so no call names a `@Generates` method. A type that is
    both declared here (`@interface X`) and read here (`X.class` handed to the reflection API)
    marks its methods as entry points. An annotation the project does not declare (a library's
    own) or never reads this way marks nothing; a framework that reads from outside the scan
    (Caliper `@Benchmark`) stays out of reach of a rule that needs the reader in the scan.
    """
    declared: Set[str] = set()
    read: Set[str] = set()
    for file_path in file_paths:
        if family_for_path(file_path) != 'java':
            continue
        text = _read_reference_text(file_path, on_read_error=on_read_error)
        if text is not None and ('@interface' in text or '.class' in text):
            file_declared, file_read = _java_annotation_facts(text)
            declared |= file_declared
            read |= file_read
    return declared & read


def _reflected_class_names(call, name: Callable) -> Set[str]:
    """`X` of `recv.isAnnotationPresent(X.class)`, else nothing."""
    parts = node_children(call)
    callee = [c for c in parts if _zero_arg(c, 'kind') == 'identifier']
    args = [c for c in parts if _zero_arg(c, 'kind') == 'argument_list']
    if not (callee and args and name(callee[-1]) in _JAVA_ANNOTATION_READS):
        return set()
    literals = [c for c in node_children(args[0]) if _zero_arg(c, 'kind') == 'class_literal']
    return {name(t) for lit in literals for t in node_children(lit) if _zero_arg(t, 'kind') == 'type_identifier'}


def _java_annotation_facts(text: str) -> Tuple[Set[str], Set[str]]:
    """Annotation types a Java file declares (`@interface X`) and reads reflectively
    (`m.isAnnotationPresent(X.class)`), from the parse tree: comments and strings do neither."""
    tree = _tree_of(text, 'java')
    if tree is None:
        return set(), set()
    content = text.encode('utf-8')
    name = lambda n: content[_zero_arg(n, 'start_byte'):_zero_arg(n, 'end_byte')].decode('utf-8', errors='replace')
    declared: Set[str] = set()
    read: Set[str] = set()
    for node in iter_tree(_zero_arg(tree, 'root_node')):
        kind = _zero_arg(node, 'kind')
        if kind == 'annotation_type_declaration':
            declared.update(name(c) for c in node_children(node) if _zero_arg(c, 'kind') == 'identifier')
        elif kind == 'method_invocation':
            read.update(_reflected_class_names(node, name))
    return declared, read
