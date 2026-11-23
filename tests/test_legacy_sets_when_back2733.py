"""A legacy word whose target control depends on its value (``LegacySpelling.sets_when``, BACK-2733).

Git's ``ignore`` carried two meanings in one scalar: ``ignore=off`` turned blame's auto-ignore off, and ``ignore=SHAS``
named commits to suppress. Its replacements are two controls, ``--auto-ignore off`` and ``--ignore-commits SHAS``, so the
legacy word's target depends on its value. ``LegacySpelling.sets`` names the other controls a word sets, applied when
the owner's translated value is non-empty; ``sets_when`` is the predicate on the typed value that decides instead, so
``ignore=off`` binds ``auto-ignore=off`` and leaves its owner unset (its codec answers None), and ``ignore=SHA`` binds the
owner only. The conflicts stay generated (``_join_set_controls``): ``ignore=off&auto-ignore=on`` exits 2 naming both
spellings as typed. A repeatable owner's legacy word repeats (each value translates on its own), and a value that
translates to None adds no term.

Effect on the other nouns: none. No other entry declares ``sets_when``, so every existing ``sets`` entry keeps the rule
"sets when the owner's value is non-empty"; no other repeatable control has a legacy word that sets other controls, so
the per-value translation reaches only the new shape; the None filter on a repeatable control's legacy values changes
only a value a codec maps to None, which no other repeatable control's legacy codec does (checked below on every
declared noun).
"""
import pytest

from reveal.utils.query_binding import bind_declared_params, switch_value
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec


