"""BACK-2726: the guide-migration script rewrites a documented URI request as the canonical request.

The script (``scripts/migrate_doc_uri_examples.py``) finds examples with the executable-docs gate's extractor
(``scripts/doc_examples.py``) and renders them with ``canonical.render_request`` (a plain path) or
``render_uri_request`` (an address). These tests hold its edges on synthetic docs: what it rewrites, and what it must
leave (a sentence or comment naming a retired spelling, a resource URI with no options, a request with no canonical
form, a twin or undeclared scheme), and they run each rewrite the script would make in the shipped docs beside its
original on the named doc fixture: same JSON (the echoed command and the request note aside) and same exit. The finished
nouns' guides were proved that way before they were written (150 pairs at 92b92e42); the docs still to migrate keep the
proof populated until the last lane writes its guides.
"""
import json
import shlex

import pytest

from scripts import migrate_doc_uri_examples as migrate
from test_canonical_request_back2716 import _without_command
from test_example_recipes_run import (_fixture_names, _named_fixture_skip, _without_format,  # noqa: F401
                                      named_harness)




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
    """A URI that carries a resource address (a JSON key path, a session) renders as that URI followed by flags."""
    planned, _ = _planned(tmp_path, _fenced("reveal 'json://data.json/users?age>25&limit=5'",
                                            "reveal 'claude://session/abc?tools=Bash&errors'"))
    assert [e.new_line for e in planned.values()] == ["reveal json://data.json/users --where 'age>25' --limit 5",
                                                      'reveal claude://session/abc --errors --tools Bash']


# The form ruling (manager, step 2; D1 as clarified 2026-11-19): a guide teaches the subcommand where the noun declares
# one and the target is a plain path, and keeps the resource URI where the URI carries an address (a key path, @ref).
FORM_PROBES = [
    ("reveal 'json://config.json?schema'", 'reveal json config.json --view schema', 'subcommand'),
    ("reveal 'json://config.json?view=keys&limit=2'", 'reveal json config.json --view keys --limit 2', 'subcommand'),
    ("reveal 'json://config.json/database?keys'", 'reveal json://config.json/database --view keys', 'resource'),
    ("reveal 'git://.@main?limit=2'", 'reveal git://.@main --limit 2', 'resource'),
    # git declares no filesystem path, but its positional is a path: a plain one teaches the subcommand, and an @REF is
    # the resource's address, so it keeps the URI (manager, step 6).
    ("reveal 'git://app.py?view=history&limit=2'", 'reveal git app.py --view history --limit 2', 'subcommand'),
    ("reveal 'git://app.py@main?view=history&limit=2'", 'reveal git://app.py@main --view history --limit 2', 'resource'),
]


def test_a_plain_path_teaches_the_subcommand_and_an_address_keeps_the_resource_uri(tmp_path):
    planned, _ = _planned(tmp_path, _fenced(*(original for original, _, _ in FORM_PROBES)))
    assert [e.new_line for e in planned.values()] == [new for _, new, _ in FORM_PROBES]
    assert [e.form for e in planned.values()] == [form for _, _, form in FORM_PROBES]


@pytest.mark.parametrize('original,rewritten,form', FORM_PROBES, ids=[o for o, _, _ in FORM_PROBES])
def test_each_form_answers_as_its_original_on_the_fixture(named_harness, original, rewritten, form):  # noqa: F811
    assert _answer(named_harness, shlex.split(rewritten)) == _as_uri_answers(_answer(named_harness,
                                                                                      shlex.split(original)))
    assert _text(named_harness, shlex.split(rewritten)) == _text(named_harness, shlex.split(original))


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
    """Claude's standalone ?search has no flag: it is left with the renderer's reason, and the binder's refusal (?tools
    without a value) is reported as such."""
    search, tools = "reveal 'claude://sessions?search=foo'", "reveal 'claude://session/abc?tools'"
    planned, docs = _planned(tmp_path, _fenced(search, tools))
    assert planned[search].reason == f'{migrate.UNRENDERABLE}: search has no flag on this noun'
    assert planned[tools].reason.startswith(f'{migrate.BINDER_REJECTS}: ')
    assert all(e.kind == 'left' for e in planned.values())
    body = (docs / 'guides' / 'G.md').read_text(encoding='utf-8')
    assert migrate.rewrite_text(body, planned.values()) == (body, 0)


