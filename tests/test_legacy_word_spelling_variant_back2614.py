"""A hyphenated legacy word is also spelled with underscores (COMMAND_MODEL "Key spelling", BACK-2614).

Canonical keys are hyphenated and the underscore spelling is an accepted alias; a control declares its own variants in
``aliases``. A legacy word had no variant, so Markdown's ``?body_contains=`` (the underscore spelling of the retired
``body-contains``) was read as a front-matter field filter on an open-field noun instead of the body match.
"""
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import LegacySpelling, ParamSpec


def _strings(value):
    return [value] if isinstance(value, str) else list(value)


MATCH = ParamSpec('match', 'array', 'terms', [], _strings, repeatable=True,
                  legacy=(LegacySpelling('body-contains', flag='--body-contains'), LegacySpelling('contains')))
SWITCH = ParamSpec('merges', 'string', 'switch', None, str, legacy=(LegacySpelling('no_merges'),))


def test_a_hyphenated_legacy_word_is_spelled_with_underscores_too():
    assert 'body_contains' in MATCH.spellings
    assert MATCH.legacy_entry('body_contains') is MATCH.legacy_entry('body-contains') is not None


def test_the_underscore_spelling_binds_as_the_legacy_word():
    params = bind_declared_params((MATCH,), 'body_contains=auth', transport='uri')
    assert params['match'] == ['auth']
    typed = bind_declared_params((MATCH,), {'body_contains': 'auth'}, transport='typed')
    assert typed['match'] == ['auth']


def test_a_word_without_a_hyphen_and_an_underscore_word_gain_no_variant():
    assert MATCH.legacy_words.count('contains') == 1 and 'body-contains' in MATCH.legacy_words
    assert SWITCH.legacy_words == ('no_merges',)  # an underscore word is not hyphenated back (no 'no-merges')
