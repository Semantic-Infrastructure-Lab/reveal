"""contracts:// adapter - contract and seam inventory for a codebase.

Scan/render logic lives here (BACK-905). The `reveal contracts` command is generated from this
adapter's declaration (BACK-901), as for surface.py (BACK-904).
"""

from __future__ import annotations

from pathlib import Path
from functools import partial
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

from reveal.reveal_types import CONTRACT_VERSION, ErrorEntry, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from .surface import _supported_coverage_languages, _unparsed_note
from .ast.analysis import analysis_skipped_warning
from .ast.surface_matrix import RECOVERED_KEY, UNPARSED_KEY
from ..registry import JS_TS_LANGUAGES, _is_cpp_header_content, extensions_for_languages
from ..utils.path_utils import (
    _language_for_path,
    _walk_code_files,
    assess_language_coverage,
    detect_non_python_language,
    to_posix,
    traversal_failed_warning,
    failure_of,
)
from ..utils.query_binding import bind_declared_params, boolean_value
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec,
                                  nonnegative_display_limit, param_schema)
from ..utils.results import ResultBuilder
from ..rendering.adapters.contracts import ContractsRenderer
from ..reveal_types import PathFailure

_CONTRACT_PATH_HINTS: frozenset = frozenset({
    'base', 'schema', 'contract', 'protocol', 'interface',
    'types', 'models', 'dto', 'abstract', 'abc',
})


# BACK-403 pt 2: languages whose grammar has a distinct interface/abstract-class
# shape close enough to TS's ('interfaces'/'types'/'classes' categories, an
# is_abstract flag on classes) that they share _scan_contracts_ts's classifier
# rather than needing their own. Java/C#/PHP/Swift/Kotlin added — each analyzer
# (analyzers/java.py, csharp.py, php.py, swift.py, kotlin.py) now emits the same
# shape TS does (interfaces/protocols → 'interfaces'; abstract classes flagged
# is_abstract; concrete classes carry their bases).
# BACK-631: plain JS/JSX added — JavaScriptAnalyzer is TreeSitterAnalyzer with
# no overrides, emitting the same 'classes' category (no interfaces/types,
# since JS has no interface/type-alias/abstract-class grammar — correctly
# absent rather than a gap) so it shares the classifier with zero code changes.
# Every extension set here comes from the registry (BACK-1255): the hand-kept
# ones missed .mts/.cts (BACK-1403) and .h++.
_INTERFACE_FAMILY_EXTENSIONS: frozenset = extensions_for_languages(
    *JS_TS_LANGUAGES, 'java', 'csharp', 'php', 'swift', 'kotlin')
_CPP_EXTENSIONS: frozenset = extensions_for_languages('cpp')


def _suffix_in(extensions: frozenset) -> Callable[[Path], bool]:
    def matches(fpath: Path) -> bool:
        return fpath.suffix.lower() in extensions
    return matches


_is_interface_family_file = _suffix_in(_INTERFACE_FAMILY_EXTENSIONS)
_is_python_file = _suffix_in(extensions_for_languages('python'))
_is_ruby_file = _suffix_in(extensions_for_languages('ruby'))
_is_go_file = _suffix_in(extensions_for_languages('go'))
_is_rust_file = _suffix_in(extensions_for_languages('rust'))

# BACK-630: `.h` is ambiguous between C and C++ (registry.py routes it to C by
# default). A header-only C++ class (Godot-style abstract base with no .cpp)
# is only included here if content-sniffed as C++ — see _is_cpp_header_content,
# same marker set the registry uses for single-file analyzer selection.


def _is_cpp_file(fpath: Path) -> bool:
    suffix = fpath.suffix.lower()
    if suffix in _CPP_EXTENSIONS:
        return True
    if suffix == '.h':
        return _is_cpp_header_content(str(fpath))
    return False


def _walk_matching(path: Path, matches: Callable[[Path], bool], *,
                   on_error: Optional[Callable[[OSError], None]] = None) -> Iterator[Path]:
    """Files under *path* (or *path* itself) that *matches* accepts, through the shared
    walker (BACK-1577): the same files ``collect_structures`` hands the Python and
    TypeScript scanners, dot-dir source included (BACK-1038)."""
    if path.is_file():
        if matches(path):
            yield path
        return
    for fpath in _walk_code_files(path, on_error=on_error):
        if matches(fpath):
            yield fpath


def _has_files(path: Path, matches: Callable[[Path], bool], *,
               on_error: Optional[Callable[[OSError], None]] = None) -> bool:
    return next(_walk_matching(path, matches, on_error=on_error), None) is not None


def _collect_files(path: Path, matches: Callable[[Path], bool], *,
                   on_error: Optional[Callable[[OSError], None]] = None) -> List[Path]:
    """Files a scanner reads (an explicitly named single file is never excluded)."""
    return list(_walk_matching(path, matches, on_error=on_error))


def _unparsed_files(unparsed: List[str]) -> List[str]:
    """Files a tree-sitter contracts scanner could not parse (BACK-1588), spelled
    like the entries' `file` (the walk's path, '/' on every OS)."""
    return sorted(to_posix(f) for f in unparsed)


