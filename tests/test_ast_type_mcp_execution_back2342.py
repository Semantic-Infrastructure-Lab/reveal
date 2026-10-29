"""Type source loss and recovery cross the actual SDK request boundary."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]
SOURCE = 'def first(target: dict):\n    return target["key"]\n'


@pytest.mark.parametrize('provenance', [False, True])
def test_real_recovered_tree_absence_and_repair_through_stdio(tmp_path, provenance):
    path = tmp_path / 'app.py'
    path.write_text(SOURCE + '\ndef broken(:\n', encoding='utf-8')

    async def scenario(session):
        async def query(variable='target'):
            return await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?reveal_type={variable}',
                'provenance': provenance})

        for variable in ('target', 'absent'):
            recovered = await query(variable)
            assert not recovered.is_error
            assert 'incomplete' in _text(recovered).lower()
            if variable == 'target':
                assert 'first' in _text(recovered)
            if provenance:
                answer = json.loads(_text(recovered))
                assert answer['type'] == 'ast_reveal_type'
                assert 'confidence' not in answer['meta']
                assert bool(answer['results']) is (variable == 'target')
        path.write_text(SOURCE, encoding='utf-8')
        restored = await query()
        assert not restored.is_error and 'first' in _text(restored)
        assert 'incomplete' not in _text(restored).lower()
        path.write_text(SOURCE.replace('first', 'fresh'), encoding='utf-8')
        fresh = await query()
        assert not fresh.is_error and 'fresh' in _text(fresh)
        assert 'first' not in _text(fresh)
        absent = await query('absent')
        assert not absent.is_error and 'incomplete' not in _text(absent).lower()
        for control in ('name=absent', 'show=dict-heatmap', 'show=dict-schemas'):
            sibling = await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?{control}', 'provenance': provenance})
            assert not sibling.is_error and 'incomplete' not in _text(sibling).lower()
        for uri in (f'ast://{tmp_path.as_posix()}/missing?reveal_type=target',
                    f'ast://{tmp_path.as_posix()}?reveal_type=target&name~=['):
            invalid = await session.call_tool('reveal_query', {'uri': uri, 'provenance': provenance})
            assert invalid.is_error and _text(invalid).strip()

    _run(tmp_path, scenario)


@pytest.mark.parametrize('provenance', [False, True])
def test_actual_type_reader_loss_zero_survivor_and_restoration_through_stdio(tmp_path, provenance):
    path = tmp_path / 'blocked.py'
    path.write_text(SOURCE, encoding='utf-8')
    marker = tmp_path / 'deny-reader'
    marker.touch()
    code = '''
import builtins
from pathlib import Path
from reveal import mcp_server
original = builtins.open
def opened(file, *args, **kwargs):
    if isinstance(file, (str, Path)):
        path = Path(file)
        if path.name == 'blocked.py' and (path.parent / 'deny-reader').exists():
            (path.parent / 'reader-denied').touch()
            raise PermissionError('TYPE_READER_DENIED')
    return original(file, *args, **kwargs)
builtins.open = opened
mcp_server.main()
'''

    async def scenario(session):
        async def query():
            return await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?reveal_type=target',
                'provenance': provenance})

        failed = await query()
        assert (tmp_path / 'reader-denied').exists()
        assert failed.is_error, _text(failed)
        (tmp_path / 'healthy.py').write_text('VALUE = 1\n', encoding='utf-8')
        partial = await query()
        assert not partial.is_error and 'incomplete' in _text(partial).lower()
        if provenance:
            assert json.loads(_text(partial))['results'] == []
        marker.unlink()
        restored = await query()
        assert not restored.is_error and 'first' in _text(restored)
        assert 'incomplete' not in _text(restored).lower()
        path.write_text(SOURCE.replace('first', 'fresh'), encoding='utf-8')
        fresh = await query()
        assert not fresh.is_error and 'fresh' in _text(fresh)
        assert 'first' not in _text(fresh)

    _run(tmp_path, scenario, code)
