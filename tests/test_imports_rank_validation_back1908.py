"""Imports rank values must select a declared mode or fail before scanning."""

import pytest

from reveal.adapters.imports import ImportsAdapter
from reveal.utils.query_parser import collect_query_keys


@pytest.mark.parametrize('query', [
    'rank=fan-out', 'rank=typo', 'rank=', 'rank',
    'unused&rank=typo', 'circular&rank=fan-out',
])
def test_invalid_rank_is_rejected_before_graph_work(tmp_path, monkeypatch, query):
    calls = []
    monkeypatch.setattr(ImportsAdapter, '_build_graph', lambda *args: calls.append(args))
    with pytest.raises(ValueError, match='rank.*fan-in'):
        ImportsAdapter(str(tmp_path), query).get_structure()
    assert calls == []


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('import b\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('VALUE = 1\n', encoding='utf-8')
    return tmp_path


def test_default_and_declared_rank_keep_distinct_answers(project):
    default = ImportsAdapter(str(project)).get_structure()
    ranked = ImportsAdapter(str(project), 'rank=fan-in').get_structure()
    assert default['type'] == 'imports'
    assert ranked['type'] == 'fan_in_ranking'
    assert [entry['fan_in'] for entry in ranked['entries']] == [1, 0]


def test_validating_rank_does_not_claim_it_was_applied(project):
    with collect_query_keys() as keys:
        result = ImportsAdapter(str(project), 'unused&rank=fan-in').get_structure()
    assert result['type'] == 'unused_imports'
    assert 'rank' in keys.seen
    assert 'rank' not in keys.used


def test_declaration_is_the_rank_value_owner(tmp_path, monkeypatch):
    # _SORT_FIELDS owns the ranking's accepted values (BACK-2620): sort binds them, rank's legacy values
    # are them without the direction, and the schema's choices are generated from them, so a change
    # leaves no second accepted-values table behind.
    from reveal.adapters import imports
    schema = ImportsAdapter.get_schema()['query_params']['sort']
    assert schema['choices'] == list(imports._SORT_FIELDS) and schema['aliases'] == ['rank']
    monkeypatch.setattr(imports, '_SORT_FIELDS', ('-other',))
    with pytest.raises(ValueError, match='rank.*other'):
        ImportsAdapter(str(tmp_path), 'rank=fan-in').get_structure()
    with pytest.raises(ValueError, match='sort.*-other'):
        ImportsAdapter(str(tmp_path), 'sort=-fan-in').get_structure()
