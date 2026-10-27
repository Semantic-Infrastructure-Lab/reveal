"""BACK-2299: a metrics:// filter on a field no file has warns ``unknown_filter_field``.

``?complxity>5`` and ``?complxity=5..15`` parse as filters, compare None on every file and match
nothing, so the answer was 0 files with no warning: a typo read as a genuine zero. json:// says
so with an ``unknown_filter_field`` warning (BACK-1165); metrics:// now asks the same question
(``find_unknown_filter_fields``) of the files it scanned. BACK-2278 keeps a range on a real field
quiet; so does a real field that matches nothing.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / 'small.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'big.py').write_text(''.join(f'x{i} = {i}\n' for i in range(20)), encoding='utf-8')
    return tmp_path


def _run(tree, monkeypatch, query, scheme='metrics'):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct(f'{scheme}://.?{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    unknown = [w for w in (data.get('meta') or {}).get('warnings', []) if w.get('type') == 'unknown_filter_field']
    return len(data['files']), unknown


@pytest.mark.parametrize('query', ['complxity>5', 'complxity=5..15', 'complxity!=0'])
def test_a_filter_on_a_field_no_file_has_warns(tree, monkeypatch, query):
    files, unknown = _run(tree, monkeypatch, query)
    assert files == 0
    [warning] = unknown
    assert "'complxity'" in warning['message']


def test_only_the_unknown_field_is_named(tree, monkeypatch):
    files, [warning] = _run(tree, monkeypatch, 'lines>1&complxity>1')
    assert files == 0
    assert "'complxity'" in warning['message'] and "'lines'" not in warning['message']


def test_the_retired_stats_spelling_warns_too(tree, monkeypatch):
    files, unknown = _run(tree, monkeypatch, 'complxity>5', scheme='stats')
    assert files == 0 and len(unknown) == 1


def test_the_human_output_shows_the_warning(tree, monkeypatch):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct('metrics://.?complxity>5')
    assert 'complxity' in result.stdout + result.stderr


# Negative controls: a field that exists does not warn, whether or not anything matched.

@pytest.mark.parametrize('query, expected', [
    ('lines=1..5', 1),            # BACK-2278's range on a real field
    ('lines=1000..2000', 0),      # a real field, a genuine zero
    ('lines>9999', 0),
    ('lines.total>9999', 0),      # a dotted path
    ('max_complexity>50', 0),     # an alias
    ('quality.check_issues>99', 0),  # a renamed field still answers (BACK-1884)
])
def test_a_field_that_exists_does_not_warn(tree, monkeypatch, query, expected):
    files, unknown = _run(tree, monkeypatch, query)
    assert files == expected
    assert unknown == []


def test_a_query_that_matches_never_warns(tree, monkeypatch):
    # A file matched, so the filters all resolved somewhere: no disclosure.
    files, unknown = _run(tree, monkeypatch, 'lines<5')
    assert files == 1 and unknown == []
