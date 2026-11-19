"""Applicability (COMMAND_MODEL "Applicability", BACK-2656): a control the selected answer does not read is an invalid
request, refused before analysis on every transport.

An answer is named by its predicted result type and by the selection that picks it (an operation's name,
``name=value``, or ``default``); a control declares the answers that read it in ``ParamSpec.answers`` (empty: every
answer). The shared check is ``query_binding.reject_unread_controls``; only the data can tell for a few controls, and
those answer with the one shared ``control_unread_by_data`` warning (Scott 2026-11-18, Q2).
"""
import pytest

from reveal.errors import RequestValidationError
from reveal.utils.query_binding import (answer_facets, apply_declared_overrides, bind_prepared_params,
                                        prepare_declared_params, reject_unread_controls, unread_by_data_warning)
from reveal.utils.query_parser import ParamSpec, collect_query_keys

VIEW = ParamSpec('view', 'string', 'answer', None, str, choices=('a', 'b'), role='operation')
MODE = ParamSpec('mode', 'boolean', 'a legacy answer', False, lambda v: str(v).lower() in ('1', 'true', ''),
                 role='operation')
ALPHA = ParamSpec('alpha', 'integer', 'read by view=a only', None, int, answers=('view=a',))
GAMMA = ParamSpec('gamma', 'integer', 'read by the fixture_b answer only', None, int, answers=('fixture_b',))
DELTA = ParamSpec('delta', 'integer', 'read by the default answer and mode', None, int, answers=('default', 'mode'))
BETA = ParamSpec('beta', 'integer', 'read by every answer', None, int)
SPECS = (VIEW, MODE, ALPHA, GAMMA, DELTA, BETA)


def _uri(query):
    params = prepare_declared_params(SPECS, query, 'uri')
    return bind_prepared_params(SPECS, params, transport='uri')


def _type(params):
    return 'fixture_b' if params.get('view') == 'b' else 'fixture_a'


def _check(params):
    reject_unread_controls(SPECS, params, lambda: _type(params))


def test_an_answer_is_named_by_its_type_and_its_selection():
    assert answer_facets(SPECS, _uri(''), 'fixture_a') == ('fixture_a', 'default')
    assert answer_facets(SPECS, _uri('view=b'), 'fixture_b') == ('fixture_b', 'view', 'view=b')
    assert answer_facets(SPECS, _uri('mode=true'), 'fixture_a') == ('fixture_a', 'mode')
    assert answer_facets(SPECS, _uri('mode=false'), 'fixture_a') == ('fixture_a', 'default')  # a switch that is off


@pytest.mark.parametrize('query', ['view=a&alpha=1', 'view=b&gamma=1', 'delta=1', 'mode&delta=1', 'view=a&beta=1',
                                   'view=b&beta=1', 'beta=1', ''])
def test_a_control_on_an_answer_that_reads_it_answers(query):
    _check(_uri(query))


@pytest.mark.parametrize('query,control,read_by,reads', [
    ('view=b&alpha=1', 'alpha', 'view=a', 'gamma, beta'),       # named by selection
    ('alpha=1', 'alpha', 'view=a', 'delta, beta'),              # the default answer
    ('view=a&gamma=1', 'gamma', 'fixture_b', 'alpha, beta'),    # named by type
    ('view=a&delta=1', 'delta', 'default, mode', 'alpha, beta'),
])
def test_a_control_the_answer_does_not_read_is_an_invalid_request(query, control, read_by, reads):
    with pytest.raises(RequestValidationError) as raised:
        _check(_uri(query))
    message = str(raised.value)
    assert message.startswith(f"control '{control}' is not read by this answer ("), message
    assert f'; {control} is read by: {read_by}; controls this answer reads: {reads}' in message, message


def test_several_unread_controls_are_named_together():
    with pytest.raises(RequestValidationError, match="controls 'alpha', 'gamma' are not read by this answer "
                                                     r"\(fixture_a, default\); alpha is read by: view=a; gamma"):
        _check(_uri('alpha=1&gamma=2'))


