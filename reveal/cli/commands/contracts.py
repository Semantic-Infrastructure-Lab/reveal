"""reveal contracts — contract and seam inventory for a codebase."""

import argparse
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Set

from ...registry import _is_cpp_header_content
from ...utils.path_utils import (
    assess_language_coverage,
    detect_non_python_language,
    is_skippable_dir,
)

_CONTRACT_PATH_HINTS: frozenset = frozenset({
    'base', 'schema', 'contract', 'protocol', 'interface',
    'types', 'models', 'dto', 'abstract', 'abc',
})


_TS_EXTENSIONS: frozenset = frozenset({'.ts', '.tsx'})

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
_INTERFACE_FAMILY_EXTENSIONS: frozenset = frozenset({
    '.ts', '.tsx', '.js', '.jsx', '.java', '.cs', '.php', '.swift', '.kt', '.kts',
})


def _has_python_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix == '.py'
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.py'):
                return True
    return False


def _has_interface_family_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in _INTERFACE_FAMILY_EXTENSIONS
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if Path(fname).suffix.lower() in _INTERFACE_FAMILY_EXTENSIONS:
                return True
    return False


def _has_ruby_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() == '.rb'
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.rb'):
                return True
    return False


def _collect_ruby_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == '.rb' else []
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.rb'):
                files.append(Path(os.path.join(root, fname)))
    return files


def _has_go_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() == '.go'
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.go'):
                return True
    return False


def _collect_go_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == '.go' else []
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.go'):
                files.append(Path(os.path.join(root, fname)))
    return files


def _has_rust_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() == '.rs'
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.rs'):
                return True
    return False


def _collect_rust_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() == '.rs' else []
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.rs'):
                files.append(Path(os.path.join(root, fname)))
    return files


_CPP_EXTENSIONS: frozenset = frozenset({'.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh'})

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


def _has_cpp_files(path: Path) -> bool:
    if path.is_file():
        return _is_cpp_file(path)
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            if _is_cpp_file(Path(os.path.join(root, fname))):
                return True
    return False


def _collect_cpp_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path] if _is_cpp_file(path) else []
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
        for fname in filenames:
            fpath = Path(os.path.join(root, fname))
            if _is_cpp_file(fpath):
                files.append(fpath)
    return files


def create_contracts_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal contracts',
        parents=[_build_global_options_parser()],
        description='Find contracts and architectural seams: ABCs, Protocols, TypedDicts, dataclasses, BaseModels.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal contracts ./src          # All contracts in src/\n"
            "  reveal contracts .              # Entire project\n"
            "  reveal contracts . --format json\n"
            "  reveal contracts . --abstract-only  # Only ABCs and Protocols\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--abstract-only',
        action='store_true',
        help='Show only ABCs and Protocols (skip TypedDicts, dataclasses, path-heuristic)'
    )
    parser.add_argument(
        '--no-implementations',
        action='store_true',
        help='Skip showing which classes implement each contract'
    )
    return parser