# Each contract scanner and the files that make it active, in merge order.
_CONTRACT_LANGUAGES: Tuple[Tuple[str, Callable[[Path], bool]], ...] = (
    ('ts', _is_interface_family_file),
    ('ruby', _is_ruby_file),
    ('go', _is_go_file),
    ('rust', _is_rust_file),
    ('cpp', _is_cpp_file),
    ('python', _is_python_file),
)


def _record_traversal_error(failures: List[PathFailure], error: OSError) -> None:
    failures.append(failure_of(error))


def _record_scan_error(skipped: List[Tuple[str, str]], file: str, exc: Exception) -> None:
    skipped.append((to_posix(file), f'{type(exc).__name__}: {exc}'))


def _with_analysis_skipped(report: Dict[str, Any], skipped: List[Tuple[str, str]], *,
                           recovered: Optional[List[str]] = None) -> Dict[str, Any]:
    """Merge input evidence once; failed coverage counts files, never channels."""
    causes: Dict[str, Set[str]] = {}
    for file, cause in [*report.get('analysis_skipped', []), *skipped]:
        causes.setdefault(to_posix(file), set()).add(cause)
    if causes:
        report['analysis_skipped'] = [[file, '; '.join(sorted(values))]
                                      for file, values in sorted(causes.items())]
    if 'unparsed_files' in report:
        report['unparsed_files'] = sorted(set(to_posix(file) for file in report['unparsed_files']))
    recovered_files = set(to_posix(file) for file in [*report.get('recovered_files', []), *(recovered or [])])
    if recovered_files:
        report['recovered_files'] = sorted(recovered_files)
    coverage = report.get('coverage')
    if coverage:
        supported = _supported_coverage_languages()
        failed = set(causes) | set(report.get('unparsed_files', []))
        count = sum(_language_for_path(Path(file)) in supported for file in failed)
        report['coverage'] = {**coverage, 'analyzed_files': max(0, coverage['analyzed_files'] - count)}
    return report


def _uses_shared_structures(file: str) -> bool:
    path = Path(file)
    return _is_python_file(path) or _is_interface_family_file(path)


def _scan_contracts(
    path: Path,
    abstract_only: bool = False,
    show_implementations: bool = True,
) -> Dict[str, Any]:
    """Dispatch to one contract scanner per language present, and merge.

    BACK-780: this used to be a mutually-exclusive if-chain (interface_family
    > ruby > go > rust > cpp > python, python last) that silently dropped
    every non-winning language's contracts in a polyglot repo. Each language
    predicate is now independent, every language actually present gets
    scanned, and results merge into `by_language` when more than one is
    active. Single-language repos (the overwhelming common case) still
    return the exact flat shape (`abcs`/`protocols`/... at the top level)
    unchanged — only the polyglot case gets the new `by_language` shape,
    since that case was never correct before and had no shape to preserve.
    """
    traversal_failures: List[PathFailure] = []
    on_error = partial(_record_traversal_error, traversal_failures)
    active = [name for name, matches in _CONTRACT_LANGUAGES if _has_files(path, matches, on_error=on_error)]

    unsupported_language = detect_non_python_language(path) if not active else ''

    # BACK-518: guard against a few stray supported-language files standing in
    # for a mostly-unsupported tree (see surface.py / assess_language_coverage).
    # BACK-DD-1: reuse surface.py's single source of truth rather than a
    # second hardcoded literal that can silently drift from it.
    coverage_failures: List[PathFailure] = []
    coverage = assess_language_coverage(
        path,
        _supported_coverage_languages(),
        on_error=partial(_record_traversal_error, coverage_failures),
    )
    coverage_dict = coverage.to_scope_dict('contracts')

    if not active:
        return {
            'path': str(path),
            'total_contracts': 0,
            'abcs': [],
            'protocols': [],
            'typeddicts': [],
            'dataclasses': [],
            'basemodels': [],
            'path_heuristic': [],
            'unsupported_language': unsupported_language,
            'coverage': coverage_dict,
            '_traversal_failures': traversal_failures,
            '_coverage_failures': coverage_failures,
        }

    # collect_structures parses every tree-sitter-supported file in `path` in
    # one pass — 'ts' and 'python' both consume it, so compute it once, lazily
    # (skip entirely for repos where neither is active, e.g. pure Go/Rust).
    structures_cache: List[Dict[str, Any]] = []
    analysis_skipped: List[Tuple[str, str]] = []
    recovered_files: List[str] = []
    structures_loaded = False

    def _structures() -> List[Dict[str, Any]]:
        nonlocal structures_loaded
        if not structures_loaded:
            from reveal.adapters.ast.analysis import collect_structures
            collected = collect_structures(str(path))
            structures_loaded = True
            traversal_failures.extend(collected.traversal_failures)
            structures_cache.extend(collected)
            analysis_skipped.extend((file, cause) for file, cause in collected.skipped
                                    if _uses_shared_structures(file))
            recovered_files.extend(item['file'] for item in collected
                                   if item.get('parse_recovered') and _uses_shared_structures(item['file']))
        return structures_cache

    def _run(name: str) -> Dict[str, Any]:
        if name == 'ts':
            return _scan_contracts_ts(path, _structures(), abstract_only, show_implementations)
        if name == 'ruby':
            return _scan_contracts_ruby(path, abstract_only, show_implementations, on_error=on_error)
        if name == 'go':
            return _scan_contracts_go(path, abstract_only, show_implementations, on_error=on_error)
        if name == 'rust':
            return _scan_contracts_rust(path, abstract_only, show_implementations, on_error=on_error)
        if name == 'cpp':
            return _scan_contracts_cpp(path, abstract_only, show_implementations, on_error=on_error)
        return _scan_contracts_python(path, _structures(), abstract_only, show_implementations)

    if len(active) == 1:
        result = _run(active[0])
        result['coverage'] = coverage_dict
        result['_traversal_failures'] = traversal_failures
        result['_coverage_failures'] = coverage_failures
        return _with_analysis_skipped(result, analysis_skipped, recovered=recovered_files)

    by_language = {name: _run(name) for name in active}
    for group in by_language.values():
        analysis_skipped.extend(group.pop('analysis_skipped', []))
        recovered_files.extend(group.get('recovered_files', []))
    report = {
        'path': str(path),
        'total_contracts': sum(g['total_contracts'] for g in by_language.values()),
        'unsupported_language': '',
        'coverage': coverage_dict,
        'by_language': by_language,
        '_traversal_failures': traversal_failures,
        '_coverage_failures': coverage_failures,
    }
    # BACK-1588: only the tree-sitter scanners (Go/Rust/Ruby/C++) have an unparsed
    # channel, so the key is present only when one of them ran.
    if any('unparsed_files' in g for g in by_language.values()):
        report['unparsed_files'] = sorted(f for g in by_language.values() for f in g.get('unparsed_files', []))
    return _with_analysis_skipped(report, analysis_skipped, recovered=recovered_files)


