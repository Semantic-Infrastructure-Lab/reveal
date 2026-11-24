"""Declared command bindings into the existing adapter Answer path."""

from __future__ import annotations

import argparse
import errno
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, TypeGuard

from ..argparsing import RevealArgumentParser
from .ledger import FlagLedger, complete, delegate, ledger_of, mark, peek
from ...config import require_selected_config
from ...errors import ConfigLoadError
from ...utils.severity import CHECK_GATES
from ...utils.path_utils import to_posix
from ...adapters.factory import predicted_result_type, scope_path_of
from ...registry import get_markdown_extensions
from ...utils.query_parser import ParamSpec
from ..invocation import typed_spelling


def declared_adapter_class(name: str):
    """Only catalog entries with a qualified declaration adopt this path."""
    from ..invocation import COMMANDS
    from ...adapters.base import get_adapter_class
    spec = COMMANDS.get(name)
    if spec is None or not spec.declared_adapter:
        return None
    adapter = get_adapter_class(spec.declared_adapter)
    # The registry also admits legacy plugins/replacements. Scheme membership
    # alone cannot opt them into resource binding and generated query controls.
    if (getattr(adapter, 'RESOURCE_SPEC', None) is None
            or getattr(adapter, 'PARAM_SPECS', None) is None):
        return None
    return adapter


class _LenientParseFailed(Exception):
    """A re-parse that only recovers the request's format and target met a usage error of its own."""


class JsonUsageParser(RevealArgumentParser):
    """A parser whose usage errors, in a request that asks for JSON (``--format json`` or the ``--output json``
    stdout sink), answer with the invalid-request JSON document the declared route builds for an invalid value
    (COMMAND_MODEL "Transports"; exit 2, the message in the document and on stderr). The one seam for the main parser
    and every noun's declared parser; in text mode each keeps its own usage error. A subclass names the document's
    target in ``invalid_request``. A long option is spelled in full (``RevealArgumentParser``, BACK-2705).
    *raise_usage_errors*: the Python API reads its request with the CLI's own parser (the noun form, BACK-2717, and the
    path read, BACK-2325) and gets the message the CLI would print as a ``RequestValidationError``; nothing prints and
    nothing exits."""
    _argv: list | None = None
    _lenient: bool = False
    raise_usage_errors: bool = False

    def raise_if_asked(self, message: str) -> None:
        """Under *raise_usage_errors*, raise *message* (the one the CLI would print) as a ``RequestValidationError``;
        else return, for the CLI's printed error."""
        if self.raise_usage_errors:
            from ...errors import RequestValidationError
            raise RequestValidationError(message)

    def parse_known_args(self, args=None, namespace=None):
        if not self._lenient:  # the request as typed (main passes it), for a usage error to recover format and target
            self._argv = None if args is None else list(args)
        return super().parse_known_args(args, namespace)

    def invalid_request(self, message: str, args):
        """The invalid-request Answer for the request *args*, or None when its target has no such document."""
        return None

    def stop_tolerant_reread(self, message: str) -> None:
        """Inside the tolerant re-read, a usage error ends it instead of the process."""
        if self._lenient:
            raise _LenientParseFailed(message)

    def answer_in_json(self, message: str, args=None) -> None:
        """When the request asks for JSON, answer *message* with the document and exit 2; else return, for the
        caller's text error. *args*: the parsed request, or None to recover it from the typed words."""
        args = self._typed_request() if args is None else args
        if not self._asks_for_json(args):
            return
        args.format = 'json'  # a stdout sink the error left unresolved still asked for it
        answer = self.invalid_request(message, args)
        if answer is not None:
            answer.emit()
            self.exit(2)  # emit exits with the answer's outcome; this is the usage exit if it did not

    def _asks_for_json(self, args) -> bool:
        if getattr(args, 'format', None) == 'json':
            return True
        stdout_sinks = [spec for spec in getattr(args, 'output', None) or () if isinstance(spec, str) and '=' not in spec]
        return stdout_sinks == ['json'] and 'format' not in self._typed_words()[1]

    def _typed_request(self):
        """The request parsed again, leniently; one whose own error stops that parse (a flag missing its value, a
        value outside its choices) is read from the typed words over the parser's defaults: the positionals in
        order, ``--format`` and ``--output``. A malformed ``--output`` leaves its specs unresolved."""
        from ..invocation import current_invocation
        from .formats import OutputSinkError, apply_output_sinks, drop_file_sinks
        self._lenient = True
        try:
            args, _unknown = self.parse_known_args(self._argv or [])
        except _LenientParseFailed:
            args = self._typed_defaults()
        finally:
            self._lenient = False
        invocation = current_invocation()
        if invocation is not None:
            try:
                apply_output_sinks(args, invocation)
            except OutputSinkError:  # the usage error at hand is the answer; the stdout specs still say what was asked
                drop_file_sinks(args)
        return args

    def _typed_defaults(self):
        defaults = {action.dest: action.default for action in self._actions  # a suppressed default is absent, as in
                    if argparse.SUPPRESS not in (action.dest, action.default)}  # argparse's namespace (BACK-2756)
        args = argparse.Namespace(**{**defaults, **self._defaults})
        positionals, values = self._typed_words()
        for action, word in zip([a for a in self._actions if not a.option_strings], positionals):
            setattr(args, action.dest, word)
        if values.get('format'):
            args.format = values['format'][-1]
        if values.get('output'):
            args.output = values['output']
        return args

    def _typed_words(self) -> tuple:
        """(positionals, {dest: [values]}) as typed: a known option takes the value its action declares (one, or
        none for a switch), never a following option string, as argparse never does (``--limit --format json`` is
        a missing limit in a JSON request, BACK-2763); an unknown one takes none."""
        positionals: list = []
        values: dict = {}
        words = list(self._argv or [])
        index = 0
        while index < len(words):
            word = words[index]
            index += 1
            if word == '--':
                positionals.extend(words[index:])
                break
            if not word.startswith('-') or word == '-':
                positionals.append(word)
                continue
            option, eq, value = word.partition('=')
            action = self._option_string_actions.get(option)
            if action is None:
                continue
            if not eq and action.nargs != 0:
                value = ''
                if index < len(words) and not self._reads_as_option(words[index]):
                    value, index = words[index], index + 1
            values.setdefault(action.dest, []).append(value)
        return positionals, values

    def _reads_as_option(self, word: str) -> bool:
        """Whether argparse reads *word* as an option string, not a value: a known option (``--x=V`` included), or a
        word starting with a prefix character that is not a lone ``-``, a negative number (unless an option looks
        like one) or a word with a space (argparse's ``_parse_optional``)."""
        if word in self._option_string_actions or word.partition('=')[0] in self._option_string_actions:
            return True
        if len(word) < 2 or word[0] not in self.prefix_chars:
            return False
        if self._negative_number_matcher.match(word) and not self._has_negative_number_optionals:
            return False
        return ' ' not in word


class _DeclaredParser(JsonUsageParser):
    """A noun's parser: an unknown flag gets rule 3's teaching (the supported controls and fields, exit 2), the
    same message the URI gives, not argparse's bare usage error (COMMAND_MODEL "Unsupported controls"); in JSON
    mode every usage error answers with the invalid-request document (``JsonUsageParser``). The Python API's noun form
    (BACK-2717) reads its request with this parser and gets the same message raised (``raise_usage_errors``)."""
    declarations: tuple = ()
    noun: str = ''
    uri_query: Optional[str] = None  # the URI's query when this parser reads a URI request's flags (BACK-2673)

    def error(self, message: str):
        self.stop_tolerant_reread(message)
        flags = [token for token in message.partition(':')[2].split() if token.startswith('-')]
        teaching = message.startswith('unrecognized arguments:') and bool(flags)
        if teaching:
            from ...utils.query_binding import unsupported_controls_message
            message = unsupported_controls_message(self.declarations, flags)
        self.raise_if_asked(message)
        if teaching:
            self.answer_in_json(message)
            self._print_message(f'{self.prog}: error: {message}\n', sys.stderr)
            self.exit(2)
        self.answer_in_json(message)
        super().error(message)

    def invalid_request(self, message: str, args):
        from ...utils.query_binding import typed_resource
        adapter = declared_adapter_class(self.noun)
        if self.uri_query is not None:  # a URI request: its document keeps the operation the query selects
            path = typed_resource(adapter.RESOURCE_SPEC, args) or ''
            return _invalid_prepared_answer(adapter, self.noun, path, '?' + self.uri_query if self.uri_query else '',
                                            message, args)
        path = typed_resource(adapter.RESOURCE_SPEC, args) or '.'
        return _invalid_answer(adapter, self.noun, path, message, args)


