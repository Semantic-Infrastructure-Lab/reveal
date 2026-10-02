"""Print a ``--grep`` result and act on its outcome, as the URI router does (BACK-1602).

``grep_handler`` printed its own text and JSON and exited on a bad pattern, so an invalid
pattern under ``--format json`` printed plain text, and a cut could not be disclosed the
shared way. It now returns a result; this emits it: a failed result's error on stderr then
exit 1 (JSON still prints its envelope), a cut list's ``⚠ Truncated`` line after the body.
"""

from argparse import Namespace
from typing import Any, Dict, List, Optional

from ...display.grep import render_grep
from ...grep_handler import grep_directory, grep_file
from .uri import announce_outcome, conclude_outcome


def _emit(result: Dict[str, Any], args: Namespace, label: str) -> None:
    output_format = getattr(args, 'format', 'text')
    outcome = announce_outcome(result, label)
    render_grep(result, output_format)
    conclude_outcome(result, outcome, output_format)


def handle_grep(path: str, pattern: str, args: Namespace) -> None:
    """``reveal FILE --grep PATTERN``."""
    _emit(grep_file(path, pattern, args), args, path)


def handle_grep_directory(path: str, pattern: str, args: Namespace,
                          include_extensions: Optional[List[str]] = None) -> None:
    """``reveal DIR --grep PATTERN [--ext ...]``."""
    _emit(grep_directory(path, pattern, args, include_extensions), args, path)