def test_the_answer_is_predicted_only_when_a_given_control_declares_answers():
    def unreachable():
        raise AssertionError('predicted although no given control declares its answers')
    for query in ('', 'beta=1', 'view=b&beta=1'):
        reject_unread_controls(SPECS, _uri(query), unreachable)


def test_an_omitted_typed_control_and_a_none_override_are_not_given():
    typed = prepare_declared_params(SPECS, {'view': 'b', 'alpha': None}, 'typed')  # an omitted flag arrives as None
    _check(bind_prepared_params(SPECS, typed, transport='typed'))
    with pytest.raises(RequestValidationError, match="'alpha' is not read"):
        _check(bind_prepared_params(SPECS, prepare_declared_params(SPECS, {'view': 'b', 'alpha': 3}, 'typed'),
                                    transport='typed'))
    uri = _uri('view=b&alpha=1')
    _check(apply_declared_overrides(SPECS, uri, {'alpha': None}))  # None selects the declared default
    with pytest.raises(RequestValidationError, match="'alpha' is not read"):
        _check(apply_declared_overrides(SPECS, _uri('view=b'), {'alpha': 2}))


PICKED = ParamSpec('picked', 'flag', 'selects the fixture_b answer without being an operation (Q5)', None,
                   lambda v: v is True or str(v).lower() in ('', '1', 'true'), answers=('fixture_b',))


def test_a_presence_flag_given_off_selects_nothing_and_is_not_judged():
    """Codex last/tokens/goal and Claude's presence flags name the answer they select; off (typed False, ?flag=false)
    they select nothing, as when omitted, so they are not a control the answer leaves unread (BACK-2656 Step 2d)."""
    specs = (*SPECS, PICKED)
    for params in (bind_prepared_params(specs, prepare_declared_params(specs, {'picked': False}, 'typed'),
                                        transport='typed'),
                   bind_prepared_params(specs, prepare_declared_params(specs, 'picked=false', 'uri'), transport='uri')):
        reject_unread_controls(specs, params, lambda: 'fixture_a')
    with pytest.raises(RequestValidationError, match="'picked' is not read"):  # on, on an answer it does not select
        reject_unread_controls(specs, bind_prepared_params(specs, prepare_declared_params(specs, 'picked', 'uri'),
                                                           transport='uri'), lambda: 'fixture_a')


PAIRED = ParamSpec('paired', 'integer', 'read by fixture_a when no operation picks it, and by fixture_b under view=b',
                   None, int, answers=('fixture_a+default', 'fixture_b+view=b'))


@pytest.mark.parametrize('query,reads', [('paired=1', True), ('view=b&paired=1', True), ('view=a&paired=1', False),
                                         ('mode&paired=1', False)])
def test_an_entry_joined_with_plus_names_one_answer_by_its_type_and_its_selection(query, reads):
    """An answer is its predicted type together with its selection (Scott 2026-11-18, Q1), so ``type+selection`` names
    exactly that pair: Claude reads ``contains`` on the ``claude_messages`` of ``/messages``, not on tail's slice of
    the same type. Every ``+`` part must name the answer; the type alone (view=a, mode: fixture_a) is not enough."""
    specs = (VIEW, MODE, PAIRED)
    params = bind_prepared_params(specs, prepare_declared_params(specs, query, 'uri'), transport='uri')
    if reads:
        reject_unread_controls(specs, params, lambda: _type(params))
        return
    with pytest.raises(RequestValidationError, match="'paired' is not read by this answer .*; paired is read by: "
                                                     r"fixture_a\+default, fixture_b\+view=b;"):
        reject_unread_controls(specs, params, lambda: _type(params))


def test_the_declaration_is_published_in_the_schema():
    assert ALPHA.schema()['answers'] == ['view=a']
    assert 'answers' not in BETA.schema()


def test_a_control_only_the_data_shows_unread_is_one_shared_warning_that_counts_as_its_read():
    with collect_query_keys() as log:
        params = _uri('beta=1')
        warning = unread_by_data_warning(params, ['beta', 'beta'], 'the value at this path is not a list')
    assert warning == {'type': 'control_unread_by_data', 'code': 'control_unread_by_data', 'fields': ['beta'],
                       'message': "'beta' has no effect on this data: the value at this path is not a list"}
    assert 'beta' in log.used
    assert unread_by_data_warning(params, [], 'x') is None