def _declared_uri(target):
    """(adapter, scheme, path, query) for a URI target whose noun is declared, or None (a file, another scheme)."""
    from ...adapters.registry import get_adapter_class
    if not isinstance(target, str) or '://' not in target:
        return None
    scheme, _, resource = target.partition('://')
    adapter = get_adapter_class(scheme)
    if (adapter is None or getattr(adapter, 'RESOURCE_SPEC', None) is None
            or getattr(adapter, 'PARAM_SPECS', None) is None):
        return None
    path, _, query = resource.partition('?')
    return adapter, scheme, path, query


def invalid_uri_request(target, message: str, args):
    """The invalid-request Answer for a URI target whose noun is declared, or None (a file, another scheme)."""
    declared = _declared_uri(target)
    if declared is None:
        return None
    adapter, scheme, path, query = declared
    # A URI-only noun (codex) has no subcommand declaration to read its findings policy from.
    return _invalid_prepared_answer(adapter, scheme, path, '?' + query if query else '', message, args,
                                    default_fail_on=getattr(adapter, 'DEFAULT_FAIL_ON', 'none'))


def uri_flag_message(target, message: str) -> str | None:
    """Rule 3's one message for flags the main parser does not have on a URI request of a declared noun, or None
    (argparse's own error stands: another error, a file, an undeclared scheme). A declared noun's URI is read by its
    own parser (``declared_uri_request``), so this answers only the requests the main parser still reads: a
    ``--stdin`` batch's and a global flag the noun's subcommand does not take."""
    from ...utils.query_binding import unsupported_controls_message
    declared = _declared_uri(target)
    flags = [token for token in message.partition(':')[2].split() if token.startswith('-')]
    if declared is None or not message.startswith('unrecognized arguments:') or not flags:
        return None
    return unsupported_controls_message(declared[0].PARAM_SPECS, flags)


def is_path_read(target: Any) -> TypeGuard[str]:
    """Whether the request's target is a path read (a file or directory), not a URI or an ``@file`` list."""
    return isinstance(target, str) and bool(target) and '://' not in target and not target.startswith('@')


def path_read_flag_message(args, message: str) -> Optional[str]:
    """Rule 3's one message for flags the main parser does not have on an element request of a path read, or None
    (argparse's own error stands: another error, a URI, a path read that is no element request, BACK-2756 cell 3).
    *args*: the request as the main parser re-read it. A path read that is not an element request has no declaration
    to name and keeps BACK-522's scoped usage; an element request names its declarations (``ELEMENT_VIEW_SPECS``),
    as its refusal of a known main-parser flag does (``_reject_unsupported_element_controls``)."""
    from ...nav_params import ELEMENT_VIEW_SPECS, element_request_given
    from ...utils.query_binding import unsupported_controls_message
    flags = [token for token in message.partition(':')[2].split() if token.startswith('-')]
    path = getattr(args, 'path', None)
    if not is_path_read(path) or not message.startswith('unrecognized arguments:') or not flags:
        return None
    if not element_request_given(element_request_source(path, getattr(args, 'element', None), args)[0]):
        return None
    return unsupported_controls_message(ELEMENT_VIEW_SPECS, flags)


def invalid_path_read(target, message: str, args, error: Optional[BaseException] = None):
    """The invalid-request Answer of a path read (exit 2, the message in the document and on stderr), or None when
    *target* is no path read (BACK-2756 cell 21j). The document answers for the path as typed; its type is the facet
    the path read's declarations use (``element_view`` for an element request, ``code_element`` for an element,
    ``file_structure`` for a file, a directory's ``directory_tree``); stderr labels it as the file route labels a
    failed file, ``Error (PATH):``. A path read reads no findings, so its findings policy is none. *error*: a
    configuration that could not be loaded (``ConfigLoadError``) is lost input, the failed answer (exit 3), as on a
    declared noun (``_resource_failure_cause``)."""
    if not is_path_read(target):
        return None
    cause = _resource_failure_cause(error) if isinstance(error, ConfigLoadError) else None
    return _invalid_answer(None, 'file', target, message, args, cause, result_type=_path_read_answer(target, args),
                           default_fail_on='none', error=error, label=target)


class PathReadRefused(Exception):
    """A path read refused at one of its sites (``path_read_refusal``), raised there and answered where the path read
    answers: the file route's entry and ``file_handler.handle_file`` hand ``answer`` to their answer consumer, or emit
    it (the site's own text and exit)."""

    def __init__(self, answer: Any):
        super().__init__(answer.public_diagnostic)
        self.answer = answer


def path_read_refusal(target: str, text: str, args, *, exit_code: int = 2, error: Optional[BaseException] = None,
                      cause: Any = None):
    """The Answer of a path read that a site of the file route refuses (BACK-2325, ruling S4). *text* is exactly what
    the site prints on stderr, its error line then any hints; the document is the path read's invalid-request document
    (``invalid_path_read``'s facet and shape), its message the error line without its ``Error:`` label; the exit is
    *exit_code*, 2 for an invalid request (a site with a legacy code keeps it). *error*: what the Python API raises,
    the request's own ``RequestValidationError``, or with *cause* ``FailureCause.ANALYSIS`` the ``OSError`` of a file
    that could not be read (exit 3). MCP reads the facts and *text* (``public_diagnostic``), as the exit and stderr
    it read before."""
    from ...errors import RequestValidationError
    from ...reveal_types import CONTRACT_VERSION
    from ...utils.json_utils import print_json_result
    from ...utils.results import FailureCause, ResultBuilder, failure_execution_facts
    from .uri import Answer
    cause = FailureCause.INVALID_REQUEST if cause is None else cause
    first = text.splitlines()[0] if text else ''
    message = first.removeprefix('❌ ').removeprefix('Error: ')
    result = ResultBuilder.create(_path_read_answer(target, args), target, contract_version=CONTRACT_VERSION,
                                  source_type='unknown', errors=[{'code': cause.value, 'message': message}],
                                  error=message)

    def emit(_answer, **_options):
        print(text, end='' if text.endswith('\n') else '\n', file=sys.stderr)
        if getattr(args, 'format', None) == 'json':
            print_json_result(result)
        sys.exit(exit_code)
    return Answer(result, 'router', emit, execution_facts=failure_execution_facts(cause),
                  exception=error if cause is FailureCause.ANALYSIS else None, public_diagnostic=text.strip(),
                  request_error=error if isinstance(error, RequestValidationError) else None)


def _path_read_answer(target: str, args) -> str:
    from ...nav_params import ELEMENT_ANSWER, element_request_given
    element = getattr(args, 'element', None)
    if element_request_given(element_request_source(target, element, args)[0]):
        return ELEMENT_ANSWER
    if element:
        return 'code_element'
    return 'directory_tree' if os.path.isdir(target) else 'file_structure'


def element_request_source(path: str, element: Optional[str], args) -> tuple:
    """(source, spelled): the element declarations a path read gives (``typed_source`` over ``ELEMENT_VIEW_SPECS``),
    the one reading of whether a path read is an element request (``file_handler.element_request_of`` binds it, the
    main parser's error names its controls). The code-element ``--outline`` is its legacy view word only for an
    element of a non-Markdown file (its ``target:nav.outline`` row)."""
    from ...nav_params import ELEMENT_VIEW_SPECS
    source, spelled = typed_source(ELEMENT_VIEW_SPECS, args)
    if peek(args, 'outline') and element and Path(path).suffix.lower() not in get_markdown_extensions():
        source['outline'], spelled['outline'] = True, '--outline'
    return source, spelled


def _main_option_arity() -> Dict[str, int]:
    """Option string -> number of values, for every option of the main parser."""
    from ..parser import create_argument_parser
    return {option: 0 if action.nargs == 0 else 1
            for action in create_argument_parser('', full_help=False)._actions for option in action.option_strings}


def _target_index(argv) -> Optional[int]:
    """Index of the path/URI form's target (its first positional), or None. An option before it takes the values
    the main parser gives it; an option it does not have takes none."""
    arity: Optional[Dict[str, int]] = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == '--':
            return None
        if not token.startswith('-') or token == '-':
            return index
        if '=' not in token:
            arity = _main_option_arity() if arity is None else arity
            index += arity.get(token, 0)
        index += 1
    return None


