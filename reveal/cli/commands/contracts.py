"""reveal contracts — contract and seam inventory for a codebase."""

import argparse
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Set

from ...defaults import SKIP_DIRECTORIES
from ...utils.path_utils import assess_language_coverage, detect_non_python_language

_SKIP_DIRS: frozenset = SKIP_DIRECTORIES

_CONTRACT_PATH_HINTS: frozenset = frozenset({
    'base', 'schema', 'contract', 'protocol', 'interface',
    'types', 'models', 'dto', 'abstract', 'abc',
})


_TS_EXTENSIONS: frozenset = frozenset({'.ts', '.tsx'})

# BACK-403 pt 2: languages whose grammar has a distinct interface/abstract-class
# shape close enough to TS's ('interfaces'/'types'/'classes' categories, an
# is_abstract flag on classes) that they share _scan_contracts_ts's classifier
# rather than needing their own. Java/C# added — each analyzer
# (analyzers/java.py, analyzers/csharp.py) now emits the same shape TS does.
_INTERFACE_FAMILY_EXTENSIONS: frozenset = frozenset({'.ts', '.tsx', '.java', '.cs'})


def _has_python_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix == '.py'
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.py'):
                return True
    return False


def _has_interface_family_files(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in _INTERFACE_FAMILY_EXTENSIONS
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            if Path(fname).suffix.lower() in _INTERFACE_FAMILY_EXTENSIONS:
                return True
    return False


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
    from reveal.adapters.ast.analysis import collect_structures

    unsupported_language = ''
    is_interface_family = _has_interface_family_files(path)

    if not _has_python_files(path) and not is_interface_family:
        unsupported_language = detect_non_python_language(path)

    # BACK-518: guard against a few stray supported-language files standing in
    # for a mostly-unsupported tree (see surface.py / assess_language_coverage).
    coverage = assess_language_coverage(path, {'python', 'typescript', 'tsx', 'java', 'csharp'})
    coverage_dict = {
        'total_code_files': coverage.total_code_files,
        'analyzed_files': coverage.analyzed_files,
        'dominant_language': coverage.dominant_language,
        'dominant_count': coverage.dominant_count,
        'dominant_supported': coverage.dominant_supported,
        'warning': coverage.warning_line('contracts'),
    }

    structures = collect_structures(str(path))

    if is_interface_family:
        result = _scan_contracts_ts(path, structures, abstract_only, show_implementations)
        result['coverage'] = coverage_dict
        return result

    all_classes = _extract_all_classes(structures)

    # Classify contracts
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
        'unsupported_language': unsupported_language,
        'coverage': coverage_dict,
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


def _render_report(report: Dict[str, Any]) -> None:
    path = report['path']
    total = report['total_contracts']
    ts_mode = report.get('_ts_mode', False)

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

    if total == 0:
        if not warning:
            lang = report.get('unsupported_language', '')
            if lang:
                print(f"  reveal contracts currently supports Python, TypeScript, Java, and C#.")
                print(f"  No supported files found — detected {lang}.")
            else:
                print("  No contracts or seams found.")
                if ts_mode:
                    print("  Try widening the path or checking for interface/abstract class usage.")
                else:
                    print("  Try widening the path or checking imports for ABC/Protocol usage.")
            print()
        return

    if ts_mode:
        _render_group("Abstract Classes", report['abcs'], show_methods=False, show_impls=True)
        _render_group("Interfaces", report['protocols'], show_methods=False, show_impls=True)
        _render_group("Type Aliases", report['typeddicts'], show_methods=False, show_impls=False)
        _render_group("Implementing Classes", report['dataclasses'], show_methods=False, show_impls=False)
    else:
        _render_group("Abstract Base Classes", report['abcs'], show_methods=True, show_impls=True)
        _render_group("Protocols", report['protocols'], show_methods=True, show_impls=True)
        _render_group("TypedDicts", report['typeddicts'], show_methods=False, show_impls=False)
        _render_group("Dataclasses", report['dataclasses'], show_methods=False, show_impls=False)
        _render_group("Pydantic BaseModels", report['basemodels'], show_methods=False, show_impls=False)
        _render_group("Path-heuristic bases", report['path_heuristic'], show_methods=True, show_impls=True)


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
