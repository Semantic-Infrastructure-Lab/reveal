"""help's search cap widens with --limit N (BACK-1383; the shared limit since BACK-2773, ruling S6).

The cap was a hard-coded ``hits[:20]`` with no query param, so the truncation note
could only say "add a search word to narrow it". The cap is a ParamSpec declared once
(``top`` until BACK-2773, now ``limit`` with ``top`` its noted legacy word); the schema,
the read and its validation come from that declaration.
"""

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.help import HelpAdapter, _SEARCH_LIMIT

pytestmark = pytest.mark.cli

# A term common enough to match well over 20 guides/adapters/recipes.
BROAD = 'a'


def _search(**controls):
    return HelpAdapter('search', params={'match': BROAD, **controls}).get_structure()


def _cut(result):
    return next((w for w in (result.get('meta') or {}).get('warnings', [])
                 if w.get('type') == 'truncated' and w.get('field') == 'hits'), None)


def test_default_cap_says_how_to_widen():
    result = _search()
    cut = _cut(result)
    assert len(result['hits']) == _SEARCH_LIMIT.default == 20
    assert cut and cut['total'] > 20
    assert '--limit N' in cut['message']


def test_limit_widens_narrows_and_zero_lists_all():
    total = _cut(_search())['total']
    assert len(_search(limit=5)['hits']) == 5
    every = _search(limit=0)
    assert len(every['hits']) == total and _cut(every) is None
    wide = _search(limit=total + 10)
    assert len(wide['hits']) == total and _cut(wide) is None


def test_old_fixed_cap_fails_the_widen_check(monkeypatch):
    """Negative control: with the cap ignored (the old hits[:20]), limit=0 does not list all."""
    real = HelpAdapter._search_help
    monkeypatch.setattr(HelpAdapter, '_search_help',
                        lambda self, term, top=20: real(self, term, top=20))
    total = _cut(_search())['total']
    assert len(_search(limit=0)['hits']) != total


@pytest.mark.parametrize('value, message', [
    (-1, 'limit must be >= 0'),
    (1.5, 'limit must be a whole number'),
    ('lots', 'limit must be a whole number'),
])
def test_bad_limit_is_an_error_not_a_silent_default(value, message):
    with pytest.raises(ValueError, match=message):
        _search(limit=value)


def test_schema_declares_limit_from_the_paramspec():
    params = HelpAdapter.get_schema()['query_params']
    assert params['limit'] == _SEARCH_LIMIT.schema()
    assert params['limit']['default'] == 20 and params['limit']['minimum'] == 0
    assert 'match' in params and 'top' not in params and 'search' not in params


def test_cli_reads_limit_and_rejects_bad_values():
    ok = _run_reveal_direct('help://search', '--match', 'a', '--limit', '3', '--format', 'json')
    assert ok.returncode == 0, ok.stderr
    assert 'has no effect' not in ok.stderr  # the flag ledger counts --limit as read
    bad = _run_reveal_direct('help://search', '--match', 'a', '--limit', '-1')
    assert bad.returncode == 2
    assert 'limit must be >= 0' in bad.stderr + bad.stdout
    legacy = _run_reveal_direct('help://search?search=a&top=-1')  # the legacy word binds through the same declaration
    assert legacy.returncode == 2 and 'limit must be >= 0' in legacy.stderr + legacy.stdout
