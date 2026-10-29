"""Required dict source evidence survives the real SDK stdio boundary."""
import json

import pytest

from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]
MODES = ('dict-heatmap', 'dict-schemas')
SOURCE = ('def first(cfg):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n'
          'def second(cfg):\n    return cfg["a"] + cfg["b"] + cfg["c"]\n')


@pytest.mark.parametrize('provenance', [False, True])
def test_real_parse_loss_survivors_and_repair_through_stdio(tmp_path, provenance):
    broken = tmp_path / 'broken.py'
    broken.write_text(SOURCE + 'def invalid(:\n', encoding='utf-8')

    async def scenario(session):
        async def query(mode):
            return await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?show={mode}', 'provenance': provenance})

        for mode in MODES:
            failed = await query(mode)
            assert failed.is_error, _text(failed)
        # Successfully parsed source makes this partial even without domain observations.
        healthy = tmp_path / 'healthy.py'
        healthy.write_text('VALUE = 1\n', encoding='utf-8')
        for mode in MODES:
            partial = await query(mode)
            assert not partial.is_error
            assert 'incomplete' in _text(partial).lower()
            if provenance:
                answer = json.loads(_text(partial))
                assert answer['type'] == 'ast_' + mode.replace('-', '_')
                assert answer['results'] == []
        healthy.write_text(SOURCE, encoding='utf-8')
        for mode in MODES:
            partial = await query(mode)
            assert not partial.is_error
            assert 'first' in _text(partial) and 'incomplete' in _text(partial).lower()
        broken.unlink()
        for mode in MODES:
            repaired = await query(mode)
            assert not repaired.is_error
            assert 'first' in _text(repaired)
            assert 'incomplete' not in _text(repaired).lower()
        healthy.write_text(SOURCE.replace('first', 'fresh'), encoding='utf-8')
        for mode in MODES:
            fresh = await query(mode)
            assert not fresh.is_error and 'fresh' in _text(fresh)
            assert 'first' not in _text(fresh)
        healthy.write_text('VALUE = 1\n', encoding='utf-8')
        for query_string in ('show=dict-heatmap', 'show=dict-schemas', 'reveal_type=absent', 'name=absent'):
            empty = await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?{query_string}', 'provenance': provenance})
            assert not empty.is_error
            assert 'incomplete' not in _text(empty).lower()

    _run(tmp_path, scenario)


@pytest.mark.parametrize('provenance', [False, True])
def test_actual_dict_reader_denial_and_restoration_through_stdio(tmp_path, provenance):
    blocked = tmp_path / 'blocked.py'
    blocked.write_text(SOURCE, encoding='utf-8')
    marker = tmp_path / 'deny-reader'
    marker.touch()
    code = '''
import io
from pathlib import Path
from reveal import mcp_server
original = io.open
def opened(file, *args, **kwargs):
    if isinstance(file, (str, Path)):
        path = Path(file)
        if path.name == 'blocked.py' and (path.parent / 'deny-reader').exists():
            (path.parent / 'reader-denied').touch()
            raise PermissionError('DICT_READER_DENIED')
    return original(file, *args, **kwargs)
io.open = opened
mcp_server.main()
'''

    async def scenario(session):
        for mode in MODES:
            failed = await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?show={mode}', 'provenance': provenance})
            assert (tmp_path / 'reader-denied').exists()
            assert failed.is_error, _text(failed)
        marker.unlink()
        for mode in MODES:
            restored = await session.call_tool('reveal_query', {
                'uri': f'ast://{tmp_path.as_posix()}?show={mode}', 'provenance': provenance})
            assert not restored.is_error and 'first' in _text(restored)
            assert 'incomplete' not in _text(restored).lower()

    _run(tmp_path, scenario, code)
