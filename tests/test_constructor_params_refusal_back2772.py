"""An unknown key in an in-process params mapping is rule 3's invalid request (D21, BACK-2772).

``MetricsAdapter(path, params={'bogus': 1})`` raises ``UnsupportedOverrideError`` with the one shared message
(``unsupported_controls_message``), as an ``api.query`` keyword the noun does not declare already does; before, the
binder dropped the key and the default answer came back, so a caller still passing a key deleted at the cut would get
an answer instead of a refusal. A parsed query string (``parse_query_params``) binds as the URI it was parsed from:
the same refusal, or the same field filter on a noun whose where fields come from the data. Every declared noun is
measured, from the declarations (the conformance file's noun list and fixture), not a hand list.

Negative controls: every spelling a noun declares (name, alias, legacy word, CLI destination) passes the refusal; the
noun's default request constructs bound, parsed and as its URI; Trace's destination key ``root`` stays an accepted
constructor key until Trace retires at the cut (ruling S9)."""
import pytest

from test_vocabulary_conformance_back2654 import BASE, NOUNS, TARGETS, _adapter, workspace  # noqa: F401 -- the fixture
from reveal.errors import UnsupportedOverrideError
from reveal.utils.query_binding import bind_declared_params, unsupported_controls_message
from reveal.utils.query_parser import parse_query_params

UNKNOWN = 'zz_unknown'


def _target(noun):
    return TARGETS.get(noun, 'proj')


def _base(noun):
    return BASE[noun][1].lstrip('?')


def _outcome(build):
    try:
        build()
    except ValueError as exc:  # TypeError-derived UnsupportedOverrideError is a ValueError too
        return type(exc).__name__, str(exc)
    return 'constructed', ''


@pytest.mark.parametrize('noun', NOUNS)
def test_an_unknown_key_in_a_params_mapping_is_refused_with_the_shared_message(workspace, noun):
    adapter = _adapter(noun)
    with pytest.raises(UnsupportedOverrideError) as raised:
        adapter(_target(noun), params={UNKNOWN: '1'})
    assert str(raised.value) == unsupported_controls_message(adapter.PARAM_SPECS, [UNKNOWN])
    assert isinstance(raised.value, TypeError)  # still what an unexpected keyword is to a library caller


@pytest.mark.parametrize('noun', NOUNS)
def test_a_parsed_query_answers_as_the_uri_it_was_parsed_from(workspace, noun):
    adapter = _adapter(noun)
    query = f'{UNKNOWN}=1'
    uri = _outcome(lambda: adapter(_target(noun), query))
    parsed = _outcome(lambda: adapter(_target(noun), params=parse_query_params(query)))
    assert parsed == uri


@pytest.mark.parametrize('noun', NOUNS)
def test_every_declared_spelling_passes_the_refusal(workspace, noun):
    """A typed None is "not given": the binder may still refuse a value (a required control), never the key."""
    adapter = _adapter(noun)
    specs = adapter.PARAM_SPECS
    keys = {key for spec in specs for key in spec.spellings}
    keys |= {spec.cli.dest for spec in specs if spec.cli and spec.cli.dest}
    try:
        adapter(_target(noun), params=dict.fromkeys(keys))
    except UnsupportedOverrideError as exc:
        pytest.fail(f'a declared spelling was refused: {exc}')
    except ValueError:
        pass  # a value the binder refuses (Trace's required from, Metrics' limit=None) is not the key refusal


@pytest.mark.parametrize('noun', NOUNS)
def test_the_default_request_constructs_bound_parsed_and_as_its_uri(workspace, noun):
    adapter = _adapter(noun)
    base = _base(noun)
    bound = bind_declared_params(adapter.PARAM_SPECS, base, transport='uri')
    assert _outcome(lambda: adapter(_target(noun), params=bound)) == ('constructed', '')
    assert _outcome(lambda: adapter(_target(noun), params=parse_query_params(base))) == ('constructed', '')
    assert _outcome(lambda: adapter(_target(noun), base)) == ('constructed', '')


def test_trace_destination_key_root_stays_an_accepted_constructor_key(workspace):
    """TRACE_ADAPTER_GUIDE teaches ``TraceAdapter(path, params={"root": ...})``: ``root`` is ``from``'s CLI destination
    (ruling S9: accepted until Trace retires at the cut)."""
    adapter = _adapter('trace')('proj', params={'root': 'serve', 'depth': 2})
    assert adapter.query_params['from'] == 'serve' and adapter.query_params['depth'] == 2