def _main_parser_reads(noun: str, adapter, parser, argv, main_modes) -> bool:
    """Whether *argv* is still the main parser's to read: it types a global flag the URI binds through *noun*'s
    ``CLI_QUERY_FLAGS`` that its subcommand does not take, or a main-command mode that takes no path (*main_modes*, ``PATHLESS_FLAGS``) the
    noun's parser does not have, which the main parser refuses with its own teaching (BACK-1751; exit 2 as on the
    subcommand)."""
    from .flag_specs import FLAG_SPECS
    received = getattr(adapter, 'CLI_QUERY_FLAGS', None) or {}
    own = parser._option_string_actions
    # Every main-parser flag a declared noun keeps is a flag-only modifier of its declaration (ParamSpec.flag_only,
    # LEGACY_CLI_MODIFIERS); a global flag the URI's injection binds through the noun's CLI_QUERY_FLAGS that its
    # subcommand does not take is still the main parser's.
    pending = (*(flag.option for flag in FLAG_SPECS if flag.dest in received and flag.option not in own),
               *(option for option in main_modes if option not in own))
    for token in argv:
        if token == '--':
            return False
        if token.partition('=')[0] in pending:
            return True
    return False


def declared_uri_request(argv, main_modes=()) -> Optional[tuple]:
    """(noun, its parser, argv for that parser, URI) when the path/URI form's target is a URI of a noun with a declared
    subcommand, else None (a path, another scheme). The noun's own parser reads the request, the URI's path in the
    URI's place as the resource argument, so a flag after the URI is that subcommand's flag (COMMAND_MODEL "Flags after
    a URI", BACK-2673); the URI's query is the request's second source. None also for such a global flag or a
    main-command mode that takes no path (*main_modes*: the main parser refuses it with its own teaching)."""
    from ..invocation import COMMANDS
    index = _target_index(argv)
    if index is None or '://' not in argv[index]:
        return None
    uri = argv[index]
    noun, _, resource = uri.partition('://')
    spec = COMMANDS.get(noun)
    if spec is None or not spec.declared_adapter:
        return None
    adapter = declared_adapter_class(noun)
    if adapter is None:  # a plugin registered over the noun's scheme (BACK-2631)
        return None
    parser = create_declared_parser(noun, uri_request=True)
    if _main_parser_reads(noun, adapter, parser, argv, main_modes):
        return None
    parser.uri_query = resource.partition('?')[2]
    return noun, parser, [*argv[:index], resource.partition('?')[0], *argv[index + 1:]], uri


def parse_declared_uri_args(parser, argv):
    """(args, element) for a URI request read by its noun's parser: a positional after the URI's path is an element
    (refused by the runner, naming the URI form, as before), any other leftover the parser's usage error. A control
    the subcommand requires as a flag (Trace's ``--from``) is given by the URI's query too, and an element is refused
    before a missing one is named."""
    required = [action for action in parser._actions if action.required and action.option_strings]
    for action in required:
        action.required = False  # judged below, after an element, and against the URI's query too
    args, extras = parser.parse_known_args(argv)
    if len(extras) > 1 or any(token.startswith('-') for token in extras):
        parser.error('unrecognized arguments: ' + ' '.join(extras))
    element = extras[0] if extras else None
    missing = _missing_required(parser, args, required)
    if missing and element is None:
        parser.error('the following arguments are required: ' + ', '.join('/'.join(a.option_strings) for a in missing))
    return args, element


def _missing_required(parser, args, required: list) -> list:
    """The required flags neither typed nor given by the URI's query under a spelling of their control."""
    from ...utils.query_parser import query_key
    given = {query_key(part) for part in (parser.uri_query or '').split('&') if part}
    return [action for action in required if action.dest not in vars(args) and not given & _spellings_of(parser, action)]


def _spellings_of(parser, action) -> set:
    """The URI keys that give the control *action* sets (its declaration's spellings), or none."""
    return next((set(spec.spellings) for spec in parser.declarations
                 if spec.cli and action.dest == (spec.cli.dest or spec.name)), set())


