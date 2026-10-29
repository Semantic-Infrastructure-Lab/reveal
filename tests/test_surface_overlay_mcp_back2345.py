"""Surface URI and output contracts survive API call admission adoption."""
import json

import pytest

from reveal import api
from test_mcp_declared_outcomes_back1994 import _SERVER
from test_mcp_expected_errors_back1992 import _run, _text

pytestmark = [pytest.mark.mcp, pytest.mark.component]


@pytest.mark.parametrize('provenance', [False, True])
def test_surface_uri_budget_partial_repair_and_ast_siblings_through_stdio(tmp_path, provenance):
    root = tmp_path / 'project'
    root.mkdir()
    source = root / 'app.py'
    source.write_text('import os\ndef first(cfg: dict):\n    return os.getenv("PRODUCTION_VAR")\n', encoding='utf-8')
    tests = root / 'tests'
    tests.mkdir()
    (tests / 'test_app.py').write_text('import os\nx=os.getenv("TEST_VAR")\n', encoding='utf-8')
    output_failure = tmp_path / 'render_permission'
    output_failure.mkdir()
    (output_failure / 'app.py').write_text('import os\nx=os.getenv("OUTPUT_VAR")\n', encoding='utf-8')

    async def scenario(session):
        async def query(query_string, path=root):
            return await session.call_tool('reveal_query', {
                'uri': f'surface://{path.as_posix()}?{query_string}', 'provenance': provenance})

        filtered = await query('type=env&source_only=true')
        assert not filtered.is_error and 'PRODUCTION_VAR' in _text(filtered)
        assert 'TEST_VAR' not in _text(filtered)
        if provenance:
            answer = json.loads(_text(filtered))
            expected = api.query(f'surface://{root.as_posix()}?type=env&source_only=true')
            assert answer['type'] == 'surface_scan'
            assert answer['surfaces'] == expected['surfaces']
            assert answer['total'] == expected['total'] == 1
        budget = await query('type=env&top=0')
        assert not budget.is_error
        if provenance:
            answer = json.loads(_text(budget))
            assert answer['type'] == 'surface_scan' and answer['total'] == 2
            assert len(answer['surfaces']['env']) == 2
        else:
            assert 'Showing top 0' in _text(budget) and '2 more' in _text(budget)
            assert 'PRODUCTION_VAR' not in _text(budget) and 'TEST_VAR' not in _text(budget)
        for path, query_string in ((root / 'absent', 'type=env'), (root, 'depth=-1')):
            failed = await query(query_string, path)
            assert failed.is_error and _text(failed).strip()
        broken = root / 'broken.py'
        broken.write_text('def broken(:\n', encoding='utf-8')
        partial = await query('type=env')
        assert not partial.is_error and 'PRODUCTION_VAR' in _text(partial)
        assert 'incomplete' in _text(partial).lower()
        if provenance:
            assert json.loads(_text(partial))['unparsed_files']
        broken.unlink()
        source.write_text(source.read_text(encoding='utf-8').replace('PRODUCTION_VAR', 'FRESH_VAR'), encoding='utf-8')
        fresh = await query('type=env&source_only=true')
        assert not fresh.is_error and 'FRESH_VAR' in _text(fresh)
        assert 'PRODUCTION_VAR' not in _text(fresh) and 'incomplete' not in _text(fresh).lower()
        failed_output = await query('type=env', output_failure)
        assert failed_output.is_error and 'PUBLIC_RENDER_PERMISSION' in _text(failed_output)
        for query_string in ('name=absent', 'show=dict-heatmap', 'show=dict-schemas', 'reveal_type=cfg'):
            sibling = await session.call_tool('reveal_query', {
                'uri': f'ast://{root.as_posix()}?{query_string}', 'provenance': provenance})
            assert not sibling.is_error and 'incomplete' not in _text(sibling).lower()

    _run(tmp_path, scenario, _SERVER)
