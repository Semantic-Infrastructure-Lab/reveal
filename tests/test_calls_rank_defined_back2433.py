"""``calls ?rank=callers`` ranks functions and classes the scan defines (BACK-2433).

It ranked every callers-index lookup key, so library methods (``d.get``, ``xs.append``), stdlib
classes (``Path``) and receiver-qualified duplicates of one call (``get`` and ``d.get``) topped the
"most-called functions" list. Each ranked count now equals what ``?callers=NAME`` reports.
"""

import json

from conftest import _run_reveal_direct
from reveal.adapters.calls.index import find_callers, rank_by_callers

SOURCE = '''from pathlib import Path


class Widget:
    def render(self):
        return helper()


def helper():
    return 1


def one(d, xs):
    xs.append(d.get('k'))
    return helper()


def two(d, xs):
    xs.append(d.get('k'))
    Path('x')
    return Widget()


def three(d):
    d.get('k')
    Widget().render()
    return helper()
'''


def _ranked(tmp_path):
    (tmp_path / 'app.py').write_text(SOURCE, encoding='utf-8')
    return rank_by_callers(str(tmp_path), top=0)


def test_only_defined_functions_and_classes_are_ranked(tmp_path):
    names = [entry['name'] for entry in _ranked(tmp_path)['entries']]
    assert names == ['helper', 'Widget', 'render']
    assert not {'get', 'append', 'Path', 'd.get', 'xs.append'} & set(names)


def test_each_ranked_count_equals_callers_query(tmp_path):
    result = _ranked(tmp_path)
    for entry in result['entries']:
        assert entry['caller_count'] == find_callers(str(tmp_path), entry['name'])['total_callers'], entry['name']


def test_ranking_states_its_rule_and_the_unranked_names(tmp_path):
    result = _ranked(tmp_path)
    assert result['total_unique_callees'] == 3
    assert result['undefined_callees'] >= 4  # get, append, Path and the qualified spellings
    assert 'defined' in result['rule'] and '?callers=' in result['rule']


def test_builtins_true_keeps_every_index_key_for_the_graph_invariants(tmp_path):
    # scripts/graph_invariants.py reads rank&builtins=true as the whole callers index.
    from reveal.adapters.calls.index import build_callers_index
    (tmp_path / 'app.py').write_text(SOURCE, encoding='utf-8')
    full = rank_by_callers(str(tmp_path), top=0, include_builtins=True, include_test_framework=True)
    assert {entry['name'] for entry in full['entries']} == set(build_callers_index(str(tmp_path)))
    assert {'get', 'd.get', 'append', 'Path', 'helper'} <= {entry['name'] for entry in full['entries']}
    assert full['undefined_callees'] == 0 and 'builtins and library methods included' in full['rule']


def test_text_output_states_the_rule(tmp_path):
    (tmp_path / 'app.py').write_text(SOURCE, encoding='utf-8')
    response = _run_reveal_direct(f'calls://{tmp_path.as_posix()}/?rank=callers')
    assert response.returncode == 0
    assert 'defined under the path' in response.stdout
    assert 'Not ranked:' in response.stdout and 'defined elsewhere' in response.stdout
    assert '  get  (' not in response.stdout


def test_json_output_carries_the_rule(tmp_path):
    (tmp_path / 'app.py').write_text(SOURCE, encoding='utf-8')
    response = _run_reveal_direct(f'calls://{tmp_path.as_posix()}/?rank=callers', '--format', 'json')
    result = json.loads(response.stdout)
    assert [entry['name'] for entry in result['entries']] == ['helper', 'Widget', 'render']
    assert result['undefined_callees'] >= 4