WHERE = ParamSpec('where', 'array', 'filters', [], lambda v: list(v) if isinstance(v, (list, tuple)) else [v],
                  role='filter-expression', repeatable=True, open_fields='any key', answers=('view=a',))
FOLDING = (VIEW, WHERE, BETA)


def test_a_folded_bare_key_is_named_as_typed_by_the_refusal_and_the_shared_warning():
    """Bare field keys fold into the filter expression: both disclosures name the control (canonical ``fields``) and
    the terms as typed, so ``?bogus=1`` is recognisable; ``where=`` itself adds nothing."""
    def bound(query):
        return bind_prepared_params(FOLDING, prepare_declared_params(FOLDING, query, 'uri'), transport='uri')
    with pytest.raises(RequestValidationError, match=r"^control 'where' \(bogus=1, n%3E1\) is not read by this "):
        reject_unread_controls(FOLDING, bound('view=b&bogus=1&n%3E1'), lambda: 'fixture_b')
    with pytest.raises(RequestValidationError, match=r"^control 'where' is not read by this "):
        reject_unread_controls(FOLDING, bound('view=b&where=n>1'), lambda: 'fixture_b')
    with collect_query_keys() as log:
        params = bound('where=n>1&bogus=1&beta=2')
        warning = unread_by_data_warning(params, ['where', 'beta'], 'not a list')
    assert warning['fields'] == ['where', 'beta']
    assert warning['message'] == "'where' (bogus=1), 'beta' have no effect on this data: not a list"
    assert {'where', 'bogus', 'beta'} <= log.used  # the folded key is disclosed with its control, not left unread


# --- the seam: every transport refuses before the adapter is built ---------------------------------------------

import json  # noqa: E402
from dataclasses import replace  # noqa: E402

from conftest import _run_reveal_direct  # noqa: E402
from reveal.adapters.base import ResourceAdapter  # noqa: E402
from reveal.adapters.registry import _ADAPTER_REGISTRY, _RENDERER_REGISTRY  # noqa: E402
from reveal.utils.query_binding import bind_declared_params  # noqa: E402
from reveal.utils.query_parser import ResourceSpec  # noqa: E402
from reveal.utils.results import ResultBuilder  # noqa: E402


def _fixture_classes(declared: bool):
    built = []

    class Adapter(ResourceAdapter):
        """A test-only declared noun: view a/b, alpha read by view=a, gamma by the fixture_b answer, beta by all."""
        LEGACY_INIT = False
        BOUND_QUERY_CALL = True
        RESOURCE_SPEC = ResourceSpec(uri_default='', walks=False, filesystem=False)
        PARAM_SPECS = SPECS
        RESULT_TYPE = 'fixture_a'
        DEFAULT_FAIL_ON = 'none'
        FINDINGS_POLICIES = ('none',)

        def __init__(self, resource='', query=None, *, params=None):
            built.append(resource)
            self.resource = resource
            self.params = params if params is not None else bind_declared_params(SPECS, query or '', transport='uri')

        @staticmethod
        def result_type_for(params):
            return _type(params)

        @staticmethod
        def uri_result_type(resource):
            return 'fixture_b' if 'view=b' in resource.partition('?')[2].split('&') else 'fixture_a'

        @classmethod
        def uri_execution_facts(cls, resource):  # a qualified operation, as every declared noun is
            return cls.execution_facts

        @staticmethod
        def execution_facts(result):
            from reveal.utils.results import AnalysisCompleteness, result_execution_facts
            return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE)

        def get_structure(self, **kwargs):
            return ResultBuilder.create(_type(self.params), self.resource, source_type='resource',
                                        data={'read': sorted(key for key, value in self.params.items()
                                                             if value is not None)})

    class Plugin(Adapter):
        """An undeclared adapter: a plugin subclass inherits the declarations, not their contract."""

    class Renderer:
        @staticmethod
        def render_structure(result, format='text'):
            print(json.dumps(result))

    return (Adapter if declared else Plugin), Renderer, built


