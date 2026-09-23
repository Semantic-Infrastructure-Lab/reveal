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
from typing import Dict, Set, Tuple

from ...core import iter_tree, ts_parse, _zero_arg
from ...conventions import family_for_path
from ...registry import language_for_extension

logger = logging.getLogger(__name__)

_WORD = re.compile(r'[A-Za-z_$][\w$]*')
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


def _count_occurrences(file_path: str, family: str, names: Set[str], defined_here: Dict[str, int],
                       occurrences: Dict[Tuple[str, str], int]) -> None:
    try:
        text = Path(file_path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return
    present = names.intersection(_WORD.findall(text))
    if not present:
        return
    try:
        from tree_sitter_language_pack import get_parser
        tree = ts_parse(get_parser(_parser_language(file_path, family)), text)
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
        binding = _binding_kind(node) if _is_name_leaf(kind) else None
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
                               occurrences)
    referenced: Dict[str, Set[str]] = {}
    for (family, name), count in occurrences.items():
        own = 0 if family == 'c' else definition_counts.get((family, name), 0)
        if count > own:
            referenced.setdefault(family, set()).add(name)
    return referenced
