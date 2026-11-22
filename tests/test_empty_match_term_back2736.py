"""An empty match term is an invalid request (COMMAND_MODEL "Empty match term", Scott 2026-11-22, BACK-2736).

An empty or whitespace-only term in any spelling of a match or a where (``--match ''``, ``?match=``, ``?search=``,
``?filter=``, ``?body-contains=``, ``--where ''``), in a standalone word or legacy filter that a term replaces (Claude
``?search=``, ``?contains=``, ``--name``/``--search``/``--type``; Codex ``?search=``), and the term-less search a Claude
address or view selects (``claude://search``, ``--view search``) exits 2 with one message, ``SPELLING needs a term:
EXAMPLE``, before the answer is selected, on every transport. Whitespace is no term, as xlsx already ruled.

Before (measured at 115578c6): Markdown dropped the term and listed every document; Claude matched every message of a
session, every history entry and every message of /messages, listed every session on the root ``?search=``, on
``?filter=``, on ``--where ''`` and ``--where session~=``, answered ``claude://search`` and ``--view search`` with no term,
and refused ``sessions --match ''`` as "search selector is unsupported on this resource"; Codex refused ``--match ''`` as
"control 'match' is not read by this answer" and listed every session on ``?search=``, ``?filter=``, ``--where ''`` and
``--where session~=``; a whitespace term matched every row that holds a space. XLSX and every other where already exited
2 (their messages move to the shared one). Conformance column 27 holds the refusal per spelling; this file holds the
requests the column does not reach and the siblings that must not change.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.base import get_adapter_class
from reveal.cli.routing.declared import declared_adapter_class

SESSION = 'claude://session/my-session'


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Claude's and Codex's recorded homes, two Markdown documents, a Python file, a JSON file and the Sales workbook."""
    from claude_session_fixture import build_claude_home
    from codex_session_fixture import build_codex_home
    from test_retirements_back2066 import sample_workbook
    claude_adapter = declared_adapter_class('claude')
    claude = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(claude_adapter, 'CLAUDE_HOME', claude)
    monkeypatch.setattr(claude_adapter, 'CONVERSATION_BASE', claude / 'projects')
    codex_adapter = get_adapter_class('codex')
    codex = build_codex_home(tmp_path / 'codex-home')
    monkeypatch.setattr(codex_adapter, 'CODEX_HOME', codex)
    monkeypatch.setattr(codex_adapter, 'CODEX_DB', codex / 'state_5.sqlite')
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'guide.md').write_text('---\ntitle: Guide\n---\n# Guide\n\nBody text.\n', encoding='utf-8')
    (docs / 'notes.md').write_text('# Notes\n\nOther words here.\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('def serve(x):\n    return x\n', encoding='utf-8')
    (tmp_path / 'data.json').write_text('[{"n": 1}, {"n": 2}]', encoding='utf-8')
    sample_workbook(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    try:
        doc = json.loads(run.stdout)
    except ValueError:
        doc = {}
    return run, doc if isinstance(doc, dict) else {}


def _error(run, doc):
    return doc.get('error') if isinstance(doc.get('error'), str) else run.stderr


# (argv, the spelling the refusal names): every empty-term request the column does not enumerate per spelling, and the
# ones it does where the answer used to differ (a repeat beside a real term, a blank term, a path's own reader).
REFUSED = [
    (('claude', 'sessions', '--match', ''), '--match'),
    (('claude', 'sessions', '--match', ' '), '--match'),
    (('claude', 'sessions', '--match', 'auth', '--match', ''), '--match'),
    (('claude://sessions/?match=',), 'match'),
    (('claude://sessions/?match=%20',), 'match'),  # a percent-encoded blank decodes to whitespace
    (('claude://sessions/?search=',), 'search'),
    (('claude://?search=',), 'search'),  # listed every session ("Empty root search historically selects ...")
    (('claude://sessions/?filter=',), 'filter'),
    (('claude', 'sessions', '--where', ''), '--where'),
    (('claude', 'sessions', '--where', 'session~='), 'session~='),  # ?filter= is this term, so it refuses alike
    (('claude', 'history', '--match', ''), '--match'),
    ((f'{SESSION}?search=',), 'search'),
    ((SESSION, '--match', ''), '--match'),
    ((f'{SESSION}/messages?contains=',), 'contains'),
    ((f'{SESSION}/messages', '--match', ''), '--match'),
    (('claude://search',), 'search'),  # the address of a search with no term (ruling 2a)
    (('claude://search/',), 'search'),
    (('claude', 'search'), 'search'),
    ((SESSION, '--view', 'search'), 'view=search'),  # "view=search uses content search, with match supplying the text"
    (('claude', 'sessions', '--name', ''), '--name'),
    (('claude', 'sessions', '--search', ''), '--search'),
    (('claude', 'history', '--name', ''), '--name'),
    (('codex', 'sessions', '--match', ''), '--match'),
    (('codex', 'sessions', '--match', ' '), '--match'),
    (('codex://sessions/?match=',), 'match'),
    (('codex://sessions/?search=',), 'search'),
    (('codex://sessions/?filter=',), 'filter'),
    (('codex', 'sessions', '--where', ''), '--where'),
    (('codex', 'sessions', '--where', 'session~='), 'session~='),
    (('markdown', 'docs', '--match', ''), '--match'),
    (('markdown', 'docs', '--match', ' '), '--match'),
    (('markdown://docs?match=',), 'match'),
    (('markdown://docs?body-contains=',), 'body-contains'),
    (('markdown', 'docs', '--body-contains', ''), '--body-contains'),
    (('markdown', 'docs', '--where', ''), '--where'),
    (('xlsx', 'book.xlsx', '--match', ''), '--match'),
    (('xlsx', 'book.xlsx', '--match', ' '), '--match'),
    (('xlsx://book.xlsx?search=',), 'search'),
    (('ast', '.', '--where', ''), '--where'),
    (('ast', '.', '--where', ' '), '--where'),
    (('json', 'data.json', '--where', ''), '--where'),
    (('metrics', '.', '--where', ''), '--where'),
]


@pytest.mark.parametrize('argv,spelling', REFUSED, ids=[' '.join(argv) for argv, _ in REFUSED])
def test_an_empty_term_is_an_invalid_request_naming_its_spelling(home, argv, spelling):
    run, doc = _json(*argv)
    message = _error(run, doc)
    assert run.returncode == 2 and f'{spelling} needs a term' in message, (run.returncode, message[:300])
    for misleading in ('is not read by this answer', 'search selector is unsupported'):
        assert misleading not in message


# A nonblank term in the same spelling answers (exit 0) with rows: the positive siblings of REFUSED.
ANSWERED = [
    (('claude', 'sessions', '--match', 'auth'), 'matches'),
    (('claude://?search=auth',), 'matches'),
    (('claude', 'sessions', '--where', 'session~=2627'), 'recent_sessions'),
    (('claude', 'history', '--match', 'auth'), 'entries'),
    ((SESSION, '--match', 'auth'), 'matches'),
    ((SESSION, '--view', 'search', '--match', 'auth'), 'matches'),
    (('claude://search/auth',), 'matches'),
    (('codex', 'sessions', '--match', 'auth'), 'sessions'),
    (('codex://sessions/?search=auth',), 'sessions'),
    (('codex', 'sessions', '--where', 'session~=auth'), 'sessions'),
    (('markdown', 'docs', '--match', 'Body'), 'results'),
    (('xlsx', 'book.xlsx', '--match', 'total'), 'matches'),
]


@pytest.mark.parametrize('argv,rows', ANSWERED, ids=[' '.join(argv) for argv, _ in ANSWERED])
def test_a_nonblank_term_still_answers(home, argv, rows):
    run, doc = _json(*argv)
    assert run.returncode == 0, run.stderr
    found = doc.get(rows) or doc.get('total_matches')
    assert found, (rows, sorted(doc))


def test_markdown_no_longer_drops_the_term_and_lists_every_document(home):
    """The term was dropped (``strings``), so ``--match ''`` answered the bare listing."""
    empty, _doc = _json('markdown', 'docs', '--match', '')
    bare, listing = _json('markdown', 'docs')
    assert bare.returncode == 0 and len(listing['results']) == 2
    assert empty.returncode == 2


@pytest.mark.parametrize('call,spelling', [
    (('claude://sessions', {'match': ''}), 'match'),
    (('claude://history', {'match': ''}), 'match'),
    (('claude://sessions?search=', {}), 'search'),
    (('codex://sessions', {'match': ''}), 'match'),
    (('codex://sessions', {'where': ['']}), 'where'),
    (('codex://sessions?filter=', {}), 'filter'),
    (('markdown://docs', {'match': ''}), 'match'),
    (('markdown://docs', {'match': ['Body', ' ']}), 'match'),
    (('xlsx://book.xlsx', {'match': ''}), 'match'),
    (('ast://.', {'where': ''}), 'where'),
])
def test_the_typed_api_raises_the_request_validation_error(home, call, spelling):
    from reveal import api
    from reveal.errors import RequestValidationError
    uri, keywords = call
    with pytest.raises(RequestValidationError, match=f'{spelling} needs a term'):
        api.query(uri, **keywords)


@pytest.mark.parametrize('argv,spelling', [
    (['claude', 'sessions', '--match', ''], '--match'),
    (['codex://sessions/?search='], 'search'),
    (['markdown', 'docs', '--match', ''], '--match'),
])
def test_mcp_reports_the_refusal(home, argv, spelling):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_run
    try:
        shown = reveal_run([*argv, '--format', 'json'])
    except Exception as exc:  # a tool error is the refusal on MCP
        shown = f'error: {exc}'
    assert 'rror' in shown and f'{spelling} needs a term' in shown, shown[:300]


def test_an_empty_exclude_still_refuses_as_a_pattern(home):
    """Negative control: ``exclude`` is a walk control, not a term; its empty URI value already exited 2, and since
    BACK-2730 the same rule names what it needs, a pattern, not a term."""
    run, doc = _json('metrics://.?exclude=')
    assert run.returncode == 2 and 'exclude needs a pattern: --exclude PATTERN' in _error(run, doc)
