"""Actual SDK calls retain Surface diagnostics and transport without estimates."""
import json

import pytest

from test_mcp_declared_outcomes_back1994 import _SERVER
from test_mcp_expected_errors_back1992 import _run, _text
from test_surface_confidence_api_back2358 import _absent

pytestmark = [pytest.mark.mcp, pytest.mark.component]


@pytest.mark.parametrize('provenance', [False, True])
def test_surface_sdk_omission_partial_refusal_repair_and_output(tmp_path, provenance):
    for case in ('healthy', 'full', 'render_permission'):
        root = tmp_path / case
        (root / 'included').mkdir(parents=True)
        (root / 'included' / 'hidden.py').write_text('import os\nx=os.getenv("HIDDEN")\n', encoding='utf-8')
        (root / 'app.py').write_text('import os\nx=os.getenv("VISIBLE")\n' if case != 'full' else 'VALUE=1\n', encoding='utf-8')
    marker = tmp_path / 'deny-source'
    attempted = tmp_path / 'denial-attempted'
    injection = '''
import os
from reveal.adapters import surface
original_collect = surface._collect_source_files
original_scandir = os.scandir
active = False

def collect(*args, **kwargs):
    global active
    active = True
    try:
        return original_collect(*args, **kwargs)
    finally:
        active = False

def scandir(path):
    if active and Path(path).name == 'included' and Path(MARKER).exists():
        Path(ATTEMPTED).touch()
        raise PermissionError(13, 'SDK controlled Surface source denial', str(path))
    return original_scandir(path)

surface._collect_source_files = collect
os.scandir = scandir
'''.replace('MARKER', repr(str(marker))).replace('ATTEMPTED', repr(str(attempted)))
    server = _SERVER.replace('mcp_server.main()', injection + '\nmcp_server.main()')

    async def scenario(session):
        async def request(case='healthy', query='type=env'):
            return await session.call_tool('reveal_query', {
                'uri': f'surface://{(tmp_path / case).as_posix()}?{query}',
                'provenance': provenance})

        def inspect(response, expected_total):
            body = _text(response)
            if provenance:
                answer, end = json.JSONDecoder().raw_decode(body)
                suffix = body[end:]
                if suffix.strip():
                    assert '[stderr' in suffix
                    assert 'incomplete' in suffix.lower() or 'directory' in suffix.lower()
                _absent(answer)
                assert answer['total'] == expected_total
                return answer
            assert 'confidence' not in body.lower()
            return None

        healthy = await request()
        assert not healthy.is_error and 'VISIBLE' in _text(healthy)
        inspect(healthy, 2)
        marker.touch()
        partial = await request()
        assert attempted.exists()
        assert not partial.is_error and 'VISIBLE' in _text(partial)
        assert 'incomplete' in _text(partial).lower()
        answer = inspect(partial, 1)
        if answer:
            assert any(w.get('unit') == 'directories' for w in answer['meta']['warnings'])
        refused = await request('full')
        assert refused.is_error and _text(refused).strip()
        marker.unlink()
        repaired = await request()
        assert not repaired.is_error and 'incomplete' not in _text(repaired).lower()
        inspect(repaired, 2)
        source = tmp_path / 'healthy' / 'app.py'
        source.write_text(source.read_text(encoding='utf-8').replace('VISIBLE', 'FRESH'), encoding='utf-8')
        fresh = await request()
        assert not fresh.is_error and 'FRESH' in _text(fresh) and 'VISIBLE' not in _text(fresh)
        inspect(fresh, 2)
        broken = tmp_path / 'healthy' / 'broken.py'
        broken.write_text('def broken(:\n', encoding='utf-8')
        parsed = await request()
        assert not parsed.is_error and 'incomplete' in _text(parsed).lower()
        inspect(parsed, 2)
        broken.unlink()
        failed = await request('render_permission')
        assert failed.is_error and 'PUBLIC_RENDER_PERMISSION' in _text(failed)
        sibling = await session.call_tool('reveal_query', {
            'uri': f'ast://{(tmp_path / "healthy").as_posix()}?name=absent', 'provenance': provenance})
        assert not sibling.is_error
        if provenance:
            assert json.loads(_text(sibling))['meta']['confidence'] == 1.0

    _run(tmp_path, scenario, server)
