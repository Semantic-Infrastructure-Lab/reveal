"""Declared consumers classify real required discovery loss before presentation."""

import builtins
import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.architecture import ArchitectureAdapter
from reveal.adapters.deps import DepsAdapter
from reveal.adapters.overview import OverviewAdapter
from reveal.analyzers.imports import file_index


OWNERS = {'deps': DepsAdapter, 'architecture': ArchitectureAdapter, 'overview': OverviewAdapter}


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def complex_source():
    return ('def observed(value):\n' + ''.join(
        f'    if value == {n}:\n        return {n}\n' for n in range(11)) + '    return -1\n')


def tree(root, kind):
    child = root / 'included_child'
    write(child / 'hidden.py', 'import decimal\n' + complex_source())
    if kind == 'import':
        write(root / 'visible.py', 'import math\n')
    elif kind == 'edge':
        write(root / 'visible.py', 'from stable import VALUE\n')
        write(root / 'stable.py', 'VALUE = 1\n')
    elif kind == 'ast':
        write(root / 'visible.py', complex_source())
    elif kind == 'zero':
        write(root / 'visible.py', 'VALUE = 1\n')
    elif kind == 'broken':
        write(root / 'visible.py', 'def broken(\n')
    elif kind == 'recovered':
        write(root / 'visible.py', 'import decimal\ndef broken(\n')
    elif kind == 'target':
        (child / 'hidden.py').unlink()
        write(root / 'visible.c', '#include "hidden.inc"\nint main(void) { return 0; }\n')
        write(child / 'deep' / 'hidden.inc', 'int helper(void);\n')
    return child


@contextmanager
def denied(child, *, imports_only=False):
    """Fail actual scandir; optionally isolate the Imports walk from Stats/AST."""
    real_scandir, real_walk = os.scandir, file_index.walk_with_causes
    active = [False]

    def walk(*args, **kwargs):
        active[0] = True
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active[0] = False

    def scandir(directory):
        if (not imports_only or active[0]) and Path(directory).resolve() == child.resolve():
            raise PermissionError(13, 'controlled required directory loss', str(child))
        return real_scandir(directory)

    with patch.object(file_index, 'walk_with_causes', walk), patch('os.scandir', scandir):
        yield


def request(name, root, query=''):
    query = '&'.join(part for part in (query, 'no_git=true' if name == 'overview' else '') if part)
    owner = OWNERS[name](str(root), query)
    result = owner.get_structure()
    return result, owner.execution_facts(result).completeness.value


def uri(name, root, query=''):
    query = '&'.join(part for part in (query, 'no_git=true' if name == 'overview' else '') if part)
    return f'{name}://{root}' + ('?' + query if query else '')


@pytest.mark.parametrize('name,kind,expected', [
    ('deps', 'import', 'incomplete'), ('deps', 'edge', 'incomplete'),
    ('deps', 'target', 'incomplete'), ('deps', 'recovered', 'incomplete'),
    ('deps', 'zero', 'failed'), ('deps', 'broken', 'failed'), ('deps', 'lost', 'failed'),
    ('architecture', 'edge', 'incomplete'), ('architecture', 'ast', 'incomplete'),
    ('architecture', 'import', 'failed'), ('architecture', 'zero', 'failed'),
    ('architecture', 'broken', 'failed'), ('architecture', 'lost', 'failed'),
    ('overview', 'zero', 'incomplete'), ('overview', 'broken', 'incomplete'),
    ('overview', 'lost', 'failed'),
])
def test_actual_observations_determine_directory_loss_outcome(tmp_path, name, kind, expected):
    child = tree(tmp_path, kind)
    with denied(child):
        result, state = request(name, tmp_path)
    assert any(w.get('type') == 'analysis_incomplete' for w in result['meta']['warnings'])
    assert state == expected


@pytest.mark.parametrize('name', OWNERS)
def test_imports_only_loss_preserves_independent_requested_observations(tmp_path, name):
    child = tree(tmp_path, 'edge' if name != 'overview' else 'lost')
    with denied(child, imports_only=True):
        _, state = request(name, tmp_path)
    assert state == 'incomplete'


@pytest.mark.parametrize('name', ['architecture', 'overview'])
def test_top_zero_retains_uncapped_real_ast_observation(tmp_path, name):
    from reveal.adapters.ast import AstAdapter
    child = tree(tmp_path, 'ast')
    with denied(child):
        ast = AstAdapter(str(tmp_path), 'complexity>9&limit=0').get_structure()
        assert ast['total_results'] == 1 and ast['displayed_results'] == 0
        result, state = request(name, tmp_path, 'top=0')
    assert state == 'incomplete'
    if name == 'overview':
        assert result['complex_functions'] == []


@pytest.mark.parametrize('kind', ['boolean_count', 'count_mismatch', 'bad_complexity'])
@pytest.mark.parametrize('surviving_edge', [False, True])
def test_malformed_ast_cannot_rescue_directory_loss(tmp_path, kind, surviving_edge):
    from reveal.adapters.ast import AstAdapter
    child = tree(tmp_path, 'edge' if surviving_edge else 'lost')
    data = {'results': [], 'total_files': 0, 'total_results': 1, 'displayed_results': 0}
    if kind == 'boolean_count':
        data['total_results'] = True
    elif kind == 'count_mismatch':
        data['displayed_results'] = 1
    else:
        data.update(displayed_results=1,
                    results=[{'file': 'invented.py', 'name': 'f', 'complexity': True}])
    with denied(child), patch.object(AstAdapter, 'get_structure', return_value=data):
        _, state = request('architecture', tmp_path)
    assert state == 'failed'


