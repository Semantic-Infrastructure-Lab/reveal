"""BACK-2625: patches' vocabulary under D20.

The raw scan's grouping is a view (--view target|test|file; group its legacy word). --suppress on|off is the switch
(--no-suppress its legacy flag). --limit caps each pressure hotspot list as it caps the scan's groups (--top its legacy
word). The pressure view's two minimums are --where terms (patches>=N, categories>=N; --min-patches and
--min-categories their legacy words). Each old word answers as before with its note; two spellings that disagree exit 2.
"""
import json

import pytest
from conftest import _run_reveal_direct as run

from reveal import api

TARGETS = 6


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """TARGETS production functions, each patched in three tests (the default minimum); only f0 is patched five times."""
    (tmp_path / 'app.py').write_text(
        'import os\n\n\n' + ''.join(f'def f{i}(x):\n    return os.getcwd() if x else 1\n\n\n' for i in range(TARGETS)),
        encoding='utf-8')
    (tmp_path / 'tests').mkdir()
    body = 'from unittest import mock\n\nimport app\n\n\n'
    for i in range(TARGETS):
        for case in range(5 if i == 0 else 3):
            body += f"def test_f{i}_{case}():\n    with mock.patch('app.f{i}'):\n        assert app.f{i}(1)\n\n\n"
    (tmp_path / 'tests' / 'test_app.py').write_text(body, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cli(*argv):
    done = run(*argv, '--format', 'json')
    return done.returncode, (json.loads(done.stdout) if done.stdout.strip().startswith('{') else None), done.stderr


def _noted(doc, key):
    return [w for w in doc['meta']['warnings'] if w.get('field') == key]


def _strip_notes(doc):
    doc = json.loads(json.dumps(doc))
    doc['meta']['warnings'] = [w for w in doc['meta']['warnings'] if w.get('type') != 'retired_spelling']
    return doc


def test_the_grouping_is_a_view_and_group_is_its_noted_legacy_word(proj):
    code, new, _ = _cli('patches', 'tests', '--view', 'file')
    assert code == 0 and {g['group_by'] for g in new['groups']} == {'file'}
    code, old, _ = _cli('patches', 'tests', '--group', 'file')
    assert code == 0
    assert [w['replacement'] for w in _noted(old, 'param:patches.group')] == ['--view MODE']
    assert _strip_notes(old) == _strip_notes(new)
    assert {g['group_by'] for g in _cli('patches', 'tests')[1]['groups']} == {'target'}  # omitted is the target grouping, as it was


def test_suppress_is_a_switch_and_no_suppress_its_noted_legacy_flag(proj):
    (proj / 'tests' / 'test_io.py').write_text(
        'from unittest import mock\n\n\ndef test_io():\n    with mock.patch("sys.stdout"):\n        pass\n',
        encoding='utf-8')
    _, on, _ = _cli('patches', 'tests', '--suppress', 'on')
    _, off, _ = _cli('patches', 'tests', '--suppress', 'off')
    assert on != off  # off shows the stdlib noise the default hides
    code, old, _ = _cli('patches', 'tests', '--no-suppress')
    assert code == 0 and [w['replacement'] for w in _noted(old, 'param:patches.no_suppress')] == ['--suppress off']
    assert _strip_notes(old) == _strip_notes(off)


def test_limit_caps_each_pressure_list_and_top_is_its_noted_legacy_word(proj):
    _, whole, _ = _cli('patches', '.', '--view', 'pressure', '--limit', '0')
    _, two, _ = _cli('patches', '.', '--view', 'pressure', '--limit', '2')
    assert len(whole['patch_hotspots']) > 2 and len(two['patch_hotspots']) == 2
    code, old, _ = _cli('patches', '.', '--view', 'pressure', '--top', '2')
    assert code == 0 and [w['replacement'] for w in _noted(old, 'param:patches.top')] == ['--limit N; 0 is uncapped']
    assert _strip_notes(old) == _strip_notes(two)


def test_the_two_minimums_are_where_terms_and_the_old_words_are_noted(proj):
    base = ('patches', '.', '--view', 'pressure')
    _, default, _ = _cli(*base)
    _, strict, _ = _cli(*base, '--where', 'patches>=4')
    assert len(strict['patch_hotspots']) < len(default['patch_hotspots'])  # only f0 has 5 patches
    code, old, _ = _cli(*base, '--min-patches', '4')
    assert code == 0 and [w['replacement'] for w in _noted(old, 'param:patches.min_patches')] == ["--where 'patches>=N'"]
    assert _strip_notes(old) == _strip_notes(strict)
    _, categories, _ = _cli(*base, '--where', 'categories>=9')
    _, old_categories, _ = _cli(*base, '--min-categories', '9')
    assert _strip_notes(old_categories) == _strip_notes(categories)
    # the strictest of repeated terms, and the bare URI key as the same term
    _, repeated, _ = _cli(*base, '--where', 'patches>=2', '--where', 'patches>=4')
    assert _strip_notes(repeated) == _strip_notes(strict)
    assert _cli('patches://.?view=pressure&patches>=4')[1]['patch_hotspots'] == strict['patch_hotspots']


@pytest.mark.parametrize('argv', [
    ['--where', 'patches<=2'], ['--where', 'lines>=2'], ['--where', 'patches>=x']])
def test_where_on_the_pressure_view_takes_only_a_minimum_of_its_two_counts(proj, argv):
    code, _, err = _cli('patches', '.', '--view', 'pressure', *argv)
    assert code == 2 and ('patches>=N' in err or 'unsupported control' in err), err


@pytest.mark.parametrize('argv,pressure', [
    (['--view', 'pressure', '--group', 'file'], True), (['--view', 'test', '--group', 'file'], False),
    (['--view', 'pressure', '--top', '1', '--limit', '2'], True), (['--suppress', 'on', '--no-suppress'], False)])
def test_two_spellings_that_disagree_exit_2(proj, argv, pressure):
    code, _, err = _cli('patches', '.' if pressure else 'tests', *argv)
    assert code == 2 and 'conflict' in err, err


def test_the_api_takes_the_canonical_words(proj):
    assert {g['group_by'] for g in api.query('patches', 'tests', view='file')['groups']} == {'file'}
    assert len(api.query('patches', '.', view='pressure', limit=1)['patch_hotspots']) == 1
    strict = api.query('patches', '.', view='pressure', where=['patches>=4'])
    assert len(strict['patch_hotspots']) < len(api.query('patches', '.', view='pressure')['patch_hotspots'])
