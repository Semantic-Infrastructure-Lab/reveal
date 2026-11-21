"""BACK-2726: the guide-migration script rewrites a documented URI request as the request note's canonical request.

The script (``scripts/migrate_doc_uri_examples.py``) finds examples with the executable-docs gate's extractor and
renders them with ``canonical.render_uri_request``. These tests hold its edges on synthetic docs: what it rewrites, and
what it must leave (a sentence or comment naming a retired spelling, a resource URI with no options, a request with no
canonical form, a twin or undeclared scheme), and they run each rewrite of the finished nouns' guides beside its original
on the named doc fixture: same JSON (the echoed command and the request note aside) and same exit.
"""
import json
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import migrate_doc_uri_examples as migrate  # noqa: E402
from test_canonical_request_back2716 import _without_command  # noqa: E402
from test_example_recipes_run import (_fixture_names, _named_fixture_skip, _without_format,  # noqa: E402,F401
                                      named_harness)

FINISHED_NOUNS = ('json', 'imports', 'calls', 'claude', 'metrics', 'overview', 'contracts', 'patches')
FINISHED_GUIDES = tuple(f'adapters/{name}' for name in (
    'JSON_ADAPTER_GUIDE.md', 'IMPORTS_ADAPTER_GUIDE.md', 'CALLS_ADAPTER_GUIDE.md', 'CLAUDE_ADAPTER_GUIDE.md',
    'METRICS_ADAPTER_GUIDE.md', 'STATS_ADAPTER_GUIDE.md', 'OVERVIEW_ADAPTER_GUIDE.md', 'CONTRACTS_ADAPTER_GUIDE.md',
    'PATCHES_ADAPTER_GUIDE.md'))


def _docs(tmp_path, body):
    docs = tmp_path / 'reveal' / 'docs'
    (docs / 'guides').mkdir(parents=True)
    (docs / 'guides' / 'G.md').write_text(body, encoding='utf-8')
    return docs


def _planned(tmp_path, body, nouns=None):
    docs = _docs(tmp_path, body)
    return {e.line: e for e in migrate.plan(['guides/G.md'], nouns, docs=docs)['guides/G.md']}, docs


def _fenced(*lines):
    return '```bash\n' + '\n'.join(lines) + '\n```\n'


def test_a_query_uri_becomes_its_subcommand_and_keeps_its_flags_pipes_and_comment(tmp_path):
    line = "reveal 'calls://src?callers=main&depth=2' --format json | grep x   # who calls main"
    planned, docs = _planned(tmp_path, _fenced(line))
    assert planned[line].kind == 'rewrite'
    assert planned[line].new_line == 'reveal calls src --callers main --depth 2 --format json | grep x   # who calls main'
    text, done = migrate.rewrite_text((docs / 'guides' / 'G.md').read_text(encoding='utf-8'), planned.values())
    assert done == 1 and planned[line].new_line in text and line not in text


def test_a_resource_keeps_its_address_and_takes_the_flags(tmp_path):
    """A resource scheme renders as its URI followed by flags, as the request note says (D20 rule 2)."""
    planned, _ = _planned(tmp_path, _fenced("reveal 'json://data.json/users?age>25&limit=5'",
                                            "reveal 'claude://session/abc?tools=Bash&errors'"))
    assert [e.new_line for e in planned.values()] == ["reveal json://data.json/users --where 'age>25' --limit 5",
                                                      'reveal claude://session/abc --errors --tools Bash']


def test_a_sentence_naming_a_retired_spelling_as_deprecated_stays(tmp_path):
    """Negative control: prose is never an example, and a fenced line that says its spelling is deprecated is left."""
    prose = "The legacy `reveal 'calls://src?callers=main'` spelling is deprecated; use the subcommand.\n"
    fenced = "reveal 'calls://src?callers=main'   # deprecated: use reveal calls src --callers main"
    body = prose + _fenced(fenced)
    planned, docs = _planned(tmp_path, body)
    assert list(planned) == [fenced]
    assert (planned[fenced].kind, planned[fenced].reason) == ('left', migrate.NAMES_DEPRECATED)
    text, done = migrate.rewrite_text(body, planned.values())
    assert (text, done) == (body, 0)


def test_a_resource_uri_without_options_is_no_example_to_rewrite(tmp_path):
    """Negative control: a resource URI with no query string is already the canonical form."""
    body = _fenced('reveal claude://session/abc', 'reveal json://data.json/users', "reveal 'git://app.py@main'")
    planned, _ = _planned(tmp_path, body)
    assert planned == {}
    assert migrate.rewrite_text(body, planned.values()) == (body, 0)


