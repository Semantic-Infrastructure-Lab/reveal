"""BACK-1644: flag values that were accepted and then ignored without a word.

- ``?sort=<a field no result has>`` left stats://, git://, markdown:// and json:// in
  their original order, which reads as sorted. Only ast:// said so (BACK-1423). Every
  sorting adapter now asks one helper (``unknown_sort_field_warning``), and the output
  seam prints the warning once, after the render.
- ``reveal f.py --check --format typed`` printed text; ``reveal check`` rejected it.
"""

import json
import os
import subprocess
import sys

import pytest

from reveal.utils.query_control import unknown_sort_field_warning

_MESSAGE = "is not a field of any result"


def _cli(*argv, cwd):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


def _git(*argv, cwd):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com',
                    '-c', 'commit.gpgsign=false', *argv],
                   cwd=cwd, check=True, capture_output=True, timeout=60)


@pytest.fixture
def project(tmp_path):
    """Two Python files, two markdown docs, a JSON array and a two-commit repo."""
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def g(x):\n    if x:\n        return 1\n    return 2\n',
                                   encoding='utf-8')
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'one.md').write_text('---\ntitle: One\n---\n# One\n', encoding='utf-8')
    (docs / 'two.md').write_text('---\ntitle: Two\n---\n# Two\n', encoding='utf-8')
    (tmp_path / 'arr.json').write_text('[{"a": 2}, {"a": 1}]', encoding='utf-8')
    _git('init', '-q', cwd=tmp_path)
    _git('add', 'a.py', cwd=tmp_path)
    _git('commit', '-q', '-m', 'one', cwd=tmp_path)
    _git('add', '.', cwd=tmp_path)
    _git('commit', '-q', '-m', 'two', cwd=tmp_path)
    return tmp_path


# (uri with an unknown sort field, the same uri with a real one)
_SORTING = [
    ('stats://.?sort=-nosuch', 'stats://.?sort=-complexity'),
    ('git://.?sort=-nosuch', 'git://.?sort=date'),
    ('markdown://docs?sort=-nosuch', 'markdown://docs?sort=-title'),
    ('json://arr.json?sort=-nosuch', 'json://arr.json?sort=a'),
    ('ast://.?sort=-nosuch', 'ast://.?sort=-complexity'),
]


@pytest.mark.parametrize('unknown, known', _SORTING, ids=[u.split(':')[0] for u, _ in _SORTING])
def test_unknown_sort_field_is_said_once_in_text(project, unknown, known):
    run = _cli(unknown, cwd=project)
    assert run.returncode == 0, run.stderr
    assert run.stdout.count(_MESSAGE) == 1, run.stdout
    assert "'nosuch'" in run.stdout

    run = _cli(known, cwd=project)
    assert run.returncode == 0, run.stderr
    assert _MESSAGE not in run.stdout + run.stderr


@pytest.mark.parametrize('unknown, _known', _SORTING, ids=[u.split(':')[0] for u, _ in _SORTING])
def test_unknown_sort_field_is_in_the_json_result(project, unknown, _known):
    run = _cli(unknown, '--format', 'json', cwd=project)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    # json:// keeps its disclosures at the top level (sort_failed, unknown_filter_field)
    warnings = (result.get('meta') or {}).get('warnings', []) + result.get('warnings', [])
    assert [w['field'] for w in warnings if w.get('type') == 'unknown_sort_field'] == ['nosuch']


def test_helper_reads_fields_the_way_the_sort_does():
    rows = [{'lines': {'total': 3}}, {'lines': {'total': 1}}]

    def get(row, field):
        return row['lines']['total'] if field == 'lines' else None

    assert unknown_sort_field_warning('lines', rows, get) is None
    warning = unknown_sort_field_warning('typo', rows, get, sortable=['lines'])
    assert warning['field'] == 'typo' and warning['message'].endswith('Sortable: lines')
    assert unknown_sort_field_warning('typo', [], get) is None
    assert unknown_sort_field_warning(None, rows) is None


def test_file_check_rejects_typed_like_the_subcommand(project):
    run = _cli('a.py', '--check', '--format', 'typed', cwd=project)
    assert run.returncode == 2
    assert 'not supported by reveal --check (supported: text, json, grep)' in run.stderr
    assert _cli('a.py', '--check', '--format', 'json', cwd=project).returncode == 0
