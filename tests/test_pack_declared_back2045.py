"""Pack runs through the declared command path (BACK-2045).

Reds first: a literal focus must not rewrite the budget, the zero-token header must
say tokens, and lost candidate discovery follows the D6 exit policy on both
spellings. Controls pin the behavior that must not move.
"""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters import pack
from reveal.cli.invocation import COMMANDS

pytestmark = pytest.mark.component


def project(root, *, empty=False):
    (root / '.git').mkdir(parents=True)
    child = root / 'lost_child'
    child.mkdir()
    if not empty:
        (root / 'main.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
        (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
        (root / 'empty.py').write_text('', encoding='utf-8')
    return child


def lose(monkeypatch, paths):
    """Real os.scandir PermissionError for the named directories, only while Pack walks."""
    real_walk, real_scandir = pack._walk_files, os.scandir
    active = {'on': False}

    def walk(*args, **kwargs):
        active['on'] = True
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active['on'] = False

    def scandir(path):
        if active['on'] and Path(path) in paths:
            raise PermissionError(13, 'controlled Pack candidate directory loss', str(path))
        return real_scandir(path)

    monkeypatch.setattr(pack, '_walk_files', walk)
    monkeypatch.setattr(os, 'scandir', scandir)


def test_pack_is_a_declared_command():
    assert COMMANDS['pack'].declared_adapter == 'pack'


def test_literal_focus_cannot_override_the_budget(tmp_path):
    root = tmp_path / 'p'
    project(root)
    result = run('pack', str(root), '--focus', 'main&budget=0', '--format', 'json')
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data['budget'] == '2000' and data['meta']['budget_tokens'] == 2000
    assert data['meta']['selected'] >= 1


def test_zero_token_budget_header_says_tokens(tmp_path):
    root = tmp_path / 'p'
    project(root)
    text = run('pack', str(root), '--budget', '0').stdout
    assert '[~0 tokens budget]' in text and 'None' not in text.splitlines()[0]


def test_zero_cost_file_still_fits_a_zero_budget(tmp_path):
    root = tmp_path / 'p'
    project(root)
    data = json.loads(run('pack', str(root), '--budget', '0', '--format', 'json').stdout)
    assert [f['relative'] for f in data['files']] == ['empty.py']


@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_lost_discovery_with_candidates_is_incomplete_exit_3(tmp_path, monkeypatch, spelling):
    root = tmp_path / 'p'
    child = project(root)
    lose(monkeypatch, {child})
    args = ('pack', str(root)) if spelling == 'command' else (f'pack://{root}',)
    result = run(*args, '--format', 'json')
    data = json.loads(result.stdout)
    assert result.returncode == 3
    assert data['meta']['total_candidates'] == 2
    assert [w['type'] for w in data['meta']['warnings'] if w['type'] == 'analysis_incomplete']


@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_total_discovery_loss_is_failed_exit_3(tmp_path, monkeypatch, spelling):
    root = tmp_path / 'p'
    project(root)
    lose(monkeypatch, {root})
    args = ('pack', str(root)) if spelling == 'command' else (f'pack://{root}',)
    result = run(*args, '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['total_candidates'] == 0


@pytest.mark.parametrize('spelling', ['command', 'uri'])
def test_healthy_empty_directory_is_complete_exit_0(tmp_path, spelling):
    root = tmp_path / 'p'
    project(root, empty=True)
    args = ('pack', str(root)) if spelling == 'command' else (f'pack://{root}',)
    assert run(*args, '--format', 'json').returncode == 0


def test_malformed_and_negative_budgets_keep_their_historical_meaning(tmp_path):
    root = tmp_path / 'p'
    project(root)
    bad = json.loads(run('pack', str(root), '--budget', 'abc', '--format', 'json').stdout)
    assert bad['meta']['budget_tokens'] == 2000
    negative = json.loads(run('pack', str(root), '--budget=-5', '--format', 'json').stdout)
    assert negative['meta']['budget_tokens'] == -5 and negative['meta']['selected'] == 0


def test_command_and_uri_json_are_equal(tmp_path):
    root = tmp_path / 'p'
    project(root)
    command = json.loads(run('pack', str(root), '--budget', '1000', '--format', 'json').stdout)
    uri = json.loads(run(f'pack://{root}?budget=1000', '--format', 'json').stdout)
    for doc in (command, uri):
        doc.pop('execution', None)
    assert command == uri


def test_missing_path_is_an_error_on_both_spellings(tmp_path):
    gone = tmp_path / 'gone'
    assert run('pack', str(gone)).returncode != 0
    assert run(f'pack://{gone}').returncode != 0


def test_malformed_or_disagreeing_counts_fail_even_beside_healthy_rows():
    from reveal.utils.results import AnalysisCompleteness
    good = {'type': 'pack', 'files': [{'relative': 'a.py'}],
            'meta': {'total_candidates': 2, 'selected': 1, 'skipped': 1}}
    assert pack.PackAdapter.execution_facts(good).completeness is AnalysisCompleteness.COMPLETE
    for bad_meta in ({'total_candidates': 2, 'selected': 1, 'skipped': 0},
                     {'total_candidates': True, 'selected': 1, 'skipped': 1},
                     {'total_candidates': -1, 'selected': 0, 'skipped': 0},
                     {'selected': 1, 'skipped': 1}):
        bad = {**good, 'meta': bad_meta}
        assert pack.PackAdapter.execution_facts(bad).completeness is AnalysisCompleteness.FAILED


def test_presentation_cut_hides_rows_but_not_the_counts(tmp_path, monkeypatch):
    root = tmp_path / 'p'
    child = project(root)
    lose(monkeypatch, {child})
    cut = run(f'pack://{root}', '--fields', 'files', '--max-items', '0', '--format', 'json')
    data = json.loads(cut.stdout)
    assert cut.returncode == 3 and data['files'] == []
    assert data['meta']['total_candidates'] == data['meta']['selected'] == 2
