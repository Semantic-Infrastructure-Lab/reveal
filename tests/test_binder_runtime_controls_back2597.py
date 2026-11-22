"""The binder owns the runtime-controls filter Codex and Claude each copied (BACK-2597; second use = move).

``runtime_controls(declarations, params)`` gives the controls a bound request gives, as a noun's readers see them: an
omitted control (None) is absent, and so is a legacy presence flag given off (typed ``False`` restores omission). The
presence flags are derived from the declarations (codec ``legacy_presence_value``), replacing Codex's hand-typed
``PRESENCE_FLAGS`` and the filter both nouns kept. Behaviour is unchanged: these tests pin it.
"""
from reveal.adapters.claude.params import PARAM_SPECS as CLAUDE_SPECS, PRESENCE_FLAGS as CLAUDE_PRESENCE
from reveal.adapters.claude.params import translate_request
from reveal.adapters.codex.params import PARAM_SPECS as CODEX_SPECS, bind_query
from reveal.utils.query_binding import bind_declared_params, legacy_presence_value, runtime_controls
from reveal.utils.query_parser import QueryParams


def _presence(specs):
    return {spec.name for spec in specs if spec.convert is legacy_presence_value}


def test_the_presence_flags_derive_from_the_declarations():
    """The derived set is each noun's former hand table."""
    assert _presence(CODEX_SPECS) == {'last', 'tokens', 'goal'}
    assert _presence(CLAUDE_SPECS) == set(CLAUDE_PRESENCE)


def test_none_and_a_presence_flag_given_off_are_absent():
    bound = QueryParams({'last': False, 'tokens': True, 'search': None, 'filter': '', 'full': False, 'matches': 0})
    assert dict(runtime_controls(CODEX_SPECS, bound).peek_items()) == {
        'tokens': True, 'filter': '', 'full': False, 'matches': 0}  # a boolean's False and a zero stay given


def test_a_plain_mapping_is_accepted():
    assert dict(runtime_controls(CODEX_SPECS, {'goal': False, 'key': 'model'}).peek_items()) == {'key': 'model'}


def test_walking_the_bound_request_reads_none_of_its_controls():
    bound = QueryParams({'last': True, 'search': 'auth'})
    bound._reads = set()
    runtime_controls(CODEX_SPECS, bound)
    assert bound._reads == set()


def test_a_name_without_a_presence_codec_keeps_its_false():
    """``full`` is a boolean on Claude too (a presence flag there): the filter follows each noun's declarations."""
    assert 'full' not in dict(runtime_controls(CLAUDE_SPECS, {'full': False}).peek_items())
    assert dict(runtime_controls(CODEX_SPECS, {'full': False}).peek_items()) == {'full': False}


def test_codex_and_claude_requests_with_a_flag_given_off_answer_as_omitted():
    codex_off = bind_declared_params(CODEX_SPECS, {'last': False, 'search': 'auth'}, transport='typed')
    assert dict(bind_query(None, codex_off).peek_items()) == {'search': 'auth'}
    claude_off = bind_declared_params(CLAUDE_SPECS, {'tokens': False}, transport='typed')
    resource, runtime = translate_request(None, claude_off, 'session/demo')
    assert (resource, dict(runtime.peek_items())) == ('session/demo', {})


def test_reading_a_control_reads_every_spelling_the_request_gave_it():
    """Reading ``where`` from the runtime controls reads its legacy word (Claude ``filter``) and a bare field key the
    binder folded into it (``?session~=x``), as reading it from the bound request does, so the unused-input ledger
    never names a spelling the answer applied. Claude's translate_request kept this; Codex's ``filter`` needs it too
    (BACK-2618), so the binder owns it."""
    for query, spellings in (('filter=demo', {'where', 'filter'}), ('session~=demo', {'where', 'session'})):
        bound = bind_declared_params(CLAUDE_SPECS, query, transport='uri')
        runtime = runtime_controls(CLAUDE_SPECS, bound)
        runtime._reads = set()
        assert runtime.get('where') == ['session~=demo']
        assert spellings <= runtime._reads, (query, runtime._reads)
    plain = runtime_controls(CLAUDE_SPECS, {'where': ['session~=demo']})  # a plain mapping has no spellings to carry
    assert plain._aliases == {}
