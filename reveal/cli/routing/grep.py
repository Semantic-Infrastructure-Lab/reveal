"""Print a ``--grep`` result and act on its outcome, as the URI router does (BACK-1602).

``grep_handler`` printed its own text and JSON and exited on a bad pattern, so an invalid
pattern under ``--format json`` printed plain text, and a cut could not be disclosed the
shared way. It now returns a result; this emits it: a failed result's error on stderr then
exit 1 (JSON still prints its envelope), a cut list's ``⚠ Truncated`` line after the body,
and exit 3 for a search that could not read every file it had to: a directory (D6,
BACK-2520) or the one file asked for (BACK-2527).
"""

import sys
from argparse import Namespace
from typing import Any, Dict, List, Optional

from ...display.formatting import print_result_control_notes
from ...display.grep import render_grep
from ...grep_handler import grep_directory, grep_execution_facts, grep_file
from ...utils.results import execution_exit_code
from .uri import announce_outcome, conclude_outcome


def _emit(result: Dict[str, Any], args: Namespace, label: str) -> None:
    output_format = getattr(args, 'format', 'text')
    outcome = announce_outcome(result, label)
    render_grep(result, output_format)
    code = execution_exit_code(grep_execution_facts(result))
    if code:  # a lost source outranks a failed result's legacy exit 1 (BACK-2527)
        print_result_control_notes(result, output_format)
        sys.exit(code)
    conclude_outcome(result, outcome, output_format)


def handle_grep(path: str, pattern: str, args: Namespace) -> None:
    """``reveal FILE --grep PATTERN``."""
    _emit(grep_file(path, pattern, args), args, path)


def handle_grep_directory(path: str, pattern: str, args: Namespace,
                          include_extensions: Optional[List[str]] = None) -> None:
    """``reveal DIR --grep PATTERN [--ext ...]``."""
    _emit(grep_directory(path, pattern, args, include_extensions), args, path)