def _commits(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    prefixes = [part.strip() for item in values for part in str(item).split(',') if part.strip()]
    if not prefixes:
        raise ValueError('commits requires a commit hash prefix')
    return prefixes


def _is_off(raw):
    return isinstance(raw, str) and raw.strip().lower() == 'off'


OLD = LegacySpelling('old', flag='--old', codec=lambda raw: None if _is_off(raw) else raw,
                     sets=(('auto', 'off'),), sets_when=_is_off)
COMMITS = ParamSpec('commits', 'array', 'Commit prefixes', None, _commits, repeatable=True,
                    cli=CliBinding(('--commits',)), legacy=(OLD,))
AUTO = ParamSpec('auto', 'boolean', 'Auto on or off', None, switch_value, cli=CliBinding(('--auto',)))
DECLARATIONS = (COMMITS, AUTO)


def _bind(source, transport='uri'):
    """The bound commits (in sorted order: the spellings of a repeatable control join as one set of terms) and auto."""
    params = bind_declared_params(DECLARATIONS, source, transport=transport)
    commits = COMMITS.read(params)
    return (sorted(commits) if commits else commits), AUTO.read(params)


def test_the_value_decides_which_controls_the_word_sets():
    entry = COMMITS.legacy_entry('old')
    assert entry.translate('off') == {'commits': None, 'auto': 'off'}
    assert entry.translate('OFF ') == {'commits': None, 'auto': 'off'}
    assert entry.translate('abc1234') == {'commits': 'abc1234'}


def test_without_sets_when_a_word_sets_its_controls_when_its_owner_has_a_value():
    """Negative control: the existing rule (Markdown ``aggregate=F`` sets ``view=aggregate``) is unchanged."""
    field = ParamSpec('field', 'string', 'A field', None, str,
                      legacy=(LegacySpelling('aggregate', sets=(('view', 'aggregate'),)),))
    entry = field.legacy_entry('aggregate')
    assert entry.sets_when is None
    assert entry.translate('type') == {'field': 'type', 'view': 'aggregate'}
    assert entry.translate('') == {'field': ''}


@pytest.mark.parametrize('source,expected', [
    ('old=off', (None, False)),
    ('old=abc1234', (['abc1234'], None)),
    ('old=abc1234,def5678', (['abc1234', 'def5678'], None)),
    ('old=off&auto=off', (None, False)),  # an equal value is one setting
    ('old=abc1234&commits=def5678', (['abc1234', 'def5678'], None)),  # a repeatable control's spellings combine
    ('old=off&commits=def5678', (['def5678'], False)),
    ('commits=def5678&auto=off', (['def5678'], False)),
])
def test_the_uri_binds_the_controls_the_value_names(source, expected):
    assert _bind(source) == expected


def test_a_word_that_turns_auto_off_leaves_its_owner_unset():
    params = bind_declared_params(DECLARATIONS, 'old=off', transport='uri')
    assert 'commits' not in params._given and 'auto' in params._given
    assert params._implied_by == {'auto': 'old'}  # a later conflict or refusal names the word typed


@pytest.mark.parametrize('values,expected', [
    (['off'], (None, False)),
    (['abc1234', 'off'], (['abc1234'], False)),  # the repeated old flag: each value translates on its own
    (['abc1234', 'def5678'], (['abc1234', 'def5678'], None)),
])
def test_a_repeated_legacy_word_translates_each_value(values, expected):
    assert _bind({'old': values}, transport='typed') == expected


@pytest.mark.parametrize('source', ['old=off&auto=on', 'auto=on&old=off'])
def test_a_conflict_with_the_set_control_names_both_spellings(source):
    with pytest.raises(ValueError) as caught:
        _bind(source)
    message = str(caught.value)
    assert 'conflicting spellings' in message and 'auto' in message and 'old' in message, message


def test_a_conflict_names_the_flags_as_typed():
    from reveal.utils.query_binding import _normalize_aliases
    with pytest.raises(ValueError) as caught:
        _normalize_aliases(DECLARATIONS, {'old': ['off'], 'auto': 'on'}, {'old': '--old', 'auto': '--auto'})
    assert str(caught.value) == 'auto: conflicting spellings: --auto, --old'


def _declared_specs():
    from reveal.adapters.base import get_adapter_class, list_supported_schemes
    from reveal.cli.invocation import COMMANDS
    from reveal.cli.routing.declared import declared_adapter_class
    classes = {declared_adapter_class(name) for name, spec in COMMANDS.items() if spec.declared_adapter}
    for scheme in list_supported_schemes():
        try:
            classes.add(get_adapter_class(scheme))
        except ImportError:  # an optional dependency's adapter the host lacks declares nothing here
            continue
    for adapter in classes:
        for spec in getattr(adapter, 'PARAM_SPECS', ()) or ():
            if isinstance(spec, ParamSpec):
                yield adapter, spec


def test_no_other_noun_meets_the_new_shape():
    """The effect on every declared noun: an entry with ``sets_when`` is Git's ``ignore`` only; no other repeatable
    control's legacy word sets other controls (so per-value translation reaches nothing else); and no other
    repeatable control's legacy codec maps a value to None (so the None filter reaches nothing else)."""
    with_predicate, repeatable_sets, none_codecs = set(), set(), set()
    for adapter, spec in _declared_specs():
        for entry in spec.legacy:
            key = (adapter.__name__, spec.name, entry.name)
            if entry.sets_when is not None:
                with_predicate.add(key)
            if spec.repeatable and entry.sets and entry.sets_when is None:
                repeatable_sets.add(key)
            if spec.repeatable and entry.codec is not None and entry.sets_when is None:
                for sample in ('x', 'off', 'on', '1', '0', 'true', 'false'):
                    try:
                        if entry.codec(sample) is None:
                            none_codecs.add(key)
                    except ValueError:
                        continue
    assert {spec for _, spec, _ in with_predicate} <= {'ignore-commits'}, with_predicate
    assert repeatable_sets == set()
    assert none_codecs == set()


# A flag after a URI whose legacy word set the control: the conflict names the URI's word as typed, not the control the
# word set (git ``git://f?view=blame&ignore=off --auto-ignore on``). Before, it named ``auto-ignore=off``, a part the URI
# never typed; the mirror (a legacy flag after a URI that spells the control) was already named as typed.
AGG_FIELD = ParamSpec('field', 'string', 'A field', None, str,
                      legacy=(LegacySpelling('agg', flag='--agg', sets=(('view', 'agg'),)),))
VIEW = ParamSpec('view', 'string', 'A view', None, str, choices=('list', 'agg'), cli=CliBinding(('--view',)))


@pytest.mark.parametrize('specs,uri,typed,spelled,message', [
    (DECLARATIONS, 'old=off', {'auto': 'on'}, {'auto': '--auto'}, '--auto conflicts with old=off in the URI'),
    ((AGG_FIELD, VIEW), 'agg=b', {'view': 'list'}, {'view': '--view'}, '--view conflicts with agg=b in the URI'),
])
def test_a_flag_after_a_uri_names_the_uri_word_that_set_the_control(specs, uri, typed, spelled, message):
    from reveal.utils.query_binding import join_uri_and_flags, prepare_declared_params
    uri_params = prepare_declared_params(specs, uri, 'uri')
    typed_params = prepare_declared_params(specs, typed, 'typed', spelled=spelled)
    with pytest.raises(ValueError) as caught:
        join_uri_and_flags(specs, uri_params, typed_params, spelled=spelled)
    assert str(caught.value).startswith(message), str(caught.value)


def test_a_flag_after_a_uri_spelling_the_control_itself_is_named_as_before():
    """Negative control: with no legacy word in the URI, the part named is the control's own."""
    from reveal.utils.query_binding import join_uri_and_flags, prepare_declared_params
    uri_params = prepare_declared_params(DECLARATIONS, 'auto=off', 'uri')
    typed_params = prepare_declared_params(DECLARATIONS, {'auto': 'on'}, 'typed', spelled={'auto': '--auto'})
    with pytest.raises(ValueError) as caught:
        join_uri_and_flags(DECLARATIONS, uri_params, typed_params, spelled={'auto': '--auto'})
    assert str(caught.value).startswith('--auto conflicts with auto=off in the URI')