def create_declared_parser(name: str, *, uri_request: bool = False) -> '_DeclaredParser':
    """The noun's subcommand parser, generated from its declarations. *uri_request*: the parser that reads a URI request
    of the noun (``declared_uri_request``), whose resource is the URI's path in one positional even where the
    subcommand spells it in several words (``ResourceSpec.parts``: ``reveal diff LEFT RIGHT``)."""
    from ..parser import (_build_global_options_parser, _add_universal_filter_flags, _add_base_path_option,
                          add_declared_presentation_options, scalar_settings)
    from ..global_flags import add_exclude_argument, add_gitignore_arguments
    from ...utils.query_binding import add_declared_arguments
    adapter = declared_adapter_class(name)
    help_info = adapter.get_help()
    from ..invocation import exit_codes_text
    exits = exit_codes_text(name, getattr(adapter, 'FINDINGS_POLICIES', ('none',)))
    epilog = '\n\n'.join(part for part in (help_info.get('epilog'), exits) if part)
    parser = _DeclaredParser(
        prog=f'reveal {name}', parents=[_build_global_options_parser(main_modes=False)],
        description=help_info['description'], epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.declarations = tuple(adapter.PARAM_SPECS)
    parser.noun = name
    scalar_settings(parser)
    _describe_fail_on(parser, tuple(getattr(adapter, 'FINDINGS_POLICIES', ('none',))))
    # The global --all reaches every declared noun's subcommand as it reaches its URI form (BACK-2654): it binds
    # what the noun's --all declaration gives the selected answer; an answer with no cap is already every row, so
    # --all there answers as without it, with no note (COMMAND_MODEL "Applicability", BACK-2656).
    parser.add_argument('--all', action='store_true',
                        help='Show all results: lift the cap of the selected answer (the same as --all on the URI '
                             'form; an answer with no cap answers as without it)')
    add_declared_arguments(parser, adapter.PARAM_SPECS, adapter.RESOURCE_SPEC, joined=uri_request)
    add_declared_presentation_options(parser, getattr(adapter, 'CLI_PRESENTATION_FLAGS', ()))
    _offer_noun_formats(parser, adapter)
    if callable(getattr(adapter, 'reconfigure_base_path', None)):
        _add_base_path_option(parser)
    _add_universal_filter_flags(parser)
    if adapter.RESOURCE_SPEC.walks:
        add_exclude_argument(parser)
        add_gitignore_arguments(parser)
    hide_note_stage_flags(parser, name, adapter.PARAM_SPECS)
    return parser


def _offer_noun_formats(parser: argparse.ArgumentParser, adapter) -> None:
    """The global ``--format`` also offers the formats only this noun renders (``noun_formats``: calls/imports
    ``--format dot``, the flag form of ``?format=dot``, BACK-2722); every other parser keeps the global choices."""
    from .formats import noun_formats
    extra = noun_formats(adapter)
    for action in parser._actions:
        if extra and '--format' in action.option_strings:
            action.choices = [*list(action.choices or ()), *extra]


def _has_findings_gate(args, command: str | None) -> bool:
    """Commands that evaluate --fail-on in their own exit owner: file or directory check (`reveal check
    PATH` or `reveal PATH --check`; URI and stdin checks differ) review and health."""
    if command in ('check', 'review', 'health'):
        return True
    path = str(peek(args, 'path', '') or '')
    return command is None and bool(peek(args, 'check', False)) and bool(path) and '://' not in path


def _describe_fail_on(parser: argparse.ArgumentParser, policies: tuple) -> None:
    """Show only this noun's --fail-on values (BACK-2486).

    The flag comes from the shared global-options parent, which lists every policy.
    Only the displayed values narrow: rejection stays in validate_execution_policy so
    the subcommand and URI spellings keep one message (test_declared_parity_back2053).
    The parent is built per parser, so this action is not shared with another noun.
    """
    action = parser._option_string_actions['--fail-on']
    action.metavar = '{' + ','.join(policies) + '}'
    if 'findings' not in policies:
        action.help = ('This command has no findings gate, so only none is accepted; '
                       '--fail-on findings exits 2. Required analysis/output failures remain errors.')


def validate_execution_policy(args, command: str | None = None) -> None:
    """Reject execution policy on transports that have not adopted its contract."""
    policy = peek(args, 'fail_on')
    if policy is None:
        return
    name = command or str(peek(args, 'path', '')).partition('://')[0]
    adapter = declared_adapter_class(name)
    supported = getattr(adapter, 'FINDINGS_POLICIES', ()) if adapter is not None else ()
    if adapter is None and _has_findings_gate(args, command):
        from ...utils.results import FINDINGS_GATES as supported
        if command == 'check' or (command is None and peek(args, 'check', False)):
            supported = CHECK_GATES
    if peek(args, 'stdin', False) or peek(args, 'batch', False) or policy not in supported:
        print(f'Error: --fail-on {policy} is not supported for this operation/transport.', file=sys.stderr)
        sys.exit(2)
    if peek(args, 'exit_zero', False):
        print('Error: --fail-on cannot be combined with the legacy --exit-zero override; '
              'use --fail-on none to report findings without failing.', file=sys.stderr)
        sys.exit(2)


def _note_retired_flags(name: str, adapter) -> None:
    """The subcommand route's retirement hook: a declared parameter typed as its flag
    (``reveal calls --target``) is the spelling ``calls://?target=`` is, so it is looked up under
    the same ``param:<name>.<param>`` key, in the order typed (a URI's are in query order). The URI
    route's hook is ``_note_retired_spellings``. A hyphenated flag names its underscore alias
    (``--max-files`` is ``max_files``). A flag-only modifier has no URI key: its row is keyed by the flag,
    ``flag:<name>.<flag>`` (``ParamSpec.flag_only``). The value a flag carries is looked up as the URI's
    ``value:<name>.<param>=<value>`` key is (``--show calls`` is ``?show=calls``, BACK-2613; ``_typed_flag_value``)."""
    from ..invocation import current_invocation, retirement_note
    invocation = current_invocation()
    if invocation is None:
        return
    flags = {flag: spec for spec in adapter.PARAM_SPECS if spec.cli is not None for flag in spec.flags}
    argv = invocation.command_argv
    for index, token in enumerate(argv):
        if token == '--':
            break
        flag, has_value, value = token.partition('=')
        spec = flags.get(flag)
        if spec is None:
            continue
        retirement_note(flag_retirement_key(name, spec, flag))
        if spec.flag_only:
            continue
        typed = value if has_value else _typed_flag_value(spec, flag, argv[index + 1:index + 2])
        if typed is not None:
            retirement_note(f'value:{name}.{_flag_param(spec, flag)}={typed}')


def _typed_flag_value(spec: ParamSpec, flag: str, following: Sequence[str]) -> Optional[str]:
    """The value *flag* carries when typed without ``=``, spelled as the URI's value, else None. A flag that takes a
    value reads the next word; a control's own flag whose value is optional (``nargs='?'``: Imports ``--importers
    [FILE]``, Calls ``--detail [LEVEL]``) reads the next word when argparse does (it does not look like an option),
    and given bare carries its ``const``, spelled as a bare URI key binds it (a boolean lowercase: ``?importers`` is
    ``importers=true``; BACK-2774 ruling S1)."""
    word = following[0] if following and following[0] != '--' else None
    if _flag_takes_value(spec, flag):
        return word
    if spec.cli is None or spec.cli.nargs != '?' or flag not in spec.cli.flags:
        return None
    if word is not None and not word.startswith('-'):
        return word
    const = spec.cli.const
    if const is None:
        return None
    return str(const).lower() if isinstance(const, bool) else str(const)


def _flag_takes_value(spec: ParamSpec, flag: str) -> bool:
    """Whether *flag* of *spec* reads the next word as its value (a switch such as ``--builtins`` reads none)."""
    entry = spec.legacy_entry(flag)
    if entry is not None and entry.flag == flag:
        return entry.flag_value is None
    cli = spec.cli
    return cli is not None and cli.action not in ('store_true', 'store_false', 'store_const', 'count') \
        and cli.nargs not in (0, '?')


def note_retired_where_fields(name: str, declarations, params, transport: str) -> None:
    """A where term on a field whose spelling retired notes that field's ``param:<name>.<field>`` row (COMMAND_MODEL
    "Retirement notes", BACK-2613 ruling Q2), however the term was spelled (``--where``, ``?where=``, a bare key). The
    fields are the noun's data, declared once on its where control (``where_param(retired_fields=...)``). A URI request
    notes through ``note_uri_spelling``, which leaves a row its request note covers to that note; once per row."""
    from ..invocation import note_uri_spelling, retirement_note
    from ...utils.query_binding import where_fields
    expression = next((spec for spec in declarations if spec.role == 'filter-expression' and spec.retired_fields), None)
    if expression is None:
        return
    note = note_uri_spelling if transport == 'uri' else retirement_note
    for field in dict.fromkeys(where_fields(params, expression)):
        if field in expression.retired_fields:
            note(f'param:{name}.{field}')


def flag_retirement_key(name: str, spec: ParamSpec, flag: str) -> str:
    """The RETIREMENTS key a declared control's *flag* is noted under on the subcommand route: a flag-only modifier's
    ``flag:<name>.<flag>``, else ``param:<name>.<param>`` for the legacy word, alias or name the flag spells."""
    return f'flag:{name}.{flag}' if spec.flag_only else f'param:{name}.{_flag_param(spec, flag)}'


def hide_note_stage_flags(parser: argparse.ArgumentParser, name: str, specs) -> None:
    """A declared noun's usage and --help list only canonical flags (Scott 2026-11-22, BACK-2755): an argument whose long
    flags are all spelled by a note-stage RETIREMENTS row is hidden (argparse SUPPRESS), with its short spellings (-v is
    --verbose). The row is the one typing the flag notes: a declared control's by ``flag_retirement_key``, any other
    flag's (the global --verbose, --also-json, --no-breadcrumbs, --no-gitignore) ``flag:<flag>``. A hidden flag still
    parses and answers with its note until the cut; help://schemas, generated from the declarations, keeps listing it."""
    from ..invocation import RETIREMENTS
    controls = {flag: spec for spec in specs if spec.cli is not None for flag in spec.flags}

    def note_stage(flag: str) -> bool:
        spec = controls.get(flag)
        row = RETIREMENTS.get(flag_retirement_key(name, spec, flag) if spec is not None else f'flag:{flag}')
        return row is not None and row.stage == 'note'

    for action in parser._actions:
        flags = [option for option in action.option_strings if option.startswith('--')]
        if flags and all(note_stage(flag) for flag in flags):
            action.help = argparse.SUPPRESS


def _flag_param(spec: ParamSpec, flag: str) -> str:
    """The declared parameter a subcommand flag spells: the legacy word or alias it names, else the canonical name."""
    spelled = flag[2:]
    if spelled == spec.name:
        return spec.name
    entry = spec.legacy_entry(flag)
    if entry is not None:
        return entry.name
    return next((alias for alias in spec.aliases if alias in (spelled, spelled.replace('-', '_'))), spec.name)


def run_declared_uri_command(name: str, uri: str, element: Optional[str], args) -> None:
    """A declared noun's URI request read by its own parser (``declared_uri_request``): the URI's spellings are noted
    as on every URI route, then the typed flags join the URI's query (``run_declared_command``)."""
    from .uri import _note_retired_spellings
    _note_retired_spellings(uri)
    query = uri.partition('?')[2]
    resource = peek(args, declared_adapter_class(name).RESOURCE_SPEC.name)
    if element:
        legacy = legacy_element_resource(name, resource, element)
        if legacy is None:
            _refuse_element(name, resource, element, args)
            return
        resource = legacy
    run_declared_command(name, args, uri_query=query, resource=resource)


def legacy_element_resource(name: str, path: str, element: str) -> Optional[str]:
    """The resource that names a positional element the noun still answers until the cut, its ``target:NOUN.element``
    row noted (``element_retirement``): the element after a ``/`` in the resource, the spelling the row names
    (``reveal diff://L:R NAME`` is ``diff://L:R/NAME``, BACK-2768); on an empty resource the element alone
    (``reveal help:// quick`` is ``help://quick``). None: the noun has no such row and refuses the element, as before
    (BACK-2526)."""
    from ..invocation import element_retirement
    if element_retirement(name) is None:
        return None
    return '/'.join(part for part in (path.rstrip('/'), element) if part)


def _refuse_element(name: str, path: str, element: str, args, answer_consumer=None) -> None:
    """A declared noun reads no element: one invalid-request answer naming the URI form (BACK-2526, BACK-2687)."""
    from ...adapters.base import unread_element_message
    adapter = declared_adapter_class(name)
    (answer_consumer or (lambda answer: answer.emit()))(_invalid_answer(
        adapter, name, path, unread_element_message(adapter, name, element), args))


def run_declared_command(name: str, args, *, answer_consumer=None, uri_query: Optional[str] = None,
                         resource: Optional[str] = None) -> None:
    """Bind original argparse values; no URI string is constructed. *uri_query*: the query of the URI these flags
    followed, the request's second source (joined under "Conflicting values", BACK-2673). *resource*: the resource in
    place of the positionals' (a URI request whose noted legacy element joins its path, ``legacy_element_resource``)."""
    from ...utils.query_binding import convert_flag_only, typed_resource
    adapter = declared_adapter_class(name)
    _note_retired_flags(name, adapter)
    convert_flag_only(adapter.PARAM_SPECS, args)
    source, spelled = typed_source(
        adapter.PARAM_SPECS, args,
        carried=lambda spec, source, spelled: _bind_global_carried(adapter, spec, args, uri_query, source, spelled))
    if resource is None:
        resource = typed_resource(adapter.RESOURCE_SPEC, args)
    _run_declared(name, args, resource, source, 'typed',
                  answer_consumer=answer_consumer, spelled=spelled, uri_query=uri_query)


def typed_source(specs, args, *, carried=None) -> tuple:
    """(source, spelled): the binder's typed source from parsed argparse values, and each key -> the flag that carried
    it, so errors name what was typed. The one reading of a declaration's flags off a namespace: a declared subcommand
    and the path read's element views both bind through it (BACK-2627). Reading here is peeking, not use (the ledger
    counts the reads the answer makes). *carried(spec, source, spelled)* fills a control with no flag of its own."""
    from ...utils.query_binding import flag_spellings, legacy_flag_dests
    source: dict = {}
    spelled: Dict[str, str] = {}
    for spec in specs:
        if spec.cli is None:
            if carried is not None:
                carried(spec, source, spelled)
            continue
        flags = flag_spellings(spec)
        dest = spec.cli.dest or spec.name
        if dest in vars(args):
            # A flag-only modifier binds by its own name: its dest may be a word the noun's own control owns (Claude's
            # --tail slice keeps args.tail for the router while ?tail=N is the legacy operation, BACK-2709).
            key = spec.name if spec.flag_only else dest
            source[key] = peek(args, dest)
            spelled[key] = typed_spelling(dest, flags.get(dest, dest))
        for legacy in legacy_flag_dests(spec):  # an old flag keeps its legacy name; the binder translates it
            if legacy in vars(args):
                source[legacy], spelled[legacy] = peek(args, legacy), flags[legacy]
    return source, spelled


def _bind_global_carried(adapter, spec: ParamSpec, args, uri_query: Optional[str], source: dict,
                         spelled: Dict[str, str]) -> None:
    """A control with no flag of its own, carried by the global flag of its name. A boolean is supplied only when set
    (`--all` is `&all`), as the URI spells it. The walk's --exclude fills the declared walk control (exclude_param) in
    the URI's spelling, a literal comma kept (BACK-1380), so a URI's exclude= and the flags after it are one list
    (BACK-2673) and the request is one request however it was spelled: ``?exclude=P`` is ``--exclude P`` (BACK-2730).
    The walk applies it through the one scope (``_walk_scope``). A --format value only this noun renders
    (``noun_formats``: calls/imports dot) is its format control, as ?format=dot spells it, so an answer that draws no
    graph refuses it as it refuses the URI's; text and json stay presentation (BACK-2722)."""
    from .formats import noun_formats
    value = peek(args, spec.name, None)
    if spec.type == 'boolean' and value is True:
        source[spec.name], spelled[spec.name] = True, _global_option(spec.name)
    elif spec.name == 'exclude' and value:
        from ...utils.query_parser import join_exclude_patterns
        source[spec.name], spelled[spec.name] = join_exclude_patterns(value), '--exclude'
    elif spec.name == 'format' and value is not None and value in noun_formats(adapter):
        source[spec.name], spelled[spec.name] = value, '--format'


def _global_option(dest: str) -> str:
    """The global flag that carries *dest* (its option string; ``--verbose`` is not a query flag)."""
    from .flag_specs import FLAG_SPECS, typed_option
    return next((typed_option(flag) for flag in FLAG_SPECS if flag.dest == dest), '--' + dest.replace('_', '-'))


def run_declared_uri(uri: str, element: str | None, args, consumed=(), *, answer_consumer=None) -> None:
    name, _, resource = uri.partition('://')
    path, _, query = resource.partition('?')
    if element:
        legacy = legacy_element_resource(name, path, element)
        if legacy is None:
            # One stderr line and an empty stdout left --format json with no answer (BACK-2526).
            _refuse_element(name, path, element, args, answer_consumer)
            return
        path = legacy
    _run_declared(name, args, path, query, 'uri', consumed, answer_consumer=answer_consumer)


def _bind_global_all(name, adapter, args, source, spelled=None, path=None, selection=None) -> None:
    """The subcommand's global ``--all`` through the URI form's own seam (``declared_flag_fragment``, BACK-2654): the
    noun's ``--all`` declaration, re-keyed to the cap of the answer the typed values select. A value the request
    already sets differently is an invalid request naming both flags, as on the URI form; on an answer with no cap
    (the noun declares no ``--all``, or the answer does not read its cap) it is satisfied, quietly, on both forms."""
    if peek(args, 'all', False) is not True:
        return
    from .flag_specs import FLAG_SPECS, declared_flag_fragment
    spec = next(flag for flag in FLAG_SPECS if flag.dest == 'all')
    fragment = declared_flag_fragment(spec, adapter, _selection(source, selection), path)
    if not fragment:  # a declared noun: no cap the selected answer reads, so --all is satisfied (lifts_no_cap)
        _satisfied_all(args, source, spelled)
        return
    key, _, value = fragment.partition('=')
    owner = next((declaration for declaration in adapter.PARAM_SPECS if key in declaration.spellings), None)
    given = _typed_value(owner, key, source)
    if given is not None and not _same_control_value(owner, given, (key, value)):
        mark(args, 'all')
        from ...errors import RequestValidationError
        typed = (spelled or {}).get(given[0], '--' + given[0])
        raise RequestValidationError(f'{typed} conflicts with --all: both set {key} with different values; give one')
    if given is None:
        source[key] = value
        if spelled is not None:
            spelled[key] = '--all'
    delegate(args, 'all', owner.name if owner is not None else key)


def _selection(source, selection) -> dict:
    """What a request selects: *selection* (a URI's query, or None) with the typed values given over it, so ``--all``
    binds to the cap of the answer both select (it binds after the join, BACK-2673)."""
    return {**(selection or {}), **{key: value for key, value in source.items() if value is not None}}


def _satisfied_all(args, source, spelled) -> None:
    """``--all`` on an answer with no cap it lifts: quiet. A control of the flag's own name that the subcommand gave
    it by name (Overview's ``all``) is dropped too, as the URI form injects nothing there."""
    if source.get('all') is True:
        del source['all']
        if spelled is not None:
            spelled.pop('all', None)
    mark(args, 'all')


def _typed_value(spec, key: str, source) -> tuple | None:
    """(source key, value) when the typed request already sets *spec*'s control under any of its keys (calls stores
    --limit under its legacy top), else None."""
    keys = (key,) if spec is None else (*spec.spellings, *((spec.cli.dest,) if spec.cli and spec.cli.dest else ()))
    return next(((typed, source[typed]) for typed in keys if source.get(typed) is not None), None)


def _same_control_value(spec, left: tuple, right: tuple) -> bool:
    """Two (spelling, raw value) pairs of one control, compared as the control reads them."""
    if spec is None:
        return str(left[1]) == str(right[1])
    try:
        return bool(spec.validate(spec.canonical_value(*left)) == spec.validate(spec.canonical_value(*right)))
    except ValueError:  # a value the control rejects is rejected when it binds; as typed, the two differ
        return False


def _bind_global_verbose(name, adapter, args, source, spelled=None) -> None:
    """The subcommand's global ``--verbose`` through the declarations, as the URI route binds it (rule 4, BACK-2654
    note #17): the noun's own legacy word ``verbose`` (the binder translates it and rejects a conflicting canonical
    value; noted under its ``param:`` row) or ``detail=full`` (noted under ``flag:--verbose``)."""
    if peek(args, 'verbose', False) is not True:
        return
    from ..invocation import retirement_note
    from ...errors import RequestValidationError
    from ...utils.query_binding import verbose_binding
    key, value = verbose_binding(adapter.PARAM_SPECS)
    given = source.get(key)
    if key == 'detail' and given is not None and given != value:
        typed = typed_spelling('verbose', '--verbose')
        raise RequestValidationError(f'{typed} conflicts with --detail {given}: {typed} is --detail full; give one')
    source[key] = value
    if spelled is not None:
        spelled[key] = typed_spelling('verbose', '--verbose')
    owner = next(spec.name for spec in adapter.PARAM_SPECS if key in spec.spellings)
    delegate(args, 'verbose', owner)  # unread when the answer does not read the control it stands for
    retirement_note('flag:--verbose' if key == 'detail' else f'param:{name}.verbose')


def _delegate_typed_parameters(name, adapter, args, source, transport: str, spelled=None) -> None:
    """Forward declaration accounting only after the receiving ledger exists. An inert flag-only modifier never shaped
    an answer: its retirement note is its whole effect, so it counts as read (ParamSpec.flag_only)."""
    mark(args, *((spec.cli.dest or spec.name) for spec in adapter.PARAM_SPECS if spec.flag_only == 'inert' and spec.cli))
    if transport != 'typed':
        return
    from ...utils.query_binding import legacy_flag_dests
    for spec in adapter.PARAM_SPECS:
        dest = (spec.cli.dest if spec.cli else None) or spec.name
        if dest in source:
            delegate(args, dest, spec.name)
        for legacy in legacy_flag_dests(spec):
            if legacy in source:
                delegate(args, legacy, spec.name)


def _validate_walk_policy(adapter, args, query_policy) -> None:
    """File-only declarations cannot promise filesystem-walking controls; a walking one refuses an empty pattern of its
    walk control's flag, declared or not (BACK-2730: ``--exclude ''`` answered as no exclusion)."""
    if adapter.RESOURCE_SPEC.walks:
        from ...utils.query_binding import reject_empty_walk_patterns
        reject_empty_walk_patterns(peek(args, 'exclude') or ())
        return
    if peek(args, 'exclude'):
        raise ValueError('--exclude requires a directory-walking operation')
    if query_policy is not None or peek(args, 'respect_gitignore', True) is False:
        typed = typed_spelling('respect_gitignore', '--respect-gitignore')
        raise ValueError(f'{typed} / ?respect-gitignore requires a directory-walking operation')



def _walk_scope(adapter, path, args, params=None):
    """The walk's scope (COMMAND_MODEL "Walk exclusion", BACK-2730): the walk control's patterns however the request
    spelled them, the --exclude flags and the declared exclude of the URI or a keyword (``params``, peeked, not read),
    as one list with REVEAL_IGNORE and config ``ignore`` (``dispatch_scope``). A file target has nothing to prune: it
    satisfies exclude quietly (D-2730-2 (a)), never an unused note or a refusal."""
    from ...utils.exclusions import dispatch_scope
    from ...utils.query_parser import peek_query_items, split_exclude_param
    from .ledger import satisfy_walk_exclusion
    if not adapter.RESOURCE_SPEC.walks:
        return None, []
    bound = dict(peek_query_items(params)).get('exclude') if params is not None else None
    patterns = list(peek(args, 'exclude') or [])
    for value in (bound if isinstance(bound, (list, tuple)) else [bound]):
        patterns += [pattern for pattern in split_exclude_param(value) if pattern not in patterns]
    if os.path.isfile(path):
        satisfy_walk_exclusion(args)
    return dispatch_scope(path, patterns)

def _spelled_query(uri_query: Optional[str], transport: str, source: Any) -> bool:
    """Whether the request spelled a URI query string: the query of the URI the flags followed, or the URI route's own."""
    if uri_query is not None:
        return bool(uri_query)
    return transport == 'uri' and bool(source)


def _note_uri_request(name: str, adapter, path: str, params, transport: str, spelled_query: bool, *,
                      early: bool = False, answer=None, walk_policy: Optional[bool] = None) -> None:
    """The one note of a retiring URI request (BACK-2716 step 3), rendered from what was bound: an analysis-only scheme
    always, any other scheme when it spells a query string. A retired twin has its own scheme row, and a resource URI
    with only flags is the canonical form: neither notes.

    At the ``note`` stage it is said once the request has an answer, and not for a rejected request: the command it
    would recommend is the one the request spells, and fails the same way. At the ``error`` stage (the cut) it is
    refused before anything runs (*early*). Rendering never marks a control as read: the answer's own unread-control
    checks see exactly what the request gave. *walk_policy* is the request's ``respect_gitignore``, split off before
    binding, so the recommended command walks as the request does."""
    from ..invocation import REQUEST_STAGE, request_note, request_noted
    if transport != 'uri' or not request_noted(name) or not (getattr(adapter, 'ANALYSIS_ONLY', False) or spelled_query):
        return
    if early != (REQUEST_STAGE == 'error'):
        return
    if answer is not None:
        from ...utils.results import FailureCause
        facts = getattr(answer, 'execution_facts', None)
        if facts is not None and FailureCause.INVALID_REQUEST in facts.failures:
            return
    from .canonical import render_uri_request
    parser = create_declared_parser(name)
    try:
        request_note(name, lambda form: render_uri_request(form, name, path, params, parser=parser, adapter=adapter,
                                                           walk_policy=walk_policy, presentation=not _typed_presentation()))
    except ValueError:
        return  # a request that cannot render is invalid: binding says why, with the answer's own type (not this note)


def _typed_presentation() -> bool:
    """Whether the invocation typed its own ``--format``/``--output``: a URI's ``?format=`` then lost to it, and the request
    note repeating it would conflict with the flag the caller keeps (rule 18)."""
    from ..invocation import current_invocation
    invocation = current_invocation()
    for token in (invocation.command_argv if invocation is not None else []):
        if token == '--':
            break
        if token.partition('=')[0] in ('--format', '--output'):
            return True
    return False


def _note_walk_policy(query_policy: Optional[bool], typed_policy: Any) -> Optional[bool]:
    """The walk policy the request note's command repeats: the URI's ``respect_gitignore``, else a typed off (on is the
    default, so repeating it changes nothing)."""
    if query_policy is not None:
        return query_policy
    return False if typed_policy is False else None


def _run_declared(name: str, args, path: str, source: Any, transport: str, consumed=(), *,
                  answer_consumer=None, spelled: Optional[Dict[str, str]] = None,
                  uri_query: Optional[str] = None) -> None:
    """*uri_query*: on the typed transport, the query of the URI the flags followed; the two prepared sources join
    into one request under "Conflicting values" (``join_uri_and_flags``) that binds as the URI does."""
    from ...utils.exclusions import exclusion_scope
    from ...utils.gitignore import gitignore_scope, split_respect_gitignore
    from ...utils.query_binding import bind_resource_path, expand_resource_user, join_uri_and_flags, prepare_declared_params
    adapter = declared_adapter_class(name)
    consume = answer_consumer or (lambda answer: answer.emit())
    from .formats import declared_output_formats, require_supported_format
    require_supported_format(args, declared_output_formats(adapter), f'{name}://')
    validate_execution_policy(args, name)
    spelled_query = _spelled_query(uri_query, transport, source)
    ledger = None
    if ledger_of(args) is None:
        ledger = FlagLedger(args)
        args = ledger.track(args)
    mark(args, *consumed)
    _delegate_typed_parameters(name, adapter, args, source, transport, spelled)
    query_resource = _flagged_query(adapter, name, path, source, transport, args, consume, spelled, uri_query)
    if query_resource is None:
        return
    # Global query policy keeps its existing codec; never split the decoded path.
    query_resource, respect = split_respect_gitignore(query_resource)
    if transport == 'uri':
        source = query_resource.partition('?')[2]
    query_walk_policy = respect
    typed_walk_policy = peek(args, 'respect_gitignore', True)
    respect = respect if respect is not None else peek(args, 'respect_gitignore', True)
    note_walk = _note_walk_policy(query_walk_policy, typed_walk_policy)
    dispatch = ledger.dispatching(query_resource, name) if ledger is not None else nullcontext()
    try:
        with dispatch:
            try:
                require_selected_config()  # on every noun, read or not (BACK-2677)
                _validate_walk_policy(adapter, args, query_walk_policy)
                source = prepare_declared_params(adapter.PARAM_SPECS, source, transport, spelled=spelled)
                if uri_query is not None:
                    _join_walk_policy(args, query_walk_policy, typed_walk_policy, uri_query)
                    source = join_uri_and_flags(adapter.PARAM_SPECS, prepare_declared_params(
                        adapter.PARAM_SPECS, query_resource.partition('?')[2], 'uri'), source, spelled=spelled)
                    transport = 'uri'  # one request now, bound as the URI binds (its path's codec included)
                note_retired_where_fields(name, adapter.PARAM_SPECS, source, transport)
                _note_uri_request(name, adapter, path, source, transport, spelled_query, early=True,
                                  walk_policy=note_walk)
            except ValueError as exc:
                consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args, error=exc))
                return
            expected_type = predicted_result_type(adapter, source)
            try:
                path = bind_resource_path(adapter.RESOURCE_SPEC, expand_resource_user(path), transport=transport,
                                          resolve=getattr(adapter, 'resource_path', None))
            except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
                consume(_invalid_answer(adapter, name, path, _resource_error_message(exc, path), args,
                                        result_type=expected_type, error=exc))
                return
            except OSError as exc:
                consume(_invalid_answer(adapter, name, path, str(exc), args, _resource_failure_cause(exc),
                                        result_type=expected_type, error=exc))
                return
            scope_path = scope_path_of(adapter, path)
            expected_type = predicted_result_type(adapter, source, scope_path)
            try:
                root, excludes = _walk_scope(adapter, scope_path, args, source)
            except (OSError, ValueError, ConfigLoadError) as exc:  # the walk's settings included (BACK-2677)
                consume(_invalid_answer(adapter, name, path, str(exc), args, _resource_failure_cause(exc),
                                        result_type=expected_type, error=exc))
                return
            with exclusion_scope(root, excludes), gitignore_scope(respect):
                answer = _declared_answer(adapter, name, path, source, transport, args, expected_type,
                                          scope_path=scope_path)
                _note_uri_request(name, adapter, path, source, transport, spelled_query, answer=answer,
                                  walk_policy=note_walk)
                consume(answer)
            complete(args)
    finally:
        if ledger is not None and ledger.complete:
            ledger.report(name)


