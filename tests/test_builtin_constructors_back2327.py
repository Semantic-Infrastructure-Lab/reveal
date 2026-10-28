"""Built-in session adapters construct once through the canonical factory."""

import warnings

import pytest

from claude_session_fixture import build_claude_home
from codex_session_fixture import SESSION_UUID, make_sqlite_db, write_fixture_jsonl
from reveal.adapters import factory
from reveal.adapters.base import ResourceAdapter
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.adapters.registry import BUILTIN_SCHEMES, get_adapter_class


pytestmark = pytest.mark.component


@pytest.fixture(params=[('claude', ClaudeAdapter), ('codex', CodexAdapter)], ids=['claude', 'codex'])
def session_adapter(request, tmp_path, monkeypatch):
    scheme, adapter = request.param
    monkeypatch.setattr(factory, '_legacy_init_warned', set())
    if scheme == 'claude':
        home = build_claude_home(tmp_path)
        for name, path in {
            'CLAUDE_HOME': home, 'CLAUDE_JSON': tmp_path / '.claude.json',
            'CONVERSATION_BASE': home / 'projects', 'PLANS_DIR': home / 'plans',
            'AGENTS_DIR': home / 'agents', 'HOOKS_DIR': home / 'hooks',
            'SESSIONS_DIR': None,
        }.items():
            monkeypatch.setattr(adapter, name, path)
        resource = 'session/infernal-earth-0118/messages'
    else:
        rollout = write_fixture_jsonl(tmp_path)
        monkeypatch.setattr(adapter, 'CODEX_HOME', tmp_path)
        monkeypatch.setattr(adapter, 'CODEX_DB', make_sqlite_db(tmp_path, rollout))
        resource = f'{SESSION_UUID}/messages'
    return scheme, adapter, resource


def test_every_builtin_uses_canonical_initialization():
    legacy = [scheme for scheme in BUILTIN_SCHEMES
              if getattr(get_adapter_class(scheme), 'LEGACY_INIT', True)]
    assert legacy == []


@pytest.mark.parametrize('kind', ['bare', 'query-only', 'session', 'session-query'])
def test_real_session_resources_construct_once_without_legacy_warning(session_adapter, monkeypatch, kind):
    scheme, adapter, session = session_adapter
    expected_resource = '.' if kind in ('bare', 'query-only') else session
    query = 'search=auth' if kind == 'query-only' else 'last=2' if kind == 'session-query' else None
    resource = '' if kind in ('bare', 'query-only') else session
    if query is not None:
        resource += '?' + query
    original = adapter.__init__
    calls = []

    def counted(self, *args, **kwargs):
        calls.append((args, kwargs))
        original(self, *args, **kwargs)

    monkeypatch.setattr(adapter, '__init__', counted)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        result = adapter.from_uri(scheme, resource, 'messages')

    assert calls == [((expected_resource, query), {})]
    assert result.resource == expected_resource and result.query == query
    assert result.query_params == ({'search': 'auth'} if kind == 'query-only'
                                   else {'last': '2'} if kind == 'session-query' else {})
    assert not [notice for notice in caught if issubclass(notice.category, DeprecationWarning)]
    if scheme == 'claude':
        assert result.CONVERSATION_BASE.is_dir()
        if kind.startswith('session'):
            assert result.session_name == 'infernal-earth-0118'
            assert result.conversation_path.is_file()
    else:
        assert result.CODEX_DB.is_file()
        if kind.startswith('session'):
            assert result._session_id_from_resource() == SESSION_UUID
            assert result._session_sub_path() == 'messages'


@pytest.mark.parametrize('kind', ['bare', 'query-only', 'session', 'session-query'])
def test_real_factory_answers_match_direct_construction(session_adapter, kind):
    from reveal.api import query

    scheme, adapter, session = session_adapter
    path = '.' if kind in ('bare', 'query-only') else session
    params = 'search=auth' if kind == 'query-only' else 'last=2' if kind == 'session-query' else None
    resource = '' if kind in ('bare', 'query-only') else session
    uri = f'{scheme}://{resource}' + (f'?{params}' if params else '')
    expected = adapter(path, params).get_structure()
    actual = query(uri)
    assert not actual.get('error')
    assert actual == expected


def test_from_uri_preserves_claude_base_path_override(tmp_path, monkeypatch):
    initial = tmp_path / 'initial-projects'
    initial.mkdir()
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', initial)
    home = build_claude_home(tmp_path / 'override-home')
    resource = 'session/infernal-earth-0118/messages'
    adapter = ClaudeAdapter.from_uri('claude', resource + '?last=2', None)
    assert adapter.conversation_path is None

    adapter.reconfigure_base_path(home / 'projects')
    expected = ClaudeAdapter(resource, 'last=2')
    expected.reconfigure_base_path(home / 'projects')
    assert adapter.conversation_path.is_relative_to(home / 'projects')
    assert adapter.get_structure() == expected.get_structure()
    assert ClaudeAdapter.CONVERSATION_BASE == initial


@pytest.mark.parametrize('resource', ['', '?search=auth', 'sessions'])
@pytest.mark.parametrize('error_type', [TypeError, ValueError])
def test_real_constructor_failure_propagates_once(session_adapter, monkeypatch, resource, error_type):
    scheme, adapter, _ = session_adapter
    error = error_type('session initialization failed')
    calls = []

    def failed(self, params):
        calls.append((self.resource, self.query))
        raise error

    monkeypatch.setattr(adapter, '_warn_unknown_query_params', failed)
    with pytest.raises(error_type) as caught:
        adapter.from_uri(scheme, resource, None)
    assert caught.value is error
    assert len(calls) == 1


def test_legacy_keyword_plugin_retains_compatibility_and_one_warning(monkeypatch):
    monkeypatch.setattr(factory, '_legacy_init_warned', set())

    class LegacyPlugin(ResourceAdapter):
        def __init__(self, *, base_path, query=None):
            self.resource, self.query = base_path, query

        def get_structure(self, **kwargs):
            return {'resource': self.resource, 'query': self.query}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        first = LegacyPlugin.from_uri('legacy', 'custom/?search=auth', None)
        second = LegacyPlugin.from_uri('legacy', 'custom/?search=auth', None)
    assert first.get_structure() == second.get_structure() == {'resource': 'custom', 'query': 'search=auth'}
    deprecations = [notice for notice in caught if issubclass(notice.category, DeprecationWarning)]
    assert len(deprecations) == 1 and 'LegacyPlugin' in str(deprecations[0].message)
