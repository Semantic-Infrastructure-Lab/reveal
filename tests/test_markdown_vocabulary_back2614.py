"""Markdown vocabulary (BACK-2614, D20): what the package must keep, and what its spellings must become.

The fixture is one directory of six documents: front matter of three shapes (guide, reference, draft), one with none,
one with malformed YAML, internal links (one to a missing doc) and a subdirectory, so every view (list, links,
backlinks, aggregate, lint) has something to answer. Every request runs from the fixture root with relative targets,
so no path spelling differs by platform.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

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
    return sorted(Path(row['relative_path']).name for row in doc['results'])


def _rows_in_order(doc):
    return [Path(row['relative_path']).name for row in doc['results']]


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


# --- REDs: what the package must change (each beside a sibling that passes today) ----------------------------------

@pytest.mark.parametrize('term,alone,with_priority', [
    ('title=alpha guide', ['alpha.md'], ['alpha.md']),
    ('title=*alpha*', ['alpha.md'], ['alpha.md']),
    ('type', ['alpha.md', 'beta.md', 'gamma.md', 'orphan.md'], ['alpha.md', 'beta.md', 'gamma.md']),
])
def test_a_where_term_means_the_same_whatever_other_terms_the_request_gives(root, term, alone, with_priority):
    """RED (B1, ruling Q6): one parser, the shared one -- case-insensitive equality and glob, a bare FIELD is 'exists'.
    Today a request of plain terms goes to markdown's own parser (case-sensitive, so the first two answer 0) and a request
    with any operator term to the shared one (where a bare FIELD matches nothing, so the third answers 0)."""
    _, one = _json(root, 'markdown', 'docs', '--where', term)
    _, two = _json(root, 'markdown', 'docs', '--where', term, '--where', 'priority>1')
    assert (_rows(one), _rows(two)) == (alone, with_priority)


def test_priority_alone_is_the_control_for_the_pairs(root):
    _, doc = _json(root, 'markdown', 'docs', '--where', 'priority>1')
    assert _rows(doc) == ['alpha.md', 'beta.md', 'gamma.md']


@pytest.mark.parametrize('terms,rows', [
    (['!type'], ['bad.md', 'plain.md']),                   # a document without front matter misses every field
    (['type!=guide'], ['beta.md', 'orphan.md']),           # ...and has no value to compare
    (['!type', 'priority>1'], []),
    (['type=GUIDE', 'tags=api'], ['alpha.md']),            # equality is case-insensitive; a list matches by item
    (['tags=ap'], []),                                     # an item is equal, not a substring
], ids=lambda value: '&'.join(value) if isinstance(value, list) and value and '.md' not in value[0] else None)
def test_where_terms_follow_the_shared_rules(root, terms, rows):
    """B1 controls (ruling Q6): presence, front-matter-less documents and list items under the one parser."""
    argv = [part for term in terms for part in ('--where', term)]
    _, doc = _json(root, 'markdown', 'docs', *argv)
    assert _rows(doc) == rows


@pytest.mark.parametrize('flags', [
    ['--link-graph', '--lint'],
    ['--lint', '--backlinks', 'alpha.md'],
    ['--backlinks', 'alpha.md', '--aggregate', 'type'],
    ['--link-graph', '--aggregate', 'type'],
    ['--view', 'links', '--lint'],
], ids=lambda flags: ' '.join(flags))
def test_two_selections_are_one_answer_too_many(root, flags):
    """RED (B2): two selectors that pick different answers exit 2 naming both (COMMAND_MODEL "One answer per request");
    today the first in a precedence chain answers, exit 0, and the ledger backstop warns that the other did nothing."""
    run, _ = _json(root, 'markdown', 'docs', *flags)
    named = [flag.lstrip('-') for flag in flags if flag.startswith('--')]
    assert run.returncode == 2 and all(name in run.stderr for name in named), run.stderr
    assert 'unused_flag' not in run.stdout + run.stderr


@pytest.mark.parametrize('flags', [['--link-graph'], ['--lint'], ['--backlinks', 'alpha.md'], ['--aggregate', 'type']])
def test_one_selection_answers(root, flags):
    run, _ = _json(root, 'markdown', 'docs', *flags)
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize('legacy,canonical', [
    (['--view', 'links', '--link-graph'], ['--view', 'links']),
    (['--view', 'lint', '--lint'], ['--view', 'lint']),
    (['--view', 'aggregate', '--field', 'type', '--aggregate', 'type'], ['--view', 'aggregate', '--field', 'type']),
], ids=lambda flags: ' '.join(flags))
def test_an_agreeing_legacy_and_canonical_selection_is_one_setting(root, legacy, canonical):
    """RED (B3): equal meanings are one setting ("Spellings"); today a hand check exits 2 'view conflicts with a legacy
    selector or backlinks target'."""
    run, doc = _json(root, 'markdown', 'docs', *legacy)
    _, expected = _json(root, 'markdown', 'docs', *canonical)
    assert run.returncode == 0, run.stderr
    strip = lambda d: {k: v for k, v in d.items() if k != 'meta'}  # noqa: E731 -- the legacy word's own note differs
    assert strip(doc) == strip(expected)


