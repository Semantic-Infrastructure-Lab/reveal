"""Declared command bindings into the existing adapter Answer path."""

from __future__ import annotations

import argparse
import errno
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .ledger import FlagLedger, complete, delegate, ledger_of, mark, peek


def declared_adapter_class(name: str):
    """Only catalog entries with a qualified declaration adopt this path."""
    from ..invocation import COMMANDS
    from ...adapters.base import get_adapter_class
    spec = COMMANDS.get(name)
    if spec is None or not spec.declared_adapter:
        return None
    return get_adapter_class(spec.declared_adapter)


def create_declared_parser(name: str) -> argparse.ArgumentParser:
    from ..parser import _build_global_options_parser, _add_universal_filter_flags
    from ..global_flags import add_exclude_argument, add_gitignore_arguments
    from ...utils.query_binding import add_declared_arguments
    adapter = declared_adapter_class(name)
    help_info = adapter.get_help()
    from ..invocation import exit_codes_text
    exits = exit_codes_text(name, getattr(adapter, 'FINDINGS_POLICIES', ('none',)))
    epilog = '\n\n'.join(part for part in (help_info.get('epilog'), exits) if part)
    parser = argparse.ArgumentParser(
        prog=f'reveal {name}', parents=[_build_global_options_parser()],
        description=help_info['description'], epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    add_declared_arguments(parser, adapter.PARAM_SPECS, adapter.RESOURCE_SPEC)
    if name == 'overview':
        parser.add_argument('--all', action='store_true',
                            help='Show every entry in capped sections (same expansion as --verbose)')
    _add_universal_filter_flags(parser)
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
    if peek(args, 'stdin', False) or peek(args, 'batch', False) or policy not in supported:
        print(f'Error: --fail-on {policy} is not supported for this operation/transport.', file=sys.stderr)
        sys.exit(2)
    if peek(args, 'exit_zero', False):
        print('Error: --fail-on cannot be combined with the legacy --exit-zero override; '
              'use --fail-on none to report findings without failing.', file=sys.stderr)
        sys.exit(2)


def run_declared_command(name: str, args, *, answer_consumer=None) -> None:
    """Bind original argparse values; no URI string is constructed."""
    adapter = declared_adapter_class(name)
    source = {}
    for spec in adapter.PARAM_SPECS:
        if spec.cli is None:
            continue
        dest = spec.cli.dest or spec.name
        if dest in vars(args):
            source[dest] = peek(args, dest)
    _run_declared(name, args, getattr(args, adapter.RESOURCE_SPEC.name), source, 'typed',
                  answer_consumer=answer_consumer)


def run_declared_uri(uri: str, element: str | None, args, consumed=(), *, answer_consumer=None) -> None:
    name, _, resource = uri.partition('://')
    path, _, query = resource.partition('?')
    if element:
        print(f'Error: {name} does not support element selection.', file=sys.stderr)
        sys.exit(2)
    _run_declared(name, args, path, query, 'uri', consumed, answer_consumer=answer_consumer)


def _delegate_typed_parameters(adapter, args, source, transport: str) -> None:
    """Forward declaration accounting only after the receiving ledger exists."""
    if transport != 'typed':
        return
    for spec in adapter.PARAM_SPECS:
        if spec.cli is not None:
            dest = spec.cli.dest or spec.name
            if dest in source:
                delegate(args, dest, spec.name)


def _run_declared(name: str, args, path: str, source: Any, transport: str, consumed=(), *,
                  answer_consumer=None) -> None:
    from ...utils.exclusions import dispatch_scope, exclusion_scope
    from ...utils.gitignore import gitignore_scope, split_respect_gitignore
    from ...utils.query_binding import bind_resource_path, prepare_declared_params
    adapter = declared_adapter_class(name)
    consume = answer_consumer or (lambda answer: answer.emit())
    from .formats import declared_output_formats, require_supported_format
    require_supported_format(args, declared_output_formats(adapter), f'{name}://')
    validate_execution_policy(args, name)
    ledger = None
    if ledger_of(args) is None:
        ledger = FlagLedger(args)
        args = ledger.track(args)
    mark(args, *consumed)
    _delegate_typed_parameters(adapter, args, source, transport)
    query_resource = '?' + source if transport == 'uri' else ''
    if transport == 'uri':
        from .flag_specs import inject_query_flags
        query_resource = inject_query_flags(query_resource, name, args)
    # Global query policy keeps its existing codec; never split the decoded path.
    query_resource, respect = split_respect_gitignore(query_resource)
    if transport == 'uri':
        source = query_resource.partition('?')[2]
    respect = respect if respect is not None else peek(args, 'respect_gitignore', True)
    dispatch = ledger.dispatching(query_resource) if ledger is not None else nullcontext()
    try:
        with dispatch:
            source = prepare_declared_params(adapter.PARAM_SPECS, source, transport)
            select_type = getattr(adapter, 'result_type_for', None)
            expected_type = select_type(source) if select_type else adapter.RESULT_TYPE
            try:
                path = bind_resource_path(adapter.RESOURCE_SPEC, os.path.expanduser(path), transport=transport)
            except ValueError as exc:
                consume(_invalid_answer(adapter, name, path, str(exc), args, result_type=expected_type))
                return
            except OSError as exc:
                from ...utils.results import FailureCause
                consume(_invalid_answer(adapter, name, path, str(exc), args, FailureCause.ANALYSIS, result_type=expected_type))
                return
            try:
                root, excludes = dispatch_scope(path, peek(args, 'exclude'))
            except OSError as exc:
                from ...utils.results import FailureCause
                consume(_invalid_answer(adapter, name, path, str(exc), args, FailureCause.ANALYSIS,
                                        result_type=expected_type))
                return
            with exclusion_scope(root, excludes), gitignore_scope(respect):
                consume(_declared_answer(adapter, name, path, source, transport, args, expected_type))
            complete(args)
    finally:
        if ledger is not None and ledger.complete:
            ledger.report(name)


def _declared_answer(adapter_class, name: str, path: str, source: Any, transport: str, args, expected_type: str):
    from ...adapters.factory import _canonical_init
    from ...utils.query_binding import bind_prepared_params
    from ...utils.path_utils import to_posix
    from ...utils.results import FailureCause
    from .uri import _answer, _call_adapter, _renderer_class_of, _structure_answer
    try:
        params = bind_prepared_params(adapter_class.PARAM_SPECS, source, transport=transport)
        validate = getattr(adapter_class, 'validate_request', None)
        if validate is not None:
            validate(params, args)
        # stat distinguishes absence from inaccessible required work.
        Path(path).stat()
    except (FileNotFoundError, NotADirectoryError):
        return _invalid_answer(adapter_class, name, path, f'Path not found: {to_posix(path)}', args, result_type=expected_type)
    except ValueError as exc:
        return _invalid_answer(adapter_class, name, path, str(exc), args, result_type=expected_type)
    except OSError as exc:
        return _invalid_answer(adapter_class, name, path, str(exc), args, FailureCause.ANALYSIS, result_type=expected_type)

    def resolve():
        adapter = _call_adapter(lambda: _canonical_init(adapter_class, path, params=params),
                                name, path, adapter_class)
        return _structure_answer(adapter, _renderer_class_of(name), args, name, path,
                                 source_path=path, facts_of=adapter_class.execution_facts, expected_type=expected_type)

    return _answer(resolve, name, args, result_type=expected_type,
                   source_path=path, facts_of=adapter_class.execution_facts)


def _invalid_answer(adapter, name, path, message, args, cause=None, *, result_type=None):
    from ...reveal_types import CONTRACT_VERSION
    from ...utils.results import FailureCause, ResultBuilder, failure_execution_facts
    from .uri import Answer, _emit_result, _render_router_result
    cause = FailureCause.INVALID_REQUEST if cause is None else cause
    result = ResultBuilder.create(
        (result_type or adapter.RESULT_TYPE), path, contract_version=CONTRACT_VERSION,
        source_type='unknown', errors=[{'code': cause.value, 'message': message}], error=message)
    facts = failure_execution_facts(cause)
    answer = Answer(result, 'router', lambda *, announce_error=True: _emit_result(
        result, args, name, _render_router_result, execution_facts=facts, execution_answer=answer,
        announce_error=announce_error),
        execution_facts=facts, public_diagnostic=message)
    return answer


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


def emit_declared_result(result, args, scheme, render, facts, *, execution_answer=None, announce_error=True, **render_kwargs) -> None:
    """Finalize selected D6 facts; legacy emitters keep their existing policy."""
    from ...display.formatting import print_result_control_notes
    from ...rendering.base import emit_rendered
    from ...utils.json_utils import (attach_provenance, print_json_result, write_also_json,
                                     write_requested_artifact)
    from ...utils.results import (FailureCause, execution_exit_code,
                                 failure_execution_facts, merge_execution_facts)
    from .uri import announce_outcome
    policy = getattr(args, 'fail_on', None) or declared_adapter_class(scheme).DEFAULT_FAIL_ON
    result = attach_provenance(result)
    if announce_error:
        announce_outcome(result, f'{scheme}://')
    failure = write_requested_artifact(lambda: write_also_json(result, args), result)
    if failure is not None:
        facts = merge_execution_facts(facts, failure_execution_facts(FailureCause.OUTPUT))
        if execution_answer is not None:
            execution_answer.exception = failure
    code = execution_exit_code(facts, fail_on=policy)
    try:
        if args.format == 'json':
            print_json_result(result)
        else:
            emit_rendered(render, result, args.format, **render_kwargs)
        print_result_control_notes(result, args.format)
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
    required = RevealResult.__required_keys__
    valid = (isinstance(result, dict)
             and all(isinstance(result.get(key), str) and result[key] for key in required)
             and result.get('type') == expected_type
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
    meta = dict(meta) if isinstance(meta, dict) else {'warnings': []}
    meta['errors'] = [*_diagnostic_dicts(meta.get('errors')),
                      {'code': 'invalid_adapter_answer', 'message': error}]
    meta['warnings'] = _diagnostic_dicts(meta.get('warnings'))
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
    if not isinstance(meta, dict):
        return False
    return all(key not in meta or (isinstance(meta[key], list)
                                  and all(_valid_diagnostic(entry) for entry in meta[key]))
               for key in ('errors', 'warnings'))


def _valid_diagnostic(entry):
    return isinstance(entry, dict) and ('type' not in entry or isinstance(entry['type'], str))
