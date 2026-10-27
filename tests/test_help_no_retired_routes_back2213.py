"""BACK-2213: no help page sends a reader to a retired spelling.

`help://imports` listed `help://depends` and `help://stats` in See Also (and, derived from it, in
Next), and `help://patches` pointed at `help://testability` and `reveal testability`. All four are
RETIREMENTS rows. test_retired_adapters_are_not_routed_to guards only `help://quick`; this guards
every adapter's own See Also, and the imports schema note that presented `deps://` / `depends://`
as live summary views.
"""
import re

import pytest

from reveal.adapters.base import get_adapter_class, list_supported_schemes
from reveal.cli.handlers.introspection import retired_schemes

pytestmark = pytest.mark.component


def _retired_route():
    names = '|'.join(map(re.escape, retired_schemes()))
    return re.compile(rf'(?:help://|reveal )(?:{names})\b')


def _see_also(scheme):
    adapter_class = get_adapter_class(scheme)
    help_data = adapter_class.get_help() if hasattr(adapter_class, 'get_help') else None
    return help_data.get('see_also', []) if isinstance(help_data, dict) else []


def test_no_live_adapter_see_also_routes_to_a_retired_spelling():
    """A retired adapter's own page may name itself (it says what replaced it)."""
    route = _retired_route()
    live = sorted(set(list_supported_schemes()) - set(retired_schemes()))
    offenders = [f'{scheme}: {line}' for scheme in live
                 for line in _see_also(scheme) if isinstance(line, str) and route.search(line)]
    assert not offenders, offenders


def test_the_scan_sees_see_also_lines(monkeypatch):
    """Positive control: a retired route in a See Also line is found, so the zero above means something."""
    assert any(_see_also(scheme) for scheme in list_supported_schemes())
    assert _retired_route().search('reveal help://depends - Reverse import graph')
    assert _retired_route().search('reveal testability src --tests tests - Combined report')
    assert not _retired_route().search('reveal help://metrics - Codebase metrics')


def test_the_imports_schema_note_does_not_present_retired_views_as_live():
    notes = ' '.join(get_adapter_class('imports').get_schema()['notes'])
    assert 'Two summary views sit on top' not in notes
    assert '?importers' in notes and '?external' in notes


def test_next_pointers_never_name_a_retired_adapter():
    """`help://imports` ended in "Next -> reveal help://depends": the curated relationship pairs still
    list retired adapters, and `_related_adapters` turned them into pointers."""
    from reveal.adapters.help import HelpAdapter
    adapter = HelpAdapter('help://quick')
    retired = set(retired_schemes())
    live = sorted(set(list_supported_schemes()) - retired)
    offenders = {scheme: pointers for scheme in live
                 for pointers in [adapter._related_adapters(scheme)]
                 if any(p.rsplit('://', 1)[-1] in retired for p in pointers)}
    assert not offenders, offenders
    assert adapter._related_adapters('imports'), 'imports keeps live neighbours'
