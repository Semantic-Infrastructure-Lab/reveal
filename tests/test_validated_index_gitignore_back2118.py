"""Validated rule indexes follow the gitignore switch of the request that uses them (BACK-2118).

D005, T006, M102 and the I007 scan (``_dep_reconciliation``) cache a project-wide index per
root, kept across host requests while a stat fingerprint of the tree is unchanged. The index
is built from a walk that honours ``.gitignore``, and the fingerprint is taken outside a
request's ``?respect_gitignore=`` scope, so an index built with the switch off was served to
the next default request, and the reverse. The calls index already keys on the switch.
"""
import os
import subprocess
import time
from pathlib import Path

import pytest

import reveal.api as api
from reveal.rules.duplicates import D005 as d005_module
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.maintainability import M102 as m102_module
from reveal.rules.types import T006 as t006_module
from reveal.utils.gitignore import gitignore_scope
from reveal.utils.request_cache import host_request

LITERAL = "COLORS = ['red', 'green', 'blue', 'cyan', 'magenta', 'yellow']\n"
PY = frozenset({'.py'})


def _age(*paths: Path) -> None:
    """Age files so the sealing walk stamps them (a file newer than the request is never stamped)."""
    aged = time.time_ns() - 60_000_000_000
    for path in paths:
        os.utime(path, ns=(aged, aged))


@pytest.fixture
def project(tmp_path):
    """A git project: two visible modules and one under a gitignored directory."""
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, timeout=60)
    (tmp_path / 'ign').mkdir()
    (tmp_path / '.gitignore').write_text('ign/\n', encoding='utf-8')
    files = [tmp_path / 'a.py', tmp_path / 'b.py', tmp_path / 'ign' / 'c.py']
    for file in files:
        file.write_text(LITERAL, encoding='utf-8')
    _age(tmp_path / '.gitignore', *files)
    return tmp_path


def _scores(project: Path, respect: bool) -> dict:
    """Per-file quality score of stats:// through the public API (D005 penalises a cluster)."""
    suffix = '' if respect else '?respect_gitignore=false'
    result = api.query(f'stats://{project}{suffix}')
    return {Path(f['file']).as_posix(): f['quality']['score'] for f in result['files']}


def _count_builds(monkeypatch, module) -> list:
    builds: list = []
    real = module._build_index
    monkeypatch.setattr(module, '_build_index', lambda *a, **k: builds.append(1) or real(*a, **k))
    return builds


def test_d005_index_built_without_gitignore_is_not_served_to_a_default_request(project):
    off = _scores(project, respect=False)
    on = _scores(project, respect=True)
    assert sorted(off) == ['a.py', 'b.py', 'ign/c.py']
    assert sorted(on) == ['a.py', 'b.py']
    # Three files form a duplicate cluster (score penalised); two visible files do not.
    assert max(off.values()) < 100.0
    assert set(on.values()) == {100.0}


def test_d005_index_built_with_gitignore_is_not_served_to_a_no_gitignore_request(project):
    on = _scores(project, respect=True)
    off = _scores(project, respect=False)
    assert set(on.values()) == {100.0}
    assert sorted(off) == ['a.py', 'b.py', 'ign/c.py']
    assert max(off.values()) < 100.0


def test_d005_same_switch_repeat_still_reuses_the_index(project, monkeypatch):
    builds = _count_builds(monkeypatch, d005_module)
    first = _scores(project, respect=True)
    second = _scores(project, respect=True)
    assert first == second
    assert len(builds) == 1, "an unchanged tree under the same switch must not be rescanned"


def test_d005_edit_to_a_gitignored_file_is_seen_by_the_next_no_gitignore_request(project):
    """An index built with the switch off is not covered by the default-scope fingerprint."""
    before = _scores(project, respect=False)
    assert max(before.values()) < 100.0
    (project / 'ign' / 'c.py').write_text('X = 1\n', encoding='utf-8')
    assert set(_scores(project, respect=False).values()) == {100.0}


def _request(respect: bool, evaluate):
    """One host request with the URI's ?respect_gitignore= scope inside it, as api.query / MCP do."""
    with host_request(), gitignore_scope(respect):
        return evaluate()


def _t006_names(project: Path, respect: bool) -> set:
    facts = _request(respect, lambda: t006_module._project_facts(str(project / 'a.py')))
    return {td['name'] for td in facts['typeddicts']}


def _m102_imports(project: Path, respect: bool) -> set:
    return set(_request(respect, lambda: m102_module.M102()._collect_all_imports(project)))


def _dep_imports(project: Path, respect: bool) -> frozenset:
    return _request(respect, lambda: dep._scan_project_imports(
        project, PY, dep._fold_hyphen_underscore, '.')).names


@pytest.fixture
def evidence_project(project):
    """The gitignored module alone declares a TypedDict and imports a distinctive module."""
    hidden = project / 'ign' / 'c.py'
    hidden.write_text('from typing import TypedDict\nimport hiddenonlymod\n\n\n'
                      'class HiddenOpts(TypedDict):\n    key_a: int\n    key_b: int\n', encoding='utf-8')
    _age(hidden)
    return project


@pytest.mark.parametrize('first, second', [(False, True), (True, False)])
def test_t006_index_follows_the_switch_in_both_orders(evidence_project, first, second):
    seen = {first: _t006_names(evidence_project, first)}
    seen[second] = _t006_names(evidence_project, second)
    assert seen[False] == {'HiddenOpts'}
    assert seen[True] == set()


@pytest.mark.parametrize('first, second', [(False, True), (True, False)])
def test_m102_imports_follow_the_switch_in_both_orders(evidence_project, first, second):
    seen = {first: _m102_imports(evidence_project, first)}
    seen[second] = _m102_imports(evidence_project, second)
    assert any('hiddenonlymod' in name for name in seen[False])
    assert not any('hiddenonlymod' in name for name in seen[True])


@pytest.mark.parametrize('first, second', [(False, True), (True, False)])
def test_dep_reconciliation_scan_follows_the_switch_in_both_orders(evidence_project, first, second):
    seen = {first: _dep_imports(evidence_project, first)}
    seen[second] = _dep_imports(evidence_project, second)
    assert 'hiddenonlymod' in seen[False]
    assert 'hiddenonlymod' not in seen[True]


def test_t006_m102_and_dep_same_switch_repeat_reuses_the_index(evidence_project, monkeypatch):
    t006_builds = _count_builds(monkeypatch, t006_module)
    walks: list = []
    for module in (m102_module, dep):
        real = module._walk_code_files
        monkeypatch.setattr(module, '_walk_code_files',
                            lambda *a, _real=real, **k: walks.append(1) or _real(*a, **k))
    for _ in range(2):
        _t006_names(evidence_project, True)
        _m102_imports(evidence_project, True)
        _dep_imports(evidence_project, True)
    assert len(t006_builds) == 1
    assert len(walks) == 2, "one walk for M102 and one for the I007 scan, not one per request"
