"""Pack discloses lost candidate discovery while retaining its legacy exit policy."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack
from reveal.mcp_server import reveal_pack, reveal_query
from reveal.utils.results import outcome_of

pytestmark = pytest.mark.component


def project(root, *, empty=False, child_name='included_child'):
    (root / '.git').mkdir(parents=True)
    child = root / child_name
    child.mkdir()
    if not empty:
        (root / 'main.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
        (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    return child


def fault(monkeypatch, paths, *, unknown=False):
    real_walk, real_scandir = pack._walk_files, os.scandir
    state = {'active': False, 'events': [], 'walks': 0, 'enabled': True}

    def walk(*args, **kwargs):
        state['walks'] += 1
        state['active'] = True
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['enabled'] and state['active'] and Path(path) in paths:
            state['events'].append(str(path))
            if unknown:
                raise PermissionError('controlled Pack unknown candidate directory')
            raise PermissionError(13, 'controlled Pack candidate directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(pack, '_walk_files', walk)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def answer(root, budget='8000', extra=''):
    return pack.PackAdapter(str(root), f'budget={budget}&content=true'+extra).get_structure()


def directory_warning(result):
    warnings = [w for w in result['meta'].get('warnings', [])
                if w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories']
    assert len(warnings) == 1
    warning = warnings[0]
    message = warning['message'].lower()
    assert 'candidate' in message and 'observed' in message
    assert 'missing file population is unknown' in message
    assert 'import graph failed' not in message
    assert outcome_of(result) != 'failed' and not result.get('error')
    return warning


@pytest.mark.parametrize('lost', ['child', 'root'])
def test_candidate_only_actual_loss_retains_observed_files_content_and_one_walk(tmp_path, monkeypatch, lost):
    root = tmp_path / 'affected'; child = project(root)
    clean = answer(root)
    state = fault(monkeypatch, {root if lost == 'root' else child})
    result = answer(root)
    assert state['events'] and state['walks'] == 1
    assert result['meta']['total_candidates'] == (0 if lost == 'root' else 1)
    assert result['meta']['selected'] == len(result['files']) == len(result['content'])
    if lost == 'child':
        assert result['files'] == [row for row in clean['files'] if row['relative'] == 'main.py']
        assert result['content'] == [row for row in clean['content'] if row['file'] == 'main.py']
    warning = directory_warning(result)
    assert warning['count'] == 1 and 'PermissionError' in warning['message']


@pytest.mark.parametrize('unknown', [False, True])
def test_full_event_sequence_keeps_named_cap_and_unknown_multiplicity(tmp_path, monkeypatch, unknown):
    root = tmp_path / 'affected'; project(root)
    paths = {root / f'part{n}' for n in range(7)}
    for child in paths:
        child.mkdir(); (child / 'lost.py').write_text('VALUE = 1\n', encoding='utf-8')
    state = fault(monkeypatch, paths, unknown=unknown)
    result = answer(root)
    assert len(state['events']) == 7 and state['walks'] == 1
    warning = directory_warning(result)
    assert warning['count'] == (0 if unknown else 7)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert len(warning['directories']) == 5 and 'and 2 more' in warning['message']


@pytest.mark.parametrize('budget,lost', [('0', 'child'), ('1', 'child'), ('8000', 'root')])
def test_empty_selection_discloses_budget_vs_unavailable_candidate_population(tmp_path, monkeypatch, budget, lost):
    root = tmp_path / 'affected'; child = project(root)
    state = fault(monkeypatch, {root if lost == 'root' else child})
    response = run(f'pack://{root}?budget={budget}', '--format', 'text')
    assert state['events'] and response.returncode == 0
    assert response.stdout.count('missing file population is unknown') == 1
    text = response.stdout.lower()
    if lost == 'root':
        assert 'population' in text and ('unavailable' in text or 'unknown' in text)
        assert 'No files fit within budget.' not in response.stdout
    else:
        assert 'observed' in text and 'budget' in text


@pytest.mark.parametrize('route', ['uri', 'subcommand'])
@pytest.mark.parametrize('format', ['text', 'json'])
def test_native_public_routes_preserve_legacy_zero_with_real_disclosure(tmp_path, monkeypatch, route, format):
    root = tmp_path / 'affected'; project(root)
    state = fault(monkeypatch, {root})
    argv = [f'pack://{root}?budget=8000&content=true'] if route == 'uri' else [
        'pack', str(root), '--budget', '8000', '--content']
    response = run(*argv, '--format', format, '--provenance')
    assert state['events'] and response.returncode == 0
    if format == 'json':
        result = json.loads(response.stdout)
        assert result['meta']['total_candidates'] == 0 and result['files'] == []
        assert result['execution']
        directory_warning(result)
    else:
        assert response.stdout.count('missing file population is unknown') == 1
        assert 'No files fit within budget.' not in response.stdout


@pytest.mark.parametrize('view', ['projection', 'artifact'])
def test_projection_and_artifact_keep_discovery_evidence(tmp_path, monkeypatch, view):
    root = tmp_path / 'affected'; child = project(root)
    state = fault(monkeypatch, {child})
    artifact = tmp_path / 'answer.json'
    flags = ['--provenance']
    if view == 'projection':
        flags += ['--format', 'json', '--fields', 'files', '--max-items', '0']
    else:
        flags += ['--format', 'text', '--also-json', str(artifact)]
    response = run(f'pack://{root}?budget=8000', *flags)
    assert state['events'] and response.returncode == 0
    result = json.loads(response.stdout if view == 'projection' else artifact.read_text(encoding='utf-8'))
    assert result['execution']
    directory_warning(result)
    if view == 'projection':
        assert result['files'] == []


@pytest.mark.parametrize('tool', ['generic', 'specialized'])
def test_both_decorated_mcp_entrypoints_are_ordinary_strings_with_directory_warning(tmp_path, monkeypatch, tool):
    root = tmp_path / 'affected'; project(root)
    state = fault(monkeypatch, {root})
    if tool == 'generic':
        wire = reveal_query(f'pack://{root}?budget=8000', provenance=True)
    else:
        wire = reveal_pack(str(root), budget=8000, content=True)
    assert state['events'] and state['walks'] == 1 and type(wire) is str
    if tool == 'generic':
        directory_warning(json.loads(wire))
    else:
        assert wire.count('missing file population is unknown') == 1
        assert 'No files fit within budget.' not in wire


@pytest.mark.parametrize('tool', ['adapter', 'specialized'])
def test_reused_adapter_or_tool_repairs_and_sibling_without_manual_clears(tmp_path, monkeypatch, tool):
    root = tmp_path / 'affected'; child = project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    adapter = pack.PackAdapter(str(root), 'budget=8000&content=true')
    def invoke(path):
        if tool == 'specialized':
            return reveal_pack(str(path), budget=8000, content=True)
        return adapter.get_structure() if path == root else answer(path)
    clean, sibling_clean = invoke(root), invoke(sibling)
    state = fault(monkeypatch, {child})
    result = invoke(root)
    assert state['events']
    if tool == 'adapter':
        directory_warning(result)
    else:
        assert result.count('missing file population is unknown') == 1
    assert invoke(sibling) == sibling_clean
    state['enabled'] = False
    assert invoke(root) == clean


@pytest.mark.parametrize('policy', ['empty', 'excluded', 'noise', 'gitignore'])
def test_policy_omissions_and_clean_empty_are_exact_without_directory_warning(tmp_path, monkeypatch, policy):
    root = tmp_path / 'affected'
    child = project(root, empty=policy == 'empty', child_name='node_modules' if policy == 'noise' else 'included_child')
    if policy == 'gitignore':
        (root / '.gitignore').write_text('included_child/\n', encoding='utf-8')
    extra = '&exclude=included_child' if policy == 'excluded' else ''
    clean = answer(root, extra=extra)
    state = fault(monkeypatch, set() if policy == 'empty' else {child})
    result = answer(root, extra=extra)
    assert state['events'] == []
    assert result == clean and not result['meta'].get('warnings')


@pytest.mark.parametrize('kind', ['positional_helpers', 'single_file'])
def test_default_helper_shapes_and_clean_budget_zero_remain_compatible(tmp_path, kind):
    root = tmp_path / 'affected'; project(root)
    if kind == 'single_file':
        file = root / 'main.py'
        assert list(pack._walk_files(file, None)) == [file]
        result = answer(file)
        assert result['meta']['total_candidates'] == 1 and len(result['files']) == 1
    else:
        candidates = pack._collect_candidates(root, None, None, None, None, None)
        assert type(candidates) is list and len(candidates) == 2
        result = answer(root, '0')
        assert result['meta']['total_candidates'] == 2
        assert result['files'] == [] and result['meta']['skipped'] == 2
    assert not result['meta'].get('warnings') and not result.get('error')