def run_contracts(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    abstract_only = getattr(args, 'abstract_only', False)
    show_implementations = not getattr(args, 'no_implementations', False)

    report = _scan_contracts(path, abstract_only=abstract_only, show_implementations=show_implementations)

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report)


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
    is_interface_family = _has_interface_family_files(path)
    is_ruby = _has_ruby_files(path)
    is_go = _has_go_files(path)
    is_rust = _has_rust_files(path)
    is_cpp = _has_cpp_files(path)
    has_python = _has_python_files(path)

    active: List[str] = []
    if is_interface_family:
        active.append('ts')
    if is_ruby:
        active.append('ruby')
    if is_go:
        active.append('go')
    if is_rust:
        active.append('rust')
    if is_cpp:
        active.append('cpp')
    if has_python:
        active.append('python')

    unsupported_language = detect_non_python_language(path) if not active else ''

    # BACK-518: guard against a few stray supported-language files standing in
    # for a mostly-unsupported tree (see surface.py / assess_language_coverage).
    coverage = assess_language_coverage(
        path,
        {'python', 'typescript', 'tsx', 'javascript', 'java', 'csharp', 'php', 'swift', 'kotlin', 'ruby', 'go', 'rust', 'cpp'},
    )
    coverage_dict = {
        'total_code_files': coverage.total_code_files,
        'analyzed_files': coverage.analyzed_files,
        'dominant_language': coverage.dominant_language,
        'dominant_count': coverage.dominant_count,
        'dominant_supported': coverage.dominant_supported,
        'warning': coverage.warning_line('contracts'),
    }

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
        }

    # collect_structures parses every tree-sitter-supported file in `path` in
    # one pass — 'ts' and 'python' both consume it, so compute it once, lazily
    # (skip entirely for repos where neither is active, e.g. pure Go/Rust).
    structures_cache: List[Dict[str, Any]] = []

    def _structures() -> List[Dict[str, Any]]:
        if not structures_cache:
            from reveal.adapters.ast.analysis import collect_structures
            structures_cache.extend(collect_structures(str(path)))
        return structures_cache

    def _run(name: str) -> Dict[str, Any]:
        if name == 'ts':
            return _scan_contracts_ts(path, _structures(), abstract_only, show_implementations)
        if name == 'ruby':
            return _scan_contracts_ruby(path, abstract_only, show_implementations)
        if name == 'go':
            return _scan_contracts_go(path, abstract_only, show_implementations)
        if name == 'rust':
            return _scan_contracts_rust(path, abstract_only, show_implementations)
        if name == 'cpp':
            return _scan_contracts_cpp(path, abstract_only, show_implementations)
        return _scan_contracts_python(path, _structures(), abstract_only, show_implementations)

    if len(active) == 1:
        result = _run(active[0])
        result['coverage'] = coverage_dict
        return result

    by_language = {name: _run(name) for name in active}
    return {
        'path': str(path),
        'total_contracts': sum(g['total_contracts'] for g in by_language.values()),
        'unsupported_language': '',
        'coverage': coverage_dict,
        'by_language': by_language,
    }


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
        _add_implementations(all_classes, contract_names, abcs + protocols + path_heuristic)

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
    for file_path in _collect_ruby_files(path):
        scanned = scan_file_contracts_ruby(str(file_path))
        modules.extend(scanned['modules'])
        classes.extend(scanned['classes'])

    implementations = [] if abstract_only else [c for c in classes if c['bases']]
    contract_names: Set[str] = {m['name'] for m in modules}

    if show_implementations:
        _add_implementations(classes, contract_names, modules)

    return {
        'path': str(path),
        'total_contracts': len(modules),
        'abcs': [],
        'protocols': modules,
        'typeddicts': [],
        'dataclasses': implementations,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        '_ruby_mode': True,
    }


def _scan_contracts_go(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
) -> Dict[str, Any]:
    """Go-specific contract scanner — interfaces + structural implementers.

    Go's contract is the `interface`; its implementers are not declared
    (no `implements` keyword) but *computed* — a struct implements an interface
    when its method-name set is a superset of the interface's (embedded
    interfaces resolved transitively). Marker/empty interfaces (0 methods, e.g.
    `interface{}`) are surfaced as contracts but excluded from implementer
    matching, since every type would trivially satisfy them. See
    `nav_contracts_go.py` for the extraction detail.
    """
    from reveal.adapters.ast.nav_contracts_go import scan_file_contracts_go

    interfaces: List[Dict[str, Any]] = []
    structs: List[Dict[str, Any]] = []
    struct_methods: Dict[str, Set[str]] = {}
    for file_path in _collect_go_files(path):
        scanned = scan_file_contracts_go(str(file_path))
        interfaces.extend(scanned['interfaces'])
        structs.extend(scanned['structs'])
        for m in scanned['methods']:
            struct_methods.setdefault(m['recv'], set()).add(m['name'])

    iface_by_name = {i['name']: i for i in interfaces}

    def _full_methods(iface: Dict[str, Any], seen: Set[str]) -> Set[str]:
        """Interface's own methods plus those of every embedded interface,
        resolved transitively (cycle-guarded)."""
        if iface['name'] in seen:
            return set()
        seen.add(iface['name'])
        methods: Set[str] = set(iface['methods'])
        for embed in iface['embeds']:
            embedded = iface_by_name.get(embed.split('.')[-1])
            if embedded is not None:
                methods |= _full_methods(embedded, seen)
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
                have = struct_methods.get(struct['name'], set())
                if required <= have:
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

    return {
        'path': str(path),
        'total_contracts': len(interfaces),
        'abcs': [],
        'protocols': interfaces,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        '_go_mode': True,
    }