@pytest.fixture(params=[True, False], ids=['declared', 'undeclared'])
def fixture_noun(request, monkeypatch):
    adapter, renderer, built = _fixture_classes(declared=request.param)
    monkeypatch.setitem(_ADAPTER_REGISTRY, 'applicability-fixture', adapter)
    monkeypatch.setitem(_RENDERER_REGISTRY, 'applicability-fixture', renderer)
    return request.param, built


def _cli_uri(query):
    return _run_reveal_direct(f'applicability-fixture://r?{query}', '--format', 'json')


def _api(query='', **kwargs):
    from reveal import api
    return api.query(f'applicability-fixture://r?{query}', **kwargs)


@pytest.mark.parametrize('query', ['alpha=1', 'view=b&alpha=1', 'view=a&gamma=1'])
def test_the_cli_uri_and_api_refuse_an_unread_control_before_construction(fixture_noun, query):
    declared, built = fixture_noun
    run = _cli_uri(query)
    if not declared:  # an undeclared adapter (a plugin subclass) keeps answering as before
        assert run.returncode == 0, run.stderr
        assert _api(query)['type'] in ('fixture_a', 'fixture_b')
        return
    assert run.returncode == 2, (run.returncode, run.stdout, run.stderr)
    assert 'is not read by this answer' in run.stderr and 'controls this answer reads:' in run.stderr, run.stderr
    with pytest.raises(RequestValidationError, match='is not read by this answer'):
        _api(query)
    control, _, value = query.rpartition('&')[2].partition('=')
    with pytest.raises(RequestValidationError, match=f"'{control}' is not read by this answer"):
        _api(query.rpartition('&')[0], **{control: int(value)})
    assert built == [], built  # refused before the adapter was built


@pytest.mark.parametrize('query', ['view=a&alpha=1', 'view=b&gamma=1', 'beta=1', 'view=b&beta=1', 'delta=1'])
def test_a_control_the_answer_reads_still_answers_on_every_transport(fixture_noun, query):
    run = _cli_uri(query)
    assert run.returncode == 0, run.stderr
    answer = json.loads(run.stdout)
    assert answer['type'] == ('fixture_b' if 'view=b' in query else 'fixture_a')
    assert _api(query)['type'] == answer['type']


