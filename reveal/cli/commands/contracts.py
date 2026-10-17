"""reveal contracts — contract and seam inventory for a codebase.

Thin argparse shim over the contracts:// adapter (BACK-905); scan/render
logic lives in reveal/adapters/contracts.py and text rendering in
reveal/rendering/adapters/contracts.py.
"""

import argparse
from argparse import Namespace

from reveal.adapters.contracts import (  # noqa: F401 - re-exported for back-compat
    ContractsAdapter,
    ContractsRenderer,
    _CONTRACT_PATH_HINTS,
    _CPP_EXTENSIONS,
    _INTERFACE_FAMILY_EXTENSIONS,
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
    _scan_contracts,
    _scan_contracts_cpp,
    _scan_contracts_go,
    _scan_contracts_python,
    _scan_contracts_ruby,
    _scan_contracts_rust,
    _scan_contracts_ts,
)


def create_contracts_parser() -> argparse.ArgumentParser:
    """Compatibility import; the adapter declaration owns the parser."""
    from ..routing.declared import create_declared_parser
    return create_declared_parser('contracts')


def run_contracts(args: Namespace) -> None:
    """Compatibility import; both spellings use the declared runner."""
    from ..routing.declared import run_declared_command
    run_declared_command('contracts', args)