def _scan_contracts_python(
    path: Path,
    structures: List[Dict[str, Any]],
    abstract_only: bool,
    show_implementations: bool,
) -> Dict[str, Any]:
    """Python-specific contract scanner — ABCs, Protocols, TypedDicts, dataclasses, BaseModels.

    `structures` may cover other languages too when scanning a polyglot repo
    (it's shared with `_scan_contracts_ts`) — filtered to `.py` files here so
    a class from another language never gets run through the Python
    classifier (bases/decorators mean different things per language).
    """
    py_structures = [s for s in structures if Path(s.get('file', '')).suffix.lower() == '.py']
    all_classes = _extract_all_classes(py_structures)

    abcs: List[Dict[str, Any]] = []
    protocols: List[Dict[str, Any]] = []
    typeddicts: List[Dict[str, Any]] = []
    dataclasses_: List[Dict[str, Any]] = []
    basemodels: List[Dict[str, Any]] = []
    path_heuristic: List[Dict[str, Any]] = []

    contract_names: Set[str] = set()

    for cls in all_classes:
        bases = cls['bases']
        decorators = cls['decorators']
        file_stem = Path(cls['file']).stem.lower()

        is_abc = _is_abc(bases)
        is_protocol = _is_protocol(bases)
        is_typeddict = _is_typeddict(bases)
        is_dataclass = _is_dataclass(decorators)
        is_basemodel = _is_basemodel(bases)
        is_path_hint = file_stem in _CONTRACT_PATH_HINTS

        if is_abc:
            abcs.append(cls)
            contract_names.add(cls['name'])
        elif is_protocol:
            protocols.append(cls)
            contract_names.add(cls['name'])
        elif is_typeddict and not abstract_only:
            typeddicts.append(cls)
            contract_names.add(cls['name'])
        elif is_dataclass and not abstract_only:
            dataclasses_.append(cls)
            contract_names.add(cls['name'])
        elif is_basemodel and not abstract_only:
            basemodels.append(cls)
            contract_names.add(cls['name'])
        elif is_path_hint and not abstract_only:
            if cls.get('abstract_methods') or _has_pass_only_methods(cls):
                path_heuristic.append(cls)
                contract_names.add(cls['name'])

    if show_implementations:
        # BACK-783: basemodels are inheritance-based contracts like abcs/protocols
        # (a subclass of a pydantic BaseModel is a real implementation edge);
        # typeddicts/dataclasses are structural, not inheritance hierarchies,
        # so they're deliberately excluded here.
        _add_implementations(all_classes, contract_names, abcs + protocols + basemodels + path_heuristic)

    return {
        'path': str(path),
        'total_contracts': len(abcs) + len(protocols) + len(typeddicts) + len(dataclasses_) + len(basemodels) + len(path_heuristic),
        'abcs': abcs,
        'protocols': protocols,
        'typeddicts': typeddicts,
        'dataclasses': dataclasses_,
        'basemodels': basemodels,
        'path_heuristic': path_heuristic,
        'unsupported_language': '',
    }


def _classify_ts(element: Dict[str, Any]) -> str:
    """Classify a TypeScript element into a contract category.

    Returns one of: 'contract', 'abstract_class', 'typed_dict', 'implementation', or ''.
    - 'contract'       → interface declarations (TS's native contract form)
    - 'abstract_class' → abstract class declarations
    - 'typed_dict'     → type alias declarations (object-shape types)
    - 'implementation' → concrete class that extends/implements something
    - ''               → concrete class with no bases (not a contract)
    """
    category = element.get('category', '')
    name = element.get('name', '')
    bases = element.get('bases', [])

    if category == 'interfaces':
        return 'contract'
    if category == 'types':
        return 'typed_dict'
    if category == 'classes':
        # Detect abstract class by checking element name matches abstract_class_declaration
        # The node_type is embedded in the file; we detect via a naming convention or
        # by inspecting the raw source. Instead, we check if the class has an
        # 'abstract' flag set. Since collect_structures doesn't pass node_type through,
        # we detect abstract classes by presence of 'abstract_methods' with no bases
        # OR by checking if the file element has an 'is_abstract' field.
        # The most reliable approach: abstract_class_declaration produces elements
        # that appear in the 'classes' category. We flag them via the element's
        # 'is_abstract' field if present (added below), or fall back to no bases + name.
        if element.get('is_abstract'):
            return 'abstract_class'
        if bases:
            return 'implementation'
    return ''


