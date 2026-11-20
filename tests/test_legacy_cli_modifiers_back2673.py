"""LEGACY_CLI_MODIFIERS and the flag-only declarations agree (BACK-2673): every flag a declared noun keeps as a flag-only
legacy modifier has exactly one note-stage, standalone flag:<noun>.<flag> RETIREMENTS row, generated from the one
table, and every row names a flag its noun declares. Claude --tail too (Scott 2026-11-19, BACK-2709)."""
import pytest

from reveal.cli.invocation import COMMANDS, LEGACY_CLI_MODIFIERS, RETIREMENTS
from reveal.cli.routing.declared import declared_adapter_class

DECLARED = sorted(name for name, spec in COMMANDS.items() if spec.declared_adapter)


def _declared_flags(noun):
    return {flag for spec in declared_adapter_class(noun).PARAM_SPECS if spec.flag_only for flag in spec.cli.flags}


@pytest.mark.parametrize('noun', DECLARED)
def test_each_declared_flag_has_its_row_and_each_row_its_flag(noun):
    assert _declared_flags(noun) == set(LEGACY_CLI_MODIFIERS.get(noun, {}))


def test_the_rows_are_generated_from_the_table():
    rows = {key for key in RETIREMENTS if key.startswith('flag:') and not key.startswith('flag:--')}
    assert rows == {f'flag:{noun}.{flag}' for noun, flags in LEGACY_CLI_MODIFIERS.items() for flag in flags}
    for noun, flags in LEGACY_CLI_MODIFIERS.items():
        for flag, replacement in flags.items():
            row = RETIREMENTS[f'flag:{noun}.{flag}']
            assert (row.old, row.replacement, row.stage, row.standalone) == (f'{noun} {flag}', replacement, 'note', True)


def test_every_note_names_something_to_use():
    """A note reads '<old> is deprecated; use <replacement>': the replacement is what to type, with the reason after
    it, never 'nothing: ...' (Scott 2026-11-19: an understandable surface)."""
    assert [key for key, row in RETIREMENTS.items() if row.replacement.lower().startswith('nothing')] == []


def test_every_table_noun_is_a_declared_noun():
    assert set(LEGACY_CLI_MODIFIERS) <= set(DECLARED)


def test_claude_tail_is_a_legacy_modifier_like_every_nouns():  # Scott 2026-11-19, BACK-2709
    assert '--tail' in _declared_flags('claude') and '--tail' in LEGACY_CLI_MODIFIERS['claude']
