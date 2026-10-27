"""Optional scope enumeration loss must follow its existing exception contract."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import architecture, overview
from reveal.capabilities import scope_dict_for_path
from reveal.utils.exclusions import exclusion_scope
from reveal.utils.path_utils import to_posix
from reveal.utils.results import AnalysisCompleteness

pytestmark = pytest.mark.component
OWNERS = [('architecture', architecture, architecture.ArchitectureAdapter, 'top=0'),
          ('overview', overview, overview.OverviewAdapter, 'no_git=true&top=0')]


def _write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


def _project(root, positive):
    root.mkdir(parents=True)
    if positive:
        _write(root / 'caller.py', 'import leaf\n\ndef caller():\n    return leaf.target()\n')
        _write(root / 'leaf.py', 'def target():\n    return 1\n')
    children = []
    for number in range(7):
        child = root / f'included_{number}'
        _write(child / 'note.txt', 'The independent census still enumerates this included directory.\n')
        children.append(child.resolve())
    return children


def _fault(monkeypatch, module):
    state = {'active': False, 'denied': set(), 'unknown': False, 'exception': None,
             'events': [], 'calls': 0}
    real_scope, real_scandir = module.scope_dict_for_path, os.scandir

    def scope(*args, **kwargs):
        state['calls'] += 1
        if state['exception'] is not None:
            raise state['exception']
        state['active'] = True
        try:
            return real_scope(*args, **kwargs)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('independent unknown optional census enumeration loss')
            raise PermissionError(13, 'independent optional census enumeration loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(module, 'scope_dict_for_path', scope)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def _body(result):
    return {key: value for key, value in result.items() if key not in ('scope', 'meta')}


def _compose(result):
    return [error for error in result['meta']['errors'] if error.get('code') == 'E_COMPOSE']


def _directories(result):
    return [warning for warning in result['meta']['warnings'] if warning.get('unit') == 'directories']


@pytest.mark.parametrize('name,module,adapter_class,query', OWNERS)
@pytest.mark.parametrize('positive,unknown', [(True, False), (False, True)])
def test_multiple_actual_scope_events_match_existing_optional_exception_and_survive_cuts(
        tmp_path, monkeypatch, name, module, adapter_class, query, positive, unknown):
    root = tmp_path / 'affected'
    children = _project(root, positive)
    sibling = tmp_path / 'sibling'
    _project(sibling, positive)
    state = _fault(monkeypatch, module)
    adapter = adapter_class(str(root), query)
    clean = adapter.get_structure()
    sibling_clean = adapter_class(str(sibling), query).get_structure()
    # Existing optional-child failure supplies the policy comparator, including empty input.
    state['exception'] = RuntimeError('independent ordinary optional scope exception')
    prior = adapter.get_structure()
    assert prior['scope'] == {} and prior['meta']['confidence'] == 0.0
    assert len(_compose(prior)) == 1
    assert adapter_class.execution_facts(prior).completeness is AnalysisCompleteness.INCOMPLETE
    assert not _directories(prior)
    state.update(exception=None, denied=set(children), unknown=unknown)
    start, calls = len(state['events']), state['calls']
    result = adapter.get_structure()
    assert len(state['events']) - start == 7 and state['calls'] == calls + 1
    assert _body(result) == _body(clean) == _body(prior)
    assert result['scope'] == {}  # Do not turn a failed optional section into false census zero.
    assert result['meta']['confidence'] == 0.0
    assert len(_compose(result)) == 1
    assert adapter_class.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
    assert not any(error.get('code') in ('E_ARCHITECTURE_ANALYSIS', 'E_OVERVIEW_ANALYSIS')
                   for error in result['meta']['errors'])
    warning, = _directories(result)
    assert warning['count'] == (0 if unknown else 7)
    assert len(warning['directories']) == (0 if unknown else 5)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert 'and 2 more' in warning['message']
    assert 'missing file population is unknown' in warning['message']
    # Reusing the owner must neither accumulate composed child errors nor lose new evidence.
    again = adapter.get_structure()
    assert again == result and len(_compose(again)) == 1
    assert adapter_class(str(sibling), query).get_structure() == sibling_clean
    uri = f'{name}://{root.as_posix()}?{query}'
    projected = run(uri, '--format', 'json', '--fields', 'path', '--provenance')
    assert projected.returncode == 3
    data = json.loads(projected.stdout)
    # architecture writes its path with '/' on every OS (BACK-2302); overview still echoes the spelling given.
    assert to_posix(data['path']) == to_posix(root) and len(_compose(data)) == 1
    assert len(_directories(data)) == 1
    assert data['execution']['command'].startswith(f'reveal {name}://')
    artifact = tmp_path / 'answer.json'
    text = run(uri, '--also-json', str(artifact))
    assert text.returncode == 3
    assert (text.stdout + text.stderr).count('identified directory enumeration(s) failed') == 1
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['scope'] == {} and saved['meta']['confidence'] == 0.0
    assert adapter_class.execution_facts(saved).completeness is AnalysisCompleteness.INCOMPLETE
    state['denied'] = set()
    assert adapter.get_structure() == clean
    assert adapter.composed_meta() is None


@pytest.mark.parametrize('name,module,adapter_class,query', OWNERS)
def test_nonwalk_oserror_retains_old_optional_policy_without_directory_claim(
        tmp_path, monkeypatch, name, module, adapter_class, query):
    _project(tmp_path / 'empty', False)
    root = tmp_path / 'empty'
    state = _fault(monkeypatch, module)
    # A caught child exception alone must never be relabeled as an enumeration event.
    state['exception'] = PermissionError(13, 'independent nonwalk optional scope failure', str(root / 'config'))
    adapter = adapter_class(str(root), query)
    result = adapter.get_structure()
    assert not state['events'] and result['scope'] == {}
    assert result['meta']['confidence'] == 0.0 and len(_compose(result)) == 1
    assert not _directories(result)
    assert adapter.execution_facts(result).completeness is AnalysisCompleteness.INCOMPLETE
    assert not any(error.get('code') in ('E_ARCHITECTURE_ANALYSIS', 'E_OVERVIEW_ANALYSIS')
                   for error in result['meta']['errors'])
    state['exception'] = None
    repaired = adapter.get_structure()
    assert not _compose(repaired) and adapter.composed_meta() is None


def test_scope_default_three_positional_contract_and_explicit_policy_omission(tmp_path):
    _write(tmp_path / 'visible.py', 'VALUE = 1\n')
    _write(tmp_path / 'excluded' / 'hidden.rb', 'VALUE = 2\n')
    default = scope_dict_for_path(tmp_path, [], True)
    assert default['total_code_files'] == 2
    with exclusion_scope(tmp_path, ['excluded']):
        excluded = scope_dict_for_path(tmp_path, [], True)
    assert excluded['total_code_files'] == 1
    assert set(excluded) == set(default)