def _extract_ts_elements(structures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract interface-family contract elements from collect_structures output.

    Collects elements of categories: 'interfaces', 'types', and 'classes', for
    any language in _INTERFACE_FAMILY_EXTENSIONS (TS/TSX, Java, C#). Name kept
    as _ts_elements for now — TS was the first and the classifier/render path
    it built (interfaces→contract, is_abstract→abstract_class) is shared as-is.
    """
    elements = []
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        if Path(file_path).suffix.lower() not in _INTERFACE_FAMILY_EXTENSIONS:
            continue
        for elem in file_struct.get('elements', []):
            cat = elem.get('category', '')
            if cat not in ('interfaces', 'types', 'classes'):
                continue
            elements.append({
                'name': elem['name'],
                'file': file_path,
                'line': elem.get('line', 0),
                'bases': elem.get('bases', []),
                'decorators': elem.get('decorators', []),
                'abstract_methods': [],
                'implementations': [],
                'category': cat,
                'is_abstract': elem.get('is_abstract', False),
            })
    return elements


def _scan_contracts_ts(
    path: Path,
    structures: List[Dict[str, Any]],
    abstract_only: bool,
    show_implementations: bool,
) -> Dict[str, Any]:
    """TypeScript-specific contract scanner."""
    all_elements = _extract_ts_elements(structures)

    # TS contract groups — mapped to the Python group names for render compatibility
    contracts: List[Dict[str, Any]] = []       # interfaces  → shown as "Protocols" slot
    abstract_classes: List[Dict[str, Any]] = [] # abstract class
    typed_dicts: List[Dict[str, Any]] = []      # type alias
    implementations: List[Dict[str, Any]] = []  # concrete class with bases

    contract_names: Set[str] = set()

    for elem in all_elements:
        kind = _classify_ts(elem)
        if kind == 'contract':
            contracts.append(elem)
            contract_names.add(elem['name'])
        elif kind == 'abstract_class':
            abstract_classes.append(elem)
            contract_names.add(elem['name'])
        elif kind == 'typed_dict' and not abstract_only:
            typed_dicts.append(elem)
            contract_names.add(elem['name'])
        elif kind == 'implementation' and not abstract_only:
            implementations.append(elem)

    if show_implementations:
        _add_implementations(all_elements, contract_names, contracts + abstract_classes)

    total = len(contracts) + len(abstract_classes) + len(typed_dicts)

    return {
        'path': str(path),
        'total_contracts': total,
        # Map to the Python group keys contracts.py renders understand
        'abcs': abstract_classes,
        'protocols': contracts,
        'typeddicts': typed_dicts,
        'dataclasses': implementations,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        '_ts_mode': True,
    }


def _scan_contracts_ruby(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
    *, on_error: Optional[Callable[[OSError], None]] = None,
) -> Dict[str, Any]:
    """Ruby-specific contract scanner — the mixin model.

    Ruby has no interface keyword, so it doesn't share `_scan_contracts_ts`'s
    classifier. A `module` is the contract; a class `include`/`extend`-ing it
    (or subclassing it, folded into the same `bases` list) is the
    implementation — see `nav_contracts_ruby.py` for the AST-walk detail.
    """
    from reveal.adapters.ast.nav_contracts_ruby import scan_file_contracts_ruby

    modules: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []
    unparsed: List[str] = []
    recovered: List[str] = []
    skipped: List[Tuple[str, str]] = []
    for file_path in _collect_files(path, _is_ruby_file, on_error=on_error):
        scanned = scan_file_contracts_ruby(str(file_path), on_error=partial(_record_scan_error, skipped))
        modules.extend(scanned['modules'])
        classes.extend(scanned['classes'])
        unparsed.extend(scanned.get(UNPARSED_KEY, []))
        recovered.extend(scanned.get(RECOVERED_KEY, []))

    # A module is a mixin contract when it defines instance methods or something includes
    # or extends it; `module Billing` that only wraps classes and constants is a namespace.
    used = {_base_tail(b) for c in classes for b in c['bases']}
    modules = [m for m in modules if m.pop('defines_methods', True) or m['name'] in used]

    implementations = [] if abstract_only else [c for c in classes if c['bases']]
    contract_names: Set[str] = {m['name'] for m in modules}

    if show_implementations:
        _add_implementations(classes, contract_names, modules)

    return _with_analysis_skipped({
        'path': str(path),
        'total_contracts': len(modules),
        'abcs': [],
        'protocols': modules,
        'typeddicts': [],
        'dataclasses': implementations,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        'unparsed_files': _unparsed_files(unparsed),
        '_ruby_mode': True,
    }, skipped, recovered=recovered)


def _scan_contracts_go(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
    *, on_error: Optional[Callable[[OSError], None]] = None,
) -> Dict[str, Any]:
    """Go-specific contract scanner — interfaces + structural implementers.

    Go's contract is the `interface`; its implementers are not declared
    (no `implements` keyword) but *computed* — a struct implements an interface
    when it has a method of every name+signature the interface declares
    (embedded interfaces resolved transitively). Signature matching is on
    syntactic parameter/return type text (BACK-816) — a struct method with
    the same name but a different return type (the `ObserverVec`/`*Vec`
    shape from `client_golang`) is correctly excluded, not just name-matched.
    Marker/empty interfaces (0 methods, e.g. `interface{}`) are surfaced as
    contracts but excluded from implementer matching, since every type would
    trivially satisfy them. See `nav_contracts_go.py` for the extraction
    detail and its disclosed limitations (aliases, generics, cross-package
    promoted methods).
    """
    from reveal.adapters.ast.nav_contracts_go import scan_file_contracts_go

    interfaces: List[Dict[str, Any]] = []
    structs: List[Dict[str, Any]] = []
    struct_methods: Dict[str, Dict[str, Dict[str, Any]]] = {}
    unparsed: List[str] = []
    recovered: List[str] = []
    skipped: List[Tuple[str, str]] = []
    for file_path in _collect_files(path, _is_go_file, on_error=on_error):
        scanned = scan_file_contracts_go(str(file_path), on_error=partial(_record_scan_error, skipped))
        interfaces.extend(scanned['interfaces'])
        structs.extend(scanned['structs'])
        unparsed.extend(scanned.get(UNPARSED_KEY, []))
        recovered.extend(scanned.get(RECOVERED_KEY, []))
        for m in scanned['methods']:
            struct_methods.setdefault(m['recv'], {})[m['name']] = m

    iface_by_name = {i['name']: i for i in interfaces}

    def _full_methods(iface: Dict[str, Any], seen: Set[str]) -> Dict[str, Dict[str, Any]]:
        """Interface's own methods plus those of every embedded interface,
        resolved transitively (cycle-guarded). A name already set by the
        interface itself (or a closer embed) is not overridden."""
        if iface['name'] in seen:
            return {}
        seen.add(iface['name'])
        methods: Dict[str, Dict[str, Any]] = {m['name']: m for m in iface['methods']}
        for embed in iface['embeds']:
            embedded = iface_by_name.get(embed.split('.')[-1])
            if embedded is not None:
                for name, sig in _full_methods(embedded, seen).items():
                    methods.setdefault(name, sig)
        return methods

    # Normalise each interface into the shared contract shape (bases empty —
    # Go interfaces have no supertype list of the kind other languages carry).
    for iface in interfaces:
        iface['bases'] = []
        iface['implementations'] = []

    struct_implements: Dict[str, List[str]] = {}
    if show_implementations:
        for iface in interfaces:
            required = _full_methods(iface, set())
            if not required:  # marker/empty interface — everything satisfies it
                continue
            for struct in structs:
                have = struct_methods.get(struct['name'], {})
                if all(
                    name in have
                    and have[name]['params'] == sig['params']
                    and have[name]['returns'] == sig['returns']
                    for name, sig in required.items()
                ):
                    iface['implementations'].append({
                        'name': struct['name'], 'file': struct['file'], 'line': struct['line'],
                    })
                    struct_implements.setdefault(struct['name'], []).append(iface['name'])

    # Implementing structs (the "who satisfies a contract" slot). Each carries
    # the interfaces it satisfies as its `bases`, mirroring the other scanners.
    implementers: List[Dict[str, Any]] = []
    if not abstract_only:
        for struct in structs:
            ifaces = struct_implements.get(struct['name'])
            if ifaces:
                implementers.append({**struct, 'bases': sorted(ifaces)})

    return _with_analysis_skipped({
        'path': str(path),
        'total_contracts': len(interfaces),
        'abcs': [],
        'protocols': interfaces,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        'unparsed_files': _unparsed_files(unparsed),
        '_go_mode': True,
    }, skipped, recovered=recovered)


def _scan_contracts_rust(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
    *, on_error: Optional[Callable[[OSError], None]] = None,
) -> Dict[str, Any]:
    """Rust-specific contract scanner — traits + explicit implementors.

    Rust's contract is the `trait`; implementors are *declared* via
    `impl Trait for Type` (no structural inference needed, unlike Go). See
    `nav_contracts_rust.py` for the extraction detail.
    """
    from reveal.adapters.ast.nav_contracts_rust import scan_file_contracts_rust

    traits: List[Dict[str, Any]] = []
    impls: List[Dict[str, Any]] = []
    unparsed: List[str] = []
    recovered: List[str] = []
    skipped: List[Tuple[str, str]] = []
    for file_path in _collect_files(path, _is_rust_file, on_error=on_error):
        scanned = scan_file_contracts_rust(str(file_path), on_error=partial(_record_scan_error, skipped))
        traits.extend(scanned['interfaces'])
        impls.extend(scanned['impls'])
        unparsed.extend(scanned.get(UNPARSED_KEY, []))
        recovered.extend(scanned.get(RECOVERED_KEY, []))

    for tr in traits:
        tr['bases'] = []
        tr['implementations'] = []

    trait_by_name = {t['name']: t for t in traits}
    # A type may implement several traits — collect its trait list for the
    # "implementing types" slot; populate each trait's implementers. Keyed by
    # (type, file), not bare type name: a short/generic name like `Error` or
    # `Result` is commonly reused for unrelated types across files in a large
    # real workspace (BACK-794) — keying by name alone silently conflated
    # every same-named type's trait list into whichever file's impl was
    # processed first.
    type_traits: Dict[tuple, Dict[str, Any]] = {}
    if show_implementations:
        for impl in impls:
            entry = {'name': impl['type'], 'file': impl['file'], 'line': impl['line']}
            tr = trait_by_name.get(impl['trait'])
            if tr is not None:
                tr['implementations'].append(entry)
            key = (impl['type'], impl['file'])
            rec = type_traits.setdefault(key, {'name': impl['type'],
                                               'file': impl['file'],
                                               'line': impl['line'], 'bases': set()})
            rec['bases'].add(impl['trait'])

    implementers: List[Dict[str, Any]] = []
    if not abstract_only:
        for rec in type_traits.values():
            implementers.append({**rec, 'bases': sorted(rec['bases'])})

    return _with_analysis_skipped({
        'path': str(path),
        'total_contracts': len(traits),
        'abcs': [],
        'protocols': traits,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        'unparsed_files': _unparsed_files(unparsed),
        '_rust_mode': True,
    }, skipped, recovered=recovered)


def _scan_contracts_cpp(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
    *, on_error: Optional[Callable[[OSError], None]] = None,
) -> Dict[str, Any]:
    """C++-specific contract scanner — abstract classes + subclasses.

    C++ has no `interface` keyword; the contract is an **abstract class** (a
    `class`/`struct` with ≥1 pure virtual method, `virtual T f() = 0`), and
    implementors are declared explicitly via inheritance. See
    `nav_contracts_cpp.py` for the extraction detail.
    """
    from reveal.adapters.ast.nav_contracts_cpp import scan_file_contracts_cpp

    classes: List[Dict[str, Any]] = []
    unparsed: List[str] = []
    recovered: List[str] = []
    skipped: List[Tuple[str, str]] = []
    for file_path in _collect_files(path, _is_cpp_file, on_error=on_error):
        scanned = scan_file_contracts_cpp(str(file_path), on_error=partial(_record_scan_error, skipped))
        classes.extend(scanned['classes'])
        unparsed.extend(scanned.get(UNPARSED_KEY, []))
        recovered.extend(scanned.get(RECOVERED_KEY, []))

    contracts: List[Dict[str, Any]] = []
    contract_names: Set[str] = set()
    for cls in classes:
        cls['implementations'] = []
        if cls['is_abstract']:
            contracts.append(cls)
            contract_names.add(cls['name'])

    implementers: List[Dict[str, Any]] = []
    if show_implementations:
        contract_map = {c['name']: c for c in contracts}
        for cls in classes:
            impl_of = [b for b in cls['bases'] if b in contract_names and b != cls['name']]
            if impl_of:
                for base in impl_of:
                    contract_map[base]['implementations'].append({
                        'name': cls['name'], 'file': cls['file'], 'line': cls['line'],
                    })
                if not abstract_only:
                    implementers.append({
                        'name': cls['name'], 'file': cls['file'], 'line': cls['line'],
                        'bases': sorted(impl_of),
                    })

    return _with_analysis_skipped({
        'path': str(path),
        'total_contracts': len(contracts),
        'abcs': [],
        'protocols': contracts,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        'unparsed_files': _unparsed_files(unparsed),
        '_cpp_mode': True,
    }, skipped, recovered=recovered)


def _extract_all_classes(structures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract class dicts from collect_structures output.

    Uses the 'bases' field added to class elements by TreeSitterAnalyzer._extract_class_bases.
    Abstract methods are derived by matching function elements with @abstractmethod decorators
    whose line falls within the class's line range.
    """
    classes = []
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        elements = file_struct.get('elements', [])

        # Partition into class elements and function elements for this file
        cls_elems = [e for e in elements if e['category'] == 'classes']
        func_elems = [e for e in elements if e['category'] in ('functions', 'methods')]

        for cls_elem in cls_elems:
            abstract_methods = _find_abstract_methods(cls_elem, func_elems)
            # Normalise decorator strings — strip leading '@'
            raw_decos = cls_elem.get('decorators', [])
            decorators = [d.lstrip('@').split('(')[0] for d in raw_decos]
            classes.append({
                'name': cls_elem['name'],
                'file': file_path,
                'line': cls_elem['line'],
                'bases': cls_elem.get('bases', []),
                'decorators': decorators,
                'abstract_methods': abstract_methods,
                'implementations': [],
            })
    return classes


def _find_abstract_methods(cls_elem: Dict[str, Any], func_elems: List[Dict[str, Any]]) -> List[str]:
    """Find method names with @abstractmethod within the class's line range."""
    cls_start = cls_elem['line']
    cls_end = cls_start + max(cls_elem.get('line_count', 0) - 1, 0)
    abstract = []
    for fn in func_elems:
        fn_line = fn['line']
        if not (cls_start < fn_line <= cls_end):
            continue
        for d in fn.get('decorators', []):
            if 'abstractmethod' in d:
                abstract.append(fn['name'])
                break
    return abstract


def _has_pass_only_methods(cls: Dict[str, Any]) -> bool:
    return bool(cls.get('abstract_methods'))


def _base_tail(base: str) -> str:
    """Strip a dotted path and a generic subscript: 'pkg.Protocol[T]' -> 'Protocol'.

    BACK-781: subscripted generic bases (class Foo(Protocol[T])) tail-matched
    on the literal string 'Protocol[T]', which never equals 'Protocol'.
    """
    return base.split('[', 1)[0].split('.')[-1]


def _is_abc(bases: List[str]) -> bool:
    for b in bases:
        if _base_tail(b) in ('ABC', 'ABCMeta'):
            return True
    return False


def _is_protocol(bases: List[str]) -> bool:
    for b in bases:
        if _base_tail(b) == 'Protocol':
            return True
    return False


def _is_typeddict(bases: List[str]) -> bool:
    for b in bases:
        if _base_tail(b) == 'TypedDict':
            return True
    return False


def _is_dataclass(decorators: List[str]) -> bool:
    for d in decorators:
        tail = d.split('.')[-1]
        if tail == 'dataclass':
            return True
    return False


def _is_basemodel(bases: List[str]) -> bool:
    for b in bases:
        if _base_tail(b) in ('BaseModel', 'BaseSettings'):
            return True
    return False


def _add_implementations(
    all_classes: List[Dict[str, Any]],
    contract_names: Set[str],
    contract_list: List[Dict[str, Any]],
) -> None:
    contract_map = {c['name']: c for c in contract_list}
    for cls in all_classes:
        for base in cls['bases']:
            tail = _base_tail(base)
            if tail in contract_map and cls['name'] != tail:
                contract_map[tail]['implementations'].append({
                    'name': cls['name'],
                    'file': cls['file'],
                    'line': cls['line'],
                })


def _contract_identity_valid(row: Any) -> bool:
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) and bool(row[key].strip()) for key in ('name', 'file'))
            and type(row.get('line')) is int and row['line'] > 0)