def test_a_dot_graph_request_teaches_its_format_flag(tmp_path):
    """Calls and imports ?format=dot have the flag form --format dot (BACK-2722): no longer left as having no canonical
    form."""
    calls, imports = "reveal 'calls://src?callers=main&format=dot' | dot -Tsvg > g.svg", \
        "reveal 'imports://src?importers&scope=path&format=dot'"
    planned, _ = _planned(tmp_path, _fenced(calls, imports))
    assert (planned[calls].kind, planned[calls].new_line) == (
        'rewrite', 'reveal calls src --callers main --format dot | dot -Tsvg > g.svg')
    assert (planned[imports].kind, planned[imports].new_line) == (
        'rewrite', 'reveal imports src --scope path --importers --format dot')


def test_twin_and_undeclared_schemes_and_other_nouns_are_left_with_their_reason(tmp_path):
    # xlsx is declared since BACK-2626: the undeclared example is an ops scheme with a query string
    stats, ops, ast = ("reveal 'stats://src?hotspots=true'", "reveal 'letsencrypt://?check-orphans&check-duplicates'",
                       "reveal 'ast://src?kind=function'")
    planned, _ = _planned(tmp_path, _fenced(stats, ops, ast), nouns=['calls'])
    assert planned[stats].reason == migrate.NO_REQUEST_NOTE_TWIN
    assert planned[ops].reason == migrate.NO_REQUEST_NOTE_UNDECLARED
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
    assert migrate.main(['--check']) == 0
    assert capsys.readouterr().out.splitlines()[-1].startswith('total: found ')
    assert {p: p.read_bytes() for p in migrate.documented_sources().values()} == before


# The extra pass (manager, step 7, option b): a line already written in the resource form, `reveal SCHEME://PLAIN --flags`
# (no query string), teaches the subcommand when the same plain-path rule says so; an address keeps the URI.
RESOURCE_LINE_PROBES = [
    ('reveal git://app.py --view history --limit 2', 'reveal git app.py --view history --limit 2'),
    ('reveal git://. --view history --limit 2', 'reveal git . --view history --limit 2'),
    ('reveal json://config.json --view keys', 'reveal json config.json --view keys'),
]
RESOURCE_LINES_KEPT = ['reveal git://app.py@main --view history --limit 2', 'reveal json://config.json/database --view keys',
                       'reveal claude://sessions --limit 2', 'reveal git://app.py']


def test_a_written_resource_line_on_a_plain_path_teaches_the_subcommand(tmp_path):
    planned, docs = _planned(tmp_path, _fenced(*(o for o, _ in RESOURCE_LINE_PROBES), *RESOURCE_LINES_KEPT))
    assert {line: (e.kind, e.new_line, e.form, e.origin) for line, e in planned.items()} == {
        original: ('rewrite', rewritten, 'subcommand', 'resource') for original, rewritten in RESOURCE_LINE_PROBES}
    text, done = migrate.rewrite_text((docs / 'guides' / 'G.md').read_text(encoding='utf-8'), planned.values())
    assert done == len(RESOURCE_LINE_PROBES) and all(kept in text for kept in RESOURCE_LINES_KEPT)


@pytest.mark.parametrize('original,rewritten', RESOURCE_LINE_PROBES, ids=[o for o, _ in RESOURCE_LINE_PROBES])
def test_a_resource_line_rewrite_answers_as_its_original_on_the_fixture(named_harness, original, rewritten):  # noqa: F811
    assert _answer(named_harness, shlex.split(rewritten)) == _as_uri_answers(_answer(named_harness,
                                                                                      shlex.split(original)))
    assert _text(named_harness, shlex.split(rewritten)) == _text(named_harness, shlex.split(original))


