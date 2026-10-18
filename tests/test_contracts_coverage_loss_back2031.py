"""Required Contracts coverage loss is distinct from healthy source observations."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters import contracts
from reveal.adapters.ast import analysis
from reveal.utils.path_utils import LanguageCoverage, assess_language_coverage
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
ABC = 'from abc import ABC\nclass Visible(ABC):\n    pass\n'
GO = 'package p\ntype Visible interface { Go() }\n'
RUST = 'struct Visible;\nimpl External for Visible { fn go(&self) {} }\n'
DATA = 'from dataclasses import dataclass\n@dataclass\nclass Data:\n    value: int\n'


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _project(root, source=ABC, suffix='py'):
    _write(root / ('visible.' + suffix), source)
    child = root / 'included'
    for index in range(3):
        _write(child / f'other{index}.lua', 'local value=1\n')
    return child


@pytest.fixture
def fault(monkeypatch):
    state = {'stage': None, 'denied': set(), 'source_denied': set(), 'unknown': False,
             'events': [], 'shared': [], 'native': [], 'mutate': None, 'mutated': False}
    real_coverage = contracts.assess_language_coverage
    real_scandir = os.scandir
    real_shared = analysis.collect_structures
    real_native = contracts._collect_files
    real_python = contracts._scan_contracts_python

    def coverage(*args, **kwargs):
        state['stage'] = 'coverage'
        try:
            return real_coverage(*args, **kwargs)
        finally:
            state['stage'] = None

    def shared(*args, **kwargs):
        state['stage'] = 'shared'
        try:
            value = real_shared(*args, **kwargs)
            state['shared'].append({'failures': list(value.traversal_failures), 'skipped': list(value.skipped)})
            return value
        finally:
            state['stage'] = None

    def native(*args, **kwargs):
        value = real_native(*args, **kwargs)
        state['native'].append(list(value))
        return value

    def scandir(path):
        target = Path(path).resolve()
        if state['stage'] == 'coverage' and target in state['denied']:
            state['events'].append(target)
            if state['unknown']:
                raise PermissionError('controlled unlocated Contracts coverage census loss')
            raise PermissionError(13, 'controlled Contracts coverage census loss', str(path))
        if state['stage'] == 'shared' and target in state['source_denied']:
            raise PermissionError(13, 'controlled Contracts source discovery loss', str(path))
        return real_scandir(path)

    def python(*args, **kwargs):
        result = real_python(*args, **kwargs)
        if state['mutate']:
            assert result['abcs']
            state['mutated'] = True
            result['abcs'].append(dict(result['abcs'][0]))
            if state['mutate'] == 'name':
                result['abcs'][0]['name'] = {'invalid': 'identity'}
            else:
                result['abcs'][0]['implementations'] = [{'name': 'Broken', 'file': 'visible.py', 'line': True}]
        return result

    monkeypatch.setattr(contracts, 'assess_language_coverage', coverage)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(analysis, 'collect_structures', shared)
    monkeypatch.setattr(contracts, '_collect_files', native)
    monkeypatch.setattr(contracts, '_scan_contracts_python', python)
    return state


def _cli(root, spelling='uri', query='', extra=(), fmt='json'):
    args = ['contracts', str(root)] if spelling == 'command' else ['contracts://' + root.as_posix() + query]
    if spelling == 'command' and query:
        if query == '?abstract_only=true':
            args += ['--abstract-only']
        elif query == '?implementations=false':
            args += ['--no-implementations']
        else:
            raise AssertionError(query)
    run = _run_reveal_direct(*args, *extra, '--format', fmt, '--no-gitignore')
    return run, json.loads(run.stdout) if fmt == 'json' else run.stdout


def _directory_warnings(answer):
    return [entry for entry in answer['meta']['warnings'] if entry.get('unit') == 'directories']


def _domain(answer):
    return {key: value for key, value in answer.items() if key not in ('meta', 'coverage', 'error')}


@pytest.mark.parametrize('spelling', ['command', 'uri'])
@pytest.mark.parametrize('case', ['child', 'root', 'unknown', 'go', 'rust', 'constant', 'empty', 'unsupported'])
def test_actual_coverage_loss_classifies_requested_rows_without_losing_healthy_source(tmp_path, fault, spelling, case):
    root = tmp_path / 'project'
    if case == 'empty':
        root.mkdir()
        child = root
    elif case == 'unsupported':
        _write(root / 'app.lua', 'local value=1\n')
        child = root
    else:
        source, suffix = (GO, 'go') if case == 'go' else ((RUST, 'rs') if case == 'rust' else (ABC, 'py'))
        if case == 'constant':
            source = 'value=1\n'
        child = _project(root, source, suffix)
    clean_run, clean = _cli(root, spelling)
    assert clean_run.returncode == 0
    target = root if case in ('root', 'rust', 'constant', 'empty', 'unsupported') else child
    fault.update(denied={target.resolve()}, unknown=case == 'unknown')
    run, answer = _cli(root, spelling)
    assert fault['events'] == [target.resolve()]
    assert all(not item['failures'] and not item['skipped'] for item in fault['shared'])
    if case in ('go', 'rust'):
        assert not fault['shared'] and len(fault['native'][-1]) == 1
    assert _domain(answer) == _domain(clean)
    if case in ('child', 'go', 'unknown'):
        assert clean['coverage']['dominant_language'] == 'Lua' and clean['coverage']['warning']
        assert answer['coverage']['total_code_files'] == 1
    else:
        assert answer['coverage']['total_code_files'] == 0
    warnings = _directory_warnings(answer)
    assert len(warnings) == 1, answer
    assert 'coverage' in warnings[0]['message'].lower() and 'census' in warnings[0]['message'].lower()
    assert 'missing file population is unknown' in warnings[0]['message']
    assert warnings[0]['count'] == (0 if case == 'unknown' else 1)
    if case == 'unknown':
        assert warnings[0]['unknown_directory_events'] == 1
    assert 'confidence' not in answer['meta']
    useful = case not in ('constant', 'empty', 'unsupported')
    assert bool(answer.get('error')) is (not useful)
    expected = AnalysisCompleteness.INCOMPLETE if useful else AnalysisCompleteness.FAILED
    assert contracts.ContractsAdapter.execution_facts(answer).completeness is expected
    assert run.returncode == 3
    if case == 'rust':
        assert answer['total_contracts'] == 0 and answer['dataclasses'][0]['name'] == 'Visible'
    text_run, text = _cli(root, spelling, fmt='text')
    assert text_run.returncode == 3
    assert (text + text_run.stderr).count('identified directory enumeration(s) failed') == 1
    if not useful:
        assert 'No contracts or seams found.' not in text
    fault['denied'].clear()
    repair_run, repair = _cli(root, spelling)
    assert repair_run.returncode == 0 and repair == clean


@pytest.mark.parametrize('source,suffix,query', [(DATA, 'py', '?abstract_only=true'),
    (RUST, 'rs', '?abstract_only=true'), (RUST, 'rs', '?implementations=false')],
    ids=['dataclass-abstract', 'rust-abstract', 'rust-noimpl'])
def test_requested_filters_cannot_be_rescued_by_hidden_unrequested_observations(tmp_path, fault, source, suffix, query):
    _project(tmp_path, source, suffix)
    clean = contracts.ContractsAdapter(str(tmp_path), query.lstrip('?')).get_structure()
    assert clean['total_contracts'] == 0
    fault['denied'] = {tmp_path.resolve()}
    run, answer = _cli(tmp_path, query=query)
    assert fault['events'] and answer['total_contracts'] == 0
    assert run.returncode == 3 and answer.get('error'), answer
    assert len(_directory_warnings(answer)) == 1
    assert contracts.ContractsAdapter.execution_facts(answer).completeness is AnalysisCompleteness.FAILED


@pytest.mark.parametrize('malformed', ['name', 'nested-line'])
def test_malformed_actual_requested_row_dominates_surviving_healthy_row(tmp_path, fault, malformed):
    child = _project(tmp_path)
    fault.update(denied={child.resolve()}, mutate=malformed)
    run, answer = _cli(tmp_path)
    assert fault['events'] and fault['mutated']
    assert run.returncode == 3 and answer.get('error'), answer
    assert len(_directory_warnings(answer)) == 1
    assert 'confidence' not in answer['meta']
    assert contracts.ContractsAdapter.execution_facts(answer).completeness is AnalysisCompleteness.FAILED


def test_source_error_precedence_and_source_diagnostic_stay_exact_with_coverage_loss(tmp_path, fault):
    _write(tmp_path / 'plain.py', 'value=1\n')
    child = tmp_path / 'included'
    _write(child / 'hidden.py', ABC)
    fault['source_denied'] = {child.resolve()}
    source_run, source = _cli(tmp_path)
    assert source_run.returncode == 3 and source.get('error')
    original_warning, = _directory_warnings(source)
    fault['denied'] = {child.resolve()}
    run, answer = _cli(tmp_path)
    assert fault['events'] and run.returncode == 3
    assert answer['error'] == source['error']
    assert answer['meta']['errors'] == source['meta']['errors']
    warnings = _directory_warnings(answer)
    assert len(warnings) == 2, answer
    assert original_warning in warnings


@pytest.mark.parametrize('useful', [False, True])
def test_generic_decorated_mcp_keeps_partial_answer_or_existing_private_failure(tmp_path, fault, useful):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    _project(tmp_path, ABC if useful else 'value=1\n')
    fault.update(denied={tmp_path.resolve()}, unknown=True)
    response = reveal_query('contracts://' + tmp_path.as_posix(), provenance=True)
    assert fault['events']
    assert isinstance(response, _ToolFailure) is (not useful)
    if useful:
        answer = json.loads(response)
        warnings = _directory_warnings(answer)
        assert len(warnings) == 1, answer
        assert warnings[0]['unknown_directory_events'] == 1
        assert 'confidence' not in answer['meta']
    else:
        assert 'reveal error:' in response


@pytest.mark.parametrize('case', ['zero', 'parse-only', 'unsupported', 'exclude', 'noise', 'sibling', 'file'])
def test_clean_parse_only_and_intentional_omissions_preserve_existing_behavior(tmp_path, fault, case):
    root = tmp_path / 'project'
    child = _project(root, 'value=1\n' if case == 'zero' else ABC)
    extra = ()
    if case == 'parse-only':
        _write(root / 'broken.py', 'def broken(:\n')
    elif case == 'unsupported':
        root = tmp_path / 'lua'
        _write(root / 'app.lua', 'local value=1\n')
    elif case == 'exclude':
        extra = ('--exclude', 'included')
    elif case == 'noise':
        child.rename(root / 'node_modules')
        child = root / 'node_modules'
    elif case == 'sibling':
        root = tmp_path / 'sibling'
        _project(root)
    elif case == 'file':
        root = root / 'visible.py'
    clean_run, clean = _cli(root, extra=extra)
    target = tmp_path / 'unconsulted' if case in ('zero', 'parse-only') else child
    fault['denied'] = {target.resolve()}
    run, answer = _cli(root, extra=extra)
    assert not fault['events']
    assert (run.returncode, answer) == (clean_run.returncode, clean)
    assert answer['meta']['confidence'] == 0.7 and not _directory_warnings(answer)
    expected = AnalysisCompleteness.INCOMPLETE if case == 'parse-only' else AnalysisCompleteness.COMPLETE
    assert contracts.ContractsAdapter.execution_facts(answer).completeness is expected


def test_existing_two_positional_coverage_helper_keeps_language_coverage_shape(tmp_path):
    _project(tmp_path)
    result = assess_language_coverage(tmp_path, {'python'})
    assert isinstance(result, LanguageCoverage)
    assert result.total_code_files == 4 and result.analyzed_files == 1
    assert result.dominant_language == 'Lua' and not result.dominant_supported
