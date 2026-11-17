"""The router's cuts restate every count that says how many rows are shown (BACK-2653).

``--max-items`` and ``--head/--tail/--range`` cut a noun's list after the noun counted it. The
noun's own "rows shown" count (metrics ``population.displayed_files``, patches ``displayed_groups``,
calls ``top``, testability ``summary.*_reported``) kept the pre-cut number: ``metrics proj
--max-items 2`` showed 2 rows and said 11. Each noun declares those counts in
``BUDGET_COUNT_FIELDS``; the router sets them to the rows left. Population totals stay uncut.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

MODULE = ('import os\nfrom pkg import m1\n\n\ndef f{i}(x):\n    if x:\n        return {i}\n    return os.sep\n\n\n'
          'def g{i}():\n    return f{i}([1])\n')
PATCH_TEST = ('from unittest import mock\nfrom pkg import m{i}\n\n\n'
              + ''.join("def test_{j}():\n    with mock.patch('pkg.m{i}.os'):\n        m{i}.f{i}(1)\n\n\n".replace('{j}', str(j))
                        for j in range(1, 4)))


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'tests').mkdir()
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    for i in range(1, 7):
        (root / 'pkg' / f'm{i}.py').write_text(MODULE.format(i=i), encoding='utf-8')
        (root / 'tests' / f'test_m{i}.py').write_text(PATCH_TEST.replace('{i}', str(i)), encoding='utf-8')
    return root


def _json(*args):
    result = _run_reveal_direct(*args, '--format', 'json')
    assert result.returncode == 0, result.stderr[-800:]
    return json.loads(result.stdout)


def _testability(proj, min_patches=1):
    return (f'testability://{(proj / "pkg").as_posix()}?tests={(proj / "tests").as_posix()}'
            f'&min_patches={min_patches}&min_categories=1&include_unresolved=true')


@pytest.mark.parametrize('cut', [['--max-items', '1'], ['--head', '1'], ['--max-items', '0']])
def test_metrics_displayed_files_follows_the_router_cut(proj, cut):
    answer = _json(f'metrics://{(proj / "pkg").as_posix()}?limit=4', *cut)
    shown = len(answer['files'])
    assert shown == int(cut[1])
    assert answer['population']['displayed_files'] == shown
    assert answer['population']['analyzed_files'] == answer['population']['filtered_files'] == 7


def test_metrics_without_a_limit_too(proj):
    answer = _json(f'metrics://{(proj / "pkg").as_posix()}', '--max-items', '2')
    assert len(answer['files']) == answer['population']['displayed_files'] == 2


@pytest.mark.parametrize('cut', [['--max-items', '1'], ['--max-items', '0'], ['--tail', '2']])
def test_patches_displayed_groups_follows_the_router_cut(proj, cut):
    answer = _json(f'patches://{proj.as_posix()}', *cut)
    assert answer['displayed_groups'] == len(answer['groups']) == int(cut[1])
    assert answer['total_targets'] == 6


def test_calls_rank_top_follows_the_router_cut(proj):
    answer = _json(f'calls://{(proj / "pkg").as_posix()}?rank=callers&limit=4', '--max-items', '1')
    assert answer['top'] == len(answer['entries']) == 1
    assert answer['total_unique_callees'] == 6


def test_testability_reported_counts_follow_each_cut_list(proj):
    uncut = _json(_testability(proj))
    assert len(uncut['patch_hotspots']) == uncut['summary']['patch_groups_reported'] == 6
    answer = _json(_testability(proj), '--max-items', '1')
    summary = answer['summary']
    assert summary['patch_groups_reported'] == len(answer['patch_hotspots']) == 1
    assert summary['boundary_profiles_reported'] == len(answer['boundary_hotspots'])
    assert summary['total_patch_targets'] == uncut['summary']['total_patch_targets']


def test_population_only_nouns_keep_their_totals(proj):
    """Control: imports' ``total`` and ast's ``total_results``/``total_files`` count the population, not the rows."""
    imports = _json(f'imports://{(proj / "pkg").as_posix()}?sort=-fan-in', '--max-items', '1')
    assert len(imports['entries']) == 1 and imports['total'] == 7
    uncut = _json(f'ast://{(proj / "pkg").as_posix()}')
    ast = _json(f'ast://{(proj / "pkg").as_posix()}', '--max-items', '1')
    assert len(ast['results']) == ast['displayed_results'] == 1
    assert (ast['total_results'], ast['total_files']) == (uncut['total_results'], uncut['total_files'])


# A count that follows the rows the noun shows when the noun's own knob changes them is a display count:
# the router's cut must restate it, so the noun declares it. (field, request at two sizes.)
_PAGE_CASES = {
    'metrics': ('files', lambda p, n: f'metrics://{(p / "pkg").as_posix()}?limit={n}'),
    'ast': ('results', lambda p, n: f'ast://{(p / "pkg").as_posix()}?limit={n}'),
    'imports': ('entries', lambda p, n: f'imports://{(p / "pkg").as_posix()}?sort=-fan-in&limit={n}'),
    'calls': ('entries', lambda p, n: f'calls://{(p / "pkg").as_posix()}?rank=callers&limit={n}'),
    'patches': ('groups', lambda p, n: f'patches://{p.as_posix()}?limit={n}'),
    # Testability does not page its patch groups; its threshold changes how many it reports.
    'testability': ('patch_hotspots', lambda p, n: _testability(p, min_patches=4 if n == 2 else 1)),
}


def _counts(answer):
    found = {k: v for k, v in answer.items() if type(v) is int}
    for block in ('population', 'summary'):
        if isinstance(answer.get(block), dict):
            found.update({f'{block}.{k}': v for k, v in answer[block].items() if type(v) is int})
    return found


@pytest.mark.parametrize('noun', sorted(_PAGE_CASES))
def test_every_count_that_follows_the_rows_is_declared(proj, noun):
    from reveal.adapters.registry import get_adapter_class
    field, request = _PAGE_CASES[noun]
    small, large = _json(request(proj, 2)), _json(request(proj, 5))
    assert len(small[field]) != len(large[field]), 'the fixture must page'
    following = sorted(key for key, value in _counts(small).items()
                       if value == len(small[field]) and _counts(large).get(key) == len(large[field]))
    declared = set(getattr(get_adapter_class(noun), 'BUDGET_COUNT_FIELDS', {}).get(field, ()))
    # displayed_results is restated by the router for any one-list answer, undeclared.
    assert sorted(set(following) - declared - {'displayed_results'}) == []