def _resource_failure_cause(error: OSError | ValueError | ConfigLoadError):
    """Windows invalid-name metadata and a request the walk's settings reject (a config value the walk reads that
    cannot be used, BACK-2677) are invalid requests; other OS loss stays analysis."""
    from ...errors import RequestValidationError
    from ...utils.results import FailureCause
    if isinstance(error, RequestValidationError):
        return FailureCause.INVALID_REQUEST
    return (FailureCause.INVALID_REQUEST if isinstance(error, OSError) and getattr(error, 'winerror', None) == 123
            else FailureCause.ANALYSIS)


def _resource_error_message(error, path: str) -> str:
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return f'Path not found: {to_posix(path)}'
    return str(error)


def _join_walk_policy(args, uri_policy: Optional[bool], typed_policy, uri_query: str) -> None:
    """Rule 1 for the gitignore switch typed after a URI: a different value than the URI's ``respect_gitignore`` is an
    invalid request naming both; equal values, or one alone, are the policy (COMMAND_MODEL "Flags after a URI")."""
    from ..invocation import typed_spellings
    from ...errors import RequestValidationError
    from ...utils.query_binding import flag_conflicts_with_uri_message
    typed = typed_spellings().get('respect_gitignore')
    if uri_policy is None or typed is None or bool(typed_policy) == uri_policy:
        return
    raw = next(part.partition('=')[2] for part in uri_query.split('&') if part.partition('=')[0] == 'respect_gitignore')
    mark(args, 'respect_gitignore')
    raise RequestValidationError(flag_conflicts_with_uri_message(typed, 'respect_gitignore', raw))