def _imports_limit_read_by_the_ranking(monkeypatch):
    """A test-only declaration on a real declared noun (no noun declares answers in this step): imports' limit caps
    only the fan-in ranking, so the default answer does not read it."""
    from reveal.adapters.imports import ImportsAdapter
    specs = tuple(replace(spec, answers=('fan_in_ranking',)) if spec.name == 'limit' else spec
                  for spec in ImportsAdapter.PARAM_SPECS)
    monkeypatch.setattr(ImportsAdapter, 'PARAM_SPECS', specs)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('import b\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('X = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    _imports_limit_read_by_the_ranking(monkeypatch)
    return tmp_path


@pytest.mark.parametrize('argv,spelled', [
    (('imports://.?limit=1',), 'limit'),                  # the URI
    (('imports://.', '--limit', '1'), 'limit'),           # the URI and a flag
    (('imports', '.', '--limit', '1'), 'limit'),          # the subcommand
    (('imports', '.', '--top', '1'), 'limit'),            # the subcommand, a legacy spelling: named as its control
])
def test_a_declared_noun_refuses_on_every_cli_form(project, argv, spelled):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 2, (run.returncode, run.stderr)
    assert (f"control '{spelled}' is not read by this answer (imports, default); {spelled} is read by: fan_in_ranking"
            in run.stderr), run.stderr
    answer = json.loads(run.stdout)  # the invalid-request document, as every invalid request answers in JSON mode
    assert answer['type'] == 'imports'
    assert not [w for w in answer['meta'].get('warnings', []) if w.get('code') in ('unused_query_param', 'unused_flag')]


def test_a_declared_noun_refuses_on_the_api_and_mcp(project):
    from reveal import api
    for call in (lambda: api.query('imports://.?limit=1'), lambda: api.query('imports://.', limit=1)):
        with pytest.raises(RequestValidationError, match=r"'limit' is not read by this answer \(imports, default\)"):
            call()
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    assert "'limit' is not read by this answer" in reveal_query('imports://.?limit=1')


@pytest.mark.parametrize('argv', [('imports://.?sort=-fan-in&limit=1',), ('imports', '.', '--sort=-fan-in', '--limit',
                                                                          '1')])
def test_a_declared_noun_answers_where_the_control_is_read(project, argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['type'] == 'fan_in_ranking'


# Every declared noun refuses before its adapter is built: one control per noun is given a test-only declaration that
# no answer matches. JSON reads its source before its controls bind (SOURCE_BEFORE_CONTROLS), so its constructor runs
# first; no noun answers (get_structure) either way. The value is one each noun accepts on its default request.
from test_vocabulary_conformance_back2654 import BASE, NOUNS, TARGETS, _adapter, workspace  # noqa: E402,F401

REFUSED_CONTROL = {'architecture': ('top', '2'), 'ast': ('limit', '2'), 'calls': ('limit', '2'),
                   'claude': ('limit', '2'), 'codex': ('matches', '2'), 'contracts': ('impls', '2'),
                   'deps': ('top', '2'), 'git': ('limit', '2'), 'hotspots': ('top', '2'), 'imports': ('limit', '2'),
                   'json': ('limit', '2'), 'markdown': ('limit', '2'), 'metrics': ('limit', '2'),
                   'overview': ('top', '2'), 'pack': ('budget', '2000'), 'patches': ('limit', '2'),
                   'surface': ('top', '2'), 'testability': ('top', '2'), 'trace': ('depth', '2')}


def test_every_declared_noun_with_a_refusal_case():
    assert set(REFUSED_CONTROL) == set(NOUNS) - {'stats'}  # stats:// is metrics' retired scheme (rule 9)


@pytest.mark.parametrize('noun', sorted(REFUSED_CONTROL))
def test_every_declared_noun_refuses_before_its_adapter_is_built(workspace, monkeypatch, noun):  # noqa: F811
    from reveal import api
    adapter = _adapter(noun)
    control, value = REFUSED_CONTROL[noun]
    monkeypatch.setattr(adapter, 'PARAM_SPECS', tuple(
        replace(spec, answers=('no-such-answer',)) if spec.name == control else spec for spec in adapter.PARAM_SPECS))
    calls = []
    for method in ('__init__', 'get_structure'):
        original = getattr(adapter, method)
        monkeypatch.setattr(adapter, method, lambda *a, _m=method, _o=original, **k: (calls.append(_m), _o(*a, **k))[1])
    base = BASE[noun][1].lstrip('?')
    uri = f"{noun}://{TARGETS.get(noun, 'proj')}?" + '&'.join(part for part in (base, f'{control}={value}') if part)
    run = _run_reveal_direct(uri, '--format', 'json')
    assert run.returncode == 2 and f"control '{control}' is not read by this answer" in run.stderr, (run.returncode,
                                                                                                    run.stderr)
    with pytest.raises(RequestValidationError, match=f"'{control}' is not read by this answer"):
        api.query(uri)
    before = ['__init__'] * 2 if getattr(adapter, 'SOURCE_BEFORE_CONTROLS', False) else []
    assert calls == before, calls


def test_the_rule_20_probe_counts_a_refusal_as_conforming(workspace, monkeypatch):  # noqa: F811
    """A probe that could only fail would measure nothing: with Markdown's limit read by the listing alone and its
    offset left undeclared (test-only), the conformance probe sees the links and lint views refuse limit, and still
    sees offset answered unread there."""
    from reveal.adapters.markdown.adapter import MarkdownQueryAdapter as adapter
    from test_vocabulary_conformance_back2654 import probe_applicability
    monkeypatch.setattr(adapter, 'PARAM_SPECS', tuple(
        replace(spec, answers=('markdown_query',)) if spec.name == 'limit' else
        replace(spec, answers=()) if spec.name == 'offset' else spec for spec in adapter.PARAM_SPECS))
    cases = probe_applicability('markdown')
    refused = [case for case in cases if case.label.endswith('?limit= refused')]
    assert len(refused) == 2 and all(case.ok for case in refused), refused  # view=links and view=lint
    assert not [case for case in cases if case.label.endswith('?limit= unread')]
    assert [case.ok for case in cases if case.label.endswith('view=links ?offset= unread')] == [False]


def test_a_refusal_on_an_unqualified_resource_is_exit_2_and_an_undeclared_adapters_error_keeps_its_exit(monkeypatch):
    """The generic route exits 1 for a construction-time validation error of a resource without execution facts; an
    applicability refusal is exit 2 there too (codex's memories, rules, skills, plugins), while an undeclared
    adapter's own RequestValidationError keeps the generic route's exit 1 (BACK-2656)."""
    declared, renderer, _built = _fixture_classes(declared=True)

    class Unqualified(declared):
        PARAM_SPECS = SPECS  # its own declaration

        @classmethod
        def uri_execution_facts(cls, resource):
            return None

    class Raises(ResourceAdapter):
        LEGACY_INIT = False
        RESOURCE_SPEC = ResourceSpec(uri_default='', walks=False, filesystem=False)

        def __init__(self, resource='', query=None, *, params=None):
            raise RequestValidationError('the adapter rejects this request itself')

        def get_structure(self, **kwargs):
            raise AssertionError('never built')

    for scheme, adapter in (('applicability-unqualified', Unqualified), ('applicability-raises', Raises)):
        monkeypatch.setitem(_ADAPTER_REGISTRY, scheme, adapter)
        monkeypatch.setitem(_RENDERER_REGISTRY, scheme, renderer)
    refused = _run_reveal_direct('applicability-unqualified://r?alpha=1', '--format', 'json')
    assert refused.returncode == 2 and 'is not read by this answer' in refused.stderr, (refused.returncode,
                                                                                         refused.stderr)
    own = _run_reveal_direct('applicability-raises://r', '--format', 'json')
    assert own.returncode == 1 and 'the adapter rejects this request itself' in own.stderr, (own.returncode, own.stderr)


def test_a_retired_spelling_that_adopts_its_parents_declaration_is_judged_by_it(monkeypatch, tmp_path):
    """A retired scheme adopts its parent's declaration with a class-local ``BOUND_QUERY_CALL`` (the opt-in
    ``factory.uses_bound_query_call`` already reads: ``stats://``, Architecture). It is the same answer, so the same
    control is refused on it before construction, on the URI and the API; a plugin subclass without that opt-in keeps
    its own behaviour (the ``undeclared`` fixture above)."""
    from reveal import api
    declared, renderer, built = _fixture_classes(declared=True)

    class Retired(declared):
        BOUND_QUERY_CALL = True  # adopts the inherited declaration, as stats:// and architecture:// do

    monkeypatch.setitem(_ADAPTER_REGISTRY, 'applicability-retired', Retired)
    monkeypatch.setitem(_RENDERER_REGISTRY, 'applicability-retired', renderer)
    run = _run_reveal_direct('applicability-retired://r?alpha=1', '--format', 'json')
    assert run.returncode == 2 and "control 'alpha' is not read by this answer" in run.stderr, (run.returncode,
                                                                                                 run.stderr)
    with pytest.raises(RequestValidationError, match="'alpha' is not read by this answer"):
        api.query('applicability-retired://r', alpha=1)
    assert built == [], built
    assert _run_reveal_direct('applicability-retired://r?view=a&alpha=1', '--format', 'json').returncode == 0

    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    for scheme in ('metrics', 'stats'):  # stats:// is metrics' retired spelling: one answer, one refusal
        run = _run_reveal_direct(f'{scheme}://.?top=3', '--format', 'json')
        assert run.returncode == 2 and "control 'top' is not read by this answer" in run.stderr, (scheme,
                                                                                                   run.returncode,
                                                                                                   run.stderr)
        assert _run_reveal_direct(f'{scheme}://.?view=hotspots&top=3', '--format', 'json').returncode == 0
