"""BACK-2308: metrics:// on a single file applies its filters, and a sort that fails says so.

``metrics://dir?lines>99999`` answers 0 files; ``metrics://file.py?lines>99999`` returned the
file, because the single-file path never asked ``matches_filters``. A filter on a field no file
has (``complxity>5``) was silent there too, where a directory warns ``unknown_filter_field``
(BACK-2299).

``?sort=`` over values that do not compare (``sort=elements`` reads a dict per file) returned
the files in walk order with no warning, as if sorted: ``_apply_sorting`` caught the TypeError
and returned the list. It now records ``sort_failed`` in ``meta.warnings``, as json:// does
(BACK-1614, BACK-2297); the output seam prints it once after the render.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / 'small.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'big.py').write_text(''.join(f'x{i} = {i}\n' for i in range(20)), encoding='utf-8')
    return tmp_path


def _json(tree, monkeypatch, uri):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct(uri, '--format', 'json')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _warnings(data, kind):
    return [w for w in (data.get('meta') or {}).get('warnings', []) if w.get('type') == kind]


# (a) A single file is filtered like a directory.

@pytest.mark.parametrize('query', ['lines>99999', 'lines=1000..2000', 'functions>0'])
def test_a_single_file_that_fails_the_filter_is_not_returned(tree, monkeypatch, query):
    data = _json(tree, monkeypatch, f'metrics://small.py?{query}')
    assert data['files'] == [] and data['summary']['total_files'] == 0
    assert _warnings(data, 'unknown_filter_field') == []  # a real field: a genuine zero


def test_a_single_file_legacy_bound_is_applied(tree, monkeypatch):
    # The min_lines parameter, through the same matches_filters as a directory.
    data = _json(tree, monkeypatch, 'metrics://small.py?min_lines=5')
    assert data['files'] == []


def test_a_single_file_unknown_filter_field_warns(tree, monkeypatch):
    data = _json(tree, monkeypatch, 'metrics://small.py?complxity>5')
    assert data['files'] == []
    [warning] = _warnings(data, 'unknown_filter_field')
    assert "'complxity'" in warning['message']


def test_a_single_file_answer_matches_the_directory_answer(tree, monkeypatch):
    for query in ('lines<5', 'lines>5', 'lines>99999'):
        single = {f['file'] for f in _json(tree, monkeypatch, f'metrics://small.py?{query}')['files']}
        whole = {f['file'] for f in _json(tree, monkeypatch, f'metrics://.?{query}')['files']}
        assert single == whole & {'small.py'}, query


# Negative controls: a file that passes, or no filter, is returned as before.

@pytest.mark.parametrize('query', ['', '?lines<5', '?lines.total=1', '?quality>0'])
def test_a_single_file_that_passes_is_returned(tree, monkeypatch, query):
    data = _json(tree, monkeypatch, f'metrics://small.py{query}')
    assert data['type'] == 'stats_file'
    assert [f['file'] for f in data['files']] == ['small.py']
    assert data['summary']['total_files'] == 1
    assert _warnings(data, 'unknown_filter_field') == []


def test_a_single_file_human_output_says_the_field_is_unknown(tree, monkeypatch):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct('metrics://small.py?complxity>5')
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("'complxity'") == 1


# (b) A sort that fails says so.

def test_a_sort_over_values_that_do_not_compare_is_disclosed(tree, monkeypatch):
    data = _json(tree, monkeypatch, 'metrics://.?sort=elements')
    assert len(data['files']) == 2  # source order, unsorted
    [warning] = _warnings(data, 'sort_failed')
    assert "Not sorted by 'elements'" in warning['message']
    assert _warnings(data, 'unknown_sort_field') == []  # the field exists; it does not compare


def test_the_sort_failure_is_printed_once_in_text(tree, monkeypatch):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct('metrics://.?sort=elements')
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("Not sorted by 'elements'") == 1


@pytest.mark.parametrize('sort, first', [('lines', 'small.py'), ('-lines', 'big.py'), ('file', 'big.py')])
def test_a_sort_that_compares_has_no_warning(tree, monkeypatch, sort, first):
    data = _json(tree, monkeypatch, f'metrics://.?sort={sort}')
    assert data['files'][0]['file'] == first
    assert _warnings(data, 'sort_failed') == []


def test_an_unknown_sort_field_is_not_a_sort_failure(tree, monkeypatch):
    data = _json(tree, monkeypatch, 'metrics://.?sort=lnes')
    assert len(_warnings(data, 'unknown_sort_field')) == 1
    assert _warnings(data, 'sort_failed') == []