def test_the_plain_path_decision_reads_declarations_not_a_noun_table(tmp_path):
    """A plain path: the noun's positional is declared a path, the resource holds no address mark it declares (git's @)
    and its declared resource_path is the whole resource. Claude's positional names a resource (sessions, a session), so
    it keeps the URI; markdown is analysis-only, so it always teaches the subcommand."""
    planned, _ = _planned(tmp_path, _fenced("reveal 'claude://sessions?limit=2'", "reveal 'git://.@HEAD~1?limit=2'",
                                            "reveal 'git://.?limit=2'", "reveal 'markdown://docs?where=status=draft'"))
    assert [(e.new_line, e.form) for e in planned.values()] == [
        ('reveal claude://sessions --limit 2', 'resource'), ("reveal 'git://.@HEAD~1' --limit 2", 'resource'),
        ('reveal git . --limit 2', 'subcommand'), ("reveal markdown docs --where status=draft", 'subcommand')]
    from reveal.cli.routing.declared import declared_adapter_class
    assert declared_adapter_class('git').RESOURCE_SPEC.address == '@'
    assert declared_adapter_class('claude').RESOURCE_SPEC.name == 'resource'


def test_a_replacement_that_spells_a_retiring_word_is_refused(tmp_path, monkeypatch):
    """The self-check: a rendered replacement whose flag, flag value or parameter has a RETIREMENTS row would teach a
    spelling that itself retires (git ?type=log rendered --view log); it is left, naming the row, never written."""
    from reveal.cli.invocation import RETIREMENTS, Retirement
    monkeypatch.setitem(RETIREMENTS, 'value:json.view=keys', Retirement('json --view keys', '--view schema'))
    line = "reveal 'json://config.json?keys'"
    planned, docs = _planned(tmp_path, _fenced(line, "reveal 'json://config.json?schema'"))
    assert planned[line].kind == 'left'
    assert planned[line].reason == f'{migrate.RETIRING_REPLACEMENT}: value:json.view=keys'
    assert planned["reveal 'json://config.json?schema'"].kind == 'rewrite'  # control: an unretired view is written
    text, done = migrate.rewrite_text((docs / 'guides' / 'G.md').read_text(encoding='utf-8'), planned.values())
    assert done == 1 and line in text


# --- every rewrite the script would make answers as its original does --------------------------------------------------

def _doc_rewrites():
    """(original, rewritten) once each, for the rewrites in the shipped docs that the named fixture runs."""
    names, seen = _fixture_names(), {}
    for examples in migrate.plan().values():
        for e in examples:
            if e.kind == 'rewrite' and _named_fixture_skip(e.tokens, names) is None:
                seen.setdefault(shlex.join(e.tokens), shlex.split(e.new_line, comments=True))
    return sorted(seen.items())


# original -> why its canonical request answers differently today. Strict xfail: a fix fails the run until deleted.
KNOWN_DIVERGENCES: dict = {}  # git ownership's legacy limit renders --scan-limit since BACK-2616 Step 4: none left


def _doc_rewrite_params():
    return [pytest.param(original, rewritten, id=original,
                         marks=[pytest.mark.xfail(strict=True, reason=KNOWN_DIVERGENCES[original])]
                         if original in KNOWN_DIVERGENCES else [])
            for original, rewritten in DOC_REWRITES]


DOC_REWRITES = _doc_rewrites()


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


@pytest.mark.parametrize('original,rewritten', _doc_rewrite_params())
def test_a_doc_rewrite_answers_as_its_original(named_harness, original, rewritten):  # noqa: F811
    """Same JSON and exit, and, where the example prints text, the same text and exit (the request note goes to
    stderr, which is not compared)."""
    assert _answer(named_harness, rewritten) == _as_uri_answers(_answer(named_harness, shlex.split(original)))
    if _without_format(rewritten) == rewritten:  # no --format: a text example (a JSON one is compared above)
        assert _text(named_harness, rewritten) == _text(named_harness, shlex.split(original))


def test_the_doc_rewrite_proof_is_not_vacuous():
    """While the docs teach URI requests the script rewrites, over 100 of them run on the fixture."""
    rewrites = sum(e.kind == 'rewrite' for examples in migrate.plan().values() for e in examples)
    assert rewrites == 0 or len(DOC_REWRITES) > 100, (rewrites, len(DOC_REWRITES))
