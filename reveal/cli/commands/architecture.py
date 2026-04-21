"""reveal architecture — targeted architectural brief for a directory.

Answers: "What do I need to know before editing this code?"
Composes imports graph, complexity data, and cycle analysis into facts + risks + next commands.
"""
import argparse
import json
import logging
import sys
from argparse import Namespace
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_COMPLEXITY_ENTRY_THRESHOLD = 20  # entry point complexity that warrants a warning
_FAN_IN_RISK_THRESHOLD = 8        # fan-in count that makes a file load-bearing


def create_architecture_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal architecture',
        parents=[_build_global_options_parser()],
        description=(
            'Architectural brief for a directory: entry points, core abstractions, '
            'risks, and suggested next commands.'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal architecture src/              # Brief for a subdirectory\n"
            "  reveal architecture .                 # Whole project\n"
            "  reveal architecture src/ --format json  # Machine-readable output\n"
            "  reveal architecture src/ --no-imports   # Skip import graph analysis\n"
        ),
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to analyze (default: current directory)',
    )
    parser.add_argument(
        '--no-imports',
        action='store_true',
        help='Skip import graph analysis',
    )
    parser.add_argument(
        '--top',
        metavar='N',
        type=int,
        default=5,
        help='Number of items to show per section (default: 5)',
    )
    return parser


