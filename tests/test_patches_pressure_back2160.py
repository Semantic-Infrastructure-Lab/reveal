"""patches:// absorbs testability:// as ``?view=pressure`` (BACK-2160, Phase 4 lane P4-B, Q-P4-2).

``patches://<src>?view=pressure`` is testability's report (patch hotspots joined with production boundary
fan-out) under the patches noun, the same answer as ``testability://<src>``. The default view is unchanged:
``patches://<tests>`` scans a test root. ``testability://`` keeps answering until the cut release and prints its
replacement (D5).
"""
import json

import pytest

from conftest import _run_reveal_direct as run

PATCH = "from unittest import mock\n\n\ndef test_x():\n    with mock.patch('pkg.mod.target'):\n        pass\n"
BOUNDARY = (
    "import subprocess\nimport requests\n\n\n"
    "def target(url):\n"
    "    requests.get(url)\n"
    "    subprocess.run(['ls'])\n"
    "    open('/tmp/x', 'w').write('x')\n"
    "    return 1\n"
)
NOTE = 'note: testability:// is deprecated; use patches://<path>?view=pressure (the same answer).'


def _w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    _w(root / 'pkg' / 'mod.py', BOUNDARY)
    for name in ('test_a.py', 'test_b.py', 'test_c.py'):
        _w(root / 't' / name, PATCH)
    return root


def _answer(doc):
    """The answer without the retirement fact and without the echoed source spelling."""
    doc = dict(doc)
    doc.pop('source', None)
    meta = dict(doc.get('meta') or {})
    warnings = [w for w in meta.get('warnings', []) if w.get('code') != 'retired_spelling']
    if warnings:
        meta['warnings'] = warnings
    else:
        meta.pop('warnings', None)
    execution = dict(meta.get('execution') or {})
    execution.pop('command', None)
    if execution:
        meta['execution'] = execution
    else:
        meta.pop('execution', None)
    if meta:
        doc['meta'] = meta
    else:
        doc.pop('meta', None)
    return doc


QUERY = ['', '&tests={repo}/t', '&top=1', '&min_patches=1', '&include_unresolved=true']


@pytest.mark.parametrize('extra', QUERY, ids=['default', 'tests', 'top', 'min_patches', 'include_unresolved'])
def test_the_pressure_view_is_the_testability_report(repo, extra):
    extra = extra.format(repo=repo)
    old = run(f'testability://{repo}' + ('?' + extra.lstrip('&') if extra else ''), '--format', 'json')
    new = run(f'patches://{repo}?view=pressure{extra}', '--format', 'json')
    assert old.returncode == new.returncode == 0, old.stderr + new.stderr
    old_doc, new_doc = json.loads(old.stdout), json.loads(new.stdout)
    assert new_doc['type'] == old_doc['type'] == 'testability_report'
    assert new_doc['summary']['total_patch_uses'] == 3  # the fixture really has patch pressure
    assert _answer(old_doc) == _answer(new_doc)
    if extra.startswith('&tests='):
        assert not [w for w in new_doc.get('meta', {}).get('warnings', [])
                    if w['type'] == 'unused_query_param' and 'tests' in w['fields']]


def test_testability_prints_its_replacement_once_and_the_new_spelling_prints_none(repo):
    old = run(f'testability://{repo}', '--format', 'json')
    new = run(f'patches://{repo}?view=pressure', '--format', 'json')
    assert old.returncode == new.returncode == 0, old.stderr + new.stderr
    assert old.stderr.count(NOTE) == 1
    assert 'deprecated' not in new.stderr
    retirement = [w for w in json.loads(old.stdout)['meta']['warnings'] if w.get('code') == 'retired_spelling']
    assert [(w['old'], w['stage']) for w in retirement] == [('testability://', 'note')]
    assert run(f'testability://{repo}').stderr.count(NOTE) == 1


def test_the_default_view_still_scans_a_test_root(repo):
    """Negative control: adding a view did not move the default. patches://<tests> is the raw scan."""
    doc = json.loads(run(f'patches://{repo}/t', '--format', 'json').stdout)
    assert doc['type'] == 'patches_scan' and doc['total_uses'] == 3


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_pressure_only_parameters_are_not_silently_ignored_by_the_default_view(repo, output_format):
    """tests= means nothing to the patches scan (its path is the root); the answer says so."""
    done = run(f'patches://{repo}/t?tests={repo}/t', '--format', output_format)
    assert done.returncode == 0, done.stderr
    if output_format == 'json':
        answer = json.loads(done.stdout)
        assert answer['type'] == 'patches_scan'
        warnings = [w for w in answer['meta']['warnings'] if w['type'] == 'unused_query_param']
        assert [(w['code'], w['fields']) for w in warnings] == [('unused_query_param', ['tests'])]
        assert 'has no effect' not in done.stderr
    else:
        assert done.stderr.count("query param 'tests' has no effect on this patches:// query") == 1


def test_an_unknown_view_is_rejected(repo):
    done = run(f'patches://{repo}?view=everything', '--format', 'json')
    assert done.returncode == 2, (done.returncode, done.stdout, done.stderr)
    assert "view must be one of ('pressure',), got 'everything'" in done.stderr
    assert json.loads(done.stdout)['error']


def test_a_missing_suite_is_the_same_failure_in_both_spellings(tmp_path):
    root = tmp_path / 'bare'
    _w(root / 'pkg' / 'mod.py', BOUNDARY)  # production code, no tests anywhere
    old = run(f'testability://{root}', '--format', 'json')
    new = run(f'patches://{root}?view=pressure', '--format', 'json')
    assert old.returncode == new.returncode
    assert _answer(json.loads(old.stdout)) == _answer(json.loads(new.stdout))


def test_an_unknown_group_is_rejected_not_silently_target(repo):
    """patches used to answer any unknown group= as target; it is a declared choice now (a correction)."""
    done = run(f'patches://{repo}/t?group=everything', '--format', 'json')
    assert done.returncode == 2, (done.returncode, done.stderr)
    assert "group must be one of ('target', 'test', 'file'), got 'everything'" in done.stderr
