"""Untyped-dict usage analysis for Python source.

Shared engine behind `ast://?show=dict-heatmap`, `ast://?show=dict-schemas`
and rule T006. For every function it finds each name used as an untyped dict
-- string keys read via subscript, `.get()`/`.pop()`/`.setdefault()`, or
`'key' in name` -- and can cluster those reads across files into implicit
record schemas and match them against TypedDicts that already exist.

Which names count (the `source` field of a usage):
    annotated_param    param annotated dict / Dict[...] / Mapping / Any, a dict
                       type alias, or Optional/Union of those
    unannotated_param  param with no annotation at all
    loop_var           for-loop / comprehension target -- the element records
                       of a List[Dict] (`for elem in structure['functions']`)
    local              name assigned inside the function
    attribute          `self.<attr>` / `cls.<attr>` read with keys
Names annotated with anything more specific (a TypedDict, a dataclass, int...)
are already typed and are skipped. Unannotated names need MIN_UNTYPED_KEYS
distinct keys, so a lone `x['k']` doesn't become noise; an explicit dict
annotation needs only one.

Keys may be string literals or ALL_CAPS constants (`config[CONF_NAME]`); a
constant is resolved to its literal when the ScanContext knows it, else kept
as its symbol, which is still a stable key for comparing shapes.

Usage record:
    {
        'file': str, 'function': str, 'line': int,
        'param': str,          # the variable name (kept as 'param' for compat)
        'source': str,         # see above
        'annotation': str,     # '' when unannotated
        'iterable': str,       # loop_var only: what it iterates, else ''
        'key_count': int,      # distinct keys
        'access_count': int,   # total key reads
        'keys': List[str],
        'suggested_name': str,
    }

TypedDict record: {'name': str, 'file': str, 'line': int, 'fields': List[str]}
"""
from __future__ import annotations

import ast
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Iterator, List, Optional, Set, Tuple

from ..utils.path_utils import is_skippable_dir

_TypeAliasStmt = getattr(ast, 'TypeAlias', None)  # `type X = ...`, Python 3.12+

_DICT_ANNOTATION_NAMES = frozenset({
    'dict', 'Dict', 'Mapping', 'MutableMapping', 'Any', 'DefaultDict', 'OrderedDict',
})
_WRAPPER_ANNOTATION_NAMES = frozenset({'Optional', 'Union'})
_KEY_METHODS = frozenset({'get', 'pop', 'setdefault'})
_SKIP_NAMES = frozenset({'self', 'cls'})
_FuncNode = (ast.FunctionDef, ast.AsyncFunctionDef)

MIN_UNTYPED_KEYS = 2
SCHEMA_MIN_SHARED_KEYS = 3
SCHEMA_MIN_OVERLAP = 0.6
SCHEMA_MIN_CONSUMERS = 2


@dataclass(frozen=True)
class ScanContext:
    """Facts a single function can't see on its own, gathered at module level
    across whatever set of files the caller parsed."""
    # ALL_CAPS key constant -> its literal; None when defined with conflicting values
    constants: Dict[str, Optional[str]] = field(default_factory=dict)
    # names aliasing an untyped dict type (`ConfigType = dict[str, Any]`)
    dict_aliases: FrozenSet[str] = frozenset()


# ─────────────────────────── whole-path entry points ─────────────────────────

