"""Markdown applicability (COMMAND_MODEL "Applicability", BACK-2656 Step 2d).

Each control declares the answers that read it: the listing reads where, match, columns, explain, sort, limit and
offset; the aggregate reads field, where and match; lint reads lint-fields; the link graph and backlinks read none of
them. A control on another answer is an invalid request with the one shared message, on the URI, the subcommand, the
URI with a flag and ``api.query``. Before, sort/limit/offset there answered with the ledger's note, exit 0, several
answered with no word at all (backlinks with where, links with columns or match, lint with explain, the listing with
lint-fields), and Markdown's own checks ("where/match require the list or aggregate view", "field requires the
aggregate view") refused two of them in their own words.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.errors import RequestValidationError

UNREAD_WARNINGS = ('unused_query_param', 'unused_flag', 'unknown_query_param')


@pytest.fixture
def docs(tmp_path, monkeypatch):
    (tmp_path / 'a.md').write_text('---\ntitle: A\nstatus: ok\n---\n# A\n\n[b](b.md)\nBody text\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('---\ntitle: B\nstatus: draft\n---\n# B\n', encoding='utf-8')
    (tmp_path / 'data.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _unread(doc):
    return [w for w in (doc.get('meta') or {}).get('warnings') or [] if (w.get('code') or w.get('type'))
            in UNREAD_WARNINGS]


_LINKS, _LINT = 'markdown_link_graph', 'markdown_frontmatter_lint'


@pytest.mark.parametrize('argv,control,answer', [
    (('markdown://.?view=links&limit=1',), 'limit', f'{_LINKS}, view, view=links'),     # the ledger's note before
    (('markdown://.?view=lint&sort=title',), 'sort', f'{_LINT}, view, view=lint'),
    (('markdown://.?view=aggregate&field=status&limit=1',), 'limit', 'markdown_aggregate, view, view=aggregate'),
    (('markdown://.?backlinks=b.md&where=title=A',), 'where', 'markdown_backlinks, default'),  # silent before
    (('markdown://.?view=links&columns=title',), 'columns', f'{_LINKS}, view, view=links'),   # silent before
    (('markdown://.?lint&explain',), 'explain', f'{_LINT}, default'),                          # silent before
    (('markdown://.?view=list&lint-fields=title',), 'lint-fields', 'markdown_query, view, view=list'),  # silent
    (('markdown://.?link-graph&match=Body',), 'match', f'{_LINKS}, default'),                  # silent before
    (('markdown://.?view=links&where=title=A',), 'where', f'{_LINKS}, view, view=links'),     # its own check before
    (('markdown://.?field=status',), 'field', 'markdown_query, default'),                     # its own check before
    (('markdown', '.', '--view', 'links', '--limit', '1'), 'limit', f'{_LINKS}, view, view=links'),  # subcommand
    (('markdown://.?view=links', '--limit', '1'), 'limit', f'{_LINKS}, view, view=links'),    # the URI and a flag
])
def test_markdown_refuses_a_control_its_answer_does_not_read(docs, argv, control, answer):
    run, _doc = _run(*argv)
    assert run.returncode == 2, (run.returncode, run.stdout[:300], run.stderr)
    assert f"control '{control}' is not read by this answer ({answer}" in run.stderr, run.stderr
    assert f'{control} is read by: ' in run.stderr, run.stderr


def test_markdown_api_refuses_the_same_request(docs):
    from reveal import api
    with pytest.raises(RequestValidationError, match=r"control 'limit' is not read by this answer \(markdown_link"):
        api.query('markdown://.?view=links', limit=1)


@pytest.mark.parametrize('uri', [
    'markdown://.?where=title=A&match=Body&columns=status&explain&sort=title&limit=1&offset=0',
    'markdown://.?view=aggregate&field=status&where=title=A&match=Body',
    'markdown://.?view=lint&lint-fields=title',
    'markdown://.?view=links',
    'markdown://.?backlinks=b.md',
    'json://data.json?limit=1',  # a sibling noun's reading answer, unchanged
])
def test_markdown_answers_where_its_controls_are_read(docs, uri):
    run, doc = _run(uri)
    assert run.returncode == 0, (run.returncode, run.stderr)
    assert not _unread(doc), doc.get('meta')
