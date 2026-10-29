"""Ignored-input evidence belongs in the JSON answer, before MCP transports it."""
import json
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from reveal.main import main
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
        (f'sqlite://{resources / "data.db"}', '--depth', ('--depth', '4')),
    ):
        code, out, err = _cli(uri, '--format', 'json', *options)
        assert code == 0, (uri, err)
        answer = json.loads(out)
        assert len(_ignored(answer, field)) == 1, (uri, answer)
        assert not err, (uri, err)
        code, out, err = _cli(uri, '--format', 'text', *options)
        assert code == 0 and out
        assert field in err and ('ignored' in err or 'has no effect' in err)


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
