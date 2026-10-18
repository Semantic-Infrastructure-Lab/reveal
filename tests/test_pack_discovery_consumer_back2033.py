"""Pack consumers disclose actual candidate loss while preserving legacy success."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import pack
from reveal.rendering.adapters.pack import PackRenderer
from reveal.utils.results import outcome_of

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root, children=1):
    _write(root / 'main.py', 'def visible():\n    return 1\n')
    _write(root / 'package.json', '{"name": "fixture", "version": "1.0.0"}\n')
    _write(root / 'runtime.lua', 'local value=1\n')
    _write(root / 'notes.txt', 'not an eligible extension\n')
    paths = []
    for number in range(children):
        child = root / f'included_{number}'
        _write(child / ('hidden.go' if number == 0 else 'notes.txt'),
               'package p\nfunc Hidden() {}\n' if number == 0 else 'not eligible\n')
        paths.append(child.resolve())
    return paths


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'events': [], 'walks': 0}
    real_walk, real_scandir = pack._walk_files, os.scandir

    def walk(*args, **kwargs):
        state['walks'] += 1
        state['active'] = True
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('independent unlocated Pack candidate loss')
            raise PermissionError(13, 'independent Pack candidate loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(pack, '_walk_files', walk)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _once(fault, action):
    fault.update(events=[], walks=0)
    result = action()
    assert fault['walks'] == 1
    return result


def _warning(result):
    warnings = [item for item in result.get('meta', {}).get('warnings', []) if item.get('unit') == 'directories']
    assert len(warnings) == 1, result
    return warnings[0]


@pytest.mark.parametrize('unknown', [False, True])
def test_mixed_actual_population_and_seven_directory_events_retain_cause_and_display_bounds(tmp_path, fault, unknown):
    children = _project(tmp_path, children=7)
    owner = pack.PackAdapter(str(tmp_path), 'budget=8000&content=true')
    clean = _once(fault, owner.get_structure)
    assert clean['meta']['total_candidates'] == 4
    fault.update(denied=set(children), unknown=unknown)
    lost = _once(fault, owner.get_structure)
    assert fault['events'] and len(fault['events']) == 7
    assert lost['meta']['total_candidates'] == lost['meta']['selected'] == 3
    assert {row['relative'] for row in lost['files']} == {'main.py', 'package.json', 'runtime.lua'}
    before_content = {item['file']: item for item in clean['content']}
    assert all(item == before_content[item['file']] for item in lost['content'])
    assert not lost.get('error') and outcome_of(lost) == 'ok'
    warning = _warning(lost)
    assert 'PermissionError' in warning['message'] and 'missing file population is unknown' in warning['message']
    assert 'candidate' in warning['message'].lower()
    if unknown:
        assert warning['count'] == 0 and warning['unknown_directory_events'] == 7
    else:
        assert warning['count'] == 7 and len(warning['directories']) == 5
        assert 'and 2 more' in warning['message']
    fault['denied'] = set()
    assert _once(fault, owner.get_structure) == clean


def test_failed_included_directory_cannot_be_declared_irrelevant_from_healthy_file_counts(tmp_path, fault):
    children = _project(tmp_path, children=2)
    owner = pack.PackAdapter(str(tmp_path), 'budget=8000')
    clean = _once(fault, owner.get_structure)
    # This directory really contains only .txt, but its failed enumeration cannot prove that.
    fault['denied'] = {children[1]}
    lost = _once(fault, owner.get_structure)
    assert fault['events'] == [children[1]]
    assert lost['files'] == clean['files']
    assert lost['meta']['total_candidates'] == clean['meta']['total_candidates'] == 4
    assert _warning(lost)['count'] == 1
    assert not lost.get('error') and outcome_of(lost) == 'ok'


@pytest.mark.parametrize('budget', [0, 8000])
def test_prebudget_population_is_preserved_on_same_owner_without_retaining_failure(tmp_path, fault, budget):
    child, = _project(tmp_path)
    owner = pack.PackAdapter(str(tmp_path), f'budget={budget}&content=true')
    clean = _once(fault, owner.get_structure)
    fault['denied'] = {child}
    partial = _once(fault, owner.get_structure)
    assert partial['meta']['total_candidates'] == 3
    assert partial['meta']['selected'] == (0 if budget == 0 else 3)
    assert partial['meta']['skipped'] == (3 if budget == 0 else 0)
    _warning(partial)
    text = PackRenderer.render_structure(partial)
    assert 'observed' in text.lower()
    if budget == 0:
        assert 'budget' in text.lower() and 'unavailable' not in text.lower()
    fault['denied'] = {tmp_path.resolve()}
    unavailable = _once(fault, owner.get_structure)
    assert unavailable['meta']['total_candidates'] == 0 and unavailable['files'] == []
    assert not unavailable.get('error') and outcome_of(unavailable) == 'ok'
    text = PackRenderer.render_structure(unavailable)
    assert 'unavailable' in text.lower() and 'No files fit within budget.' not in text
    fault['denied'] = set()
    assert _once(fault, owner.get_structure) == clean


@pytest.mark.parametrize('tool', ['specialized', 'generic-text', 'generic-json'])
@pytest.mark.parametrize('root_loss', [False, True])
def test_both_decorated_tools_keep_ordinary_strings_with_one_attributed_diagnostic(tmp_path, fault, tool, root_loss):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_pack, reveal_query
    child, = _project(tmp_path)
    fault['denied'] = {tmp_path.resolve() if root_loss else child}
    def invoke():
        if tool == 'specialized':
            return reveal_pack(str(tmp_path), budget=8000, content=True)
        return reveal_query('pack://' + tmp_path.as_posix() + '?budget=8000&content=true',
                            provenance=tool == 'generic-json')
    answer = _once(fault, invoke)
    assert type(answer) is str and fault['events']
    if tool == 'generic-json':
        result = json.loads(answer)
        assert not result.get('error')
        assert result['meta']['total_candidates'] == (0 if root_loss else 3)
        _warning(result)
    else:
        assert answer.count('identified directory enumeration(s) failed') == 1, answer
        assert 'observed' in answer.lower()
        if root_loss:
            assert 'unavailable' in answer.lower() and 'No files fit within budget.' not in answer
        else:
            assert 'main.py' in answer and 'package.json' in answer


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('root_loss', [False, True])
def test_cli_projection_and_text_artifact_keep_legacy_zero_and_population_uncertainty(tmp_path, fault, spelling, root_loss):
    root = tmp_path / 'project'
    child, = _project(root)
    budget = 8000 if root_loss else 0
    fault['denied'] = {root.resolve() if root_loss else child}
    args = (['pack', str(root), '--budget', str(budget), '--content'] if spelling == 'command' else
            ['pack://' + root.as_posix() + f'?budget={budget}&content=true'])
    projection = ['--fields', 'files', '--max-items', '0'] if spelling == 'uri' else []
    run = _once(fault, lambda: _run_reveal_direct(*args, *projection, '--format', 'json', '--provenance'))
    assert run.returncode == 0 and fault['events'], run.stderr
    result = json.loads(run.stdout)
    assert result['files'] == [] and not result.get('error')
    assert result['meta']['total_candidates'] == (0 if root_loss else 3)
    assert result['meta']['budget_tokens'] == budget
    _warning(result)
    # Native Pack supports text/JSON/provenance; JSON sidecars use the URI route.
    if spelling == 'command':
        native_text = _once(fault, lambda: _run_reveal_direct(*args))
        assert native_text.returncode == 0 and fault['events']
        assert (native_text.stdout + native_text.stderr).count('identified directory enumeration(s) failed') == 1
    artifact = tmp_path / 'answer.json'
    artifact_args = ['pack://' + root.as_posix() + f'?budget={budget}&content=true']
    text = _once(fault, lambda: _run_reveal_direct(*artifact_args, '--also-json', str(artifact)))
    assert text.returncode == 0 and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    _warning(saved)
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    assert 'observed' in text.stdout.lower()
    if root_loss:
        assert 'unavailable' in text.stdout.lower() and 'No files fit within budget.' not in text.stdout
    else:
        assert 'budget' in text.stdout.lower() and 'unavailable' not in text.stdout.lower()


def test_uri_presentation_cap_zero_cannot_erase_positive_observed_population_warning(tmp_path, fault):
    child, = _project(tmp_path)
    fault['denied'] = {child}
    response = _once(fault, lambda: _run_reveal_direct(
        'pack://' + tmp_path.as_posix() + '?budget=8000&content=true',
        '--fields', 'files', '--max-items', '0', '--format', 'json'))
    assert response.returncode == 0 and fault['events']
    result = json.loads(response.stdout)
    assert result['files'] == []
    assert result['meta']['total_candidates'] == result['meta']['selected'] == 3
    assert result['meta']['skipped'] == 0
    assert _warning(result)['count'] == 1


@pytest.mark.parametrize('case', ['exclude', 'noise', 'dotdir', 'sibling', 'file', 'budget-zero'])
def test_clean_policy_omissions_and_budget_zero_remain_exact_legacy_success(tmp_path, fault, case):
    root = tmp_path / 'project'
    child, = _project(root)
    query = 'budget=8000'
    if case == 'exclude':
        query += '&exclude=included_0'
    elif case in ('noise', 'dotdir'):
        renamed = root / ('node_modules' if case == 'noise' else '.internal')
        child.rename(renamed)
        child = renamed.resolve()
    elif case == 'sibling':
        root = tmp_path / 'sibling'
        _project(root)
    elif case == 'file':
        root = root / 'main.py'
    elif case == 'budget-zero':
        query = 'budget=0'
        child = tmp_path / 'unconsulted'
    owner = pack.PackAdapter(str(root), query)
    clean = _once(fault, owner.get_structure)
    fault['denied'] = {child}
    assert _once(fault, owner.get_structure) == clean
    assert not fault['events'] and not clean.get('error') and outcome_of(clean) == 'ok'
    assert not any(item.get('unit') == 'directories' for item in clean['meta'].get('warnings', []))
    if case == 'budget-zero':
        assert clean['meta']['total_candidates'] == 4 and clean['files'] == []
        assert 'No files fit within budget.' in PackRenderer.render_structure(clean)
