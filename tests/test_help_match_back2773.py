"""Help search binds as the shared match control (D21, BACK-2773; the manager's rulings S5-A, S6, S7 on the vocab V1
inventory).

Before, help declared ``search`` and ``top`` with no flag and no subcommand, and the answer re-parsed the URI's query
text instead of reading the bound controls: ``reveal help://search --search TERM`` landed on the file route's ``--name``
and answered "No search term", exit 1; ``--match`` was an unsupported control; an empty term exited 1.

Now ``help`` is a declared subcommand (``reveal help [TOPIC] [--match TEXT] [--limit N]``): ``reveal help://search
--match TERM``, ``reveal help search --match TERM`` and ``reveal help --match TERM`` answer the search on the CLI, the
URI, ``api.query`` and MCP; ``--search``/``?search=`` and ``--top``/``?top=`` answer as ``--match``/``--limit`` with
their replaced-by notes; ``help://search/TERM`` answers with a note naming ``reveal help://search --match TERM``; an
empty or missing term is an invalid request, exit 2 (BACK-2736). A topic page that names nothing that exists exits 2
(D6), not 1.
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.cli

TERM = 'callers'


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    doc = json.loads(run.stdout) if run.returncode in (0, 1, 3) and run.stdout.strip() else None
    return run, doc


def _hits(doc):
    return [hit['command'] for hit in doc['hits']]


def _noted(doc, field):
    return any(w.get('type') == 'retired_spelling' and w.get('field') == field for w in doc.get('meta', {}).get('warnings', []))


@pytest.fixture(scope='module')
def canonical():
    """The search as the one spelling names it."""
    run, doc = _json('help://search', '--match', TERM)
    assert run.returncode == 0, run.stderr
    assert doc['type'] == 'help_search' and doc['query'] == TERM and doc['hits']
    return doc


def test_the_legacy_search_flag_reaches_the_search(canonical):
    """The binding bug: the declared ``search`` never reached the answer (it answered "No search term", exit 1)."""
    run, doc = _json('help://search', '--search', TERM)
    assert run.returncode == 0, run.stderr
    assert doc['type'] == 'help_search' and _hits(doc) == _hits(canonical)
    assert _noted(doc, 'param:help.search')
    assert 'No search term' not in run.stderr + run.stdout
    assert '--name PATTERN' not in run.stderr  # the file route's replacement, printed on a help request


@pytest.mark.parametrize('argv', [
    ('help://search', '--match', TERM),
    ('help', 'search', '--match', TERM),
    ('help', '--match', TERM),  # no topic: the search, as the usage line teaches
    ('help://', '--match', TERM),
], ids=['uri', 'subcommand-topic', 'subcommand', 'uri-index'])
def test_match_answers_the_search_on_every_cli_form(canonical, argv):
    run, doc = _json(*argv)
    assert run.returncode == 0, run.stderr
    assert doc['type'] == 'help_search' and doc['query'] == TERM and _hits(doc) == _hits(canonical)
    assert not any(w.get('type') == 'retired_spelling' for w in doc.get('meta', {}).get('warnings', []))


def test_the_api_and_mcp_answer_the_same_search(canonical):
    from reveal import api
    for kwargs in ({'match': TERM}, {'match': [TERM]}):
        assert _hits(api.query('help://search', **kwargs)) == _hits(canonical)
    assert _hits(api.query('help', 'search', match=TERM)) == _hits(canonical)
    assert _hits(api.query(f'help://search?match={TERM}')) == _hits(canonical)
    mcp = pytest.importorskip('reveal.mcp_server')
    text = mcp.reveal_run(['help://search', '--match', TERM])
    assert text.startswith(f"# Help Search: '{TERM}'") and canonical['hits'][0]['command'] in text


@pytest.mark.parametrize('argv, spelling', [
    (('help://search',), 'search'),  # the term-less search address (the claude://search precedent)
    (('help', 'search'), 'search'),
    (('help://search/',), 'search'),
    (('help://search', '--match', ''), '--match'),
    (('help://search', '--match', '  '), '--match'),
    (('help://search', '--search', ''), '--search'),
    (('help://search?search=',), 'search'),
    (('help://search?search=%20%20',), 'search'),
])
def test_an_empty_or_missing_term_is_an_invalid_request(argv, spelling):
    run = _run_reveal_direct(*argv)
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert f'{spelling} needs a term: --match TEXT' in run.stderr


def test_an_empty_term_raises_on_the_api_and_refuses_on_mcp():
    from reveal import api
    from reveal.errors import RequestValidationError
    for uri, kwargs in (('help://search', {}), ('help://search', {'match': ''}), ('help://search', {'search': ''}),
                        ('help://search?search=', {})):
        with pytest.raises(RequestValidationError, match='needs a term: --match TEXT'):
            api.query(uri, **kwargs)
    mcp = pytest.importorskip('reveal.mcp_server')
    assert 'needs a term: --match TEXT' in mcp.reveal_run(['help://search'])


def test_the_query_string_and_the_path_term_answer_with_a_note_naming_match(canonical):
    run, doc = _json(f'help://search?search={TERM}')
    assert run.returncode == 0 and _hits(doc) == _hits(canonical)
    request = [w for w in doc.get('meta', {}).get('warnings', []) if w.get('field') == 'request:help']
    assert request and f'reveal help://search --match {TERM}' in request[0]['message']
    run, doc = _json(f'help://search/{TERM}')
    assert run.returncode == 0 and _hits(doc) == _hits(canonical)
    assert _noted(doc, 'target:help.search-term')
    text = _run_reveal_direct(f'help://search/{TERM}')
    assert ('note: help://search/TERM is deprecated and works until 1.0; use reveal help://search --match TERM.'
            in text.stderr)


def test_limit_caps_the_hits_and_top_is_its_noted_legacy_word():
    total = _json('help://search', '--match', 'a', '--limit', '0')[1]
    assert total['count'] > 3 and not any(w.get('field') == 'hits' for w in total.get('meta', {}).get('warnings', []))
    capped = _json('help://search', '--match', 'a', '--limit', '3')[1]
    assert capped['count'] == 3
    cut = next(w for w in capped['meta']['warnings'] if w.get('field') == 'hits')
    assert cut['total'] == total['count'] and '--limit N' in cut['message']
    for argv in (('--top', '3'), ('--limit', '3')):
        run, doc = _json('help://search', '--match', 'a', *argv)
        assert run.returncode == 0 and doc['hits'] == capped['hits']
        assert _noted(doc, 'param:help.top') is (argv[0] == '--top')
    from reveal import api
    assert api.query('help://search', match='a', top=3)['hits'] == capped['hits']
    assert len(_json('help://search', '--match', 'a')[1]['hits']) == 20  # the default cap
    assert _json('help://search', '--match', 'a', '--all')[1]['count'] == total['count']
    bad = _run_reveal_direct('help://search', '--match', 'a', '--limit', '-1')
    assert bad.returncode == 2 and 'limit must be >= 0' in bad.stderr


def test_repeated_terms_and_as_the_words_of_one_term_do():
    one = _json('help://search', '--match', 'find callers', '--limit', '0')[1]
    two = _json('help://search', '--match', 'find', '--match', 'callers', '--limit', '0')[1]
    assert one['hits'] and one['hits'] == two['hits']


def test_another_topic_refuses_the_search_controls():
    run = _run_reveal_direct('help://quick', '--match', TERM)
    assert run.returncode == 2 and "control 'match' is not read by this answer" in run.stderr


@pytest.mark.parametrize('argv, page', [
    (('help://quick',), 'help_quick'),
    (('help', 'quick'), 'help_quick'),
    (('help://', 'quick'), 'help_quick'),  # the positional topic keeps its note until the cut
    (('help',), 'help'),
    (('help://ast/workflows',), 'help_section'),
    (('help://reveal',), 'adapter_help'),  # an adapter's own help data, in the answer envelope
])
def test_every_topic_answers_its_page_in_the_answer_envelope(argv, page):
    run, doc = _json(*argv)
    assert run.returncode == 0, run.stderr
    assert doc['type'] == page and doc['source'].startswith('help://') and doc['source_type'] == 'runtime'


def test_the_text_page_is_the_topic_not_the_index():
    run = _run_reveal_direct('help', 'quick')
    assert run.returncode == 0 and 'Quick Reference' in run.stdout and 'Reveal Help System' not in run.stdout


@pytest.mark.parametrize('uri', ['help://ast/bogus', 'help://schemas/bogus', 'help://examples/bogus'])
def test_a_page_that_names_nothing_is_an_invalid_request(uri):
    """D6: an address that names nothing that exists is exit 2 (it exited 1, the findings code)."""
    run = _run_reveal_direct(uri)
    assert run.returncode == 2, (run.returncode, run.stderr)
