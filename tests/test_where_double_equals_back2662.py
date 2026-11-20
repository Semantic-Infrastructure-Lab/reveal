"""``==`` is equality in every where expression (BACK-2662).

AST read ``F==V`` as equality (its help lists ``==``) while the shared parser that Markdown, JSON, Git and Metrics
use split ``status==draft`` at the first ``=`` into field ``status`` and value ``=draft``: zero rows, exit 0, no
warning. ``QueryFilter`` already mapped ``==`` to ``=``; the tokenizer never produced it. A value that merely
contains ``==`` (base64 padding) keeps its meaning: ``==`` is the operator only where it is the term's first ``=``.
"""
import json
import subprocess

import pytest

from conftest import _run_reveal_direct, without_request_notes
from reveal.utils.query_parser import parse_query_filters


@pytest.mark.parametrize('term, expected', [
    ('status==draft', ('status', '=', 'draft')),
    ('lines==9', ('lines', '=', 9)),
    ('status == draft', ('status', '=', 'draft')),
    # A value containing == keeps it: the first = is the operator.
    ('hash=abc==', ('hash', '=', 'abc==')),
    ('hash=a==b', ('hash', '=', 'a==b')),
    # Existing two-character operators keep precedence over a == inside their value.
    ('name!==x', ('name', '!=', '=x')),
    ('name~==x', ('name', '~=', '=x')),
    ('lines>=9', ('lines', '>=', 9)),
])
def test_double_equals_is_equality_only_as_the_first_equals(term, expected):
    [parsed] = parse_query_filters(term, record=False)
    assert (parsed.field, parsed.op, parsed.value) == expected


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run.returncode, json.loads(run.stdout)


def _same_answer(single, double):
    """``F==V`` answers exactly as ``F=V``, which must itself match something (a positive control)."""
    rc_single, doc_single = single
    rc_double, doc_double = double
    assert rc_single == rc_double == 0
    return doc_single, doc_double


@pytest.fixture
def docs(tmp_path):
    (tmp_path / 'a.md').write_text('---\ntitle: Alpha\nstatus: draft\n---\n# Alpha\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\ntitle: Beta\nstatus: done\n---\n# Beta\n', encoding='utf-8')
    return tmp_path


def test_markdown_double_equals_matches_like_equals(docs):
    single, double = _same_answer(_json(f'markdown://{docs.as_posix()}?where=status=draft'),
                                  _json(f'markdown://{docs.as_posix()}?where=status==draft'))
    assert single['matched_files'] == double['matched_files'] == 1
    sub_rc, sub = _json('markdown', docs.as_posix(), '--where', 'status==draft')
    assert sub_rc == 0 and sub['matched_files'] == 1


def test_json_double_equals_matches_like_equals(tmp_path):
    data = tmp_path / 'd.json'
    data.write_text('[{"n": "a", "v": 1}, {"n": "b", "v": 2}]', encoding='utf-8')
    single, double = _same_answer(_json(f'json://{data.as_posix()}?where=v=1'),
                                  _json(f'json://{data.as_posix()}?where=v==1'))
    assert without_request_notes(single) == without_request_notes(double)  # each request's own note (BACK-2716)
    assert json.dumps(double).count('"n": "a"') >= 1 and '"n": "b"' not in json.dumps(double)


def test_git_double_equals_matches_like_equals(tmp_path):
    env = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 'T',
           'GIT_COMMITTER_EMAIL': 't@example.com', 'HOME': str(tmp_path), 'PATH': '/usr/bin:/bin'}
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, env=env)
    (tmp_path / 'f.txt').write_text('x\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'f.txt'], check=True, env=env)
    subprocess.run(['git', '-C', str(tmp_path), 'commit', '-q', '-m', 'one'], check=True, env=env)
    uri = f'git://{tmp_path.as_posix()}?view=log&where=author'
    single, double = _same_answer(_json(f'{uri}=T'), _json(f'{uri}==T'))
    assert single.get('history') and single.get('history') == double.get('history')


def test_metrics_double_equals_matches_like_equals(tmp_path):
    (tmp_path / 'mod.py').write_text('def a():\n    return 1\n', encoding='utf-8')
    single, double = _same_answer(_json('metrics', tmp_path.as_posix(), '--where', 'lines=2'),
                                  _json('metrics', tmp_path.as_posix(), '--where', 'lines==2'))
    assert single['summary']['total_files'] == double['summary']['total_files'] == 1