def test_a_request_with_no_canonical_form_is_reported_not_rewritten(tmp_path):
    """Calls ?format=dot has no --format value; Claude's standalone ?search has no flag: each is left with the
    renderer's reason, and the binder's refusal (?tools without a value) is reported as such."""
    dot, search, tools = ("reveal 'calls://src?callers=main&format=dot'", "reveal 'claude://sessions?search=foo'",
                          "reveal 'claude://session/abc?tools'")
    planned, docs = _planned(tmp_path, _fenced(dot, search, tools))
    assert planned[dot].reason == f"{migrate.UNRENDERABLE}: --format does not offer 'dot'"
    assert planned[search].reason == f'{migrate.UNRENDERABLE}: search has no flag on this noun'
    assert planned[tools].reason.startswith(f'{migrate.BINDER_REJECTS}: ')
    assert all(e.kind == 'left' for e in planned.values())
    body = (docs / 'guides' / 'G.md').read_text(encoding='utf-8')
    assert migrate.rewrite_text(body, planned.values()) == (body, 0)


def test_twin_and_undeclared_schemes_and_other_nouns_are_left_with_their_reason(tmp_path):
    stats, xlsx, ast = ("reveal 'stats://src?hotspots=true'", "reveal 'xlsx://book.xlsx?sheet=Sales'",
                        "reveal 'ast://src?kind=function'")
    planned, _ = _planned(tmp_path, _fenced(stats, xlsx, ast), nouns=['calls'])
    assert planned[stats].reason == migrate.NO_REQUEST_NOTE_TWIN
    assert planned[xlsx].reason == migrate.NO_REQUEST_NOTE_UNDECLARED
    assert planned[ast].reason == migrate.OTHER_NOUN
    planned, _ = _planned(tmp_path / 'all', _fenced(ast))
    assert planned[ast].new_line == 'reveal ast src --kind function'


def test_lines_the_script_cannot_place_or_should_not_touch_are_left(tmp_path):
    shown = 'reveal \'calls://src?callers=main\'   # not valid'
    several = "reveal 'imports://src?unused' && reveal 'imports://tests?unused'"
    pair = "reveal 'metrics://src?view=hotspots'   # the same answer as a URI"
    placeholder, variable = "reveal 'calls://src?callers=<name>'", 'reveal "metrics://$DIR?view=hotspots"'
    both = "reveal 'calls://src?sort=-callers' --sort name"
    continued = "reveal 'calls://src?callers=main' --format=json | \\\n    jq '.levels'"
    planned, _ = _planned(tmp_path, _fenced(shown, several, pair, placeholder, variable, both, continued))
    reasons = {line.split(' ', 2)[1]: e.reason for line, e in planned.items()}
    assert planned[shown].reason == migrate.SHOWN_FAILING
    assert planned[several].reason == migrate.SEVERAL_COMMANDS
    assert planned[pair].reason == migrate.SHOWS_THE_URI
    assert planned[placeholder].reason == planned[variable].reason == migrate.PLACEHOLDER
    assert planned[both].reason == f'{migrate.BOTH_SPELL} (sort)'
    assert migrate.NOT_ONE_LINE in reasons.values()
    assert all(e.kind == 'left' for e in planned.values())


def test_a_regex_anchor_is_a_value_not_a_shell_variable(tmp_path):
    line = "reveal 'metrics://src?file~=\\.(py|js)$'"
    planned, _ = _planned(tmp_path, _fenced(line))
    assert planned[line].new_line == "reveal metrics src --where 'file~=\\.(py|js)$'"


def test_a_line_left_anywhere_is_left_everywhere(tmp_path):
    """Lines are matched by text: a copy the doc shows failing keeps every copy as written."""
    line = "reveal 'calls://src?callers=main'"
    body = _fenced(line) + _fenced(line + '\n# Error: no such function')
    docs = _docs(tmp_path, body)
    examples = migrate.plan(['guides/G.md'], docs=docs)['guides/G.md']
    assert sorted(e.reason for e in examples) == sorted([migrate.SHOWN_FAILING, migrate.COPY_LEFT])
    assert migrate.rewrite_text(body, examples) == (body, 0)