def _contract_row_valid(row: Any) -> bool:
    if not _contract_identity_valid(row):
        return False
    for field in ('bases', 'abstract_methods'):
        if field in row and (not isinstance(row[field], list)
                             or any(not isinstance(value, str) for value in row[field])):
            return False
    return ('implementations' not in row or isinstance(row['implementations'], list)
            and all(_contract_identity_valid(item) for item in row['implementations']))


def _contract_observations(report: Dict[str, Any]) -> bool:
    groups = report.get('by_language', {'flat': report})
    if not isinstance(groups, dict) or any(not isinstance(group, dict) for group in groups.values()):
        raise ValueError('Contract groups must be objects')
    observed = False
    for group in groups.values():
        for field in ('abcs', 'protocols', 'typeddicts', 'dataclasses', 'basemodels', 'path_heuristic'):
            rows = group.get(field)
            if not isinstance(rows, list) or any(not _contract_row_valid(row) for row in rows):
                raise ValueError(f'Invalid required contract rows: {field}')
            observed = observed or bool(rows)
    return observed


def _discovery_error(
    report: Dict[str, Any], failures: List[PathFailure], *,
    coverage_only: bool = False,
) -> Optional[str]:
    if not failures:
        return None
    context = 'Required language-coverage census' if coverage_only else 'Required directory discovery'
    try:
        usable = _contract_observations(report)
    except ValueError as exc:
        return f'{context} failed and the contract report is invalid: {exc}'
    if not usable:
        return f'{context} failed and no contract or implementation observations survived'
    return None