def _flagged_query(adapter, name, path, source, transport: str, args, consume, spelled=None,
                   uri_query: Optional[str] = None) -> str | None:
    """The URI query with the global flags injected; None after answering a flag that conflicts with the
    URI's own value as an invalid request (BACK-2654). On the typed transport the global flags bind into the typed
    values, ``--all`` against the selection the URI's query (*uri_query*) makes as well; that query is returned
    unchanged, for the join."""
    query_resource: str = '?' + source if transport == 'uri' else '?' + uri_query if uri_query else ''
    if transport != 'uri':
        from ...utils.query_parser import parse_query_params, peek_query_items
        # peek: reading the URI's selection to place --all is routing, not the answer reading its controls
        selection = dict(peek_query_items(parse_query_params(uri_query))) if uri_query else None
        try:
            _bind_global_verbose(name, adapter, args, source, spelled)
            _bind_global_all(name, adapter, args, source, spelled, path, selection)
        except ValueError as exc:
            consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args, error=exc))
            return None
        return query_resource
    from .flag_specs import inject_query_flags
    try:
        flagged: str = inject_query_flags(query_resource, name, args, path)
    except ValueError as exc:
        consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args, error=exc))
        return None
    return flagged


def _invalid_prepared_answer(adapter, name, path, resource, message, args, *, default_fail_on=None, error=None):
    """Keep an unbound request's mode identity when decoding/alias validation fails."""
    selector = getattr(adapter, 'uri_result_type', None)
    try:
        expected_type = selector(resource) if selector is not None else adapter.RESULT_TYPE
    except ValueError:  # the selector reads the same rejected query (BACK-2655): no mode beyond the default
        expected_type = adapter.RESULT_TYPE
    return _invalid_answer(adapter, name, path, message, args, result_type=expected_type,
                           default_fail_on=default_fail_on, error=error)


