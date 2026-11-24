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
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

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
    return AnalysisFailedError(message, result=_answer_document(answer))


def _answer_document(answer: Any) -> Optional[Dict[str, Any]]:
    """The JSON document *answer* prints with ``--format json``: the one its renderer builds (``Answer.document``: a
    file's envelope, a directory listing; None when it prints no document), else ``json_answer(result)``."""
    from ...utils.json_utils import json_answer
    if answer.document is not None:
        built: Optional[Dict[str, Any]] = answer.document()
        return built
    document: Dict[str, Any] = json_answer(answer.result)
    return document


def _failure(answer: Any, facts: Any) -> Exception:
    """The exception a library caller gets for an answer the CLI exits 2 or 3 on (``execution_failed``)."""
    from ...utils.results import execution_exit_code
    return _invalid_request(answer) if execution_exit_code(facts) == 2 else _analysis_failure(answer, facts)


def answer_failure(adapter: Any, result: Any, facts: Any) -> Optional[Exception]:
    """The exception for a declared noun's answer the CLI's declared route exits 2 or 3 on, mapped as the noun form maps
    its own (``_failure``); None for an answer that does not fail (findings and an incomplete answer return, marked).
    The URI form of ``api.query`` hands it the *adapter* that answered, its *result* and the owner's execution *facts*
    (BACK-2788). The answer is the one the route builds (``uri._structure_answer``), the owner's authored diagnostic
    (``public_diagnostic``) included."""
    from ...utils.results import execution_failed
    from .uri import Answer, _public_answer_diagnostic
    if facts is None or not isinstance(result, dict) or not execution_failed(facts):
        return None
    diagnostic = _public_answer_diagnostic(adapter, result, facts)
    return _failure(Answer(result, 'structure', _unprinted, execution_facts=facts, public_diagnostic=diagnostic), facts)


def _unprinted(_answer: Any, **_options: Any) -> None:
    """The printer of an answer the Python API raises instead of printing."""


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


# --- the path read (D21, BACK-2325): api.analyze(PATH, **controls) is ``reveal PATH --flags --format json`` -------------

def path_read_options(parser: argparse.ArgumentParser) -> Dict[str, Tuple[str, argparse.Action]]:
    """keyword -> (the long flag it writes, its action), for every request control of a path read, read from the main
    *parser*: its long flags with ``-`` as ``_``, minus what is no control of a file or directory read: the output and
    process options (the global options, ``--breadcrumbs`` aside), the modes that read no path or no element
    (``PATHLESS_FLAGS``, ``ELEMENT_LESS_FLAGS``), the element's own controls (the element views, ``ELEMENT_KEYS``, and
    ``--section``, ``ELEMENT_FLAGS``: an element read) and help."""
    from ...nav_params import ELEMENT_KEYS, ELEMENT_VIEW_SPECS
    from ...utils.query_binding import legacy_flag_dests
    from ..parser import _build_global_options_parser
    from .file import ELEMENT_FLAGS, ELEMENT_LESS_FLAGS, PATHLESS_FLAGS
    excluded = {action.dest for action in _build_global_options_parser(main_modes=True)._actions} - {'breadcrumbs'}
    excluded |= set(PATHLESS_FLAGS) | set(ELEMENT_LESS_FLAGS) | set(ELEMENT_FLAGS) | {'help', 'help_all', 'version'}
    excluded |= {dest for spec in ELEMENT_VIEW_SPECS if spec.name in ELEMENT_KEYS
                 for dest in ((spec.cli.dest if spec.cli else None) or spec.name, *legacy_flag_dests(spec))}
    options: Dict[str, Tuple[str, argparse.Action]] = {}
    for action in parser._actions:
        if action.dest in excluded:
            continue
        for flag in action.option_strings:
            if flag.startswith('--'):
                options.setdefault(flag[2:].replace('-', '_'), (flag, action))
    return options


def _analyzer_words(parser: argparse.ArgumentParser, options: Mapping[str, Tuple[str, argparse.Action]]) -> Dict[str, List[str]]:
    """analyzer keyword -> the path read's keywords that set it, read from the CLI's one mapping
    (``display.formatting._build_analyzer_kwargs``): the words ``api.analyze`` forwarded to ``get_structure()`` before
    it took the path read's flags (``extract_links`` is ``links``)."""
    from ...display.formatting import _build_analyzer_kwargs

    class _EveryAnalyzer:  # the attributes _build_analyzer_kwargs asks of Markdown, HTML and nginx analyzers
        _extract_links = _extract_metadata = _filter_structure_by_domain = None

    words: Dict[str, List[str]] = {}
    for keyword, (_flag, action) in options.items():
        args = parser.parse_args([])
        value: Any = True if action.nargs == 0 else (action.choices and next(iter(action.choices))) or (
            1 if action.type is int else 'x')
        setattr(args, action.dest, value)
        try:
            produced = _build_analyzer_kwargs(cast(Any, _EveryAnalyzer()), args)
        except (TypeError, ValueError):  # a value of the wrong shape for a reader this probe does not model
            continue
        for word in produced:
            if word not in options:
                words.setdefault(word, []).append(keyword)
    return words


