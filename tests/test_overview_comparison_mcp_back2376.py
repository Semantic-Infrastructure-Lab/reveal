"""Comparison qualification through the registered SDK stdio transport."""

import json
from urllib.parse import quote

import pytest

pytest.importorskip('mcp')

from test_mcp_expected_errors_back1992 import _run, _text  # noqa: E402
from test_overview_comparison_back2376 import (  # noqa: E402
    invoke, make_repository, same_answer, source,
)

pytestmark = [pytest.mark.mcp, pytest.mark.component]


def uri(root, noun='overview', query='against=HEAD'):
    return f'{noun}://{quote(root.as_posix(), safe="/.:")}?{query}'


@pytest.mark.parametrize('provenance', [False, True])
def test_registered_overview_comparison_matches_cli_and_live_edits(tmp_path, provenance):
    root = make_repository(tmp_path / 'project space & percent%')

    async def scenario(session):
        async def query(parameters='against=HEAD'):
            return await session.call_tool('reveal_query', {
                'uri': uri(root, query=parameters), 'provenance': provenance})

        identical = await query()
        assert not identical.is_error, _text(identical)
        if provenance:
            body = json.loads(_text(identical))
            assert body['type'] == 'overview_diff'
            assert body['analysis'] == {'complete': True, 'basis': 'identical_tree', 'snapshots': {}}
            assert body['deltas']['complexity_centroid'] == {
                'base': None, 'head': None, 'change': 0.0, 'top_n': 20}
        else:
            assert 'neither snapshot was analyzed' in _text(identical)

        (root / 'app.py').write_text(source(23), encoding='utf-8')
        changed = await query()
        assert not changed.is_error, _text(changed)
        flags = ['--provenance'] if provenance else []
        cli = invoke(root, flags=flags, format='json' if provenance else 'text')
        assert cli.returncode == 0, cli.stderr
        if provenance:
            body = json.loads(_text(changed))
            same_answer(json.loads(cli.stdout), body)
            assert body['head_ref'] == 'working tree'
            assert body['deltas']['complexity_centroid'] == {
                'base': 13.0, 'head': 23.0, 'change': 10.0, 'top_n': 20}
            zero = await query('against=HEAD&top=0')
            assert not zero.is_error
            assert json.loads(_text(zero))['deltas']['complexity_centroid']['top_n'] == 4
            encoded = await query('against=' + quote('base+%26=é', safe=''))
            assert not encoded.is_error
            assert json.loads(_text(encoded))['base_ref'] == 'base+%26=é'
        else:
            assert _text(changed) == cli.stdout.rstrip('\n') or _text(changed) == cli.stdout

        for query_text in ('against=missing-ref', 'against=', 'against',
                           'against=HEAD&no_imports=false', 'against=HEAD&all=true',
                           'against=HEAD&verbose=false'):
            rejected = await query(query_text)
            assert rejected.is_error and _text(rejected).strip(), query_text
        (root / 'app.py').write_text('def broken(\n', encoding='utf-8')
        lost = await query()
        assert lost.is_error and _text(lost).strip()
        (root / 'app.py').write_text(source(23), encoding='utf-8')
        repaired = await query()
        assert not repaired.is_error, _text(repaired)
        ordinary = await session.call_tool('reveal_query', {
            'uri': 'overview://' + quote(root.as_posix(), safe='/.:'), 'provenance': True})
        assert not ordinary.is_error
        assert json.loads(_text(ordinary))['type'] == 'overview'

    _run(tmp_path, scenario)


_CORRUPTING_SERVER = '''
from copy import deepcopy
from pathlib import Path
from reveal import mcp_server
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.overview import OverviewAdapter

def wrap(original):
    def project(self, result, args):
        result = original(self, result, args)
        if result.get('type') not in ('architecture_diff', 'overview_diff'):
            return result
        result = deepcopy(result)
        kind = Path(self.path).name
        if kind == 'drop-basis':
            result['analysis'].pop('basis')
        elif kind == 'drop-side':
            result['analysis']['snapshots'].pop('head')
        elif kind == 'contradictory':
            result['analysis']['snapshots']['head']['complexity'] = 'incomplete'
        return result
    return project

ArchitectureAdapter.post_process = wrap(ArchitectureAdapter.post_process)
OverviewAdapter.post_process = wrap(OverviewAdapter.post_process)
mcp_server.main()
'''


@pytest.mark.parametrize('provenance', [False, True])
@pytest.mark.parametrize('noun', ['architecture', 'overview'])
def test_registered_comparison_proof_corruption_is_tool_error(tmp_path, provenance, noun):
    roots = {}
    for kind in ('healthy', 'drop-basis', 'drop-side', 'contradictory'):
        roots[kind] = make_repository(tmp_path / kind)
        (roots[kind] / 'app.py').write_text(source(23), encoding='utf-8')

    async def scenario(session):
        for kind, root in roots.items():
            answer = await session.call_tool('reveal_query', {
                'uri': uri(root, noun), 'provenance': provenance})
            assert answer.is_error is (kind != 'healthy'), (kind, _text(answer))
            assert _text(answer).strip()
        # Failure in one target must not poison the ordinary-map sibling.
        healthy = await session.call_tool('reveal_query', {
            'uri': 'overview://' + roots['healthy'].as_posix(), 'provenance': True})
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['type'] == 'overview'

    _run(tmp_path, scenario, code=_CORRUPTING_SERVER)