# Implementers listed under each contract in the text view; JSON always carries
# them all. 0 lists every one (BACK-1384).
def _contracts_impls(value: Any) -> int:
    if isinstance(value, bool) or (isinstance(value, str) and 'e' in value.lower()):
        raise ValueError('impls requires a non-negative whole number without scientific notation')
    return nonnegative_display_limit(value, 'impls')


_ABSTRACT_ONLY = ParamSpec(
    'abstract_only', 'boolean', 'Show only ABCs and Protocols (skip TypedDicts, dataclasses, path-heuristic)',
    False, boolean_value, ('abstract_only=true',), role='analysis',
    cli=CliBinding(('--abstract-only',), action='store_true'))
_IMPLEMENTATIONS = ParamSpec(
    'implementations', 'boolean', 'Show which classes implement each contract', True,
    boolean_value, ('implementations=false',), role='analysis',
    cli=CliBinding(('--no-implementations',), action='store_false'))
_IMPLS = ParamSpec('impls', 'integer', 'Implementers listed per contract in the text view (0 = all; JSON always has all)',
                   5, _contracts_impls, ('impls=20', 'impls=0'), minimum=0, zero_policy='all',
                   role='presentation', cli=CliBinding(('--impls',), metavar='N'))


@register_adapter('contracts')
@register_renderer(ContractsRenderer)
class ContractsAdapter(ResourceAdapter):
    """Adapter for finding contracts and architectural seams: ABCs, Protocols,
    TypedDicts, dataclasses, BaseModels, and their per-language equivalents."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    RESULT_TYPE = 'contracts'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (_ABSTRACT_ONLY, _IMPLEMENTATIONS, _IMPLS)

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def execution_facts(result):
        """Only the contracts producers identify missing required input evidence."""
        from ..utils.results import AnalysisCompleteness, result_execution_facts
        incomplete = isinstance(result, dict) and bool(
            result.get('recovered_files') or result.get('unparsed_files') or
            any(w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories'
                for w in (result.get('meta') or {}).get('warnings', [])) or
            any(error.get('code') == 'E_CONTRACTS_ANALYSIS'
                for error in (result.get('meta') or {}).get('errors', [])))
        state = AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'contracts',
            'description': 'Find contracts and architectural seams: ABCs, Protocols, TypedDicts, dataclasses, BaseModels.',
            'syntax': 'contracts://<path>[?abstract_only=true&implementations=false]',
            'examples': [
                {'uri': 'contracts://src', 'description': 'All contracts in src/'},
                {'uri': 'contracts://.?abstract_only=true', 'description': 'Only ABCs and Protocols'},
                {'uri': 'contracts://.?implementations=false', 'description': "Skip showing which classes implement each contract"},
            ],
            'features': [
                'Detects ABCs, Protocols, TypedDicts, dataclasses, Pydantic BaseModels (Python)',
                'Detects interfaces, abstract classes, type aliases (TypeScript/JS, Java, C#, PHP, Swift, Kotlin)',
                'Detects mixins (Ruby), interfaces (Go, structural), traits (Rust), abstract classes (C++)',
                'Merges results across languages for polyglot repos',
            ],
            'notes': [
                'Single-language repos return a flat abcs/protocols/... shape; polyglot repos nest under by_language.',
            ],
            'see_also': [
                'reveal contracts <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'contracts',
            'description': 'Contract and architectural-seam scanner (ABCs, Protocols, interfaces, traits, mixins)',
            'uri_syntax': 'contracts://<path>?abstract_only=true&implementations=false',
            'resource': ContractsAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': ContractsAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(ContractsAdapter.FINDINGS_POLICIES)},
            'query_params': param_schema(ContractsAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'contracts',
                    'description': 'Per-language contract groups (ABCs/Protocols/interfaces/traits/mixins) plus implementers',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'total_contracts': {'type': 'integer'},
                            'abcs': {'type': 'array'},
                            'protocols': {'type': 'array'},
                            'unparsed_files': {'type': 'array', 'description': 'Go/Rust/Ruby/C++ files that could not be read or parsed and contribute no entries'},
                            'recovered_files': {'type': 'array', 'description': 'Files with recovered syntax; surviving contracts are retained but may be incomplete'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'contracts://src', 'description': 'All contracts in src/', 'output_type': 'contracts', 'task': 'codebase'},
            ],
            'notes': [
                'Polyglot repos (more than one supported language present) nest results under by_language.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        abstract_only = _ABSTRACT_ONLY.read(self.query_params)
        show_implementations = _IMPLEMENTATIONS.read(self.query_params)

        impls_cap = _IMPLS.read(self.query_params)

        report = _scan_contracts(Path(self.path), abstract_only=abstract_only, show_implementations=show_implementations)
        traversal_failures = report.pop('_traversal_failures', [])
        coverage_failures = report.pop('_coverage_failures', [])
        report['impls_cap'] = impls_cap  # the text view's per-contract cap; the lists themselves are whole

        warnings: List[Any] = []
        traversal_warning = traversal_failed_warning(traversal_failures, Path(self.path))
        if traversal_warning:
            warnings.append(traversal_warning)
        census_warning = traversal_failed_warning(coverage_failures, Path(self.path))
        if census_warning:
            census_warning['message'] = ('Required language-coverage census is incomplete; '
                                         'counts reflect only observed files: ' + census_warning['message'])
            warnings.append(census_warning)
        coverage_warning = report.get('coverage', {}).get('warning', '')
        if coverage_warning:
            warnings.append({'type': 'coverage_gap', 'code': 'W-CONTRACTS-1', 'message': coverage_warning})
        if report.get('unparsed_files'):
            warnings.append({'type': 'unparsed_files', 'code': 'W-CONTRACTS-2', 'message': _unparsed_note(report['unparsed_files'])})
        skipped = report.pop('analysis_skipped', [])
        unparsed = set(report.get('unparsed_files', []))
        failed = analysis_skipped_warning(
            [(file, cause) for file, cause in skipped if file not in unparsed],
            None, "analysis is incomplete; some contracts may be missing from the result")
        if failed:
            warnings.append(failed)
        recovered = report.get('recovered_files', [])
        if recovered:
            warnings.append({'type': 'parse_recovered', 'count': len(recovered), 'files': recovered,
                             'message': f"{len(recovered)} file(s) contain recovered syntax; their contracts may be incomplete: {', '.join(recovered)}"})
        errors: List[ErrorEntry] = [
            {'code': 'E_CONTRACTS_ANALYSIS', 'file': file, 'message': cause}
            for file, cause in skipped]

        discovery_error = _discovery_error(
            report, traversal_failures or coverage_failures,
            coverage_only=not traversal_failures)
        if discovery_error:
            report['error'] = discovery_error
            errors.append({'code': 'E_CONTRACTS_DISCOVERY' if traversal_failures else 'E_CONTRACTS_COVERAGE',
                           'message': discovery_error})

        return ResultBuilder.create(
            result_type=self.RESULT_TYPE,
            source=self.path,
            contract_version=CONTRACT_VERSION,
            parse_mode='ast+tree_sitter',
            confidence=None if traversal_failures or coverage_failures else 0.7,
            warnings=warnings,
            errors=errors,
            data=report,
        )
