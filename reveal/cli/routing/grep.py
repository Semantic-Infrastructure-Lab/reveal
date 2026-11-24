"""Print a ``--grep`` result and act on its outcome, as the URI router does (BACK-1602).

``grep_handler`` printed its own text and JSON and exited on a bad pattern, so an invalid
pattern under ``--format json`` printed plain text, and a cut could not be disclosed the
shared way. It now returns a result; this emits it: a failed result's error on stderr (JSON
still prints its envelope), a cut list's ``⚠ Truncated`` line after the body, exit 2 for an
invalid pattern (BACK-2765; its JSON is the path read's invalid-request document, ruling S4), and
exit 3 for a search that could not read every file it had to: a directory (D6, BACK-2520) or the
one file asked for (BACK-2527).
"""

import sys
from argparse import Namespace
from typing import Any, Dict, List, Optional

from ...display.formatting import print_result_control_notes
from ...display.grep import FORMATS as GREP_FORMATS, _json_view as json_view, render_grep
from .formats import require_supported_format
from ...grep_handler import grep_directory, grep_execution_facts, grep_file
from ...utils.json_utils import json_answer
from ...utils.results import FailureCause, execution_exit_code
from .uri import announce_outcome, conclude_outcome


def _emit(result: Dict[str, Any], args: Namespace, label: str, answer_consumer=None) -> None:
    """The search's Answer, emitted or handed to *answer_consumer* (the Python API, BACK-2325). Its facts say whether
    the pattern was invalid (exit 2, ``RequestValidationError`` from the API) or a file it had to read was lost (exit 3).
    An invalid pattern is the path read's own refusal, answered as its other refusals are (``invalid_path_read``: the
    path's invalid-request document in JSON, ruling S4)."""
    from .uri import Answer
    facts = grep_execution_facts(result)
    if FailureCause.INVALID_REQUEST in facts.failures:
        from .declared import invalid_path_read
        refusal = invalid_path_read(label, result['error'], args)
        if refusal is not None:
            (answer_consumer or (lambda answer: answer.emit()))(refusal)
            return

    def printer(_answer, **_options):
        output_format = getattr(args, 'format', 'text')
        outcome = announce_outcome(result, label)
        render_grep(result, output_format)
        code = execution_exit_code(facts)
        if code:  # an invalid pattern (2) or a lost source (3), before conclude_outcome's legacy exit 1 (BACK-2527)
            print_result_control_notes(result, output_format)
            sys.exit(code)
        conclude_outcome(result, outcome, output_format)
    answer = Answer(result, 'structure', printer, execution_facts=facts, document=lambda: json_answer(json_view(result)))
    if answer_consumer is None:
        answer.emit()
    else:
        answer_consumer(answer)


def handle_grep(path: str, pattern: str, args: Namespace, *, answer_consumer=None) -> None:
    """``reveal FILE --grep PATTERN``."""
    require_supported_format(args, GREP_FORMATS, '--grep')  # before the search (BACK-2530)
    _emit(grep_file(path, pattern, args), args, path, answer_consumer)


def handle_grep_directory(path: str, pattern: str, args: Namespace,
                          include_extensions: Optional[List[str]] = None, *, answer_consumer=None) -> None:
    """``reveal DIR --grep PATTERN [--ext ...]``."""
    require_supported_format(args, GREP_FORMATS, '--grep')
    _emit(grep_directory(path, pattern, args, include_extensions), args, path, answer_consumer)