def path_read_words(parser: argparse.ArgumentParser, controls: Mapping[str, Any]) -> List[str]:
    """The path read's flags for *controls* (``path_read_options``); a keyword that names none is the
    unsupported-control error (``UnsupportedOverrideError``), raised before anything runs, naming the flag keyword for
    an analyzer word ``api.analyze`` used to forward. A ``range`` tuple ``(A, B)`` is the flag's ``A-B``."""
    from ...errors import UnsupportedOverrideError
    from .canonical import _flag_words
    options = path_read_options(parser)
    unknown = [keyword for keyword in controls if keyword not in options]
    if unknown:
        renamed = _analyzer_words(parser, options)
        taught = [f"{word!r} is the analyzer's word that {_either(renamed[word])} set{'s' if len(renamed[word]) == 1 else ''}"
                  for word in unknown if word in renamed]
        raise UnsupportedOverrideError(
            f"unsupported keyword{'s' if len(unknown) > 1 else ''} {', '.join(map(repr, unknown))} for a path read; "
            f"its keywords are the flags of reveal PATH with - as _ (reveal --help)"
            + (f" ({'; '.join(taught)})" if taught else ''))
    words: List[str] = []
    for keyword, value in controls.items():
        flag, action = options[keyword]
        if action.dest == 'range' and isinstance(value, tuple) and len(value) == 2:
            value = f'{value[0]}-{value[1]}'
        words.extend(_flag_words(keyword, flag, action, value))
    return words


def _either(keywords: List[str]) -> str:
    named = [f'{keyword}=' for keyword in keywords]
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} or {named[-1]}"


class _Failed(Exception):
    """The answer consumer's stop: the path read failed (exit 2 or 3); the failure is raised outside the route."""


def answer_path_read(path: Any, controls: Mapping[str, Any], element: Optional[str] = None) -> Dict[str, Any]:
    """Answer ``reveal PATH [ELEMENT] --flags`` as the CLI's JSON document carries it (a file's envelope, a directory's
    tree, an element), through the CLI's own path-read route (``handle_file_or_directory`` with an answer consumer),
    inside the caller's host request and invocation log (``api.analyze``, ``api.element``). An invalid request raises
    ``RequestValidationError`` (the CLI's exit 2; a missing path ``PathNotFoundError``, an element miss
    ``ElementNotFoundError``), a failed analysis raises its cause or ``AnalysisFailedError`` carrying the document
    (exit 3); an incomplete answer returns, marked in itself as on the CLI."""
    from ...version import __version__
    from ...errors import RequestValidationError
    from ...utils.gitignore import gitignore_scope
    from ...utils.invocation_log import answer_is_json
    from ...utils.results import execution_failed, note_incomplete
    from ..invocation import Invocation, invocation_scope, record_typed_spellings
    from ..parser import check_navigation_args, create_argument_parser
    from .declared import JsonUsageParser
    from .file import _parse_file_line_syntax, handle_file_or_directory
    if not isinstance(path, (str, os.PathLike)):
        raise TypeError(f'the path of a path read is a path string, got {type(path).__name__}')
    target = os.fspath(path)
    if element is not None and not isinstance(element, str):
        raise TypeError(f'the element of a path read is a string, got {type(element).__name__}')
    if element is None and _parse_file_line_syntax(target)[1] is not None:
        raise RequestValidationError(f"{target} names lines of a file, an element: "
                                     f"api.element({target.rpartition(':')[0]!r}, {':' + target.rpartition(':')[2]!r})")
    parser = cast(JsonUsageParser, create_argument_parser(__version__))  # the main parser is one (raise_if_asked)
    parser.raise_usage_errors = True
    words = path_read_words(parser, controls)
    # The format words come before '--', which ends the options, so a path or element that starts with '-' stays one.
    invocation = Invocation.parse(['reveal', *words, '--format=json', '--', target, *([] if element is None else [element])])
    answers: list = []
    documents: List[Optional[Dict[str, Any]]] = []

    def consume(answer: Any) -> None:
        answers.append(answer)
        if answer.execution_facts is not None and execution_failed(answer.execution_facts):
            raise _Failed()
        # The document is read where the CLI prints it, inside the dispatch: the flag ledger's unused-input facts reach
        # its meta.warnings and the ledger prints no stderr note (ruling STOP 2 (a)).
        note_incomplete(answer.result, answer.execution_facts)  # as the CLI's JSON says it (a listing did)
        documents.append(_answer_document(answer))

    with invocation_scope(invocation, retirements_to_stderr=False, form='python'):
        args = parser.parse_args(invocation.argv)
        record_typed_spellings(parser, invocation.argv)
        check_navigation_args(args)  # the one check the CLI prints (validate_navigation_args), raised
        answer_is_json(True)  # diagnostics belong in the answer, as in the CLI's JSON mode
        try:
            with gitignore_scope(getattr(args, 'respect_gitignore', None) is not False):
                handle_file_or_directory(args.path, args, answer_consumer=consume)
        except _Failed:
            raise _failure(answers[-1], answers[-1].execution_facts) from None
        if not documents:
            raise RuntimeError(f'reveal {target} returned without an answer')
        document = documents[-1]
        if document is None:
            raise RequestValidationError(f'reveal {target} {" ".join(words)} prints no JSON document (its answer is '
                                         'text: --related-flat prints paths)')
        return document