@pytest.mark.parametrize('name', OWNERS)
def test_loss_cli_uri_exit_and_provenance_agree(tmp_path, name):
    child = tree(tmp_path, 'edge')
    flags = ['--no-git'] if name == 'overview' else []
    with denied(child):
        cli = run(name, tmp_path, *flags, '--format', 'json', '--provenance')
        resource = run(uri(name, tmp_path), '--format', 'json', '--provenance')
    assert cli.returncode == resource.returncode == 3
    left, right = json.loads(cli.stdout), json.loads(resource.stdout)
    # command differs by spelling; repo.dirty reads the process checkout, which other workers write to (BACK-2059)
    for side in (left, right):
        side['execution'].pop('command')
        side['execution'].pop('repo')
    assert left == right


@pytest.mark.parametrize('name', OWNERS)
def test_all_lost_decorated_mcp_suppresses_failed_answer(tmp_path, name):
    from reveal import mcp_server
    child = tree(tmp_path, 'lost')
    with denied(child):
        answer = mcp_server.reveal_query(uri(name, tmp_path), provenance=True)
    assert isinstance(answer, mcp_server._ToolFailure)


def test_deps_summary_projection_cannot_erase_or_manufacture_observations(tmp_path):
    child = tree(tmp_path, 'import')
    with denied(child):
        response = run(uri('deps', tmp_path, 'top=0&summary_only=true&no_unused=true&no_circular=true'),
                       '--format', 'json', '--fields', 'analysis', '--provenance')
    assert response.returncode == 3
    payload = json.loads(response.stdout)
    assert set(payload['analysis']['components']) == {'base'}
    assert payload['analysis']['components']['base']['completeness'] == 'incomplete'


@pytest.mark.parametrize('name', ['architecture', 'overview'])
def test_no_imports_skips_unrequested_loss(tmp_path, name):
    child = tree(tmp_path, 'lost')
    with denied(child, imports_only=True):
        _, state = request(name, tmp_path, 'no_imports=true')
    assert state == 'complete'


@pytest.mark.parametrize('name', OWNERS)
def test_repaired_same_owner_and_exact_sibling_are_clean(tmp_path, name):
    root, sibling = tmp_path / 'affected', tmp_path / 'sibling'
    child = tree(root, 'edge')
    write(sibling / 'healthy.py', 'import os\n')
    query = 'no_git=true' if name == 'overview' else ''
    owner = OWNERS[name](str(root), query)
    clean, sibling_clean = owner.get_structure(), request(name, sibling)
    with denied(child):
        owner.get_structure()
        assert request(name, sibling) == sibling_clean
    assert owner.get_structure() == clean
    assert owner.execution_facts(clean).completeness.value == 'complete'


@pytest.mark.parametrize('name', OWNERS)
def test_clean_zero_remains_complete(tmp_path, name):
    write(tmp_path / 'zero.py', 'VALUE = 1\n')
    assert request(name, tmp_path)[1] == 'complete'


@pytest.mark.parametrize('collector_raises', [False, True])
def test_architecture_request_capture_is_cleared_on_success_and_exception(tmp_path, collector_raises):
    write(tmp_path / 'visible.py', complex_source())
    owner = ArchitectureAdapter(str(tmp_path))
    if collector_raises:
        with patch('reveal.adapters.architecture._run_combined_analysis', side_effect=OSError('collector failed')):
            with pytest.raises(OSError, match='collector failed'):
                owner.get_structure()
    else:
        owner.get_structure()
    assert not hasattr(owner, '_architecture_observations')
    result = owner.get_structure()
    assert owner.execution_facts(result).completeness.value == 'complete'
    assert not hasattr(owner, '_architecture_observations')


def test_overview_real_read_failures_are_not_stats_observations(tmp_path):
    from reveal.adapters.stats import StatsAdapter
    from reveal.adapters.stats import analysis
    child = tree(tmp_path, 'zero')
    visible = (tmp_path / 'visible.py').resolve()
    real_analyze, real_open = analysis.analyze_file, builtins.open
    active = [False]

    def analyze(*args, **kwargs):
        active[0] = True
        try:
            return real_analyze(*args, **kwargs)
        finally:
            active[0] = False

    def read(file, *args, **kwargs):
        if active[0] and Path(file).resolve() == visible:
            raise PermissionError(13, 'controlled Stats file read loss', str(visible))
        return real_open(file, *args, **kwargs)

    with denied(child), patch.object(analysis, 'analyze_file', analyze), patch('builtins.open', read):
        stats = StatsAdapter(str(tmp_path), 'hotspots=true').get_structure()
        assert stats['files'] == [] and stats['summary']['total_files'] == 0
        assert any(w['type'] == 'analysis_failed' for w in stats['meta']['warnings'])
        _, state = request('overview', tmp_path)
    assert state == 'failed'
