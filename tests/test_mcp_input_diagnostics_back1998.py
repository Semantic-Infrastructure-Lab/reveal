"""Ignored-input evidence belongs in the JSON answer, before MCP transports it."""
import json
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from reveal.main import main
from reveal.cli.defaults import _default_args
from reveal.cli.routing.ledger import FlagLedger
from reveal.utils.json_utils import print_json_result
from reveal.utils.query_parser import parse_query_params, warn_unknown_query_params
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]


@pytest.fixture
def resources(tmp_path):
    (tmp_path / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'object.json').write_text('{"value": 1}', encoding='utf-8')
    database = tmp_path / 'data.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE items (id INTEGER)')
    return tmp_path


def _cli(uri, *options):
    out, err = StringIO(), StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            main(['reveal', uri, *options])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _ignored(answer, field):
    warnings = answer.get('meta', {}).get('warnings', [])
    return [warning for warning in warnings
            if field in warning.get('fields', []) and warning.get('type') in
            ('unknown_query_param', 'unused_query_param', 'unused_flag')]


def test_cli_json_and_text_preserve_unknown_and_unused_inputs(resources):
    for uri, field, options in (
        (f'trace://{resources}?from=main&bogus=1', 'bogus', ()),
        (f'json://{resources / "object.json"}?bogus=1', 'bogus', ()),
        (f'sqlite://{resources / "data.db"}?bogus=1', 'bogus', ()),
        (f'sqlite://{resources / "data.db"}?limit=1', 'limit', ()),
        (f'sqlite://{resources / "data.db"}', '--depth', ('--depth', '4')),
    ):
        code, out, err = _cli(uri, '--format', 'json', *options)
        assert code == 0, (uri, err)
        answer = json.loads(out)
        assert len(_ignored(answer, field)) == 1, (uri, answer)
        assert field not in err and 'has no effect' not in err, (uri, err)
        code, out, err = _cli(uri, '--format', 'text', *options)
        assert code == 0 and out
        assert field in err and ('ignored' in err or 'has no effect' in err)


def test_json_writer_uses_live_accounting_without_mutation_or_context_leaks():
    ledger = FlagLedger(_default_args(format='json'))
    args = ledger.track(_default_args(format='json'))
    result = {'type': 'probe', 'meta': {'warnings': [{'type': 'existing', 'message': 'keep me'}]}}
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        with ledger.dispatching('probe?used=1&bogus=1&unread=1', 'probe'):
            params = parse_query_params('used=1&bogus=1&unread=1')
            params.get('used')
            warn_unknown_query_params(params, {'used', 'unread'}, adapter='probe')
            # The normal renderer chooses the format before calling the JSON writer.
            assert args.format == 'json'
            print_json_result(result)
        ledger.report('probe')
    answer = json.loads(out.getvalue())
    assert not err.getvalue()
    assert not _ignored(answer, 'used')
    assert len(_ignored(answer, 'bogus')) == len(_ignored(answer, 'unread')) == 1
    assert len(result['meta']['warnings']) == 1  # no mutation of the producer's answer
    clean = StringIO()
    print_json_result(result, file=clean)
    assert not _ignored(json.loads(clean.getvalue()), 'bogus')


def test_json_dispatch_without_shared_writer_keeps_deferred_warning_fallback():
    ledger = FlagLedger(_default_args(format='json'))
    err = StringIO()
    with redirect_stderr(err):
        with ledger.dispatching('probe?bogus=1', 'probe'):
            params = parse_query_params('bogus=1')
            warn_unknown_query_params(params, (), adapter='probe')
        ledger.report('probe')
    assert err.getvalue().count('Unknown query param') == 1


def test_text_primary_keeps_warning_and_json_artifact_has_the_same_fact(resources):
    artifact = resources / 'answer.json'
    code, out, err = _cli(f'sqlite://{resources / "data.db"}?bogus=1',
                          '--format', 'text', '--output', f'json={artifact}')
    assert code == 0 and out and 'bogus' in err
    assert len(_ignored(json.loads(artifact.read_text(encoding='utf-8')), 'bogus')) == 1


def test_nested_and_failed_dispatches_restore_outer_warning_context():
    outer = FlagLedger(_default_args(format='json'))
    inner = FlagLedger(_default_args(format='json'))
    with outer.dispatching('probe?outer=1', 'probe'):
        with pytest.raises(ValueError, match='stop'):
            with inner.dispatching('probe?inner=1', 'probe'):
                raise ValueError('stop')
        out = StringIO()
        print_json_result({'type': 'probe'}, file=out)
        answer = json.loads(out.getvalue())
        assert len(_ignored(answer, 'outer')) == 1
        assert not _ignored(answer, 'inner')
    out = StringIO()
    print_json_result({'type': 'probe'}, file=out)
    assert not _ignored(json.loads(out.getvalue()), 'outer')


def test_sdk_provenance_keeps_one_json_value_and_diagnostics_without_leaking(resources):
    async def scenario(session):
        for uri in (
            f'trace://{resources}?from=main&bogus=1',
            f'trace://{resources}?from=absent&bogus=1',
            f'json://{resources / "object.json"}?bogus=1',
            f'sqlite://{resources / "data.db"}?bogus=1',
        ):
            result = await session.call_tool('reveal_query', {'uri': uri, 'provenance': True})
            assert not result.is_error, _text(result)
            answer = json.loads(_text(result))
            assert len(_ignored(answer, 'bogus')) == 1, answer
            assert answer['execution']['command']
        # Text still discloses ignored input. A later clean JSON answer has no stale warning.
        text = await session.call_tool('reveal_query', {'uri': f'trace://{resources}?from=main&bogus=1'})
        assert not text.is_error and 'bogus' in _text(text)
        clean = await session.call_tool('reveal_query', {
            'uri': f'trace://{resources}?from=main', 'provenance': True})
        assert not clean.is_error
        assert not _ignored(json.loads(_text(clean)), 'bogus')
        sibling = await session.call_tool('reveal_trace', {'path': str(resources), 'entry_point': 'main'})
        assert not sibling.is_error and 'bogus' not in _text(sibling)

    _run(resources, scenario)
