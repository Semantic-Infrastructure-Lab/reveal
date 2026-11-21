"""BACK-2716 step 4: the generated old-to-new table lists every retired spelling (the cut's CHANGELOG table).

scripts/retirement_table.py reads RETIREMENTS, the generated shared-name family and, on every noun that says the request
note, the analysis-only scheme and each declared query key with the flag that replaces it (the renderer's own lookup).
"""
from scripts.retirement_table import NO_FLAG_YET, main, markdown, migration_rows
from reveal.adapters.base import get_adapter_class
from reveal.cli.invocation import COMMANDS, RETIREMENTS, generated_retirements, request_noted
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class

NOTED = [noun for noun in sorted(COMMANDS) if request_noted(noun)]


def _rows():
    # Built per test: a fixture's monkeypatch.delitem re-inserts RETIREMENTS keys at the end, so dict order is not stable.
    return migration_rows()


def _keys():
    return [row['key'] for row in _rows()]


def _request_row(noun, name):
    return next(row for row in _rows() if row['key'] == f'request:{noun}.{name}')


def test_every_retirements_row_and_every_generated_row_is_listed_once():
    keys = _keys()
    assert len(keys) == len(set(keys))
    assert set(RETIREMENTS) <= set(keys) and set(generated_retirements()) <= set(keys)
    for row in _rows():
        entry = RETIREMENTS.get(row['key'])
        if entry is not None:
            assert (row['old'], row['replacement'], row['stage']) == (entry.old, entry.replacement, entry.stage)


def test_every_declared_query_key_of_every_request_noted_noun_is_listed():
    for noun in NOTED:
        for spec in declared_adapter_class(noun).PARAM_SPECS:
            if not spec.flag_only:
                assert f'request:{noun}.{spec.name}' in _keys(), (noun, spec.name)


def test_each_analysis_only_scheme_has_its_own_row_and_a_resource_has_none():
    for noun in NOTED:
        analysis_only = getattr(get_adapter_class(noun), 'ANALYSIS_ONLY', False)
        assert (f'request:{noun}' in _keys()) == analysis_only, noun


def test_each_replacement_flag_is_one_the_nouns_parser_reads():
    for row in _rows():
        if row['kind'] != 'request' or row['replacement'].startswith('no flag') or '.' not in row['key']:
            continue
        noun = row['key'].partition(':')[2].partition('.')[0]
        flag = next(word for word in row['replacement'].split() if word.startswith('--'))
        assert flag in create_declared_parser(noun)._option_string_actions, row


def test_a_store_false_flag_replaces_the_key_given_false():
    """Red control for the step-4 polarity fix: ?suppress=true is patches' default, --no-suppress spells false."""
    row = _request_row('patches', 'suppress')
    assert row['old'] == 'patches://PATH?suppress=false' and row['replacement'] == 'reveal patches PATH --no-suppress'


def test_a_walk_control_with_no_binding_of_its_own_is_its_shared_flag():
    assert _request_row('overview', 'all')['replacement'] == 'reveal overview PATH --all'


def test_a_key_no_flag_spells_says_so_and_names_its_own_row_when_it_has_one():
    assert _request_row('claude', 'search')['replacement'].endswith('(param:claude.search)')
    assert _request_row('git', 'no_merges')['replacement'] == NO_FLAG_YET


def test_the_markdown_table_has_one_line_per_row(capsys):
    assert main(['--format', 'markdown']) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == ['| Old spelling | Use instead | Stage |', '|---|---|---|']
    rows = _rows()
    assert len(lines) == len(rows) + 2
    assert markdown(rows).count('\n') == len(rows) + 2
