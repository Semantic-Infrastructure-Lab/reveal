"""Deterministic shared-seam probes used by self-validation and CI (BACK-1660).

No network, subprocesses, user files, or test-package imports. A probe returns
violations; exceptions propagate so the runner reports unavailable checks.
"""

from contextlib import contextmanager, redirect_stdout, redirect_stderr
from io import StringIO
import json
import logging

from reveal.reveal_types import WarningEntry


def builder_violations():
    """Verify envelope protection and preservation of supplied diagnostics."""
    from reveal.utils.results import ResultBuilder, _CONTRACT_FIELDS
    failures = []
    for field in sorted(_CONTRACT_FIELDS):
        try:
            ResultBuilder.create('probe', 'probe', data={field: 'overwritten'})
        except ValueError:
            continue
        failures.append(f'ResultBuilder permits data to overwrite {field}')
    warning: WarningEntry = {'code': 'W_PROBE', 'message': 'recorded builder warning'}
    result = ResultBuilder.create('probe', 'probe', warnings=[warning])
    if warning not in result.get('meta', {}).get('warnings', []):
        failures.append('ResultBuilder silently loses supplied warnings')
    result = ResultBuilder.create('probe', 'probe', errors=[warning], confidence=0.0, parse_mode='regex')
    for key, value in (('errors', [warning]), ('confidence', 0.0), ('parse_mode', 'regex')):
        if result.get('meta', {}).get(key) != value:
            failures.append(f'ResultBuilder silently loses supplied {key}')
    return failures


@contextmanager
def _quiet_recorded_failures():
    """Suppress only our expected synthetic child-failure logs, not real failures."""
    logger = logging.getLogger('reveal.adapters.base')
    class ProbeFilter(logging.Filter):
        def filter(self, record):
            return not (isinstance(record.args, tuple) and record.args
                        and record.args[0] == '_SelfCheckChild')
    probe_filter = ProbeFilter()
    logger.addFilter(probe_filter)
    try:
        yield
    finally:
        logger.removeFilter(probe_filter)


def composition_violations():
    """Returned and raised failures must survive folding and consume once."""
    from reveal.adapters.base import ResourceAdapter
    from reveal.reveal_types import CONTRACT_VERSION
    from reveal.utils.results import ResultBuilder

    class _SelfCheckChild(ResourceAdapter):
        def get_structure(self, **kwargs):
            if self.resource == 'raised':
                raise ValueError('recorded child failure')
            if self.resource == 'returned':
                return ResultBuilder.create_error('probe', 'probe', 'recorded child failure')
            return ResultBuilder.create('probe', 'probe', confidence=1.0,
                                        contract_version=CONTRACT_VERSION)

    failures = []
    for mode in ('returned', 'raised'):
        parent = _SelfCheckChild()
        with _quiet_recorded_failures():
            parent.compose(_SelfCheckChild, 'success')
            parent.compose(_SelfCheckChild, mode, default={})
        meta = parent.composed_meta() or {}
        if not meta.get('errors'):
            failures.append(f'Composition hides {mode} child failure')
        if meta.get('confidence', 1.0) >= 1.0:
            failures.append(f'Composition reports full confidence after {mode} failure')
        if parent.composed_meta() is not None:
            failures.append('Composition repeats consumed diagnostics')
    return failures


def pagination_violations():
    """Bad controls reject explicitly; zero and ordinary slicing remain valid."""
    from reveal.utils.query_control import parse_result_control, apply_result_control
    failures = []
    for key in ('limit', 'offset'):
        for raw in ('abc', '-1', ''):
            try:
                parse_result_control(f'{key}={raw}')
            except ValueError:
                continue
            failures.append(f'Pagination silently accepts {key}={raw}')
    for query, expected in (('limit=0', []), ('offset=1&limit=1', [{'value': 2}]),
                            ('offset=10', [])):
        remaining, control = parse_result_control('name=probe&' + query)
        if remaining != 'name=probe' or apply_result_control([{'value': 1}, {'value': 2}, {'value': 3}], control) != expected:
            failures.append(f'Pagination mishandles {query}')
    return failures


def renderer_violations(renderer=None):
    """Recorded offline stats fixture: warning, partial error, cut, failed result.

    Exercises a registered renderer plus the URI outcome seam. This is a
    bounded canary, not a claim that every renderer has been fixture-tested.
    """
    from reveal.adapters.base import get_renderer_class
    from reveal.cli.routing.uri import announce_outcome, conclude_outcome
    from reveal.reveal_types import CONTRACT_VERSION
    from reveal.utils.results import ResultBuilder, note_truncation
    renderer = renderer or get_renderer_class('stats')
    if renderer is None:
        raise RuntimeError('Registered stats renderer unavailable for recorded fixture')
    result = ResultBuilder.create('stats_file', 'probe', data={'file': 'probe'},
        contract_version=CONTRACT_VERSION,
        warnings=[{'code': 'W_PROBE', 'message': 'recorded renderer warning'}],
        errors=[{'code': 'E_PROBE', 'message': 'recorded partial error'}])
    note_truncation(result, 'files', 1, 2, '--all')
    failures = []
    text, err = StringIO(), StringIO()
    with redirect_stdout(text), redirect_stderr(err):
        outcome = announce_outcome(result, 'probe')
        renderer.render_structure(result, 'text')
        conclude_outcome(result, outcome, 'text')
    for message in ('recorded renderer warning', 'recorded partial error', 'Truncated files:'):
        if (text.getvalue() + err.getvalue()).count(message) != 1:
            failures.append(f'Renderer hides or duplicates {message}')
    output = StringIO()
    with redirect_stdout(output):
        renderer.render_structure(result, 'json')
        conclude_outcome(result, outcome, 'json')
    if json.loads(output.getvalue()) != result:
        failures.append('Renderer JSON changes recorded diagnostics')
    failed = ResultBuilder.create_error('stats_file', 'probe', 'recorded fatal error')
    output, err = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(err):
        outcome = announce_outcome(failed, 'probe')
        renderer.render_structure(failed, 'text')
        try:
            conclude_outcome(failed, outcome, 'text')
        except SystemExit as exc:
            if exc.code != 1:
                failures.append('Failed render exits with a code other than 1')
        else:
            failures.append('Failed render exits successfully')
    if (output.getvalue() + err.getvalue()).count('recorded fatal error') != 1:
        failures.append('Renderer hides or duplicates fatal error')
    return failures
