"""The binder's one empty-term rule (COMMAND_MODEL "Empty match term", Scott 2026-11-22, BACK-2736), on bare
declarations: every spelling of ``match`` and ``where`` and every control declared with ``TermValue`` refuse an empty or
whitespace-only term before the spellings are joined, named as typed; nothing else changes."""
import pytest

from reveal.errors import RequestValidationError
from reveal.utils.match_terms import TermValue, empty_term_message, is_blank_term
from reveal.utils.query_binding import apply_declared_overrides, bind_declared_params, prepare_declared_params
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ParamValueError, where_param


def _strings(value):
    return [value] if isinstance(value, str) else list(value)


MATCH = ParamSpec('match', 'array', 'terms', None, _strings, uri_codec='percent', repeatable=True,
                  cli=CliBinding(('--match',)), legacy=(LegacySpelling('body-contains', flag='--body-contains'),))
WHERE = where_param('filters', legacy=(LegacySpelling('filter', codec=lambda value: f'session~={value}'),),
                    convert=_strings)
SEARCH = ParamSpec('search', 'string', 'a standalone word', None, TermValue('search', '--match TEXT'), role='operation')
NAME = ParamSpec('name', 'string', 'not a term', None, str, cli=CliBinding(('--name',)))
SPECS = (MATCH, WHERE, SEARCH, NAME)


def _refused(call, message):
    with pytest.raises(RequestValidationError) as raised:
        call()
    assert str(raised.value) == message


@pytest.mark.parametrize('value', ['', ' ', '\t', ['auth', ''], ['', 'auth'], ('auth', ' ')])
def test_a_typed_empty_term_is_refused_naming_the_flag_typed(value):
    _refused(lambda: prepare_declared_params(SPECS, {'match': value}, 'typed', spelled={'match': '--match'}),
             '--match needs a term: --match TEXT')


def test_a_legacy_flag_is_named_as_typed():
    _refused(lambda: prepare_declared_params(SPECS, {'body-contains': ''}, 'typed',
                                             spelled={'body-contains': '--body-contains'}),
             '--body-contains needs a term: --match TEXT')


@pytest.mark.parametrize('query,message', [
    ('match=', 'match needs a term: --match TEXT'),
    ('match=%20', 'match needs a term: --match TEXT'),  # the control percent-decodes: a blank
    ('match=auth&match=', 'match needs a term: --match TEXT'),  # every occurrence, not the last one only
    ('match=&match=auth', 'match needs a term: --match TEXT'),
    ('body-contains=', 'body-contains needs a term: --match TEXT'),  # named before the repeats are gathered as match
    ('where=', 'where needs a term: --where FIELD OP VALUE'),
    ('filter=', 'filter needs a term: --where FIELD OP VALUE'),  # before its codec makes it session~=
    ('search=', 'search needs a term: --match TEXT'),  # declared with TermValue
])
def test_a_uri_empty_term_is_refused_naming_its_key(query, message):
    _refused(lambda: bind_declared_params(SPECS, query, transport='uri'), message)


def test_a_typed_keyword_override_is_refused_naming_the_keyword():
    params = bind_declared_params(SPECS, '', transport='uri')
    _refused(lambda: apply_declared_overrides(SPECS, params, {'where': ['']}),
             'where needs a term: --where FIELD OP VALUE')


@pytest.mark.parametrize('source', [{'match': 'auth'}, {'match': ['auth', 'token']}, {'where': 'session~=a'},
                                    {'search': 'auth'}, {'match': []}, {'match': None}])
def test_a_nonblank_or_absent_term_binds_as_before(source):
    """Negative controls: a term with text, several, an empty list (no term at all) and an omitted flag."""
    params = bind_declared_params(SPECS, source, transport='typed')
    assert {key: value for key, value in params.items() if value is not None} == \
        {key: _strings(value) if key in ('match', 'where') else value for key, value in source.items()
         if value is not None}


@pytest.mark.parametrize('query', ['name=', 'search=%20'])
def test_a_control_that_states_no_term_keeps_its_value(query):
    """``name`` is no term (an empty string binds as before); a raw-codec URI value is not decoded, so ``%20`` is the
    literal text it always was."""
    params = bind_declared_params(SPECS, query, transport='uri')
    key, _, value = query.partition('=')
    assert params[key] == value


def test_term_value_refuses_an_empty_term_when_called_directly():
    """A library caller validating the declaration (no binder) meets the same message."""
    with pytest.raises(ParamValueError, match='^search needs a term: --match TEXT$'):
        SEARCH.validate(' ')
    with pytest.raises(ValueError, match='search must be a valid string'):  # as string_value's NUL refusal reads
        SEARCH.validate('a\x00b')
    assert SEARCH.validate('auth') == 'auth'


@pytest.mark.parametrize('value,blank', [('', True), (' \t', True), ('a', False), (['a', ''], True), (['a'], False),
                                         ([], False), (True, False), (None, False)])
def test_is_blank_term(value, blank):
    assert is_blank_term(value) is blank


def test_the_message_names_the_spelling_and_the_term():
    assert empty_term_message('?search', '--match TEXT') == '?search needs a term: --match TEXT'
