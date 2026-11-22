"""Markdown vocabulary (BACK-2614, D20): what the package must keep, and what its spellings must become.

The fixture is one directory of six documents: front matter of three shapes (guide, reference, draft), one with none,
one with malformed YAML, internal links (one to a missing doc) and a subdirectory, so every view (list, links,
backlinks, aggregate, lint) has something to answer. Every request runs from the fixture root with relative targets,
so no path spelling differs by platform.
"""
import json
import os

import pytest

from conftest import _run_reveal_in, without_request_notes

DOCS = {
    'alpha.md': ('---\ntitle: Alpha Guide\ntype: guide\npriority: 5\ntags: [auth, api]\n---\n# Alpha\n\n'
                 'Authentication body text. See [beta](beta.md) and [sub](sub/gamma.md).\n'),
    'beta.md': ('---\ntitle: Beta\ntype: reference\npriority: 2\ntags: [api]\n---\n# Beta\n\n'
                'Body about tokens. Link to [alpha](alpha.md) and [missing](nope.md).\n'),
    'sub/gamma.md': '---\ntitle: Gamma\ntype: guide\npriority: 9\n---\n# Gamma\n\nauthentication authentication deep text.\n',
    'plain.md': '# No frontmatter\n\nJust body, links [alpha](alpha.md).\n',
    'bad.md': '---\ntitle: [unclosed\n---\n# Bad yaml\n',
    'orphan.md': '---\ntitle: Orphan\ntype: draft\n---\nNothing links here.\n',
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    for name, text in DOCS.items():
        path = tmp_path / 'docs' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(root, *argv):
    run = _run_reveal_in(root, *argv, '--format', 'json')
    try:
        doc = json.loads(run.stdout)
    except ValueError:
        doc = None
    return run, doc


def _warnings(doc):
    return (doc or {}).get('meta', {}).get('warnings', [])


def _rows(doc):
    return sorted(row['relative_path'].rsplit('/', 1)[-1] for row in doc['results'])


def _rows_in_order(doc):
    return [row['relative_path'].rsplit('/', 1)[-1] for row in doc['results']]


def _notes(doc):
    return {w['field']: w for w in _warnings(doc) if w.get('code') == 'retired_spelling'}


VIEWS = [
    ([], 'markdown_query'),
    (['--where', 'type=guide'], 'markdown_query'),
    (['--match', 'authentication'], 'markdown_query'),
    (['--columns', 'priority'], 'markdown_query'),
    (['--view', 'links'], 'markdown_link_graph'),
    (['--backlinks', 'alpha.md'], 'markdown_backlinks'),
    (['--view', 'aggregate', '--field', 'type'], 'markdown_aggregate'),
    (['--view', 'lint'], 'markdown_frontmatter_lint'),
    (['--view', 'lint', '--lint-fields', 'priority'], 'markdown_frontmatter_lint'),
]
_IDS = [' '.join(flags) or 'list' for flags, _ in VIEWS]


# --- preservation pins: these hold before and after the package --------------------------------------------------

@pytest.mark.parametrize('flags,kind', VIEWS, ids=_IDS)
def test_each_view_answers_alike_on_the_subcommand_and_the_uri_with_flags(root, flags, kind):
    cli, a = _json(root, 'markdown', 'docs', *flags)
    uri, b = _json(root, 'markdown://docs', *flags)
    assert cli.returncode == uri.returncode == 0, (cli.stderr, uri.stderr)
    assert a['type'] == kind and a == without_request_notes(b)


@pytest.mark.parametrize('flags,kind', VIEWS, ids=_IDS)
def test_each_view_answers_alike_on_the_python_noun_form(root, flags, kind):
    from reveal import api
    keywords: dict = {}
    for flag, value in zip(flags[::2], flags[1::2]):
        keywords[flag.lstrip('-').replace('-', '_')] = value
    _, cli = _json(root, 'markdown', 'docs', *flags)
    assert api.query('markdown', 'docs', **keywords) == cli


@pytest.mark.parametrize('flags,kind', VIEWS, ids=_IDS)
def test_each_view_answers_alike_through_mcp(root, flags, kind):
    pytest.importorskip('mcp')
    from reveal import mcp_server
    _, cli = _json(root, 'markdown', 'docs', *flags)
    assert json.loads(mcp_server.reveal_run(['markdown', 'docs', *flags, '--format', 'json'])) == cli


def test_the_views_answer_the_fixture(root):
    _, listing = _json(root, 'markdown', 'docs')
    assert _rows(listing) == ['alpha.md', 'bad.md', 'beta.md', 'gamma.md', 'orphan.md', 'plain.md']
    _, guides = _json(root, 'markdown', 'docs', '--where', 'type=guide')
    assert _rows(guides) == ['alpha.md', 'gamma.md']
    _, body = _json(root, 'markdown', 'docs', '--match', 'authentication', '--match', 'deep')
    assert _rows(body) == ['gamma.md']
    _, graph = _json(root, 'markdown', 'docs', '--view', 'links')
    assert graph['total_edges'] == 4 and sorted(graph['isolated']) == ['bad.md', 'orphan.md']
    _, back = _json(root, 'markdown', 'docs', '--backlinks', 'alpha.md')
    assert back['found'] is True and sorted(back['linked_by']) == ['beta.md', 'plain.md']
    _, agg = _json(root, 'markdown', 'docs', '--view', 'aggregate', '--field', 'type')
    assert {row['value']: row['count'] for row in agg['aggregate']} == {'guide': 2, 'reference': 1, 'draft': 1}
    _, lint = _json(root, 'markdown', 'docs', '--view', 'lint')
    assert lint['issues_found'] == 2
    _, required = _json(root, 'markdown', 'docs', '--view', 'lint', '--lint-fields', 'priority')
    assert required['issues_found'] == 3


def test_legacy_columns_and_body_words_answer_as_their_replacements_with_their_rows(root):
    _, columns = _json(root, 'markdown', 'docs', '--columns', 'priority')
    run, fields = _json(root, 'markdown://docs?fields=priority')
    assert run.returncode == 0 and without_request_notes(fields) == columns
    _, match = _json(root, 'markdown', 'docs', '--match', 'authentication')
    run, body = _json(root, 'markdown', 'docs', '--body-contains', 'authentication')
    assert run.returncode == 0 and 'param:markdown.body-contains' in _notes(body)
    assert body['results'] == match['results']


@pytest.fixture
def lossy(root):
    """beta.md unreadable: required document evidence is lost."""
    if os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0):
        pytest.skip('chmod 000 does not deny reading here')
    target = root / 'docs' / 'beta.md'
    target.chmod(0)
    yield root
    target.chmod(0o644)


@pytest.mark.parametrize('flags,kind', VIEWS, ids=_IDS)
def test_partial_source_loss_is_incomplete_on_every_view(lossy, flags, kind):
    run, doc = _json(lossy, 'markdown', 'docs', *flags)
    assert run.returncode == 3, run.stderr
    types = [w.get('type') for w in _warnings(doc)]
    assert 'unreadable_files' in types and 'analysis_incomplete' in types