def _scan_contracts_rust(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
) -> Dict[str, Any]:
    """Rust-specific contract scanner — traits + explicit implementors.

    Rust's contract is the `trait`; implementors are *declared* via
    `impl Trait for Type` (no structural inference needed, unlike Go). See
    `nav_contracts_rust.py` for the extraction detail.
    """
    from reveal.adapters.ast.nav_contracts_rust import scan_file_contracts_rust

    traits: List[Dict[str, Any]] = []
    impls: List[Dict[str, Any]] = []
    for file_path in _collect_rust_files(path):
        scanned = scan_file_contracts_rust(str(file_path))
        traits.extend(scanned['interfaces'])
        impls.extend(scanned['impls'])

    for tr in traits:
        tr['bases'] = []
        tr['implementations'] = []

    trait_by_name = {t['name']: t for t in traits}
    # A type may implement several traits — collect its trait list for the
    # "implementing types" slot; populate each trait's implementers.
    type_traits: Dict[str, Dict[str, Any]] = {}
    if show_implementations:
        for impl in impls:
            entry = {'name': impl['type'], 'file': impl['file'], 'line': impl['line']}
            tr = trait_by_name.get(impl['trait'])
            if tr is not None:
                tr['implementations'].append(entry)
            rec = type_traits.setdefault(impl['type'], {'name': impl['type'],
                                                        'file': impl['file'],
                                                        'line': impl['line'], 'bases': set()})
            rec['bases'].add(impl['trait'])

    implementers: List[Dict[str, Any]] = []
    if not abstract_only:
        for rec in type_traits.values():
            implementers.append({**rec, 'bases': sorted(rec['bases'])})

    return {
        'path': str(path),
        'total_contracts': len(traits),
        'abcs': [],
        'protocols': traits,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        '_rust_mode': True,
    }


def _scan_contracts_cpp(
    path: Path,
    abstract_only: bool,
    show_implementations: bool,
) -> Dict[str, Any]:
    """C++-specific contract scanner — abstract classes + subclasses.

    C++ has no `interface` keyword; the contract is an **abstract class** (a
    `class`/`struct` with ≥1 pure virtual method, `virtual T f() = 0`), and
    implementors are declared explicitly via inheritance. See
    `nav_contracts_cpp.py` for the extraction detail.
    """
    from reveal.adapters.ast.nav_contracts_cpp import scan_file_contracts_cpp

    classes: List[Dict[str, Any]] = []
    for file_path in _collect_cpp_files(path):
        scanned = scan_file_contracts_cpp(str(file_path))
        classes.extend(scanned['classes'])

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

    return {
        'path': str(path),
        'total_contracts': len(contracts),
        'abcs': [],
        'protocols': contracts,
        'typeddicts': [],
        'dataclasses': implementers,
        'basemodels': [],
        'path_heuristic': [],
        'unsupported_language': '',
        '_cpp_mode': True,
    }


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


def _is_abc(bases: List[str]) -> bool:
    for b in bases:
        tail = b.split('.')[-1]
        if tail in ('ABC', 'ABCMeta'):
            return True
    return False


def _is_protocol(bases: List[str]) -> bool:
    for b in bases:
        tail = b.split('.')[-1]
        if tail == 'Protocol':
            return True
    return False


def _is_typeddict(bases: List[str]) -> bool:
    for b in bases:
        tail = b.split('.')[-1]
        if tail == 'TypedDict':
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
        tail = b.split('.')[-1]
        if tail in ('BaseModel', 'BaseSettings'):
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
            tail = base.split('.')[-1]
            if tail in contract_map and cls['name'] != tail:
                contract_map[tail]['implementations'].append({
                    'name': cls['name'],
                    'file': cls['file'],
                    'line': cls['line'],
                })


_LANGUAGE_LABELS: Dict[str, str] = {
    'python': 'Python',
    'ts': 'TypeScript / Java / C# / PHP / Swift / Kotlin / JS',
    'ruby': 'Ruby',
    'go': 'Go',
    'rust': 'Rust',
    'cpp': 'C++',
}

# Fixed render order for the polyglot (`by_language`) case — arbitrary but stable.
_LANGUAGE_RENDER_ORDER: List[str] = ['python', 'ts', 'ruby', 'go', 'rust', 'cpp']


