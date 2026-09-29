"""reveal contracts — contract and seam inventory for a codebase.

Thin argparse shim over the contracts:// adapter (BACK-905); scan/render
logic lives in reveal/adapters/contracts.py. Internal names are re-exported
here for backward compatibility with existing callers/tests.
"""

import argparse
import sys
from argparse import Namespace
from functools import partial
from pathlib import Path

from reveal.adapters.contracts import (  # noqa: F401 - re-exported for back-compat
    ContractsAdapter,
    ContractsRenderer,
    _CONTRACT_PATH_HINTS,
    _CPP_EXTENSIONS,
    _INTERFACE_FAMILY_EXTENSIONS,
    _LANGUAGE_LABELS,
    _LANGUAGE_RENDER_ORDER,
    _add_implementations,
    _base_tail,
    _classify_ts,
    _extract_all_classes,
    _extract_ts_elements,
    _find_abstract_methods,
    _has_pass_only_methods,
    _is_abc,
    _is_basemodel,
    _is_cpp_file,
    _is_dataclass,
    _is_protocol,
    _is_typeddict,
    _no_contracts_hint,
    _render_contract_groups,
    _render_group,
    _render_report,
    _scan_contracts,
    _scan_contracts_cpp,
    _scan_contracts_go,
    _scan_contracts_python,
    _scan_contracts_ruby,
    _scan_contracts_rust,
    _scan_contracts_ts,
)
from ..global_flags import add_exclude_argument, add_gitignore_arguments
from ..routing.subcommand import emit_subcommand_result


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
    add_exclude_argument(parser)
    add_gitignore_arguments(parser)
    return parser


def run_contracts(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    abstract_only = getattr(args, 'abstract_only', False)
    show_implementations = not getattr(args, 'no_implementations', False)

    query = f'abstract_only={"true" if abstract_only else "false"}&implementations={"true" if show_implementations else "false"}'
    result = ContractsAdapter(str(path), query).get_structure()
    emit_subcommand_result(result, args, name='contracts', source=path, render=partial(
        ContractsRenderer.render_structure, format=args.format))
