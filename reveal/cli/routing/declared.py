"""Declared command bindings into the existing adapter Answer path."""

from __future__ import annotations

import argparse
import errno
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, Optional

from ..argparsing import RevealArgumentParser
from .ledger import FlagLedger, complete, delegate, ledger_of, mark, peek
from ...config import require_selected_config
from ...errors import ConfigLoadError
from ...utils.severity import CHECK_GATES
from ...utils.path_utils import to_posix
from ...adapters.factory import predicted_result_type, scope_path_of
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
    target in ``invalid_request``. A long option is spelled in full (``RevealArgumentParser``, BACK-2705)."""
    _argv: list | None = None
    _lenient: bool = False

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
        defaults = {action.dest: action.default for action in self._actions if action.dest != argparse.SUPPRESS}
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
        none for a switch); an unknown one takes none."""
        positionals: list = []
        values: dict = {}
        words = iter(self._argv or [])
        for word in words:
            if word == '--':
                positionals.extend(words)
                break
            if not word.startswith('-') or word == '-':
                positionals.append(word)
                continue
            option, eq, value = word.partition('=')
            action = self._option_string_actions.get(option)
            if action is None:
                continue
            if not eq and action.nargs != 0:
                value = next(words, '')
            values.setdefault(action.dest, []).append(value)
        return positionals, values


class _DeclaredParser(JsonUsageParser):
    """A noun's parser: an unknown flag gets rule 3's teaching (the supported controls and fields, exit 2), the
    same message the URI gives, not argparse's bare usage error (COMMAND_MODEL "Unsupported controls"); in JSON
    mode every usage error answers with the invalid-request document (``JsonUsageParser``). *raise_usage_errors*: the
    Python API's noun form (BACK-2717) reads its request with this parser and gets the same message as a
    ``RequestValidationError``; nothing prints and nothing exits."""
    declarations: tuple = ()
    noun: str = ''
    uri_query: Optional[str] = None  # the URI's query when this parser reads a URI request's flags (BACK-2673)
    raise_usage_errors: bool = False

    def error(self, message: str):
        self.stop_tolerant_reread(message)
        flags = [token for token in message.partition(':')[2].split() if token.startswith('-')]
        teaching = message.startswith('unrecognized arguments:') and bool(flags)
        if teaching:
            from ...utils.query_binding import unsupported_controls_message
            message = unsupported_controls_message(self.declarations, flags)
        if self.raise_usage_errors:
            from ...errors import RequestValidationError
            raise RequestValidationError(message)
        if teaching:
            self.answer_in_json(message)
            self._print_message(f'{self.prog}: error: {message}\n', sys.stderr)
            self.exit(2)
        self.answer_in_json(message)
        super().error(message)

    def invalid_request(self, message: str, args):
        adapter = declared_adapter_class(self.noun)
        if self.uri_query is not None:  # a URI request: its document keeps the operation the query selects
            path = getattr(args, adapter.RESOURCE_SPEC.name, None) or ''
            return _invalid_prepared_answer(adapter, self.noun, path, '?' + self.uri_query if self.uri_query else '',
                                            message, args)
        path = getattr(args, adapter.RESOURCE_SPEC.name, None) or '.'
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
    parser = create_declared_parser(noun)
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


