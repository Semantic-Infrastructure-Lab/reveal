"""Independent old-API Stats scoring-disclosure and composed-consumer evidence."""
import copy
import importlib
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.stats.adapter import StatsAdapter
from reveal.adapters.stats import adapter as stats_adapter
from reveal.adapters.stats import metrics
from reveal.rules import RuleRegistry

owner = importlib.import_module('reveal.rules.duplicates.D005')
pytestmark = pytest.mark.component
LITERAL = 'ROUTE_KEYS=["alpha","beta","gamma","delta","epsilon"]\n'


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root, *, disabled=False):
    codes = [rule.code for rule in RuleRegistry.get_rules() if disabled or rule.code != 'D005']
    write(root / '.reveal.yaml', 'root: true\nrules:\n  disable: ' + json.dumps(codes) + '\n')
    write(root / 'pyproject.toml', '[project]\nname="independent-scoring"\n')
    checked = write(root / 'checked.py', LITERAL)
    write(root / 'visible.py', LITERAL)
    hidden = root / 'included_child'
    write(hidden / 'hidden.py', LITERAL)
    return checked, hidden


@pytest.fixture
def actual(monkeypatch):
    state = dict(active=False, enabled=False, unknown=False, denied=set(), outer=None,
                 events=[], builds=[], checks=[], measured=[], ledgers=[])
    real_build, real_scan, real_rule = owner._build_index, os.scandir, owner.D005.check
    real_registry, real_calculate = RuleRegistry.check_file, metrics.calculate_file_stats

    def build(root, rule):
        state['active'] = True
        try:
            result = real_build(root, rule)
            state['builds'].append((root, copy.deepcopy(result.scan_budget)))
            return result
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and state['enabled'] and Path(path) in state['denied']:
            state['events'].append(Path(path))
            if state['unknown']:
                raise PermissionError('actual unlocated scoring inventory loss')
            raise PermissionError(13, 'actual scoring inventory loss', str(path))
        if not state['active'] and Path(path) == state['outer']:
            raise PermissionError(13, 'outer census only', str(path))
        return real_scan(path)

    def rule(self, *args, **kwargs):
        result = real_rule(self, *args, **kwargs)
        state['checks'].append((Path(args[0]), len(result)))
        return result

    def registry(*args, **kwargs):
        ledger = kwargs.get('coverage')
        if ledger is None:
            ledger = []; kwargs['coverage'] = ledger
        result = real_registry(*args, **kwargs)
        state['ledgers'].append((Path(args[0]), copy.deepcopy(ledger)))
        return result

    def calculate(*args, **kwargs):
        result = real_calculate(*args, **kwargs)
        state['measured'].append((Path(args[0]), copy.deepcopy(result)))
        return result

    monkeypatch.setattr(owner, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(owner.D005, 'check', rule)
    monkeypatch.setattr(RuleRegistry, 'check_file', registry)
    monkeypatch.setattr(metrics, 'calculate_file_stats', calculate)
    monkeypatch.setattr(stats_adapter, 'calculate_file_stats', calculate)
    return state


def owner_note(checked):
    note, = owner.get_scan_disclosures([checked])
    assert 'D005' in note and 'missing file population is unknown' in note
    row, = owner.get_scan_budgets([checked])
    assert not row['exact'] and row['failed_files'] == 0
    return note


def scoring_note(result, original):
    notes = [note for note in result.get('meta', {}).get('warnings', [])
             if note.get('type') == 'analysis_incomplete']
    assert notes, result
    text = '\n'.join(note['message'] for note in notes)
    assert original in text and 'scor' in text.lower()
    assert 'lower bound' not in text.lower()  # generic discovery loss can also cause false positives
    return text


@pytest.mark.parametrize('view', ['quality-filter', 'offset', 'filtered-summary'])
def test_two_root_raw_loss_survives_removal_of_every_affected_measured_row(tmp_path, actual, view):
    first, hidden = project(tmp_path / 'first')
    second, _ = project(tmp_path / 'second')
    query = {'quality-filter': 'quality<99', 'offset': 'offset=999',
             'filtered-summary': 'min_lines=999&summary_only=true'}[view]
    actual.update(enabled=True, denied={hidden})
    result = StatsAdapter(str(tmp_path), query).get_structure(code_only=True)
    assert actual['events'] == [hidden] and len(actual['builds']) == 2
    measured = [row for path, row in actual['measured'] if path.suffix == '.py']
    assert len(measured) == 6 and all(not row.get('parse_degraded') for row in measured)
    assert {row['quality']['score'] for row in measured} == {98.0, 100.0}
    assert all(not path.is_relative_to(first.parent) for path, count in actual['checks'] if count)
    original = owner_note(first)
    assert owner.get_scan_disclosures([second]) == []
    assert result['summary']['total_files'] == (3 if view == 'quality-filter' else 0)
    if view == 'filtered-summary':
        assert 'files' not in result
    else:
        assert all('first/' not in row['file'] for row in result['files'])
    scoring_note(result, original)


@pytest.mark.parametrize('scheme', ['hotspots', 'overview'])
@pytest.mark.parametrize('view', ['json', 'text', 'projected', 'artifact'])
def test_declared_composites_keep_existing_incomplete_policy_after_real_scoring_loss(tmp_path, actual, scheme, view):
    checked, hidden = project(tmp_path)
    query = 'files_only=true' if scheme == 'hotspots' else 'no_git=true&no_imports=true'
    uri = f'{scheme}://{tmp_path}?{query}'
    artifact = tmp_path.parent / (tmp_path.name + '.json')
    flags = ['--format', 'text' if view in {'text', 'artifact'} else 'json']
    if view == 'projected':
        flags += ['--fields', 'summary' if scheme == 'hotspots' else 'stats']
        if scheme == 'hotspots':
            flags += ['--max-items', '0']
    if view == 'artifact':
        flags += ['--also-json', str(artifact)]
    clean = run(uri, *flags)
    assert clean.returncode == 0, clean.stderr
    assert 'missing file population is unknown' not in clean.stdout
    owner._evict_root(tmp_path)
    actual.update(enabled=True, denied={hidden})
    lost = run(uri, *flags)
    assert actual['events'] == [hidden]
    assert len([row for path, row in actual['measured'] if path.suffix == '.py']) == 6
    original = owner_note(checked)
    # Positive measured Stats rows remain: empty displayed hotspot rankings do not mean no domain evidence.
    assert len([path for path, _count in actual['checks'] if path.suffix == '.py']) == 6
    assert lost.returncode == 3, (lost.returncode, lost.stdout, lost.stderr)
    if view in {'text', 'artifact'}:
        assert lost.stdout.count('missing file population is unknown') == 1
    else:
        scoring_note(json.loads(lost.stdout), original)
    if view == 'artifact':
        scoring_note(json.loads(artifact.read_text(encoding='utf-8')), original)


@pytest.mark.parametrize('unknown', [False, True])
def test_reused_directory_to_element_drops_old_outer_facts_but_keeps_fresh_scoring_facts(tmp_path, actual, unknown):
    checked, hidden = project(tmp_path / 'project')
    sibling, _ = project(tmp_path / 'sibling')
    adapter = StatsAdapter(str(checked.parent), 'code_only=true')
    actual['outer'] = hidden
    prior = adapter.get_structure()
    assert 'outer census only' in str(prior.get('meta'))
    actual.update(outer=None, enabled=True, denied={hidden}, unknown=unknown)
    owner._evict_root(checked.parent)
    lost = adapter.get_element('checked.py')
    original = owner_note(checked)
    assert actual['events'] == [hidden] and lost['quality']['score'] == 100.0
    assert 'outer census only' not in str(lost.get('meta'))
    actual['enabled'] = False; owner._evict_root(checked.parent)
    repaired = adapter.get_element('checked.py')
    other = StatsAdapter(str(sibling.parent)).get_element('checked.py')
    repeated = adapter.get_structure()
    assert repaired['quality']['score'] == other['quality']['score'] == 98.0
    assert not repaired.get('meta') and not other.get('meta') and not repeated.get('meta')
    scoring_note(lost, original)


def test_seven_actual_unknown_events_are_retained_without_outer_population_loss(tmp_path, actual):
    checked, hidden = project(tmp_path)
    denied = {hidden}
    for number in range(6):
        branch = tmp_path / f'part{number}'
        write(branch / 'hidden.py', LITERAL); denied.add(branch)
    actual.update(enabled=True, unknown=True, denied=denied)
    result = StatsAdapter(str(tmp_path), 'code_only=true&summary_only=true').get_structure()
    assert set(actual['events']) == denied and len(actual['events']) == 7
    assert result['summary']['total_files'] == 9 and result['summary']['avg_quality_score'] == 100.0
    assert len(actual['measured']) == len(actual['checks']) == 9
    original = owner_note(checked)
    assert '0 identified directory' in original and '7 enumeration error event(s)' in original
    assert len(owner._project_index[tmp_path].traversal_failures) == 7
    scoring_note(result, original)


def test_unused_cached_loss_does_not_leak_into_disabled_or_other_root_measurements(tmp_path, actual):
    checked, hidden = project(tmp_path / 'lost')
    disabled, _ = project(tmp_path / 'disabled', disabled=True)
    sibling, _ = project(tmp_path / 'sibling')
    actual.update(enabled=True, denied={hidden})
    owner._project_index[checked.parent] = owner._build_index(checked.parent, owner.D005())
    assert owner_note(checked) and actual['events'] == [hidden]
    disabled_row = StatsAdapter(str(disabled)).get_structure()
    other = StatsAdapter(str(sibling)).get_structure()
    assert disabled_row['summary']['total_files'] == other['summary']['total_files'] == 1
    assert not disabled_row.get('meta') and not other.get('meta')
    assert not any(path == disabled for path, _count in actual['checks'])
    ledger = next(ledger for path, ledger in actual['ledgers'] if path == disabled)
    assert all(entry['status'] == 'skipped' for entry in ledger)


def test_clean_reused_element_and_genuine_empty_remain_exactly_clean(tmp_path, actual):
    checked, _ = project(tmp_path / 'project')
    adapter = StatsAdapter(str(checked.parent), 'code_only=true')
    first = adapter.get_element('checked.py'); repeated = adapter.get_element('checked.py')
    empty = tmp_path / 'empty'; empty.mkdir()
    result = StatsAdapter(str(empty), 'code_only=true').get_structure()
    assert first == repeated and first['quality']['score'] == 98.0
    assert not first.get('meta') and not result.get('meta')
    assert result['summary']['total_files'] == 0 and actual['events'] == []
