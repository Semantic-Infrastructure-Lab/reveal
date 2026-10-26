"""BACK-2197: --adapters, --discover and help://adapters read "retired" from the RETIREMENTS table.

Every ``scheme:*`` row is listed as retired, with the table's replacement text, apart from the live
code nouns; no live scheme is listed as retired; the hosting-ops family is its own group. The hand-
written ``Retired:`` description prefixes are gone, so the table is the one place that says it.
"""
import json

import pytest

from reveal.adapters.base import _ADAPTER_REGISTRY, list_public_schemes
from reveal.adapters.help import HelpAdapter
from reveal.cli.handlers.introspection import (
    OPS_SCHEMES, build_discover_payload, handle_adapters,
)
from reveal.cli.invocation import RETIREMENTS

RETIRED = {k.split(':', 1)[1]: v for k, v in RETIREMENTS.items() if k.startswith('scheme:')}
RETIRED_HEADING = 'Retired adapters'
OPS_HEADING = 'Hosting and server operations'


def _text_listing(capsys, **kw):
    with pytest.raises(SystemExit):
        handle_adapters(**kw)
    return capsys.readouterr().out


def _sections(text):
    """Split the --adapters text at the two group headings: (live, ops, retired)."""
    assert RETIRED_HEADING in text and OPS_HEADING in text
    head, retired = text.split(RETIRED_HEADING)
    live, ops = head.split(OPS_HEADING)
    return live, ops, retired


def test_table_has_scheme_rows():
    """Positive control: the table this test reads is not empty."""
    assert {'depends', 'deps', 'testability', 'stats', 'classify', 'trace'} <= set(RETIRED)


def test_text_listing_shows_every_scheme_row_as_retired(capsys):
    live, ops, retired = _sections(_text_listing(capsys))
    for scheme, row in RETIRED.items():
        assert f'  {scheme}://' in retired, scheme
        assert row.replacement in retired, scheme
        assert f'  {scheme}://' not in live + ops, scheme


def test_text_listing_no_live_scheme_is_retired(capsys):
    live, ops, retired = _sections(_text_listing(capsys))
    for scheme in set(list_public_schemes()) - set(RETIRED):
        assert f'  {scheme}://' not in retired, scheme
        assert f'  {scheme}://' in live + ops, scheme


def test_text_listing_groups_ops_family_apart(capsys):
    live, ops, _ = _sections(_text_listing(capsys))
    for scheme in OPS_SCHEMES:
        assert f'  {scheme}://' in ops, scheme
        assert f'  {scheme}://' not in live, scheme
    assert '  calls://' in live and '  calls://' not in ops


def test_ops_schemes_are_registered_and_not_retired():
    assert set(OPS_SCHEMES) <= set(_ADAPTER_REGISTRY)
    assert not set(OPS_SCHEMES) & set(RETIRED)


def test_discover_payload_marks_retired_from_the_table():
    adapters = build_discover_payload()['adapters']
    for scheme, row in RETIRED.items():
        assert adapters[scheme]['retired'] is True, scheme
        assert adapters[scheme]['replaced_by'] == row.replacement, scheme
    for scheme, entry in adapters.items():
        if scheme not in RETIRED:
            assert 'retired' not in entry and 'replaced_by' not in entry, scheme


def test_json_listing_is_the_discover_payload(capsys):
    with pytest.raises(SystemExit):
        handle_adapters(fmt='json')
    assert json.loads(capsys.readouterr().out)['adapters'] == build_discover_payload()['adapters']


def test_help_adapters_marks_retired_and_groups():
    data = HelpAdapter().get_element('adapters')
    for scheme, row in RETIRED.items():
        info = data['adapters'][scheme]
        assert info['group'] == 'retired', scheme
        assert info['replaced_by'] == row.replacement, scheme
    for scheme in OPS_SCHEMES:
        assert data['adapters'][scheme]['group'] == 'ops', scheme
    for scheme, info in data['adapters'].items():
        if scheme not in RETIRED and scheme not in OPS_SCHEMES:
            assert info['group'] == 'code', scheme


def test_help_adapters_text_has_the_groups(capsys):
    from reveal.rendering.adapters.help import _render_help_adapter_summary
    _render_help_adapter_summary(HelpAdapter().get_element('adapters'))
    out = capsys.readouterr().out
    assert RETIRED_HEADING in out and OPS_HEADING in out
    retired = out.split(RETIRED_HEADING)[1]
    for scheme, row in RETIRED.items():
        assert f'## {scheme}://' in retired and row.replacement in retired, scheme


@pytest.mark.parametrize('scheme', sorted(RETIRED))
def test_no_hand_written_retired_prefix(scheme):
    description = _ADAPTER_REGISTRY[scheme].get_help().get('description', '')
    assert not description.startswith('Retired:'), scheme