def run_architecture(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    top = args.top
    no_imports = getattr(args, 'no_imports', False)

    complex_fns = _run_complex_functions(path, top * 4)
    imports_data = {} if no_imports else _run_imports_analysis(path)

    risks = _compute_risks(imports_data, complex_fns, path)
    next_commands = _build_next_commands(path, risks, imports_data)

    report = {
        'path': str(path),
        'facts': {
            'entry_points': imports_data.get('entry_points', []),
            'core_abstractions': imports_data.get('core_abstractions', []),
            'components': imports_data.get('components', []),
            'circular_groups': imports_data.get('circular_groups', []),
        },
        'risks': risks,
        'next_commands': next_commands,
    }

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_brief(report, top, path)


def _run_complex_functions(path: Path, limit: int) -> List[Dict[str, Any]]:
    try:
        from reveal.adapters.ast import AstAdapter
        data = AstAdapter(str(path), f'complexity>9&sort=-complexity&limit={limit}').get_structure()
        return data.get('results', data.get('elements', []))
    except Exception as exc:
        logger.warning("AST analysis failed for %s: %s", path, exc)
        return []


def _run_imports_analysis(path: Path) -> Dict[str, Any]:
    try:
        from reveal.adapters.imports import ImportsAdapter
        adapter = ImportsAdapter(str(path))
        adapter._build_graph(path)

        fan_in_data = adapter._format_fan_in()
        entrypoints_data = adapter._format_entrypoints()
        components_data = adapter._format_components()
        circular_data = adapter._format_circular()

        all_entries = fan_in_data.get('entries', [])
        raw_eps = entrypoints_data.get('entries', [])
        components = components_data.get('components', [])
        cycle_groups = circular_data.get('cycles', [])

        live_eps = [
            e for e in raw_eps
            if e.get('fan_out', 0) > 0
            and not _is_test_file(e['file'])
            and Path(e['file']).name != '__init__.py'
        ]
        core_abstractions = [e for e in all_entries if e.get('fan_in', 0) > 0]

        return {
            'entry_points': live_eps,
            'core_abstractions': core_abstractions,
            'components': components,
            'circular_groups': cycle_groups,
        }
    except Exception as exc:
        logger.warning("imports analysis failed for %s: %s", path, exc)
        return {}


def _compute_risks(
    imports_data: Dict[str, Any],
    complex_fns: List[Dict[str, Any]],
    base_path: Path,
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []

    file_max_cx: Dict[str, int] = {}
    for fn in complex_fns:
        f = fn.get('file', '')
        cx = fn.get('complexity', 0)
        if f:
            file_max_cx[f] = max(file_max_cx.get(f, 0), cx)

    for group in imports_data.get('circular_groups', []):
        count = len(group)
        rep = _relpath(group[0], base_path) if group else ''
        risks.append({
            'type': 'circular',
            'severity': 'high' if count > 10 else 'medium',
            'description': f"{count}-file circular group",
            'detail': f"{rep} + {count - 1} more" if count > 1 else rep,
            'file_count': count,
            'representative': group[0] if group else '',
        })

    for ep in imports_data.get('entry_points', []):
        cx = file_max_cx.get(ep['file'], 0)
        if cx >= _COMPLEXITY_ENTRY_THRESHOLD:
            risks.append({
                'type': 'high_complexity_entry',
                'severity': 'medium',
                'description': f"{_relpath(ep['file'], base_path)} — high-complexity entry point",
                'detail': f"fan-out {ep['fan_out']}, cx {cx}",
                'file': ep['file'],
                'complexity': cx,
                'fan_out': ep['fan_out'],
            })

    for abstraction in imports_data.get('core_abstractions', [])[:5]:
        fan_in = abstraction.get('fan_in', 0)
        if fan_in >= _FAN_IN_RISK_THRESHOLD:
            risks.append({
                'type': 'load_bearing',
                'severity': 'low',
                'description': f"{_relpath(abstraction['file'], base_path)} — load-bearing file",
                'detail': f"fan-in {fan_in}",
                'file': abstraction['file'],
                'fan_in': fan_in,
            })

    return risks


def _build_next_commands(
    path: Path,
    risks: List[Dict[str, Any]],
    imports_data: Dict[str, Any],
) -> List[str]:
    cmds: List[str] = []
    path_str = str(path)

    if any(r['type'] == 'circular' for r in risks):
        cmds.append(f"reveal 'imports://{path_str}?circular'")

    cx_entries = [r for r in risks if r['type'] == 'high_complexity_entry']
    if cx_entries:
        worst = max(cx_entries, key=lambda r: r.get('complexity', 0))
        cmds.append(f"reveal {worst['file']} --boundary")

    if imports_data.get('core_abstractions'):
        cmds.append(f"reveal 'ast://{path_str}?complexity>20'")

    lb = [r for r in risks if r['type'] == 'load_bearing']
    if lb:
        top_lb = max(lb, key=lambda r: r.get('fan_in', 0))
        cmds.append(f"reveal {top_lb['file']}")

    if not cmds:
        cmds.append(f"reveal overview {path_str}")
        cmds.append(f"reveal {path_str}")

    return cmds


def _render_brief(report: Dict[str, Any], top: int, base_path: Path) -> None:
    path = report['path']
    facts = report['facts']

    print(f"Architecture Brief: {path}\n")

    _render_entry_points(facts.get('entry_points', []), top, base_path)
    _render_core_abstractions(facts.get('core_abstractions', []), top, base_path)
    _render_components(facts.get('components', []), top, base_path)
    _render_risks(report.get('risks', []))
    _render_next_commands(report.get('next_commands', []))


def _render_entry_points(entry_points: List[Dict], top: int, base_path: Path) -> None:
    if not entry_points:
        return
    print(f"Entry Points  ({len(entry_points)} active)")
    for ep in entry_points[:top]:
        rel = _relpath(ep['file'], base_path)
        print(f"  {rel:<54}  fan-out {ep['fan_out']}")
    print()


def _render_core_abstractions(core: List[Dict], top: int, base_path: Path) -> None:
    ranked = [e for e in core if e.get('fan_in', 0) > 0 and Path(e['file']).name != '__init__.py'][:top]
    if not ranked:
        return
    print("Core Abstractions  (most imported)")
    for e in ranked:
        rel = _relpath(e['file'], base_path)
        print(f"  {rel:<54}  fan-in {e['fan_in']}")
    print()


def _render_components(components: List[Dict], top: int, base_path: Path) -> None:
    if not components:
        return
    print(f"Components  ({len(components)} directories)")
    for c in components[:top]:
        rel = _relpath(c['component'], base_path)
        cohesion = c['cohesion']
        bar = '█' * int(cohesion * 10) + '░' * (10 - int(cohesion * 10))
        print(f"  {rel:<44}  {cohesion:.2f}  {bar}  {c['files']} files")
    print()


def _render_risks(risks: List[Dict]) -> None:
    if not risks:
        return
    print(f"Risks  ({len(risks)} found)")
    for r in risks:
        detail = r.get('detail', '')
        suffix = f"  ({detail})" if detail else ''
        print(f"  ⚠ {r['description']}{suffix}")
    print()


def _render_next_commands(commands: List[str]) -> None:
    if not commands:
        return
    print("Next Commands")
    for cmd in commands:
        print(f"  {cmd}")


def _is_test_file(file_str: str) -> bool:
    p = Path(file_str)
    return p.name.startswith('test_') or '/test/' in file_str or '/tests/' in file_str


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    if not base_path:
        return file_str
    try:
        return str(Path(file_str).relative_to(base_path))
    except ValueError:
        return file_str
