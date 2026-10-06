"""help://search?top=N widens the 20-hit cap (BACK-1383).

The cap was a hard-coded ``hits[:20]`` with no query param, so the truncation note
could only say "add a search word to narrow it". ``top`` is a ParamSpec declared once;
the schema, the read and its validation come from that declaration.
"""

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.help import HelpAdapter, _SEARCH_TOP

pytestmark = pytest.mark.cli

# A term common enough to match well over 20 guides/adapters/recipes.
BROAD = 'search?search=a'


@pytest.fixture(scope='module')
def adapter():
    return HelpAdapter('')


def _cut(result):
    return next((w for w in (result.get('meta') or {}).get('warnings', [])
                 if w.get('type') == 'truncated' and w.get('field') == 'hits'), None)


def test_default_cap_says_how_to_widen(adapter):
    result = adapter.get_element(BROAD)
    cut = _cut(result)
    assert len(result['hits']) == _SEARCH_TOP.default == 20
    assert cut and cut['total'] > 20
    assert '?top=N' in cut['message']


def test_top_widens_narrows_and_zero_lists_all(adapter):
    total = _cut(adapter.get_element(BROAD))['total']
    assert len(adapter.get_element(BROAD + '&top=5')['hits']) == 5
    every = adapter.get_element(BROAD + '&top=0')
    assert len(every['hits']) == total and _cut(every) is None
    wide = adapter.get_element(f'{BROAD}&top={total + 10}')
    assert len(wide['hits']) == total and _cut(wide) is None


def test_old_fixed_cap_fails_the_widen_check(adapter, monkeypatch):
    """Negative control: with top ignored (the old hits[:20]), top=0 does not list all."""
    real = HelpAdapter._search_help
    monkeypatch.setattr(HelpAdapter, '_search_help',
                        lambda self, term, top=20: real(self, term, top=20))
    total = _cut(adapter.get_element(BROAD))['total']
    assert len(adapter.get_element(BROAD + '&top=0')['hits']) != total


@pytest.mark.parametrize('value, message', [
    ('-1', 'top must be >= 0'),
    ('1.5', 'top must be a whole number'),
    ('lots', 'top must be a whole number'),
])
def test_bad_top_is_an_error_not_a_silent_default(adapter, value, message):
    result = adapter.get_element(f'{BROAD}&top={value}')
    assert result['type'] == 'help_search'
    assert message in result['error']
    assert 'hits' not in result


def test_schema_declares_top_from_the_paramspec():
    params = HelpAdapter.get_schema()['query_params']
    assert params['top'] == _SEARCH_TOP.schema()
    assert params['top']['default'] == 20 and params['top']['minimum'] == 0
    assert 'search' in params


def test_cli_reads_top_and_rejects_bad_values():
    ok = _run_reveal_direct('help://search?search=a&top=3', '--format', 'json')
    assert ok.returncode == 0, ok.stderr
    assert 'has no effect' not in ok.stderr  # the flag ledger counts top= as read
    bad = _run_reveal_direct('help://search?search=a&top=-1')
    assert bad.returncode == 1
    assert 'top must be >= 0' in bad.stderr + bad.stdout