def create_declared_parser(name: str) -> '_DeclaredParser':
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
    add_declared_arguments(parser, adapter.PARAM_SPECS, adapter.RESOURCE_SPEC)
    add_declared_presentation_options(parser, getattr(adapter, 'CLI_PRESENTATION_FLAGS', ()))
    if callable(getattr(adapter, 'reconfigure_base_path', None)):
        _add_base_path_option(parser)
    _add_universal_filter_flags(parser)
    if adapter.RESOURCE_SPEC.walks:
        add_exclude_argument(parser)
        add_gitignore_arguments(parser)
    return parser


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
    ``flag:<name>.<flag>`` (``ParamSpec.flag_only``)."""
    from ..invocation import current_invocation, retirement_note
    invocation = current_invocation()
    if invocation is None:
        return
    keys = {flag: f'flag:{name}.{flag}' if spec.flag_only else f'param:{name}.{_flag_param(spec, flag)}'
            for spec in adapter.PARAM_SPECS if spec.cli is not None for flag in spec.flags}
    for token in invocation.command_argv:
        if token == '--':
            break
        key = keys.get(token.partition('=')[0])
        if key is not None:
            retirement_note(key)


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
    if element:
        _refuse_element(name, peek(args, declared_adapter_class(name).RESOURCE_SPEC.name), element, args)
        return
    run_declared_command(name, args, uri_query=query)


def _refuse_element(name: str, path: str, element: str, args, answer_consumer=None) -> None:
    """A declared noun reads no element: one invalid-request answer naming the URI form (BACK-2526, BACK-2687)."""
    from ...adapters.base import unread_element_message
    adapter = declared_adapter_class(name)
    (answer_consumer or (lambda answer: answer.emit()))(_invalid_answer(
        adapter, name, path, unread_element_message(adapter, name, element), args))


def run_declared_command(name: str, args, *, answer_consumer=None, uri_query: Optional[str] = None) -> None:
    """Bind original argparse values; no URI string is constructed. *uri_query*: the query of the URI these flags
    followed, the request's second source (joined under "Conflicting values", BACK-2673)."""
    from ...utils.query_binding import convert_flag_only, flag_spellings, legacy_flag_dests
    adapter = declared_adapter_class(name)
    _note_retired_flags(name, adapter)
    convert_flag_only(adapter.PARAM_SPECS, args)
    source: dict = {}
    spelled: Dict[str, str] = {}  # each key -> the flag that carried it, so errors name what was typed
    for spec in adapter.PARAM_SPECS:
        if spec.cli is None:
            # A boolean with no flag of its own is carried by the global flag of its name
            # (`--all` is `&all`), supplied only when set, as the URI spells it. The walk's --exclude scopes the walk
            # (``_walk_scope``); after a URI that sets the declared exclude control (exclude_param) it fills that control
            # too, in the URI's spelling, a literal comma kept (BACK-1380), so the URI's exclude= and the flags after it
            # are one list: the control's own walk scope replaces the dispatch's (BACK-2673).
            value = peek(args, spec.name, None)
            if spec.type == 'boolean' and value is True:
                source[spec.name], spelled[spec.name] = True, _global_option(spec.name)
            elif spec.name == 'exclude' and value and _uri_sets(adapter, uri_query, spec):
                from ...utils.query_parser import join_exclude_patterns
                source[spec.name], spelled[spec.name] = join_exclude_patterns(value), '--exclude'
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
    _run_declared(name, args, getattr(args, adapter.RESOURCE_SPEC.name), source, 'typed',
                  answer_consumer=answer_consumer, spelled=spelled, uri_query=uri_query)


def _uri_sets(adapter, uri_query: Optional[str], spec: ParamSpec) -> bool:
    """Whether the URI's query (None: no URI) gives *spec*'s control under any of its spellings."""
    from ...utils.query_parser import query_key
    if not uri_query:
        return False
    return any(query_key(part) in spec.spellings for part in uri_query.split('&') if part)


def _global_option(dest: str) -> str:
    """The global flag that carries *dest* (its option string; ``--verbose`` is not a query flag)."""
    from .flag_specs import FLAG_SPECS, typed_option
    return next((typed_option(flag) for flag in FLAG_SPECS if flag.dest == dest), '--' + dest.replace('_', '-'))


def run_declared_uri(uri: str, element: str | None, args, consumed=(), *, answer_consumer=None) -> None:
    name, _, resource = uri.partition('://')
    path, _, query = resource.partition('?')
    if element:
        # One stderr line and an empty stdout left --format json with no answer (BACK-2526).
        _refuse_element(name, path, element, args, answer_consumer)
        return
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
    """File-only declarations cannot promise filesystem-walking controls."""
    if adapter.RESOURCE_SPEC.walks:
        return
    if peek(args, 'exclude'):
        raise ValueError('--exclude requires a directory-walking operation')
    if query_policy is not None or peek(args, 'respect_gitignore', True) is False:
        typed = typed_spelling('respect_gitignore', '--respect-gitignore')
        raise ValueError(f'{typed} / ?respect-gitignore requires a directory-walking operation')