def test_only_shell_fences_are_rewritten(tmp_path):
    line = "reveal 'calls://src?callers=main'"
    body = _fenced(line) + '```text\n' + line + '\n```\n'
    docs = _docs(tmp_path, body)
    text, done = migrate.rewrite_text(body, migrate.plan(['guides/G.md'], docs=docs)['guides/G.md'])
    assert done == 1 and text == _fenced('reveal calls src --callers main') + '```text\n' + line + '\n```\n'


def test_a_rewritten_doc_plans_nothing_more(tmp_path):
    body = _fenced("reveal 'calls://src?callers=main'", "reveal 'imports://src?circular' --format json",
                   "reveal 'json://data.json/users?status=active'")
    docs = _docs(tmp_path, body)
    text, done = migrate.rewrite_text(body, migrate.plan(['guides/G.md'], docs=docs)['guides/G.md'])
    assert done == 3
    (docs / 'guides' / 'G.md').write_text(text, encoding='utf-8')
    assert migrate.plan(['guides/G.md'], docs=docs)['guides/G.md'] == []


def test_check_writes_nothing(tmp_path, capsys):
    before = {p: p.read_bytes() for p in migrate.documented_sources().values()}
    assert migrate.main(['--check', str(migrate.DOCS / 'adapters' / 'PATCHES_ADAPTER_GUIDE.md')]) == 0
    assert 'adapters/PATCHES_ADAPTER_GUIDE.md: found ' in capsys.readouterr().out
    assert {p: p.read_bytes() for p in migrate.documented_sources().values()} == before


# --- the finished nouns' guides: each rewrite answers as its original does -------------------------------------------

def _finished_rewrites():
    """(original, rewritten) once each, for the rewrites of the finished nouns' guides the named fixture runs."""
    names, seen = _fixture_names(), {}
    for examples in migrate.plan(FINISHED_GUIDES, FINISHED_NOUNS).values():
        for e in examples:
            if e.kind == 'rewrite' and _named_fixture_skip(e.tokens, names) is None:
                seen.setdefault(shlex.join(e.tokens), shlex.split(e.new_line, comments=True))
    return sorted(seen.items())


FINISHED_REWRITES = _finished_rewrites()


def _answer(harness, words):
    """(exit, JSON without the echoed command and the request note) of the reveal stage of *words*; a grep after it
    reads that same output, so it is not run."""
    stage = words[1:words.index('|')] if '|' in words else words[1:]
    argv = _without_format(stage)  # one --format: the JSON run's
    code, out, err, _ = harness.run_subcommand(argv[0], *argv[1:], '--format', 'json')
    return code, _without_command(json.loads(out)) if out.strip() else err


def _as_uri_answers(answer):
    """The URI answer without what only the URI spelling adds: a ``meta`` that held nothing but the request note, and
    Calls' ``_query_format`` (the URI route's renderer-steering key leaked into its JSON; filed, and popped the same way
    in tests/test_canonical_request_back2716.py)."""
    code, document = answer
    if isinstance(document, dict):
        document.pop('_query_format', None)
        if document.get('meta') == {'warnings': []}:
            del document['meta']
    return code, document


def _text(harness, words):
    """(exit, stdout) of the reveal stage of *words*, as written."""
    stage = words[1:words.index('|')] if '|' in words else words[1:]
    code, out, _err, _ = harness.run_subcommand(stage[0], *stage[1:])
    return code, out


@pytest.mark.parametrize('original,rewritten', FINISHED_REWRITES, ids=[o for o, _ in FINISHED_REWRITES])
def test_a_finished_guide_rewrite_answers_as_its_original(named_harness, original, rewritten):  # noqa: F811
    """Same JSON and exit, and, where the example prints text, the same text and exit (the request note goes to
    stderr, which is not compared)."""
    assert _answer(named_harness, rewritten) == _as_uri_answers(_answer(named_harness, shlex.split(original)))
    if _without_format(rewritten) == rewritten:  # no --format: a text example (a JSON one is compared above)
        assert _text(named_harness, rewritten) == _text(named_harness, shlex.split(original))


def test_the_finished_guide_proof_is_not_vacuous():
    """While the finished nouns' guides teach URI requests, over 100 rewrites run on the fixture (150 of 362 at 6f1c40d8)."""
    rewrites = sum(e.kind == 'rewrite' for examples in migrate.plan(FINISHED_GUIDES, FINISHED_NOUNS).values()
                   for e in examples)
    assert rewrites == 0 or len(FINISHED_REWRITES) > 100, (rewrites, len(FINISHED_REWRITES))