def test_an_agreeing_selection_on_the_uri_is_one_setting(root):
    """RED (B3), the URI form of the same rule."""
    run, doc = _json(root, 'markdown://docs?view=links&link-graph=true')
    _, expected = _json(root, 'markdown', 'docs', '--view', 'links')
    assert run.returncode == 0, run.stderr
    assert {k: v for k, v in doc.items() if k != 'meta'} == {k: v for k, v in expected.items() if k != 'meta'}


def test_two_different_aggregate_fields_exit_2_naming_both(root):
    """RED (B3): --field and the legacy aggregate word set one field; different values exit 2 naming both spellings
    (the Conflicting-values error, ruling Q2-A); today --field wins silently."""
    run, _ = _json(root, 'markdown', 'docs', '--field', 'type', '--aggregate', 'tags')
    assert run.returncode == 2 and '--field' in run.stderr and '--aggregate' in run.stderr, run.stderr


def test_one_aggregate_field_given_twice_alike_is_the_sibling(root):
    run, _ = _json(root, 'markdown', 'docs', '--view', 'aggregate', '--field', 'type', '--field', 'type')
    assert run.returncode == 0, run.stderr


@pytest.mark.parametrize('underscore,hyphen', [
    ('markdown://docs?body_contains=authentication', 'markdown://docs?body-contains=authentication'),
    ('markdown://docs?lint&lint_fields=priority', 'markdown://docs?lint&lint-fields=priority'),
], ids=['body_contains', 'lint_fields'])
def test_the_underscore_spelling_of_a_hyphenated_key_is_that_key(root, underscore, hyphen):
    """RED (B5, "Key spelling"): today ?body_contains= is read as a front-matter field (0 rows and a typo warning) and
    ?lint_fields= as an unread where term (exit 2)."""
    run, doc = _json(root, underscore)
    _, expected = _json(root, hyphen)
    assert run.returncode == 0, run.stderr
    assert {k: v for k, v in doc.items() if k != 'meta'} == {k: v for k, v in expected.items() if k != 'meta'}


def test_the_underscore_spelling_is_accepted_by_the_python_uri_form(root):
    """RED (B5): api.query('markdown://docs', body_contains=...) raises UnsupportedOverrideError today."""
    from reveal import api
    assert api.query('markdown://docs', body_contains='authentication')['matched_files'] == 2


def test_link_graph_underscore_is_the_sibling(root):
    run, doc = _json(root, 'markdown://docs?link_graph')
    assert run.returncode == 0 and doc['type'] == 'markdown_link_graph'


def test_sort_by_a_front_matter_field_sorts_by_it(root):
    """RED (B6): --sort reads the front matter it is declared to read; today it sorts only fields a row carries, so
    priority is 'not a field of any result' and the rows stay unsorted."""
    run, doc = _json(root, 'markdown', 'docs', '--where', 'priority>0', '--sort', '-priority')
    assert run.returncode == 0
    assert _rows_in_order(doc) == ['gamma.md', 'alpha.md', 'beta.md']
    assert 'unknown_sort_field' not in [w.get('type') for w in _warnings(doc)]


def test_sort_by_a_column_is_the_sibling(root):
    _, doc = _json(root, 'markdown', 'docs', '--where', 'priority>0', '--sort', '-priority', '--columns', 'priority')
    assert _rows_in_order(doc) == ['gamma.md', 'alpha.md', 'beta.md']


def test_explain_without_match_is_a_conflicting_request(root):
    """RED (B7): explain reads the body match; without one it is an invalid request naming match (exit 2), as a control
    another control's value leaves unread is; today it answers the plain listing, exit 0."""
    run, _ = _json(root, 'markdown', 'docs', '--explain')
    assert run.returncode == 2 and 'match' in run.stderr, run.stderr


def test_explain_with_match_is_the_sibling(root):
    run, doc = _json(root, 'markdown', 'docs', '--explain', '--match', 'authentication')
    assert run.returncode == 0 and all('term_counts' in str(row) for row in doc['results'])


@pytest.mark.parametrize('flags', [['--view', 'links'], ['--backlinks', 'alpha.md'], ['--match', 'authentication']],
                         ids=lambda flags: ' '.join(flags))
def test_a_lost_file_is_reported_once_in_the_json_and_names_no_absolute_path(lossy, flags):
    """RED (B10, "Transports"): in JSON mode a diagnostic the JSON carries (unreadable_files) is not printed on stderr as
    well, and no error string names an absolute path; today a 'Failed to read /abs/...' log line does both. A real process:
    the in-process runner does not capture the logging handler's stderr."""
    run = _process(lossy, 'markdown', 'docs', *flags)
    doc = json.loads(run.stdout)
    assert run.returncode == 3 and 'unreadable_files' in [w.get('type') for w in _warnings(doc)]
    assert str(lossy) not in run.stderr and 'beta.md' not in run.stderr, run.stderr


