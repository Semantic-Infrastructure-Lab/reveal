"""Codex reads each control it applies through its declaration (BACK-2597: Codex was the last noun reading query keys
outside its declarations).

Before, ``search``, ``filter``, ``since`` and ``until`` (the catalog), ``goal``, ``last`` and ``tokens`` (a session's
selectors) and ``key`` (config) were read as raw dict keys (``.get``, ``in``) in the adapter and the config handler,
beside their ``ParamSpec`` declarations, so a declaration's codec, default and normalized value were not what the
reader used; only ``matches`` and ``full`` went through ``ParamSpec.read``. The history handler took the query and
read nothing. Now every control an answer applies is read through its declaration (the binder's normalized value),
and the history handler takes no query.

Since the vocabulary step (BACK-2618) ``filter``, ``full`` and ``last``/``tokens``/``goal`` are legacy words of
``where``, ``detail`` and ``view``: a legacy word is read through the declaration of the control it spells.
"""
import inspect

import pytest

from codex_session_fixture import DOC_SESSION_ID as S, build_codex_home
from reveal import api
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.adapters.codex.handlers import system
from reveal.adapters.codex.params import PARAM_SPECS
from reveal.utils.query_parser import ParamSpec


@pytest.fixture
def codex(tmp_path, monkeypatch):
    home = build_codex_home(tmp_path / 'home')
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', home)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', home / 'state_5.sqlite')
    monkeypatch.chdir(tmp_path)
    return home


@pytest.fixture
def declared_reads(monkeypatch):
    """The Codex controls read through ``ParamSpec.read`` while a request is answered."""
    seen = set()
    original = ParamSpec.read

    def spy(self, params):
        if any(self is spec for spec in PARAM_SPECS):
            seen.add(self.name)
        return original(self, params)

    monkeypatch.setattr(ParamSpec, 'read', spy)
    return seen


# The declaration each legacy word is read through (its canonical control).
CANONICAL = {'filter': 'where', 'full': 'detail', 'last': 'view', 'tokens': 'view', 'goal': 'view'}

# (resource, typed controls, the answer's type)
APPLIED = [
    ('sessions/', {'match': 'auth'}, 'codex_content_search'),
    ('sessions/', {'where': 'session~=auth', 'since': '2020-01-01'}, 'codex_session_list'),
    (S, {'view': 'tokens'}, 'codex_tokens'),
    (f'{S}/exchanges', {'detail': 'full'}, 'codex_exchanges'),
    ('sessions/', {'search': 'auth'}, 'codex_content_search'),
    ('sessions/', {'search': 'auth', 'matches': 1, 'since': '2020-01-01', 'until': 'today'}, 'codex_content_search'),
    ('sessions/', {'filter': 'auth'}, 'codex_session_list'),
    ('sessions/', {'filter': 'auth', 'since': '2020-01-01', 'until': 'today'}, 'codex_session_list'),
    (S, {'last': True}, 'codex_messages'),
    (S, {'tokens': True}, 'codex_tokens'),
    (S, {'goal': True}, 'codex_goal'),
    ('config', {'key': 'model'}, 'codex_config'),
    (f'{S}/exchanges', {'full': True}, 'codex_exchanges'),     # control: already a declared read
]


@pytest.mark.parametrize('resource,controls,kind', APPLIED, ids=[f'{row[0]}:{",".join(row[1])}' for row in APPLIED])
def test_every_applied_control_is_read_through_its_declaration(codex, declared_reads, resource, controls, kind):
    result = api.query(f'codex://{resource}', **controls)
    assert result['type'] == kind, result.get('error')
    names = {CANONICAL.get(name, name) for name in controls}
    assert names <= declared_reads, f'read outside their declarations: {sorted(names - declared_reads)}'


@pytest.mark.parametrize('query,kind', [('last', 'codex_messages'), ('tokens', 'codex_tokens'), ('goal', 'codex_goal')])
def test_a_uri_presence_flag_is_read_through_its_declaration(codex, declared_reads, query, kind):
    assert api.query(f'codex://{S}?{query}')['type'] == kind
    assert CANONICAL[query] in declared_reads


def test_the_config_key_selects_the_masked_value(codex):
    """Negative control: the answer the key read gives is unchanged."""
    result = api.query('codex://config', key='model')
    assert (result['key'], 'error' in result) == ('model', False)


def test_the_history_handler_takes_no_query():
    assert list(inspect.signature(system.get_history).parameters) == ['codex_home']


def test_the_config_handler_takes_the_key_not_the_query():
    assert list(inspect.signature(system.get_config).parameters) == ['codex_home', 'key']
