"""The Python API's noun form (BACK-2717): ``api.query(NOUN, TARGET, **controls)`` is the request
``reveal NOUN TARGET --flag value`` (COMMAND_MODEL rule 2, Scott 2026-11-19).

It runs through the CLI's own declared dispatch, not beside it: the keywords are written as the noun's flags,
the noun's parser reads them (its conversions, conflicts and teaching messages), ``run_declared_command``
answers, and the answer comes back to the caller instead of being printed. No URI is built, so a target keeps
every character it has, and no stdout is captured.

A keyword is a long flag with ``-`` written as ``_`` (``--test-framework`` is ``test_framework``; ``--from`` is
``**{'from': ...}``), read from the noun's parser, never from a table typed here. The keywords are the noun's
declared controls (their legacy flags included, which note as they do on the CLI), the walk's ``all``,
``exclude`` and ``respect_gitignore``, and the options the adapter itself declares (``base_path``,
``with_stats``). Output, sink, gate and process options (``format``, ``output``, ``fail_on``, ``copy``...) are
not request controls: the caller receives the answer itself.
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .canonical import _WALK_CONTROLS, typed_options, typed_words  # noqa: F401  (the keyword <-> flag words live in canonical)

def typed_nouns() -> Tuple[str, ...]:
    """The nouns the noun form answers: every command whose adapter is qualified for the declared route."""
    from ..invocation import COMMANDS
    from .declared import declared_adapter_class
    return tuple(sorted(name for name, spec in COMMANDS.items()
                        if spec.declared_adapter and declared_adapter_class(spec.declared_adapter) is not None))


def _noun_adapter(noun: str) -> Tuple[str, Any]:
    """(declared adapter name, class) for *noun*, or the ValueError that names what was asked for."""
    from ..invocation import COMMANDS
    from .declared import declared_adapter_class
    spec = COMMANDS.get(noun)
    adapter_name = spec.declared_adapter if spec is not None else ''
    adapter = declared_adapter_class(adapter_name) if adapter_name else None
    if adapter is not None:
        return adapter_name, adapter
    from ...adapters.base import get_adapter_class
    if get_adapter_class(noun) is not None:
        raise ValueError(f"{noun!r} has no subcommand: name the resource by its URI, "
                         f"query('{noun}://RESOURCE', ...)")
    raise ValueError(f"{noun!r} is neither a noun nor a URI. Nouns: {', '.join(typed_nouns())}; "
                     "a resource is named by its URI: scheme://resource (e.g. git://app.py@main)")


def _answer_dict(answer: Any) -> Dict[str, Any]:
    return answer.result if isinstance(answer.result, dict) else {}


def _invalid_request(answer: Any) -> Exception:
    """Exit 2: the request's own validation error (``UnreadControlError`` for an unread control, as the URI form raises;
    BACK-2720), else one with the CLI's message."""
    from ...errors import RequestValidationError
    for exc in (answer.exception, getattr(answer, 'request_error', None)):
        if isinstance(exc, RequestValidationError):
            return exc
    return RequestValidationError(answer.public_diagnostic or _answer_dict(answer).get('error') or 'invalid request')


def _analysis_failure(answer: Any, facts: Any) -> Exception:
    """Exit 3: the analysis's cause, else ``AnalysisFailedError`` with the answer's failure warnings and the answer
    itself, built inside the request's invocation scope so it carries its notes as the CLI's document does."""
    from ...errors import AnalysisFailedError
    from ...utils.json_utils import json_answer
    from ...utils.results import note_incomplete
    exc: Optional[Exception] = answer.exception
    if exc is not None:
        return exc
    result = _answer_dict(answer)
    meta = result.get('meta')
    warnings = meta.get('warnings') or () if isinstance(meta, dict) else ()
    failed = [w['message'] for w in warnings
              if isinstance(w, dict) and w.get('type') == 'analysis_failed' and w.get('message')]
    message = '; '.join(failed) or answer.public_diagnostic or result.get('error') or 'Required analysis or output failed'
    if not result:
        return AnalysisFailedError(message)
    note_incomplete(result, facts)
    document: Dict[str, Any] = json_answer(result)
    return AnalysisFailedError(message, result=document)


def _failure(answer: Any, facts: Any) -> Exception:
    """The exception a library caller gets for an answer the CLI exits 2 or 3 on (``execution_failed``)."""
    from ...utils.results import execution_exit_code
    return _invalid_request(answer) if execution_exit_code(facts) == 2 else _analysis_failure(answer, facts)


def answer_typed_request(noun: str, target: Optional[str], controls: Mapping[str, Any]) -> Dict[str, Any]:
    """Answer ``reveal NOUN [TARGET] --flags`` as the CLI's JSON document carries it, inside the caller's host request
    and invocation log (``api.query``). An invalid request raises ``RequestValidationError`` (the CLI's exit 2), a
    failed analysis raises its cause or ``AnalysisFailedError`` (exit 3); an incomplete answer and findings return,
    marked as on the CLI."""
    from ..invocation import Invocation, invocation_scope, record_typed_spellings, retirement_note
    from ...utils.invocation_log import answer_is_json
    from ...utils.json_utils import json_answer
    from ...utils.results import execution_failed, note_incomplete
    from .declared import create_declared_parser, run_declared_command
    from .subcommand import dispatch_subcommand
    adapter_name, adapter = _noun_adapter(noun)
    if target is not None and not isinstance(target, (str, os.PathLike)):
        raise TypeError(f'the target of {noun} is a path or resource string, got {type(target).__name__}')
    parser = create_declared_parser(adapter_name)  # the parser CommandSpec.load() gives a declared noun
    parser.raise_usage_errors = True
    words = typed_words(parser, adapter, controls)
    # The format words come before '--', which ends the options, so a target that starts with '-' stays the target.
    argv = [noun, *words, '--format=json', *([] if target is None else ['--', os.fspath(target)])]
    invocation = Invocation.parse(['reveal', *argv])
    answers: list = []

    def consume(answer: Any) -> None:
        # emit's exits, without exiting: a failure stops the dispatch before complete(args), as sys.exit does.
        facts = answer.execution_facts
        if facts is not None and execution_failed(facts):
            raise _failure(answer, facts)
        answers.append(answer)

    with invocation_scope(invocation, retirements_to_stderr=False, form='python'):
        retirement_note(f'subcommand:{noun}')  # a retired noun notes as its subcommand does (main._prepare)
        args = parser.parse_args(invocation.command_argv)
        record_typed_spellings(parser, invocation.command_argv)
        answer_is_json(True)  # diagnostics belong in the answer, as in the CLI's JSON mode
        dispatch_subcommand(noun, parser, partial(run_declared_command, adapter_name, answer_consumer=consume), args)
        if not answers:
            raise RuntimeError(f'reveal {noun} returned without an answer')
        answer = answers[-1]
        note_incomplete(answer.result, answer.execution_facts)
        document: Dict[str, Any] = json_answer(answer.result)
        return document