def test_a_lost_file_on_the_listing_is_the_sibling(lossy):
    run = _process(lossy, 'markdown', 'docs')
    assert run.returncode == 3 and str(lossy) not in run.stderr and 'beta.md' not in run.stderr, run.stderr


def _process(cwd, *argv):
    return subprocess.run([sys.executable, '-m', 'reveal', *argv, '--format', 'json'], cwd=cwd, capture_output=True,
                          text=True, encoding='utf-8', timeout=120, env={**os.environ, 'REVEAL_DISK_CACHE': '0'})


def test_the_aggregate_view_without_a_field_names_the_flag(root):
    """RED (B12): the refusal names --field, the flag the subcommand takes; today 'aggregate view requires field'."""
    run, _ = _json(root, 'markdown', 'docs', '--view', 'aggregate')
    assert run.returncode == 2 and '--field' in run.stderr, run.stderr


def test_an_unknown_backlinks_doc_exits_2_naming_it_and_the_tree(root):
    """RED (rule 9, ruling Q5): a backlinks target no document in the tree is exits 2 naming the doc and the tree
    searched; today found: false, exit 0."""
    run, _ = _json(root, 'markdown', 'docs', '--backlinks', 'nosuch.md')
    assert run.returncode == 2 and 'nosuch.md' in run.stderr and 'docs' in run.stderr, run.stderr


def test_a_known_backlinks_doc_with_no_inbound_link_still_answers(root):
    """Sibling: orphan.md exists and nothing links to it -- an answer, not a miss."""
    run, doc = _json(root, 'markdown', 'docs', '--backlinks', 'orphan.md')
    assert run.returncode == 0 and doc['linked_by'] == []


def test_an_aggregate_field_no_document_has_warns_as_an_open_field(root):
    """RED (ruling Q5): the shared open-field unknown_filter_field warning, exit 0; today an empty table and nothing."""
    run, doc = _json(root, 'markdown', 'docs', '--view', 'aggregate', '--field', 'zzz')
    assert run.returncode == 0
    assert 'unknown_filter_field' in [w.get('type') for w in _warnings(doc)]


def test_a_where_field_no_document_has_is_the_sibling(root):
    run, doc = _json(root, 'markdown', 'docs', '--where', 'zzz=1')
    assert run.returncode == 0 and 'unknown_filter_field' in [w.get('type') for w in _warnings(doc)]


def test_an_empty_tree_stays_an_answer(root):
    """Ruling Q5 control: a directory with no documents is 0 of 0, exit 0."""
    (root / 'empty').mkdir()
    run, doc = _json(root, 'markdown', 'empty')
    assert run.returncode == 0 and doc['total_files'] == 0


@pytest.mark.parametrize('legacy,row,replacement', [
    (['--link-graph'], 'param:markdown.link-graph', '--view links'),
    (['--lint'], 'param:markdown.lint', '--view lint'),
    (['--aggregate', 'type'], 'param:markdown.aggregate', '--view aggregate --field'),
], ids=['link-graph', 'lint', 'aggregate'])
def test_the_legacy_selectors_note_their_rows(root, legacy, row, replacement):
    """RED (D20; rulings Q1, Q2-C): link-graph and lint translate to --view links / --view lint with a row; aggregate is
    a standalone legacy word whose row names --view aggregate --field F. Each answers as its replacement."""
    run, doc = _json(root, 'markdown', 'docs', *legacy)
    assert run.returncode == 0
    note = _notes(doc).get(row)
    assert note is not None and replacement in note['replacement'], _notes(doc)


@pytest.mark.parametrize('uri,canonical', [
    ('markdown://docs?link-graph', 'reveal markdown docs --view links'),
    ('markdown://docs?lint', 'reveal markdown docs --view lint'),
], ids=['link-graph', 'lint'])
def test_a_legacy_selector_request_note_renders_the_view(root, uri, canonical):
    """RED: the request note renders the canonical request, never a spelling that itself retires (today --link-graph,
    --lint)."""
    _, doc = _json(root, uri)
    assert _notes(doc)['request:markdown']['replacement'] == canonical


def test_a_view_request_note_is_the_sibling(root):
    _, doc = _json(root, 'markdown://docs?view=links')
    assert _notes(doc)['request:markdown']['replacement'] == 'reveal markdown docs --view links'


def test_the_aggregate_word_request_note_renders_view_and_field(root):
    """Ruling Q2-A (re-ruled from Q2-C after M3): aggregate=F translates to two controls, so its request note renders the
    full canonical request, --view aggregate --field F, never the retiring --aggregate F."""
    run, doc = _json(root, 'markdown://docs?aggregate=type')
    assert run.returncode == 0 and doc['type'] == 'markdown_aggregate'
    assert _notes(doc)['request:markdown']['replacement'] == 'reveal markdown docs --view aggregate --field type'
