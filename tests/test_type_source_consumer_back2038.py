"""Independent native reveal_type discovery loss and presentation boundaries."""
import copy
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal import capabilities
from reveal.adapters.ast import nav_reveal_type as nav
from reveal.adapters.ast.adapter import AstAdapter
from reveal.utils import path_utils
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component
VISIBLE = 'def visible(target: dict):\n    return target\n'
HIDDEN = 'def hidden_a(target: list):\n    return target\ndef hidden_b(target):\n    return target\n'


def project(root):
    child = root / 'included_child'; child.mkdir(parents=True)
    (root / 'visible.py').write_text(VISIBLE, encoding='utf-8')
    (child / 'hidden.py').write_text(HIDDEN, encoding='utf-8')
    return child


@pytest.fixture
def fault(monkeypatch):
    state = {'stage': None, 'denied': set(), 'mode': 'source', 'unknown': False,
             'events': [], 'scans': [], 'trees': 0, 'censuses': []}
    real_collect, real_scan, real_tree = nav.collect_type_evidence, nav._scan_file, nav.tree_root
    real_hint, real_census, real_scandir = capabilities.python_only_warning, path_utils.census_for_path, os.scandir

    def collect(*args, **kwargs):
        previous = state['stage']; state['stage'] = 'source'
        try:
            return real_collect(*args, **kwargs)
        finally:
            state['stage'] = previous

    def hint(*args, **kwargs):
        previous = state['stage']; state['stage'] = 'hint'
        try:
            return real_hint(*args, **kwargs)
        finally:
            state['stage'] = previous

    def scan(file, var, evidence):
        before = len(evidence)
        real_scan(file, var, evidence)
        state['scans'].append((file, copy.deepcopy(evidence[before:])))

    def tree(*args, **kwargs):
        value = real_tree(*args, **kwargs)
        if state['stage'] == 'source':
            assert value is not None
            state['trees'] += 1
        return value

    def census(*args, **kwargs):
        value = real_census(*args, **kwargs)
        if state['stage'] == 'hint':
            state['censuses'].append(dict(value.per_language))
        return value

    def scandir(path):
        if Path(path) in state['denied'] and state['stage'] in (
                {'source', 'hint'} if state['mode'] == 'both' else {state['mode']}):
            stage = state['stage']; state['events'].append((stage, str(path)))
            if state['unknown']:
                raise PermissionError('independent ' + stage + ' enumeration loss')
            raise PermissionError(13, 'independent ' + stage + ' enumeration loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(nav, 'collect_type_evidence', collect)
    monkeypatch.setattr(nav, '_scan_file', scan)
    monkeypatch.setattr(nav, 'tree_root', tree)
    monkeypatch.setattr(capabilities, 'python_only_warning', hint)
    monkeypatch.setattr(path_utils, 'census_for_path', census)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


def source_warning(result):
    warnings = [w for w in result['meta']['warnings'] if w.get('unit') == 'directories'
                and 'type' in w.get('message', '').lower() and 'source' in w.get('message', '').lower()]
    assert len(warnings) == 1, result['meta']
    warning = warnings[0]
    assert warning.get('code') and warning['type'] == 'analysis_incomplete'
    assert 'missing file population is unknown' in warning['message']
    assert 'confidence' not in result['meta']
    assert result['meta']['parse_mode'] == 'tree_sitter_full' and result['meta']['errors'] == []
    assert not result.get('error')
    return warning


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_actual_source_events_preserve_native_row_and_healthy_hint_population(tmp_path, fault, unknown):
    root = tmp_path / 'project'; root.mkdir()
    (root / 'visible.py').write_text(VISIBLE, encoding='utf-8')
    children = {root / f'part{n}' for n in range(7)}
    for child in children:
        child.mkdir(); (child / 'hidden.py').write_text(VISIBLE, encoding='utf-8')
    fault.update(denied=children, unknown=unknown)
    result = AstAdapter(str(root), 'reveal_type=target').get_structure()
    assert len(fault['events']) == 7 and all(stage == 'source' for stage, _ in fault['events'])
    assert fault['censuses'] == [{'python': 8}] and fault['trees'] == 1
    assert len(fault['scans']) == 1 and fault['scans'][0][1] == result['results']
    assert result['total_results'] == 1 and result['results'][0]['annotation'] == 'dict'
    warning = source_warning(result)
    assert warning['count'] == (0 if unknown else 7)
    if unknown:
        assert warning['unknown_directory_events'] == 7
    else:
        assert len(warning['directories']) == 5 and 'and 2 more' in warning['message']


def test_unknown_root_source_loss_is_not_an_empty_successful_measurement(tmp_path, fault):
    root = tmp_path / 'project'; project(root)
    fault.update(denied={root}, unknown=True)
    result = AstAdapter(str(root), 'reveal_type=target').get_structure()
    assert fault['events'] == [('source', str(root))]
    assert fault['censuses'] == [{'python': 2}] and fault['scans'] == [] and fault['trees'] == 0
    assert result['total_results'] == 0
    warning = source_warning(result)
    assert warning['count'] == 0 and warning['unknown_directory_events'] == 1


@pytest.mark.parametrize('view', ['text_cap0', 'grep', 'artifact', 'projection'])
def test_actual_source_loss_public_outputs_qualify_display_and_preserve_data_channels(tmp_path, fault, view):
    root = tmp_path / 'project'; child = project(root)
    fault['denied'] = {child}
    artifact = tmp_path / 'answer.json'
    flags = ['--provenance']
    if view in {'text_cap0', 'artifact'}:
        flags += ['--format', 'text', '--max-items', '0']
        if view == 'artifact':
            flags += ['--also-json', str(artifact)]
    elif view == 'grep':
        flags += ['--format', 'grep']
    else:
        flags += ['--format', 'json', '--fields', 'results,total_results', '--max-items', '0']
    response = run(f'ast://{root}?reveal_type=target', *flags)
    assert fault['events'] and response.returncode == 0
    assert fault['censuses'] == [{'python': 2}] and fault['trees'] == 1
    if view == 'grep':
        assert len(response.stdout.strip().splitlines()) == 1
        assert response.stdout.strip().endswith(':target')
        assert 'enumeration loss' not in response.stdout
        assert response.stderr.count('missing file population is unknown') == 1
    elif view == 'projection':
        result = json.loads(response.stdout)
        assert result['results'] == [] and result['total_results'] == 1
        assert result['execution']; source_warning(result)
    else:
        text = response.stdout.lower()
        assert 'no occurrences found' not in text and '0 occurrence(s) found' not in text
        assert text.count('displayed') >= 2 and 'analyzed portion' in text
        assert text.count('missing file population is unknown') == 1
        if view == 'artifact':
            result = json.loads(artifact.read_text(encoding='utf-8'))
            assert result['results'] == [] and result['total_results'] == 1
            source_warning(result)


def test_same_directory_source_and_advisory_hint_losses_remain_distinct_populations(tmp_path, fault):
    root = tmp_path / 'project'; child = project(root)
    fault.update(denied={child}, mode='both')
    result = AstAdapter(str(root), 'reveal_type=target').get_structure()
    assert {stage for stage, _ in fault['events']} == {'source', 'hint'}
    assert result['total_results'] == 1
    source = source_warning(result)
    hint, = [w for w in result['meta']['warnings'] if 'capability-language hint' in w.get('message', '').lower()]
    assert source is not hint and source.get('code') != hint.get('code')
    assert source['directories'] == hint['directories'] == ['included_child']
    assert 'independent source enumeration loss' in source['message']
    assert 'independent hint enumeration loss' in hint['message']


def test_advisory_hint_only_zero_results_keep_domain_prior_and_existing_empty_claim(tmp_path, fault):
    root = tmp_path / 'project'; child = project(root)
    fault.update(denied={child}, mode='hint')
    result = AstAdapter(str(root), 'reveal_type=absent').get_structure()
    assert fault['events'] == [('hint', str(child))] and fault['trees'] == 2
    assert result['total_results'] == 0 and result['meta']['confidence'] == 1.0
    assert len(result['meta']['warnings']) == 1
    assert 'capability-language hint' in result['meta']['warnings'][0]['message'].lower()
    response = run(f'ast://{root}?reveal_type=absent')
    assert response.returncode == 0 and 'no occurrences found' in response.stdout
    assert '0 occurrence(s) found' in response.stdout and 'analyzed portion' not in response.stdout


def test_reused_adapter_source_events_clear_on_repair_and_sibling_stays_exact(tmp_path, fault):
    root = tmp_path / 'project'; child = project(root)
    sibling = tmp_path / 'sibling'; project(sibling)
    owner = AstAdapter(str(root), 'reveal_type=target')
    clean = owner.get_structure(); sibling_clean = AstAdapter(str(sibling), 'reveal_type=target').get_structure()
    fault['denied'] = {child}
    lost = owner.get_structure()
    assert lost['total_results'] == 1
    assert AstAdapter(str(sibling), 'reveal_type=target').get_structure() == sibling_clean
    fault['denied'] = set()
    assert owner.get_structure() == clean
    source_warning(lost)


@pytest.mark.parametrize('control', ['singlefile', 'excluded', 'default_positional'])
def test_existing_single_file_pruning_and_default_native_shapes_remain_compatible(tmp_path, fault, control):
    root = tmp_path / 'project'; child = project(root)
    if control == 'singlefile':
        fault['denied'] = {root, child}
        result = AstAdapter(str(root / 'visible.py'), 'reveal_type=target').get_structure()
        assert result['total_results'] == 1 and fault['events'] == []
        assert result['meta']['confidence'] == 1.0 and result['meta']['warnings'] == []
    elif control == 'excluded':
        fault['denied'] = {child}
        with exclusion_scope(root, ['included_child']):
            result = AstAdapter(str(root), 'reveal_type=target').get_structure()
        assert result['total_results'] == 1 and fault['events'] == []
        assert result['meta']['confidence'] == 1.0 and result['meta']['warnings'] == []
    else:
        result = nav.collect_type_evidence(str(root), 'target')
        assert type(result) is list and len(result) == 3
        assert nav.render_type_evidence('target', [], str(root)) == f'reveal_type(target): no occurrences found in {root}'
        assert fault['events'] == []
