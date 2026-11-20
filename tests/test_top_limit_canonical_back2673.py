"""Hotspots and Testability take --limit as the cap (COMMAND_MODEL "Caps"; Scott 2026-11-19, BACK-2708 ruling 4):
`--limit N` capped their lists only after a URI, while the subcommand and `?limit=N` exited 2. Now `limit` is the
declared cap on every spelling, each list still capped separately, and `top` is its legacy word with a note. Patches'
pressure view keeps `top` (BACK-2625 owns its --limit question)."""
import json

import pytest

import test_vocabulary_conformance_back2654 as C
from legacy_modifier_fixture import rich, workspace  # noqa: F401  (fixtures)

# noun -> (subcommand flags, URI query) selecting an answer with several rows in each list
CASES = {'hotspots': (['--min-complexity', '1'], 'min_complexity=1', ('file_hotspots', 'function_hotspots')),
         'testability': (['--min-patches', '1', '--min-categories', '1', '--include-unresolved'],
                         'min_patches=1&min_categories=1&include_unresolved=true', ('patch_hotspots', 'boundary_hotspots'))}
NOUNS = sorted(CASES)


def _json(*argv):
    run = C._run(*argv, '--format', 'json')
    return run, (json.loads(run.out) if run.out.strip().startswith('{') else None)


def _lists(doc, noun):
    return {field: doc[field] for field in CASES[noun][2]}


def _retired(doc):
    return [w['message'] for w in doc['meta'].get('warnings', []) if w.get('code') == 'retired_spelling']


def _top_notes(doc):
    return [message for message in _retired(doc) if '?top=N' in message]


@pytest.mark.parametrize('noun', NOUNS)
def test_limit_caps_each_list_on_every_spelling(rich, noun):  # noqa: F811
    flags, query, _ = CASES[noun]
    _, base = _json(f'{noun}://proj?{query}&limit=0')
    spellings = {'subcommand --limit': (noun, 'proj', *flags, '--limit', '1'),
                 'URI limit=': (f'{noun}://proj?{query}&limit=1',),
                 'URI then --limit': (f'{noun}://proj?{query}', '--limit', '1')}
    answers = {}
    for label, argv in spellings.items():
        run, doc = _json(*argv)
        assert run.rc == 0, f'{label}: {run.brief()}'
        assert _lists(doc, noun) == {field: rows[:1] for field, rows in _lists(base, noun).items()}, label
        assert not _top_notes(doc), label
        answers[label] = C._answer(run, noun)
    assert len({json.dumps(answer, sort_keys=True) for answer in answers.values()}) == 1


@pytest.mark.parametrize('noun', NOUNS)
def test_top_is_the_noted_legacy_word_of_limit(rich, noun):  # noqa: F811
    flags, query, _ = CASES[noun]
    canonical_run, canonical = _json(f'{noun}://proj?{query}&limit=1')
    for argv in ((noun, 'proj', *flags, '--top', '1'), (f'{noun}://proj?{query}&top=1',),
                 (f'{noun}://proj?{query}', '--top', '1')):
        run, doc = _json(*argv)
        assert run.rc == 0, run.brief()
        assert _lists(doc, noun) == _lists(canonical, noun)
        assert _top_notes(doc) == [f'{noun} ?top=N (--top N) is deprecated; use --limit N, which caps each '
                                   f'list; 0 is uncapped.'], argv
        assert C._answer(run, noun) == C._answer(canonical_run, noun)


@pytest.mark.parametrize('noun', NOUNS)
def test_limit_zero_is_uncapped(rich, noun):  # noqa: F811
    flags, query, fields = CASES[noun]
    _, capped = _json(noun, 'proj', *flags)
    _, uncapped = _json(noun, 'proj', *flags, '--limit', '0')
    _, every = _json(noun, 'proj', *flags, '--all')
    assert _lists(uncapped, noun) == _lists(every, noun)
    assert sum(len(rows) for rows in _lists(uncapped, noun).values()) >= sum(len(rows) for rows in _lists(capped, noun).values())


@pytest.mark.parametrize('noun', NOUNS)
@pytest.mark.parametrize('argv', [('--top', '1', '--limit', '2'), ('?top=1&limit=2',), ('?top=1', '--limit', '2')])
def test_two_values_for_the_cap_exit_2_naming_both(rich, noun, argv):  # noqa: F811
    request = (noun, 'proj', *argv) if argv[0].startswith('--') else (f'{noun}://proj{argv[0]}', *argv[1:])
    run = C._run(*request)
    assert run.rc == 2, run.brief()
    assert 'top' in run.err and 'limit' in run.err


def test_patches_pressure_keeps_top_and_still_refuses_limit(rich):  # noqa: F811  (negative control)
    flags = ['--view', 'pressure', '--min-patches', '1', '--min-categories', '1', '--include-unresolved']
    run, doc = _json('patches', 'proj', *flags, '--top', '1')
    assert run.rc == 0 and not _retired(doc)
    assert [len(doc[field]) for field in ('patch_hotspots', 'boundary_hotspots')] == [1, 1]
    refused = C._run('patches', 'proj', *flags, '--limit', '1')
    assert refused.rc == 2 and "control 'limit' is not read by this answer" in refused.err


@pytest.mark.parametrize('noun', NOUNS)
def test_api_query_and_mcp_take_limit(rich, noun):  # noqa: F811
    from reveal import query
    from reveal.mcp_server import reveal_query
    _, query_text, _ = CASES[noun]
    uri = f'{noun}://proj?{query_text}&limit=1'
    _, cli = _json(uri)
    api = query(f'{noun}://proj?{query_text}', limit=1)
    mcp = json.loads(reveal_query(uri, provenance=True))  # provenance makes the MCP answer JSON
    assert _lists(api, noun) == _lists(cli, noun) == _lists(mcp, noun)
    assert all(len(rows) <= 1 for rows in _lists(cli, noun).values())