def _typed_spellings(adapter) -> set:
    """The parameter spellings the subcommand's flags named (``--rank`` is ``rank``), as the URI's keys are."""
    from ..invocation import current_invocation
    invocation = current_invocation()
    if invocation is None:
        return set()
    flags = {flag: _flag_param(spec, flag) for spec in adapter.PARAM_SPECS if spec.cli is not None for flag in spec.flags}
    return {flags[token.partition('=')[0]] for token in invocation.command_argv if token.partition('=')[0] in flags}


def _validate_bound_request(adapter_class, params, path, args):
    from ...utils.query_binding import reject_two_answers
    reject_two_answers(adapter_class.PARAM_SPECS, params, _typed_spellings(adapter_class))  # one answer (BACK-2654)
    validate = getattr(adapter_class, 'validate_request', None)
    if validate is not None:
        validate(params, args)
    validate_at = getattr(adapter_class, 'validate_request_at', None)
    if validate_at is not None:
        validate_at(params, path, args)


def _declared_answer(adapter_class, name: str, path: str, source: Any, transport: str, args, expected_type: str,
                     *, scope_path: str | None = None):
    from ...adapters.factory import _canonical_init
    from ...utils.query_binding import bind_prepared_params
    from ...utils.path_utils import to_posix
    from .uri import _answer, _call_adapter, _renderer_class_of, _structure_answer, _configure_base_path
    scope = path if scope_path is None else scope_path
    try:
        params = source
        if not getattr(adapter_class, 'SOURCE_BEFORE_CONTROLS', False):
            params = bind_prepared_params(adapter_class.PARAM_SPECS, source, transport=transport)
            _validate_bound_request(adapter_class, params, path, args)
        # stat distinguishes absence from inaccessible required work.
        if adapter_class.RESOURCE_SPEC.filesystem:
            Path(scope).stat()
    except (FileNotFoundError, NotADirectoryError):
        return _invalid_answer(adapter_class, name, scope, f'Path not found: {to_posix(path)}', args, result_type=expected_type)
    except ValueError as exc:
        return _invalid_answer(adapter_class, name, scope, str(exc), args, result_type=expected_type, error=exc)
    except OSError as exc:
        return _invalid_answer(adapter_class, name, scope, str(exc), args, _resource_failure_cause(exc),
                               result_type=expected_type, error=exc)

    def resolve():
        adapter = _call_adapter(lambda: _canonical_init(adapter_class, path, params=params),
                                name, scope, adapter_class, classify_validation=True)
        _configure_base_path(adapter, args, name, scope, adapter_class, qualified=True)
        return _structure_answer(adapter, _renderer_class_of(name), args, name, scope,
                                 source_path=scope, facts_of=adapter_class.execution_facts, expected_type=expected_type)

    return _answer(resolve, name, args, result_type=expected_type,
                   source_path=scope, facts_of=adapter_class.execution_facts)