def collect_dict_analysis(path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(usage records, TypedDicts) for every .py/.pyi under path.

    Two phases because key constants and dict aliases are usually defined in
    a different module (const.py, typing.py) from the ones reading them: every
    file is parsed first to build the context, then functions are scanned.
    """
    trees = [(f, t) for f in iter_python_files(path) for t in [parse_file(f)] if t is not None]
    ctx = build_context(t for _, t in trees)

    usages: List[Dict[str, Any]] = []
    raw_typeddicts: Dict[str, List[Dict[str, Any]]] = {}
    for file_path, tree in trees:
        collect_typeddict_definitions(tree, file_path, raw_typeddicts)
        for node in ast.walk(tree):
            if isinstance(node, _FuncNode):
                usages.extend(function_dict_usages(node, file_path, ctx))
    usages.sort(key=lambda x: (-x['key_count'], -x['access_count'], x['file'], x['line']))
    return usages, resolve_typeddicts(raw_typeddicts)


def collect_dict_heatmap(path: str) -> List[Dict[str, Any]]:
    """Usage records under path, most distinct keys first."""
    return collect_dict_analysis(path)[0]


def has_python_files(path: str) -> bool:
    """True if `path` is, or contains, at least one .py/.pyi file.

    Used to tell "genuinely clean Python project" apart from "no Python
    source here at all" when a report comes back empty (BACK-749).
    """
    return next(iter_python_files(path), None) is not None


def iter_python_files(path: str) -> Iterator[str]:
    path_obj = Path(path)
    if path_obj.is_file():
        if path_obj.suffix in ('.py', '.pyi'):
            yield str(path_obj)
        return
    if not path_obj.is_dir():
        return
    for root, dirs, files in os.walk(str(path_obj)):
        dirs[:] = sorted(
            d for d in dirs
            if not d.startswith('.')
            and not is_skippable_dir(Path(root), d)
            and not d.endswith('.egg-info')
        )
        for name in sorted(files):
            if name.endswith(('.py', '.pyi')):
                yield str(Path(root) / name)


def parse_file(file_path: str) -> Optional[ast.Module]:
    try:
        return ast.parse(Path(file_path).read_text(encoding='utf-8', errors='replace'))
    except (SyntaxError, OSError, ValueError):
        return None


# ─────────────────────────── context ─────────────────────────────────────────

def build_context(
    trees: Iterable[ast.Module],
    known_aliases: FrozenSet[str] = frozenset(),
) -> ScanContext:
    """Key constants (`ALL_CAPS = 'literal'`) and dict type aliases defined at
    module level in `trees`. Aliases resolve to a fixpoint, seeded with
    `known_aliases`, so `A = dict[str, Any]; B = Optional[A]` makes both."""
    constants: Dict[str, Optional[str]] = {}
    alias_candidates: Dict[str, ast.expr] = {}
    for tree in trees:
        for name, value in _module_assignments(tree):
            if _is_constant_name(name) and _is_str_literal(value):
                previous = constants.get(name, value.value)
                constants[name] = value.value if previous == value.value else None
            elif isinstance(value, (ast.Name, ast.Attribute, ast.Subscript, ast.BinOp)):
                alias_candidates[name] = value
    aliases = _resolve_aliases(alias_candidates, known_aliases)
    return ScanContext(constants=constants, dict_aliases=aliases)


def _resolve_aliases(candidates: Dict[str, ast.expr], known: FrozenSet[str]) -> FrozenSet[str]:
    aliases: Set[str] = set(known)
    changed = True
    while changed:
        changed = False
        for name, value in candidates.items():
            if name not in aliases and is_untyped_dict(value, frozenset(aliases)):
                aliases.add(name)
                changed = True
    return frozenset(aliases)


def _module_assignments(tree: ast.Module) -> Iterator[Tuple[str, ast.expr]]:
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target, value = stmt.targets[0], stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            target, value = stmt.target, stmt.value
        elif _TypeAliasStmt is not None and isinstance(stmt, _TypeAliasStmt):
            target, value = stmt.name, stmt.value
        else:
            continue
        if isinstance(target, ast.Name):
            yield target.id, value


def _is_constant_name(name: str) -> bool:
    return name.isupper() and any(c.isalpha() for c in name)


def _is_str_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


# ─────────────────────────── per-function usage ──────────────────────────────

def function_dict_usages(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    ctx: Optional[ScanContext] = None,
) -> List[Dict[str, Any]]:
    """Usage records for every untyped-dict name in one function body
    (nested functions excluded -- they get their own call)."""
    ctx = ctx or ScanContext()
    bindings = _collect_bindings(func_node, ctx.dict_aliases)
    reads = _collect_key_reads(func_node, set(bindings), ctx)
    for owner in reads:
        if owner not in bindings and '.' in owner:
            bindings[owner] = ('attribute', '', '')

    usages = []
    for name, (source, annotation, iterable) in bindings.items():
        key_reads = reads.get(name)
        if not key_reads:
            continue
        keys = set(key_reads)
        if not annotation and len(keys) < MIN_UNTYPED_KEYS:
            continue
        usages.append({
            'file': file_path,
            'function': func_node.name,
            'line': func_node.lineno,
            'param': name,
            'source': source,
            'annotation': annotation,
            'iterable': iterable,
            'key_count': len(keys),
            'access_count': len(key_reads),
            'keys': sorted(keys),
            'suggested_name': suggest_typeddict_name(name),
        })
    return usages


def has_untyped_dict_param(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    aliases: FrozenSet[str] = frozenset(),
) -> bool:
    """Signature-only check: does any param carry an untyped-dict annotation?
    Lets a caller that only cares about annotated params skip the body walk."""
    args = func_node.args
    return any(
        param.annotation is not None and is_untyped_dict(param.annotation, aliases)
        for param in args.posonlyargs + args.args + args.kwonlyargs
    )


def _own_nodes(func_node: ast.AST) -> Iterator[ast.AST]:
    """Walk a function body in document order without descending into nested
    defs/classes -- those are scanned as functions in their own right."""
    stack = list(reversed(list(ast.iter_child_nodes(func_node))))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (*_FuncNode, ast.ClassDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _collect_bindings(
    func_node: ast.AST,
    aliases: FrozenSet[str] = frozenset(),
) -> Dict[str, Tuple[str, str, str]]:
    """name -> (source, annotation_text, iterable_text) for every name the
    function binds that could be an untyped dict. First binding wins, and
    params are bound first, so a reassigned param keeps its param source."""
    bindings, typed = _param_bindings(func_node.args, aliases)
    for node in _own_nodes(func_node):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if not is_untyped_dict(node.annotation, aliases):
                typed.add(name)
            elif name not in bindings and name not in typed:
                bindings[name] = ('local', ast.unparse(node.annotation), '')
            continue
        for target, source, iterable in _bound_targets(node):
            for name_node in _target_names(target):
                name = name_node.id
                if name not in _SKIP_NAMES and name not in typed and name not in bindings:
                    bindings[name] = (source, '', iterable)
    return bindings


def _param_bindings(
    args: ast.arguments,
    aliases: FrozenSet[str],
) -> Tuple[Dict[str, Tuple[str, str, str]], Set[str]]:
    """(untyped-dict-capable params, params typed as something more specific)."""
    bindings: Dict[str, Tuple[str, str, str]] = {}
    typed: Set[str] = set()
    for param in (
        args.posonlyargs + args.args + args.kwonlyargs
        + ([args.vararg] if args.vararg else [])
        + ([args.kwarg] if args.kwarg else [])
    ):
        if param.arg in _SKIP_NAMES:
            continue
        if param.annotation is None:
            bindings[param.arg] = ('unannotated_param', '', '')
        elif is_untyped_dict(param.annotation, aliases):
            bindings[param.arg] = ('annotated_param', ast.unparse(param.annotation), '')
        else:
            typed.add(param.arg)
    return bindings, typed


def _bound_targets(node: ast.AST) -> List[Tuple[ast.AST, str, str]]:
    """(target, source, iterable_text) for each name-binding target of an
    unannotated binding statement. AnnAssign is handled by the caller."""
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return [(node.target, 'loop_var', _short(node.iter))]
    if isinstance(node, ast.Assign):
        return [(target, 'local', '') for target in node.targets]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [(w.optional_vars, 'local', '') for w in node.items if w.optional_vars is not None]
    if isinstance(node, ast.NamedExpr):
        return [(node.target, 'local', '')]
    return []


def _target_names(target: ast.AST) -> Iterator[ast.Name]:
    if isinstance(target, ast.Name):
        yield target
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _target_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)


def _collect_key_reads(
    func_node: ast.AST,
    names: Set[str],
    ctx: ScanContext,
) -> Dict[str, List[str]]:
    """owner -> every key read on it (duplicates kept, for access_count)."""
    reads: Dict[str, List[str]] = {}

    def record(owner: ast.AST, key_node: Optional[ast.AST]) -> None:
        name = _owner_name(owner, names)
        key = _key_text(key_node, ctx.constants) if name is not None else None
        if key is not None:
            reads.setdefault(name, []).append(key)

    for node in _own_nodes(func_node):
        if isinstance(node, ast.Subscript):
            record(node.value, node.slice)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _KEY_METHODS
            and node.args
        ):
            record(node.func.value, node.args[0])
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            if isinstance(node.ops[0], (ast.In, ast.NotIn)):
                record(node.comparators[0], node.left)
    return reads


def _owner_name(owner: ast.AST, names: Set[str]) -> Optional[str]:
    """A bound local name, or `self.<attr>` / `cls.<attr>` (an instance or
    class attribute used as an untyped dict across a class's methods)."""
    if isinstance(owner, ast.Name):
        return owner.id if owner.id in names else None
    if (
        isinstance(owner, ast.Attribute)
        and isinstance(owner.value, ast.Name)
        and owner.value.id in _SKIP_NAMES
    ):
        return f"{owner.value.id}.{owner.attr}"
    return None


def _key_text(key_node: Optional[ast.AST], constants: Dict[str, Optional[str]]) -> Optional[str]:
    """A string-literal key, or an ALL_CAPS key constant (`CONF_NAME`,
    `const.ATTR_ID`) -- resolved to its literal when known unambiguously, else
    kept as the symbol."""
    if _is_str_literal(key_node):
        return key_node.value
    symbol = None
    if isinstance(key_node, ast.Name):
        symbol = key_node.id
    elif isinstance(key_node, ast.Attribute):
        symbol = key_node.attr
    if symbol is None or not _is_constant_name(symbol):
        return None
    return constants.get(symbol) or symbol


def is_untyped_dict(annotation: ast.expr, aliases: FrozenSet[str] = frozenset()) -> bool:
    """dict / Dict[...] / Mapping[...] / Any (or a known alias of one),
    optionally wrapped in Optional[...] or a Union / `X | None` of only such types."""
    dict_names = _DICT_ANNOTATION_NAMES | aliases
    if isinstance(annotation, ast.Constant):
        if not isinstance(annotation.value, str):
            return False
        try:
            return is_untyped_dict(ast.parse(annotation.value, mode='eval').body, aliases)
        except SyntaxError:
            return False
    if isinstance(annotation, ast.Name):
        return annotation.id in dict_names
    if isinstance(annotation, ast.Attribute):
        return annotation.attr in dict_names
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _union_is_untyped_dict([annotation.left, annotation.right], aliases)
    if isinstance(annotation, ast.Subscript):
        base_name = _base_name(annotation.value)
        if base_name in _WRAPPER_ANNOTATION_NAMES:
            inner = annotation.slice
            members = inner.elts if isinstance(inner, ast.Tuple) else [inner]
            return _union_is_untyped_dict(members, aliases)
        return base_name in dict_names
    return False


def _union_is_untyped_dict(members: List[ast.expr], aliases: FrozenSet[str]) -> bool:
    non_none = [m for m in members if not (isinstance(m, ast.Constant) and m.value is None)]
    return bool(non_none) and all(is_untyped_dict(m, aliases) for m in non_none)


def _short(node: ast.AST, limit: int = 60) -> str:
    text = ast.unparse(node)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def suggest_typeddict_name(name: str) -> str:
    """'trade' → 'TradeState', 'self._config' → 'ConfigState',
    'query_params' → 'QueryParamsState', 'ASTElement' → 'ASTElementState'.

    Each underscore-separated part gets its first letter upper-cased and the
    rest left alone (``str.capitalize`` would lower-case ``ASTElement`` and
    leave ``query_params`` as ``Query_params``). A name already ending in
    ``State`` is not suffixed twice.
    """
    base = re.sub(r'[^0-9A-Za-z_]', '', name.rsplit('.', 1)[-1])
    camel = ''.join(part[0].upper() + part[1:] for part in base.split('_') if part)
    if not camel or camel[0].isdigit():
        return 'ItemState'
    return camel if camel.endswith('State') else camel + 'State'


# ─────────────────────────── TypedDict definitions ───────────────────────────

def collect_typeddict_definitions(
    tree: ast.Module,
    file_path: str,
    raw: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Record every class (a potential TypedDict or TypedDict base) and every
    functional `X = TypedDict('X', ...)` in `tree` into `raw`, keyed by bare
    name. resolve_typeddicts() decides which classes really are TypedDicts."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            raw.setdefault(node.name, []).append({
                'name': node.name, 'file': file_path, 'line': node.lineno,
                'bases': [_base_name(b) for b in node.bases],
                'own_fields': [
                    stmt.target.id for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                ],
                'functional': False,
            })
    for name, value in _module_assignments(tree):
        fields = _functional_typeddict_fields(value)
        if fields:
            raw.setdefault(name, []).append({
                'name': name, 'file': file_path, 'line': value.lineno,
                'bases': [], 'own_fields': fields, 'functional': True,
            })


def _functional_typeddict_fields(value: ast.expr) -> List[str]:
    """Fields of `TypedDict('X', a=int)` or `TypedDict('X', {'a': int})`."""
    if not (isinstance(value, ast.Call) and _base_name(value.func) == 'TypedDict'):
        return []
    fields = [kw.arg for kw in value.keywords if kw.arg and kw.arg != 'total']
    if len(value.args) >= 2 and isinstance(value.args[1], ast.Dict):
        fields.extend(k.value for k in value.args[1].keys if _is_str_literal(k))
    return fields


def resolve_typeddicts(raw: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Keep only TypedDicts (functional, subclassing TypedDict, or subclassing a
    TypedDict defined in `raw`) with inherited fields folded in. Base classes
    are looked up by bare name; when two definitions share a name, a subclass
    inherits from the first -- acceptable for suggestions, not type checking."""
    memo: Dict[str, Optional[List[str]]] = {}

    def fields_of(entry: Dict[str, Any], seen: Tuple[str, ...]) -> Optional[List[str]]:
        if entry['functional']:
            return list(entry['own_fields'])
        inherited: List[str] = []
        is_typeddict = False
        for base in entry['bases']:
            if base == 'TypedDict':
                is_typeddict = True
                continue
            base_fields = inherited_fields(base, seen + (entry['name'],))
            if base_fields is not None:
                is_typeddict = True
                inherited.extend(base_fields)
        return inherited + entry['own_fields'] if is_typeddict else None

    def inherited_fields(name: str, seen: Tuple[str, ...]) -> Optional[List[str]]:
        if name in seen or name not in raw:
            return None
        if name not in memo:
            memo[name] = fields_of(raw[name][0], seen)
        return memo[name]

    resolved = []
    for entries in raw.values():
        for entry in entries:
            fields = fields_of(entry, ())
            if fields:
                resolved.append({
                    'name': entry['name'], 'file': entry['file'], 'line': entry['line'],
                    'fields': sorted(set(fields)),
                })
    return resolved


def best_typeddict_match(
    keys: Set[str],
    typeddicts: List[Dict[str, Any]],
    min_shared: int = SCHEMA_MIN_SHARED_KEYS,
) -> Optional[Tuple[Dict[str, Any], Set[str]]]:
    """(TypedDict, matched keys) that best explains `keys`: at least
    `min_shared` shared, covering at least SCHEMA_MIN_OVERLAP of `keys`.
    Most shared keys wins; ties keep list order."""
    best: Optional[Tuple[Dict[str, Any], Set[str]]] = None
    for td in typeddicts:
        matched = keys & set(td['fields'])
        if len(matched) < min_shared or len(matched) / len(keys) < SCHEMA_MIN_OVERLAP:
            continue
        if best is None or len(matched) > len(best[1]):
            best = (td, matched)
    return best


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ''


# ─────────────────────────── implicit schemas ────────────────────────────────

def collect_dict_schemas(
    usages: List[Dict[str, Any]],
    typeddicts: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Cluster usage records into implicit record schemas read in
    SCHEMA_MIN_CONSUMERS+ functions.

    Seed-based, not union-growing: each cluster is anchored on its first
    (largest) member's key set, and a usage joins only if it shares at least
    SCHEMA_MIN_SHARED_KEYS keys with the seed and those keys are at least
    SCHEMA_MIN_OVERLAP of its own keys. Growing a cluster by union would let
    generic keys ('path', 'name') chain unrelated shapes together.

    Each schema lists TypedDicts that already describe it
    (`typeddict_matches`) plus the keys its readers use that the TypedDict
    does not declare -- a TypedDict that exists but is bypassed, or has drifted.
    """
    schemas = []
    for seed, members in _cluster_by_seed(usages):
        if len({(m['file'], m['function']) for m in members}) >= SCHEMA_MIN_CONSUMERS:
            schemas.append(_build_schema(seed, members, typeddicts or []))
    schemas.sort(key=lambda s: (-s['file_count'], -s['consumer_count'], s['suggested_name']))
    return schemas


def _cluster_by_seed(usages: List[Dict[str, Any]]) -> List[Tuple[Set[str], List[Dict[str, Any]]]]:
    clusters: List[Tuple[Set[str], List[Dict[str, Any]]]] = []
    for usage in sorted(usages, key=lambda x: (-x['key_count'], x['file'], x['line'])):
        keys = set(usage['keys'])
        if len(keys) < SCHEMA_MIN_SHARED_KEYS:
            continue
        for seed, members in clusters:
            shared = keys & seed
            overlap = len(shared) / len(keys)
            if len(shared) >= SCHEMA_MIN_SHARED_KEYS and overlap >= SCHEMA_MIN_OVERLAP:
                members.append(usage)
                break
        else:
            clusters.append((keys, [usage]))
    return clusters


def _build_schema(
    seed: Set[str],
    members: List[Dict[str, Any]],
    typeddicts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    key_freq = Counter(k for m in members for k in m['keys'])
    name_freq = Counter(m['param'] for m in members)
    return {
        'suggested_name': suggest_typeddict_name(name_freq.most_common(1)[0][0]),
        'consumer_count': len({(m['file'], m['function']) for m in members}),
        'file_count': len({m['file'] for m in members}),
        'seed_keys': sorted(seed),
        'keys': [{'key': k, 'consumers': n} for k, n in key_freq.most_common()],
        'variable_names': [n for n, _ in name_freq.most_common()],
        'sources': dict(Counter(m['source'] for m in members)),
        'typeddict_matches': _match_typeddicts(key_freq, typeddicts),
        'consumers': [
            {k: m[k] for k in ('file', 'line', 'function', 'param', 'source')}
            for m in members
        ],
    }


def _match_typeddicts(key_freq: Counter, typeddicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """TypedDicts covering a schema's core keys (read by 2+ consumers, or all
    keys when every key is read once)."""
    core = {k for k, n in key_freq.items() if n >= 2} or set(key_freq)
    matches = []
    for td in typeddicts:
        fields = set(td['fields'])
        covered = core & fields
        if len(covered) < SCHEMA_MIN_SHARED_KEYS or len(covered) / len(core) < SCHEMA_MIN_OVERLAP:
            continue
        matches.append({
            'name': td['name'],
            'file': td['file'],
            'line': td['line'],
            'coverage': round(len(covered) / len(core), 2),
            'undeclared_keys': sorted(k for k in key_freq if k not in fields),
        })
    matches.sort(key=lambda m: (-m['coverage'], m['name']))
    return matches[:3]