def _render_contract_groups(mode: str, report: Dict[str, Any]) -> None:
    """Render one language's contract groups under its own labels/groupings."""
    if mode == 'ts':
        _render_group("Abstract Classes", report['abcs'], show_methods=False, show_impls=True)
        _render_group("Interfaces", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Type Aliases", report['typeddicts'], show_methods=False, show_impls=False)
        _render_group("Implementing Classes", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'ruby':
        _render_group("Mixins (Modules)", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Including Classes", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'go':
        _render_group("Interfaces", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Implementing Types (structural)", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'rust':
        _render_group("Traits", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Implementing Types", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'cpp':
        _render_group("Abstract Classes (interfaces)", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Subclasses", report['dataclasses'], show_methods=False, show_impls=False)
    else:
        _render_group("Abstract Base Classes", report['abcs'], show_methods=True, show_impls=True)
        _render_group("Protocols", report['protocols'], show_methods=True, show_impls=True)
        _render_group("TypedDicts", report['typeddicts'], show_methods=False, show_impls=False)
        _render_group("Dataclasses", report['dataclasses'], show_methods=False, show_impls=False)
        _render_group("Pydantic BaseModels", report['basemodels'], show_methods=False, show_impls=False)
        _render_group("Path-heuristic bases", report['path_heuristic'], show_methods=True, show_impls=True)


def _no_contracts_hint(mode: str) -> str:
    if mode == 'ts':
        return "  Try widening the path or checking for interface/abstract class usage."
    if mode == 'ruby':
        return "  Try widening the path or checking for module/include/extend (mixin) usage."
    if mode == 'go':
        return "  Try widening the path or checking for interface type declarations."
    if mode == 'rust':
        return "  Try widening the path or checking for trait / impl-for declarations."
    if mode == 'cpp':
        return "  Try widening the path or checking for abstract classes (pure virtual methods)."
    return "  Try widening the path or checking imports for ABC/Protocol usage."


def _render_report(report: Dict[str, Any]) -> None:
    path = report['path']
    total = report['total_contracts']

    print()
    print(f"Contracts: {path}")
    print("━" * 50)
    # BACK-518: warn when reveal only understood a minority of the tree — the
    # results (total>0) are a supported-language subset, or the emptiness
    # (total==0) is a false-clean on a mostly-unsupported repo (e.g. 15 stray
    # .py files in a Lua tree yielding "no contracts"), not a real verdict. The
    # coverage warning supersedes the legacy detect_non_python_language decline.
    warning = report.get('coverage', {}).get('warning', '')
    if warning:
        print(warning)
        print()
    print(f"Total contracts found: {total}")
    print()

    by_language = report.get('by_language')
    if by_language is not None:
        # BACK-780: more than one language present — render each language's
        # section under its own labels rather than picking one winner.
        if total == 0:
            if not warning:
                print("  No contracts or seams found.")
                print()
            return
        for name in _LANGUAGE_RENDER_ORDER:
            group = by_language.get(name)
            if group is None:
                continue
            print(f"── {_LANGUAGE_LABELS[name]} ──")
            print()
            _render_contract_groups(name, group)
        return

    ts_mode = report.get('_ts_mode', False)
    ruby_mode = report.get('_ruby_mode', False)
    go_mode = report.get('_go_mode', False)
    rust_mode = report.get('_rust_mode', False)
    cpp_mode = report.get('_cpp_mode', False)
    mode = ('ts' if ts_mode else 'ruby' if ruby_mode else 'go' if go_mode
            else 'rust' if rust_mode else 'cpp' if cpp_mode else 'python')

    if total == 0:
        if not warning:
            lang = report.get('unsupported_language', '')
            if lang:
                print(f"  reveal contracts currently supports Python, TypeScript, JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, and C++.")
                print(f"  No supported files found — detected {lang}.")
            else:
                print("  No contracts or seams found.")
                print(_no_contracts_hint(mode))
            print()
        return

    _render_contract_groups(mode, report)


def _render_group(
    label: str,
    entries: List[Dict[str, Any]],
    show_methods: bool,
    show_impls: bool,
) -> None:
    if not entries:
        return
    print(f"{label} ({len(entries)}):")
    for cls in entries:
        name = cls['name']
        file_path = cls['file']
        line = cls['line']
        bases = cls.get('bases', [])
        bases_str = f"({', '.join(bases)})" if bases else ''
        print(f"  {name}  {bases_str}  {file_path}:{line}")
        if show_methods and cls.get('abstract_methods'):
            methods = ', '.join(cls['abstract_methods'])
            print(f"    → abstract: {methods}")
        if show_impls and cls.get('implementations'):
            impls = cls['implementations']
            impl_strs = [f"{i['name']} ({i['file']}:{i['line']})" for i in impls[:5]]
            print(f"    ← implements: {', '.join(impl_strs)}")
            if len(impls) > 5:
                print(f"    ← … and {len(impls) - 5} more")
    print()
