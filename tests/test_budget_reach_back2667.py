"""The router's budget reaches every list the noun's own cap shapes (BACK-2667).

``--max-items`` and ``--head/--tail/--range`` cut the lists a noun declares in ``BUDGET_LIST_FIELD``.
Three answers kept a capped row list outside that declaration, so the flags cut nothing and said
nothing: git's repository and ref views (the list is nested, ``commits.recent``), json's value view
(json declared no list; the probe fallback does not know ``value``) and patches' ``?view=pressure``
(testability's ``patch_hotspots``/``boundary_hotspots``; patches declared only ``groups``).

The conformance rule: a list whose length follows the noun's own cap is reachable by the budget.
"""
import json
import subprocess

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

MODULE = ('import os\nfrom pkg import m1\n\n\ndef f{i}(x):\n    if x:\n        return {i}\n    return os.getenv(\'X\') or open(x).read()\n\n\n'
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
    (root / 'data.json').write_text(json.dumps({'items': [{'id': i} for i in range(8)], 'meta': {'k': [1, 2, 3]}}),
                                    encoding='utf-8')
    return root


@pytest.fixture
def repo(proj):
    pytest.importorskip('pygit2')

    def git(*args):
        subprocess.run(['git', *args], cwd=proj, check=True, capture_output=True, timeout=60)
    git('init', '-q', '.')
    for i in range(1, 7):
        (proj / 'pkg' / f'm{i}.py').write_text(MODULE.format(i=i) + f'\n# rev {i}\n', encoding='utf-8')
        git('add', '.')
        git('-c', 'user.name=T', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', f'c{i}')
    return proj


def _json(*args):
    result = _run_reveal_direct(*args, '--format', 'json')
    assert result.returncode == 0, result.stderr[-800:]
    return json.loads(result.stdout)


def _at(answer, path):
    for part in path.split('.'):
        answer = answer.get(part) if isinstance(answer, dict) else None
    return answer


def _cut(answer, field):
    entries = [w for w in answer['meta'].get('warnings', []) if w.get('type') == 'truncated' and w['field'] == field]
    assert len(entries) == 1, answer['meta'].get('warnings')
    return entries[0]


def _pressure(proj, top=None):
    query = (f'view=pressure&tests={(proj / "tests").as_posix()}&min_patches=1&min_categories=1'
             f'&include_unresolved=true' + (f'&top={top}' if top is not None else ''))
    return f'patches://{(proj / "pkg").as_posix()}?{query}'


# git: the repository view nests its commit list.

@pytest.mark.parametrize('ref', ['', '@HEAD'])
def test_git_repository_view_max_items_cuts_recent_commits(repo, ref):
    answer = _json(f'git://{repo.as_posix()}{ref}', '--max-items', '1')
    assert len(answer['commits']['recent']) == 1
    entry = _cut(answer, 'commits.recent')
    assert (entry['shown'], entry['total']) == (1, 6)
    assert entry['cause'] == 'max_items'


def test_git_repository_view_limit_and_max_items_name_both_cuts(repo):
    answer = _json(f'git://{repo.as_posix()}?limit=4', '--max-items', '2')
    assert len(answer['commits']['recent']) == 2
    entry = _cut(answer, 'commits.recent')
    assert entry['shown'] == 2 and entry['causes'] == ['max_items', 'limit']


def test_git_repository_view_head_and_tail(repo):
    uncut = _json(f'git://{repo.as_posix()}')['commits']['recent']
    head = _json(f'git://{repo.as_posix()}', '--head', '2')['commits']['recent']
    tail = _json(f'git://{repo.as_posix()}', '--tail', '1')['commits']['recent']
    assert head == uncut[:2] and tail == uncut[-1:]


def test_git_repository_view_other_lists_stay_whole(repo):
    """Control: branch and tag lists are not paged by ``?limit``, so the budget leaves them alone."""
    uncut = _json(f'git://{repo.as_posix()}')
    answer = _json(f'git://{repo.as_posix()}', '--max-items', '1')
    assert answer['branches'] == uncut['branches'] and answer['tags'] == uncut['tags']


# json: the value view's list.

def test_json_value_list_max_items_cuts_and_restates(proj):
    answer = _json(f'json://{(proj / "data.json").as_posix()}/items', '--max-items', '2')
    assert [row['id'] for row in answer['value']] == [0, 1]
    entry = _cut(answer, 'value')
    assert (entry['shown'], entry['total'], entry['cause']) == (2, 8, 'max_items')


def test_json_value_limit_then_max_items_restates_displayed_results(proj):
    answer = _json(f'json://{(proj / "data.json").as_posix()}/items?limit=5', '--max-items', '1')
    assert len(answer['value']) == answer['displayed_results'] == 1
    assert answer['total_matches'] == 8
    assert _cut(answer, 'value')['causes'] == ['max_items', 'limit']


def test_json_value_tail(proj):
    answer = _json(f'json://{(proj / "data.json").as_posix()}/items', '--tail', '1')
    assert [row['id'] for row in answer['value']] == [7]


def test_json_object_value_is_not_a_row_list(proj):
    """Control: a whole-file object value has no rows; nested lists inside it are data, not cut."""
    uncut = _json(f'json://{(proj / "data.json").as_posix()}')
    answer = _json(f'json://{(proj / "data.json").as_posix()}', '--max-items', '1')
    assert answer['value'] == uncut['value']
    assert not [w for w in answer['meta'].get('warnings', []) if w.get('type') == 'truncated']


# patches ?view=pressure: testability's lists and counts.

def test_patches_pressure_max_items_cuts_both_lists_and_restates_counts(proj):
    uncut = _json(_pressure(proj))
    assert len(uncut['patch_hotspots']) > 1 and len(uncut['boundary_hotspots']) > 1, 'the fixture must have rows'
    answer = _json(_pressure(proj), '--max-items', '1')
    summary = answer['summary']
    assert len(answer['patch_hotspots']) == summary['patch_groups_reported'] == 1
    assert len(answer['boundary_hotspots']) == summary['boundary_profiles_reported'] == 1
    assert summary['total_patch_targets'] == uncut['summary']['total_patch_targets']
    assert _cut(answer, 'patch_hotspots')['cause'] == 'max_items'


def test_patches_default_view_still_cuts_groups(proj):
    """Control: the scan view's one list keeps its single-list cut and count."""
    answer = _json(f'patches://{proj.as_posix()}', '--max-items', '1')
    assert answer['displayed_groups'] == len(answer['groups']) == 1


# Conformance: every list that follows the noun's own cap is cut by --max-items.
# (noun case -> list path, request at a cap size n)
_CAP_CASES = {
    'ast': ('results', lambda p, n: f'ast://{(p / "pkg").as_posix()}?limit={n}'),
    'metrics': ('files', lambda p, n: f'metrics://{(p / "pkg").as_posix()}?limit={n}'),
    'imports': ('entries', lambda p, n: f'imports://{(p / "pkg").as_posix()}?sort=-fan-in&limit={n}'),
    'calls': ('entries', lambda p, n: f'calls://{(p / "pkg").as_posix()}?rank=callers&limit={n}'),
    'patches': ('groups', lambda p, n: f'patches://{p.as_posix()}?limit={n}'),
    'patches-pressure': ('patch_hotspots', lambda p, n: _pressure(p, top=n)),
    'json-value': ('value', lambda p, n: f'json://{(p / "data.json").as_posix()}/items?limit={n}'),
    'git-repository': ('commits.recent', lambda p, n: f'git://{p.as_posix()}?limit={n}'),
}

# Exemptions, each with its written reason. A strict xfail: the cell fails the suite once the budget reaches
# the list, so the exemption is removed with the fix.
_MAP_SECTIONS_REASON = ('map sections follow ?top, the Caps-row divergence Overview\'s own package closes (BACK-2669)')
_EXEMPT_CASES = {
    f'{noun}-{section}': (f'map.{section}.rows', lambda p, n, noun=noun: f'{noun}://{p.as_posix()}?top={n}')
    for noun in ('overview', 'architecture') for section in ('fan_in', 'entrypoints')
}
_CAP_CASES.update(_EXEMPT_CASES)


@pytest.mark.parametrize('case', [
    pytest.param(case, marks=pytest.mark.xfail(strict=True, reason=_MAP_SECTIONS_REASON))
    if case in _EXEMPT_CASES else case for case in sorted(_CAP_CASES)])
def test_every_list_the_cap_shapes_is_reachable_by_the_budget(request, case):
    path, uri = _CAP_CASES[case]
    proj = request.getfixturevalue('repo' if case.startswith('git') else 'proj')
    small, large = _at(_json(uri(proj, 2)), path), _at(_json(uri(proj, 5)), path)
    assert len(small) == 2 and len(large) > 2, 'the list must follow the cap'
    assert len(_at(_json(uri(proj, 5), '--max-items', '1'), path)) == 1