def _walk_scope(adapter, path, args):
    from ...utils.exclusions import dispatch_scope
    return dispatch_scope(path, peek(args, 'exclude')) if adapter.RESOURCE_SPEC.walks else (None, [])

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
                                                           walk_policy=walk_policy))
    except ValueError:
        return  # a request that cannot render is invalid: binding says why, with the answer's own type (not this note)


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
    from ...utils.query_binding import bind_resource_path, join_uri_and_flags, prepare_declared_params
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
                _note_uri_request(name, adapter, path, source, transport, spelled_query, early=True,
                                  walk_policy=note_walk)
            except ValueError as exc:
                consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args))
                return
            expected_type = predicted_result_type(adapter, source)
            try:
                path = bind_resource_path(adapter.RESOURCE_SPEC, os.path.expanduser(path), transport=transport,
                                          resolve=getattr(adapter, 'resource_path', None))
            except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
                consume(_invalid_answer(adapter, name, path, _resource_error_message(exc, path), args,
                                        result_type=expected_type))
                return
            except OSError as exc:
                consume(_invalid_answer(adapter, name, path, str(exc), args, _resource_failure_cause(exc), result_type=expected_type))
                return
            scope_path = scope_path_of(adapter, path)
            expected_type = predicted_result_type(adapter, source, scope_path)
            try:
                root, excludes = _walk_scope(adapter, scope_path, args)
            except (OSError, ValueError, ConfigLoadError) as exc:  # the walk's settings included (BACK-2677)
                consume(_invalid_answer(adapter, name, path, str(exc), args, _resource_failure_cause(exc),
                                        result_type=expected_type))
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
            consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args))
            return None
        return query_resource
    from .flag_specs import inject_query_flags
    try:
        flagged: str = inject_query_flags(query_resource, name, args, path)
    except ValueError as exc:
        consume(_invalid_prepared_answer(adapter, name, path, query_resource, str(exc), args))
        return None
    return flagged


def _invalid_prepared_answer(adapter, name, path, resource, message, args, *, default_fail_on=None):
    """Keep an unbound request's mode identity when decoding/alias validation fails."""
    selector = getattr(adapter, 'uri_result_type', None)
    try:
        expected_type = selector(resource) if selector is not None else adapter.RESULT_TYPE
    except ValueError:  # the selector reads the same rejected query (BACK-2655): no mode beyond the default
        expected_type = adapter.RESULT_TYPE
    return _invalid_answer(adapter, name, path, message, args, result_type=expected_type,
                           default_fail_on=default_fail_on)


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
        return _invalid_answer(adapter_class, name, scope, str(exc), args, result_type=expected_type)
    except OSError as exc:
        return _invalid_answer(adapter_class, name, scope, str(exc), args, _resource_failure_cause(exc), result_type=expected_type)

    def resolve():
        adapter = _call_adapter(lambda: _canonical_init(adapter_class, path, params=params),
                                name, scope, adapter_class, classify_validation=True)
        _configure_base_path(adapter, args, name, scope, adapter_class, qualified=True)
        return _structure_answer(adapter, _renderer_class_of(name), args, name, scope,
                                 source_path=scope, facts_of=adapter_class.execution_facts, expected_type=expected_type)

    return _answer(resolve, name, args, result_type=expected_type,
                   source_path=scope, facts_of=adapter_class.execution_facts)


def _invalid_answer(adapter, name, path, message, args, cause=None, *, result_type=None, default_fail_on=None):
    from ...reveal_types import CONTRACT_VERSION
    from ...utils.results import FailureCause, ResultBuilder, failure_execution_facts
    from .uri import Answer, _emit_result, _render_router_result
    cause = FailureCause.INVALID_REQUEST if cause is None else cause
    result = ResultBuilder.create(
        (result_type or adapter.RESULT_TYPE), path, contract_version=CONTRACT_VERSION,
        source_type='unknown', errors=[{'code': cause.value, 'message': message}], error=message)
    facts = failure_execution_facts(cause)
    return Answer(result, 'router', lambda answer, *, announce_error=True: _emit_result(
        result, args, name, _render_router_result, execution_facts=facts, execution_answer=answer,
        announce_error=announce_error, default_fail_on=default_fail_on),
        execution_facts=facts, public_diagnostic=message)


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
