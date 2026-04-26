"""reveal contracts — contract and seam inventory for a codebase."""

import argparse
import json
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_CONTRACT_PATH_HINTS: frozenset = frozenset({
    'base', 'schema', 'contract', 'protocol', 'interface',
    'types', 'models', 'dto', 'abstract', 'abc',
})


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

    structures = collect_structures(str(path))
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

    print()
    print(f"Contracts: {path}")
    print("━" * 50)
    print(f"Total contracts found: {total}")
    print()

    if total == 0:
        print("  No contracts or seams found.")
        print("  Try widening the path or checking imports for ABC/Protocol usage.")
        print()
        return

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
