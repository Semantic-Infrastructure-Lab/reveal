"""Surface's required source and independent census loss reach public boundaries."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import surface
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root, useful=True, hidden=True, native=False):
    child = root / 'included_child'
    if native:
        _write(root / 'visible.go', 'package p\nimport "os"\nfunc visible() { ' +
               ('os.Getenv("VISIBLE")' if useful else '') + ' }\n')
        _write(child / 'hidden.go', 'package p\nimport "os"\nfunc hidden() { ' +
               ('os.Getenv("HIDDEN")' if hidden else '') + ' }\n')
    else:
        _write(root / 'visible.py', 'import os\n' +
               ('value=os.getenv("VISIBLE")\n' if useful else 'value=1\n'))
        _write(child / 'hidden.py', 'import os\n' +
               ('value=os.getenv("HIDDEN")\n' if hidden else 'value=1\n'))
    return child


@pytest.fixture
def fault(monkeypatch):
    state = {'stage': None, 'denied': set(), 'unknown': False, 'attempts': [],
             'collection': {}, 'census': None, 'mutate': None, 'mutated': False}
    real_scandir = os.scandir
    real_collect = surface._collect_source_files
    real_census = surface.census_and_coverage_for_path
    real_loader = surface._load_scanner

    def collect(*args, **kwargs):
        state['stage'] = 'source'
        try:
            value = real_collect(*args, **kwargs)
            state['collection'] = {spec.language: list(paths) for spec, paths in value.items() if paths}
            return value
        finally:
            state['stage'] = None

    def census(*args, **kwargs):
        state['stage'] = 'census'
        try:
            value = real_census(*args, **kwargs)
            state['census'] = value[0].to_scope_dict()
            return value
        finally:
            state['stage'] = None

    def scandir(path):
        if (state['stage'], Path(path).resolve()) in state['denied']:
            state['attempts'].append((state['stage'], Path(path).resolve()))
            if state['unknown']:
                raise PermissionError('controlled unlocated Surface enumeration loss')
            raise PermissionError(13, 'controlled Surface enumeration loss', str(path))
        return real_scandir(path)

    def loader(spec):
        scan = real_loader(spec)
        def scanner(path):
            value = scan(path)
            if state['mutate'] and Path(path).name == 'visible.py':
                assert value['env'], value
                state['mutated'] = True
                if state['mutate'] == 'row':
                    value['env'].append(dict(value['env'][0]))
                    value['env'][0]['line'] = True
                else:
                    value['env'] = 42
            return value
        return scanner

    monkeypatch.setattr(surface, '_collect_source_files', collect)
    monkeypatch.setattr(surface, 'census_and_coverage_for_path', census)
    monkeypatch.setattr(surface, '_load_scanner', loader)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _cli(root, spelling, query='', extra=(), fmt='json'):
    args = ['surface', str(root)] if spelling == 'command' else ['surface://' + str(root) + query]
    if spelling == 'command' and query:
        for part in query.lstrip('?').split('&'):
            key, value = part.split('=')
            args += ['--' + key.replace('_', '-')] + ([] if value == 'true' else [value])
    result = _run_reveal_direct(*args, *extra, '--format', fmt, '--no-gitignore')
    return result, json.loads(result.stdout) if fmt == 'json' else result.stdout


def _directory_warnings(answer):
    return [warning for warning in answer.get('meta', {}).get('warnings', [])
            if warning.get('type') == 'analysis_incomplete' and warning.get('unit') == 'directories']


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('case', ['source-positive', 'source-zero', 'source-root', 'source-unknown',
                                 'census-positive', 'census-zero', 'go-source'])
def test_required_population_loss_classifies_actual_requested_observations(tmp_path, fault, spelling, case):
    root = tmp_path / 'project'
    useful = case not in ('source-zero', 'census-zero')
    child = _project(root, useful=useful, hidden=case != 'census-zero', native=case == 'go-source')
    clean_run, clean = _cli(root, spelling)
    assert clean_run.returncode == 0
    stage = 'census' if case.startswith('census') else 'source'
    target = root if case == 'source-root' else child
    fault['denied'].add((stage, target.resolve()))
    fault['unknown'] = case == 'source-unknown'
    run, answer = _cli(root, spelling)
    assert fault['attempts'] == [(stage, target.resolve())]
    if stage == 'source':
        assert fault['census']['total_code_files'] == clean['scope']['total_code_files'] == 2
    else:
        assert answer['surfaces'] == clean['surfaces']
        assert sum(len(paths) for paths in fault['collection'].values()) == 2
        assert answer['scope']['total_code_files'] == 1
    warnings = _directory_warnings(answer)
    assert len(warnings) == 1, answer
    note = warnings[0]
    assert ('census' in note['message'].lower()) if stage == 'census' else ('source' in note['message'].lower())
    assert 'missing file population is unknown' in note['message']
    assert note['count'] == (0 if fault['unknown'] else 1)
    if fault['unknown']:
        assert note['unknown_directory_events'] == 1
    assert 'confidence' not in answer['meta'] and 'confidence' not in answer['_meta']
    partial = useful and case != 'source-root'
    assert bool(answer.get('error')) is (not partial)
    expected = AnalysisCompleteness.INCOMPLETE if partial else AnalysisCompleteness.FAILED
    assert surface.SurfaceAdapter.execution_facts(answer).completeness is expected
    assert run.returncode == 3
    text_run, text = _cli(root, spelling, fmt='text')
    assert text_run.returncode == 3
    assert (text + text_run.stderr).count('directory enumeration(s) failed') == 1
    if not partial:
        assert 'No external surfaces detected.' not in text
    fault['denied'].clear()
    repair_run, repaired = _cli(root, spelling)
    assert repair_run.returncode == clean_run.returncode and repaired == clean


@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_census_loss_cannot_hide_unsupported_majority(tmp_path, fault, spelling):
    _write(tmp_path / 'app.py', 'import os\nx=os.getenv("APP")\n')
    child = tmp_path / 'lua'
    for index in range(3):
        _write(child / f'app{index}.lua', 'local x=1\n')
    _, clean = _cli(tmp_path, spelling)
    assert clean['coverage']['dominant_language'] == 'Lua' and clean['coverage']['warning']
    fault['denied'].add(('census', child.resolve()))
    run, answer = _cli(tmp_path, spelling)
    assert answer['surfaces'] == clean['surfaces'] and answer['total'] == 1
    assert answer['scope']['total_code_files'] == 1
    notes = _directory_warnings(answer)
    assert len(notes) == 1 and 'census' in notes[0]['message'].lower(), answer
    assert run.returncode == 3 and not answer.get('error')


@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_both_independent_populations_disclose_their_own_actual_failure(tmp_path, fault, spelling):
    child = _project(tmp_path)
    fault['denied'] = {('source', child.resolve()), ('census', child.resolve())}
    run, answer = _cli(tmp_path, spelling)
    assert set(fault['attempts']) == fault['denied']
    notes = _directory_warnings(answer)
    assert len(notes) == 2, answer
    assert any('census' in note['message'].lower() for note in notes)
    assert any('source' in note['message'].lower() for note in notes)
    assert notes[0]['message'] != notes[1]['message']
    assert answer['total'] == 1 and run.returncode == 3 and not answer.get('error')


@pytest.mark.parametrize('shape', ['row', 'group'])
@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_actual_malformed_required_scanner_payload_cannot_override_discovery_failure(tmp_path, fault, spelling, shape):
    child = _project(tmp_path)
    fault['denied'].add(('source', child.resolve()))
    fault['mutate'] = shape
    run, answer = _cli(tmp_path, spelling)
    assert fault['attempts'] and fault['mutated']
    assert len(_directory_warnings(answer)) == 1, answer
    assert answer.get('error') and run.returncode == 3
    assert surface.SurfaceAdapter.execution_facts(answer).completeness is AnalysisCompleteness.FAILED
    assert 'Traceback' not in run.stderr


@pytest.mark.parametrize('useful', [False, True])
def test_decorated_generic_mcp_retains_existing_partial_vs_private_failure(tmp_path, fault, useful):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    child = _project(tmp_path, useful=useful)
    fault['denied'].add(('source', child.resolve()))
    fault['unknown'] = True
    result = reveal_query('surface://' + str(tmp_path), provenance=True)
    assert fault['attempts']
    assert isinstance(result, _ToolFailure) is (not useful)
    if useful:
        answer = json.loads(result)
        assert len(_directory_warnings(answer)) == 1
        assert 'unknown directory' in result
        assert not answer.get('error')
    else:
        assert 'reveal error:' in result


@pytest.mark.parametrize('case', ['zero', 'parse-only', 'unsupported', 'source-only', 'noise', 'excluded', 'sibling', 'file'])
def test_clean_and_intentional_scope_controls_stay_complete_or_existing_parse_partial(tmp_path, fault, case):
    root = tmp_path / 'project'
    child = _project(root, useful=case != 'zero', hidden=case != 'zero')
    query, extra = '', ()
    if case == 'parse-only':
        _write(root / 'broken.py', 'def broken(:\n')
    elif case == 'unsupported':
        root = tmp_path / 'lua'
        _write(root / 'app.lua', 'local x=1\n')
    elif case == 'source-only':
        child.rename(root / 'tests')
        child = root / 'tests'
        query = '?source_only=true'
    elif case == 'noise':
        child.rename(root / 'node_modules')
        child = root / 'node_modules'
    elif case == 'excluded':
        extra = ('--exclude', 'included_child')
    elif case == 'sibling':
        root = tmp_path / 'sibling'
        _project(root)
    elif case == 'file':
        root = root / 'visible.py'
    clean_run, clean = _cli(root, 'command', query, extra)
    if case in ('zero', 'parse-only'):
        child = tmp_path / 'unconsulted'
    fault['denied'].add(('source', child.resolve()))
    run, answer = _cli(root, 'command', query, extra)
    assert not fault['attempts']
    assert (run.returncode, answer) == (clean_run.returncode, clean)
    assert not _directory_warnings(answer)
    assert answer['meta']['confidence'] == 0.6 and answer['_meta']['confidence'] == 'medium'
    expected = AnalysisCompleteness.INCOMPLETE if case == 'parse-only' else AnalysisCompleteness.COMPLETE
    assert surface.SurfaceAdapter.execution_facts(answer).completeness is expected
    assert run.returncode == (3 if case == 'parse-only' else 0)
    if case == 'source-only':
        assert answer['total'] == 1 and answer['scope']['total_code_files'] == 2
