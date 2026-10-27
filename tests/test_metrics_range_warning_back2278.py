"""metrics:// `field=a..b` is applied, so it must not warn "Unknown query param ... ignored" (BACK-2278).

The unknown-param check skipped only keys carrying an operator character (`lines>5`); a range keeps
its operator in the value, so `lines=1..5` was named "ignored" while the filter parser applied it.
A key the filter parser consumed is applied; a key nothing reads still warns.
"""
import json

import pytest

from conftest import _run_reveal_direct


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / 'small.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'big.py').write_text(''.join(f'x{i} = {i}\n' for i in range(20)), encoding='utf-8')
    return tmp_path


def _run(tree, monkeypatch, query):
    monkeypatch.chdir(tree)
    result = _run_reveal_direct(f'metrics://.?{query}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    names = sorted(f['file'].replace('\\', '/').rsplit('/', 1)[-1] for f in json.loads(result.stdout)['files'])
    return names, result.stderr


def test_range_filter_is_applied_without_an_ignored_warning(tree, monkeypatch):
    names, stderr = _run(tree, monkeypatch, 'lines=1..5')
    assert names == ['small.py']
    assert 'Unknown query param' not in stderr


def test_range_matches_the_bound_pair(tree, monkeypatch):
    assert _run(tree, monkeypatch, 'lines=10..30')[0] == _run(tree, monkeypatch, 'lines>=10&lines<=30')[0] == ['big.py']


def test_equality_filter_applied_beside_an_operator_does_not_warn(tree, monkeypatch):
    # `lines=1` alone is not a filter (no operator in the query), but next to one it is parsed and applied.
    names, stderr = _run(tree, monkeypatch, 'lines=1&functions>=0')
    assert names == ['small.py']
    assert 'Unknown query param' not in stderr


def test_a_key_nothing_reads_still_warns(tree, monkeypatch):
    # Negative controls: no filter is parsed, so the key really is ignored and says so.
    names, stderr = _run(tree, monkeypatch, 'lines=1')
    assert names == ['big.py', 'small.py']
    assert "Unknown query param 'lines'" in stderr
    _, stderr = _run(tree, monkeypatch, 'bogus=1')
    assert "Unknown query param 'bogus'" in stderr


def test_direct_adapter_construction_agrees(tree, capsys):
    from reveal.adapters.stats.adapter import StatsAdapter
    StatsAdapter(str(tree), 'complexity=0..15')
    assert 'Unknown query param' not in capsys.readouterr().err
