"""Trace URI evidence and composition remain honest at the actual SDK boundary."""
import json
from pathlib import Path

import pytest

from reveal import api
from test_mcp_expected_errors_back1992 import _run, _text
from test_trace_api_overlay_back2349 import SOURCE

pytestmark = [pytest.mark.mcp, pytest.mark.component]
_SERVER = '''
import builtins
from pathlib import Path
from reveal import mcp_server
from reveal.adapters.trace import TraceRenderer
from reveal.utils import json_utils
opened = builtins.open

def read(file, *args, **kwargs):
    if isinstance(file, (str, Path)):
        path = Path(file)
        if path.parent.name == 'project' and path.suffix == '.py':
            root = path.parent.parent
            if (root / 'deny-all').exists() or (path.name.startswith('bad') and (root / 'deny-bad').exists()):
                (root / 'reader-denied').touch()
                raise PermissionError('TRACE_SOURCE_READER_DENIED')
    return opened(file, *args, **kwargs)

builtins.open = read
render = TraceRenderer.render_structure
json_render = json_utils.print_json_result

def rendered(result, *args, **kwargs):
    if Path(result.get('path', '')).name == 'output_failure':
        raise PermissionError('TRACE_OUTPUT_DENIED')
    return render(result, *args, **kwargs)

def json_rendered(result, *args, **kwargs):
    if Path(result.get('path', '')).name == 'output_failure':
        raise PermissionError('TRACE_OUTPUT_DENIED')
    return json_render(result, *args, **kwargs)

TraceRenderer.render_structure = staticmethod(rendered)
json_utils.print_json_result = json_rendered
mcp_server.main()
'''


@pytest.mark.parametrize('provenance', [False, True])
def test_trace_depth_absence_actual_source_loss_recovery_and_siblings_through_stdio(tmp_path, provenance):
    root = tmp_path / 'project'
    root.mkdir()
    source = root / 'app.py'
    source.write_text(SOURCE, encoding='utf-8')
    for number in range(7):
        (root / f'bad{number}.py').write_text(f'def hidden{number}(): return {number}\n', encoding='utf-8')
    output = tmp_path / 'output_failure'
    output.mkdir()
    (output / 'app.py').write_text(SOURCE, encoding='utf-8')
    recovered = tmp_path / 'recovered'
    recovered.mkdir()
    (recovered / 'app.ts').write_text(
        'export function main() { const x = ; helper(); }\nexport function helper() { return 1; }\n', encoding='utf-8')

    async def scenario(session):
        async def query(query_string='from=main', path=root):
            return await session.call_tool('reveal_query', {
                'uri': f'trace://{path.as_posix()}?{query_string}', 'provenance': provenance})
        for depth in (1, 3):
            answer = await query(f'from=main&depth={depth}')
            assert not answer.is_error
            if provenance:
                data = json.loads(_text(answer))
                assert data['type'] == 'trace' and data['depth'] == depth
                assert data['frames'] == api.query(f'trace://{root.as_posix()}?from=main&depth={depth}')['frames']
            else:
                assert f'depth {depth}' in _text(answer)
                assert ('third' in _text(answer)) is (depth == 3)
        absent = await query('from=absent')
        assert not absent.is_error and 'absent' in _text(absent)
        assert 'incomplete' not in _text(absent).lower()
        marker = tmp_path / 'deny-bad'
        marker.touch()
        partial = await query()
        assert (tmp_path / 'reader-denied').exists()
        assert not partial.is_error and 'main' in _text(partial)
        assert 'incomplete' in _text(partial).lower()
        if provenance:
            text = _text(partial)
            data, end = json.JSONDecoder().raw_decode(text)
            warnings = data['meta']['warnings']
            # The answer is one block, the CLI's JSON exactly: the reader failures it states are not
            # also printed beside it (BACK-2659), and the replaced-by note is in its meta.warnings,
            # not appended as text (BACK-2650).
            assert len(partial.content) == 1 and json.loads(partial.content[0].text) == data
            assert text[end:].strip() == ''
            assert '[note:' not in text
            assert any(w.get('code') == 'retired_spelling' and 'trace://' in w['message'] for w in warnings)
            loss = [entry for entry in warnings if entry.get('type') == 'analysis_failed']
            assert len(loss) == 1 and loss[0]['count'] == 7 and len(loss[0]['files']) == 5
            assert '(PermissionError)' in loss[0]['message']  # the cause, by class
            # Every failed file and its full reason, past the five the message names (BACK-2659, D8).
            failures = loss[0]['failures']
            assert sorted(Path(f['path']).name for f in failures) == [f'bad{n}.py' for n in range(7)]
            assert {(f['cause'], f['reason']) for f in failures} == {
                ('PermissionError', 'PermissionError: TRACE_SOURCE_READER_DENIED')}
        marker.unlink()
        (tmp_path / 'reader-denied').unlink()
        marker = tmp_path / 'deny-all'
        marker.touch()
        failed = await query()
        assert (tmp_path / 'reader-denied').exists()
        assert failed.is_error and _text(failed).strip()
        marker.unlink()
        source.write_text(SOURCE.replace('first', 'fresh'), encoding='utf-8')
        fresh = await query()
        assert not fresh.is_error and 'fresh' in _text(fresh)
        assert 'first' not in _text(fresh) and 'incomplete' not in _text(fresh).lower()
        recovery = await query(path=recovered)
        assert not recovery.is_error and 'helper' in _text(recovery)
        assert 'incomplete' in _text(recovery).lower()
        if provenance:
            assert any(entry['type'] == 'parse_recovered' for entry in json.loads(_text(recovery))['meta']['warnings'])
        for path, query_string in ((root / 'missing', 'from=main'), (root, 'from=main&depth=1.5'),
                                   (output, 'from=main')):
            failure = await query(query_string, path)
            assert failure.is_error and _text(failure).strip()
        for scheme, query_string in (('surface', 'type=env&top=0'), ('contracts', 'impls=0'),
                                     ('ast', 'name=absent'), ('ast', 'show=dict-heatmap'),
                                     ('ast', 'show=dict-schemas')):
            sibling = await session.call_tool('reveal_query', {
                'uri': f'{scheme}://{root.as_posix()}?{query_string}', 'provenance': provenance})
            assert not sibling.is_error and 'incomplete' not in _text(sibling).lower()
        # a variable a complete search finds nowhere is rule 9's usage error, never lost evidence (BACK-2613 Q6)
        absent = await session.call_tool('reveal_query', {
            'uri': f'ast://{root.as_posix()}?reveal_type=absent', 'provenance': provenance})
        assert absent.is_error and 'incomplete' not in _text(absent).lower()

    _run(tmp_path, scenario, _SERVER)