def _invalid_answer(adapter, name, path, message, args, cause=None, *, result_type=None, default_fail_on=None,
                    error: Optional[BaseException] = None, label: Optional[str] = None):
    """An invalid-request answer saying *message*. *error*, the exception the message came from, is kept on the answer
    when it is the request's own validation error (``Answer.request_error``: the noun form of api.query raises it, an
    ``UnreadControlError`` as the URI form does, BACK-2720). *label*: what the stderr error line names, when not the
    noun's ``scheme://`` (a path read names its path)."""
    from ...errors import RequestValidationError
    from ...reveal_types import CONTRACT_VERSION
    from ...utils.results import FailureCause, ResultBuilder, failure_execution_facts
    from .uri import Answer, _emit_result, _render_router_result, announce_outcome
    cause = FailureCause.INVALID_REQUEST if cause is None else cause
    result = ResultBuilder.create(
        (result_type or adapter.RESULT_TYPE), path, contract_version=CONTRACT_VERSION,
        source_type='unknown', errors=[{'code': cause.value, 'message': message}], error=message)
    facts = failure_execution_facts(cause)

    def emit(answer, *, announce_error=True):
        if announce_error and label is not None:
            announce_outcome(result, label)
            announce_error = False
        _emit_result(result, args, name, _render_router_result, execution_facts=facts, execution_answer=answer,
                     announce_error=announce_error, default_fail_on=default_fail_on)
    return Answer(result, 'router', emit, execution_facts=facts, public_diagnostic=message,
                  request_error=error if isinstance(error, RequestValidationError) else None)


def is_closed_reader(exc: BaseException) -> bool:
    """A write failed because the reader closed (`| head`). Windows reports a closed pipe as
    EINVAL (WinError 232) where POSIX raises BrokenPipeError."""
    if isinstance(exc, BrokenPipeError):
        return True
    return os.name == 'nt' and isinstance(exc, OSError) and exc.errno in (errno.EINVAL, errno.EPIPE)


def detach_stdout() -> None:
    """Point stdout at the null device so buffered output and interpreter exit stop failing."""
    fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(fd, sys.stdout.fileno())
    finally:
        os.close(fd)


def emit_declared_result(result, args, scheme, render, facts, *, execution_answer=None, announce_error=True,
                         default_fail_on=None, renderer_owns_json=False, json_document=None, **render_kwargs) -> None:
    """Finalize selected D6 facts; legacy emitters keep their existing policy.

    File structures own their current JSON representation through the renderer;
    their output and failures still pass through this same boundary.
    """
    from ...display.formatting import print_result_control_notes
    from ...rendering.base import emit_rendered
    from ...utils.json_utils import (attach_provenance, print_json_result, write_also_json,
                                     write_requested_artifact)
    from ...utils.results import (FailureCause, execution_exit_code,
                                 failure_execution_facts, merge_execution_facts, note_incomplete)
    from .uri import announce_outcome
    if default_fail_on is None:
        default_fail_on = declared_adapter_class(scheme).DEFAULT_FAIL_ON
    policy = getattr(args, 'fail_on', None) or default_fail_on
    output_format = args.format
    note_incomplete(result, facts)
    result = attach_provenance(result)
    if announce_error:
        announce_outcome(result, f'{scheme}://')
    failure = write_requested_artifact(lambda: write_also_json(result, args, render, json_document=json_document, **render_kwargs), result)
    if failure is not None:
        facts = merge_execution_facts(facts, failure_execution_facts(FailureCause.OUTPUT))
        if execution_answer is not None:
            execution_answer.exception = failure
    code = execution_exit_code(facts, fail_on=policy)
    try:
        if output_format == 'json' and not renderer_owns_json:
            print_json_result(json_document(result) if json_document else result)
        else:
            emit_rendered(render, result, output_format, **render_kwargs)
        print_result_control_notes(result, output_format)
        sys.stdout.flush()
    except Exception as exc:  # boundary-ok: broad-except -- selected output boundary contains renderer/plugin failures, discloses required output failure and exits 3
        if is_closed_reader(exc):
            # Reader closure alone retains 0; independently established failures survive.
            detach_stdout()
        else:
            print(f'Error: Requested output failed: {exc}', file=sys.stderr)
            facts = merge_execution_facts(facts, failure_execution_facts(FailureCause.OUTPUT))
            if execution_answer is not None:
                execution_answer.exception = exc
            code = 3
    if execution_answer is not None:
        execution_answer.execution_facts = facts
    if code != 2:
        complete(args)
    if code:
        sys.exit(code)



def qualify_declared_answer(result, adapter_class, path: str, expected_type=None, prior_facts=None):
    """Keep required answers canonical before projections; malformed success is failure."""
    from ...reveal_types import RevealResult
    expected_type = expected_type or adapter_class.RESULT_TYPE
    variants = getattr(adapter_class, 'RESULT_TYPE_VARIANTS', {}).get(expected_type, ())
    required = RevealResult.__required_keys__
    valid = (isinstance(result, dict)
             and all(isinstance(result.get(key), str) and result[key] for key in required)
             and result.get('type') in (expected_type, *variants)
             and _valid_answer_meta(result.get('meta', {}))
             and isinstance(result.get('scope', {}), dict))
    requirement_error = None
    if valid:
        requirement = getattr(adapter_class, 'answer_requirement_error', None)
        requirement_error = requirement(result, expected_type, prior_facts) if requirement else None
        if requirement_error is None:
            return result
    return _repair_declared_answer(result, path, expected_type, requirement_error)


def _repair_declared_answer(result, path, expected_type, requirement_error):
    from ...reveal_types import CONTRACT_VERSION, RevealResult
    from ...utils.path_utils import to_posix
    from ...utils.results import ResultBuilder
    required = RevealResult.__required_keys__
    original = result if isinstance(result, dict) else {}
    error = original.get('error') or requirement_error or 'Adapter returned an invalid required answer envelope'
    fields = required | {'meta', 'scope'}
    data = {key: value for key, value in original.items() if key not in fields}
    data['error'] = error
    meta = _repair_answer_meta(original.get('meta'), requirement_error or error)
    return ResultBuilder.create(
        expected_type, to_posix(path), contract_version=CONTRACT_VERSION,
        source_type='directory' if Path(path).is_dir() else 'file',
        meta=meta, scope=original.get('scope') if isinstance(original.get('scope'), dict) else None,
        data=data)


def _repair_answer_meta(meta, error):
    """Keep usable diagnostics when repairing a malformed required envelope."""
    from reprlib import Repr
    from ...utils.results import valid_warning_entry
    meta = dict(meta) if isinstance(meta, dict) else {'warnings': []}
    meta['errors'] = [*_diagnostic_dicts(meta.get('errors')),
                      {'code': 'invalid_adapter_answer', 'message': error}]
    warnings = meta.get('warnings', [])
    invalid = [entry for entry in warnings if not valid_warning_entry(entry)] if isinstance(warnings, list) else warnings
    if not isinstance(warnings, list) or invalid:
        bounded_repr = Repr()
        bounded_repr.maxstring = 160
        detail = bounded_repr.repr(invalid)[:1000]
        meta['errors'].append({'code': 'invalid_adapter_warning',
                               'message': f'Invalid warning diagnostic: {detail}'})
    meta['warnings'] = [entry for entry in warnings if valid_warning_entry(entry)] if isinstance(warnings, list) else []
    return meta


def _diagnostic_dicts(entries):
    if not isinstance(entries, list):
        return []
    diagnostics = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if 'type' in entry and not isinstance(entry['type'], str):
            entry = {key: value for key, value in entry.items() if key != 'type'}
        diagnostics.append(entry)
    return diagnostics


def _valid_answer_meta(meta):
    from ...utils.results import valid_error_entry, valid_warning_entry
    if not isinstance(meta, dict):
        return False
    return all(key not in meta or (isinstance(meta[key], list)
                                  and all(valid(entry) for entry in meta[key]))
               for key, valid in (('errors', valid_error_entry), ('warnings', valid_warning_entry)))
