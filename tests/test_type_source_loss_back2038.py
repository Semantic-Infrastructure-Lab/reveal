"""Native reveal_type source loss must remain distinct from a healthy hint census."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast import nav_reveal_type as nav
from reveal.adapters.ast.adapter import AstAdapter
from reveal.utils import path_utils

pytestmark = pytest.mark.component
VISIBLE = 'def visible(cfg: dict):\n    return cfg\n'
HIDDEN = 'cfg = {"alpha": 1}\nfor cfg in records:\n    pass\n'


def _project(root, visible=True):
    root.mkdir(parents=True)
    (root / 'visible.py').write_text(VISIBLE if visible else 'VALUE = 1\n', encoding='utf-8')
    hidden = root / 'included'
    hidden.mkdir()
    (hidden / 'hidden.py').write_text(HIDDEN, encoding='utf-8')
    return hidden.resolve()


@pytest.fixture
def fault(monkeypatch):
    state = {'stage': 'source', 'active': None, 'denied': set(), 'unknown': False,
             'events': [], 'roots': [], 'hints': [], 'walk_kwargs': []}
    real_collect, real_root = nav.collect_type_evidence, nav.tree_root
    real_hint, real_census = capabilities.python_only_warning, path_utils.census_for_path
    real_scandir, real_walk = os.scandir, nav._walk_code_files

    def collect(*args, **kwargs):
        state['active'] = 'source'
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['active'] = None

    def root(*args, **kwargs):
        value = real_root(*args, **kwargs)
        if state['active'] == 'source':
            state['roots'].append(value is not None)
        return value

    def hint(*args, **kwargs):
        state['active'] = 'hint'
        try:
            return real_hint(*args, **kwargs)
        finally:
            state['active'] = None

    def census(*args, **kwargs):
        result = real_census(*args, **kwargs)
        if state['active'] == 'hint':
            state['hints'].append(dict(result.per_language))
        return result

    def walk(*args, **kwargs):
        if state['active'] == 'source':
            state['walk_kwargs'].append(dict(kwargs))
        yield from real_walk(*args, **kwargs)

    def scandir(path):
        if state['active'] == state['stage'] and Path(path).resolve() in state['denied']:
            state['events'].append((state['active'], Path(path).resolve()))
            if state['unknown']:
                raise PermissionError('actual unlocated reveal_type source directory loss')
            raise PermissionError(13, 'actual reveal_type source directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(nav, 'collect_type_evidence', collect)
    monkeypatch.setattr(nav, 'tree_root', root)
    monkeypatch.setattr(nav, '_walk_code_files', walk)
    monkeypatch.setattr(capabilities, 'python_only_warning', hint)
    monkeypatch.setattr(path_utils, 'census_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _owner(root):
    return AstAdapter(str(root), 'reveal_type=cfg')


def _warning(result):
    warnings = [note for note in result['meta']['warnings'] if note.get('unit') == 'directories']
    assert len(warnings) == 1, result['meta']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_full' and not result['meta']['errors']
    note = warnings[0]
    assert note['type'] == 'analysis_incomplete'
    assert 'missing file population is unknown' in note['message']
    assert 'type' in note['message'].lower() and 'incomplete' in note['message'].lower()
    return note


@pytest.mark.parametrize('population', ['partial', 'zero', 'root', 'unknown'])
def test_real_type_source_loss_disclosed_despite_healthy_hint_census(tmp_path, fault, population):
    hidden = _project(tmp_path / 'project', visible=population != 'zero')
    owner = _owner(hidden.parent)
    clean = owner.get_structure()
    assert clean['total_results'] == (2 if population == 'zero' else 3)
    assert {item['kind'] for item in clean['results']} >= {'assign', 'for'}
    fault.update(denied={hidden.parent} if population == 'root' else {hidden},
                 unknown=population == 'unknown', roots=[], hints=[])
    result = owner.get_structure()
    assert fault['events'] and all(stage == 'source' for stage, _ in fault['events'])
    assert result['total_results'] == (1 if population in ('partial', 'unknown') else 0)
    assert fault['roots'] == ([] if population == 'root' else [True])
    assert fault['hints'] == [{'python': 2}]
    if result['results']:
        assert result['results'][0]['kind'] == 'param' and result['results'][0]['annotation'] == 'dict'
    note = _warning(result)
    assert note['count'] == (0 if population == 'unknown' else 1)
    if population == 'unknown':
        assert note['unknown_directory_events'] == 1
    assert not any('hint census' in item['message'] for item in result['meta']['warnings'])
    fault['denied'] = set()
    assert owner.get_structure() == clean


@pytest.mark.parametrize('visible', [False, True])
def test_text_empty_and_nonempty_footer_qualify_only_displayed_source_portion(tmp_path, fault, visible):
    hidden = _project(tmp_path / 'project', visible)
    fault['denied'] = {hidden}
    response = run(f'ast://{hidden.parent.as_posix()}?reveal_type=cfg')
    assert response.returncode == 3 and fault['events']
    output = response.stdout + response.stderr
    assert 'displayed' in output.lower() and 'analyzed portion' in output.lower()
    assert 'occurrence(s) found' not in output and 'no occurrences found' not in output
    assert output.count('identified directory enumeration(s) failed') == 1


def test_positive_uncapped_native_evidence_cut_zero_keeps_honest_text_and_sidecar(tmp_path, fault):
    hidden = _project(tmp_path / 'project')
    fault['denied'] = {hidden}
    uri = f'ast://{hidden.parent.as_posix()}?reveal_type=cfg'
    uncut = _owner(hidden.parent).get_structure()
    assert uncut['total_results'] == 1 and uncut['results'][0]['kind'] == 'param'
    artifact = tmp_path / 'answer.json'
    response = run(uri, '--max-items', '0', '--also-json', artifact)
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert response.returncode == 3 and saved['total_results'] == 1 and saved['results'] == []
    output = response.stdout + response.stderr
    assert 'displayed' in output.lower() and 'analyzed portion' in output.lower()
    assert 'no occurrences found' not in output and '0 occurrence(s) found' not in output
    _warning(saved)


@pytest.mark.parametrize('visible', [False, True])
def test_grep_preserves_only_native_rows_on_stdout_and_one_source_warning_on_stderr(tmp_path, fault, visible):
    hidden = _project(tmp_path / 'project', visible)
    fault['denied'] = {hidden}
    response = run(f'ast://{hidden.parent.as_posix()}?reveal_type=cfg', '--format', 'grep')
    assert response.returncode == 3 and fault['events']
    expected = f'{(hidden.parent / "visible.py").as_posix()}:1:cfg\n' if visible else ''
    assert response.stdout == expected
    assert response.stderr.count('identified directory enumeration(s) failed') == 1
    assert 'type' in response.stderr.lower()


def test_json_projection_provenance_and_same_adapter_persistent_repair_sibling(tmp_path, fault):
    hidden = _project(tmp_path / 'project')
    sibling = _project(tmp_path / 'sibling')
    owner = _owner(hidden.parent)
    sibling_owner = _owner(sibling.parent)
    baseline, unaffected = owner.get_structure(), sibling_owner.get_structure()
    fault['denied'] = {hidden}
    first, second = owner.get_structure(), owner.get_structure()
    assert first['total_results'] == second['total_results'] == 1 and first == second
    assert len(fault['events']) == 2 and owner.get_structure()['total_results'] == 1
    assert sibling_owner.get_structure() == unaffected
    response = run(f'ast://{hidden.parent.as_posix()}?reveal_type=cfg', '--format', 'json',
                   '--fields', 'total_results', '--provenance')
    data = json.loads(response.stdout)
    assert response.returncode == 3 and data['total_results'] == 1
    assert data['execution']['command'].startswith('reveal ast://')
    _warning(data)
    fault['denied'] = set()
    assert owner.get_structure() == baseline and sibling_owner.get_structure() == unaffected


def test_decorated_mcp_keeps_useful_partial_and_source_attribution(tmp_path, fault):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    hidden = _project(tmp_path / 'project', False)
    fault['denied'] = {hidden}
    answer = reveal_query(f'ast://{hidden.parent.as_posix()}?reveal_type=cfg', provenance=True)
    assert type(answer) is str and not isinstance(answer, _ToolFailure)
    data = json.loads(answer)
    assert data['total_results'] == 0 and fault['hints'] == [{'python': 2}]
    _warning(data)


def test_hint_only_loss_keeps_prior_and_original_empty_text_footer(tmp_path, fault):
    hidden = _project(tmp_path / 'project', False)
    # Use a variable genuinely absent from all native sources.
    uri = f'ast://{hidden.parent.as_posix()}?reveal_type=absent'
    clean = run(uri)
    fault.update(stage='hint', denied={hidden})
    result = AstAdapter(str(hidden.parent), 'reveal_type=absent').get_structure()
    assert result['total_results'] == 0 and result['meta']['confidence'] == 1.0
    assert len(result['meta']['warnings']) == 1
    assert 'hint census' in result['meta']['warnings'][0]['message']
    response = run(uri)
    assert response.returncode == 0 and response.stdout.startswith(clean.stdout.rstrip())
    assert 'no occurrences found' in response.stdout and '0 occurrence(s) found' in response.stdout
    assert 'analyzed portion' not in response.stdout


def test_default_two_positional_helper_native_shapes_and_unsorted_default_walk_unchanged(tmp_path, fault):
    hidden = _project(tmp_path / 'project')
    rows = nav.collect_type_evidence(str(hidden.parent), 'cfg')
    assert type(rows) is list and len(rows) == 3
    assert {item['kind'] for item in rows} == {'param', 'assign', 'for'}
    assert all(item['line'] > 0 and item['file'] for item in rows)
    assert fault['roots'] == [True, True] and len(fault['walk_kwargs']) == 1
    assert 'sort' not in fault['walk_kwargs'][0] and 'purpose' not in fault['walk_kwargs'][0]
    assert nav.collect_type_evidence(str(tmp_path / 'missing'), 'cfg') == []
    assert 'no occurrences found' in nav.render_type_evidence('cfg', [], '.')


def test_report_exclusion_noise_singlefile_and_unrelated_dict_mode_stay_exact(tmp_path, fault):
    hidden = _project(tmp_path / 'project')
    noise = hidden.parent / '.venv'
    noise.mkdir()
    (noise / 'hidden.py').write_text(HIDDEN, encoding='utf-8')
    uri = f'ast://{hidden.parent.as_posix()}?reveal_type=cfg'
    baseline = run(uri, '--exclude', 'included', '--format', 'json')
    file_owner = _owner(hidden.parent / 'visible.py')
    file_baseline = file_owner.get_structure()
    fault['denied'] = {hidden, noise.resolve()}
    response = run(uri, '--exclude', 'included', '--format', 'json')
    assert response.returncode == 0 and response.stdout == baseline.stdout and not fault['events']
    assert file_owner.get_structure() == file_baseline
    assert file_baseline['meta']['confidence'] == 1.0
    unrelated = AstAdapter(str(hidden.parent), 'show=dict-heatmap').get_structure()
    assert unrelated['meta']['confidence'] == 1.0 and not unrelated['meta']['warnings']
    assert not fault['events']
